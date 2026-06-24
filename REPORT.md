# SQLite cold-start Prefetch 研究

> literature / full experiment推導見配套文件：
> - [overall_results.md](overall_results.md) — 全 P0 數據（strategy×workload×layout + N/K-sweep + RAM + churn + cadence）
> - [overall_strategies.md](overall_strategies.md) — 每個strategy的原理
> - [overall_workloads.md](overall_workloads.md) — Workload 定義

---

## Abstract

**摘要**——隨著 SQLite 廣泛deployment於行動裝置、IoT 與桌面應用，其 cold-start read效能逐漸成為使用者體驗的關鍵bottleneck，並衍生出兩個尚未被同時解決的core
挑戰：**prefetch 目標選擇（targeting）** 與 **preprocessing cost核算（cost-accounting）**。就 targeting 而言，作業系統與應用層皆缺乏對 SQLite B+tree internal page-type structure的visibility，盲目 prefetch 會將 I/O 浪費在大量無關 page 上，無法精準命中真正dominate cold-start cost 的少數關鍵 page；就 cost-accounting 而言，既有 prefetch strategy多僅優化 first-query latency，未將 prefetch 本身的 preprocessing overhead納入 end-to-end cold-start real cost evaluation，造成「first-query improvement幅度」與「real cold-start cost」之間的系統性misleading。SQLite 因其輕量embedded design、零組態deployment與廣泛 SQL compatibility，是此topic最具代表性的研究subject，然而現有 SQLite 相關literature多聚焦於writepath（fsync、WAL、journal mode），對 cold-start readpath的系統性分析較少；現有跨領域工作中，作業系統層的 readahead 僅依賴 sequential pattern detection、無法針對 page-type 做精準預判，DBMS 層的 buffer pool warming 又須侵入式修改 engine、且皆未將 preprocessing 計入real cost。為彌補此 gap，我們提出一套結合 **page-type-aware physical layout reorder** 與 **基於 mincore 的 targeted madvise prefetch** 的兩層 cold-start framework（下稱本framework）。在固定的 reference DB（**600k rows、102 MB**）上，我們依 SQLite B+tree role（interior/leaf）對 page 做精確classification，僅針對dominate cold-start cost 的 **0.35%（92個 interior page、共 368 KB）** 進行 prefetch，避免盲目 preload 帶來的 I/O 與 page reclaim 浪費，且整套design無需修改 SQLite internal。據我們所知，**本研究** 是第一個在 **empty OS page cache cold-start scenario下**（區別於 Yi et al. [2026] 處理的 hotspot-shift buffer cold-start），將 prefetch preprocessing overhead明確納入 end-to-end evaluation的 SQLite prefetch
研究（以下numbers全部來自 P0 master batch,authoritative表見 §5 / [overall_results.md](overall_results.md);全 cell `cold_pct`=0）：experiment顯示既有 cache-dump strategy（2f_slru,load整個 resident working set）雖能把 first-query latency 降到最低（**−79 ~ −90%**,A/orig 497→107 µs、C/orig 1058→102 µs），但其 **~6–7.5 ms 的 preprocessing overhead** 反讓 end-to-end cold start **慢上一個order of magnitude**——這個 trade-off 在既有 prefetch literature中長期被忽略。相對地,**page-type-aware 的structural / access-pattern prefetch（layers_5 / 2e_K10）** 以**極少 syscall** 取得 first-query **−30 ~ −85%**(file-tail uniform workload 上 access-pattern 與blind-load全部 interior 相當,皆約 **−47%**);關鍵在於 **end-to-end 取決於 baseline 有多慢**:慢 workload（C, baseline ~1058 µs）上 2e_K10 達 **e2e −56%（462 µs）**,而快 workload（A, baseline ~497 µs）上 warmer 的 preprocessing 反而蓋過 first-query 省下的時間。三條 robustness 軸——**50k write churn**(static t=0 hotset 不decay)、**cgroup `MemoryMax=20M`** memory壓縮(20M/unlimited ratio近 1.0)、與多-process **cadence re-warm**——下conclusion皆穩定。

**Index Terms**——SQLite, Cold-start latency, Prefetch, Page-type aware

---

## 1. Introduction

SQLite 是當今deployment最廣的database engine——根據 SQLite 開發團隊與學界合著的最新
evaluation [Gaffney+22]，全球**估計超過 1 兆個 SQLite database處於使用中**，幾乎
所有智慧型手機、瀏覽器、汽車與電視都內嵌 SQLite。在這個規模下，每一次
app startup、每一次裝置自休眠喚醒、每一次 background process 重新被排程，
使用者所感知的「第一筆查詢latency」（first-query latency）即由 SQLite
cold-start 性能直接決定。然而，SQLite cold-start readpath的系統性
優化在學術界仍少有著墨：現有 SQLite literature多聚焦於writepath（fsync、WAL、
journal mode），而跨領域的 prefetch 工作或不感知 SQLite internal structure（OS-level
readahead，繼承 [Smith 1978] 的 sequential pattern detection 主線），或要求
侵入式修改 engine 並側重 hot-set warming 而非 cold-start critical path
（DBMS-internal buffer pool warming，包含 InnoDB `buffer_pool_dump` 與最近
的 Pre-Buffer [Yi+26]）。

SQLite 將整個database以 4 KB page 為單位組織為 B+tree，每筆 query 必須從 root
走到 leaf，沿途的 **interior page** 必須全部駐留在 memory 中才能進一步存取
leaf。在 cold-start scenario下——OS page cache 為空、所有 page 皆須自 disk
fetch——這條 B+tree path 上的每一次 page miss 都觸發一次 5–100 µs 的
random I/O，使 cold first query 較 warm 狀態慢逾 200 倍。在本研究 600k row
的reference DB（102 MB；orig/ta 26,331 page、vacuum 25,613 page）上，P0 rerun的
cold first query baseline 落在 **~497–1058 µs** 區間（A 497 / B 725 / C 1058 µs @orig,
依 workload 與 layout 而定）。

本研究的關鍵observation是：**interior page 僅占整個 DB 的 0.35%**（92 個 page、共
368 KB），卻負擔所有 query path traversal cost。若能在 first query 之前將
這 368 KB 的關鍵 page 主動load OS page cache，cold-start 的 random I/O 即
可被 amortize 至 sequential prefetch 操作。據此，我們提出一套針對 SQLite
cold-start 的**兩層 prefetch framework**（下稱本framework）：第一層為
**page-type-aware physical layout reorder**——在 binary 層級重寫 SQLite file、
將 92 個 interior page 集中至file head連續 slot 並 patch 所有 page-number
reference（跨頁 pointer、`sqlite_master.rootpage`、freelist）；第二層為
**基於 `mincore()` 的 targeted madvise prefetch**——透過 page-type
classification 僅對dominate cold-start cost 的 interior 集合下達
`madvise(MADV_WILLNEED)`，避免盲目 preload 引發的 I/O 與 page reclaim
浪費。整套design**無需修改 SQLite internal**，作為 application-side tool deployment。
此外，我們將 prefetch preprocessing overhead顯式quantify、並與 first-query latency
共同 sum 為 end-to-end cold-start real cost——此 cost-accounting framework揭露
出 prefetch literature中長期被忽略的 trade-off。

### 1.1 Research Questions（研究問題）

本研究環繞四個 research question，對應前述兩大挑戰（targeting / cost-accounting）：

- **RQ1（targeting）**：cold-start cost 集中在哪些 page？只針對 page type（B+tree interior）做 prefetch，first-query latency 能省多少？
- **RQ2（cost-accounting）**：把 prefetch 自身的 preprocessing overhead 算進去後，end-to-end cold-start 是否仍改善？在什麼條件下贏、什麼條件下反而變差？
- **RQ3（selection vs delivery）**：prefetch 效益可拆成「選對哪些 page（selection）」與「真的把 page 載進 cache（delivery）」；async `madvise` hint 在 first-query 之前實際交付多少？與強制載入（pread oracle）差多少？
- **RQ4（robustness）**：上述效益在 write churn 造成的 layout 漂移、RAM 壓力（cgroup）、多 process 共享 cache 下是否穩定？

下列貢獻 C1–C4 與 §3.5 的 selection–delivery 拆解共同回應這四個問題。

本文的主要貢獻如下：

> **以下貢獻numbers全部依 P0 master batch 更新(authoritative表見 §5 / [overall_results.md](overall_results.md))。**

- **(C1) Type-aware layout rewriter**：實作並validation在 binary 層級reorder SQLite
  file 並修補所有 page-number reference 的可行性與正確性。P0 下structural
  prefetch(layers_5)在 A 取得 **first-query −30%**(497→350 µs);**但 e2e
  取決於 baseline**——快 workload(A)上 warmer preprocessing 蓋過省下的時間、
  e2e 反而變差,e2e 真正有改善的是慢 workload(見 C3/C2)。
- **(C2) Access-pattern frugality**：基於 `mincore()` snapshot 的
  access-history prefetch(2e_K10)用**極少 syscall** 取得 first-query
  **−30 ~ −85%**;在 file-tail uniform(B)上與blind-load全部 interior 相當(皆約
  **−47%**);在慢 workload **C 上 2e_K10 達 first-query −85%、e2e −56%(462 µs)**——
  顯示「access-pattern」在 e2e 上最有效益。
- **(C3) Preprocessing cost-accounting framework**：據我們所知，首次將 prefetch
  preprocessing 顯式納入 SQLite cold-start end-to-end evaluation（區別於
  [Yi+26]）。P0 證實既有 cache-dump strategy(2f_slru)雖把 first-query 降到最低
  (**−79 ~ −90%**),但其 **~6–7.5 ms preprocessing** 反讓 end-to-end cold
  start **慢一個order of magnitude**——此 trade-off 在既有 prefetch literature中長期被忽略。
- **(C4) Robustness 三維validation**：50k write churn 後 static t=0 hotset 不decay
  (C 上 2e_K10 跨 checkpoint 持平 ~82–86 µs vs baseline ~580);cgroup
  `MemoryMax=20M` memory壓縮下 first-q 幾乎免疫(20M/unlimited ratio近 1.0);多 process
  cadence re-warm下,cadence ≤
  query gap 即可可靠 warm cache。

本文後續組織如下：§2 闡述 SQLite cold-start mechanics、本研究採用的
「warm process, cold data」measurement模型，以及 related work 定位；§3 描述
測試 DB、workload、benchmark harness、實驗假設與統計方法；§4 分述三類strategy（layout /
prefetch / memory-sharing）的design選擇；§5 為 experiment and evaluation，
其中 **§5.5 為本文core trade-off observation**；§6 為 discussion，含 key
findings、robustness validation、實務recommendation與 limitations；§7 future work；§8
conclusion；§9 references。

---

## 2. Background and Related Work

### 2.1 SQLite B+tree storage and cold-start mechanics

SQLite 的整體架構（SQL compiler / VDBE / B-tree / pager / OS interface）
與儲存格式詳見其官方文件與 [Gaffney+22] 提供的最新full evaluation——後者由 SQLite
創始團隊（Hipp、Kennedy、Brasfield @ sqlite.org）與 UW-Madison 學界合著，
是目前學術界對 SQLite 最 authoritative 的描述。本節僅萃取與 cold-start
read path相關的細節。

SQLite 以單一 file 存放整個database、internal以 **4 KB page** 為基本單位，每個
logical table 或 index 對應一棵 B+tree。Page 依role分為兩大類：**interior
page**（B+tree internal節點，儲存 key 與 child pointer，再細分 `interior_table`
與 `interior_index`）與 **leaf page**（實際資料 row 或 index entry）。本
研究使用的 reference database 含 600,000 row，產生 **92 個 interior page**
（51 個 table interior + 41 個 index interior，占整 file 大小 0.35% /
368 KB）與 26,239 個 leaf page。

執行任一 query（如 `SELECT payload FROM items WHERE id=?`）時，SQLite 從
B+tree root 逐層下行至 leaf；走full條 path 上的所有 interior page **必須
駐於 memory**，任一缺席即觸發一次磁碟 random read（典型latency 5–100 µs per
fault）。需注意 SQLite 的 **`page 1` 為 DB header 與 `sqlite_master`
（schema）的 b-tree root**——使用者表的 B+tree root 落在 `sqlite_master.rootpage`
記載的某個低頁號、不必為 1。本研究定義的 **cold-start** 即「OS page cache
為空時的第一筆 query」（measurement協定詳見 §2.2）；此時走 B+tree path 必觸發多次
major page fault，相較 warm 狀態高出**兩個order of magnitude以上**的 first-query latency
（具體quantify見 §5）。

### 2.2 Cold-start measurement protocol

嚴格 textbook 的 cold-start 要求機器剛開機、process 從未存在、所有軟體層
cache 皆空——這在 benchmark 環境每 cell reproducible是不可行的。本研究改採
**「warm process, cold data」protocol**：process 層級的 long-lived structure
保持 warm，但 process 以下的每一層 software cache 在每次measurement前都歸零。

具體而言，每個 measurement cell measurement前的狀態如下表：

| 層級 | measurement時狀態 | 對照嚴格 cold-start |
|---|---|---|
| **OS page cache (DB 內容)** | 透過 `/usr/local/sbin/drop-caches` setuid wrapper 全機 drop (`sync; echo 3 > /proc/sys/vm/drop_caches`)，並以 harness built-in `--verify-hotset`（`mincore`，emit `verify_cold_pct`）validation ≈0% resident | 完全空 |
| **磁碟 I/O** | `majflt > 0` validation確實到 disk | 必須 physical I/O |
| **SQLite handle / pager** | 預先開好（`PRAGMA cache_size=0`、statement 已 prepare） | 從未 open |
| **`mmap()` 區域** | 預先建立（mapping 在、page 未 fault） | 從未呼叫 |
| **CPU 指令 cache / TLB / branch predictor** | Warm（harness 程式碼跑過多輪） | 全部冷 |

「warm process」的三項刻意妥協服務三個目的：(1) **更貼近實際deployment**——
mobile app / server worker 的 SQLite 多半已 load、schema 已 introspect，
使用者感知的 cold-start 是 data cold 不是 process cold；(2) **isolation研究
變數**——SQLite parser/optimizer startup時間是相對 prefetch 機制standalone的常數，
混入只會增加 noise；(3) **可重複性**——「process from scratch」會多出
~50–200 µs 的 SQLite 初始化 noise，需要更多 reps 才壓得住。

Warm CPU caches 帶來的下偏小（first-q 估 1–3 µs，相較典型 cold-start
baseline < 1%）。Harness 可選擇更嚴格的模式（`--sqlite-open-timing=after-cold`、
`--schema-init-timing=after-cold`）；本文全部 report 預設模式以利 cross-cell
comparison，**P0 跟 strict 模式 between-mode delta 的quantify列於 §6.4 limitations**。

> **2026-06-19 P0 pipeline 統一**（措辭 2026-06-22 校正）：上表 OS page cache 那層的機制（全機
> `drop-caches` wrapper + harness built-in `--verify-hotset` 量 `cold_pct`/`delivery_pct`，
> 非外部 residency_checker）即為本研究採用的 P0 pipeline。本 paper 所有 §5 / §6
> 數據均依此 protocol measurement；歷史上使用 per-file `posix_fadvise` /
> `sudo drop_caches` 量出的numbers已由 P0 master rerun 取代。

### 2.3 Related Work

本節分五類整理跟本研究最相關的既有工作，每段最後點出「跟本 paper 的差別」。

#### 2.3.1 OS-level prefetching & readahead

Linux kernel 的 readahead 機制（`mmap` MADV_WILLNEED / MADV_SEQUENTIAL、
`posix_fadvise(POSIX_FADV_WILLNEED)`、kernel `do_page_cache_ra`）跟 SSD-aware
I/O scheduling 的相關literature。

**歷史 lineage**：sequential prefetching 的概念可追溯至 [Smith 1978]，
原始在 DB 層提出 **One Block Lookahead (OBL)**；Linux kernel readahead
繼承這條概念主線但下放到 OS 層、操作對 DB-internal structure不可見的 file
offsets——也因此只能做 sequential pattern detection、無法 page-type aware。

候選 reading：
- Linux kernel mm `readahead.c` design notes
- "Anticipatory I/O Scheduling" (USENIX ATC '04, Iyer & Druschel) （經典文獻）
- "I/O Behavior of NAND Flash" 系列（NVMe readahead、SSD pre-read）

**跟我們的差別**：OS readahead 是 **sequential pattern detection**（Smith
'78 lineage）；我們的strategy是 **page-type aware**（知道 SQLite interior
page 在哪），用 madvise 做明確 hint 而不是依賴 kernel 自動推測。

#### 2.3.2 Database buffer pool warming

Oracle/PostgreSQL/DB2 都有「warmup tool」把 hot pages 預先載進 buffer
pool；學術界這條 lineage 的兩個 foundational anchor 是：

- **[Effelsberg & Härder 1984]** "Principles of database buffer management"
  *ACM TODS* 9(4):560–595——DB buffer mgmt 的奠基論文，建立了 replacement /
  prefetching / reference-count 等基本design dimension。**Pre-Buffer [Yi+26] 跟
  Chen+21 都引這篇**。
- **[Smith 1978]** "Sequentiality and prefetching in database systems"
  *ACM TODS* 3(3):223–247——**OBL (One Block Lookahead) 的原始出處**；
  也是 §2.3.1 提到的 sequential prefetching 概念主線的源頭。**Pre-Buffer**
  在 Database Prefetching 段引此為 prefetch 開山之作；**Chen+21** 把
  OBL 擴充為 K-page LookAhead 當作 ML 模型對照 baseline。

**生產系統的代表例：MySQL/InnoDB buffer pool dump/load** —— InnoDB 提供
`innodb_buffer_pool_dump_at_shutdown` / `innodb_buffer_pool_load_at_startup`，
關機時把 buffer pool 內的 page id 清單 dump 下來、重啟時整份重載（MySQL Reference
Manual，見 §9.2）。這正是「blind 整份重載 resident working set」的 engine-internal
版本——與本研究的 **2f SLRU（§4.2）同一個 pattern**，差別只在 InnoDB 內建於
engine、本研究在 application side 且不修改 SQLite。與多數 buffer-pool warming 工作
一樣，它**未把重載本身的 preprocessing 成本計入 critical-path latency**——正是本
研究 §5.5 cost-accounting 要補的空白。

近年 ML-based 路線（已在前段討論）：[Chen+21] / [Yang+20 Leaper, PVLDB
13(12)] 用 NN 預測 page access；Pre-Buffer [Yi+26] 用 Jaccard similarity
做 hotspot matching。所有這些工作都建立在上述 Smith '78 + Effelsberg '84
的傳統上。

**跟我們的差別**：buffer pool warming 用 DBMS 自有 cache；我們用 OS page
cache + mmap、不修改 SQLite，把 prefetch 變成 application-side tool。

**Pre-Buffer [Yi et al. 2026]** —— 最近最相關，但解的是**不同的 cold-start
問題**。他們提出 workload-aware buffer prefetching framework，針對週期性 workload
下的 **"buffer cold-start"** ——其定義為 **hit-rate 在 hotspot shift 後的恢復
時間**（curve 從谷底回到 steady state 的秒數），prefetch 由standalone background
thread 在 hit-rate 跌幅 ≥10% 後觸發，且使用 **Direct I/O 繞過 OS page cache**。
本研究處理的是 **OS page cache 為空時的 first-query latency**——prefetch
位於 user-facing critical path 上、與 first-query 直接競爭時間，因此
preprocessing overhead無法藏在 background。值得注意的是，Yi et al. 在批評既有
ML-based prefetcher [Chen et al. 2021] 時明確指出："*it is also necessary
to consider the direct and indirect impact of the prefetch module on
system performance*" ——但其 evaluation（hit-rate recovery time + 總
execution time）並未將 prefetch overhead 與 query latency 分離。

**Chen+21 原文validation**：細讀 [Chen et al. 2021] 證實 Pre-Buffer 的批評公允——他們
在 MySQL 上跑 TPC-H/DS/SSB benchmark 收集 page access trace 訓練 DNN/CNN/RNN/
LSTM/Multi-Model ensemble（8–20M 參數）預測下一個 page offset，但 (1) 訓練資
料明確採用 **"with warm-start"** trace（已避開 cold-start scenario）、(2) evaluation
只報 next-page prediction 的 **precision/recall**（Multi-Model 76–87% vs
LookAhead 20%），從未measurement NN inference 對 query latency 的衝擊、也沒measurement錯誤
prefetch 的 wasted I/O cost——即便他們自己在 §IV-B 親口寫："*wrong prefetching,
though asynchronous, will hurt the performance of the system due to the
extra I/O cost.*"並為此design了 Decision Module。Chen+21 的 gap 是 **cost-awareness
在 design 但缺席 evaluation**；Pre-Buffer 的 gap 是 **evaluation 採用 system-level
混合指標、未分離 prefetch overhead 與 query latency**。本研究的 preprocessing-aware
end-to-end methodology 同時 close 這兩個 gap：在 SQLite cold-start scenario下把
prefetch preprocessing 與 first-query latency **顯式分開測量**、再 **sum 為
end-to-end cold-start real cost**。

#### 2.3.3 SQLite / mobile / embedded DB optimization

SQLite 作為 mobile / embedded DB 的事實標準，已有相當數量的學術工作針對其
在 mobile platform 上的效能bottleneck做優化。值得注意的是，**這條 lineage 幾乎
全部聚焦於writepath**（write amplification、fsync、journaling、autocommit
overhead），與本研究的 cold-start read latency 在問題定義、優化機制與
hardware hypothesis上皆正交：

- **[Oh+15] SQLite/PPL** (PVLDB 8(12), VLDB '15) ——專為 mobile app 的
  autocommit write workload design，finding「single message 常觸發 ≥10 次 page
  write、write amplification > 100×」。解法是 **深度 fork SQLite**（B+tree
  module、pager、buffer management policy、journaling 全部改）並搭配
  **custom PCM hardware (UMS board)**——在 PCM 中為每個 data page 維護 per-page
  log，將多次 successive page writes 替換為小型 log records。回報相較
  vanilla SQLite 達 **8–24× throughput improvement**。
- **[Kang+13] X-FTL** (SIGMOD '13) ——同樣聚焦 SQLite 在 mobile flash 上
  的 transactional write 性能，但介入層在 **FTL (Flash Translation Layer)**。
- **[Kim+12] "Revisiting Storage for Smartphones"** (USENIX FAST '12)
  ——mobile storage performance 的奠基分析論文，建立「SQLite + journaling
  on flash」是 mobile I/O 主要bottleneck的認識。
- **[Jeong+13] "I/O Stack Optimization for Smartphones"** (USENIX ATC '13)
  ——mobile I/O stack 層級的優化，同樣是 write-side focus。

工程界（非 academic）相關討論則散落於 Google Android team、Meta（Lithium /
Trident）、Apple Core Data 的 WWDC talks 等資源，幾乎全部涉及 page size /
journal mode / mmap / WAL 等writepath參數調校。

**跟我們的差別（三條軸）**：
1. **問題dimension**：上述工作全部處理 **steady-state write throughput / write
   amplification**；我們處理 **first-query cold-start read latency**——一個
   未被學術界系統性分析過的dimension。
2. **介入侵入性**：[Oh+15] / [Kang+13] 深度修改 SQLite engine 甚至 FTL；
   我們**完全不修改 SQLite internal**，作為 application-side tool deployment。
3. **hardware hypothesis**：[Oh+15] 需要custom PCM hardware (UMS)；我們在 **commodity
   hardware**（Ryzen 9950X + NVMe SSD）上運作，無特殊hardware需求。

此外，本研究的 type-aware layout rewriter (§4.1.1c) 也是該領域 novel——
既有 SQLite mobile-optimization fork 無 page-type aware physical reorder
的design。

**[Gaffney+22] SQLite: Past, Present, and Future** (PVLDB 15(12)) ——
SQLite 創始團隊與 UW-Madison 合著的最新full SQLite evaluation，涵蓋 OLTP (TATP) /
OLAP (SSB) / blob 三種 workload，並以 Bloom filter Lookahead Information
Passing (LIP) 把 SSB 加速 4.2×。**重要的是其 evaluation 方法論**：所有 SSB
查詢前都明確執行 `SELECT *` 預熱 buffer pool（原文 §4.2.1: "*before running
the SSB queries, we scan each table with a SELECT * query, ensuring that
the buffer pool is populated*"）。這是學界標準作法，但其副作用是
**cold-start latency 被當作 noise 系統性地排除在 measurement 之外**——即便
是 SQLite 創始團隊自己參與的最新 academic evaluation，也未對 cold-start readpath
做系統性quantify。這直接validation本研究的 niche：cold-start read latency 不僅在
mobile SQLite write優化literature中缺席（§2.3.3 上述 4 篇），在 SQLite 整體
academic evaluation literature中亦被視為應規避的測量noise。本研究是針對此空白的
直接回應。

#### 2.3.4 SSD / NVMe page-aware optimization

把 page-type / hot-cold awareness 下放到 SSD 層：
- **NVMe Stream Directives** (NVMe spec 1.3+)
- **ZNS (Zoned Namespace) SSDs**
- **F2FS / Multi-stream SSD** 系列（USENIX FAST, SOSP）
- **FEMU** (FAST '18, Li et al.) — 我們未來 Level 2 工作的 emulator

**跟我們的差別**：本 paper Level 1 全部在 application + OS 層；規劃中的
Level 2 才下放到 SSD line / namespace isolation——是 future work。

#### 2.3.5 Memory-mapped DB & virtual-memory-assisted caching

本研究的 prefetch strategy大量使用 `mmap()` + `mincore()` + `madvise()` 這組
OS primitive，因此與「以 virtual memory 為基礎的 DB caching」這條 lineage
直接相關。值得區分本研究與該 lineage 在**使用意圖**與**操作規模**上的根本
差異：

**File-backed mmap as DBMS substrate**：
- **[LMDB]** (Lightning Memory-Mapped DB) ——mmap-only DBMS 的代表，無自有
  buffer pool，把整個 DB file mmap 進 process address space，依賴 OS page
  cache 做 caching。
- **[Crotty+22]** "Are You Sure You Want to Use MMAP in Your Database
  Management System?" (CIDR '22) ——對 mmap-as-DBMS-substrate 的系統性
  批判：(1) DBMS 失去 eviction control（無法做 ARIES-style 事務）；(2)
  無 async I/O 介面、I/O stall 不可預測；(3) I/O 錯誤處理困難；(4) Linux
  kernel mmap path在 fast NVMe 上 scalability 不足。

**Virtual-memory-assisted, DBMS-controlled caching**（Crotty+22 的後續回應）：
- **[Leis+23] vmcache + exmap** (SIGMOD '23) ——用 **anonymous mmap**（不
  是 file-backed）+ DBMS 控制的 `madvise(MADV_DONTNEED)` eviction + custom
  Linux kernel module (exmap) 解決 Crotty+22 點出的 scalability 問題（TLB
  shootdown @ >1M page evict ops/s、page allocator 競爭）。回報達 286 M
  alloc+free ops/s（vs vanilla Linux 1.5 M ops/s）。

**Mincore-based tooling**：
- **vmtouch** / **fincore** ——標準 mincore-based tool，僅做整個 file 的
  page-cache residency 查詢與全頁 preload，不感知任何 DB-internal structure。

**跟我們的差別（兩條軸）**：

1. **使用意圖**：[Crotty+22] / [Leis+23] / [LMDB] 都把 mmap + madvise 當作
   **DBMS storage substrate**（page cache、eviction 控制、transaction
   semantics）；我們**完全不是**——SQLite 自有 pager / B+tree / journal，
   我們**不取代**任何一部分。我們把 mmap + `mincore()` + `madvise(MADV_
   WILLNEED)` 當作**外掛在 SQLite 旁的 prefetch hint 通道**，純粹為了在
   first-query 前把 interior page 帶進 OS page cache。因此 Crotty+22 對
   mmap-as-DBMS-substrate 的批評（eviction control、ARIES recovery、I/O
   error handling）跟本研究**根本不適用**——這些都是 SQLite engine
   本身已處理的事，與我們的 prefetch 通道無關。
2. **操作規模**：[Leis+23] 處理的是**高 throughput steady-state OLTP**
   scenario下的 `madvise(DONTNEED)` 規模化問題（百萬次 evict ops/s、TLB
   shootdown 成為bottleneck）；本研究的 cold-start prefetch 每次只下 ~92 個
   `madvise(WILLNEED)` call（與 layout_N strategy中 N 等價），且為 cold-start
   一次性操作，**操作frequency比 vmcache 解的問題低 4 個order of magnitude以上**，碰不到
   TLB shootdown / page allocator 的 scalability 邊界。

**正面 design rationale**——值得強調的是，[Crotty+22] 在其 §6 conclusion明確列出
「**maybe use mmap**」的兩項條件：
- **(a) workload 為 read-only**
- **(b) working set（或整個 DB）fit 進 memory**

本研究的 cold-start scenario**完全滿足這兩項**：first-query 為唯讀；reference
DB 102 MB 遠小於主機 RAM (62 GiB)；experiment中亦透過 cgroup `MemoryMax=20M`
額外validation了壓縮scenario（§6.2.2）下 first-q 仍保持穩定。換言之，**Crotty+22
自己訂的 mmap-OK criteria 直接背書本研究的 use case**。此外，相較傳統
user-space buffer pool design，mmap path**避免了 OS page cache 與 application
buffer 之間的資料複製**，memory footprint 更小——這也是 [Crotty+22] §3.4
親口承認的 mmap 優勢（"*mmap-based file I/O also results in lower total
memory consumption, as the data is not unnecessarily duplicated in user
space*"）。對 mobile / embedded SQLite deployment scenario而言，這個 memory 優勢非
trivial。因此本研究選擇 mmap-based prefetch hint 通道是 deliberate
design choice，而非 mmap-as-substrate 妥協。

進一步：既有 mincore-based tool（如 vmtouch）只做全 page-cache 整檔
preload，**沒有 page-type 區分**；本研究的 contribution 是把 `mincore()`
snapshot 與 SQLite B+tree 的 **page-type classification** 結合，做出 2d/2e
(interior + top-K leaves) 的 frugal prefetch——僅loaddominate cold-start cost
的少數關鍵 page，避免整檔 preload 的 I/O 浪費。

---

## 3. Methodology

### 3.1 Test database

所有experiment shared一個固定的 reference database（由 builder script 產生），
schema 為 `items(id INTEGER PRIMARY KEY, k1 INTEGER, k2 INTEGER, payload
BLOB(100))` 加上 secondary index `idx_items_k1k2 ON items(k1, k2)`，含
600,000 row：

| 項目 | 數值 |
|---|---|
| Page 大小 | 4 KB |
| 總筆數 | 600,000 rows |
| 總 page 數 | 26,331 |
| DB 總大小 | ~102 MB |
| **Interior page** | **92 個 / 368 KB / 0.35%** |
| Leaf page | 26,239 個 / ~102 MB / 99.65% |

如 §2.1 所述，interior page 雖僅占 0.35%（368 KB）卻是每筆 query 必經
之路；本研究的core命題即是「如何最有效率地預載這 368 KB 進 OS page cache
以消除 cold-start 的 random I/O」。三種 layout（1a / 1b / 1c）shared同一份
schema 與 600,000 row 內容，僅 page physical排列不同（詳見 §4.1 與圖 1）。

![三種 layout 下 92 個 interior page 在file裡的位置](figures/out/01_page_distribution.png)

*圖 1：interior page（紅色）在三 layout 下的physical分佈。**1a 原始**：散落
整個 102 MB；**1b VACUUM**：略集中但仍散；**1c type-aware**：全部集中於
file head前 400 KB，可被 sequential prefetch 一次涵蓋。*

### 3.2 Workloads

研究選用 4 種代表性 workload 覆蓋不同的 access pattern 軸：

| 名稱 | 特性 | 典型deployment scenario |
|---|---|---|
| **A** | Zipfian point read（集中查少數熱門資料）| App 首頁、常開的聯絡人 |
| **B** | Uniform random point read（uniform 隨機讀）| 隨機抽樣、爬蟲 |
| **C** | High-key uniform read（只查最新加入的file tail資料）| 剛收到的訊息、剛拍的照片 |
| **D** | Write-heavy churn generator | 模擬 DB 被持續 write（§6.2.1 churn experiment）|

A / B / C 分別涵蓋三個正交的「hotspot分布」dimension（read skew、uniform、file tail
locality）；D 不直接量 latency，是 §6.2.1 churn experiment用於製造 layout 漂移
的 write generator。每個 workload 的full定義（key range、Zipf parameter α、
ops 數）見 [overall_workloads.md](overall_workloads.md)。

Workload A 與 B 的 op string 格式與分布參考自 [YCSB-cpp](https://github.com/ls4154/YCSB-cpp)
（C++ port of YCSB）——A 對應 YCSB-C profile（read-only Zipfian over single
table），B 對應 YCSB-A 的 read 部分（uniform random）。本研究延用 YCSB 風格
的 op string 格式（`read <key>` / `update <key>` / `scan <key> <len>`），讓
`benchmark_harness` 一行一 op 直接解析。C 與 D 為本研究自行design（file tail
locality 與 write-heavy churn generator），YCSB 標準 6 個 profile 並無對應。

### 3.3 Benchmark harness

所有 measurement cell 透過自研的 `benchmark_harness`（C 程式）執行，**嚴格遵守
§2.2 表定義的 P0 cold-start protocol**。每個 cell 的執行
順序如下：

| 階段 | 動作 | P0 protocol 對應 |
|---|---|---|
| **(i) Warm-process setup**（measurement前一次性）| `mmap(db, PROT_READ)` 建立 read-only mapping；`sqlite3_open()` 開啟 connection 並 `PRAGMA cache_size=0`；`sqlite3_prepare_v2()` 預編譯所有 workload 內出現過的 statement | §2.2 表 SQLite/mmap 行（process 層保持 warm）|
| **(ii) Pre-cold residency snapshot** | `mincore()` snapshot write record file，作為 cache 清空前的 baseline | measurement前 sanity |
| **(iii) Cold-start clearing**（P0 第①+②層）| `--cold-advice dontneed` 對 mmap region 依序執行 `madvise(MADV_COLD) → MADV_PAGEOUT → MADV_DONTNEED`；緊接 `--drop-caches-script /usr/local/sbin/drop-caches` 進行全機 `sync; echo 3 > /proc/sys/vm/drop_caches`；接著 **harness built-in** `--verify-hotset` 做一次 `mincore`，emit `verify_cold_pct`（應 ≈0；>1% 的 cell 由 runner 在彙整時剔除，harness 不自動 abort）| §2.2 表 OS page cache 行 |
| **(iv) Post-cold prefetch**（P0 第③層）| `--post-cold-script` 執行統一delivery engine **`warmer`**（`WARM_METHOD=pread` 或 `fadvise`，hotset 由離線的 `prefetch_layers/access/slru` 預先產生並freeze，見 §3.4.1）；warmer 在 stderr 自報 `warmer_us`；**baseline cell 不帶 post-cold-script（不做任何 prefetch）** | §2.2 P0 banner 第③層 |
| **(v) Delivery residency check** | drop-caches→prefetch 後、first-query之前，harness 再做一次 `mincore`（~µs），emit `verify_delivery_pct`＝first-query實際看到的hit rate（µs 級，async readahead 來不及多載 → 不污染 `fq_async`，修復漏洞 2）| prefetch coverage validation |
| **(v′) CPU frequency暖機** | `--warm-cpu-ms`（預設 10ms）對 taskset 釘定的core busy-spin，把 amd-pstate 拉到滿頻**才**進first-query，消除「最快 cell 受 freq ramp 懲罰最重」的偏差；spin 在計時區外 | measurement前 sanity |
| **(vi) Timed workload execution** | `clock_gettime(CLOCK_MONOTONIC)` 逐 op 量 `sqlite3_bind → step → reset`，寫 `first_query_us` 與 cumulative `avg_us`；`getrusage` delta 記 `total_majflt/minflt`。**F8**：harness `--require-read-first` 確保 op[0]=read，否則 abort（first-query 才是乾淨 TTFQ）| measurement階段 |

每個 cell 對**同一 hotset** 跑 **pread（oracle）/ async（hint）雙臂**，外加每 (workload,layout) 一個 **baseline（無 prefetch）cell** 當分母。輸出欄位：`verify_cold_pct`、`verify_delivery_pct`、`fq_pread`、`fq_async`、`delivery_pct`、`preproc_us`（= `warmer_us`）、`e2e_us`（= preproc + fq）、`avg_us`、`majflt`、`minflt`，每筆並記 `ra_kb` 與當下 `loadavg/memavail`。

> **P0 嚴格性聲明**：cold-clear (drop-caches)一律 `madvise chain（process-local）+ 全機 drop-caches`，residual validation一律走 **harness built-in `--verify-hotset`**（兩道 `mincore`：cold ① 應 ≈0、delivery ② 即first-queryhit rate），**不**用外部 `residency_checker`——後者的 ~100 ms 間隔會讓 async readahead 多載、污染 `fq_async`（漏洞 2），故只保留作離線/regen 用途。`cold_pct>1%` 的 cell 視為冷清失敗、由彙整剔除。歷史上採用 per-file `posix_fadvise(DONTNEED)` 或 `sudo drop_caches` 量出的numbers一律標記為 pre-P0、由 master rerun 取代。

### 3.4 End-to-end cold start metric

`benchmark_harness`（§3.3）只measurement SQL query 本身的 wall-clock 時間
`first_query_us`，**不包含** prefetch tool startup、發 `madvise()` 等
preprocessing overhead。然而從使用者角度看，cold-start 的reallatency是「按下按鈕
到看到結果」的end-to-end時間，必須把 prefetch preprocessing 算進去。本研究因此
定義：

$$
\text{cold-start}_\text{e2e} = \text{prefetch\_us} + \text{first\_query\_us}
$$

其中 P0 的 `prefetch_us` ＝統一delivery engine **`warmer`** 的 preprocessing wall-clock
（warmer 在 stderr 自報 `warmer_us=...`，pread/async 兩臂同一engine、只差 sync/async），
與 `first_query_us` 在同一個 P0 cell、同一 rep 內依序measurement。

此分離design有三項依據：(1) `first_query_us` 以 `clock_gettime(CLOCK_MONOTONIC)`
包住 SQLite `step()` 直接measurement，乾淨且 reproducible；(2) `prefetch_us` 不嵌入
`benchmark_harness` 而由 `warmer` 自報，因為 `madvise/fadvise(WILLNEED)`
是 async hint、不等 I/O 完成即 return（見 §2.3.5 / §4.2），warmer 的
wall-clock 跟線上跑時order of magnitude一致；(3) 早期對各 native tool 另做的 offline
calibration 僅留作 sanity-check，**§5 的 `prefetch_us` 一律取自每個 async cell 的 live
`warmer_us`（per-rep median）**，不再從 native-tool numbers補齊（避免混engine、重複計入）。

> **本 metric 是本論文 §5.5 core observation的依據**：當 `prefetch_us` 與
> `first_query_us` order of magnitude接近（多數 prefetch strategy < 100 µs）時，`cold-start_e2e`
> 約等於 `first_query_us`；但當strategy preprocessing overhead大（如 2f SLRU 的
> `prefetch_us` 達 ms magnitude）時，`cold-start_e2e` 反而被 `prefetch_us` dominate，
> 揭露「first-q 看似最低 ≠ end-to-end real最快」的 trade-off。具體quantify
> 見 §5.5。

#### 3.4.1 measurement環境與 hotset freeze（reproducibility）

每個 batch 由 `p0_env.sh` 釘住並**記錄**影響cold-start µs 的環境knob,把單行 `P0_ENV`
（kernel / disk / `read_ahead_kb` / governor / THP / loadavg）折進每筆 run record,環境一漂移
即可事後察覺。cold-clear (drop-caches)一律用全機 `/usr/local/sbin/drop-caches`（`echo 3`)。

CPU frequency strategy需特別說明:measurement主機 (Ryzen 9950X, `amd-pstate-epp`) 上,真正釘住frequency的是
**EPP（`energy_performance_preference=performance`)** 而非 cpufreq governor 標籤——後者顯示
`powersave` 但在 amd-pstate-epp 下不鎖低頻(實測 `boost=1`、負載core ~5.7 GHz)。`P0_ENV` 因此
額外記錄 `driver/epp/boost/maxfreq_khz`,以證明各 run 跑在 performance frequency strategy。
`read_ahead_kb` 固定為 **128**（裝置預設）並逐 run 記錄;本研究一律以 ra=128 measurement,不掃描其他值。

hotset 是**輸入**,結果隨之漂移,故全部 checksum freeze。其中歷史派 hotset (2d/2e/2f) 一律以
**P0 pipeline重產**(全機冷清 → workload warmup → mincore residual快照;
2e 的 top-K leaf 由 workload frequency決定、deterministic),freeze 清單(checksum)
在 master batch 前由 `--verify-frozen` 把關,杜絕 P1 來源混入。

---

### 3.5 Prefetch delivery：pread oracle vs. async hint（selection–delivery 拆解）

§3.4 分離了 prefetch 的**cost**（preprocessing）與 first-query。本節進一步把 prefetch
的**效益**拆成兩個正交因子——**選對哪些 page**（targeting / selection）與**這些 page
是否及時load**（delivery）——並說明 P0 如何同時measurement兩者。

**根因：`madvise(MADV_WILLNEED)` 是 async hint、不保證load。** 它向 kernel 登記 readahead
即 return，實際load在background非同步完成；某頁在 first-query 之前「載進來沒」取決於 readahead
是否來得及。因此 first-query 同時受「選對頁」與「載得及」兩件事影響，混在一起無法歸因。

**兩臂measurement。** P0 對每個 cell 用**相同 hotset**、只切換delivery方式各跑一次（pread 不是新strategy，
而是對每個strategy的 hotset 額外做一次同步delivery，以isolation selection）：

| 臂 | delivery | 量到 | 回答的問題 |
|---|---|---|---|
| **pread**（oracle） | `pread()` 同步阻塞，return 即 100% resident | `fq_pread` | 「hotset **選對**了嗎？」= delivery 理想時的 first-query lower bound |
| **async**（實務） | `madvise` / `fadvise(WILLNEED)` 非同步 | `fq_async` + `delivery_pct` | 「**實務**上真的拿到多少？」 |

兩臂之差即 **delivery loss**：

$$\text{delivery\_loss} = \text{fq}_\text{async} - \text{fq}_\text{pread}$$

這個差值**用measurement直接回答了「`MADV_WILLNEED` 到底保不保證load」**——它不保證，而漏載的代價
就是 $\text{fq}_\text{async} - \text{fq}_\text{pread}$（配合 `delivery_pct` 看「當時載了幾成」）。

**定位：pread 是upper bound，不是幻想。** pread 因同步阻塞、preprocessing 達 ms magnitude，**不是可deployment
strategy**（§5 的deployment comparison一律用 async 的 end-to-end，pread 只當參考線）。但它代表的 first-query
是「**只要用任何手段（idle 空檔background預暖、`readahead(2)`、io_uring）把 hotset 成功暖好**就能
達到的upper bound」。real deployment落在光譜中間：

```text
裸 madvise hint  ──►  readahead(2) / io_uring  ──►  pread
 不額外努力（lower bound）       強力非同步（實務多半在此）        同步保證（upper bound）
   = fq_async              = 落在兩者之間                = fq_pread
```

**delivery 受 readahead 上限封頂。** 單一 `madvise(MADV_WILLNEED)` 對一段 range 的實際load量
被 kernel readahead window 封頂為約 $2\times(\texttt{read\_ahead\_kb}/4)$ 頁；這正是 2a range
在散佈 layout 上「一次 madvise 只載 32/92 頁」的成因（§5）。因此 `read_ahead_kb` **並非中性
參數**——它同時決定 async 的封頂、以及「冷 fault 順帶 readahead」帶來的免費 prefetch。本研究
一律 **釘在 128 KB（裝置預設，外部效度最高）並逐 run 記錄**;所有conclusion均在 ra=128 下成立。

> **重點摘要（§5 以此framework陳述）：**
>
> 1. **可達upper bound（oracle）**：`fq_pread`。
> 2. **實務可deployment best**：async，以 end-to-end `e2e = prefetch_us + fq_async` comparison（layers_5
>    勝；2f SLRU 因 ms magnitude preprocessing 不具優勢，見 §5.5）。
> 3. **delivery 代價**：`fq_async − fq_pread`，即 async 作為 hint 相對 oracle 的漏載損失。

### 3.6 實驗假設與外部效度（assumptions & threats to validity）

**本研究跑在真實硬體、非模擬器。** measurement 主機為裸機 Ryzen 9950X + NVMe SSD，cold cache 由全機 `drop-caches`（`sync; echo 3 > /proc/sys/vm/drop_caches`）真實清空，每筆 I/O 都實際打到 disk（`majflt>0` 驗證）。因此沒有模擬器 timing model 失真的疑慮，代價是無法控制 SSD 內部的 FTL/GC 行為。

**本實驗模型納入的真實現象（assumptions）：**

- **「warm process, cold data」cold-start**（§2.2）：app 仍在跑、SQLite connection 與 prepared statement 已建立，但 file-backed page 已被回收——對應 app 自背景被喚醒、裝置自休眠恢復的真實情境。
- **Write churn 造成的 layout 漂移**（§6.2.1）：50k 寫入 × 10 checkpoint，模擬 DB 隨使用持續成長、page split/append。
- **RAM 壓力**（§6.2.2）：cgroup `MemoryMax=20M`，模擬 memory 受限裝置下 page 被 reclaim 的競爭。
- **多 process 共享 cache**（§6.2.3）：MAP_SHARED + cadence re-warm，模擬手機背景 service + 前景 App 共用同一份 page cache。

**未納入（threats to external validity，屬 future work）：**

- **SSD 內部行為**：本研究停在 OS page cache 層（Level 1）；FTL GC、write amplification、device-level 隔離需 FEMU 或實體多裝置（Level 2）才能控制，本機環境（無 kvm/root）未涵蓋。
- **單機、單一 kernel/SSD**：所有 cell 跑在同一台機器、同一 kernel（6.17）、`read_ahead_kb`=128；跨裝置 / 跨 kernel 的外部效度待獨立複現。
- **固定 reference DB**：600k row / 102 MB 單一 schema；更大 DB 或多表 join 的行為未測。

### 3.7 Statistical methodology（統計嚴謹性）

- **重複次數**：每個 (workload, layout, strategy, arm) cell 跑 **n=10 reps**（rep-major：同一 cell 的 10 次連續量，降低跨 cell 的環境漂移）；N/K sweep 類為 n≥5。
- **彙總統計量**：報 **median**（對 cold-start 的長尾 random-I/O 比 mean 穩健），另記 **p95 / min / stdev**；improvement-% 一律對**同 batch 的 baseline（無 prefetch）臂**配對計算，避免跨 pipeline 比較。
- **雜訊控制（壓低 rep 間變異）**：(1) `--cpu` 把 measurement 釘在固定 core（`sched_setaffinity`）；(2) `--warm-cpu-ms` 在計時區外把 amd-pstate 拉到滿頻，消除「最快 cell 受 freq ramp 懲罰最重」的偏差；(3) 每 cell 前全機 `drop-caches` + harness `--verify-hotset` 量 `cold_pct`，**`cold_pct>1%` 的 cell 視為冷清失敗、彙整時剔除**；(4) 逐 run 記錄 `loadavg/memavail`，環境漂移可事後察覺。
- **顯著性判讀（誠實）**：主要結論的**效應量遠大於 rep 間變異**——例如 first-query −30~90%、e2e 相差一個 order of magnitude（2f preproc ~7 ms vs first-q ~0.1 ms），不依賴邊際顯著。**反之，落在雜訊內的差異一律不宣稱排名**：例如 2f 在三 layout 間 first-q 差 <3 µs（< 單筆 noise）→ 結論為「layout-agnostic」；RAM 20M/unlimited 比值 0.95–1.07 → 結論為「幾乎不受影響」。本研究**未**做正式假設檢定 / 信賴區間，因效應量級已足以支撐方向性結論；邊際案例則明確標為「打平 / 在雜訊內」。

---

## 4. Strategies

三類正交，可以**自由組合**——例如「1c layout + 2c layers_5 prefetch + 4a
MAP_SHARED」是目前測過的全局best組合。

| 類別 | strategy | 做法簡述 |
|---|---|---|
| **改 layout** | 1a 原始 / 1b VACUUM / **1c type-aware** | 改變 page 在file裡的physical排列 |
| **Prefetch** | 2a–2c（看structure）/ 2d–2e（access-pattern）/ 2f（抄 cache）| First query 之前先載哪些 page |
| **Memory shared** | 4a MAP_SHARED / 4b private buffer pool | 多 process shared同一份 cache |

### 4.1 Layout strategies (1a / 1b / 1c)

- **1a 原始**：builder 跑出來的 DB，SQLite 怎麼配 page 就怎麼擺。
  Interior 跟 leaf 完全 interleaved（scatter score 0.96）。
- **1b VACUUM**：呼叫 SQLite built-in `VACUUM;`。會重新打包，但 source code 顯示
  它**按 insertion order** reorder、**不看 page type**。experiment證實：scatter 從
  0.96 變 1.13（更散）、file小 ~3%、prefetch 效益**沒提升**。
- **1c Type-aware layout rewriter**（**本 paper 的 contribution C1**）：自己
  寫的 binary file rewriter。把 92 個 interior 全搬到 file 開頭 page 2..93（連續排列）、leaf 接著、
  freelist 與 overflow 在最後。同時 patch 所有跨頁 pointer：interior 的
  child pointer、overflow 的 next-page、freelist 的 next-trunk、page 1 header
  的 freelist pointer，並 emit SQL 修正 `sqlite_master.rootpage`。Scatter
  score 從 0.96 → 0.0001（幾乎完美 clustering）；`PRAGMA integrity_check;`
  通過。

### 4.2 Prefetch strategies (2a–2f)

cold start 後第一筆 query 之前，主動發 `madvise(MADV_WILLNEED)` 把指定 page
hint 給 OS。差別在「指定哪些 page」：

- **Structure-based**（不access-pattern，只看 page structure）
  - **2a Range**：把連續的 interior page 合成 range，每個 range 一次 madvise
  - **2b Perpage**：每個 interior page 個別 madvise
  - **2c Layers_N**：按 file offset 升序排前 N 個 interior。**等同於
    「B+tree 上 N 層」僅在 1c (type-aware) 成立**（因為 1c 把所有 interior
    集中到 file 頭）；在 1a/1b 是「file中最早出現的 N 個 interior」，跟
    B+tree tree depth無 1-to-1 對應。P0 下 A/orig 上 **N≥5 即進 plateau ~−30% first-q**
    (N=1 反而 +31% 較慢);C 則要 N=92(見 §5.3)。
- **Access-pattern-based**（access-pattern = 跑一次 workload 後用 `mincore()` dump
  哪些 page resident）
  - **2d Access-pattern interior-only**：只 prefetch resident 的 interior。
  - **2e Access-pattern interior + top-K leaves**：2d + 加 K 個 access-count
    最高的 leaf。K ∈ {10, 50, 100, 500}。
- **SLRU-approximated**
  - **2f SLRU**：workload 結束後**不要 evict**，直接 mincore() 拍當下 resident
    set，下次 cold start 把那 ~500 個 page 全載。

full實作細節見 [overall_strategies.md](overall_strategies.md) §二「Prefetch strategy」。

### 4.3 Memory-sharing strategies (4a / 4b)

- **4a MAP_SHARED**：SQLite 設 `PRAGMA mmap_size = file_size` 後用
  `mmap(MAP_SHARED)` 開檔，**所有 process shared同一份 OS page cache**。
  一個 process prefetch 全部 process 受惠。
- **4b Private buffer pool per process**：傳統 read() + SQLite internal cache。
  每個 process 各自有 cache，N 個 process 就 N 倍 RAM。

4a 跟 4b 是對照組——validation「MAP_SHARED 在多 process deployment下省 RAM 跟攤平
prefetch cost」的關鍵。

---

## 5. Experiment and Evaluation

> **P0 master batch（authoritative）**：本章全部numbers為 P0 pipeline rerun(全 cell `cold_pct`=0),authoritative表見 [overall_results.md](overall_results.md)。core:first-query 最低為 **2f_slru(−79~90%)**,但其 preproc 使 `e2e` 不具優勢;**e2e 取決於 baseline 有多慢**——快 workload(A)上 prefetch e2e 反而變差,慢 workload(C)上 **2e_K10 e2e −56%(462µs)**。

**預期 vs 實際（本章解讀主軸）**：下表先列開工前的預期，§5.1–§5.5 的數據逐一檢驗。**最重要的發現都來自「不符合預期」的格子**——這也是本研究的 core observation（RQ1–RQ2）。

| # | 原本預期 | 實際結果 | 是否符合 |
|---|---|---|---|
| 1 | Prefetch 普遍能改善 cold-start | first-query 普遍改善（−30~90%），但**算進 preprocessing 後，快 workload(A) 上 e2e 反而變差** | **出乎意料**（§5.5）|
| 2 | 載越多 page（整份 working set，2f）效益越好 | 2f first-q 最低，但 ~7 ms preproc 使 **e2e 慢一個 order of magnitude** | **出乎意料**（§5.5）|
| 3 | layers_N 有「N=5 universal sweet spot」 | 形狀依 (workload, layout) 而異：A/Z N≥5 plateau、**C 要 N=92**、N=1 反而變慢 | **部分不符**（§5.3）|
| 4 | 慢 workload 上 access-pattern + 少量熱 leaf 最有效益 | C 上 2e_K10 **first-q −85%、e2e −56%**，是唯一 e2e 真正贏的格子 | **符合**（§5.4）|
| 5 | RAM 壓力會吃掉 prefetch 效益 | cgroup 20M 下 first-q 幾乎不受影響（ratio 0.95–1.07） | **符合（但原因不同）**（§6.2.2）|

### 5.1 Per-workload best methods (overview)

P0 下(layout orig,async first-query;baseline A 497 / B 725 / C 1058 µs),每個 workload
的「first-query 最低」與「end-to-end best(可deployment)」常常**不是同一個strategy**:

| workload | first-q 最低 | first-q | e2e | end-to-end best(可deployment) | e2e | first-q improvement |
|---|---|---:|---:|---|---:|---:|
| **A** (Zipfian) | 2f_slru | **107 µs (−79%)** | 7489 µs | **baseline（不 prefetch）** | 497 µs | 任何 prefetch e2e 皆較慢 |
| **B** (uniform) | 2f_slru | **105 µs (−85%)** | 7572 µs | layers_5 / 2d（structural)| 680–698 µs（**−4~6%**) | layers_5 −47% |
| **C** (churn-heavy) | 2f_slru | **102 µs (−90%)** | 1179 µs | **2e_K10（access-pattern)** | **462 µs（−56%)** | 2e_K10 −85% |

> **註**:「重載前次 cache」(2f SLRU) first-q 三 workload 都最低(−79~90%),但
> **preprocessing 自己花 ~0.9–7.5 ms**(視 working set 大小),**real cold start =
> preprocessing + first-q,因此 e2e 反而比 baseline 慢**(A +1407% / B +944% / C +11%)。
> 詳見 §5.5。
>
> P0 的可deployment的最佳strategy依 baseline 速度而定:**A(快)上沒有 prefetch strategy的 e2e 優於 baseline**
> (warmer startup ~250µs 起就 > 省下的時間);**C(慢)上「access-pattern」2e_K10 以 ~300µs preproc
> 換到 e2e −56%**,是真正有效益的。

![7 種strategy × 3 種 layout 跨 A/B/C 的 first query latency comparison](figures/out/05_strategy_comparison.png)

*圖 5(P0):每個 workload × layout 下各strategy的 async first-query(越短越好)。
**沒有萬用解**——first-q 上 2f 全部最低,但看 e2e 時只有慢 workload(C)的 access-pattern(2e_K10)真正有效益。*

### 5.2 Best combination on Workload A

**（P0 rerun數據,async 臂,median;authoritative表見 [overall_results.md「P0 master batch 結果」](overall_results.md)。舊 P1「318→127 −60%」整組numbers已由下表取代。）**

Workload A、layout orig（first-query / preproc=warmer wall-clock / end-to-end µs）:

| 做法 | First query | Preproc(warmer) | End-to-end | e2e vs baseline |
|---|---:|---:|---:|---:|
| baseline（不 prefetch）| 496.86 | 0 | **496.86** | — |
| layers_5 | 349.61 | 257.82 | 606.89 | **+22%(較慢)** |
| 2e_K10 | 337.32 | 287.85 | 626.31 | +26%(較慢) |
| 2f_slru | 106.76 | 7381.94 | 7489.41 | +1408%(較慢) |

> **P0 關鍵修正**:在 A 這種 baseline 本來就快(~497µs)的 cell,**warmer 的 preprocessing(含 process startup,~250µs 以上)反而 > first-query 省下的時間 → e2e 比 baseline 還慢**。first-query improvement(layers_5 −30%、2f −79%)是真的,但 **e2e 的結果要看 baseline 有多慢**:e2e 真正有改善是在慢 workload(C:baseline 1058µs → 2e_K10 e2e 462µs = **−56%**)。這推翻舊 P1「A 上 layout+layers_5 e2e −60%」的說法。

![Workload A 上 layout × strategy 的效果](figures/out/02_layout_effect.png)

*圖 2(P0):Workload A、async first-query,各 layout 的 baseline 與strategy(2f ≈ −79% first-q)。注意 first-query 與 end-to-end 的結果不同(見上表)。*

### 5.3 Workload-dependent benefit ceiling

P0 first-query improvement上限(orig,vs baseline):

| scenario | 只載 interior(layers/2d) | + 熱 leaves / 全 working set | 為什麼 |
|---|---:|---:|---|
| **A**（熱門集中）| −30~33% | 2e_K500 −69% / 2f −79% | hot leaves 多半已暖,interior-only 即有中段效益 |
| **B**（uniform 隨機讀）| −47% | 2f −85% | 每筆打 cold leaf,interior-only 卡在 −47%,只有整份 dump 才壓得低 |
| **C**（查file tail新資料）| −40% | **2e_K10 −85%** / 2f −90% | 每筆 cold leaf,但**「access-pattern」加載 top-K 熱 leaf 可突破**到 −85% |

![A/B/C 三 workload 在 clean DB 上的 layers_N plateau（P0）](figures/out/04_nsweep_plateau.png)
*（P0 rerun:clean DB、layout orig、async first-query;A/B 在 N=5 落底、C 需 N=92。3-layout 版見 Figure 11、churned-DB 版見 Figure 12,皆已 P0。）*

*圖 4：N（prefetch 多少個 interior page）對 first query 的影響。**A 在 N=5
就到 plateau**——**注意這個 plateau 描述的是「跑full段 workload 的 avg
latency / steady-state」**：first-q 時 leaves 跟 interior 同樣是 cold
（cold-start protocol DONTNEED 全清），layers_5 在 first-q 只移除 interior
fault，仍付一次 leaf fault；**跑開後** hot keys 對應的 leaves 自然 warm-up、
interior 才成為唯一反覆需要且shared的bottleneck，所以 prefetch 專攻 interior 就夠。
**B/C 要到 N≈92 才壓住** first-q 是因為它們每筆 query 都打不同 cold leaf、
沒有自然熱葉可依賴。Churn 不改變這個 plateau 形狀。*

### 5.4 Access-pattern frugality on Workload C

不是盲目載前 N 個，而是**先observation哪些 page 真的被用到**，再只載那些。P0,Workload C、
layout orig(baseline 1058 µs;preproc = warmer wall-clock,含 process startup):

| 做法 | First-q | First-q improvement | Preproc | End-to-end | e2e improvement |
|---|---:|---:|---:|---:|---:|
| 載全部 interior（layers_92）| 636 µs | −40% | +433 µs | 1068 µs | +1% |
| 只載真正用過的 interior（2d）| 635 µs | −40% | +299 µs | 930 µs | −12% |
| **+ 最熱的 10 個 leaf node（2e_K10）**| **155 µs** | **−85%** | +308 µs | **462 µs** | **−56%** (e2e 最佳) |

> P0 關鍵:在 C 上「只載 interior」(2d/layers_92) 只到 first-q −40%、e2e ≈ 打平;
> **真正解鎖的是加載 top-10 熱 leaf(2e_K10)**——把 first-q 從 635 → 155 µs(−85%)、
> e2e 462 µs(−56%)。warmer preproc 三者都 ~300–430µs(以 process startup為主、與載幾頁
> 關係不大),所以結果由 first-q 決定,而 2e_K10 的少量熱 leaf 是最有效益的選擇。

### 5.5 The preprocessing trade-off （本 paper 的core observation）

前面所有 first-q numbers都**只算 SQL 第一筆 query 的時間**——但 prefetch tool
自己也要時間（叫 OS 預先 load page、發 madvise 之類）。**real cold start =
preprocessing + first-q**。這個 preprocessing overhead會讓 first-q 看似很好的
strategy，整體 cold start 反而較慢。

**兩種觀點的視覺對比**：

![純 first-query latency comparison（preprocessing 沒算進去）](figures/out/13_strategy_firstq_bars.png)

*圖 13(P0)：純 first-query latency（async,log scale）。**2f SLRU first-q 全部最低**——
A/B ~105 µs、C ~102 µs(−79~90%),比 baseline 497–1058 µs 短一個order of magnitude。這是 §5.1
「first-q 最低」欄的視覺版本(但 e2e 另有結論,見圖 14)。*

![End-to-end cold start：preprocessing + first-q stacked，跟 baseline 比](figures/out/14_strategy_endtoend_stacked.png)

*圖 14(P0)：**real的 end-to-end cold start**(stacked:底層 first-q + 黃色斜紋
preprocessing=warmer wall-clock)。紅虛線 = baseline。**2f SLRU 明顯超過紅線**——
A 7489 µs(15× baseline)、B 7572 µs(10×)、C 1179 µs(1.1×)。**在快 workload A 上,
連 layers_5/2e_K10 的 e2e 也超過紅線**(warmer ~250–390µs preproc > first-q 省的時間);
**只有慢 workload C 上 2e_K10 e2e(462µs)安全在紅線(1058)下方**。*

#### 5.5.1 每種strategy的 preprocessing overhead（P0）

P0 的 `preproc_us` = **統一delivery engine `warmer` 的 wall-clock**（含 process fork/exec
startup,~250 µs 以上;這是「以standalone warmer process deployment」的real cost)。orig 代表值:

| strategy | 做什麼 | Preproc(warmer wall-clock) | 跟 first-q 比 |
|---|---|---:|---|
| **2c layers_5** | prefetch 前 5 個 interior | **~258 µs** | ~與 first-q 同magnitude |
| **2c layers_92** | prefetch 全部 interior | **~390 µs** | 同magnitude |
| **2d access-pattern（只 interior）**| access-pattern只載用過的 interior | **~275–300 µs** | 同magnitude |
| **2e_K10（interior + 10 熱 leaf）**| + 最熱 10 leaf | **~290–310 µs** | 同magnitude |
| **2e_K500（interior + 500 熱 leaf）**| + 最熱 500 leaf | **~0.7–1.1 ms** | > first-q |
| **2f SLRU（重載前次 cache）**| 載整份 resident working set(~0.4k–4.4k page)| **~0.9–7.5 ms** | **比 first-q 大一個order of magnitude** |

> **與舊報告的差異**:舊 calibration 量的是「裸 `madvise` syscall」(~1–2 µs);P0 量的是
> **full warmer process 的 wall-clock**(含 ~250 µs startup)。若把 prefetch **integrate進 app**
> (不另起 process),preproc 會降回 syscall 級(µs)、e2e ≈ first-q;但若以standalone warmer
> deployment,則小 hotset 也要付 ~250–400 µs startup。下面以 P0 量到的(standalone warmer)為準。

#### 5.5.2 real cold start 表現（end-to-end,P0）

加上 preprocessing 後,**e2e 取決於 baseline 有多慢**。對比快(A)與慢(C):

| strategy | A/orig e2e (vs base 497) | C/orig e2e (vs base 1058) |
|---|---:|---:|
| Baseline | **497** (—) | **1058** (—) |
| 2c layers_5 | 607 (**+22% 較慢**) | 1322 (+25% 較慢) |
| 2d access-pattern | 610 (+23%) | 930 (**−12%**) |
| 2e_K10 (+10 leaf) | 626 (+26%) | **462 (−56%)** |
| 2e_K500 (+500 leaf) | 1225 (+146%) | 864 (−18%) |
| **2f SLRU** | 7489 (**+1407%**) | 1179 (+11%) |

#### 5.5.3 three-line takeaway（P0）

1. **「重載前次 cache」(2f SLRU) first-q 最低(−79~90%)但 e2e 不具優勢**——其 preprocessing
   達 ~0.9–7.5 ms,使 e2e 比 baseline 慢(A 15×、B 10×、C 1.1×)。first-q 的numbers
   雖亮眼卻 misleading,real cold start 要看 e2e。
2. **e2e 是否improvement取決於 baseline 速度**:在快 workload(A ~497 µs)上,**連最便宜的
   2c/2d/2e 的 e2e 都 > baseline**(warmer ~250–400 µs startup > first-q 省下的時間);
   在慢 workload(C ~1058 µs)上,**access-pattern 2e_K10 以 ~300 µs preproc 換到
   e2e −56%(462 µs)**,是最有效益的選擇。
3. **若把 prefetch integrate進 app(免去standalone process startup),小 hotset 的 preproc 降回
   syscall 級、e2e ≈ first-q**——此時 2c/2d/2e 在所有 workload 都有效益;deployment形式
   (integrate vs standalone warmer)是決定 e2e 的關鍵knob。

> Cadence(圖 8)是同一條 trade-off 的時間版:background warmer 每 cadence 秒re-warm一次。
> 實測 **cadence=1s/5s maintain first-q ~26/29 µs**(warm);**cadence=30s/never 退到
> ~281/305 µs**(≈ 沒 prefetch)。即「**依在意 first-q 還是 overhead,在 frontier 上選一點**」,
> 而非「兩個 metric 各有best cadence」。

---

## 6. Discussion

### 6.1 Key findings recap

跨整個 P0 experiment matrix 看到的structure性 finding（robustness validation在 §6.2）：

1. **N（prefetch 幾個 interior）的形狀因 (workload, layout) 而異**:P0 dense N-sweep
   (async)顯示——A/Z 在 **N≥5 即 plateau ~−30%**(orig);**N=1 反而比 baseline 慢
   ~+31%**(warmer/madvise overhead > coverage);B 全 plateau **~−47%**(leaf-fault dominate);
   **C 要 N=92 才到 −40%**(熱 interior 在 file 中段、按 offset 取前 N 選錯頁)。
   沒有「N=5 universal sweet spot」這種單一敘事——best N 跟 layout/workload 綁定。
2. **沒有通用 best strategy**:first-query 上 2f 全部最低(−79~90%),但看 e2e 時要視
   baseline 速度與deployment形式(見 #3、§5.5)。
3. **e2e 取決於 baseline 速度,不是strategy本身**:在快 workload(A ~497 µs)上,
   warmer 的 ~250–400 µs preprocessing 蓋過 first-query 省下的時間 → **任何
   prefetch 的 e2e 都不優於 baseline**;在慢 workload(C ~1058 µs)上,**access-pattern
   2e_K10 以 ~300 µs preproc 換到 e2e −56%**。type-aware layout 在 P0 下把 A/B 的
   baseline **推高**(A +31%、B +10%)、C 較快(−18%),不是舊 P1「A −69% 大幅改善」。
4. **慢 workload 上「access-pattern + 熱 leaf」最有效益**:C 上 interior-only(2d/layers_92)只
   −40% first-q、e2e ≈ 打平;加 top-10 熱 leaf(2e_K10)才解鎖 first-q −85%、e2e −56%。

### 6.2 Robustness checks

validation所有 §5 conclusion在三條動態軸下都成立：DB 一直被 write、RAM 被砍掉、多 process
shared。

#### 6.2.1 Churn evolution（DB 被持續 write 後）

DB 被持續 write（11 個 checkpoint × 5k mutation ops = 5.5 萬筆）後,**static t=0 hotset
完全沒decay**:P0 量到 C 上 2e_K10_static 跨 checkpoint maintain ~82–86 µs(vs baseline ~580 µs),
ck0→ck10 無上升趨勢;三 layout(orig/vacuum/ta)皆然。

![11 個 checkpoint × 5k churn ops 下 A/B/C 的 first query 演化](figures/out/07_churn_evolution.png)

*圖 7(P0)：DB 被持續 write 後,static t=0 hot pages 在 A/B/C 三種 workload 上都不decay
(主面板 = layout orig;CSV 另含 vacuum/ta)。C 上 2e_K10_static 跨 11 個 checkpoint
持平 ~82–86 µs;B 上沒有自然熱葉,access-pattern 與structural打平,但同樣不 decay。*

#### 6.2.2 RAM pressure（cgroup MemoryMax=20M）

**DB ~102 MB、RAM 用 cgroup `MemoryMax=20M` 砍到 20 MB**（systemd-run --user --scope 套用）,first query 的improvement**幾乎不受影響**:

- **First query**：P0 量到「20M / unlimited」ratio**全部落在 0.95–1.07**(54 個 strategy×
  workload×layout cell),因為 first query 只摸到少數 page、不在 reclaim path上。
- **為什麼pressure這麼小**:resident working set(2f hotset ~4.4k page ≈ **17 MB**)其實
  **略小於** 20M cap,hotset 幾乎塞得下、eviction有限(這也修正了舊「20M ≪ 16MB」的方向錯誤)。

![RAM-pressure heatmap (20 MB cgroup vs unlimited)](figures/out/06_ram_pressure_heatmap.png)

*圖 6(P0)：把可用 RAM 砍到 20 MB（A/B/C × 3 layout × 6 strategy）。
每 cell 的「20M / unlimited」async first-query ratio**全部落在 0.95–1.07**——memory
pressure 幾乎不影響 first query(working set ~17 MB < 20M cap)。*

#### 6.2.3 Multi-process MAP_SHARED

一個 process 做 prefetch，所有shared同一份 cache 的 process 都受惠。

![Multi-process prefetch cadence 對 first query latency 的影響](figures/out/08_cadence_comparison.png)

*圖 8(P0)：background warmer 每 cadence 秒re-warm、前景每 probe 做全機 drop-caches 後量first-query。
**Cadence 是一個 trade-off 參數**：cadence=1s/5s maintain first-q ~26/29 µs、cadence=30s/never
退回 ~281/305 µs(≈ 沒 prefetch)。若要維持 first-q warm,cadence 需 ≤ query 間隔;若要節省cost則加大
cadence(代價是 first-q 退回 cold)。視deployment在意哪個目標而定。*

### 6.3 Practical recommendations

| scenario | recommendation做法 | First-q improvement | End-to-end（P0,standalone warmer）|
|---|---|---|---|
| **慢 workload(查file tail/churn,baseline 高)** | access-pattern:interior + 最熱 ~10 leaf(2e_K10) | **−85%**(C) | **e2e −56%(462µs)** 真正有效益 |
| uniform 隨機讀(uniform) | structural layers_5 / 2d | −47%(B) | e2e ≈ 打平(−4~6%) |
| **快 workload(熱門集中,baseline 已快)** | structural layers_5(first-q) | −30%(A) | standalone warmer 下 e2e 不優於 baseline;**要改善 e2e 須把 prefetch integrate進 app**(免 ~250µs startup) |
| Batch / 平均 latency 場景 | 重載前次 cache(2f SLRU) | −79~90%(first-q) | **e2e 不具優勢**(preproc ~0.9–7.5ms);僅適合 batch 場景,不適合 cold-start critical path |
| 多 process shared DB | shared cache + background warmer,cadence ≤ query 間隔 | cost固定、效益乘 process 數 | cadence=1s maintain first-q ~26µs |

> P0 兩條原則:(1)**2f SLRU 的 first-q 最低但 e2e 不具優勢**,不適合 cold-start critical path;
> (2)**e2e 要改善,或是 baseline 夠慢(C 用 2e_K10),或是把 prefetch integrate進 app 免掉 warmer startupcost**。

### 6.4 Limitations

- **Machine-state drift across sessions**：clean DB 上同個 cell 跨 session 的
  絕對 µs 可能差 30-70%（同 harness、同 DB、同 code），來自 SSD internal SLC
  cache / wear leveling 狀態漂移 + 機器整體background負載。我們的對策是「所有要
  互相comparison的數據都在同一個 batch 內跑」（一致性 < 5%）。Page fault 數量
  完全 reproducible，只是 per-fault 時間飄。
- **Sample size**：P0 master batch 每 cell async 10 reps、pread 5 reps、baseline 10 reps
  (丟第 1 rep warmup)、rep-major;sweep/RAM 批次 async 3–5 reps。報 median(+p95 when n≥4)。
- **「Warm process, cold data」cold-start 模型**（§2.2）：跟「process from
  scratch」差約 1–3 µs,對 baseline ~500–1058 µs 來說 < 1%;對 2f 的 ~105 µs
  first-q 約 ~1–3%。不改變conclusion(2f 的 ~0.9–7.5 ms preprocessing 仍 dominate e2e)。
- **Preprocessing 計法**:P0 的 `preproc_us` = standalone warmer process 的 wall-clock(含
  ~250 µs startup);integrate進 app deployment可降回 syscall 級(見 §5.5),會改變快 workload 上的
  e2e conclusion。`read_ahead_kb` 固定 128(主值);{0,512} 掃描需 root、未跑。
- **Workload coverage**：A/B/C 是合成的三種 access pattern；real world 行為
  可能更複雜（mixed read/write、time-of-day 變化）。另已準備
  600 個額外 workload 留待後續validation。
- **未測「真正 cold reboot」cold start**：受限於 sudo 權限與機器shared，沒做
  「每筆量都 reboot」的嚴格 cold start。harness `--sqlite-open-timing=after-cold`
  可以模擬部分（重 open SQLite handle）。
- **Single-machine 結果**：所有experiment在同一台 Ryzen 9950X + NVMe 上跑。SSD
  類型 / 機器架構不同的 reproducibility 未validation。

---

## 7. Future Work

- **Type-aware Physical Segregation (Level 2)**：把 type-aware layout 從
  filesystem 層下放到 NVMe SSD 層（用 NVMe Stream Directives 把 interior /
  leaf 分到不同 SSD line/namespace），讓 SSD GC / wear leveling 不會打亂
  layout。在 FEMU SSD emulator 上做（PoC spec 已備）。
- **Strict cold-start 模式**：跑 `--sqlite-open-timing=after-cold +
  --schema-init-timing=after-cold` 一輪，quantify「warm process cold data」跟
  「full cold」之間的 µs 差距，把 §2.2 的「約 1-3 µs」換成精確numbers。
- **額外 workload validation**（後續工作）：600 個額外 workload
  ({read,scan} × {uniform,zipf} × {full,window,tail} × 50 seeds) 跑過後，
  validation §5 conclusion的 robustness。
- **Independent verification**（後續工作）：在不同 machine / SSD 上重
  跑關鍵 cell，quantify我們 §6.4 「machine drift」估計的可信度。
- **NVMe SSD page-aware GC 影響**：long-term 跑 large churn (multi-million
  ops)，看 SSD internal GC 對 interior page layout 的影響。
- **Continuous prefetch / steady-state hot-set maintenance**：本研究的
  prefetch 為 cold-start 一次性事件（每次 ~92 `madvise(WILLNEED)` call、
  單 process）。若擴展為持續性 daemon 不斷依 `mincore()` snapshot 維護
  hot-set（cadence ↓ 至 10 ms、hot-set ↑ 至 10K page），總 madvise frequency將
  進入 **>1 M ops/s** regime——剛好踩進 [Leis+23] 解的 TLB shootdown 與
  page allocator scalability 邊界。然而 [Leis+23] 的 fix（**exmap** Linux
  kernel module）需 **root 權限** + `modprobe` deployment，與本研究 application-
  side 非侵入式deployment hypothesis不相容；若要追求 continuous prefetch 方向，需重新
  evaluation deployment模型（可接受 kernel module）或與 [Leis+23] 做 kernel-level
  co-design。本研究刻意把 design point 鎖在「低頻 + 無 root」這個角落，
  與 [Leis+23] 的「高頻 + kernel module」角落在 design space 上正交，互為
  補集。

---

## 8. Conclusion

SQLite cold start 後 first query 很慢，因為要先從 disk 讀進關鍵的 **interior
page**。我們用 **prefetch（提前 load）** 把它們先放進 memory。**P0 rerun conclusion**
(authoritative numbers見 §5 / [overall_results.md P0 master 表](overall_results.md)):first-query
最低是載整個 working set 的 **2f_slru(−79 ~ −90%)**,structural **layers_5 / 2e_K10**
用極少 syscall 取得 first-query −30 ~ −85%;但 **end-to-end 取決於 baseline
有多慢**——在慢 workload(C, baseline ~1058µs)上 **2e_K10 e2e −56%(462µs)**、
2f 因 ~7.5ms preproc e2e 不具優勢;在快 workload(A, baseline ~497µs)上 warmer 的
preprocessing 反而蓋過 first-query 省下的時間、e2e 反而變差。這些結果在 50k write
churn、cgroup `MemoryMax=20M` memory pressure、與 cadence re-warm三條 robustness 軸下穩定
(全 P0 cell `cold_pct`=0)。

更重要的observation：**「重載前次 cache」(2f SLRU) first-q 看似最低(−79~90%)是misleading**——
其 preprocessing ~0.9–7.5 ms 比 first-q(~105 µs)大一個order of magnitude,**real e2e cold start
反而比 baseline 慢**(A 15×、B 10×、C 1.1×)。2f 的價值在「跑full段」的 avg latency,
不在第一筆。這個 first-q vs e2e 的 trade-off 在 prefetch literature中很少被明說。

---

## 9. References

### 9.1 Code & Data

| 想看什麼 | 去哪 |
|---|---|
| 全 P0 數據（strategy×workload×layout + N/K-sweep + RAM + churn + cadence）| [overall_results.md](overall_results.md) |
| 每個strategy的原理與狀態 | [overall_strategies.md](overall_strategies.md) |
| 四種 workload 的定義 | [overall_workloads.md](overall_workloads.md) |
| Figures | [figures/out/](figures/out/) |

### 9.2 External References

**Tools / Code repositories：**

| Resource | Where | 用途 |
|---|---|---|
| **YCSB-cpp** | https://github.com/ls4154/YCSB-cpp | Workload A/B 的格式 / 分布 reference（YCSB-C Zipfian、YCSB-A uniform）——我們延續 YCSB 的 op string 風格作為 workload file 格式（見 §3.2） |
| SQLite | https://www.sqlite.org/ | 被研究的 DB engine（讀path、B+tree、page cache 行為）|
| FEMU | https://github.com/MoatLab/FEMU | Future Work §7 提到的 SSD-level evaluation 平台 |
| MySQL InnoDB buffer pool preload | https://dev.mysql.com/doc/refman/8.0/en/innodb-preload-buffer-pool.html | §2.3.2 對照——engine-internal「整份 buffer pool dump/load」的生產實作，與本研究 2f SLRU 同 pattern |

**Papers：**

| # | Citation | 在本研究中的role |
|---|---|---|
| [Smith 1978] | Smith, A. J. "Sequentiality and prefetching in database systems." *ACM Transactions on Database Systems* 3(3):223–247 (1978) | §2.3.1 + §2.3.2 foundational ancestor——**OBL (One Block Lookahead) 的原始出處**，sequential prefetching 概念主線的源頭。Chen+21 把它擴充為 K-page LookAhead baseline；Linux readahead 繼承同一條 lineage |
| [Effelsberg & Härder 1984] | Effelsberg, W., Härder, T. "Principles of database buffer management." *ACM Transactions on Database Systems* 9(4):560–595 (1984) | §2.3.2 foundational anchor——DB buffer management 奠基論文，建立 replacement / prefetching / ref-count design dimension。Pre-Buffer 跟 Chen+21 都引這篇 |
| [Yi+26] | Yi, J., Wang, X., Jin, P. "Workload-Aware Buffer Prefetching for Database Systems." *Data Science and Engineering* (2026). https://doi.org/10.1007/s41019-025-00342-6 | §2.3.2 對比——他們的 "buffer cold-start" = hotspot-shift recovery，background thread + Direct I/O；我們處理 OS page cache cold-start + critical-path preprocessing accounting |
| [Chen+21] | Chen, Y., Zhang, Y., Wu, J., Wang, J., Xing, C. "Revisiting data prefetching for database systems with machine learning techniques." *ICDE* (2021), pp. 2165–2170. DOI: 10.1109/ICDE51399.2021.00218 | §2.3.2 引用——ML-based prefetcher（DNN/CNN/RNN/LSTM/Multi-Model，8–20M 參數）。**訓練 trace 採 warm-start**，evaluation 只報 precision/recall，未measurement NN inference 對 latency 的衝擊、也未measurement wasted-prefetch I/O cost——雖其 §IV-B 自承「wrong prefetching... will hurt the performance of the system due to the extra I/O cost」。Pre-Buffer 的批評因此公允；本研究的 preprocessing-aware methodology 正是 fill 這個 gap |
| [Oh+15] | Oh, G., Kim, S., Lee, S.-W., Moon, B. "SQLite Optimization with Phase Change Memory for Mobile Applications." *Proceedings of the VLDB Endowment* 8(12):1454–1465 (2015) | §2.3.3 canonical exemplar——mobile SQLite write-optimization 路線的代表作。**深度 fork SQLite**（B+tree / pager / buffer mgmt / journaling 全改）+ **custom PCM hardware (UMS board)**，解 autocommit write amplification（>100×）達 8–24× throughput improvement。完美對照本研究三條 differentiator：read cold-start vs write throughput / 無 SQLite mod vs 深度 fork / commodity HW vs custom PCM |
| [Kang+13] | Kang, W.-H., Lee, S.-W., Moon, B. "X-FTL: Transactional FTL for SQLite Databases." *SIGMOD* (2013), pp. 97–108 | §2.3.3——mobile SQLite write-optimization 同 lineage，介入層在 **FTL**（Flash Translation Layer）。Oh+15 的近鄰先行工作 |
| [Kim+12] | Kim, H., Agrawal, N., Ungureanu, C. "Revisiting Storage for Smartphones." *USENIX FAST* (2012), pp. 17–29 | §2.3.3——mobile storage performance 奠基分析論文，建立「SQLite + journaling on flash」是 mobile I/O 主要bottleneck的認識 |
| [Jeong+13] | Jeong, S., Lee, K., Lee, S., Son, S., Won, Y. "I/O Stack Optimization for Smartphones." *USENIX ATC* (2013), pp. 309–320 | §2.3.3——mobile I/O stack 層級優化，write-side focus |
| [Gaffney+22] | Gaffney, K. P., Prammer, M., Brasfield, L., Hipp, D. R., Kennedy, D., Patel, J. M. "SQLite: Past, Present, and Future." *PVLDB* 15(12):3535–3547 (2022). DOI: 10.14778/3554821.3554842 | §1 + §2.1 + §2.3.3 multi-purpose anchor——SQLite 創始團隊（Hipp / Kennedy / Brasfield @ sqlite.org）+ UW-Madison 合著的最新 authoritative SQLite evaluation。§1 引用其 ubiquity 統計（>1T database）；§2.1 引用為 SQLite 架構標準描述；§2.3.3 引用其 SSB evaluation 方法論——**他們明確 `SELECT *` 預熱 buffer pool**，是「cold-start 在 SQLite 學術literature中被系統性排除」的直接證據 |
| [Crotty+22] | Crotty, A., Leis, V., Pavlo, A. "Are You Sure You Want to Use MMAP in Your Database Management System?" *CIDR* (2022) | §2.3.5 anchor——對 file-backed mmap-as-DBMS-substrate 的系統性批判（eviction control 喪失、無 async I/O、I/O 錯誤難處理、fast NVMe scalability 不足）。**重要的是**：其 §6 conclusion明確列出 "maybe use mmap" 的兩項條件——read-only + fits in memory——本研究 cold-start use case 完全符合；§3.4 又親口承認 mmap "lower total memory consumption" 的優勢。**Crotty+22 不僅不否定我們，反而 explicitly 背書我們的 design choice** |
| [Leis+23] | Leis, V., Alhomssi, A., Ziegler, T., Loeck, Y., Dietrich, C. "Virtual-Memory Assisted Buffer Management." *SIGMOD* (2023) | §2.3.5——Crotty+22 的後續回應。anonymous mmap + DBMS-controlled `madvise(DONTNEED)` eviction + custom Linux kernel module (exmap) 解 TLB shootdown 跟 page allocator scalability。我們用同 family OS primitive 但操作frequency低 4 個order of magnitude以上（cold-start 一次 ~92 calls vs 他們的 >1M ops/s），碰不到他們解的bottleneck |
| 其他 papers / blog posts | §2.3 candidate reading list | survey 進度見 `related_work_reading_list.md`（待建立）|

---

## Appendix A: Supplementary Figures

### A.1 Latency CDF（cold → warm 過渡區）

![前 50 筆 query 的累計 latency（cold→warm 過渡區）](figures/out/03_latency_cdf.png)

*圖 3：前 50 筆 query 的累計時間。Prefetch 把「cold→warm」的過渡時間整段
壓掉；第 50 筆之後所有方法都converge到 ~1.5 µs/query。*

### A.2 Workload Z robustness check（低 id hotspot 變體）

![Workload Z：低 id hotspot 的 Zipfian 變體](figures/out/09_zlowkey_nsweep.png)

*圖 9：把 hotspot 從 [8, 99997] 移到 [1, 1000]（低 id 區段）的 robustness
check。N-sweep 形狀跟 Workload A 同形（差 ≤ 5pp）——「hotspot 落在哪個 key
區段」不是 prefetch 效益的主要變因。*

### A.3 Interior:leaf 比例掃描（3a/3b ratio variants）

![Interior:leaf 比例掃描（3a/3b ratio variants）](figures/out/10_ratio_sweep.png)

*圖 10：Load interior 跟 hot leaf 的比例（K=10/40/50/92/100/500）。**K 才是
主要變因，ratio 不是**——A 上 K=500 才追平、C 上 K=10 就 saturate。*

### A.4 Dense N=0..92 sweep（rigor pass）

full數據 + 兩張 9-cell grid 圖在 [figures/out/11_nsweep_full.png](figures/out/11_nsweep_full.png)
（clean DB, A/B/C × 1a/1b/1c）跟 [figures/out/12_nsweep_full_churn.png](figures/out/12_nsweep_full_churn.png)
（churn DB, A/B/C）。Sparse 6-pt 跟 dense 93-pt slice的對照、9/12 cell conclusion
不變但 3 個 sweet spot 被漏掉的分析，見 overall_strategies.md 2c bullet 跟
overall_workloads.md 「已完成的覆蓋」表。

---

# SQLite 冷啟動 Prefetch 研究

> 文獻 / 完整實驗推導見配套文件：
> - [overall_results.md](overall_results.md) — 19 維實驗的完整數字
> - [overall_strategies.md](overall_strategies.md) — 每個策略的原理
> - [overall_workloads.md](overall_workloads.md) — Workload 定義
> - [README.md](README.md) — 研究故事 (chronological)
> - [calibration/](calibration/) — Preprocessing-time 量測

---

## Abstract

**摘要**——隨著 SQLite 廣泛部署於行動裝置、IoT 與桌面應用，其 cold-start 讀取效能逐漸成為使用者體驗的關鍵瓶頸，並衍生出兩個尚未被同時解決的核心
挑戰：**prefetch 目標選擇（targeting）** 與 **preprocessing 成本核算（cost-accounting）**。就 targeting 而言，作業系統與應用層皆缺乏對 SQLite B+tree 內部 page-type 結構的可見性，盲目 prefetch 會將 I/O 浪費在大量無關 page 上，無法精準命中真正主導 cold-start cost 的少數關鍵 page；就 cost-accounting 而言，既有 prefetch 策略多僅優化 first-query latency，未將 prefetch 本身的 preprocessing 開銷納入 end-to-end cold-start 真實成本評估，造成「first-query 改善幅度」與「真實 cold-start cost」之間的系統性誤導。SQLite 因其輕量嵌入式設計、零組態部署與廣泛 SQL 相容性，是此議題最具代表性的研究對象，然而現有 SQLite 相關文獻多聚焦於寫入路徑（fsync、WAL、journal mode），對 cold-start 讀取路徑的系統性分析較少；現有跨領域工作中，作業系統層的 readahead 僅依賴 sequential pattern detection、無法針對 page-type 做精準預判，DBMS 層的 buffer pool warming 又須侵入式修改 engine、且皆未將 preprocessing 計入真實成本。為彌補此 gap，我們提出一套結合 **page-type-aware 物理 layout 重排** 與 **基於 mincore 的 targeted madvise prefetch** 的兩層 cold-start 框架（系統正式命名待定）。在固定的 reference DB（**600k rows、102 MB**）上，我們依 SQLite B+tree 角色（interior/leaf）對 page 做精確分類，僅針對主導 cold-start cost 的 **0.35%（92個 interior page、共 368 KB）** 進行 prefetch，避免盲目 preload 帶來的 I/O 與 page reclaim 浪費，且整套設計無需修改 SQLite 內部。據我們所知，**我們的研究** 是第一個在 **empty OS page cache cold-start 場景下**（區別於 Yi et al. [2026] 處理的 hotspot-shift buffer cold-start），將 prefetch preprocessing 開銷明確納入 end-to-end 評估的 SQLite prefetch
研究：實驗顯示既有 cache-dump 策略雖能將 first-query latency 從 baseline 的 **318 µs 壓降至 14 µs（−94%）**，但其 **1.8 ms 的 preprocessing 開銷** 反讓 end-to-end cold start **慢 3–7 倍**——這個 trade-off 在既有 prefetch 文獻中長期被忽略。最終 **我們的研究** 在 Zipfian workload 上將 first-query latency 從 **318 µs 降至 127 µs**、end-to-end cold start 達成 **−68%（preprocessing 僅 1.1 µs）** 於 file-tail uniform workload 上以 **僅 4 個 syscall** 的 access-pattern prefetch 取得與盲載全部 92 個 interior 相當的 −47%；且在 **50k 寫入 churn**、**cgroup `MemoryMax=20M`**（約 working set 的 1/5）記憶體壓縮、以及多 process MAP_SHARED 共享三條 robustness 軸下皆保持穩定（63 個 cell 的 first-q 比值全落於 0.90–1.19）。

**Index Terms**——SQLite, Cold-start latency, Prefetch, Page-type aware

---

## 1. Introduction

### 1.1 Problem

- SQLite 把整個資料庫存成一個 **4 KB page 的陣列**，用 B+tree 組織。
- 每筆 query 都要**從 root 走到 leaf**，沿路的 **interior page（interior node）
  全部都要在 memory 裡**。
- **Cold start**（cache 是空的）時，這些 page 都得從 disk 讀，每讀一個就是一次
  慢速的 random I/O。

**核心問題：能不能在 first query 之前，先把這些關鍵 page 載進 memory？**

### 1.2 Key insight

Interior 只占整個 DB 的 **0.35%**（92 個 / 26,331 個 = 368 KB / 102 MB），
但每筆 query 都得用到。**只要先載這 368 KB，就能避開 cold start 的 random I/O**。

這個 0.35% 的瓶頸暗示三類**正交**的優化路徑：

1. **Layout**：把這 92 個 page 集中到檔頭，readahead 一次就能載完
2. **Prefetch**：cold start 後 first query 之前，主動把這 92 個（或更多）page
   載進 cache
3. **Memory sharing**：多個 process 共用同一份 page cache，preprocessing 的
   成本被攤平

### 1.3 Contributions

- **(C1) Type-aware layout rewriter** (1c)：在 binary 層級重排 SQLite file，
  把 92 個 interior 全集中到檔頭 page 2..93（連續），patch 所有跨頁 pointer +
  `sqlite_master.rootpage` + freelist。**1c + layers_5 在 Workload A 拿到
  end-to-end cold start −68%**，preprocessing 僅 1.1 µs。
- **(C2) Access-pattern prefetch (2d/2e) 完勝 file-offset 排序**：用 mincore()
  snapshot 找出真正被讀過的 page。對 file-tail workload (C) **只用 4 個 syscall
  就追平載全部 92 個 interior 的效果**（−47% vs −46%）。
- **(C3) End-to-end cold-start trade-off 量化**：揭露 SLRU-style preload (2f)
  看似 **first-q −94%**，但 preprocessing 1.8 ms 比 first-q 14 µs **大兩個
  數量級**，真實 cold start 反而**慢 3–7 倍**。這是 prefetch 文獻中很少明說
  的觀察。
- **(C4) Robustness 三條軸**：50k churn ops 下 static t=0 hotpages 不 decay；
  cgroup MemoryMax=20M (約 working set 的 1/5) 下 first-q 完全免疫；多 process
  MAP_SHARED 下 prefetcher cadence ≤ query gap 就能 warm。

### 1.4 Paper roadmap

§2 講 SQLite cold-start 的 mechanics、我們採用的 "warm process, cold data"
量測模型，以及 related work 定位；§3 描述測試 DB / workload / benchmark
harness；§4 把三類策略（layout / prefetch / memory-sharing）逐一列出設計
選擇；§5 是 experiment and evaluation，**§5.5 是 paper 的核心 trade-off
觀察（preprocessing cost）**；§6 discussion——含 key findings、robustness
驗證、實務建議、limitations；§7 future work；§8 conclusion；§9 references。

---

## 2. Background and Related Work

### 2.1 SQLite B+tree storage 與 cold-start mechanics

SQLite 把每個 logical table 跟 index 存成一棵 B+tree、用 4 KB page 為基本單位
循環儲存在 single file 裡。Page 分四種：

- `interior_table` / `interior_index`：B+tree 的內部節點，存 key + child pointer
- `leaf_table` / `leaf_index`：實際資料

對 600k row 的 reference DB（schema 詳見 §3.1）：interior page 只有 92 個
（51 table + 41 index）、占整 file 的 **0.35%**；leaf page 26,239 個、占
**99.65%**。

每筆 query (例：`SELECT payload FROM items WHERE id=?`) 都得從 B+tree root
（pageno 1）逐層往下走到 leaf。**走完整條 path 要的 interior page 全部都得
在 memory**——任何一個不在，就要去 disk fetch，每次 ~5-100 µs 的 random
read 延遲。

**Cold start = OS page cache 是空的狀態下做第一筆 query**。這時 SQLite 走
B+tree path 會 trigger 多次 major page fault（majflt），每次都是真的 disk
read。Reference DB 上一筆 cold start query 通常需要 ~300-700 µs（取決於
workload 跟 layout），比 warm 狀態下的 ~1.5 µs 慢 200-450 倍。

### 2.2 Cold-start 模型：「warm process, cold data」（pragmatic choice）

嚴格 textbook 的 cold start 是「機器剛開機、process 從來沒跑過、所有 cache
都空」，但這在 benchmark 環境**做不到**（要每筆量都 reboot），所以我們選了
一個務實的版本：

| 層 | 我們的狀態 | 嚴格 cold 要求 |
|---|---|---|
| **OS page cache（DB 內容）** | ✅ **每筆量前用 `posix_fadvise(DONTNEED)` 清掉** | 完全空 ✓ |
| **磁碟 I/O** | ✅ majflt > 0 證實確實到 disk | 必須 physical I/O ✓ |
| **SQLite handle / pager** | ⚠️ **預先開好**（PRAGMA cache_size=0、statement 已 prepare）| 從未 open |
| **mmap()** | ⚠️ **預先建立**（mapping 在、但 page 還沒 fault 進來）| 從未呼叫 |
| **CPU 指令 cache / TLB / branch predictor** | ⚠️ **已 warm**（harness 程式碼之前跑過很多次）| 全部冷 |

**為什麼這樣選**（design rationale）：

- **跟真實情境更接近**：手機 app / server worker 大多時候是「process 已
  running、SQLite 已 load、schema 已 introspect」，使用者按下去那筆 query
  才是 cold data。比「process 從來沒存在過」更接近實際 cold-start 情境。
- **隔離我們關心的變數**：要量「prefetch 對 page fault 路徑的影響」。SQLite
  parser/optimizer 的啟動時間是常數，混進去只會增加 noise、不會 reveal
  任何 prefetch 機制相關的東西。
- **可重複性高**：「process from scratch」會多出 50-200 µs 的 SQLite 初始化
  noise，需要更多 reps 才壓得住。

**這個選擇對結果的影響**：

- 對 first_query 數字大約**少算 1-3 µs**（CPU cache / TLB 之類熱了一點點）
- 對 baseline ~500 µs 來說 < 1%，可忽略
- 對 first-q 只剩 14 µs 的 2f SLRU 約 ~10%，但**不改變結論**（2f 的
  preprocessing 1.8 ms 仍然 dominate）

> Harness 已支援更嚴格的模式：`--sqlite-open-timing=after-cold` +
> `--schema-init-timing=after-cold`，但本報告**全部使用預設的 "warm process,
> cold data"** 模式，所有數字一致可比。

### 2.3 Related Work

> **TODO（survey 後填）**：本節分五類整理跟我們最相關的既有工作，每段最後
> 點出「跟本 paper 的差別」。survey 進度見
> [related_work_reading_list.md](related_work_reading_list.md)（待建立）。

#### 2.3.1 OS-level prefetching & readahead

Linux kernel 的 readahead 機制（`mmap` MADV_WILLNEED / MADV_SEQUENTIAL、
`posix_fadvise(POSIX_FADV_WILLNEED)`、kernel `do_page_cache_ra`）跟 SSD-aware
I/O scheduling 的相關文獻。

**歷史 lineage**：sequential prefetching 的概念可追溯至 [Smith 1978]，
原始在 DB 層提出 **One Block Lookahead (OBL)**；Linux kernel readahead
繼承這條概念主線但下放到 OS 層、操作對 DB-internal 結構不可見的 file
offsets——也因此只能做 sequential pattern detection、無法 page-type aware。

候選 reading：
- Linux kernel mm `readahead.c` design notes
- "Anticipatory I/O Scheduling" (USENIX ATC '04, Iyer & Druschel) ← 經典
- "I/O Behavior of NAND Flash" 系列（NVMe readahead、SSD pre-read）

**跟我們的差別**：OS readahead 是 **sequential pattern detection**（Smith
'78 lineage）；我們的策略是 **page-type aware**（知道 SQLite interior
page 在哪），用 madvise 做明確 hint 而不是依賴 kernel 自動推測。

#### 2.3.2 Database buffer pool warming

Oracle/PostgreSQL/DB2 都有「warmup tool」把 hot pages 預先載進 buffer
pool；學術界這條 lineage 的兩個 foundational anchor 是：

- **[Effelsberg & Härder 1984]** "Principles of database buffer management"
  *ACM TODS* 9(4):560–595——DB buffer mgmt 的奠基論文，建立了 replacement /
  prefetching / reference-count 等基本設計維度。**Pre-Buffer [Yi+26] 跟
  Chen+21 都引這篇**。
- **[Smith 1978]** "Sequentiality and prefetching in database systems"
  *ACM TODS* 3(3):223–247——**OBL (One Block Lookahead) 的原始出處**；
  也是 §2.3.1 提到的 sequential prefetching 概念主線的源頭。**Pre-Buffer**
  在 Database Prefetching 段引此為 prefetch 開山之作；**Chen+21** 把
  OBL 擴充為 K-page LookAhead 當作 ML 模型對照 baseline。

近年 ML-based 路線（已在前段討論）：[Chen+21] / [Yang+20 Leaper, PVLDB
13(12)] 用 NN 預測 page access；Pre-Buffer [Yi+26] 用 Jaccard similarity
做 hotspot matching。所有這些工作都建立在上述 Smith '78 + Effelsberg '84
的傳統上。

**跟我們的差別**：buffer pool warming 用 DBMS 自有 cache；我們用 OS page
cache + mmap、不修改 SQLite，把 prefetch 變成 application-side 工具。

**Pre-Buffer [Yi et al. 2026]** —— 最近最相關，但解的是**不同的 cold-start
問題**。他們提出 workload-aware buffer prefetching 框架，針對週期性 workload
下的 **"buffer cold-start"** ——其定義為 **hit-rate 在 hotspot shift 後的恢復
時間**（curve 從谷底回到 steady state 的秒數），prefetch 由獨立 background
thread 在 hit-rate 跌幅 ≥10% 後觸發，且使用 **Direct I/O 繞過 OS page cache**。
本研究處理的是 **OS page cache 為空時的 first-query latency**——prefetch
位於 user-facing critical path 上、與 first-query 直接競爭時間，因此
preprocessing 開銷無法藏在 background。值得注意的是，Yi et al. 在批評既有
ML-based prefetcher [Chen et al. 2021] 時明確指出："*it is also necessary
to consider the direct and indirect impact of the prefetch module on
system performance*" ——但其 evaluation（hit-rate recovery time + 總
execution time）並未將 prefetch overhead 與 query latency 分離。

**Chen+21 原文驗證**：細讀 [Chen et al. 2021] 證實 Pre-Buffer 的批評公允——他們
在 MySQL 上跑 TPC-H/DS/SSB benchmark 收集 page access trace 訓練 DNN/CNN/RNN/
LSTM/Multi-Model ensemble（8–20M 參數）預測下一個 page offset，但 (1) 訓練資
料明確採用 **"with warm-start"** trace（已避開 cold-start 場景）、(2) evaluation
只報 next-page prediction 的 **precision/recall**（Multi-Model 76–87% vs
LookAhead 20%），從未量測 NN inference 對 query latency 的衝擊、也沒量測錯誤
prefetch 的 wasted I/O 成本——即便他們自己在 §IV-B 親口寫："*wrong prefetching,
though asynchronous, will hurt the performance of the system due to the
extra I/O cost.*"並為此設計了 Decision Module。Chen+21 的 gap 是 **cost-awareness
在 design 但缺席 evaluation**；Pre-Buffer 的 gap 是 **evaluation 採用 system-level
混合指標、未分離 prefetch overhead 與 query latency**。本研究的 preprocessing-aware
end-to-end methodology 同時 close 這兩個 gap：在 SQLite cold-start 場景下把
prefetch preprocessing 與 first-query latency **顯式分開測量**、再 **sum 為
end-to-end cold-start 真實成本**。

#### 2.3.3 SQLite / mobile / embedded DB optimization

SQLite 是手機 / IoT / desktop 最廣的 DB，optimization paper 很多分散在
工程 blog：
- Google Android team 的 SQLite optimization（page size, journal mode, mmap）
- Meta 的 mobile DB pattern (Lithium / Trident)
- Apple Core Data / WAL optimization (WWDC talks)
- Academic: "Mobile SQLite Performance Study" (?)

**跟我們的差別**：既有工作多半專注「**寫入** / fsync / WAL」性能；我們專注
**read cold-start**，且明確切出「**interior 0.35% 主導**」這個 quantitative
observation。Type-aware layout rewriter (§4.1.1c) 也是 novel——既有 SQLite
fork 沒有 page-type aware physical reorder。

#### 2.3.4 SSD / NVMe page-aware optimization

把 page-type / hot-cold awareness 下放到 SSD 層：
- **NVMe Stream Directives** (NVMe spec 1.3+)
- **ZNS (Zoned Namespace) SSDs**
- **F2FS / Multi-stream SSD** 系列（USENIX FAST, SOSP）
- **FEMU** (FAST '18, Li et al.) — 我們未來 Level 2 工作的 emulator

**跟我們的差別**：本 paper Level 1 全部在 application + OS 層；
[type_aware_physical_segregation/README.md](type_aware_physical_segregation/README.md)
規劃的 Level 2 才下放到 SSD line / namespace 隔離——是 future work。

#### 2.3.5 Memory-mapped DB & mincore-based introspection

- **LMDB** (Lightning Memory-Mapped DB) — mmap-only DB，無自有 cache
- **Mincore-based working-set estimation** (少數 systems paper 用)
- **vmtouch / mincore tooling**

**跟我們的差別**：我們用 `mincore()` snapshot 推 hot set 是常見技巧，但
**把它跟 page-type classification 結合做出 2d/2e (interior + top-K leaves)
的 frugal prefetch** 是本 paper contribution；既有 mincore-based tool（如
vmtouch）只做全 page-cache preload，沒 page-type 區分。

---

## 3. Methodology

### 3.1 Test database

固定一個 reference DB，所有實驗共用：

| 項目 | 數值 |
|---|---|
| Page 大小 | 4 KB |
| 總筆數 | 600,000 rows |
| 總 page 數 | 26,331 |
| 整個 DB | ~102 MB |
| **Interior page（瓶頸）** | **92 個 → 368 KB（占 0.35%）** |
| Leaf page（資料本體） | 26,239 個 → ~102 MB（占 99.65%） |

Schema: `items(id INTEGER PRIMARY KEY, k1 INTEGER, k2 INTEGER, payload BLOB(100))`
加上一個 secondary index `idx_items_k1k2 ON items(k1, k2)`。

**重點：interior 只占 0.35%（368 KB），但每筆 query 都得用到。只要先載這 368 KB，
就能避開 cold start 的 random I/O。** 整個 paper 的研究空間就是「怎麼把這 368 KB
最有效率地預載進 memory」。

![三種 layout 下 92 個 interior page 在檔案裡的位置](figures/out/01_page_distribution.png)

*圖 1：interior page（紅色）在檔案裡怎麼擺。**1a 原始**：散落整個 102 MB；
**1b VACUUM**：略集中但仍散；**1c type-aware**：全部塞到檔頭前 400 KB，讓
prefetch 可以一口氣抓完。三 layout 共用同一份 schema 跟 600k row 內容，只是
page 物理排列不同。*

### 3.2 Workloads

選 4 種代表性 workload，每種測試 prefetch 在不同 access pattern 下的行為：

| 名稱 | 特性 | 像什麼 |
|---|---|---|
| **A** | 集中查少數熱門資料（Zipfian）| App 首頁、常開的聯絡人 |
| **B** | 平均亂查（uniform）| 隨機抽樣、爬蟲 |
| **C** | 只查最新加入的資料（檔尾）| 剛收到的訊息、剛拍的照片 |
| **D** | Write workload 產生器 | 模擬 DB 被持續 write（用在 §6.2.1 churn 實驗）|

**Design rationale**：A 是 read skew、B 是 uniform、C 是檔尾 locality，三個
covering 不同的「熱點分布」維度；D 不直接 measure latency，是 §6.2.1 churn
實驗用的 write generator。完整定義（key range、Zipf parameter、ops count）見
[overall_workloads.md](overall_workloads.md)。

**Workload generator 來源**：A (Zipfian point read) 跟 B (uniform random read)
的格式 / 分布 reference 自 [YCSB-cpp](https://github.com/ls4154/YCSB-cpp)
（C++ port of YCSB）——A 對應 YCSB-C profile（read-only, Zipfian over single
table）、B 對應 YCSB-A 的 read 部分（uniform）。我們把 YCSB 風格的 op string
（`read <key>`, `update <key>`, `scan <key> <len>` 等）保留為 workload file
格式，讓 `benchmark_harness` 一格 op 一行直接解析。C 跟 D 是我們自己加的
（high-key locality、write-heavy churn generator），YCSB 沒有對應。

### 3.3 Benchmark harness

`benchmark_harness` 是一隻 C 程式（[benchmark_harness/benchmark_harness.c](benchmark_harness/benchmark_harness.c)），
**一格量測** 的時間軸：

```
1. mmap(db, PROT_READ)                    ← harness 啟動就做
2. sqlite3_open() + PRAGMA cache_size=0   ← 預設 "warm process" 模式
3. sqlite3_prepare_v2(...)                ← statement 預先 compile
4. mincore() snapshot (resident before)   ← 量「清 cache 前有多少 resident」
5. posix_fadvise(DONTNEED)  ← 清掉 OS page cache (cold start 從這裡開始)
6. drop-caches-script (per-cell)
7. post-cold-script (prefetch tool, optional)
8. mincore() snapshot (resident after prefetch)
9. clock_gettime() start
10. for op in workload: bind + step + reset
11. clock_gettime() end
12. mincore() snapshot (resident after run)
```

每格產生：`first_query_us`、`avg_us`（整個 100k ops 平均）、`total_majflt`、
`total_minflt`、三張 residency snapshot。詳細流程見
[strategies_explained.md](strategies_explained.md)（如果存在）或
[benchmark_harness/BENCHMARK_HARNESS.md](benchmark_harness/BENCHMARK_HARNESS.md)。

### 3.4 End-to-end cold start metric

Benchmark harness 直接量到的是 `first_query_us`（**只算 SQL 那筆 query
本身的時間**），但 prefetch tool 自己也要時間（叫 OS 預先 load page、發
madvise 之類）。**真實 cold start latency** 應該是兩者之和：

$$\text{cold\_start}_{e2e} = \text{prefetch\_us} + \text{first\_query\_us}$$

其中 `prefetch_us` 來自每個 prefetch tool 自己印到 stderr 的 `time_us=...`，
我們離線量過全部 (tool, layout, workload, strategy) 組合 × 3 reps（351 cells
共 1,053 runs，存在 [calibration/prefetch_time_summary.csv](calibration/prefetch_time_summary.csv)）。

**Design rationale**：
- 直接量 `first_query_us` 是用 `clock_gettime()` 包住 SQLite `step()`，乾淨
  且 reproducible
- prefetch_us 用獨立 calibration 而非塞進 benchmark_harness，因為 madvise
  是 OS hint、不等 I/O，**離線量到的 prefetch_us 跟線上跑時幾乎一樣**（差
  異 < 5%）
- 這個 e2e metric 是 §5.5 賣點所在——它揭露 first-q 跟 preprocessing 數量
  級不同時的 trade-off

---

## 4. Strategies

三類正交，可以**自由組合**——例如「1c layout + 2c layers_5 prefetch + 4a
MAP_SHARED」是目前測過的全局最佳組合。

| 類別 | 策略 | 做法簡述 |
|---|---|---|
| **改 layout** | 1a 原始 / 1b VACUUM / **1c type-aware** | 改變 page 在檔案裡的物理排列 |
| **Prefetch** | 2a–2c（看結構）/ 2d–2e（看歷史）/ 2f（抄 cache）| First query 之前先載哪些 page |
| **Memory 共用** | 4a MAP_SHARED / 4b private buffer pool | 多 process 共用同一份 cache |

### 4.1 Layout strategies (1a / 1b / 1c)

- **1a 原始**：testdb_builder.py 跑出來的 DB，SQLite 怎麼配 page 就怎麼擺。
  Interior 跟 leaf 完全 interleaved（scatter score 0.96）。
- **1b VACUUM**：呼叫 SQLite 內建 `VACUUM;`。會重新打包，但 source code 顯示
  它**按 insertion order** 重排、**不看 page type**。實驗證實：scatter 從
  0.96 變 1.13（更散）、檔案小 ~3%、prefetch 效益**沒提升**。
- **1c Type-aware layout rewriter**（**本 paper 的 contribution C1**）：自己
  寫的 binary file rewriter
  ([layout_rewriter/layout_rewriter.c](layout_rewriter/layout_rewriter.c))。
  把 92 個 interior 全搬到 file 開頭 page 2..93（連續排列）、leaf 接著、
  freelist 與 overflow 在最後。同時 patch 所有跨頁 pointer：interior 的
  child pointer、overflow 的 next-page、freelist 的 next-trunk、page 1 header
  的 freelist pointer，並 emit SQL 修正 `sqlite_master.rootpage`。Scatter
  score 從 0.96 → 0.0001（幾乎完美 clustering）；`PRAGMA integrity_check;`
  通過。

### 4.2 Prefetch strategies (2a–2f)

cold start 後第一筆 query 之前，主動發 `madvise(MADV_WILLNEED)` 把指定 page
hint 給 OS。差別在「指定哪些 page」：

- **Structure-based**（不看歷史，只看 page 結構）
  - **2a Range**：把連續的 interior page 合成 range，每個 range 一次 madvise
  - **2b Perpage**：每個 interior page 個別 madvise
  - **2c Layers_N**：按 file offset 排序、prefetch 前 N 個 interior（B+tree
    上層）。**N=5 是 Workload A 上的 sweet spot**——僅 5 個 syscall 拿到
    -54%。
- **Access-pattern-based**（看歷史 = 跑一次 workload 後用 `mincore()` dump
  哪些 page resident）
  - **2d Access-pattern interior-only**：只 prefetch resident 的 interior。
  - **2e Access-pattern interior + top-K leaves**：2d + 加 K 個 access-count
    最高的 leaf。K ∈ {10, 50, 100, 500}。
- **SLRU-approximated**
  - **2f SLRU**：workload 結束後**不要 evict**，直接 mincore() 拍當下 resident
    set，下次 cold start 把那 ~500 個 page 全載。

完整實作細節見 [overall_strategies.md](overall_strategies.md) §二「Prefetch 策略」。

### 4.3 Memory-sharing strategies (4a / 4b)

- **4a MAP_SHARED**：SQLite 設 `PRAGMA mmap_size = file_size` 後用
  `mmap(MAP_SHARED)` 開檔，**所有 process 共享同一份 OS page cache**。
  一個 process prefetch 全部 process 受惠。
- **4b Private buffer pool per process**：傳統 read() + SQLite 內部 cache。
  每個 process 各自有 cache，N 個 process 就 N 倍 RAM。

4a 跟 4b 是對照組——驗證「MAP_SHARED 在多 process 部署下省 RAM 跟攤平
prefetch cost」的關鍵。詳見 [multiprocess/MULTIPROCESS_MMAP.md](multiprocess/MULTIPROCESS_MMAP.md)。

---

## 5. Experiment and Evaluation

### 5.1 Per-workload best methods (overview)

同一套量測基準（7 種方法 × 3 種 layout，A/B/C 同條件）下，每個情境表現最好
的方法：

| 情境 | 最佳方法 | First query | **Preprocessing** | **End-to-end = preprocessing + first-q** | First-q 改善 |
|---|---|---:|---:|---:|---:|
| **A** | 抄上次 cache | 305 → **16 µs** | **+1,808 µs** | **1,824 µs** ⚠️ | −95% (僅 first-q) |
| **B** | 抄上次 cache | 464 → **17 µs** | **+1,810 µs** | **1,827 µs** ⚠️ | −96% (僅 first-q) |
| **C** | 抄上次 cache | 671 → **17 µs** | **+1,246 µs** | **1,263 µs** ⚠️ | −97% (僅 first-q) |
| **D** | 看歷史 + 最熱 10 個 leaf node | 281 → **21 µs** | +6 µs | **27 µs** ✅ | −92% |

> ⚠️ **重要提醒**：「抄上次 cache」（2f SLRU）first-q 看起來省 95-97%，
> 但**preprocessing 自己花 1.2-1.8 ms**（比 first-q 大 80-130 倍）。
> **真實 cold start = preprocessing + first-q**，反而比 baseline 慢 2-6 倍。
> 詳見 §5.5。
>
> 想要真正讓 cold start 變快，要用 preprocessing 開銷小的策略：**A 用「prefetch
> 前 5 個 interior」(preprocessing 才 1.4 µs)、C 用「看歷史只載用過的」(2 µs)**。

![7 種策略 × 3 種 layout 跨 A/B/C 的 first query latency 比較](figures/out/05_strategy_comparison.png)

*圖 5：每個 workload × layout 下 7 種方法的 first query latency（越短越好）。
**沒有萬用解**——A 上「整理 layout + prefetch 前 5 個」就贏；C 上「看歷史」
(2d/2e) 拿下；「抄上次 cache」(2f) 三 workload 通殺，但要先 dump 一份 hot set。*

### 5.2 Best combination on Workload A

| 做法 | First query | **Preprocessing** | **End-to-end** | 改善 (end-to-end) |
|---|---:|---:|---:|---:|
| 什麼都不做（baseline）| 318 µs | 0 µs | **318 µs** | — |
| 只 prefetch 前 5 個 interior | 224 µs | **+1.4 µs** | **225 µs** | **−29%** |
| **整理 layout + prefetch 前 5 個** | **127 µs** | **+1.1 µs** | **128 µs** | **−60%** ← 結構式方法的最佳 |

> **這個策略 preprocessing 幾乎免費（1-2 µs）**，end-to-end 改善 ≈ first-q
> 改善。跟 5.1 表的「抄上次 cache」（preprocessing 1.8 ms）正好相反。

![Workload A 上 layout × strategy 的效果](figures/out/02_layout_effect.png)

*圖 2：Workload A 上，**1c type-aware + layers_5** 的組合把 first query 從
404 µs 壓到 127 µs（−69%）。**單獨 VACUUM（1b）幾乎沒幫助**——要 layout +
prefetch 一起做。*

### 5.3 Workload-dependent benefit ceiling

| 情境 | 最好能改善多少 | 為什麼 |
|---|---:|---|
| **A**（熱門集中）| **−69 ~ −91%** | Leaves 自然在 cache，只剩 interior 要救 |
| **B**（平均亂查）| −49% | 每筆都打到 cold leaf，救不掉 |
| **C**（查檔尾新資料）| −54 ~ −83% | 同上，但用「看歷史」的方法可突破 |

![A/B/C 三 workload 在 clean / churned DB 上的 N-sweep plateau](figures/out/04_nsweep_plateau.png)

*圖 4：N（prefetch 多少個 interior page）對 first query 的影響。**A 在 N=5
就到 plateau**（leaves 自然熱、只剩 interior 要救）；**B/C 要到 N≈92 才壓住**
（每筆都打到 cold leaf）。Churn 不改變 plateau 形狀。*

### 5.4 Access-pattern frugality on Workload C

不是盲目載前 N 個，而是**先觀察哪些 page 真的被用到**，再只載那些：

| 做法 | First-q 改善 | 載入次數 | **Preprocessing** | **End-to-end (1a, 1,079 µs baseline)** |
|---|---:|---:|---:|---:|
| 載全部 92 個 interior | −54% | 92 次 | +15 µs | **611 µs (−43%)** |
| **只載真正用過的 interior** | **−48%** | **4 次** ← 一樣效果，省 23 倍 | **+1.6 µs** | **247 µs (−77%)** ← e2e 最佳 |
| 再加最熱的 10 個 leaf node | **−83%** | 14 次 | +4 µs | **84 µs (−92%)** |

> 「只載真正用過的 interior」preprocessing 才 1.6 µs（**比載全部少 9 倍時間**），
> 加上 first-q 跟「載全部」差不多——**所以 e2e 才是真正最佳，不是 first-q 看
> 起來的那個**。

### 5.5 The preprocessing trade-off （本 paper 的核心觀察）

前面所有 first-q 數字都**只算 SQL 第一筆 query 的時間**——但 prefetch tool
自己也要時間（叫 OS 預先 load page、發 madvise 之類）。**真實 cold start =
preprocessing + first-q**。這個 preprocessing 開銷會讓 first-q 看起來很美的
策略，整體 cold start 反而更慢。

**一張圖看懂兩種觀點的差別**：

![純 first-query latency 比較（preprocessing 沒算進去）](figures/out/13_strategy_firstq_bars.png)

*圖 13：純 first-query latency 比較（log scale）。**2f SLRU 看起來通殺**——
17 µs across A/B/C，比 baseline 306–667 µs 短一個數量級。這是 §5.1 headline
數字的視覺版本。*

![End-to-end cold start：preprocessing + first-q stacked，跟 baseline 比](figures/out/14_strategy_endtoend_stacked.png)

*圖 14：**真實的 end-to-end cold start**。每根 bar 是 stacked：彩色底層 =
first-q (SQL 那筆)，黃色斜紋頂層 = preprocessing (prefetch tool 自己的時間)。
紅色虛線 = baseline cold start。**2f SLRU 的 bar 高高超過紅線**——A 1,825 µs
(6× baseline)、B 1,826 µs (3.9×)、C 1,262 µs (1.9×)，全部都比「什麼都不做」
更慢。其他策略（2d / 2e_K10-K500）都安全在紅線下方。*

#### 5.5.1 每種策略的 preprocessing 開銷

獨立量過每個 (策略, layout, workload) 組合，median over 3 reps
（[calibration/](calibration/)）：

| 策略 | 做什麼 | Preprocessing 時間 | 跟 first-q 比 |
|---|---|---:|---|
| **2c layers_5** | Prefetch 前 5 個 interior | **1-2 µs** | < 1% first-q ✅ 幾乎免費 |
| **2c layers_92** | Prefetch 全部 92 個 interior | **14-15 µs** | < 5% first-q ✅ 幾乎免費 |
| **2d access-pattern (只 interior)** | 看歷史只載真正用過的 interior | **2-6 µs** | < 2% first-q ✅ 幾乎免費 |
| **2e_K10 (interior + 10 個熱 leaf)** | 同上 + 加最熱 10 個 leaf | **5-8 µs** | < 5% first-q ✅ 幾乎免費 |
| **2e_K500 (interior + 500 個熱 leaf)** | 同上 + 加最熱 500 個 leaf | **80-85 µs** | 10-20% first-q ⚠️ 有點重 |
| **2f SLRU (抄上次 cache)** | 把上次 workload 結束時 cache 裡的 ~500 個 page 全載 | **1,200-1,900 µs** | **80-130× first-q** ⛔ **比 first-q 大兩個數量級** |

#### 5.5.2 真實 cold start 表現（end-to-end）

把 preprocessing 加進去之後，哪個策略真的讓 cold start 變快？以 Workload A
為例：

| 策略 | Preprocessing | First-q | **End-to-end** | **vs Baseline (505 µs)** |
|---|---:|---:|---:|---:|
| Baseline（什麼都不做）| 0 µs | 505 µs | **505 µs** | — |
| 2c layers_5 | 1.4 µs | 296 µs | **297 µs** | **−41%** ✅ |
| 1c type-aware + 2c layers_5 | 1.1 µs | 160 µs | **161 µs** | **−68%** ✅ 最佳 |
| 2d access-pattern | 5.5 µs | 222 µs | **228 µs** | **−55%** ✅ |
| 2e_K10 (+10 hot leaves) | 6.8 µs | 223 µs | **230 µs** | **−54%** ✅ |
| 2e_K500 (+500 hot leaves) | 84 µs | 81 µs | **165 µs** | **−67%** ✅ |
| **2f SLRU (抄上次 cache)** | **1,808 µs** | 14 µs | **1,822 µs** | **+261%** ⛔ **慢 3.6 倍** |

#### 5.5.3 三句話結論

1. **「抄上次 cache」(2f SLRU) 的 first-q −94% 是誤導**——preprocessing 1.8 ms
   比 first-q 14 µs 大兩個數量級，真實 cold start 反而**比 baseline 慢 3-7 倍**。
2. **2f SLRU 的價值在「跑完整段」的 avg latency**（warmup 之後 5 萬筆 query
   共省 38%），**不在第一筆**。給 batch processing、不給 cold-start critical
   path 用。
3. **真正讓 cold start 變快的是 2c/2d/2e 系列**：preprocessing 1-90 µs，跟
   first-q 相比可忽略，end-to-end 等於 first-q。**「整理 layout + 2c layers_5」
   是 cold-start 的真正贏家，−68% real**。

> 圖 8 已經點出這個 tradeoff：「Prefetcher 每 1 秒掃一次 first-q 19 µs（−94%）」
> 也是只算 first-q；端到端如果算上 prefetcher 自己跑的時間，要 cadence ≥ 30s
> 才回本（取決於 query 間隔）。

---

## 6. Discussion

### 6.1 Key findings recap

跨整個實驗 matrix 看到的四個結構性 finding（robustness 驗證在 §6.2）：

1. **少即是多**：載前 5 個 interior（−54%）比載全部 92 個（−31%）還好——載
   太多反而來不及（async madvise 還沒完成、prefetch 自己花的時間吃掉收益）。
2. **沒有通用 best strategy**：最適合載幾個 page，跟「資料怎麼排」「query
   什麼樣」強烈相關。layers_5 sweet spot 只在 A workload + 1a layout 上成立。
3. **整理 layout 對 A 是大勝（−69%），但對 B 反而變慢**——1c type-aware 把
   interior 集中後，B 的 cold leaf fault 距離反而拉長。不能無腦套用。
4. **看歷史 > 看結構**：access-pattern (2d) 只載真正用過的 page，4 次 load
   就追平 layers_92 盲載 92 次的效果。

### 6.2 Robustness checks

驗證所有 §5 結論在三條動態軸下都成立：DB 一直被 write、RAM 被砍掉、多 process
共用。

#### 6.2.1 Churn evolution（DB 被持續 write 後）

DB 被持續 write（5 萬筆 write ops）後，效益完全沒衰退（A 仍 −91%、C 仍 −54%）。

![10 個 checkpoint × 50k churn ops 下 C/A/B 三 workload 的 first query 演化](figures/out/07_churn_evolution.png)

*圖 7：DB 被持續 write 5 萬筆 ops 後，static t=0 hot pages 在 C/A/B 三種
workload 上都不衰退。B 上 access-pattern 跟盲載前 N 個沒差別（沒 hot leaf
可挑），但也不失效。*

#### 6.2.2 RAM pressure（cgroup MemoryMax=20M）

**DB ~102 MB、RAM 用 cgroup `MemoryMax=20M` 砍到 20 MB**（約 working set 的
1/5、強制 trigger page reclaim ~80%），first query 的改善幾乎不受影響——但
avg latency 跟 majflt 在某些配置會被打。

- **First query**：63 個 cell 的「20M / 不限」比值**全部落在 0.90–1.19**，
  因為 first query 只摸到少數 page、不在 reclaim 路徑上。
- **後續 query**：2f SLRU 在 1a/1c 上的 preload **被 reclaim 完整清掉**
  （majflt 從 0 → 180，avg 從 1.50 µs 退回 1.78 µs）。
- **唯一全保留組合：1b VACUUM + 2f SLRU** ——VACUUM 把 DB 壓緊到 ~100 MB，
  working set 剛好塞進 20M cgroup、preload 不被 evict（majflt 維持 0、avg
  1.50 µs）。

![RAM-pressure heatmap (20 MB cgroup vs unlimited)](figures/out/06_ram_pressure_heatmap.png)

*圖 6：把可用 RAM 砍到 20 MB（A/B/C × 3 layout × 7 策略 = 63 個 cell）。
每 cell 的「20M / 不限」比值**全部落在 0.90–1.19**——memory pressure 下
first query 仍保住，但 avg/majflt 視 layout 與策略而定。*

#### 6.2.3 Multi-process MAP_SHARED

一個 process 做 prefetch，所有共用同一份 cache 的 process 都受惠。

![Multi-process prefetch cadence 對 first query latency 的影響](figures/out/08_cadence_comparison.png)

*圖 8：writer + prefetcher + probe 三個 thread 的實驗。Prefetcher 每 1 秒掃
一次能把 first query 從 295 µs 壓到 19 µs（−94%）；每 30 秒幾乎等於沒跑。
**經驗法則：cadence ≤ query 間隔 才可靠 warm**。*

### 6.3 Practical recommendations

| 情境 | 建議做法 | First-q 改善 | **Preprocessing** | **End-to-end 真實改善** |
|---|---|---|---:|---:|
| 熱門資料集中（最常見）| Prefetch 前 5 個 interior | −54% | **1-2 µs** | ≈ −54%（preprocessing 可忽略）|
| 想追求極致 cold start | 先整理 layout，再 prefetch 前 5 個 | −69% | **1-2 µs** | ≈ **−68%** ← 真正最佳 |
| 平均亂查 / 查檔尾新資料 | 看歷史，只載用過的 + 最熱 10 個 leaf node | −83% | **5-8 µs** | ≈ **−82%** |
| **想要 batch processing 整段省時間** | 抄上次 cache (2f SLRU) | −94% (僅 first-q) | **1,200-1,800 µs ⚠️** | first-q 慢 3-6 倍 / 但全段 −38% |
| 多 process 共用 DB | 開 shared memory，背景定時 prefetch | 成本固定、效益乘以 process 數 | 同上 | 同上 |

> **「抄上次 cache」不適合 cold-start critical path**——preprocessing 太重。
> 適合「user 開了 app 之後不停打 query 一整段」這種 batch 情境。

### 6.4 Limitations

- **Machine-state drift across sessions**：clean DB 上同個 cell 跨 session 的
  絕對 µs 可能差 30-70%（同 harness、同 DB、同 code），來自 SSD 內部 SLC
  cache / wear leveling 狀態漂移 + 機器整體背景負載。我們的對策是「所有要
  互相比較的數據都在同一個 batch 內跑」（一致性 < 5%）。Page fault 數量
  完全 reproducible，只是 per-fault 時間飄。
- **Sample size**：大多數 cell 是 3 reps median；少數關鍵 cell（RAM-pressure
  matrix）是 6 reps。對於 first-q 級的 µs 量級噪音夠用，但 paper 標準通常想
  看 10+ reps + IQR/confidence interval。
- **「Warm process, cold data」cold-start 模型**（§2.2）：跟「process from
  scratch」差約 1-3 µs，對 baseline ~500 µs 來說 < 1% 但對 2f SLRU 的 14 µs
  first-q 約 ~10%。不改變結論（2f 的 1.8 ms preprocessing 仍 dominate）。
- **Workload coverage**：A/B/C 是合成的三種 access pattern；real world 行為
  可能更複雜（mixed read/write、time-of-day 變化）。new_workloads/ 已準備好
  600 個額外 workload 待你同學跑驗證。
- **未測「真正 cold reboot」cold start**：受限於 sudo 權限與機器共用，沒做
  「每筆量都 reboot」的嚴格 cold start。harness `--sqlite-open-timing=after-cold`
  可以模擬部分（重 open SQLite handle）。
- **Single-machine 結果**：所有實驗在同一台 Ryzen 9950X + NVMe 上跑。SSD
  類型 / 機器架構不同的 reproducibility 未驗證。

---

## 7. Future Work

- **Type-aware Physical Segregation (Level 2)**：把 type-aware layout 從
  filesystem 層下放到 NVMe SSD 層（用 NVMe Stream Directives 把 interior /
  leaf 分到不同 SSD line/namespace），讓 SSD GC / wear leveling 不會打亂
  layout。在 FEMU SSD emulator 上做。完整 PoC spec 已寫
  [type_aware_physical_segregation/README.md](type_aware_physical_segregation/README.md)。
- **Strict cold-start 模式**：跑 `--sqlite-open-timing=after-cold +
  --schema-init-timing=after-cold` 一輪，量化「warm process cold data」跟
  「full cold」之間的 µs 差距，把 §2.2 的「約 1-3 µs」換成精確數字。
- **new_workloads validation**（你同學 A 在做）：600 個額外 workload
  ({read,scan} × {uniform,zipf} × {full,window,tail} × 50 seeds) 跑過後，
  驗證 §5 結論的 robustness。
- **Independent verification**（你同學 B 在做）：在不同 machine / SSD 上重
  跑關鍵 cell，量化我們 §6.4 「machine drift」估計的可信度。
- **NVMe SSD page-aware GC 影響**：long-term 跑 large churn (multi-million
  ops)，看 SSD 內部 GC 對 interior page layout 的影響。

---

## 8. Conclusion

SQLite cold start 後 first query 很慢，因為要先從 disk 讀進那 **92 個關鍵的
interior page**。我們用 **prefetch（提前 load）** 把它們先放進 memory，最高
可把 first query **從 318 µs 降到 127 µs（−69%）**——end-to-end cold start
**−68%**（preprocessing 1.1 µs 可忽略）。這個方法在 DB 持續被 write、memory
吃緊、多 process 共用的情況下都站得住。

更重要的觀察：**「抄上次 cache」(2f SLRU) first-q 看起來 −94% 是誤導**——
preprocessing 1.8 ms 比 first-q 14 µs 大兩個數量級，**真實 cold start 反而
慢 3-7 倍**。2f SLRU 的價值在「跑完整段」的 avg latency（−38%），不在第一筆。
這個 trade-off 在 prefetch 文獻中很少被明說。

---

## 9. References

### 9.1 Code & Data

| 想看什麼 | 去哪 |
|---|---|
| 每一維實驗的完整數字（19 維）| [overall_results.md](overall_results.md) |
| 每個策略的原理與狀態 | [overall_strategies.md](overall_strategies.md) |
| 四種 workload 的定義 | [overall_workloads.md](overall_workloads.md) |
| 完整研究故事（按週）| [README.md](README.md) |
| Preprocessing time calibration | [calibration/](calibration/) |
| Type-aware layout rewriter source | [layout_rewriter/](layout_rewriter/) |
| Benchmark harness source | [benchmark_harness/](benchmark_harness/) |
| Figures | [figures/out/](figures/out/) |

### 9.2 External References

**Tools / Code repositories：**

| Resource | Where | 用途 |
|---|---|---|
| **YCSB-cpp** | https://github.com/ls4154/YCSB-cpp | Workload A/B 的格式 / 分布 reference（YCSB-C Zipfian、YCSB-A uniform）——我們延續 YCSB 的 op string 風格作為 workload file 格式（見 §3.2） |
| SQLite | https://www.sqlite.org/ | 被研究的 DB engine（讀路徑、B+tree、page cache 行為）|
| FEMU | https://github.com/MoatLab/FEMU | Future Work §7 提到的 SSD-level evaluation 平台 |

**Papers：**

| # | Citation | 在本研究中的角色 |
|---|---|---|
| [Smith 1978] | Smith, A. J. "Sequentiality and prefetching in database systems." *ACM Transactions on Database Systems* 3(3):223–247 (1978) | §2.3.1 + §2.3.2 foundational ancestor——**OBL (One Block Lookahead) 的原始出處**，sequential prefetching 概念主線的源頭。Chen+21 把它擴充為 K-page LookAhead baseline；Linux readahead 繼承同一條 lineage |
| [Effelsberg & Härder 1984] | Effelsberg, W., Härder, T. "Principles of database buffer management." *ACM Transactions on Database Systems* 9(4):560–595 (1984) | §2.3.2 foundational anchor——DB buffer management 奠基論文，建立 replacement / prefetching / ref-count 設計維度。Pre-Buffer 跟 Chen+21 都引這篇 |
| [Yi+26] | Yi, J., Wang, X., Jin, P. "Workload-Aware Buffer Prefetching for Database Systems." *Data Science and Engineering* (2026). https://doi.org/10.1007/s41019-025-00342-6 | §2.3.2 對比——他們的 "buffer cold-start" = hotspot-shift recovery，背景 thread + Direct I/O；我們處理 OS page cache cold-start + critical-path preprocessing accounting |
| [Chen+21] | Chen, Y., Zhang, Y., Wu, J., Wang, J., Xing, C. "Revisiting data prefetching for database systems with machine learning techniques." *ICDE* (2021), pp. 2165–2170. DOI: 10.1109/ICDE51399.2021.00218 | §2.3.2 引用——ML-based prefetcher（DNN/CNN/RNN/LSTM/Multi-Model，8–20M 參數）。**訓練 trace 採 warm-start**，evaluation 只報 precision/recall，未量測 NN inference 對 latency 的衝擊、也未量測 wasted-prefetch I/O 成本——雖其 §IV-B 自承「wrong prefetching... will hurt the performance of the system due to the extra I/O cost」。Pre-Buffer 的批評因此公允；本研究的 preprocessing-aware methodology 正是 fill 這個 gap |
| 其他 papers / blog posts | §2.3 candidate reading list | survey 進度見 `related_work_reading_list.md`（待建立）|

---

## Appendix A: Supplementary Figures

### A.1 Latency CDF（cold → warm 過渡區）

![前 50 筆 query 的累計 latency（cold→warm 過渡區）](figures/out/03_latency_cdf.png)

*圖 3：前 50 筆 query 的累計時間。Prefetch 把「cold→warm」的過渡時間整段
壓掉；第 50 筆之後所有方法都收斂到 ~1.5 µs/query。*

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

完整數據 + 兩張 9-cell grid 圖在 [figures/out/11_nsweep_full.png](figures/out/11_nsweep_full.png)
（clean DB, A/B/C × 1a/1b/1c）跟 [figures/out/12_nsweep_full_churn.png](figures/out/12_nsweep_full_churn.png)
（churn DB, A/B/C）。Sparse 6-pt 跟 dense 93-pt 切片的對照、9/12 cell 結論
不變但 3 個 sweet spot 被漏掉的分析，見 overall_strategies.md 2c bullet 跟
overall_workloads.md 「已完成的覆蓋」表。

---

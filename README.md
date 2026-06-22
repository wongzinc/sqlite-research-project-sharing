# SQLite Research Project

研究 SQLite cold-start 行為、page residency、prefetch 與 page layout 的工具與實驗集合。

---

## 📖 這個專案在做什麼 — 故事版

### 第 0 章：起點 — 一個被忽略的 0.35%

SQLite 是世界上部署量最多的 DBMS（地球上每支手機裡都有好幾個）。它用 **B+tree** 存資料，整個 DB 是一個 flat 的 4 KB page 陣列。每筆 query 都得從 root 走到 leaf，**沿路經過的 interior page 全部都要在記憶體裡**。

但 interior page 通常只佔整個 DB 的 **0.35%**（92 個 / 26,331 個）。聽起來微不足道，直到你考慮**冷啟動**：

> App 剛開機、SQLite 程式剛啟動、或久未使用 → OS page cache 是空的 → 第一筆 query 要把那 ~4 個 interior page 從 disk 拉進來 → **first query 比後續慢 10–100 倍**。

問題清楚了：**能不能在第一筆 query 之前，先把那 92 個關鍵的 interior page 預載入 cache？**

這就是整個 repo 的研究主題。

### 第 1 章：先看清楚地形 — `classify_pages/`

要 prefetch interior page，首先得**知道哪些 page 是 interior**。SQLite 自己不會告訴你 — 它只給你 SELECT。

所以第一步是寫一個**不依賴 libsqlite** 的 page-type 分類器，直接讀 SQLite 的 file format spec、解析每個 page 的 b-tree flag byte：

```
0x02 → interior_index    0x0A → leaf_index
0x05 → interior_table    0x0D → leaf_table
```

跑完 `classify_pages test.db`，得到一份 CSV：每個 page 編號 + 它的型別 + 它在檔案裡的 offset。配上 `plot_pages.py` 可以畫出 page layout 圖，肉眼看到 interior 散得多開。

**這個工具還順手算了一個叫 scatter score 的數字** — 0 代表 interior 全擠在檔頭、1 代表均勻分布。**真實 DB 的 scatter ≈ 0.96**。Interior pages 不只少，還散得到處都是。這意味著 OS sequential readahead 救不了我們，**必須顯式 prefetch**。

### 第 2 章：建一台儀器 — `benchmark_harness/`

要證明 prefetch 有沒有用，需要可重現的測量。`benchmark_harness` 就是這個專案的測量儀器：

1. mmap 整個 DB
2. 跑 `madvise(MADV_DONTNEED)` 或 `drop_caches` 假裝冷啟動
3. 用 `mincore()` 記錄哪些 page 還在 RAM（cold snapshot）
4. （如果要測 prefetch）執行 prefetch script，再 mincore 一次（after-prefetch snapshot）
5. 逐筆跑 workload，用 `clock_gettime()` + `getrusage()` 記 latency + page fault delta
6. 跑完再 mincore 一次（after-run snapshot）

產出兩種 artifact：**per-operation CSV**（每筆 query 一列）+ **run record log**（整次的 metadata 與 residency 分布）。

> **🔧 最近一次更新**：原本 benchmark_harness 沒有把「協助測量 prefetch」當主任務寫進去；後來加了 `--post-cold-script` 讓 prefetch + residency snapshot 進入 cold boundary 之內，現在量到的 `first_query_latency_us` 才能真正反映「prefetch 之後、第一筆 query 的延遲」。

> **📐 P0 pipeline（2026-06，量測標準）**：所有正式數字都跑在 P0 下——全機 `/usr/local/sbin/drop-caches` 冷清 + harness 內建 `--verify-hotset`（`cold_pct`/`delivery_pct`，取代外部 residency_checker）+ 統一 `warmer` 引擎的 **pread(oracle)/async(hint) 雙臂** + 每 (workload,layout) 一個 **no-prefetch baseline** 當分母;另含釘核升頻、op[0]=read 強制、`cold_pct>1%` 剔除、hotset checksum 凍結、`read_ahead_kb=128`。一鍵跑 [`run_p0.py`](run_p0.py),完整規格見 [IMPLEMENTATION_PIPELINES.md §3](IMPLEMENTATION_PIPELINES.md)。**本 README 下方的歷史結果數字屬 pre-P0,待 master rerun 取代。**

### 第 3 章：第一次嘗試 — Range vs Perpage（Week 9）

有了測量工具，先試最直覺的兩種 prefetch 策略：

| 策略 | 做法 |
|------|------|
| `range` | 把相鄰的 interior page 合成 range，每個 range 一次 `madvise(MADV_WILLNEED)` |
| `perpage` | 每個 interior page 都單獨一次 madvise |

**結果讓人意外：**

| 策略 | syscall | first query | 改善 |
|------|---------|-------------|------|
| baseline | 0 | 73 µs | — |
| `range` | 87 | 53.6 µs | -27% |
| `perpage` | 92 | 48.0 µs | -34% |

`range` **只省了 5 次 syscall**（92→87），而且**反而比 perpage 慢**。為什麼？因為 interior pages scatter 太嚴重，相鄰的根本沒幾個；而 `range` 涵蓋的大區間裡夾雜了一堆 leaf pages 也被一起載進來，浪費 I/O。

**第一個學到的教訓**：當 page 已經散開時，「批次合併」這種傳統 I/O 最佳化技巧無效。

### 第 4 章：找到甜蜜點（Week 10）

如果不該載**所有**的 92 個 interior page，那載多少才剛好？掃 N = 1, 5, 10, 20, 46, 92：

```
N=1    →  38 µs  (-48%)
N=5    →  33 µs  (-54%) ← 甜蜜點
N=10   →  44 µs  (-39%)
N=20   →  35 µs  (-53%)
N=46   →  41 µs  (-45%)
N=92   →  50 µs  (-31%) ← 越多越糟
```

呈現一個 **U 型曲線**。為什麼？

`madvise(MADV_WILLNEED)` 是**非同步**的 — 它叫 OS 排程 I/O 就馬上回傳，**不等載完**。

- N 太少（1 個）：上層 interior 載到了，中層還沒，第一筆 query 還是會 fault
- **N=5 剛好**：5 個 page 只花 94 µs 就 prefetch 完，OS 在第一筆 query 跑到前剛好載完
- N 太多（92 個）：prefetch syscall 本身花了 2,229 µs，benchmark 開始時 OS 還沒載完，後面 query 還是要 fault；而且 prefetch 本身已經吃掉時間

**第二個學到的教訓**：**load 5 個 page（佔整個 DB 的 0.02%）就能砍掉一半以上的 cold-start latency**。Prefetch 不是越多越好，要剛好讓 OS 來得及做完。

### 第 5 章：VACUUM 的背叛（Week 11）

直覺：SQLite 內建的 `VACUUM` 命令會把 DB 整理得更緊湊，layout 應該變整齊，prefetch 應該更有效。

**實際跑出來完全相反：**

| 條件 | scatter | first query | 改善 |
|------|---------|-------------|------|
| Before VACUUM + prefetch 5 | 0.96 | 33.4 µs | -54% |
| After VACUUM + prefetch 5 | **1.13** | **66.2 µs** | **-9%** |

scatter 從 0.96 變 1.13（**更散**），prefetch 效益從 -54% 退化到 -9%。

翻 SQLite source code（`src/vacuum.c` 的 `sqlite3RunVacuum()`）發現原因：**它按 row 的插入順序重排 page，完全沒考慮 page type**。新的 interior page 全部被推到一大堆 leaf page 之後，變得**更**分散。

**第三個學到的教訓**：SQLite 內建的 VACUUM 是 type-unaware 的，反而破壞 cold-start 性能。**這是一個改進 SQLite 本身的具體切入點：實作 type-aware VACUUM，把 interior 集中到檔頭**。

### 第 6 章：免費的乘數效應 — `multiprocess/`（Week 12）

到目前為止，所有實驗都假設只有一個 process。但實際應用（手機、伺服器）常常有**很多 process 共用同一個 DB**。

問題：如果一個 process 做 prefetch，其他 process 拿不拿得到好處？

關鍵在 SQLite 的 `PRAGMA mmap_size`：開啟它之後 SQLite 用 `mmap(MAP_SHARED)` 開檔，理論上**所有 process 共享同一份 OS page cache**。

實驗驗證：fork 3 個 child 各讀 1/3 的 DB，parent 自己沒讀任何東西，最後 mincore 看到 **25,613 / 25,613 全 resident**。

對照組（每個 process 用 private buffer pool）：3 個 process 各自佔 10 MB RAM，**完全不共享**。

| 模式 | 3 process | 10 process | 100 process |
|------|-----------|------------|-------------|
| MAP_SHARED mmap | ~100 MB | **~100 MB** | **~100 MB** |
| Private buffer pool | ~30 MB | ~100 MB | ~1 GB |

**第四個學到的教訓**：**一個 process 呼叫一次 `madvise(MADV_WILLNEED)`，所有 mmap 同一個 DB 的兄弟 process 都立刻拿到加速**。在多 process 部署下，prefetch 的成本被攤平，效益被放大。

### 第 7 章：層次三 — 動態世界的測試 `prefetch_churn/`

到這裡為止的實驗都用**靜態**的乾淨 DB。但真實 app 不停在寫入、刪除、更新 — page layout 會隨時間漂移。所以最新一輪實驗（「層次三」）測：**隨著 DB 被 churn，prefetch 的效益會怎麼變化？**

設計：同一個 DB，跑 10 個 checkpoint，每個 checkpoint 之間執行 5,000 筆 mixed workload（含 1,000 insert + 1,000 delete）製造 churn。每個 checkpoint 做兩件事：
1. 跑 `classify_pages` 看當下 layout
2. drop cache → 跑 cold-start query → 量 latency

兩組對照：**有 prefetch** vs **無 prefetch**。

結果：

| | baseline | ck001 | ck005 | ck010 |
|---|---|---|---|---|
| no_prefetch first_query | 4,918 µs | 4,511 | 5,709 | **6,892** |
| prefetch first_query | 5,130 µs | 5,398 | 7,055 | **6,300** |

**觀察：**
- 兩組的 first_query latency 都隨 churn 累積而上升（4,918 → 6,892 µs）— 這是 scatter 增加造成的
- 新出現的 interior page 全部在檔尾（page 26,393、26,474、…、27,030）
- baseline 時 prefetch 沒效益（甚至略差），但 **churn 累積後 prefetch 開始幫忙，平均省 ~590 µs（~10%）**
- 寫入越多次，OS 的 sequential readahead 越無效，**顯式 prefetch 越不可取代**

**第五個學到的教訓**：prefetch 在真實的、被使用過一段時間的 DB 上**仍然有效**，但 baseline 也變得更慢，所以絕對省的時間（μs）比百分比更值得看。

**補測 — N sweep on churned DB（2026-05）**：上表只測 `N=5`。後來把 churned DB 上的 N 補滿 {0,1,5,10,20,46,92}，每 N × 11 checkpoint 共 77 runs（換成 unprivileged `posix_fadvise` 避開 sudo，所以絕對 µs 跟上表不可比，但 sweep 內部 N 之間相對效益可比）：

| N | avg first-q (µs, ck001–010) | vs N=0 |
|---:|---:|---:|
| 0 (no prefetch) | 462 | — |
| 1 | 449 | −2.8% |
| 5 | 413 | −10.6% |
| 10 | 425 | −8.0% |
| 20 | 418 | −9.5% |
| 46 | 406 | −12.1% |
| **92** | **213** | **−53.9%** |

`N=92` 在 churned DB 上**獨大**，且在 11 個 checkpoint 全部維持優勢。原因跟第 11 章驚訝 1 同源：churn 製造的新 interior page 全在檔尾，按 file offset 排前 N 永遠選不到熱頁，**必須全載**。這也是「layers_N 是 Zipfian-friendly heuristic、不是 universal 解」這條觀察首次在動態 DB 上被驗證。

> 📂 詳見 [overall_results.md 第十維](overall_results.md#第十維--n-sweep-on-churned-db-2026-05-補測)。

> 📊 **想看跨實驗的策略矩陣與每個 workload 的最佳組合？** 看
> [overall_results.md](overall_results.md)（結果）／
> [overall_strategies.md](overall_strategies.md)（策略目錄）／
> [overall_workloads.md](overall_workloads.md)（workload 定義）。
> 下文 第 8–12 章 用故事方式串起這份資料。

### 第 8 章：54% 跟 10% 看起來矛盾，其實不矛盾

```
prefetch_vacuum:  73 µs   → 33 µs   省 40 µs   (-54%)  ← Zipf workload + 乾淨 DB
prefetch_churn:   6,892 µs → 6,300 µs 省 592 µs (-10%)  ← uniform workload + churned DB
```

**百分比看起來差 5 倍，絕對時間卻是 prefetch_churn 省得多 14 倍。** 為什麼？

一筆冷啟動 query 的成本拆解：

```
[Interior page faults] + [Leaf page fault] + [SQLite CPU]
       ↑                       ↑
   prefetch 能解決         prefetch 解決不了
                          （不知道 query 要哪一筆）
```

- **Zipf workload**：少數熱 key 反覆被查，leaf 自然變熱；Interior 是唯一 bottleneck → prefetch 把它解掉就大勝
- **Uniform workload**：每筆 query 都打到沒看過的 leaf → leaf fault 不可避免 → prefetch 只能解決一部分

百分比看起來低不是 prefetch 沒用，是 baseline 本來就被「leaf 一定冷」拉高了。

### 第 9 章：救回來了 — Type-aware VACUUM（`layout_rewriter/`）

第 5 章的 cliffhanger：SQLite 內建 VACUUM 把 prefetch 效益從 -54% 打到 -9%。如果我們**自己寫一個 type-aware 的版本**，把 interior 全部排到檔頭，會發生什麼？

`layout_rewriter/layout_rewriter.c` 直接讀 source DB、重寫一個新 DB，把所有 interior pages 排到 page 2–93（連續），leaves 排在後面。**整個過程不碰 SQLite source code，純粹操作 file format**。

```
scatter score:     0.96 (原始)   →  0.0001 (type-aware)
                              ↓
       和 SQLite VACUUM 的 1.13（更散）正好相反方向
```

跑同一組 prefetch 策略對照：

| Layout | baseline | range | perpage | **layers_5** |
|---|---:|---:|---:|---:|
| 原始 | 318 µs | 370 µs (+16%) | 319 µs (+0%) | 224 µs (-30%) |
| SQLite VACUUM | 333 µs | 330 µs (-1%) | 338 µs (+2%) | 234 µs (-30%) |
| **Type-aware** | 404 µs | 387 µs (-4%) | 273 µs (-32%) | **127 µs (-69%)** ← 全局最佳 |

**第六個學到的教訓**：type-aware VACUUM 不只**救回**了 prefetch 效益（第 5 章 -9% → 現在 -69%），還**超越**原始 layout 的 -54%。第 5 章的研究問題「能不能救回來」答案是：**能，而且贏更多**。

但⚠️：type-aware 在 baseline 反而**變慢** 27%（318 → 404 µs），因為第一個 cold leaf 被推到 file 後段、cold fault 跑得更遠。**只有打開 prefetch 才會贏**。如果產品不打算 ship prefetch，type-aware layout 是反指標。

> 📂 見 [layout_rewriter/LAYOUT_REWRITER.md](layout_rewriter/LAYOUT_REWRITER.md) 與 [overall_results.md 第二維](overall_results.md#第二維--layout-對-strategy-的放大效果workload-a-only)。

### 第 10 章：偷看 OS 的 cache — 2f SLRU（`prefetch_slru/`）

到第 9 章為止，所有 prefetch 都只 prefetch **interior page**（92 個）。leaf 是 cold fault，是宿命。

新策略：跑完一次 workload **不要 evict**，直接用 `mincore()` dump 當下 OS page cache 裡的所有 resident page —— 大約 4,000 個（interior + 用到的 leaf）。下次 cold start 對這 4,000 個 page 一一呼叫 `madvise(MADV_WILLNEED)`。

這是 SLRU（segmented LRU）的「protected segment」概念用 mincore 近似，不用碰 SQLite 內部，~70 行 C：

```
first query latency:  251 µs (baseline)  →  14 µs (2f SLRU)   ← -94%
```

第一筆 query 砸進的是熱 leaf，幾乎是 RAM cache hit。**但**：

- 4,000 個 `madvise` syscall 自己花 **7.5 ms**
- 端到端 cold start：251 µs → **7,269 µs**（比 baseline 慢 29×）

**所以 2f 不是「降低 cold start」的策略，是「working-set preload」的策略。** 整段 workload 跑完：

| 情境 | baseline | 2f SLRU | 改善 |
|---|---:|---:|---:|
| Cold tap 到第一筆結果 | **251 µs** | 7,269 µs | **慢 29×** |
| 全 100k queries 跑完 | 411 ms | **256 ms** | **省 38%** |

**第七個學到的教訓**：策略不只一個維度。`layers_5` 是「點開就看一筆」的最佳解；`2f SLRU` 是「點開後跑一段」的最佳解。**問問題之前先問你的應用屬於哪一種**。

> 📂 見 [prefetch_slru/PREFETCH_SLRU.md](prefetch_slru/PREFETCH_SLRU.md)。

### 第 11 章：不同 workload 翻轉策略排名

前面所有實驗只跑兩個 workload（Zipfian + uniform churn）。後來補上 Workload B (uniform random point-read) 和 Workload C (high-key uniform read)，跑了完整的 4 prefetch × 3 layout × 3 workload 矩陣：

**驚訝 1：layers_N 的「N=5 甜蜜點」是 Zipfian-only。**

| Workload | 最佳 N | 改善 |
|---|---|---|
| A (Zipfian) | N=5 | -54% |
| B (Uniform) | N=5~92 都一樣 | -48% (plateau) |
| C (high-key) | **必須 N=92** | -46% |

C 上的「query 走的 interior path 不在 file 前段」—— 按 offset 排前 N 選不到熱頁，必須**全載**。**「layers_N」其實是 Zipfian-friendly 啟發式，不是 universal 解。**

> ➕ **後續驗證（2026-05）**：把 N sweep 跑在 **churned DB** 上（10 個 checkpoint 累積 50,000 ops），N=92 同樣是唯一贏家（−54%），其他 N 全部退化。Churn 把新 interior pages 推到檔尾，跟 C 的「熱頁不在 file 前段」結構同源 → 這條 Zipfian-friendly 觀察在動態 DB 上也成立。見第 7 章補測。

> ➕ **後續驗證（2026-05，第 12 維）**：把 N sweep 跑在 **Layout 1c (type-aware)** × A/B/C 上，發現「最佳 N 跟 layout 強耦合」：
> - **A on 1c**: layers_N 上限從 1a 的 -26% 跳到 **-71%**；N≥5 全 plateau（U 型曲線消失，因為 TA 把 interior 集中到檔頭，任何 N≥5 都 cover）
> - **C on 1c**: **N=46 -32%（最佳）、N≥5 全 -29~32%**；N=92 反而退到 -10%（inverted cliff）—— TA 解掉 C「必須載全 92 個」的問題
> - **B on 1c**: layers_N 失效（N=5 +4%、最佳 N=46 -23%）；1c 對 B 是 layout-hostile
>
> 詳見 [overall_results.md 第十二維](overall_results.md#第十二維--n-sweep--layout-1c-type-aware--abc)。

> ➕ **後續驗證（2026-05，第 13 維）**：新增 **Workload Z (Zipfian low-key
> hotspot, keys [1, 1000], α=0.99)**，跑 N sweep × 3 layout，回答「熱點落在
> file 哪段會不會改變結論」：
> - **跟 A 結果同形（差異 ≤ 5pp）**：1a 最佳 N=20 −31%、1b 最佳 N=5 −31%、
>   1c 最佳 N=92 −72%；hotspot location 不是 prefetch 效益的主要變因
> - **N=1 universally worse**：on 1a/1b 比 baseline 還慢 ~+22%（純 madvise
>   syscall overhead、root page 已 cached、無 coverage 受益），跟 A 的 N=1
>   退化同源 → 確認「N=1 從來不是合理選擇」
> - **1c 永遠最強**：跨 4 個 N 值（0/5/20/92）1c 都贏 1a/1b 30~50%
>
> 詳見 [overall_results.md 第十三維](overall_results.md#第十三維--n-sweep--workload-z-zipfian-low-key-hotspot--1a1b1c)。

**驚訝 2：Type-aware layout 不是 universal best。**

- Workload A: **-69%**（最強）
- Workload B: **+8%（反效果！）** —— ta 把 leaf 推到高 offset，B 的 cold leaf fault 跑更遠
- Workload C: -37%（搭 perpage 才好；搭 layers_5 -32%）

**驚訝 3：SQLite VACUUM 在 Workload C 上反而讓 baseline 變快 -6%**（A/B 變慢 +5~8%）。VACUUM 把整個 file 壓緊後，high-key region 的 seek 距離縮短。**「VACUUM 一律有害」是第 5 章的過度結論。**

**第八個學到的教訓**：沒有 universal 最佳策略。**配方依 workload 而定**：Zipfian → ta + layers_5；uniform 全段 → orig + layers_5；file-tail uniform → ta + perpage 或 orig + 2f SLRU。

> 📂 見 [overall_results.md](overall_results.md) 第六/七/八/九維。

### 第 12 章：解掉 Workload C — Access-pattern prefetch（2026-05）

第 11 章發現 layers_N 在 Workload C 上「必須 N=92」才能達到 -46%。**為什麼？** 因為 layers_N 按 **file offset** 排前 N，C 的熱頁不在檔頭。如果改按 **access count** 排前 N 呢？

實作：跑一遍 workload 拿到「真實被 walk 的 interior pages + 真實 hottest leaves」（`prefetch_access/`），然後 cold start 時 madvise 那些 page。**這需要先有一輪 access history**——所以是 warm-start 策略，不是 first-ever-launch 策略。

**2d（interior-only）—— 用 4 個 syscall 追平 layers_92 的 -46%**：

| Workload × Layout | syscalls | 改善 |
|---|---:|---:|
| C × 1a (orig)   | **4**  | **-47.6%** |
| C × 1b (vacuum) | 4      | -47.4% |
| C × 1c (ta)     | 32     | -52.2% |
| B × 任一 layout | 14-31  | -47~51% |
| A × 任一 layout | 14-21  | **+0~3%**（持平 baseline——A 熱點集中在前段，已被 readahead cover）|

2d 在 C 上把 syscall 從 92→4（省 23×）、改善持平 layers_92。這是 file-offset ordering vs access-count ordering 的本質差異。

**2e（interior + top-K hot leaves）—— 邊際 syscall 把 first-query 推到接近 0**：

| Workload × Layout × K | syscalls | 改善 |
|---|---:|---:|
| C × 1a × K=10 | **14** | **-83.9%** |
| C × 1b × K=10 | 14 | -83.0% |
| C × 1c × K=10 | 42 | -82.3% |
| C × 任一 K=500 | ~514 | -98~99% |
| A × 任一 K=500 | ~510 | -73~77% |
| B × 任一 K=500 | ~510 | -49~58% |

**驚訝**：2e_K10 在 C 上把 first-query 從 baseline 切掉 **84%**，**超過 2f SLRU 的 -77%**——而 2f 要 dump 整個 mincore (~4030 leaves)，2e_K10 只要 14 個 madvise。**邊際 syscall 報酬率：每多 1 個 madvise ≈ 救 18 µs first-query latency**。

> ⚠️ **歷史 bug**：先前 prefetch_access.c 的 cap_leaf ternary 兩條 branch 都返回同樣值，導致所有 2e_K* 實際上跑的是 2d（n_leaf=0）。已修復、重跑、結果都是合法的。

**對齊原始 spec 的 ratio variant（策略 3a / 3b，2026-05 補跑）：** 原 prefetch spec 把「interior + leaf」拆成兩種 ratio：**3a = 7:3、3b = 5:5**。Codebase 用 K (top-K leaves) 參數化，所以 3a → K=40、3b → K=92。但 2e 只 prefetch **resident interior**（warmup 真的觸碰過的，4–32 個，不是全部 92 個），實際 ratio 因 (workload, layout) 變動於 9:91 ~ 44:56 之間，**只有 ta layout 接近 spec 的 44:56**。

| | K=40 (3a) | K=92 (3b) |
|---|---:|---:|
| A × 1a | 233 µs | 212 µs |
| A × 1b | 251 µs | 214 µs |
| **A × 1c** | **250 µs** | **410 µs ⚠️** |
| B × 1a–1c | 251–254 µs | 243–345 µs |
| C × 1a–1c | 78–82 µs | 79–82 µs |

**最反直覺的點：A × 1c × K=92 = 410 µs，比 K=40 (250) 跟 K=500 (119) 都差**。ta layout 把 interior 集中後，加 92 個熱 leaves 引發 OS readahead pollution；直到 K=500 把整個熱集都載入才回穩。**這個非單調 K=92/100 hump 是 ta-specific**（1a/1b 上沒有）。C 則任何 K 都 saturate ~80 µs；B 沒有真的 hot leaf，ratio 怎麼分都差不多。**結論：ratio 不是 first-q 的主要 axis**，K 才是；除了 A × ta × K≈92 這個 anti-pattern 之外。視覺化見 [figures/out/10_ratio_sweep.png](figures/out/10_ratio_sweep.png)。

> **編號註：** 原本「策略 3a/3b」指 multi-process memory-sharing（MAP_SHARED / Private buffer pool），**已重新編號為 4a/4b**，把 3a/3b 留給 ratio prefetch。

**RAM 緊環境下還成立嗎？** systemd-run --user --scope -p MemoryMax=20M（< working set ~16 MB + DB 107 MB）跑完整 756-cell 矩陣（**A/B/C × 1a/1b/1c × 7 strategies × {20M, none} × 6 reps**）：

| 觀察 | 數字 |
|---|---|
| First-q ratio (20M / unlimited) 全部範圍 | **[0.90, 1.19]**（63 cells） |
| 2e_K10 on C × 任一 layout × 20M | **-82~88%** (跟 unlimited 一致) |
| 2f SLRU first-q on 任一 (WL, layout) × 20M | **15-19 µs** (-95~98%, unlimited 一致) |
| 2f SLRU majflt on 1b vacuum × 20M | **0** (unlimited 也是 0) |
| 2f SLRU majflt on 1a/1c × 20M | 172-181（**preload 被 evict、跌回 base level**） |
| 2f SLRU avg_us on 1b vacuum × 20M | **1.50/1.56**（unlimited 也是 1.50/1.56） |
| 2f SLRU avg_us on 1a/1c × 20M | 1.79-1.87（**退到 base level**） |

**兩個關鍵發現：**
1. **First-q 對 RAM 壓力幾乎免疫**：63 cells 沒有任何一個 ratio > 1.2x。「cgroup MemoryMax 會打殘 prefetch」這個直覺被推翻——first-q 只需要 ~4 個 page 在 cache 裡，cgroup 20 MB 完全充足。
2. **1b vacuum 是 2f SLRU 的「avg/majflt RAM-pressure-immune」唯一 layout**：A/B/C × vacuum 在 20M 下 2f 仍保持 majflt=0、avg=1.50（unlimited 一致）。1a/1c 下 2f preload 被 evict 跌回 base level。**「2f SLRU + 1b vacuum」是 RAM 緊環境的全保留組合**。

**第九個學到的教訓**：**Access-count ordering 完勝 file-offset ordering**。當你有「最近的 query log」時，**4-14 個精選 syscall 比 92 個無腦載入更有效**。代價是需要一輪 warm-up 才能拿到 access count——適合 background prefetcher / SLRU 模式，不適合 cold first-ever-launch。**且整套 access-pattern prefetch 在 cgroup 20M 下優勢完全保留**。

> 📂 詳見 [overall_results.md](overall_results.md) 第十四維（2d）、第十五維（2e）、第十六維（RAM-pressure 完整 756-cell 矩陣）、**第十七維（3a / 3b ratio = K=40 / K=92）**。

### 第 13 章：目前進度與下一步

#### ✅ 已完成

- **工具鏈完整**：classify_pages、benchmark_harness、residency_checker、prefetch_layers、layout_rewriter、prefetch_slru、prefetch_access 全部可用
- **prefetch 策略全覆蓋**：2a Range / 2b Perpage / 2c Layers_N sweep / **2d Access-pattern interior-only** / **2e Access-pattern interior + top-K leaves** / 2f SLRU 在 Workload A/B/C × Layout **1a / 1b / 1c** 上完整跑過。**2f SLRU 是 layout-agnostic**（三個 layout first-q 都 13–16 µs；只有 1b 能省 ~17% prefetch overhead）。**2c layers_N 完整跨三 layout 矩陣**（A/B/C × {1a, 1b, 1c} × N∈{0,1,5,10,20,46,92}）：最佳 N 跟 layout 強耦合（1c × A: N=92 -71%、1c × C: N=46 -32%、1c × B: layers_N 失效）。**2d/2e access-pattern prefetch 主要打到 Workload C**：2d 在 1a × C 只用 **4 個 syscall** 拿到 -47.6%（追平 layers_92 的 -46% 但 syscall 從 92→4，省 23×）；2e_K10 在 C × 任一 layout 上用 14-42 syscalls 拿到 **-82~84%**（明顯超過 2f SLRU 的 -77%）
- **3 個層次都有結果**：
  1. **找到 prefetch 甜蜜點**（A 上 N=5、-54%）
  2. **解掉了 VACUUM 的問題**（type-aware layout_rewriter，A 上 -69%）
  3. **動態世界與 working-set preload**（churn 上 -10%、2f SLRU 在 A/B 全 workload -38%）
- **驗證了 MAP_SHARED 共享**：一個 process prefetch，所有人受惠
- **跨 workload 矩陣**：Workload B（uniform）、C（high-key uniform）和 A 一起跑 4 prefetch × 3 layout 的完整對照

#### 🔬 已回答的研究問題

1. **2d/2e access-pattern prefetch 能否在 Workload C 上以 <10 個 syscall 達到接近 layers_92 的 -46% 改善？**

   答：**可以、而且超過預期**。2d 用 **4 個 syscall** 在 C × 1a 上拿到 -47.6%（追平 layers_92 的 -46%，syscall 數從 92→4 省 23×）；2e_K10 用 14 個 syscall 在 C × 1a 上拿到 **-83.9%**（甚至超越 2f SLRU 的 -77%）。Access-count ordering 完勝 file-offset ordering，邊際 syscall 成本極低（每多 1 個 madvise ≈ 救 18 µs first-query latency）。
   資料來源：[overall_results.md 第十四維](overall_results.md#第十四維--2d-access-pattern-prefetch-interior-only--abc--3-layouts)、[第十五維](overall_results.md#第十五維--2e-access-pattern-prefetch-interior--top-k-leaves--abc--3-layouts--kk10k50k100k500)；matrix CSV [prefetch_access/runs/matrix_2d_results.csv](prefetch_access/runs/matrix_2d_results.csv) + [matrix_2e_results.csv](prefetch_access/runs/matrix_2e_results.csv)；圖 [figures/out/05_strategy_comparison.png](figures/out/05_strategy_comparison.png)。

2. **2f SLRU 在 RAM 緊（cgroup MemoryMax=20M）時還有用嗎？**

   答：**first-q 完全免疫；avg/majflt 是否退化依 layout 而定**。756-cell 全矩陣（A/B/C × 1a/1b/1c × 7 strategies × {20M, none} × 6 reps）發現：(a) **63 cells 的 first-q ratio 全部落在 [0.90, 1.19]**——2f SLRU first-q 在 20M 下仍 15-19 µs；(b) **1b vacuum 是唯一讓 2f 在 20M 下仍保持 majflt=0 / avg=1.50 的 layout**——1a/1c 下 2f preload 被 evict、avg/majflt 跌回 base level（first-q 仍贏）。「2f SLRU + 1b vacuum」是 RAM 緊環境的全保留配方。
   資料來源：[overall_results.md 第十六維](overall_results.md#第十六維--ram-pressure-完整矩陣cgroup-memorymax20-mb-abc--1a1b1c--base-2d-2e_k1050100500-2f_slru)；matrix CSV [prefetch_access/runs/matrix_ram_full_results.csv](prefetch_access/runs/matrix_ram_full_results.csv)（756 cells × 6 reps）；圖 [figures/out/06_ram_pressure_heatmap.png](figures/out/06_ram_pressure_heatmap.png)（✅ P0：`run_p0.py --mem-limit 20M` vs unlimited）。

3. **多 process 場景下，prefetch worker cadence 該多大？**

   答：**cadence ≤ query 間隔 才可靠 warm**。在 writer + prefetcher + probe 三線程的最小實驗中（gap=3 s），cadence=1 s 把 first_q 從 295 µs 壓到 19 µs（-94%），cadence=5 s 只有 ~50% hit rate（177 µs, -40%），cadence=30 s 等同無 prefetcher。1 s prefetcher 成本是 ~14 syscalls/s，但 N 個 reader 共享同一個 MAP_SHARED page cache，所以 prefetcher 開銷固定、benefit 乘 N。
   資料來源：[multiprocess/runs_prefetch_cadence/README.md](multiprocess/runs_prefetch_cadence/README.md)；matrix CSV [multiprocess/runs_prefetch_cadence/cadence_results.csv](multiprocess/runs_prefetch_cadence/cadence_results.csv)；圖 [figures/out/08_cadence_comparison.png](figures/out/08_cadence_comparison.png)（⚠️ P0 cold-start 模型外：cadence 為 multiprocess warm-keeping、非 cold-start TTFQ）。

4. **2d/2e access-pattern prefetch 在 churned DB 上會不會退化？**

   答：**在 C × insert / A × delete / B × churn 三個正交設置下都不會退化**。10 checkpoints × 50k 寫入 ops，靜態 hotpages（t=0 計算）在四組設置都撐住：(a) **C × insert-churn**: acc_2e_K10 -91% / acc_2d -50%（hot leaves 跟 insert target 重疊）；(b) **A × delete-heavy churn (B1)**: 2e_K10_static **-92.4%** / 2d_static **-91.8%** / 2e_K50_static -91.5%，全部贏過 layers_92（-91.4%）；原假設「delete from id=1 會擾動 A 的低 id 熱 keys」被推翻——50k delete 集中在窄區、B+tree 不立即 merge、hot leaves 持續被 read 命中。(c) **A/B × layers_N × churn (B2)**: A layers_5 -90.7% / B layers_5 -45.9%，churn 不改變 N-sweep plateau 形狀。(d) **B × access-pattern × churn (B3)**: 2d -45.7% / 2e_K10 -48.8% / 2e_K50 -47.7%，跟 file-offset 的 layers_5 (-45.9%) / layers_92 (-49.2%) 打平——uniform reads 沒有自然熱葉，top-K leaves 等同隨機選頁、沒帶來額外效益，但也不 decay。結論：access-pattern × static hot 是 production-ready baseline；plateau 高度由 workload leaf-warmth 決定（Zipfian -91% / uniform/high-key -49~54%），不由 churn 決定。
   資料來源：[overall_results.md 第十八維](overall_results.md#第十八維--churn-擴充abc--churn--2c-layers_n--2d--2e_kab--churn--statictk0-hotpages)（B1/B2/B3）；run dirs [prefetch_churn/runs_access_churn/](prefetch_churn/runs_access_churn/README.md)（C insert-churn）、[runs_access_churn_a/](prefetch_churn/runs_access_churn_a/README.md)（A delete-churn）、[runs_access_churn_b/](prefetch_churn/runs_access_churn_b/README.md)（B mixed-churn）；layers_N × churn run dirs [runs_nsweep_a/](prefetch_churn/runs_nsweep_a/README.md) + [runs_nsweep_b/](prefetch_churn/runs_nsweep_b/README.md)；圖 [figures/out/07_churn_evolution.png](figures/out/07_churn_evolution.png)（✅ P0：`run_p0_churn.py`，量測走 run_p0、churn 用 harness write 製造）。

---

## Repository Layout

每個實驗都是獨立的子目錄，包含自己的程式碼、文件與數據：

```
├── overall_results.md      # 📊 跨實驗策略 × workload 結果矩陣（最新）
├── overall_strategies.md   # 📋 所有策略目錄與狀態
├── overall_workloads.md    # 📋 Workload A/B/C/D 定義
├── classify_pages/         # SQLite page-type 分類器
├── benchmark_harness/      # Cold-start workload benchmark 工具
├── residency_checker/      # Page residency 檢查工具
├── prefetch_vacuum/        # 早期 prefetch + VACUUM 實驗（第 3–5 章）
├── prefetch_churn/         # Prefetch + page churn 主實驗（第 7 章）
├── multiprocess/           # Multi-process mmap 實驗（第 6 章）
├── layout_rewriter/        # ⭐ Type-aware layout rewriter + cross-layout 矩陣（第 9, 11 章）
├── prefetch_slru/          # ⭐ 2f SLRU prefetch via mincore（第 10 章）
├── prefetch_access/        # ⭐ 2d/2e access-pattern prefetch + 756-cell RAM-pressure 矩陣（第 12 章）
└── frontend/               # 16-week 研究計畫 UI 元件
```

每個實驗目錄裡都同時放：
- 程式碼（C source、Python script、shell script）
- 該實驗的文件（`*.md`）
- 該實驗使用或產生的資料（`workloads/`、`results/`、`logs/` 等）

對照故事章節：

| 目錄 | 章節 | 角色 |
|------|------|------|
| `classify_pages/` | 第 1 章 | 看清 DB 內部結構的基礎工具 |
| `benchmark_harness/` | 第 2 章 | 測量儀器 |
| `residency_checker/` | 第 2 章 | 輔助 residency 量測 |
| `prefetch_vacuum/` | 第 3–5 章 | 找到甜蜜點 + 揭露 VACUUM 問題 |
| `multiprocess/` | 第 6 章 | 證明 mmap 共享，prefetch 效益乘 N |
| `prefetch_churn/` | 第 7–8 章 | 動態世界驗證 + workload 偏斜度討論 |
| `layout_rewriter/` | 第 9, 11 章 | Type-aware layout + cross-workload 對照矩陣 |
| `prefetch_slru/` | 第 10 章 | mincore-based working-set preload |
| `prefetch_access/` | 第 12 章 | Access-pattern prefetch (2d/2e) + 756-cell RAM-pressure 矩陣 |
| `frontend/16week_plan.jsx` | — | 整個研究計畫的 UI tracker |

## 各實驗目錄

### [classify_pages/](classify_pages/) — SQLite Page Classifier

不依賴 libsqlite 的 page-type 分類器，直接照 SQLite file format 解析。

- `classify_pages.c` — C 分類器，輸出 CSV
- `plot_pages.py` — matplotlib 視覺化 + scatter-score 診斷
- `build_testdb.py` — 建立符合研究 schema 的 test DB

```bash
gcc -O2 -Wall -o classify_pages classify_pages/classify_pages.c
python3 classify_pages/build_testdb.py
./classify_pages test.db > pages.csv 2> stats.txt
python3 classify_pages/plot_pages.py pages.csv page_layout.png
```

### [benchmark_harness/](benchmark_harness/) — Cold-start Benchmark Harness

觀察 SQLite workload 在 cold-start 情境下的 latency / page fault / residency。詳見 [benchmark_harness/BENCHMARK_HARNESS.md](benchmark_harness/BENCHMARK_HARNESS.md)。

- `benchmark_harness.c` — 主程式
- `benchmark_harness_analyze_residency_by_page_type.py` — 配合 classify_pages 分析 residency
- `benchmark_harness_plot_latency_vs_faults.py` — latency vs faults 圖
- `benchmark_harness_plot_results.py` — 結果圖
- `benchmark_harness_residency_report.py` — residency 報告
- `workloads/workload_a_zipfian.txt` — 測試用 workload

### [residency_checker/](residency_checker/) — Residency Checker

檢查 SQLite database 檔案中每個 page 是否 resident。詳見 [residency_checker/RESIDENCY_CHECKER.md](residency_checker/RESIDENCY_CHECKER.md)。

### [prefetch_churn/](prefetch_churn/) — Prefetch Churn Experiment（主實驗）

外層 orchestration script，循環執行 classify → prefetch → benchmark → 寫入造成 page churn，量測 prefetch 對 cold-start query latency 的效果如何隨 page layout churn 變化。詳見 [prefetch_churn/SQLITE_PREFETCH_CHURN_EXPERIMENT.md](prefetch_churn/SQLITE_PREFETCH_CHURN_EXPERIMENT.md)。

- `sqlite_prefetch_churn_experiment.py` — orchestration script
- `join_and_plot_pages.py` — 合併 page 與 residency 資料、繪圖
- `testdb_builder.py` — 建立 benchmark 用的大型 DB
- `drop_caches.sh` — root helper，清空 Linux page cache
- `workloads/` — page churn workload 檔案
- `results/` — 各 checkpoint 的 churn / prefetch summary CSV（含 `nsweep_churn_*.csv` 補測結果）
- `runs_nsweep/` — N∈{0,1,5,10,20,46,92} × 11 checkpoint sweep（unprivileged `posix_fadvise` evict）
- `runs_access_churn/` — 2d / 2e_K10 access-pattern prefetch × 50 k 寫入 churn（**靜態 t=0 hotpages 即可，2e_K10 -91%**）
- `logs/` — benchmark_harness run 紀錄

### [multiprocess/](multiprocess/) — Multi-process mmap 實驗

詳見 [multiprocess/MULTIPROCESS_MMAP.md](multiprocess/MULTIPROCESS_MMAP.md) 與 [multiprocess/MADVISE_KERNEL_NOTES.md](multiprocess/MADVISE_KERNEL_NOTES.md)。

- `runs_prefetch_cadence/` — **prefetch worker 排程實驗**：writer + prefetcher + probe 三線程，掃 cadence ∈ {1 s, 5 s, 30 s, never}。**結論：cadence ≤ gap_s 才可靠 warm**（cadence=1 s, gap=3 s 拿到 -94%）。詳見 [multiprocess/runs_prefetch_cadence/README.md](multiprocess/runs_prefetch_cadence/README.md)

### [prefetch_vacuum/](prefetch_vacuum/) — Prefetch + VACUUM 實驗

詳見 [prefetch_vacuum/PREFETCH_VACUUM.md](prefetch_vacuum/PREFETCH_VACUUM.md)。

### [layout_rewriter/](layout_rewriter/) — Type-aware Layout Rewriter + 跨 layout/workload 矩陣

從 source DB 直接寫一個 type-aware layout 的新 DB（interior 全排到 page 2-93 連續區），不碰 SQLite source code。包含 cross-workload × cross-layout 完整對照矩陣（第六/七/八/九維）。詳見 [layout_rewriter/LAYOUT_REWRITER.md](layout_rewriter/LAYOUT_REWRITER.md)。

### [prefetch_slru/](prefetch_slru/) — 2f SLRU Prefetch（mincore-based）

跑完一次 workload 後用 `mincore()` dump 當下 OS page cache 的 residency snapshot，下次 cold start 全部 `madvise(MADV_WILLNEED)`。**完全不用攔截 SQLite 內部**，~70 行 C。詳見 [prefetch_slru/PREFETCH_SLRU.md](prefetch_slru/PREFETCH_SLRU.md)。

### [prefetch_access/](prefetch_access/) — Access-pattern Prefetch (2d/2e) + RAM-pressure Matrix

從上一輪 query log 推出 page access count，把 madvise 預算花在「最常被讀的」interior + 最熱 K 個 leaves。2d = interior-only (4-92 syscalls)、2e_K = interior + top-K leaves。**Workload C × 1a 上 2d 只用 4 個 syscall 拿到 -47.6%**（追平 layers_92 的 -46%，syscall 從 92→4 省 23×），**2e_K10 在 C × 任一 layout 用 14-42 syscalls 拿到 -82~84%**（超越 2f SLRU 的 -77%）。包含 756-cell RAM-pressure 完整矩陣（A/B/C × 1a/1b/1c × 7 strategies × {20M, none} × 6 reps）。詳見 [prefetch_access/PREFETCH_ACCESS.md](prefetch_access/PREFETCH_ACCESS.md)。

### [frontend/](frontend/) — 16-week Research Plan UI

React 元件，呈現 16 週研究計畫。

## What classify_pages does

1. 讀 100-byte database header；取出 `page_size` (offset 16)、`page_count` (offset 28)、`first_freelist_trunk` (offset 32)。
2. 走 freelist trunk chain，標記所有 trunk + leaf freelist page。
3. 標記保留的 lock-byte page（若在檔案範圍內）。
4. 對其餘每個 page 讀 b-tree flag byte：
   - `0x02` → interior index
   - `0x05` → interior table
   - `0x0A` → leaf index
   - `0x0D` → leaf table
   - 其他 → overflow（b-tree cell 的內容延續）
5. 輸出 `page_number,page_type,file_offset` 每 page 一列。

Page 1 特別處理：它的 b-tree flag byte 在 file offset 100（在 100-byte db header 之後），不在 offset 0。

## Scatter score

`classify_pages/plot_pages.py` 對 interior pages 計算 scatter score：

- **0.0** = 完全集中在檔案開頭
- **1.0** = 均勻分布在整個檔案

真實世界的 database（以及 VACUUM 之後的 database）會接近 1.0 — 這正是本工具要量化的現象。type-aware layout 演算法應該能把這個數字推向 0.0。

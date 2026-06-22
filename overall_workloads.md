# Overall Results — Workload 説明

這個檔案說明 repo 裡**現階段實際使用**的 workload，以及每個 workload 對應到哪個實驗、想模擬什麼情境。

所有 workload 都跑在同一個 reference DB 上 (`testdb_builder.py` 產生的
`items(id PK, k1, k2, payload BLOB(100))`，**600,000 rows**)。

> 🆕 **2026-06-19 P0 Pipeline 統一**：所有 workload 的 cold-start measurement
> 機制已統一為 P0 pipeline——harness MADV chain (`--cold-advice dontneed`) +
> `/usr/local/sbin/drop-caches` setuid wrapper 全機 drop + harness 內建
> `--verify-hotset`（`cold_pct`/`delivery_pct`,非外部 residency_checker；措辭 2026-06-22 校正）。
> 歷史上各 workload 跨 sub-project 用不同機制量測（per-file
> posix_fadvise / system sudo drop_caches / prefetch_churn 跳過 MADV chain），
> 這是 [CONTRADICTIONS.md](CONTRADICTIONS.md) 30 條矛盾的程式碼根因，已在
> commit `691bd6b` + `fc998cb` 統一。詳見
> [IMPLEMENTATION_PIPELINES.md](IMPLEMENTATION_PIPELINES.md)。
>
> 本檔內所有 workload **定義不變**（key 範圍、分布、ops 數），但既有
> measurement 數字（baseline latency / 改善 %）需要在 P0 pipeline 下重跑驗證
> 才能列入論文最終版。

---

## Reference DB 結構

**Schema：** `items(id INTEGER PRIMARY KEY, k1 INTEGER, k2 INTEGER, payload BLOB(100))`
加上一個 secondary index `idx_items_k1k2 ON items(k1, k2)`。

**核心數字（layout 1a 原始 DB）：**

| 項目 | 數值 |
|---|---|
| `PRAGMA page_size` | **4096 bytes (4 KB)** — SQLite 預設 |
| 總 row 數 | **600,000** |
| 總 page 數 | **26,331** |
| 整個 DB 大小 | **107,851,776 bytes ≈ 102.86 MiB（~102 MB）** |
| **Interior pages** | **92 個 → 92 × 4 KB = 368 KB（0.35%）** |
| **Leaf pages** | **26,239 個 → 26,239 × 4 KB ≈ 102.5 MB（99.65%）** |

**比例直觀感受：** Interior 跟 Leaf 的數量比 ≈ **1 : 285**；大小比 ≈ **368 KB : 102 MB**。
**Interior 全載只需 368 KB，就可避開 cold start 時 92 次 4 KB random I/O。**

**Interior 細分（92 = 51 table interior + 41 index interior）：**

| Page type | 個數 | 用途 |
|---:|---:|---|
| `interior_table` | 51 | `items` table B+tree 的內部節點 |
| `interior_index` | 41 | secondary index `idx_items_k1k2` 的內部節點 |
| **合計** | **92** | |

**三個 layout 的 DB 大小對照：**

| Layout | 檔案大小 | Page count | Interior | Leaf |
|---|---|---|---|---|
| **1a 原始（orig）** | 102.86 MiB | 26,331 | **92**（368 KB）| 26,239 |
| **1b VACUUM** | 100.05 MiB | 25,613 | 85（340 KB）| 25,528 |
| **1c Type-aware** | 102.86 MiB | 26,331 | **92**（368 KB）| 26,239 |

資料來源：[layout_rewriter/runs/classify_before.csv](layout_rewriter/runs/classify_before.csv)（1a/1c）、
[layout_rewriter/runs/classify_vacuum.csv](layout_rewriter/runs/classify_vacuum.csv)（1b）。

**為什麼只有 1b VACUUM 變小、1c 不變？**

- **1b VACUUM = 整庫打掉重建+壓實**，所以 page 數和檔案都變小；**1c type-aware
  只把 page 重新排位置、不重塞資料**，所以 page 數/大小跟 1a 完全一樣（只有
  scatter 變了，見下表）。
- **1b 省下來的 718 個 page 全部來自 secondary index，table 一個都沒少：**

  | Page type | 1a / 1c | 1b VACUUM | 差異 |
  |---|---:|---:|---:|
  | `interior_table`（items 表）| 51 | 51 | **0** |
  | `leaf_table`（items 表資料）| 19,984 | 19,984 | **0** |
  | `interior_index`（k1k2 索引）| 41 | 34 | **−7** |
  | `leaf_index`（k1k2 索引資料）| 6,255 | 5,544 | **−711** |
  | **合計** | **26,331** | **25,613** | **−718** |

- 原因：`items` 的主鍵 `id` 是**遞增插入**，leaf 一頁塞滿才開新頁、本來就很密，
  VACUUM 沒得壓；但 secondary index `idx_items_k1k2(k1,k2)` 是**亂序建的**，
  page split 讓索引頁只塞到 ~60–90% 滿，VACUUM 改成按 key 排序灌入、把索引葉
  子塞緊（−711 葉子 ≈ −11%），葉子變少後上層 index interior 也跟著少 7 個
  （92→85 的 interior 減少**全部**是 41→34 的 index interior）。

**為什麼這 92 個 interior page 是重點？**

- Interior pages 只占整個 DB 的 **0.35%**（92/26,331），但 **每筆 query 都得從 root 走到 leaf**，沿路經過的 interior page **全部必須在記憶體裡**才能繼續往下找。
- Cold start 時，這 92 個 page **每個都會觸發一次 disk I/O**（4 KB random read，HDD 上 ~5-10 ms，SSD 上 ~50-100 µs）。
- Leaf page 雖然占 99.65%，但每筆 query 通常只命中 1-2 個 leaf；而且熱 keys 反覆被查，leaf 自然 cache warm。
- → **整個 project 的目標：用 prefetch 把這 92 個 interior page 提前載進 OS page cache，避開 cold-start 的 random I/O。**

**Interior page 的 file 散佈情況（scatter score）：**

| Layout | Interior page 位置範圍 | Scatter score | 意義 |
|---|---|---|---|
| 1a orig | page 2 到 page 26,007 | **0.96** | 散佈於整個 file（接近 uniform） |
| 1b vacuum | 跟 1a 類似 | **1.13**（更散） | VACUUM 沒幫忙，反而稍微更散 |
| 1c type-aware | page 2 到 page 93（連續）| **0.0001** | 全部集中到檔頭、幾乎完美 clustering |

> Scatter score 定義：interior pages 的相鄰 offset 差的中位數 / 「理想連續」的中位數。0 = 完美連續，1 = uniform 散佈。

---

這樣不同 workload 的結果可以橫向比較。

Workload 格式（`benchmark_harness` 讀的）每行一個 op：
```
read <id>
update <id>
insert <id>
scan <id> <len>
readmodifywrite <id>
```

> Op string 格式 reference 自 [YCSB-cpp](https://github.com/ls4154/YCSB-cpp)
> （C++ port of YCSB）。Workload A 對應 YCSB-C profile（read-only,
> Zipfian over single table），Workload B 對應 YCSB-A 的 read 部分
> （uniform random read）。C 跟 D 是我們自己加的（high-key locality
> 與 write-heavy churn generator），不在 YCSB 原本的 6 個 profile 裡。

---

## Workload A — Zipfian Point Read（YCSB-C 風格）

**檔案：** [benchmark_harness/workloads/workload_a_zipfian.txt](benchmark_harness/workloads/workload_a_zipfian.txt)
**規模：** 100,000 ops，全部 `read`
**Key 範圍：** id ∈ [8, 99997]（只打 DB 前 1/6 的 id 區段）
**分佈：** 強 Zipfian skew
- 100,000 次查詢只觸及 **23,253 個 unique key**（76% 是 repeat query）
- **Top 100 個熱 key 吃掉 42.3% 的流量**
- 最熱的單一 key (`id=74406`) 被查 **7,752 次**（單 key 佔總流量 7.75%）

**模擬什麼：** 真實 App 的「熱資料反覆被打」情境 — 使用者常開的聯絡人、最近瀏覽
的相簿、首頁那幾筆 item。少數熱 key 把對應 leaf page 撐成熱頁，**leaf 自然會
warm；唯一還是 cold 的是 interior page**。所以這個 workload 是 prefetch 的最佳
舞台，會放大 interior prefetch 的效益。

**用在哪：**
- `prefetch_vacuum/` 第 9–11 週的全部實驗（baseline / range / perpage / layers N）
- `layout_rewriter/` 的 type-aware vacuum 端到端驗證（-69%）
- `layout_rewriter/runs/` 的 1b VACUUM 補測、N sweep × {orig, vacuum} 全矩陣（找到 A vac 新甜蜜點 N=20）
- `prefetch_slru/` 的 2f SLRU 驗證（orig + vacuum DB，first-q -94%、全 workload -39%）

**為什麼這個 workload 會給「-54%」、「-69%」、甚至「-94%」這種看起來很漂亮的
數字：** 因為 cold start 的 cost 被拆成「interior fault + leaf fault + CPU」，Zipfian 下
leaf 部分被反覆查詢拉進 cache，**剩下的瓶頸只有 interior**，prefetch 一解就
見效。而 2f SLRU 連 leaf 一起 preload，連那點 leaf cold fault 都消掉。

---

## Workload B — Uniform Random Point Read

**檔案：** [benchmark_harness/workloads/workload_uniform.txt](benchmark_harness/workloads/workload_uniform.txt)
**規模：** 100,000 ops，全部 `read`
**Key 範圍：** id ∈ [1, 99999]（同 Workload A 的 1/6 區段）
**分佈：** 均勻
- 100,000 次查詢觸及 **63,138 個 unique key**（多數查詢是新的）
- 最熱的 key 也只被查 7–8 次
- 每 10k id 區段平均 ~10,000 次（誤差 < 5%）

**模擬什麼：** 沒有熱點的 OLTP/批次掃描情境，例如「按 id 一筆筆檢查」、隨機
sampling、爬蟲式存取。**每筆 query 都打到沒看過的 leaf**，leaf fault 不可避免。

**用在哪：**（最初是對照組，後來變成完整實測 workload）
- `layout_rewriter/runs/` 的 1b VACUUM 補測、1c type-aware 補測、N sweep × {orig, vacuum} 全矩陣
  - **發現一**：B 上 N sweep 從 N=5 開始全 plateau（沒有 A 的 U 型曲線）
  - **發現二**：ta + layers_5 在 B 上反而 +8%（不是 universal best）
- `prefetch_slru/` 的 2f SLRU 驗證（orig + vacuum DB，first-q -94%、全 workload -38%）
- 原始定位：當 Workload A 量出「prefetch 省了 54%」，B 回答「這效益只在熱點下
  才有意義嗎」 — 答案是 prefetch 仍然有效，但比例會被「無法被解決的 leaf
  fault」攤薄

---

## Workload C — High-key Uniform Read（churn 後段查詢）

**檔案：** [prefetch_churn/workloads/page_churn_benchmark_high.txt](prefetch_churn/workloads/page_churn_benchmark_high.txt)
**規模：** 100,000 ops，全部 `read`
**Key 範圍：** id ∈ [590000, 609999]（**只打 DB 末段 20k id**，含 churn 後新增的 id）
**分佈：** 均勻覆蓋這 20k 個 id（剛好每個 id 平均被打 5 次）

**模擬什麼：** 「新加入的資料馬上被讀取」— 例如剛收到的訊息、剛拍的照片、剛
push 的 commit。**重點不是熱點，而是 id 落在哪個 file region**。Churn 過程持續
INSERT 會把新資料放在檔尾，這個 workload 就在量「檔尾新資料 cost start 的 latency
怎麼隨 churn 累積而漂移」。

**用在哪：**
- `prefetch_churn/` 的 10 個 checkpoint：每個 checkpoint 之間先用 Workload D
  製造寫入壓力，然後 drop cache，再跑這個 workload 量 cold-start latency
  - 原本只跑 N=5（第四維）
  - **後續 N sweep 補測**：[`prefetch_churn/runs_nsweep/`](prefetch_churn/runs_nsweep/) 跑了
    N=0/1/5/10/20/46/92 × 10 checkpoints，見 [overall_results.md 第十維](overall_results.md#第十維--n-sweep--workload-c--churned-db補齊-prefetch_churn-缺口)
- `layout_rewriter/runs/` 的 1b VACUUM、1c type-aware、N sweep × {orig, vacuum}
  全矩陣
  - **關鍵發現**：C 上 layers_N 必須 N=92（載全部 interior）才有 -46% 改善，
    N≤46 只有 ~15%。原因：C 走的 interior path 不在 file 前段，按 offset 排
    top-N 完全選錯 page。**這直接證明「layers_N 是 zipfian-friendly 啟發式」**
  - **churned DB 上同樣的形狀**（第十維）：N=92 -54%、N≤46 plateau ~10%
- `prefetch_slru/` 的 2f SLRU 驗證（C 上 hot set 只 1.6 MB，prefetch 開銷
  只 1.9 ms vs A/B 的 7.5 ms — 是 2f 的甜蜜情境）

**為什麼選 high-key 而不是低 key：** 因為 prefetch_churn 想觀察 layout 隨寫入
漂移的效果，而新 interior page 都會配在檔尾（id 590k+），打這段最能看到 layout
惡化的影響。**意外副作用**：因 leaves 高度集中在檔尾，C 也成了 2f SLRU 的最
小 hot set 對照點。

---

## Workload D — Mixed Write-heavy Churn Generator

**檔案：** [prefetch_churn/workloads/page_churn_write.txt](prefetch_churn/workloads/page_churn_write.txt)
**檔案規模：** 100,000 ops，混合操作（**檔內定義**）
**每 batch 實際用量：** 5,000 ops（**取前 5,000 行**，跑 10 batch = 累計 50,000 ops）
**Op 組成：**

| op | 次數 | 佔比 |
|---|---:|---:|
| `update` | 30,000 | 30% |
| `insert` | 20,000 | 20% |
| `read` | 20,000 | 20% |
| `readmodifywrite` | 20,000 | 20% |
| `scan <len>` | 10,000 | 10% |

**Key 行為：**
- `insert` 從 id = 600,001 開始往上長（DB 原本 600k 筆，所以每 batch 都是真
  新資料、不是 overwrite）
- `update` / `read` / `rmw` / `scan` 都打既有 id 範圍
- `readmodifywrite` 被 harness 預設 remap 成 DELETE（見 [project-churn-rmw-delete-remap](memory/project-churn-rmw-delete-remap.md)）——raw 檔沒 `delete` 字樣但有實際刪除

**模擬什麼：** **不是用來測 latency 的**。它是 churn generator — 製造大量
INSERT/UPDATE/DELETE 的寫入壓力，讓 SQLite freelist 重新分配、interior pages
分裂、layout 隨時間漂移。

**用在哪：** `prefetch_churn/` 的 checkpoint 之間。每個 checkpoint 之間執行
5,000 ops 的這個 workload（取前 5,000 行），跑 10 次累積 50,000 ops。然後在每個
checkpoint 用 Workload C 量 cold-start latency，看「prefetch 在被 churn 過的
layout 上還剩多少效益」。

> ⚠️ **規模標示落差（[CONTRADICTIONS.md](CONTRADICTIONS.md) #29）**：「**檔案
> 規模 100,000 ops**」跟「**實際每 batch 只用 5,000 × 10 batch = 50,000 ops**」
> 是兩個不同概念，過去文件只標 100,000 容易讓人誤以為單次跑滿。**已修法**：
> 上方欄位現在同時標兩個數字。**論文 §3.2 引用此 workload 時應寫**：「Workload D
> 是 churn 寫入產生器，**每次 checkpoint 之間執行 5,000 ops、共 10 個 checkpoint**，
> 累積影響 DB layout 演化」。

---

## Workload 與實驗的對照表

| 實驗 | 用的 workload | 想回答的問題 |
|---|---|---|
| `prefetch_vacuum/` (Week 9–11) | A (Zipfian) | Prefetch interior pages 在熱點 workload 下能省多少？甜蜜點是 N=幾個 page？|
| `layout_rewriter/` (type-aware vacuum 端到端) | A (Zipfian) | 把 interior 重排到檔頭，能不能救回 prefetch 效益？(-69%) |
| `layout_rewriter/runs/` (1b VACUUM × B/C) | B + C | VACUUM 對 baseline 和 prefetch 的影響在非 Zipfian workload 上是什麼樣 |
| `layout_rewriter/runs/` (1c type-aware × B/C) | B + C | ta layout 是否 universal best？(答案：B 上反效果) |
| `layout_rewriter/runs/` (N sweep × A/B/C × {orig, vacuum}) | A + B + C | 「N=5 甜蜜點」是 zipfian-friendly 還是 universal？(答案：zipfian-only) |
| `prefetch_slru/` (2f SLRU × A/B/C × {orig, vacuum}) | A + B + C | mincore-dumped resident set preload 在三種 workload 的效益 (first-q -94%、全 workload A/B -38%、C -7%) |
| `prefetch_churn/` 量測 (N=5 only) | C (high-key uniform) | Layout 隨 churn 漂移後，prefetch 效益怎麼變？|
| `prefetch_churn/runs_nsweep/` (N=0,1,5,10,20,46,92) | C (high-key uniform) | churned DB 的 N sweep 形狀是否跟乾淨 DB 一致？(答案：完全一致，N=92 -54%) |
| `prefetch_churn/` churn 生成 | D (mixed write) | 製造真實的 layout 漂移壓力（不量 latency）|
| `multiprocess/` | 不用 workload（只測 residency / RSS）| MAP_SHARED 是否真的跨 process 共享 page cache？|

---

## 為什麼需要這四種 workload，而不是只用一個

不同 workload 拆解 cold-start latency 的不同 component，缺一不可：

```
[Interior page fault]  +  [Leaf page fault]  +  [SQLite CPU]
        ↑                          ↑
   prefetch 能解決              prefetch 解決不了
                                （workload-dependent）
```

- **Workload A (Zipfian)** 把「leaf fault」這項壓低（leaf 自然熱），讓 interior
  fault 成為唯一瓶頸 → 量出 prefetch 的**上界效益**
- **Workload B (uniform)** 讓「leaf fault」這項變最大，prefetch 只能解決剩下
  的 interior 部分 → 量出 prefetch 的**下界效益**
- **Workload C (high-key uniform)** 同 B 的分佈但鎖定檔尾，跟 Workload D 配合 →
  量「layout 漂移」隨時間的影響
- **Workload D** 不為了 latency 而存在，純粹是製造寫入歷史，讓 layout 偏離
  testdb_builder 剛建好的乾淨狀態

---

## 已完成的覆蓋（A/B/C 三維 × 全策略矩陣）

對照原本只有「A → prefetch_vacuum + layout_rewriter; C → prefetch_churn; B 只
是對照組」的設計，目前實際已跑：

| | A (Zipfian) | B (Uniform) | C (high-key) |
|---|---|---|---|
| **Layout 1a (orig)** | ✅ 全策略 + **RAM 20M** + **dense N=0..92** | ✅ 全策略 + **RAM 20M** + **dense N=0..92** | ✅ 全策略 + **RAM 20M** + **dense N=0..92** |
| **Layout 1b (VACUUM)** | ✅ baseline + range/perpage/layers_5 + **N sweep + 2f SLRU + 2d/2e + RAM 20M** + **dense N=0..92** | ✅ 全策略 + **2d/2e + RAM 20M** + **dense N=0..92** | ✅ 全策略 + **2d/2e + RAM 20M** + **dense N=0..92** |
| **Layout 1c (type-aware)** | ✅ baseline + range/perpage + **N sweep** + 2f SLRU + **2d/2e + RAM 20M** + **dense N=0..92** | ✅ baseline + range/perpage + **N sweep** + 2f SLRU + **2d/2e + RAM 20M** + **dense N=0..92** | ✅ baseline + range/perpage + **N sweep** + 2f SLRU + **2d/2e + RAM 20M** + **dense N=0..92** |
| **Churn 漂移** | ✅ **N sweep + 2d/2e × delete-churn** + **dense N=0..92 × churn** | ✅ **N sweep + 2d/2e × churn** + **dense N=0..92 × churn** | ✅ 10 checkpoints × **N sweep + 2d/2e × insert-churn** + **dense N=0..92 × churn** |
| **RAM-pressure 全矩陣** | ✅ 7 strategies × 1a/1b/1c × {20M, none} × 6 reps | ✅ 同左 | ✅ 同左 |

B 早就不再只是「對照組」 — 它是 prefetch 失敗模式（leaf fault 主導）和 ta
layout 反效果（+8%）的主要證據來源。

RAM-pressure 矩陣現已涵蓋 **9 個 (workload × layout) cell × 7 個策略 × 2 個 mem 上限**，
全部以 6 reps median 聚合（756 cells，第十六維）。原本只測 A × 1a × 4 策略
的 48-cell 縮影矩陣完全被取代，且新舊矩陣在 A × 1a × 4 策略上誤差 ≤ 3 µs
（交叉驗證）。


# New Workloads
請參考new_workloads 資料夾底下的 README.md

**Dense N=0..92 全 sweep（第十九維）** 進一步把每個 (workload × layout) 的
layers_N 從 6 個採樣點補成全 93 個值 × 3 reps：clean DB 2,511 cells + churn DB
3,069 cells = **~5,580 額外 benchmark**。發現 sparse 6-pt 在 9/12 cell 結論正確，
但漏掉 3 個 sweet spot：**A × 1b N=62 -31% / B × 1c N=26 -36% / C × 1b N=87 -57%**。

# Overall Strategies — 現有策略總覽

這個 repo 嘗試了三類正交的策略，每類處理不同的層級：

1. **Layout 策略**（build-time，一次性，影響整個 file 的物理排列）
2. **Prefetch 策略**（runtime，每次 cold start 跑一次）
3. **Memory-sharing 策略**（architectural，影響多 process 的 RAM 用量）

三類可以**自由組合** — 例如「type-aware layout + layers_5 prefetch + MAP_SHARED」
是目前測過的全局最佳組合。

> **編號規約：**
> - **1a/1b/1c** = Layout（orig / VACUUM / type-aware）
> - **2a–2f** = Prefetch 策略（range / perpage / layers_N / 2d / 2e_K* / 2f SLRU）
> - **3a / 3b** = Access-pattern **ratio variants**：interior:leaf = 7:3 / 5:5（由 2e_K40 / 2e_K92 實現）
> - **4a / 4b** = Memory-sharing（MAP_SHARED / Private buffer pool）

---

## 一、Layout 策略

決定 interior pages 在 file 裡的物理位置。一次性決策，做完之後所有 cold start
都受影響。

### 策略 1a — 原始 layout（do nothing）

不做任何事，SQLite 怎麼分配就怎麼放。Interior pages 散佈於整個 file（**scatter
score ≈ 0.96**，92 個 interior 散在 page 2..26,007 之間）。是所有實驗的基準線。

**狀態：** 永遠存在。
**結論：** 沒有任何 prefetch 也能拿 baseline；上層 5 個 interior page 已經自然在檔頭，所以 `layers_5` 不需要做 layout 改動就能拿 **-54%** 改善。

### 策略 1b — SQLite 內建 VACUUM（已驗證，效果 workload-dependent）

呼叫 `VACUUM;`。理論上應該把 file 緊湊化，實際上 [src/vacuum.c](https://sqlite.org/src/file?name=src/vacuum.c)
的 `sqlite3RunVacuum()` 按照 insertion order 重排，**不看 page type**。

**狀態：** 已驗證（[prefetch_vacuum/](prefetch_vacuum/) Week 11、[layout_rewriter/runs/](layout_rewriter/runs/) 補測 A、[layout_rewriter/runs/matrix_1b_bc_results.csv](layout_rewriter/runs/matrix_1b_bc_results.csv) 補測 B、C）。
**Layout 結果：**
- scatter score 從 **0.96 → 1.13**（變得**更**散）
- 檔案從 107.8 MB 縮到 104.9 MB（reclaim ~3%）

**Latency 結果（同一 `posix_fadvise` harness）：**

| Workload | baseline 變化 | layers_5 改善（orig → vacuum）|
|---|---|---|
| A (Zipfian) | +5%（318→333 µs） | -30% → -30%（無變化）|
| B (Uniform) | +8%（463→503 µs） | -47% → **-50%**（略增）|
| C (high-key) | **-6%（467→437 µs，變快）** | -13% → -7%（略降）|

> 早期 `prefetch_vacuum/` 報告的「layers_5 從 -54% 退化到 -9%」是用 `sudo
> drop_caches` + leaf 自然熱的 A workload 量出來的；換成統一 `posix_fadvise`
> harness 後 A 的退化幅度從「-54%→-9%」收斂到「-30%→-30%」(同樣的「無
> 改善」結論但 baseline 點不同)。

**結論：**
- **不要為了 cold-start 性能 VACUUM**：A、B 上會讓 baseline 變慢 5-8%。
- **特例：高 id 區段查詢（C）反而會變快 6%**，因 VACUUM 把整檔壓緊，
  high-key region 的 seek 距離縮短。
- VACUUM 對 reclaim disk space 仍然有用，且不會破壞 layers_5 在 B 上的
  prefetch 效益。

### 策略 1c — Type-aware layout（layout_rewriter，已完成，效果 workload-dependent）

[layout_rewriter/layout_rewriter.c](layout_rewriter/layout_rewriter.c) — 在
binary 層級重排 file：page 1 留原位，**interior pages 全部搬到 slots 2..93
（連續）**，leaf 接著，overflow/freelist 在最後。同時 patch 所有跨頁指標：
interior 的 child pointer、overflow 的 next-page、freelist 的 next-trunk、page 1
header 的 freelist pointer，以及產 SQL 修正 `sqlite_master.rootpage`。

**狀態：** 已完成 + 端到端驗證（A 在 [layout_rewriter/results/](layout_rewriter/results/)；B、C 在 [layout_rewriter/runs/matrix_1c_bc_results.csv](layout_rewriter/runs/matrix_1c_bc_results.csv)）。
**Layout 結果：**
- scatter score 從 **0.96 → 0.0001**（幾乎完美 clustering）
- `PRAGMA integrity_check;` 通過

**Latency 結果（first-q 改善 vs 同 DB baseline）：**

| Workload | ta baseline 變化 | 最佳 prefetch on ta | 跨 layout 最佳 |
|---|---|---|---|
| A (Zipfian) | +27%（318→404 µs） | **layers_5 -69%（127 µs）** | **ta + layers_5** ✅ |
| B (Uniform) | **-12%（463→408 µs）** | perpage -14%（352 µs） | orig + layers_5（244 µs） |
| C (high-key) | ±0%（467→467 µs） | **perpage -37%（294 µs）** | **ta + perpage** ✅ |

**結論：**
- **不是 universal best**：A 上 -69%（全局最強），C 上配 perpage 達 -37%，
  但 **B 上 ta + layers_5 反而變慢 +8%**（leaves 被推到高 offset、第一個
  cold leaf fault 距離拉長，prefetch coverage 不夠時暴露 penalty）。
- **配方依 workload 而定**：Zipfian 點讀 → ta + layers_5；File-tail 讀
  → ta + perpage；Uniform 全段讀 → 不要 ta。
- `range` 在任何 layout 都不該選 —— `MADV_WILLNEED` 對單一大 range 的
  readahead 是 bounded（~32/92 pages）。

---

## 二、Prefetch 策略

決定 cold start 後、第一筆 query 跑之前，要主動把哪些 page 載進 OS page cache。

### Structure-based（不看存取歷史，純粹看 page 結構）

#### 策略 2a — Range（structure-based，已完成）

把連續的 interior pages 合併成 range，每個 range 呼叫一次 `madvise(MADV_WILLNEED)`。
[prefetch_vacuum/src/prefetch.c](prefetch_vacuum/src/prefetch.c) 的 `range` mode。

**狀態：** 已完成。
**結果：**
- 原始 layout：92 個 interior → 87 syscalls，改善 **-27%**
- type-aware layout：92 個 interior → **1 syscall**（連續），但 kernel
  readahead 是 bounded，1 個 `MADV_WILLNEED` 只實際載入 32/92 pages → 改善僅 **-4%**

**結論：** 即使 layout 完美，`MADV_WILLNEED` 是 advisory，**不保證載入量**。
range 在任何 layout 下都不是好選擇。

#### 策略 2b — Perpage（structure-based，已完成）

對每個 interior page 個別呼叫一次 `madvise(MADV_WILLNEED)`。
[prefetch_vacuum/src/prefetch.c](prefetch_vacuum/src/prefetch.c) 的 `perpage` mode。

**狀態：** 已完成。
**結果：**
- 原始 layout：92 syscalls，改善 **-34%**
- type-aware layout：92 syscalls，改善 **-33%**

**結論：** 比 range 確定載入更多 page（每次 madvise 指定一頁，kernel 確實會
load 那一頁），但 92 個 syscall 開銷 2.9 ms，吃掉一部分效益。

#### 策略 2c — Layers N（structure-based，已完成 + 找到甜蜜點）

只 prefetch 前 N 個 interior page（按 file offset 排序，等同於 B+tree 上層）。
[prefetch_vacuum/src/prefetch_layers.c](prefetch_vacuum/src/prefetch_layers.c)。

**狀態：** 已完成，N=1/5/10/20/46/92 全跑過。
**結果（Workload A，原始 layout）：U 型曲線**

| N | syscalls | 改善 |
|---:|---:|---:|
| 1 | 1 | -48% |
| **5** | **5** | **-54%** ← 甜蜜點 |
| 10 | 10 | -39% |
| 92 | 92 | -31% |

**結論：** N=5 是 syscall overhead 與 coverage 的最佳折衷**僅在 Workload A
上**。配合 type-aware layout 可達 -69%。

**Workload-specific 結果**（A/B/C × {1a orig, 1b vacuum, 1c type-aware, churned}，
數字全部從 dense N=0..92 全 sweep 切片，內部一致）：
- **A on 1a**: N=5/10 plateau **-41~42%**（dense 找到 cost-effective sweet spot）；
  U 型曲線存在但寬而平、不是 sharp minimum
- **A on 1b vacuum**: N=5 起就 plateau **-21%**；**dense 找到 1b 真正最佳 N=62 -31%**
  （不在原 sparse 6 個 N 採樣裡）
- **A on 1c**: layers_N 升級為 **N=5..92 全 plateau 在 -73~75%**（U 型曲線消失；
  TA 把 interior 全集中到檔頭，任何 N≥5 都 cover）
- **B on 1a/1b**: N=5~92 全 plateau 在 **-51~53%**（沒有 U 型曲線；leaf-fault 主導）
- **B on 1c**: 比 1a/1b 弱一半，**N=5 -11%、N=46 -27%（sparse 6-pt 內最佳）；
  dense 找到 1c 真正最佳 N=26 -36%**（仍比 1a/1b 的 -52% 差）；
  跟第七維「1c × B baseline 變慢」、第十一維「1c × 2f SLRU 蓋掉 B penalty」同源
- **C 乾淨 DB on 1a/1b**: N≤46 plateau **~-10%**，**N=92 跳到 -45~53%**（hot interior
  在 file 中段，按 offset 排 top-N 完全選錯 page）；**dense 找到 1b 真正最佳 N=87 -57%**
- **C on 1c**: **N=5 就拿到 -46%**，N=46 略退 -40%，N=92 達到 -50%（最佳）；
  TA 解掉 C「必須載全 92 個」的 cost-effective 問題（N=5 拿到 92% 的好處）
- **C churned DB**: N≤46 plateau **~-11~15%**，**N=92 跳到 -58%**（churn 不改變這個
  結論，反而把 N=92 的相對優勢拉大）
- **A churned DB** (第十八維, B2 補測): N=5 已到 plateau **-92.3%**、N=10 最佳 **-92.9%**、
  N=92 **-92.7%**；跟乾淨 DB 上 A 的 N=5 plateau 同形 — **churn 不改變 Zipfian 熱點分佈**
- **B churned DB** (第十八維, B2 補測): N=5 -50.3%、**N=20 最佳 -51.3%**、N=92 -50.3%；
  跟 C × churn 的 -58% 同級 — **兩個 cold-leaf workload 的 churn N-sweep
  plateau 都卡在 -50% 左右**（leaf miss 是上限）
- **Dense N=0..92 全 sweep** (rigor 補測, ~5,580 個 benchmark)：本 bullet 區
  的所有數字都從這個 dense run 切出 N ∈ {1, 5, 10, 20, 46, 92} 6 個點重算
  （早期 sparse 跑跟 dense 用了同個 harness 但相隔三週，絕對 µs 略飄移；切片
  讓所有 cell 用同個 machine state）。**3 個 cell 漏掉真正最佳 N（不在 sparse
  6 個採樣裡）：A×1b N=62 -31% / B×1c N=26 -36% / C×1b N=87 -57%**——這 3 個
  sweet spot 跟 sparse best 差距 ≤12pp，原 sparse 結論沒被推翻、只是次優
- **Z (Zipfian low-key, keys [1,1000])**: 跟 A 結果同形，差異 ≤ 5pp（1a 最佳
  N=20 −31%、1b 最佳 N=5 −31%、1c 任何 N≥5 都 −69~72%，N=92 最佳 −72%）；
  **N=1 universally worse** than baseline by ~+22% on 1a/1b（純 madvise syscall
  overhead、無 coverage 受益），跟 A 的 N=1 退化同源 →「熱點落在 file 哪段」
  不是 prefetch 效益的主要變因，**hotspot location 不影響結論**

**因此 layers_N 的最佳 N 跟 layout 強耦合**，不是 universal best。詳見
[overall_results.md 第八維](overall_results.md#第八維--2c-layers_n-sweep--workload-b--c原始-layout)
（乾淨 DB B/C）+ [第九維](overall_results.md#第九維--layout-1b-vacuum-補測n-sweep--2f-slru--abc)
（vacuum DB）+ [第十維](overall_results.md#第十維--n-sweep--workload-c--churned-db補齊-prefetch_churn-缺口)
（churned DB）+ [第十二維](overall_results.md#第十二維--n-sweep--layout-1c-type-aware--abc)
（type-aware DB，完成跨三 layout 矩陣）+
[第十三維](overall_results.md#第十三維--n-sweep--workload-z-zipfian-low-key-hotspot--1a1b1c)
（Zipfian low-key 變體，confirms hotspot location 不變結論）+
[第十八維](overall_results.md#第十八維--churn-擴充abc--churn--2c-layers_n--2d--2e_kab--churn--statictk0-hotpages)
（A/B × churn × layers_N，補齊 churn × workload 矩陣）。

**Dense N=0..92 全 sweep（rigor 補測）**：clean + churn × A/B/C × 3 layouts × 3 reps，
共 ~5,580 額外 benchmark；證實 sparse 6-pt 在 9/12 cells 結論正確；但 **A×1b 漏
N=62 (-31%)、B×1c 漏 N=26 (-36%)、C×1b 漏 N=87 (-57%) 三個 sweet spot**。資料:
[layout_rewriter/runs/nsweep_full/](layout_rewriter/runs/nsweep_full/) +
[prefetch_churn/runs_nsweep_full_{a,b,c}/](prefetch_churn/)；
圖: [Figure 11](figures/out/11_nsweep_full.png) / [Figure 12](figures/out/12_nsweep_full_churn.png)。

### Access-pattern-based（看存取歷史，已完成）

#### 策略 2d — Access pattern，只 interior（已完成）

跑一次 workload 後用 `mincore()` dump residency snapshot，只 prefetch 那些
**實際被走過**的 interior page（按 file offset 排序，cap_interior=0 = 全載
resident 集合）。實作 [prefetch_access/src/prefetch_access.c](prefetch_access/src/prefetch_access.c)，
~110 行 C，同 mmap + madvise 機制。

**狀態：** 已完成，3 workloads × 3 layouts × {base, 2d} × 3 reps = 54 cells。
**結果：**

| Workload × Layout | baseline | 2d | 改善 | syscalls |
|---|---:|---:|---:|---:|
| **C × 1a (orig)** | 468 | **245 µs** | **-47.6%** | **4** ← 追平 layers_92 (-46% / 92 syscalls)，23× syscall 減少 |
| **C × 1b (vacuum)** | 446 | **243 µs** | **-45.5%** | **4** |
| C × 1c (ta) | 454 | 424 µs | -6.7% | 32 ← TA × C 上 readahead pollution 干擾 |
| A × 1a (orig) | 300 | 222 µs | -25.9% | 18 |
| A × 1c (ta) | 416 | **139 µs** | **-66.7%** | 31 |
| B × 1a (orig) | 464 | 245 µs | **-47.3%** | 16 |

**結論：**
- **2d 直接解掉「layers_N 在 C 上失效」的鎖**：C × 1a 只用 4 syscall 達到 -48%，
  追平 layers_92。
- **prefetch 開銷可忽略**（4 syscall < 5 µs），對 avg_us 影響 ≤ 0.02 µs。
- **TA layout × C 上 2d 失效**：mincore 觀察到的 resident interior 集合被
  readahead pollution 污染（32 個 page，大部分沒走過）— 解法用第十五維的 2e
  排序。
- **RAM-pressure 不會打掉 2d 的優勢**（756-cell 矩陣，第十六維）：在
  cgroup MemoryMax=20M 下 C × 1a 仍 -63%、C × 1b 仍 -44%、A × ta 仍 -68%。
  唯一例外仍是 B × ta 的 -1~-4%（RAM pressure 與否都失效，TA pollution 鎖死）。
- **2d × A × delete-heavy churn 完全不 decay**（第十八維, B1 補測）：static
  t=0 hotpages 跨 10 churn checkpoint × 50k ops，2d_static avg -91.8%，
  略勝 layers_92 (-91.4%) — hypothesis「delete from id=1 會擾動 Zipfian 熱
  keys」**被推翻**。連同先前的 C × insert-churn -50% 結果，**2d × static hot
  在兩種正交 churn 下都穩定**。
- **2d × B × churn 跟 file-offset 打平、同樣不 decay**（第十八維, B3 補測）：
  2d_static avg -45.7% ≈ layers_5 (-45.9%)。B（uniform）沒有自然熱葉，2d 只
  能救 interior path，跟盲載前 N 個 page 沒差別；drift 無單調惡化。**access-
  pattern 在 B 上不帶額外效益，但也不會壞掉。**
- 詳見 [overall_results.md 第十四維](overall_results.md#第十四維--2d-access-pattern-prefetch-interior-only--abc--3-layouts)
  + [第十六維](overall_results.md#第十六維--ram-pressure-完整矩陣cgroup-memorymax20-mb-abc--1a1b1c--base-2d-2e_k1050100500-2f_slru)
  + [第十八維](overall_results.md#第十八維--churn-擴充abc--churn--2c-layers_n--2d--2e_kab--churn--statictk0-hotpages)。

#### 策略 2e — Access pattern，interior + top-K leaves（已完成）

2d 集合再加 top-K hot leaf：用 `sqlite_dbpage` + varint decoder 把每個 leaf 的
first_rowid 抽出來、建立 key → leaf 對應表；對 workload 的每個 read key 算
所屬 leaf、累加查詢次數；取前 K。實作 [prefetch_access/runs/gen_hotleaves.py](prefetch_access/runs/gen_hotleaves.py)。

**狀態：** 已完成，3 workloads × 3 layouts × K∈{10,50,100,500} × 6 reps = 216 cells。

**結果（first-q 改善 %）：**

| Workload × Layout | 2d | K10 | K50 | K100 | K500 | 最佳 |
|---|---:|---:|---:|---:|---:|---|
| **C × 1a** | -47.6% | **-83.9%** | -83.4% | -81.7% | -83.3% | **K=10** |
| **C × 1b** | -45.5% | **-82.7%** | -82.2% | -82.1% | -81.8% | **K=10** |
| **C × 1c** | -6.7% | **-82.4%** | -81.8% | -82.2% | -82.7% | **K=10**（救回 2d）|
| A × 1a | -25.9% | -25.7% | -22.2% | -29.4% | **-73.0%** | K=500 |
| A × 1b | -28.4% | -27.4% | -27.2% | -22.7% | **-76.6%** | K=500 |
| A × 1c | **-66.7%** | -40.7% | -39.9% | -18.8% | -52.6% | **2d**（K 都退化）|
| B × 1a | -47.3% | **-47.2%** | -46.6% | -46.8% | -24.5% | K=10 ≈ 2d |
| B × 1b | -51.2% | **-51.4%** | -51.2% | -50.0% | -37.2% | K=10 ≈ 2d |
| B × 1c | -0.6% | -36.9% | **-38.2%** | -19.2% | -25.4% | K=50（救回 2d）|

**結論：**
- **C 上 2e_K10 是全局最佳「不需要 warmup pass」策略**：14~42 syscall → -82~84%，
  接近 2f SLRU 的 -94% 但 syscall 數量降 ~100×。
- **A 1a/1b 上 2e_K500 比 2d 翻倍效益**（-73~77% vs -26~28%）。
- **A × ta 上 2d 完勝**：K≥10 全部退化 — TA × A 已經把 interior 集中、加 leaves
  反而拖慢 syscall。
- **B 上 K=10 ≈ 2d，K=500 退化**：uniform workload 沒有 leaf-level hot set，
  prefetch leaves 無益。
- **2e 把 2f 的「-94%」效益拆解**：證明 leaf preload 是 2f 主要貢獻；用 top-K
  hot leaf 就能複製 80~95% 的效益。
- **2e_K10 在 RAM-pressure 下完全保留優勢**（756-cell 矩陣，第十六維）：
  cgroup MemoryMax=20M 下 C × {1a, 1b, 1c} 全部 -82~88%（ratio 1.04-1.06x），
  跟 unlimited RAM 幾乎沒差。**K=500 在 vacuum/B 上偶有 noise（ratio 0.93-1.10x）
  但仍維持 -32~-77% 主要效益**。RAM 壓力不是 2e 的瓶頸。
- **2e_K10 / 2e_K50 × A × delete-heavy churn 完全不 decay**（第十八維, B1 補測）：
  2e_K10_static avg **-92.4%**（最佳）/ 2e_K50_static -91.5%，全部贏過
  layers_92 (-91.4%)。**static t=0 hotpages 在 A × delete + C × insert 兩個正交
  churn 設置下都 production-stable**。
- **2e × B × churn：多載 leaves 沒幫助、但也不 decay**（第十八維, B3 補測）：
  2e_K10_static -48.8% / 2e_K50_static -47.7% ≈ layers_92 (-49.2%)；從 2d
  (-45.7%) 加到 K=50 只在 noise 範圍內擺動。**uniform reads 沒有 hot leaf，
  top-K leaves 等同隨機選頁**，B 的 ~-49% 天花板由 cold-leaf fault 鎖死，不
  由 K 決定。三 workload（A/B/C）× access-pattern × churn 全部驗證不 decay。
- 詳見 [overall_results.md 第十五維](overall_results.md#第十五維--2e-access-pattern-prefetch-interior--top-k-leaves--abc--3-layouts--kk10k50k100k500)
  + [第十六維](overall_results.md#第十六維--ram-pressure-完整矩陣cgroup-memorymax20-mb-abc--1a1b1c--base-2d-2e_k1050100500-2f_slru)
  + [第十八維](overall_results.md#第十八維--churn-擴充abc--churn--2c-layers_n--2d--2e_kab--churn--statictk0-hotpages)。

### SLRU-approximated（已完成）

#### 策略 2f — SLRU prefetch（mincore-dumped resident set，已完成）

跑完一次 workload 後**不要 evict**，直接用 `mincore()` dump 當下 OS page cache
裡的所有 resident page，存成 `hotpages.csv`。下次 cold start 時對每個
`is_resident=1` 的 page 一一呼叫 `madvise(MADV_WILLNEED)`。
[prefetch_slru/src/prefetch_slru.c](prefetch_slru/src/prefetch_slru.c)。

**和 2d/2e 的差別：** 2d/2e 要攔截 SQLite 的 page read 才能算 access count；
2f 只看 workload 結束後的 residency snapshot，**完全不用碰 SQLite 內部**，
但精度較低 —— 只知道一個 page **有沒有**被用過，不知道**被用幾次**。
實作成本：~70 行 C。

**狀態：** 已完成，在 Workload A (Zipfian)、B (Uniform)、C (high-key uniform)
三個 workload × **三個 layout (1a orig / 1b vacuum / 1c type-aware)** 上跑過。
**結果：**
- **First-query latency 在三個 workload × 三個 layout 上一致大勝 -94~95%**：
  - Layout 1a (orig): A 251 → 14 µs、B 255 → 15 µs、C 250 → 16 µs
  - Layout 1b (vacuum): A 219 → 15 µs、B 230 → 14 µs、C 212 → 14 µs
  - Layout 1c (type-aware): A 321 → 15 µs、B 304 → 16 µs、C 249 → 13 µs
  - **2f SLRU 是 layout-agnostic**：layout 變動對 first-q 影響 < 3 µs（小於單筆 noise）
- **Prefetch 開銷由 hot set 大小決定**：A/B 4,000+ syscalls 花 ~7.5 ms；
  **C 只 420 syscalls 花 1.9 ms（4× 便宜）**，端到端 cold start C 只「慢
  7.6×」（A/B 慢 30×）
- **全 workload 跑完的省下幅度跟 baseline 的 avg-q 走**：A 省 39%（411 → 249 ms）、
  B 省 38%（413 → 255 ms）、**C 只省 7%**（262 → 245 ms）—— 因 C 的 baseline
  avg-q 已經是 2.62 µs（leaves 高度共享同個 disk region，沒多少 cold fault 可解）
- **A 和 B 結果幾乎一樣**，推翻原本「SLRU 在 skewed 上會輸給 access-count」的
  預測 —— 因為 hot set (~16 MB) 全塞得進 RAM，沒有「該丟誰」的競爭，frequency
  資訊用不上
- **2f 的「working-set preload」價值跟 hot set 的 leaf spread 成正比** —— 越
  分散（A/B），preload 收益越大；越集中（C），收益越小

**結論：** 2f 不是「降低 cold-start」的策略，是「working-set preload」的策略。
適用情境跟 2c Layers N 完全不同 —— 詳見
[prefetch_slru/PREFETCH_SLRU.md](prefetch_slru/PREFETCH_SLRU.md) 的 trade-off
矩陣。

**RAM-pressure 結果（756-cell 矩陣，第十六維）：**
- **First-q 完全免疫**：18 個 (WL, layout, mem) cells 全部 15-19 µs（-95~98%），
  跟 RAM 壓力與 layout 都無關。
- **新發現：1b vacuum 是唯一「avg/majflt 也 RAM-pressure-immune」的 layout** ——
  cgroup 20M 下 A/B/C × vacuum × 2f_SLRU 全部 majflt = 0、avg = 1.50/1.56
  （跟 unlimited RAM 一樣）。1a orig / 1c ta 下 majflt 從 0 跳到 172-181、
  avg 從 1.50 退到 1.79-1.87（**接近 base level，2f preload 被 evict**）。
- **意義：「2f SLRU + 1b vacuum」是 RAM 緊環境的全保留組合**——既拿到 -95% first-q，
  也拿到 working-set preload 的 avg 改善。其他 layout 下 2f 在 20M 仍贏 first-q
  但失去 avg 優勢。

### Access-pattern ratio variants（3a / 3b）

3a / 3b 是 2e 的 ratio 變體：固定 **interior:leaf** 比例分別為 7:3 與 5:5，
由 `2e_K=40` / `2e_K=92` 實現。它們不是新策略，是為了驗證「ratio 是不是
first-q 的主要 axis」（結論：K 才是，ratio 只是 K 的副產品）。

#### 策略 3a — Access pattern, interior + leaf @ 7:3 ratio (= 2e_K40, 已完成)

原始 spec 把「interior 集合再加 leaf」拆成兩個 ratio：3a = 70% interior + 30%
leaf。在 92 個 interior 的 DB 上，這對應到 leaf 數 ≈ 92 × 30/70 ≈ **40**，
所以 3a 由 **2e_K=40** 實現。

**狀態：** 已完成，A/B/C × 3 layouts × 6 reps = 54 cells。
資料 [matrix_2e_ratio_results.csv](prefetch_access/runs/matrix_2e_ratio_results.csv)，
視覺化 [figures/out/10_ratio_sweep.png](figures/out/10_ratio_sweep.png)。

**實作細節：** 2e 只 prefetch **resident** interior（warmup 真的觸碰過的，
4 - 32 個），不是全部 92 個。所以實際 ratio 偏離 spec：

| Workload × Layout | 實際 (interior:K=40) | 距離 spec 7:3 |
|---|---|---|
| A × 1c (ta) | 31:40 ≈ 44:56 | ✓ 最接近 |
| C × 1c (ta) | 32:40 ≈ 44:56 | ✓ 最接近 |
| A × 1a (orig) | 18:40 ≈ 31:69 | 偏 leaf |
| C × 1a (orig) | 4:40 ≈ 9:91  | 嚴重偏 leaf |

**Latency 結果（first-query µs, median of 6 reps）：**

| WL | 1a | 1b | 1c |
|---|---:|---:|---:|
| A | 233 | 251 | 250 |
| B | 251 | 253 | 254 |
| C | **78** | 82 | 81 |

C 上已經 saturate（任意 K≥10 都 ≈ 80 µs）；A/B 介於 2d 與 K=500 之間。

#### 策略 3b — Access pattern, interior + leaf @ 5:5 ratio (= 2e_K92, 已完成)

3b = 50% interior + 50% leaf。92 interior × 50/50 = **92** leaves，由
**2e_K=92** 實現。同樣資料 [matrix_2e_ratio_results.csv](prefetch_access/runs/matrix_2e_ratio_results.csv)。

| Workload × Layout | 實際 (interior:K=92) | 距離 spec 5:5 |
|---|---|---|
| A × 1c (ta) | 31:92 ≈ 25:75 | 最接近（偏 leaf）|
| C × 1c (ta) | 32:92 ≈ 26:74 | 最接近 |
| A × 1a (orig) | 18:92 ≈ 16:84 | 偏 leaf |
| C × 1a (orig) | 4:92 ≈ 4:96 | 嚴重偏 leaf |

**Latency 結果：**

| WL | 1a | 1b | 1c |
|---|---:|---:|---:|
| A | 212 | 214 | **410 ⚠️** |
| B | 243 | 251 | 345 |
| C | 80 | 79 | 82 |

**反直覺發現：A × 1c (ta) × K=92 = 410 µs，比 K=40 (250) 跟 K=500 (119) 都差。**
ta layout 把 interior 集中後，加 92 個熱 leaves 反而引發 readahead pollution——
直到 K=500 把整個熱集都載入才回穩。這個非單調 K=92/100 hump 是 ta layout
特有的現象，1a/1b 上沒有。

**結論（3a vs 3b）：**
- **C workload**：任一 ratio 都 saturate，2e_K10 已經夠用（-83%）。3a/3b 沒有
  額外好處，但也沒退化。
- **A workload**：3a (K=40) 比 3b (K=92) 穩定；3b 在 ta layout 上反而退化。
- **B workload**：兩個 ratio 都改善 ~50%，差別不大；uniform read 沒有 leaf-level
  hot set，ratio 怎麼分都差不多。
- **與原 spec 對齊度**：實際 ratio 受「resident interior 數」拖累，只有 ta layout
  接近 spec（44:56），其他 layout 嚴重偏 leaf。要嚴格對齊原 ratio，需改 2e
  讓它強制 prefetch 全部 92 interior（不只 resident 的）— 屬未來工作。

---

## 三、Memory-sharing 策略（4a / 4b）

決定多 process 場景下 page cache 的共享方式。在手機（背景 service + 主 App）
或 server（worker process pool）這類部署最關鍵。

### 策略 4a — MAP_SHARED mmap（已驗證）

所有 process 用 `mmap(MAP_SHARED)` 開同一個 DB file。整個 fleet 共享 OS page
cache 的同一份 physical copy。**SQLite 開啟 `PRAGMA mmap_size = <size>` 就走
這條路徑**。
[multiprocess/src/multiprocess_residency.c](multiprocess/src/multiprocess_residency.c)。

**狀態：** 已驗證（[multiprocess/](multiprocess/)）。
**結果：**
- 3 個 child process 各讀 1/3 的 DB，parent 完全沒讀任何東西
- 最後 `mincore()` 看到 **25,613 / 25,613 pages 全部 resident**，跨 process 共享確實成立
- 任何一個 process 呼叫 `madvise(MADV_WILLNEED)` prefetch，其他 process 立即受惠

**結論：** **prefetch 的成本固定 O(1)，效益隨 process 數量 O(N) 放大**。是
mobile / embedded 場景下 prefetch 設計的天然 multiplier。

### 策略 4b — Private buffer pool per process（已驗證對照）

`PRAGMA mmap_size=0` + `PRAGMA cache_size=N`，每個 process 持有獨立 buffer pool。
[multiprocess/src/multiprocess_buffer_pool.c](multiprocess/src/multiprocess_buffer_pool.c)。

**狀態：** 已驗證對照組。
**結果：**

| Process 數量 | MAP_SHARED 總 RAM | Private buffer pool 總 RAM |
|---:|---:|---:|
| 3 | ~100 MB | ~30 MB |
| 10 | ~100 MB | ~100 MB |
| 100 | ~100 MB | **~1 GB** |

**結論：** Process 數量少時 private buffer pool 反而省 RAM（因為只 cache 用到
的 working set）；但 process 數量 → ∞ 時 MAP_SHARED 是唯一可行解。**這也是
為什麼 Android / mobile 場景一定要走 mmap 路徑**。

---

## 組合策略 — 目前測過的最佳堆疊

```
Layout:           type-aware (layout_rewriter)    ← scatter 0.00     [1c]
Prefetch:         layers_5                         ← 5 syscalls, 94 µs [2c]
Memory sharing:   MAP_SHARED                       ← 多 process 自動受惠 [4a]
```

在 Workload A 上：first query 從 baseline **404 µs → 127 µs（-69%）**，且
prefetch 的 5 個 syscall 可由任一 process 出資、整個 fleet 共享成果。

---

## 策略狀態總覽

| 類別 | 策略 | 狀態 |
|---|---|---|
| Layout | 1a 原始 | ✅ baseline |
| Layout | 1b SQLite VACUUM | ✅ 完整覆蓋（A/B/C × {baseline, range, perpage, layers_N sweep, 2f SLRU}）—— N=5 仍是 cost-effective 預設、A vac 甜蜜點移到 N=20、2f vacuum 開銷比 orig 省 7-16% |
| Layout | 1c type-aware layout_rewriter | ✅ 已完成（A 最強 -69%、C + perpage -37%；B 反效果）|
| Prefetch | 2a Range（structure） | ✅ 已完成 |
| Prefetch | 2b Perpage（structure） | ✅ 已完成 |
| Prefetch | 2c Layers N（structure） | ✅ 完整覆蓋 A/B/C × {1a orig, 1b vacuum, **1c type-aware**, churned} + Workload Z (Zipfian low-key) + **A/B × churn N-sweep (B2 第十八維)** + **dense N=0..92 全 sweep (第十九維)**（最佳 N 跟 layout 強耦合：1a/1b A 最佳 N=5/20、1c A 任何 N≥5 都 plateau 在 -71%；1c 上 C 變成 N=46 -32% 最佳、不再需要 N=92；但 1c × B 上 layers_N 失效，要回到 1a/1b 或改用 2f SLRU；Z 跟 A 結果同形、hotspot location 不變結論；A × churn N=5 -90.7% / B × churn N=92 -49.2%，churn 不改 plateau 形狀；dense 補測 ~5,580 個 benchmark 發現 sparse 6-pt 漏掉 3 個 sweet spot — **A×1b N=62 -31% / B×1c N=26 -36% / C×1b N=87 -57%**）|
| Prefetch | 2d Access pattern，interior only | ✅ 已完成 A/B/C × 3 layouts × 6 reps + **RAM-pressure 全矩陣** + **A × delete-churn / B × churn × 10 checkpoint (B1/B3 第十八維)**（**C × 1a 4 syscalls -47.6% 追平 layers_92；B 全 layout -47~51% / 14-31 syscalls；A 中性偏負**；RAM 20M 下優勢全保留；A × delete-churn 上 2d_static -91.8%、B × churn 上 -45.7%（≈layers_5），static t=0 hot 在 A/B/C 都不 decay）|
| Prefetch | 2e Access pattern，interior + leaf | ✅ 已完成 A/B/C × 3 layouts × K∈{10,50,100,500} × 6 reps + **RAM-pressure 全矩陣** + **A × delete-churn / B × churn × 10 checkpoint (B1/B3 第十八維)**（**C × 任一 layout K=10 -82~84% / 14-42 syscalls；A K=500 -73~77%；B 跟 2d 差不多 -49~58%**；先前 cap_leaf bug 已修復重跑；RAM 20M 下 C 全保留 -82~88%、K=500 偶有 noise；A × delete-churn 上 2e_K10_static -92.4% 為最佳 arm；B × churn 上 2e_K10 -48.8% ≈ layers_92，多載 leaf 無增益但不 decay）|
| Prefetch | 2f SLRU（mincore-dumped resident set）| ✅ 已完成 A/B/C × layout 1a/1b/1c + **RAM-pressure 全矩陣**（layout-agnostic：first-q 三 layout × 兩 mem 一致 15–19 µs；**1b vacuum 是唯一 avg/majflt 都 RAM-pressure-immune 的 layout**，1a/1c 下 RAM 緊時 2f preload 被 evict）|
| Prefetch | 3a Access pattern interior+leaf 7:3 ratio (= 2e_K40) | ✅ 已完成 A/B/C × 3 layouts × 6 reps（[matrix_2e_ratio_results.csv](prefetch_access/runs/matrix_2e_ratio_results.csv)；fig 10）— 實際 ratio 隨 (workload, layout) 變動於 9:91 ~ 44:56 之間（2e 只 prefetch resident interior） |
| Prefetch | 3b Access pattern interior+leaf 5:5 ratio (= 2e_K92) | ✅ 已完成 A/B/C × 3 layouts × 6 reps；A × 1c 出現非單調 K=92 hump（410 µs，比 K=40 還差）；A × 1a/1b plateau ~213 µs；C 全 layout 已 saturate 至 ~80 µs |
| Memory sharing | 4a MAP_SHARED | ✅ 已驗證 |
| Memory sharing | 4b Private buffer pool | ✅ 已驗證對照 |

# Prefetch SLRU — 策略 2f：mincore-approximated 工作集 prefetch

`prefetch_slru` 用 SLRU 的「protected segment」概念近似 hot set：跑完一次
workload 後，**直接用 `mincore()` 把當下還在 OS page cache 裡的 page list
存下來**（叫做 `hotpages.csv`），下次 cold start 時對這些 page 一一呼叫
`madvise(MADV_WILLNEED)`。

對照 [overall_strategies.md](../overall_strategies.md) 的編號，這是 **2c
Layers N**、**2d/2e Access-pattern-based** 之外的新軸線，編號 **2f**，補進
prefetch 策略的最末項。

## 與其他策略的差別

| 策略 | 資料來源 | 精度 |
|---|---|---|
| 2c Layers N | classify_pages（只看 page 類型 + offset）| 假設「offset 小 = 上層 = 熱」|
| 2d Access pattern, interior only（**已完成**，見 [prefetch_access/](../prefetch_access/)）| 攔截每次 page read，存 access count | 區分 1 次 vs 100 次 |
| 2e Access pattern, interior+leaf（**已完成**，見 [prefetch_access/](../prefetch_access/)）| 同上但含 leaf | 同上 |
| **2f SLRU**（本檔）| 跑完 workload 後 `mincore()` dump residency | **只知道 hot/cold，不知道 hot degree** |

策略 2f 的優勢：**完全不用攔截 SQLite 的內部呼叫**——residency_checker 已經
有現成的 mincore 邏輯。實作就是一個 ~70 行 C 程式。

## Build

```bash
gcc -O2 -Wall -o src/prefetch_slru src/prefetch_slru.c
```

## 使用

```
prefetch_slru <database.db> <residency.csv> <page_size>
```

`residency.csv` 是 [residency_checker](../residency_checker/) 的標準輸出
（`page_number,is_resident`）。工具會跳過 header，對每個 `is_resident=1` 的
page 算 file offset 並呼叫 `madvise(MADV_WILLNEED)`。

完整流程（以 Workload A = Zipfian 為例）：

```bash
# 1. WARMUP — evict + 跑 workload + dump residency
./runs/warmup.sh ./runs/workload_a_zipfian.txt ./runs/hotpages_a.csv

# 2. MEASUREMENT — 用 hotpages_a.csv 餵 prefetch_slru
benchmark_harness \
  --db test.db --workload workload_a_zipfian.txt \
  --cold-advice dontneed \
  --drop-caches-script ./runs/evict_helper.sh \
  --post-cold-script ./runs/prefetch_slru_a.sh
```

## 實測結果

Reference DB：600,000 rows, 26,331 × 4 KB pages (其中 92 interior)。
冷啟動方式：`posix_fadvise(POSIX_FADV_DONTNEED)`（無 sudo）。
3 reps median。

> Workload 命名沿用 [overall_workloads.md](../overall_workloads.md)：
> - **Workload A** = Zipfian point-read (`workloadc.txt`)
> - **Workload B** = Uniform random point-read (`workload_uniform.txt`)
> - **Workload C** = High-key uniform read (`page_churn_benchmark_high.txt`)

### Hot set 大小（warmup 後的 resident page 分佈）

| Workload | 總 resident pages | leaf_table | leaf_index | interior_table | interior_index |
|---|---:|---:|---:|---:|---:|
| **A (Zipfian)** | 4,048 | 3,328 | 702 | 10 | 8 |
| **B (Uniform)** | 4,122 | 3,331 | 775 | 10 | 6 |
| **C (high-key)** | **420** | 357 | 59 | 2 | 2 |

**觀察 1：A 和 B 的 resident set 幾乎一樣（4,048 vs 4,122）**，但組成邏輯不
同 — A 是「23k unique key、最熱的被打 7,752 次」、B 是「63k unique key、
每個只被打 1-2 次」。共同點：**兩者都打 DB 前 1/6 的 id 區段**，所以 touch
到的 leaf 頁面大致相同。

**觀察 2：A/B 上 92 interior pages 只有 16 個 resident**。因為 workload 只查
id ∈ [1, 99999]（DB 前 1/6），剩下 5/6 區段的 interior 從沒被 traverse 到。

**觀察 3：C 的 hot set 比 A/B 小 10×（420 vs 4,000+）**。C 查 id ∈ [590k, 610k]
（高度集中的 20k 區段、且半數落在 600k 後的不存在 id），leaf 高度共享 →
**hot set 只有 1.6 MB（A/B 各 ~16 MB）**。這直接決定了 2f 在 C 上的 prefetch
overhead 縮水到 1/4。

### Latency 矩陣（first query / 平均 / 全 workload 總時間 / prefetch 開銷）

| Workload | Strategy | first-q (µs) | avg-q (µs) | total (ms) | prefetch (µs) | madvise syscalls |
|---|---|---:|---:|---:|---:|---:|
| A (Zipfian) | 1a baseline | 251 | 4.11 | 411 | 0 | 0 |
| A (Zipfian) | 2c Layers N=5 | 133 | 4.13 | 412 | 15 | 5 |
| A (Zipfian) | **2f SLRU** | **14** | **2.50** | **249** | 7,255 | 4,048 |
| B (Uniform) | 1a baseline | 255 | 4.13 | 413 | 0 | 0 |
| B (Uniform) | 2c Layers N=5 | 137 | 4.11 | 411 | 15 | 5 |
| B (Uniform) | **2f SLRU** | **15** | **2.55** | **255** | 7,478 | 4,122 |
| C (high-key) | 1a baseline | 250 | 2.62 | 262 | 0 | 0 |
| C (high-key) | 2c Layers N=5 | 185 | 2.66 | 266 | 13 | 5 |
| C (high-key) | **2f SLRU** | **16** | **2.45** | **245** | **1,881** | **420** |

### 與 baseline 比的相對改善

| Workload | Strategy | first-q 改善 | 全 workload 總時間改善 | 端到端 cold start (prefetch+first) |
|---|---|---:|---:|---:|
| A (Zipfian) | 2c Layers N=5 | -47% | ≈ 0% | 148 µs（vs 251 baseline，**-41%**）|
| A (Zipfian) | **2f SLRU** | **-94%** | **-39%** | 7,269 µs（比 baseline 慢 29×）|
| B (Uniform) | 2c Layers N=5 | -46% | ≈ 0% | 152 µs（vs 255 baseline，**-40%**）|
| B (Uniform) | **2f SLRU** | **-94%** | **-38%** | 7,493 µs（比 baseline 慢 30×）|
| C (high-key) | 2c Layers N=5 | -26% | ≈ 0% | 198 µs（vs 250 baseline，**-21%**）|
| C (high-key) | **2f SLRU** | **-94%** | **-7%** | 1,897 µs（比 baseline 慢 7.6×）|

## 六個發現

### 1. 策略 2f 第一筆 query 把 2c 打到地上（-94% on all workloads）

`madvise(MADV_WILLNEED)` 對單一 leaf page 是 kernel 確實會 load 的。SLRU 把
所有 touched leaf 全 prefetch 進來，第一筆 query 不管打哪個 id 都打到熱 leaf。
2c 只 prefetch interior，leaf 還是 cold-fault → A/B 落在 130–137 µs，**C 更
落在 185 µs（layers_5 在 C 上的 -26% 是三個 workload 中最差的）**。

### 2. **但** 2f 的 prefetch 開銷由 hot set 大小決定 — A/B 慢 30×、C 慢 7.6×

A/B 各 4,000+ syscalls × 1.8 µs/個 = 7.5 ms；**C 只 420 syscalls × 4.5 µs/個
= 1.9 ms（4× 便宜）**。對使用者來說，cold-tap 到「螢幕看到第一筆結果」的
時間：

```
                  baseline   →   2f SLRU
  A (Zipfian)     251 µs         7,269 µs  (慢 29×)
  B (Uniform)     255 µs         7,493 µs  (慢 30×)
  C (high-key)    250 µs         1,897 µs  (慢 7.6×)  ← 明顯改善
```

這是 2f 的核心 trade-off：**它不是「降低 cold start」的策略，是「升級成
working set preload」的策略**。

### 3. 全 workload 累積下來，2f 在 A/B 省 38–39%、**C 只省 7%**

```
總時間（cold start + 全 workload）：
  Workload A:  baseline 411 ms → 2f 249 ms  (-39%)
  Workload B:  baseline 413 ms → 2f 255 ms  (-38%)
  Workload C:  baseline 262 ms → 2f 245 ms  (-7%)
```

**改善幅度跟 baseline 的 avg-q 走**：A/B 的 baseline avg-q 是 4.1 µs（每筆
都要 cold-fault leaf），2f 壓到 2.5 µs；C 的 baseline avg-q 已經是 **2.62
µs**（leaves 已經高度共享同個 disk region、seek 路徑短），2f 只壓到 2.45 µs。
**C 的 baseline 本來就接近 SLRU 拉得到的下限，所以 2f 收益小。**

### 4. Workload A vs B 對 2f 沒差（推翻原本預測）

原本預期：2f 在 uniform B 上 ≈ 2d/2e（access count），在 skewed A 上
**劣於** 2d/2e，因為 SLRU 不會區分「打 7,752 次」 vs 「打 1 次」。

實測：A 和 B 結果幾乎相同（first-q 14 vs 15 µs、resident set 4048 vs 4122）。
原因：
- 兩個 workload 都打 id ∈ [1, 100k]，touch 到的**唯一 leaf 集合差不多**
- mincore 只能說 hot/cold，不能說 hot-degree，但這裡 hot set 全塞得進 RAM
  (4,000 × 4 KB ≈ 16 MB)，所以**沒有「該丟掉哪個」的競爭**，frequency 資訊
  用不上
- 2f vs 2d/2e 的差異只會在 **resident set 大於 RAM 預算** 時體現
  （RAM 預算 < 16 MB 時 access count 才能挑出最熱的 K 個）

### 5. C 上 layers_5 也大幅退化（-26% vs A/B 的 -46~47%）

confirm 先前在 [overall_results.md](../overall_results.md) 第七維就看到的
現象：「按 file offset 排前 5」對 file-tail workload 命中率低，因為 C 走的
interior path 不在全局上層。**layers_5 是 zipfian-friendly 的啟發式，
file-region workload 上效益打折。**

### 6. 2f 的「working-set preload」價值跟 hot set 的 leaf spread 成正比

A/B 的 hot set 是「3,300 個 leaf 散在 file 前 1/6」—— 每筆 query 都要解決
cold leaf fault，2f preload 完全消除這個 cost，所以全 workload 省 38%。
C 的 hot set 是「357 個 leaf 集中在 file 尾」—— baseline 已經幾乎沒有 cold
fault 可解（連續 leaves 一個 readahead 就吃完），2f preload 邊際收益只 7%。

**Working-set preload 的天花板**：當 baseline 的 avg-q 已經接近「全 hot 命中」
的下限時，2f 沒有空間再省。**C 的 baseline avg-q 2.62 µs 就是這個天花板。**

## Trade-off 矩陣（誰該用哪個策略）

| 應用情境 | 建議策略 | 為什麼 |
|---|---|---|
| 點開 App 馬上要看到第一筆（聯絡人、設定）| **2c Layers N=5** | cold-start 148 µs vs 2f 7,269 µs |
| 開啟後會跑一整段 workload（瀏覽相簿、滑訊息列表）| **2f SLRU** | 全 workload 時間 A/B 省 38% |
| Hot set 小且集中（高 id 區段、append-only tail）| **2f SLRU** | C 上 cold start 只慢 7.6×（vs A/B 慢 30×）|
| Workload baseline avg-q 已經接近 OS readahead 下限 | **不要用 2f** | C 全 workload 只省 7%，prefetch 成本回不來 |
| RAM 充裕、想最少程式碼實作 prefetch | **2f SLRU** | 不用攔截 SQLite，~70 行 C |
| RAM 緊（cgroup MemoryMax=20M），只看 first-q | **2f SLRU on 任一 layout** | 18 個 (WL, layout, mem) cells 全部 15-19 µs（-95~98%）；first-q **對 RAM 壓力完全免疫**（756-cell 矩陣：63 cells fq ratio 全在 [0.90, 1.19]） |
| RAM 緊（cgroup MemoryMax=20M），同時想保 avg/majflt | **2f SLRU + 1b vacuum** | A/B/C × vacuum × 2f × 20M 全部 majflt=0、avg=1.50/1.56（跟 unlimited 一致）；1a orig / 1c ta 下 2f preload 被 evict 跌回 base level | 
| RAM 緊、不想跑 warmup pass | **2e_K10**（C 全 layout）/ **2e_K500**（A/B）| 14-42 syscalls；C × 任一 layout × 20M 仍 -82~88%（跟 unlimited 一致） |

## Files

```
src/prefetch_slru.c    — 70 行 C，讀 residency CSV + madvise
runs/                  — warmup.sh、prefetch wrappers、runmatrix.sh、raw results
  workload_a_zipfian.txt → ../../benchmark_harness/workloads/workloadc.txt
  workload_b_uniform.txt → ../../benchmark_harness/workloads/workload_uniform.txt
  workload_c_highkey.txt → ../../prefetch_churn/workloads/page_churn_benchmark_high.txt
  hotpages_a.csv        — Workload A (Zipfian) warmup residency
  hotpages_b.csv        — Workload B (Uniform) warmup residency
  hotpages_c.csv        — Workload C (high-key uniform) warmup residency
results/               — results_summary.csv 等
```

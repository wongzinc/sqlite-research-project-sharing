# Prefetch Access-pattern — 策略 2d / 2e：access-count-ordered prefetch

`prefetch_access` 跑一遍 workload 取得「真實 walk 過的 interior pages」與「真實
查詢命中過的 leaf pages」，下一輪 cold start 時只對這些 page 呼叫
`madvise(MADV_WILLNEED)`。對照 [overall_strategies.md](../overall_strategies.md)
的編號，這個目錄涵蓋兩條軸線：

| 策略 | 載什麼 | 用途 |
|---|---|---|
| **2d** | 只 prefetch 真正被走過的 interior pages | 取代 2c layers_N 的「按 file offset 排前 N」啟發式，用 access count 排 |
| **2e** | 2d 集合再加 top-K 熱 leaves | 加上 leaf preload，但 K 可調（K=10/50/100/500）|

策略 2f (`prefetch_slru/`) 跟這裡的差別：2f 只看 mincore residency snapshot
（**hot/cold 二元**），這裡的 2d/2e 用 **access count**（區分 1 次 vs 100 次），
所以 K 個 syscall 永遠挑得到「真的最熱」的 K 個 page。

## 與其他策略的對應關係

| 策略 | 資料來源 | 精度 | 載入大小 |
|---|---|---|---|
| 2c Layers N（[prefetch_vacuum/](../prefetch_vacuum/)）| classify_pages（只看 page 類型 + offset）| 假設「offset 小 = 上層 = 熱」| 5~92 interior |
| **2d**（本目錄）| classify + warmup pass 的 mincore | access count（interior 端）| **4~32 interior**（不含 leaves）|
| **2e**（本目錄）| 同 2d，再加 access-count-ranked top-K leaves | access count（含 leaves）| **interior + K leaves**（K = 10/50/100/500）|
| 2f SLRU（[prefetch_slru/](../prefetch_slru/)）| warmup pass 的 mincore | 只 hot/cold | ~420~4,100 pages（整個 resident set）|

## Build

```bash
gcc -O2 -Wall -o src/prefetch_access src/prefetch_access.c
```

## 使用

```
prefetch_access <db> <classify.csv> <hotpages.csv> <n_interior> <n_leaf> <page_size>
  n_interior : cap on interior pages to prefetch (0 = no cap, take all resident)
  n_leaf     : cap on leaf pages to prefetch     (0 = 2d mode, skip leaves entirely)
```

- 2d mode：`n_leaf=0`，餵 baseline `hotpages_<wl>.csv`（mincore 的 raw dump）
- 2e mode：`n_leaf=K > 0`，餵 `hot2e_<WL>_<layout>_K<K>.csv`
  （`gen_hotleaves.py` 產生的 access-count-ranked 版本）

### 2e 的 hot-leaves CSV 怎麼來

`runs/gen_hotleaves.py` 用 `sqlite_dbpage` + varint decoder：

1. 對每個 leaf page 抽 first_rowid，建 `key → leaf_pageno` 對應表
2. 掃 workload 每個 `read <id>`，二分搜尋對應的 leaf
3. 對 leaves 累加查詢次數，取前 K
4. 跟 baseline `hotpages_<wl>.csv` 合併 → `hot2e_<WL>_<layout>_K<K>.csv`

```bash
python3 runs/gen_hotleaves.py \
  test.db classify_before.csv hotpages_a.csv \
  runs/workload_a_zipfian.txt 500 \
  runs/hot2e_A_orig_K500.csv
```

## 完整流程（以 Workload C × 1a × 2e_K10 為例）

```bash
# 1. WARMUP — evict + 跑 workload + dump residency
benchmark_harness \
  --db test.db --workload runs/workload_c_highkey.txt \
  --cold-advice dontneed --drop-caches-script runs/cold_orig.sh \
  --output runs/warmup_c.csv

# 2. 從 mincore snapshot 抽 top-K 熱 leaves
python3 runs/gen_hotleaves.py \
  test.db runs/classify_before.csv runs/hotpages_c.csv \
  runs/workload_c_highkey.txt 10 runs/hot2e_C_orig_K10.csv

# 3. MEASUREMENT — 2e_K10 wrapper
benchmark_harness \
  --db runs/test.db --workload runs/workload_c_highkey.txt \
  --cold-advice dontneed --drop-caches-script runs/cold_orig.sh \
  --post-cold-script runs/prefetch_2e_C_orig_K10.sh \
  --output runs/ops_C_orig_K10.csv
```

完整 A/B/C × 1a/1b/1c × {2d, 2e_K10/50/100/500} × {RAM=20M, none} 的批次跑法見
[runs/runmatrix_ram_pressure_full.sh](runs/runmatrix_ram_pressure_full.sh)（756
cells、median of 6）。

## 主要結果（first-q 改善 vs base，median of 6）

### 2d（interior-only）

| Workload × Layout | syscalls | 改善 |
|---|---:|---:|
| C × 1a (orig)   | **4**  | **-64%**（241 µs，base 667 µs；追平 layers_92）|
| C × 1b (vacuum) | 4      | -43% |
| C × 1c (ta)     | 32     | -6%（**TA × C 失效**——mincore 觀察到的 resident interior 被 readahead pollution 污染；解法用 2e）|
| A × 1a / 1b     | 14-21  | -25~-28% |
| A × 1c (ta)     | 31     | **-68%**（最強）|
| B × 任一 layout | 14-31  | -45~-51% |

**2d 解掉「layers_N 在 C 上失效」**：C × 1a 只用 4 syscall 拿到 layers_92 的
-46% 效益（甚至更高），syscall 數從 92 → 4（**省 23×**）。

### 2e（interior + top-K hot leaves）

最佳組合按 (workload, layout) 排：

| WL × Layout | 最佳 K | syscalls | 改善 |
|---|---|---:|---:|
| **C × 任一 layout** | **K=10** | 14~42 | **-82~88%**（救回 1c × C 的 -6% 失效） |
| **A × 1a / 1b** | K=500 | ~518 | -73~77% |
| A × 1c (ta) | 2d 完勝 | (上表) | K≥10 全部退化 |
| B × 1a / 1b | K=10 ≈ 2d | 14~16 | -47~51% |
| B × 1c (ta) | K=50 | ~52 | -37~38%（救回 2d 失效） |

**邊際 syscall 報酬率**：在 C 上，從 2d 的 4 syscall (-64%) 加到 2e_K10 的
14 syscall (-88%)，**每多 1 個 madvise ≈ 救 18 µs first-query latency**。

> ⚠️ **歷史 bug**：`src/prefetch_access.c` 早期 `cap_leaf` ternary 兩個分支都
> 返回 `cap_leaf`，加上 `cap_leaf==0` → 2d-mode 覆寫，早期所有 2e_K* 實際跑
> 的都是 2d（n_leaf=0）。修正後（[`src/prefetch_access.c`](src/prefetch_access.c)
> 第 113-115 行）重跑，現在的數據才是合法的 2e 結果。

## RAM-pressure 完整矩陣

`runs/runmatrix_ram_pressure_full.sh` 用 `systemd-run --user --scope -p
MemoryMax=20M` 把 process memory.max 卡到 20 MB（≪ DB 107 MB），跑
**A/B/C × 1a/1b/1c × {base, 2d, 2e_K10/50/100/500, 2f_SLRU} × {20M, none}
× 6 reps = 756 cells**。

| 觀察 | 數字 |
|---|---|
| First-q ratio (20M / unlimited) 全部範圍 | **[0.90, 1.19]**（63 cells） |
| 2d / 2e_K10 / 2f_SLRU 的最佳改善在 20M 下保留 | C × 任一 layout × 2e_K10 仍 -82~88% |
| 最差退化 | A vacuum × 2e_K100：223 → 266 µs (+19%)，仍遠優於 base 337 µs |

**結論：access-pattern prefetch 的優勢在 RAM 緊環境下完全成立**——cgroup
MemoryMax 不會打殘 first-q。受影響的是 avg_us / majflt（後續 query 的 cache
命中率），而非 first-q。詳見 [overall_results.md 第十六維](../overall_results.md#第十六維--ram-pressure-完整矩陣cgroup-memorymax20-mb-abc--1a1b1c--base-2d-2e_k1050100500-2f_slru)。

## Trade-off 矩陣（誰該用 2d 或 2e）

| 應用情境 | 建議策略 | 為什麼 |
|---|---|---|
| 有 warmup pass、想用最少 syscall 在 C 上拿 -46% | **2d on 1a/1b** | 4 syscall，等同 layers_92 |
| 有 warmup pass、想在 C 上 first-q 接近 0 | **2e_K10** 任何 layout | 14-42 syscall → -82~88% |
| 有 warmup pass、A workload | **2e_K500 on 1a/1b** | 518 syscall → -73~77%（K=10 因 A 熱點分散不夠強）|
| 有 warmup pass、A × ta | **2d** | K≥10 全部退化，TA 已把 interior 集中、加 leaves 反而拖慢 |
| 沒 warmup pass（cold first-ever-launch）| 退回 [prefetch_vacuum/](../prefetch_vacuum/) 的 2c layers_N | access-pattern 需要先看過一輪 query |
| RAM 緊（cgroup MemoryMax=20M）| **2e_K10 on C / 2e_K500 on A** | 第十六維 756-cell：改善在 20M 下完全保留 |

## Files

```
src/prefetch_access.c           — 主程式 (~140 行 C)，2d/2e 共用
src/prefetch_access              — 編譯後 binary（不入 git，gitignore'd）
runs/
  gen_hotleaves.py              — 從 workload + classify 算 top-K 熱 leaves
  aggregate_ram_full.py         — 把 matrix CSV 聚合成 markdown
  cold_{orig,vacuum,ta}.sh      — 對應三個 DB layout 的 evict helper
  prefetch_2d_<wl>_<layout>.sh  — 9 個 2d wrapper（A/B/C × orig/vacuum/ta）
  prefetch_2e_<WL>_<layout>_K<K>.sh — 36 個 2e wrapper (× 4 K)
  prefetch_2f_<WL>_<layout>.sh  — 9 個 2f wrapper（呼叫 ../../prefetch_slru/runs/prefetch_slru）
  hotpages_<wl>[_<layout>].csv  — 各 workload × layout 的 mincore baseline
  hot2e_<WL>_<layout>_K<K>.csv  — gen_hotleaves.py 產生的 access-count ranked
  classify_{before,after,vacuum}.csv — 各 layout 的 page type 表
  runmatrix_2d.sh                — 2d 矩陣跑法（A/B/C × 3 layouts）
  runmatrix_2e.sh / _abc.sh      — 2e 矩陣跑法
  runmatrix_ram_pressure.sh      — 早期 48-cell RAM 矩陣（A × 1a × 4 策略）
  runmatrix_ram_pressure_full.sh — 全 756-cell RAM 矩陣（A/B/C × 1a/1b/1c × 7 策略）
  matrix_2d_results.csv          — 2d raw 結果
  matrix_2e_results.csv          — 2e raw 結果
  matrix_ram_results.csv         — 48-cell RAM 矩陣 raw
  matrix_ram_full_results.csv    — 756-cell RAM 矩陣 raw
  matrix_ram_full_summary.md     — aggregate_ram_full.py 輸出
```

## 結果文件對照

- [overall_results.md 第十四維](../overall_results.md#第十四維--2d-access-pattern-prefetch-interior-only--abc--3-layouts) — 2d × A/B/C × 3 layouts
- [overall_results.md 第十五維](../overall_results.md#第十五維--2e-access-pattern-prefetch-interior--top-k-leaves--abc--3-layouts--kk10k50k100k500) — 2e × A/B/C × 3 layouts × K∈{10,50,100,500}
- [overall_results.md 第十六維](../overall_results.md#第十六維--ram-pressure-完整矩陣cgroup-memorymax20-mb-abc--1a1b1c--base-2d-2e_k1050100500-2f_slru) — RAM-pressure 全 756-cell 矩陣

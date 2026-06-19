# Workload × Strategy 跑全排列的檔案 reference

> **目的**：給接手「跑新 workload 全策略排列」的同學一份 trace map——避免在
> 12,000+ 個 file 裡找半天。本檔列出每種 workload 已用到哪些檔，以及加新
> workload 時要產出什麼。

---

## 0. P0 Cold-Start Pipeline（**所有實驗都必須遵循**）

> 這是 2026-06-19 起的 gold-standard 規範。本檔列出的 command、§3 範例、
> 以及未來新加的任何 workload / strategy **全部都必須跑在 P0 pipeline 下**。
> 偏離者請在 PR 描述明示理由。設計依據與歷史 pipeline 對照見
> [IMPLEMENTATION_PIPELINES.md](IMPLEMENTATION_PIPELINES.md)。

### P0 = 四個強制層級

| 層 | 機制 | 目的 |
|---|---|---|
| ① harness MADV chain | `--cold-advice dontneed`（= `MADV_COLD → MADV_PAGEOUT → MADV_DONTNEED`）| 對自家 mmap 區域強制 kernel 回收 |
| ② 全機 drop_caches | `--drop-caches-script /usr/local/sbin/drop-caches` | 全機 page cache + dentries + inodes 一律清空（setuid wrapper、u03 可跑、不需 sudo）|
| ③ Prefetch hint | `--post-cold-script <strategy_prefetch.sh>` | 策略本身的 prefetch（這是「策略」差異所在）|
| ④ Residency verify | 跑完後 `residency_checker --threshold 0` | 強制驗證 cache 真的清空了；不為 0 abort 該 cell |

### 為什麼必須 P0

過去 codebase 同時跑 4 條不同 pipeline（per-file fadvise / system drop_caches /
跳過 MADV chain / 關掉 residency verify）——這是
[CONTRADICTIONS.md](../CONTRADICTIONS.md) #24 與 #1/6/7/9 一票數據打架的根因。
P0 統一機制後，**同一個 batch 內**的數字才有跨表可比性。

### 注意：禮貌（強制）

`/usr/local/sbin/drop-caches` **會沖掉工作站上所有同學的 page cache**。
跑 master batch（>100 cell）請：

- 集中夜間時段
- 跑前 group chat 公告（含預估 wallclock）
- 不要在 interactive dev / 探索時 loop 呼叫

---

## 1. 共用 infrastructure（所有 workload 都會用）

這些檔案**跟 workload 無關**，建立一次就所有人用：

### 1.1 三個 DB file（測試 DB，每個對應一個 layout）

| Layout | File | Scatter score |
|---|---|---:|
| 1a 原始 | `layout_rewriter/runs/test.db` | 0.96 |
| 1b VACUUM | `layout_rewriter/runs/test_vacuum.db` | 1.13 |
| 1c type-aware | `layout_rewriter/runs/test_typeaware.db` | 0.0001 |

**Schema 都一樣**：`items(id PK, k1, k2, payload BLOB(100))` + `idx_items_k1k2`。600k row、102 MB。

> 三個 DB **不要重建**——換 DB 等於換 machine state，已有的 result 全部要重跑。

`prefetch_access/runs/test*.db` 跟 `prefetch_slru/runs/test*.db` 都是 symlink 指到上面三個。

### 1.2 三個 classify.csv（page_number → page_type 的對照，每個 DB 一份）

| Layout | File |
|---|---|
| 1a | `layout_rewriter/runs/classify_before.csv` |
| 1b | `layout_rewriter/runs/classify_vacuum.csv` |
| 1c | `layout_rewriter/runs/classify_after.csv` |

`prefetch_access/runs/classify_*.csv` 也是 symlink。

### 1.3 三個 cold script（per-layout cold-start drop）

**2026-06-19 起全部走 P0 §0**：所有 cold script 統一 `exec /usr/local/sbin/drop-caches`
（全機 page cache + dentries + inodes 一刀清）。layout 不再決定 evict 機制——
這三個檔留著只是為了 orchestrator 向後相容（各自的路徑不變）。

| Layout | File | 做什麼 |
|---|---|---|
| 1a | `layout_rewriter/runs/cold_orig.sh` | `exec /usr/local/sbin/drop-caches` |
| 1b | `layout_rewriter/runs/cold_vacuum.sh` | `exec /usr/local/sbin/drop-caches` |
| 1c | `layout_rewriter/runs/cold_ta.sh` | `exec /usr/local/sbin/drop-caches` |

> **歷史**：2026-06-19 之前這三個檔呼叫 `evict` binary（per-file
> `posix_fadvise(POSIX_FADV_DONTNEED)`）。`evict.c` 跟編出的 binary 仍在 repo
> 內以備需要 single-file evict 場景，但**不再是 production cold-start 機制**。

### 1.4 四個 prefetch tool（C binary）

| Tool | Source | 用在哪些策略 | Args 簽章 |
|---|---|---|---|
| `prefetch` | [`prefetch_vacuum/src/prefetch.c`](prefetch_vacuum/src/prefetch.c) | **2a range / 2b perpage**（structure-based）| `<db> <classify.csv> {range\|perpage}` |
| `prefetch_layers` | [`prefetch_vacuum/src/prefetch_layers.c`](prefetch_vacuum/src/prefetch_layers.c) | **2c layers_N**（structure-based）| `<db> <classify.csv> <N> <page_size>` |
| `prefetch_access` | [`prefetch_access/src/prefetch_access.c`](prefetch_access/src/prefetch_access.c) | **2d/2e**（history + page-type aware）+ **3a/3b** ratio variant | `<db> <classify.csv> <hotpages.csv> <cap_interior> <cap_leaf> <page_size>` |
| `prefetch_slru` | [`prefetch_slru/src/prefetch_slru.c`](prefetch_slru/src/prefetch_slru.c) | **2f SLRU** | `<db> <hotpages.csv> <page_size>` |

> **歷史錯誤更正（2026-06-19）**：本表之前把 2a/2b 也歸到 `prefetch_layers`
> 名下、並寫成「`prefetch_layers <db> <classify> 92 4096 range`」5-arg 簽章
> ——這是錯誤的。`prefetch_layers` 只吃 4 個 arg、且不接 `range`/`perpage`
> 子命令。2a/2b 用的是另一個 binary `prefetch`。對應到
> [CONTRADICTIONS.md](../CONTRADICTIONS.md) #26 已更正。

### 1.5 Benchmark harness + workload generator

| Tool | Source | 用途 |
|---|---|---|
| `benchmark_harness` | [`benchmark_harness/benchmark_harness.c`](benchmark_harness/benchmark_harness.c) | 跑一格 cold-start latency measurement |
| `gen_hotleaves.py` | [`prefetch_access/runs/gen_hotleaves.py`](prefetch_access/runs/gen_hotleaves.py) | 從 (DB, classify, base hotpages, workload, K) 產 hot2e_*.csv |

---

## 2. 每個 workload 用的檔案（per-workload artifacts）

每個 workload 需要它**自己的**：
- **workload .txt 檔**（100k ops，一格 op 一行）
- **3 個 base hotpages CSV**（layout × workload，從 warmup pass 量出來）
- **18 個 hot2e CSV**（3 layout × K=6 個值 [10, 40, 50, 92, 100, 500]）

### 2.1 Workload A（Zipfian, keys [8, 99997]）

| 用途 | File |
|---|---|
| Workload .txt | `benchmark_harness/workloads/workload_a_zipfian.txt`（原名 `workloadc.txt`，2026-06 改名以跟 B/C 對齊）|
| | 同檔的 symlink：`prefetch_slru/runs/workload_a_zipfian.txt`、`prefetch_access/runs/workload_a_zipfian.txt`、`prefetch_churn/generated_workloads/workload_a_zipfian.txt` |
| Base hotpages（1a/1b/1c）| `prefetch_access/runs/hotpages_a{,_vacuum,_ta}.csv` |
| hot2e（18 個檔）| `prefetch_access/runs/hot2e_A_{orig,vacuum,ta}_K{10,40,50,92,100,500}.csv` |

### 2.2 Workload B（uniform, keys [1, 99999]）

| 用途 | File |
|---|---|
| Workload .txt | `benchmark_harness/workloads/workload_uniform.txt` |
| | 另一份 copy: `prefetch_access/runs/workload_b_uniform.txt` |
| Base hotpages | `prefetch_access/runs/hotpages_b{,_vacuum,_ta}.csv` |
| hot2e | `prefetch_access/runs/hot2e_B_{orig,vacuum,ta}_K{10,40,50,92,100,500}.csv` |

### 2.3 Workload C（high-key, keys [590k, 610k]）

| 用途 | File |
|---|---|
| Workload .txt | `prefetch_churn/workloads/page_churn_benchmark_high.txt` |
| | 另一份 copy: `prefetch_access/runs/workload_c_highkey.txt` |
| Base hotpages | `prefetch_access/runs/hotpages_c{,_vacuum,_ta}.csv` |
| hot2e | `prefetch_access/runs/hot2e_C_{orig,vacuum,ta}_K{10,40,50,92,100,500}.csv` |

### 2.4 Workload Z（Zipfian low-key, [1, 1000]）— robustness 對照

| 用途 | File |
|---|---|
| Workload .txt | `benchmark_harness/workloads/workload_zipf_lowkey.txt` |
| Generator | `benchmark_harness/workloads/gen_zipf_lowkey.py` |
| hotpages | **沒做**（Z 只用 2c layers_N，不用 access-pattern）|

### 2.5 Workload D（write generator）— 不量 latency，是 churn 用的寫入產生器

| 用途 | File |
|---|---|
| Write workload .txt | `prefetch_churn/workloads/page_churn_write.txt` |
| 用在 | `prefetch_churn/sqlite_prefetch_churn_experiment.py --write-workload` |

D **不需要 hotpages**——它只負責寫入製造 churn，不會被 cold-start measure。

### 2.6 new_workloads/（同學 A 跑的 600 個檔）

| 用途 | File |
|---|---|
| 600 workload txt | `new_workloads/read/...` + `new_workloads/scan/...` |
| Metadata | `new_workloads/SUMMARY.csv` |
| 說明 | [`new_workloads/README.md`](new_workloads/README.md) |
| hotpages | **每個都還沒產**（同學 A 跑全排列前要產）|

---

## 3. 一格 benchmark 的精確 command（**P0 pipeline 版本**）

無論哪種策略，都長這樣（只差 `--post-cold-script` 換哪支 prefetch script）：

```sh
benchmark_harness/benchmark_harness \
  --db        layout_rewriter/runs/test.db \
  --workload  <某個 workload .txt 路徑> \
  --output    <ops CSV 輸出路徑> \
  --record-dir <log 目錄> \
  --cold-advice dontneed \                                # P0 ①
  --drop-caches-script /usr/local/sbin/drop-caches \      # P0 ②（**取代 cold_*.sh**）
  --post-cold-script   <某支 prefetch script>             # P0 ③

# 跑完後（P0 ④）：
residency_checker --db <db> --threshold 0 || exit 1       # 不為 0 abort cell
```

> 也可繼續傳 `--drop-caches-script layout_rewriter/runs/cold_orig.sh`——這些
> `cold_*.sh` 內部已經改成 `exec /usr/local/sbin/drop-caches`，跑出來效果
> 一致。但建議**直接傳 wrapper 路徑**，少一層 indirection。

`--post-cold-script` 是「換策略」的開關。每支 prefetch script 就是 `exec`
對應的 prefetch tool 帶不同參數。**所有簽章與 §1.4 一致**：

| 策略 | post-cold-script 內容 | Tool |
|---|---|---|
| 2a range | `exec prefetch <db> <classify> range` | `prefetch` |
| 2b perpage | `exec prefetch <db> <classify> perpage` | `prefetch` |
| 2c layers_5 | `exec prefetch_layers <db> <classify> 5 4096` | `prefetch_layers` |
| 2c layers_N | `exec prefetch_layers <db> <classify> N 4096` | `prefetch_layers` |
| 2d | `exec prefetch_access <db> <classify> <hotpages> 0 0 4096` | `prefetch_access` |
| 2e_K10 | `exec prefetch_access <db> <classify> <hot2e_K10> 0 10 4096` | `prefetch_access` |
| 2e_K500 | `exec prefetch_access <db> <classify> <hot2e_K500> 0 500 4096` | `prefetch_access` |
| 2f SLRU | `exec prefetch_slru <db> <hotpages> 4096` | `prefetch_slru` |

詳細的 timeline + 每支 prefetch script 模板見
[`strategies_explained.md`](strategies_explained.md) 或
[`benchmark_harness/BENCHMARK_HARNESS.md`](benchmark_harness/BENCHMARK_HARNESS.md)。

---

## 4. Recipe：加新 workload 要產出什麼

假設你同學要加一個新 workload，叫 **Workload W**：

### 4.1 必要產出（無論跑哪些策略都需要）

```bash
# 1. workload .txt 檔，每行一個 op
# 例: read 12345
echo "read ..." > new_workloads/workload_W.txt
```

### 4.2 想跑 2a/2b/2c（structure-based）→ 不用再產 hotpages

只要有 §1 的共用 DB / classify / evict 就能跑。post-cold-script 直接帶 `prefetch_layers` + 參數。

### 4.3 想跑 2d / 2e_K* / 2f SLRU（history-based）→ **每個 layout 各產一份 hotpages**

對每個 layout（1a/1b/1c），跑一次 warmup pass 量 base hotpages：

```bash
# Warmup pass: 把 workload 跑一次、用 mincore() 拍 resident snapshot
benchmark_harness/benchmark_harness \
  --db layout_rewriter/runs/test.db \
  --workload new_workloads/workload_W.txt \
  --output /tmp/warmup_ops.csv \
  --record-dir /tmp/warmup_rec \
  --cold-advice dontneed \
  --drop-caches-script layout_rewriter/runs/cold_orig.sh
# 跑完之後用 residency_checker 拍快照
residency_checker/residency_checker \
  layout_rewriter/runs/test.db \
  prefetch_access/runs/hotpages_w.csv
```

> ⚠️ 要 1a/1b/1c 三個 layout 都要產，命名統一：`hotpages_w{,_vacuum,_ta}.csv`。

然後對每個 K∈{10, 40, 50, 92, 100, 500}（或你選的 K 集合）產 hot2e CSV：

```bash
for layout in orig vacuum ta; do
  case $layout in
    orig)   db=layout_rewriter/runs/test.db;          cl=classify_before.csv;  hot_suffix= ;;
    vacuum) db=layout_rewriter/runs/test_vacuum.db;   cl=classify_vacuum.csv;  hot_suffix=_vacuum ;;
    ta)     db=layout_rewriter/runs/test_typeaware.db; cl=classify_after.csv;   hot_suffix=_ta ;;
  esac
  for K in 10 40 50 92 100 500; do
    python3 prefetch_access/runs/gen_hotleaves.py \
      $db \
      layout_rewriter/runs/$cl \
      prefetch_access/runs/hotpages_w$hot_suffix.csv \
      new_workloads/workload_W.txt \
      $K \
      prefetch_access/runs/hot2e_W_${layout}_K${K}.csv
  done
done
```

→ 每新 workload 多 **3 個 base hotpages + 18 個 hot2e = 21 個 CSV**。

### 4.4 想跑 churn（access-pattern × churn 對 W 的衰退）→ 額外需要

- 一份 churn workload（mixed write/read）——目前 D 就是這個用途
- run script 模仿 [`prefetch_churn/runs_access_churn_b/run_access_churn_b.sh`](prefetch_churn/runs_access_churn_b/run_access_churn_b.sh)
  改 `--benchmark-workload` 跟 `--prefetch-hotpages` 即可

### 4.5 跑全排列 matrix 的 driver 範例

最像「全排列」的現成 driver：

| Driver | 包含 |
|---|---|
| [`prefetch_access/runs/runmatrix_2d.sh`](prefetch_access/runs/runmatrix_2d.sh) | 2d × A/B/C × 3 layout × 3 reps |
| [`prefetch_access/runs/runmatrix_2e_abc.sh`](prefetch_access/runs/runmatrix_2e_abc.sh) | 2e_K* × A/B/C × 3 layout × 6 reps |
| [`prefetch_access/runs/runmatrix_ram_pressure_full.sh`](prefetch_access/runs/runmatrix_ram_pressure_full.sh) | A/B/C × 1a/1b/1c × 7 策略 × 2 mem × 6 reps（756 cells）|
| [`layout_rewriter/runs/runmatrix_Nsweep_FULL.sh`](layout_rewriter/runs/runmatrix_Nsweep_FULL.sh) | 2c × N=0..92 × A/B/C × 3 layout × 3 reps |

複製其中一支、把 workload 路徑換成 `workload_W.txt`、把對應的 hotpages 換成 `hotpages_w*` 就能跑。

---

## 5. Calibration（prefetch tool 自己的時間）

跑完 latency benchmark 後，**還要量 prefetch tool 自己花的時間**——這跟 workload 沒關（同個 layout、同個 N/K 下時間相同），所以同學跑新 workload 時可以**重用既有 calibration 數據**。

| File | 內容 |
|---|---|
| [`calibration/prefetch_time_summary.csv`](calibration/prefetch_time_summary.csv) | 351 cells × 3 reps median 的 prefetch_us |
| [`calibrate_prefetch_time.py`](calibrate_prefetch_time.py) | 重跑 calibration 的 driver |

如果同學跑新 workload 用了**沒在 calibration 裡的 K**（例如 K=200），要補跑那個 cell 的 calibration。

---

## 6. 結果 CSV 應該放哪、命名怎麼一致

| 實驗類型 | 既有命名慣例 | 新 workload 建議用 |
|---|---|---|
| Clean-DB matrix | `layout_rewriter/runs/matrix_*_results.csv` | `matrix_W_results.csv` |
| Access-pattern matrix | `prefetch_access/runs/matrix_2{d,e}_results.csv` | 新欄位加 workload column |
| Churn experiments | `prefetch_churn/runs_access_churn_w/...` | 同上模式 |
| Aggregated summary | `*/results/results_summary.csv` | 同上 |

Schema 建議 `workload,db_layout,strategy,rep,first_query_us,avg_us,majflt,minflt`（既有的標準）。

---

## 7. TL;DR for the classmate

```
跑 1 個新 workload W 全排列要產的東西：
─────────────────────────────────────────
1 個 workload .txt                              ←自己生
3 個 hotpages CSV (1a/1b/1c base)               ←跑 warmup pass × 3
18 個 hot2e CSV (3 layout × K=6 values)         ←跑 gen_hotleaves.py × 18
0 個 calibration（重用既有的）
─────────────────────────────────────────
                  = 22 個新檔案

跑全排列要 N 個 cell：
─────────────────────────────────────────
3 layouts × 7 strategies × 3 reps × {不限, 20M cgroup} × 1 workload
= 126 cells (~ 4 分鐘 clean DB only;  +20-40 min for churn variant)
```

不確定就翻 [`overall_strategies.md`](overall_strategies.md) 看每個策略原理，或翻 [`benchmark_harness/BENCHMARK_HARNESS.md`](benchmark_harness/BENCHMARK_HARNESS.md) 看 harness 細節。

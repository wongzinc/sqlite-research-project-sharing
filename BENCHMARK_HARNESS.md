# benchmark_harness 說明

`benchmark_harness` 是這個專案裡用來觀察 SQLite workload 在 cold-start 情境下行為的主要測試程式。

它的核心用途不是單純跑快慢測試，而是把「執行 workload 前後，SQLite database pages 留在記憶體裡的情況」和「每個 operation 的 latency / page fault 變化」一起記錄下來，方便後續和 `classify_pages` 的 page type 結果合併分析。

## 適合回答的問題

`benchmark_harness` 可以幫你觀察：

- cold advice 前後，SQLite database file 有多少 page 還 resident。
- cold advice 前後，resident page 的 page number 分布長什麼樣子。
- benchmark 跑完後，哪些 SQLite page 又變成 resident。
- workload 中每個 operation 的 latency。
- 每個 operation 期間 major / minor page fault 數量增加多少。
- 整次 benchmark 的 operation count、average latency、first query latency、total major faults、total minor faults。
- 搭配 `classify_pages` 後，不同 page type 在 benchmark 前後的 residency rate。

它不會測量「每一次 page fault 本身花了多久」。目前記錄的是 operation 前後的 `getrusage()` fault counter 差值，也就是某個 operation 期間 major / minor fault 數量增加多少。

## 基本流程

一次 benchmark 大致會做這些事：

1. 讀取 workload 檔案。
2. 開啟並 mmap SQLite database file。
3. 讀 SQLite header，取得 page size 與 page count。
4. 建立唯一的 operations CSV。
5. 建立唯一的 run record log。
6. 依照設定，在 cold advice 前或後開啟 SQLite connection / 初始化 schema。
7. 記錄 cold advice 前的 SQLite page residency。
8. 對 database mapping 執行 cold advice。
9. 記錄 cold advice 後的 SQLite page residency。
10. 逐筆執行 workload operation，記錄 latency 與 fault delta。
11. 輸出整體 benchmark summary。
12. 記錄 benchmark 結束後的 SQLite page residency。

## 輸入

最小執行方式：

```sh
./benchmark_harness --workload generated_workloads/workloadc.txt
```

常用參數：

```sh
./benchmark_harness \
  --db test.db \
  --workload generated_workloads/workloadc.txt \
  --output benchmark_harness_operations.csv \
  --record-dir benchmark_harness_runs \
  --cold-advice dontneed
```

預設值：

| 參數 | 預設值 | 說明 |
| --- | --- | --- |
| `--db` | `test.db` | 要測試的 SQLite database |
| `--output` | `benchmark_harness_operations.csv` | per-operation CSV 輸出 |
| `--record-dir` | `benchmark_harness_runs` | run record log 目錄 |
| `--mmap-size` | database file size | SQLite `PRAGMA mmap_size` 目標值 |
| `--cold-advice` | `dontneed` | cold advice 模式 |
| `--sqlite-open-timing` | `before-cold` | SQLite connection 開啟時機 |
| `--schema-init-timing` | `before-cold` | schema / prepared statements 初始化時機 |

`--workload` 沒有預設值，必須指定。

## Workload 格式

workload 是純文字檔，一行一個 operation：

```text
READ 123
UPDATE 456
INSERT 789
READMODIFYWRITE 321
```

目前支援的 operation：

| operation | 行為 |
| --- | --- |
| `READ <id>` | 查詢指定 key |
| `UPDATE <id>` | 更新指定 key |
| `INSERT <id>` | 插入指定 key |
| `READMODIFYWRITE <id>` | 先讀再更新 |

`UPDATE`、`INSERT`、`READMODIFYWRITE` 都會改變 database file。若你要比較不同實驗之間的 page residency，請留意每次 benchmark 後 database 內容可能已經不同。

使用 `generated_workloads/generate_ycsb_workloads.py` 產生 workload 時，預設 seed 是固定的。同樣的 workload spec、generator 版本與 seed 會產生相同 workload。

## Cold Advice

`--cold-advice` 控制 harness 如何要求 kernel 降低 database pages 的 residency：

| 模式 | 行為 |
| --- | --- |
| `cold` | 使用 `MADV_COLD` |
| `pageout` | 使用 `MADV_COLD` 後再使用 `MADV_PAGEOUT` |
| `dontneed` | 使用 `MADV_COLD`、`MADV_PAGEOUT`，再使用 `MADV_DONTNEED` |

這些 API 是 kernel hint，不是絕對保證。實際有多少 page 被移出 resident set，要看 run record 裡 cold advice 前後的 residency 結果。

## Debug Mode

預設不開 `--debug` 時，harness 只輸出 benchmark 需要的主要資訊：

- cold advice 前後的 resident SQLite page 數量。
- cold advice 前後的 resident page 分布。
- operation count。
- average latency。
- first query latency。
- total major page faults。
- total minor page faults。
- benchmark 結束後 resident SQLite page 數量。

開啟 `--debug` 後，才會額外輸出比較偏實作細節的資訊：

- `madvise()` 是否成功。
- `msync()` / `fsync()` 是否成功。
- SQLite open timing。
- schema initialization timing。

## 輸出一：operations CSV

`benchmark_harness_operations.csv` 是 per-operation 結果。每一列對應 workload 的一筆 operation。

欄位：

```text
op_no,op_type,target_id,rows_returned,bytes_returned,elapsed_ns,majflt_delta,minflt_delta
```

欄位意義：

| 欄位 | 說明 |
| --- | --- |
| `op_no` | operation 編號，從 1 開始 |
| `op_type` | operation 類型 |
| `target_id` | operation 目標 key |
| `rows_returned` | 查詢回傳列數 |
| `bytes_returned` | 查詢回傳資料量 |
| `elapsed_ns` | operation latency，單位 ns |
| `majflt_delta` | 這個 operation 期間 major fault counter 增加量 |
| `minflt_delta` | 這個 operation 期間 minor fault counter 增加量 |

operations CSV 不會覆蓋既有檔案。如果指定的輸出檔已經存在，harness 會自動產生 suffix：

```text
benchmark_harness_operations.csv
benchmark_harness_operations-1.csv
benchmark_harness_operations-2.csv
```

實際使用的 CSV 路徑會寫進 run record 的 `output=` 欄位。

## 輸出二：run record log

每次 benchmark 都會在 `--record-dir` 裡建立一個唯一 log：

```text
benchmark_harness_runs/run-YYYYMMDD-HHMMSS-pid.log
```

run record 會記錄：

- db path。
- workload path。
- 實際 operations CSV path。
- page size。
- page count。
- cold advice mode。
- cold advice 前的 residency count / distribution / ranges。
- cold advice 後的 residency count / distribution / ranges。
- benchmark summary。
- benchmark 結束後的 residency count / distribution / ranges。

run record 的用途是保留「這次 benchmark 的整體狀態」。它適合拿來做跨 run 比較，也適合和 `classify_pages.csv` 合併，分析不同 page type 的 residency rate。

## Residency 分布怎麼記錄

harness 會對 SQLite database 的每個 page 呼叫 `mincore()`，判斷該 page 是否 resident。

接著它會輸出三種資訊：

| 資訊 | 用途 |
| --- | --- |
| count | resident pages 總數 |
| distribution | resident pages 依 page number 區間分桶後的分布 |
| ranges | 連續 resident page range |

distribution 適合快速看 resident pages 集中在檔案前段、中段或後段。ranges 則適合給後處理腳本還原每個 page 的 resident 狀態。

## 搭配 classify_pages 分析 page type

如果你想知道不同類型 page 的存活率，流程是：

1. 先用 `classify_pages` 產生 page type CSV。
2. 跑 `benchmark_harness`，取得 run record log。
3. 用分析腳本把 page type 和 run record residency 合併。

範例：

```sh
./classify_pages test.db > classify_pages.csv

./benchmark_harness \
  --db test.db \
  --workload generated_workloads/workloadc.txt

python3 benchmark_harness_analyze_residency_by_page_type.py \
  classify_pages.csv \
  benchmark_harness_runs/run-YYYYMMDD-HHMMSS-pid.log \
  benchmark_harness_residency_by_page_type.csv
```

`benchmark_harness_residency_by_page_type.csv` 會 append 新資料，不會覆蓋既有內容。每列會用 `benchmark_log_name` 記錄資料來自哪一個 run record。

輸出欄位包含：

```text
benchmark_log_name,phase,page_type,total_pages,resident_pages,nonresident_pages,
residency_rate,phase_resident_pages,phase_first_resident_page,
phase_last_resident_page,operation_count,average_latency_us,
first_query_latency_us,total_major_page_faults,total_minor_page_faults
```

其中 `phase` 通常會包含：

- `before madvise`
- `after madvise`
- `after run`

這個 CSV 比較適合給程式讀。如果要人讀，建議再產生 Markdown report。

## 後處理腳本

### 繪製 per-operation latency / fault

```sh
python3 benchmark_harness_plot_results.py \
  benchmark_harness_operations.csv \
  benchmark_harness_results.png
```

預設最多取樣 20000 筆資料。若要每筆 operation 都畫：

```sh
python3 benchmark_harness_plot_results.py \
  benchmark_harness_operations.csv \
  benchmark_harness_results.png \
  --max-points 0
```

### 繪製 latency vs fault 數量

```sh
python3 benchmark_harness_plot_latency_vs_faults.py \
  benchmark_harness_operations.csv
```

預設只畫 major faults。可以用 `--faults` 切換：

```sh
python3 benchmark_harness_plot_latency_vs_faults.py \
  benchmark_harness_operations.csv \
  --faults both
```

可用值：

- `major`
- `minor`
- `both`

### 產生 page type residency Markdown report

```sh
python3 benchmark_harness_residency_report.py \
  benchmark_harness_residency_by_page_type.csv
```

預設會輸出同名 `.md`：

```text
benchmark_harness_residency_by_page_type.md
```

## 建議工作流

常見完整流程：

```sh
python3 testdb_builder.py

python3 generated_workloads/generate_ycsb_workloads.py

./classify_pages test.db > classify_pages.csv

./benchmark_harness \
  --db test.db \
  --workload generated_workloads/workloadc.txt \
  --output benchmark_harness_operations.csv \
  --record-dir benchmark_harness_runs

python3 benchmark_harness_plot_results.py \
  benchmark_harness_operations.csv \
  benchmark_harness_results.png

python3 benchmark_harness_analyze_residency_by_page_type.py \
  classify_pages.csv \
  benchmark_harness_runs/run-YYYYMMDD-HHMMSS-pid.log \
  benchmark_harness_residency_by_page_type.csv

python3 benchmark_harness_residency_report.py \
  benchmark_harness_residency_by_page_type.csv
```

請把 `run-YYYYMMDD-HHMMSS-pid.log` 換成實際產生的 run record 檔名。

## 注意事項

- `benchmark_harness` 使用 `mmap()`、`mincore()`、`madvise()`、`getrusage()` 等 POSIX / Linux 介面，主要應在 Linux 或相容環境中編譯執行。
- `MADV_COLD`、`MADV_PAGEOUT`、`MADV_DONTNEED` 是 kernel hint，cold advice 後仍可能有 page resident。
- `majflt_delta` / `minflt_delta` 是 operation 前後 fault counter 的差值，不是 fault latency。
- `UPDATE`、`INSERT`、`READMODIFYWRITE` 會改變 database file。
- operations CSV 由 harness 產生，run record 也由 harness 產生；`benchmark_harness_residency_by_page_type.csv` 則是後處理腳本產生。
- 多次 benchmark 的 operations CSV 和 run record 都會用唯一檔名保留，不會覆蓋先前紀錄。

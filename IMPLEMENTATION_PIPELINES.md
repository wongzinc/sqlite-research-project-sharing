# 實作 Pipeline 審查 — 跨文件一致性 + 策略實作 vs 定義

> **目的**：審查每個策略實際**怎麼跑出來的**，而不是文件**宣稱**怎麼跑。配合
> [CONTRADICTIONS.md](../CONTRADICTIONS.md)（資料矛盾彙整）使用——本檔處理
> **流程矛盾**的程式碼證據鏈。
>
> **使用方法**：先讀 §1 答案、§2 距 gold-standard 多遠、§3 同學重跑用哪個
> pipeline。其他章節是 evidence。

---

## §1. 結論先講

**目前 codebase 裡同時存在 4 條不同的 cold-start pipeline**，但所有文件都
（隱性地）假設只有一條。這就是 [CONTRADICTIONS.md #24] 的程式碼根因，也是
為什麼同一 cell 的絕對 µs 在不同表打架（#1, 6, 7, 9 那一票）。

| Pipeline | 用在哪 | Cache-clear 機制 | 殘留風險 |
|---|---|---|---|
| **P1**（多數）| `layout_rewriter` / `prefetch_access` / `prefetch_slru` / `prefetch_warmer` 各 `runs/runmatrix*.sh` | harness `--cold-advice dontneed` (MADV_COLD→PAGEOUT→DONTNEED) + `--drop-caches-script evict_helper.sh` → `evict` binary → **posix_fadvise(POSIX_FADV_DONTNEED)**（單檔，不需 sudo）| 名字叫 "drop-caches-script" 但實際是 fadvise；residency 驗證有時跑有時沒跑 |
| **P2** | `prefetch_churn/` 全部 Python orchestrator | `--benchmark-cold-advice none`（**跳過 harness MADV chain**）+ evict binary（posix_fadvise）+ `--no-run-residency-checker`（**verify 也關掉**） | 跟 P1 差兩個關鍵步驟，**生出的 baseline µs 系統性不同** |
| **P3**（歷史，可能仍在 CSV 裡）| 早期 prefetch_vacuum（已棄用但 CSV 沒重跑）| `sync && echo 3 > /proc/sys/vm/drop_caches`（**真 system-wide drop，需 root**）| `strategies_explained.md:57` 自承「早期用這套」、「絕對 µs 不能跨表比」——舊數字仍在 `overall_results.md` |
| **P0**（**推薦新標準**，2026-06-19 起才可能）| 尚未使用 | harness MADV chain + **`/usr/local/sbin/drop-caches`**（setuid wrapper，全機 drop，u03 可跑）+ `residency_checker` 強制驗證 0% | — |

**Gold standard 缺什麼**：P0 還沒被任何 batch 用過。重跑必須採 P0。

---

## §2. Pipeline 之間距 gold-standard 多遠

| 維度 | P1 標準 | P2 churn | P3 歷史 | **P0 推薦** |
|---|---|---|---|---|
| 1. harness MADV chain | ✅ `dontneed` | ❌ `none`（**跳過**）| ❌（直接 system drop）| ✅ `dontneed` |
| 2. 全機 page cache drop | ❌ 只 per-file fadvise | ❌ 只 per-file fadvise | ✅ `echo 3 > drop_caches` | ✅ `/usr/local/sbin/drop-caches` |
| 3. Residency verify (mincore == 0) | ⚠️ 有 binary 但不一定跑 | ❌ `--no-run-residency-checker` | ❌（沒驗）| ✅ 強制 |
| 4. 跨 sub-project 可比性 | ⚠️（同 P1 內部 OK，跨 P1/P2 不可比）| ⚠️（同上）| ❌（跟 P1/P2 完全不可比）| ✅ |
| 5. u03 可跑 | ✅ | ✅ | ❌（u03 沒 sudo）| ✅（**2026-06-19 後**）|

**距 P0 差距總結**：P1 缺「全機 drop + 強制 verify」；P2 缺「MADV chain + 全機 drop + 強制 verify」；P3 缺「MADV chain + verify」且 u03 跑不了。

---

## §3. 重跑用 P0 — 完整配方

> 給同學跑 master rerun 直接 copy 用。Headline cell（Abstract / §1 引用）建議 5 reps；
> 其餘可 3 reps。

```bash
benchmark_harness \
  --db <test_xxx.db> \
  --workload <workload_xxx.txt> \
  --output <out.csv> \
  --record-dir <records_dir> \
  --cold-advice dontneed \                           # ① 自家 mmap MADV chain
  --drop-caches-script /usr/local/sbin/drop-caches \ # ② 全機 drop（取代舊 evict）
  --post-cold-script <strategy_prefetch.sh>          # ③ 策略本身的 prefetch
# 跑完後額外驗證：
residency_checker --db <test_xxx.db> --threshold 0  # ④ 強制 0% resident or abort
```

關鍵差別 vs 現行 P1：第 ② 步把 `evict_helper.sh` 換成 `/usr/local/sbin/drop-caches`。
P2 churn 還要把 `--benchmark-cold-advice none` → `dontneed`、`--no-run-residency-checker` → `--run-residency-checker`。

**禮貌警告**：全機 drop 會把同學的 page cache 也沖掉。Master batch 要**夜間集中跑** + 群組公告。

---

## §4. 策略實作 — 一覽

### §4.1 結構派（用 `classify_*.csv` 找 interior pages）

| Strategy | Binary | 機制 | Args | 出處 |
|---|---|---|---|---|
| **2a range** | `prefetch_vacuum/src/prefetch` | madvise(MADV_WILLNEED) per contiguous range | `<db> <classify.csv> range` | [prefetch.c:131-139](prefetch_vacuum/src/prefetch.c) |
| **2b perpage** | `prefetch_vacuum/src/prefetch` | madvise(MADV_WILLNEED) **per individual page** | `<db> <classify.csv> perpage` | [prefetch.c:111](prefetch_vacuum/src/prefetch.c) |
| **2c layers_N** | `prefetch_vacuum/src/prefetch_layers` | madvise(MADV_WILLNEED) on first N interior pages by file offset | `<db> <classify.csv> N <page_size>` | [prefetch_layers.c](prefetch_vacuum/src/prefetch_layers.c) |

→ 三者**共用同一 OS primitive**（`madvise(MADV_WILLNEED)`），差別只在「對哪些 page、怎麼分段」。

### §4.2 歷史派（用 `hotpages_*.csv` 找曾被讀過的 page）

| Strategy | Binary | 機制 | Args | 出處 |
|---|---|---|---|---|
| **2d access** | `prefetch_access/src/prefetch_access` | mincore 找 resident + madvise(MADV_WILLNEED) | `<db> <classify> <hotpages> <K_leaf> <ratio> <page_size>` | [prefetch_access.c](prefetch_access/src/prefetch_access.c) |
| **2e access+K leaves** | 同上 | 同上，但允許 K > 0 個熱門 leaf | 同上，K = 10 / 50 etc. | 同上 |
| **3a/3b ratio variants** | 同上 | 同上，不同 interior:leaf 比例 | 同上，調 ratio | 同上 |
| **2f SLRU** | `prefetch_slru/src/prefetch_slru` | madvise(MADV_WILLNEED) on all pages in hotpages.csv | `<db> <hotpages> <page_size>` | [prefetch_slru.c](prefetch_slru/src/prefetch_slru.c) |

→ 全部共用 `madvise(MADV_WILLNEED)`，差別在「拿哪份 hotset 餵進去」。

### §4.3 異類：prefetch_warmer

| 變體 | Binary | 機制 | 跟其他 prefetch 不同 |
|---|---|---|---|
| **warmer (pread mode, default)** | `prefetch_warmer/src/warmer.c` | **`pread()` 阻塞讀**進 scratch buffer | 不是 madvise hint！是強制把 page 拉進 OS page cache |
| **warmer (fadvise mode)** | 同 binary, `WARM_METHOD=fadvise` | `posix_fadvise(POSIX_FADV_WILLNEED)` | 同其他 prefetch 系列 |

**警告**：pread 與 fadvise 的「prefetch 保證等級」不同：
- `pread` = synchronously block 直到 page 進記憶體（**100% 保證**）
- `madvise(MADV_WILLNEED)` / `posix_fadvise(POSIX_FADV_WILLNEED)` = async hint（**不保證**，可能來不及）

這直接連到 [CONTRADICTIONS.md #17]：「MADV_WILLNEED 到底會不會 load」的爭論——
答案是 **kernel 不保證**，warmer 用 pread 才是真保證。其他策略都活在「希望 kernel
有時間 load 完」的不確定性裡。

---

## §5. 策略實作 vs 文件定義的 mismatch

| # | 文件宣稱 | 程式碼實作 | 落差 |
|---|---|---|---|
| **M1** | `--drop-caches-script` 名字暗示「drop OS caches」 | 實際呼叫的 helper script 是 `evict` binary → posix_fadvise（per-file）| ❌ 命名誤導，不是真正的 drop_caches |
| **M2** | `strategies_explained.md:39` 說「製造冷啟動」步驟 = MADV chain + cold helper | prefetch_churn 用 `--benchmark-cold-advice none` 跳過 MADV chain | ❌ prefetch_churn 偏離 doc 宣稱的 protocol |
| **M3** | `strategies_explained.md:5` 七策略「共用同一套引擎」 | warmer.c 用 pread（不是 madvise），跟其他六策略**不同保證等級** | ⚠️ 是「同一個 harness 呼叫」但 prefetch 機制其實異質 |
| **M4** | `strategies_explained.md:57` 親口承認「早期 prefetch_vacuum 用 sudo drop_caches」「絕對 µs 不能跨表比」 | `overall_results.md` 與 `REPORT.md` 仍把不同 pipeline 的 µs 數字混在一張表裡 | 🔴 文件自承不可比，但仍然在比 → [CONTRADICTIONS.md #24] |
| **M5** | `--drop-caches-use-sudo` flag 暗示「會用 sudo」 | u03 沒 sudo，所有 production scripts 都用 `--no-drop-caches-use-sudo`；唯一用 sudo 的 `prefetch_churn/drop_caches.sh` 從未在 u03 上執行 | ⚠️ flag 存在但實務上**從未被啟用過**，整個 sudo 路徑死碼 |
| **M6** | residency_checker 存在於 4 個位置：`./residency_checker`、`prefetch_churn/residency_checker`、`residency_checker/residency_checker.c`、`prefetch_slru/runs/residency_checker` | prefetch_churn 用 `--no-run-residency-checker` 主動關掉 | ⚠️ 驗證 infrastructure 有，但**使用率不一致** |
| **M7** | 文件說「7 個策略」（`strategies_explained.md:9`）| 實際算下來 binary 有 5 個（prefetch、prefetch_layers、prefetch_access、prefetch_slru、warmer），策略變體 ≥ 8（含 3a/3b ratio）| ⚠️ count 對不上但屬於 [CONTRADICTIONS.md R3] 已調和項 |
| **M8** | `WORKLOAD_FILE_REFERENCE.md:51,145` 命令簽章 `prefetch_layers <db> <classify> 92 4096 range` | 實際 `prefetch_layers.c:32-35` 只吃 4 個 arg（`db classify N page_size`，沒有 `range` 字串）| 🔴 文件命令簽章錯誤 — [CONTRADICTIONS.md #26] |

---

## §6. (Workload × Strategy × Layout) → Pipeline 對照

> 從 `runmatrix*.sh` 的覆蓋範圍倒推。每 cell 列「Pipeline / Orchestrator」。

### Layout sweep（1a orig / 1b vacuum / 1c type-aware × A/B/C）

| Cell | Pipeline | Orchestrator |
|---|---|---|
| {A,B,C} × {orig,vacuum,ta} × {range, layers_N} | **P1** | `layout_rewriter/runs/runmatrix_Nsweep_FULL.sh` etc. |
| Workload Z（low-key zipfian）× layers_N | **P1** | `layout_rewriter/runs/runmatrix_Nsweep_zlowkey.sh` |

### Access pattern（2d / 2e / 3a / 3b）

| Cell | Pipeline | Orchestrator |
|---|---|---|
| A × 2d/2e × orig | **P1** | `prefetch_access/runs/runmatrix_2d.sh`, `runmatrix_2e.sh` |
| {A,B,C} × 2e × {orig,vacuum,ta} | **P1** | `prefetch_access/runs/runmatrix_2e_abc.sh` |
| 3a/3b ratio sweep | **P1** | `prefetch_access/runs/runmatrix_2e_ratio.sh` |
| RAM-pressure 2d | **P1** + cgroup | `prefetch_access/runs/runmatrix_ram_pressure*.sh` |

### SLRU（2f）

| Cell | Pipeline | Orchestrator |
|---|---|---|
| {A,B,C} × 2f × {orig,vacuum,ta} | **P1** | `prefetch_slru/runs/runmatrix*.sh` |

### Churn evolution（§6.2.1）

| Cell | Pipeline | Orchestrator |
|---|---|---|
| A × {access, layers_N} × churn | **P2** | `prefetch_churn/runs_access_churn_a/`, `runs_nsweep_a/` |
| B × {access, layers_N} × churn | **P2** | `runs_access_churn_b/`, `runs_nsweep_b/` |
| C × {access, layers_N} × churn | **P2** | `runs_access_churn/`, `runs_nsweep_full_c/` |
| Page-split churn variants | **P2** | `prefetch_churn/runs_page_split/` |

### Multi-process MAP_SHARED（§6.2.3）

| Cell | Pipeline | Orchestrator |
|---|---|---|
| 三 process cadence | **變體（Python）** | `multiprocess/runs_prefetch_cadence/cadence_experiment.py` |

### Warmer ablation（live hotset）

| Cell | Pipeline | Orchestrator |
|---|---|---|
| {A,B} × warmer levels | **P1**（但 prefetch 機制是 pread 不是 madvise）| `prefetch_warmer/runs/run_ablation.sh` |

---

## §7. 統計：到底有幾種 pipeline 在跑？

把所有 cell 的「(MADV chain 是否啟用) × (cache-clear 機制) × (residency verify 是否啟用) × (prefetch 機制)」攤開：

| Pipeline ID | MADV chain | Cache-clear helper | Residency verify | Prefetch 機制 | Sub-project |
|---|---|---|---|---|---|
| **P1a** | dontneed | evict (fadvise) | optional | madvise(WILLNEED) | layout_rewriter, prefetch_access, prefetch_slru |
| **P1b** | dontneed | evict (fadvise) | optional | **pread** | prefetch_warmer |
| **P2** | **none** | evict (fadvise) | **disabled** | madvise(WILLNEED) | prefetch_churn |
| **P3** | (history) | sudo drop_caches | unknown | (depends) | early prefetch_vacuum (data 仍在 CSV) |
| **multiprocess** | varies | varies | varies | varies | multiprocess/ |

→ **至少 4 條 distinct pipeline 並存**（5 條算上 multiprocess）。
→ `REPORT.md` §5/§6 的數字混了 P1a + P1b + P2 + P3 但沒在表格 caption 標 mechanism。

---

## §8. 給重跑的具體 action items

### 必修（不修就解不掉 [CONTRADICTIONS.md] 的硬矛盾根因）

1. **統一所有 sub-project 用 P0**：harness MADV chain + `/usr/local/sbin/drop-caches` + residency_checker
2. **prefetch_churn 的 Python orchestrator** 要把 `--no-drop-caches-use-sudo` 改成直接呼叫 `/usr/local/sbin/drop-caches`（不再需要 sudo 邏輯）+ 把 `--benchmark-cold-advice none` 改回 `dontneed` + 啟用 `--run-residency-checker`
3. **prefetch_warmer 的 pread 模式**：保留作為「保證載入」的 baseline，但**在 paper 裡明確標示** vs 其他 madvise 策略不同類別
4. **棄用 P3 的舊 CSV**：`overall_results.md` 裡早期 prefetch_vacuum 的數字標示 `[deprecated — pre-2026-06 P3 pipeline]` 或直接重跑取代

### 應改（提升 paper rigor）

5. **文件命名修正**：把 `--drop-caches-script` 改名（在 P0 之後可以叫 `--cache-clear-script`），或在文件明示「**name is historical, mechanism is whatever the script does**」
6. **每張表 caption 標 pipeline ID**：禁止跨 pipeline cell 同表並列；若必須並列，加 caveat
7. **`WORKLOAD_FILE_REFERENCE.md` 命令簽章修正**：把 `prefetch_layers <db> <classify> 92 4096 range` 改成正確的 4-arg 版本

### 加分（perf 開通後）

8. **每 cell 額外記 perf page-fault count**（待 `perf_event_paranoid` 修正後）—— 解 [CONTRADICTIONS.md #17/18/20] 的理論敘事矛盾
9. **residency_checker 升級**：除了 `mincore == 0`，加 `total_majflt` snapshot before/after，作為 cold-start 嚴格性的硬證據

---

## §9. 引用

- `benchmark_harness/benchmark_harness.c` — 主 harness（行 39-41 cold_advice_t enum、行 138-144 flag 說明、行 738-753 MADV chain 實作）
- `layout_rewriter/runs/evict.c` — 「drop-caches」helper 實際就是 posix_fadvise（行 12）
- `strategies_explained.md` — 行 5 / 22 / 39 / 49-57 自承多機制並存
- `prefetch_churn/sqlite_prefetch_churn_experiment.py` — 行 455-463、870-877、1260-1267 prefetch_churn 偏離 P1 的證據
- `prefetch_warmer/src/warmer.c` — 行 46-70 pread vs fadvise 切換
- `prefetch_vacuum/src/prefetch.c` — 行 41-43、111、131-139 range/perpage madvise
- `prefetch_vacuum/src/prefetch_layers.c` — 行 23-35 4-arg 簽章（非文件宣稱的 5-arg）
- `prefetch_access/src/prefetch_access.c` — mincore + madvise(WILLNEED)
- `prefetch_slru/src/prefetch_slru.c` — madvise(WILLNEED) on hotpages
- [CONTRADICTIONS.md](../CONTRADICTIONS.md) #17, #18, #20, #24, #26 — 對應的資料矛盾條目

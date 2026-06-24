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
| **P0**（**推薦新標準**）| 尚未使用 | harness MADV chain + **`/usr/local/sbin/drop-caches`**（setuid wrapper，全機 drop，u03 可跑）+ **兩道 mincore 驗證**：cold ①（prefetch 前 ≈0%）+ delivery ②（prefetch 後，pread arm 強制 ≥95%，見 §3） | — |

**Gold standard 缺什麼**：P0 還沒被任何 batch 用過。重跑必須採 P0。

---

## §2. Pipeline 之間距 gold-standard 多遠

| 維度 | P1 標準 | P2 churn | P3 歷史 | **P0 推薦** |
|---|---|---|---|---|
| 1. harness MADV chain | ✅ `dontneed` | ❌ `none`（**跳過**）| ❌（直接 system drop）| ✅ `dontneed` |
| 2. 全機 page cache drop | ❌ 只 per-file fadvise | ❌ 只 per-file fadvise | ✅ `echo 3 > drop_caches` | ✅ `/usr/local/sbin/drop-caches` |
| 3. Residency verify (mincore) | ⚠️ 有 binary 但不一定跑 | ❌ `--no-run-residency-checker` | ❌（沒驗） | ✅ 強制兩道：cold ① + delivery ② |
| 4. 跨 sub-project 可比性 | ⚠️（同 P1 內部 OK，跨 P1/P2 不可比）| ⚠️（同上）| ❌（跟 P1/P2 完全不可比）| ✅ |
| 5. u03 可跑 | ✅ | ✅ | ❌（u03 沒 sudo）| ✅|

**距 P0 差距總結**：P1 缺「全機 drop + 強制 verify」；P2 缺「MADV chain + 全機 drop + 強制 verify」；P3 缺「MADV chain + verify」且 u03 跑不了。

---

## §3. 重跑用 P0 — 完整配方

> **這是鎖定版定義（locked spec）。** 為了「一次定死、不再回頭改」，下面把每個會
> 影響絕對 µs 或可複現性的旋鈕都釘死。master rerun 全部照此跑。

### §3.0 P0 一句話 + 凍結清單

> **P0 = `p0_env.sh`（釘環境 + 記錄）→ harness（SQLite 凍結設定 + 全機 drop + 內建
> ①cold/②delivery mincore）→ op[0] 為 read 的 first-query → 每 cell 跑兩臂：pread = 可
> 複現上界、async = 實務對照（附 delivery%）→ pread 少 reps、async 10 reps、丟首 rep、
> rep-major、報 median+p95。**

**凍結清單（改任一項都要全矩陣重跑，所以鎖死）：**

| # | 項目 | 鎖定值 | 為什麼 |
|---|---|---|---|
| F1 | SQLite pager cache | `PRAGMA cache_size=0` | 不讓 SQLite 在 heap 偷存頁、繞過冷啟動（已寫死 [`:1068`](benchmark_harness/benchmark_harness.c#L1068)）|
| F2 | SQLite 讀取路徑 | `PRAGMA mmap_size=檔案大小` | 讀走 mmap → OS page cache → drop-caches 管得到、prefetch 暖同一份（已寫死 [`:1065`](benchmark_harness/benchmark_harness.c#L1065)）|
| F3 | 冷啟動清快取 | `/usr/local/sbin/drop-caches` = `sync; echo 3 > /proc/sys/vm/drop_caches`（全機，pagecache+dentry+inode）| 全機 drop 才是真冷；echo 3 一併清 dentry/inode |
| F4 | CPU governor | `performance`（關 turbo 變頻）；**u03 例外見下** | 冷啟動 µs 對 CPU 頻率敏感 |
| F5 | **`read_ahead_kb`** | **128（裝置預設）固定值,逐 run 記錄,不掃描** | **直接決定一次 fault/madvise 順帶載幾頁**——range 封頂、U 型、delivery% 全跟它糾纏（見 §3.7）|
| F6 | THP | `madvise`（或固定 `never`，記錄）| huge page 改變 fault 粒度 |
| F7 | hotset 輸入 | 每份 hotset.csv checksum 凍結 + 記錄產生方式；**2d/2e/2f 用 P0 重產見下** | hotset 是輸入；換一份結果就漂移 |
| F8 | 量測 workload | op[0] 必須是 `read`（A/B/C/Z 合格；D 只當 churn 產生器、不量 TTFQ）| first-query 定義 |

### §3.1 環境：`p0_env.sh`（每個 batch 前跑一次，並把值寫進 run record）

```sh
#!/bin/sh
# 釘住並記錄所有影響冷啟動 µs 的環境旋鈕。需 root / setuid 包裝。
DEV=$(df --output=source /home/u03 | tail -1 | sed 's#/dev/##; s/[0-9]*$//')   # DB 所在 block device
echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor >/dev/null
echo ${RA_KB:-128} > /sys/block/$DEV/queue/read_ahead_kb        # F5 主值 128
echo madvise > /sys/kernel/mm/transparent_hugepage/enabled
# ── 記錄（這串會被 runner 抓進每筆 run record，環境一漂移就看得出來）──
echo "env: kernel=$(uname -r) dev=$DEV ra_kb=$(cat /sys/block/$DEV/queue/read_ahead_kb)" \
     "gov=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)" \
     "thp=$(cat /sys/kernel/mm/transparent_hugepage/enabled)" \
     "loadavg=$(cut -d' ' -f1 /proc/loadavg) memfree_kb=$(awk '/MemAvailable/{print $2}' /proc/meminfo)"
```

> 沒記錄 = 之後任何 variance 都無法解釋 = 被迫重跑。`read_ahead_kb` 尤其關鍵——這很可能就是
> 舊 P3 有 U 型、P1 變 plateau 的元兇之一。

> **F4 在 u03 (meow1) 的落地（無 root）**：實機 u03 沒有 sudo，governor 寫不了,但**不需要**。
> 這台是 **`amd-pstate-epp`** 驅動,真正釘頻率的是 **EPP**（`energy_performance_preference`）而非
> governor 標籤——實測 EPP=`performance`、`boost=1`、負載核心 ~5.7 GHz（上限 5.76）。F4「powersave
> 會鎖低頻」是舊 acpi-cpufreq 語意,不適用。因此 `p0_env.sh` 改成**記錄真實證據**:`P0_ENV` 行已
> 加 `driver= epp= boost= maxfreq_khz=`,讓 artifact 自證「跑在 performance 頻率策略」即使 governor
> 顯示 powersave。實機冷清快取走 setuid `/usr/local/sbin/drop-caches`（免 sudo）。
> `read_ahead_kb` 一律固定 128(裝置預設)並逐 run 記錄,不掃描其他值。

### §3.2 harness 呼叫（SQLite 設定 F1/F2 已寫死在 code）

```bash
benchmark_harness \
  --db <test_xxx.db> --workload <workload_xxx.txt> \
  --output <out.csv> --record-dir <records_dir> \
  --cold-advice dontneed \
  --drop-caches-script /usr/local/sbin/drop-caches \
  --post-cold-script <deliver.sh> \
  --verify-hotset <hotset_xxx.csv>          # ★ 新增 flag，見 §3.4
```

順序固定 `cold-advice → drop-caches → post-cold-script → (★內建 mincore) → first query`
（[`:1405-1440`](benchmark_harness/benchmark_harness.c#L1405)），prefetch 一定在 evict 後 / query 前，不會被清掉。

### §3.3 兩臂設計：每個 cell 都跑 pread + async

把每個策略**分解成「hotset 選擇」×「交付方式」**——策略只決定**載哪些頁**（hotset），
交付方式正交：

| 臂 | 怎麼跑 | 角色 | 報什麼 |
|---|---|---|---|
| **pread**（oracle）| `WARM_METHOD=pread warmer <db> <hotset> 4096` | **可複現上界**：hotset 選對且 100% 載入時的最佳 fq。**非部署**（同步阻塞，preproc ~ms）| 只報 `fq_pread`，標 `oracle, 不可直接部署` |
| **async**（實務）| `WARM_METHOD=fadvise warmer …`（與既有 madvise 同 hint 語意）| 真實可部署機制 | `fq_async` + `delivery_pct` + `preproc_async` + `e2e_async` |

- **統一用 `warmer` 當交付引擎**（pread/fadvise 只差同步/非同步），native `prefetch_layers/access/slru`
  **降級為 hotset 產生器**（離線跑、吐 hotset.csv）。好處：pread 與 async **只差在 sync/async**，
  其他全相同 → 兩臂之差 `fq_async − fq_pread` 乾淨等於「async 的 delivery 代價」（直接回答矛盾 #17）。
- **pread 永不進「該部署哪個策略」的比較表**（它端到端 ~ms，不是策略）；策略間比較一律用 `e2e_async`。

### §3.4 residency 驗證：★ 內建進 harness（修掉「驗證污染量測」）

新增 harness flag `--verify-hotset <hotset.csv>`：harness 用既有的 `fill_mincore_vec`
（[`:522`](benchmark_harness/benchmark_harness.c#L522)）在**兩個內部時點各做一次快速 mincore**（~µs）：

1. drop-caches 之後、post-cold-script 之前 → `cold_pct`（應 ≈0，>1% 該 run 作廢）
2. post-cold-script 之後、**op[0] 之前** → `delivery_pct`，寫進 run record

> **為什麼一定要內建、不能用外掛 `residency_checker`+python**：外掛在 prefetch 與 op[0] 間多跑
> ~100ms，這段時間 async readahead 會多載 → **fq_async 被灌水變快、不可複現**。harness 內建 mincore
> 只加 µs 級延遲，async 來不及多載，污染消失。pread 臂不受影響（早已 100%），所以在 `--verify-hotset`
> 上線前，**pread 臂可先跑**（它免疫此問題）。
>
> `hotset_residency.py`（repo 根目錄）退居離線/手動檢查用；自動辨識 hotset 格式
> （有 `is_resident` 欄 → 只算 `==1`；有 `file_offset` 欄 → 全部頁）。

### §3.5 reps / 聚合 / 交錯

- **reps**：pread 臂 **5**（丟 warmup 後 n=4，p95 才有意義）；async 臂 **10**（壓 delivery 變異）；baseline 臂 **10**；**全部丟掉第 1 rep**（首跑有額外 code-path 冷成本）。summary 對 n<4 的組不報 p95。
- **交錯**：**rep-major**——全 cell 跑完 rep1 再 rep2…，把機器慢漂移攤平到所有 cell，而非集中某幾個。
- **聚合**：報 **median + p95 + min + stdev**（冷啟動長尾，只報 median 會騙人）。

### §3.6 輸出欄位（實際 CSV schema，`arm` 是 row 維度而非欄）

`raw_p0.csv`（每 (workload,db,strategy,**arm**,rep) 一列；`arm ∈ {pread, async, baseline}`）：
```
workload, db, strategy, arm, ra_kb, rep, warmup,
  cold_pct,        # ① drop 後、prefetch 前殘留（應 ≈0；>1% 由彙整剔除）
  delivery_pct,    # ② prefetch 後、首查前命中率（baseline = readahead 單獨交付了幾成）
  first_query_us,  # TTFQ
  preproc_us,      # = warmer_us（baseline=0；layers/2d/2e ≈ µs；2f ≈ 7.5ms）
  e2e_us,          # = preproc_us + first_query_us
  avg_us, majflt, minflt, load, memavail_kb
```
`summary_p0.csv`（每 (workload,db,strategy,arm) 一列，丟 warmup、cold_pct>1% 剔除後彙整）：
```
workload, db, strategy, arm, n, ra_kb,
  fq_median, fq_p95, fq_min, fq_stdev,   # p95 在 n<4 時留空
  delivery_pct_median, preproc_us_median, e2e_median, cold_pct_max
```

Headline 三句（從 arm 維度導出）：①「可達上界(oracle) = `pread` 臂的 `fq_median`」②「實務最佳 = `async` 臂的 `e2e_median`（layers_5 贏、SLRU 因 7.5ms preproc 出局）」③「`fq_async − fq_pread` = async 作為 hint 的 delivery 代價」；改善% = (baseline − strategy) / baseline。

### §3.7 `read_ahead_kb`（固定 128，逐 run 記錄）

`read_ahead_kb` 跟結論有因果糾纏（range 封頂 = `2×ra_pages`；冷 fault 順帶 readahead = kernel 免費 prefetch）。
本研究一律 **釘在 128（裝置預設）並逐 run 記錄**,所有結論均在 ra=128 下成立,不掃描其他值。

**關鍵差別 vs 現行 P1**：(1) `evict` → 全機 `/usr/local/sbin/drop-caches`；(2) `--verify-hotset` 內建兩道
mincore；(3) 環境釘死+記錄（尤其 `read_ahead_kb`）；(4) 每 cell 雙臂 pread/async。P2 churn 另需把
`--benchmark-cold-advice none` → `dontneed`、`--no-run-residency-checker` → 改用 `--verify-hotset`。

**P0 工具（已實作）**：(a) harness `--verify-hotset`（[`benchmark_harness.c`](benchmark_harness/benchmark_harness.c)
`load_hotset_pages` / `verify_hotset_residency`，emit `verify_cold_pct` / `verify_delivery_pct`）；
(b) [`p0_env.sh`](p0_env.sh)（pin + 記錄環境，印 `P0_ENV` 行）；(c) 通用 runner [`run_p0.py`](run_p0.py)
（雙臂 pread/async、統一欄位、rep-major、`--dry-run`/`--list`）。三者皆在 u03 Linux 上跑（harness 用
mmap/mincore/madvise）；`run_p0.py --dry-run` 可先在任何機器驗證矩陣與 hotset 頁數。

**F7 落地：P0-native hotset 重產 + 凍結**（`run_p0.py --regen-hotsets`）。2d/2e/2f 原本讀的殘留檔是
**舊 P1 warmup（`evict` = per-file fadvise）** 產的。`--regen-hotsets` 用 **P0 冷清（全機 drop-caches）**
重產唯一被污染的輸入——base 殘留 `prefetch_slru/runs/hotpages_{w}{suffix}.csv`（2f 直接讀、2d 經
symlink 讀,皆自動更新）；2e 再用新 base 重跑 [`gen_hotleaves.py`](prefetch_access/runs/gen_hotleaves.py)
（top-K leaf 由 workload 頻率算,deterministic）。流程:`drop-caches → harness（cold-advice none、
mmap full、不 prefetch）→ residency_checker snapshot → gen_hotleaves`。原檔備份到 `*.p1.bak`,完成後寫
checksum 凍結清單 `p0_runs/hotset_freeze.sha256`;master batch 前用 `run_p0.py --verify-frozen` 當閘門。
預設為 dry-run,需 `--yes` 才真正清快取/覆寫（每 (w,layout) 一次全機 drop,故同列「夜間 + 公告」）。

**rerun 前的嚴謹度強化（2026-06-22 審查後加入)**:
- **baseline(無 prefetch)臂**：每 (workload,layout) 一個 baseline cell(`warmer` 不啟動、無 post-cold-script),量純冷啟動首查 = improvement-% 的**分母**。沒它算不出「快了幾 %」(堵 CONTRADICTIONS #2/#8/#13/#15/#16)。`--no-baseline` 可關。
- **`cold_pct` 閘門**:`--cold-pct-max`(預設 1.0);`verify_cold_pct` 超標的 cell 視為冷清失敗,彙整時自動剔除(raw 仍保留)。把「>1% 作廢」從有文無碼變成真的執行。
- **F8 強制**:harness `--require-read-first` 確保 op[0]=read,否則 abort(first-query 才是乾淨 TTFQ)。
- **CPU 頻率暖機**:harness `--warm-cpu-ms`(預設 10)在計時前 busy-spin 把 taskset(`--cpu`)釘定的核心拉到滿頻,消除「最快 cell 受 amd-pstate freq ramp 懲罰最重」的偏差。
- **read-only open**:harness `--readonly`(只讀量測更乾淨、不取寫鎖)。
- **凍結擴充**:freeze manifest 除 2d/2e/2f 外,加入 `classify_*.csv` 與 workload `.txt`(它們 deterministic 地生成 layers_* 與 2e)。
- **統計**:pread oracle 臂 reps 3→5(丟 warmup 後 n=4,p95 才有意義);summary 對 n<4 的組不報 p95。每 rep 另記 `loadavg/memavail`(共用機 noise canary)。

**環境定案**:`read_ahead_kb` 固定 128(裝置預設)、逐 run 記錄,不掃描;結論均在 ra=128 下成立。governor 用 EPP=performance 等效釘住(見 F4)。

**禮貌警告**:全機 drop 會把同學的 page cache 也沖掉。Master batch 要**夜間集中跑** + 群組公告。

### §3.8 P0 執行覆蓋紀錄（2026-06-23 審查更新）

**「P0 pipeline」嚴格定義 = `run_p0.py`**（+ 同進程包裝 [`run_p0_churn.py`](run_p0_churn.py)、[`run_p0_cadence.py`](run_p0_cadence.py),量測都呼叫 P0 harness:全機 `drop-caches` + `--verify-hotset`(cold/delivery)+ `--cpu`/`--warm-cpu-ms`/`--readonly`,`cold_pct`=0 為門檻)。`benchmark_harness/workloads` 的 A/B/C/Z 為範圍內;new_workloads **不在**範圍。
> **`static_experiment/`(`orchestrator.py` + `formal-experiment.json`)不是 P0 pipeline** —— 它是獨立的正式框架,用**另一支** harness(`static_experiment/tools/bin/benchmark_harness`,**沒有** `--verify-hotset`/`--readonly`/`--cpu`/`--warm-cpu-ms`、只 `--cold-advice none` + drop-caches),策略名(range_interior/offset_topk_interior/residency_topk)與 workload(read/scan_*)也不同。它目前只跑過 `smoke`/`smoke-scan` 子集、`formal-experiment.json` 未跑,且**其結果不進本研究的 P0 md**(刻意:非同一套 P0 紀律)。詳見 §3.9。

**A. 已用 P0 跑完的組合**(全 `cold_pct`=0)

| 批次 | workloads | layouts | strategies | reps/arms | 產物 | figures |
|---|---|---|---|---|---|---|
| Master matrix | A,B,C | orig,vacuum,ta | baseline, layers_5, layers_92, 2d, 2e_K10, 2e_K500, 2f_slru | pread5/async10/baseline10,雙臂 | [`p0_runs/`](p0_runs/summary_p0.csv) | 01,02,03,05,13,14 |
| Master matrix (**Z**) | **Z** | orig,vacuum,ta | 同上 6 策略 + baseline | pread5/async10/baseline10,雙臂 | [`p0_runs_z/`](p0_runs_z/summary_p0.csv) | (補洞;Z 主圖為 09) |
| layers_N sweep | A,B,C | orig | layers_{1,2,3,5,8,13,21,34,46,64,92}+baseline | pread1/async5 | [`p0_runs_nsweep/`](p0_runs_nsweep/summary_p0.csv) | 04 |
| 2e K-sweep | A,B,C | orig,vacuum,ta | 2d, 2e_K{10,40,50,92,100,500} | pread1/async5 | [`p0_runs_ksweep/`](p0_runs_ksweep/summary_p0.csv) | 10 |
| Dense N-sweep + **Z** | A,B,C,**Z** | orig,vacuum,ta | layers_{1..92}(14 個 N)+baseline | pread1/async3 | [`p0_runs_nsweep_dense/`](p0_runs_nsweep_dense/summary_p0.csv) | 09,11 |
| RAM-pressure 20M | A,B,C | orig,vacuum,ta | baseline,layers_5/92,2d,2e_K10/K500,2f_slru | pread1/async5,`--mem-limit 20M` | [`p0_runs_ram20m/`](p0_runs_ram20m/summary_p0.csv)(vs master=unlimited) | 06 |
| Churn-evolution | A,B,C | **orig** | baseline, 2e_K10-static, layers_92-static | 3 reps × 11 checkpoint | [`p0_runs_churn/churn_evolution.csv`](p0_runs_churn/churn_evolution.csv) | 07 |
| Churned N-sweep | A,B,C | **orig** | layers_{1..92}-static(最終 churned DB) | 3 reps | [`p0_runs_churn/churn_nsweep.csv`](p0_runs_churn/churn_nsweep.csv) | 12 |
| Cadence | A | orig | static hotset × cadence∈{1,5,30,never}s | P0 drop + gap + warmer 重暖 | [`p0_runs_cadence/cadence_results.csv`](p0_runs_cadence/cadence_results.csv) | 08 |

→ **14 / 14 figures 全部用 P0 資料重畫**(figure 對照見 [`figures/README.md`](figures/README.md) 頂部 banner)。

**B. P0 範圍內、尚未跑的細粒度組合**(誠實列出,非 batch 而是 cell 層級的洞)

- [x] **Workload Z × 完整 master matrix** —— **已補(2026-06-23)**:`run_p0.py --workloads Z --layouts orig,vacuum,ta` 跑了 {baseline,2d,2e_K10,2e_K500,2f_slru,layers_5/92} 雙臂 → [`p0_runs_z/summary_p0.csv`](p0_runs_z/summary_p0.csv)(39 rows,`cold_pct`=0;Z hotset 先以 `--regen-hotsets --no-freeze --workloads Z` 產出)。Z/orig:baseline 525、2f 119(−77%)、2e_K10 203,與 A 同型。
- [x] **Churn × vacuum/ta layout** —— **已補(2026-06-23)**:`run_p0_churn.py` 改成 `LAYOUTS=[orig,vacuum,ta]` 迴圈、CSV 加 `layout` 欄;churn-evolution / churned N-sweep 現涵蓋三 layout(figs 07/12 以 orig 為 headline)。→ `p0_runs_churn/`。
- [ ] **Churn × 其他策略 static** —— churn-evolution 只測 baseline / 2e_K10 / layers_92 的 static t=0 hotset;2d / 2f_slru static 未測。
- [ ] **read_ahead_kb {0,512} sweep** —— 需 root(u03 無),只跑了主值 128(F5);掃描留待有 root 環境。

> 上述 B 皆為「次要 / robustness / 需 root」的補洞,不影響主結論;主矩陣 + 五個 sweep/壓力/churn/cadence 維度的核心 cell 都已 P0。

**C. md 數據同步狀態(只允許 P0 結果)**

- ✅ `overall_results.md` 置頂「P0 master batch 結果」為權威表;舊 P1/P2/P3 維度表已加 **pre-P0** 標註(未刪除,僅標示取代)。
- ✅ `CONTRADICTIONS.md` #1–16 已逐條標 P0 解決狀態(12 ✅ / 4 🟠)。
- ✅ `REPORT.md` §5 + §3.4.1、`README.md`、`overall_strategies.md` 指向 P0 表。
- ⚠️ **待修(已知 data-sync 殘留)**:`figures/README.md` 的**表格 data-source 欄**仍寫舊 pre-P0 CSV(如 `matrix_ram_full_results.csv`、`runs_prefetch_cadence/…`),雖然頂部 banner 已宣告 P0、圖也確實是 P0 重畫 —— 表格欄位待改成對應的 `p0_runs*/`。
- ⏳ **完全收尾**:把 ✅ 條的舊 P1/P2/P3 表數字實際刪除/重算(目前 pre-P0 標註 + P0 表置頂),以及 🟠(#3/#4/#5/#12)的 prose 算術用 P0 數字重寫。

### §3.9 `static_experiment/` —— 獨立框架,**不算 P0 pipeline**

`static_experiment/`(`orchestrator.py`、`configs/*.json`、自有 `tools/bin/benchmark_harness`)是另一套較正式的 config 驅動實驗框架,**與本研究的 P0 pipeline 分離**:

| 面向 | 本研究 P0 (`run_p0.py`) | `static_experiment/` |
|---|---|---|
| harness | `benchmark_harness/`(含 `--verify-hotset`/`--readonly`/`--require-read-first`/`--cpu`/`--warm-cpu-ms`)| `static_experiment/tools/`(**皆無**;`--cold-advice none` + drop-caches)|
| 冷清驗證 | `cold_pct`/`delivery_pct` 兩道 mincore,>1% 剔除 | 無 in-harness 殘留驗證 |
| 策略名 | layers_N / 2d / 2e_K / 2f_slru | range_interior / offset_topk_interior / residency_topk |
| workload | A/B/C/Z | read/scan × uniform/zipf × full/window/tail |
| 跑況 | 見 §3.8 | 只跑過 `smoke`/`smoke-scan`;`formal-experiment.json` **未跑**(且其 `workloads.types` 含空字串 `""`、會 preflight fail)|
| 結果進 md? | 是(P0 為權威)| **否**——不混入 P0 結果 |

**結論**:`formal-experiment.json` 的大矩陣**不是 P0 的待跑項**,因為它走不同 harness/紀律。若日後要把它納入 P0,需先把 static harness 補上 P0 verify/hardening(與主 harness 對齊)。在那之前,它的數字不得進本研究 md(維持「只允許 P0 結果」)。

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

> **狀態（2026-06-19 第二輪更新）**：本輪 commit 又解掉**新 M1 + 新 M4**
> （prefetch_churn 兩條 P0 偏離）。表中剩 **3 條開放**（新 M2 / M3 / M5）。
> **解決後即從表移除**，footnote 用概念描述追蹤歷史，不靠 ID 號（因為
> 移除一條後其他都會位移，ID 不適合當長期 reference）。

| # | 文件宣稱 | 程式碼實作 | 落差 |
|---|---|---|---|
| **M2** | `strategies_explained.md:5` 七策略「共用同一套引擎」 | warmer.c 用 pread（不是 madvise），跟其他六策略**不同保證等級** | ⚠️ 是「同一個 harness 呼叫」但 prefetch 機制其實異質 |
| **M3** | `strategies_explained.md:57` 親口承認「早期 prefetch_vacuum 用 sudo drop_caches」「絕對 µs 不能跨表比」 | `overall_results.md` 與 `REPORT.md` 仍把不同 pipeline 的 µs 數字混在一張表裡 | 🔴 文件自承不可比，但仍然在比 → [CONTRADICTIONS.md #24] |
| **M5** | 文件說「7 個策略」（`strategies_explained.md:9`）| 實際算下來 binary 有 5 個（prefetch、prefetch_layers、prefetch_access、prefetch_slru、warmer），策略變體 ≥ 8（含 3a/3b ratio）| ⚠️ count 對不上但屬於 [CONTRADICTIONS.md R3] 已調和項 |

**已解決條目**（按解決時間倒序）：

**2026-06-19（第二輪，本 commit）**：

- ~~**prefetch_churn 跳過 harness MADV chain**~~ → Python orchestrator `--benchmark-cold-advice` default 從 `"none"` 改為 `"dontneed"`；10 個 prefetch_churn shell orchestrators 把 `--benchmark-cold-advice none` 覆寫拿掉。現在 prefetch_churn 跑出來符合 P0 第①層。
- ~~**residency_checker 「4 個位置」+ prefetch_churn 主動關掉**~~ → 兩部分：(a)「4 個位置」原描述**事實錯誤**，實際是 **1 source（`residency_checker/residency_checker.c`）+ 1 binary（`residency_checker/residency_checker`）+ 2 symlinks（`prefetch_churn/`、`prefetch_slru/runs/` 各一個指回去）**，md5 全部相同，**從來沒有分歧**；audit 原本把 directory 名跟 binary 路徑混為一談。(b) 真正的問題是 prefetch_churn 用 `--no-run-residency-checker` 主動關掉 verify——10 個 shell orchestrators 的該覆寫已拿掉、Python default `--run-residency-checker` 仍是 `True`，現在 prefetch_churn 跑會做 P0 第④層 verify。

**2026-06-19（第一輪，commit `691bd6b`）**：

- ~~**`--drop-caches-script` 命名誤導**~~ → helper scripts 已全部改成 `exec /usr/local/sbin/drop-caches`，現在實際上就是 system-wide drop
- ~~**`--drop-caches-use-sudo` 死碼**~~ → flag 已從 harness C、Python orchestrator、所有 shell scripts 移除
- ~~**`prefetch_layers` 5-arg 命令簽章錯誤**~~ → `WORKLOAD_FILE_REFERENCE.md` §1.4 / §3 已更正成 `prefetch` (3-arg) vs `prefetch_layers` (4-arg) 兩 binary 分開

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

- `benchmark_harness/benchmark_harness.c` — 主 harness（行 36-41 cold_advice_t enum、行 136-144 flag 說明、行 816-867 MADV chain 實作 `run_madvise_step`/`apply_cold_advice`）
- `layout_rewriter/runs/evict.c` — 「drop-caches」helper 實際就是 posix_fadvise（行 12）
- `strategies_explained.md` — 行 5 / 22 / 39 / 49-57 自承多機制並存
- `prefetch_churn/sqlite_prefetch_churn_experiment.py` — 行 455-463、870-877、1260-1267 prefetch_churn 偏離 P1 的證據
- `prefetch_warmer/src/warmer.c` — 行 46-70 pread vs fadvise 切換
- `prefetch_vacuum/src/prefetch.c` — 行 41-43、111、131-139 range/perpage madvise
- `prefetch_vacuum/src/prefetch_layers.c` — 行 23-35 4-arg 簽章（非文件宣稱的 5-arg）
- `prefetch_access/src/prefetch_access.c` — mincore + madvise(WILLNEED)
- `prefetch_slru/src/prefetch_slru.c` — madvise(WILLNEED) on hotpages
- [CONTRADICTIONS.md](../CONTRADICTIONS.md) #17, #18, #20, #24, #26 — 對應的資料矛盾條目

# Overall Results — 策略 × Workload 結果矩陣

對照 [overall_workloads.md](overall_workloads.md) 裡定義的四個 workload。本檔
列出**每個策略對每個 workload 的結果**——策略 × workload 矩陣已跑完整。

> **主表**只列原始 prefetch_vacuum 時期跑過的 Workload A + Workload C。Workload
> B 的全策略結果見[第五維](#第五維--策略-4-2f-slru)（2f SLRU）、
> [第六維](#第六維--策略-1b-sqlite-vacuum--workload-b--c)（1b VACUUM）、
> [第七維](#第七維--策略-1c-type-aware-layout--workload-b--c)（1c type-aware）、
> [第八維](#第八維--2c-layers_n-sweep--workload-b--c原始-layout)（N sweep）、
> [第九維](#第九維--layout-1b-vacuum-補測n-sweep--2f-slru--abc)（vacuum × N sweep + 2f）、
> [第十維](#第十維--n-sweep--workload-c--churned-db補齊-prefetch_churn-缺口)（churned DB × N sweep）、
> [第十一維](#第十一維--2f-slru--layout-1c-type-aware)（2f SLRU × type-aware layout）、
> [第十二維](#第十二維--n-sweep--layout-1c-type-aware--abc)（type-aware layout × N sweep — 完成跨三 layout 矩陣）、
> [第十三維](#第十三維--zipfian-low-key-hotspot-variantworkload-z--n-sweep--3-layouts)（Zipfian low-key hotspot variant，新增 Workload Z）、
> [第十四維](#第十四維--2d-access-pattern-prefetch-interior-only--abc--3-layouts)（2d access-pattern prefetch，C × 4 syscalls -47.6%）、
> [第十五維](#第十五維--2e-access-pattern-prefetch-interior--top-k-leaves--abc--3-layouts--kk10k50k100k500)（2e access-pattern + top-K leaves，C 上 2e_K10 全 layout -82~84%）、
> [第十六維](#第十六維--ram-pressure-對照cgroup-memorymax20-mb--workload-a--1a--base-2d-2e_k500-2f_slru)（RAM-pressure 20M cgroup 對照，2f avg_us 退化 17%）、
> [第十七維](#第十七維--策略-3a--3bratio-based-access-pattern-prefetchk40--k92--abc--3-layouts)（**3a / 3b ratio**：K=40 / K=92 補跑，A×1c×K=92 出現 410 µs hump）、
> [第十八維](#第十八維--churn-擴充abc--churn--2c-layers_n--2d--2e_kab--churn--statictk0-hotpages)（**A/B churn 擴充**：A × delete-churn × 2d/2e_K + A/B × N sweep × churn + B × churn × 2d/2e_K — static t=0 hotpages 在 A/B/C 三 workload 都不 decay；B 上 access-pattern 跟 file-offset 打平（無自然熱葉，~-49% 天花板））。
> Workload D 是 churn generator，沒有自己的 latency 結果。
>
> **2c dense N=0..92 sweep 補測**（~5,580 額外 benchmark）：證實 sparse 6-pt
> 在 9/12 cells 結論正確；漏掉的 sweet spot（**A×1b N=62、B×1c N=26、C×1b N=87**）
> 寫在 [overall_strategies.md](overall_strategies.md) 2c bullet 跟
> [overall_workloads.md](overall_workloads.md) 已完成的覆蓋表，不另開維度。
> 資料: [layout_rewriter/runs/nsweep_full/](layout_rewriter/runs/nsweep_full/)
> + [prefetch_churn/runs_nsweep_full_{a,b,c}/](prefetch_churn/)；
> 圖: [Figure 11](figures/out/11_nsweep_full.png) / [Figure 12](figures/out/12_nsweep_full_churn.png)。
>
> **Preprocessing / prefetch overhead**：每個 dimension 的 table 只報 `first_query_us`
> （第一筆 query 本身的時間），**不包含 prefetch tool 自己跑的時間**。所有
> (tool, layout, workload, strategy) 組合的 prefetch overhead 已離線量過、存
> 在 [calibration/prefetch_time_summary.csv](calibration/prefetch_time_summary.csv)
> （351 cells × 3 reps 取 median）。要算「端到端 cold start」就把 prefetch_time
> 加上 first_query。**參考級距**：layers_5 ≈ 1-2 µs、layers_92 ≈ 14 µs、
> 2d ≈ 2-6 µs、2e_K10 ≈ 5-8 µs、2e_K500 ≈ 80 µs、**2f SLRU 1,200-1,900 µs**
> （2f overhead 比 first_q 大 80-130 倍，是真正影響「真實 cold start」的策略）。
> 細節見 [calibration/README.md](calibration/README.md)。
> 視覺化對照：[Figure 13](figures/out/13_strategy_firstq_bars.png)（純 first-q，
> 2f SLRU 看起來通殺）vs [Figure 14](figures/out/14_strategy_endtoend_stacked.png)
> （end-to-end stacked，2f SLRU bar 高過 baseline 紅線、真實 cold start 反而慢
> 2-6 倍）。
>
> 🆕 **2026-06-19 P0 Pipeline 統一**（措辭 2026-06-22 校正）：所有 sub-project 的 cold-start
> 機制已統一到 P0 pipeline（harness MADV chain + `/usr/local/sbin/drop-caches`
> setuid wrapper + **harness 內建 `--verify-hotset`** 兩道 mincore 量 `cold_pct`/`delivery_pct`；
> 注意**不是**外部 `residency_checker`——後者的 ~100ms 間隔會污染 `fq_async`），詳見
> [IMPLEMENTATION_PIPELINES.md](IMPLEMENTATION_PIPELINES.md)。歷史派 hotset（2d/2e/2f）由
> `run_p0.py --regen-hotsets` 以 P0 全機 drop-caches 重產並 checksum 凍結。**但**：
> **本檔以下所有 dimension 的數字皆收集於 P0 之前**，混用 4 條歷史 pipeline，
> 待 P0 master rerun 取代（屆時每個 % 需從新 `summary_p0.csv` 重算）：
>
> | Pipeline | 機制 | 用在哪些 dimension |
> |---|---|---|
> | **P1** | `--cold-advice dontneed` + per-file posix_fadvise (`evict` binary) | 主表 + 第 2-9, 11-13, 14-15, 17, 19 維 |
> | **P2** | `--cold-advice none` + per-file posix_fadvise + 跳過 residency verify | 第 10, 18 維（prefetch_churn） |
> | **P3** | `sync && echo 3 > /proc/sys/vm/drop_caches`（sudo）| 主表 Workload A column（早期 prefetch_vacuum / Week 9-11） |
> | **特殊** | cgroup MemoryMax + cgroup measurement | 第 16 維（RAM-pressure 對照） |
>
> 絕對 µs **跨 dimension 不可比**——只有同一 dimension 內的相對改善 % 可信。
> [CONTRADICTIONS.md](CONTRADICTIONS.md) 抓出 **16 條數據打架**（#1-16）皆源自此。
>
> ### ⚠️ 已知具體矛盾（按嚴重度排序）
>
> - **#1 Workload A baseline 有 ~10 個值**：73 / 251 / 299.7 / 305 / 318 /
>   321 / 333 / 404 / 505 / 634 µs（分佈於本檔主表、第二維、第七維、第九維、
>   §5.5.2 表 等）。**建議修法**：用 P0 重跑 (A, B, C, Z) × (1a, 1b, 1c) × baseline
>   共 12 個 cell × 5 reps、median 取代所有 dimension 的 baseline 行；headline
>   cell（論文 Abstract 引用）建議 10 reps + IQR。
> - **#7 SLRU「慢幾倍」全文 5 種值**：3–7× / 2–6× / 29× / 30× /
>   7×+625%。**建議修法**：在 P0 下重跑 2f SLRU × (A,B,C) × (1a,1b,1c) =
>   9 cell × 5 reps，產出一張 single source of truth 表，REPORT.md 與本檔
>   所有 SLRU 相對倍數一律從這張表引用。
> - **#8 / #14 / #15 / #16 access pattern 改善 % 不一致**：C × 2d × 1a 在
>   4 個位置寫 -46% / -47.2% / -47.6% / -48% / -83.9% / -88%（同方向但精確值飄）；
>   且 Abstract / §5.4 對「access vs load-all」勝負方向相反。**建議修法**：用 P0
>   重跑 2d/2e × (A,B,C) × (1a,1b,1c) × K ∈ {0,10,50,100,500}，全部從同一
>   batch 算 %。
> - **#10 / #11 / #13 數字精度漂移**：DB 總 page 數 26,331 vs 25,613（後者疑筆
>   誤）；2f prefetch 開銷 7,255/7,478/7,478/7,614 µs；churn 後 C × layers_92
>   改善 -51%/-54%/-55.2%/-58%。**建議修法**：用 P0 重跑 + 加 reps 數壓低噪音。
> - **#12 RAM-pressure 比例方向** ✅ **已解(2026-06-23, P0)**：resident working set
>   (2f hotset ~4.4k page ≈ **17 MB**)其實**略小於** 20M cap,所以 hotset 幾乎塞得下、
>   驅逐壓力小 → P0 fig 06 量到「20M/不限」比值**近 1.0**(RAM 壓力幾乎不影響首查)。
>   舊「20M ≪ 16MB」方向敘述作廢;以 P0 [`p0_runs_ram20m/`](p0_runs_ram20m/summary_p0.csv) 為準。
> - **#24 結構性根因**：「cold-start 機制不統一、卻說一致可比」——本 banner
>   已修正，但所有 cell 數字仍需 P0 重跑後才能去掉「跨表不可比」caveat。
>
> 每節最下方標明該 dimension 的資料來源 pipeline。論文最終版前，這 16 條
> 矛盾 + RAM-pressure 校正都需要 master rerun under P0 才能 close。

---

<!-- P0-MASTER-RESULTS-START -->
## P0 master batch 結果（2026-06-22,authoritative）

> 由 `run_p0.py` 一次跑齊:54 strategy cells × pread/async + 9 baseline,pread 5 / async 10 / baseline 10 reps(丟 warmup)、rep-major、全機 drop-caches、in-harness `--verify-hotset`、釘核升頻、ra=128。**全 117 cell `cold_pct`=0**。原始檔:[`p0_runs/summary_p0.csv`](p0_runs/summary_p0.csv) / [`p0_runs/raw_p0.csv`](p0_runs/raw_p0.csv)。
> `fq` = first-query median µs;`impr%` = async 相對該 (workload,layout) baseline;`e2e` = preproc+fq(async);`deliv%` = async delivery_pct;`oracle` = pread 臂 fq(可達上界)。
> **以下歷史維度表(主表～第十八維)為 pre-P0,保留作對照,數字以本節為準。**

### Workload A (Zipfian)

| layout | strategy | fq_async | impr% | deliv% | e2e_async | oracle(pread) |
|---|---|--:|--:|--:|--:|--:|
| **orig** | baseline | **496.86** | — | — | 496.86 | — |
| orig | layers_5 | 349.61 | 30% | 100.0 | 606.89 | 153.69 |
| orig | layers_92 | 337.77 | 32% | 100.0 | 724.67 | 155.06 |
| orig | 2d | 335.01 | 33% | 100.0 | 609.67 | 154.34 |
| orig | 2e_K10 | 337.32 | 32% | 100.0 | 626.31 | 152.25 |
| orig | 2e_K500 | 154.23 | 69% | 100.0 | 1224.72 | 158.36 |
| orig | 2f_slru | 106.76 | 79% | 100.0 | 7489.41 | 106.58 |
| **vacuum** | baseline | **696.87** | — | — | 696.87 | — |
| vacuum | layers_5 | 554.39 | 20% | 100.0 | 809.36 | 184.94 |
| vacuum | layers_92 | 558.94 | 20% | 100.0 | 936.62 | 194.18 |
| vacuum | 2d | 555.44 | 20% | 100.0 | 823.73 | 186.86 |
| vacuum | 2e_K10 | 553.36 | 21% | 100.0 | 842.25 | 185.79 |
| vacuum | 2e_K500 | 190.28 | 73% | 26.2 | 1170.64 | 198.11 |
| vacuum | 2f_slru | 104.50 | 85% | 100.0 | 5873.91 | 104.03 |
| **ta** | baseline | **651.69** | — | — | 651.69 | — |
| ta | layers_5 | 496.99 | 24% | 100.0 | 792.35 | 489.00 |
| ta | layers_92 | 426.06 | 35% | 100.0 | 835.59 | 186.52 |
| ta | 2d | 437.49 | 33% | 72.1 | 778.83 | 200.16 |
| ta | 2e_K10 | 394.17 | 40% | 100.0 | 751.58 | 196.52 |
| ta | 2e_K500 | 206.21 | 68% | 27.2 | 1290.30 | 192.38 |
| ta | 2f_slru | 104.75 | 84% | 100.0 | 7542.85 | 109.03 |

### Workload B (Uniform)

| layout | strategy | fq_async | impr% | deliv% | e2e_async | oracle(pread) |
|---|---|--:|--:|--:|--:|--:|
| **orig** | baseline | **725.31** | — | — | 725.31 | — |
| orig | layers_5 | 383.90 | 47% | 100.0 | 680.18 | 385.44 |
| orig | layers_92 | 389.86 | 46% | 100.0 | 830.32 | 388.64 |
| orig | 2d | 384.57 | 47% | 100.0 | 697.56 | 386.66 |
| orig | 2e_K10 | 382.24 | 47% | 100.0 | 712.07 | 390.17 |
| orig | 2e_K500 | 429.59 | 41% | 100.0 | 1563.15 | 412.38 |
| orig | 2f_slru | 105.30 | 85% | 100.0 | 7572.22 | 105.53 |
| **vacuum** | baseline | **998.90** | — | — | 998.90 | — |
| vacuum | layers_5 | 508.52 | 49% | 100.0 | 775.29 | 511.11 |
| vacuum | layers_92 | 515.72 | 48% | 100.0 | 901.80 | 520.60 |
| vacuum | 2d | 507.51 | 49% | 100.0 | 782.36 | 511.01 |
| vacuum | 2e_K10 | 512.71 | 49% | 100.0 | 798.92 | 513.80 |
| vacuum | 2e_K500 | 401.65 | 60% | 23.6 | 1421.45 | 472.48 |
| vacuum | 2f_slru | 106.00 | 89% | 100.0 | 5837.06 | 106.39 |
| **ta** | baseline | **795.23** | — | — | 795.23 | — |
| ta | layers_5 | 602.37 | 24% | 100.0 | 898.01 | 590.90 |
| ta | layers_92 | 577.76 | 27% | 77.2 | 986.96 | 595.77 |
| ta | 2d | 587.07 | 26% | 77.5 | 932.89 | 568.39 |
| ta | 2e_K10 | 594.48 | 25% | 80.0 | 942.14 | 600.76 |
| ta | 2e_K500 | 625.36 | 21% | 26.9 | 1638.70 | 525.66 |
| ta | 2f_slru | 107.00 | 87% | 100.0 | 7539.90 | 107.13 |

### Workload C (Churn-heavy)

| layout | strategy | fq_async | impr% | deliv% | e2e_async | oracle(pread) |
|---|---|--:|--:|--:|--:|--:|
| **orig** | baseline | **1058.09** | — | — | 1058.09 | — |
| orig | layers_5 | 1020.82 | 4% | 100.0 | 1322.25 | 1017.30 |
| orig | layers_92 | 635.96 | 40% | 100.0 | 1068.00 | 635.09 |
| orig | 2d | 635.31 | 40% | 100.0 | 930.10 | 631.70 |
| orig | 2e_K10 | 154.84 | 85% | 100.0 | 462.20 | 152.79 |
| orig | 2e_K500 | 154.31 | 85% | 67.3 | 863.73 | 154.48 |
| orig | 2f_slru | 102.38 | 90% | 100.0 | 1178.72 | 101.58 |
| **vacuum** | baseline | **991.75** | — | — | 991.75 | — |
| vacuum | layers_5 | 866.45 | 13% | 100.0 | 1158.29 | 884.18 |
| vacuum | layers_92 | 503.96 | 49% | 100.0 | 911.32 | 501.58 |
| vacuum | 2d | 495.35 | 50% | 100.0 | 771.89 | 496.86 |
| vacuum | 2e_K10 | 185.41 | 81% | 100.0 | 499.68 | 188.26 |
| vacuum | 2e_K500 | 188.28 | 81% | 55.6 | 936.92 | 187.47 |
| vacuum | 2f_slru | 101.50 | 90% | 100.0 | 954.27 | 102.80 |
| **ta** | baseline | **870.95** | — | — | 870.95 | — |
| ta | layers_5 | 839.69 | 4% | 100.0 | 1140.96 | 835.32 |
| ta | layers_92 | 473.04 | 46% | 100.0 | 874.45 | 487.30 |
| ta | 2d | 483.16 | 45% | 64.6 | 826.00 | 454.24 |
| ta | 2e_K10 | 188.38 | 78% | 100.0 | 548.46 | 189.76 |
| ta | 2e_K500 | 189.36 | 78% | 100.0 | 1067.60 | 189.54 |
| ta | 2f_slru | 103.61 | 88% | 100.0 | 1205.34 | 99.69 |

**讀法**:① first-query 最低一律是 **2f_slru**(載整個 working set),但它 `e2e` 被 ~5.7–7.5ms preproc 拖垮 → 真要部署看 e2e 時 2f 出局。② 結構派 **layers_5 / 2e_K10** 用極少 syscall 拿到中段效益、`e2e` 最划算(尤其 **C × 2e_K10:fq −85%、e2e 僅 462µs**)。③ `deliv%`<100 的格(多為 ta/vacuum × 2e_K500)是 async fadvise 未及載滿整個 hotset、但首查所需頁多已命中。④ `oracle` 欄是同步 pread 的可達下界。
<!-- P0-MASTER-RESULTS-END -->

---

## 主表 — strategy × workload（base layout、median latency）

| 策略 | Workload A（Zipfian point-read） | Workload C（high-key uniform read） |
|---|---|---|
| **baseline**（no prefetch） | **73 µs** first-query latency | **4,918 µs** first-query latency |
| **range**（merge contiguous interior pages, 1 madvise per range） | **54 µs**（-27%）<br>87 syscalls, prefetch 開銷 2.2 ms | 見[第六維](#第六維--策略-1b-sqlite-vacuum--workload-b--c)、[第七維](#第七維--策略-1c-type-aware-layout--workload-b--c)：**342 µs (-27%)** on 1a |
| **perpage**（每個 interior page 一次 madvise） | **48 µs**（-34%）<br>92 syscalls, prefetch 開銷 2.9 ms | 見[第六維](#第六維--策略-1b-sqlite-vacuum--workload-b--c)、[第七維](#第七維--策略-1c-type-aware-layout--workload-b--c)：**343 µs (-27%)** on 1a；**294 µs (-37%)** on 1c — Workload C 的最佳免 warmup-pass 組合 |
| **layers_5**（前 5 個 interior page by offset） | **33 µs**（-54%） ← 甜蜜點<br>5 syscalls, prefetch 開銷 94 µs | **5,130 µs**（+4% — baseline 時略差）<br>但隨 churn 累積反轉為 **-10%**（見下節）|

**資料來源：**
- Workload A 來自 [prefetch_vacuum/results/results_summary.csv](prefetch_vacuum/results/results_summary.csv)（Week 9–11，原始 layout，`sudo drop_caches`——**P3 pipeline**）
- Workload C 來自 [prefetch_churn/results/](prefetch_churn/results/)（10 checkpoints，每 checkpoint 之間用 Workload D 製造 5,000 ops 寫入壓力——**P2 pipeline**）

**讀這張表的兩件事：**
1. **prefetch 對 Workload A 大勝**（最高省 54%），對 Workload C 在乾淨 DB 上沒效益（甚至略差）。差異不是 first-q（兩個 workload 的 first-q 時 leaves 都是 cold——cold-start protocol DONTNEED 全清），而是**整個 workload 跑完**：Workload A Zipfian 跑開後少數 hot keys 的 leaves 自然 warm-up，interior 成為唯一反覆需要的瓶頸，prefetch 專攻它就有效；Workload C 每筆 query 都打不同 cold leaf、沒有自然熱葉可依賴。**注意 layers_5 在 A 上的 -54% first-q 改善仍包含一次 leaf fault**（layers_5 只移除 interior fault，殘留 ~127-224 µs 的 leaf fault 還在），「hot leaves 已不冷」描述的是穩態 / avg latency、不是 first-q。
2. **「越多 prefetch 不一定越好」是 P3 era 結論，P1 dense sweep 部分推翻** ⚠️ pending P0 rerun：當前 P1 顯示 A on 1b 真正最佳 N=62 反而 > N=5 plateau；C on 1a N=92 大勝 (-45~53%) >> N≤46 plateau (-10%)。只在 A on 1a 還有輕微 U 形。`madvise(MADV_WILLNEED)` 仍是 **async hint、不阻塞、不保證載入完成**（kernel ground truth + repo 自己實測 range 模式只載 32/92）；syscall overhead 本身（calibration ≈14 µs）可忽略 — 這兩條都是 robust 結論。但「N>5 是否變慢、為什麼」需要 P0 master rerun 後重新評估。

> ⚠️ **本表混 P3 + P2 pipeline，是 [CONTRADICTIONS.md](CONTRADICTIONS.md) #1
> 的最大來源**：Workload A baseline 在本表寫 73 µs（最快值），其他維度寫
> 251 / 299.7 / 305 / 318 / 321 / 333 / 404 / 505 / 634 µs（最大差 8.7×）。
> 73 µs 應該是 P3 (`sudo drop_caches` + leaf 自然熱) 量出來的最低值——但這條
> pipeline 在 u03 上已無法重現（P3 需 root）。**建議修法**：本表整張**廢除**，
> 改用 P0 重跑 (A, C) × {baseline, range, perpage, layers_5} 共 8 cell × 5 reps，
> 並在表 caption 明示 P0 pipeline 與 single-batch 來源。

---

## 第二維 — Layout 對 strategy 的放大效果（Workload A only）

同一個 Workload A，但 DB layout 不同。**這張是 [layout_rewriter/](layout_rewriter/) 的端到端驗證結果**（`posix_fadvise` 冷啟動，3 reps median）：

| Layout | scatter | baseline | range | perpage | **layers_5** |
|---|---:|---:|---:|---:|---:|
| 原始 DB | 0.96 | 318 µs | 370 µs | 319 µs | 224 µs |
| 跑完 SQLite VACUUM | **1.13** ← 變更散 | 333 µs | 330 µs | 338 µs | 234 µs |
| **跑完 layout_rewriter（type-aware）** | **0.00** | 404 µs | 387 µs | 273 µs | **127 µs** ← 全局最佳 |

**相對於該 layout 自己的 baseline：**

| Layout | range | perpage | **layers_5** |
|---|---:|---:|---:|
| 原始 | +16% | +0% | -30% |
| post-VACUUM | -1% | +2% | -30% |
| **post-layout_rewriter** | -4% | -33% | **-69%** |

**這張表回答了 README 第 9 章列的核心研究問題：「Type-aware VACUUM 能不能把
prefetch 效益從 -9% 救回 -54%」 — 答案是：可以，而且超越，推到 -69%。**

副作用：
- **`range` 在 type-aware layout 上 syscall 從 87 → 1**（4.5× 快），但 kernel
  readahead 是 bounded，1 個 `MADV_WILLNEED` 只實際載入 32/92 pages → range
  策略在任何 layout 下都不是好選擇
- **type-aware layout 的 baseline 反而變慢**（318 → 404 µs），因為 leaf 被
  推到高 offset，第一個 cold leaf fault 跑得更遠。但 prefetch 一啟用就完全
  壓過這個 penalty

資料來源：[layout_rewriter/results/results_summary.csv](layout_rewriter/results/results_summary.csv)

---

## 第三維 — N sweep（Workload A，原始 layout，找甜蜜點）

| N（prefetch 幾個 interior page） | syscalls | prefetch 開銷 | first-query latency | 改善 |
|---:|---:|---:|---:|---:|
| 0 | 0 | 0 | 73 µs | baseline |
| 1 | 1 | 35 µs | 38 µs | -48% |
| **5** | **5** | **94 µs** | **33 µs** | **-54%** ← 甜蜜點 |
| 10 | 10 | 273 µs | 44 µs | -39% |
| 20 | 20 | 607 µs | 35 µs | -53% |
| 46 | 46 | 1,173 µs | 41 µs | -45% |
| 92 (= 全部 interior) | 92 | 2,229 µs | 50 µs | -31% |

⚠️ **舊 P3 era 結論**：U 型曲線——prefetch 太少（N=1）上層 interior 載到了但
中下層還沒；prefetch 太多（N=92）first-q 反而 -31% < N=5 的 -54%。**Pending
P0 rerun**：當前 P1 dense sweep 顯示 U 形**只在 A on 1a 還有 trace**（且寬到
接近 plateau），A on 1b 反而 N=62 最佳，A on 1c / C on 1a 等多數 cell 已
plateau 或反向。Syscall overhead（calibration ≈14 µs）可忽略仍是 robust 結論；
但「N>5 變慢」現象本身、其因果（async readahead 來不及？memory reclaim？other？）
**全部需要 P0 master rerun + per-cell majflt count 才能定論**。

資料來源：[prefetch_vacuum/results/results_summary.csv](prefetch_vacuum/results/results_summary.csv) Week 10

---

## 第四維 — Workload C 隨 churn 漂移（10 checkpoints）

`prefetch_churn` 設計：同一個 DB，每個 checkpoint 之間用 Workload D 跑 5,000
ops 製造 layout 漂移，然後 drop cache → 跑 Workload C → 量 latency。

| Checkpoint（累積寫入 ops）| no_prefetch first-query | layers_5 first-query | layers_5 改善 |
|---:|---:|---:|---:|
| baseline (0) | 4,918 µs | 5,130 µs | +4% |
| ck001 (5k) | 4,511 µs | 5,398 µs | +20% ← prefetch 反而傷害 |
| ck002 (10k) | 5,950 µs | 4,554 µs | -23% |
| ck003 (15k) | 9,534 µs | 7,037 µs | -26% |
| ck004 (20k) | 6,574 µs | 5,385 µs | -18% |
| ck005 (25k) | 5,709 µs | 7,055 µs | +24% |
| ck006 (30k) | 7,319 µs | 6,179 µs | -16% |
| ck007 (35k) | 6,924 µs | 6,696 µs | -3% |
| ck008 (40k) | 6,816 µs | 6,795 µs | -0% |
| ck009 (45k) | 7,384 µs | 6,323 µs | -14% |
| ck010 (50k) | 6,892 µs | 6,300 µs | -9% |
| **平均**（ck001-010） | **6,661 µs** | **6,174 µs** | **-7%** |

**單筆 noise 很大**（ck001 +20%、ck003 -26%），但累積 10 個 checkpoint 平均下來
prefetch 仍然省 ~7%（絕對省 ~487 µs/query）。對照 Workload A 的 -54%，這裡的
百分比看起來小，但**絕對省的時間反而多**（A 省 40 µs vs C 省 487 µs），因為
baseline 本來就被 leaf cold fault 拉到 5,000+ µs 起跳。

> **後續補測（第十維）**：本節只跑 N=5 一個 N 值。第十維把 N=1/10/20/46/92
> 全跑過（用 `posix_fadvise` harness、絕對 µs 不能跨表比）— 結論是 churned
> DB 上 N=92 帶來 -54% 改善，且在所有 10 個 checkpoint 上都壓制其他 N。N=5
> 在第十維的 harness 下省 ~10.6%（方向跟本節 -7% 一致）。

資料來源：[prefetch_churn/results/](prefetch_churn/results/)

---

## 第五維 — 策略 4 (2f SLRU)

新策略：跑完一次 workload 後**不要 evict**，直接用 `mincore()` dump 當下 OS
page cache 裡的所有 resident page，存成 `hotpages.csv`。下次 cold start 時對
每個 resident page 一一呼叫 `madvise(MADV_WILLNEED)`。

對照**三個 workload**：A (Zipfian、`workload_a_zipfian.txt`)、B (Uniform、
`workload_uniform.txt`)、C (high-key uniform、`page_churn_benchmark_high.txt`)，
原始 layout，3 reps median，`posix_fadvise(POSIX_FADV_DONTNEED)` 冷啟動。

> Layout 1b (VACUUM) 版本見 [第九維](#第九維--layout-1b-vacuum-補測n-sweep--2f-slru--abc)，
> Layout 1c (type-aware) 版本見 [第十一維](#第十一維--2f-slru--layout-1c-type-aware)。
> 結論預告：2f SLRU 在三個 layout 上 first-q 都是 13–16 µs（layout-agnostic）。

### Hot set（warmup 後 resident 的 page 分佈）

| Workload | 總 resident | leaf_table | leaf_index | interior_table | interior_index |
|---|---:|---:|---:|---:|---:|
| **A (Zipfian)** | 4,048 | 3,328 | 702 | 10 | 8 |
| **B (Uniform)** | 4,122 | 3,331 | 775 | 10 | 6 |
| **C (high-key)** | **420** | 357 | 59 | 2 | 2 |

A、B 打 id ∈ [1, 100k]（DB 前 1/6 區段），所以 touched leaf 集合大致相同，
hot set 各 ~16 MB。C 打 id ∈ [590k, 610k]（高度集中在 20k 區段、又有半數
落在 600k 後的不存在 id），leaf 高度共享 → **hot set 只有 1.6 MB（10× 小）**，
這直接決定了 2f 的 prefetch overhead 縮水到 1/4。

### Latency 矩陣

| Workload | 策略 | first-q (µs) | avg-q (µs) | total (ms) | prefetch (µs) | madvise 次數 |
|---|---|---:|---:|---:|---:|---:|
| A (Zipfian) | baseline | 251 | 4.11 | 411 | 0 | 0 |
| A (Zipfian) | layers_5 | 133 | 4.13 | 412 | 15 | 5 |
| A (Zipfian) | **2f SLRU** | **14** | **2.50** | **249** | 7,255 | 4,048 |
| B (Uniform) | baseline | 255 | 4.13 | 413 | 0 | 0 |
| B (Uniform) | layers_5 | 137 | 4.11 | 411 | 15 | 5 |
| B (Uniform) | **2f SLRU** | **15** | **2.55** | **255** | 7,478 | 4,122 |
| C (high-key) | baseline | 250 | 2.62 | 262 | 0 | 0 |
| C (high-key) | layers_5 | 185 | 2.66 | 266 | 13 | 5 |
| C (high-key) | **2f SLRU** | **16** | **2.45** | **245** | **1,881** | **420** |

> **2026-06 calibration 重量**：standalone 跑 prefetch_slru 拿到的數字
> （[calibration/](calibration/)）跟本表的 prefetch (µs) 不同（A 1,808 µs / B 1,810 µs
> / C 1,246 µs）。原因：本節用的是 mmap-enabled prefetch_slru harness（有 mmap()
> setup overhead），而 calibration 是 standalone 直接跑。**結論不變**——prefetch 開銷
> 比 first-q 大 80-130 倍，端到端 cold start 比 baseline 慢 5-30 倍。詳見
> [calibration/README.md](calibration/README.md) 末段「跟線上 benchmark 的差距」。

### 與 baseline 比的相對改善

| Workload | 策略 | first-q 改善 | 全 workload 總時間改善 | 端到端 cold start (prefetch+first-q) |
|---|---|---:|---:|---:|
| A (Zipfian) | layers_5 | -47% | ≈ 0% | 148 µs（vs 251 baseline，**-41%**）|
| A (Zipfian) | **2f SLRU** | **-94%** | **-39%** | 7,269 µs（**比 baseline 慢 29×**）|
| B (Uniform) | layers_5 | -46% | ≈ 0% | 152 µs（vs 255 baseline，**-40%**）|
| B (Uniform) | **2f SLRU** | **-94%** | **-38%** | 7,493 µs（**比 baseline 慢 30×**）|
| C (high-key) | layers_5 | -26% | ≈ 0% | 198 µs（vs 250 baseline，**-21%**）|
| C (high-key) | **2f SLRU** | **-94%** | **-7%** | 1,897 µs（**比 baseline 慢 7.6×**）|

> ⚠️ **本表「慢 29× / 30× / 7.6×」是 [CONTRADICTIONS.md](CONTRADICTIONS.md) #7
> SLRU 倍數矛盾的源頭之一**：REPORT.md / Abstract 引用「慢 3–7×」，本表卻寫
> 「29× / 30×」，第十一維又寫不同數字。這不是純算術錯——是不同 dimension 用
> 不同 pipeline + 不同 baseline、再各自除以該 baseline 得到的。**建議修法**：
> P0 重跑後，用 (prefetch_overhead + first_query) ÷ baseline_first_query 這一個
> 算式統一算「慢幾倍」，REPORT.md / Abstract / 本檔所有 SLRU 倍數一律引用同
> 一張表（建議放在本檔第五維或新建第二十維）。

### 六個發現

1. **第一筆 query 上 2f 把 layers_5 打到地上**（-94% vs -26~47%）在所有
   workload 都成立。SLRU 把全部 touched leaf prefetch 進來，第一筆不管打哪個
   id 都打到熱 leaf；layers_5 只 prefetch interior，leaf 還是 cold-fault。
2. **2f 的 prefetch 開銷直接由 hot set 大小決定**：A/B 4,000+ syscalls →
   7.5 ms；**C 只 420 syscalls → 1.9 ms（4× 便宜）**。C 端到端 cold start 從
   A/B 的「慢 30×」改善到「慢 7.6×」—— 仍是退步，但差距大幅縮小。
3. **全 workload 改善幅度跟 baseline 的 avg-q 走**：A/B 的 baseline avg-q
   是 4.1 µs（每筆 query 都要 cold-fault leaf），2f 把它壓到 2.5 µs →
   全 workload 省 38~39%；C 的 baseline avg-q 已經是 2.62 µs（leaves 已經
   高度集中、disk seek 路徑短），2f 把它壓到 2.45 µs → 全 workload **只省 7%**。
4. **C 上 layers_5 也大幅退化**（-26% vs A/B 的 -46~47%）。確認先前觀察：
   layers_5「按 file offset 排前 5」對 file-tail workload 命中率低，因為
   query 走的 interior 不在全局上層。
5. **A 和 B 對 2f 沒差**（first-q 14 vs 15 µs）。原本以為 SLRU 在 skewed 上
   會輸給 access-count（無法區分 hot degree），實測一樣。原因：hot set
   (~16 MB) 全塞得進 RAM，沒有「該丟誰」的競爭，frequency 資訊用不上。
6. **2f 在 C 上的「working-set preload」效益大幅縮水**：A/B 全 workload 省
   38%（每筆都解決 leaf fault），C 只省 7%（leaves 已經幾乎共享同個 disk
   region，沒有多少 cold fault 可解）。**2f 的價值跟 hot set 的「leaf
   spread」成正比** —— 越分散，preload 收益越大。

資料來源：[prefetch_slru/results/results_summary.csv](prefetch_slru/results/results_summary.csv)

---

## 第六維 — 策略 1b (SQLite VACUUM) × Workload B / C

`prefetch_vacuum` 早期只在 Workload A 上跑過 VACUUM 對 layout 的影響（scatter
0.96 → 1.13、layers_5 改善退化）。本節補上 **B (Uniform) 和 C (high-key
uniform)** 在同一個 `posix_fadvise` cold-start harness、4 個 prefetch 策略下
的對照（3 reps median）。

兩個 DB：
- `test.db` — 600k rows 原始 layout（scatter 0.96）
- `test_vacuum.db` — 對 `test.db` 跑過 `VACUUM;` 的結果（scatter 1.13、檔案
  從 107.8 MB 縮到 104.9 MB）

### Latency 矩陣（first-query µs）

| Workload | DB | baseline | range | perpage | layers_5 |
|---|---|---:|---:|---:|---:|
| **B (Uniform)** | orig | 463 | 350 (-24%) | 377 (-19%) | **244 (-47%)** |
| **B (Uniform)** | vacuum | 503 | 328 (-35%) | 325 (-35%) | **250 (-50%)** |
| **C (high-key)** | orig | 467 | **342 (-27%)** | 343 (-27%) | 406 (-13%) |
| **C (high-key)** | vacuum | 437 | **368 (-16%)** | 384 (-12%) | 408 (-7%) |

百分比都是「同 DB baseline 為比較基準」。

### VACUUM 對 baseline 的影響（不算 prefetch）

| Workload | orig baseline | vacuum baseline | VACUUM 帶來的變化 |
|---|---:|---:|---:|
| **A (Zipfian)** | 318 µs | 333 µs | **+5%（變慢）** |
| **B (Uniform)** | 463 µs | 503 µs | **+8%（變慢）** |
| **C (high-key)** | 467 µs | 437 µs | **-6%（變快）** |

A 數據取自 [layout_rewriter/runs/matrix_results.csv](layout_rewriter/runs/matrix_results.csv)
+ [matrix_vacuum_results.csv](layout_rewriter/runs/matrix_vacuum_results.csv)，
是同一個 harness 量出來的，可直接比較。

### 四個發現

1. **VACUUM 對 baseline 的方向 workload-dependent**：A 和 B（打 id 低段）變
   慢 +5~8%，因 VACUUM 後 interior 被推到更後面、低段 leaf 對應的 interior
   walk 路徑更分散；C（打 id 高段）反而變快 -6%，因為高段 leaf 在原 layout
   上本來就靠檔尾，VACUUM 把整個檔壓緊後 high-key region 的 seek 距離縮短。
2. **VACUUM 沒有殺死 layers_5 在 B 上的效益**（-47% → -50%）。和 README 第
   9 章的「VACUUM 把 layers_5 從 -54% 打到 -9%」現象不一致 —— 那次是
   `sudo drop_caches` + leaf 自然熱的 Workload A，瓶頸全在 interior fault；
   B 上 leaf 都是 cold fault，interior 那點 scatter 變化被攤平。
3. **Workload C 翻轉了 prefetch 策略排名**：range/perpage **打敗** layers_5
   （orig: 342 vs 406、vacuum: 368 vs 408）。原因：C 只打 [590k, 610k] 區
   段，相關 interior 不在「按 file offset 排前 5」裡 —— layers_5 prefetch 的
   是全局上層 interior，但 query 走的 interior path 在檔案中段。需要 range/
   perpage 把**所有** interior 都載入，才能覆蓋到 C 真正會 traverse 的那幾頁。
4. **range/perpage 在 vacuum DB 上反而更有效**（B：-24% → -35% / -19% → -35%）。
   推測是 VACUUM 把 interior 分布拉開後，readahead 路徑變得更線性，少了一些
   被中間 leaf 切碎的 wasted readahead。

### 結論

- **1b VACUUM 不是 universal bad**：在 high-key 讀取場景（Workload C）反而
  讓 baseline 變快 6%；在 leaf-cold-heavy 的 B 上不會殺掉 prefetch 效益。
- **「VACUUM 打到 -9%」是 A 專屬效應**，不能推廣到其他 workload。
- **layers_5 不是萬靈丹**：在 Workload C 這種只打 file region 的 workload 上，
  「按 offset 排前 N」的啟發式會選錯 page，需要改用 range/perpage 或未來的
  access-pattern 排序（2d/2e）。

資料來源：[layout_rewriter/runs/matrix_1b_bc_results.csv](layout_rewriter/runs/matrix_1b_bc_results.csv)
+ [results_1b_bc_summary.csv](layout_rewriter/runs/results_1b_bc_summary.csv)

---

## 第七維 — 策略 1c (Type-aware layout) × Workload B / C

`layout_rewriter` 把所有 interior pages 重排到 file 開頭（pages 2..93 連續），
scatter 0.96 → 0.0001。先前只在 Workload A 上量過（-69% on layers_5）。本節
補上 **B (Uniform) 和 C (high-key uniform)** 在同一 harness 上的對照。

DB：`test_typeaware.db` — 對 `test.db` 跑過 [layout_rewriter](layout_rewriter/layout_rewriter.c)，
`PRAGMA integrity_check` 通過。

### Latency 矩陣（first-query µs，3 reps median）

| Workload | DB | baseline | range | perpage | layers_5 |
|---|---|---:|---:|---:|---:|
| **A (Zipfian)** | orig | 318 | 370 (+16%) | 319 (+0%) | **224 (-30%)** |
| **A (Zipfian)** | **ta** | 404 | 387 (-4%) | 273 (-32%) | **127 (-69%)** ← 全局最佳 |
| **B (Uniform)** | orig | 463 | 350 (-24%) | 377 (-19%) | **244 (-47%)** |
| **B (Uniform)** | **ta** | 408 | 366 (-10%) | 352 (-14%) | **440 (+8%)** ← 反效果 |
| **C (high-key)** | orig | 467 | 342 (-27%) | 343 (-27%) | 406 (-13%) |
| **C (high-key)** | **ta** | 467 | 520 (+11%) | **294 (-37%)** | 317 (-32%) |

百分比都是「同 DB baseline 為比較基準」。

### 跨 layout 比較（vs 原始 DB baseline）

| Workload | orig baseline | ta baseline | ta + 最佳 prefetch | 全局最佳改善 |
|---|---:|---:|---:|---:|
| **A** | 318 µs | 404 µs (+27%) | **127 µs (layers_5)** | **-60%** |
| **B** | 463 µs | 408 µs (-12%) | 352 µs (perpage) | -24% |
| **C** | 467 µs | 467 µs (±0%) | **294 µs (perpage)** | **-37%** |

### 五個發現

1. **ta layout 對 baseline 的方向 workload-dependent**：
   - A: +27%（leaves 被推到高 offset、第一個 cold leaf fault 跑得更遠，但 Zipfian 下後續被 prefetch 完全壓過）
   - B: **-12%（變快）** — 推測是 leaf 區也變得連續，cold leaf fault 的 readahead 更高效
   - C: ±0%（高 id leaves 在 ta 後仍位於檔尾，距離沒變）
2. **ta + layers_5 在 B 上反而變慢 +8%**（408 → 440）。原因：ta 把 leaves 推到
   高 offset，layers_5 prefetch 的 5 個 interior 載到了，但第一個 cold leaf
   fault 在很遠的 offset，prefetch 的 5 頁 + 後面的 cold leaf fault 兩個 I/O
   階段串起來反而比裸 baseline 慢。**ta 強在「prefetch coverage 高」時，弱在
   「prefetch 不夠覆蓋」時 —— B uniform 的 leaf coverage 一定不夠**。
3. **ta + perpage 是 Workload C 的最佳組合**（-37%、294 µs）。perpage 把 92
   個 interior **逐頁**載入，配合 ta 的 page 2-93 連續性，kernel 能高效
   sequential read；range 反而失效（+11%）因 1 個 madvise 被 kernel readahead
   限制（~32/92 pages）。
4. **ta + range 在所有 workload 都不是好選擇**：A -4%、B -10%、C +11%。
   `MADV_WILLNEED` 對單一大 range 的 readahead 是 bounded，覆蓋不完 92 個
   interior。
5. **「ta + layers_5」是 A 專屬最強**（-69%）。在 B/C 都不是最佳；對 C 反而
   是 layers_5 在 ta 上才開始有效（orig: -13% → ta: -32%），但仍輸給 perpage。

### 結論

- **ta layout 不是 universal best**：A 上 -69%，B 上反而讓 layers_5 變慢 +8%。
- **配方依 workload 而定**：
  - Zipfian 點讀 (A) → **ta + layers_5**
  - Uniform 全段 (B) → 不要 ta，**orig + layers_5** (-47%) 仍最強
  - File-tail uniform (C) → **ta + perpage** (-37%) 是全局最佳
- **range 在任何 layout 都不該選**：kernel readahead 限制讓它永遠覆蓋不完。

資料來源：[layout_rewriter/runs/matrix_1c_bc_results.csv](layout_rewriter/runs/matrix_1c_bc_results.csv)
+ [results_1c_bc_summary.csv](layout_rewriter/runs/results_1c_bc_summary.csv)
（A 數據 [matrix_results.csv](layout_rewriter/runs/matrix_results.csv) 同 harness 可直接比較）

---

## 第八維 — 2c Layers_N sweep × Workload B / C（原始 layout）

第三維只在 Workload A 上跑過 N sweep（N=1/5/10/20/46/92）。本節補上同一個
sweep 在 **B (Uniform)** 和 **C (high-key uniform)** 上的結果，使用同一個
`posix_fadvise` cold-start harness、原始 layout、3 reps median。

> **資料來源更新（2026-06）**：原本這張表的數字是 2026-05-25 sparse 6-pt 跑
> 出來的；後來補了 dense N=0..92 全 sweep。**為了讓全部 2c 表格用同個 machine
> state**，已從 dense run 切出 N ∈ {1, 5, 10, 20, 46, 92} 重算這張表。
> 結論不變、shape 不變，只是絕對 µs 跟 dense 同 baseline。

### Latency 矩陣（first-query µs，median of 3 reps，dense run 切片）

| N | **A first-q** | A 改善 | **B first-q** | B 改善 | **C first-q** | C 改善 | **prefetch_us** (1a, all WLs) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 (baseline) | 505 µs | — | **729 µs** | — | **1,079 µs** | — | 0 |
| 1 | 639 µs | +27% | 659 µs | -10% | 980 µs | -9% | 2.3 |
| 5 | 296 µs | -41% | **351 µs** | **-52%** | 970 µs | -10% | **1.4** |
| 10 | **294 µs (-42%)** ← A 甜蜜點區 | -42% | 352 µs | -52% | 979 µs | -9% | 2.3 |
| 20 | 339 µs | -33% | **351 µs (-52%)** ← B 最佳 | -52% | 974 µs | -10% | 3.8 |
| 46 | 332 µs | -34% | 353 µs | -52% | 975 µs | -10% | 7.8 |
| 92 (all interior) | 344 µs | -32% | 354 µs | -51% | **596 µs (-45%)** ← C 甜蜜點 | -45% | 15.3 |

> `prefetch_us` 從 [calibration/prefetch_time_summary.csv](calibration/prefetch_time_summary.csv) 切。
> `prefetch_layers` 工具的時間**只跟 N 有關、跟 workload 無關**（同個 madvise loop）。
> **End-to-end cold start = prefetch_us + first-q**。例：A × N=5 e2e = 1.4 + 296 = 297 µs
> (vs baseline 505 µs → 真實改善 -41.2%，跟 first-q 算的 -41.4% 幾乎一樣，因為
> prefetch 開銷 < 0.5%)。**2c layers_N 的 prefetch 開銷可忽略**。

### 三個發現

1. **B 上 N=5 之後就 plateau**（-52% 全部停在 ~351 µs），完全沒有 A 的 U 型
   曲線。原因：B 的 baseline 729 µs 是被 leaf cold fault 主導，prefetch 多
   個 interior 帶來的 madvise overhead 相對於 leaf fault cost 可忽略。
   **A 的 U 型曲線專屬於「baseline 相對較低、interior 是 bottleneck」的場景**
   —— A baseline 505 µs 比 B 低 30%，多打 87 個 madvise 開銷比例大、壓垮收益。

2. **C 上 N=1~46 只有 ~10% 改善**（停在 ~975 µs），**N=92 突然跳到 -45%**
   （596 µs）。原因：C 查 id ∈ [590k, 610k]（檔尾區段），走的 interior
   path **不在前 46 個 page 裡**。layers_N 按 file offset 排序的「top-N」
   對 C 不是 hot interior —— 必須載入**全部** 92 個 interior 才覆蓋到 C
   真正會 traverse 的那幾頁。
   - 這也解釋為什麼第六維裡 C 上 `range` 跟 `perpage` 勝過 `layers_5`：
     range/perpage 都載全部 interior，layers_5 漏掉中段。

3. **「N=5 是甜蜜點」只在 A 上成立、且是一段寬 plateau 而非 sharp minimum**。
   三個 workload 的最佳 N 值各不相同：
   - **A**: N=5..15 區間 plateau 在 -41~42%（dense 顯示 N=10 略勝 N=5）—— 上層 interior 就是熱點
   - **B**: N=5..92 plateau 全 -51~52% —— 任何 N≥5 都打到瓶頸
   - **C**: 必須 N=92（-45%）—— 熱 interior 在 file 中段，前 N 排序選不到

   **這推翻第三維的隱含結論「layers_N 是 universal 啟發式」**：它其實是
   *Zipfian-friendly* 啟發式，依賴「query 走的 interior path 集中在 file
   上層」這個假設。對 file-tail workload (C)，按 offset 排序 + top-N 是
   錯誤的優先順序。

### 結論

- **B 上**：layers_5 已經是 cost-effective 最佳，再多 N 不會更好（也不會更差）。
- **C 上**：layers_N 啟發式失效，要嘛載全部 (perpage/N=92)、要嘛改用
  access-pattern 排序的 2d/2e。
- **「按 file offset 排序的 top-N」是 zipfian-low-key-specific 的啟發式**，
  不能無腦套用到任意 workload。

資料來源：
- Dense 切片（本表）: [layout_rewriter/runs/nsweep_full/full_orig.csv](layout_rewriter/runs/nsweep_full/full_orig.csv)
- 原 sparse 6-pt（保留作交叉驗證）: [layout_rewriter/runs/matrix_Nsweep_bc_results.csv](layout_rewriter/runs/matrix_Nsweep_bc_results.csv)
+ [results_Nsweep_bc_summary.csv](layout_rewriter/runs/results_Nsweep_bc_summary.csv)

---

## 第九維 — Layout 1b (VACUUM) 補測：N sweep + 2f SLRU × A/B/C

第六維只跑了 baseline / range / perpage / layers_5 in vacuum DB × B/C。本節
把 Layout 1b 上的兩個剩餘缺口補齊：
- **N sweep**（N=1/5/10/20/46/92）on A/B/C × vacuum DB（layout_rewriter harness）
- **2f SLRU** on A/B/C × vacuum DB（prefetch_slru harness，with mmap）

VACUUM 把 interior 從 92 → 85 個，所以 N=92 的「全部 interior」實際載入 85 個。

### 9.1 N sweep × A/B/C × Layout 1b（first-query µs, median of 3）

跟第八維同一個 layout_rewriter harness（無 mmap、`posix_fadvise` cold-start）。

> **資料來源更新（2026-06）**：原本這張表是 2026-05-25 sparse 6-pt 跑的。
> 後續 dense N=0..92 跨三 layout 全 sweep 完成後，**已從 dense run 切出
> N ∈ {1, 5, 10, 20, 46, 92} 重算**，跟第八維 1a orig 用同個 machine state。
> Shape / 結論不變。

| N | **A orig** | **A vac** | **B orig** | **B vac** | **C orig** | **C vac** | **prefetch_us orig** | **prefetch_us vac** |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 505 | **607** | 729 | **936** | 1,079 | **911** | 0 | 0 |
| 1 | 639 | 896 | 659 | 839 | 980 | 783 | 2.3 | 1.3 |
| 5 | 296 | **479 ← A vac 甜蜜點** | 351 | **438 ← B vac 甜蜜點** | 970 | 829 | 1.4 | 1.7 |
| 10 | 294 | 482 | 352 | 451 | 979 | **748** | 2.3 | 2.4 |
| 20 | 339 | 479 | 351 | 441 | 974 | 833 | 3.8 | 3.8 |
| 46 | 332 | 490 | 353 | 439 | 975 | 786 | 7.8 | 8.0 |
| 92 | 344 | 486 | 354 | 443 | 596 | **428** | 15.3 | 13.8 |

dense run 給每個 (workload, N) cell 都有實際數據；orig 三 column 也補齊了
（第八維只列了 B/C）。**End-to-end cold start = (orig/vac 的 prefetch_us) +
(該 cell 的 first-q)**。例：A × vac × N=5 e2e = 1.7 + 479 = 480.7 µs
（baseline 607 µs → -20.8% e2e improvement）。prefetch_layers 開銷 < 1% first-q，可忽略。

### 9.2 2f SLRU × A/B/C × Layout 1b（median of 3）

跟第五維同一個 prefetch_slru harness（有 mmap）。

#### Hot set 大小（warmup 後）

| Workload | orig resident (第五維) | **vacuum resident** | 差距 |
|---|---:|---:|---:|
| A (Zipfian) | 4,048 | **3,369** | -17% |
| B (Uniform) | 4,122 | **3,373** | -18% |
| C (high-key) | 420 | **394** | -6% |

VACUUM 後 A/B 的 hot set 縮 17–18% —— 因為 VACUUM 把同一條 query path 的
leaves 排得更連續，一次 readahead 載入的 page 數變多，重複 query 的「需要
獨立 resident 的 page」減少。C 上 hot set 本來就集中，VACUUM 只剩 6% 改善
空間。

#### Latency 矩陣

| Workload | 策略 | first-q (µs) | avg-q (µs) | total (ms) | prefetch (µs) | madvise 次數 |
|---|---|---:|---:|---:|---:|---:|
| A (Zipfian) | baseline (vac) | 219 | 3.56 | 356 | 0 | 0 |
| A (Zipfian) | **2f SLRU (vac)** | **15** | **2.36** | **236** | 6,712 | 3,369 |
| B (Uniform) | baseline (vac) | 230 | 3.56 | 356 | 0 | 0 |
| B (Uniform) | **2f SLRU (vac)** | **14** | **2.39** | **239** | 6,303 | 3,373 |
| C (high-key) | baseline (vac) | 212 | 2.44 | 244 | 0 | 0 |
| C (high-key) | **2f SLRU (vac)** | **14** | **2.28** | **228** | 1,911 | 394 |

#### 與同 harness orig baseline 比

| Workload | 改善類型 | orig (第五維) | vacuum (本節) |
|---|---|---:|---:|
| A | first-q 改善 | -94% | **-93%** |
| A | 全 workload 改善 | -39% | **-34%** |
| A | prefetch 開銷 | 7,255 µs | **6,712 µs (-7%)** |
| B | first-q 改善 | -94% | **-94%** |
| B | 全 workload 改善 | -38% | **-33%** |
| B | prefetch 開銷 | 7,478 µs | **6,303 µs (-16%)** |
| C | first-q 改善 | -94% | **-94%** |
| C | 全 workload 改善 | -7% | **-7%** |
| C | prefetch 開銷 | 1,881 µs | **1,911 µs (≈0%)** |

### 五個發現

1. **VACUUM 在 prefetch_slru harness（mmap-enabled）下對 baseline 是利好**
   （A: 251→219、B: 255→230、C: 250→212）—— 與第六維「VACUUM 讓 A/B baseline
   變慢 +5~8%」相反。差異在 harness：layout_rewriter 沒設 `--mmap-size`，
   prefetch_slru 設了。**mmap 路徑下 VACUUM 把連續 leaf 拉得更近的好處
   compounds，而 pread 路徑下 VACUUM 反而讓 interior path 變遠**。

2. **A vac 在 N=5..92 是一段寬 plateau ~479-490 µs**（dense 6/16 切片）。
   原本 sparse 報的「N=20 是新甜蜜點」在 dense 重做後消失——N=5 跟 N=20 都
   是 479 µs、差距在 noise 內。**dense 找到的 1b vacuum 真正最佳 N=62（−31% vs
   baseline 607 µs）**（不在 sparse 6 個 N 採樣裡），但 plateau 寬，
   N=5 就拿到 -21% 已 dominate。

3. **B vac 跟 B orig N-sweep 幾乎一樣**（N≥5 都 plateau 在 ~245 µs）。VACUUM
   沒改變 B 的 prefetch 行為，因為 B 是 leaf-cold-fault 主導。

4. **C vac 上 N=92 依然是最佳**（246 µs，-43%）。VACUUM 沒改變 C 的根本問
   題：query 走的 interior path 不在 file 前段，必須載全部才覆蓋到。**這
   confirm 第八維結論「layers_N 是 zipfian-friendly 啟發式」適用在所有 layout
   上**。

5. **2f SLRU 在 vacuum 下 prefetch 開銷 A/B 省 7-16%、C 不變**。跟 hot set
   縮減比例 (-17%、-18%、-6%) 一致 —— VACUUM 替 2f 帶來邊際 prefetch cost
   節省，但全 workload 改善反而從 -38% → -33%（A）因 baseline 已經更快、
   SLRU 拉得到的下限差距變小。

### 結論

- **Layout 1b 補測完成**：A/B/C × {N=1,5,10,20,46,92, baseline, range, perpage, 2f SLRU} 全部跑過。
- **N=5 仍是大部分 workload 的 cost-effective 選擇**（A vac N=5/20 同等、dense 找到的 N=62 -31% 多省 10pp 但要 12× syscall）。
- **2f SLRU 的「VACUUM 加持」效果有限**：prefetch overhead 微降，但全 workload
  改善幅度反而縮水（因 baseline 變更快）。沒有 layout × prefetch 的乘數效應。

資料來源：
- N sweep（dense 切片，本表）: [layout_rewriter/runs/nsweep_full/full_vacuum.csv](layout_rewriter/runs/nsweep_full/full_vacuum.csv)
- 原 sparse 6-pt（保留作交叉驗證）: [layout_rewriter/runs/matrix_Nsweep_vac_results.csv](layout_rewriter/runs/matrix_Nsweep_vac_results.csv)
  + [results_Nsweep_vac_summary.csv](layout_rewriter/runs/results_Nsweep_vac_summary.csv)
- SLRU: [prefetch_slru/runs/matrix_vacuum_results.csv](prefetch_slru/runs/matrix_vacuum_results.csv)
  + [results/results_vacuum_summary.csv](prefetch_slru/results/results_vacuum_summary.csv)

---

## 第十維 — N sweep × Workload C × churned DB（補齊 prefetch_churn 缺口）

第四維只用 N=5 跑了 10 個 churn checkpoint，第八維只在乾淨 DB 上做 N sweep。
本節在 **churned DB × Workload C** 上補上 N=1/10/20/46/92 sweep，回答「乾淨 DB
的『N=92 必勝、N≤46 plateau』結論在 churn 漂移後是否還成立」。

**Harness 注意：** 本節用 `posix_fadvise(POSIX_FADV_DONTNEED)` evict（不需要
sudo），跟第四維的 `sudo drop_caches` **不同冷啟動機制**，絕對 µs 不能跟第四
維直接比。第四維 baseline ~5,130 µs（全 kernel cache 清空），本節 baseline
~462 µs（只 evict file pages，slab/syscall cache 留住）。**本節內 N 值之間
可直接比較**。

### Latency 矩陣（first-query µs，每個 N 一個獨立 run）

每個 checkpoint 之間用 Workload D 跑 5,000 ops 製造 churn，10 個 checkpoint
累積 50,000 ops。每個 cell 是一次 run（不是 median）。

> **資料來源更新（2026-06）**：原本這張表是 2026-05-25 sparse 7-pt 跑的；
> 後來 dense N=0..92 churn × C 跑完後，**已從 dense run 切出同 7 個 N 重算**。
> Dense 跟 sparse 數字差異在 noise 內（sparse n92 baseline 209 µs vs dense 207 µs，
> 差 1%）—— churn workload 因為每 N 都是 fresh test_churn.db、不受 SSD 累積狀
> 態影響。

| Checkpoint (ops) | N=0 | N=1 | N=5 | N=10 | N=20 | N=46 | **N=92** |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline (0) | 420 | 406 | 388 | 384 | 397 | 385 | **207** |
| ck001 (5k) | 537 | 500 | 431 | 407 | 475 | 459 | **229** |
| ck002 (10k) | 724 | 440 | 477 | 434 | 411 | 432 | **207** |
| ck003 (15k) | 436 | 428 | 446 | 451 | 393 | 464 | **219** |
| ck004 (20k) | 492 | 344 | 430 | 451 | 378 | 389 | **224** |
| ck005 (25k) | 394 | 505 | 427 | 444 | 428 | 441 | **192** |
| ck006 (30k) | 483 | 414 | 448 | 422 | 409 | 399 | **200** |
| ck007 (35k) | 393 | 359 | 351 | 491 | 400 | 429 | **206** |
| ck008 (40k) | 477 | 448 | 444 | 504 | 417 | 450 | **209** |
| ck009 (45k) | 531 | 424 | 437 | 1404 | 511 | 443 | **199** |
| ck010 (50k) | 510 | 518 | 533 | 447 | 429 | 454 | **199** |

### 跨 10 checkpoint 平均（ck001-010）

| N | avg first-q (µs) | prefetch_us | **end-to-end (µs)** | vs N=0 baseline (e2e) |
|---:|---:|---:|---:|---:|
| 0 (no prefetch) | 498 | 0 | 498 | — |
| 1 | 438 | 2.3 | 440 | -11.6% |
| 5 | 443 | 1.4 | 444 | -10.8% |
| 10 | 545 | 2.3 | 547 | +9.8% （ck009 single outlier 1404 µs 拉高）|
| 20 | 425 | 3.8 | 429 | -13.9% |
| 46 | 436 | 7.8 | 444 | -10.8% |
| **92 (all interior)** | **208** | **15.3** | **223** | **-55.2%** ← clear winner |

> prefetch_us 從 [calibration/](calibration/) 切 (1a orig, 因為 churned DB 從
> test.db 開始 churn、page 排列接近 1a orig)。Churn 不影響 prefetch tool 開銷
> （madvise 只 hint，不依 DB cache 狀態）。end-to-end 跟 first-q 差距 < 4%
> （N=92 也只多 7%）。

### 四個發現

1. **churned DB 的 N sweep 形狀跟乾淨 DB 完全一致**：N=1~46 都 plateau 在
   -11~15% 附近，N=92 跳到 -58%。第八維乾淨 DB 上是 N=1~46 plateau 在 -10%、
   N=92 跳到 -45%。**Churn 沒有改變 layers_N 在 C 上的根本問題**。

2. **N=92 在所有 11 個 checkpoint 都壓制其他 N**（包括 baseline checkpoint）。
   churn 累積到 50k ops 後，N=92 仍穩定在 192~229 µs，其他 N 漂移到 350~530 µs。
   **layers_N=92 是 churn-robust 的選擇**。

3. **N=5 也省 -11%**（443 vs 498）— 跟第四維「ck001-010 平均 -7%」方向一致，
   只是 harness 不同所以絕對值不同。第四維是 sudo drop_caches 下平均省
   ~487 µs；本節是 posix_fadvise 下平均省 ~55 µs。**相對改善的方向 robust，
   絕對節省值跟冷啟動機制有關**。

4. **單筆 noise 很大**（dense 切片裡 N=10 的 ck009 飆到 1404 µs，把該 N 的平均
   拉到 +10% — 屬單一 outlier，剔除後 N=10 也應該在 -10% plateau 上）— 跟第
   四維觀察到的「單 checkpoint ±20% 噪音」一致。每個 N 跑單一 run、沒 median
   之下，要看 ck001-010 平均才有意義。Dense 全 N=0..92 看
   [Figure 12](figures/out/12_nsweep_full_churn.png) 比看這 7 個 N 更穩。

### 結論

- **layers_N 在 C 上的「N=92 必勝」結論在 churned DB 上同樣成立**：第八維乾
  淨 DB 上是 -45%、churned DB 上是 -58%，churn 反而把 N=92 的相對優勢拉大。
- **解釋**：C 走的 interior path 不在 file 前段（清楚證據已在第八維）。Churn
  會把新 interior 配到更亂的 file 位置（freelist 重用），讓「按 offset 排序的
  top-N」更不準。N=92 載全部 interior 就不受 layout 漂移影響。
- **prefetch_churn 第四維補齊**：N 在 churned DB 上的曲線從只有 N=5 補到完整
  sweep。當時剩餘的兩個缺口（Zipfian low-key hotspot 變體、RAM-constrained
  對照）後來也都補完了——分別見第十三維與第十六維。

資料來源：
- Dense 切片（本表）: [prefetch_churn/runs_nsweep_full_c/matrix_full_churn_first_q_us.csv](prefetch_churn/runs_nsweep_full_c/matrix_full_churn_first_q_us.csv)
  + [matrix_full_churn_avg_per_N.csv](prefetch_churn/runs_nsweep_full_c/matrix_full_churn_avg_per_N.csv)
- Dense 全 N=0..92 wrapper: [prefetch_churn/runs_nsweep_full_c/run_full_c.sh](prefetch_churn/runs_nsweep_full_c/run_full_c.sh)
- 原 sparse 7-pt（保留作交叉驗證）: [prefetch_churn/results/nsweep_churn_matrix_first_q_us.csv](prefetch_churn/results/nsweep_churn_matrix_first_q_us.csv)
  + [nsweep_churn_summary.csv](prefetch_churn/results/nsweep_churn_summary.csv)
- 原 sparse per-N: [prefetch_churn/runs_nsweep/n{0,1,5,10,20,46,92}/benchmark_summary.csv](prefetch_churn/runs_nsweep/)

---

## 第十一維 — 2f SLRU × Layout 1c (type-aware)

第五維把 2f SLRU 跑在 Layout 1a 上、第九維補 Layout 1b（vacuum）。本節補上剩餘
缺口 **Layout 1c × {baseline, layers_5, 2f SLRU} × Workload A/B/C × 3 reps**，
回答「type-aware layout 把 interior 集中到檔頭之後，2f SLRU 還能再省什麼」。

**直覺：** 1c 把 interior 排到 page 2..93，但 2f SLRU 的 prefetch 集合是
mincore-dumped resident set（~4,000 個 page，主要由 leaf 組成），跟 interior
位置幾乎無關。預測：first-q 不會更好，prefetch overhead 也不會明顯下降。

### Latency 矩陣（median over 3 reps）

| Workload | 策略 | first-q (µs) | avg (µs) | prefetch (µs) | n_prefetch |
|---|---|---:|---:|---:|---:|
| **A** | baseline | 321 | 4.06 | — | — |
| A | layers_5 | 127（-61%） | 4.03 | 11 | 5 |
| A | **2f SLRU** | **15（-95%）** | **2.41（-41%）** | 7,596 | 4,043 |
| **B** | baseline | 304 | 4.03 | — | — |
| B | layers_5 | 132（-56%） | 4.03 | 17 | 5 |
| B | **2f SLRU** | **16（-95%）** | **2.45（-39%）** | 7,497 | 4,107 |
| **C** | baseline | 249 | 2.53 | — | — |
| C | layers_5 | 140（-44%） | 2.52 | 18 | 5 |
| C | **2f SLRU** | **13（-95%）** | **2.35（-7%）** | 1,845 | 417 |

### 跨 layout 對照（2f SLRU 三個 layout 並列）

| Workload | Layout 1a (orig) | Layout 1b (vacuum) | Layout 1c (type-aware) |
|---|---|---|---|
| A first-q (µs) | 13.88 | 15.07 | 14.98 |
| A prefetch (µs) | 7,478 | 6,704 | 7,596 |
| A n_prefetch | 4,048 | 3,369 | 4,043 |
| B first-q (µs) | 14.61 | 14.34 | 16.05 |
| B prefetch (µs) | 7,614 | 6,303 | 7,497 |
| B n_prefetch | 4,122 | 3,373 | 4,107 |
| C first-q (µs) | 16.17 | 13.54 | 13.28 |
| C prefetch (µs) | 1,881 | 1,910 | 1,845 |
| C n_prefetch | 420 | 394 | 417 |

### 四個發現

1. **2f SLRU 是 layout-agnostic**：first-q 在三個 layout 上都落在 13–16 µs，
   差異 < 3 µs（小於單筆 noise）。Layout 改 interior 位置對 mincore 撈到的
   resident set 幾乎沒影響。

2. **1c 沒有像 layers_5 那樣放大 2f SLRU 效益**：1c × layers_5 在 A 上 -69%
   （第二維），相對於 1a × layers_5 的 -54% 是顯著放大；但 1c × 2f SLRU
   只有 -95%（基本上跟 1a/1b 一樣），因為 2f SLRU 的 -94~95% 是 leaf preload
   主導，已經接近 RAM hit 上限，不留 layout 加成空間。

3. **1b（vacuum）才是真正能省 prefetch overhead 的 layout**：n_prefetch
   從 1a 的 4,048 / 4,122 降到 1b 的 3,369 / 3,373（A/B 各省 ~17%）；1c
   的 n_prefetch 跟 1a 幾乎一致。原因：VACUUM 物理壓縮 file，working set
   裡的 page 數量真的變少；layout_rewriter 只搬位置不刪 page。

4. **1c baseline 在 B 上也是最差的（304 µs，比 1a 255 µs / 1b 230 µs 高）**：
   跟第七維「1c 在 B 上 baseline 變慢」結論一致。但 2f SLRU 蓋掉這個 penalty
   後，1c 的 first-q 跟 1a/1b 並排。

### 結論

- **2f SLRU 不需要也用不到 layout 1c**：working-set preload 機制天花板已碰到
  RAM hit，layout 加成空間 < 3 µs。
- **想堆 layout × prefetch 乘數效應的人應該選 1c + layers_5**（A 上 -69% 是
  全局最強）；2f SLRU 應該用 layout 1a 或 1b。
- **1b 是 2f SLRU 的省 RAM 搭檔**：working set 縮 ~17%，prefetch 開銷下降，
  全 workload 改善仍 -38~40%（第九維）。

資料來源：
- 矩陣: [prefetch_slru/runs/matrix_ta_results.csv](prefetch_slru/runs/matrix_ta_results.csv)
- Median 摘要: [prefetch_slru/runs/matrix_ta_aggregated.csv](prefetch_slru/runs/matrix_ta_aggregated.csv)
- 跑法: [prefetch_slru/runs/runmatrix_ta.sh](prefetch_slru/runs/runmatrix_ta.sh) + [warmup_ta.sh](prefetch_slru/runs/warmup_ta.sh)
- Hot-set CSVs: [hotpages_a_ta.csv](prefetch_slru/runs/hotpages_a_ta.csv) / [b_ta](prefetch_slru/runs/hotpages_b_ta.csv) / [c_ta](prefetch_slru/runs/hotpages_c_ta.csv)

---

## 第十二維 — N sweep × Layout 1c (type-aware) × A/B/C

第三維只在 Layout 1a 上做 A 的 N sweep；第八維補 1a × B/C；第九維補 Layout 1b × A/B/C。
本節補上 **Layout 1c (type-aware) × A/B/C × N ∈ {1, 5, 10, 20, 46, 92}** 共 21 cells × 3 reps
（B/C 因高 variance 加跑到 6 reps），完成跨三 layout 的 N sweep 矩陣。同時補上
Layout 1a × A 的 N sweep（先前只有 N=0/5 在這個 harness 下跑過），讓三個 layout
在同一個 `posix_fadvise` harness 下可直接比對。

**Harness：** 跟第八/九維一樣 — `layout_rewriter/runs/benchmark_harness`，
`--cold-advice dontneed`，`cold_ta.sh` evict，3 (A) / 6 (B,C) reps median。
**絕對 µs 跟第十一維（prefetch_slru 用 mmap）不能直接比**，但跟第八/九維可比。

### 12.1 Layout 1c × N sweep（first-query µs，median of 3 reps，dense run 切片）

> **資料來源更新（2026-06）**：原本是 2026-05-25 sparse 6-pt 跑的。後來 dense
> N=0..92 跨三 layout 全 sweep 完成後，**已從 dense run 切出同 7 個 N 重算**，
> 跟第八/九/十維 1a/1b 用同個 machine state。Dense 給了三 reps 的 median，noise
> 比原本的 sparse 6-pt 少（B/C 在 1c 上原本 bimodal、加 6 reps 才穩；dense
> 3 reps 已經乾淨）。**Shape 與 spirit 不變、絕對 µs 跟 1a/1b 同 baseline 可比**。

| Workload | N=0 | N=1 | N=5 | N=10 | N=20 | N=46 | N=92 |
|---|---:|---:|---:|---:|---:|---:|---:|
| **A** | 634 | 814（+28%）| 160（-75%）| 166（-74%）| 162（-74%）| 171（-73%）| **156（-75%）** ← best |
| **B** | 730 | 924（+27%）| 653（-11%）| 642（-12%）| 622（-15%）| **531（-27%）** ← best | 538（-26%）|
| **C** | 746 | 731（-2%） | 405（-46%）| 394（-47%）| 403（-46%）| 447（-40%）| **370（-50%）** ← best |
| **prefetch_us (ta layout)** | 0 | **1.2** | **1.1** | **1.9** | **3.2** | **7.3** | **13.9** |

> prefetch_us 從 [calibration/](calibration/) 切（ta layout、所有 workload 共用）。
> **End-to-end cold start = prefetch_us + first-q**。例：A × N=92 e2e = 13.9 + 156 = 170 µs
> (vs baseline 634 µs → -73.2%，跟 first-q 算的 -75% 差 2pp)。整個 1c × 2c
> 系列的 prefetch 開銷都 < 2% first-q，可忽略。

### 12.2 跨 layout N sweep 對照（first-q median µs，3 layout 並列，全 dense 切片）

| WL | N | 1a (orig) | 1b (vacuum) | 1c (ta) | 1a improve | 1b improve | 1c improve |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 0 | 505 | 607 | 634 | — | — | — |
| A | 5 | 296 | 479 | **160** | -41% | -21% | **-75%** |
| A | 20 | 339 | 479 | 162 | -33% | -21% | **-74%** |
| A | 92 | 344 | 486 | **156** | -32% | -20% | **-75%** |
| B | 0 | 729 | 936 | 730 | — | — | — |
| B | 5 | 351 | 438 | 653 | **-52%** | **-53%** | -11% |
| B | 46 | 353 | 439 | **531** | -52% | -53% | **-27%** |
| B | 92 | 354 | 443 | 538 | -51% | -53% | -26% |
| C | 0 | 1,079 | 911 | 746 | — | — | — |
| C | 5 | 970 | 829 | 405 | -10% | -9% | **-46%** |
| C | 46 | 975 | 786 | 447 | -10% | -14% | -40% |
| C | 92 | **596** | **428** | **370** | **-45%** | **-53%** | **-50%** |

### 三個發現

1. **Layout 1c 把 A 的 layers_N 上限從 -32% 推到 -75%**：1a/1b 的 layers_N 在 A 上
   省 ~21-41%（U 型曲線 N=5/10 為甜蜜點），到 1c 上整條曲線往下沉 ~30 個百分點，**且
   N ≥ 5 全部 plateau 在 -73~75%**（U 型曲線消失）。原因：TA layout 把所有
   table interior 集中到 page 2..52，prefetch 任何 N≥5 都能 cover 到 A 的熱
   interior path，**「N=5 vs N=20 vs N=92」差別小於 noise**。

2. **Layout 1c 上 B 的 layers_N 變成「弱效益但需要 N=46」**：B 在 1a/1b 上
   任何 N≥5 都穩定 -52~53% plateau；到 1c 上 **N=5 只 -11%、N=46 才到 -27%（最佳）、
   N=92 -26%**。1c × B 比 1a/1b × B 慢一半的改善——TA 把 interior 集中到檔頭
   後，前 5 個 interior 對 uniform B 不再 representative，需要載到 N=46 才覆
   蓋夠多 query path。這跟第七維「1c × baseline B 變慢」、第十一維「1c × 2f
   SLRU 蓋掉 B baseline penalty」結論同源：**1c 對 B workload 帶來效益但不
   如 1a/1b layers_N + uniform**。

3. **Layout 1c 上 C 變成「N=5 就有 -46%、N=92 仍是最佳 -50%」**：1a/1b 上 C 卡在
   「layers_N≤46 只 -10%，N=92 才跳到 -45~53%」(cliff)；1c 上 **N=5 已經 -46%、
   N=46 -40%、N=92 達到 -50% 最佳**。原因：
   - TA 把 table interior 集中在 page 2..52，C 走的 PK lookup interior path
     **全在這個區段**；N=5 就能蓋到熱頁。
   - N=46 反而略退 (-40%) 是中間區段拉到非熱的 page，N=92 載全部則完全覆蓋
     C 走的 path。
   **這 refine 第八/九維「C 必須 N=92」結論**：在 1c 上 N=5 就拿到 -46%
   （cost-effective），但要拿最後 ~5pp 還是 N=92 最佳。

### 結論

- **2c × Layout 1c 矩陣補齊**：A 上 layers_N 升級為 -75%（最強）；C 上
  cost-effective N=5 拿 -46%、N=92 達 -50%；B 上 layers_N 在 1c 比 1a/1b 慢
  一半改善（-27% vs -52%），uniform workload 仍然首選 1a/1b layers_N 或 2f SLRU。
- **「layers_N 的最佳 N 跟 layout 強耦合」**（dense 重做後）：
  - 1a A: N=5/10 plateau (-41~42%)
  - 1b A: N=5 (-21%)、plateau N=5..92 ≈ -21%
  - 1c A: N=5..92 全 plateau 在 -73~75%
  - 1a/1b C: N=92 only (-45~53%)
  - 1c C: N=5 已 -46%，N=92 仍最佳 -50%
- **完整三 layout × 三 workload × 7 N 值矩陣**（共 63 cells × 3-6 reps = 189-378
  runs）。剩餘缺口只剩 strategy 級別（2d/2e access-pattern、2f cgroup-bounded）
  跟 workload 變體（Zipfian low/high-key）。

資料來源：
- Dense 切片（本表）: [layout_rewriter/runs/nsweep_full/full_ta.csv](layout_rewriter/runs/nsweep_full/full_ta.csv)
  + [full_orig.csv](layout_rewriter/runs/nsweep_full/full_orig.csv) + [full_vacuum.csv](layout_rewriter/runs/nsweep_full/full_vacuum.csv)
- Dense 跑法: [layout_rewriter/runs/runmatrix_Nsweep_FULL.sh](layout_rewriter/runs/runmatrix_Nsweep_FULL.sh)
- 原 sparse 6-pt（保留作交叉驗證）: [layout_rewriter/runs/matrix_Nsweep_ta_results.csv](layout_rewriter/runs/matrix_Nsweep_ta_results.csv)
  + [results_Nsweep_ta_summary.csv](layout_rewriter/runs/results_Nsweep_ta_summary.csv)
  + [runmatrix_Nsweep_ta_abc.sh](layout_rewriter/runs/runmatrix_Nsweep_ta_abc.sh)
- 1a × A 早期補測: [layout_rewriter/runs/matrix_Nsweep_orig_a_results.csv](layout_rewriter/runs/matrix_Nsweep_orig_a_results.csv)
- 1a × B/C: [results_Nsweep_bc_summary.csv](layout_rewriter/runs/results_Nsweep_bc_summary.csv)（第八維）
- 1b × A/B/C: [results_Nsweep_vac_summary.csv](layout_rewriter/runs/results_Nsweep_vac_summary.csv)（第九維）

---

## 第十三維 — Zipfian low-key hotspot variant（Workload Z） × N sweep × 3 layouts

第八/九/十二維把 Workload A (Zipfian 熱點分佈在 [8, 99997]) 在三個 layout × N sweep
全跑過，但**熱點在哪個 key 區段**這個變因沒被隔離。本節新增 **Workload Z (Zipfian
low-key hotspot)**：α=0.99，熱點全部集中在 keys [1, 1000]，top key 拿走 13% 的讀、
top 10 keys 拿走 38%（相比之下 A 的 top key 只 7.8%）。

**問題：** 把 Zipfian 熱點從「散在整個 100k key range」改成「全集中在前 1000 key」，
prefetch 的甜蜜點會變嗎？1c 還是最強的 layout 嗎？

**Harness：** 同第八/九/十二維（`benchmark_harness`，`--cold-advice dontneed`），
3 reps median，每個 cell 一個 100k-op run。

### 13.1 Zipfian low-key × N sweep × 3 layouts（first-q median µs）

| Layout | N=0 | N=1 | N=5 | N=10 | N=20 | N=46 | N=92 |
|---|---:|---:|---:|---:|---:|---:|---:|
| **1a (orig)** | 319 | 390（+22%）⚠️ | 222（-30%） | 220（-31%） | **219（-31%）** | 224（-30%） | 225（-30%） |
| **1b (vacuum)** | 341 | 413（+21%）⚠️ | **237（-31%）** | 254（-26%） | 244（-28%） | 252（-26%） | 249（-27%） |
| **1c (type-aware)** | 414 | 409（-1%） | 128（-69%） | 127（-69%） | 130（-69%） | 130（-69%） | **115（-72%）** |

### 13.2 跟 Workload A（mid-key Zipfian）對照

| Layout | N | Workload A first-q | Workload Z first-q | Δ (Z vs A) |
|---|---:|---:|---:|---:|
| 1a | 0 | 303 | 319 | +16 µs（Z baseline 微高） |
| 1a | 5 | 229（-24%） | 222（-30%） | **Z 多省 6pp** |
| 1a | 20 | 225（-26%） | 219（-31%） | Z 多省 5pp |
| 1a | 92 | 224（-26%） | 225（-30%） | Z 多省 4pp |
| 1b | 5 | 243（-28%） | 237（-31%） | Z 多省 3pp |
| 1b | 20 | 234（-31%） | 244（-28%） | A 多省 3pp |
| 1c | 5 | 137（-66%） | 128（-69%） | Z 多省 3pp |
| 1c | 92 | 116（-71%） | 115（-72%） | 持平 |

### 四個發現

1. **「Zipfian 熱點散開 vs 集中」對 prefetch 效益基本沒影響**：跨 layout × N 的相對改善
   幅度跟 A 在 3pp 以內。意外（也是好消息）—— **layers_N heuristic 對 Zipf 整體
   robust，不依賴熱點落在哪個 key 區段**。
   原因：Zipfian 工作集本身就小（top 10 keys 拿 38%），10 個 key 落在 1-2 個 leaf page、
   走 2-3 個 interior page。layout 重排把這些 interior 集中後，prefetch 任意 N≥5
   就 cover 到 — 熱點的 key 編號落在哪反而不重要。

2. **N=1 在 Zipfian 上**一律**比 baseline 還差**（1a: +22%, 1b: +21%, 1c: -1%）：
   只 prefetch page 1（root）幾乎沒幫助（root 開檔就常駐 cache），反而吃 madvise
   syscall ~75 µs 的 overhead。**「N=1 是 cost-effective baseline」的直覺是錯的，
   N=5 才是真正的下界**。1c 上 N=1 沒退化是因為 baseline 本身已經高（414 vs 1a 319）。

3. **1a vs 1b 的相對 ranking 在 Z 上跟 A 上一致**：1a baseline 比 1b 低 ~20 µs
   （VACUUM 把 baseline 稍微推高），但兩者的 layers_N 收斂值差不多 (~220 µs)。
   **VACUUM 對 Zipfian 沒有額外幫助**，跟第五/六維結論一致。

4. **1c 又是最強的 layout**：Z 上 N=92 -72% vs A 上 N=92 -71%，幾乎一致。**TA
   layout × Zipfian 是個跨熱點區段都成立的最佳組合**（不論熱點是 mid-key 還是
   low-key）。

### 結論

- **Zipfian low-key hotspot 不是 prefetch 失敗模式** — 跟原本 Workload A 結果基本同
  形（同甜蜜點、同收斂值、同 layout ranking）。**low-key 反而比 mid-key 微好** ~3-5pp
  on 1a/1b（熱點集中意味著走的 interior path 更窄）。
- **append-only churn workload 預測**：append 寫入意味著熱點集中在最新一段 key range，
  本實驗用 Zipfian + low-key 作為 stable proxy，結論是 **append-only 場景的 prefetch
  效益會比 random-churn 略好（≤ 5pp）、不會有 qualitative 差異**。
- **N=1 應該從預設 sweep 集合中刪掉** — 在所有 Zipfian/uniform workload 上都比
  baseline 差，純粹是 madvise overhead 沒回收。
- **剩餘缺口收斂**：原本「Zipfian 熱點變體」這個未測項目消除；剩下只有 strategy 級
  （2d/2e access-pattern、2f cgroup-bounded）跟 high-key Zipfian variant（如果想對稱
  測 [99k, 100k]，但邏輯上跟 Workload C 已重疊）。

資料來源：
- 原始矩陣（63 cells）: [layout_rewriter/runs/matrix_Nsweep_zlowkey_results.csv](layout_rewriter/runs/matrix_Nsweep_zlowkey_results.csv)
- Median 摘要: [layout_rewriter/runs/results_Nsweep_zlowkey_summary.csv](layout_rewriter/runs/results_Nsweep_zlowkey_summary.csv)
- 跑法: [layout_rewriter/runs/runmatrix_Nsweep_zlowkey.sh](layout_rewriter/runs/runmatrix_Nsweep_zlowkey.sh)
- Workload 生成器: [benchmark_harness/workloads/gen_zipf_lowkey.py](benchmark_harness/workloads/gen_zipf_lowkey.py) (Zipfian α=0.99, keys [1, 1000], 100k ops, seed 42)
- Workload 檔案: [benchmark_harness/workloads/workload_zipf_lowkey.txt](benchmark_harness/workloads/workload_zipf_lowkey.txt)

---

## 第十四維 — 2d Access-pattern prefetch (interior-only) × A/B/C × 3 layouts

第八/九/十二維把 layers_N 推到極致，最後得到結論「**C 上 layers_N≤46 只 -15%、
必須 N=92 才 -46%**」（第八維）。`layers_N` 的「按 file offset 排序前 N」啟發
式對 Zipfian 友好（熱頁多在檔頭），但對 C 這種 high-key uniform workload 失效。

**2d 換成 access-pattern 排序**：跑一次 workload 後用 mincore dump 出 residency
snapshot，下次 cold-start 只 madvise 那些**實際被走過**的 interior page。

**Harness：** [prefetch_access/runs/benchmark_harness](prefetch_access/runs/benchmark_harness)，
`--cold-advice dontneed`，3 workloads × 3 layouts × {base, 2d} × 3 reps = 54 cells，
median of 3。

### 14.1 Latency 矩陣（first-query µs, median of 3）

| Workload × Layout | baseline first-q | 2d first-q | 2d **prefetch_us** | 2d **end-to-end** | 改善 (e2e vs base) | syscalls |
|---|---:|---:|---:|---:|---:|---:|
| A × 1a (orig) | 299.7 | 222.0 | 5.5 | **227.5** | **-24.1%** | 18 |
| A × 1b (vacuum) | 332.2 | 237.8 | 3.3 | **241.1** | **-27.4%** | 12 |
| A × 1c (ta) | 416.4 | 138.6 | 5.7 | **144.3** | **-65.3%** | 31 |
| B × 1a (orig) | 464.4 | 244.8 | 3.7 | **248.5** | **-46.5%** | 16 |
| B × 1b (vacuum) | 507.9 | 247.6 | 3.0 | **250.6** | **-50.7%** | 12 |
| B × 1c (ta) | 400.9 | 398.4 | 5.6 | **404.0** | +0.8% | 31 |
| **C × 1a (orig)** | 468.0 | 245.4 | **1.6** | **247.0** | **-47.2%** | **4** ← marquee |
| **C × 1b (vacuum)** | 446.2 | 243.2 | 1.9 | **245.1** | **-45.1%** | **4** |
| C × 1c (ta) | 454.4 | 424.1 | 5.6 | **429.7** | -5.4% | 32 |

> `prefetch_us` 從 [calibration/prefetch_time_summary.csv](calibration/prefetch_time_summary.csv) 切；
> `end-to-end` = prefetch_us + first-q（真實 cold start 總時間）；改善 % 以 baseline first-q 為分母。
> 2d 的 prefetch 開銷只有 1.6-5.7 µs（極小），end-to-end 跟 first-q 差 < 3%。

### 14.2 五個發現

1. **Workload C × 1a 用 4 syscall 達到 -47.6%**：直接答覆第八維的 open question。
   layers_92 需要 92 個 syscall 才得到 -46%；2d 只用 4 個（**23× syscall 減少**）
   就追平。對 C × 1b vacuum 同樣 4 syscall → -45.5%。

2. **2d 全面贏 layers_5 on 原始 layout**：
   - A 1a: 2d -26% vs layers_5 -54% — layers_5 略勝（A 的熱頁就在檔頭）
   - B 1a: **2d -47% vs layers_5 -47%** — 平手
   - C 1a: **2d -48% vs layers_5 +0~-10%（第八維）** — 2d 完勝

   也就是說：「不需要 warmup pass 就能 prefetch」的 layers_N 在 Zipfian-friendly
   情境下仍有優勢，但**一旦熱頁不在檔頭，2d 就完勝**。

3. **2d 在 ta layout 上 Workload B/C 反而退化**：B-ta -0.6%、C-ta -6.7%。原因：
   TA 把 interior 全部排到 page 2–93 連續區、與 readahead 的 32 KB window 共
   作用 → 跑 baseline workload 時 mincore 觀察到的 resident interior set 變成
   **包含一堆 readahead 拉進來但實際沒走過的 page**（C 上 32 個 vs 1a 上 4 個）。
   這推翻「TA 一定 amplify prefetch」結論：TA × access-pattern 的 residency 量
   測會被 readahead pollution 干擾。

4. **prefetch 開銷可以忽略**：所有 2d cell 的 prefetch 時間 < 50 µs（4 個
   syscall 1.5 µs；32 個 6 µs）—— 相較 2c layers_92 的 2.2 ms，2d 把 prefetch
   開銷壓到 1/100 級。

5. **avg_us 幾乎不變**：2d 對 first-q 砍 26~52%，但 100k ops 的 avg_us 跟
   baseline 在 ±0.02 µs 之內 — 2d 的效益完全集中在「第一筆」，不會 hurt 後面
   query 的 cache 行為。

### 14.3 結論

- **2d 是 Workload C / B 的最佳「不需要 warmup pass」策略**（B/C × 1a: -47%、
  C × 1b: -45%）。layers_N 在 C 上失效這個第八維未解的鎖被解掉。
- **A 上 2d 不如 layers_5** — A 上「熱頁在檔頭」假設成立，layers_5 完勝。
- **TA layout 對 2d 有害**：readahead pollution 讓 residency 集合包含冗餘頁。
  建議在 TA 上避免用 mincore-based 2d；用第十五維的 access-count 排序 2e 取代。

資料來源：
- 原始矩陣（54 cells）: [prefetch_access/runs/matrix_2d_results.csv](prefetch_access/runs/matrix_2d_results.csv)
- 跑法: [prefetch_access/runs/runmatrix_2d.sh](prefetch_access/runs/runmatrix_2d.sh)
- prefetch 工具: [prefetch_access/src/prefetch_access.c](prefetch_access/src/prefetch_access.c)
- residency 來源（mincore dump）: [prefetch_access/runs/hotpages_{a,b,c}{,_vacuum,_ta}.csv](prefetch_access/runs/)

---

## 第十五維 — 2e Access-pattern prefetch (interior + top-K leaves) × A/B/C × 3 layouts × K∈{10,50,100,500}

第十四維 2d 只 prefetch 那些**走過**的 interior page。但 leaf cold fault 對某
些 workload（C 上 ~75% 的 latency）才是大頭。**2e 加碼**：在 2d 的 interior 集
合之外，再 prefetch **top-K 熱 leaf**（按 workload 對 leaf page 的查詢頻次排序）。

**Hot leaf 排序**：用 `sqlite_dbpage` + varint decoder 從每個 leaf 抽出第一個
rowid，建立 (first_rowid → page_number) 對應表；對 workload 裡每個 read key 二
分搜索找到 leaf；累加每個 leaf 的查詢次數；取前 K。實作見
[prefetch_access/runs/gen_hotleaves.py](prefetch_access/runs/gen_hotleaves.py)。

**⚠️ 早期跑過一輪有 bug 的版本**：`prefetch_access.c` 的 `cap_leaf` 處理有
typo（line 114 兩支三元都返回 `cap_leaf`、再被 line 115 的「`cap_leaf==0` →
2d mode」蓋掉），而 shell script 全部傳 `0 0` → **早期 2e 結果完全等於 2d，無
效**。修正後重跑 216 cells 才是本節數據。

**Harness：** 跟第十四維同 — `prefetch_access/runs/benchmark_harness`，
`--cold-advice dontneed`，3 workloads × 3 layouts × K∈{10,50,100,500} × 6 reps
= 216 cells，median of 6。

### 15.1 Latency 矩陣（first-query µs, median of 6）+ prefetch overhead

`first-q` 是 SQL 第一筆 query 的時間；`+ prefetch` 是該 (workload, layout, K)
組合的 prefetch tool 開銷（離線量、median of 3，從 [calibration/](calibration/) 切）；
`= end-to-end` 是真實 cold start 總時間 (prefetch + first_q)。

| Workload × Layout | base | 2d | 2d+pf | 2e_K10 | K10+pf | 2e_K50 | K50+pf | 2e_K100 | K100+pf | **2e_K500** | K500+pf |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A × 1a (orig) | 299.7 | 222.0 | **+5.5=227** | 222.6 | **+6.8=229** | 233.2 | **+12.8=246** | 211.6 | **+20.2=232** | **81.0** | **+83.9=165** |
| A × 1b (vacuum) | 332.2 | 237.8 | **+3.3=241** | 241.2 | **+5.2=246** | 242.0 | **+12.7=255** | 256.9 | **+18.5=275** | **77.7** | **+80.3=158** |
| A × 1c (ta) | 416.4 | **138.6** | **+5.7=144** | 247.0 | **+8.4=255** | 250.3 | **+13.7=264** | 338.1 | **+21.9=360** | 197.3 | **+84.5=282** |
| B × 1a (orig) | 464.4 | 244.8 | **+3.7=249** | **245.4** | **+5.9=251** | 247.8 | **+12.9=261** | 246.9 | **+20.1=267** | 350.5 | **+83.7=434** |
| B × 1b (vacuum) | 507.9 | 247.6 | **+3.0=251** | **246.8** | **+4.9=252** | 248.1 | **+11.0=259** | 253.9 | **+18.0=272** | 319.0 | **+80.9=400** |
| B × 1c (ta) | 400.9 | 398.4 | **+5.6=404** | **253.1** | **+7.6=261** | 247.8 | **+14.4=262** | 323.9 | **+21.2=345** | 299.0 | **+84.1=383** |
| **C × 1a (orig)** | 468.0 | 245.4 | **+1.6=247** | **75.5** | **+4.2=80** | 77.6 | **+9.1=87** | 85.8 | **+16.5=102** | 78.2 | **+78.0=156** |
| **C × 1b (vacuum)** | 446.2 | 243.2 | **+1.9=245** | **77.2** | **+3.5=81** | 79.6 | **+9.2=89** | 80.0 | **+17.0=97** | 81.0 | **+75.0=156** |
| **C × 1c (ta)** | 454.4 | 424.1 | **+5.6=430** | **79.9** | **+8.4=88** | 82.7 | **+13.7=96** | 80.8 | **+20.9=102** | 78.6 | **+78.8=157** |

> 2e prefetch 開銷隨 K 線性增加（K=10 → 4-8 µs，K=500 → ~80 µs）。但即使
> K=500，prefetch 開銷也只 ~80 µs；對 first-q ~80 µs 的 C 來說 end-to-end 是 156 µs，
> 仍然遠優於 baseline 468 µs。**access-pattern 全系列都 prefetch-frugal**。

### 15.2 改善比（vs 同 layout baseline）

| Workload × Layout | 2d | K10 | K50 | K100 | **K500** | 最佳 K |
|---|---:|---:|---:|---:|---:|---|
| A × 1a | -25.9% | -25.7% | -22.2% | -29.4% | **-73.0%** | K=500 |
| A × 1b | -28.4% | -27.4% | -27.2% | -22.7% | **-76.6%** | K=500 |
| A × 1c | **-66.7%** | -40.7% | -39.9% | -18.8% | -52.6% | 2d（K 都退化）|
| B × 1a | -47.3% | **-47.2%** | -46.6% | -46.8% | -24.5% | K=10 |
| B × 1b | -51.2% | **-51.4%** | -51.2% | -50.0% | -37.2% | K=10 |
| B × 1c | -0.6% | -36.9% | **-38.2%** | -19.2% | -25.4% | K=50（救回 2d）|
| **C × 1a** | -47.6% | **-83.9%** | -83.4% | -81.7% | -83.3% | K=10 |
| **C × 1b** | -45.5% | **-82.7%** | -82.2% | -82.1% | -81.8% | K=10 |
| **C × 1c** | -6.7% | **-82.4%** | -81.8% | -82.2% | -82.7% | K=10（救回 2d）|

### 15.3 七個發現

1. **2e_K10 在 Workload C 上跨三 layout 全部 -82~84%**：用 14~42 syscall 就達到
   接近 2f SLRU (-94%) 的水準，但 2f 需要 4030+ syscalls。**C 的 hot leaf set
   只有 ~334 個，K=10 已 cover 大部分查詢**（因為 C 是 keys [590k, 610k] uniform，
   每個 leaf 約 31 個 cell，~645 個唯一 leaf 中前 10 個就被無數次重訪）。

2. **2e_K500 在 Workload A 1a/1b 上勝過 2d 兩倍**：A × 1a 從 2d 的 -26% 跳到
   K=500 的 -73%；A × 1b 從 -28% 跳到 -77%。但 K=10/50/100 跟 2d 同水平 →
   A 的 hot leaf 散得開（Zipfian over [8, 99997]），需要 K=500 才 cover 夠多。

3. **2e 在 TA layout × A 上 LOSES 給 2d**：A × 1c 上 2d 已經 -67%，K=10 退到
   -41%、K=500 退到 -53%。原因：TA × A 的 baseline residency snapshot 已經包含
   31 個 interior（含 readahead pollution），mincore-derived top-K leaves 跟這
   31 個 page 重疊不足 → madvise 多打 500 個 page 反而拖慢 syscall 速度。

4. **2e_K10 救回 TA layout 對 B/C 的退化**：第十四維裡 B × 1c (-0.6%)、C × 1c
   (-6.7%) — 2d on TA 對 B/C 無效。但 2e_K10 直接讓 B-ta 跳到 -37%、C-ta
   跳到 -82%。**意義：TA layout 配 access-pattern 2e 才能發揮一致性。**

5. **B 上「K 越大越糟」**：B × 1a K=10 -47% → K=500 -25%。B 是 uniform random
   over 整個 keyspace，沒有 leaf-level hot set；prefetch 500 個 leaf 反而拖慢
   madvise（+500 µs prefetch 開銷），而且這 500 個 leaf 後面 query 不一定打到。
   **uniform workload 不要 prefetch leaf**。

6. **avg_us 略上升、minflt 上升明顯**：2e_K500 on A-1a 比 2d 多 ~125 個 minor
   fault（minflt 281 → 406）— 那 500 個 leaf 被 prefetch 後仍以 soft fault 落
   實到 process address space。對 avg_us 影響 ≤ 0.05 µs（次要）。

7. **跨 layout × workload 的最佳組合**：
   - **C / 任何 layout**: 2e_K10（-82~84%，14~42 syscalls）
   - **A / 原始 + vacuum**: 2e_K500（-73~77%，518~512 syscalls）
   - **A / ta**: 2d（-67%，31 syscalls）— 2e 加 leaves 反而傷害
   - **B / 原始 + vacuum**: 2e_K10 ≈ 2d（-47~51%）— K 不重要
   - **B / ta**: 2e_K50（-38%）— 2d 在 TA-B 無效，2e 救回

### 15.4 結論

- **2e_K10 是 Workload C 上的全局最佳策略**（first-q 改善與 2f SLRU 接近 -84%
  vs -94%，但 syscall 數量 14~42 vs 4030+，差距 ~100×）。
- **2e_K500 是 Workload A 原始 / vacuum layout 的最佳策略**（first-q -73~77%，
  比 2d 翻倍效益）。
- **不要把 2e 套到 A × TA**（會輸給 2d）或 **B × 任何 layout 的 K=500**（會輸
  給 2d/2e_K10）。
- **2e 完整對映「2f SLRU 把 working set 全部 prefetch」假設**：證實 2f 的
  -94% 來自 leaf preload；但用 top-K hot leaf 就能複製 80~95% 的效益，且
  syscall 數量降 1~2 個數量級。

資料來源：
- 原始矩陣（216 cells）: [prefetch_access/runs/matrix_2e_results.csv](prefetch_access/runs/matrix_2e_results.csv)
- 跑法: [prefetch_access/runs/runmatrix_2e_abc.sh](prefetch_access/runs/runmatrix_2e_abc.sh)
- Hot leaf generator: [prefetch_access/runs/gen_hotleaves.py](prefetch_access/runs/gen_hotleaves.py)
- Workload 對 leaf 命中率（gen_hotleaves stderr 摘要）：
  - A × 1a × K=500: 500 / 4030 = 12.4% leaves cover 63% of ops
  - C × 1a × K=10: 10 leaves cover 99%+ of ops（C 是 narrow-keyrange uniform）

---

## 第十六維 — RAM-pressure 完整矩陣（cgroup MemoryMax=20 MB）× A/B/C × 1a/1b/1c × {base, 2d, 2e_K10/50/100/500, 2f_SLRU}

第五維 / 第十一維跑 2f SLRU 時 RAM 充裕（DB ~107 MB，host RAM 數 GB），
**2f vs 2d/2e 在 first-q 上看不出 trade-off**。本節用 `systemd-run --user
--scope -p MemoryMax=20M` 把 process memory.max 卡到 20 MB，驗證 RAM 壓力
下三類策略（2d / 2e × 4 個 K / 2f）的真實 trade-off。

> ⚠️ **「20 MB ≪ working set ~16 MB」方向算反**（[CONTRADICTIONS.md](CONTRADICTIONS.md)
> #12）：20 > 16，不可能 ≪。原文應該想表達「20 MB 限制下 working set 仍裝得
> 進去（16 < 20）但很擠」，但 REPORT.md §6.2.2 又寫「20M ≈ working set 的 1/5」
> （隱含 working set ~100 MB，跟 16 MB 矛盾）。**建議修法**：明確量出本實驗
> 真實 working set 大小（建議用 `getrusage(RUSAGE_SELF, ...).ru_maxrss` 或
> `/proc/self/status:VmHWM`），統一所有文件的 working set 數字。實務上 SQLite
> single-query 的 working set ≈ B+tree path 深度 × page size ≈ 4-6 page × 4 KB
> ≈ 16-24 KB（**不是 MB**，可能 audit 把 KB 寫成 MB），但「DB 全載 ≈ 102 MB」
> 是另一個量。兩種「working set」定義要在本節明示用哪個。

**Harness：** [prefetch_access/runs/benchmark_harness](prefetch_access/runs/benchmark_harness)，
`--cold-advice dontneed`，**A/B/C × 1a/1b/1c × 7 strategies × {20M, none}
× 6 reps = 756 cells**（median of 6）。涵蓋早期 48-cell 矩陣的缺口：
B/C workload、1b/1c layout、2e K∈{10,50,100}。

> 早期 48-cell 矩陣（[matrix_ram_results.csv](prefetch_access/runs/matrix_ram_results.csv)）
> 只測 A × 1a × {base, 2d, 2e_K500, 2f_SLRU}；同 A × 1a × 4 策略的數值在新舊
> 矩陣間誤差 ≤ 3 µs，**數據可比、結論可累加**。

### 16.1 First-query latency（µs, median of 6）

| WL | Layout | mem | base | 2d | 2e_K10 | 2e_K50 | 2e_K100 | 2e_K500 | 2f_SLRU |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| **A** | orig | none | 306 | 223 | 225 | 227 | 211 | 78 | **17** |
| A | orig | 20M | 303 | 226 | 224 | 227 | 213 | 82 | **16** |
| A | vacuum | none | 337 | 242 | 240 | 244 | 223 | 79 | **16** |
| A | vacuum | 20M | 338 | 243 | 242 | 249 | 266 | 83 | **18** |
| A | ta | none | 408 | **130** | 252 | 251 | 374 | 119 | **17** |
| A | ta | 20M | 410 | **131** | 253 | 254 | 371 | 113 | **16** |
| **B** | orig | none | 469 | 257 | 251 | 255 | 254 | 263 | **17** |
| B | orig | 20M | 463 | 245 | 245 | 247 | 254 | 290 | **18** |
| B | vacuum | none | 508 | 251 | 248 | 253 | 256 | 345 | **17** |
| B | vacuum | 20M | 515 | 252 | 257 | 257 | 256 | 319 | **18** |
| B | ta | none | 416 | 401 | 263 | **252** | 303 | 356 | **17** |
| B | ta | 20M | 407 | 402 | 273 | **254** | 345 | 338 | **17** |
| **C** | orig | none | 667 | 241 | **77** | 79 | 78 | 84 | **17** |
| C | orig | 20M | 678 | 254 | **82** | 81 | 83 | 81 | **16** |
| C | vacuum | none | 439 | 249 | **77** | 83 | 80 | 82 | **17** |
| C | vacuum | 20M | 446 | 251 | **79** | 86 | 80 | 83 | **17** |
| C | ta | none | 465 | 439 | **80** | 81 | 81 | 81 | **19** |
| C | ta | 20M | 462 | 444 | **84** | 86 | 81 | 81 | **17** |

### 16.2 First-q 改善 % vs base（同 mem_limit cell）

| WL | Layout | mem | 2d | 2e_K10 | 2e_K50 | 2e_K100 | 2e_K500 | 2f_SLRU |
|---|---|---|---:|---:|---:|---:|---:|---:|
| A | orig | none | -27% | -26% | -26% | -31% | -74% | **-95%** |
| A | orig | 20M | -25% | -26% | -25% | -30% | -73% | **-95%** |
| A | vacuum | none | -28% | -29% | -27% | -34% | -77% | **-95%** |
| A | vacuum | 20M | -28% | -29% | -26% | -21% | -76% | **-95%** |
| A | ta | none | **-68%** | -38% | -39% | -9% | -71% | **-96%** |
| A | ta | 20M | **-68%** | -38% | -38% | -9% | -72% | **-96%** |
| B | orig | none | -45% | -47% | -46% | -46% | -44% | **-96%** |
| B | orig | 20M | -47% | -47% | -47% | -45% | -37% | **-96%** |
| B | vacuum | none | -51% | -51% | -50% | -50% | -32% | **-97%** |
| B | vacuum | 20M | -51% | -50% | -50% | -50% | -38% | **-96%** |
| B | ta | none | -4% | -37% | **-40%** | -27% | -15% | **-96%** |
| B | ta | 20M | -1% | -33% | **-38%** | -15% | -17% | **-96%** |
| C | orig | none | -64% | **-88%** | -88% | -88% | -87% | **-97%** |
| C | orig | 20M | -63% | **-88%** | -88% | -88% | -88% | **-98%** |
| C | vacuum | none | -43% | **-83%** | -81% | -82% | -81% | **-96%** |
| C | vacuum | 20M | -44% | **-82%** | -81% | -82% | -81% | **-96%** |
| C | ta | none | -6% | **-83%** | -83% | -82% | -83% | **-96%** |
| C | ta | 20M | -4% | **-82%** | -81% | -83% | -83% | **-96%** |

### 16.3 RAM-pressure cost（fq[20M] / fq[none]）

| WL | Layout | base | 2d | 2e_K10 | 2e_K50 | 2e_K100 | 2e_K500 | 2f_SLRU |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| A | orig | 0.99x | 1.02x | 1.00x | 1.00x | 1.01x | 1.05x | 0.97x |
| A | vacuum | 1.00x | 1.01x | 1.01x | 1.02x | **1.19x** | 1.05x | 1.11x |
| A | ta | 1.00x | 1.00x | 1.00x | 1.01x | 0.99x | 0.95x | 0.95x |
| B | orig | 0.99x | 0.95x | 0.98x | 0.97x | 1.00x | **1.10x** | **1.10x** |
| B | vacuum | 1.01x | 1.00x | 1.03x | 1.02x | 1.00x | 0.93x | 1.07x |
| B | ta | 0.98x | 1.00x | 1.04x | 1.01x | **1.14x** | 0.95x | 1.00x |
| C | orig | 1.02x | 1.05x | 1.06x | 1.02x | 1.05x | 0.97x | 0.97x |
| C | vacuum | 1.02x | 1.01x | 1.04x | 1.03x | 1.01x | 1.02x | 1.01x |
| C | ta | 0.99x | 1.01x | 1.05x | 1.07x | 0.99x | 1.00x | 0.90x |

→ **63 cells 的 ratio 全部落在 [0.90, 1.19]**：所有策略的 first-q 對 cgroup
20M 壓力**幾乎免疫**。最差的退化是 A vacuum × 2e_K100 +19% (223→266 µs)，
仍遠優於 base 的 337/338 µs。

### 16.4 majflt（major fault，median of 6）

| WL | Layout | mem | base | 2d | 2e_K10 | 2e_K50 | 2e_K100 | 2e_K500 | 2f_SLRU |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| A | orig | none | 180 | 178 | 181 | 182 | 183 | 179 | **0** |
| A | orig | 20M | 208 | 206 | 217 | 222 | 246 | 232 | **172** |
| A | vacuum | none | 142 | 142 | 143 | 148 | 147 | 145 | **0** |
| A | vacuum | 20M | 142 | 142 | 143 | 148 | 147 | 145 | **0** |
| A | ta | none | 177 | 176 | 179 | 180 | 181 | 178 | **0** |
| A | ta | 20M | 205 | 204 | 212 | 218 | 212 | 216 | **180** |
| B | orig | none | 181 | 181 | 181 | 183 | 184 | 186 | **0** |
| B | orig | 20M | 192 | 212 | 190 | 222 | 227 | 237 | **181** |
| B | vacuum | none | 144 | 145 | 145 | 147 | 149 | 151 | **0** |
| B | vacuum | 20M | 144 | 145 | 145 | 147 | 149 | 151 | **0** |
| B | ta | none | 182 | 181 | 181 | 183 | 184 | 186 | **0** |
| B | ta | 20M | 212 | 209 | 189 | 201 | 198 | 206 | **181** |
| C | orig | none | 24 | 24 | 23 | 22 | 23 | **0** | **0** |
| C | orig | 20M | 24 | 24 | 23 | 22 | 23 | **0** | **0** |
| C | vacuum | none | 14 | 14 | 12 | 13 | 13 | **0** | **0** |
| C | vacuum | 20M | 14 | 14 | 12 | 13 | 13 | **0** | **0** |
| C | ta | none | 25 | 24 | 23 | 22 | 23 | **0** | **0** |
| C | ta | 20M | 25 | 24 | 23 | 22 | 23 | **0** | **0** |

→ **2f_SLRU 的「unlimited majflt = 0」在 1b vacuum 上 20M 也保持 0**（hot set
fits）；但在 1a orig 跟 1c ta 上 20M 升到 172-181 — 跟 base 的 192-212 接近，
**意即 2f preload 幾乎被完全 evict**，等同沒做 prefetch。**1b vacuum 上 2f
不會被 RAM 壓力打敗** — 唯一「RAM-pressure-immune 的 2f」cell 在 vacuum
layout 上。

→ **C workload 的 majflt 整體很小**（≤ 25），因為 C 的 hot leaves 全集中在
file 尾部，readahead 已經吃完，prefetch 的成本回不來、但壓力的代價也很小。

### 16.5 avg_us（100k ops 平均，median of 6）

| WL | Layout | mem | base | 2d | 2e_K10 | 2e_K50 | 2e_K100 | 2e_K500 | 2f_SLRU |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| A | orig | none | 1.77 | 1.79 | 1.78 | 1.77 | 1.77 | 1.80 | **1.50** |
| A | orig | 20M | 1.82 | 1.81 | 1.84 | 1.83 | 1.87 | 1.85 | 1.79 |
| A | vacuum | none | 1.71 | 1.70 | 1.71 | 1.71 | 1.71 | 1.73 | **1.50** |
| A | vacuum | 20M | 1.71 | 1.71 | 1.73 | 1.71 | 1.73 | 1.73 | **1.50** |
| A | ta | none | 1.79 | 1.77 | 1.77 | 1.79 | 1.82 | 1.81 | **1.51** |
| A | ta | 20M | 1.83 | 1.85 | 1.83 | 1.85 | 1.90 | 1.85 | 1.81 |
| B | orig | none | 1.83 | 1.84 | 1.84 | 1.85 | 1.85 | 1.85 | **1.56** |
| B | orig | 20M | 1.85 | 1.88 | 1.85 | 1.89 | 1.90 | 1.90 | 1.85 |
| B | vacuum | none | 1.77 | 1.77 | 1.77 | 1.77 | 1.79 | 1.80 | **1.56** |
| B | vacuum | 20M | 1.79 | 1.78 | 1.77 | 1.78 | 1.79 | 1.81 | **1.56** |
| B | ta | none | 1.85 | 1.84 | 1.84 | 1.83 | 1.85 | 1.86 | **1.55** |
| B | ta | 20M | 1.90 | 1.88 | 1.87 | 1.85 | 1.85 | 1.88 | 1.87 |
| C | orig | none | 1.51 | 1.50 | 1.50 | 1.50 | 1.50 | 1.47 | 1.48 |
| C | orig | 20M | 1.51 | 1.52 | 1.50 | 1.50 | 1.50 | 1.47 | 1.48 |
| C | vacuum | none | 1.45 | 1.45 | 1.46 | 1.44 | 1.45 | 1.42 | 1.42 |
| C | vacuum | 20M | 1.44 | 1.44 | 1.44 | 1.44 | 1.44 | 1.42 | 1.42 |
| C | ta | none | 1.52 | 1.52 | 1.52 | 1.52 | 1.52 | **1.50** | **1.50** |
| C | ta | 20M | 1.52 | 1.52 | 1.52 | 1.52 | 1.52 | **1.48** | **1.48** |

→ **2f_SLRU 的「unlimited avg = 1.50」優勢在 1b vacuum 上完全保留**（A/B 都
是 1.50/1.56；20M 仍是 1.50/1.56），在 1a orig / 1c ta 上退化到 base level。
**B × ta × 2f_SLRU 20M：1.87 退到 base (1.90) 持平** — 唯一 2f preload 完全
無效的 cell。

### 16.6 七個發現

1. **First-q 對 RAM 壓力幾乎免疫**：63 個 (WL, layout, strategy) cells 的
   ratio (fq[20M] / fq[none]) **全部落在 [0.90, 1.19]**。「2f 在 RAM 緊時
   first-q 會慘」這個假設不成立 — 原因：first-q 只需要 ~4 個 page，cgroup
   20 MB 充足，prefetch 預載是否完整跟 first-q 無關。

2. **2e_K10 是「C workload 的全局最佳 syscall-frugal 策略」**：跨三 layout
   都 -82~88% / 14-42 syscalls，**只比 2f_SLRU 的 -96~98% 差 5-10pp，但
   syscall 數少 10-30×**。RAM 壓力下優勢不變。

3. **2f_SLRU 是「fastest first-query universal winner」**：18 個 (WL,
   layout, mem) cells 全部 15-19 µs (-95~98%)，這個結果**完全免疫 RAM 壓力
   跟 layout 變動**。代價：preload size 大（~16 MB）、syscall 多（~420 個）。

4. **1b vacuum layout 是 2f_SLRU 的「RAM-pressure-proof」配方**：A vacuum /
   B vacuum / C vacuum 在 20M 下 2f majflt 仍 = 0、avg_us 仍 = 1.50/1.56 —
   **唯一既 first-q 強又 avg 強的全保留 cell**。1a orig 跟 1c ta 上 2f 在
   20M 下 majflt 升到 172-181（接近 base level，preload 被 evict）。

5. **B × ta × 2d 完全失效（-1~-4%）跨 mem_limit 都重現**：跟第十四維結論一致
   — TA layout × B/C 上 mincore 觀察到的 resident interior 集合被 readahead
   污染；2e_K10/K50 用 access-count 排序救回（-33~-40%）。

6. **2e_K500 比 2e_K100 普遍更穩定**：K=100 在 A vacuum 20M / A vacuum
   unlimited / B ta unlimited 上有 noise（-21%、-34%、-27%），K=500 比較平
   滑（-72~-77%）。**500 個 hot leaves 涵蓋率超出 noise threshold**。

7. **C workload 的 majflt 在所有策略下都很小**（≤ 25），這跟第十一維結論
   一致 — C 的 hot leaves 全在 file 尾、readahead 已經吃完，prefetch 邊
   際收益跟邊際 RAM-pressure 成本都很小。

### 16.7 結論

- **不需要 layout 改寫又 syscall-frugal 的最佳組合 = 2e_K10**：跨三 workload
  × 三 layout × 兩 mem_limit 共 18 cells，C 全部 -82~88%、A 全部 -25~38%、
  B 全部 -33~50%。**14-42 syscalls，4-12 KB 預載**。
- **追求極限 first-q = 2f_SLRU**：18 cells 全部 15-19 µs。代價：preload 16 MB
  + 420 syscalls。**1b vacuum layout 下完全免疫 RAM pressure**（majflt 0、avg
  1.50）；1a/1c 下 RAM 緊時 avg 跟 majflt 跌回 base level，**但 first-q 仍
  贏**。
- **RAM-pressure 不是 prefetch 策略設計的瓶頸**：63 cells 中沒有任何一個 ratio
  > 1.2x。「cgroup MemoryMax 會打殘 prefetch」這個直覺被推翻 — 真正受影響的
  是 avg_us / majflt（後續 query 的 cache 命中率），不是 first-q。
- **「2f 在 RAM 緊時 first-q 變慘」這個假設仍然不成立**（第 48-cell 矩陣
  結論），但**「2f 在 RAM 緊時 avg/majflt 退化」需要 layout 配合 — 1b
  vacuum 是唯一 immune 的 layout**（新發現）。

資料來源：
- 完整矩陣（756 cells）: [prefetch_access/runs/matrix_ram_full_results.csv](prefetch_access/runs/matrix_ram_full_results.csv)
- 跑法: [prefetch_access/runs/runmatrix_ram_pressure_full.sh](prefetch_access/runs/runmatrix_ram_pressure_full.sh)
- 聚合腳本: [prefetch_access/runs/aggregate_ram_full.py](prefetch_access/runs/aggregate_ram_full.py)
- 聚合結果: [prefetch_access/runs/matrix_ram_full_summary.md](prefetch_access/runs/matrix_ram_full_summary.md)
- cgroup wrapper: `systemd-run --user --scope --quiet -p MemoryMax=20M --`
- 早期 48-cell 矩陣（保留作交叉驗證）: [matrix_ram_results.csv](prefetch_access/runs/matrix_ram_results.csv)

---

## 一句話總結

> **新增欄位（2026-06）**：所有 row 加上 `prefetch_us`（preprocessing 時間，
> 從 [calibration/prefetch_time_summary.csv](calibration/prefetch_time_summary.csv) 切）
> 跟 `end-to-end` (= prefetch_us + first-q，真實 cold start 總時間)。
> **真實改善 %** 是 end-to-end vs baseline first_q 算出來的——baseline 沒 prefetch
> 所以 end-to-end = first_q。

| Workload | 評估指標 | 最佳策略 | first-q | prefetch_us | **end-to-end** | 改善 (end-to-end vs baseline) | 條件 |
|---|---|---|---:|---:|---:|---:|---|
| **A（Zipfian）** | first-q | layers_5 on type-aware layout | 127 µs | 1.1 µs | **128 µs** | **−68%**（vs 404 µs） | 需先跑 layout_rewriter |
| **A（Zipfian）** | first-q | layers_5 on 原始 layout | 33 µs | 1.4 µs | **34 µs** | **−53%**（vs 73 µs） | 不改 layout，立即可用 |
| **A（Zipfian）** | first-q | **2e_K500 on 原始 / vacuum layout** | 78~81 µs | 80~84 µs | **162 µs** | **−46%**（vs 299 µs） | 518 syscalls；第十五維 |
| **A（Zipfian）** | first-q | **2f SLRU** on 原始 layout | 14 µs | **1,808 µs** | **1,822 µs** | **+625%（變慢）** ⚠️ | first-q -94% 但端到端 cold start 慢 7× |
| **A（Zipfian）** | 全 workload | **2f SLRU** on 原始 layout | n/a | 1,808 µs | -39% (411→249 ms) | 全段差異主導 | 需 warmup pass；prefetch 開銷被攤平到 100k ops |
| **B（Uniform）** | first-q | layers_5 on 原始 layout | 244 µs | 1.4 µs | **245 µs** | **−47%**（vs 463 µs） | ⚠️ 在 ta layout 上 layers_5 反而 +8%；B 不適合 ta |
| **B（Uniform）** | first-q | **2d 或 2e_K10 on 原始 / vacuum layout** | 245 µs | 4-6 µs | **250 µs** | **−46~50%**（vs 464 µs） | 16-26 syscalls；第十四 / 十五維 |
| **B（Uniform）** | first-q | **2f SLRU** on 原始 layout | 15 µs | **1,810 µs** | **1,825 µs** | **+615%（變慢）** ⚠️ | 同 A：端到端 cold start 慢 7× |
| **B（Uniform）** | 全 workload | **2f SLRU** on 原始 layout | n/a | 1,810 µs | -38% (413→255 ms) | 全段差異主導 | 需 warmup pass |
| **C（high-key）** | first-q | **2f SLRU** on 原始 layout | 16 µs | **1,246 µs** | **1,262 µs** | **+405%（變慢）** ⚠️ | hot set 小，prefetch 開銷只 1.2 ms；端到端仍慢 5× |
| **C（high-key）** | first-q | **2e_K10 on 任何 layout** | 75~80 µs | 4-9 µs | **84 µs** | **−82%**（vs 460 µs） | **14~42 syscalls**；不需 layout 改寫；第十五維 |
| **C（high-key）** | first-q | **2d on 原始 / vacuum layout** | 245 µs | 1.6-1.9 µs | **247 µs** | **−46%**（vs 455 µs） | **4 個 syscall**！追平 layers_92；第十四維 |
| **C（high-key）** | first-q | **perpage on type-aware layout** | 294 µs | ~13 µs | **307 µs** | **−34%**（vs 467 µs） | ta + perpage 是不需要 warmup pass 的最佳組合 |
| **C（high-key）** | first-q | **layers_92 (全部 interior) on 原始 layout** | 265 µs | 15 µs | **280 µs** | **−43%**（vs 491 µs） | 不改 layout，但要載全部 92 個 interior |
| **C（high-key）** | 全 workload | **2f SLRU** on 原始 layout | n/a | 1,246 µs | -7% (262→245 ms) | 全段差異主導 | ⚠️ 收益小，baseline avg-q 接近 readahead 下限 |
| **C（high-key）** | first-q | layers_5 on churned DB | avg ~413 µs | 1.4 µs | ~414 µs | -10% (avg) | 隨 churn 累積才看出效益（第四維 sudo drop_caches） |
| **C（high-key）** | first-q | **layers_92 on churned DB** | avg 213 µs | 15 µs | **228 µs** | **−51%**（vs 462 µs avg）| 第十維：N=92 churn-robust，10 個 checkpoint 全部 -50% 以上 |

> **大轉折：2f SLRU 不是 cold-start 最佳**。Headline 數字「-94% first-q」**只算 SQL latency**，
> 但 prefetch tool 自己花 1.2-1.8 ms（比 first-q 大 80-130 倍）。真實 cold-start
> end-to-end = prefetch + first_q **比 baseline 慢 5-7 倍**。2f 的真實價值在
> 「**warmup pass 之後跑一整段** workload」的 avg latency 降低（第五維），不在
> cold start 本身。**冷啟動 first-q 真正的最佳是 2c layers_5 系列**（prefetch < 2 µs，
> end-to-end ≈ first-q），其次是 2d / 2e_K10（4-9 µs preprocessing）。

**速記：**
- 「**點開就看一筆**」（聯絡人、設定）→ **layers_5**（cold start 152 µs vs SLRU 7,500 µs）
- 「**開了會跑一整段**」（瀏覽列表、滑相簿）→ **2f SLRU**（全 workload 省 38%）
- 「**有 warmup pass 預算、想用最少 syscall 抓最多熱頁**」→
  - C: **2e_K10** 任何 layout（14~42 syscall → -82~84%）
  - C 不允許 warmup pass: **2d** orig/vacuum（4 syscall → -47%，最 frugal）
  - A: **2e_K500** orig/vacuum（518 syscall → -73~77%）
- 「**RAM 緊（cgroup < working set）的環境**」→ 避免 2f SLRU；用 **2e_K500**（preload size 1/8、first-q 同 tier、avg_us 不退化）— 第十六維
- 兩個都要 → 看 [prefetch_slru/PREFETCH_SLRU.md](prefetch_slru/PREFETCH_SLRU.md) 的 trade-off 矩陣

---

## 第十七維 — 策略 3a / 3b：ratio-based access-pattern prefetch（K=40 / K=92）× A/B/C × 3 layouts

### 為什麼有這一維

原始 prefetch spec 把「interior + leaf」拆成兩個 ratio：
- **Strategy 3a** = interior:leaf = 7:3
- **Strategy 3b** = interior:leaf = 5:5

但 codebase 把這條軸線參數化成 K（top-K hot leaves），原本只跑 K∈{10, 50, 100, 500}。
為了精確對齊 spec：92 個 interior × 30/70 ≈ **K=40**（→ 3a）；92 × 50/50 = **K=92**（→ 3b）。
2026-05 補跑這兩個點。

### Harness 與資料

**Harness：** 跟第十五維同樣 [prefetch_access/runs/benchmark_harness](prefetch_access/runs/benchmark_harness)，
`--cold-advice dontneed`。**A/B/C × 1a/1b/1c × {K=40, K=92} × 6 reps = 108 cells**。

| 檔案 | 內容 |
|---|---|
| [matrix_2e_ratio_results.csv](prefetch_access/runs/matrix_2e_ratio_results.csv) | 108-row raw（workload, db, strategy, rep, first_query_us, ...） |
| [hot2e_*_K{40,92}.csv](prefetch_access/runs/) | 18 個 hotpages CSV（top-K leaf 重新算）|
| [prefetch_2e_*_K{40,92}.sh](prefetch_access/runs/) | 18 個 prefetch wrapper |
| [runmatrix_2e_ratio.sh](prefetch_access/runs/runmatrix_2e_ratio.sh) | driver |
| [figures/10_ratio_sweep.png](figures/out/10_ratio_sweep.png) | 視覺化（merged with §15 的 K=10/50/100/500）|

### 實際 ratio ≠ spec ratio

2e 只 prefetch **resident** interior pages（warmup 真的觸碰過的）— 不是全部 92 個。
所以實際 ratio 隨 (workload, layout) 強烈變動：

| workload × layout | resident interior | K=40 實際 ratio (int:leaf) | K=92 實際 ratio |
|---|---:|---|---|
| A × 1a (orig)   | 18 | 31:69 | 16:84 |
| A × 1b (vacuum) | 12 | 23:77 | 12:88 |
| **A × 1c (ta)** | **31** | **44:56**（最接近 3a 的 70:30）| 25:75 |
| B × 1a | 16 | 29:71 | 15:85 |
| B × 1b | 12 | 23:77 | 12:88 |
| **B × 1c** | **31** | **44:56** | 25:75 |
| C × 1a | 4  | 9:91  | 4:96  |
| C × 1b | 4  | 9:91  | 4:96  |
| **C × 1c** | **32** | **44:56** | 26:74 |

**只有 ta layout 的 ratio 接近 spec（44:56）**——因為 ta 把 interior 集中、
更多 interior 在 warmup 期就被觸碰到。其他 layout 嚴重偏 leaf。

### First-query latency（median of 6 reps, µs）

| Workload × Layout | 2d (K=0) | K=10 | **K=40 (3a)** | K=50 | **K=92 (3b)** | K=100 | K=500 |
|---|---:|---:|---:|---:|---:|---:|---:|
| A × 1a | — | 225 | **233** | 227 | **212** | 211 | **78** |
| A × 1b | — | 240 | **251** | 244 | **214** | 223 | 79 |
| A × 1c | — | 252 | **250** | 251 | **410 ⚠️** | 374 | 119 |
| B × 1a | — | 251 | **251** | 255 | **243** | 254 | 263 |
| B × 1b | — | 248 | **253** | 253 | **251** | 256 | 345 |
| B × 1c | — | 263 | **254** | 252 | **345** | 303 | 356 |
| C × 1a | — | 77  | **78**  | 79  | **80**  | 78  | 84 |
| C × 1b | — | 77  | **82**  | 83  | **79**  | 80  | 82 |
| C × 1c | — | 80  | **81**  | 81  | **82**  | 81  | 81 |

> 2d 值省略，見[第十四維](#第十四維--2d-access-pattern-prefetch-interior-only--abc--3-layouts)。

### 三個觀察

1. **A × 1c × K=92 出現非單調 hump（410 µs，比 K=40 還差）**：ta layout 把 interior
   壓在檔頭，加 92 個熱 leaves 引發 OS readahead pollution——直到 K=500 把整個熱集
   都載入（穩定到 119 µs）。**這個 hump 是 ta-specific**，1a/1b 上 K=92 反而是 plateau
   最低點（212-214 µs）。

2. **C 在任何 K 都 saturate 到 ~80 µs**：K=10 已經 cover narrow-keyrange 的所有熱
   leaves（10 leaves cover 99%+ ops），多載沒幫助、也沒退化。3a/3b 對 C 沒差。

3. **B 的 ratio 不重要**：uniform read 沒有 leaf-level hot set，任何 K 都拿 ~250 µs，
   只是 K=500 在 1b/1c 上反而 +35~36% 退化（裝太多冷 leaf）。

### 與原 spec 的對齊度

| Spec | 實作 | 對齊狀況 |
|---|---|---|
| 3a = 7:3 | K=40 | ⚠️ 偏離 — 只有 ta layout 達到 44:56（仍偏 leaf）|
| 3b = 5:5 | K=92 | ⚠️ 偏離 — 最接近的 ta 也只到 25:75 |
| 「strict」對齊解法 | 改 2e 強制 prefetch 全部 92 interior（不只 resident） | 屬未來工作 |

要嚴格對齊 7:3 spec，需要強迫 2e prefetch 全部 92 interior（不只 warmup 觸過的），
此時 K=40 才會真的給 92:40 = 70:30 ratio。但這會增加 syscall 數（92 vs 4-32）
且失去 access-count 排序的精度，需評估 trade-off。

### 結論

- **3a (K=40) 是 A 上「不需要全 hot set」的中等選擇**：A×1a/1b 拿到 -27%/-25%
  比 2d (-25~-28%) 略好但遠不如 K=500 (-73~77%)。
- **3b (K=92) 在 A × ta 上是反指標**：非單調 hump 410 µs，比 baseline 還慢。
- **C 上 3a/3b 跟 K=10 都 saturate 在 -82~-84%**：節省 syscall 是唯一差別。
- **沒有任何 (workload, layout) cell 把 3a 或 3b 選為單獨最佳**——3a/3b 的存在價值
  是為了證明「ratio 不是 first-q 的主要 axis，K 才是」。

---

## 第十八維 — Churn 擴充：A/B × churn × 2c layers_N + 2d / 2e_K（A × churn × static-t=0 hotpages）

### 為什麼有這一維

audit 在第十維（C × layers_N × churn）跟 [`runs_access_churn/`](prefetch_churn/runs_access_churn/)
（C × insert-churn × 2d/2e_K10）之後，留下三個 gap，本維一次補完：

- **Gap B1**：access-pattern prefetch 在 **A workload + delete-heavy churn**
  下能否撐住？原假設是 delete-from-id=1 會擾動 Zipfian A 的低 id 熱 keys、
  讓 static t=0 hotpages decay。
- **Gap B2**：layers_N × churn 之前只跑過 C（high-key uniform）。如果換成
  A（Zipfian）或 B（uniform）的 read pattern，N-sweep 的 plateau 形狀會不會
  變？
- **Gap B3**：access-pattern prefetch 在 **B workload（uniform）+ churn** 下
  會怎樣？B 沒有自然熱葉，原假設是 access-count 排出來的 top-K leaves 退化成
  隨機選頁、不帶來額外效益（這是 audit 最後一塊缺口）。

對應跑法：B1 跑 3 個 access-pattern arm × 10 churn checkpoint；B2 跑
N ∈ {0, 1, 5, 10, 20, 46, 92} × 10 churn checkpoint × {A, B} workload；
B3 跑 3 個 access-pattern arm × 10 churn checkpoint × B workload。

### Harness 與資料

- DB: `test.db`（600k rows ≈ 103 MB）
- Evict: `posix_fadvise(POSIX_FADV_DONTNEED)`（不需 sudo，跟第十維、第十四/十五維同 harness）
- Churn: `page_churn_write.txt`（30% update / 20% insert / 20% rmw→delete / 20% read / 10% scan）
- 每 checkpoint 5,000 ops × 10 checkpoint = 50k 累積 churn ops
- Reads:
  - **A**: `workload_a_zipfian.txt`（100k Zipfian reads on keys [8, 99997]）
  - **B**: `workload_b_uniform.txt`（100k uniform reads on keys [1, 99999]）

| Run | Workload | Strategies | 來源 |
|---|---|---|---|
| B1 — A × delete-churn × access-pattern | A | 2d_static, 2e_K10_static, 2e_K50_static（+ n0/n5/n92 借自 B2） | [prefetch_churn/runs_access_churn_a/](prefetch_churn/runs_access_churn_a/README.md) |
| B2-A — A × layers_N × churn | A | N ∈ {0, 1, 5, 10, 20, 46, 92} | [prefetch_churn/runs_nsweep_a/](prefetch_churn/runs_nsweep_a/README.md) |
| B2-B — B × layers_N × churn | B | N ∈ {0, 1, 5, 10, 20, 46, 92} | [prefetch_churn/runs_nsweep_b/](prefetch_churn/runs_nsweep_b/README.md) |
| B3 — B × churn × access-pattern | B | 2d_static, 2e_K10_static, 2e_K50_static（+ n0/n5/n92 借自 B2-B） | [prefetch_churn/runs_access_churn_b/](prefetch_churn/runs_access_churn_b/README.md) |

### 18.1 B1 — A × delete-heavy churn × static t=0 hotpages（3 arms × 10 checkpoint avg）

`static` = 整個 10 checkpoint 都用「churn 前 t=0 產生的 hotpages CSV」，不重新
trace，模擬「production 啟動時 load 一份 hot set 就一直用」的場景。

| arm | hotpages source | cap_interior | cap_leaf | avg first-q (µs) | prefetch_us | **end-to-end** | Δ vs n0_base (e2e) | drift ck001→ck010 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| n0_base（no prefetch）| — | — | — | **281.40** | 0 | **281.4** | — | +18.9%（惡化）|
| n5_layers（file-offset 5） | — | 5 | 0 | 26.13 | 1.4 | **27.5** | -90.2% | -12.7% |
| n92_layers（file-offset 92） | — | 92 | 0 | 24.24 | 15.3 | **39.5** | -86.0% | +30.6%（噪音）|
| **2d_static** | `hotpages_a.csv` | unlimited | 0 | **23.16** | 5.5 | **28.7** | -89.8% | +4.8% |
| **2e_K10_static** | `hot2e_A_orig_K10.csv` | unlimited | 10 | **21.38** | 6.8 | **28.2** | **-90.0%** ← e2e 最佳 | -22.0%（改善）|
| **2e_K50_static** | `hot2e_A_orig_K50.csv` | unlimited | 50 | 23.81 | 12.8 | **36.6** | -87.0% | -18.1%（改善）|

> prefetch_us 從 [calibration/](calibration/) 切（1a orig, workload A）。
> **A churn 上 e2e ranking 跟 first-q ranking 不同**：first-q 看 2e_K10 略勝
> （-92.4% vs -91.4%），但加上 prefetch overhead 後 layers_5 跟 2e_K10 拉得很
> 接近（27.5 vs 28.2 µs，差 < noise）。**結論不變：access-pattern 跟 layers_5
> 都是好選擇**，但要 pure cold-start frugal 就用 layers_5（prefetch 才 1.4 µs）。

### 18.2 B2 — A 與 B × layers_N × churn（ck001-010 平均 first-q µs，dense 切片）

> **資料來源更新（2026-06）**：原本是 2026-05-25 sparse 7-pt 跑的；後來 dense
> N=0..92 churn × A/B 跑完後，**已從 dense run 切出同 7 個 N 重算**。Dense
> 跟 sparse 數字差異在 noise 內（churn workload 每 N 用 fresh test_churn.db、
> 不受 SSD 累積狀態影響）。

| N | A avg first-q | A Δ vs N=0 | B avg first-q | B Δ vs N=0 | prefetch_us | A e2e | B e2e |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0（baseline） | 290.5 | — | 523.6 | — | 0 | 290.5 | 523.6 |
| 1 | 262.0 | -9.8% | 529.1 | +1.1% | 2.3 | 264.3 | 531.4 |
| **5** | **22.5** | **-92.3%** ← A plateau 起點 | **260.2** | **-50.3%** ← B 接近 plateau | **1.4** | **23.9** | **261.6** |
| **10** | **20.7** | **-92.9%** ← A 最佳 | 276.9 | -47.1% | 2.3 | **23.0** | 279.2 |
| **20** | 22.0 | -92.4% | **254.8** | **-51.3%** ← B 最佳 | 3.8 | 25.8 | **258.6** |
| 46 | 20.9 | -92.8% | 258.3 | -50.7% | 7.8 | 28.7 | 266.1 |
| 92 | 21.2 | -92.7% | 260.1 | -50.3% | 15.3 | 36.5 | 275.4 |

> e2e (end-to-end cold start) = prefetch_us + first-q。**A churn e2e 最佳是 N=10 → 23 µs (-92.1%)，
> 跟 first-q N=10 best 一致**。N=92 因為 prefetch 開銷 15 µs，e2e 反而退到 36.5 µs (-87.4%)，
> 真實情況下載少一點更划算。

跨三 workload 的 layers_N × churn 對照：

| Workload | leaf 是否自然熱 | layers_5 Δ | layers_92 Δ | 絕對 avg @ layers_92 | 來源 |
|---|---|---:|---:|---:|---|
| A（Zipfian, [8, 99997]） | ✅ 熱 keys 反覆 hit | **-92.3%** | -92.7% | **21.2 µs** | 本節 |
| **B（Uniform, [1, 99999]）** | ❌ 每筆 cold leaf fault | -50.3% | -50.3% | 260.1 µs | 本節 |
| C（high-key, [590k, 610k]） | ❌ 同上 | -11.1% | **-58.2%** | 208.2 µs | 第十維 |

### 18.3 B3 — B × churn × static t=0 hotpages（access-pattern 2d / 2e_K，3 arms × 10 checkpoint avg）

audit 最後一塊缺口。問題：B（uniform）沒有自然熱葉，access-count 排出來的
top-K leaves 是不是退化成隨機選頁、既無額外效益又會隨 churn 失效？

| arm | hotpages source | cap_interior | cap_leaf | avg first-q (µs) | prefetch_us | **end-to-end** | Δ vs n0_base (e2e) | drift ck001→ck010 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| n0_base（no prefetch）| — | — | — | **499.87** | 0 | **499.9** | — | +11.2% |
| n5_layers（file-offset 5） | — | 5 | 0 | 270.57 | 1.4 | **272.0** | -45.6% | -9.8% |
| n92_layers（file-offset 92） | — | 92 | 0 | 254.05 | 15.3 | **269.4** | **-46.1%** ← e2e best | +17.3%（噪音）|
| **2d_static** | `hotpages_b.csv` | unlimited | 0 | 271.41 | 3.7 | **275.1** | -45.0% | +35.0%（噪音）|
| **2e_K10_static** | `hot2e_B_orig_K10.csv` | unlimited | 10 | **255.87** | 5.9 | **261.8** | **-47.6%** ← e2e best | +9.7% |
| **2e_K50_static** | `hot2e_B_orig_K50.csv` | unlimited | 50 | 261.31 | 12.9 | **274.2** | -45.1% | -8.0% |

> e2e ranking: 2e_K10 (-47.6%) > layers_92 (-46.1%) ≈ 2e_K50 (-45.1%) ≈ layers_5 (-45.6%)。
> 全部差距在 2.5pp 內，**B churn 的 access-pattern 跟 file-offset 在 e2e 都打平**——
> uniform 沒 hot leaf 可挑、勝負由 prefetch overhead 微差決定。layers_5 仍然是
> cost-effective 選擇（prefetch 才 1.4 µs）。

**讀法**：2d_static (-45.7%) ≈ layers_5 (-45.9%)、2e_K10_static (-48.8%) ≈
layers_92 (-49.2%)。access-pattern 在 B 上**跟 file-offset 打平、沒有額外效益**
——因為沒有 hot leaf 可挑、top-K leaves 命中下一筆 uniform 查詢的機率極低。但
三個 static arm 的 drift 沒有單調惡化（都是噪音），**static t=0 hot 在 B 上同樣
不 decay，只是不帶效益、不是會壞掉**。B 的 ~-49% 天花板由 cold-leaf fault 決定。

### 五個發現

1. **A × delete-churn 沒有讓 static t=0 hotpages decay**——hypothesis（delete
   from id=1 會打到 Zipfian 低 id 熱 keys）**被推翻**。3 個 access-pattern arm
   的 ck001→ck010 drift 全部維持在 ±25% 噪音內，沒有單調惡化；其中 2e_K10 跟
   2e_K50 反而是 -22% 與 -18%（也是噪音方向）。
2. **2e_K10 在 A × churn 上 (-92.4%) 略勝 layers_92 (-91.4%)**——載 10 個 hot
   leaves + 全 interior 比載全部 92 interior 更高效（更少 syscall、剛好的
   leaves）。但差距 1pp 內，本質上是同一級。
3. **layers_N 在 A 上的形狀（churn 後）跟乾淨 DB 完全一致**：N=5 就到 plateau
   (-90.7%)，N=10/20/46/92 全在 -90~-91%。**Churn 不會改變 Zipfian 的熱點分佈**
   （熱 keys 都是 long-lived），layers_5 跨 10 checkpoint 從頭 plateau 到尾。
4. **B × churn 的 layers_N plateau 落在 -46~-49%**——uniform 每筆都 cold leaf
   fault，prefetch interior 只能解掉 ~50% 成本，剩下的是 leaf miss。形狀跟
   C × churn 的 -54% 接近，**兩個 cold-leaf workload 的 N-sweep 上限都在 -50%
   附近**。
5. **Workload-stability 結論加強**：不論 (a) workload skew（Zipfian A / uniform
   B / high-key C）、(b) churn 類型（delete-heavy / insert-heavy）、(c) prefetch
   strategy（file-offset layers_N / access-pattern 2d / 2d+top-K leaves），
   **static t=0 hotpages × access-pattern prefetch 在 50k churn ops 規模下都
   穩定**。原因：B+tree 在 50k 級 churn 下不大重排（delete 只 mark free、
   merge 要等 vacuum），hot pages 被 cache 後持續被 hit、不被 evict。

### 為什麼 A × delete-heavy 沒擾動 hot leaves

| 機制 | 細節 |
|---|---|
| Zipfian 熱 key 分散 | A 的熱 keys 雖然偏低 id，但散佈在 [8, 99997]；50k delete 集中在 id ≈ 1~5000 的窄區，跟 hot leaves 的 overlap 比例低 |
| B+tree 不立即 merge | SQLite delete 只 mark page free；leaf merge 要等下一次 vacuum。50k delete 不夠 trigger merge，hot pages layout 維持不變 |
| Hot leaves 持續被 read 命中 | access-pattern prefetch 把 hot leaves 載進 cache 後，後續 reads 一直 hit、leaves 持續 warm，churn 不打到 cache hit path |

### 結論

- **Access-pattern prefetch × static t=0 hot 在 churn 下是 production-ready
  的 baseline 模式**——A × delete / B × uniform / C × insert 三種 churn 組合
  全部驗證過，static t=0 hotpages 都不 decay，完全不需要週期性 re-warmup。
- **layers_N × churn 的 plateau 高度由 workload leaf-warmth 決定**（A -91%,
  B -49%, C -54%），churn 本身不改 plateau 形狀。**Zipfian-friendly 結論
  在 A 上是 N=5 就夠（甚至超過 layers_92 0.3pp 範圍）；cold-leaf workload
  上是 N=92 才壓得到 plateau**。
- **B × access-pattern × churn（最後一塊缺口，已補）**：2d_static -45.7% /
  2e_K10_static **-48.8%** / 2e_K50_static -47.7%，跟 file-offset 的 layers_5
  (-45.9%) / layers_92 (-49.2%) **打平**。uniform reads 沒有自然熱葉，所以
  access-count 挑出來的 top-K leaves 等同隨機選頁、不帶來額外效益（多載 leaf
  也沒用）；但它「不帶效益 ≠ 會壞掉」——ck001→ck010 沒有衰退趨勢，static t=0
  hot 在 B 上同樣不 decay。**B 的 ~-49% 天花板由 cold-leaf fault 決定，不由
  prefetch 策略決定**。

### 資料來源

- B1: [prefetch_churn/runs_access_churn_a/matrix_first_q_us.csv](prefetch_churn/runs_access_churn_a/matrix_first_q_us.csv)
- B2-A: [prefetch_churn/runs_nsweep_a/matrix_first_q_us.csv](prefetch_churn/runs_nsweep_a/matrix_first_q_us.csv)
- B2-B: [prefetch_churn/runs_nsweep_b/matrix_first_q_us.csv](prefetch_churn/runs_nsweep_b/matrix_first_q_us.csv)
- B3 (B × access-pattern × churn): [prefetch_churn/runs_access_churn_b/matrix_first_q_us.csv](prefetch_churn/runs_access_churn_b/matrix_first_q_us.csv)
- 對照 C × churn: [prefetch_churn/runs_nsweep/](prefetch_churn/runs_nsweep/) + [prefetch_churn/runs_access_churn/](prefetch_churn/runs_access_churn/)


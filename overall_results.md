# Overall Results — 策略 × Workload 結果矩陣

本檔列出**每個策略 × 每個 workload × 每個 layout 的 P0 結果**（對照
[overall_workloads.md](overall_workloads.md) 的 workload 定義）。

> **2026-06-23:本檔已全面更新為 P0 數據。** 所有數字來自 **P0 pipeline**
> （`run_p0.py` 家族 → `p0_runs*/`,全 cell `cold_pct`=0)。原本的「主表～第十八維」
> pre-P0 mixed-pipeline 表格已被下方 **「全維度 P0 數據」** 取代(舊表保存在 git 歷史,
> 需對照可 `git log`)。[CONTRADICTIONS.md](CONTRADICTIONS.md) 的 16 條數據矛盾(#1–16)
> 已全部以 P0 單一權威值解決。Workload D 是 churn generator,無自身 latency 結果。
>
> **Preprocessing 計入 e2e**:P0 的 `e2e` = warmer preprocessing(warmer wall-clock,
> 含 process 啟動)+ first-query。**2f_slru 雖 first-query 最低(−79~90%),但其
> ~6–7.5ms preproc 使 e2e 出局**;結構式/access(layers_5 / 2e_K10)preproc 小、
> e2e 才划算(尤其慢 workload C)。視覺化:[figures 13/14](figures/out/13_strategy_firstq_bars.png)。
> 完整執行覆蓋見 [IMPLEMENTATION_PIPELINES.md §3.8](IMPLEMENTATION_PIPELINES.md)。

---

<!-- P0-MASTER-RESULTS-START -->
## P0 master batch 結果（2026-06-22,authoritative）

> 由 `run_p0.py` 一次跑齊:54 strategy cells × pread/async + 9 baseline,pread 5 / async 10 / baseline 10 reps(丟 warmup)、rep-major、全機 drop-caches、in-harness `--verify-hotset`、釘核升頻、ra=128。**全 117 cell `cold_pct`=0**。原始檔:[`p0_runs/summary_p0.csv`](p0_runs/summary_p0.csv) / [`p0_runs/raw_p0.csv`](p0_runs/raw_p0.csv)。
> `fq` = first-query median µs;`impr%` = async 相對該 (workload,layout) baseline;`e2e` = preproc+fq(async);`deliv%` = async delivery_pct;`oracle` = pread 臂 fq(可達上界)。
> 此為 A/B/C 的詳表(含 delivery_pct/oracle);下方「全維度 P0 數據」涵蓋全 workload(含 Z)× layout × 策略 + N/K-sweep + RAM + churn + cadence。舊 pre-P0 18 維表已移除(git 歷史可查)。

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

## 全維度 P0 數據（2026-06-23,取代舊 18 維 pre-P0 表）

> 本節以下全部為 **P0 pipeline**(`run_p0.py` 家族 → `p0_runs*/`,全 cell `cold_pct`=0)的數據,**取代**本檔原本的「主表～第十八維」pre-P0 mixed-pipeline 表格(舊表保存在 git 歷史中,如需對照可 `git log`)。上方「P0 master batch 結果」為 A/B/C 含 delivery_pct/oracle 的詳表;此處為全 workload(含 **Z**)× layout × 策略 + N/K-sweep + RAM + churn + cadence 的彙整。

## 全策略 × layout × workload（P0,async first-query / e2e µs,median）

> baseline = no-prefetch;`impr%` 相對該 (workload,layout) baseline 的 first-query。`e2e` = preproc(warmer)+fq。
> 來源 [`p0_runs/summary_p0.csv`](p0_runs/summary_p0.csv)(A/B/C)+ [`p0_runs_z/`](p0_runs_z/summary_p0.csv)(Z)。

### Workload A

| layout | baseline | layers_5 | layers_92 | 2d | 2e_K10 | 2e_K500 | 2f_slru |
|---|--:|--:|--:|--:|--:|--:|--:|
| orig (1a) | 497 | 350 (−30%) | 338 (−32%) | 335 (−33%) | 337 (−32%) | 154 (−69%) | 107 (−79%) |
| vacuum (1b) | 697 | 554 (−20%) | 559 (−20%) | 555 (−20%) | 553 (−21%) | 190 (−73%) | 104 (−85%) |
| ta (1c) | 652 | 497 (−24%) | 426 (−35%) | 437 (−33%) | 394 (−40%) | 206 (−68%) | 105 (−84%) |

### Workload B

| layout | baseline | layers_5 | layers_92 | 2d | 2e_K10 | 2e_K500 | 2f_slru |
|---|--:|--:|--:|--:|--:|--:|--:|
| orig (1a) | 725 | 384 (−47%) | 390 (−46%) | 385 (−47%) | 382 (−47%) | 430 (−41%) | 105 (−85%) |
| vacuum (1b) | 999 | 509 (−49%) | 516 (−48%) | 508 (−49%) | 513 (−49%) | 402 (−60%) | 106 (−89%) |
| ta (1c) | 795 | 602 (−24%) | 578 (−27%) | 587 (−26%) | 594 (−25%) | 625 (−21%) | 107 (−87%) |

### Workload C

| layout | baseline | layers_5 | layers_92 | 2d | 2e_K10 | 2e_K500 | 2f_slru |
|---|--:|--:|--:|--:|--:|--:|--:|
| orig (1a) | 1058 | 1021 (−4%) | 636 (−40%) | 635 (−40%) | 155 (−85%) | 154 (−85%) | 102 (−90%) |
| vacuum (1b) | 992 | 866 (−13%) | 504 (−49%) | 495 (−50%) | 185 (−81%) | 188 (−81%) | 102 (−90%) |
| ta (1c) | 871 | 840 (−4%) | 473 (−46%) | 483 (−45%) | 188 (−78%) | 189 (−78%) | 104 (−88%) |

### Workload Z

| layout | baseline | layers_5 | layers_92 | 2d | 2e_K10 | 2e_K500 | 2f_slru |
|---|--:|--:|--:|--:|--:|--:|--:|
| orig (1a) | 525 | 409 (−22%) | 383 (−27%) | 411 (−22%) | 203 (−61%) | 204 (−61%) | 119 (−77%) |
| vacuum (1b) | 705 | 570 (−19%) | 572 (−19%) | 571 (−19%) | 205 (−71%) | 203 (−71%) | 117 (−83%) |
| ta (1c) | 737 | 598 (−19%) | 460 (−38%) | 467 (−37%) | 203 (−72%) | 203 (−72%) | 117 (−84%) |

### 2f_slru first-q vs e2e（preprocessing trap,P0）

| workload×layout | fq | preproc | e2e | e2e vs baseline |
|---|--:|--:|--:|--:|
| A/orig | 107 | 7382 | 7489 | 15.1× |
| A/vacuum | 104 | 5768 | 5874 | 8.4× |
| A/ta | 105 | 7440 | 7543 | 11.6× |
| B/orig | 105 | 7462 | 7572 | 10.4× |
| B/vacuum | 106 | 5732 | 5837 | 5.8× |
| B/ta | 107 | 7432 | 7540 | 9.5× |
| C/orig | 102 | 1060 | 1179 | 1.1× |
| C/vacuum | 102 | 855 | 954 | 1.0× |
| C/ta | 104 | 1102 | 1205 | 1.4× |

## layers_N sweep（P0 clean,async first-q µs;N=0=baseline）

> 來源 [`p0_runs_nsweep_dense/`](p0_runs_nsweep_dense/summary_p0.csv)。

### Workload A

| layout | N=0 | N=1 | N=2 | N=3 | N=4 | N=5 | N=6 | N=8 | N=12 | N=16 | N=24 | N=32 | N=46 | N=64 | N=92 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| orig | 505 | 663 | 639 | 662 | 334 | 333 | 331 | 331 | 302 | 331 | 334 | 335 | 327 | 332 | 333 |
| vacuum | 702 | 961 | 962 | 968 | 556 | 549 | 556 | 555 | 552 | 552 | 555 | 552 | 548 | 552 | 558 |
| ta | 681 | 894 | 866 | 856 | 496 | 498 | 498 | 498 | 490 | 482 | 470 | 459 | 489 | 464 | 426 |

### Workload B

| layout | N=0 | N=1 | N=2 | N=3 | N=4 | N=5 | N=6 | N=8 | N=12 | N=16 | N=24 | N=32 | N=46 | N=64 | N=92 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| orig | 728 | 696 | 703 | 692 | 380 | 385 | 382 | 382 | 385 | 379 | 390 | 379 | 383 | 387 | 382 |
| vacuum | 1023 | 916 | 919 | 916 | 507 | 503 | 511 | 510 | 508 | 507 | 531 | 511 | 515 | 508 | 519 |
| ta | 798 | 1004 | 999 | 933 | 603 | 603 | 603 | 603 | 598 | 590 | 579 | 565 | 596 | 570 | 582 |

### Workload C

| layout | N=0 | N=1 | N=2 | N=3 | N=4 | N=5 | N=6 | N=8 | N=12 | N=16 | N=24 | N=32 | N=46 | N=64 | N=92 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| orig | 1074 | 1018 | 1021 | 952 | 1017 | 1021 | 1015 | 1017 | 1019 | 1017 | 1016 | 1012 | 1009 | 1008 | 633 |
| vacuum | 983 | 859 | 902 | 895 | 897 | 891 | 898 | 901 | 897 | 896 | 894 | 895 | 866 | 495 | 504 |
| ta | 872 | 858 | 830 | 821 | 832 | 838 | 844 | 826 | 824 | 824 | 811 | 788 | 890 | 796 | 474 |

### Workload Z

| layout | N=0 | N=1 | N=2 | N=3 | N=4 | N=5 | N=6 | N=8 | N=12 | N=16 | N=24 | N=32 | N=46 | N=64 | N=92 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| orig | 509 | 676 | 676 | 638 | 356 | 335 | 381 | 368 | 364 | 364 | 339 | 381 | 376 | 364 | 382 |
| vacuum | 708 | 968 | 963 | 964 | 543 | 554 | 555 | 555 | 552 | 552 | 559 | 555 | 552 | 552 | 562 |
| ta | 728 | 901 | 835 | 905 | 575 | 571 | 576 | 575 | 572 | 562 | 552 | 558 | 564 | 540 | 438 |

## 2e K-sweep（P0,async first-q µs;K=0=2d interior-only）

> 來源 [`p0_runs_ksweep/`](p0_runs_ksweep/summary_p0.csv)。

### Workload A

| layout | K=0 | K=10 | K=40 | K=50 | K=92 | K=100 | K=500 |
|---|--:|--:|--:|--:|--:|--:|--:|
| orig | 332 | 335 | 331 | 333 | 244 | 248 | 156 |
| vacuum | 560 | 557 | 554 | 552 | 348 | 348 | 188 |
| ta | 453 | 398 | 393 | 395 | 786 | 512 | 201 |

### Workload B

| layout | K=0 | K=10 | K=40 | K=50 | K=92 | K=100 | K=500 |
|---|--:|--:|--:|--:|--:|--:|--:|
| orig | 385 | 385 | 381 | 387 | 383 | 382 | 429 |
| vacuum | 509 | 519 | 508 | 507 | 517 | 512 | 409 |
| ta | 590 | 595 | 596 | 593 | 593 | 592 | 611 |

### Workload C

| layout | K=0 | K=10 | K=40 | K=50 | K=92 | K=100 | K=500 |
|---|--:|--:|--:|--:|--:|--:|--:|
| orig | 636 | 153 | 153 | 152 | 154 | 154 | 155 |
| vacuum | 493 | 187 | 185 | 186 | 185 | 187 | 188 |
| ta | 480 | 189 | 189 | 188 | 189 | 188 | 189 |

## RAM-pressure（cgroup MemoryMax=20M / unlimited 比值,P0 async first-q）

> 來源 [`p0_runs_ram20m/`](p0_runs_ram20m/summary_p0.csv) ÷ master。比值近 1.0 → 壓力幾乎不影響。

| workload×layout | layers_5 | layers_92 | 2d | 2e_K10 | 2e_K500 | 2f_slru |
|---|--:|--:|--:|--:|--:|--:|
| A/orig | 1.05 | 1.00 | 1.00 | 0.98 | 1.01 | 1.03 |
| A/vacuum | 1.00 | 1.00 | 1.01 | 1.00 | 1.00 | 1.00 |
| A/ta | 1.00 | 1.01 | 1.01 | 1.01 | 0.95 | 1.03 |
| B/orig | 1.01 | 1.00 | 1.01 | 1.00 | 1.00 | 1.07 |
| B/vacuum | 1.00 | 1.00 | 1.01 | 1.00 | 1.01 | 0.98 |
| B/ta | 1.01 | 1.01 | 1.01 | 1.00 | 1.00 | 1.02 |
| C/orig | 1.00 | 1.00 | 0.99 | 0.98 | 1.01 | 1.01 |
| C/vacuum | 1.00 | 1.00 | 1.00 | 1.01 | 1.00 | 1.00 |
| C/ta | 0.99 | 1.01 | 0.99 | 1.00 | 1.00 | 1.00 |

## Churn-evolution（P0,layout orig,static t=0 hotset,first-q µs;CSV 另含 vacuum/ta）

> 來源 [`p0_runs_churn/churn_evolution.csv`](p0_runs_churn/churn_evolution.csv)。

### Workload A

| strategy | ck0 | ck1 | ck2 | ck3 | ck4 | ck5 | ck6 | ck7 | ck8 | ck9 | ck10 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| baseline | 378 | 407 | 369 | 360 | 377 | 329 | 368 | 369 | 347 | 362 | 327 |
| 2e_K10_static | 241 | 271 | 339 | 277 | 271 | 309 | 271 | 230 | 230 | 225 | 228 |
| layers_92_static | 254 | 278 | 278 | 276 | 270 | 309 | 270 | 231 | 229 | 244 | 230 |

### Workload B

| strategy | ck0 | ck1 | ck2 | ck3 | ck4 | ck5 | ck6 | ck7 | ck8 | ck9 | ck10 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| baseline | 531 | 547 | 571 | 517 | 559 | 507 | 514 | 508 | 543 | 475 | 493 |
| 2e_K10_static | 253 | 252 | 302 | 280 | 305 | 302 | 295 | 265 | 276 | 235 | 246 |
| layers_92_static | 259 | 252 | 283 | 298 | 339 | 299 | 295 | 266 | 278 | 248 | 253 |

### Workload C

| strategy | ck0 | ck1 | ck2 | ck3 | ck4 | ck5 | ck6 | ck7 | ck8 | ck9 | ck10 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| baseline | 592 | 563 | 616 | 564 | 565 | 587 | 611 | 586 | 543 | 528 | 544 |
| 2e_K10_static | 86 | 89 | 83 | 81 | 265 | 86 | 82 | 88 | 86 | 84 | 82 |
| layers_92_static | 252 | 245 | 278 | 274 | 303 | 309 | 268 | 592 | 265 | 264 | 266 |

## Multi-process cadence（P0,背景 warmer 重暖 + 全機 drop probe,first-q µs）

> 來源 [`p0_runs_cadence/cadence_results.csv`](p0_runs_cadence/cadence_results.csv)。

| cadence | round | first_q_us | delivery_pct |
|---|---|---|---|
| 1.0 | 0 | 27.03 | 100.0 |
| 1.0 | 1 | 25.76 | 100.0 |
| 1.0 | 2 | 25.16 | 100.0 |
| 1.0 | 3 | 36.74 | 100.0 |
| 1.0 | 4 | 26.10 | 100.0 |
| 1.0 | 5 | 29.93 | 100.0 |
| 1.0 | 6 | 26.07 | 100.0 |
| 1.0 | 7 | 25.46 | 100.0 |
| 5.0 | 0 | 262.38 | 0.7 |
| 5.0 | 1 | 25.80 | 100.0 |
| 5.0 | 2 | 24.71 | 100.0 |
| 5.0 | 3 | 273.25 | 0.7 |

## 資料來源（P0）

- 主矩陣:[`p0_runs/summary_p0.csv`](p0_runs/summary_p0.csv)、Z:[`p0_runs_z/`](p0_runs_z/summary_p0.csv)
- N-sweep:[`p0_runs_nsweep_dense/`](p0_runs_nsweep_dense/summary_p0.csv)、K-sweep:[`p0_runs_ksweep/`](p0_runs_ksweep/summary_p0.csv)
- RAM 20M:[`p0_runs_ram20m/`](p0_runs_ram20m/summary_p0.csv)、churn:[`p0_runs_churn/`](p0_runs_churn/)、cadence:[`p0_runs_cadence/`](p0_runs_cadence/cadence_results.csv)
- 凍結清單:[`p0_runs/hotset_freeze.sha256`](p0_runs/hotset_freeze.sha256)。完整執行覆蓋見 [IMPLEMENTATION_PIPELINES.md §3.8](IMPLEMENTATION_PIPELINES.md)。


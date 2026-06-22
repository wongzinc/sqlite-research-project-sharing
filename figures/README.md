# Publication-quality figures (Week 14)

14 figures covering all research weeks. Each script is self-contained
and reproducible from the CSVs in the repo.

> **📊 P0 status (2026-06-22).** **13 of 14 figures redrawn from P0 data**
> (`run_p0.py` / `run_p0_churn.py` → `p0_runs*/`, async arm, `cold_pct`=0 on every cell):
> **01, 02, 03, 04, 05, 06, 07, 09, 10, 11, 12, 13, 14**.
> P0 data sources: master matrix (`p0_runs/`), N-sweep (`p0_runs_nsweep/`, `p0_runs_nsweep_dense/`),
> K-sweep (`p0_runs_ksweep/`), RAM-pressure 20M (`p0_runs_ram20m/`, via `--mem-limit`),
> churn (`p0_runs_churn/`, via `run_p0_churn.py`).
> **Only exception: 08** cadence — an intrinsically **multiprocess warm-keeping** experiment
> (background re-warmer vs foreground probe over real elapsed time), **not** a cold-start TTFQ,
> so it cannot be expressed by the single-process P0 pipeline. It stays on its existing
> multiprocess measurement and is marked ⚠️ "outside P0 cold-start model".

## Quick start

```bash
# matplotlib + numpy + pandas — venv already exists at:
/home/u03/.cache/coldstart-venv/bin/python figures/01_page_distribution.py
# Output PNGs land in figures/out/
```

Or regenerate all:

```bash
for f in figures/0?_*.py; do /home/u03/.cache/coldstart-venv/bin/python "$f"; done
```

## Figures

| # | Script | Output | Story | Data source |
|---|---|---|---|---|
| 1 | [01_page_distribution.py](01_page_distribution.py) | [out/01_page_distribution.png](out/01_page_distribution.png) | Interior-page placement across the 3 layouts. 1a: 92 interiors scattered across 99% of file. 1c (type-aware): all 92 packed into the first 0.4 MB. | `layout_rewriter/runs/classify_{before,vacuum,after}.csv` |
| 2 | [02_layout_effect.py](02_layout_effect.py) | [out/02_layout_effect.png](out/02_layout_effect.png) | Layout × strategy first-query latency, Workload A. VACUUM alone -0%; layers_5 on 1a -30%; **layers_5 on 1c -69%** (404 → 127 µs). | `layout_rewriter/results/matrix_results.csv` |
| 3 | [03_latency_cdf.py](03_latency_cdf.py) | [out/03_latency_cdf.png](out/03_latency_cdf.png) | Cumulative latency for the first 50 queries. 2f_SLRU stays at 152 µs total through query 50; baseline takes 6996 µs (46× slower warmup). | `prefetch_access/runs/ops_csv_ram/ops_A_orig_*_none_r*.csv` |
| 4 | [04_nsweep_plateau.py](04_nsweep_plateau.py) | [out/04_nsweep_plateau.png](out/04_nsweep_plateau.png) | layers_N plateau shape, clean DB vs churned DB, all 3 workloads. A drops fast (Zipfian hot leaves); B/C plateau higher (cold-leaf bottleneck); churn does not change the plateau shape. | `layout_rewriter/runs/matrix_Nsweep_*_results.csv` + `prefetch_churn/runs_nsweep*/matrix_first_q_us.csv` |
| 5 | [05_strategy_comparison.py](05_strategy_comparison.py) | [out/05_strategy_comparison.png](out/05_strategy_comparison.png) | All 7 strategies × 3 layouts × 3 workloads, no RAM limit, 6 reps median. 2f_SLRU wins everywhere when RAM is unlimited; 2e_K10 dominates on C (-82%). | `prefetch_access/runs/matrix_ram_full_results.csv` |
| 6 | [06_ram_pressure_heatmap.py](06_ram_pressure_heatmap.py) | [out/06_ram_pressure_heatmap.png](out/06_ram_pressure_heatmap.png) | 63-cell RAM-pressure ratio (20 MB cap / unlimited). All ratios in [0.90, 1.25] — surprisingly stable. First-query latency is gated by the **load** not by **eviction**. | `prefetch_access/runs/matrix_ram_full_results.csv` (756 measurements) |
| 7 | [07_churn_evolution.py](07_churn_evolution.py) | [out/07_churn_evolution.png](out/07_churn_evolution.png) | First-query latency across 10 churn checkpoints (50 k total ops). Static t=0 hotpages survive both **C × insert-churn** and **A × delete-churn** with no decay. | `prefetch_churn/runs_access_churn{,_a}/matrix_first_q_us.csv` |
| 8 | [08_cadence_comparison.py](08_cadence_comparison.py) | [out/08_cadence_comparison.png](out/08_cadence_comparison.png) | Multi-process prefetcher cadence vs probe latency. cadence=1 s → 16 µs (-95%); cadence ≥ 30 s → no effect. Rule: cadence ≤ gap_s. | `multiprocess/runs_prefetch_cadence/cadence_results.csv` |
| 9 | [09_zlowkey_nsweep.py](09_zlowkey_nsweep.py) | [out/09_zlowkey_nsweep.png](out/09_zlowkey_nsweep.png) | **Robustness check on Workload A**: Z = same Zipfian skew, different hotspot LOCATION (keys 1–1000 instead of mid-range). Right panel overlays A vs Z plateaus — same N=5 elbow, same layout ordering (1c<1a<1b), heights within 10%. layers_N's gain is structural, not specific to the leaves A happens to hit. | `layout_rewriter/runs/matrix_Nsweep_{zlowkey,orig_a,vac,ta}_results.csv` |
| 10 | [10_ratio_sweep.py](10_ratio_sweep.py) | [out/10_ratio_sweep.png](out/10_ratio_sweep.png) | **Strategy 3a (7:3) and 3b (5:5) realised via K-sweep**. K=40 ≈ 3a, K=92 ≈ 3b. Right panel shows actual interior:leaf ratio per (workload×layout) — 2e only prefetches RESIDENT interior (4–32 pages, not 92), so real ratios are workload-dependent. ta-layout cells (44:56) are closest to original 7:3 spec. | `prefetch_access/runs/matrix_ram_full_results.csv` + `matrix_2e_ratio_results.csv` |

## Style conventions

`plot_utils.py` sets shared style for all figures:
- DPI 150 for PNG output (publication-grade)
- DejaVu Sans, fontsize 10, no top/right spines
- Per-workload colors: A blue, B green, C red, Z purple
- Per-strategy colors: base grey, layers_* blue scale, 2d/2e green scale, 2f_SLRU orange

## Notes

- Workload A in the churned-DB N-sweep (fig 4 right panel) plateaus at ~25 µs
  vs ~225 µs on the clean-DB benchmark (fig 4 left). The difference is the
  benchmark harness — the churn experiment's read sequence hits a warm key
  early, while the clean-DB harness is true one-shot cold. Both rows
  honestly reflect their respective experiments.
- Fig 3's CDF was originally over all 100k queries; collapsed because every
  strategy converges to ~1.5 µs once warm. Rebuilt as cumulative warmup
  curve over the first 50 queries — the region where prefetch actually
  matters.

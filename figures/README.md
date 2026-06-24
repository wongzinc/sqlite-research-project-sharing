# Publication-quality figures (Week 14)

14 figures covering all research weeks. Each script is self-contained
and reproducible from the CSVs in the repo.

> **📊 P0 status (2026-06-22).** **All 14 figures redrawn from P0 data**
> (`run_p0.py` / `run_p0_churn.py` / `run_p0_cadence.py`, `cold_pct`=0 on every cold-clear):
> **01–14**. P0 data sources: master matrix (`p0_runs/`), N-sweep (`p0_runs_nsweep/`,
> `p0_runs_nsweep_dense/`), K-sweep (`p0_runs_ksweep/`), RAM-pressure 20M (`p0_runs_ram20m/`,
> via `--mem-limit`), churn (`p0_runs_churn/`, via `run_p0_churn.py`), cadence
> (`p0_runs_cadence/`, via `run_p0_cadence.py` — background re-warmer + P0 full-drop-caches probe).

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
| 1 | [01_page_distribution.py](01_page_distribution.py) | [out/01_page_distribution.png](out/01_page_distribution.png) | Interior-page placement across the 3 layouts (static structure). 1a: interiors scattered across the file; 1c (type-aware): packed into the file head. | `layout_rewriter/runs/classify_{before,vacuum,after}.csv` (static) |
| 2 | [02_layout_effect.py](02_layout_effect.py) | [out/02_layout_effect.png](out/02_layout_effect.png) | Layout × strategy first-query, Workload A (async). baseline 497/697/652 µs (orig/vac/ta); best-per-layout Δ shown (2f ≈ −79%). | `p0_runs/summary_p0.csv` |
| 3 | [03_latency_cdf.py](03_latency_cdf.py) | [out/03_latency_cdf.png](out/03_latency_cdf.png) | Cumulative latency over the first 50 queries (one P0 cold run each); baseline steep early, 2e/2f shallow from query 1. | `p0_runs/work/rec_*/ops.csv` (P0 per-op traces) |
| 4 | [04_nsweep_plateau.py](04_nsweep_plateau.py) | [out/04_nsweep_plateau.png](out/04_nsweep_plateau.png) | layers_N plateau, clean DB, A/B/C × orig (async). A/B drop at N=5; C only at N=92; N=1–3 sit above baseline. | `p0_runs_nsweep/summary_p0.csv` |
| 5 | [05_strategy_comparison.py](05_strategy_comparison.py) | [out/05_strategy_comparison.png](out/05_strategy_comparison.png) | All strategies × 3 layouts × A/B/C, async first-q. 2f_slru wins first-query everywhere; 2e_K10 dominates on C (−85%). | `p0_runs/summary_p0.csv` |
| 6 | [06_ram_pressure_heatmap.py](06_ram_pressure_heatmap.py) | [out/06_ram_pressure_heatmap.png](out/06_ram_pressure_heatmap.png) | RAM-pressure ratio (20 MB cgroup / unlimited). Ratios near 1.0 → RAM pressure barely changes first-query. | `p0_runs_ram20m/summary_p0.csv` + `p0_runs/summary_p0.csv` |
| 7 | [07_churn_evolution.py](07_churn_evolution.py) | [out/07_churn_evolution.png](out/07_churn_evolution.png) | First-query across 11 churn checkpoints (×5k mutation ops). Static t=0 hotset stays flat-low (C: 2e_K10 ~99 µs vs baseline ~580); no decay. | `p0_runs_churn/churn_evolution.csv` |
| 8 | [08_cadence_comparison.py](08_cadence_comparison.py) | [out/08_cadence_comparison.png](out/08_cadence_comparison.png) | Background re-warmer cadence vs P0 cold-probe first-query. cadence 1 s/5 s → warm (26/29 µs); 30 s/never → cold (281/305 µs). Rule: cadence ≤ gap. | `p0_runs_cadence/cadence_results.csv` |
| 9 | [09_zlowkey_nsweep.py](09_zlowkey_nsweep.py) | [out/09_zlowkey_nsweep.png](out/09_zlowkey_nsweep.png) | Workload Z (low-key Zipfian) robustness vs A: same N=5 elbow, plateau within ~10% → layers_N gain is structural, not specific to A's leaves. | `p0_runs_nsweep_dense/summary_p0.csv` |
| 10 | [10_ratio_sweep.py](10_ratio_sweep.py) | [out/10_ratio_sweep.png](out/10_ratio_sweep.png) | 2e K-sweep (2d=K0 … K500) × A/B/C × 3 layouts, async. C saturates ~190 µs by K=10; A×ta has a K=92 readahead-pollution hump (~787 µs), recovers at K=500. | `p0_runs_ksweep/summary_p0.csv` |
| 11 | [11_nsweep_full.py](11_nsweep_full.py) | [out/11_nsweep_full.png](out/11_nsweep_full.png) | Dense layers_N sweep × 3 layouts (clean DB), A/B/C, async. Per-workload plateau by layout. | `p0_runs_nsweep_dense/summary_p0.csv` |
| 12 | [12_nsweep_full_churn.py](12_nsweep_full_churn.py) | [out/12_nsweep_full_churn.png](out/12_nsweep_full_churn.png) | layers_N sweep on the CHURNED DB (after 50k churn), A/B/C, async. Plateau shape survives churn. | `p0_runs_churn/churn_nsweep.csv` |
| 13 | [13_strategy_firstq_bars.py](13_strategy_firstq_bars.py) | [out/13_strategy_firstq_bars.png](out/13_strategy_firstq_bars.png) | First-query bars per workload (orig, async). 2f_slru lowest (~105 µs); the "deceptive" view (preprocessing excluded). | `p0_runs/summary_p0.csv` |
| 14 | [14_strategy_endtoend_stacked.py](14_strategy_endtoend_stacked.py) | [out/14_strategy_endtoend_stacked.png](out/14_strategy_endtoend_stacked.png) | End-to-end (preproc + first-q) per workload. 2f_slru's ~7.5 ms preproc pushes e2e ~15× over baseline; 2e_K10/layers_5 stay below. | `p0_runs/summary_p0.csv` |

## Style conventions

`plot_utils.py` sets shared style for all figures:
- DPI 150 for PNG output (publication-grade)
- DejaVu Sans, fontsize 10, no top/right spines
- Per-workload colors: A blue, B green, C red, Z purple
- Per-strategy colors: base grey, layers_* blue scale, 2d/2e green scale, 2f_SLRU orange

## Notes

- **All data is P0** (`run_p0.py` family → `p0_runs*/`, `cold_pct`=0; see
  IMPLEMENTATION_PIPELINES.md §3.8). Story numbers in the table are P0 medians.
- fig 4 is the clean-DB plateau (single panel, orig); the **churned-DB** N-sweep is now
  its own figure **12** (`run_p0_churn.py` on the post-50k-churn DB).
- fig 3's CDF is over the first 50 queries (the cold→warm region); under P0 it plots one
  representative cold run per strategy from `p0_runs/work/rec_*/ops.csv` (the batch keeps
  the last rep's per-op CSV), so no rep band.

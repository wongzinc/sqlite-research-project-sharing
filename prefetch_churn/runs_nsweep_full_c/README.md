# Full N=0..92 layers_N sweep × Workload C × Churned (high-key) DB

Dense companion to [../runs_nsweep/](../runs_nsweep/README.md), which only
covered N ∈ {0, 1, 5, 10, 20, 46, 92}. This one fills in every integer N
from 0 to 92 (= 93 N values × 11 checkpoints each = 1,023 benchmark runs).

Motivation: the rigor pass for 2c (第十九維 in [overall_results.md](../../overall_results.md)).

## Result

| Best N | First-q avg (10 ckpts) | Δ vs N=0 |
|---|---:|---:|
| **N=92** | **208.2 µs** | **−58.2%** |

Compared to sparse-best (N=92 → 208.2 µs, −58.2%), dense same as sparse.
Difference is within rep noise — the N=92 is the unique minimum (cold-leaf workload) for C × churn.

## Files

- `run_full_c.sh` — driver: loops N=0..92
- `aggregate.py` — also aggregates B and C dirs (single script for all three)
- `n*/benchmark_summary.csv` — per-N raw (baseline + ck001..010 × 3 reps each)
- `matrix_full_churn_first_q_us.csv` — wide-form: checkpoint × N
- `matrix_full_churn_avg_per_N.csv` — per-N avg over 10 churn checkpoints

## Reproduce

```bash
cd /home/u03/sqlite-research-project-sharing
bash prefetch_churn/runs_nsweep_full_c/run_full_c.sh
python3 prefetch_churn/runs_nsweep_full_c/aggregate.py
```

Runtime: ~7.5 min wallclock.

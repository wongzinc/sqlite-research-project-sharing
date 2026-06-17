# Full N=0..92 layers_N sweep × Clean DB × A/B/C × {1a, 1b, 1c}

Dense companion to the original sparse N ∈ {0, 1, 5, 10, 20, 46, 92} matrices
in [layout_rewriter/runs/matrix_Nsweep_*.csv](../). Covers every integer N from
0 to 92 with 3 reps per cell = 2,511 benchmarks total.

Motivation: rigor pass for 2c (第十九維 in [overall_results.md](../../../overall_results.md)).

## Output

| File | Content |
|---|---|
| `full_orig.csv` | A/B/C × N=0..92 × 3 reps on **test.db** (1a orig) |
| `full_vacuum.csv` | … on **test_vacuum.db** (1b VACUUM) |
| `full_ta.csv` | … on **test_typeaware.db** (1c type-aware) |

All three have schema `workload,N,rep,first_query_us,avg_us,majflt,minflt`.

## Best N per cell (3-rep median)

| Cell | Sparse best (舊) | Dense best (新) | Sweet spot 漏掉？ |
|---|---|---|---|
| A × 1a | N=10 → 293.8 µs | N=11 → 290.9 µs | 否 |
| A × 1b | N=5 → 478.8 µs | **N=62 → 420.4 µs** | **是 (−12%)** |
| A × 1c | N=92 → 156.5 µs | N=91 → 153.6 µs | 否 |
| B × 1a | N=20 → 350.5 µs | N=44 → 337.8 µs | 否（noise）|
| B × 1b | N=5 → 438.1 µs | N=26 → 431.8 µs | 否（noise）|
| B × 1c | N=46 → 530.9 µs | **N=26 → 467.3 µs** | **是 (−12%)** |
| C × 1a | N=92 → 596.2 µs | N=92 → 596.2 µs | 否 ✅ |
| C × 1b | N=92 → 428.0 µs | **N=87 → 392.2 µs** | **是 (−8%)** |
| C × 1c | N=92 → 370.4 µs | N=92 → 370.4 µs | 否 ✅ |

## Reproduce

```bash
cd /home/u03/sqlite-research-project-sharing
bash layout_rewriter/runs/runmatrix_Nsweep_FULL.sh
```

Runtime: ~10 minutes wallclock.

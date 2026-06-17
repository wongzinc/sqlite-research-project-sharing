#!/usr/bin/env python3
"""Aggregate the full N=0..92 churn sweep across A/B/C workloads.

Reads each prefetch_churn/runs_nsweep_full_{a,b,c}/n*/benchmark_summary.csv
(11 rows each: baseline + checkpoint_001..010) and emits:

  matrix_full_churn_first_q_us.csv  — wide-form: N,checkpoint_label cells
  matrix_full_churn_avg_per_N.csv   — per-N: avg first_q over ck001..ck010
                                       (matches the existing aggregate.py style)
"""
import csv, statistics
from pathlib import Path

DIR = Path('/home/u03/sqlite-research-project-sharing/prefetch_churn')

def load_n(workload_dir, N):
    p = workload_dir / f"n{N}/benchmark_summary.csv"
    if not p.exists(): return None
    return list(csv.DictReader(open(p)))

for wl, wlname in [('a', 'A'), ('b', 'B'), ('c', 'C')]:
    rundir = DIR / f"runs_nsweep_full_{wl}"
    if not rundir.exists():
        print(f"skip {wlname}: dir missing")
        continue

    # per-N benchmark rows (baseline + ck001..ck010 = 11 rows each)
    by_N = {}
    for N in range(0, 93):
        rows = load_n(rundir, N)
        if rows is None: continue
        by_N[N] = rows

    if not by_N:
        print(f"skip {wlname}: no per-N data yet")
        continue

    # checkpoint labels are the first column across rows
    labels = [r['label'] for r in next(iter(by_N.values()))]

    # Wide-form: rows=checkpoint, cols=N
    wide = rundir / "matrix_full_churn_first_q_us.csv"
    with wide.open("w") as f:
        ns = sorted(by_N)
        f.write("checkpoint," + ",".join(f"N{n}" for n in ns) + "\n")
        for i, lab in enumerate(labels):
            row = lab
            for n in ns:
                row += f",{float(by_N[n][i]['first_query_latency_us']):.2f}"
            f.write(row + "\n")
    print(f"wrote {wide} ({len(labels)} ckpts × {len(by_N)} N)")

    # Per-N summary: avg first_q over checkpoint_001..010 (skip baseline)
    summary = rundir / "matrix_full_churn_avg_per_N.csv"
    with summary.open("w") as f:
        f.write("N,avg_first_q_us,n_checkpoints\n")
        for n in sorted(by_N):
            vals = [float(r['first_query_latency_us']) for r in by_N[n][1:]]  # skip baseline
            f.write(f"{n},{statistics.mean(vals):.2f},{len(vals)}\n")
    print(f"wrote {summary}")

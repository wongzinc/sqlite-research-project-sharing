#!/usr/bin/env python3
"""Aggregate matrix_ram_full_results.csv into per-cell median/mean and
emit a markdown table grouped by (workload, db) with mem_limit columns
for first_query_us, avg_us, majflt.

Usage: aggregate_ram_full.py <matrix.csv>
"""
import sys, csv, statistics
from collections import defaultdict

if len(sys.argv) != 2:
    print(__doc__); sys.exit(1)

rows = defaultdict(list)  # (wl, db, strat, lim) -> [(fq, avg, maj, mn), ...]
with open(sys.argv[1]) as f:
    r = csv.DictReader(f)
    for row in r:
        try:
            fq  = float(row['first_query_us'])
            avg = float(row['avg_us'])
            maj = int(row['majflt'])
            mn  = int(row['minflt'])
        except (ValueError, KeyError):
            continue
        key = (row['workload'], row['db'], row['strategy'], row['mem_limit'])
        rows[key].append((fq, avg, maj, mn))

agg = {}
for key, vs in rows.items():
    fqs = [v[0] for v in vs]
    avgs = [v[1] for v in vs]
    majs = [v[2] for v in vs]
    mins = [v[3] for v in vs]
    agg[key] = {
        'n':   len(vs),
        'fq':  statistics.median(fqs),
        'fq_min': min(fqs),
        'fq_max': max(fqs),
        'avg': statistics.median(avgs),
        'maj': statistics.median(majs),
        'mn':  statistics.median(mins),
    }

workloads = sorted({k[0] for k in agg})
dbs = sorted({k[1] for k in agg}, key=lambda x: {'orig':0,'vacuum':1,'ta':2}.get(x,9))
strats = ['base','2d','2e_K10','2e_K50','2e_K100','2e_K500','2f_SLRU']
limits = ['none','20M']

print(f"# RAM-pressure full matrix aggregation ({sum(v['n'] for v in agg.values())} measurements)\n")
print(f"Reps per cell: {agg[next(iter(agg))]['n']}\n")

# Table 1: first_query_us (median) — wide table per (wl,db)
print("## first_query_us (median µs)\n")
print("| WL | Layout | mem | " + " | ".join(strats) + " |")
print("|---|---|---|" + "|".join(["---"]*len(strats)) + "|")
for wl in workloads:
    for db in dbs:
        for lim in limits:
            row = []
            for strat in strats:
                k = (wl, db, strat, lim)
                if k in agg:
                    row.append(f"{agg[k]['fq']:.0f}")
                else:
                    row.append("—")
            print(f"| {wl} | {db} | {lim} | " + " | ".join(row) + " |")
        # base improvement reference per (wl,db)
        if (wl, db, 'base', 'none') in agg and (wl, db, 'base', '20M') in agg:
            b_none = agg[(wl, db, 'base', 'none')]['fq']
            b_20M  = agg[(wl, db, 'base', '20M')]['fq']
            print(f"|  |  | _baseline pressure cost_ | " + " | ".join([""]*len(strats)) + " |")

# Table 2: improvement vs baseline per same mem_limit (per cell)
print("\n## first_query_us improvement vs `base` (same mem_limit)\n")
print("| WL | Layout | mem | " + " | ".join(strats[1:]) + " |")
print("|---|---|---|" + "|".join(["---"]*(len(strats)-1)) + "|")
for wl in workloads:
    for db in dbs:
        for lim in limits:
            base_key = (wl, db, 'base', lim)
            if base_key not in agg: continue
            base_fq = agg[base_key]['fq']
            row = []
            for strat in strats[1:]:
                k = (wl, db, strat, lim)
                if k in agg:
                    pct = (agg[k]['fq'] - base_fq) / base_fq * 100
                    row.append(f"{pct:+.0f}%")
                else:
                    row.append("—")
            print(f"| {wl} | {db} | {lim} | " + " | ".join(row) + " |")

# Table 3: majflt median
print("\n## majflt (median)\n")
print("| WL | Layout | mem | " + " | ".join(strats) + " |")
print("|---|---|---|" + "|".join(["---"]*len(strats)) + "|")
for wl in workloads:
    for db in dbs:
        for lim in limits:
            row = []
            for strat in strats:
                k = (wl, db, strat, lim)
                if k in agg:
                    row.append(f"{agg[k]['maj']:.0f}")
                else:
                    row.append("—")
            print(f"| {wl} | {db} | {lim} | " + " | ".join(row) + " |")

# Table 4: RAM-pressure cost: fq[20M] / fq[none] per cell
print("\n## RAM-pressure cost (fq[20M] / fq[none])\n")
print("| WL | Layout | " + " | ".join(strats) + " |")
print("|---|---|" + "|".join(["---"]*len(strats)) + "|")
for wl in workloads:
    for db in dbs:
        row = []
        for strat in strats:
            k_n = (wl, db, strat, 'none')
            k_p = (wl, db, strat, '20M')
            if k_n in agg and k_p in agg:
                ratio = agg[k_p]['fq'] / agg[k_n]['fq']
                row.append(f"{ratio:.2f}x")
            else:
                row.append("—")
        print(f"| {wl} | {db} | " + " | ".join(row) + " |")

# Table 5: avg_us median
print("\n## avg_us (median µs over 1000 ops)\n")
print("| WL | Layout | mem | " + " | ".join(strats) + " |")
print("|---|---|---|" + "|".join(["---"]*len(strats)) + "|")
for wl in workloads:
    for db in dbs:
        for lim in limits:
            row = []
            for strat in strats:
                k = (wl, db, strat, lim)
                if k in agg:
                    row.append(f"{agg[k]['avg']:.2f}")
                else:
                    row.append("—")
            print(f"| {wl} | {db} | {lim} | " + " | ".join(row) + " |")

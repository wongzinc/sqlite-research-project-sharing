"""Figure 6: RAM-pressure ratio heatmap (20M cgroup / unlimited) — P0.

Story: for each (workload × layout × strategy), ratio of first-query latency under a
20 MB cgroup MemoryMax vs unlimited RAM. Ratios near 1.0 → RAM pressure barely changes
first-query — the dominant axis is workload, not RAM.

Data (P0): unlimited = master batch p0_runs/summary_p0.csv; 20M = p0_runs_ram20m/
summary_p0.csv (run under `systemd-run --user --scope -p MemoryMax=20M` via run_p0
--mem-limit). async arm, first-query median.
"""
import csv
from collections import defaultdict
from plot_utils import ROOT, save
import matplotlib.pyplot as plt
import numpy as np

UNLIM = ROOT / "p0_runs/summary_p0.csv"
CAP   = ROOT / "p0_runs_ram20m/summary_p0.csv"
LAYOUTS = ["orig", "vacuum", "ta"]
LAYOUT_LBL = {"orig": "1a", "vacuum": "1b", "ta": "1c"}
STRATS = ["layers_5", "layers_92", "2d", "2e_K10", "2e_K500", "2f_slru"]
WORKLOADS = ["A", "B", "C"]

def load(path):
    d = {}
    for r in csv.DictReader(open(path)):
        if r["arm"] == "async" and r["fq_median"]:
            d[(r["workload"], r["db"], r["strategy"])] = float(r["fq_median"])
    return d

unl, cap = load(UNLIM), load(CAP)

M = np.full((len(STRATS), len(WORKLOADS) * len(LAYOUTS)), np.nan)
col_labels = []
for ci, w in enumerate(WORKLOADS):
    for cj, l in enumerate(LAYOUTS):
        col_labels.append(f"{w}\n{LAYOUT_LBL[l]}")
        for ri, s in enumerate(STRATS):
            u, c = unl.get((w, l, s)), cap.get((w, l, s))
            if u and c and u > 0:
                M[ri, ci * len(LAYOUTS) + cj] = c / u

fig, ax = plt.subplots(figsize=(11, 4.2))
im = ax.imshow(M, cmap="RdBu_r", vmin=0.85, vmax=1.25, aspect="auto")
for i in range(M.shape[0]):
    for j in range(M.shape[1]):
        v = M[i, j]
        if not np.isnan(v):
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=8,
                    color="white" if (v > 1.15 or v < 0.92) else "black")
ax.set_xticks(np.arange(M.shape[1]), col_labels, fontsize=9)
ax.set_yticks(np.arange(M.shape[0]), STRATS)
ax.set_xlabel("workload × layout")
ax.set_ylabel("strategy")
for k in range(1, len(WORKLOADS)):
    ax.axvline(k * len(LAYOUTS) - 0.5, color="black", lw=1.0)
cbar = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
cbar.set_label("first-query latency ratio (20 MB cap / unlimited)")
ax.set_title("RAM-pressure ratio · P0 (async first-q) · values near 1.0 → pressure barely matters",
             fontsize=11)
fig.tight_layout()
save(fig, "06_ram_pressure_heatmap")

"""Figure 11: Full N=1..92 layers_N sweep — densifies the original sparse 6-point sweep.

Story: the rigor add-on. Previous results sampled N ∈ {1, 5, 10, 20, 46, 92} which is
enough to spot the U-shape minimum but cannot trace the plateau / inflection. This
figure shows the full N=0..92 curve (3 reps per cell, median plotted) for all 9
(workload × layout) cells on a clean DB.
"""
import csv, statistics
from pathlib import Path
from plot_utils import ROOT, save
import matplotlib.pyplot as plt

DATA = {}
for layout in ['orig', 'vacuum', 'ta']:
    p = ROOT / f"layout_rewriter/runs/nsweep_full/full_{layout}.csv"
    by_wl_n = {}
    for r in csv.DictReader(open(p)):
        key = (r['workload'], int(r['N']))
        by_wl_n.setdefault(key, []).append(float(r['first_query_us']))
    DATA[layout] = by_wl_n

WORKLOADS = ['A', 'B', 'C']
LAYOUTS = [('orig', '1a orig'), ('vacuum', '1b VACUUM'), ('ta', '1c type-aware')]
SPARSE = [1, 5, 10, 20, 46, 92]  # the original 6 sampling points

fig, axes = plt.subplots(3, 3, figsize=(13, 9), sharex=True)

for col, (layout_key, layout_label) in enumerate(LAYOUTS):
    for row, wl in enumerate(WORKLOADS):
        ax = axes[row, col]
        d = DATA[layout_key]
        ns = sorted(n for (w, n) in d if w == wl)
        meds = [statistics.median(d[(wl, n)]) for n in ns]
        # full dense line
        ax.plot(ns, meds, '-', color='#1f77b4', lw=1.4, alpha=0.85, label='dense 1..92')
        # overlay sparse 6-point sweep (the original)
        sparse_pts = [(n, statistics.median(d[(wl, n)])) for n in SPARSE if (wl, n) in d]
        if sparse_pts:
            sx, sy = zip(*sparse_pts)
            ax.plot(sx, sy, 'o', color='#d62728', ms=6, label='sparse 6-pt (original)')
        # baseline as horizontal dashed
        if (wl, 0) in d:
            b = statistics.median(d[(wl, 0)])
            ax.axhline(b, ls='--', color='#888', lw=0.9, alpha=0.7, label=f'N=0 baseline ({b:.0f}µs)')
        # mark the actual minimum N
        best_n, best_v = min(zip(ns, meds), key=lambda x: x[1])
        ax.plot([best_n], [best_v], '*', color='#2ca02c', ms=14, label=f'best N={best_n} ({best_v:.0f}µs)')
        if row == 0:
            ax.set_title(layout_label, fontsize=11)
        if col == 0:
            ax.set_ylabel(f"Workload {wl}\nfirst-q (µs)", fontsize=10)
        if row == 2:
            ax.set_xlabel("N (interior pages prefetched)")
        ax.legend(fontsize=7, loc='best')
        ax.set_xticks([0, 5, 10, 20, 46, 92])
        ax.grid(alpha=0.25)

fig.suptitle("2c layers_N — full N=0..92 sweep · sparse 6-pt overlay (3 reps median)", fontsize=12, y=0.995)
fig.tight_layout()
save(fig, "11_nsweep_full")

"""Figure 12: Full N=0..92 layers_N sweep — under churn (A/B/C, 10 checkpoints avg).

Story: companion to figure 11. The dense churn-mode sweep confirms the plateau
shape across all 92 N values (vs the original 6-point sparse sweep), and that
churn does not change the plateau height for A/B/C.
"""
import csv, statistics
from plot_utils import ROOT, save
import matplotlib.pyplot as plt

def load_summary(wl_letter):
    p = ROOT / f"prefetch_churn/runs_nsweep_full_{wl_letter}/matrix_full_churn_avg_per_N.csv"
    rows = list(csv.DictReader(open(p)))
    ns = [int(r['N']) for r in rows]
    avgs = [float(r['avg_first_q_us']) for r in rows]
    return ns, avgs

WORKLOADS = [('a', 'A (Zipfian)', '#1f77b4'),
             ('b', 'B (uniform)', '#ff7f0e'),
             ('c', 'C (high-key)', '#2ca02c')]
SPARSE = [1, 5, 10, 20, 46, 92]

fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), sharex=True)

for ax, (wl_letter, label, color) in zip(axes, WORKLOADS):
    ns, avgs = load_summary(wl_letter)
    if not ns: continue
    ax.plot(ns, avgs, '-', color=color, lw=1.5, label='dense 1..92 (10-ckpt avg)')
    # sparse 6-point overlay
    sparse_x = [n for n in SPARSE if n in ns]
    sparse_y = [avgs[ns.index(n)] for n in sparse_x]
    if sparse_x:
        ax.plot(sparse_x, sparse_y, 'o', color='#d62728', ms=6, label='sparse 6-pt (original)')
    # baseline (N=0)
    if 0 in ns:
        b = avgs[ns.index(0)]
        ax.axhline(b, ls='--', color='#888', lw=0.9, alpha=0.7, label=f'N=0 baseline ({b:.0f}µs)')
    # best
    best_i = min(range(len(ns)), key=lambda i: avgs[i])
    ax.plot([ns[best_i]], [avgs[best_i]], '*', color='#2ca02c', ms=14,
            label=f'best N={ns[best_i]} ({avgs[best_i]:.0f}µs)')
    ax.set_title(f"Workload {label} · churn", fontsize=11)
    ax.set_xlabel("N (interior pages prefetched)")
    ax.set_xticks([0, 5, 10, 20, 46, 92])
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25)

axes[0].set_ylabel("first-q (µs, avg over 10 churn checkpoints)")
fig.suptitle("2c layers_N — full N=0..92 sweep under 50k-op churn · sparse 6-pt overlay",
             fontsize=12, y=0.99)
fig.tight_layout()
save(fig, "12_nsweep_full_churn")

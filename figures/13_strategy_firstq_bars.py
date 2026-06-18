"""Figure 13: Pure first-query bar chart — strategy comparison per workload.

Story: the "deceptive" view. Showing only first_query_us (the SQL latency,
NOT counting prefetch tool overhead), 2f SLRU looks dominant — 14-17 µs across
all workloads. This is the headline number reported in §4.1.

Pair with figure 14, which adds preprocessing cost and exposes that 2f SLRU's
end-to-end cold start is actually slower than baseline by 3-7×.

Data: prefetch_access/runs/matrix_ram_full_results.csv (mem_limit=none, layout=1a orig),
median over 6 reps. Strategies: base / 2d / 2e_K10 / 2e_K50 / 2e_K100 / 2e_K500 / 2f_SLRU.
"""
import csv, statistics
from plot_utils import ROOT, save
import matplotlib.pyplot as plt
import numpy as np

DATA_PATH = ROOT / "prefetch_access/runs/matrix_ram_full_results.csv"

STRATEGIES = ['base', '2d', '2e_K10', '2e_K50', '2e_K100', '2e_K500', '2f_SLRU']
LABELS    = ['base', '2d', '2e_K10', '2e_K50', '2e_K100', '2e_K500', '2f SLRU']
COLORS    = ['#9ca3af', '#3b82f6', '#10b981', '#10b981', '#10b981', '#10b981', '#f97316']
ALPHAS    = [1.0, 1.0, 0.5, 0.65, 0.8, 1.0, 1.0]
WORKLOADS = ['A', 'B', 'C']
WL_TITLE  = {'A': 'Workload A (Zipfian)',
             'B': 'Workload B (uniform)',
             'C': 'Workload C (high-key uniform)'}

# Load & median per (workload, strategy) on 1a orig, unlimited RAM
data = {}
for r in csv.DictReader(open(DATA_PATH)):
    if r['mem_limit'] != 'none' or r['db'] != 'orig':
        continue
    key = (r['workload'], r['strategy'])
    data.setdefault(key, []).append(float(r['first_query_us']))

fig, axes = plt.subplots(1, 3, figsize=(13, 4.6), sharey=False)
x = np.arange(len(STRATEGIES))

for ax, wl in zip(axes, WORKLOADS):
    medians = [statistics.median(data[(wl, s)]) for s in STRATEGIES]
    bars = ax.bar(x, medians, color=COLORS, alpha=0.85, edgecolor='black', linewidth=0.5)
    for bar, alpha in zip(bars, ALPHAS):
        bar.set_alpha(alpha)
    # baseline reference dashed line
    baseline = medians[0]
    ax.axhline(baseline, color='#9ca3af', ls='--', lw=1.0, alpha=0.6, zorder=0)
    # value labels on top
    for xi, val in zip(x, medians):
        ax.text(xi, val * 1.06, f'{val:.0f}', ha='center', va='bottom', fontsize=8, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(LABELS, fontsize=9, rotation=25, ha='right')
    ax.set_title(WL_TITLE[wl], fontsize=11)
    ax.set_yscale('log')
    ax.set_ylim(8, max(medians) * 2.5)
    ax.grid(axis='y', alpha=0.25, which='both')
    ax.set_axisbelow(True)

axes[0].set_ylabel('first-query latency (µs, log scale)', fontsize=10)
fig.suptitle('First-query latency by strategy (only SQL latency — preprocessing cost NOT included)',
             fontsize=12, y=1.0)
fig.tight_layout()
save(fig, '13_strategy_firstq_bars')

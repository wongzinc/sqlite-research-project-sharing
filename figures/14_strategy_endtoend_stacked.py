"""Figure 14: End-to-end cold start (preprocessing + first-q) — KILLER figure.

Story: counter to figure 13's headline. Once we add prefetch tool overhead
(from calibration/prefetch_time_summary.csv), the picture changes:
  - 2c / 2d / 2e_K10 / 2e_K50 / 2e_K100: prefetch overhead < 5% of first-q
    → end-to-end ≈ first-q, all genuinely beat baseline.
  - 2e_K500: prefetch ~80 µs, end-to-end still beats baseline.
  - 2f SLRU: prefetch 1.2-1.8 ms, dwarfs first-q (14-17 µs) by 80-130×.
    End-to-end = 1.2-1.8 ms, ACTUALLY SLOWER than baseline (~500 µs) by 3-7×.

Visual design: stacked bar (first_q bottom + prefetch_us top), baseline as
horizontal dashed reference. The 2f SLRU bar towers OVER the baseline line —
one glance shows the deception in figure 13.

Data: same matrix_ram_full (first-q) + calibration (prefetch_us). Median over 6/3 reps.
"""
import csv, statistics
from plot_utils import ROOT, save
import matplotlib.pyplot as plt
import numpy as np

LATENCY = ROOT / "prefetch_access/runs/matrix_ram_full_results.csv"
CALIB   = ROOT / "calibration/prefetch_time_summary.csv"

# Strategy -> (display label, tool name, color)
STRATEGIES = [
    ('base',    'base',     'prefetch_layers', '#9ca3af'),
    ('2d',      '2d',       'prefetch_access', '#3b82f6'),
    ('2e_K10',  '2e_K10',   'prefetch_access', '#10b981'),
    ('2e_K50',  '2e_K50',   'prefetch_access', '#10b981'),
    ('2e_K100', '2e_K100',  'prefetch_access', '#10b981'),
    ('2e_K500', '2e_K500',  'prefetch_access', '#10b981'),
    ('2f_SLRU', '2f SLRU',  'prefetch_slru',   '#f97316'),
]
ALPHAS = [1.0, 1.0, 0.5, 0.65, 0.8, 1.0, 1.0]
WORKLOADS = ['A', 'B', 'C']
WL_TITLE  = {'A': 'Workload A (Zipfian)',
             'B': 'Workload B (uniform)',
             'C': 'Workload C (high-key uniform)'}

# --- Load first_q medians per (workload, strategy) on 1a orig, unlimited RAM
firstq = {}
for r in csv.DictReader(open(LATENCY)):
    if r['mem_limit'] != 'none' or r['db'] != 'orig':
        continue
    firstq.setdefault((r['workload'], r['strategy']), []).append(float(r['first_query_us']))

# --- Load prefetch_us median per (tool, db, workload, strategy) — 1a orig
pf = {}
for r in csv.DictReader(open(CALIB)):
    if r['db_layout'] != 'orig':
        continue
    pf[(r['tool'], r['workload'], r['strategy'])] = float(r['prefetch_time_us_med'])

def get_prefetch(strat_key, tool, wl):
    if strat_key == 'base':
        return 0.0
    # prefetch_layers in calibration uses workload='ALL'
    wl_key = 'ALL' if tool == 'prefetch_layers' else wl
    return pf.get((tool, wl_key, strat_key), 0.0)

fig, axes = plt.subplots(1, 3, figsize=(13, 5.0), sharey=False)
x = np.arange(len(STRATEGIES))

for ax, wl in zip(axes, WORKLOADS):
    # Get first-q and prefetch for each strategy
    fqs = [statistics.median(firstq[(wl, s[0])]) for s in STRATEGIES]
    pfs = [get_prefetch(s[0], s[2], wl) for s in STRATEGIES]
    e2es = [f + p for f, p in zip(fqs, pfs)]

    # baseline (= e2e of the first bar, which is base + 0 prefetch = first_q baseline)
    baseline = e2es[0]

    # Stacked bars: first_q at bottom, prefetch on top
    colors = [s[3] for s in STRATEGIES]
    # bottom layer = first-q
    ax.bar(x, fqs, color=colors, alpha=0.85, edgecolor='black', linewidth=0.5,
           label='first-q (SQL latency)')
    # top layer = prefetch
    ax.bar(x, pfs, bottom=fqs, color='#fbbf24', alpha=0.95, edgecolor='black',
           linewidth=0.5, hatch='///', label='preprocessing (prefetch tool)')

    # baseline reference line
    ax.axhline(baseline, color='#dc2626', ls='--', lw=1.4, alpha=0.8, zorder=3,
               label=f'baseline cold start ({baseline:.0f} µs)')

    # value labels on top: total end-to-end
    for xi, e2e, fq, pp in zip(x, e2es, fqs, pfs):
        if pp > fq * 2:  # 2f SLRU case — annotate dramatically
            ax.text(xi, e2e * 1.04, f'{e2e:.0f} µs\n⚠ {e2e/baseline:.1f}× baseline',
                    ha='center', va='bottom', fontsize=8, color='#dc2626', fontweight='bold')
        else:
            improve = (e2e - baseline) / baseline * 100
            sign = '+' if improve >= 0 else ''
            ax.text(xi, e2e * 1.05, f'{e2e:.0f} ({sign}{improve:.0f}%)',
                    ha='center', va='bottom', fontsize=7.5,
                    color='#dc2626' if improve > 0 else 'black')

    ax.set_xticks(x)
    ax.set_xticklabels([s[1] for s in STRATEGIES], fontsize=9, rotation=25, ha='right')
    ax.set_title(WL_TITLE[wl], fontsize=11)
    ax.set_yscale('log')
    ax.set_ylim(8, max(e2es) * 3.5)
    ax.grid(axis='y', alpha=0.25, which='both')
    ax.set_axisbelow(True)
    if wl == 'A':
        ax.legend(loc='upper left', fontsize=7.5, framealpha=0.92)

axes[0].set_ylabel('end-to-end cold start (µs, log scale)', fontsize=10)
fig.suptitle('End-to-end cold start: preprocessing + first-q  vs  baseline. '
             'Compare to Figure 13 (first-q only) — 2f SLRU\'s "−94%" headline collapses.',
             fontsize=11, y=1.0)
fig.tight_layout()
save(fig, '14_strategy_endtoend_stacked')

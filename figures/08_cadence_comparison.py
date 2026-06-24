"""Figure 8: Prefetch cadence — first-query latency vs background re-warm cadence — P0.

Story: a background prefetcher re-warms the hotset every `cadence` seconds; each probe does
a P0 full-machine drop-caches then waits a fixed gap (3 s) before measuring first-query. If
cadence < gap the prefetcher fires during the gap → warm probe; if cadence >> gap it doesn't
fire in time → cold probe. Rule of thumb: cadence ≤ gap_s.

Data (P0): p0_runs_cadence/cadence_results.csv — measurement via benchmark_harness with P0
discipline (full drop-caches + --verify-hotset); cadence = background warmer (run_p0_cadence.py).
"""
import csv, statistics
from collections import defaultdict
from plot_utils import ROOT, save
import matplotlib.pyplot as plt

CSV = ROOT / "p0_runs_cadence/cadence_results.csv"

g = defaultdict(list)
for r in csv.DictReader(open(CSV)):
    g[r["cadence"]].append(float(r["first_q_us"]))

def kf(k):
    try: return float(k)
    except ValueError: return 1e9

cadences = sorted(g.keys(), key=kf)
xs = list(range(len(cadences)))
meds = [statistics.median(g[c]) for c in cadences]
lo   = [min(g[c]) for c in cadences]
hi   = [max(g[c]) for c in cadences]
labels = [f"{c} s" if c != "never" else "never\n(no prefetcher)" for c in cadences]

fig, ax = plt.subplots(figsize=(8, 4.5))
err_lo = [m - l for m, l in zip(meds, lo)]
err_hi = [h - m for h, m in zip(hi, meds)]
colors = ["#10b981", "#34d399", "#fbbf24", "#9ca3af"][:len(cadences)]
bars = ax.bar(xs, meds, color=colors, yerr=[err_lo, err_hi], capsize=4, edgecolor="white")
for b, m in zip(bars, meds):
    ax.text(b.get_x() + b.get_width()/2, m + 8, f"{m:.0f} µs",
            ha="center", va="bottom", fontsize=10, fontweight="bold")

ax.axhline(meds[-1], color="#9ca3af", lw=0.6, ls=":", alpha=0.6)
ax.text(len(xs) - 0.5, meds[-1] - 30, f"never (no prefetcher) = {meds[-1]:.0f} µs",
        color="#6b7280", fontsize=8, ha="right")

ax.set_xticks(xs, labels)
ax.set_xlabel("prefetcher cadence  (1 re-warm / cadence sec)")
ax.set_ylabel("first-query latency (µs, median; bars = min/max of 8 rounds)")
ax.set_title("Prefetch cadence (P0) · background re-warmer + P0 drop-caches probe (gap 3 s)\n"
             "rule of thumb: cadence ≤ gap_s → warm",
             fontsize=11)
ax.set_ylim(0, max(hi) * 1.18)
fig.tight_layout()
save(fig, "08_cadence_comparison")

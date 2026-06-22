"""Figure 11: Dense layers_N sweep × 3 layouts (clean DB) — P0.

Story: the layers_N plateau, now across all three layouts. Per workload, one line
per layout (1a orig / 1b vacuum / 1c type-aware). N=0 = no-prefetch baseline.

Data (P0): p0_runs_nsweep_dense/summary_p0.csv — layers_N (dense N) × A/B/C ×
{orig,vacuum,ta}, async arm, first-query median (warmup dropped).
"""
import csv, re
from collections import defaultdict
from plot_utils import ROOT, LAYOUT_COLORS, save
import matplotlib.pyplot as plt

SUMMARY = ROOT / "p0_runs_nsweep_dense/summary_p0.csv"

# (workload, db) -> {N: fq_median}
data = defaultdict(dict)
for r in csv.DictReader(open(SUMMARY)):
    w, db = r["workload"], r["db"]
    if r["strategy"] == "baseline" and r["arm"] == "baseline":
        data[(w, db)][0] = float(r["fq_median"]); continue
    if r["arm"] != "async" or not r["fq_median"]:
        continue
    m = re.fullmatch(r"layers_(\d+)", r["strategy"])
    if m:
        data[(w, db)][int(m.group(1))] = float(r["fq_median"])

WORKLOADS = ["A", "B", "C"]
LAYOUTS = [("orig", "1a"), ("vacuum", "1b"), ("ta", "1c")]
fig, axes = plt.subplots(1, 3, figsize=(14, 4.6), sharey=True)
ymax = max((v for (w, _), d in data.items() if w in WORKLOADS for v in d.values()), default=1)
for ax, w in zip(axes, WORKLOADS):
    for db, lbl in LAYOUTS:
        d = data.get((w, db), {})
        ns = sorted(d)
        ax.plot(ns, [d[n] for n in ns], "-o", color=LAYOUT_COLORS[db], lw=1.6, ms=4,
                label=f"layout {lbl}")
    ax.set_xscale("symlog", linthresh=1)
    ax.set_xticks([0, 1, 5, 16, 46, 92]); ax.set_xticklabels(["0", "1", "5", "16", "46", "92"])
    ax.set_xlabel("N (interior pages prefetched; N=0=baseline)")
    ax.set_title(f"Workload {w}")
    ax.grid(True, linestyle=":", alpha=0.4)
    if w == "A":
        ax.set_ylabel("first-query latency (µs, async, median)")
        ax.legend(loc="upper right", fontsize=8)
axes[0].set_ylim(0, ymax * 1.05)
fig.suptitle("Dense layers_N sweep · clean DB · A/B/C × 3 layouts · P0 (async first-query)",
             fontsize=12, y=1.02)
fig.tight_layout()
save(fig, "11_nsweep_full")

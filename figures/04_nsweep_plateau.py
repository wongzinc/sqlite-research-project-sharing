"""Figure 4: layers_N plateau shape (clean DB, all 3 workloads) — P0.

Story: layers_N first-query latency drops as N grows (more interior pages
prefetched) and plateaus where the remaining cost is leaf faults. The plateau
HEIGHT/SHAPE is workload-dependent. N=0 is the no-prefetch baseline.

Data (P0): p0_runs_nsweep/summary_p0.csv — layers_N sweep on layout=orig,
async arm, first-query median (warmup dropped). N=0 = baseline cell.
NOTE: the churned-DB N-sweep (old fig had a 2nd panel) needs churn-checkpoint
infra not in the P0 batch — see overall_results.md (kept pre-P0).
"""
import csv, re
from collections import defaultdict
from plot_utils import ROOT, WORKLOAD_COLORS, save
import matplotlib.pyplot as plt

SUMMARY = ROOT / "p0_runs_nsweep/summary_p0.csv"

# workload -> {N: fq_median(async)}
data = defaultdict(dict)
for r in csv.DictReader(open(SUMMARY)):
    w = r["workload"]
    if r["strategy"] == "baseline" and r["arm"] == "baseline":
        data[w][0] = float(r["fq_median"])
        continue
    if r["arm"] != "async":
        continue
    m = re.fullmatch(r"layers_(\d+)", r["strategy"])
    if m and r["fq_median"]:
        data[w][int(m.group(1))] = float(r["fq_median"])

fig, ax = plt.subplots(figsize=(7.6, 4.6))
for w in ["A", "B", "C"]:
    d = data.get(w, {})
    if not d:
        continue
    ns = sorted(d)
    ax.plot(ns, [d[n] for n in ns], "-o", color=WORKLOAD_COLORS[w], lw=1.7, ms=5,
            label=f"Workload {w}")

ax.set_xlabel("N (number of interior pages prefetched; N=0 = baseline)")
ax.set_ylabel("first-query latency (µs, async, median)")
ax.set_xscale("symlog", linthresh=1)
ax.set_xticks([0, 1, 5, 13, 34, 92])
ax.set_xticklabels(["0", "1", "5", "13", "34", "92"])
ax.set_ylim(0, max((max(d.values()) for d in data.values() if d), default=1) * 1.1)
ax.legend(loc="upper right")
ax.set_title("layers_N plateau · clean DB · layout orig · P0 (async first-query)")
fig.tight_layout()
save(fig, "04_nsweep_plateau")

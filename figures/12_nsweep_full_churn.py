"""Figure 12: layers_N sweep on a CHURNED DB (A/B/C) — P0.

Story: companion to figure 11 (clean DB). After 50k churn ops, re-run the layers_N
sweep (static t=0 layers hotsets) on the churned DB. Confirms the plateau shape
survives churn. N=0 = no-prefetch baseline on the churned DB.

Data (P0): p0_runs_churn/churn_nsweep.csv — measurement via run_p0 on the final
churned DB (after 50k mutation ops), layout=orig, async first-query (median of 3).
"""
import csv
from collections import defaultdict
from plot_utils import ROOT, WORKLOAD_COLORS, save
import matplotlib.pyplot as plt

CSVP = ROOT / "p0_runs_churn/churn_nsweep.csv"
data = defaultdict(dict)   # workload -> {N: fq}
for r in csv.DictReader(open(CSVP)):
    data[r["workload"]][int(r["N"])] = float(r["first_query_us"])

fig, ax = plt.subplots(figsize=(7.8, 4.6))
for w in ["A", "B", "C"]:
    d = data.get(w, {})
    ns = sorted(d)
    if ns:
        ax.plot(ns, [d[n] for n in ns], "-o", color=WORKLOAD_COLORS[w], lw=1.7, ms=5,
                label=f"Workload {w}")
ax.set_xscale("symlog", linthresh=1)
ax.set_xticks([0, 1, 5, 13, 34, 92]); ax.set_xticklabels(["0", "1", "5", "13", "34", "92"])
ax.set_xlabel("N (interior pages prefetched; N=0=baseline)")
ax.set_ylabel("first-query latency (µs, async, median)")
ax.set_ylim(0, max((max(d.values()) for d in data.values() if d), default=1) * 1.1)
ax.legend(loc="upper right")
ax.set_title("layers_N plateau on CHURNED DB (after 50k churn ops) · layout orig · P0")
fig.tight_layout()
save(fig, "12_nsweep_full_churn")

"""Figure 7: First-query latency across churn checkpoints — P0.

Story: a STATIC t=0 hotset (captured once on the clean DB) is re-used to prefetch at
every checkpoint as the DB churns (5k mutation ops per checkpoint, 50k total). If the
static hotset goes stale, prefetch first-query would creep back toward baseline. Per
workload: baseline (no prefetch) vs 2e_K10-static vs layers_92-static.

Data (P0): p0_runs_churn/churn_evolution.csv — measurement via run_p0 (drop-caches +
verify-hotset + warmer), churn applied via the harness in write mode. layout=orig.
"""
import csv
from collections import defaultdict
from plot_utils import ROOT, save
import matplotlib.pyplot as plt

CSVP = ROOT / "p0_runs_churn/churn_evolution.csv"
STRATS = [("baseline", "baseline", "#9ca3af"),
          ("2e_K10_static", "2e_K10 (static t=0)", "#059669"),
          ("layers_92_static", "layers_92 (static t=0)", "#1e3a8a")]
WORKLOADS = ["A", "B", "C"]
WL_TITLE = {"A": "Workload A (Zipfian)", "B": "Workload B (uniform)", "C": "Workload C (churn-heavy)"}

# (workload, strategy) -> {checkpoint: fq}
data = defaultdict(dict)
for r in csv.DictReader(open(CSVP)):
    data[(r["workload"], r["strategy"])][int(r["checkpoint"])] = float(r["first_query_us"])

fig, axes = plt.subplots(1, 3, figsize=(14, 4.4), sharey=True)
ymax = max((v for d in data.values() for v in d.values()), default=1)
for ax, w in zip(axes, WORKLOADS):
    for skey, slbl, color in STRATS:
        d = data.get((w, skey), {})
        cks = sorted(d)
        if cks:
            ax.plot(cks, [d[c] for c in cks], "-o", color=color, lw=1.7, ms=4, label=slbl)
    ax.set_title(WL_TITLE[w])
    ax.set_xlabel("churn checkpoint (×5k mutation ops)")
    ax.grid(True, linestyle=":", alpha=0.4)
    if w == "A":
        ax.set_ylabel("first-query latency (µs, median of 3)")
        ax.legend(loc="upper left", fontsize=8)
axes[0].set_ylim(0, ymax * 1.08)
fig.suptitle("First-query vs churn · static t=0 hotset re-used across checkpoints · P0",
             fontsize=12, y=1.0)
fig.tight_layout()
save(fig, "07_churn_evolution")

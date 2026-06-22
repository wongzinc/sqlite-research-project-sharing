"""Figure 9: Workload Z (low-key Zipfian) — robustness check on Workload A — P0.

A = Zipfian over mid-range keys; Z = Zipfian over keys [1,1000] (same skew, different
hotspot LOCATION). If layers_N's win on A came from the specific hot leaves A hits,
Z would plateau differently. Left: Z's layers_N across 3 layouts. Right: A vs Z on
orig — same N=5 elbow, heights within ~10% → the gain is structural.

Data (P0): p0_runs_nsweep_dense/summary_p0.csv — layers_N × {A,Z} × {orig,vacuum,ta},
async arm, first-query median (warmup dropped). N=0 = baseline.
"""
import csv, re
from collections import defaultdict
from plot_utils import ROOT, LAYOUT_COLORS, WORKLOAD_COLORS, save
import matplotlib.pyplot as plt

SUMMARY = ROOT / "p0_runs_nsweep_dense/summary_p0.csv"

data = defaultdict(dict)   # (w, db) -> {N: fq}
for r in csv.DictReader(open(SUMMARY)):
    w, db = r["workload"], r["db"]
    if r["strategy"] == "baseline" and r["arm"] == "baseline":
        data[(w, db)][0] = float(r["fq_median"]); continue
    if r["arm"] != "async" or not r["fq_median"]:
        continue
    m = re.fullmatch(r"layers_(\d+)", r["strategy"])
    if m:
        data[(w, db)][int(m.group(1))] = float(r["fq_median"])

LAYOUTS = [("orig", "1a"), ("vacuum", "1b"), ("ta", "1c")]
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.6), sharey=True)

# Left: Z across 3 layouts
for db, lbl in LAYOUTS:
    d = data.get(("Z", db), {})
    ns = sorted(d)
    ax1.plot(ns, [d[n] for n in ns], "-o", color=LAYOUT_COLORS[db], lw=1.6, ms=4, label=f"layout {lbl}")
ax1.set_title("Workload Z (low-key Zipfian) · layers_N × 3 layouts")
ax1.set_ylabel("first-query latency (µs, async, median)")
ax1.legend(loc="upper right", fontsize=8)

# Right: A vs Z on orig
for w in ["A", "Z"]:
    d = data.get((w, "orig"), {})
    ns = sorted(d)
    ax2.plot(ns, [d[n] for n in ns], "-o", color=WORKLOAD_COLORS[w], lw=1.8, ms=5, label=f"Workload {w}")
ax2.set_title("A vs Z · layout orig · same N=5 elbow → structural")
ax2.legend(loc="upper right", fontsize=9)

for ax in (ax1, ax2):
    ax.set_xscale("symlog", linthresh=1)
    ax.set_xticks([0, 1, 5, 16, 46, 92]); ax.set_xticklabels(["0", "1", "5", "16", "46", "92"])
    ax.set_xlabel("N (interior pages prefetched; N=0=baseline)")
    ax.grid(True, linestyle=":", alpha=0.4)
fig.suptitle("Workload Z robustness check (P0) — hotspot location changes, layers_N behaviour doesn't",
             fontsize=12, y=1.0)
fig.tight_layout()
save(fig, "09_zlowkey_nsweep")

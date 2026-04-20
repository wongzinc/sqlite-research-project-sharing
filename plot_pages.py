#!/usr/bin/env python3
"""plot_pages.py — visualise SQLite page-type layout from classifier CSV.

Usage:  python3 plot_pages.py pages.csv [out.png]

Produces a horizontal strip where each x-position is one page number
and the stripe colour encodes page type. The goal is to answer:
"Are interior pages clustered at the start of the file, or scattered?"
"""
import sys, csv
from collections import Counter
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

if len(sys.argv) < 2:
    sys.exit("usage: plot_pages.py pages.csv [out.png]")

csv_path = sys.argv[1]
out_path = sys.argv[2] if len(sys.argv) > 2 else "page_layout.png"

# ---- read CSV ----
rows = []
with open(csv_path) as f:
    for r in csv.DictReader(f):
        rows.append((int(r["page_number"]), r["page_type"]))
rows.sort()
n = len(rows)

# ---- colour palette: interior = warm, leaf = cool, others = neutral ----
colors = {
    "interior_table":  "#D14520",   # coral — the thing we care about
    "interior_index":  "#7F2418",   # dark coral
    "leaf_table":      "#85B7EB",   # light blue
    "leaf_index":      "#185FA5",   # dark blue
    "freelist_trunk":  "#B4B2A9",   # gray
    "freelist_leaf":   "#D3D1C7",   # lighter gray
    "overflow":        "#EF9F27",   # amber
    "lock_page":       "#E24B4A",   # red
    "unknown":         "#000000",
}

# ---- plot: one vertical line per page, coloured by type ----
fig, ax = plt.subplots(figsize=(14, 2.8))

# Use pcolormesh-style approach: build a 1xN array of colour indices
type_list = list(colors.keys())
type_to_idx = {t: i for i, t in enumerate(type_list)}
arr = np.array([[type_to_idx.get(pt, len(type_list) - 1) for _, pt in rows]])

from matplotlib.colors import ListedColormap
cmap = ListedColormap([colors[t] for t in type_list])
ax.imshow(arr, aspect="auto", cmap=cmap,
          extent=(0.5, n + 0.5, 0, 1),
          vmin=0, vmax=len(type_list) - 1,
          interpolation="nearest")

ax.set_yticks([])
ax.set_xlabel("page number  (file offset →)")
ax.set_title(f"SQLite page-type layout  —  {n} pages total")

present = {pt for _, pt in rows}
patches = [mpatches.Patch(color=colors[t], label=t)
           for t in type_list if t in present]
ax.legend(handles=patches, loc="upper center",
          bbox_to_anchor=(0.5, -0.35), ncol=min(4, len(patches)),
          fontsize=9, frameon=False)

plt.tight_layout()
plt.savefig(out_path, dpi=130, bbox_inches="tight")
print(f"saved {out_path}")

# ---- concentration diagnostic ----
counts = Counter(pt for _, pt in rows)
interior_pos = [pn for pn, pt in rows if pt.startswith("interior")]

print(f"\nTotal pages: {n}")
for t, c in sorted(counts.items(), key=lambda x: -x[1]):
    print(f"  {t:16s} {c:5d}  ({100*c/n:5.2f}%)")

if interior_pos:
    k = len(interior_pos)
    # If perfectly clustered at start, mean position would be (k+1)/2.
    # If uniformly scattered, mean position would be ~n/2.
    mean_pos = sum(interior_pos) / k
    ideal_clustered = (k + 1) / 2
    ideal_scattered = n / 2
    print(f"\nInterior page positions: {interior_pos[:8]}"
          + (" ..." if len(interior_pos) > 8 else ""))
    print(f"  first={min(interior_pos)}  last={max(interior_pos)}  "
          f"spread={max(interior_pos)-min(interior_pos)}")
    print(f"  mean position = {mean_pos:.1f}")
    print(f"    if clustered at start, would be ≈ {ideal_clustered:.1f}")
    print(f"    if uniformly scattered, would be ≈ {ideal_scattered:.1f}")
    ratio = (mean_pos - ideal_clustered) / (ideal_scattered - ideal_clustered)
    print(f"  scatter score: {ratio:.2f}  (0 = clustered, 1 = scattered)")

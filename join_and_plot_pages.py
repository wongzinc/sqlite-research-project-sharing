#!/usr/bin/env python3
"""Join SQLite page classifier output with residency data and plot both.

Usage:
    python3 join_and_plot_pages.py classify.csv residency.csv merged.csv [plot.png]

Inputs:
    classify.csv   page_number,page_type,...
    residency.csv  page_number,is_resident

Outputs:
    merged.csv     page_number,page_type,is_resident
    plot.png       two-row overview:
                   top row    = resident pages
                   bottom row = non-resident pages
                   page type is encoded by color
"""

import csv
import sys
from collections import Counter, defaultdict

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from matplotlib.colors import ListedColormap


COLORS = {
    "interior_table": "#D14520",
    "interior_index": "#7F2418",
    "leaf_table": "#85B7EB",
    "leaf_index": "#185FA5",
    "freelist_trunk": "#B4B2A9",
    "freelist_leaf": "#D3D1C7",
    "overflow": "#EF9F27",
    "lock_page": "#E24B4A",
    "unknown": "#000000",
}

EMPTY_COLOR = "#FFFFFF"


def usage() -> None:
    sys.exit(
        "usage: python3 join_and_plot_pages.py "
        "classify.csv residency.csv merged.csv [plot.png]"
    )


def read_classifier(path: str):
    rows = {}
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        required = {"page_number", "page_type"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"{path}: missing required columns: {', '.join(sorted(missing))}"
            )

        for r in reader:
            page_number = int(r["page_number"])
            if page_number in rows:
                raise ValueError(f"{path}: duplicate page_number {page_number}")
            rows[page_number] = r["page_type"]
    return rows


def read_residency(path: str):
    rows = {}
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = set(reader.fieldnames or [])
        if "page_number" in fieldnames:
            page_col = "page_number"
        else:
            raise ValueError(f"{path}: missing required column: page_number")

        if "is_resident" not in fieldnames:
            raise ValueError(f"{path}: missing required column: is_resident")

        for r in reader:
            page_number = int(r[page_col])
            if page_number in rows:
                raise ValueError(f"{path}: duplicate page number {page_number}")
            rows[page_number] = int(r["is_resident"])
    return rows


def join_rows(classifier_rows, residency_rows):
    classifier_pages = set(classifier_rows)
    residency_pages = set(residency_rows)

    missing_in_residency = sorted(classifier_pages - residency_pages)
    missing_in_classifier = sorted(residency_pages - classifier_pages)
    if missing_in_residency or missing_in_classifier:
        parts = []
        if missing_in_residency:
            parts.append(
                "pages missing in residency: "
                + ", ".join(map(str, missing_in_residency[:10]))
                + (" ..." if len(missing_in_residency) > 10 else "")
            )
        if missing_in_classifier:
            parts.append(
                "pages missing in classifier: "
                + ", ".join(map(str, missing_in_classifier[:10]))
                + (" ..." if len(missing_in_classifier) > 10 else "")
            )
        raise ValueError("; ".join(parts))

    merged = []
    for page_number in sorted(classifier_rows):
        merged.append(
            {
                "page_number": page_number,
                "page_type": classifier_rows[page_number],
                "is_resident": residency_rows[page_number],
            }
        )
    return merged


def write_merged_csv(path: str, merged_rows) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["page_number", "page_type", "is_resident"]
        )
        writer.writeheader()
        writer.writerows(merged_rows)


def plot_rows(path: str, merged_rows) -> None:
    type_list = list(COLORS.keys())
    type_to_idx = {page_type: idx + 1 for idx, page_type in enumerate(type_list)}
    n = len(merged_rows)

    arr = np.zeros((2, n), dtype=int)
    for idx, row in enumerate(merged_rows):
        color_idx = type_to_idx.get(row["page_type"], type_to_idx["unknown"])
        if row["is_resident"]:
            arr[0, idx] = color_idx
        else:
            arr[1, idx] = color_idx

    cmap = ListedColormap([EMPTY_COLOR] + [COLORS[t] for t in type_list])

    fig, ax = plt.subplots(figsize=(14, 3.4))
    ax.imshow(
        arr,
        aspect="auto",
        cmap=cmap,
        extent=(0.5, n + 0.5, 2, 0),
        vmin=0,
        vmax=len(type_list),
        interpolation="nearest",
    )

    ax.set_yticks([0.5, 1.5])
    ax.set_yticklabels(["resident", "non-resident"])
    ax.set_xlabel("page number")
    ax.set_title(f"SQLite page layout by type and residency ({n} pages)")

    type_counts = Counter(row["page_type"] for row in merged_rows)
    resident_counts = defaultdict(int)
    for row in merged_rows:
        if row["is_resident"]:
            resident_counts[row["page_type"]] += 1

    patches = []
    for page_type in type_list:
        if type_counts[page_type] == 0:
            continue
        resident = resident_counts[page_type]
        total = type_counts[page_type]
        patches.append(
            mpatches.Patch(
                color=COLORS[page_type],
                label=f"{page_type} ({resident}/{total} resident)",
            )
        )

    ax.legend(
        handles=patches,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.28),
        ncol=min(3, max(1, len(patches))),
        fontsize=9,
        frameon=False,
    )

    plt.tight_layout()
    plt.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def print_summary(merged_rows) -> None:
    total = len(merged_rows)
    resident_total = sum(row["is_resident"] for row in merged_rows)
    non_resident_total = total - resident_total

    print(f"Total pages:        {total}")
    print(f"Resident pages:     {resident_total} ({100.0 * resident_total / total:.2f}%)")
    print(
        f"Non-resident pages: {non_resident_total} "
        f"({100.0 * non_resident_total / total:.2f}%)"
    )

    per_type = defaultdict(lambda: [0, 0])
    for row in merged_rows:
        per_type[row["page_type"]][0] += 1
        per_type[row["page_type"]][1] += row["is_resident"]

    print("\nPer page type:")
    for page_type, (total_count, resident_count) in sorted(
        per_type.items(), key=lambda item: (-item[1][0], item[0])
    ):
        ratio = 100.0 * resident_count / total_count
        print(
            f"  {page_type:16s} total={total_count:6d} "
            f"resident={resident_count:6d} ({ratio:6.2f}%)"
        )


def main() -> int:
    if len(sys.argv) not in (4, 5):
        usage()

    classify_csv = sys.argv[1]
    residency_csv = sys.argv[2]
    merged_csv = sys.argv[3]
    plot_path = sys.argv[4] if len(sys.argv) == 5 else "page_residency_layout.png"

    classifier_rows = read_classifier(classify_csv)
    residency_rows = read_residency(residency_csv)
    merged_rows = join_rows(classifier_rows, residency_rows)

    write_merged_csv(merged_csv, merged_rows)
    plot_rows(plot_path, merged_rows)
    print_summary(merged_rows)
    print(f"\nWrote merged CSV: {merged_csv}")
    print(f"Wrote plot:       {plot_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

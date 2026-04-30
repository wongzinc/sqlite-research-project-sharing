#!/usr/bin/env python3
"""Plot latency and page-fault metrics from benchmark_harness output.

Usage:
    python3 benchmark_harness_plot_results.py benchmark_harness_operations.csv [out.png] [--max-points N]

Use --max-points 0 to plot every operation.
"""

import argparse
import csv

import matplotlib.pyplot as plt


MAX_PLOT_POINTS = 20000


def usage() -> None:
    raise SystemExit(__doc__)


def sampled_indices(count: int, max_points: int = MAX_PLOT_POINTS) -> list[int]:
    if max_points == 0 or count <= max_points:
        return list(range(count))
    if max_points < 0:
        raise ValueError("--max-points must be >= 0")

    stride = (count + max_points - 1) // max_points
    indices = list(range(0, count, stride))
    if indices[-1] != count - 1:
        indices.append(count - 1)
    return indices


def take(values, indices: list[int]):
    return [values[i] for i in indices]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path")
    parser.add_argument("out_path", nargs="?", default="benchmark_harness_results.png")
    parser.add_argument(
        "--max-points",
        type=int,
        default=MAX_PLOT_POINTS,
        help="maximum sampled points to plot; use 0 to plot every operation",
    )
    args = parser.parse_args()

    csv_path = args.csv_path
    out_path = args.out_path

    query_no = []
    elapsed_us = []
    majflt = []
    minflt = []

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        op_col = "query_no"
        if reader.fieldnames and "op_no" in reader.fieldnames:
            op_col = "op_no"
        required = {
            "elapsed_ns",
            "majflt_delta",
            "minflt_delta",
        }
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"{csv_path}: missing required columns: {', '.join(sorted(missing))}"
            )

        for row in reader:
            query_no.append(int(row[op_col]))
            elapsed_us.append(int(row["elapsed_ns"]) / 1000.0)
            majflt.append(int(row["majflt_delta"]))
            minflt.append(int(row["minflt_delta"]))

    plot_indices = sampled_indices(len(query_no), args.max_points)
    plot_query_no = take(query_no, plot_indices)
    plot_elapsed_us = take(elapsed_us, plot_indices)
    plot_majflt = take(majflt, plot_indices)
    plot_minflt = take(minflt, plot_indices)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True)

    ax1.plot(plot_query_no, plot_elapsed_us, color="#D14520", linewidth=1.3)
    ax1.set_ylabel("latency (us)")
    ax1.set_title("Cold-start benchmark: per-query latency")
    ax1.grid(alpha=0.25, linewidth=0.6)

    ax2.vlines(plot_query_no, 0, plot_majflt, color="#185FA5", alpha=0.85,
               linewidth=0.8, label="major faults")
    ax2.plot(plot_query_no, plot_minflt, color="#EF9F27", linewidth=1.0,
             label="minor faults")
    ax2.set_xlabel("query number")
    ax2.set_ylabel("fault delta")
    ax2.set_title("Page faults per query")
    ax2.grid(alpha=0.25, linewidth=0.6)
    ax2.legend(loc="upper right", frameon=False)

    plt.tight_layout()
    plt.savefig(out_path, dpi=140)
    plt.close(fig)

    print(f"Wrote plot: {out_path}")
    print(f"Queries:    {len(query_no)}")
    if len(plot_query_no) != len(query_no):
        print(f"Plotted:    {len(plot_query_no)} sampled points")
    if query_no:
        print(f"First query latency (us): {elapsed_us[0]:.2f}")
        print(f"Mean latency (us):        {sum(elapsed_us) / len(elapsed_us):.2f}")
        print(f"Total major faults:       {sum(majflt)}")
        print(f"Total minor faults:       {sum(minflt)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

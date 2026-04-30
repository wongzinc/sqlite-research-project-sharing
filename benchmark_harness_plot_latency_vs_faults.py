#!/usr/bin/env python3
"""Plot operation latency versus page fault deltas.

Usage:
    python3 benchmark_harness_plot_latency_vs_faults.py \
        benchmark_harness_operations.csv [out.png] [--faults major|minor|both]

The x-axis is operation latency in microseconds. The y-axis is page fault
delta for that operation, plotted separately for major and minor faults.
The default is --faults major.
"""

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt


def default_output_path(input_path: Path) -> Path:
    return input_path.with_name(input_path.stem + "_latency_vs_faults.png")


def read_operations(path: Path):
    elapsed_us = []
    major_faults = []
    minor_faults = []

    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        required = {"elapsed_ns", "majflt_delta", "minflt_delta"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"{path}: missing required columns: {', '.join(sorted(missing))}"
            )

        for row in reader:
            elapsed_us.append(int(row["elapsed_ns"]) / 1000.0)
            major_faults.append(int(row["majflt_delta"]))
            minor_faults.append(int(row["minflt_delta"]))

    return elapsed_us, major_faults, minor_faults


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_png", type=Path, nargs="?")
    parser.add_argument(
        "--faults",
        choices=("major", "minor", "both"),
        default="major",
        help="which fault delta series to plot",
    )
    args = parser.parse_args()

    input_path = args.input_csv
    output_path = args.output_png or default_output_path(input_path)

    elapsed_us, major_faults, minor_faults = read_operations(input_path)
    if not elapsed_us:
        raise ValueError(f"{input_path}: no data rows")

    fig, ax = plt.subplots(figsize=(12, 6.5))

    if args.faults in ("major", "both"):
        ax.scatter(
            elapsed_us,
            major_faults,
            s=10,
            color="#185FA5",
            alpha=0.65,
            label="major faults",
        )
    if args.faults in ("minor", "both"):
        ax.scatter(
            elapsed_us,
            minor_faults,
            s=10,
            color="#EF9F27",
            alpha=0.45,
            label="minor faults",
        )

    ax.set_xlabel("latency (us)")
    ax.set_ylabel("fault delta")
    ax.set_title(f"Benchmark operation latency vs {args.faults} fault delta")
    ax.grid(alpha=0.25, linewidth=0.6)
    ax.legend(loc="upper right", frameon=False)

    plt.tight_layout()
    plt.savefig(output_path, dpi=140)
    plt.close(fig)

    print(f"Wrote plot: {output_path}")
    print(f"Operations: {len(elapsed_us)}")
    print(f"Total major faults: {sum(major_faults)}")
    print(f"Total minor faults: {sum(minor_faults)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

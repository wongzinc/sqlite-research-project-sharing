#!/usr/bin/env python3
"""Generate a Markdown report from benchmark residency-by-page-type CSV.

Usage:
    python3 benchmark_harness_residency_report.py \
        benchmark_harness_residency_by_page_type.csv [output.md]

If output.md is omitted, the output path is derived from the input path by
replacing its suffix with .md.
"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path


PHASE_ORDER = ["before_madvise", "after_madvise", "after_run"]
PHASE_LABELS = {
    "before_madvise": "before madvise",
    "after_madvise": "after madvise",
    "after_run": "after run",
}

PAGE_TYPE_ORDER = [
    "__all__",
    "interior_table",
    "interior_index",
    "leaf_table",
    "leaf_index",
    "freelist_trunk",
    "freelist_leaf",
    "overflow",
    "lock_page",
    "unknown",
]

SUMMARY_FIELDS = [
    "operation_count",
    "average_latency_us",
    "first_query_latency_us",
    "total_major_page_faults",
    "total_minor_page_faults",
]

REQUIRED_COLUMNS = {
    "benchmark_log_name",
    "phase",
    "page_type",
    "total_pages",
    "resident_pages",
    "residency_rate",
    *SUMMARY_FIELDS,
}


def markdown_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\r\n", "<br>")
        .replace("\n", "<br>")
        .replace("\r", "<br>")
    )


def default_output_path(input_path: Path) -> Path:
    return input_path.with_suffix(".md")


def read_rows(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = REQUIRED_COLUMNS.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"{path}: missing required columns: {', '.join(sorted(missing))}"
            )
        return list(reader)


def page_type_sort_key(page_type: str):
    try:
        return (0, PAGE_TYPE_ORDER.index(page_type), page_type)
    except ValueError:
        return (1, len(PAGE_TYPE_ORDER), page_type)


def percent(rate: str) -> str:
    return f"{float(rate) * 100.0:.2f}%"


def resident_cell(row) -> str:
    return f"{row['resident_pages']} ({percent(row['residency_rate'])})"


def build_report(rows) -> str:
    by_log = defaultdict(list)
    for row in rows:
        by_log[row["benchmark_log_name"]].append(row)

    lines = ["# Benchmark Harness Residency By Page Type", ""]

    for log_name in sorted(by_log):
        log_rows = by_log[log_name]
        lines.extend([f"## {markdown_escape(log_name)}", ""])

        summary = log_rows[0]
        for field in SUMMARY_FIELDS:
            lines.append(f"- `{field}`: {markdown_escape(summary[field])}")
        lines.append("")

        by_page_type = defaultdict(dict)
        total_pages_by_type = {}
        for row in log_rows:
            page_type = row["page_type"]
            phase = row["phase"]
            by_page_type[page_type][phase] = row
            total_pages_by_type[page_type] = row["total_pages"]

        page_types = sorted(by_page_type, key=page_type_sort_key)

        header = [
            "page_type",
            "total_pages",
            *[PHASE_LABELS[phase] for phase in PHASE_ORDER],
        ]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join(["---"] * len(header)) + " |")

        for page_type in page_types:
            cells = [
                markdown_escape(page_type),
                total_pages_by_type[page_type],
            ]
            for phase in PHASE_ORDER:
                row = by_page_type[page_type].get(phase)
                cells.append(resident_cell(row) if row else "")
            lines.append("| " + " | ".join(cells) + " |")

        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_md", type=Path, nargs="?")
    args = parser.parse_args()

    input_path = args.input_csv
    output_path = args.output_md or default_output_path(input_path)

    rows = read_rows(input_path)
    report = build_report(rows)
    output_path.write_text(report, encoding="utf-8")

    print(f"Wrote Markdown report: {output_path}")
    print(f"Input rows: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

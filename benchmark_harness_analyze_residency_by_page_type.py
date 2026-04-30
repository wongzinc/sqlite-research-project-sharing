#!/usr/bin/env python3
"""Analyze benchmark residency by SQLite page type.

Usage:
    python3 benchmark_harness_analyze_residency_by_page_type.py \
        classify_pages.csv benchmark_harness_runs/run.log \
        benchmark_harness_residency_by_page_type.csv

Inputs:
    classify_pages.csv  Output from classify_pages:
                        page_number,page_type,file_offset
    run.log             Benchmark harness run record with resident ranges for:
                        before madvise, after madvise, after run

Output:
    benchmark_harness_residency_by_page_type.csv
        Appendable per-phase, per-page-type residency rates plus benchmark summary.
"""

import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


PAGE_TYPE_ORDER = [
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

PHASE_ORDER = ["before_madvise", "after_madvise", "after_run"]

LABEL_TO_PHASE = {
    "before madvise": "before_madvise",
    "after madvise": "after_madvise",
    "after run": "after_run",
}

DIST_RE = re.compile(
    r"^(?P<label>.+) resident-page distribution: "
    r"count=(?P<count>\d+) first=(?P<first>\d+) last=(?P<last>\d+) "
    r"first_1%=(?P<first_1pct>\d+) first_5%=(?P<first_5pct>\d+) "
    r"first_10%=(?P<first_10pct>\d+)$"
)

RANGE_RE = re.compile(
    r"^(?P<label>.+) resident range\[(?P<idx>\d+)\]="
    r"(?P<start>\d+)-(?P<end>\d+)$"
)

SUMMARY_RE = re.compile(
    r"^ops=(?P<operation_count>\d+) "
    r"avg_latency_us=(?P<average_latency_us>[0-9.]+) "
    r"total_majflt=(?P<total_major_page_faults>-?\d+) "
    r"total_minflt=(?P<total_minor_page_faults>-?\d+) "
    r"first_query_latency_us=(?P<first_query_latency_us>[0-9.]+)$"
)


def usage() -> None:
    sys.exit(
        "usage: python3 benchmark_harness_analyze_residency_by_page_type.py "
        "classify_pages.csv benchmark_harness_runs/run.log "
        "benchmark_harness_residency_by_page_type.csv"
    )


def normalize_phase(label: str) -> str:
    phase = LABEL_TO_PHASE.get(label.strip())
    if phase is None:
        raise ValueError(f"unknown benchmark residency phase label: {label!r}")
    return phase


def read_classifier(path: str) -> Dict[int, str]:
    pages: Dict[int, str] = {}
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        required = {"page_number", "page_type"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"{path}: missing required columns: {', '.join(sorted(missing))}"
            )

        for row in reader:
            page_number = int(row["page_number"])
            if page_number in pages:
                raise ValueError(f"{path}: duplicate page_number {page_number}")
            pages[page_number] = row["page_type"]

    if not pages:
        raise ValueError(f"{path}: no classifier rows")
    return pages


def read_benchmark_record(path: str):
    ranges: Dict[str, List[Tuple[int, int]]] = defaultdict(list)
    distributions = {}
    summary = {
        "operation_count": "",
        "average_latency_us": "",
        "first_query_latency_us": "",
        "total_major_page_faults": "",
        "total_minor_page_faults": "",
    }

    with open(path, newline="") as f:
        for lineno, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue

            dist_match = DIST_RE.match(line)
            if dist_match:
                phase = normalize_phase(dist_match.group("label"))
                distributions[phase] = {
                    key: int(value)
                    for key, value in dist_match.groupdict().items()
                    if key != "label"
                }
                continue

            range_match = RANGE_RE.match(line)
            if range_match:
                phase = normalize_phase(range_match.group("label"))
                start = int(range_match.group("start"))
                end = int(range_match.group("end"))
                if end < start:
                    raise ValueError(
                        f"{path}:{lineno}: invalid resident range {start}-{end}"
                    )
                ranges[phase].append((start, end))
                continue

            summary_match = SUMMARY_RE.match(line)
            if summary_match:
                summary = summary_match.groupdict()

    missing_phases = [phase for phase in PHASE_ORDER if phase not in distributions]
    if missing_phases:
        raise ValueError(
            f"{path}: missing resident-page distribution for: "
            + ", ".join(missing_phases)
        )

    return ranges, distributions, summary


def iter_resident_pages(ranges: Iterable[Tuple[int, int]]) -> Iterable[int]:
    for start, end in ranges:
        yield from range(start, end + 1)


def count_resident_by_type(
    classifier_pages: Dict[int, str],
    ranges: Dict[str, List[Tuple[int, int]]],
    distributions,
) -> Dict[str, Counter]:
    by_phase: Dict[str, Counter] = {}
    valid_pages = set(classifier_pages)

    for phase in PHASE_ORDER:
        counter: Counter = Counter()
        seen_pages = set()
        for page_number in iter_resident_pages(ranges.get(phase, [])):
            if page_number not in valid_pages:
                raise ValueError(
                    f"benchmark record has resident page {page_number}, "
                    "but classifier CSV does not contain that page"
                )
            if page_number in seen_pages:
                continue
            seen_pages.add(page_number)
            counter[classifier_pages[page_number]] += 1
        expected = distributions[phase]["count"]
        actual = len(seen_pages)
        if actual != expected:
            raise ValueError(
                f"{phase}: resident range coverage has {actual} pages, "
                f"but distribution count says {expected}. "
                "Use a benchmark run log that contains complete resident ranges."
            )
        by_phase[phase] = counter

    return by_phase


def sorted_page_types(type_totals: Counter) -> List[str]:
    ordered = [page_type for page_type in PAGE_TYPE_ORDER if type_totals[page_type]]
    extras = sorted(
        page_type for page_type in type_totals if page_type not in PAGE_TYPE_ORDER
    )
    return ordered + extras


def write_analysis_csv(
    path: str,
    benchmark_log: str,
    classifier_pages: Dict[int, str],
    resident_by_phase: Dict[str, Counter],
    distributions,
    summary,
) -> None:
    type_totals = Counter(classifier_pages.values())
    page_types = sorted_page_types(type_totals)
    total_pages = len(classifier_pages)
    output_path = Path(path)
    log_path = Path(benchmark_log)

    fieldnames = [
        "benchmark_log_name",
        "phase",
        "page_type",
        "total_pages",
        "resident_pages",
        "nonresident_pages",
        "residency_rate",
        "phase_resident_pages",
        "phase_first_resident_page",
        "phase_last_resident_page",
        "operation_count",
        "average_latency_us",
        "first_query_latency_us",
        "total_major_page_faults",
        "total_minor_page_faults",
    ]

    should_write_header = not output_path.exists() or output_path.stat().st_size == 0
    if not should_write_header:
        with output_path.open(newline="") as existing:
            reader = csv.reader(existing)
            existing_header = next(reader, None)
        if existing_header != fieldnames:
            raise ValueError(
                f"{path}: existing CSV header does not match the current schema. "
                "Write to a new output file or remove the old one."
            )

    with output_path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if should_write_header:
            writer.writeheader()

        for phase in PHASE_ORDER:
            phase_counts = resident_by_phase[phase]
            dist = distributions[phase]

            all_resident = sum(phase_counts.values())
            writer.writerow(
                {
                    "benchmark_log_name": log_path.name,
                    "phase": phase,
                    "page_type": "__all__",
                    "total_pages": total_pages,
                    "resident_pages": all_resident,
                    "nonresident_pages": total_pages - all_resident,
                    "residency_rate": f"{all_resident / total_pages:.8f}",
                    "phase_resident_pages": dist["count"],
                    "phase_first_resident_page": dist["first"],
                    "phase_last_resident_page": dist["last"],
                    **summary,
                }
            )

            for page_type in page_types:
                total = type_totals[page_type]
                resident = phase_counts[page_type]
                writer.writerow(
                    {
                        "benchmark_log_name": log_path.name,
                        "phase": phase,
                        "page_type": page_type,
                        "total_pages": total,
                        "resident_pages": resident,
                        "nonresident_pages": total - resident,
                        "residency_rate": f"{resident / total:.8f}",
                        "phase_resident_pages": dist["count"],
                        "phase_first_resident_page": dist["first"],
                        "phase_last_resident_page": dist["last"],
                        **summary,
                    }
                )


def print_summary(classifier_pages, resident_by_phase) -> None:
    type_totals = Counter(classifier_pages.values())
    page_types = sorted_page_types(type_totals)

    for phase in PHASE_ORDER:
        print(f"\n{phase}:")
        phase_counts = resident_by_phase[phase]
        all_resident = sum(phase_counts.values())
        total_pages = len(classifier_pages)
        print(
            f"  {'__all__':16s} total={total_pages:6d} "
            f"resident={all_resident:6d} rate={100.0 * all_resident / total_pages:6.2f}%"
        )
        for page_type in page_types:
            total = type_totals[page_type]
            resident = phase_counts[page_type]
            print(
                f"  {page_type:16s} total={total:6d} "
                f"resident={resident:6d} rate={100.0 * resident / total:6.2f}%"
            )


def main() -> int:
    if len(sys.argv) != 4:
        usage()

    classify_csv = sys.argv[1]
    benchmark_log = sys.argv[2]
    output_csv = sys.argv[3]

    classifier_pages = read_classifier(classify_csv)
    ranges, distributions, summary = read_benchmark_record(benchmark_log)
    resident_by_phase = count_resident_by_type(
        classifier_pages, ranges, distributions
    )
    write_analysis_csv(
        output_csv,
        benchmark_log,
        classifier_pages,
        resident_by_phase,
        distributions,
        summary,
    )
    print_summary(classifier_pages, resident_by_phase)
    print(f"\nAppended residency-by-page-type CSV: {output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

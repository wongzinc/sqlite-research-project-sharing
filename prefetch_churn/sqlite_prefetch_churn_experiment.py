#!/usr/bin/env python3
"""
Copy a SQLite database, replay an existing workload, and re-sample page types.

This is intended for the existing test.db built by testdb_builder.py:

    CREATE TABLE items (
      id INTEGER PRIMARY KEY,
      k1 TEXT NOT NULL,
      k2 TEXT NOT NULL,
      payload BLOB NOT NULL
    );
    CREATE INDEX idx_items_k1 ON items(k1);
    CREATE INDEX idx_items_k2 ON items(k2);

The script intentionally reuses existing repo artifacts:

* a write workload supplies read/update/insert/scan/RMW operations to mutate the
  DB between checkpoints.
* a benchmark workload supplies read/scan operations for cold-start latency
  measurement at each checkpoint.
* classify_pages.c, normally built with `make classify_pages`, supplies page
  type classification.
* benchmark_harness can measure cold-start query latency at each checkpoint.
* prefetch_vacuum/src/prefetch* can prefetch current interior pages between
  the cold-cache reset and benchmark_harness query measurement.

SQLite DELETE can be mapped onto readmodifywrite operations for this experiment:
the write workload chooses a key to read and then "modify"; here, that
modification can be deleting the row. A periodic delete policy is also available
for workloads that do not contain readmodifywrite operations.

When --run-benchmarks is enabled, only the drop-cache helper is run through
sudo -n when the script is not already root. All prefetch, benchmark, classifier,
residency, and write steps run without elevated privileges.
"""

from __future__ import annotations

import argparse
import csv
import os
import shlex
import subprocess
import shutil
import sqlite3
import stat
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO


INTERIOR_TYPES = {"interior_index", "interior_table"}
DEFAULT_OUTPUT_DIR = "sqlite_page_churn_runs"


def default_run_dir(prefetch_mode: str) -> Path:
    suffix = "no_prefetch" if prefetch_mode == "none" else f"prefetch_{prefetch_mode}"
    return Path(DEFAULT_OUTPUT_DIR) / suffix


def fill_default_output_paths(args: argparse.Namespace) -> argparse.Namespace:
    run_dir = default_run_dir(args.prefetch_mode)
    if args.work_db is None:
        args.work_db = str(run_dir / "test_churn.db")
    if args.checkpoint_dir is None:
        args.checkpoint_dir = str(run_dir / "checkpoints")
    if args.summary_csv is None:
        args.summary_csv = str(run_dir / "interior_page_churn_summary.csv")
    if args.interior_pages_csv is None:
        args.interior_pages_csv = str(run_dir / "interior_page_churn_pages.csv")
    if args.benchmark_dir is None:
        args.benchmark_dir = str(run_dir / "benchmarks")
    if args.benchmark_summary_csv is None:
        args.benchmark_summary_csv = str(run_dir / "sqlite_page_churn_benchmark_summary.csv")
    return args


@dataclass(frozen=True)
class PageSnapshot:
    label: str
    operation_count: int
    inserted_total: int
    deleted_total: int
    row_count: int
    page_size: int
    page_count: int
    freelist_count: int
    counts: Counter[str]
    pages_by_type: dict[str, set[int]]

    @property
    def interior_pages(self) -> set[int]:
        pages: set[int] = set()
        for page_type in INTERIOR_TYPES:
            pages.update(self.pages_by_type.get(page_type, set()))
        return pages


@dataclass(frozen=True)
class BenchmarkResult:
    label: str
    operation_count: int
    benchmark_record: str
    operations_csv: str
    classify_csv: str
    prefetch_script: str
    residency_before_csv: str
    residency_before_join_csv: str
    residency_after_csv: str
    residency_after_join_csv: str
    average_latency_us: str
    first_query_latency_us: str
    total_major_page_faults: str
    total_minor_page_faults: str


def ensure_classifier(classifier: Path, build: bool) -> None:
    if classifier.exists():
        return
    if not build:
        raise RuntimeError(f"classifier not found: {classifier}")
    subprocess.run(["make", "classify_pages"], check=True)
    if not classifier.exists():
        raise RuntimeError(f"classifier still not found after build: {classifier}")


def ensure_path(path: Path, description: str) -> None:
    if not path.exists():
        raise RuntimeError(f"{description} not found: {path}")


def executable_path(path: Path) -> str:
    return str(path.resolve()) if path.exists() else str(path)


def make_executable(path: Path) -> None:
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def run_checkpoint_plot(plot_script: Path, csv_path: Path, png_path: Path) -> None:
    subprocess.run(
        ["python3", str(plot_script), str(csv_path), str(png_path)],
        check=True,
    )


def classify_pages(
    db_path: Path, classifier: Path, raw_csv_path: Path | None = None
) -> tuple[int, int, int, Counter[str], dict[str, set[int]]]:
    result = subprocess.run(
        [executable_path(classifier), str(db_path)],
        check=True,
        text=True,
        capture_output=True,
    )
    if raw_csv_path is not None:
        raw_csv_path.parent.mkdir(parents=True, exist_ok=True)
        raw_csv_path.write_text(result.stdout, encoding="utf-8", newline="")

    counts: Counter[str] = Counter()
    pages_by_type: dict[str, set[int]] = {}
    reader = csv.DictReader(result.stdout.splitlines())
    for row in reader:
        page_number = int(row["page_number"])
        page_type = row["page_type"]
        counts[page_type] += 1
        pages_by_type.setdefault(page_type, set()).add(page_number)

    with sqlite3.connect(db_path) as conn:
        page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
        page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
        freelist_count = int(conn.execute("PRAGMA freelist_count").fetchone()[0])

    return page_size, page_count, freelist_count, counts, pages_by_type


def parse_benchmark_record(record_path: Path) -> dict[str, str]:
    summary = {
        "operation_count": "",
        "output_csv": "",
        "average_latency_us": "",
        "first_query_latency_us": "",
        "total_major_page_faults": "",
        "total_minor_page_faults": "",
    }
    for line in record_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("output="):
            summary["output_csv"] = line.partition("=")[2].strip()
            continue
        if not line.startswith("ops="):
            continue
        for part in line.split():
            key, _, value = part.partition("=")
            if key == "ops":
                summary["operation_count"] = value
            elif key == "avg_latency_us":
                summary["average_latency_us"] = value
            elif key == "first_query_latency_us":
                summary["first_query_latency_us"] = value
            elif key == "total_majflt":
                summary["total_major_page_faults"] = value
            elif key == "total_minflt":
                summary["total_minor_page_faults"] = value
    return summary


def benchmark_record_from_stderr(stderr: str) -> Path:
    for line in stderr.splitlines():
        prefix = "benchmark record: "
        if line.startswith(prefix):
            return Path(line[len(prefix) :].strip())
    raise RuntimeError("benchmark_harness did not report a run record path")


def write_prefetch_wrapper(
    path: Path,
    prefetch_tool: Path,
    db_path: Path,
    classify_csv: Path,
    mode: str,
    page_size: int,
    n_pages: int,
    hotpages_csv: Path | None = None,
    cap_interior: int = 0,
    cap_leaf: int = 0,
) -> None:
    if mode == "none":
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    if mode in {"range", "perpage"}:
        command = " ".join(
            [
                shlex.quote(executable_path(prefetch_tool)),
                shlex.quote(str(db_path.resolve())),
                shlex.quote(str(classify_csv.resolve())),
                shlex.quote(mode),
                str(page_size),
            ]
        )
    elif mode == "layers":
        command = " ".join(
            [
                shlex.quote(executable_path(prefetch_tool)),
                shlex.quote(str(db_path.resolve())),
                shlex.quote(str(classify_csv.resolve())),
                str(n_pages),
                str(page_size),
            ]
        )
    elif mode in {"access-2d", "access-2e"}:
        if hotpages_csv is None:
            raise RuntimeError(f"mode {mode} requires --prefetch-hotpages")
        leaf = 0 if mode == "access-2d" else cap_leaf
        command = " ".join(
            [
                shlex.quote(executable_path(prefetch_tool)),
                shlex.quote(str(db_path.resolve())),
                shlex.quote(str(classify_csv.resolve())),
                shlex.quote(str(hotpages_csv.resolve())),
                str(cap_interior),
                str(leaf),
                str(page_size),
            ]
        )
    else:
        raise RuntimeError(f"unsupported prefetch mode: {mode}")

    path.write_text(f"#!/bin/sh\nset -eu\nexec {command}\n", encoding="utf-8", newline="\n")
    make_executable(path)


def run_residency_checker(
    db_path: Path,
    page_size: int,
    classifier_csv: Path,
    residency_checker: Path,
    join_script: Path,
    residency_csv: Path,
    joined_csv: Path,
    plot_png: Path | None,
) -> None:
    residency_csv.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            executable_path(residency_checker),
            str(db_path),
            str(page_size),
            str(residency_csv),
        ],
        check=True,
    )
    command = [
        "python3",
        str(join_script),
        str(classifier_csv),
        str(residency_csv),
        str(joined_csv),
    ]
    if plot_png is not None:
        command.append(str(plot_png))
    subprocess.run(command, check=True)


def write_post_cold_wrapper(
    path: Path,
    args: argparse.Namespace,
    prefetch_script: Path,
    db_path: Path,
    page_size: int,
    classify_csv: Path,
    residency_before_csv: Path,
    residency_before_join_csv: Path,
    residency_plot: Path | None,
) -> None:
    lines = ["#!/bin/sh", "set -eu"]

    if args.prefetch_mode != "none":
        lines.append(shlex.join([str(prefetch_script.resolve())]))

    if args.run_residency_checker:
        lines.append(
            shlex.join(
                [
                    executable_path(Path(args.residency_checker)),
                    str(db_path),
                    str(page_size),
                    str(residency_before_csv),
                ]
            )
        )
        join_command = [
            "python3",
            str(Path(args.residency_join_script)),
            str(classify_csv),
            str(residency_before_csv),
            str(residency_before_join_csv),
        ]
        if residency_plot is not None:
            join_command.append(str(residency_plot))
        lines.append(shlex.join(join_command))

    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    make_executable(path)


def run_measurement_segment_in_systemd_scope(
    args: argparse.Namespace,
    label: str,
    benchmark_dir: Path,
    benchmark_command: list[str],
    benchmark_stdout: Path,
    benchmark_stderr: Path,
) -> None:
    segment_script = benchmark_dir / f"measurement_{label}.sh"
    lines = ["#!/bin/sh", "set -eu"]

    lines.append(
        f"{shlex.join(benchmark_command)} > {shlex.quote(str(benchmark_stdout))} "
        f"2> {shlex.quote(str(benchmark_stderr))}"
    )
    segment_script.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    make_executable(segment_script)

    subprocess.run(
        [
            "systemd-run",
            "--user",
            "--scope",
            "--quiet",
            f"--working-directory={Path.cwd()}",
            "-p",
            f"MemoryMax={args.systemd_memory_max}",
            "--",
            str(segment_script.resolve()),
        ],
        check=True,
    )


def run_benchmark_round(
    args: argparse.Namespace,
    label: str,
    db_path: Path,
    classify_csv: Path,
    page_size: int,
    operation_count: int,
) -> BenchmarkResult | None:
    if not args.run_benchmarks:
        return None

    benchmark_dir = Path(args.benchmark_dir)
    benchmark_dir.mkdir(parents=True, exist_ok=True)
    (benchmark_dir / "runs").mkdir(parents=True, exist_ok=True)

    prefetch_script = benchmark_dir / f"prefetch_{label}.sh"
    if args.prefetch_mode != "none":
        prefetch_tool = Path(args.prefetch_tool)
        write_prefetch_wrapper(
            prefetch_script,
            prefetch_tool,
            db_path,
            classify_csv,
            args.prefetch_mode,
            page_size,
            args.prefetch_pages,
            hotpages_csv=Path(args.prefetch_hotpages) if args.prefetch_hotpages else None,
            cap_interior=args.prefetch_cap_interior,
            cap_leaf=args.prefetch_cap_leaf,
        )
    else:
        prefetch_script = Path("")

    residency_before_csv = benchmark_dir / f"residency_before_{label}.csv"
    residency_before_join_csv = benchmark_dir / f"residency_before_joined_{label}.csv"
    residency_after_csv = benchmark_dir / f"residency_after_{label}.csv"
    residency_after_join_csv = benchmark_dir / f"residency_after_joined_{label}.csv"
    residency_before_plot = (
        benchmark_dir / f"residency_before_{label}.png" if args.plot_residency else None
    )
    residency_after_plot = (
        benchmark_dir / f"residency_after_{label}.png" if args.plot_residency else None
    )
    operations_csv = benchmark_dir / f"ops_{label}.csv"
    post_cold_script: Path | None = benchmark_dir / f"post_cold_{label}.sh"
    if args.prefetch_mode != "none" or args.run_residency_checker:
        write_post_cold_wrapper(
            post_cold_script,
            args,
            prefetch_script,
            db_path,
            page_size,
            classify_csv,
            residency_before_csv,
            residency_before_join_csv,
            residency_before_plot,
        )
    else:
        post_cold_script = None

    command = [
        executable_path(Path(args.benchmark_harness)),
        "--db",
        str(db_path),
        "--workload",
        str(Path(args.benchmark_workload)),
        "--output",
        str(operations_csv),
        "--record-dir",
        str(benchmark_dir / "runs"),
        "--cold-advice",
        args.benchmark_cold_advice,
        "--sqlite-open-timing",
        args.benchmark_sqlite_open_timing,
        "--schema-init-timing",
        args.benchmark_schema_init_timing,
    ]
    if args.drop_caches_script:
        command.extend(["--drop-caches-script", executable_path(Path(args.drop_caches_script))])
    if post_cold_script is not None:
        command.extend(["--post-cold-script", str(post_cold_script.resolve())])
    if args.benchmark_debug:
        command.append("--debug")

    if args.systemd_memory_max:
        benchmark_stdout = benchmark_dir / f"benchmark_{label}.stdout"
        benchmark_stderr = benchmark_dir / f"benchmark_{label}.stderr"
        run_measurement_segment_in_systemd_scope(
            args,
            label,
            benchmark_dir,
            command,
            benchmark_stdout,
            benchmark_stderr,
        )
        stdout_text = benchmark_stdout.read_text(encoding="utf-8")
        stderr_text = benchmark_stderr.read_text(encoding="utf-8")
    else:
        result = subprocess.run(command, check=True, text=True, capture_output=True)
        stdout_text = result.stdout
        stderr_text = result.stderr

    if stdout_text:
        print(stdout_text, end="")
    if stderr_text:
        print(stderr_text, end="")

    record_path = benchmark_record_from_stderr(stderr_text)
    summary = parse_benchmark_record(record_path)

    if args.run_residency_checker:
        run_residency_checker(
            db_path,
            page_size,
            classify_csv,
            Path(args.residency_checker),
            Path(args.residency_join_script),
            residency_after_csv,
            residency_after_join_csv,
            residency_after_plot,
        )

    return BenchmarkResult(
        label=label,
        operation_count=operation_count,
        benchmark_record=str(record_path),
        operations_csv=summary["output_csv"] or str(operations_csv),
        classify_csv=str(classify_csv),
        prefetch_script=str(prefetch_script) if args.prefetch_mode != "none" else "",
        residency_before_csv=str(residency_before_csv) if args.run_residency_checker else "",
        residency_before_join_csv=str(residency_before_join_csv) if args.run_residency_checker else "",
        residency_after_csv=str(residency_after_csv) if args.run_residency_checker else "",
        residency_after_join_csv=str(residency_after_join_csv) if args.run_residency_checker else "",
        average_latency_us=summary["average_latency_us"],
        first_query_latency_us=summary["first_query_latency_us"],
        total_major_page_faults=summary["total_major_page_faults"],
        total_minor_page_faults=summary["total_minor_page_faults"],
    )


def configure_connection(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=OFF;
        PRAGMA synchronous=OFF;
        PRAGMA temp_store=MEMORY;
        PRAGMA cache_size=-200000;
        """
    )


def max_item_id(conn: sqlite3.Connection) -> int:
    value = conn.execute("SELECT COALESCE(MAX(id), 0) FROM items").fetchone()[0]
    return int(value)


def item_count(conn: sqlite3.Connection) -> int:
    value = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    return int(value)


def take_snapshot(
    db_path: Path,
    conn: sqlite3.Connection,
    classifier: Path,
    checkpoint_dir: Path,
    plot_script: Path | None,
    label: str,
    operation_count: int,
    inserted_total: int,
    deleted_total: int,
) -> PageSnapshot:
    conn.commit()
    raw_csv_path = checkpoint_dir / f"classify_pages_{label}.csv"
    png_path = checkpoint_dir / f"layout_{label}.png"
    page_size, page_count, freelist_count, counts, pages_by_type = classify_pages(
        db_path, classifier, raw_csv_path
    )
    if plot_script is not None:
        run_checkpoint_plot(plot_script, raw_csv_path, png_path)
    return PageSnapshot(
        label=label,
        operation_count=operation_count,
        inserted_total=inserted_total,
        deleted_total=deleted_total,
        row_count=item_count(conn),
        page_size=page_size,
        page_count=page_count,
        freelist_count=freelist_count,
        counts=counts,
        pages_by_type=pages_by_type,
    )


def insert_item(conn: sqlite3.Connection, item_id: int, payload_size: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO items(id, k1, k2, payload) VALUES (?, ?, ?, ?)",
        (
            item_id,
            f"churn_group_{item_id % 1000:04d}",
            f"churn_tag_{item_id:012d}",
            os.urandom(payload_size),
        ),
    )


def delete_batch(conn: sqlite3.Connection, next_delete_id: int, batch_size: int) -> tuple[int, int]:
    cursor = conn.execute(
        "DELETE FROM items WHERE id IN "
        "(SELECT id FROM items WHERE id >= ? ORDER BY id LIMIT ?)",
        (next_delete_id, batch_size),
    )
    return next_delete_id + batch_size, cursor.rowcount


def update_item(conn: sqlite3.Connection, item_id: int, payload_size: int) -> None:
    conn.execute(
        "UPDATE items SET payload = ?, k2 = ? WHERE id = ?",
        (os.urandom(payload_size), f"updated_tag_{item_id:012d}", item_id),
    )


def read_item(conn: sqlite3.Connection, item_id: int) -> None:
    conn.execute("SELECT payload FROM items WHERE id = ?", (item_id,)).fetchone()


def scan_items(conn: sqlite3.Connection, item_id: int, scan_length: int) -> None:
    conn.execute(
        "SELECT id FROM items WHERE id >= ? ORDER BY id LIMIT ?",
        (item_id, scan_length),
    ).fetchall()


def replay_workload_chunk(
    conn: sqlite3.Connection,
    workload_file: TextIO,
    max_ops: int,
    payload_size: int,
    delete_every: int,
    delete_batch_size: int,
    next_delete_id: int,
    next_insert_id: int,
    rmw_action: str,
) -> tuple[int, int, int, int, int]:
    replayed = 0
    inserted = 0
    deleted = 0

    while replayed < max_ops:
        raw_line = workload_file.readline()
        if not raw_line:
            break
        parts = raw_line.strip().split()
        if not parts:
            continue

        op = parts[0]
        key = int(parts[1]) if len(parts) > 1 else 0
        if op == "insert":
            insert_item(conn, next_insert_id, payload_size)
            next_insert_id += 1
            inserted += 1
        elif op == "update":
            update_item(conn, key, payload_size)
        elif op == "read":
            read_item(conn, key)
        elif op == "scan":
            scan_items(conn, key, int(parts[2]))
        elif op == "readmodifywrite":
            read_item(conn, key)
            if rmw_action == "delete":
                cursor = conn.execute("DELETE FROM items WHERE id = ?", (key,))
                deleted += cursor.rowcount
            elif rmw_action == "update":
                update_item(conn, key, payload_size)
            else:
                raise RuntimeError(f"unsupported --rmw-action: {rmw_action}")
        else:
            raise RuntimeError(f"unsupported workload operation: {raw_line.rstrip()}")

        replayed += 1
        if delete_every > 0 and replayed % delete_every == 0:
            next_delete_id, batch_deleted = delete_batch(
                conn, next_delete_id, delete_batch_size
            )
            deleted += batch_deleted

    return replayed, inserted, deleted, next_delete_id, next_insert_id


def replay_insert_workload_chunk(
    conn: sqlite3.Connection,
    workload_file: TextIO,
    max_ops: int,
    payload_size: int,
    next_insert_id: int,
) -> tuple[int, int, int]:
    replayed = 0
    inserted = 0

    while replayed < max_ops:
        raw_line = workload_file.readline()
        if not raw_line:
            break
        parts = raw_line.strip().split()
        if not parts:
            continue

        replayed += 1
        if parts[0] != "insert":
            continue

        insert_item(conn, next_insert_id, payload_size)
        next_insert_id += 1
        inserted += 1

    return replayed, inserted, next_insert_id


def summarize_new_pages(previous: PageSnapshot, current: PageSnapshot) -> dict[str, object]:
    previous_interior = previous.interior_pages
    current_interior = current.interior_pages
    new_pages = sorted(current_interior - previous_interior)
    removed_pages = sorted(previous_interior - current_interior)
    previous_freelist = (
        previous.pages_by_type.get("freelist_leaf", set())
        | previous.pages_by_type.get("freelist_trunk", set())
    )
    reused_pages = sorted(page for page in new_pages if page in previous_freelist)

    previous_max_page = previous.page_count
    appended_pages = [page for page in new_pages if page > previous_max_page]
    in_file_pages = [page for page in new_pages if page <= previous_max_page]

    return {
        "new_interior_count": len(new_pages),
        "removed_interior_count": len(removed_pages),
        "new_min_page": min(new_pages) if new_pages else "",
        "new_max_page": max(new_pages) if new_pages else "",
        "new_appended_count": len(appended_pages),
        "new_in_file_count": len(in_file_pages),
        "new_reused_freelist_count": len(reused_pages),
        "new_pages_preview": " ".join(map(str, new_pages[:40])),
        "removed_pages_preview": " ".join(map(str, removed_pages[:40])),
    }


def snapshot_row(previous: PageSnapshot | None, current: PageSnapshot) -> dict[str, object]:
    interior_table = current.counts.get("interior_table", 0)
    interior_index = current.counts.get("interior_index", 0)
    leaf_table = current.counts.get("leaf_table", 0)
    leaf_index = current.counts.get("leaf_index", 0)
    freelist = current.counts.get("freelist_trunk", 0) + current.counts.get("freelist_leaf", 0)
    overflow = current.counts.get("overflow", 0)

    row: dict[str, object] = {
        "label": current.label,
        "operation_count": current.operation_count,
        "inserted_total": current.inserted_total,
        "deleted_total": current.deleted_total,
        "row_count": current.row_count,
        "page_size": current.page_size,
        "page_count": current.page_count,
        "freelist_count_header": current.freelist_count,
        "interior_total": interior_table + interior_index,
        "interior_table": interior_table,
        "interior_index": interior_index,
        "leaf_total": leaf_table + leaf_index,
        "leaf_table": leaf_table,
        "leaf_index": leaf_index,
        "freelist_total_classified": freelist,
        "overflow": overflow,
        "interior_pct": (interior_table + interior_index) * 100.0 / current.page_count,
    }
    if previous is None:
        row.update(
            {
                "new_interior_count": "",
                "removed_interior_count": "",
                "new_min_page": "",
                "new_max_page": "",
                "new_appended_count": "",
                "new_in_file_count": "",
                "new_reused_freelist_count": "",
                "new_pages_preview": "",
                "removed_pages_preview": "",
            }
        )
    else:
        row.update(summarize_new_pages(previous, current))
    return row


def write_snapshot_csv(path: Path, snapshots: list[PageSnapshot]) -> None:
    rows = [
        snapshot_row(snapshots[index - 1] if index else None, snapshot)
        for index, snapshot in enumerate(snapshots)
    ]
    fieldnames: list[str] = []
    for row in rows:
        for name in row:
            if name not in fieldnames:
                fieldnames.append(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_interior_pages_csv(path: Path, snapshots: list[PageSnapshot]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(["label", "operation_count", "page_number", "page_type"])
        for snapshot in snapshots:
            for page_type in sorted(INTERIOR_TYPES):
                for page_number in sorted(snapshot.pages_by_type.get(page_type, set())):
                    writer.writerow([snapshot.label, snapshot.operation_count, page_number, page_type])


def write_benchmark_csv(path: Path, results: list[BenchmarkResult]) -> None:
    if not results:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "label",
        "operation_count",
        "benchmark_record",
        "operations_csv",
        "classify_csv",
        "prefetch_script",
        "residency_before_csv",
        "residency_before_join_csv",
        "residency_after_csv",
        "residency_after_join_csv",
        "average_latency_us",
        "first_query_latency_us",
        "total_major_page_faults",
        "total_minor_page_faults",
    ]
    with path.open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow({name: getattr(result, name) for name in fieldnames})


def prepare_checkpoint_dir(path: Path, force: bool) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if not force:
        return
    for old_checkpoint in path.glob("classify_pages_*.csv"):
        old_checkpoint.unlink()


def prepare_benchmark_dir(path: Path, force: bool) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "runs").mkdir(parents=True, exist_ok=True)
    if not force:
        return
    patterns = [
        "ops_*.csv",
        "prefetch_*.sh",
        "post_cold_*.sh",
        "residency_*.csv",
        "residency_*.png",
        "benchmark_*.stdout",
        "benchmark_*.stderr",
        "measurement_*.sh",
    ]
    for pattern in patterns:
        for artifact in path.glob(pattern):
            artifact.unlink()
    for run_record in (path / "runs").glob("run-*.log"):
        run_record.unlink()


def validate_benchmark_args(args: argparse.Namespace) -> None:
    if not args.run_benchmarks:
        return

    ensure_path(Path(args.benchmark_harness), "benchmark harness")
    ensure_path(Path(args.benchmark_workload), "benchmark workload")
    if args.prefetch_mode != "none" and args.benchmark_cold_advice != "none":
        raise SystemExit(
            "--prefetch-mode requires --benchmark-cold-advice none; otherwise "
            "benchmark_harness would cool the DB again after prefetch."
        )

    if args.drop_caches_script:
        drop_script = Path(args.drop_caches_script)
        ensure_path(drop_script, "drop-caches script")

    if args.prefetch_mode != "none":
        if args.prefetch_tool:
            prefetch_tool = Path(args.prefetch_tool)
        elif args.prefetch_mode == "layers":
            prefetch_tool = Path("prefetch_vacuum/src/prefetch_layers")
        elif args.prefetch_mode in {"access-2d", "access-2e"}:
            prefetch_tool = Path("prefetch_access/src/prefetch_access")
        else:
            prefetch_tool = Path("prefetch_vacuum/src/prefetch")
        args.prefetch_tool = str(prefetch_tool)
        ensure_path(prefetch_tool, "prefetch tool")
        if args.prefetch_mode in {"access-2d", "access-2e"}:
            if not args.prefetch_hotpages:
                raise SystemExit(
                    f"--prefetch-mode {args.prefetch_mode} requires --prefetch-hotpages <hotpages.csv>"
                )
            ensure_path(Path(args.prefetch_hotpages), "prefetch hotpages")

    if args.run_residency_checker:
        ensure_path(Path(args.residency_checker), "residency checker")
        ensure_path(Path(args.residency_join_script), "residency join script")


def staleness_enabled(args: argparse.Namespace) -> bool:
    return bool(args.staleness_hotlist) and bool(args.staleness_workload)


def record_staleness(
    args: argparse.Namespace,
    db_path: Path,
    label: str,
    operation_count: int,
    rows: list,
) -> None:
    """Append a frozen-list coverage row for this checkpoint, if enabled.

    Quantifies how stale the static prefetch list has become: the fraction of the
    workload's read ops whose CURRENT leaf page is still in the frozen list.
    """
    if not staleness_enabled(args):
        return
    import measure_staleness

    metrics = measure_staleness.compute_coverage(
        str(db_path),
        args.staleness_hotlist,
        args.staleness_workload,
        max_read_ops=args.staleness_max_ops,
    )
    row = {"label": label, "operation_count": operation_count}
    row.update(metrics)
    rows.append(row)
    print(
        f"  staleness[{label}]: coverage={metrics['hot_key_coverage']:.4f} "
        f"dead_frozen_leaves={metrics['dead_frozen_leaves']} "
        f"leaf_pages_now={metrics['leaf_pages_now']}"
    )


def write_staleness_csv(path: Path, rows: list) -> None:
    import measure_staleness

    fields = ["label", "operation_count"] + measure_staleness.METRIC_FIELDS
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def run_experiment(args: argparse.Namespace) -> None:
    source = Path(args.source_db)
    target = Path(args.work_db)
    classifier = Path(args.classifier)
    write_workload = Path(args.workload)
    insert_workload = Path(args.insert_workload) if args.insert_workload else None
    checkpoint_dir = Path(args.checkpoint_dir)
    plot_script = Path(args.plot_script) if args.plot_checkpoints else None
    if not source.exists():
        raise SystemExit(f"source database does not exist: {source}")
    if not write_workload.exists():
        raise SystemExit(f"write workload does not exist: {write_workload}")
    if insert_workload is not None and not insert_workload.exists():
        raise SystemExit(f"insert workload does not exist: {insert_workload}")
    if plot_script is not None and not plot_script.exists():
        raise SystemExit(f"plot script does not exist: {plot_script}")
    if target.exists() and not args.force:
        raise SystemExit(f"target already exists: {target}; pass --force to overwrite it")

    ensure_classifier(classifier, args.build_classifier)
    validate_benchmark_args(args)
    prepare_checkpoint_dir(checkpoint_dir, args.force)
    if args.run_benchmarks:
        prepare_benchmark_dir(Path(args.benchmark_dir), args.force)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)

    conn = sqlite3.connect(target)
    configure_connection(conn)
    next_insert_id = max_item_id(conn) + 1
    next_delete_id = args.delete_start_id
    snapshots: list[PageSnapshot] = []
    benchmark_results: list[BenchmarkResult] = []
    staleness_rows: list = []
    inserted_total = 0
    deleted_total = 0
    operation_count = 0

    label = "baseline"
    snapshots.append(
        take_snapshot(
            target,
            conn,
            classifier,
            checkpoint_dir,
            plot_script,
            label,
            operation_count,
            inserted_total,
            deleted_total,
        )
    )
    result = run_benchmark_round(
        args,
        label,
        target,
        checkpoint_dir / f"classify_pages_{label}.csv",
        snapshots[-1].page_size,
        operation_count,
    )
    if result is not None:
        benchmark_results.append(result)
    record_staleness(args, target, label, operation_count, staleness_rows)

    print(f"write workload: {write_workload}")
    if insert_workload is not None:
        print(f"legacy insert workload: {insert_workload}")
    if args.run_benchmarks:
        print(f"benchmark workload: {Path(args.benchmark_workload)}")

    with write_workload.open("r", encoding="utf-8") as workload_file:
        insert_workload_file = (
            insert_workload.open("r", encoding="utf-8") if insert_workload is not None else None
        )
        for checkpoint_index in range(1, args.checkpoints + 1):
            replayed, inserted, deleted, next_delete_id, next_insert_id = replay_workload_chunk(
                conn,
                workload_file,
                args.ops_per_checkpoint,
                args.payload_size,
                args.delete_every,
                args.delete_batch,
                next_delete_id,
                next_insert_id,
                args.rmw_action,
            )
            insert_replayed = 0
            if insert_workload_file is not None:
                insert_replayed, extra_inserted, next_insert_id = replay_insert_workload_chunk(
                    conn,
                    insert_workload_file,
                    args.insert_ops_per_checkpoint,
                    args.payload_size,
                    next_insert_id,
                )
                inserted += extra_inserted

            if replayed == 0 and insert_replayed == 0:
                print("workload exhausted")
                break

            inserted_total += inserted
            deleted_total += deleted
            operation_count += replayed + insert_replayed

            label = f"checkpoint_{checkpoint_index:03d}"
            snapshots.append(
                take_snapshot(
                    target,
                    conn,
                    classifier,
                    checkpoint_dir,
                    plot_script,
                    label,
                    operation_count,
                    inserted_total,
                    deleted_total,
                )
            )
            result = run_benchmark_round(
                args,
                label,
                target,
                checkpoint_dir / f"classify_pages_{label}.csv",
                snapshots[-1].page_size,
                operation_count,
            )
            if result is not None:
                benchmark_results.append(result)
            record_staleness(args, target, label, operation_count, staleness_rows)
            latest = snapshot_row(snapshots[-2], snapshots[-1])
            print(
                f"{label}: pages={latest['page_count']} "
                f"interior={latest['interior_total']} "
                f"inserted={inserted_total} "
                f"deleted={deleted_total} "
                f"new={latest['new_interior_count']} "
                f"appended={latest['new_appended_count']} "
                f"in_file={latest['new_in_file_count']} "
                f"freelist={latest['freelist_total_classified']}"
            )
        if insert_workload_file is not None:
            insert_workload_file.close()

    conn.close()
    write_snapshot_csv(Path(args.summary_csv), snapshots)
    write_interior_pages_csv(Path(args.interior_pages_csv), snapshots)
    write_benchmark_csv(Path(args.benchmark_summary_csv), benchmark_results)
    if staleness_enabled(args) and args.staleness_summary_csv:
        write_staleness_csv(Path(args.staleness_summary_csv), staleness_rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Observe SQLite interior-page distribution during INSERT/DELETE churn.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--source-db", default="test.db", help="original database to copy")
    parser.add_argument(
        "--work-db",
        default=None,
        help="experiment copy to mutate (default: sqlite_page_churn_runs/<mode>/test_churn.db)",
    )
    parser.add_argument(
        "--write-workload",
        "--workload",
        dest="workload",
        default="generated_workloads/page_churn_write.txt",
        help=(
            "workload replayed between checkpoints to mutate the DB; "
            "--workload is kept as a backward-compatible alias"
        ),
    )
    parser.add_argument(
        "--insert-workload",
        default="",
        help=(
            "legacy optional insert-only workload scanned in addition to "
            "--write-workload; empty disables it"
        ),
    )
    parser.add_argument(
        "--classifier",
        default="./classify_pages",
        help="path to existing classify_pages binary",
    )
    parser.add_argument(
        "--build-classifier",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="run `make classify_pages` if --classifier does not exist",
    )
    parser.add_argument("--force", action="store_true", help="overwrite --work-db if it exists")
    parser.add_argument("--checkpoints", type=int, default=10, help="number of analysis points")
    parser.add_argument(
        "--ops-per-checkpoint",
        type=int,
        default=5000,
        help="write workload operations replayed between page analyses",
    )
    parser.add_argument(
        "--insert-ops-per-checkpoint",
        type=int,
        default=5000,
        help="legacy --insert-workload operations scanned between page analyses",
    )
    parser.add_argument(
        "--delete-every",
        type=int,
        default=0,
        help="delete one batch after this many replayed workload operations; 0 disables deletes",
    )
    parser.add_argument("--delete-batch", type=int, default=10, help="rows deleted per delete event")
    parser.add_argument(
        "--rmw-action",
        choices=("delete", "update"),
        default="delete",
        help="map readmodifywrite workload operations to DELETE or UPDATE",
    )
    parser.add_argument(
        "--delete-start-id",
        type=int,
        default=1,
        help="first existing row id considered for deletion",
    )
    parser.add_argument(
        "--payload-size",
        type=int,
        default=100,
        help="random BLOB payload bytes for inserted rows",
    )
    parser.add_argument(
        "--checkpoint-dir",
        default=None,
        help="directory for per-checkpoint classify_pages CSV files",
    )
    parser.add_argument(
        "--plot-checkpoints",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="run classify_pages_plot.py for each checkpoint CSV",
    )
    parser.add_argument(
        "--plot-script",
        default="classify_pages_plot.py",
        help="path to the existing classify_pages_plot.py script",
    )
    parser.add_argument(
        "--summary-csv",
        default=None,
        help="checkpoint-level output CSV",
    )
    parser.add_argument(
        "--interior-pages-csv",
        default=None,
        help="per-checkpoint list of interior pages",
    )
    parser.add_argument(
        "--run-benchmarks",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="run cold-start benchmark + optional prefetch for each checkpoint",
    )
    parser.add_argument(
        "--benchmark-harness",
        default="./benchmark_harness",
        help="path to benchmark_harness binary",
    )
    parser.add_argument(
        "--benchmark-workload",
        default="generated_workloads/page_churn_benchmark_high.txt",
        help="workload used by benchmark_harness to measure query latency",
    )
    parser.add_argument(
        "--benchmark-dir",
        default=None,
        help="directory for benchmark outputs, run records, wrappers, and residency CSVs",
    )
    parser.add_argument(
        "--benchmark-summary-csv",
        default=None,
        help="CSV summary of per-checkpoint benchmark latency results",
    )
    parser.add_argument(
        "--staleness-hotlist",
        default="",
        help=(
            "frozen hotpages CSV (page_number,is_resident) to score for decay; "
            "when set with --staleness-workload, per-checkpoint coverage is written "
            "to --staleness-summary-csv (additive; empty = disabled)"
        ),
    )
    parser.add_argument(
        "--staleness-workload",
        default="",
        help="read workload whose keys define the hot set for --staleness-hotlist scoring",
    )
    parser.add_argument(
        "--staleness-summary-csv",
        default=None,
        help="output CSV for per-checkpoint frozen-list coverage (staleness) metrics",
    )
    parser.add_argument(
        "--staleness-max-ops",
        type=int,
        default=20000,
        help="cap read ops sampled from --staleness-workload per checkpoint (0=all)",
    )
    parser.add_argument(
        "--drop-caches-script",
        default="/usr/local/sbin/drop-caches",
        help="helper run by benchmark_harness to drop the OS page cache; default is the system-wide setuid wrapper (P0 pipeline). Empty disables it.",
    )
    parser.add_argument(
        "--prefetch-mode",
        choices=("none", "range", "perpage", "layers", "access-2d", "access-2e"),
        default="layers",
        help="prefetch strategy to run after cold/drop-caches and before query measurement",
    )
    parser.add_argument(
        "--prefetch-tool",
        default="",
        help="prefetch binary path; defaults to prefetch or prefetch_layers based on --prefetch-mode",
    )
    parser.add_argument(
        "--prefetch-pages",
        type=int,
        default=5,
        help="number of pages for --prefetch-mode layers",
    )
    parser.add_argument(
        "--prefetch-hotpages",
        default="",
        help="hotpages CSV (page_number,is_resident) for --prefetch-mode access-2d/access-2e",
    )
    parser.add_argument(
        "--prefetch-cap-interior",
        type=int,
        default=0,
        help="interior page cap for --prefetch-mode access-2d/access-2e (0=all resident interior)",
    )
    parser.add_argument(
        "--prefetch-cap-leaf",
        type=int,
        default=0,
        help="leaf page cap for --prefetch-mode access-2e (top-K hot leaves)",
    )
    parser.add_argument(
        "--benchmark-cold-advice",
        choices=("none", "cold", "pageout", "dontneed"),
        default="none",
        help="cold-advice mode passed to benchmark_harness",
    )
    parser.add_argument(
        "--benchmark-sqlite-open-timing",
        choices=("before-cold", "after-cold"),
        default="before-cold",
        help="SQLite open timing passed to benchmark_harness",
    )
    parser.add_argument(
        "--benchmark-schema-init-timing",
        choices=("before-cold", "after-cold"),
        default="before-cold",
        help="schema init timing passed to benchmark_harness",
    )
    parser.add_argument(
        "--benchmark-debug",
        action="store_true",
        help="pass --debug to benchmark_harness",
    )
    parser.add_argument(
        "--run-residency-checker",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="after each benchmark, capture residency_checker output and join it with current classification",
    )
    parser.add_argument(
        "--residency-checker",
        default="./residency_checker",
        help="path to residency_checker binary",
    )
    parser.add_argument(
        "--residency-join-script",
        default="residency_checker_join_classify_pages.py",
        help="script that joins classify_pages and residency_checker CSVs",
    )
    parser.add_argument(
        "--plot-residency",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="write residency layout PNGs for each benchmark checkpoint",
    )
    parser.add_argument(
        "--systemd-memory-max",
        default="",
        help=(
            "run each cold-start measurement segment inside "
            "systemd-run --user --scope with MemoryMax set to this value, "
            "for example 512M"
        ),
    )
    return fill_default_output_paths(parser.parse_args())


if __name__ == "__main__":
    parsed_args = parse_args()
    run_experiment(parsed_args)

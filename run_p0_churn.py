#!/usr/bin/env python3
"""run_p0_churn.py — P0 churn-checkpoint driver (figs 07 + 12).

Measurement is strictly via the P0 pipeline (run_p0.run_baseline / run_one: full-machine
drop-caches + in-harness --verify-hotset + warmer delivery). Churn is applied by running
the harness in WRITE mode (page_churn_write slices) on a writable copy of the DB — that is
DB mutation (setup), not measurement.

Outputs (p0_runs_churn/):
  churn_evolution.csv  workload,checkpoint,strategy,first_query_us   (fig 07)
  churn_nsweep.csv     workload,N,first_query_us                     (fig 12, on final churned DB)
"""
import csv, shutil, statistics, subprocess, sys
from pathlib import Path
import run_p0 as R

OUT      = R.ROOT / "p0_runs_churn"
WORKDIR  = OUT / "work"
CHUNKS   = WORKDIR / "chunks"
CHURN_SRC = R.ROOT / "prefetch_churn/workloads/page_churn_write.txt"
WORKLOADS = ["A", "B", "C"]
LAYOUTS   = ["orig", "vacuum", "ta"]
N_CKPT    = 10
OPS_PER   = 5000
REPS      = 3
NSWEEP_N  = [1, 2, 3, 5, 8, 13, 21, 34, 46, 64, 92]   # for fig 12 (+ baseline=0)


class Args:                       # mimic run_p0 argparse for the measurement helpers
    cpu = 2; warm_cpu_ms = 10; mem_limit = "none"
ARGS = Args()


def make_chunks():
    CHUNKS.mkdir(parents=True, exist_ok=True)
    lines = [l for l in open(CHURN_SRC).read().splitlines() if l.strip()]
    out = []
    for i in range(N_CKPT):
        seg = lines[i * OPS_PER:(i + 1) * OPS_PER]
        p = CHUNKS / f"churn_chunk_{i}.txt"
        p.write_text("\n".join(seg) + "\n")
        out.append(p)
    return out


def apply_churn(workdb, chunkfile, recdir):
    """Mutate workdb by running a churn slice through the harness in write mode."""
    cmd = [str(R.BH), "--db", str(workdb), "--workload", str(chunkfile),
           "--output", str(recdir / "churn_ops.csv"), "--record-dir", str(recdir),
           "--cold-advice", "none", "--cpu", "2"]   # write mode (no --readonly/--require-read-first)
    subprocess.run(cmd, capture_output=True, text=True, timeout=900)


def med_fq(fn):
    """Run a measurement REPS times, return median first_query_us (None if all failed)."""
    vals = []
    for _ in range(REPS):
        m = fn()
        if m and m["first_query_us"] is not None:
            vals.append(m["first_query_us"])
    return statistics.median(vals) if vals else None


def main():
    WORKDIR.mkdir(parents=True, exist_ok=True)
    chunks = make_chunks()
    evo_rows, nsweep_rows = [], []   # evo: (workload,layout,checkpoint,strategy,fq); nsweep: (workload,layout,N,fq)
    for layout in LAYOUTS:
        db0 = R.resolve_pointer(R.DBS[layout])
        classify = R.load_classify(layout)
        for w in WORKLOADS:
            wl = R.WORKLOADS[w]
            workdb = WORKDIR / f"churn_{w}_{layout}.db"
            shutil.copy2(db0, workdb)
            recdir = WORKDIR / f"rec_{w}_{layout}"; recdir.mkdir(exist_ok=True)
            # static t=0 hotsets for this (workload,layout): 2e is workload-dependent; layers_92 is structural
            hot_2e = WORKDIR / f"static_2e_{w}_{layout}.csv"
            R.build_hotset(R.select_pages(R.resolve_strategy("2e_K10"), w, layout, classify), classify, hot_2e)
            hot_l92 = WORKDIR / f"static_l92_{w}_{layout}.csv"
            R.build_hotset(R.select_pages(R.resolve_strategy("layers_92"), w, layout, classify), classify, hot_l92)

            for ck in range(N_CKPT + 1):
                base = med_fq(lambda: R.run_baseline(workdb, wl, recdir, ARGS, verify_hotset=hot_2e))
                s2e  = med_fq(lambda: R.run_one(workdb, wl, hot_2e,  "fadvise", recdir, ARGS))
                sl92 = med_fq(lambda: R.run_one(workdb, wl, hot_l92, "fadvise", recdir, ARGS))
                for strat, v in [("baseline", base), ("2e_K10_static", s2e), ("layers_92_static", sl92)]:
                    if v is not None:
                        evo_rows.append((w, layout, ck, strat, f"{v:.2f}"))
                sys.stderr.write(f"[ckpt {ck}/{N_CKPT}] {w}/{layout}: base={base} 2e={s2e} l92={sl92}\n")
                if ck < N_CKPT:
                    apply_churn(workdb, chunks[ck], recdir)

            # fig 12: layers_N sweep on the FINAL churned DB (static t=0 layers hotsets)
            nbase = med_fq(lambda: R.run_baseline(workdb, wl, recdir, ARGS, verify_hotset=hot_l92))
            if nbase is not None:
                nsweep_rows.append((w, layout, 0, f"{nbase:.2f}"))
            for N in NSWEEP_N:
                hs = WORKDIR / f"churn_layers_{w}_{layout}_{N}.csv"
                R.build_hotset(R.select_pages(R.resolve_strategy(f"layers_{N}"), w, layout, classify), classify, hs)
                v = med_fq(lambda hs=hs: R.run_one(workdb, wl, hs, "fadvise", recdir, ARGS))
                if v is not None:
                    nsweep_rows.append((w, layout, N, f"{v:.2f}"))
                sys.stderr.write(f"[churn-nsweep] {w}/{layout} N={N}: {v}\n")

    OUT.mkdir(exist_ok=True)
    with open(OUT / "churn_evolution.csv", "w", newline="") as f:
        wr = csv.writer(f); wr.writerow(["workload", "layout", "checkpoint", "strategy", "first_query_us"])
        wr.writerows(evo_rows)
    with open(OUT / "churn_nsweep.csv", "w", newline="") as f:
        wr = csv.writer(f); wr.writerow(["workload", "layout", "N", "first_query_us"])
        wr.writerows(nsweep_rows)
    print(f"wrote {OUT/'churn_evolution.csv'} ({len(evo_rows)}) + {OUT/'churn_nsweep.csv'} ({len(nsweep_rows)})")


if __name__ == "__main__":
    main()

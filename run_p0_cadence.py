#!/usr/bin/env python3
"""run_p0_cadence.py — P0-disciplined multiprocess prefetch cadence (figure 08).

Cadence is intrinsically multiprocess (a background prefetcher re-warms while a foreground
probes), but the *measurement* is kept strictly P0: each probe does a full-machine
`/usr/local/sbin/drop-caches` (P0 cold-clear), waits a fixed gap during which the background
warmer may fire, then measures first-query via benchmark_harness with the P0 hardening flags
+ in-harness --verify-hotset (cold-advice none, since the drop already happened).

  cadence < gap  -> warmer fires during the gap -> probe hits a warm hotset (low first-q)
  cadence >> gap -> warmer rarely fires in the gap -> probe hits cold cache (high first-q)

Output: p0_runs_cadence/cadence_results.csv  (cadence,round,first_q_us,delivery_pct)
"""
import csv, os, signal, statistics, subprocess, sys, time
from pathlib import Path
import run_p0 as R

OUT  = R.ROOT / "p0_runs_cadence"
WORK = OUT / "work"
DB   = R.resolve_pointer(R.DBS["orig"])
WL   = R.WORKLOADS["A"]
GAP_S, ROUNDS = 3.0, 8
CADENCES = ["1.0", "5.0", "30.0", "never"]   # seconds between background re-warms


class Args:
    cpu = 2; warm_cpu_ms = 10; mem_limit = "none"
ARGS = Args()


def build_hotset():
    classify = R.load_classify("orig")
    pages = R.select_pages(R.resolve_strategy("2f_slru"), "A", "orig", classify)
    hs = WORK / "cadence_hotset.csv"
    R.build_hotset(pages, classify, hs)
    return hs


def start_bg_warmer(hotset, cadence_s):
    """Background process: re-warm the hotset every cadence_s seconds (the 'prefetcher')."""
    loop = (f'while true; do WARM_METHOD=fadvise {R.WARMER} {DB} {hotset} 4096 '
            f'>/dev/null 2>&1; sleep {cadence_s}; done')
    return subprocess.Popen(["sh", "-c", loop], preexec_fn=os.setsid)


def probe(hotset, recdir):
    """One probe: P0 full drop-caches, gap (warmer may fire), measure first-q (no re-drop)."""
    subprocess.run([R.DROP_CACHES], check=True, timeout=120)
    time.sleep(GAP_S)
    cmd = [str(R.BH), "--db", str(DB), "--workload", str(WL),
           "--output", str(recdir / "ops.csv"), "--record-dir", str(recdir),
           "--cold-advice", "none", "--verify-hotset", str(hotset)] + R._harness_hardening(ARGS)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return R.parse_metrics(r.stderr + "\n" + r.stdout)


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    hotset = build_hotset()
    recdir = WORK / "rec"; recdir.mkdir(exist_ok=True)
    rows = []
    for cad in CADENCES:
        proc = None
        if cad != "never":
            proc = start_bg_warmer(hotset, cad)
            time.sleep(0.5)
        try:
            for rd in range(ROUNDS):
                m = probe(hotset, recdir)
                fq = m["first_query_us"]; dl = m["delivery_pct"]
                if fq is not None:
                    rows.append((cad, rd, f"{fq:.2f}", "" if dl is None else f"{dl:.1f}"))
                sys.stderr.write(f"[cad={cad} round={rd}] fq={fq} delivery={dl}\n")
        finally:
            if proc:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass
    OUT.mkdir(exist_ok=True)
    with open(OUT / "cadence_results.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["cadence", "round", "first_q_us", "delivery_pct"]); w.writerows(rows)
    # quick summary
    by = {}
    for cad, _, fq, _ in rows:
        by.setdefault(cad, []).append(float(fq))
    for cad in CADENCES:
        v = by.get(cad, [])
        if v:
            sys.stderr.write(f"  cadence={cad}: median first_q={statistics.median(v):.1f} us (n={len(v)})\n")
    print(f"wrote {OUT/'cadence_results.csv'} ({len(rows)} rows)")


if __name__ == "__main__":
    main()

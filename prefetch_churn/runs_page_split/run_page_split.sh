#!/bin/bash
# PAGE-SPLIT churn: the opposite of runs_access_churn* — a churn that MOVES hot pages.
#
# Every prior churn series (runs_access_churn / _a / _b) replays page_churn_write.txt,
# which is layout-preserving: the 26,331 existing pages never move (verified 0-diff at
# every checkpoint), so the frozen t=0 hotpages list can't decay.
#
# This run builds the missing opposite case with TWO changes that together move the hot
# pages:
#   (1) write workload = UPDATEs on workload-A's own hot keys (page_split_write.txt),
#       so the writes land on the leaves the frozen list prefetches; and
#   (2) --payload-size 512, so each UPDATE grows its row 100->512 B, overflowing the
#       near-full leaf -> SQLite splits it and moves ~80% of its rows to new pages.
# Keys that used to live on a frozen hot leaf now live elsewhere -> the static list goes
# stale. The new staleness_summary.csv measures this directly (hot_key_coverage).
#
# Three arms make the cause airtight:
#   2e_k10_p512 : hot-key updates WITH growth  -> expect coverage COLLAPSE (page-moving)
#   2e_k10_p100 : hot-key updates WITHOUT growth-> control: in-place rewrite, no split,
#                 coverage should stay flat (proves it's the growth/splits, not targeting)
#   2d_p512     : interior-only list under the same growing churn (interior splits less)
set -u
DIR=/home/u03/sqlite-research-project-sharing/prefetch_churn
RUNS=$DIR/runs_page_split
HOT_BASE=/home/u03/sqlite-research-project-sharing/prefetch_access/runs/hotpages_a.csv
HOT_2E_K10=/home/u03/sqlite-research-project-sharing/prefetch_access/runs/hot2e_A_orig_K10.csv
PA=/home/u03/sqlite-research-project-sharing/prefetch_access/src/prefetch_access
WL_A=generated_workloads/workload_a_zipfian.txt
WRITE=generated_workloads/page_split_write.txt   # UPDATEs on workload-A hot keys
cd "$DIR"

run_one() {
  local label="$1"
  local hot_csv="$2"
  local cap_leaf="$3"
  local payload="$4"
  local outdir="$RUNS/${label}"
  mkdir -p "$outdir/checkpoints" "$outdir/benchmarks"

  local evict_script="$outdir/evict.sh"
  cat > "$evict_script" <<EOF
#!/bin/sh
exec /usr/local/sbin/drop-caches
EOF
  chmod +x "$evict_script"

  local mode
  if [ "$cap_leaf" = "0" ]; then mode="access-2d"; else mode="access-2e"; fi

  echo "=== SPLIT: ${label} (mode=${mode}, hot=$(basename $hot_csv), cap_leaf=$cap_leaf, payload=${payload}) ==="
  python3 sqlite_prefetch_churn_experiment.py \
    --force \
    --run-benchmarks \
    --source-db test.db \
    --work-db "$outdir/test_churn.db" \
    --classifier ./classify_pages \
    --benchmark-harness ./benchmark_harness \
    --benchmark-workload "$WL_A" \
    --write-workload "$WRITE" \
    --payload-size "$payload" \
    --drop-caches-script "$evict_script" \
    --prefetch-mode "$mode" \
    --prefetch-tool "$PA" \
    --prefetch-hotpages "$hot_csv" \
    --prefetch-cap-interior 0 \
    --prefetch-cap-leaf "$cap_leaf" \
    --benchmark-cold-advice none \
    --no-plot-checkpoints \
    --no-run-residency-checker \
    --staleness-hotlist "$hot_csv" \
    --staleness-workload "$WL_A" \
    --staleness-summary-csv "$outdir/staleness_summary.csv" \
    --checkpoint-dir "$outdir/checkpoints" \
    --benchmark-dir "$outdir/benchmarks" \
    --summary-csv "$outdir/interior_summary.csv" \
    --interior-pages-csv "$outdir/interior_pages.csv" \
    --benchmark-summary-csv "$outdir/benchmark_summary.csv" \
    > "$outdir/run.log" 2>&1
  local rc=$?
  if [ $rc -ne 0 ]; then
    echo "  FAIL ${label} (rc=$rc) -- see $outdir/run.log"
    tail -30 "$outdir/run.log"
    return $rc
  fi
  echo "  OK ${label} -> $outdir/staleness_summary.csv"
}

run_one "2e_k10_p512"  "$HOT_2E_K10"  10  512  || exit 1
run_one "2e_k10_p100"  "$HOT_2E_K10"  10  100  || exit 1
run_one "2d_p512"      "$HOT_BASE"     0  512  || exit 1

echo "ALL DONE (page-split churn, Workload A hot-key UPDATEs, static t=0 hotpages)"

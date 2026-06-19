#!/bin/bash
# Access-pattern prefetch (2d / 2e_K10) on a churned DB.
# Tests static-hotpages decay: uses the baseline hotpages_c.csv (from a t=0 warmup
# on the unchurned DB) for ALL checkpoints, while the DB layout shifts via writes.
# Comparable to runs_nsweep/n0 (no prefetch) and runs_nsweep/n92 (layers_92).
set -u
DIR=/home/u03/sqlite-research-project-sharing/prefetch_churn
RUNS=$DIR/runs_access_churn
HOT_BASE=/home/u03/sqlite-research-project-sharing/prefetch_access/runs/hotpages_c.csv
HOT_2E_K10=/home/u03/sqlite-research-project-sharing/prefetch_access/runs/hot2e_C_orig_K10.csv
PA=/home/u03/sqlite-research-project-sharing/prefetch_access/src/prefetch_access
cd "$DIR"

run_one() {
  local label="$1"   # e.g. "2d", "2e_k10"
  local hot_csv="$2"
  local cap_leaf="$3"
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

  echo "=== ${label} (mode=${mode}, hot=$(basename $hot_csv), cap_leaf=$cap_leaf) ==="
  python3 sqlite_prefetch_churn_experiment.py \
    --force \
    --run-benchmarks \
    --source-db test.db \
    --work-db "$outdir/test_churn.db" \
    --classifier ./classify_pages \
    --benchmark-harness ./benchmark_harness \
    --benchmark-workload generated_workloads/page_churn_benchmark_high.txt \
    --write-workload generated_workloads/page_churn_write.txt \
    --drop-caches-script "$evict_script" \
    --prefetch-mode "$mode" \
    --prefetch-tool "$PA" \
    --prefetch-hotpages "$hot_csv" \
    --prefetch-cap-interior 0 \
    --prefetch-cap-leaf "$cap_leaf" \
    --benchmark-cold-advice none \
    --no-plot-checkpoints \
    --no-run-residency-checker \
    --checkpoint-dir "$outdir/checkpoints" \
    --benchmark-dir "$outdir/benchmarks" \
    --summary-csv "$outdir/interior_summary.csv" \
    --interior-pages-csv "$outdir/interior_pages.csv" \
    --benchmark-summary-csv "$outdir/benchmark_summary.csv" \
    > "$outdir/run.log" 2>&1
  local rc=$?
  if [ $rc -ne 0 ]; then
    echo "  FAIL ${label} (rc=$rc) — see $outdir/run.log"
    tail -30 "$outdir/run.log"
    return $rc
  fi
  echo "  OK ${label} done → $outdir/benchmark_summary.csv"
}

run_one "2d"      "$HOT_BASE"   0   || exit 1
run_one "2e_k10"  "$HOT_2E_K10" 10  || exit 1

echo "ALL DONE"

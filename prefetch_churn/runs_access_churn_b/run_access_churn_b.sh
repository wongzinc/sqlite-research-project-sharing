#!/bin/bash
# B × access-pattern × churn: the last remaining gap from the audit.
#
# Question: workload B reads keys uniformly over [1, 99999], so there is NO
# natural hot leaf. Does access-count ordering (2d interior-only / 2e_K
# interior + top-K leaves), captured once at t=0, still help on a churned DB —
# or does the top-K leaf set degrade into a near-random selection that gives no
# benefit beyond loading interior pages?
#
# 3 arms × 10 checkpoints × 5000 churn ops:
#   - 2d_static     : access-pattern interior-only, static hotpages_b.csv
#   - 2e_k10_static : access-pattern interior + top-10 leaves, static hot2e_B_orig_K10.csv
#   - 2e_k50_static : access-pattern interior + top-50 leaves, static hot2e_B_orig_K50.csv
#   - (baseline + layers_5 + layers_92 reuse runs_nsweep_b/{n0,n5,n92} directly)
set -u
DIR=/home/u03/sqlite-research-project-sharing/prefetch_churn
RUNS=$DIR/runs_access_churn_b
HOT_BASE=/home/u03/sqlite-research-project-sharing/prefetch_access/runs/hotpages_b.csv
HOT_2E_K10=/home/u03/sqlite-research-project-sharing/prefetch_access/runs/hot2e_B_orig_K10.csv
HOT_2E_K50=/home/u03/sqlite-research-project-sharing/prefetch_access/runs/hot2e_B_orig_K50.csv
PA=/home/u03/sqlite-research-project-sharing/prefetch_access/src/prefetch_access
cd "$DIR"

run_one() {
  local label="$1"
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

  echo "=== B: ${label} (mode=${mode}, hot=$(basename $hot_csv), cap_leaf=$cap_leaf) ==="
  python3 sqlite_prefetch_churn_experiment.py \
    --force \
    --run-benchmarks \
    --source-db test.db \
    --work-db "$outdir/test_churn.db" \
    --classifier ./classify_pages \
    --benchmark-harness ./benchmark_harness \
    --benchmark-workload generated_workloads/workload_b_uniform.txt \
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
    echo "  FAIL ${label} (rc=$rc) -- see $outdir/run.log"
    tail -30 "$outdir/run.log"
    return $rc
  fi
  echo "  OK ${label} done -> $outdir/benchmark_summary.csv"
}

run_one "2d_static"      "$HOT_BASE"     0   || exit 1
run_one "2e_k10_static"  "$HOT_2E_K10"  10   || exit 1
run_one "2e_k50_static"  "$HOT_2E_K50"  50   || exit 1

echo "ALL DONE (Workload B × churn, static t=0 hotpages)"

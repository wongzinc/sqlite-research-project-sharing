#!/bin/bash
# N-sweep on churned DB × Workload A (Zipfian, keys [8, 99997])
# baseline + N∈{1,5,10,20,46,92} × 10 checkpoints
# Same posix_fadvise harness as runs_nsweep/ → cross-comparable
set -u
DIR=/home/u03/sqlite-research-project-sharing/prefetch_churn
RUNS=$DIR/runs_nsweep_a
cd "$DIR"

run_one() {
  local n="$1"
  local outdir="$RUNS/n${n}"
  mkdir -p "$outdir/checkpoints" "$outdir/benchmarks"

  local evict_script="$outdir/evict.sh"
  cat > "$evict_script" <<EOF
#!/bin/sh
exec /usr/local/sbin/drop-caches
EOF
  chmod +x "$evict_script"

  local mode pages_arg
  if [ "$n" = "0" ]; then
    mode="none"
    pages_arg=""
  else
    mode="layers"
    pages_arg="--prefetch-pages $n"
  fi

  echo "=== A: N=$n (mode=$mode) ==="
  python3 sqlite_prefetch_churn_experiment.py \
    --force \
    --run-benchmarks \
    --source-db test.db \
    --work-db "$outdir/test_churn.db" \
    --classifier ./classify_pages \
    --benchmark-harness ./benchmark_harness \
    --benchmark-workload generated_workloads/workload_a_zipfian.txt \
    --write-workload generated_workloads/page_churn_write.txt \
    --drop-caches-script "$evict_script" \
    --prefetch-mode "$mode" $pages_arg \
    --prefetch-tool ./prefetch_layers \
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
    echo "  X N=$n failed (rc=$rc) -- see $outdir/run.log"
    tail -20 "$outdir/run.log"
    return $rc
  fi
  echo "  OK N=$n done -> $outdir/benchmark_summary.csv"
}

for N in "$@"; do
  run_one "$N" || exit 1
done

echo "ALL DONE (Workload A)"

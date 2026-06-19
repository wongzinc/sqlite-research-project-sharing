#!/bin/bash
# Full N-sweep on churned DB × Workload A (Zipfian), N=0..92 (all 93 values)
# Densifies the existing sparse n0/1/5/10/20/46/92 to all integers 0..92 for
# rigorous U-shape / plateau characterisation. 11 checkpoints each (baseline + 10).
set -u
DIR=/home/u03/sqlite-research-project-sharing/prefetch_churn
RUNS=$DIR/runs_nsweep_full_a
cd "$DIR"

# Reuse the evict binary symlink from runs_nsweep_a/
EVICT=$DIR/runs_nsweep_a/evict
test -x "$EVICT" || { echo "evict binary missing: $EVICT"; exit 1; }

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
  if [ "$n" = "0" ]; then mode="none"; pages_arg=""
  else mode="layers"; pages_arg="--prefetch-pages $n"
  fi

  echo "=== A: N=$n (mode=$mode) ==="
  python3 sqlite_prefetch_churn_experiment.py \
    --force --run-benchmarks \
    --source-db test.db --work-db "$outdir/test_churn.db" \
    --classifier ./classify_pages --benchmark-harness ./benchmark_harness \
    --benchmark-workload generated_workloads/workload_a_zipfian.txt \
    --write-workload generated_workloads/page_churn_write.txt \
    --prefetch-mode "$mode" $pages_arg --prefetch-tool ./prefetch_layers \
    --benchmark-cold-advice none --no-plot-checkpoints --no-run-residency-checker \
    --checkpoint-dir "$outdir/checkpoints" --benchmark-dir "$outdir/benchmarks" \
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
}

for N in $(seq 0 92); do
  run_one "$N" || exit 1
done
echo "ALL DONE (Workload A full sweep)"

#!/bin/sh
# Full 2c Layers_N sweep × Workload A/B/C × Layout {1a, 1b, 1c} × N=0..92 × 3 reps.
# Densifies the original sparse sweep (N=0,1,5,10,20,46,92 → all 93 values 0..92) for
# rigorous U-shape / plateau characterisation.
#
# Per cell: ~0.26s wallclock; total ≈ 3 layouts × 3 workloads × 93 N × 3 reps × 0.26s ≈ 11 min.
#
# Emits one CSV per layout: nsweep_full/full_{orig,vac,ta}.csv with header
#   workload,N,rep,first_query_us,avg_us,majflt,minflt
set -u
DIR=/home/u03/sqlite-research-project-sharing/layout_rewriter/runs
BH=/home/u03/sqlite-research-project-sharing/benchmark_harness/benchmark_harness
PL=/home/u03/sqlite-research-project-sharing/prefetch_vacuum/src/prefetch_layers
OUTDIR=$DIR/nsweep_full
WL_A=/home/u03/sqlite-research-project-sharing/benchmark_harness/workloads/workloadc.txt
WL_B=/home/u03/sqlite-research-project-sharing/benchmark_harness/workloads/workload_uniform.txt
WL_C=/home/u03/sqlite-research-project-sharing/prefetch_churn/workloads/page_churn_benchmark_high.txt
mkdir -p "$OUTDIR/bench_records" "$OUTDIR/ops_csv"

# layout label -> (db, classify_csv, cold_script)
run_layout() {
  local LAYOUT="$1"; local DB="$2"; local CL="$3"; local COLD="$4"
  local OUT="$OUTDIR/full_${LAYOUT}.csv"
  echo "workload,N,rep,first_query_us,avg_us,majflt,minflt" > "$OUT"
  echo "=== layout=$LAYOUT db=$(basename $DB) ==="
  for WL_LABEL in A B C; do
    case "$WL_LABEL" in
      A) WL="$WL_A" ;;
      B) WL="$WL_B" ;;
      C) WL="$WL_C" ;;
    esac
    for N in $(seq 0 92); do
      # Build a tiny prefetch script that calls prefetch_layers with this N
      if [ "$N" = "0" ]; then
        PCS_ARG=""
      else
        PFS="$OUTDIR/pfs_${LAYOUT}_N${N}.sh"
        cat > "$PFS" <<EOF
#!/bin/sh
exec $PL $DB $CL $N 4096 >&2
EOF
        chmod +x "$PFS"
        PCS_ARG="--post-cold-script $PFS"
      fi
      for REP in 1 2 3; do
        OPS="$OUTDIR/ops_csv/ops_${LAYOUT}_${WL_LABEL}_N${N}_r${REP}.csv"
        LINE=$($BH --db "$DB" --workload "$WL" \
          --output "$OPS" --record-dir "$OUTDIR/bench_records" \
          --cold-advice dontneed --drop-caches-script "$COLD" \
          $PCS_ARG 2>&1 | grep "^ops=" || echo "MISSING")
        FQ=$(echo "$LINE"  | sed -n 's/.*first_query_latency_us=\([0-9.]*\).*/\1/p')
        AVG=$(echo "$LINE" | sed -n 's/.*avg_latency_us=\([0-9.]*\).*/\1/p')
        MAJ=$(echo "$LINE" | sed -n 's/.*total_majflt=\([0-9]*\).*/\1/p')
        MIN=$(echo "$LINE" | sed -n 's/.*total_minflt=\([0-9]*\).*/\1/p')
        echo "$WL_LABEL,$N,$REP,$FQ,$AVG,$MAJ,$MIN" >> "$OUT"
      done
    done
    echo "  done $WL_LABEL"
  done
  # cleanup wrapper scripts
  rm -f "$OUTDIR"/pfs_${LAYOUT}_N*.sh
  echo "wrote $OUT"
}

run_layout orig    "$DIR/test.db"          "$DIR/classify_before.csv" "$DIR/cold_orig.sh"
run_layout vacuum  "$DIR/test_vacuum.db"   "$DIR/classify_vacuum.csv" "$DIR/cold_vacuum.sh"
run_layout ta      "$DIR/test_typeaware.db" "$DIR/classify_after.csv" "$DIR/cold_ta.sh"

echo "ALL DONE"

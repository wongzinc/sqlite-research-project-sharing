#!/bin/sh
# 2c Layers_N sweep × Zipfian low-key hotspot workload × all 3 layouts (1a/1b/1c).
# Keys hot in [1, 1000] (alpha=0.99, top key 13% of reads).
# N values: 0 (baseline), 1, 5, 10, 20, 46, 92. 3 reps each.
# Emits CSV: workload,db,N,rep,first_query_us,avg_us,majflt,minflt
set -u
DIR=/home/u03/sqlite-research-project-sharing/layout_rewriter/runs
BH=/home/u03/sqlite-research-project-sharing/benchmark_harness/benchmark_harness
WL=/home/u03/sqlite-research-project-sharing/benchmark_harness/workloads/workload_zipf_lowkey.txt
mkdir -p "$DIR/bench_records_Nsweep_zlowkey" "$DIR/ops_csv_Nsweep_zlowkey"
echo "workload,db,N,rep,first_query_us,avg_us,majflt,minflt"

for DB_LABEL in orig vacuum ta; do
  case "$DB_LABEL" in
    orig)   DB="$DIR/test.db";          CLASSIFY="$DIR/classify_before.csv" ;;
    vacuum) DB="$DIR/test_vacuum.db";   CLASSIFY="$DIR/classify_vacuum.csv" ;;
    ta)     DB="$DIR/test_typeaware.db"; CLASSIFY="$DIR/classify_after.csv"  ;;
  esac
  COLD="$DIR/cold_${DB_LABEL}.sh"
  for N in 0 1 5 10 20 46 92; do
    if [ "$N" = "0" ]; then
      PCS=""
    else
      # Pick the correct per-layout prefetch script (already exists).
      case "$DB_LABEL" in
        orig)   PCS_SCRIPT="$DIR/prefetch_layers${N}_orig.sh" ;;
        vacuum) PCS_SCRIPT="$DIR/prefetch_layers${N}_vacuum.sh" ;;
        ta)     PCS_SCRIPT="$DIR/prefetch_layers${N}_ta.sh" ;;
      esac
      PCS="--post-cold-script $PCS_SCRIPT"
    fi
    for REP in 1 2 3; do
      OUT="$DIR/ops_csv_Nsweep_zlowkey/ops_Z_${DB_LABEL}_N${N}_r${REP}.csv"
      LINE=$($BH --db "$DB" --workload "$WL" \
        --output "$OUT" --record-dir "$DIR/bench_records_Nsweep_zlowkey" \
        --cold-advice dontneed --drop-caches-script "$COLD" \
        $PCS 2>&1 | grep "^ops=" || echo "MISSING")
      FQ=$(echo "$LINE"  | sed -n 's/.*first_query_latency_us=\([0-9.]*\).*/\1/p')
      AVG=$(echo "$LINE" | sed -n 's/.*avg_latency_us=\([0-9.]*\).*/\1/p')
      MAJ=$(echo "$LINE" | sed -n 's/.*total_majflt=\([0-9]*\).*/\1/p')
      MIN=$(echo "$LINE" | sed -n 's/.*total_minflt=\([0-9]*\).*/\1/p')
      echo "Z,$DB_LABEL,$N,$REP,$FQ,$AVG,$MAJ,$MIN"
    done
  done
done

#!/bin/sh
# 2e Access-pattern prefetch (interior + top-K hot leaves) × Workload A × 3 layouts × K∈{10,50,100,500} × 6 reps.
# Emits CSV: workload,db,strategy,rep,first_query_us,avg_us,majflt,minflt
set -u
DIR=/home/u03/sqlite-research-project-sharing/prefetch_access/runs
BH=$DIR/benchmark_harness
WL=$DIR/workload_a_zipfian.txt
mkdir -p "$DIR/bench_records_2e" "$DIR/ops_csv_2e"
echo "workload,db,strategy,rep,first_query_us,avg_us,majflt,minflt"

for DB_LABEL in orig vacuum ta; do
  case "$DB_LABEL" in
    orig)   DB="$DIR/test.db";          COLD="$DIR/cold_orig.sh" ;;
    vacuum) DB="$DIR/test_vacuum.db";   COLD="$DIR/cold_vacuum.sh" ;;
    ta)     DB="$DIR/test_typeaware.db"; COLD="$DIR/cold_ta.sh" ;;
  esac
  for STRAT in 2e_K10 2e_K50 2e_K100 2e_K500; do
    K="${STRAT##2e_K}"
    PCS="--post-cold-script $DIR/prefetch_2e_A_${DB_LABEL}_K${K}.sh"
    for REP in 1 2 3 4 5 6; do
      OUT="$DIR/ops_csv_2e/ops_A_${DB_LABEL}_${STRAT}_r${REP}.csv"
      LINE=$($BH --db "$DB" --workload "$WL" \
        --output "$OUT" --record-dir "$DIR/bench_records_2e" \
        --cold-advice dontneed --drop-caches-script "$COLD" \
        $PCS 2>&1 | grep "^ops=" || echo "MISSING")
      FQ=$(echo  "$LINE" | sed -n 's/.*first_query_latency_us=\([0-9.]*\).*/\1/p')
      AVG=$(echo "$LINE" | sed -n 's/.*avg_latency_us=\([0-9.]*\).*/\1/p')
      MAJ=$(echo "$LINE" | sed -n 's/.*total_majflt=\([0-9]*\).*/\1/p')
      MIN=$(echo "$LINE" | sed -n 's/.*total_minflt=\([0-9]*\).*/\1/p')
      echo "A,$DB_LABEL,$STRAT,$REP,$FQ,$AVG,$MAJ,$MIN"
    done
  done
done

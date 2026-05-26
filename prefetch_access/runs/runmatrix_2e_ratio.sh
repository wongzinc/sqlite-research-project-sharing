#!/bin/sh
# 2e ratio-based prefetch: interior:leaf = 7:3 (K=40) and 5:5 (K=92).
# Strategies 3a (K=40) and 3b (K=92) against A/B/C x 3 layouts x 6 reps.
#
# Prerequisites: run gen_hotleaves_ratio.sh first to generate the K=40/K=92
# hotpages CSVs.
#
# Emits CSV: workload,db,strategy,rep,first_query_us,avg_us,majflt,minflt
set -u
DIR=/home/u03/sqlite-research-project-sharing/prefetch_access/runs
BH=$DIR/benchmark_harness
WL_A=$DIR/workload_a_zipfian.txt
WL_B=$DIR/workload_b_uniform.txt
WL_C=$DIR/workload_c_highkey.txt
mkdir -p "$DIR/bench_records_2e" "$DIR/ops_csv_2e"
echo "workload,db,strategy,rep,first_query_us,avg_us,majflt,minflt"

for WL_LABEL in A B C; do
  case "$WL_LABEL" in
    A) WL=$WL_A ;;
    B) WL=$WL_B ;;
    C) WL=$WL_C ;;
  esac
  for DB_LABEL in orig vacuum ta; do
    case "$DB_LABEL" in
      orig)   DB="$DIR/test.db";           COLD="$DIR/cold_orig.sh" ;;
      vacuum) DB="$DIR/test_vacuum.db";    COLD="$DIR/cold_vacuum.sh" ;;
      ta)     DB="$DIR/test_typeaware.db"; COLD="$DIR/cold_ta.sh" ;;
    esac
    for STRAT in 2e_K40 2e_K92; do
      K="${STRAT##2e_K}"
      PCS="--post-cold-script $DIR/prefetch_2e_${WL_LABEL}_${DB_LABEL}_K${K}.sh"
      for REP in 1 2 3 4 5 6; do
        OUT="$DIR/ops_csv_2e/ops_${WL_LABEL}_${DB_LABEL}_${STRAT}_r${REP}.csv"
        LINE=$($BH --db "$DB" --workload "$WL" \
          --output "$OUT" --record-dir "$DIR/bench_records_2e" \
          --cold-advice dontneed --drop-caches-script "$COLD" \
          $PCS 2>&1 | grep "^ops=" || echo "MISSING")
        FQ=$(echo  "$LINE" | sed -n 's/.*first_query_latency_us=\([0-9.]*\).*/\1/p')
        AVG=$(echo "$LINE" | sed -n 's/.*avg_latency_us=\([0-9.]*\).*/\1/p')
        MAJ=$(echo "$LINE" | sed -n 's/.*total_majflt=\([0-9]*\).*/\1/p')
        MIN=$(echo "$LINE" | sed -n 's/.*total_minflt=\([0-9]*\).*/\1/p')
        echo "$WL_LABEL,$DB_LABEL,$STRAT,$REP,$FQ,$AVG,$MAJ,$MIN"
      done
    done
  done
done

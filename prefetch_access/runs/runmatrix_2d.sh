#!/bin/sh
# 2d Access-pattern prefetch (interior-only by resident set)
#   × Workload A/B/C × Layout 1a/1b/1c × {baseline, 2d} × 3 reps.
# Emits CSV: workload,db,strategy,rep,first_query_us,avg_us,majflt,minflt
set -u
DIR=/home/u03/sqlite-research-project-sharing/prefetch_access/runs
BH=$DIR/benchmark_harness
WL_A=$DIR/workload_a_zipfian.txt
WL_B=$DIR/workload_b_uniform.txt
WL_C=$DIR/workload_c_highkey.txt
mkdir -p "$DIR/bench_records_2d" "$DIR/ops_csv_2d"
echo "workload,db,strategy,rep,first_query_us,avg_us,majflt,minflt"

for WL_LABEL in A B C; do
  case "$WL_LABEL" in
    A) WL=$WL_A; wl_low=a ;;
    B) WL=$WL_B; wl_low=b ;;
    C) WL=$WL_C; wl_low=c ;;
  esac
  for DB_LABEL in orig vacuum ta; do
    case "$DB_LABEL" in
      orig)   DB="$DIR/test.db";          COLD="$DIR/cold_orig.sh" ;;
      vacuum) DB="$DIR/test_vacuum.db";   COLD="$DIR/cold_vacuum.sh" ;;
      ta)     DB="$DIR/test_typeaware.db"; COLD="$DIR/cold_ta.sh" ;;
    esac
    for STRAT in base 2d; do
      if [ "$STRAT" = "base" ]; then
        PCS=""
      else
        PCS="--post-cold-script $DIR/prefetch_2d_${wl_low}_${DB_LABEL}.sh"
      fi
      for REP in 1 2 3; do
        OUT="$DIR/ops_csv_2d/ops_${WL_LABEL}_${DB_LABEL}_${STRAT}_r${REP}.csv"
        LINE=$($BH --db "$DB" --workload "$WL" \
          --output "$OUT" --record-dir "$DIR/bench_records_2d" \
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

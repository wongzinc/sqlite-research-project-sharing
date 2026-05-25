#!/bin/sh
# Full RAM-pressure matrix: extends runmatrix_ram_pressure.sh from
#   { A × 1a × {base,2d,2e_K500,2f_SLRU} × {20M,none} × 6 }                       =  48 cells
# to
#   { A,B,C × 1a,1b,1c × {base,2d,2e_K10,2e_K50,2e_K100,2e_K500,2f_SLRU} × {20M,none} × 6 } = 756 cells.
#
# Closes the three gaps surfaced by overall_results.md §"還沒跑的策略 × workload 組合":
#   1. B,C workload under RAM pressure (was only A)
#   2. 1b vacuum / 1c type-aware layout under RAM pressure (was only 1a)
#   3. 2e K∈{10,50,100} under RAM pressure (was only K=500)
#
# Emits CSV: workload,db,strategy,mem_limit,rep,first_query_us,avg_us,majflt,minflt
set -u
DIR=/home/u03/sqlite-research-project-sharing/prefetch_access/runs
BH=$DIR/benchmark_harness
WL_A=$DIR/workload_a_zipfian.txt
WL_B=$DIR/workload_b_uniform.txt
WL_C=$DIR/workload_c_highkey.txt
mkdir -p "$DIR/bench_records_ram_full" "$DIR/ops_csv_ram_full"
echo "workload,db,strategy,mem_limit,rep,first_query_us,avg_us,majflt,minflt"

run_one() {
  WL_LABEL=$1; DB_LABEL=$2; STRAT=$3; LIMIT=$4; REP=$5; PCS=$6
  case "$WL_LABEL" in
    A) WL=$WL_A ;;
    B) WL=$WL_B ;;
    C) WL=$WL_C ;;
  esac
  case "$DB_LABEL" in
    orig)   DB="$DIR/test.db";          COLD="$DIR/cold_orig.sh" ;;
    vacuum) DB="$DIR/test_vacuum.db";   COLD="$DIR/cold_vacuum.sh" ;;
    ta)     DB="$DIR/test_typeaware.db"; COLD="$DIR/cold_ta.sh" ;;
  esac
  OUT="$DIR/ops_csv_ram_full/ops_${WL_LABEL}_${DB_LABEL}_${STRAT}_${LIMIT}_r${REP}.csv"
  if [ "$LIMIT" = "none" ]; then
    WRAP=""
  else
    WRAP="systemd-run --user --scope --quiet -p MemoryMax=$LIMIT --"
  fi
  LINE=$($WRAP $BH --db "$DB" --workload "$WL" \
    --output "$OUT" --record-dir "$DIR/bench_records_ram_full" \
    --cold-advice dontneed --drop-caches-script "$COLD" \
    $PCS 2>&1 | grep "^ops=" || echo "MISSING")
  FQ=$(echo  "$LINE" | sed -n 's/.*first_query_latency_us=\([0-9.]*\).*/\1/p')
  AVG=$(echo "$LINE" | sed -n 's/.*avg_latency_us=\([0-9.]*\).*/\1/p')
  MAJ=$(echo "$LINE" | sed -n 's/.*total_majflt=\([0-9]*\).*/\1/p')
  MIN=$(echo "$LINE" | sed -n 's/.*total_minflt=\([0-9]*\).*/\1/p')
  echo "$WL_LABEL,$DB_LABEL,$STRAT,$LIMIT,$REP,$FQ,$AVG,$MAJ,$MIN"
}

# Map (wl_lower, db_label) → 2d wrapper path. 2d wrappers use lowercase workload.
pcs_for() {
  WL_LABEL=$1; DB_LABEL=$2; STRAT=$3
  wl_lower=$(echo "$WL_LABEL" | tr 'A-Z' 'a-z')
  case "$STRAT" in
    base)     echo "" ;;
    2d)       echo "--post-cold-script $DIR/prefetch_2d_${wl_lower}_${DB_LABEL}.sh" ;;
    2e_K10)   echo "--post-cold-script $DIR/prefetch_2e_${WL_LABEL}_${DB_LABEL}_K10.sh" ;;
    2e_K50)   echo "--post-cold-script $DIR/prefetch_2e_${WL_LABEL}_${DB_LABEL}_K50.sh" ;;
    2e_K100)  echo "--post-cold-script $DIR/prefetch_2e_${WL_LABEL}_${DB_LABEL}_K100.sh" ;;
    2e_K500)  echo "--post-cold-script $DIR/prefetch_2e_${WL_LABEL}_${DB_LABEL}_K500.sh" ;;
    2f_SLRU)  echo "--post-cold-script $DIR/prefetch_2f_${WL_LABEL}_${DB_LABEL}.sh" ;;
  esac
}

for WL_LABEL in A B C; do
  for DB_LABEL in orig vacuum ta; do
    for LIMIT in 20M none; do
      for REP in 1 2 3 4 5 6; do
        for STRAT in base 2d 2e_K10 2e_K50 2e_K100 2e_K500 2f_SLRU; do
          PCS=$(pcs_for $WL_LABEL $DB_LABEL $STRAT)
          run_one $WL_LABEL $DB_LABEL $STRAT $LIMIT $REP "$PCS"
        done
      done
    done
  done
done

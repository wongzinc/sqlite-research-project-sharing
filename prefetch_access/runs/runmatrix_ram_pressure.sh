#!/bin/sh
# RAM-pressure comparison: baseline / 2d / 2e_K500 / 2f SLRU on Workload A × 1a layout,
# wrapped in a 20 MB systemd memory.max scope so file-backed cache fights for space.
#
# DB is ~107 MB; ceiling 20 MB ≪ working set ≪ DB. 6 reps each.
# Emits CSV: workload,db,strategy,mem_limit,rep,first_query_us,avg_us,majflt,minflt
set -u
DIR=/home/u03/sqlite-research-project-sharing/prefetch_access/runs
BH=$DIR/benchmark_harness
WL=$DIR/workload_a_zipfian.txt
DB=$DIR/test.db
COLD=$DIR/cold_orig.sh
mkdir -p "$DIR/bench_records_ram" "$DIR/ops_csv_ram"
echo "workload,db,strategy,mem_limit,rep,first_query_us,avg_us,majflt,minflt"

run_one() {
  STRAT=$1; LIMIT=$2; REP=$3; PCS=$4
  OUT="$DIR/ops_csv_ram/ops_A_orig_${STRAT}_${LIMIT}_r${REP}.csv"
  # Wrap benchmark in cgroup memory.max scope (or 'none' = no limit, host system).
  if [ "$LIMIT" = "none" ]; then
    WRAP=""
  else
    WRAP="systemd-run --user --scope --quiet -p MemoryMax=$LIMIT --"
  fi
  LINE=$($WRAP $BH --db "$DB" --workload "$WL" \
    --output "$OUT" --record-dir "$DIR/bench_records_ram" \
    --cold-advice dontneed --drop-caches-script "$COLD" \
    $PCS 2>&1 | grep "^ops=" || echo "MISSING")
  FQ=$(echo  "$LINE" | sed -n 's/.*first_query_latency_us=\([0-9.]*\).*/\1/p')
  AVG=$(echo "$LINE" | sed -n 's/.*avg_latency_us=\([0-9.]*\).*/\1/p')
  MAJ=$(echo "$LINE" | sed -n 's/.*total_majflt=\([0-9]*\).*/\1/p')
  MIN=$(echo "$LINE" | sed -n 's/.*total_minflt=\([0-9]*\).*/\1/p')
  echo "A,orig,$STRAT,$LIMIT,$REP,$FQ,$AVG,$MAJ,$MIN"
}

for LIMIT in 20M none; do
  for REP in 1 2 3 4 5 6; do
    run_one base    $LIMIT $REP ""
    run_one 2d      $LIMIT $REP "--post-cold-script $DIR/prefetch_2d_a_orig.sh"
    run_one 2e_K500 $LIMIT $REP "--post-cold-script $DIR/prefetch_2e_A_orig_K500.sh"
    run_one 2f_SLRU $LIMIT $REP "--post-cold-script $DIR/prefetch_2f_A_orig.sh"
  done
done

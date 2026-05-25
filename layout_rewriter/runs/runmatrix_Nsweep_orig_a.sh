#!/bin/sh
# A only N-sweep on Layout 1a (orig) to complete cross-layout matrix
set -u
DIR=/home/u03/sqlite-research-project-sharing/layout_rewriter/runs
BH=/home/u03/sqlite-research-project-sharing/benchmark_harness/benchmark_harness
WL_A=/home/u03/sqlite-research-project-sharing/benchmark_harness/workloads/workloadc.txt
mkdir -p "$DIR/bench_records_Nsweep_orig" "$DIR/ops_csv_Nsweep_orig"
echo "workload,N,rep,first_query_us,avg_us,majflt,minflt"

for N in 0 1 5 10 20 46 92; do
  if [ "$N" = "0" ]; then
    PCS=""
  else
    PCS="--post-cold-script $DIR/prefetch_layers${N}_orig.sh"
  fi
  for REP in 1 2 3; do
    OUT="$DIR/ops_csv_Nsweep_orig/ops_A_N${N}_r${REP}.csv"
    LINE=$($BH --db "$DIR/test.db" --workload "$WL_A" \
      --output "$OUT" --record-dir "$DIR/bench_records_Nsweep_orig" \
      --cold-advice dontneed --drop-caches-script "$DIR/cold_orig.sh" \
      $PCS 2>&1 | grep "^ops=" || echo "MISSING")
    FQ=$(echo "$LINE"  | sed -n 's/.*first_query_latency_us=\([0-9.]*\).*/\1/p')
    AVG=$(echo "$LINE" | sed -n 's/.*avg_latency_us=\([0-9.]*\).*/\1/p')
    MAJ=$(echo "$LINE" | sed -n 's/.*total_majflt=\([0-9]*\).*/\1/p')
    MIN=$(echo "$LINE" | sed -n 's/.*total_minflt=\([0-9]*\).*/\1/p')
    echo "A,$N,$REP,$FQ,$AVG,$MAJ,$MIN"
  done
done

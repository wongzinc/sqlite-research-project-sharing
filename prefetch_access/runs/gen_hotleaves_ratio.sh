#!/bin/sh
# Generate hot-leaves CSVs for K=40 (7:3 ratio) and K=92 (5:5 ratio).
# Run once on Linux before runmatrix_2e_ratio.sh.
#
# Assumes hotpages baselines exist:
#   hotpages_{a,b,c}.csv          (orig layout, from 2d/2f warmup runs)
#   hotpages_{a,b,c}_vacuum.csv   (vacuum layout)
#   hotpages_{a,b,c}_ta.csv       (type-aware layout)
set -eu
DIR=/home/u03/sqlite-research-project-sharing/prefetch_access/runs

for K in 40 92; do
  for WL_LABEL in A B C; do
    WL_LOWER=$(echo "$WL_LABEL" | tr 'A-Z' 'a-z')
    case "$WL_LABEL" in
      A) WL="$DIR/workload_a_zipfian.txt" ;;
      B) WL="$DIR/workload_b_uniform.txt" ;;
      C) WL="$DIR/workload_c_highkey.txt" ;;
    esac
    for DB_LABEL in orig vacuum ta; do
      case "$DB_LABEL" in
        orig)
          DB="$DIR/test.db"
          CL="$DIR/classify_before.csv"
          HP="$DIR/hotpages_${WL_LOWER}.csv"
          ;;
        vacuum)
          DB="$DIR/test_vacuum.db"
          CL="$DIR/classify_vacuum.csv"
          HP="$DIR/hotpages_${WL_LOWER}_vacuum.csv"
          ;;
        ta)
          DB="$DIR/test_typeaware.db"
          CL="$DIR/classify_after.csv"
          HP="$DIR/hotpages_${WL_LOWER}_ta.csv"
          ;;
      esac
      OUT="$DIR/hot2e_${WL_LABEL}_${DB_LABEL}_K${K}.csv"
      echo "==> K=${K}  WL=${WL_LABEL}  layout=${DB_LABEL}"
      python3 "$DIR/gen_hotleaves.py" "$DB" "$CL" "$HP" "$WL" "$K" "$OUT"
    done
  done
done
echo "Done. Run runmatrix_2e_ratio.sh next."

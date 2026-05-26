#!/bin/sh
exec /home/u03/sqlite-research-project-sharing/prefetch_access/runs/prefetch_access \
  /home/u03/sqlite-research-project-sharing/prefetch_access/runs/test_typeaware.db \
  /home/u03/sqlite-research-project-sharing/prefetch_access/runs/classify_after.csv \
  /home/u03/sqlite-research-project-sharing/prefetch_access/runs/hot2e_B_ta_K92.csv \
  0 92 4096 >&2

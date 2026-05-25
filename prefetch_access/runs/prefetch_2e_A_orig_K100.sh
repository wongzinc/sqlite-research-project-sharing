#!/bin/sh
exec /home/u03/sqlite-research-project-sharing/prefetch_access/runs/prefetch_access \
  /home/u03/sqlite-research-project-sharing/prefetch_access/runs/test.db \
  /home/u03/sqlite-research-project-sharing/prefetch_access/runs/classify_before.csv \
  /home/u03/sqlite-research-project-sharing/prefetch_access/runs/hot2e_A_orig_K100.csv \
  0 100 4096 >&2

#!/bin/sh
exec /home/u03/sqlite-research-project-sharing/prefetch_access/runs/prefetch_access \
  /home/u03/sqlite-research-project-sharing/prefetch_access/runs/test_vacuum.db \
  /home/u03/sqlite-research-project-sharing/prefetch_access/runs/classify_vacuum.csv \
  /home/u03/sqlite-research-project-sharing/prefetch_access/runs/hot2e_C_vacuum_K500.csv \
  0 500 4096 >&2

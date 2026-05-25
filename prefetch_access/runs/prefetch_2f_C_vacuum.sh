#!/bin/sh
exec /home/u03/sqlite-research-project-sharing/prefetch_slru/runs/prefetch_slru \
  /home/u03/sqlite-research-project-sharing/prefetch_access/runs/test_vacuum.db \
  /home/u03/sqlite-research-project-sharing/prefetch_access/runs/hotpages_c_vacuum.csv \
  4096 >&2

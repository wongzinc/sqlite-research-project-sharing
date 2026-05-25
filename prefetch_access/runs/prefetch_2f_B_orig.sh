#!/bin/sh
exec /home/u03/sqlite-research-project-sharing/prefetch_slru/runs/prefetch_slru \
  /home/u03/sqlite-research-project-sharing/prefetch_access/runs/test.db \
  /home/u03/sqlite-research-project-sharing/prefetch_access/runs/hotpages_b.csv \
  4096 >&2

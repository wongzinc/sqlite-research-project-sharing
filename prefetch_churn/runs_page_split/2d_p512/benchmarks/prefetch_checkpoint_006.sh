#!/bin/sh
set -eu
exec /home/u03/sqlite-research-project-sharing/prefetch_access/src/prefetch_access /home/u03/sqlite-research-project-sharing/prefetch_churn/runs_page_split/2d_p512/test_churn.db /home/u03/sqlite-research-project-sharing/prefetch_churn/runs_page_split/2d_p512/checkpoints/classify_pages_checkpoint_006.csv /home/u03/sqlite-research-project-sharing/prefetch_slru/runs/hotpages_a.csv 0 0 4096

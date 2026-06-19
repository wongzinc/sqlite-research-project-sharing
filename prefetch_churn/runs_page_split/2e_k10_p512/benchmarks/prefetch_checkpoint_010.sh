#!/bin/sh
set -eu
exec /home/u03/sqlite-research-project-sharing/prefetch_access/src/prefetch_access /home/u03/sqlite-research-project-sharing/prefetch_churn/runs_page_split/2e_k10_p512/test_churn.db /home/u03/sqlite-research-project-sharing/prefetch_churn/runs_page_split/2e_k10_p512/checkpoints/classify_pages_checkpoint_010.csv /home/u03/sqlite-research-project-sharing/prefetch_access/runs/hot2e_A_orig_K10.csv 0 10 4096

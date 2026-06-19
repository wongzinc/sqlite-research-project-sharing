#!/bin/sh
# Drop the OS page cache via /usr/local/sbin/drop-caches setuid wrapper.
# Replaces previous per-file posix_fadvise (evict binary) — gold-standard
# P0 cold-start mechanism per IMPLEMENTATION_PIPELINES.md.
# WARNING: this drops ALL users page cache on the workstation. Coordinate.
exec /usr/local/sbin/drop-caches

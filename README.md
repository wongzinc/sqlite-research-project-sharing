# SQLite Page Classifier

Direct-read page-type classifier for SQLite database files. No libsqlite
dependency — parses the file format from scratch per the spec.

## Files

- `classify_pages.c` — C classifier, emits CSV
- `plot_pages.py` — matplotlib visualiser + scatter-score diagnostic
- `build_testdb.py` — builds a test database matching the research schema

## Workflow

```bash
# 1. Compile the classifier
gcc -O2 -Wall -o classify_pages classify_pages.c

# 2. Build a test database (optional — use your own .db if you have one)
python3 build_testdb.py

# 3. Classify every page; CSV to stdout, stats to stderr
./classify_pages test.db > pages.csv 2> stats.txt
cat stats.txt

# 4. Visualise
python3 plot_pages.py pages.csv page_layout.png
```

## What the classifier does

1. Reads the 100-byte database header; extracts `page_size` (offset 16),
   `page_count` (offset 28), `first_freelist_trunk` (offset 32).
2. Walks the freelist trunk chain, marking every trunk + leaf freelist page.
3. Marks the reserved lock-byte page (if it falls within the file).
4. For every remaining page, reads the b-tree flag byte:
   - `0x02` → interior index
   - `0x05` → interior table
   - `0x0A` → leaf index
   - `0x0D` → leaf table
   - anything else → overflow (content continuation from a b-tree cell)
5. Emits `page_number,page_type,file_offset` one row per page.

Page 1 is handled specially: its b-tree flag byte lives at file offset 100
(after the 100-byte db header), not at offset 0.

## Scatter score

`plot_pages.py` reports a scatter score for interior pages:

- **0.0** = perfectly clustered at the start of the file
- **1.0** = uniformly distributed across the whole file

Real-world databases (and databases after VACUUM) score close to 1.0 —
that's the phenomenon this tooling is built to measure. A type-aware
layout algorithm would push this toward 0.0.

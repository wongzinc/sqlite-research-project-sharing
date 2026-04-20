#!/usr/bin/env python3
"""Build a test.db matching the research schema (table t + index idx_tag).

We insert enough rows with non-trivial payload to force the b-trees to
grow beyond a single leaf, so interior pages actually appear.
"""
import sqlite3, os, random, string

DB = 'test.db'
if os.path.exists(DB):
    os.remove(DB)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.executescript("""
    CREATE TABLE t (
        id INTEGER PRIMARY KEY,
        payload BLOB,
        tag TEXT
    );
    CREATE INDEX idx_tag ON t(tag);
""")

# 4 KB default page size -> need several KB of data per page to see tree depth
# Insert ~5000 rows, each with ~400 byte payload + short random tag
random.seed(42)
def rnd_tag():
    return ''.join(random.choices(string.ascii_lowercase, k=8))

rows = [(i, os.urandom(400), rnd_tag()) for i in range(1, 30001)]
cur.executemany("INSERT INTO t VALUES (?, ?, ?)", rows)
conn.commit()

# Create an auxiliary table, fill it, then drop it -- this reliably
# releases whole pages to the freelist so we can see them in the plot.
cur.execute("CREATE TABLE junk (x BLOB)")
cur.executemany("INSERT INTO junk VALUES (?)",
                [(os.urandom(800),) for _ in range(2000)])
conn.commit()
cur.execute("DROP TABLE junk")
conn.commit()
conn.close()

size = os.path.getsize(DB)
print(f"built {DB}: {size} bytes = {size // 4096} pages of 4 KB")

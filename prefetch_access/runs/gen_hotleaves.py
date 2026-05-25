#!/usr/bin/env python3
"""Build a hotpages-style CSV that includes:
  - All currently-resident INTERIOR pages (from baseline hotpages)
  - Top-K hottest LEAF pages by workload query frequency

Output: page_number,is_resident (only listed if is_resident=1; layered with classify
to drive prefetch_access's interior-or-leaf selection).

Usage: gen_hotleaves.py <db> <classify.csv> <baseline_hotpages.csv> <workload.txt> <top_K_leaves> <out.csv>
"""
import sys, sqlite3, csv
from collections import Counter
import bisect

if len(sys.argv) != 7:
    print(__doc__); sys.exit(1)
DB, CLASSIFY, HOT, WL, TOPK, OUT = sys.argv[1:]
TOPK = int(TOPK)

# ---- 1) Read leaf page rowid ranges via sqlite_dbpage ----
def varint(buf, off):
    v = 0
    for i in range(8):
        b = buf[off+i]
        v = (v << 7) | (b & 0x7F)
        if not (b & 0x80):
            return v, off+i+1
    return (v << 8) | buf[off+8], off+9

def first_rowid(page_bytes):
    if page_bytes[0] != 0x0D: return None
    ncells = (page_bytes[3] << 8) | page_bytes[4]
    if ncells == 0: return None
    cp0 = (page_bytes[8] << 8) | page_bytes[9]
    _, off = varint(page_bytes, cp0)
    rid, _ = varint(page_bytes, off)
    return rid

db = sqlite3.connect(DB)
db.execute("CREATE VIRTUAL TABLE temp.s USING dbstat(main)")
leaf_pages = [pn for (pn,) in db.execute(
    "SELECT pageno FROM temp.s WHERE name='items' AND pagetype='leaf' ORDER BY pageno")]

leaf_first = []   # (first_rowid, pageno) sorted by first_rowid
for pn in leaf_pages:
    data = db.execute("SELECT data FROM sqlite_dbpage WHERE pgno=?", (pn,)).fetchone()[0]
    fr = first_rowid(data)
    if fr is not None:
        leaf_first.append((fr, pn))
leaf_first.sort()
firsts = [fr for fr, _ in leaf_first]
pages  = [pn for _,  pn in leaf_first]
print(f"loaded {len(leaf_first)} leaf pages with rowid ranges", file=sys.stderr)

def page_for_key(k):
    # last leaf whose first_rowid <= k
    i = bisect.bisect_right(firsts, k) - 1
    if i < 0: return None
    return pages[i]

# ---- 2) Count key frequency in workload ----
keycnt = Counter()
with open(WL) as f:
    for line in f:
        parts = line.split()
        if len(parts) >= 2 and parts[0] == 'read':
            try: keycnt[int(parts[1])] += 1
            except ValueError: pass
print(f"workload has {len(keycnt)} unique keys, {sum(keycnt.values())} ops", file=sys.stderr)

# ---- 3) Aggregate frequency per leaf page ----
leafcnt = Counter()
for k, c in keycnt.items():
    pn = page_for_key(k)
    if pn is not None:
        leafcnt[pn] += c
top_leaves = set(pn for pn, _ in leafcnt.most_common(TOPK))
print(f"top-{TOPK} hot leaves cover {sum(leafcnt[pn] for pn in top_leaves)}/{sum(leafcnt.values())} = "
      f"{100*sum(leafcnt[pn] for pn in top_leaves)/sum(leafcnt.values()):.1f}% of ops", file=sys.stderr)

# ---- 4) Read baseline hotpages for resident interior set ----
ptype = {}
with open(CLASSIFY) as f:
    for row in csv.DictReader(f):
        ptype[int(row['page_number'])] = row['page_type']

resident_interior = set()
all_pages = set()
with open(HOT) as f:
    for row in csv.DictReader(f):
        pn = int(row['page_number'])
        all_pages.add(pn)
        if int(row['is_resident']) == 1 and ptype.get(pn,'').startswith('interior'):
            resident_interior.add(pn)
print(f"resident interior set: {len(resident_interior)} pages", file=sys.stderr)

# ---- 5) Emit hotpages-style CSV ----
with open(OUT, 'w') as f:
    f.write('page_number,is_resident\n')
    for pn in sorted(all_pages):
        is_res = 1 if (pn in resident_interior or pn in top_leaves) else 0
        f.write(f'{pn},{is_res}\n')
print(f"wrote {OUT}: interior={len(resident_interior)} top_leaves={len(top_leaves)} total_marked={len(resident_interior)+len(top_leaves)}",
      file=sys.stderr)

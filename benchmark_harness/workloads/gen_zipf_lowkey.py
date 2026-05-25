#!/usr/bin/env python3
"""Generate YCSB-style Zipfian workload over key range [1, N] (no scrambling).
Rank 1 -> key 1 (hottest). Outputs "read <key>" lines.

Usage: gen_zipf_lowkey.py <N_keys> <N_ops> <alpha> <seed> <out>
"""
import sys, math, random

N_KEYS = int(sys.argv[1])
N_OPS  = int(sys.argv[2])
ALPHA  = float(sys.argv[3])
SEED   = int(sys.argv[4])
OUT    = sys.argv[5]

random.seed(SEED)

# Precompute prefix-sum of 1/k^alpha for sampling via binary search
weights = [1.0 / ((k+1) ** ALPHA) for k in range(N_KEYS)]
prefix = []
s = 0.0
for w in weights:
    s += w
    prefix.append(s)
total = prefix[-1]

# Sample
import bisect
counts = {}
with open(OUT, "w") as f:
    for _ in range(N_OPS):
        u = random.random() * total
        rank = bisect.bisect_left(prefix, u)
        key = rank + 1  # rank 0 -> key 1, rank 1 -> key 2, ...
        f.write(f"read {key}\n")
        counts[key] = counts.get(key, 0) + 1

# Print top-20 hot keys
top = sorted(counts.items(), key=lambda x: -x[1])[:20]
print(f"Generated {N_OPS} ops over {N_KEYS} keys, alpha={ALPHA}, seed={SEED}")
print(f"Top 20 keys: {top}")
print(f"Top 1 key share: {top[0][1]/N_OPS*100:.1f}%")
print(f"Top 10 keys share: {sum(c for _,c in top[:10])/N_OPS*100:.1f}%")
print(f"Distinct keys used: {len(counts)}")

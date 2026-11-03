"""Recover a raw image's load base by correlating code pointers with string
locations, keeping only page-aligned candidate bases (real load bases are
aligned). Run from project root:  python tools/findbase2.py <file>
"""
import sys, re, collections
import numpy as np

path = sys.argv[1]
data = open(path, 'rb').read()
n = len(data)

# all 32-bit little-endian words = pointer candidates
words = np.frombuffer(data[:(n//4)*4], dtype='<u4').astype(np.int64)

# anchor strings: long printable runs, sampled across the file
offs = [m.start() for m in re.finditer(rb'[\x20-\x7e]{10,}', data)]
step = max(len(offs)//120, 1)
anchors = offs[::step][:120]

ALIGN = 0xFFF            # require base aligned to 4KB
votes = collections.Counter()
for S in anchors:
    diff = (words - S) & 0xFFFFFFFF          # candidate base for each pointer
    aligned = diff[(diff & ALIGN) == 0]       # keep only page-aligned ones
    aligned = aligned[(aligned >= 0x1000) & (aligned <= 0xFFFF0000)]
    u, c = np.unique(aligned, return_counts=True)
    for val, cnt in zip(u.tolist(), c.tolist()):
        votes[val] += 1          # count DISTINCT anchors supporting this base

print("file:", path, "size:", n, "anchors:", len(anchors), "words:", len(words))
print("top page-aligned base candidates (base -> # anchors referencing it):")
for b, c in votes.most_common(10):
    print("  0x%08x : %d" % (b, c))

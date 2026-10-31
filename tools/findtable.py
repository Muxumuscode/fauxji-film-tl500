"""Recover load base by finding a pointer table to known strings.

Debug enum-name lists are stored as arrays of const char* (absolute runtime
addresses). If the strings sit at file offsets O0,O1,... then the table holds
words W0,W1,... with Wi = Oi + B for one constant B (B = runtime_base folded
with the component's file offset). We find a run of words whose consecutive
differences match the strings' consecutive offset differences, which pins B.

Run from project root:  python -I tools/findtable.py <file> <regex-for-anchor-strings>
"""
import sys, re, struct

path, pat = sys.argv[1], sys.argv[2]
data = open(path, 'rb').read()

# 1. anchor string offsets, in file order
anchors = [(m.start(), m.group().decode('latin1'))
           for m in re.finditer(rb'[\x20-\x7e]{4,}', data) if re.search(pat.encode(), m.group())]
anchors.sort()
offs = [o for o, _ in anchors]
if len(offs) < 4:
    print("too few anchors (%d) - need a longer list" % len(offs)); sys.exit(0)
print("anchors: %d strings, offsets 0x%x..0x%x" % (len(offs), offs[0], offs[-1]))
diffs = [offs[i+1]-offs[i] for i in range(len(offs)-1)]

# 2. all 32-bit LE words and a position->value view
n = len(data)
words = struct.unpack('<%dI' % (n//4), data[:(n//4)*4])

# index word-diffs: find positions p where words[p+1]-words[p]==diffs[0], then extend
first = diffs[0]
hits = []
# build a dict from value-diff at each aligned pair is expensive; just scan
L = len(diffs)
for p in range(len(words) - L):
    if words[p+1] - words[p] != first:
        continue
    ok = all(words[p+1+k] - words[p+k] == diffs[k] for k in range(L))
    if ok:
        B = (words[p] - offs[0]) & 0xFFFFFFFF
        hits.append((p*4, B))

print("pointer-table matches: %d" % len(hits))
for tbl_off, B in hits[:8]:
    print("  table @ file 0x%x  ->  base B = 0x%08x  (runtime = file_offset + B)" % (tbl_off, B))
    # sanity: show first pointer and the string it points to
    print("     first ptr 0x%08x -> string @ file 0x%x = %r"
          % (words[tbl_off//4], offs[0], anchors[0][1]))

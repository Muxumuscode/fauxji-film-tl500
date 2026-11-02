"""python tools/liveness.py ADDR...: climb the call graph from each address up to functions that a data word points at."""
import sys, struct, bisect, collections
BASE = 0xC0003FF5
d = open('extracted/tl500_008264/EX1-DSP-SR-008264.elf', 'rb').read()
n = (len(d) - 3) // 4
words = struct.unpack_from('<%dI' % n, d, 3)
TEXT_END = 0xC0700000
callers = collections.defaultdict(list)   # target -> [site]
starts = []
for k, w in enumerate(words):
    a = BASE + 3 + 4 * k
    if a >= TEXT_END: break
    if (w >> 25) & 7 == 5 and (w >> 28) != 0xF:
        imm = w & 0xFFFFFF
        if imm & 0x800000: imm -= 1 << 24
        t = (a + 8 + (imm << 2)) & 0xFFFFFFFF
        callers[t].append((a, (w >> 24) & 1))
    if (w & 0xFFFF0000) == 0xE92D0000 and (w & 0x4000):   # push {..., lr}
        starts.append(a)
starts.sort()
dataref = collections.defaultdict(list)
for k, w in enumerate(words):
    a = BASE + 3 + 4 * k
    if 0xC0004000 <= w < TEXT_END and w & 3 == 0 and (a >= TEXT_END or True):
        # a word that equals a function start
        if bisect.bisect_left(starts, w) < len(starts) and starts[bisect.bisect_left(starts, w)] == w:
            dataref[w].append(a)
def func_of(a):
    i = bisect.bisect_right(starts, a) - 1
    return starts[i] if i >= 0 else None
for t in map(lambda s: int(s, 16), sys.argv[1:]):
    f = func_of(t)
    print('target %08x in function %08x' % (t, f))
    seen, q, hits = {f}, [f], []
    depth = {f: 0}
    while q:
        x = q.pop(0)
        if dataref.get(x): hits.append((x, depth[x], dataref[x][:3]))
        for site, link in callers.get(x, []):
            g = func_of(site)
            if g and g not in seen:
                seen.add(g); depth[g] = depth[x] + 1; q.append(g)
    print('  reached %d functions; data-referenced ancestors:' % len(seen))
    for x, dp, refs in hits[:6]: print('   %08x depth %d data@%s' % (x, dp, [hex(r) for r in refs]))

if len(sys.argv) == 1:
    # forward closure from every data-referenced function: print live functions in a range
    import os
    lo, hi = int(os.environ.get('LO', '0xC0580000'), 16), int(os.environ.get('HI', '0xC05B0000'), 16)
    fwd = collections.defaultdict(set)
    for t, sites in callers.items():
        for site, link in sites:
            f = func_of(site)
            if f: fwd[f].add(t)
    live, q = set(), list(dataref.keys())
    live.update(q)
    while q:
        x = q.pop()
        for t in fwd.get(x, ()):
            if t not in live: live.add(t); q.append(t)
    for i, s in enumerate(starts):
        if lo <= s < hi:
            ln = (starts[i + 1] - s) if i + 1 < len(starts) else 0
            print('%08x len %5d %s' % (s, ln, 'LIVE' if s in live else 'dead'))

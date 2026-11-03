"""Cross-check function matches via the call graph.

For a WB850F function name: list its WB850F callers (by name) and callees.
For a TL500 address: list its callers and callees (by TL500 address), and annotate
any TL500 address that fuzzy_match already paired with a WB850F name (pass pairs
via --pair NAME=0xADDR).

Run from project root:
  python tools/callgraph.py --wb CalcHandShakeTv256FromFL35 --tl 0xc05454f8 \
      --pair AeReadPLParam=0xc0541e9c ...
"""
import sys, os, re, struct, bisect, argparse, collections
sys.path.insert(0, os.path.dirname(__file__))
import match_funcs as M


def bl_targets(blob, base, lo=None, hi=None):
    """yield (site, target) for ARM BL (cond AL) words in blob[lo:hi]."""
    lo = 0 if lo is None else lo; hi = len(blob) if hi is None else hi
    for o in range(lo & ~3, hi - 3, 4):
        w = struct.unpack_from('<I', blob, o)[0]
        if (w >> 24) == 0xEB:
            imm = w & 0xFFFFFF
            if imm & 0x800000: imm -= 0x1000000
            site = base + o
            yield site, (site + 8 + (imm << 2)) & 0xFFFFFFFF


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--wb'); ap.add_argument('--tl')
    ap.add_argument('--pair', action='append', default=[])
    a = ap.parse_args()
    pairs = {}
    for p in a.pair:
        n, v = p.split('='); pairs[int(v, 16)] = n

    if a.wb:
        img = M.wb_main_image(); syms = M.wb_text_symbols()
        starts = sorted((s, n) for n, (s, e) in syms.items())
        sa = [s for s, _ in starts]
        def name_at(x):
            k = bisect.bisect_right(sa, x) - 1
            return starts[k][1] if k >= 0 else '?'
        name = [n for n in syms if n.startswith(a.wb)][0]
        s, e = syms[name]
        callers = collections.Counter(name_at(site) for site, t in bl_targets(img, M.WB_BASE) if t == s)
        callees = collections.Counter(name_at(t) for site, t in bl_targets(img, M.WB_BASE, s - M.WB_BASE, e - M.WB_BASE))
        print('WB850F %s @0x%08x' % (name, s))
        print('  callers:', dict(callers))
        print('  callees:', dict(callees))

    if a.tl:
        d = open(M.TL_ELF, 'rb').read(); img = d[M.TL_HDR:]
        base = M.TL_HDR + M.TL_B
        tl = int(a.tl, 16)
        words = struct.unpack('<%dI' % (len(img) // 4), img[:(len(img) // 4) * 4])
        fstarts = [base + i * 4 for i, w in enumerate(words) if (w & 0xFFFF4000) == 0xE92D4000]
        def fn_at(x):
            k = bisect.bisect_right(fstarts, x) - 1
            return fstarts[k] if k >= 0 else None
        def label(x):
            return '0x%08x%s' % (x, (' [%s]' % pairs[x]) if x in pairs else '')
        callers = collections.Counter(fn_at(site) for site, t in bl_targets(img, base) if t == tl)
        # callees: scan until next function start
        k = bisect.bisect_right(fstarts, tl)
        end = fstarts[k] if k < len(fstarts) else tl + 0x400
        callees = collections.Counter(t for site, t in bl_targets(img, base, tl - base, end - base))
        print('TL500 0x%08x' % tl)
        print('  callers:', {label(c): n for c, n in callers.items() if c})
        print('  callees:', {label(c): n for c, n in callees.items()})


if __name__ == '__main__':
    main()

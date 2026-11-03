"""Find TL500 functions that match named WB850F functions by instruction shape.

Both images come from the same Samsung SPID/VxWorks codebase, so a function compiled
from the same source keeps nearly the same mnemonic sequence even when addresses,
literal pools and register allocation shift. We fingerprint each WB850F target as
overlapping mnemonic n-grams and vote for the TL500 alignment that shares the most.

Run from project root:  python tools/fuzzy_match.py <name-regex> [...]
The TL500 mnemonic stream is cached in tools/.cache/ after the first run.
"""
import sys, os, re, pickle, collections
import capstone as cs
sys.path.insert(0, os.path.dirname(__file__))
import match_funcs as M

N = 6
CACHE = os.path.join(os.path.dirname(__file__), '.cache', 'tl500_mnemonics.pkl')


def norm(ins):
    # mnemonic only; condition codes kept (they're part of the logic shape)
    return ins.mnemonic


def tl_stream():
    if os.path.exists(CACHE):
        return pickle.load(open(CACHE, 'rb'))
    d = open(M.TL_ELF, 'rb').read()
    img = d[M.TL_HDR:]
    md = cs.Cs(cs.CS_ARCH_ARM, cs.CS_MODE_ARM | cs.CS_MODE_LITTLE_ENDIAN)
    addrs, mns = [], []
    pos = 4
    while pos < len(img) - 4:
        chunk = img[pos:pos + 0x10000]; got = 0
        for ins in md.disasm(chunk, (M.TL_HDR + pos + M.TL_B) & 0xFFFFFFFF):
            got += 1; addrs.append(ins.address); mns.append(norm(ins))
        pos += (0x10000 if got * 4 >= 0xfffc else got * 4 + 4)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    pickle.dump((addrs, mns), open(CACHE, 'wb'))
    return addrs, mns


def main():
    pats = [re.compile(p) for p in sys.argv[1:]]
    img = M.wb_main_image(); syms = M.wb_text_symbols()
    addrs, mns = tl_stream()
    index = collections.defaultdict(list)
    for i in range(len(mns) - N):
        index[tuple(mns[i:i + N])].append(i)
    md = cs.Cs(cs.CS_ARCH_ARM, cs.CS_MODE_ARM | cs.CS_MODE_LITTLE_ENDIAN)
    for name, (s, e) in sorted(syms.items(), key=lambda x: x[1][0]):
        if not any(p.search(name) for p in pats):
            continue
        o = s - M.WB_BASE
        seq = [norm(i) for i in md.disasm(img[o:o + (e - s)], s)]
        if len(seq) < N + 2:
            print('%-46s too short (%d instrs)' % (name[:46], len(seq))); continue
        votes = collections.Counter()
        for j in range(len(seq) - N):
            hits = index.get(tuple(seq[j:j + N]), ())
            if len(hits) > 50:          # too common to be informative
                continue
            for h in hits:
                votes[h - j] += 1
        total = len(seq) - N
        best = votes.most_common(3)
        line = ', '.join('0x%08x (%d%%)' % (addrs[k], 100 * v // total) for k, v in best if k >= 0)
        print('%-46s %4d instrs -> %s' % (name[:46], len(seq), line or 'no match'))


if __name__ == '__main__':
    main()

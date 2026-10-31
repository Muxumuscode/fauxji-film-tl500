"""Recover the load/base address of a raw firmware image.

ARM code loads string addresses from literal pools: a nearby 32-bit word holds
the string's ABSOLUTE runtime address. If we take a known string's FILE offset S
and a pointer word W that refers to it, then  base = W - S  (folding any file
header into the constant). The true base is the value of (W - S) that recurs for
many different strings. We histogram it.

Run from project root:  python -I tools/findbase.py <file>
"""
import sys, re, struct, collections

def main():
    path = sys.argv[1]
    data = open(path, 'rb').read()
    n = len(data)

    # 1. collect file offsets of reasonably long ASCII strings (good anchors)
    str_offsets = []
    for m in re.finditer(rb'[\x20-\x7e]{8,}', data):
        str_offsets.append(m.start())
    str_set = set(str_offsets)

    # 2. collect all 4-byte little-endian words that look like pointers
    #    (i.e. could plausibly be a runtime address, not tiny, not huge)
    #    We only need the SET of distinct pointer values.
    words = struct.unpack('<%dI' % (n // 4), data[:(n // 4) * 4])
    # keep pointer-ish values; firmware RAM bases are usually high-ish
    ptrs = [w for w in words if 0x1000 <= w <= 0xFFFFFFFF]
    ptr_set = set(ptrs)

    # 3. for each candidate base guess, how many string offsets S have (S+base) in ptr_set?
    #    Instead of scanning all bases, derive base from pairs: base = W - S.
    #    Only bother when W-S lands in a sane range.
    votes = collections.Counter()
    # limit anchors for speed
    anchors = str_offsets[:6000]
    for S in anchors:
        for cand_base in (0x00000000, 0x00008000, 0x00010000, 0x20000000,
                          0x40000000, 0x80000000, 0xC0000000, 0xD0000000,
                          0x01000000, 0x02000000, 0x04000000, 0x08000000):
            if (S + cand_base) & 0xFFFFFFFF in ptr_set:
                votes[cand_base] += 1

    print("file:", path, "size:", n, "strings:", len(str_offsets),
          "distinct ptrs:", len(ptr_set))
    print("base guess votes (base -> #strings referenced):")
    for b, c in votes.most_common(12):
        print("  0x%08x : %d" % (b, c))

if __name__ == '__main__':
    main()

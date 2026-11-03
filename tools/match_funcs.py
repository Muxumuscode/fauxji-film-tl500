"""Match named WB850F functions into the unnamed TL500 firmware via shared strings.

WB850F: Main_Image from the DRIMe III container, base 0xC0004000, names from
partialImage.o.map. TL500: EX1-DSP-SR-008264.elf, 7-byte header, runtime =
file_offset + 0xC0003FF5.

For each target name: find its WB850F code range, collect the strings its literal
pools point at, then find TL500 literal-pool words pointing at the same strings and
report which TL500 functions (nearest preceding 'push {...lr}') reference them.

Run from project root:  python tools/match_funcs.py <name-regex> [<name-regex> ...]
"""
import sys, re, struct, bisect, collections

WB_BIN = 'extracted/wb850f/WB850-FW-SR-210086.bin'
WB_MAP = 'extracted/wb850f/partialImage.o.map'
TL_ELF = 'extracted/tl500_008264/EX1-DSP-SR-008264.elf'
WB_BASE = 0xC0004000
TL_B = 0xC0003FF5
TL_HDR = 7


def wb_main_image():
    d = open(WB_BIN, 'rb').read()
    _, count = struct.unpack_from('<7sB', d, 0)
    for k in range(count):
        path, size, off, name = struct.unpack_from('<32sII20s', d, 8 + k * 60)
        if name.split(b'\0')[0] == b'Main_Image':
            return d[off:off + size]
    raise SystemExit('Main_Image not found')


def wb_text_symbols():
    """name -> (start, end) runtime addresses for .text functions, from the map."""
    txt = open(WB_MAP, 'r', errors='replace').read()
    a = txt.find('\n.text'); b = txt.find('\n.debug_frame')
    body = txt[a:b if b > 0 else len(txt)]
    out = {}
    for name, addr, size in re.findall(r'^\s*([A-Za-z_][\w$:~]*)\s+([0-9a-fA-F]{8})\s+([0-9a-fA-F]+)\s*$', body, re.M):
        if name.startswith('L$_') or '$' in name:
            continue
        start = int(addr, 16) + WB_BASE
        out.setdefault(name, (start, start + max(int(size, 16), 4)))
    return out


def cstring(blob, off):
    if not (0 <= off < len(blob)):
        return None
    e = blob.find(b'\0', off, off + 200)
    if e <= off:
        return None
    s = blob[off:e]
    if len(s) >= 6 and all(32 <= c < 127 or c in (9, 10) for c in s):
        return s
    return None


def strings_used_by(img, start, end):
    """Strings referenced through literal-pool words inside [start, end)."""
    used = set()
    lo = start - WB_BASE; hi = min(end - WB_BASE + 0x400, len(img))  # pools may trail the body
    for o in range(lo & ~3, hi - 3, 4):
        w = struct.unpack_from('<I', img, o)[0]
        if WB_BASE <= w < WB_BASE + len(img):
            s = cstring(img, w - WB_BASE)
            if s:
                used.add(s)
    return used


def tl_index():
    d = open(TL_ELF, 'rb').read()
    img = d[TL_HDR:]
    words = struct.unpack('<%dI' % (len(img) // 4), img[:(len(img) // 4) * 4])
    by_val = collections.defaultdict(list)
    for i, w in enumerate(words):
        if 0xC0004000 <= w < 0xC0C00000:
            by_val[w].append(TL_HDR + i * 4 + TL_B)  # runtime address of the pool word
    # function starts: 'push {..., lr}' = stmdb sp!, {...lr}: 0xE92D4xxx
    starts = [TL_HDR + i * 4 + TL_B for i, w in enumerate(words) if (w & 0xFFFF4000) == 0xE92D4000]
    return d, by_val, starts


def main():
    pats = [re.compile(p) for p in sys.argv[1:]] or [re.compile(r'^AeCalcProgramLine')]
    img = wb_main_image()
    syms = wb_text_symbols()
    tl, by_val, starts = tl_index()
    for name, (s, e) in sorted(syms.items(), key=lambda x: x[1][0]):
        if not any(p.search(name) for p in pats):
            continue
        used = strings_used_by(img, s, e)
        votes = collections.Counter(); evidence = collections.defaultdict(list)
        for st in used:
            for m in re.finditer(re.escape(st) + b'\0', tl):
                rt = (m.start() + TL_B) & 0xFFFFFFFF
                for pool in by_val.get(rt, []):
                    k = bisect.bisect_right(starts, pool) - 1
                    if k >= 0:
                        fn = starts[k]
                        votes[fn] += 1; evidence[fn].append(st.decode()[:50])
        print('\n%s  WB 0x%08x  (%d strings used)' % (name, s, len(used)))
        if not votes:
            print('   no TL500 match via strings')
        for fn, v in votes.most_common(3):
            print('   TL500 fn ~0x%08x  shared=%d  e.g. %s' % (fn, v, '; '.join(sorted(set(evidence[fn]))[:3])))


if __name__ == '__main__':
    main()

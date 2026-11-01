"""Read and rewrite the menu text tables in the TL500 resource ROM (SPID.Rom).

SPID.Rom holds ~40 language tables placed back to back. Each table is
`uint32 ?, uint32 total_size, uint32 count` followed by `count` entries of
`uint32 n` + n bytes of UTF-16LE text (NUL-terminated, padded with 0xAB to a
multiple of 4). Strings are addressed by their index in the table, and the
following table starts right after the last entry, so an edit must keep the
table's total byte size unchanged: growth in one entry is paid for by shrinking
others, and any spare bytes are absorbed as extra padding in the last edited entry.

Run from project root:
  python tools/spid_strings.py list <SPID.Rom> [table_start_hex] [regex]
"""
import re, struct, sys

ENGLISH = 0x683110   # first entry of the English table (header is the 12 bytes before)


def entry_bytes(text, size=None):
    raw = text.encode('utf-16-le') + b'\0\0'
    need = (len(raw) + 3) & ~3
    size = need if size is None else size
    if size < need:
        raise ValueError('%r needs %d bytes, slot has %d' % (text, need, size))
    return struct.pack('<I', size) + raw + b'\xab' * (size - len(raw))


def read_table(d, start=ENGLISH):
    count = struct.unpack_from('<I', d, start - 4)[0]
    out, o = [], start
    for _ in range(count):
        n = struct.unpack_from('<I', d, o)[0]
        out.append((o, n, d[o + 4:o + 4 + n].decode('utf-16-le').split('\0')[0]))
        o += 4 + n
    return out, o


def rewrite(d, changes, start=ENGLISH):
    """changes: {index: new_text}. Returns new bytes with the table size preserved."""
    ents, end = read_table(d, start)
    texts = [t for _, _, t in ents]
    sizes = [n for _, n, _ in ents]
    for i, t in changes.items():
        texts[i] = t
        sizes[i] = len(entry_bytes(t)) - 4
    spare = (end - start) - sum(4 + n for n in sizes)
    if spare < 0:
        raise ValueError('edits grow the table by %d bytes; shorten some text' % -spare)
    sizes[max(changes)] += spare          # absorb leftover bytes as padding
    body = b''.join(entry_bytes(t, n) for t, n in zip(texts, sizes))
    assert len(body) == end - start
    out = bytearray(d)
    out[start:end] = body
    check, end2 = read_table(bytes(out), start)
    assert end2 == end and [t for _, _, t in check] == texts
    return bytes(out), spare


if __name__ == '__main__':
    if sys.argv[1] == 'list':
        d = open(sys.argv[2], 'rb').read()
        start = int(sys.argv[3], 16) if len(sys.argv) > 3 else ENGLISH
        pat = re.compile(sys.argv[4]) if len(sys.argv) > 4 else None
        ents, end = read_table(d, start)
        for i, (o, n, t) in enumerate(ents):
            if not pat or pat.search(t):
                print('%4d 0x%08x %3d %r' % (i, o, n, t))

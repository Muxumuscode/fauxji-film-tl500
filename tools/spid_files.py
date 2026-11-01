"""List and replace files in the TL500 resource ROM (SPID.Rom) file system.

SPID.Rom begins with a directory of `/int/rom` files. Each record is a 128-byte
NUL-padded name followed by `u32 offset, u32 size` (stride 144). A replacement must
fit the file's slot (up to the next file's offset); the data is written in place,
the rest of the slot is zero-filled, and the size field is updated.

Run from project root:
  python tools/spid_files.py list <SPID.Rom> [regex]
  python tools/spid_files.py extract <SPID.Rom> <name> <out>
"""
import re, struct, sys

DIR_END = 0x40000


def directory(d):
    """name -> (record_offset, data_offset, size, slot)"""
    recs = []
    for m in re.finditer(rb'[A-Za-z0-9_]+\.[A-Za-z0-9]{2,4}\0', d[:DIR_END]):
        name = m.group()[:-1].decode()
        off, size = struct.unpack_from('<II', d, m.start() + 128)
        if 0 < off < len(d) and size <= len(d):
            recs.append((name, m.start(), off, size))
    offs = sorted(set(r[2] for r in recs)) + [len(d)]
    out = {}
    for name, rec, off, size in recs:
        nxt = offs[offs.index(off) + 1]
        out[name] = (rec, off, size, nxt - off)
    return out


def replace(d, name, data):
    rec, off, size, slot = directory(d)[name]
    if len(data) > slot:
        raise ValueError('%s: %d bytes, slot is %d' % (name, len(data), slot))
    out = bytearray(d)
    out[off:off + slot] = data + b'\0' * (slot - len(data))
    struct.pack_into('<I', out, rec + 132, len(data))
    assert directory(bytes(out))[name][1:3] == (off, len(data))
    return bytes(out)


if __name__ == '__main__':
    cmd, rom = sys.argv[1], sys.argv[2]
    d = open(rom, 'rb').read()
    files = directory(d)
    if cmd == 'list':
        pat = re.compile(sys.argv[3]) if len(sys.argv) > 3 else None
        for n, (rec, off, size, slot) in sorted(files.items(), key=lambda x: x[1][1]):
            if not pat or pat.search(n):
                print('%-32s off 0x%08x size %8d slot %8d' % (n, off, size, slot))
    elif cmd == 'extract':
        rec, off, size, slot = files[sys.argv[3]]
        open(sys.argv[4], 'wb').write(d[off:off + size])

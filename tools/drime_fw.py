"""drime_fw.py - unpack / repack Samsung DRIMe III camera firmware archives
(EX1 / TL500 / EX2F / WB850F family).

Format (confirmed against EX1 110271, matches community drime3-firmware.py):
  header:  <7s B>              7-byte version string, 1-byte component count
  entry:   <32s I I 20s>       path(32), size(u32), offset(u32), name(20)
           repeated <count> times, starting at byte 8
  then raw component data located by each entry's (offset, size).
  Region before the first component (header + table + padding) is preserved
  verbatim so a repack can be byte-for-byte identical to the original.

NO checksum or signature exists in this format (verified separately).

Usage (run from project root; pass the firmware path as an argument):
  python -I tools/drime_fw.py info   <firmware.bin>
  python -I tools/drime_fw.py unpack <firmware.bin> <out_dir>
  python -I tools/drime_fw.py pack   <in_dir> <new_firmware.bin>

'unpack' writes each component as <name>.bin, the verbatim pre-data region as
_container_header.bin, and a manifest.json describing the layout.
'pack' rebuilds the archive from that directory, placing each component at the
offset recorded in the manifest (so a same-size edit reproduces a valid file).
"""
import sys, os, json, struct

HDR = struct.Struct('<7sB')
ENT = struct.Struct('<32sII20s')

def _clean(b):
    return b.split(b'\x00')[0].decode('latin1')

def parse(data):
    ver, count = HDR.unpack_from(data, 0)
    entries = []
    pos = 8
    for _ in range(count):
        path, size, offset, name = ENT.unpack_from(data, pos)
        pos += ENT.size
        entries.append(dict(path=_clean(path), name=_clean(name),
                            size=size, offset=offset,
                            path_raw=path.hex(), name_raw=name.hex()))
    return ver, count, entries, pos

def cmd_info(fw):
    data = open(fw, 'rb').read()
    ver, count, entries, table_end = parse(data)
    print("file: %s  (%d bytes)" % (fw, len(data)))
    print("version field: %r   components: %d" % (ver, count))
    first = min(e['offset'] for e in entries)
    print("table ends at 0x%x, first component at 0x%x (0x%x padding between)"
          % (table_end, first, first - table_end))
    for e in entries:
        end = e['offset'] + e['size']
        print("  %-12s %-18s size=%10d  0x%08x..0x%08x"
              % (e['name'], e['path'], e['size'], e['offset'], end))
    last_end = max(e['offset'] + e['size'] for e in entries)
    print("last component ends at 0x%x ; file size 0x%x ; trailing %d bytes"
          % (last_end, len(data), len(data) - last_end))

def cmd_unpack(fw, out):
    data = open(fw, 'rb').read()
    ver, count, entries, _ = parse(data)
    os.makedirs(out, exist_ok=True)
    first = min(e['offset'] for e in entries)
    open(os.path.join(out, '_container_header.bin'), 'wb').write(data[:first])
    for e in entries:
        comp = data[e['offset']:e['offset'] + e['size']]
        fn = e['name'] + '.bin'
        open(os.path.join(out, fn), 'wb').write(comp)
        e['file'] = fn
    manifest = dict(version=ver.hex(), count=count,
                    total_size=len(data), header_file='_container_header.bin',
                    entries=entries)
    json.dump(manifest, open(os.path.join(out, 'manifest.json'), 'w'), indent=2)
    print("unpacked %d components + header into %s" % (count, out))

def cmd_pack(indir, outfw):
    m = json.load(open(os.path.join(indir, 'manifest.json')))
    buf = bytearray(m['total_size'])
    header = open(os.path.join(indir, m['header_file']), 'rb').read()
    buf[:len(header)] = header
    for e in m['entries']:
        comp = open(os.path.join(indir, e['file']), 'rb').read()
        if len(comp) != e['size']:
            print("  note: %s is now %d bytes (was %d) - offsets NOT recomputed; "
                  "same-size edits only in this mode" % (e['file'], len(comp), e['size']))
        buf[e['offset']:e['offset'] + len(comp)] = comp
    open(outfw, 'wb').write(buf)
    print("packed %d components -> %s (%d bytes)" % (len(m['entries']), outfw, len(buf)))

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    cmd = sys.argv[1]
    if cmd == 'info':   cmd_info(sys.argv[2])
    elif cmd == 'unpack': cmd_unpack(sys.argv[2], sys.argv[3])
    elif cmd == 'pack':   cmd_pack(sys.argv[2], sys.argv[3])
    else: print("unknown command", cmd); sys.exit(1)

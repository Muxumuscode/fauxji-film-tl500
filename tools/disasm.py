"""Disassemble a raw ARM binary and dump instructions + string xrefs.
Usage: python tools/disasm.py <file> [--thumb] [--base 0x0] [--len N] [--offset N]
Run from the project root; never from inside extracted/ or firmware-original/.
"""
import sys, re, argparse
import capstone as cs

def strings_with_offsets(data, minlen=5):
    out = []
    for m in re.finditer(rb'[\x20-\x7e]{%d,}' % minlen, data):
        out.append((m.start(), m.group().decode()))
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('file')
    ap.add_argument('--thumb', action='store_true')
    ap.add_argument('--base', type=lambda x: int(x, 0), default=0)
    ap.add_argument('--offset', type=lambda x: int(x, 0), default=0)
    ap.add_argument('--len', type=lambda x: int(x, 0), default=None)
    ap.add_argument('--grep', default=None, help='only print instructions whose mnemonic+ops match this regex')
    args = ap.parse_args()

    data = open(args.file, 'rb').read()
    if args.len:
        data = data[args.offset:args.offset+args.len]
    else:
        data = data[args.offset:]

    mode = cs.CS_MODE_THUMB if args.thumb else cs.CS_MODE_ARM
    md = cs.Cs(cs.CS_ARCH_ARM, mode | cs.CS_MODE_LITTLE_ENDIAN)
    md.detail = False

    pat = re.compile(args.grep, re.I) if args.grep else None
    count = 0
    for insn in md.disasm(data, args.base):
        line = f"0x{insn.address:08x}:\t{insn.mnemonic}\t{insn.op_str}"
        if pat is None or pat.search(line):
            print(line)
            count += 1
        if count > 4000:
            print('... (truncated at 4000 matching lines)')
            break

if __name__ == '__main__':
    main()

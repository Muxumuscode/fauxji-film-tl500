"""Disassemble TL500 .elf at a runtime address: python tools/dis.py ADDR [count] [stockdir]"""
import sys, capstone as cs
BASE = 0xC0003FF5
def load(p='extracted/tl500_008264/EX1-DSP-SR-008264.elf'):
    return open(p, 'rb').read()
def dis(d, addr, n=40):
    off = addr - BASE
    md = cs.Cs(cs.CS_ARCH_ARM, cs.CS_MODE_ARM)
    for i in md.disasm(d[off:off + 4 * n], addr):
        print('%08x: %s %s' % (i.address, i.mnemonic, i.op_str))
if __name__ == '__main__':
    dis(load(), int(sys.argv[1], 16), int(sys.argv[2]) if len(sys.argv) > 2 else 40)

def scan(d, lo, hi, pat):
    """yield (addr, text) of instructions in [lo,hi) matching regex pat; steps word by word."""
    import re
    md = cs.Cs(cs.CS_ARCH_ARM, cs.CS_MODE_ARM)
    r = re.compile(pat)
    for a in range(lo, hi, 4):
        o = a - BASE
        for i in md.disasm(d[o:o + 4], a):
            t = '%s %s' % (i.mnemonic, i.op_str)
            if r.search(t):
                yield a, t

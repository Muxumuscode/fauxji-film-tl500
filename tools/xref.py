"""python tools/xref.py ADDR  -> all BL/B sites calling ADDR"""
import sys, struct
BASE = 0xC0003FF5
d = open('extracted/tl500_008264/EX1-DSP-SR-008264.elf','rb').read()
t = int(sys.argv[1],16)
for o in range(3, len(d)-3, 4):
    w = struct.unpack_from('<I', d, o)[0]
    if (w>>25)&7 == 5:  # B/BL any cond
        imm = w & 0xFFFFFF
        if imm & 0x800000: imm -= 1<<24
        a = BASE + o
        if (a+8+(imm<<2)) & 0xFFFFFFFF == t:
            print('%08x %s cond=%x' % (a, 'BL' if w&(1<<24) else 'B', w>>28))

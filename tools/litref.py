"""python tools/litref.py LIT_ADDR... -> ldr [pc,#x] sites that load that literal-pool address"""
import sys, struct
sys.path.insert(0, 'tools')
BASE = 0xC0003FF5
d = open('extracted/tl500_008264/EX1-DSP-SR-008264.elf', 'rb').read()
want = set(int(a, 16) for a in sys.argv[1:])
for o in range(3, len(d) - 3, 4):
    w = struct.unpack_from('<I', d, o)[0]
    if (w & 0x0F7F0000) == 0x051F0000 or (w & 0x0F7F0000) == 0x059F0000:
        a = BASE + o
        off = w & 0xFFF
        t = a + 8 + (off if w & (1 << 23) else -off)
        if t in want: print('%08x ldr r%d,=%08x' % (a, (w >> 12) & 15, t))

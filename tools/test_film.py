"""Runs the real emitted words of film_mode.py (stage 1) in test_sky's ARM interpreter, and checks the pointer patches on a built .elf.
From the project root:  python tools/test_film.py     (prints "bad 0" when every case is right)"""
import os, struct, sys
sys.path.insert(0, 'tools')
import fauxji_ui as ui
import diag_probe as P
import film_mode as F
from test_sky import CPU

B = ui.B
BASE, DATA, LAB = F.blob()
A = F.addrs(BASE)
ENTRY = A['code']
MGR, OBJ, DCFM, LIST = 0xC1000000, 0xC1100000, 0xC1200000, 0xC1300000
SLOT0 = ui.STR_BASE
bad = 0


def fail(*a):
    global bad
    bad += 1
    print('BAD', *a)


def cstr(c, addr, n=40):
    out = b''
    for i in range(n):
        v = c.mem.get(addr + i, 0)
        if v == 0:
            break
        out += bytes([v])
    return out.decode('latin1')


def utf16(c, addr):
    out = ''
    for i in range(20):
        h = c.get16(addr + 2 * i)
        if h == 0:
            break
        out += chr(h)
    return out


class Rig:
    def __init__(self, mgr_word=5, obj_chain=True, cached=None):
        self.c = CPU([(BASE, DATA)])
        c = self.c
        self.mode, self.count, self.opens, self.calls = 2, 0, [], []
        c.set32(P.MANAGER_GLOBAL, MGR)
        c.set32(MGR + 4 * mgr_word, OBJ)
        if obj_chain:
            c.set32(OBJ, P.VPTR); c.set32(OBJ + 0x118, DCFM); c.set32(DCFM + 0x10, LIST); c.set32(LIST + 0x20, 0x64)
        if cached is not None:
            c.set32(A['vars'], cached)
        self.reads = []
        orig = c.get32
        c.get32 = lambda a: (self.reads.append(a), orig(a))[1]
        c.stubs[F.GET_SYSVAL] = lambda s: (self.asked.append(s.r[0]), s.r.__setitem__(0, self.mode))
        c.stubs[F.OPEN] = lambda s: (self.opens.append((s.r[0], s.r[1])), self.calls.append('open'), s.r.__setitem__(0, self.count))
        c.stubs[ui.ARM_NAME] = lambda s: self.calls.append(('arm', s.r[0]))
        c.stubs[ui.TOAST_CODE] = lambda s: self.calls.append(('toast', s.r[0]))
        c.stubs[ui.KEYHOOK] = lambda s: self.calls.append(('keyhook', s.r[0], s.r[1]))
        c.stubs[ui.KEY_CALL[1]] = lambda s: self.calls.append(('keycall', s.r[0], s.r[1]))
        self.asked = []
        self.saved = [0x2000 + i for i in range(16)]

    def key(self, key=10, state=1):
        c = self.c
        self.calls.clear(); self.asked.clear()
        for i in range(2, 13):
            c.r[i] = self.saved[i]
        c.r[0], c.r[1] = key, state
        c.run(ENTRY, lr=0xCAFE0000, ret=0xCAFE0000)
        if not (all(c.r[i] == self.saved[i] for i in range(4, 11)) and c.r[13] == 0x10000000):
            fail('registers / stack changed', self.calls)
        return list(self.calls)

    def names(self):
        c = self.c
        return cstr(c, A['buf'], 8), cstr(c, A['buf'] + 8, 8), cstr(c, A['buf'] + 16, 24)

    def stray(self):
        stack = lambda a: 0x0FFFF000 <= a < 0x10000000
        return [hex(a) for a in self.reads if not (P.RAM_LO <= a < P.RAM_HI) and not stack(a)]


STOCK_NAMES = ('DCIM', '%s/DCIM', '%s/DCIM/100PHOTO')
FILM_NAMES = ('FILM', '%s/FILM', '%s/FILM/100PHOTO')
PLAIN = lambda k=10, s=1: [('keyhook', k, s)]

# 1. buffers start as the stock strings, nothing happens while the mode does not change
r = Rig()
if r.names() != STOCK_NAMES:
    fail('initial buffers', r.names())
for mode in (2, 3, 4, 5, 1, 8):
    r.mode = mode
    calls = r.key(10, 1)
    if calls != PLAIN() or r.opens or r.names() != STOCK_NAMES or r.c.get32(A['vars'] + 4) != 0:
        fail('no change', mode, calls)

# 2. P -> SCENE: rescan, FILM names, pop-up with frames left, stock key hook skipped, then SCENE -> P again
for count, left in ((0, 36), (1, 35), (17, 19), (36, 0), (37, 0), (0xFFFFFFFF, 0)):
    r = Rig()
    r.mode = 10
    r.count = count
    calls = r.key(10, 1)
    want = [('open'), ('arm', 11), ('toast', 11), ('keycall', 10, 1)]
    if calls != want or r.opens != [(OBJ, 0x64)]:
        fail('enter scene', count, calls, r.opens)
    if r.names() != FILM_NAMES or r.c.get32(A['vars'] + 4) != 1 or utf16(r.c, SLOT0) != 'Film %02d left' % left:
        fail('enter scene state', count, r.names(), utf16(r.c, SLOT0))
    calls = r.key(5, 1)                                   # still SCENE: plain
    if calls != PLAIN(5, 1) or len(r.opens) != 1:
        fail('stay in scene', calls)
    r.mode = 2
    r.count = 99
    calls = r.key(6, 1)
    if calls != ['open', ('arm', 11), ('toast', 11), ('keycall', 6, 1)] or r.opens[-1] != (OBJ, 0x64) or len(r.opens) != 2:
        fail('leave scene', calls, r.opens)
    if r.names() != STOCK_NAMES or r.c.get32(A['vars'] + 4) != 0 or utf16(r.c, SLOT0) != 'Film off':
        fail('leave scene state', r.names(), utf16(r.c, SLOT0))
    if r.stray():
        fail('read outside RAM window', r.stray())

# 3. the object is found wherever it sits in the manager, and a stale cached pointer is replaced
for word in (0, 1, 0x20, 0x7F, 0xFF):
    r = Rig(mgr_word=word)
    r.mode = 10
    r.key()
    if r.opens != [(OBJ, 0x64)] or r.c.get32(A['vars']) != OBJ:
        fail('find object at word', word, r.opens)
r = Rig(cached=0xC1999990)                                # cached pointer that is not a CSFileList any more
r.mode = 10
r.key()
if r.opens != [(OBJ, 0x64)] or r.c.get32(A['vars']) != OBJ:
    fail('stale cache', r.opens)
r = Rig(cached=0x1234)                                    # junk cache: never dereferenced
r.mode = 10
r.key()
if r.opens != [(OBJ, 0x64)] or r.stray():
    fail('junk cache', r.opens, r.stray())

# 4. nothing found / broken chain: nothing changes and the state is not committed (retried on the next key)
for kw in (dict(obj_chain=False), ):
    r = Rig(**kw)
    r.mode = 10
    calls = r.key(10, 1)
    if calls != PLAIN() or r.opens or r.names() != STOCK_NAMES or r.c.get32(A['vars'] + 4) != 0:
        fail('broken chain', calls, r.opens, r.names())
r = Rig()
r.c.mem.update({MGR + 4 * 5 + k: 0 for k in range(4)})    # object gone from the manager
r.mode = 10
calls = r.key()
if calls != PLAIN() or r.opens or r.names() != STOCK_NAMES or r.stray():
    fail('object missing', calls, r.opens)
for mgr in (0, 0x12345678, 0xC1000002):
    r = Rig()
    r.c.set32(P.MANAGER_GLOBAL, mgr)
    r.mode = 10
    calls = r.key()
    if calls != PLAIN() or r.opens or r.stray():
        fail('bad manager', hex(mgr), calls, r.stray())

# 5. the pointer patches on a real built .elf
elf_path = r'extracted\tl500_008264_FAUXJI63\EX1-DSP-SR-008264.elf'
if os.path.exists(elf_path):
    stock = open(elf_path, 'rb').read()
    out = F.patch(stock)
    again = F.patch(out)
    if out != again:
        fail('patch is not idempotent')
    def word(d, a): return struct.unpack_from('<I', d, a - B)[0]
    def cs(d, a):
        o = a - B
        return d[o:d.index(b'\0', o)].decode('latin1')
    for pool, stock_ptr in F.STOCK.items():
        want = {F.FMT1_POOL: A['buf'] + 8, F.FMT2_POOL: A['buf'] + 16}.get(pool, A['buf'])
        if word(out, pool) != want:
            fail('pointer not patched', hex(pool))
        if cs(out, word(out, pool)) != cs(stock, stock_ptr):      # the RAM buffer starts out equal to the stock string
            fail('buffer differs from the stock string', hex(pool), cs(out, word(out, pool)), cs(stock, stock_ptr))
    changed = [i for i in range(len(stock)) if stock[i] != out[i]]
    lo, hi = min(changed) + B, max(changed) + B
    outside = [hex(i + B) for i in changed if not (BASE <= i + B < BASE + len(DATA)) and (i + B) not in
               [p + k for p in list(F.STOCK) + [ui.KEY_CALL[0]] for k in range(4)]]
    if outside:
        fail('bytes changed outside the block / pointers / key site', outside[:8])
    print('real .elf: 6 pointers + key site + %d bytes of block; first %x last %x' % (len(DATA), BASE, BASE + len(DATA)))
else:
    print('(no FAUXJI63 .elf here: skipped the real-image check)')

print('film block', len(DATA), 'bytes at', hex(BASE), 'ends', hex(BASE + len(DATA)), 'limit', hex(ui.DIAG_END), 'bad', bad)

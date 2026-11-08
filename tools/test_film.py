"""Runs the real emitted words of film_mode.py (stage 1) in test_sky's ARM interpreter, and checks the pointer patches on a built .elf.
From the project root:  python tools/test_film.py     (prints "bad 0" when every case is right)"""
import os, struct, sys
sys.path.insert(0, 'tools')
import fauxji_ui as ui
import diag_probe as P
import film_mode as F
from test_sky import CPU

B = ui.B
BLOCKS, LAB = F.blob()
BASE, DATA = BLOCKS[0]
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
        self.c = CPU(BLOCKS)
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
        self.at_draw = []
        c.stubs[ui.DRAW_ICONS] = lambda s: (self.calls.append(('draw', s.r[0])),                    # full redraw of the shooting-screen icons (r0 = 0)
                                            self.at_draw.append((s.get32(A['vars'] + 4), s.get32(A['vars'] + 8), s.get32(A['vars'] + 12))))
        c.stubs[ui.KEYHOOK] = lambda s: self.calls.append(('keyhook', s.r[0], s.r[1]))
        c.stubs[ui.KEY_CALL[1]] = lambda s: self.calls.append(('keycall', s.r[0], s.r[1]))
        c.stubs[F.GATE_STOCK] = lambda s: (self.calls.append(('gate', s.r[0], s.r[1])), s.r.__setitem__(0, 0x55))
        c.stubs[F.DIAL_STOCK] = lambda s: self.calls.append(('dial', s.r[0], s.r[1]))
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
    want = [('open'), ('arm', 11), ('draw', 0), ('toast', 11), ('keycall', 10, 1)]      # redraw so the stock shots-left number is recalculated at once
    if calls != want or r.opens != [(OBJ, 0x64)]:
        fail('enter scene', count, calls, r.opens)
    if r.at_draw != [(1, count, 0)]:                       # film flag on, files seen = the rescan's count, unlocked: all set before the redraw
        fail('state at the redraw (enter)', count, r.at_draw)
    if r.names() != FILM_NAMES or r.c.get32(A['vars'] + 4) != 1 or utf16(r.c, SLOT0) != 'Film %02d left' % left:
        fail('enter scene state', count, r.names(), utf16(r.c, SLOT0))
    calls = r.key(5, 1)                                   # still SCENE: plain
    if calls != PLAIN(5, 1) or len(r.opens) != 1:
        fail('stay in scene', calls)
    r.mode = 2
    r.count = 99
    r.at_draw.clear()
    calls = r.key(6, 1)
    if r.at_draw != [(0, 99, 0)]:
        fail('state at the redraw (leave)', r.at_draw)
    if calls != ['open', ('arm', 11), ('draw', 0), ('toast', 11), ('keycall', 6, 1)] or r.opens[-1] != (OBJ, 0x64) or len(r.opens) != 2:
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

# 5b. shots left (stage 2a): min(stock shots left, 36 - files in the roll) while in SCENE, untouched otherwise
def clamp(r, remaining):
    c = r.c
    seen = []
    c.stubs[F.ROLL_BACK] = lambda s: (seen.append((s.r[0], s.r[13])), 'stop')[1]      # the function epilogue follows in the firmware
    for i in range(2, 13):
        c.r[i] = r.saved[i]
    c.r[0] = remaining
    c.run(LAB['rollclamp'], lr=0xCAFE0000, ret=0xCAFE0000)
    if not all(c.r[i] == r.saved[i] for i in range(4, 12)):
        fail('clamp changed callee-saved registers')
    if len(seen) != 1 or seen[0][1] != 0x10000058:
        fail('clamp stack / exit', seen)
    return seen[0][0] if seen else None


for n in (0, 1, 6, 35, 36, 37, 500, 0xFFFFFFFF):
    left = max(0, 36 - n) if n <= 36 else 0
    for stock in (0, 1, 5, 36, 37, 400, 99999):
        r = Rig()
        r.mode = 10
        r.key()                                              # enter SCENE: caches the object, film flag on
        r.c.set32(LIST + 0x24, n)
        got = clamp(r, stock)
        if got != min(stock, left):
            fail('clamp', n, stock, got, 'want', min(stock, left))
r = Rig()                                                    # never in SCENE: stock value untouched
r.c.set32(LIST + 0x24, 3)
for stock in (0, 7, 99999):
    if clamp(r, stock) != stock:
        fail('clamp outside scene', stock)
r = Rig()
r.mode = 10
r.key()
r.mode = 2
r.key(6, 1)                                                  # left SCENE again: film flag off
r.c.set32(LIST + 0x24, 30)
if clamp(r, 77) != 77:
    fail('clamp after leaving scene')
for breakit in ('obj', 'mgr', 'list'):                       # a pointer in the chain went bad: stock value untouched, nothing read outside the window
    r = Rig()
    r.mode = 10
    r.key()
    r.c.set32(LIST + 0x24, 30)
    if breakit == 'obj':
        r.c.set32(A['vars'], 0x1234)
    elif breakit == 'mgr':
        r.c.set32(OBJ + 0x118, 0x12345678)
    else:
        r.c.set32(DCFM + 0x10, 0xC1300002)
    r.reads.clear()
    got = clamp(r, 20)
    if got != 20 or r.stray():
        fail('clamp with broken', breakit, got, r.stray())

# 5c. wind-on lock: shot detection in the shots-left hook, the gate on the shutter keys, the unlock on a turn of the front dial
def utf16s(c, addr):
    return utf16(c, addr)


def enter_scene(count=0):
    r = Rig()
    r.mode = 10
    r.count = count
    r.key()
    return r


SLOT1 = F.SLOT1
r = enter_scene(5)
if r.c.get32(A['vars'] + 8) != 5 or r.c.get32(A['vars'] + 12) != 0:
    fail('entering scene: files seen / unlocked', r.c.get32(A['vars'] + 8), r.c.get32(A['vars'] + 12))
for step, (count, locked, seen) in enumerate(((5, 0, 5), (5, 0, 5), (6, 1, 6), (6, 1, 6), (7, 1, 7), (3, 1, 3))):
    r.c.set32(LIST + 0x24, count)
    clamp(r, 36)
    if (r.c.get32(A['vars'] + 12), r.c.get32(A['vars'] + 8)) != (locked, seen):
        fail('shot detection', step, count, r.c.get32(A['vars'] + 12), r.c.get32(A['vars'] + 8))
r = enter_scene(5)                                          # fewer files than before (deleted on a PC) never locks
r.c.set32(LIST + 0x24, 2)
clamp(r, 36)
if r.c.get32(A['vars'] + 12) != 0 or r.c.get32(A['vars'] + 8) != 2:
    fail('count went down')
r = enter_scene(5)
r.c.set32(LIST + 0x24, 6)
clamp(r, 36)                                                # locked now
r.mode = 2
r.key(6, 1)                                                 # leaving SCENE resets the lock
if r.c.get32(A['vars'] + 12) != 0:
    fail('leaving scene keeps the lock')
r.mode = 10
r.count = 9
r.key()                                                     # entering again: unlocked, files seen = new count
if r.c.get32(A['vars'] + 12) != 0 or r.c.get32(A['vars'] + 8) != 9:
    fail('re-entering scene', r.c.get32(A['vars'] + 12), r.c.get32(A['vars'] + 8))


def gate(r, key, state, fp=0x1111):
    c = r.c
    r.calls.clear()
    for i in range(2, 13):
        c.r[i] = r.saved[i]
    c.r[7], c.r[8] = state, key                              # the dispatcher's own state / key registers
    c.r[0], c.r[1] = fp, key
    c.run(LAB['filmgate'], lr=0xCAFE0000, ret=0xCAFE0000)
    exp = {i: r.saved[i] for i in range(4, 11)}
    exp[7], exp[8] = state, key
    if not (all(c.r[i] == exp[i] for i in exp) and c.r[13] == 0x10000000):
        fail('gate changed registers / stack', key, state)
    return c.r[0], list(r.calls)


ORIG = lambda key, fp=0x1111: [('gate', fp, key)]
SWALLOWED = [('arm', 12), ('toast', 12)]
r = Rig()                                                   # not in SCENE: always the stock call
r.c.set32(A['vars'] + 12, 1)
if gate(r, 10, 1) != (0x55, ORIG(10)):
    fail('gate outside scene')
r = enter_scene(0)                                          # SCENE, not locked: stock call
if gate(r, 10, 1) != (0x55, ORIG(10)) or gate(r, 10, 2) != (0x55, ORIG(10)):
    fail('gate unlocked')
r.c.set32(A['vars'] + 12, 1)                                # SCENE and locked
for key, state, swallow in ((10, 1, True), (10, 2, True), (11, 1, True), (11, 2, True), (10, 0, False), (10, 3, False), (11, 0, False),
                            (5, 1, False), (6, 1, False), (9, 1, False), (14, 1, False), (0, 1, False), (12, 1, False)):
    got = gate(r, key, state)
    want = (0, SWALLOWED) if swallow else (0x55, ORIG(key))
    if got != want:
        fail('gate locked', key, state, got)
    if swallow and utf16(r.c, SLOT1) != 'Wind on >':
        fail('wind pop-up text', utf16(r.c, SLOT1))
if r.stray():
    fail('gate read outside the window', r.stray())


def dial(r, value, fp=0x2222):
    c = r.c
    r.calls.clear()
    for i in range(2, 13):
        c.r[i] = r.saved[i]
    c.set32(PAYLOAD_EV, VT_EV)                               # the click dial event: vtable with the method at +0x10
    c.set32(VT_EV + 0x10, 0)
    c.set32(VT_EV + 0x14, DIRFN_EV)
    asked = []
    c.stubs[DIRFN_EV] = lambda s: (asked.append(s.r[0]), s.r.__setitem__(0, value))
    c.r[0], c.r[1] = fp, PAYLOAD_EV
    c.run(LAB['filmdial'], lr=0xCAFE0000, ret=0xCAFE0000)
    if not (all(c.r[i] == r.saved[i] for i in range(4, 11)) and c.r[13] == 0x10000000):
        fail('dial changed registers / stack', value)
    return list(r.calls), asked


PAYLOAD_EV, VT_EV, DIRFN_EV = 0xC1500000, 0xC1600000, 0xC1700000
DIAL = lambda fp=0x2222: [('dial', fp, PAYLOAD_EV)]
r = Rig()                                                   # not in SCENE: straight to the stock handler, the event is not touched
r.c.set32(A['vars'] + 12, 1)
if dial(r, 1) != (DIAL(), []):
    fail('dial outside scene')
r = enter_scene(0)                                          # SCENE but not locked: same
if dial(r, 1) != (DIAL(), []) or r.c.get32(A['vars'] + 12) != 0:
    fail('dial unlocked')
for value, unlocks in ((1, True), (0, False), (2, False), (3, False)):
    r = enter_scene(0)
    r.c.set32(A['vars'] + 12, 1)
    calls, asked = dial(r, value)
    want_calls = (SWALLOWED if False else [('arm', 12), ('toast', 12)]) + DIAL() if unlocks else DIAL()
    if calls != want_calls or asked != [PAYLOAD_EV] or r.c.get32(A['vars'] + 12) != (0 if unlocks else 1):
        fail('dial locked', value, calls, asked, r.c.get32(A['vars'] + 12))
    if unlocks and utf16(r.c, SLOT1) != 'Wound':
        fail('wound text', utf16(r.c, SLOT1))
if r.stray():
    fail('dial read outside the window', r.stray())

# full cycle: shoot -> locked -> shutter blocked -> turn left (still blocked) -> turn right (unlocked) -> shutter passes
r = enter_scene(0)
if gate(r, 10, 1) != (0x55, ORIG(10)):
    fail('cycle: first frame must be free')
r.c.set32(LIST + 0x24, 1)
clamp(r, 36)                                                # the photo was saved
if gate(r, 10, 1) != (0, SWALLOWED):
    fail('cycle: locked after a shot')
dial(r, 0)
if gate(r, 10, 2) != (0, SWALLOWED):
    fail('cycle: still locked after a turn to the left')
dial(r, 1)
if gate(r, 10, 1) != (0x55, ORIG(10)):
    fail('cycle: unlocked after a turn to the right')

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
    ranges = [(b, b + len(x)) for b, x in BLOCKS]
    sites = [p + k for p in list(F.STOCK) + [ui.KEY_CALL[0], F.ROLL_SITE, F.GATE_SITE, F.DIAL_SITE] for k in range(4)]
    outside = [hex(i + B) for i in changed if not any(lo <= i + B < hi for lo, hi in ranges) and (i + B) not in sites]
    if word(out, F.ROLL_SITE) != ui._b(F.ROLL_SITE, LAB['rollclamp']):
        fail('shots-left hook not in place')
    if outside:
        fail('bytes changed outside the block / pointers / key site', outside[:8])
    print('real .elf: 6 pointers + 4 hook sites + blocks %s' % ', '.join('%x-%x' % r_ for r_ in ranges))
else:
    print('(no FAUXJI63 .elf here: skipped the real-image check)')

print('film blocks', [(hex(b), len(x)) for b, x in BLOCKS], 'bad', bad)

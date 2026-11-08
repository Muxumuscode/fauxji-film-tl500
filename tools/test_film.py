"""Runs the real emitted words of film_mode.py in test_sky's ARM interpreter, and checks the pointer patches on a built .elf.
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
ENTRY = LAB['filmhook']
MGR, OBJ, DCFM, LIST = 0xC1000000, 0xC1100000, 0xC1200000, 0xC1300000
SLOT0, SLOT1 = ui.STR_BASE, F.SLOT1
V = A['vars']
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
    def __init__(self, mgr_word=5, obj_chain=True, cached=None, rolls=None):
        self.c = CPU(BLOCKS)
        c = self.c
        self.mode, self.opens, self.calls, self.asked = 2, [], [], []
        self.rolls = dict(rolls or {})                   # folder name -> files in it (the rescan's return value); DCIM has 27
        c.set32(P.MANAGER_GLOBAL, MGR)
        c.set32(MGR + 4 * mgr_word, OBJ)
        if obj_chain:
            c.set32(OBJ, P.VPTR); c.set32(OBJ + 0x118, DCFM); c.set32(DCFM + 0x10, LIST); c.set32(LIST + 0x20, 0x64)
        if cached is not None:
            c.set32(V, cached)
        self.reads = []
        orig = c.get32
        c.get32 = lambda a: (self.reads.append(a), orig(a))[1]
        self.at_draw = []

        def do_open(s):
            name = cstr(c, A['buf'], 8)
            self.opens.append(name)
            self.calls.append('open')
            s.r[0] = self.rolls.get(name, 27 if name == 'DCIM' else 0)

        c.stubs[F.RAW_GET] = lambda s: (self.asked.append(s.r[0]), c.set32(s.r[1], self.mode if s.r[0] == 3 else 0))   # the raw getter writes the real mode
        c.stubs[F.OPEN] = do_open
        c.stubs[ui.ARM_NAME] = lambda s: self.calls.append(('arm', s.r[0]))
        c.stubs[ui.TOAST_CODE] = lambda s: self.calls.append(('toast', s.r[0]))
        c.stubs[ui.DRAW_ICONS] = lambda s: (self.calls.append(('draw', s.r[0])),
                                            self.at_draw.append((s.get32(V + 4), s.get32(V + 8), s.get32(V + 12), s.get32(V + 16))))
        c.stubs[ui.KEYHOOK] = lambda s: self.calls.append(('keyhook', s.r[0], s.r[1]))
        c.stubs[ui.KEY_CALL[1]] = lambda s: self.calls.append(('keycall', s.r[0], s.r[1]))
        c.stubs[F.GATE_STOCK] = lambda s: (self.calls.append(('gate', s.r[0], s.r[1])), s.r.__setitem__(0, 0x55))
        c.stubs[F.DIAL_STOCK] = lambda s: self.calls.append(('dial', s.r[0], s.r[1]))
        self.saved = [0x2000 + i for i in range(16)]

    def run(self, entry, key, state, extra=None):
        c = self.c
        self.calls.clear(); self.asked.clear()
        for i in range(2, 13):
            c.r[i] = self.saved[i]
        c.r[0], c.r[1] = key, state
        if extra:
            for i, v in extra.items():
                c.r[i] = v
        c.run(entry, lr=0xCAFE0000, ret=0xCAFE0000, limit=3000000)
        exp = {i: self.saved[i] for i in range(4, 11)}
        if extra:
            exp.update({i: v for i, v in extra.items() if 4 <= i <= 10})
        if not (all(c.r[i] == exp[i] for i in exp) and c.r[13] == 0x10000000):
            fail('registers / stack changed', entry, key, state)
        return list(self.calls)

    def key(self, key=10, state=1):
        return self.run(ENTRY, key, state)

    def names(self):
        c = self.c
        return cstr(c, A['buf'], 8), cstr(c, A['buf'] + F.FMT1_AT, 16), cstr(c, A['buf'] + F.FMT2_AT, 24)

    def v(self, i):
        return self.c.get32(V + i)

    def stray(self):
        stack = lambda a: 0x0FFFF000 <= a < 0x10000000
        return [hex(a) for a in self.reads if not (P.RAM_LO <= a < P.RAM_HI) and not stack(a)]


def roll_names(n):
    nm = 'FILM%03d' % n
    return (nm, '%%s/%s' % nm, '%%s/%s/100PHOTO' % nm)


STOCK_NAMES = ('DCIM', '%s/DCIM', '%s/DCIM/100PHOTO')
POP = [('arm', 11), ('draw', 0), ('toast', 11)]                  # the look-11 pop-up with the full icon redraw
ENTER = ['open'] + POP + [('keycall', 10, 1)]

# 1. buffers start as the stock strings; nothing happens while the mode does not change
r = Rig()
if r.names() != STOCK_NAMES:
    fail('initial buffers', r.names())
for mode in (2, 3, 4, 5, 1, 8):
    r.mode = mode
    calls = r.key(10, 1)
    if calls != [('keyhook', 10, 1)] or r.opens or r.names() != STOCK_NAMES or r.v(4) != 0:
        fail('no change', mode, calls)

# 2. entering SCENE on the first roll: FILM001, frames left from the rescan, then leaving again
for count, left in ((0, 36), (1, 35), (17, 19), (35, 1)):
    r = Rig(rolls={'FILM001': count})
    r.mode = 10
    calls = r.key(10, 1)
    if calls != ENTER or r.opens != ['FILM001']:
        fail('enter scene', count, calls, r.opens)
    if r.at_draw != [(1, count, 0, 1)]:                       # flag on, files seen, unlocked, roll 1: all set before the redraw
        fail('state at the redraw (enter)', count, r.at_draw)
    if r.names() != roll_names(1) or utf16(r.c, SLOT0) != 'Film %02d left' % left or r.v(4) != 1 or r.v(8) != count or r.v(16) != 1:
        fail('enter scene state', count, r.names(), utf16(r.c, SLOT0), r.v(8), r.v(16))
    if r.key(5, 1) != [('keyhook', 5, 1)] or len(r.opens) != 1:
        fail('stay in scene')
    r.mode = 2
    r.at_draw.clear()
    calls = r.key(6, 1)
    if calls != ['open'] + POP + [('keycall', 6, 1)] or r.opens != ['FILM001', 'DCIM'] or r.at_draw != [(0, 27, 0, 1)]:
        fail('leave scene', calls, r.opens, r.at_draw)
    if r.names() != STOCK_NAMES or r.v(4) != 0 or utf16(r.c, SLOT0) != 'Film off':
        fail('leave scene state', r.names(), utf16(r.c, SLOT0))
    if r.stray():
        fail('read outside RAM window', r.stray())

# 3. finding the current roll: the first with room; an empty folder after full ones does not start silently
for rolls, want_opens, want_roll, want_files in (
        ({'FILM001': 36, 'FILM002': 36, 'FILM003': 12}, ['FILM001', 'FILM002', 'FILM003'], 3, 12),
        ({'FILM001': 36, 'FILM002': 5}, ['FILM001', 'FILM002'], 2, 5),
        ({'FILM001': 36}, ['FILM001', 'FILM002', 'FILM001'], 1, 36),                  # FILM002 is new and empty: stay on the full roll
        ({'FILM001': 36, 'FILM002': 36}, ['FILM001', 'FILM002', 'FILM003', 'FILM002'], 2, 36),
        ({'FILM001': 0}, ['FILM001'], 1, 0),                                           # a first roll that is empty is the roll
        ({'FILM001': 0xFFFFFFFF}, ['FILM001'], 1, 0xFFFFFFFF),                         # failure code: stop, never loop
        ({'FILM001': 40000}, ['FILM001', 'FILM002', 'FILM001'], 1, 40000),             # a big but plausible count counts as a full roll
        ({'FILM001': 0x20000}, ['FILM001'], 1, 0x20000)):                              # garbage count: stop
    r = Rig(rolls=rolls)
    r.mode = 10
    r.key()
    left = 0 if (want_files >= 36) else 36 - want_files
    if r.opens != want_opens or r.v(16) != want_roll or r.v(8) != want_files or r.names() != roll_names(want_roll):
        fail('probe', rolls, r.opens, r.v(16), r.v(8), r.names())
    if utf16(r.c, SLOT0) != 'Film %02d left' % left:
        fail('probe text', rolls, utf16(r.c, SLOT0))
r = Rig(rolls={'FILM998': 36, 'FILM999': 36})                                         # the last roll number is the cap
r.c.set32(V + 16, 998)
r.mode = 10
r.key()
if r.opens != ['FILM998', 'FILM999'] or r.v(16) != 999 or r.names() != roll_names(999):
    fail('roll cap', r.opens, r.v(16), r.names())

# 4. the object is found wherever it sits in the manager, and a stale cached pointer is replaced
for word in (0, 1, 0x20, 0x7F, 0xFF):
    r = Rig(mgr_word=word)
    r.mode = 10
    r.key()
    if r.opens != ['FILM001'] or r.v(0) != OBJ:
        fail('find object at word', word, r.opens)
for cached in (0xC1999990, 0x1234):
    r = Rig(cached=cached)
    r.mode = 10
    r.key()
    if r.opens != ['FILM001'] or r.v(0) != OBJ or r.stray():
        fail('stale / junk cache', hex(cached), r.opens, r.stray())

# 5. nothing found / broken chain / bad manager: nothing changes and the state is not committed (retried on the next key)
r = Rig(obj_chain=False)
r.mode = 10
calls = r.key(10, 1)
if calls != [('keyhook', 10, 1)] or r.opens or r.names() != STOCK_NAMES or r.v(4) != 0:
    fail('broken chain', calls, r.opens, r.names())
r = Rig()
r.c.mem.update({MGR + 4 * 5 + k: 0 for k in range(4)})
r.mode = 10
calls = r.key()
if calls != [('keyhook', 10, 1)] or r.opens or r.names() != STOCK_NAMES or r.stray():
    fail('object missing', calls, r.opens)
for mgr in (0, 0x12345678, 0xC1000002):
    r = Rig()
    r.c.set32(P.MANAGER_GLOBAL, mgr)
    r.mode = 10
    calls = r.key()
    if calls != [('keyhook', 10, 1)] or r.opens or r.stray():
        fail('bad manager', hex(mgr), calls, r.stray())


def enter_scene(count=0, rolls=None):
    r = Rig(rolls=dict(rolls or {'FILM001': count}))
    r.mode = 10
    r.key()
    return r


# 6. shots left (counter): min(stock shots left, 36 - files in the roll) while in SCENE, untouched otherwise
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
        r = enter_scene(0)
        r.c.set32(LIST + 0x24, n)
        got = clamp(r, stock)
        if got != min(stock, left):
            fail('clamp', n, stock, got, 'want', min(stock, left))
r = Rig()
r.c.set32(LIST + 0x24, 3)
for stock in (0, 7, 99999):
    if clamp(r, stock) != stock:
        fail('clamp outside scene', stock)
r = enter_scene(0)
r.mode = 2
r.key(6, 1)
r.c.set32(LIST + 0x24, 30)
if clamp(r, 77) != 77:
    fail('clamp after leaving scene')
for breakit in ('obj', 'mgr', 'list'):
    r = enter_scene(0)
    r.c.set32(LIST + 0x24, 30)
    if breakit == 'obj':
        r.c.set32(V, 0x1234)
    elif breakit == 'mgr':
        r.c.set32(OBJ + 0x118, 0x12345678)
    else:
        r.c.set32(DCFM + 0x10, 0xC1300002)
    r.reads.clear()
    got = clamp(r, 20)
    if got != 20 or r.stray():
        fail('clamp with broken', breakit, got, r.stray())

# 7. shot detection (a rising file count locks), entering resets the lock
r = enter_scene(5)
if (r.v(8), r.v(12)) != (5, 0):
    fail('entering scene: files seen / unlocked', r.v(8), r.v(12))
for step, (count, locked, seen) in enumerate(((5, 0, 5), (5, 0, 5), (6, 1, 6), (6, 1, 6), (7, 1, 7), (3, 1, 3))):
    r.c.set32(LIST + 0x24, count)
    clamp(r, 36)
    if (r.v(12), r.v(8)) != (locked, seen):
        fail('shot detection', step, count, r.v(12), r.v(8))
r = enter_scene(5)
r.c.set32(LIST + 0x24, 2)
clamp(r, 36)
if r.v(12) != 0 or r.v(8) != 2:
    fail('count went down')
r = enter_scene(5)
r.c.set32(LIST + 0x24, 6)
clamp(r, 36)
r.mode = 2
r.key(6, 1)
if r.v(12) != 0:
    fail('leaving scene keeps the lock')
r.mode = 10
r.rolls['FILM001'] = 9
r.key()
if r.v(12) != 0 or r.v(8) != 9:
    fail('re-entering scene', r.v(12), r.v(8))


# 8. the gate: wind-on lock on the shutter keys, the film-look key rules
def gate(r, key, state, fp=0x1111):
    c = r.c
    r.calls.clear()
    for i in range(2, 13):
        c.r[i] = r.saved[i]
    c.r[7], c.r[8] = state, key                              # the dispatcher's own state / key registers
    c.r[0], c.r[1] = fp, key
    c.run(LAB['filmgate'], lr=0xCAFE0000, ret=0xCAFE0000, limit=3000000)
    exp = {i: r.saved[i] for i in range(4, 11)}
    exp[7], exp[8] = state, key
    if not (all(c.r[i] == exp[i] for i in exp) and c.r[13] == 0x10000000):
        fail('gate changed registers / stack', key, state)
    return c.r[0], list(r.calls)


ORIG = lambda key, fp=0x1111: [('gate', fp, key)]
SWALLOWED = [('arm', 12), ('toast', 12)]
r = Rig()                                                   # not in SCENE: always the stock call, whatever the variables say
r.c.set32(V + 12, 1)
r.c.set32(V + 8, 36)
for key in (10, 14):
    if gate(r, key, 1) != (0x55, ORIG(key)):
        fail('gate outside scene', key)
r = enter_scene(0)                                          # SCENE, not locked: stock call
if gate(r, 10, 1) != (0x55, ORIG(10)) or gate(r, 10, 2) != (0x55, ORIG(10)):
    fail('gate unlocked')
r.c.set32(V + 12, 1)                                        # SCENE and locked
for key, state, swallow in ((10, 1, True), (10, 2, True), (11, 1, True), (11, 2, True), (10, 0, False), (10, 3, False), (11, 0, False),
                            (5, 1, False), (6, 1, False), (9, 1, False), (0, 1, False), (12, 1, False)):
    got = gate(r, key, state)
    want = (0, SWALLOWED) if swallow else (0x55, ORIG(key))
    if got != want:
        fail('gate locked', key, state, got)
    if swallow and utf16(r.c, SLOT1) != 'Wind on >':
        fail('wind pop-up text', utf16(r.c, SLOT1))
if r.stray():
    fail('gate read outside the window', r.stray())

# the film-look key (14): empty roll = free, part-shot roll = swallowed, full roll = a new roll then through
r = enter_scene(0)
if gate(r, 14, 1) != (0x55, ORIG(14)) or r.opens != ['FILM001'] or r.v(16) != 1:
    fail('film key on an empty roll', r.opens)
for files in (1, 10, 35):
    r = enter_scene(files)
    r.c.set32(V + 12, 0)
    got = gate(r, 14, 1)
    if got != (0, SWALLOWED) or utf16(r.c, SLOT1) != 'Roll in use' or r.opens != ['FILM001'] or r.v(16) != 1:
        fail('film key mid-roll', files, got, r.opens)
    if gate(r, 14, 2) != (0x55, ORIG(14)) or gate(r, 14, 0) != (0x55, ORIG(14)):         # releases are never swallowed
        fail('film key release mid-roll', files)
r = enter_scene(36, rolls={'FILM001': 36})                  # a full roll: AE-L starts roll 2, then the stock FILM SIM sees the key
r.c.set32(V + 12, 1)
r.rolls['FILM002'] = 0
r.at_draw.clear()
got = gate(r, 14, 1)
if got != (0x55, ['open'] + POP + ORIG(14)) or r.opens[-1] != 'FILM002':
    fail('new roll', got, r.opens)
if r.names() != roll_names(2) or (r.v(16), r.v(8), r.v(12), r.v(4)) != (2, 0, 0, 1) or utf16(r.c, SLOT0) != 'Film 36 left':
    fail('new roll state', r.names(), r.v(16), r.v(8), r.v(12), utf16(r.c, SLOT0))
if r.at_draw != [(1, 0, 0, 2)]:
    fail('new roll state at the redraw', r.at_draw)
n_opens = len(r.opens)
got = gate(r, 14, 1)                                        # roll 2 is empty now: the look can be chosen freely, no second new roll
if got != (0x55, ORIG(14)) or len(r.opens) != n_opens:
    fail('after the new roll', got, r.opens)
r = enter_scene(36, rolls={'FILM001': 36})                  # garbage count: leave the key alone
r.c.set32(V + 8, 0xFFFFFFFF)
if gate(r, 14, 1) != (0x55, ORIG(14)):
    fail('film key with a garbage count')
r = enter_scene(36, rolls={'FILM001': 36})                  # new roll asked for but the object is gone: key passes, nothing changes
r.c.set32(V, 0)
r.c.mem.update({MGR + 4 * 5 + k: 0 for k in range(4)})
before = list(r.opens)
got = gate(r, 14, 1)
if got != (0x55, ORIG(14)) or r.opens != before:
    fail('new roll without an object', got, r.opens)
if r.stray():
    fail('film key read outside the window', r.stray())

# 9. the dial: unlock on a turn to the right
PAYLOAD_EV, VT_EV, DIRFN_EV = 0xC1500000, 0xC1600000, 0xC1700000


def dial(r, value, fp=0x2222):
    c = r.c
    c.set32(PAYLOAD_EV, VT_EV)
    c.set32(VT_EV + 0x10, 0)
    c.set32(VT_EV + 0x14, DIRFN_EV)
    asked = []
    c.stubs[DIRFN_EV] = lambda s: (asked.append(s.r[0]), s.r.__setitem__(0, value))
    calls = r.run(LAB['filmdial'], fp, PAYLOAD_EV)
    return calls, asked


DIAL = lambda fp=0x2222: [('dial', fp, PAYLOAD_EV)]
r = Rig()
r.c.set32(V + 12, 1)
if dial(r, 1) != (DIAL(), []):
    fail('dial outside scene')
r = enter_scene(0)
if dial(r, 1) != (DIAL(), []) or r.v(12) != 0:
    fail('dial unlocked')
for value, unlocks in ((1, True), (0, False), (2, False), (3, False)):
    r = enter_scene(0)
    r.c.set32(V + 12, 1)
    calls, asked = dial(r, value)
    want_calls = [('arm', 12), ('toast', 12)] + DIAL() if unlocks else DIAL()
    if calls != want_calls or asked != [PAYLOAD_EV] or r.v(12) != (0 if unlocks else 1):
        fail('dial locked', value, calls, asked, r.v(12))
    if unlocks and utf16(r.c, SLOT1) != 'Wound':
        fail('wound text', utf16(r.c, SLOT1))

# 10. full cycle: shoot -> locked -> shutter blocked -> turn left (still blocked) -> turn right (unlocked) -> shutter passes
r = enter_scene(0)
if gate(r, 10, 1) != (0x55, ORIG(10)):
    fail('cycle: first frame must be free')
r.c.set32(LIST + 0x24, 1)
clamp(r, 36)
if gate(r, 10, 1) != (0, SWALLOWED):
    fail('cycle: locked after a shot')
dial(r, 0)
if gate(r, 10, 2) != (0, SWALLOWED):
    fail('cycle: still locked after a turn to the left')
dial(r, 1)
if gate(r, 10, 1) != (0x55, ORIG(10)):
    fail('cycle: unlocked after a turn to the right')

# 10b. SCENE reads as P: the hook at the end of GET_SYSVAL turns the value 10 into 2 for index 3 only; the film code still sees the real mode
def getval(idx, value):
    r = Rig()
    c = r.c
    seen = []
    c.stubs[F.GETVAL_BACK] = lambda s: (seen.append((s.r[0], s.r[13])), 'stop')[1]
    for i in range(1, 13):
        c.r[i] = 0x3000 + i
    c.r[11] = idx                                            # fp holds the index in GET_SYSVAL
    c.set32(0x10000000, value)                               # the fetched value on the stack
    c.run(LAB['filmget'], lr=0xCAFE0000, ret=0xCAFE0000)
    if len(seen) != 1 or seen[0][1] != 0x10000000:
        fail('filmget exit / sp', idx, value, seen)
    if not all(c.r[i] == (idx if i == 11 else 0x3000 + i) for i in range(1, 13)):
        fail('filmget changed a register other than r0', idx, value)
    return seen[0][0] if seen else None


for idx in (0, 1, 2, 3, 4, 5, 6, 7, 9, 0x1B):
    for value in (0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 19, 29, 30, 0xFFFFFFFF):
        want = F.MODE_P if (idx == 3 and value == F.SCENE_MODE) else value
        if getval(idx, value) != want:
            fail('filmget', idx, value, getval(idx, value), 'want', want)
r = Rig()                                                    # the film code reads the real mode through the raw getter, with the right index
r.mode = 10
r.key()
if r.asked != [3] or r.v(4) != 1:
    fail('film hook must read the raw mode (index 3)', r.asked, r.v(4))

# 11. the pointer patches on a real built .elf
elf_path = r'extracted\tl500_008264_FAUXJI63\EX1-DSP-SR-008264.elf'
if os.path.exists(elf_path):
    stock = open(elf_path, 'rb').read()
    out = F.patch(stock)
    if out != F.patch(out):
        fail('patch is not idempotent')

    def word(d, a): return struct.unpack_from('<I', d, a - B)[0]

    def cs(d, a):
        o = a - B
        return d[o:d.index(b'\0', o)].decode('latin1')

    for pool, stock_ptr in F.STOCK.items():
        want = {F.FMT1_POOL: A['buf'] + F.FMT1_AT, F.FMT2_POOL: A['buf'] + F.FMT2_AT}.get(pool, A['buf'])
        if word(out, pool) != want:
            fail('pointer not patched', hex(pool))
        if cs(out, word(out, pool)) != cs(stock, stock_ptr):      # the RAM buffer starts out equal to the stock string
            fail('buffer differs from the stock string', hex(pool), cs(out, word(out, pool)), cs(stock, stock_ptr))
    changed = [i for i in range(len(stock)) if stock[i] != out[i]]
    ranges = [(b, b + len(x)) for b, x in BLOCKS]
    sites = [p + k for p in list(F.STOCK) + [ui.KEY_CALL[0], F.ROLL_SITE, F.GATE_SITE, F.DIAL_SITE, F.GETVAL_SITE] for k in range(4)]
    outside = [hex(i + B) for i in changed if not any(lo <= i + B < hi for lo, hi in ranges) and (i + B) not in sites]
    if outside:
        fail('bytes changed outside the blocks / pointers / hook sites', outside[:8])
    if word(out, F.ROLL_SITE) != ui._b(F.ROLL_SITE, LAB['rollclamp']):
        fail('shots-left hook not in place')
    if word(out, ui.KEY_CALL[0]) != ui._b(ui.KEY_CALL[0], LAB['filmhook'], link=True):
        fail('key hook not in place')
    if word(out, F.GETVAL_SITE) != ui._b(F.GETVAL_SITE, LAB['filmget']):
        fail('SCENE-as-P hook not in place')
    print('real .elf: 6 pointers + 5 hook sites + blocks %s' % ', '.join('%x-%x' % r_ for r_ in ranges))
else:
    print('(no FAUXJI63 .elf here: skipped the real-image check)')

print('film blocks', [(hex(b), len(x)) for b, x in BLOCKS], 'bad', bad)

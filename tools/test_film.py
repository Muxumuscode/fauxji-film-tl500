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
STATE_OBJ = 0xC1400000
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


def utf16(c, addr, n=20):
    out = ''
    for i in range(n):
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
        for k, ch in enumerate(b'ROOT\0'):                       # the card root string inline in the DCF list object
            c.mem[LIST + 0x40 + k] = ch
        self.mkdirs, self.roots = [], []
        self.reads = []
        orig = c.get32
        c.get32 = lambda a: (self.reads.append(a), orig(a))[1]
        self.at_draw = []

        def do_open(s):
            name = cstr(c, A['buf'], 16).split('/')[-1]       # the roll's own name; the parent comes with the path
            self.opens.append(name)
            self.roots.append(cstr(c, LIST + 0x40, 48))
            self.calls.append('open')
            s.r[0] = self.rolls.get(name, 27 if name == 'DCIM' else 0)

        c.stubs[F.RAW_GET] = lambda s: (self.asked.append(s.r[0]), c.set32(s.r[1], self.mode if s.r[0] == 3 else 0))   # the raw getter writes the real mode
        c.stubs[F.OPEN] = do_open
        c.stubs[F.MKDIR] = lambda s: (self.mkdirs.append((s.r[0], cstr(c, s.r[1], 48), len(self.opens))), None)[1]
        c.stubs[ui.SET_UI] = lambda s: self.calls.append(('setui', s.r[0], s.r[1]))
        c.stubs[ui.APPLY] = lambda s: self.calls.append(('apply', s.r[0], s.r[1]))
        c.stubs[ui.REFRESH_MASKS] = lambda s: self.calls.append(('refresh',))
        c.stubs[ui.GUI_EVENT] = lambda s: self.calls.append(('guievt', s.r[0], s.r[1]))
        c.stubs[ui.NOTIFY1] = lambda s: self.calls.append(('n1', s.r[0]))
        c.stubs[ui.NOTIFY2] = lambda s: self.calls.append(('n2', s.r[0]))
        self.vis = []
        c.stubs[F.OSD_VIS] = lambda s: self.vis.append((s.r[0], s.r[1], s.r[2], s.r[3]))
        c.stubs[ui.ARM_NAME] = lambda s: self.calls.append(('arm', s.r[0]))
        c.stubs[ui.TOAST_CODE] = lambda s: self.calls.append(('toast', s.r[0]))
        c.stubs[ui.DRAW_ICONS] = lambda s: (self.calls.append(('draw', s.r[0])),
                                            self.at_draw.append((s.get32(V + 4), s.get32(V + 8), s.get32(V + 12), s.get32(V + 16))))
        c.stubs[ui.KEYHOOK] = lambda s: self.calls.append(('keyhook', s.r[0], s.r[1]))
        c.stubs[ui.KEY_CALL[1]] = lambda s: self.calls.append(('keycall', s.r[0], s.r[1]))
        c.stubs[F.GATE_STOCK] = lambda s: (self.calls.append(('gate', s.r[0], s.r[1])), s.r.__setitem__(0, 0x55))
        c.stubs[F.DIAL_STOCK] = lambda s: self.calls.append(('dial', s.r[0], s.r[1]))
        c.stubs[F.RATCHET] = lambda s: self.calls.append(('ratchet',))
        self.saved = [0x2000 + i for i in range(16)]

    def run(self, entry, key, state, extra=None):
        c = self.c
        self.calls.clear(); self.asked.clear(); self.vis.clear()
        for i in range(2, 13):
            c.r[i] = self.saved[i]
        c.r[11] = STATE_OBJ                                   # the dispatcher's fp: the live-view state object
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
        return cstr(c, A['buf'], 16), cstr(c, A['buf'] + F.FMT1_AT, 24), cstr(c, A['buf'] + F.FMT2_AT, 32)

    def v(self, i):
        return self.c.get32(V + i)

    def stray(self):
        stack = lambda a: 0x0FFFF000 <= a < 0x10000000
        return [hex(a) for a in self.reads if not (P.RAM_LO <= a < P.RAM_HI) and not stack(a)]


def roll_names(n, code='PROV'):
    nm = 'FILMS/%s%03d' % (code, n)
    return (nm, '%%s/%s' % nm, '%%s/%s/100PHOTO' % nm)


STOCK_NAMES = ('DCIM', '%s/DCIM', '%s/DCIM/100PHOTO')
POP = [('arm', 11), ('draw', 0), ('toast', 11)]                  # the look-11 pop-up with the full icon redraw
LOOK = lambda v: [('setui', 0x41, v), ('apply', 0x41, v), ('refresh',), ('guievt', 0x42, 0), ('n1', 0x41), ('n2', 0x41)]   # the film look being applied
ENTER = ['open'] + LOOK(0) + POP + [('keycall', 10, 1)]

# 1. buffers start as the stock strings; nothing happens while the mode does not change
r = Rig()
if r.names() != STOCK_NAMES:
    fail('initial buffers', r.names())
for mode in (2, 3, 4, 5, 1, 8):
    r.mode = mode
    calls = r.key(10, 1)
    if calls != [('keyhook', 10, 1)] or r.opens or r.names() != STOCK_NAMES or r.v(4) != 0:
        fail('no change', mode, calls)

# 2. entering SCENE on the first roll: PROV001, frames left from the rescan, then leaving again
for count, left in ((0, 36), (1, 35), (17, 19), (35, 1)):
    r = Rig(rolls={'PROV001': count})
    r.mode = 10
    calls = r.key(10, 1)
    if calls != ENTER or r.opens != ['PROV001']:
        fail('enter scene', count, calls, r.opens)
    if r.at_draw != [(1, count, 0, 1)]:                       # flag on, files seen, unlocked, roll 1: all set before the redraw
        fail('state at the redraw (enter)', count, r.at_draw)
    if r.names() != roll_names(1) or utf16(r.c, SLOT0) != 'PROV001 #%02d' % (count + 1) or r.v(4) != 1 or r.v(8) != count or r.v(16) != 1:
        fail('enter scene state', count, r.names(), utf16(r.c, SLOT0), r.v(8), r.v(16))
    if r.key(5, 1) != [('keyhook', 5, 1)] or len(r.opens) != 1:
        fail('stay in scene')
    r.mode = 2
    r.at_draw.clear()
    calls = r.key(6, 1)
    if calls != ['open'] + POP + [('keycall', 6, 1)] or r.opens != ['PROV001', 'DCIM'] or r.at_draw != [(0, 27, 0, 1)]:
        fail('leave scene', calls, r.opens, r.at_draw)
    if r.names() != STOCK_NAMES or r.v(4) != 0 or utf16(r.c, SLOT0) != 'Film off':
        fail('leave scene state', r.names(), utf16(r.c, SLOT0))
    if r.stray():
        fail('read outside RAM window', r.stray())

# 3. finding the current roll: the first with room; an empty folder after full ones does not start silently
for rolls, want_opens, want_roll, want_files in (
        ({'PROV001': 36, 'PROV002': 36, 'PROV003': 12}, ['PROV001', 'PROV002', 'PROV003'], 3, 12),
        ({'PROV001': 36, 'PROV002': 5}, ['PROV001', 'PROV002'], 2, 5),
        ({'PROV001': 36}, ['PROV001', 'PROV002', 'PROV001'], 1, 36),                  # PROV002 is new and empty: stay on the full roll
        ({'PROV001': 36, 'PROV002': 36}, ['PROV001', 'PROV002', 'PROV003', 'PROV002'], 2, 36),
        ({'PROV001': 0}, ['PROV001'], 1, 0),                                           # a first roll that is empty is the roll
        ({'PROV001': 0xFFFFFFFF}, ['PROV001'], 1, 0xFFFFFFFF),                         # failure code: stop, never loop
        ({'PROV001': 40000}, ['PROV001', 'PROV002', 'PROV001'], 1, 40000),             # a big but plausible count counts as a full roll
        ({'PROV001': 0x20000}, ['PROV001'], 1, 0x20000)):                              # garbage count: stop
    r = Rig(rolls=rolls)
    r.mode = 10
    r.key()
    left = 0 if (want_files >= 36) else 36 - want_files
    if r.opens != want_opens or r.v(16) != want_roll or r.v(8) != want_files or r.names() != roll_names(want_roll):
        fail('probe', rolls, r.opens, r.v(16), r.v(8), r.names())
    frame = 'full' if want_files >= 36 else '#%02d' % (want_files + 1)
    if utf16(r.c, SLOT0) != '%s %s' % (r.names()[0].split('/')[-1], frame):
        fail('probe text', rolls, utf16(r.c, SLOT0))
r = Rig(rolls={'PROV%03d' % n: 36 for n in range(1, 1000)})                           # the last roll number is the cap
r.mode = 10
r.key()
if len(r.opens) != 999 or r.v(16) != 999 or r.names() != roll_names(999):
    fail('roll cap', len(r.opens), r.v(16), r.names())

# 4. the object is found wherever it sits in the manager, and a stale cached pointer is replaced
for word in (0, 1, 0x20, 0x7F, 0xFF):
    r = Rig(mgr_word=word)
    r.mode = 10
    r.key()
    if r.opens != ['PROV001'] or r.v(0) != OBJ:
        fail('find object at word', word, r.opens)
for cached in (0xC1999990, 0x1234):
    r = Rig(cached=cached)
    r.mode = 10
    r.key()
    if r.opens != ['PROV001'] or r.v(0) != OBJ or r.stray():
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
    r = Rig(rolls=dict(rolls or {'PROV001': count}))
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
        # the counter counts up: the frame about to be shot (37 - frames left); 0 on a full roll (the camera will not shoot); a card with less
        # room than the roll keeps the stock number
        want = 0 if left == 0 else (37 - left if stock >= left else stock)
        if got != want:
            fail('clamp', n, stock, got, 'want', want)
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
r.rolls['PROV001'] = 9
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

# the film-look key (14) only reloads: an empty or part-shot roll swallows it (part-shot says "Roll in use"), a full roll starts the next
# roll of the same film and swallows it too (the film is the scene card's, so the stock FILM SIM never sees the key)
r = enter_scene(0)
if gate(r, 14, 1) != (0, []) or r.opens != ['PROV001'] or r.v(16) != 1:
    fail('film key on an empty roll', r.opens)
for files in (1, 10, 35):
    r = enter_scene(files)
    r.c.set32(V + 12, 0)
    got = gate(r, 14, 1)
    if got != (0, SWALLOWED) or utf16(r.c, SLOT1) != 'Roll in use' or r.opens != ['PROV001'] or r.v(16) != 1:
        fail('film key mid-roll', files, got, r.opens)
    if gate(r, 14, 2) != (0x55, ORIG(14)) or gate(r, 14, 0) != (0x55, ORIG(14)):         # releases are never swallowed
        fail('film key release mid-roll', files)
r = enter_scene(36, rolls={'PROV001': 36})                  # a full roll: AE-L starts roll 2 of the same film and swallows the key
r.c.set32(V + 12, 1)
r.rolls['PROV002'] = 0
r.at_draw.clear()
got = gate(r, 14, 1)
if got != (0, ['open'] + POP) or r.opens[-1] != 'PROV002':
    fail('new roll', got, r.opens)
if r.names() != roll_names(2) or (r.v(16), r.v(8), r.v(12), r.v(4)) != (2, 0, 0, 1) or utf16(r.c, SLOT0) != 'PROV002 #01':
    fail('new roll state', r.names(), r.v(16), r.v(8), r.v(12), utf16(r.c, SLOT0))
if r.at_draw != [(1, 0, 0, 2)]:
    fail('new roll state at the redraw', r.at_draw)
n_opens = len(r.opens)
got = gate(r, 14, 1)                                        # roll 2 is empty now: swallowed, no second new roll
if got != (0, []) or len(r.opens) != n_opens:
    fail('after the new roll', got, r.opens)
r = enter_scene(36, rolls={'PROV001': 36})                  # garbage count: swallowed, nothing else
r.c.set32(V + 8, 0xFFFFFFFF)
if gate(r, 14, 1) != (0, []):
    fail('film key with a garbage count')
r = enter_scene(36, rolls={'PROV001': 36})                  # new roll asked for but the object is gone: swallowed, nothing changes
r.c.set32(V, 0)
r.c.mem.update({MGR + 4 * 5 + k: 0 for k in range(4)})
before = list(r.opens)
got = gate(r, 14, 1)
if got != (0, []) or r.opens != before:
    fail('new roll without an object', got, r.opens)
if r.stray():
    fail('film key read outside the window', r.stray())

# 8b. the scene picker is the film picker: every card is one look, with its own roll folder; a different card is a different film
CARDS = {10: (0, 'PROV'), 12: (1, 'BLCH'), 13: (2, 'NOST'), 14: (3, 'ASTI'), 15: (4, 'VELV'), 16: (5, 'REAL'), 17: (6, 'CCHR'),
         18: (7, 'CNEG'), 19: (8, 'ETRN'), 20: (9, 'ACRO'), 21: (10, 'SEPI'), 22: (None, 'MYST')}
MYST = F.mystery_table()
for card, (look, code) in CARDS.items():
    r = Rig(rolls={code + '001': 36, code + '002': 7})
    r.mode = card
    calls = r.key(10, 1)
    film = F.MYSTERY if look is None else look
    if r.opens != [code + '001', code + '002'] or r.names() != roll_names(2, code) or r.v(24) != film or r.v(16) != 2:
        fail('card', card, r.opens, r.names(), r.v(24), r.v(16))
    if look is None:                                          # the mystery film: the look of its roll 2
        look = MYST[2]
    if calls != ['open', 'open'] + LOOK(look) + POP + [('keycall', 10, 1)] or utf16(r.c, SLOT0) != '%s002 #08' % code:
        fail('card calls / text', card, calls, utf16(r.c, SLOT0))
r = Rig(rolls={'PROV001': 12, 'ACRO001': 3})                 # switching cards: a part-shot roll resumes when its film comes back
r.mode = 10
r.key()
r.mode = 20
calls = r.key(5, 1)
if r.opens != ['PROV001', 'ACRO001'] or r.names() != roll_names(1, 'ACRO') or r.v(8) != 3 or r.v(24) != 9 or calls != ['open'] + LOOK(9) + POP + [('keycall', 5, 1)]:
    fail('changing card', r.opens, r.names(), r.v(8), calls)
r.mode = 10
r.key(5, 1)
if r.opens != ['PROV001', 'ACRO001', 'PROV001'] or r.names() != roll_names(1) or r.v(8) != 12 or r.v(24) != 0:
    fail('back to the first card', r.opens, r.names(), r.v(8))
n_opens = len(r.opens)
if r.key(5, 1) != [('keyhook', 5, 1)] or len(r.opens) != n_opens:
    fail('same card again must do nothing')
r = Rig(rolls={'PROV001': 36})                               # a full roll of the same film again: a new roll of that film only
r.mode = 10
r.key()
r.mode = 15
r.rolls['VELV001'] = 0
r.key(5, 1)
if r.names() != roll_names(1, 'VELV') or r.v(24) != 4:
    fail('roll count restarts for another film', r.names(), r.v(24))
if r.stray():
    fail('card change read outside the window', r.stray())

# 8c. each film remembers its roll: re-entering a film with many full rolls probes from the roll it was on, not from 001
r = Rig(rolls={**{'PROV%03d' % n: 36 for n in range(1, 21)}, 'PROV021': 4})
r.mode = 10
r.key()
if len(r.opens) != 21 or r.v(16) != 21:
    fail('first entry probes every roll', len(r.opens), r.v(16))
r.mode = 2
r.key(6, 1)
r.mode = 20                                                     # another film in between
r.key(6, 1)
del r.opens[:]
r.mode = 10                                                     # back to PROVIA: straight to roll 21
r.key(6, 1)
if r.opens != ['PROV021'] or r.v(16) != 21 or r.names() != roll_names(21) or r.v(8) != 4:
    fail('film remembers its roll', r.opens, r.v(16), r.names())
if r.c.get32(A['tab_last'] + 4 * 9) != 1:                       # ACROS was on roll 1
    fail('roll memory of the other film', r.c.get32(A['tab_last'] + 4 * 9))
r.rolls['PROV021'] = 36                                         # roll 21 filled, then a new roll: the memory moves on
r.c.set32(V + 8, 36)
r.rolls['PROV022'] = 0
gate(r, 14, 1)
if r.v(16) != 22 or r.c.get32(A['tab_last']) != 22:
    fail('new roll updates the memory', r.v(16), r.c.get32(A['tab_last']))
r = Rig(rolls={'PROV001': 36, 'PROV002': 36})                    # a remembered full roll still steps on to the next one with room
r.mode = 10
r.key()
r.mode = 2
r.key(6, 1)
r.rolls['PROV003'] = 7
r.mode = 10
del r.opens[:]
r.key(6, 1)
if r.opens != ['PROV002', 'PROV003'] or r.v(16) != 3:
    fail('remembered full roll steps on', r.opens, r.v(16))

# 8d. the mystery roll (card 22): each roll gets the shuffle table's look for its number (survives power-off: nothing is stored); a new roll with
# AE-L applies the next roll's look; the folders are MYST001 ...
if sorted(set(MYST)) != list(range(11)) or len(MYST) != 32 or any(MYST[i] == MYST[(i + 1) % 32] for i in range(32)):
    fail('mystery table', list(MYST))
for roll in (1, 2, 5, 31, 32, 33):
    rolls = {'MYST%03d' % n: 36 for n in range(1, roll)}
    rolls['MYST%03d' % roll] = 3
    r = Rig(rolls=rolls)
    r.mode = 22
    calls = r.key(10, 1)
    if r.v(24) != F.MYSTERY or r.v(16) != roll or LOOK(MYST[roll & 31])[0] not in calls:
        fail('mystery roll look', roll, r.v(24), r.v(16), calls[:4])
r = Rig(rolls={'MYST001': 36})
r.mode = 22
r.key()
r.rolls['MYST002'] = 0
r.c.set32(V + 8, 36)
r.calls.clear()
got = gate(r, 14, 1)
if r.v(16) != 2 or got[1][:6] != ['open'] + LOOK(MYST[2])[:5] or utf16(r.c, SLOT0) != 'MYST002 #01':
    fail('new mystery roll gets a new look', r.v(16), got, utf16(r.c, SLOT0))
r = Rig(rolls={'PROV001': 36})                                     # a full roll of a normal film: AE-L does not change the look
r.mode = 10
r.key()
r.rolls['PROV002'] = 0
r.c.set32(V + 8, 36)
got = gate(r, 14, 1)
if any(x[0] == 'setui' for x in got[1] if isinstance(x, tuple)):
    fail('a new roll of a normal film must not apply a look', got)
if F.card_strings(['b%d' % k for k in range(11)])[F.CARD_STRING[22]] != 'Mystery':
    fail('mystery card name')


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
    want_calls = [('ratchet',), ('draw', 0), ('arm', 12), ('toast', 12)] + DIAL() if unlocks else DIAL()      # (the redraw brings the stock mode tile back)
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
    for value in (0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 16, 19, 21, 22, 23, 24, 29, 30, 0xFFFFFFFF):
        want = F.MODE_P if (idx == 3 and F.SCENE_MODE <= value < F.SCENE_MODE + F.SCENE_COUNT) else value
        if getval(idx, value) != want:
            fail('filmget', idx, value, getval(idx, value), 'want', want)
for mode in range(0, 40):                                    # every scene card (10..22) enters film mode, nothing else does
    r = Rig()
    r.mode = mode
    r.key()
    if (r.v(4) == 1) != (10 <= mode <= 22):
        fail('film mode for mode', mode, r.v(4))
r = Rig()                                                    # the film code reads the real mode through the raw getter, with the right index
r.mode = 10
r.key()
if not r.asked or set(r.asked) != {3} or r.v(4) != 1:
    fail('film hook must read the raw mode (index 3)', r.asked, r.v(4))

# 10c. the film-themed "roll full": GetStaticString's entry returns our text for "Memory Full" (687) in SCENE, everything else is stock
def strfetch(r, ident, ctx=0x4444):
    c = r.c
    seen = []
    c.stubs[F.STR_BACK] = lambda s: (seen.append((s.r[0], s.r[1], s.r[2])), r3s.append(s.r[3]), 'stop')[1]
    r3s = []
    for i in range(4, 13):
        c.r[i] = 0x3000 + i
    c.r[0], c.r[1], c.r[3] = ctx, ident, 0x7777
    c.run(LAB['filmstr'], lr=0xCAFE0000, ret=0xCAFE0000)
    if r3s and r3s != [0x7777]:
        fail('filmstr changed r3', ident, r3s)
    if not all(c.r[i] == 0x3000 + i for i in range(4, 12)):
        fail('filmstr changed a callee-saved register', ident)
    return c.r[0], seen


r = Rig()                                                    # not in SCENE: always the stock path (r2 = ctx from the replaced `mov r2,r0`)
for ident in (687, 0, 1, 686, 688):
    got, seen = strfetch(r, ident)
    if seen != [(0x4444, ident, 0x4444)]:
        fail('string fetch outside scene', ident, seen)
r = enter_scene(0)                                           # SCENE with frames left: a full CARD keeps the stock "Memory Full"
for files in (0, 1, 35, 0x20000, 0xFFFFFFFF):
    r.c.set32(V + 8, files)
    got, seen = strfetch(r, 687)
    if seen != [(0x4444, 687, 0x4444)]:
        fail('memory full with frames left (or a garbage count) must be stock', files, seen)
for files in (36, 37, 40000):                                # a full roll: our text
    r.c.set32(V + 8, files)
    got, seen = strfetch(r, 687)
    if got != A['text_full'] or seen:
        fail('memory full in scene', files, hex(got), seen)
r.mode = 2                                                   # the dial moved to P, no key yet: stock text already
got, seen = strfetch(r, 687)
if seen != [(0x4444, 687, 0x4444)]:
    fail('memory full after the dial left scene (no key yet)', seen)
r.mode = 10
if utf16(r.c, A['text_full'], 30) != F.TEXT_FULL_STR:
    fail('roll full text', utf16(r.c, A['text_full'], 30))
for ident in (0, 1, 2, 686, 688, 689, 686 + 1000, 0xFFFFFFFF):
    got, seen = strfetch(r, ident)
    if seen != [(0x4444, ident, 0x4444)]:
        fail('other strings in scene', ident, seen)
r.mode = 2
r.key(6, 1)                                                  # left SCENE: back to the stock text
if strfetch(r, 687)[1] != [(0x4444, 687, 0x4444)]:
    fail('memory full after leaving scene')

# 10d. no playback in SCENE: the state-change entry drops requests for state 5 (with a pop-up) and passes every other one on
def state(r, ident, fsm=0x5555):
    c = r.c
    seen = []
    c.stubs[F.STATE_BACK] = lambda s: (seen.append((s.r[0], s.r[1], s.r[13])), argregs.append((s.r[2], s.r[3])), 'stop')[1]
    argregs = []
    r.calls.clear()
    for i in range(2, 13):
        c.r[i] = r.saved[i]
    c.r[0], c.r[1] = fsm, ident
    c.run(LAB['filmstate'], lr=0xCAFE0000, ret=0xCAFE0000, limit=3000000)
    if seen and argregs != [(r.saved[2], r.saved[3])]:
        fail('filmstate changed r2 / r3 (arguments of the state-change function)', ident, argregs)
    ok = all(c.r[i] == r.saved[i] for i in range(4, 11)) if not seen else True
    if not ok or (not seen and c.r[13] != 0x10000000):
        fail('filmstate changed registers / stack', ident)
    return seen, c.r[0], list(r.calls)


r = Rig()                                                     # outside SCENE: always the stock function, whatever the id
for ident in (0, 3, 4, 5, 12, 30):
    seen, ret, calls = state(r, ident)
    if seen != [(0x5555, ident, 0x10000000 - 36)] or calls:
        fail('state outside scene', ident, seen, calls)
r = enter_scene(0)
for ident in (0, 1, 3, 4, 6, 12, 18, 30, 0xFFFFFFFF):
    seen, ret, calls = state(r, ident)
    if seen != [(0x5555, ident, 0x10000000 - 36)] or calls:
        fail('state in scene passes on', ident, seen, calls)
seen, ret, calls = state(r, 5)
if seen or ret != 0 or calls != SWALLOWED or utf16(r.c, SLOT1) != 'No playback':
    fail('playback in scene must be dropped', seen, ret, calls, utf16(r.c, SLOT1))
for ident in (3, 12, 7, 11, 30):                                  # only 5 is dropped: 3 is the review after a shot, it must always pass
    r = enter_scene(0)
    state(r, 12)
    seen, ret, calls = state(r, ident)
    if seen != [(0x5555, ident, 0x10000000 - 36)] or calls:
        fail('state', ident, 'must pass in scene', seen, calls)
r = enter_scene(0)
r.mode = 2
r.key(6, 1)
seen, ret, calls = state(r, 3)
seen2, ret, calls2 = state(r, 5)
if seen != [(0x5555, 3, 0x10000000 - 36)] or calls or seen2 != [(0x5555, 5, 0x10000000 - 36)] or calls2:
    fail('playback states after leaving scene')
r = enter_scene(0)
r.mode = 2
r.key(6, 1)
seen, ret, calls = state(r, 5)
if seen != [(0x5555, 5, 0x10000000 - 36)] or calls:
    fail('playback after leaving scene')

# 10e. the PLAY event (type 0x11) is dropped at the entry of its handler in SCENE; every other event type passes
EV_OBJ, EV_VT, EV_FN = 0xC1500000, 0xC1600000, 0xC1700000


def event(r, etype, fsm=0x5555):
    c = r.c
    c.set32(EV_OBJ, EV_VT)
    c.set32(EV_VT + 8, 0)                                    # halfword adjustment 0
    c.set32(EV_VT + 0xC, EV_FN)
    asked = []
    c.stubs[EV_FN] = lambda s: (asked.append(s.r[0]), s.r.__setitem__(0, etype))
    seen = []
    argregs = []
    c.stubs[F.EVENT_BACK] = lambda s: (seen.append((s.r[0], s.r[1], s.r[13], s.r[14])), argregs.append((s.r[2], s.r[3])), 'stop')[1]
    r.calls.clear()
    for i in range(2, 13):
        c.r[i] = r.saved[i]
    c.r[0], c.r[1] = fsm, EV_OBJ
    c.run(LAB['filmevent'], lr=0xCAFE0000, ret=0xCAFE0000, limit=3000000)
    if not seen and (c.r[13] != 0x10000000 or not all(c.r[i] == r.saved[i] for i in range(4, 11))):
        fail('filmevent changed registers / stack', etype)
    if seen and argregs != [(r.saved[2], r.saved[3])]:
        fail('filmevent changed r2 / r3', etype, argregs)
    if seen and (seen[0][3] != 0xCAFE0000 or c.r[4] != r.saved[4]):
        fail('filmevent changed lr / r4 on the way to the handler', etype, seen)
    return seen, c.r[0], list(r.calls), asked


r = Rig()
for etype in (0, 1, 5, 0x10, 0x11, 0x17, 0x1A, 0x1B, 0x2B):
    seen, ret, calls, asked = event(r, etype)
    if seen != [(0x5555, EV_OBJ, 0x10000000 - 36, 0xCAFE0000)] or calls or asked:
        fail('event outside scene', etype, seen, calls, asked)
r = enter_scene(0)
for etype in (0, 1, 2, 5, 0x10, 0x12, 0x17, 0x1A, 0x1B, 0x2B, 0x41, 0xFFFFFFFF):
    seen, ret, calls, asked = event(r, etype)
    if seen != [(0x5555, EV_OBJ, 0x10000000 - 36, 0xCAFE0000)] or calls or asked != [EV_OBJ]:
        fail('event in scene passes on', etype, seen, calls, asked)
seen, ret, calls, asked = event(r, 0x11)
if seen or ret != 0 or calls != SWALLOWED or utf16(r.c, SLOT1) != 'No playback' or asked != [EV_OBJ]:
    fail('PLAY in scene must be dropped', seen, ret, calls, asked)
r.mode = 2
r.key(6, 1)
seen, ret, calls, asked = event(r, 0x11)
if len(seen) != 1 or calls:
    fail('PLAY after leaving scene')
r = enter_scene(0)                                              # the dial moved to P but no key was pressed yet (film still flagged on):
r.mode = 2                                                      # PLAY and the playback state follow the real mode, so playback works
seen, ret, calls, asked = event(r, 0x11)
if len(seen) != 1 or calls:
    fail('PLAY after the dial left scene (no key yet)', seen, calls)
seen, ret, calls = state(r, 5)
if seen != [(0x5555, 5, 0x10000000 - 36)] or calls:
    fail('playback state after the dial left scene (no key yet)', seen, calls)
for card in (10, 16, 22):                                       # every scene card still drops it
    r.mode = card
    if event(r, 0x11)[0] or state(r, 5)[0]:
        fail('PLAY must be dropped in card', card)

# 10f. one parent folder: the roll folder is "FILMS/<roll>"; entering SCENE makes <root>/FILMS first with the camera's folder creator (the root string
# gets "/FILMS" for that call only and is back at once); nothing else touches the root
r = Rig()
r.mode = 10
r.key()
if r.mkdirs != [(LIST, 'ROOT/FILMS', 0)] or r.roots != ['ROOT'] or cstr(r.c, LIST + 0x40, 48) != 'ROOT':
    fail('parent folder on entering', r.mkdirs, r.roots, cstr(r.c, LIST + 0x40, 48))
if r.names() != roll_names(1):
    fail('nested roll names', r.names())
r.mode = 15                                                   # another film: no second mkdir
r.key(5, 1)
if len(r.mkdirs) != 1:
    fail('another film must not make the parent again', r.mkdirs)
r.mode = 2
r.key(6, 1)
if len(r.mkdirs) != 1 or cstr(r.c, LIST + 0x40, 48) != 'ROOT' or r.names() != STOCK_NAMES:
    fail('leaving: no mkdir, stock names, root as it was', r.mkdirs, r.names())
r.mode = 10                                                   # entering again: the parent is made again (it may have been deleted)
r.key(5, 1)
if len(r.mkdirs) != 2 or r.mkdirs[1][1] != 'ROOT/FILMS' or r.mkdirs[1][2] != 3 or cstr(r.c, LIST + 0x40, 48) != 'ROOT':
    fail('second entry', r.mkdirs)
r = enter_scene(36, rolls={'PROV001': 36})                    # a new roll with AE-L: same state, no mkdir
r.rolls['PROV002'] = 0
n = len(r.mkdirs)
gate(r, 14, 1)
if len(r.mkdirs) != n:
    fail('new roll must not make the parent', r.mkdirs)
r = Rig(obj_chain=False)                                      # no object: nothing happens
r.mode = 10
r.key()
if cstr(r.c, LIST + 0x40, 48) != 'ROOT' or r.mkdirs:
    fail('root changed without an object')
r = Rig()                                                     # a root too long to extend is left alone (and restored as it was)
for k, ch in enumerate(b'X' * 0x2A + b'\0'):
    r.c.mem[LIST + 0x40 + k] = ch
r.mode = 10
r.key()
if cstr(r.c, LIST + 0x40, 48) != 'X' * 0x2A or r.mkdirs:
    fail('long root must stay', cstr(r.c, LIST + 0x40, 48), r.mkdirs)

# 10g. the counter follows the real mode at once: film active but the camera already in P (the mode dial moved, no key yet) -> the stock number
r = enter_scene(10)
r.c.set32(LIST + 0x24, 10)
r.mode = 2
if clamp(r, 500) != 500:
    fail('shots left must be stock as soon as the mode is not a scene card')
r.mode = 10
if clamp(r, 500) != 11:
    fail('shots left in a scene card', clamp(r, 500))
for mode in (1, 3, 8, 9, 23, 30):
    r.mode = mode
    if clamp(r, 77) != 77:
        fail('shots left outside the scene cards', mode)

# 10h. the state object's cached mode (+0xC) is made P in a scene card so the direction keys (macro, flash ...) work; every other value is left alone
for mode in range(0, 40):
    r = Rig()
    r.mode = mode
    r.c.set32(STATE_OBJ + 12, mode)
    r.key(2, 1)
    want = 2 if 10 <= mode <= 22 else mode
    if r.c.get32(STATE_OBJ + 12) != want:
        fail('state object mode cache', mode, r.c.get32(STATE_OBJ + 12), 'want', want)
r = Rig()                                                     # and every later key in the scene card keeps it at P
r.mode = 13
r.c.set32(STATE_OBJ + 12, 13)
for key in (1, 2, 3, 15, 10):
    r.c.set32(STATE_OBJ + 12, 13)
    r.key(key, 1)
    if r.c.get32(STATE_OBJ + 12) != 2:
        fail('state object cache after key', key)

# 10i. the wind-on / roll-full icons in the mode icon spot (the OSD show/hide called with node indices)
def icons(r):
    """the vis calls of one iconfix run"""
    c = r.c
    r.vis.clear()
    for i in range(2, 13):
        c.r[i] = r.saved[i]
    c.run(LAB['iconfix'], lr=0xCAFE0000, ret=0xCAFE0000, limit=3000000)
    if not (all(c.r[i] == r.saved[i] for i in range(4, 11)) and c.r[13] == 0x10000000):
        fail('iconfix changed registers / stack')
    return list(r.vis)


def want_icons(shown, look=0):
    out = []
    for first, last, wind, full, tile in F.ICON_GROUPS:
        child = {'wind': wind, 'full': full, 'tile': tile + look}[shown]
        out += [(n, 0, 0, 0) for n in range(first, last + 1)] + [(child, 1, 0, 0)]
    return out


r = Rig()                                                      # not in SCENE: nothing
r.c.set32(V + 12, 1)
if icons(r):
    fail('iconfix outside scene')
r = Rig()                                                      # the dial just moved to a scene card, the key hook has not run: the tile already
r.mode = 13
if icons(r) != want_icons('tile', 2):
    fail('iconfix before the roll is switched')
r.mode = 2                                                     # left the scene cards: our children are hidden again, once
want = []
for first, last, wind, full, tile in F.ICON_GROUPS:
    want += [(n, 0, 0, 0) for n in range(tile, wind + 1)]
if icons(r) != want or r.c.get32(V + 28) != 0 or icons(r):
    fail('iconfix clean-up', len(r.vis))
r.mode = 10
r.c.set32(V + 28, 1 * 16 + 0 + 1)                              # the roll-full child was shown: it is hidden too on leaving
r.mode = 2
want2 = []
for first, last, wind, full, tile in F.ICON_GROUPS:
    want2 += [(n, 0, 0, 0) for n in range(tile, wind + 1)]    # the roll-full child is one of the tiles: no other stock child is touched
if icons(r) != want2:
    fail('iconfix clean-up of the roll-full child')
for first, last, wind, full, tile in F.ICON_GROUPS:              # the roll-full icon is the spare twelfth tile, never a mode's own child
    if full != tile + 11 or full in (809, 880):
        fail('roll-full child must be the twelfth scene tile', full)
if F.IMG_FULL != F.SCENE_TILES[22] or F.IMG_FULL == 231:
    fail('roll-full image must be the twelfth scene tile image', F.IMG_FULL)
r = enter_scene(5)                                             # frames left, not locked: the look's cartridge tile (look 0 = PROVIA)
if icons(r) != want_icons('tile', 0):
    fail('iconfix with frames left', icons(r)[-3:])
for card, look in ((10, 0), (12, 1), (13, 2), (14, 3), (15, 4), (16, 5), (17, 6), (18, 7), (19, 8), (20, 9), (21, 10)):   # the tile follows the card's look
    r.mode = card
    if icons(r) != want_icons('tile', look):
        fail('iconfix tile for card', card)
r.mode = 22                                                    # the mystery film: every child hidden, no tile shown, the film icon hidden
hidden = [(n, 0, 0, 0) for first, last, wind, full, tile in F.ICON_GROUPS for n in range(first, last + 1)]
if icons(r) != hidden + [(F.FILM_GROUP, 0, 0, 0)]:
    fail('iconfix mystery tile', icons(r)[-3:])
r.mode = 10                                                    # back to a normal film: the tile, and the film icon shown again once
if icons(r) != want_icons('tile', 0) + [(F.FILM_GROUP, 1, 0, 0)] or icons(r) != want_icons('tile', 0):
    fail('iconfix after the mystery film', icons(r)[-3:])
r.mode = 22
icons(r)
r.mode = 2                                                     # leaving SCENE from the mystery film: the film icon back too
got = icons(r)
if got[0] != (F.FILM_GROUP, 1, 0, 0) or len(got) != 1 + 2 * 13:
    fail('clean-up after the mystery film', got[:2], len(got))
r.mode = 10
r.c.set32(V + 24, 0)
r.c.set32(V + 12, 1)                                           # locked: the wind-on child, in both groups
if icons(r) != want_icons('wind'):
    fail('iconfix locked', icons(r)[-3:])
r.c.set32(V + 12, 0)
r.c.set32(V + 8, 36)                                           # full roll, wound: the roll-full child
if icons(r) != want_icons('full'):
    fail('iconfix full')
r.c.set32(V + 12, 1)                                           # locked wins over full (the last shot is not wound yet)
if icons(r) != want_icons('wind'):
    fail('iconfix locked and full')
r.c.set32(V + 12, 0)
r.c.set32(V + 8, 0xFFFFFFFF)                                   # a garbage count: the tile
if icons(r) != want_icons('tile'):
    fail('iconfix garbage count')
r = Rig(rolls={'PROV001': 36})                                 # a full roll entered: the pop-up path ends with the icon
r.mode = 10
r.key()
if r.vis[-len(want_icons('full')):] != want_icons('full'):
    fail('entering a full roll must show the roll-full icon', len(r.vis))
r.c.set32(V + 12, 1)                                           # a shutter press while locked: banner and icon
r.vis.clear()
gate(r, 10, 1)
if r.vis != want_icons('wind'):
    fail('gate swallow must show the wind-on icon', len(r.vis))
r.rolls['PROV002'] = 0                                         # a new roll: the tile again
r.vis.clear()
gate(r, 14, 1)
if r.vis[-len(want_icons('tile')):] != want_icons('tile'):
    fail('a new roll must show the tile', len(r.vis))


# 10i2. the lazy entry (the counter's hook): nothing is drawn again while the wanted state is the one set last
def lazy(r):
    c = r.c
    r.vis.clear()
    for i in range(2, 13):
        c.r[i] = r.saved[i]
    c.run(LAB['iconlazy'], lr=0xCAFE0000, ret=0xCAFE0000, limit=3000000)
    if not (all(c.r[i] == r.saved[i] for i in range(4, 11)) and c.r[13] == 0x10000000):
        fail('iconlazy changed registers / stack')
    return list(r.vis)


r = enter_scene(5)
r.c.set32(V + 28, 0)
if lazy(r) != want_icons('tile') or lazy(r):
    fail('iconlazy: first call draws, the second does not')
r.c.set32(V + 12, 1)                                           # a shot locked the roll
if lazy(r) != want_icons('wind') or lazy(r):
    fail('iconlazy after a lock')
r.c.set32(V + 12, 0)
r.c.set32(V + 28, 0)                                           # a stock redraw reset the spot: forced by the DRAW_ICONS hook, not by the lazy call
if icons(r) != want_icons('tile') or lazy(r):
    fail('iconfix forces, iconlazy then sees nothing new')

# a shot seen by the counter's hook (the file count rises) shows the wind-on icon at once; with no shot nothing is drawn again
r = enter_scene(5)
r.c.set32(V + 28, 0)
r.c.set32(LIST + 0x24, 5)
r.vis.clear()
clamp(r, 36)
tile_calls = list(r.vis)
if tile_calls != want_icons('tile'):
    fail('counter hook draws the tile once', len(tile_calls))
r.vis.clear()
clamp(r, 36)
if r.vis:
    fail('counter hook must not draw again', len(r.vis))
r.c.set32(LIST + 0x24, 6)                                      # the shot
r.vis.clear()
if clamp(r, 36) != 7 or r.vis != want_icons('wind'):
    fail('counter hook after a shot must show the wind-on icon', len(r.vis))

# 10j. the end of the full redraw: `add sp,sp,#0x14`, then iconfix, then on to the stock `pop {sl, fp, pc}`
def draw_end(r):
    c = r.c
    seen = []
    c.stubs[F.DRAW_BACK] = lambda s: (seen.append((s.r[13], s.r[0])), 'stop')[1]
    r.vis.clear()
    for i in range(2, 13):
        c.r[i] = r.saved[i]
    c.r[0] = 0x600D
    c.run(LAB['filmdraw'], lr=0xCAFE0000, ret=0xCAFE0000, limit=3000000)
    if seen != [(0x10000000 + 0x14, 0x600D)] or not all(c.r[i] == r.saved[i] for i in range(4, 12)):
        fail('filmdraw sp / registers / return value', seen)
    return list(r.vis)


r = Rig()
if draw_end(r):
    fail('filmdraw outside scene')
r = enter_scene(5)
if draw_end(r) != want_icons('tile'):
    fail('filmdraw in scene')
r.c.set32(V + 12, 1)
if draw_end(r) != want_icons('wind'):
    fail('filmdraw locked')

# 12. EXIF names (tools/film_exif.py): the Model hook writes "TL500 <look>" into its buffer, hands r3 = the buffer to the writer and keeps
# every other register; Make / Software are static strings
import film_exif as X
XBLOCKS, XLAB = X.blob(b'TL-F65q\0')
for look in list(range(11)) + [11, 0xFFFFFFFF]:
    c = CPU(XBLOCKS)
    c.set32(ui.UI_CACHE + 0x40, look)
    for k in range(len(X.MODEL_PREFIX), X.MODEL_N):              # a dirty name: the hook must pad with NULs (the prefix is static)
        c.mem[XLAB['model'] + k] = 0x41
    seen = []
    c.stubs[X.MODEL_BACK] = lambda s: (seen.append([s.r[i] for i in range(16)]), 'stop')[1]
    for i in range(0, 13):
        c.r[i] = 0x5000 + i
    c.run(XLAB['exifmodel'], lr=0xCAFE0000, ret=0xCAFE0000, limit=100000)
    want = 'TL500 ' + X.NAMES[look if look < 11 else 0]
    got = bytes(c.mem.get(XLAB['model'] + k, 0) for k in range(X.MODEL_N))
    if got != want.encode().ljust(X.MODEL_N, b'\0'):
        fail('exif model text', look, got)
    if len(seen) != 1 or seen[0][3] != XLAB['model'] or seen[0][13] != 0x10000000 or \
            any(seen[0][i] != 0x5000 + i for i in (0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12)):
        fail('exif model registers', look, [hex(x) for x in (seen[0] if seen else [])])
xb = dict(XBLOCKS)[X.CODE_AT]
if xb[:12] != b'FAUXJI FILM\0' or xb[12:28] != b'FAUXJI TL-F65q\0\0':
    fail('exif make / software', xb[:28])


# 13. the wind-on ratchet (tools/film_sound.py): plays like the stock player plays a shutter sound: silent only with the volume Off (or a level the
# mixer refuses); the output value follows the route bytes (flag 0 -> 0, route 4, 5 -> 2, 0..3 -> 1 on output kind 2 else 2, >= 6 -> 0)
import film_sound as SND
SCODE, SLAB = SND.code()


def ratchet(level=2, setok=0, on=1, vol=2, kind=2):
    c = CPU([(SND.CODE_AT, SCODE)])
    c.set32(SND.SND_LEVEL, level)
    played, asked = [], []
    c.stubs[SND.SET_LEVEL] = lambda s: (asked.append(('level', s.r[0])), s.r.__setitem__(0, setok))
    c.stubs[SND.SND_ON] = lambda s: s.r.__setitem__(0, on)
    c.stubs[SND.SND_VOL] = lambda s: s.r.__setitem__(0, vol)
    c.stubs[SND.DEV_GET] = lambda s: s.r.__setitem__(0, 0x77)
    c.stubs[SND.DEV_KIND] = lambda s: (asked.append(('kind', s.r[0])), s.r.__setitem__(0, kind))
    c.stubs[SND.PLAY_BLOCK] = lambda s: played.append((s.r[0], s.r[1], s.r[2], s.r[3], s.get32(s.r[13])))
    for i in range(4, 13):
        c.r[i] = 0x6000 + i
    c.run(SND.RATCHET, lr=0xCAFE0000, ret=0xCAFE0000, limit=10000)
    if c.r[13] != 0x10000000 or any(c.r[i] != 0x6000 + i for i in range(4, 12)):
        fail('ratchet changed registers / stack')
    return played, asked


for args, out in (({}, 1), ({'kind': 1}, 2), ({'vol': 0}, 1), ({'vol': 3, 'kind': 0}, 2), ({'vol': 4}, 2), ({'vol': 5}, 2),
                  ({'on': 0}, 0), ({'on': 0x100}, 0), ({'vol': 6}, 0), ({'level': 1}, 1), ({'level': 3, 'on': 0}, 0),
                  ({'level': 0}, None), ({'setok': 0x80000000}, None)):
    played, asked = ratchet(**args)
    want = [] if out is None else [(SND.BLOCK_AT, out, 0, 0, SND.RATE)]
    if played != want:
        fail('ratchet', args, played)
    if args.get('level', 2) and ('level', args.get('level', 2)) not in asked:
        fail('ratchet must apply the volume level like the player', asked)
blk = SND.block()
if struct.unpack_from('<I', blk)[0] != len(blk) - 4 or len(blk) > 0x4000 or SND.BLOCK_AT % 16:
    fail('ratchet block', len(blk))


# 14. the date stamp (tools/film_stamp.py): Samsung's own blitter, patched, run through `stampwrap`: Samsung's colour outside the film camera,
# orange in it, pixels only where the glyph has bits; `fmt98` writes "YY MM DD" in the film camera for date layouts and leaves the rest alone
import film_stamp as STP
STOCK_ELF = r'extracted\tl500_008264\EX1-DSP-SR-008264.elf'
if os.path.exists(STOCK_ELF):
    sd = STP.patch(open(STOCK_ELF, 'rb').read(), V)
    if STP.patch(sd, V) != sd:
        fail('stamp patch is not idempotent')
    blit = sd[STP.BLIT - B:STP.BLIT_END - B]
    tcode, tlab = STP.code(V)
    STRIDE_PTR = 0xC0921EBC
    for film_on in (0, 1):
        pool = 0xC03CCA34                                         # the blitter's literal: the address of the stride word
        c = CPU([(STP.BLIT, blit), (STP.CODE_AT, tcode), (STP.COLOURS_AT, STP.data()[0]), (pool, sd[pool - B:pool - B + 4])])
        c.set32(V + 4, film_on)
        c.set32(STRIDE_PTR, 32)                                   # image line stride
        glyph, GW, GH = 0xC1A00000, 16, 3
        rows = [0b1000000000000001, 0b0110000000000000, 0]          # pixel 0 and 15; pixels 1 and 2; none
        for r, bits in enumerate(rows):
            c.mem[glyph + 2 * r], c.mem[glyph + 2 * r + 1] = bits >> 8, bits & 255
        YB, UVB = 0xC1B00000, 0xC1C00000
        for k in range(32 * GH):
            c.mem[YB + k], c.mem[UVB + k] = 0x10, 0x80
        c.set32(0x10000000, glyph)                                 # the draw's [sp] = the glyph
        for i in range(4, 12):
            c.r[i] = 0x7000 + i
        c.r[0], c.r[1], c.r[2], c.r[3] = YB, UVB, GW, GH
        c.run(tlab['stampwrap'], lr=0xCAFE0000, ret=0xCAFE0000, limit=200000)
        if c.r[13] != 0x10000000 or any(c.r[i] != 0x7000 + i for i in range(4, 12)):
            fail('stampwrap registers / stack', film_on)
        y_, u_, v_ = STP.ORANGE_YUV if film_on else STP.STOCK_YUV
        want = {(0, 0), (0, 15), (1, 1), (1, 2)}
        for r in range(GH):
            for x in range(GW):
                yv, cv = c.mem[YB + 32 * r + x], c.mem[UVB + 32 * r + x]
                on = (r, x) in want
                wy, wc = (y_, (u_ if x % 2 == 0 else v_)) if on else (0x10, 0x80)
                if (yv, cv) != (wy, wc):
                    fail('stamp pixel', film_on, r, x, hex(yv), hex(cv))
    # fmt98
    for film_on, layout, want_text in ((1, 2, True), (1, 7, True), (1, 0, False), (1, 1, False), (1, 8, False), (0, 2, False)):
        c = CPU([(STP.CODE_AT, tcode), (STP.FMT_AT, STP.data()[1])])
        c.set32(V + 4, film_on)
        c.set32(0x10000000 + 0x118, layout)
        got = []
        c.stubs[STP.SPRINTF] = lambda s: got.append((s.r[0], cstr(s, s.r[1]), s.r[2], s.r[3], s.get32(s.r[13])))
        ends = []
        c.stubs[STP.SWITCH_TAIL] = lambda s: (ends.append(('tail', s.get32(s.r[13] + 0xDC), s.r[2])), 'stop')[1]
        c.stubs[STP.SWITCH_NEXT] = lambda s: (ends.append(('next', s.r[2])), 'stop')[1]
        c.r[4], c.r[5], c.r[6] = 8, 11, 2026                       # day, month, year
        c.run(tlab['fmt98'], lr=0xCAFE0000, ret=0xCAFE0000, limit=10000)
        if want_text:
            if got != [(0x10000000 + 0xCC, '%02d %02d %02d', 26, 11, 8)] or ends != [('tail', 8, 26)]:
                fail('fmt98 film', layout, got, ends)
        elif got or ends != [('next', layout)]:
            fail('fmt98 passes on', film_on, layout, got, ends)
    for film_on in (0, 1):                                        # forcestamp: the stamp call in the film camera even with Imprint Off
        r = Rig()
        r.c.set32(V + 4, film_on)
        CAP = 0xC1D00000
        r.c.set32(CAP + 0x1BC, 5)
        seen = []
        r.c.stubs[F.STAMP_CALL] = lambda s: (seen.append(('call', s.r[0], s.r[1], s.r[2])), 'stop')[1]
        r.c.stubs[F.STAMP_SKIP] = lambda s: (seen.append(('skip',)), 'stop')[1]
        r.c.r[8] = CAP
        r.c.run(LAB['forcestamp'], lr=0xCAFE0000, ret=0xCAFE0000, limit=1000)
        if seen != ([('call', CAP + 0xA8, 5, 2)] if film_on else [('skip',)]):
            fail('forcestamp', film_on, seen)
    if struct.unpack_from('<I', sd, STP.STAMP_BEQ - B)[0] != ui._b(STP.STAMP_BEQ, LAB['forcestamp'], cond=0):
        fail('forcestamp branch not in place')
    for base, w, h in STP.FONTS:                                  # the digits changed only in the large fonts; '.' and ':' never
        g = w // 8 * h
        o, so = sd[base - B:base - B + 12 * g], open(STOCK_ELF, 'rb').read()[base - B:base - B + 12 * g]
        if o[10 * g:] != so[10 * g:] or ((o[:10 * g] != so[:10 * g]) != (h >= STP.SEVEN_MIN_H)):
            fail('stamp font', hex(base))


# 15. the film camera gets P's exposure fixes (tools/film_ae.py): the zoom hand-shake shift is skipped and the flash floor has no zoom shift
# whenever the film camera is on, whatever mode number the exposure engine keeps; with it off, only for P / A / S (0, 2, 3) as before
import film_ae as AE
import fauxji_rot as ROT
ABLK, ALAB = AE.blocks(V)
rot_blobs = [(x, c) for x, c in ROT.build()[0]]
for film_on in (0, 1):
    for mode in (0, 1, 2, 3, 4, 5, 6, 9, 10, 0xFFFF):
        want_skip = bool(film_on) or mode in (0, 2, 3)
        c = CPU(ABLK + [(V, struct.pack('<II', 0, film_on))])
        seen = []
        c.stubs[ui.ZOOM_SKIP] = lambda s: (seen.append('skip'), 'stop')[1]
        c.stubs[ui.ZOOM_BACK] = lambda s: (seen.append('shift'), 'stop')[1]
        c.run(ALAB['zoom'], lr=mode, ret=0xCAFE0000, limit=100)     # lr = the mode number the exposure engine keeps
        if seen != (['skip'] if want_skip else ['shift']):
            fail('zoom shift', film_on, mode, seen)
        # flash floor: plzoom (patched to go through plfilm first) leaves lr = the zoom shift to add (0 = none)
        c = CPU(rot_blobs + ABLK + [(V, struct.pack('<II', 0, film_on))])
        c.set32(ALAB['plzoom'], ui._b(ALAB['plzoom'], ALAB['plfilm']))
        AEI = 0xC1E00000
        c.mem[AEI + 0xA], c.mem[AEI + 0xB] = mode & 255, (mode >> 8) & 255
        c.mem[AEI + 0x12], c.mem[AEI + 0x13] = 16, 0
        got = []
        c.stubs[ROT.PLZ_BACK] = lambda s: (got.append(s.r[14]), 'stop')[1]
        c.r[11] = AEI
        c.run(ALAB['plzoom'], ret=0xCAFE0000, limit=100)
        if got != [0 if want_skip else 16]:
            fail('flash floor zoom shift', film_on, mode, got)


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
    import fauxji
    tab_at = word(out, F.LIVE_POOL)
    ranges = [(b, b + len(x)) for b, x in BLOCKS] + [(tab_at, tab_at + 360)]
    if not (BASE + len(DATA) <= tab_at < BASE + len(DATA) + 4 and tab_at + 360 <= F.FILM_END):
        fail('live table placement', hex(tab_at))
    if out[tab_at - B:tab_at - B + 324] != stock[fauxji.LIVE - B:fauxji.LIVE - B + 324]:
        fail('live table slots 0-8 differ from the patched stock table')
    if struct.unpack_from('<9i', out, tab_at - B + 324) != tuple(fauxji.fixed(fauxji.LOOKS[9])):
        fail('live slot 9 is not the Bleach Bypass matrix')
    if word(out, F.LIVE_KEY_SITE) != F.LIVE_KEY_NEW or word(stock, F.LIVE_KEY_SITE) != F.LIVE_KEY_OLD:
        fail('Bleach Bypass live slot word')
    sites = [p + k for p in list(F.STOCK) + [F.LIVE_POOL, F.LIVE_KEY_SITE, ui.KEY_CALL[0], F.ROLL_SITE, F.DRAW_END, F.STATE_SITE, F.EVENT_SITE, F.GATE_SITE, F.DIAL_SITE, F.GETVAL_SITE, F.STR_SITE] for k in range(4)]
    outside = [hex(i + B) for i in changed if not any(lo <= i + B < hi for lo, hi in ranges) and (i + B) not in sites]
    if outside:
        fail('bytes changed outside the blocks / pointers / hook sites', outside[:8])
    if word(out, F.ROLL_SITE) != ui._b(F.ROLL_SITE, LAB['rollclamp']):
        fail('shots-left hook not in place')
    if word(out, ui.KEY_CALL[0]) != ui._b(ui.KEY_CALL[0], LAB['filmhook'], link=True):
        fail('key hook not in place')
    if word(out, F.GETVAL_SITE) != ui._b(F.GETVAL_SITE, LAB['filmget']):
        fail('SCENE-as-P hook not in place')
    if word(out, F.STR_SITE) != ui._b(F.STR_SITE, LAB['filmstr']):
        fail('roll-full text hook not in place')
    print('real .elf: 6 pointers + 6 hook sites + blocks %s' % ', '.join('%x-%x' % r_ for r_ in ranges))
    xo = X.patch(out, b'TL-F65q\0')                               # EXIF on top: counts, the three sites, the two pool words, nothing else
    if X.patch(xo, b'TL-F65q\0') != xo:
        fail('exif patch is not idempotent')
    for rec, n in ((X.REC_MAKE, 12), (X.REC_MODEL, 24), (X.REC_SOFT, 16)):
        if word(xo, X.TABLE + 0x14 * rec + 8) != n:
            fail('exif count', rec)
    if cs(xo, word(xo, X.MAKE_POOL)) != 'FAUXJI FILM' or cs(xo, word(xo, X.SOFT_POOL)) != 'FAUXJI TL-F65q':
        fail('exif pool strings')
    if word(xo, X.MAKE_SITE) != 0xE59F3588 or word(xo, X.SOFT_SITE) != 0xE59F33D8 or word(xo, X.MODEL_SITE) != ui._b(X.MODEL_SITE, XLAB['exifmodel']):
        fail('exif sites', hex(word(xo, X.MAKE_SITE)), hex(word(xo, X.SOFT_SITE)))
    xr = [(a_, a_ + len(b_)) for a_, b_ in XBLOCKS] + [(X.TABLE, X.TABLE + 0xDC)]
    xs = [p + k for p in (X.MAKE_SITE, X.MODEL_SITE, X.SOFT_SITE, X.MAKE_POOL, X.SOFT_POOL) for k in range(4)]
    stray = [hex(i + B) for i in range(len(out)) if out[i] != xo[i] and not any(lo <= i + B < hi for lo, hi in xr) and i + B not in xs]
    if stray:
        fail('exif changed bytes elsewhere', stray[:8])
    if any(lo < hi_ and lo_ < hi for lo, hi in xr[:2] for lo_, hi_ in ranges):
        fail('exif blocks overlap the film blocks')
else:
    print('(no FAUXJI63 .elf here: skipped the real-image check)')

print('film blocks', [(hex(b), len(x)) for b, x in BLOCKS], 'bad', bad)

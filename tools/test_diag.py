"""Runs the real emitted words of the diagnostic probe (diag_probe.py, DIAG02) in test_sky's ARM interpreter.
From the project root:  python tools/test_diag.py     (prints "bad 0" when every case is right)"""
import sys, struct
sys.path.insert(0, 'tools')
import fauxji_ui as ui
import diag_probe as P
from test_sky import CPU

BASE = ui.diag_base()
CODE, LAB = ui.diag_code()
FK = ui.DIAG_FINDER_KEY
BUF0, BUF1 = ui.STR_BASE, ui.STR_BASE + ui.STR_SLOT
MGR, OBJ, DCFM, LIST = 0xC1000000, 0xC1100000, 0xC1200000, 0xC1300000
bad = 0


def fail(*a):
    global bad
    bad += 1
    print('BAD', *a)


def text(c, buf):
    out = ''
    for i in range(20):
        h = c.get16(buf + 2 * i)
        if h == 0:
            break
        out += chr(h)
    return out


class Rig:
    def __init__(self, mgr=MGR, words=None, obj_chain=True, mgr_is_obj=False, type_=0x64, open_ret=0x1234):
        self.c = CPU([(BASE, CODE)])
        c = self.c
        tmpl = [ui.DIAG_TEXTS[0], ui.DIAG_TEXTS[1]]
        for buf, t in zip((BUF0, BUF1), tmpl):
            for i, ch in enumerate(t):
                c.mem[buf + 2 * i], c.mem[buf + 2 * i + 1] = ord(ch), 0
        c.set32(P.MANAGER_GLOBAL, mgr)
        self.reads = []
        orig = c.get32
        c.get32 = lambda a: (self.reads.append(a), orig(a))[1]
        for k, w in (words or {}).items():
            c.set32(mgr + 4 * k, w)
        if mgr_is_obj:
            c.set32(mgr, P.VPTR)
        if obj_chain:
            c.set32(OBJ, P.VPTR)
            c.set32(OBJ + 0x118, DCFM)
            c.set32(DCFM + 0x10, LIST)
            c.set32(LIST + 0x20, type_)
        self.calls = []
        c.stubs[ui.ARM_NAME] = lambda s: self.calls.append(('arm', s.r[0]))
        c.stubs[ui.TOAST_CODE] = lambda s: self.calls.append(('toast', s.r[0]))
        c.stubs[ui.KEY_CALL[1]] = lambda s: self.calls.append(('stock', s.r[0], s.r[1]))
        c.stubs[P.OPEN] = lambda s: (self.calls.append(('open', s.r[0], s.r[1])), s.r.__setitem__(0, open_ret))
        self.saved = [0x1000 + i for i in range(16)]

    def press(self, key, state, entry=None):
        c = self.c
        self.calls.clear()
        for i in range(2, 13):
            c.r[i] = self.saved[i]
        c.r[0], c.r[1] = key, state
        c.run(BASE if entry is None else entry, lr=0xCAFE0000, ret=0xCAFE0000)
        regs_ok = all(c.r[i] == self.saved[i] for i in range(4, 11)) and c.r[13] == 0x10000000
        if not regs_ok:
            fail('registers / stack changed', key, state)
        return list(self.calls)

    def safe_reads(self):
        """every dereferenced address was inside the RAM window (or the probe's own code / vars / text)"""
        return not self.stray()

    def stray(self):
        stack = lambda a: 0x0FFFF000 <= a < 0x10000000          # the interpreter's stack, not a data read
        return [a for a in self.reads if not (P.RAM_LO <= a < P.RAM_HI) and not stack(a)]


# 1. key text (with the shooting mode) for every key except the finder key
for key in range(16):
    if key == FK:
        continue
    for state in range(10):
        for mode in ((0, 7, 12, 25) if state in (0, 1) else (12,)):
            r = Rig()
            asked = []
            r.c.stubs[P.GET_SYSVAL] = lambda s, m=mode: (asked.append(s.r[0]), s.r.__setitem__(0, m))
            calls = r.press(key, state)
            t = text(r.c, BUF0)
            if (t != 'Key %02d st %d M%02d' % (key, state, mode) or asked != [3]
                    or calls != [('arm', 11), ('toast', 11), ('stock', key, state)]):
                fail('key text', key, state, mode, repr(t), asked, calls)

# 2. finder key release / other states: no pop-up, stock call still happens with the original key and state
for state in (0, 2, 3):
    r = Rig()
    calls = r.press(FK, state)
    if calls != [('stock', FK, state)]:
        fail('finder key non-press', state, calls)

# 3. the state-change log (DIAG06): statelog records every requested state id and hands on with the arguments untouched
RING = ui.DIAG_RING
M32 = 0xFFFFFFFF


def fresh():
    r = Rig()
    for k in (0, 4, 8):
        r.c.set32(RING + k, 0)
    return r


def statechange(r, ident):
    c = r.c
    seen = []
    c.stubs[P.STATE_BACK] = lambda s: (seen.append((s.r[0], s.r[1], s.r[2], s.r[3], s.r[13], s.get32(s.r[13]), s.get32(s.r[13] + 32))), 'stop')[1]
    for i in range(4, 13):
        c.r[i] = r.saved[i]
    c.r[0], c.r[1], c.r[2], c.r[3] = 0xA0, ident, 0xA2, 0xA3
    c.run(LAB['statelog'], lr=0xBEEF0000, ret=0xCAFE0000)
    if len(seen) != 1:
        fail('statelog did not reach the stock function', ident, seen)
        return
    r0, r1, r2, r3, sp, top, savedlr = seen[0]
    if (r0, r1, r2, r3) != (0xA0, ident, 0xA2, 0xA3):
        fail('statelog changed the arguments', ident, seen)
    if sp != 0x10000000 - 36 or top != r.saved[4] or savedlr != 0xBEEF0000:        # the replaced `push {r4-r8,sb,sl,fp,lr}` has run
        fail('statelog stack / replaced push', ident, hex(sp), hex(top), hex(savedlr))
    if not all(c.r[i] == r.saved[i] for i in range(4, 12)):          # r12 (ip) is scratch at a function's entry
        fail('statelog changed callee-saved registers', ident)


r = fresh()
lo = hi = 0
ids = [30, 4, 12, 3, 5, 11, 18, 2, 7, 300, 41, 0, 255, 39]
for ident in ids:
    statechange(r, ident)
    hi = ((hi << 8) | (lo >> 24)) & M32
    lo = ((lo << 8) | (ident & 255)) & M32
    if (r.c.get32(RING), r.c.get32(RING + 4)) != (lo, hi):
        fail('ring after', ident, hex(r.c.get32(RING)), hex(r.c.get32(RING + 4)), 'want', hex(lo), hex(hi))


def shown(r):
    calls = r.press(FK, 1)
    if calls != [('arm', 12), ('toast', 12), ('stock', FK, 1)]:
        fail('log display calls', calls)
    return text(r.c, BUF1)


# the AE-L key shows the newest four ids first ("S:"), the four before on the next press ("T:"), then starts again
r = fresh()
for ident in (30, 4, 12, 3, 5, 11, 18, 2):                  # 2 is the newest
    statechange(r, ident)
if (shown(r), shown(r), shown(r)) != ('S:02181105', 'T:03120430', 'S:02181105'):
    fail('log display', text(r.c, BUF1))
r = fresh()                                                  # an empty log
if shown(r) != 'S:00000000':
    fail('empty log display')
r = fresh()                                                  # fewer than eight entries
statechange(r, 7)
statechange(r, 12)
if shown(r) != 'S:12070000':
    fail('log with two entries', text(r.c, BUF1))

# 7. dial / non-key events (DIAG03): trampoline k shows "Dial L d", then the original handler runs with r0, r1 unchanged
PAYLOAD, VT, DIRFN = 0xC1500000, 0xC1600000, 0xC1700000
for k, letter in enumerate('WCDM'):
    for direction in ((0, 1) if k == 0 else (0, 1, 2) if k == 1 else (0,)):
        r = Rig()
        c = r.c
        c.set32(PAYLOAD, VT)                                   # event / payload object: vtable pointer ...
        c.set32(VT + 8, 0)                                     # ... entry +8 (wheel dial payload): adjustment short 0 ...
        c.set32(VT + 12, DIRFN)                                # ... and its method
        c.set32(VT + 0x10, 0)                                  # ... entry +0x10 (click dial event): the same
        c.set32(VT + 0x14, DIRFN)
        dir_calls = []
        c.stubs[DIRFN] = lambda s, v=direction: (dir_calls.append(s.r[0]), s.r.__setitem__(0, v))
        handler = P.DIAL_SITES[k][1]
        c.stubs[handler] = lambda s: r.calls.append(('handler', s.r[0], s.r[1]))
        arg1 = PAYLOAD if k <= 1 else 0x12345678
        calls = r.press(0xC1400000 + k, arg1, entry=LAB['tramp%d' % k])
        t = text(c, BUF1)
        want = 'Dial %s %d' % (letter, direction)
        if t != want or calls != [('arm', 12), ('toast', 12), ('handler', 0xC1400000 + k, arg1)]:
            fail('dial event', k, direction, repr(t), calls)
        if (k <= 1 and dir_calls != [PAYLOAD]) or (k > 1 and dir_calls):
            fail('direction method calls', k, dir_calls)               # drive / mode dial: the argument is never touched
        if r.stray():
            fail('dial read outside RAM window', k, [hex(a) for a in r.stray()])

print('probe code', len(CODE), 'bytes at', hex(BASE), 'ends', hex(BASE + len(CODE)), 'bad', bad)

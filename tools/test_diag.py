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

    def press(self, key, state):
        c = self.c
        self.calls.clear()
        for i in range(2, 13):
            c.r[i] = self.saved[i]
        c.r[0], c.r[1] = key, state
        c.run(BASE, lr=0xCAFE0000, ret=0xCAFE0000)
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


# 1. key text for every key except the finder key
for key in range(16):
    if key == FK:
        continue
    for state in range(10):
        r = Rig()
        calls = r.press(key, state)
        t = text(r.c, BUF0)
        if t != 'Key %02d st %d' % (key, state) or calls != [('arm', 11), ('toast', 11), ('stock', key, state)]:
            fail('key text', key, state, repr(t), calls)

# 2. finder key release / other states: no pop-up, stock call still happens with the original key and state
for state in (0, 2, 3):
    r = Rig()
    calls = r.press(FK, state)
    if calls != [('stock', FK, state)]:
        fail('finder key non-press', state, calls)

# 3. finder: object at various manager offsets, then open, then search again
for off in (0, 4, 0x20, 0x7C, 0xFC, 0x3FC):
    k = off // 4
    r = Rig(words={k: OBJ})
    calls = r.press(FK, 1)
    t = text(r.c, BUF1)
    want = 'O:%08X %08X' % (OBJ, 0x64)
    if t != want or calls != [('arm', 12), ('toast', 12), ('stock', FK, 1)]:
        fail('find at', hex(off), repr(t), calls)
    calls = r.press(FK, 1)
    t = text(r.c, BUF1)
    if t != 'R:00001234' or calls != [('open', OBJ, 0x64), ('arm', 12), ('toast', 12), ('stock', FK, 1)]:
        fail('open', hex(off), repr(t), calls)
    calls = r.press(FK, 1)
    if text(r.c, BUF1) != want:
        fail('find again', hex(off), text(r.c, BUF1))
    if not r.safe_reads():
        fail('read outside RAM window', [hex(a) for a in r.stray()])

# 4. the manager global itself is the object
r = Rig(mgr=OBJ, mgr_is_obj=True)
r.press(FK, 1)
if text(r.c, BUF1) != 'O:%08X %08X' % (OBJ, 0x64):
    fail('manager is object', text(r.c, BUF1))

# 5. not found / junk: never opens, never reads outside the window
junk = {0: 0x1234, 1: 0xC1000001, 2: 0xC4000000, 3: 0xBFFFFFFC, 4: 0xFFFFFFFF, 5: 0xDEADBEEF, 6: 0}
for kw in (dict(mgr=0), dict(mgr=0x12345678), dict(mgr=0xC1000002), dict(words=junk, obj_chain=False)):
    r = Rig(**kw)
    calls = r.press(FK, 1)
    t = text(r.c, BUF1)
    if t != 'O:00000000 FFFFFFFF' or calls != [('arm', 12), ('toast', 12), ('stock', FK, 1)]:
        fail('not found', kw, repr(t), calls)
    calls = r.press(FK, 1)                         # a second press searches again, it must not call Open
    if any(c[0] == 'open' for c in calls):
        fail('opened without an object', kw)
    if not r.safe_reads():
        fail('read outside RAM window', kw, [hex(a) for a in r.stray()])

# 6. broken chain behind a found object: type shows FFFFFFFF, still armed so Open is reachable
r = Rig(words={3: OBJ}, obj_chain=False)
r.c.set32(OBJ, P.VPTR)
r.c.set32(OBJ + 0x118, 0x1234)                    # invalid DCF manager pointer
r.press(FK, 1)
if text(r.c, BUF1) != 'O:%08X FFFFFFFF' % OBJ:
    fail('broken chain', text(r.c, BUF1))

print('probe code', len(CODE), 'bytes at', hex(BASE), 'ends', hex(BASE + len(CODE)), 'bad', bad)

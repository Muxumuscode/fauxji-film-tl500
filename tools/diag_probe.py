"""DIAG02 probe for the diagnostic build (build_fauxji.py --diag-keys). Runs in the live-view key dispatcher's first call
(fauxji_ui.KEY_CALL: r0 = logical key 0-15, r1 = press state) and does two jobs.

1. Every key event shows "Key kk st s" in the name pop-up (text slot 0, look 11).
2. Key FINDER_KEY (default 0 = AE-L, press only) looks for the live CSFileList object and shows the result (text slot 1, look 12):
     press 1:  "O:oooooooo"  o = address of the CSFileList object (0 = not found)
     press 2:  "T:tttttttt"  t = media type [[[obj+0x118]+0x10]+0x20] (FFFFFFFF = chain not valid)
     press 3:  calls CSFileList::Open(obj, type) 0xC01A5BA4 (the folder rescan; same arguments the list already has) and shows
               "R:rrrrrrrr" = its return value; then press 4 searches again.
   (One short value per press: the pop-up box holds about 13 characters on one line, the earlier two-value line wrapped and was cut off.)
   The object is found by scanning the first 256 words of the manager at *0xC08B439C (and the manager itself) for a pointer whose
   target starts with the CSFileList vtable pointer 0xC074EA7C. A word is only dereferenced if it is 4-aligned and inside
   0xC0000000-0xC4000000, to keep a stray value from faulting.
Registers: r0-r10 and lr are saved; only ip (r12) and the stack are touched besides.  The code is written with the tiny assembler below
and checked in tools/test_diag.py (ARM interpreter) and by disassembly."""
import struct

M = 0xFFFFFFFF
R0, R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, IP, LR, PC = 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 15
AND, SUB, ADD, TST, CMP, ORR, MOV, MVN = 0, 2, 4, 8, 10, 12, 13, 15
EQ, NE, HS, LO, GE, LT, AL = 0x0, 0x1, 0x2, 0x3, 0xA, 0xB, 0xE

VPTR = 0xC074EA7C            # CSFileList vtable pointer (stored by its constructor, literal at 0xC01A664C)
MANAGER_GLOBAL = 0xC08B439C  # read by the instance getter 0xC01A4E00
OPEN = 0xC01A5BA4            # CSFileList::Open(this, mediaType)
RAM_LO, RAM_HI = 0xC0000000, 0xC4000000
FINDER_KEY = 0


def _imm(v):
    for rot in range(16):
        r = ((v << (2 * rot)) | (v >> (32 - 2 * rot))) & M if rot else v
        if r < 256:
            return (rot << 8) | r
    raise ValueError(hex(v))


def dp_i(op, rd, rn, v, cond=AL, s=0):
    return (cond << 28) | (1 << 25) | (op << 21) | (s << 20) | (rn << 16) | (rd << 12) | _imm(v)


def dp_r(op, rd, rn, rm, cond=AL, s=0, shift=0, amt=0):
    return (cond << 28) | (op << 21) | (s << 20) | (rn << 16) | (rd << 12) | (amt << 7) | (shift << 5) | rm


def mov_i(rd, v, cond=AL): return dp_i(MOV, rd, 0, v, cond)
def mov_r(rd, rm, cond=AL): return dp_r(MOV, rd, 0, rm, cond)
def mvn_i(rd, v): return dp_i(MVN, rd, 0, v)
def add_i(rd, rn, v, cond=AL): return dp_i(ADD, rd, rn, v, cond)
def sub_i(rd, rn, v, cond=AL): return dp_i(SUB, rd, rn, v, cond)
def cmp_i(rn, v): return dp_i(CMP, 0, rn, v, s=1)
def cmp_r(rn, rm): return dp_r(CMP, 0, rn, rm, s=1)
def tst_i(rn, v): return dp_i(TST, 0, rn, v, s=1)
def lsr_i(rd, rm, n): return dp_r(MOV, rd, 0, rm, shift=1, amt=n)
def lsl_i(rd, rm, n): return dp_r(MOV, rd, 0, rm, shift=0, amt=n)
def ldr(rd, rn, off): return 0xE5900000 | (rn << 16) | (rd << 12) | off
def str_(rd, rn, off): return 0xE5800000 | (rn << 16) | (rd << 12) | off
def ldr_x(rd, rn, rm): return 0xE7900000 | (rn << 16) | (rd << 12) | rm
def strh(rd, rn, off): return 0xE1C000B0 | (rn << 16) | (rd << 12) | ((off >> 4) << 8) | (off & 15)
def push(mask): return 0xE92D0000 | mask
def pop(mask): return 0xE8BD0000 | mask
MOV_PC_LR = 0xE1A0F00E


def _b(src, dst, cond=AL, link=False):
    return (cond << 28) | ((0xB if link else 0xA) << 24) | (((dst - (src + 8)) >> 2) & 0xFFFFFF)


class Asm:
    """Words, branches to labels or absolute addresses, and `ldr rd,=value` literals pooled after the code."""

    def __init__(self, base):
        self.base, self.items, self.labels = base, [], {}

    def w(self, *ws):
        self.items += [('w', x) for x in ws]

    def label(self, name):
        self.items.append(('label', name))

    def b(self, cond, target, link=False):
        self.items.append(('b', cond, target, link))

    def lit(self, rd, value):
        self.items.append(('lit', rd, value))

    def data(self, name, value=0):
        self.items.append(('data', name, value))

    def build(self):
        addr, lits = self.base, {}
        for it in self.items:                                   # pass 1: addresses
            if it[0] == 'label':
                self.labels[it[1]] = addr
            elif it[0] in ('w', 'b', 'lit'):
                addr += 4
                if it[0] == 'lit':
                    lits.setdefault(it[2], None)
        pool = addr
        for v in lits:
            lits[v] = pool
            pool += 4
        datas = {}
        for it in self.items:
            if it[0] == 'data':
                datas[it[1]] = pool
                self.labels[it[1]] = pool
                pool += 4
        out, addr = [], self.base
        for it in self.items:                                   # pass 2: words
            if it[0] == 'w':
                out.append(it[1]); addr += 4
            elif it[0] == 'b':
                t = self.labels[it[2]] if isinstance(it[2], str) else it[2]
                out.append(_b(addr, t, it[1], it[3])); addr += 4
            elif it[0] == 'lit':
                off = lits[it[2]] - (addr + 8)
                assert 0 <= off < 4096
                out.append(0xE59F0000 | (it[1] << 12) | off); addr += 4
        out += list(lits)
        out += [v for it in self.items if it[0] == 'data' for v in [it[2]]]
        return b''.join(struct.pack('<I', x & M) for x in out)


LDRSH_R0_R5 = 0xE1D500F0                           # ldrsh r0,[r5]
# (site of the `bl handler`, handler) per event class in the live-view state handler 0xC04C1F04, in tramp order:
# wheel dial, click dial, drive / half-shutter dial (shared handler), mode dial (same handler, own site)
DIAL_SITES = ((0xC04C21FC, 0xC04BF860), (0xC04C2228, 0xC04C06E0), (0xC04C22D0, 0xC04BFBF8), (0xC04C2328, 0xC04BFBF8))


GET_SYSVAL = 0xC048F81C                            # GET_SYSVAL(3) = shooting mode (see fauxji_rot.py)


STATE_SITE, STATE_BACK, STATE_STOCK = 0xC0491150, 0xC0491154, 0xE92D4FF0   # state-change function: entry `push {r4-r8,sb,sl,fp,lr}`


def probe(base, buf0, buf1, arm_name, toast, key_call, look0=11, look1=12, finder_key=FINDER_KEY,
          dial_targets=tuple(t for _, t in DIAL_SITES), get_sysval=GET_SYSVAL, ring=0, state_back=STATE_BACK):
    """Machine code of the probe; entry = base. buf0 / buf1 = the two 40-byte text slots (UTF-16)."""
    a = Asm(base)
    # ---- entry: replaces `bl key_call`
    a.w(push(0x47FF))                              # push {r0-r10, lr}
    a.w(mov_r(R4, R0), mov_r(R5, R1))
    a.w(cmp_i(R4, finder_key))
    a.b(NE, 'keytxt')
    a.w(cmp_i(R5, 1))
    a.b(EQ, 'find')
    a.b(AL, 'exit')                                # finder key, not a press: leave the result on screen
    # ---- "Key kk st s"
    a.label('keytxt')
    a.w(mov_i(R0, 3))                              # shooting mode: GET_SYSVAL(3) (10 and up = scene modes; the menu unlock reads it too)
    a.b(AL, get_sysval, link=True)
    a.w(mov_r(R6, R0), mov_r(R0, R4), mov_r(R1, R5))
    a.lit(R2, buf0)
    a.w(mov_i(R3, 0x30))
    a.label('tens')
    a.w(cmp_i(R0, 10), sub_i(R0, R0, 10, GE), add_i(R3, R3, 1, GE))
    a.b(GE, 'tens')
    a.w(strh(R3, R2, 8), add_i(R0, R0, 0x30), strh(R0, R2, 10), add_i(R1, R1, 0x30), strh(R1, R2, 20))
    a.w(mov_i(R3, 0x30))
    a.label('mtens')                               # the mode number as two digits at the end of the text ("Key 06 st 1 M12")
    a.w(cmp_i(R6, 10), sub_i(R6, R6, 10, GE), add_i(R3, R3, 1, GE))
    a.b(GE, 'mtens')
    a.w(strh(R3, R2, 26), add_i(R6, R6, 0x30), strh(R6, R2, 28))
    a.w(mov_i(R8, look0))
    a.label('show')                                # r8 = look: name flag + 8 s timer, then draw
    a.w(mov_r(R0, R8))
    a.b(AL, arm_name, link=True)
    a.w(mov_r(R0, R8))
    a.b(AL, toast, link=True)
    a.label('exit')
    a.w(pop(0x47FF))
    a.b(AL, key_call)
    # ---- finder key (AE-L) press: show the state-change log (DIAG06). The ring holds the last 8 state ids the camera was asked to go to
    # (one byte each, newest in the low byte of word 0, then word 1); press 1 shows the newest four as "S:" + four 2-digit ids (newest
    # first), press 2 the four before as "T:", then it starts again.
    a.label('find')
    a.lit(R7, ring)
    a.w(ldr(R2, R7, 8), cmp_i(R2, 0))
    a.b(NE, 'log2')
    a.w(ldr(R9, R7, 0), mov_i(R2, 1), str_(R2, R7, 8), mov_i(R6, ord('S')))
    a.b(AL, 'logfmt')
    a.label('log2')
    a.w(ldr(R9, R7, 4), mov_i(R2, 0), str_(R2, R7, 8), mov_i(R6, ord('T')))
    a.label('logfmt')
    a.lit(R1, buf1)
    a.w(strh(R6, R1, 0), mov_i(R0, ord(':')), strh(R0, R1, 2), add_i(R1, R1, 4), mov_i(R8, 4))
    a.label('idl')
    a.w(lsl_i(R2, R9, 24), lsr_i(R2, R2, 24), lsr_i(R9, R9, 8), mov_i(R3, 0x30))
    a.label('idt')
    a.w(cmp_i(R2, 10), sub_i(R2, R2, 10, GE), add_i(R3, R3, 1, GE))
    a.b(GE, 'idt')
    a.w(strh(R3, R1, 0), add_i(R2, R2, 0x30), strh(R2, R1, 2), add_i(R1, R1, 4), sub_i(R8, R8, 1), cmp_i(R8, 0))
    a.b(NE, 'idl')
    a.w(mov_i(R0, 0), strh(R0, R1, 0), mov_i(R8, look1))
    a.b(AL, 'show')
    # ---- the state-change log hook: the entry of the camera's state-change function 0xC0491150(fsm, id, ...) is replaced by a branch
    # here; r1 = the requested state id. Pushes the replaced instruction and goes on at the second instruction.
    a.label('statelog')
    a.w(push(0x400F))                                        # push {r0-r3, lr}
    a.lit(R2, ring)
    a.w(ldr(R3, R2, 0), ldr(IP, R2, 4))
    a.w(lsl_i(IP, IP, 8), dp_r(ORR, IP, IP, R3, shift=1, amt=24))        # hi = hi << 8 | lo >> 24
    a.w(lsl_i(R3, R3, 8), lsl_i(R0, R1, 24), lsr_i(R0, R0, 24), dp_r(ORR, R3, R3, R0))   # lo = lo << 8 | (id & 255)
    a.w(str_(R3, R2, 0), str_(IP, R2, 4))
    a.w(pop(0x400F))
    a.w(0xE92D4FF0)                                          # the replaced instruction: push {r4-r8, sb, sl, fp, lr}
    a.b(AL, state_back)
    # ---- DIAG03: dial / non-key events. The live-view state handler 0xC04C1F04 tells event classes apart by type name and calls one
    # handler per class; each `bl handler` is replaced by `bl tramp_k` (r2 = the original handler, r3 = k), which shows
    # "Dial L d" (L = W wheel dial, C click dial, D drive / half-shutter dial, M mode dial; d = the wheel's direction flag, 0 for the
    # other classes) in text slot 1 and then jumps to the original handler with r0, r1 unchanged.
    for k, orig in enumerate(dial_targets):
        a.label('tramp%d' % k)
        a.lit(R2, orig)
        a.w(mov_i(R3, k))
        a.b(AL, 'dialc')
    a.label('dialc')
    a.w(push(0x47FF))                              # push {r0-r10, lr}: r2 = handler and r3 = k come back after the pop
    a.w(mov_r(R8, R3), mov_r(R4, R1))
    a.w(mov_i(R6, ord('W')), cmp_i(R8, 1), mov_i(R6, ord('C'), EQ), cmp_i(R8, 2), mov_i(R6, ord('D'), EQ),
        cmp_i(R8, 3), mov_i(R6, ord('M'), EQ))
    a.w(mov_i(R7, 0x30))                           # direction digit, 0 unless the wheel says otherwise
    a.w(cmp_i(R8, 0))
    a.b(EQ, 'wheel')
    a.w(cmp_i(R8, 1))
    a.b(NE, 'dtext')
    # click dial (the front dial): the event's method +0x10 returns 1 / 0 for the two directions and 2 for a press of the dial
    a.w(ldr(R5, R4, 0), add_i(R5, R5, 0x10), ldr(IP, R5, 4), LDRSH_R0_R5, dp_r(ADD, R0, R4, R0), mov_r(LR, PC), mov_r(PC, IP))
    a.w(add_i(R7, R0, 0x30))
    a.b(AL, 'dtext')
    a.label('wheel')
    a.w(ldr(R5, R4, 0), add_i(R5, R5, 8), ldr(IP, R5, 4), LDRSH_R0_R5, dp_r(ADD, R0, R4, R0), mov_r(LR, PC), mov_r(PC, IP))
    a.w(tst_i(R0, 1), mov_i(R7, 0x31, NE))         # the payload's method +8 returns the direction (the stock handler adds or subtracts one)
    a.label('dtext')
    a.lit(R1, buf1)
    for off, ch in enumerate('Dial '):
        a.w(mov_i(R0, ord(ch)), strh(R0, R1, 2 * off))
    a.w(strh(R6, R1, 10), mov_i(R0, ord(' ')), strh(R0, R1, 12), strh(R7, R1, 14), mov_i(R0, 0), strh(R0, R1, 16))
    a.w(mov_i(R8, look1))
    a.w(mov_r(R0, R8))
    a.b(AL, arm_name, link=True)
    a.w(mov_r(R0, R8))
    a.b(AL, toast, link=True)
    a.w(pop(0x47FF), mov_r(PC, R2))                # restore r0-r10 and lr, jump to the original handler
    a.data('VARS_OBJ', 0)
    a.data('VARS_TYPE', 0)
    a.data('VARS_ARMED', 0)
    return a


def build(base, **kw):
    """(code bytes, labels)."""
    a = probe(base, **kw)
    return a.build(), a.labels

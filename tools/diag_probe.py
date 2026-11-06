"""DIAG02 probe for the diagnostic build (build_fauxji.py --diag-keys). Runs in the live-view key dispatcher's first call
(fauxji_ui.KEY_CALL: r0 = logical key 0-15, r1 = press state) and does two jobs.

1. Every key event shows "Key kk st s" in the name pop-up (text slot 0, look 11).
2. Key FINDER_KEY (default 0 = AE-L, press only) looks for the live CSFileList object and shows the result (text slot 1, look 12):
     press 1:  "O:oooooooo tttttttt"  o = address of the CSFileList object (0 = not found), t = media type
               [[[obj+0x118]+0x10]+0x20] (FFFFFFFF = chain not valid)
     press 2:  calls CSFileList::Open(obj, type) 0xC01A5BA4 (the folder rescan; same arguments the list already has) and shows
               "R:rrrrrrrr" = its return value; then press 3 searches again.
   The object is found by scanning the first 256 words of the manager at *0xC08B439C (and the manager itself) for a pointer whose
   target starts with the CSFileList vtable pointer 0xC074EA7C. A word is only dereferenced if it is 4-aligned and inside
   0xC0000000-0xC4000000, to keep a stray value from faulting.
Registers: r0-r10 and lr are saved; only ip (r12) and the stack are touched besides.  The code is written with the tiny assembler below
and checked in tools/test_diag.py (ARM interpreter) and by disassembly."""
import struct

M = 0xFFFFFFFF
R0, R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, IP, LR, PC = 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 15
AND, SUB, ADD, TST, CMP, MOV, MVN = 0, 2, 4, 8, 10, 13, 15
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


def probe(base, buf0, buf1, arm_name, toast, key_call, look0=11, look1=12, finder_key=FINDER_KEY):
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
    a.lit(R2, buf0)
    a.w(mov_i(R3, 0x30))
    a.label('tens')
    a.w(cmp_i(R0, 10), sub_i(R0, R0, 10, GE), add_i(R3, R3, 1, GE))
    a.b(GE, 'tens')
    a.w(strh(R3, R2, 8), add_i(R0, R0, 0x30), strh(R0, R2, 10), add_i(R1, R1, 0x30), strh(R1, R2, 20))
    a.w(mov_i(R8, look0))
    a.label('show')                                # r8 = look: name flag + 8 s timer, then draw
    a.w(mov_r(R0, R8))
    a.b(AL, arm_name, link=True)
    a.w(mov_r(R0, R8))
    a.b(AL, toast, link=True)
    a.label('exit')
    a.w(pop(0x47FF))
    a.b(AL, key_call)
    # ---- finder key press
    a.label('find')
    a.lit(R7, None)                                # r7 = &vars (patched below)
    a.w(ldr(R2, R7, 8))                            # armed?
    a.w(cmp_i(R2, 0))
    a.b(NE, 'openit')
    a.lit(R9, MANAGER_GLOBAL)
    a.w(ldr(R9, R9, 0))                            # manager object
    a.w(mov_i(R6, 0))                              # found object
    a.w(mov_r(R0, R9))
    a.b(AL, 'valid', link=True)
    a.w(cmp_i(IP, 0))
    a.b(EQ, 'fdone')
    a.lit(R2, VPTR)
    a.w(ldr(R3, R9, 0), cmp_r(R3, R2), mov_r(R6, R9, EQ))      # the global may be the object itself
    a.b(EQ, 'fdone')
    a.w(mov_i(R8, 0))
    a.label('scan')
    a.w(ldr_x(R0, R9, R8), mov_r(R10, R0))
    a.b(AL, 'valid', link=True)
    a.w(cmp_i(IP, 0))
    a.b(EQ, 'next')
    a.lit(R2, VPTR)
    a.w(ldr(R3, R10, 0), cmp_r(R3, R2), mov_r(R6, R10, EQ))
    a.b(EQ, 'fdone')
    a.label('next')
    a.lit(R3, 0x400)
    a.w(add_i(R8, R8, 4), cmp_r(R8, R3))
    a.b(LT, 'scan')
    a.label('fdone')
    a.w(str_(R6, R7, 0))                           # vars[0] = object
    a.w(mvn_i(R9, 0))                              # type: unknown
    a.w(cmp_i(R6, 0))
    a.b(EQ, 'showf')
    a.w(ldr(R0, R6, 0x118))                        # DCF manager
    a.b(AL, 'valid', link=True)
    a.w(cmp_i(IP, 0))
    a.b(EQ, 'showf')
    a.w(ldr(R0, R0, 0x10))                         # DCF list
    a.b(AL, 'valid', link=True)
    a.w(cmp_i(IP, 0))
    a.b(EQ, 'showf')
    a.w(ldr(R9, R0, 0x20))                         # media type
    a.label('showf')
    a.w(str_(R9, R7, 4))                           # vars[1] = type
    a.w(cmp_i(R6, 0), mov_i(R2, 1, NE), mov_i(R2, 0, EQ), str_(R2, R7, 8))   # arm only when an object was found
    a.lit(R1, buf1)
    a.w(mov_i(R0, ord('O')), strh(R0, R1, 0), mov_i(R0, ord(':')), strh(R0, R1, 2), add_i(R1, R1, 4))
    a.w(mov_r(R0, R6))
    a.b(AL, 'hex8', link=True)
    a.w(mov_i(R0, ord(' ')), strh(R0, R1, 0), add_i(R1, R1, 2))
    a.w(mov_r(R0, R9))
    a.b(AL, 'hex8', link=True)
    a.w(mov_i(R0, 0), strh(R0, R1, 0))             # NUL in the 20th halfword = end of the 40-byte slot
    a.w(mov_i(R8, look1))
    a.b(AL, 'show')
    # ---- second press: rescan
    a.label('openit')
    a.w(mov_i(R2, 0), str_(R2, R7, 8))             # disarm
    a.w(ldr(R0, R7, 0), ldr(R1, R7, 4))            # object, media type
    a.b(AL, OPEN, link=True)
    a.w(mov_r(R9, R0))
    a.lit(R1, buf1)
    a.w(mov_i(R0, ord('R')), strh(R0, R1, 0), mov_i(R0, ord(':')), strh(R0, R1, 2), add_i(R1, R1, 4))
    a.w(mov_r(R0, R9))
    a.b(AL, 'hex8', link=True)
    a.w(mov_i(R0, 0), strh(R0, R1, 0))
    a.w(mov_i(R8, look1))
    a.b(AL, 'show')
    # ---- ip = 1 if r0 is 4-aligned and inside the RAM window (r0 kept)
    a.label('valid')
    a.w(mov_i(IP, 0))
    a.lit(R1, RAM_LO)
    a.w(cmp_r(R0, R1))
    a.b(LO, 'vret')
    a.lit(R1, RAM_HI)
    a.w(cmp_r(R0, R1))
    a.b(HS, 'vret')
    a.w(tst_i(R0, 3))
    a.b(NE, 'vret')
    a.w(mov_i(IP, 1))
    a.label('vret')
    a.w(MOV_PC_LR)
    # ---- hex8: write r0 as 8 UTF-16 hex digits at [r1], r1 advances; clobbers r0, r2, r3
    a.label('hex8')
    a.w(mov_i(R2, 8))
    a.label('hx')
    a.w(lsr_i(R3, R0, 28), cmp_i(R3, 10), add_i(R3, R3, 0x30, LO), add_i(R3, R3, 0x37, HS),
        strh(R3, R1, 0), add_i(R1, R1, 2), lsl_i(R0, R0, 4), sub_i(R2, R2, 1), cmp_i(R2, 0))
    a.b(NE, 'hx')
    a.w(MOV_PC_LR)
    a.data('VARS_OBJ', 0)
    a.data('VARS_TYPE', 0)
    a.data('VARS_ARMED', 0)
    return a


def build(base, **kw):
    """(code bytes, labels). The `ldr r7,=&vars` literal needs the address of the data words that follow the literal pool, and
    the pool size does not depend on it, so one dry run finds the address."""
    a = probe(base, **kw)
    slot = next(k for k, it in enumerate(a.items) if it[0] == 'lit' and it[2] is None)
    a.items[slot] = ('lit', R7, 0)
    a.build()
    vars_addr = a.labels['VARS_OBJ']
    a.items[slot] = ('lit', R7, vars_addr)
    code = a.build()
    assert a.labels['VARS_OBJ'] == vars_addr
    return code, a.labels

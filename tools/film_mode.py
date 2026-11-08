"""FILM CAMERA mode, stage 1 (build_fauxji.py --film, label TL-F64a): the SCENE dial position saves its photos into their own folder.

What it does
  * Every key event goes through `filmhook` first (it replaces the key dispatcher's first call, 0xC04C1938, and hands on to the
    stock key hook). It reads the shooting mode, GET_SYSVAL(3): P 2, A 3, S 4, M 5, SCENE 10 (measured on the camera).
  * When the mode changes between SCENE and anything else, it switches the camera's "DCIM" folder name to "FILM" (or back) and makes
    the camera rescan its file list: CSFileList::Open(obj, type) 0xC01A5BA4, which returns the number of files it found (the owner's
    test: 27 returned with 27 files on the card, playback fine afterwards).
  * The name is switched by pointing the six code pointers that carry it at RAM buffers (the camera builds every photo path from
    root + "DCIM" + "NNNPHOTO" + "SAM_nnnn.JPG"; the folder creator uses "%s/DCIM" formats). Normal playback scans /DCIM, so photos in
    /FILM are never listed there. Outside SCENE the buffers hold the stock strings, so every other mode behaves as before.
  * A pop-up shows "Film nn left" (36 minus the files in /FILM) when SCENE is entered and "Film off" when it is left. It appears on the
    next key press after the dial moves (the mode dial itself raises no key event); the stock key hook is skipped for that one key
    because it would hide the pop-up again at once.
Stage 2a: the shots-left number is capped at 36 minus the files in the roll (the camera then says "Memory Full" and will not shoot).
Stage 2b: wind-on lock. A rising file count (read in the shots-left hook) marks a photo as taken; while locked the shutter keys are swallowed
(pop-up "Wind on >") until the front dial (click dial) is turned right (`Dial C 1`), which shows "Wound".
Not yet: roll folders, the review lock, the canister screens, the film picker, a film-themed "roll full" message.
If the camera's file list object cannot be found, or its chain is not valid, nothing is changed (the hook retries on the next key).
The code sits in the dead factory region after fauxji_rot's `gate3` (the same region the diagnostic probe uses; they are never
built together). Tests: tools/test_film.py.
"""
import struct

import diag_probe as P
import fauxji_ui as ui
from diag_probe import (Asm, R0, R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, IP, LR, PC, EQ, NE, GE, LT, HS, LO, AL, ADD, SUB, MOV,
                        mov_i, mov_r, add_i, sub_i, cmp_i, cmp_r, tst_i, ldr, str_, ldr_x, strh, push, pop, dp_r, MOV_PC_LR)

HI = 0x8
B = ui.B
SCENE_MODE = 10
FRAMES = 36
GET_SYSVAL = P.GET_SYSVAL
OPEN, VPTR, MANAGER_GLOBAL = P.OPEN, P.VPTR, P.MANAGER_GLOBAL
LOOK_ON = 11                                  # name pop-up look 11 = tilt text slot 0 (served by STRWRAP), overwritten at run time
SLOT0 = ui.STR_BASE
SLOT1 = ui.STR_BASE + ui.STR_SLOT                 # look 12 = tilt text slot 1
LOOK_MSG = 12
GATE_SITE, GATE_STOCK = 0xC04C1944, 0xC04BFF98   # `bl` of the dispatcher's "is this key handled" call (r0 = state obj, r1 = key)
DIAL_SITE, DIAL_STOCK = 0xC04C2228, 0xC04C06E0   # `bl` of the click dial (front dial) event handler (r0 = state obj, r1 = event)
ROLL_SITE, ROLL_BACK, ROLL_STOCK = 0xC047B6B8, 0xC047B6BC, 0xE28DD058   # end of getRemainPhotoNum: `add sp,sp,#0x58` (r0 = shots left)

# the six code pointers that carry the folder name: (pool word address, stock string pointer, which buffer)
NAME_POOLS = (0xC01AEC58, 0xC01B1210, 0xC01B181C)          # "DCIM" in the photo path builder, folder creator and folder scan (ldr lr/ip)
NAME_POOL_DCFDIR = 0xC01B3664                               # CSDCFDir's own "DCIM" (stock string 0xC07500AC)
FMT1_POOL, FMT2_POOL = 0xC01B10FC, 0xC01B1104               # "%s/DCIM" and "%s/DCIM/100PHOTO" (default folders created by the scan)
STOCK = {0xC01AEC58: 0xC074FF08, 0xC01B1210: 0xC074FF08, 0xC01B181C: 0xC074FF08, 0xC01B3664: 0xC07500AC,
         0xC01B10FC: 0xC074FF60, 0xC01B1104: 0xC074FF74}

# layout of the data in front of the code (fixed addresses so the pointer patches do not depend on the code size)
BUF = 0                      # 40 bytes: name (8) | fmt1 (8) | fmt2 (24)  -- what the six pointers point at
VARS = 0x28                  # 16 bytes: [0] CSFileList object (cache), [4] film active (0/1), [8] files seen in the roll, [12] locked (0/1)
TAB_DCIM, TAB_FILM = 0x38, 0x60
TEXT_ON, TEXT_OFF = 0x88, 0xA4
TEXT_WIND, TEXT_WOUND = 0xB8, 0xCC             # 'Wind on >' (20 bytes), 'Wound' (12 bytes)
CODE_AT = 0xDC


def _table(name):
    b = name.encode() + b'\0'
    n = b.ljust(8, b'\0')
    f1 = ('%%s/%s' % name).encode().ljust(8, b'\0')
    f2 = ('%%s/%s/100PHOTO' % name).encode().ljust(24, b'\0')
    assert len(n) == 8 and len(f1) == 8 and len(f2) == 24
    return n + f1 + f2


def _utf16(text, size):
    raw = text.encode('utf-16-le') + b'\0\0'
    assert len(raw) <= size
    return raw.ljust(size, b'\0')


def str_x(rd, rn, rm):
    return 0xE7800000 | (rn << 16) | (rd << 12) | rm


def str_c(rd, rn, off, cond):
    return (cond << 28) | 0x05800000 | (rn << 16) | (rd << 12) | off


def cmp_ic(rn, v, cond):
    return P.dp_i(P.CMP, 0, rn, v, cond=cond, s=1)


def base():
    return ui.diag_base()


def addrs(b=None):
    b = base() if b is None else b
    return dict(buf=b + BUF, vars=b + VARS, tab_dcim=b + TAB_DCIM, tab_film=b + TAB_FILM, text_on=b + TEXT_ON, text_off=b + TEXT_OFF,
                text_wind=b + TEXT_WIND, text_wound=b + TEXT_WOUND, code=b + CODE_AT)


def base_r4():
    """First free word of fauxji_rot's R4 region (dead factory code, `waitEXStrobeSignal`) after its own blob, 16-byte aligned."""
    import fauxji_rot
    blobs, _ = fauxji_rot.build()
    end = max(x + len(c) for x, c in blobs if fauxji_rot.R4 <= x < fauxji_rot.R4_END)
    return (end + 15) & ~15


def helpers(b4=None, b=None):
    """Shared routines (copy, valid, findobj, rollclamp) in the R4 region: (bytes, labels)."""
    A = addrs(b)
    a = Asm(base_r4() if b4 is None else b4)
    # ---- copy r1 bytes (multiple of 4) from [r2] to [r3]; clobbers r0, ip
    a.label('copy')
    a.w(mov_i(IP, 0))
    a.label('cl')
    a.w(ldr_x(R0, R2, IP), str_x(R0, R3, IP), add_i(IP, IP, 4), cmp_r(IP, R1))
    a.b(LT, 'cl')
    a.w(MOV_PC_LR)
    # ---- ip = 1 if r0 is 4-aligned and inside the RAM window (r0 kept; clobbers r1)
    a.label('valid')
    a.w(mov_i(IP, 0))
    a.lit(R1, P.RAM_LO)
    a.w(cmp_r(R0, R1))
    a.b(LO, 'vret')
    a.lit(R1, P.RAM_HI)
    a.w(cmp_r(R0, R1))
    a.b(HS, 'vret')
    a.w(tst_i(R0, 3))
    a.b(NE, 'vret')
    a.w(mov_i(IP, 1))
    a.label('vret')
    a.w(MOV_PC_LR)
    # ---- shots left (stage 2a): replaces `add sp,sp,#0x58` at the end of the camera's getRemainPhotoNum (r0 = shots left, the value the
    # shooting screen shows). In SCENE it becomes min(shots left, 36 - files in the roll), the file count being the DCF list's running
    # total [list+0x24] (the same number CSFileList::Open returned). Outside SCENE, or if any pointer on the way is not valid, r0 is
    # untouched. lr, r1-r3 and ip are free here (the epilogue pops the saved registers next).
    a.label('rollclamp')
    a.lit(R2, A['vars'])
    a.w(ldr(R1, R2, 4), cmp_i(R1, 0))
    a.b(EQ, 'cdone')
    a.w(mov_r(R3, R0))                                       # r3 = stock shots left
    a.w(ldr(R0, R2, 0))                                      # CSFileList object
    a.b(AL, 'valid', link=True)
    a.w(cmp_i(IP, 0))
    a.b(EQ, 'crest')
    a.w(ldr(R0, R0, 0x118))                                  # DCF manager
    a.b(AL, 'valid', link=True)
    a.w(cmp_i(IP, 0))
    a.b(EQ, 'crest')
    a.w(ldr(R0, R0, 0x10))                                   # DCF list
    a.b(AL, 'valid', link=True)
    a.w(cmp_i(IP, 0))
    a.b(EQ, 'crest')
    a.w(ldr(R1, R0, 0x24))                                   # files in the roll
    a.w(ldr(R0, R2, 8), cmp_r(R1, R0))                       # a rising count = a photo was just saved = wind on before the next one
    a.w(mov_i(R0, 1, HI), str_c(R0, R2, 12, HI), str_(R1, R2, 8))
    a.w(cmp_i(R1, FRAMES), mov_i(R1, FRAMES, HI))
    a.w(mov_i(R2, FRAMES), dp_r(SUB, R1, R2, R1))            # r1 = frames left
    a.w(cmp_r(R3, R1), mov_r(R3, R1, HI))                    # shots left = min(stock, frames left)
    a.label('crest')
    a.w(mov_r(R0, R3))
    a.label('cdone')
    a.w(add_i(13, 13, 0x58))                                 # the replaced instruction: add sp,sp,#0x58
    a.b(AL, ROLL_BACK)
    # ---- r4 = the CSFileList object (cached in vars[0], checked by its vtable pointer), else found by scanning the manager at
    # *0xC08B439C like the diagnostic's finder; r6, r7 kept
    a.label('findobj')
    a.w(push(0x4000))                                        # push {lr}
    a.w(ldr(R4, R7, 0), cmp_i(R4, 0))
    a.b(EQ, 'fscan')
    a.w(mov_r(R0, R4))
    a.b(AL, 'valid', link=True)
    a.w(cmp_i(IP, 0))
    a.b(EQ, 'fscan')
    a.lit(R2, VPTR)
    a.w(ldr(R3, R4, 0), cmp_r(R3, R2))
    a.b(EQ, 'fret')
    a.label('fscan')
    a.w(mov_i(R4, 0))
    a.lit(R9, MANAGER_GLOBAL)
    a.w(ldr(R9, R9, 0), mov_r(R0, R9))
    a.b(AL, 'valid', link=True)
    a.w(cmp_i(IP, 0))
    a.b(EQ, 'fstore')
    a.lit(R2, VPTR)
    a.w(ldr(R3, R9, 0), cmp_r(R3, R2), mov_r(R4, R9, EQ))
    a.b(EQ, 'fstore')
    a.w(mov_i(R8, 0))
    a.label('sc')
    a.w(ldr_x(R0, R9, R8), mov_r(R10, R0))
    a.b(AL, 'valid', link=True)
    a.w(cmp_i(IP, 0))
    a.b(EQ, 'nx')
    a.lit(R2, VPTR)
    a.w(ldr(R3, R10, 0), cmp_r(R3, R2), mov_r(R4, R10, EQ))
    a.b(EQ, 'fstore')
    a.label('nx')
    a.lit(R3, 0x400)
    a.w(add_i(R8, R8, 4), cmp_r(R8, R3))
    a.b(LT, 'sc')
    a.label('fstore')
    a.w(str_(R4, R7, 0))
    a.label('fret')
    a.w(0xE8BD8000)                                          # pop {pc}
    out = a.build()
    return out, a.labels


def code(b=None, H=None):
    """The hooks (filmhook, filmgate, filmdial) after the data block in the R5 region: (bytes, labels). H = the helper labels."""
    A = addrs(b)
    if H is None:
        H = helpers(None, b)[1]
    a = Asm(A['code'])
    # ---- entry: replaces `bl key_call`; r0 = key, r1 = state, lr = back into the dispatcher
    a.w(push(0x47FF))                                        # push {r0-r10, lr}
    a.w(mov_i(R0, 3))
    a.b(AL, GET_SYSVAL, link=True)                           # shooting mode
    a.w(cmp_i(R0, SCENE_MODE), mov_i(R6, 0), mov_i(R6, 1, EQ))   # r6 = want film mode
    a.lit(R7, A['vars'])
    a.w(ldr(R2, R7, 4), cmp_r(R2, R6))
    a.b(EQ, 'plain')                                         # no change: the common case, a handful of instructions
    a.b(AL, H['findobj'], link=True)                            # r4 = CSFileList object or 0
    a.w(cmp_i(R4, 0))
    a.b(EQ, 'plain')
    a.w(ldr(R0, R4, 0x118))                                  # DCF manager
    a.b(AL, H['valid'], link=True)
    a.w(cmp_i(IP, 0))
    a.b(EQ, 'plain')
    a.w(ldr(R0, R0, 0x10))                                   # DCF list
    a.b(AL, H['valid'], link=True)
    a.w(cmp_i(IP, 0))
    a.b(EQ, 'plain')
    a.w(ldr(R9, R0, 0x20))                                   # media type, the argument the list already has
    a.w(str_(R6, R7, 4))                                     # commit the new state, then switch the name and rescan
    a.lit(R2, A['tab_dcim'])
    a.w(cmp_i(R6, 0), add_i(R2, R2, TAB_FILM - TAB_DCIM, NE))
    a.lit(R3, A['buf'])
    a.w(mov_i(R1, 40))
    a.b(AL, H['copy'], link=True)
    a.w(mov_r(R0, R4), mov_r(R1, R9))
    a.b(AL, OPEN, link=True)                                 # rescan; r0 = number of files found
    a.w(mov_r(R5, R0))
    a.w(str_(R5, R7, 8), mov_i(R2, 0), str_(R2, R7, 12))      # files seen = what the rescan found; unlocked (a loaded camera is ready for frame 1)
    a.lit(R3, SLOT0)
    a.w(cmp_i(R6, 0))
    a.b(NE, 'on')
    a.lit(R2, A['text_off'])
    a.w(mov_i(R1, 20))
    a.b(AL, H['copy'], link=True)
    a.b(AL, 'popup')
    a.label('on')
    a.lit(R2, A['text_on'])
    a.w(mov_i(R1, 28))
    a.b(AL, H['copy'], link=True)
    a.w(cmp_i(R5, FRAMES), mov_i(R5, FRAMES, HI))            # more than a roll (or a failed scan) shows 0 left
    a.w(mov_i(R0, FRAMES), dp_r(SUB, R0, R0, R5))
    a.w(mov_i(R2, 0x30))
    a.label('tens')
    a.w(cmp_i(R0, 10), sub_i(R0, R0, 10, GE), add_i(R2, R2, 1, GE))
    a.b(GE, 'tens')
    a.w(strh(R2, R3, 10), add_i(R0, R0, 0x30), strh(R0, R3, 12))
    a.label('popup')
    a.w(mov_i(R0, LOOK_ON))
    a.b(AL, ui.ARM_NAME, link=True)
    a.w(mov_i(R0, 0))
    a.b(AL, ui.DRAW_ICONS, link=True)                        # full redraw of the shooting-screen icons: the stock shots-left number is only
                                                             # recalculated (through the clamp) when it is redrawn, which used to wait for the first shot
    a.w(mov_i(R0, LOOK_ON))
    a.b(AL, ui.TOAST_CODE, link=True)
    a.w(pop(0x47FF))
    a.b(AL, ui.KEY_CALL[1])                                  # pop-up shown: skip the stock key hook (it would hide the box again)
    a.label('plain')
    a.w(pop(0x47FF))
    a.b(AL, ui.KEYHOOK)                                      # the stock key hook, which ends in the original call
    # ---- wind-on lock (stage 2b). Replaces the dispatcher's `bl 0xC04BFF98` ("is this key handled"; returning 0 swallows the key, the same
    # trick the old tilt code used for the VIDEO key). While in SCENE and locked, a press of the shutter keys (10, and 11 in case it is the
    # full press; states 1 and 2 are the only ones the stock handlers act on, so releases still pass and nothing can stay "held") is swallowed
    # and a "Wind on >" pop-up shows. r7 / r8 are the dispatcher's own state / key registers.
    a.label('filmgate')
    a.lit(R2, A['vars'])
    a.w(ldr(R3, R2, 4), cmp_i(R3, 0))
    a.b(EQ, 'gorig')
    a.w(ldr(R3, R2, 12), cmp_i(R3, 0))
    a.b(EQ, 'gorig')
    a.w(cmp_i(R8, 10), cmp_ic(R8, 11, NE))
    a.b(NE, 'gorig')
    a.w(cmp_i(R7, 1), cmp_ic(R7, 2, NE))
    a.b(NE, 'gorig')
    a.w(push(0x47FF))
    a.lit(R2, A['text_wind'])
    a.lit(R3, SLOT1)
    a.w(mov_i(R1, 20))
    a.b(AL, H['copy'], link=True)
    a.w(mov_i(R0, LOOK_MSG))
    a.b(AL, ui.ARM_NAME, link=True)
    a.w(mov_i(R0, LOOK_MSG))
    a.b(AL, ui.TOAST_CODE, link=True)
    a.w(pop(0x47FF), mov_i(R0, 0), MOV_PC_LR)                # swallowed: "not handled"
    a.label('gorig')
    a.b(AL, GATE_STOCK)
    # ---- unlock: replaces `bl 0xC04C06E0` (front dial = click dial event; the event's method +0x10 returns 1 for a turn to the right).
    # Always hands on to the stock handler afterwards.
    a.label('filmdial')
    a.lit(R2, A['vars'])
    a.w(ldr(R3, R2, 4), cmp_i(R3, 0))
    a.b(EQ, 'dorig')
    a.w(ldr(R3, R2, 12), cmp_i(R3, 0))
    a.b(EQ, 'dorig')
    a.w(push(0x47FF), mov_r(R4, R1))
    a.w(ldr(R5, R4, 0), add_i(R5, R5, 0x10), ldr(IP, R5, 4), P.LDRSH_R0_R5, dp_r(ADD, R0, R4, R0), mov_r(LR, PC), mov_r(PC, IP))
    a.w(cmp_i(R0, 1))
    a.b(NE, 'dno')
    a.lit(R2, A['vars'])
    a.w(mov_i(R3, 0), str_(R3, R2, 12))                      # wound: unlocked
    a.lit(R2, A['text_wound'])
    a.lit(R3, SLOT1)
    a.w(mov_i(R1, 12))
    a.b(AL, H['copy'], link=True)
    a.w(mov_i(R0, LOOK_MSG))
    a.b(AL, ui.ARM_NAME, link=True)
    a.w(mov_i(R0, LOOK_MSG))
    a.b(AL, ui.TOAST_CODE, link=True)
    a.label('dno')
    a.w(pop(0x47FF))
    a.label('dorig')
    a.b(AL, DIAL_STOCK)
    out = a.build()
    return out, a.labels


def blob(b=None, b4=None):
    """([(address, bytes), ...], labels): block 1 = data + texts + hooks (R5 region), block 2 = helpers (R4 region)."""
    b = base() if b is None else b
    b4 = base_r4() if b4 is None else b4
    hbytes, H = helpers(b4, b)
    c, labels = code(b, H)
    out = bytearray(CODE_AT)
    out[BUF:BUF + 40] = _table('DCIM')
    out[TAB_DCIM:TAB_DCIM + 40] = _table('DCIM')
    out[TAB_FILM:TAB_FILM + 40] = _table('FILM')
    out[TEXT_ON:TEXT_ON + 28] = _utf16('Film 00 left', 28)
    out[TEXT_OFF:TEXT_OFF + 20] = _utf16('Film off', 20)
    out[TEXT_WIND:TEXT_WIND + 20] = _utf16('Wind on >', 20)
    out[TEXT_WOUND:TEXT_WOUND + 12] = _utf16('Wound', 12)
    allp = dict(H)
    allp.update(labels)
    return [(b, bytes(out) + c), (b4, hbytes)], allp


def patch(d):
    """Apply to a built (normal) .elf: block, pointer patches, key hook chain. Call after fauxji_ui / fauxji_rot patches."""
    d = bytearray(d)
    blocks, labels = blob()
    (b, data), (b4, hdata) = blocks
    import fauxji_rot
    assert b + len(data) <= ui.DIAG_END, hex(b + len(data))       # both blocks stay inside dead factory regions
    assert b4 + len(hdata) <= fauxji_rot.R4_END, hex(b4 + len(hdata))
    d[b - B:b - B + len(data)] = data
    d[b4 - B:b4 - B + len(hdata)] = hdata
    A = addrs(b)
    for pool, stock in STOCK.items():                              # the six pointers: stock string -> RAM buffer
        want = {FMT1_POOL: A['buf'] + 8, FMT2_POOL: A['buf'] + 16}.get(pool, A['buf'])
        have = struct.unpack_from('<I', d, pool - B)[0]
        assert have in (stock, want), (hex(pool), hex(have))
        struct.pack_into('<I', d, pool - B, want)
    site, target = ui.KEY_CALL                                     # key dispatcher: filmhook first, then the stock key hook
    entry = b + CODE_AT
    assert struct.unpack_from('<I', d, site - B)[0] in (ui._b(site, ui.KEYHOOK, link=True), ui._b(site, entry, link=True)), 'patch() first'
    struct.pack_into('<I', d, site - B, ui._b(site, entry, link=True))
    for site, stock, name in ((GATE_SITE, GATE_STOCK, 'filmgate'), (DIAL_SITE, DIAL_STOCK, 'filmdial')):    # wind-on lock
        assert struct.unpack_from('<I', d, site - B)[0] in (ui._b(site, stock, link=True), ui._b(site, labels[name], link=True)), hex(site)
        struct.pack_into('<I', d, site - B, ui._b(site, labels[name], link=True))
    clamp = labels['rollclamp']                                    # shots left: min(stock, 36 - files in the roll) while in SCENE
    assert struct.unpack_from('<I', d, ROLL_SITE - B)[0] in (ROLL_STOCK, ui._b(ROLL_SITE, clamp)), hex(ROLL_SITE)
    struct.pack_into('<I', d, ROLL_SITE - B, ui._b(ROLL_SITE, clamp))
    return bytes(d)

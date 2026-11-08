"""FILM CAMERA mode (build_fauxji.py --film): the SCENE dial position is a film camera.

What it does
  * Every key event goes through `filmhook` first (it replaces the key dispatcher's first call, 0xC04C1938, and hands on to the
    stock key hook). It reads the shooting mode, GET_SYSVAL(3): P 2, A 3, S 4, M 5, SCENE 10 (measured on the camera).
  * Folders. When the mode changes between SCENE and anything else, the camera's "DCIM" folder name is switched to the current roll's
    folder, FILM001, FILM002 ... in the card's root (or back to DCIM) and the camera rescans its file list: CSFileList::Open(obj, type)
    0xC01A5BA4, which returns the number of files it found. The name is switched by pointing the six code pointers that carry it at RAM
    buffers (the camera builds every photo path from root + "DCIM" + "NNNPHOTO" + "SAM_nnnn.JPG"; the folder creator uses "%s/DCIM"
    formats). Normal playback scans /DCIM, so the rolls are never listed there. Outside SCENE the buffers hold the stock strings.
  * Rolls. The current roll is the first FILMnnn with fewer than 36 files; if the next folder is the empty one just created after a
    full roll, the full roll stays current (nothing starts silently). A full roll is started over with the film-look key (AE-L = key 14,
    state 1): it makes the next roll and then lets the key through, so the stock FILM SIM cycles the look. A roll that is part shot
    keeps its film: the key is swallowed with "Roll in use". An empty roll lets the look be chosen freely. A roll is 36 frames.
  * Counter. A hook at the end of getRemainPhotoNum makes the camera's own shots-left number min(stock, 36 - files in the roll) in SCENE
    (at 0 the camera shows its stock "Memory Full" and will not shoot). The switch forces a full icon redraw so it shows at once.
  * Wind-on lock. A rising file count (read in that hook) marks a photo as taken; while locked the shutter keys are swallowed (pop-up
    "Wind on >") until the front dial (click dial) is turned right (`Dial C 1`), which shows "Wound".
  * Pop-ups: "Film nn left" when SCENE is entered or a roll is started, "Film off" when it is left. They appear on the next key press
    after the dial moves (the mode dial itself raises no key event); the stock key hook is skipped for that key (it would hide them).
  * SCENE is P. The scene picker is not wanted, so the SCENE position must behave like P (program exposure with the 1/60 floor and auto
    ISO, the unlocked menus): GET_SYSVAL(3) reports SCENE (10) as P (2) to every reader, this code reads the real value (`rawmode`).
If the camera's file list object cannot be found, or its chain is not valid, nothing is changed (the hook retries on the next key).
Not yet: the review lock, the canister screens and picker, a film-themed "roll full" message.
Code and data live in dead factory regions: shared routines after fauxji_rot's `plzoom` (R4), data and hooks after `gate3` (R5, extended
to 0xC04274B8: the functions at 0xC04272C0 and 0xC04274B8 have no live caller, tools/liveness.py). Tests: tools/test_film.py.
"""
import struct

import diag_probe as P
import fauxji_ui as ui
from diag_probe import (Asm, R0, R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, IP, LR, PC, EQ, NE, GE, LT, HS, LO, AL, ADD, SUB, MOV,
                        mov_i, mov_r, add_i, sub_i, cmp_i, cmp_r, tst_i, ldr, str_, ldr_x, strh, push, pop, dp_r, lsr_i, MOV_PC_LR)

HI = 0x8
B = ui.B
SCENE_MODE = 10
FRAMES = 36
MAX_ROLL = 999
FILM_END = 0xC04274B8                         # end of the usable dead region after R5's `gate3`
GET_SYSVAL = P.GET_SYSVAL
OPEN, VPTR, MANAGER_GLOBAL = P.OPEN, P.VPTR, P.MANAGER_GLOBAL
LOOK_ON, LOOK_MSG = 11, 12                    # name pop-up looks 11 / 12 = tilt text slots 0 / 1 (served by STRWRAP), overwritten at run time
SLOT0 = ui.STR_BASE
SLOT1 = ui.STR_BASE + ui.STR_SLOT
GATE_SITE, GATE_STOCK = 0xC04C1944, 0xC04BFF98   # `bl` of the dispatcher's "is this key handled" call (r0 = state obj, r1 = key)
DIAL_SITE, DIAL_STOCK = 0xC04C2228, 0xC04C06E0   # `bl` of the click dial (front dial) event handler (r0 = state obj, r1 = event)
ROLL_SITE, ROLL_BACK, ROLL_STOCK = 0xC047B6B8, 0xC047B6BC, 0xE28DD058   # end of getRemainPhotoNum: `add sp,sp,#0x58` (r0 = shots left)
FILM_KEY = 14                                 # the film-look key (AE-L): FILM SIM
# SCENE behaves like P: the camera reads the shooting mode through GET_SYSVAL(3) at 104 places (exposure program, menus, item lists ...);
# the value 10 (SCENE) is reported as 2 (P) there, while this code reads the real value with the raw getter.
RAW_GET = 0xC049094C                          # raw getter: r0 = index, r1 = pointer for the value
GETVAL_SITE, GETVAL_BACK, GETVAL_STOCK = 0xC048F83C, 0xC048F840, 0xE59D0000   # end of GET_SYSVAL: `ldr r0,[sp]` (fp = index, [sp] = value), then `add sp,sp,#4`
MODE_P = 2

# the six code pointers that carry the folder name (pool word address -> stock string pointer)
FMT1_POOL, FMT2_POOL = 0xC01B10FC, 0xC01B1104               # "%s/DCIM" and "%s/DCIM/100PHOTO" (default folders created by the scan)
STOCK = {0xC01AEC58: 0xC074FF08, 0xC01B1210: 0xC074FF08, 0xC01B181C: 0xC074FF08, 0xC01B3664: 0xC07500AC,
         0xC01B10FC: 0xC074FF60, 0xC01B1104: 0xC074FF74}

# layout of the data in front of the code (fixed addresses so the pointer patches do not depend on the code size)
BUF = 0                      # 48 bytes: name (8) | fmt1 (16) | fmt2 (24)  -- what the six pointers point at
FMT1_AT, FMT2_AT = 8, 24     # offsets of the two format buffers inside BUF
VARS = 0x30                  # 32 bytes: [0] CSFileList object (cache), [4] film active, [8] files seen, [12] locked, [16] roll number, [20] new-roll request
TAB_DCIM, TAB_FILM = 0x50, 0x80
TEXT_ON, TEXT_OFF = 0xB0, 0xCC               # 'Film 00 left' (28 bytes), 'Film off' (20)
TEXT_WIND, TEXT_WOUND, TEXT_USE = 0xE0, 0xF4, 0x100    # 'Wind on >' (20), 'Wound' (12), 'Roll in use' (24)
CODE_AT = 0x118


def _table(name):
    n = name.encode() + b'\0'
    f1 = ('%%s/%s' % name).encode() + b'\0'
    f2 = ('%%s/%s/100PHOTO' % name).encode() + b'\0'
    assert len(n) <= 8 and len(f1) <= 16 and len(f2) <= 24
    return n.ljust(8, b'\0') + f1.ljust(16, b'\0') + f2.ljust(24, b'\0')


def _utf16(text, size):
    raw = text.encode('utf-16-le') + b'\0\0'
    assert len(raw) <= size
    return raw.ljust(size, b'\0')


def str_x(rd, rn, rm):
    return 0xE7800000 | (rn << 16) | (rd << 12) | rm


def str_c(rd, rn, off, cond):
    return (cond << 28) | 0x05800000 | (rn << 16) | (rd << 12) | off


def strb(rd, rn, off):
    return 0xE5C00000 | (rn << 16) | (rd << 12) | off


def cmp_ic(rn, v, cond):
    return P.dp_i(P.CMP, 0, rn, v, cond=cond, s=1)


def base():
    return ui.diag_base()


def base_r4():
    """First free word of fauxji_rot's R4 region (dead factory code, `waitEXStrobeSignal`) after its own blob, 16-byte aligned."""
    import fauxji_rot
    blobs, _ = fauxji_rot.build()
    end = max(x + len(c) for x, c in blobs if fauxji_rot.R4 <= x < fauxji_rot.R4_END)
    return (end + 15) & ~15


def addrs(b=None):
    b = base() if b is None else b
    return dict(buf=b + BUF, vars=b + VARS, tab_dcim=b + TAB_DCIM, tab_film=b + TAB_FILM, text_on=b + TEXT_ON, text_off=b + TEXT_OFF,
                text_wind=b + TEXT_WIND, text_wound=b + TEXT_WOUND, text_use=b + TEXT_USE, code=b + CODE_AT)


def helpers(b4=None, b=None):
    """Shared routines (copy, valid, findobj, setnames, rollclamp) in the R4 region: (bytes, labels)."""
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
    # ---- the roll folder names: copy the FILM template into the three buffers and write the roll number (vars[16], 1-999) as
    # three digits into each ("FILM001", "%s/FILM001", "%s/FILM001/100PHOTO"); r7 = vars; clobbers r0-r3, ip
    a.label('setnames')
    a.w(push(0x4000))
    a.lit(R2, A['tab_film'])
    a.lit(R3, A['buf'])
    a.w(mov_i(R1, 48))
    a.b(AL, 'copy', link=True)
    a.w(ldr(R0, R7, 16), mov_i(R1, 0x30))
    a.label('hund')
    a.w(cmp_i(R0, 100), sub_i(R0, R0, 100, GE), add_i(R1, R1, 1, GE))
    a.b(GE, 'hund')
    a.w(mov_i(R2, 0x30))
    a.label('tens')
    a.w(cmp_i(R0, 10), sub_i(R0, R0, 10, GE), add_i(R2, R2, 1, GE))
    a.b(GE, 'tens')
    a.w(add_i(R0, R0, 0x30))
    a.lit(R3, A['buf'])
    for off in (4, FMT1_AT + 7, FMT2_AT + 7):
        a.w(strb(R1, R3, off), strb(R2, R3, off + 1), strb(R0, R3, off + 2))
    a.w(pop(0x8000))                                         # pop {pc}
    # ---- shots left: replaces `add sp,sp,#0x58` at the end of the camera's getRemainPhotoNum (r0 = shots left, the value the shooting
    # screen shows). In SCENE it becomes min(shots left, 36 - files in the roll), the file count being the DCF list's running total
    # [list+0x24] (the same number CSFileList::Open returned). A count that went up since the last look means a photo was just saved:
    # locked (wind on before the next one). Outside SCENE, or if any pointer on the way is not valid, r0 is untouched. lr, r1-r3 and ip
    # are free here (the epilogue pops the saved registers next).
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
    # ---- r0 = the REAL shooting mode (the camera's own GET_SYSVAL(3) reads report SCENE as P); clobbers r0-r3, ip
    a.label('rawmode')
    a.w(push(0x4000), sub_i(13, 13, 8), mov_i(R2, 0), str_(R2, 13, 0), mov_r(R1, 13), mov_i(R0, 3))
    a.b(AL, RAW_GET, link=True)
    a.w(ldr(R0, 13, 0), add_i(13, 13, 8))
    a.w(pop(0x8000))                                         # pop {pc}
    # ---- r4 = the CSFileList object (cached in vars[0], checked by its vtable pointer), else found by scanning the manager at
    # *0xC08B439C like the diagnostic's finder; r6, r7 kept (clobbers r0-r3, r5, r8-r10)
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
    a.w(pop(0x8000))                                         # pop {pc}
    out = a.build()
    return out, a.labels


def code(b=None, H=None):
    """The data-adjacent code in the R5 region: doswitch, the pop-ups and the three hooks: (bytes, labels). H = the helper labels."""
    A = addrs(b)
    if H is None:
        H = helpers(None, b)[1]
    a = Asm(A['code'])
    # ---- switch to (r6 = 1) or away from (r6 = 0) the film folder; r7 = vars; vars[20] = 1 asks for a new roll.
    # Out: r0 = 1 done / 0 failed (nothing changed), r5 = files in the folder now active. Clobbers r0-r5, r8-r10.
    a.label('doswitch')
    a.w(push(0x4000))
    a.b(AL, H['findobj'], link=True)                         # r4 = CSFileList object or 0
    a.w(cmp_i(R4, 0))
    a.b(EQ, 'dfail')
    a.w(ldr(R0, R4, 0x118))                                  # DCF manager
    a.b(AL, H['valid'], link=True)
    a.w(cmp_i(IP, 0))
    a.b(EQ, 'dfail')
    a.w(ldr(R0, R0, 0x10))                                   # DCF list
    a.b(AL, H['valid'], link=True)
    a.w(cmp_i(IP, 0))
    a.b(EQ, 'dfail')
    a.w(ldr(R9, R0, 0x20))                                   # media type, the argument the list already has
    a.w(str_(R6, R7, 4))                                     # commit the new state, then switch the names and rescan
    a.w(cmp_i(R6, 0))
    a.b(NE, 'dfilm')
    a.lit(R2, A['tab_dcim'])                                 # leaving: the stock names
    a.lit(R3, A['buf'])
    a.w(mov_i(R1, 48))
    a.b(AL, H['copy'], link=True)
    a.w(mov_r(R0, R4), mov_r(R1, R9))
    a.b(AL, OPEN, link=True)
    a.w(mov_r(R5, R0))
    a.b(AL, 'ddone')
    a.label('dfilm')
    a.w(ldr(R10, R7, 16), cmp_i(R10, 0), mov_i(R10, 1, EQ))  # the roll number so far (0 = none yet)
    a.w(ldr(R8, R7, 20), cmp_i(R8, 0), add_i(R10, R10, 1, NE))   # a new roll was asked for
    a.label('dprobe')
    a.lit(R2, MAX_ROLL)
    a.w(cmp_r(R10, R2), mov_r(R10, R2, HI), str_(R10, R7, 16))
    a.b(AL, H['setnames'], link=True)
    a.w(mov_r(R0, R4), mov_r(R1, R9))
    a.b(AL, OPEN, link=True)                                 # rescan: r0 = files in this roll folder
    a.w(mov_r(R5, R0))
    a.w(cmp_i(R5, FRAMES))
    a.b(LO, 'dgot')                                          # room left (or a new folder): this is the roll
    a.w(lsr_i(R1, R5, 16), cmp_i(R1, 0))
    a.b(NE, 'dgot')                                          # a failure code or garbage: stop, do not loop
    a.lit(R2, MAX_ROLL)
    a.w(cmp_r(R10, R2))
    a.b(HS, 'dgot')                                          # last roll number
    a.w(add_i(R10, R10, 1))
    a.b(AL, 'dprobe')                                        # this roll is full: look at the next one
    a.label('dgot')
    a.w(cmp_i(R5, 0))
    a.b(NE, 'ddone')                                         # has frames: the current roll
    a.w(ldr(R8, R7, 20), cmp_i(R8, 0))
    a.b(NE, 'ddone')                                         # a new roll was asked for: the empty folder is it
    a.w(cmp_i(R10, 2))
    a.b(LO, 'ddone')                                         # roll 1 and empty: the first roll
    a.w(sub_i(R10, R10, 1), str_(R10, R7, 16))               # an empty folder after a full one: stay on the full roll (nothing starts silently)
    a.b(AL, H['setnames'], link=True)
    a.w(mov_r(R0, R4), mov_r(R1, R9))
    a.b(AL, OPEN, link=True)
    a.w(mov_r(R5, R0))
    a.label('ddone')
    a.w(mov_i(R0, 0), str_(R0, R7, 20), str_(R0, R7, 12))    # request cleared, unlocked (a loaded camera is ready for frame 1)
    a.w(str_(R5, R7, 8))                                     # files seen
    a.w(mov_i(R0, 1), pop(0x8000))
    a.label('dfail')
    a.w(mov_i(R0, 0), pop(0x8000))
    # ---- look-11 pop-up with a full icon redraw (the stock shots-left number is recalculated when it is redrawn)
    a.label('popup11')
    a.w(push(0x4000), mov_i(R0, LOOK_ON))
    a.b(AL, ui.ARM_NAME, link=True)
    a.w(mov_i(R0, 0))
    a.b(AL, ui.DRAW_ICONS, link=True)
    a.w(mov_i(R0, LOOK_ON))
    a.b(AL, ui.TOAST_CODE, link=True)
    a.w(pop(0x8000))
    # ---- "Film nn left" for r5 files in the roll (0 left for a full roll or a failed scan); clobbers r0-r3, ip
    a.label('msgleft')
    a.w(push(0x4000))
    a.lit(R2, A['text_on'])
    a.lit(R3, SLOT0)
    a.w(mov_i(R1, 28))
    a.b(AL, H['copy'], link=True)
    a.w(cmp_i(R5, FRAMES), mov_i(R5, FRAMES, HI))
    a.w(mov_i(R0, FRAMES), dp_r(SUB, R0, R0, R5), mov_i(R2, 0x30))
    a.label('ltens')
    a.w(cmp_i(R0, 10), sub_i(R0, R0, 10, GE), add_i(R2, R2, 1, GE))
    a.b(GE, 'ltens')
    a.w(strh(R2, R3, 10), add_i(R0, R0, 0x30), strh(R0, R3, 12))
    a.b(AL, 'popup11', link=True)
    a.w(pop(0x8000))
    # ---- SCENE reads as P. Replaces `ldr r0,[sp]` at the end of GET_SYSVAL (fp = the index, [sp] = the value it fetched): for index 3 (the
    # shooting mode) the value 10 (SCENE) becomes 2 (P), so the exposure program (1/60 floor, auto ISO, bias), the menus and the screens all
    # behave as in P. Everything else is passed through; only r0 and the flags change.
    a.label('filmget')
    a.w(ldr(R0, 13, 0), cmp_i(11, 3))
    a.b(NE, 'gvback')
    a.w(cmp_i(R0, SCENE_MODE), mov_i(R0, MODE_P, EQ))
    a.label('gvback')
    a.b(AL, GETVAL_BACK)
    # ---- entry: replaces `bl key_call`; r0 = key, r1 = state, lr = back into the dispatcher
    a.label('filmhook')
    a.w(push(0x47FF))                                        # push {r0-r10, lr}
    a.b(AL, H['rawmode'], link=True)                         # the real shooting mode (the camera's own reads see SCENE as P)
    a.w(cmp_i(R0, SCENE_MODE), mov_i(R6, 0), mov_i(R6, 1, EQ))   # r6 = want film mode
    a.lit(R7, A['vars'])
    a.w(ldr(R2, R7, 4), cmp_r(R2, R6))
    a.b(EQ, 'plain')                                         # no change: the common case, a handful of instructions
    a.w(mov_i(R2, 0), str_(R2, R7, 20))                      # no new-roll request
    a.b(AL, 'doswitch', link=True)
    a.w(cmp_i(R0, 0))
    a.b(EQ, 'plain')
    a.w(cmp_i(R6, 0))
    a.b(NE, 'on')
    a.lit(R2, A['text_off'])
    a.lit(R3, SLOT0)
    a.w(mov_i(R1, 20))
    a.b(AL, H['copy'], link=True)
    a.b(AL, 'popup11', link=True)
    a.b(AL, 'fpop')
    a.label('on')
    a.b(AL, 'msgleft', link=True)
    a.label('fpop')
    a.w(pop(0x47FF))
    a.b(AL, ui.KEY_CALL[1])                                  # pop-up shown: skip the stock key hook (it would hide the box again)
    a.label('plain')
    a.w(pop(0x47FF))
    a.b(AL, ui.KEYHOOK)                                      # the stock key hook, which ends in the original call
    # ---- the gate. Replaces the dispatcher's `bl 0xC04BFF98` ("is this key handled"; returning 0 swallows the key, the same trick the
    # old tilt code used for the VIDEO key). r0 = state obj, r1 = key; r7 / r8 are the dispatcher's own state / key registers.
    #  * the film-look key (14, press): empty roll = free choice; part-shot roll = swallowed ("Roll in use"); full roll = a new roll is
    #    started, then the key goes on to the stock handler (the look cycles).
    #  * while locked, a press of the shutter keys (10, and 11 in case it is the full press; states 1 and 2 are the only ones the stock
    #    handlers act on, so releases still pass and nothing can stay "held") is swallowed with a "Wind on >" pop-up.
    a.label('filmgate')
    a.lit(R2, A['vars'])
    a.w(ldr(R3, R2, 4), cmp_i(R3, 0))
    a.b(EQ, 'gorig')                                         # not in SCENE
    a.w(cmp_i(R8, FILM_KEY))
    a.b(NE, 'gshut')
    a.w(cmp_i(R7, 1))
    a.b(NE, 'gorig')
    a.w(ldr(R3, R2, 8), cmp_i(R3, 0))
    a.b(EQ, 'gorig')                                         # empty roll: pick the film freely
    a.w(lsr_i(IP, R3, 16), cmp_i(IP, 0))                     # (ip, not r1: r0 / r1 must reach the stock call intact)
    a.b(NE, 'gorig')                                         # garbage count: leave it alone
    a.w(cmp_i(R3, FRAMES))
    a.b(HS, 'gnew')
    a.w(push(0x47FF))                                        # part-shot roll: no film change
    a.lit(R2, A['text_use'])
    a.lit(R3, SLOT1)
    a.w(mov_i(R1, 24))
    a.b(AL, H['copy'], link=True)
    a.b(AL, 'gshow')
    a.label('gnew')
    a.w(push(0x47FF))                                        # full roll: start the next one, then let the key through
    a.lit(R7, A['vars'])
    a.w(mov_i(R6, 1), mov_i(R2, 1), str_(R2, R7, 20))
    a.b(AL, 'doswitch', link=True)
    a.w(cmp_i(R0, 0))
    a.b(EQ, 'gnd')
    a.b(AL, 'msgleft', link=True)
    a.label('gnd')
    a.w(pop(0x47FF))
    a.b(AL, GATE_STOCK)
    a.label('gshut')
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
    a.label('gshow')                                         # slot-1 pop-up (look 12), then swallow the key
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
    """([(address, bytes), ...], labels): block 1 = data + texts + code (R5 region), block 2 = helpers (R4 region)."""
    b = base() if b is None else b
    b4 = base_r4() if b4 is None else b4
    hbytes, H = helpers(b4, b)
    c, labels = code(b, H)
    out = bytearray(CODE_AT)
    out[BUF:BUF + 48] = _table('DCIM')
    out[TAB_DCIM:TAB_DCIM + 48] = _table('DCIM')
    out[TAB_FILM:TAB_FILM + 48] = _table('FILM000')
    out[TEXT_ON:TEXT_ON + 28] = _utf16('Film 00 left', 28)
    out[TEXT_OFF:TEXT_OFF + 20] = _utf16('Film off', 20)
    out[TEXT_WIND:TEXT_WIND + 20] = _utf16('Wind on >', 20)
    out[TEXT_WOUND:TEXT_WOUND + 12] = _utf16('Wound', 12)
    out[TEXT_USE:TEXT_USE + 24] = _utf16('Roll in use', 24)
    allp = dict(H)
    allp.update(labels)
    return [(b, bytes(out) + c), (b4, hbytes)], allp


def patch(d):
    """Apply to a built (normal) .elf: blocks, pointer patches, hook sites. Call after the fauxji_ui / fauxji_rot patches."""
    d = bytearray(d)
    blocks, labels = blob()
    (b, data), (b4, hdata) = blocks
    import fauxji_rot
    assert b + len(data) <= FILM_END, hex(b + len(data))           # both blocks stay inside dead factory regions
    assert b4 + len(hdata) <= fauxji_rot.R4_END, hex(b4 + len(hdata))
    d[b - B:b - B + len(data)] = data
    d[b4 - B:b4 - B + len(hdata)] = hdata
    A = addrs(b)
    for pool, stock in STOCK.items():                              # the six pointers: stock string -> RAM buffer
        want = {FMT1_POOL: A['buf'] + FMT1_AT, FMT2_POOL: A['buf'] + FMT2_AT}.get(pool, A['buf'])
        have = struct.unpack_from('<I', d, pool - B)[0]
        assert have in (stock, want), (hex(pool), hex(have))
        struct.pack_into('<I', d, pool - B, want)
    site, target = ui.KEY_CALL                                     # key dispatcher: filmhook first, then the stock key hook
    entry = labels['filmhook']
    assert struct.unpack_from('<I', d, site - B)[0] in (ui._b(site, ui.KEYHOOK, link=True), ui._b(site, entry, link=True)), 'patch() first'
    struct.pack_into('<I', d, site - B, ui._b(site, entry, link=True))
    for site, stock, name in ((GATE_SITE, GATE_STOCK, 'filmgate'), (DIAL_SITE, DIAL_STOCK, 'filmdial')):
        assert struct.unpack_from('<I', d, site - B)[0] in (ui._b(site, stock, link=True), ui._b(site, labels[name], link=True)), hex(site)
        struct.pack_into('<I', d, site - B, ui._b(site, labels[name], link=True))
    assert struct.unpack_from('<I', d, GETVAL_SITE - B)[0] in (GETVAL_STOCK, ui._b(GETVAL_SITE, labels['filmget'])), hex(GETVAL_SITE)
    struct.pack_into('<I', d, GETVAL_SITE - B, ui._b(GETVAL_SITE, labels['filmget']))     # SCENE reads as P everywhere
    clamp = labels['rollclamp']                                    # shots left: min(stock, 36 - files in the roll) while in SCENE
    assert struct.unpack_from('<I', d, ROLL_SITE - B)[0] in (ROLL_STOCK, ui._b(ROLL_SITE, clamp)), hex(ROLL_SITE)
    struct.pack_into('<I', d, ROLL_SITE - B, ui._b(ROLL_SITE, clamp))
    return bytes(d)

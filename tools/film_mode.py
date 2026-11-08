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
  * Direction keys (macro, flash, self-timer, display) work: the state object's cached mode (+0xC) is made P in a scene card.
  * SCENE is P. The scene picker is not wanted, so the SCENE position must behave like P (program exposure with the 1/60 floor and auto
    ISO, the unlocked menus): GET_SYSVAL(3) reports SCENE (10) as P (2) to every reader, this code reads the real value (`rawmode`).
If the camera's file list object cannot be found, or its chain is not valid, nothing is changed (the hook retries on the next key).
  * Roll full. At 0 frames the camera's "Memory Full" is shown as "Roll full - press AE-L" while in SCENE (GetStaticString wrapped for id 687).
  * No playback in SCENE: requests for the Playback state (id 5) are dropped with a "No playback" pop-up (`filmstate`).
Not yet: the review right after a shot, the big canister screens.
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
SCENE_MODE = 10                               # first scene card: the 13 scene cards are the modes 10..22 (the mode-change code takes the stored scene id, sysval 4, 10..22, as the mode)
SCENE_COUNT = 13
LS = 0x9
FRAMES = 36
MAX_ROLL = 999
FILM_END = 0xC0427D24                         # end of the usable dead region after R5's `gate3`: the function at 0xC04274B8 (the factory command switch, 0xC0427870 inside it) has no caller at all (tools/liveness.py)
GET_SYSVAL = P.GET_SYSVAL
OPEN, VPTR, MANAGER_GLOBAL = P.OPEN, P.VPTR, P.MANAGER_GLOBAL
LOOK_ON, LOOK_MSG = 11, 12                    # name pop-up looks 11 / 12 = tilt text slots 0 / 1 (served by STRWRAP), overwritten at run time
SLOT0 = ui.STR_BASE
SLOT1 = ui.STR_BASE + ui.STR_SLOT
GATE_SITE, GATE_STOCK = 0xC04C1944, 0xC04BFF98   # `bl` of the dispatcher's "is this key handled" call (r0 = state obj, r1 = key)
DIAL_SITE, DIAL_STOCK = 0xC04C2228, 0xC04C06E0   # `bl` of the click dial (front dial) event handler (r0 = state obj, r1 = event)
ROLL_SITE, ROLL_BACK, ROLL_STOCK = 0xC047B6B8, 0xC047B6BC, 0xE28DD058   # end of getRemainPhotoNum: `add sp,sp,#0x58` (r0 = shots left)
FILM_KEY = 14                                 # the film-look key (AE-L): FILM SIM
# No playback in the film camera: the state-change function 0xC0491150(fsm, id, ...) is entered for every screen change; id 5 is Playback.
# (The roll folder is the camera's folder while in SCENE, so playback only ended in a file error.) In SCENE the request is dropped.
STATE_SITE, STATE_BACK, STATE_STOCK = 0xC0491150, 0xC0491154, 0xE92D4FF0   # entry `push {r4-r8,sb,sl,fp,lr}`, continues at the second word
STATE_PLAYBACK = 5
# PLAY is an event of type 0x11 (not a key) in the handler 0xC0494984, which answers it with a request for state 5 (and 5 = MENU -> state 0x12,
# 0x10 / 1 -> 12). Owner's D06 log of PLAY (requested ids, oldest first): 12, 3, 5, then on leaving 7, 3, 11, 12. Dropping 5 alone, or 3 as well
# (FILM13), still showed the file error, and dropping 3 froze the camera after a few shots (3 is the review after a shot). So the event itself
# is dropped at the entry of that handler in SCENE (`filmevent`), as well as the state-5 request.
EVENT_SITE, EVENT_BACK, EVENT_STOCK = 0xC0494984, 0xC0494988, 0xE92D4FF0   # handler entry `push {r4-r8,sb,sl,fp,lr}` (r0 = state, r1 = event)
EVENT_PLAY = 0x11
# SCENE behaves like P: the camera reads the shooting mode through GET_SYSVAL(3) at 104 places (exposure program, menus, item lists ...);
# the value 10 (SCENE) is reported as 2 (P) there, while this code reads the real value with the raw getter.
RAW_GET = 0xC049094C                          # raw getter: r0 = index, r1 = pointer for the value
GETVAL_SITE, GETVAL_BACK, GETVAL_STOCK = 0xC048F83C, 0xC048F840, 0xE59D0000   # end of GET_SYSVAL: `ldr r0,[sp]` (fp = index, [sp] = value), then `add sp,sp,#4`
MODE_P = 2
# the film-themed "roll full": the camera's "Memory Full" (SPID string 687) is what it shows at 0 frames. GetStaticString (0xC05BA87C, every UI text
# comes through it: r0 = string context, r1 = id, returns a pointer to the UTF-16 text) is wrapped: in SCENE, for id 687, our text is returned.
STR_SITE, STR_BACK, STR_STOCK = 0xC05BA87C, 0xC05BA880, 0xE1A02000   # entry `mov r2,r0`, then `cmp r1,#0`
STR_MEMFULL = 687
TEXT_FULL_STR = 'Roll full - press AE-L'

# the six code pointers that carry the folder name (pool word address -> stock string pointer)
FMT1_POOL, FMT2_POOL = 0xC01B10FC, 0xC01B1104               # "%s/DCIM" and "%s/DCIM/100PHOTO" (default folders created by the scan)
STOCK = {0xC01AEC58: 0xC074FF08, 0xC01B1210: 0xC074FF08, 0xC01B181C: 0xC074FF08, 0xC01B3664: 0xC07500AC,
         0xC01B10FC: 0xC074FF60, 0xC01B1104: 0xC074FF74}

# layout of the data in front of the code (fixed addresses so the pointer patches do not depend on the code size)
BUF, BUFSZ = 0, 72           # name (16) | fmt1 (24) | fmt2 (32)  -- what the six pointers point at
FMT1_AT, FMT2_AT = 16, 40    # offsets of the two format buffers inside BUF
NAME_LET, NAME_DIG = 6, 10   # in the name "FILMS/ACRO001": the four letters of the look, the three digits of the roll
FMT_LET, FMT_DIG = 9, 13     # in "%s/FILMS/ACRO001": the same, in both format buffers
VARS = 0x48                  # 32 bytes: [0] CSFileList object (cache), [4] film active, [8] files seen, [12] locked, [16] roll number, [20] new-roll request, [24] look, [28] the mode icon spot as last set (0 = stock, else state * 16 + look + 1)
TAB_DCIM, TAB_FILM = 0x68, 0xB0
TEXT_ON, TEXT_OFF = 0xF8, 0x118               # 'ACRO001 36 left' (32 bytes), 'Film off' (20)
TEXT_WIND, TEXT_WOUND, TEXT_USE = 0x12C, 0x140, 0x14C    # 'Wind on >' (20), 'Wound' (12), 'Roll in use' (24)
TEXT_FULL = 0x164                            # 'Roll full - press AE-L' (48 bytes), the replacement for "Memory Full"
TEXT_NOPLAY = 0x194                          # 'No playback' (32 bytes)
ROOT_SUFFIX, ROOT_BACKUP = 0x1B4, 0x1BC      # '/FILMS' (8 bytes), the card root string as the camera had it (48 bytes)
TAB_LOOK, TAB_ID = 0x1EC, 0x218              # 11 x 4 letters (the folder name of each look), 16 bytes: scene card number - 10 -> look
CODE_AT = 0x228
# One parent folder for the rolls: the roll's folder name is "FILMS/ACRO001" (every place that builds a path formats root + name + folder +
# file with snprintf, so a name with a slash is just a deeper path; the name sites and both folder-creator formats carry it). The folder
# creator only makes one level, so the parent is made first, with the camera's own single-folder creator 0xC01B0140(list, path) (-> 0xC03BCD4C):
# the card root string (an inline string at list+0x40: the creator formats "%s/DCIM" from it) gets '/FILMS' appended for the call and is put
# back at once. FILM17 appended it for the whole stay in SCENE instead; the camera kept saving to the root (the save path does not use this
# list's root), so only an empty FILMS folder came out of that.
MKDIR, ROOT_OFF, ROOT_SIZE, ROOT_MAXLEN = 0xC01B0140, 0x40, 48, 0x28
# Wind-on and roll-full icons in the live view's mode-icon spot. The OSD show/hide call 0xC0201CAC(node, visible, 0, 0) takes a node index
# directly when it is below 0x10000 (0xC020011C maps larger values, the hashes, through the skin's hash table). The mode icon group (803, and
# its twin 874) has one 58 x 54 child per mode; in SCENE the stock code shows the card's tile (the film's cartridge). While the roll is locked
# or full `iconfix` hides every child and shows the 'play' child (skin image 17, repainted as the wind-on icon) or the 'DUAL IS' child (image 231,
# the roll-full icon): neither mode shows in the live view of the film camera. Groups: (first child, last child, wind child, full child).
OSD_VIS = ui.OSD_SET_VISIBLE
ICON_GROUPS = ((804, 823, 823, 809, 811), (875, 895, 895, 880, 883))     # first child, last child, wind child, full child, first scene tile
# In SCENE the mode icon showed P (the camera reports SCENE as P, FILM21 owner report), so iconfix now always shows the look's cartridge tile there: the
# scene tiles are in look order (tile = first tile + look, the twelfth repeats PROVIA). A hook at the end of the full redraw (DRAW_ICONS, 0xC04B74AC,
# `add sp,sp,#0x14` before its `pop {sl,fp,pc}`) re-applies it after every redraw, so the stock P tag cannot come back.
DRAW_END, DRAW_BACK, DRAW_END_STOCK = 0xC04B74AC, 0xC04B74B0, 0xE28DD014
IMG_WIND, IMG_FULL = 17, 231
PARENT = b'/FILMS\0\0'
# The scene picker is the film picker: the 13 scene cards are the modes 10..22 (measured: no card has 11), in this on-screen order
# (Beauty Shot 10, Night 12, Portrait 13, Children 14, Landscape 15, Close Up 16, Text 17, Sunset 18, Dawn 19, Backlight 20, Fireworks 21,
# Beach & Snow 22). Each card shows one look (PHOTO STYLE menu value 0..10); the 12th card repeats PROVIA.
LOOK_CODES = ('PROV', 'BLCH', 'NOST', 'ASTI', 'VELV', 'REAL', 'CCHR', 'CNEG', 'ETRN', 'ACRO', 'SEPI')   # roll folders: ACRO001, ACRO002 ...
CARD_LOOK = {10: 0, 12: 1, 13: 2, 14: 3, 15: 4, 16: 5, 17: 6, 18: 7, 19: 8, 20: 9, 21: 10, 22: 0}


# The picker's cards in the film build (build_fauxji.py): the scene names become the films' names (SPID strings: name n, description n + 1)
# and the sample pictures (skin images 195-206) become cartridges. Card number -> string id of the scene name, skin image, look.
LOOK_NAMES = ('Provia', 'Bleach Bypass', 'Nostalgic Neg.', 'Astia', 'Velvia', 'Reala Ace', 'Classic Chrome', 'Classic Neg.', 'Eterna',
              'Acros', 'Sepia')
CARD_STRING = {10: 21, 12: 19, 13: 29, 14: 31, 15: 33, 16: 35, 17: 37, 18: 39, 19: 41, 20: 43, 21: 45, 22: 47}   # Beauty Shot, Night, Portrait ...
CARD_IMAGE = {10: 197, 12: 203, 13: 204, 14: 198, 15: 202, 16: 199, 17: 195, 18: 206, 19: 200, 20: 196, 21: 201, 22: 205}


# The mode icon of the live view (group 803): in SCENE it shows the chosen scene's own icon; these are those twelve skin images (58 x 54) in card order
SCENE_TILES = {10: 242, 12: 248, 13: 250, 14: 243, 15: 247, 16: 244, 17: 239, 18: 251, 19: 245, 20: 240, 21: 246, 22: 241}


# The d-pad "up" key cycles the information display and names each view in the little text box (164 px: about 14 characters on one line); the
# stock descriptions are 27-78 characters and wrapped into two unreadable rows. Short ones for the film build (the SPID string ids of the
# display-mode descriptions: 1011/1018 all info, 1012/1019 basic, 1015 grid, 1016/1021 grid + histogram, 1334 histogram, 1335 hidden, 1014 help).
DISPLAY_TEXT = {1011: 'Full info', 1018: 'Full info', 1012: 'Basic info', 1019: 'Basic info', 1015: 'Info + grid', 1016: 'Grid+histogram',
                1021: 'Grid+histogram', 1334: 'Histogram', 1335: 'Info hidden', 1014: 'Function help'}


# The big cartridge with the shots left in it (live view, film build). Group 1009 (the film icon, a child of the left column 994) moves to the
# top right, its eleven children (images 414-424) become 80 x 96 (tools/badges.big_cartridge: a blank white strip with a transparent window), and the
# shots-left digits (group 797, a child of the bottom bar 744, right-aligned digits at x 2, 16, 30, 44, 57) move up behind the window: the left
# column is drawn after the bar, so the digits show through the hole instead of being covered.
BIG_AT = (484, 6)                                   # absolute top left of the cartridge image
FILM_GROUP, FILM_CHILDREN = 1009, range(1010, 1021)
COUNT_GROUP, BAR_Y = 797, 426
DIGIT_X0 = 44                                       # x of the tens digit inside the group (the units digit is at 57)


def layout(k):
    """Film build: apply the big-cartridge layout to skin.bin (bytes in, bytes out). Returns the patched bytes."""
    import badges
    import fauxji_layout as L
    k = bytearray(k)
    x, y = BIG_AT
    L.set_rect(k, FILM_GROUP, (x + 3, y + 3, 58, 58))
    for n in FILM_CHILDREN:
        L.set_rect(k, n, (-3, -3, badges.BIG_W, badges.BIG_H))
    hx0, hy0, hx1, hy1 = badges.BIG_HOLE
    L.set_rect(k, COUNT_GROUP, (x + hx0 + 1 - DIGIT_X0, y + hy0 + 2 - BAR_Y, 72, 25))
    return bytes(k)


def card_strings(blurbs):
    """{string id: text} for the film build: the 12 scene names -> film names, their descriptions -> blurbs (one per look)."""
    out = {}
    for card, sid in CARD_STRING.items():
        look = CARD_LOOK[card]
        out[sid] = LOOK_NAMES[look]
        out[sid + 1] = blurbs[look]
    return out


# Bleach Bypass's live-view preview. The live CCMatrix stage (0xC04463C4..) reads a matrix per colour slot from a 9-slot table (pool word
# 0xC0447174 -> 0xC07B3C40, 36 bytes a slot, slot = byte 1 of the 64-bit key it builds, `mla r7, slot, 0x24, table`); the stock firmware has
# no slot for FAUXJI's Bleach Bypass (style 9), which therefore previewed with slot 1, the black-and-white matrix. In the film build the
# table is copied to a 10-slot one in the dead region (slots 0-8 as FAUXJI patched them, slot 9 = Bleach Bypass's own capture matrix) and
# the style-9 case picks slot 9.
LIVE_POOL, LIVE_TABLE_STOCK = 0xC0447174, 0xC07B3C40
LIVE_KEY_SITE = 0xC04461BC + 16                # `orreq r0,r0,#0x100` of the style-9 case in the live default case (fauxji.LIVE_DEFAULT_NEW word 4)
LIVE_KEY_OLD, LIVE_KEY_NEW = 0x03800C01, 0x03800C09
BLEACH_STYLE = 9


def live_table(d, b, n):
    """(address, bytes) of the 10-slot live matrix table: the patched 9 slots + Bleach Bypass's matrix, in the dead region after block 1."""
    import fauxji
    at = (b + n + 3) & ~3
    tab = bytes(d[fauxji.LIVE - B:fauxji.LIVE - B + 36 * 9]) + struct.pack('<9i', *fauxji.fixed(fauxji.LOOKS[BLEACH_STYLE]))
    return at, tab


def _table(name):
    n = name.encode() + b'\0'
    f1 = ('%%s/%s' % name).encode() + b'\0'
    f2 = ('%%s/%s/100PHOTO' % name).encode() + b'\0'
    assert len(n) <= 16 and len(f1) <= 24 and len(f2) <= 32
    return n.ljust(16, b'\0') + f1.ljust(24, b'\0') + f2.ljust(32, b'\0')


def ldrb(rd, rn, off):
    return 0xE5D00000 | (rn << 16) | (rd << 12) | off


def ldrb_x(rd, rn, rm, cond=0xE):
    return (cond << 28) | 0x07D00000 | (rn << 16) | (rd << 12) | rm


def ldrsh0(rd, rn):
    return 0xE1D000F0 | (rn << 16) | (rd << 12)         # ldrsh rd, [rn]


def strb_x(rd, rn, rm):
    return 0xE7C00000 | (rn << 16) | (rd << 12) | rm


def cmp_rc(rn, rm, cond):
    return (cond << 28) | 0x01500000 | (rn << 16) | rm


def lsl2(rd, rm):
    return 0xE1A00100 | (rd << 12) | rm                     # mov rd, rm, lsl #2


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
                text_wind=b + TEXT_WIND, text_wound=b + TEXT_WOUND, text_use=b + TEXT_USE, text_full=b + TEXT_FULL,
                text_noplay=b + TEXT_NOPLAY, root_suffix=b + ROOT_SUFFIX, root_backup=b + ROOT_BACKUP, tab_look=b + TAB_LOOK, tab_id=b + TAB_ID, code=b + CODE_AT)


def helpers(b4=None, b=None, icon=0):
    """Shared routines (copy, valid, findobj, rollclamp, rawmode) in the R4 region: (bytes, labels)."""
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
    # ---- shots left: replaces `add sp,sp,#0x58` at the end of the camera's getRemainPhotoNum (r0 = shots left, the value the shooting
    # screen shows). In SCENE it becomes min(shots left, 36 - files in the roll), the file count being the DCF list's running total
    # [list+0x24] (the same number CSFileList::Open returned). A count that went up since the last look means a photo was just saved:
    # locked (wind on before the next one). Outside SCENE, or if any pointer on the way is not valid, r0 is untouched. lr, r1-r3 and ip
    # are free here (the epilogue pops the saved registers next).
    a.label('rollclamp')
    a.lit(R2, A['vars'])
    a.w(ldr(R1, R2, 4), cmp_i(R1, 0))
    a.b(EQ, 'cdone')
    a.w(push(0x0001))                                        # keep the stock number while the real mode is read
    a.b(AL, 'rawmode', link=True)                            # (a switch back to P: the stock number at once, not ours until the next shot)
    a.w(sub_i(R1, R0, SCENE_MODE), cmp_i(R1, SCENE_COUNT - 1))
    a.w(pop(0x0008))                                         # pop {r3} = the stock number (the flags stay)
    a.w(mov_r(R0, R3, HI))
    a.b(HI, 'cdone')                                         # not a scene card: r0 = stock
    a.lit(R2, A['vars'])
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
    a.w(push(0x0008))                                        # the stock number, kept over the call
    a.b(AL, icon, link=True)                                 # `iconlazy` in the other block (its address is passed in): a shot that locked the roll
                                                             # shows the wind-on icon at once
    a.w(pop(0x0008))
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
    # ---- the roll folder names: copy the template into the three buffers, write the look's four letters (vars[24]) and the roll
    # number (vars[16], 1-999) as three digits into each ("ACRO001", "%s/ACRO001", "%s/ACRO001/100PHOTO"); r7 = vars; clobbers r0-r3, ip
    a.label('setnames')
    a.w(push(0x4000))
    a.lit(R2, A['tab_film'])
    a.lit(R3, A['buf'])
    a.w(mov_i(R1, BUFSZ))
    a.b(AL, H['copy'], link=True)
    a.w(ldr(R0, R7, 24), lsl2(R0, R0))                       # the look's four letters (vars[24] = look): name, fmt1 (after "%s/"), fmt2
    a.lit(R2, A['tab_look'])
    a.w(dp_r(ADD, R2, R2, R0))
    a.lit(R3, A['buf'])
    for k in range(4):
        a.w(ldrb(R0, R2, k), strb(R0, R3, NAME_LET + k), strb(R0, R3, FMT1_AT + FMT_LET + k), strb(R0, R3, FMT2_AT + FMT_LET + k))
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
    for off in (NAME_DIG, FMT1_AT + FMT_DIG, FMT2_AT + FMT_DIG):
        a.w(strb(R1, R3, off), strb(R2, R3, off + 1), strb(R0, R3, off + 2))
    a.w(pop(0x8000))                                         # pop {pc}
    # ---- r0 = the DCF list (r4 = the CSFileList object, already validated by doswitch)
    a.label('getlist')
    a.w(ldr(R0, R4, 0x118), ldr(R0, R0, 0x10), MOV_PC_LR)
    # ---- make <root>/FILMS (r4 = object; clobbers r0-r3, ip): the card root string gets "/FILMS" appended for the call and is put back at once
    a.label('mkparent')
    a.w(push(0x4000))
    a.b(AL, 'getlist', link=True)
    a.w(add_i(R2, R0, ROOT_OFF), mov_i(R1, ROOT_SIZE))
    a.lit(R3, A['root_backup'])
    a.b(AL, H['copy'], link=True)
    a.b(AL, 'getlist', link=True)
    a.w(add_i(R0, R0, ROOT_OFF), mov_i(R1, 0))
    a.label('rlen')
    a.w(ldrb_x(R2, R0, R1), cmp_i(R2, 0))
    a.b(EQ, 'rfound')
    a.w(add_i(R1, R1, 1), cmp_i(R1, ROOT_MAXLEN))
    a.b(LO, 'rlen')
    a.b(AL, 'rdone')                                         # a root too long to extend: no parent (the roll folder is then made without it: the
                                                             # camera's creator fails and the scan finds nothing; the card root is never that long)
    a.label('rfound')
    a.lit(R3, A['root_suffix'])
    for k in range(7):                                       # "/FILMS" and its NUL after the root's last character
        a.w(ldrb(R2, R3, k), strb_x(R2, R0, R1), add_i(R1, R1, 1))
    a.b(AL, 'getlist', link=True)
    a.w(add_i(R1, R0, ROOT_OFF))
    a.b(AL, MKDIR, link=True)                                # the camera's own single-folder creator: list, path
    a.label('rdone')
    a.b(AL, 'getlist', link=True)                            # the root back as it was
    a.w(add_i(R3, R0, ROOT_OFF), mov_i(R1, ROOT_SIZE))
    a.lit(R2, A['root_backup'])
    a.b(AL, H['copy'], link=True)
    a.w(pop(0x8000))
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
    a.w(ldr(R8, R7, 4), str_(R6, R7, 4))                     # commit the new state (r8 = the old one), then the parent folder, the names, the rescan
    a.w(cmp_i(R6, 0))
    a.b(EQ, 'droot')                                         # leaving: nothing to make
    a.w(cmp_i(R8, 0))
    a.b(NE, 'droot')                                         # SCENE already on (a new roll, another film): the parent exists
    a.b(AL, 'mkparent', link=True)
    a.label('droot')
    a.w(cmp_i(R6, 0))
    a.b(NE, 'dfilm')
    a.lit(R2, A['tab_dcim'])                                 # leaving: the stock names
    a.lit(R3, A['buf'])
    a.w(mov_i(R1, BUFSZ))
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
    a.b(AL, 'setnames', link=True)
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
    a.b(AL, 'setnames', link=True)
    a.w(mov_r(R0, R4), mov_r(R1, R9))
    a.b(AL, OPEN, link=True)
    a.w(mov_r(R5, R0))
    a.label('ddone')
    a.w(mov_i(R0, 0), str_(R0, R7, 20), str_(R0, R7, 12))    # request cleared, unlocked (a loaded camera is ready for frame 1)
    a.w(str_(R5, R7, 8))                                     # files seen
    a.w(mov_i(R0, 1), pop(0x8000))
    a.label('dfail')
    a.w(mov_i(R0, 0), pop(0x8000))
    # ---- the mode icon spot (clobbers r0-r3, ip). iconfix = set it now, iconlazy = only when the wanted state differs from vars[28] (cheap enough for
    # the counter's hook). The wanted state follows the REAL mode: a scene card shows the look's cartridge tile (the look comes from the card, so the
    # tile is right on the first redraw after the dial moved, before the key hook has switched the roll), the wind-on icon while the roll is
    # locked, the roll-full icon while it is full. Any other mode: if we had set the spot, our children are hidden again (the stock draw ran first).
    a.label('iconlazy')
    a.w(mov_i(R0, 1))
    a.b(AL, 'iconcore')
    a.label('iconfix')
    a.w(mov_i(R0, 0))
    a.label('iconcore')
    a.w(push(0x41F0))                                        # push {r4-r8, lr}
    a.w(mov_r(R6, R0))                                       # r6 = 1: lazy
    a.b(AL, H['rawmode'], link=True)                         # r0 = the real mode
    a.w(mov_r(R8, R0), sub_i(R1, R0, SCENE_MODE), cmp_i(R1, SCENE_COUNT - 1))
    a.b(HI, 'icclean')
    a.lit(R2, A['tab_id'])
    a.w(ldrb_x(R5, R2, R1))                                  # r5 = the look of the card
    a.lit(R2, A['vars'])
    a.w(mov_i(R4, 2))                                        # the look's tile
    a.w(ldr(R3, R2, 4), cmp_i(R3, 0))
    a.b(EQ, 'ichave')                                        # the roll is not switched yet: the tile
    a.w(ldr(R3, R2, 12), cmp_i(R3, 0))
    a.b(NE, 'iclock')
    a.w(ldr(R3, R2, 8), cmp_i(R3, FRAMES))
    a.b(LO, 'ichave')
    a.w(lsr_i(IP, R3, 16), cmp_i(IP, 0))
    a.b(NE, 'ichave')                                        # a garbage count: the tile
    a.w(mov_i(R4, 1))                                        # full roll
    a.b(AL, 'ichave')
    a.label('iclock')
    a.w(mov_i(R4, 0))                                        # locked: wind on
    a.label('ichave')
    a.w(dp_r(ADD, R3, R5, R4, shift=0, amt=4), add_i(R3, R3, 1))     # code = state * 16 + look + 1
    a.w(ldr(IP, R2, 28), cmp_i(R6, 1), cmp_rc(R3, IP, EQ))
    a.b(EQ, 'icdone')                                        # lazy and nothing changed
    a.w(str_(R3, R2, 28))
    for g, (first, last, wind, full, tile) in enumerate(ICON_GROUPS):
        a.lit(R7, first)
        a.lit(R8, last + 1)
        a.label('ifl%d' % g)
        a.w(mov_r(R0, R7), mov_i(R1, 0), mov_i(R2, 0), mov_i(R3, 0))
        a.b(AL, OSD_VIS, link=True)                          # hide every child
        a.w(add_i(R7, R7, 1), cmp_r(R7, R8))
        a.b(LO, 'ifl%d' % g)
        a.lit(R0, tile)
        a.w(dp_r(ADD, R0, R0, R5))                           # tile = first tile + look
        a.lit(R1, wind)
        a.w(cmp_i(R4, 0), mov_r(R0, R1, EQ))
        a.lit(R1, full)
        a.w(cmp_i(R4, 1), mov_r(R0, R1, EQ), mov_i(R1, 1), mov_i(R2, 0), mov_i(R3, 0))
        a.b(AL, OSD_VIS, link=True)                          # show the icon
    a.label('icdone')
    a.w(pop(0x81F0))                                         # pop {r4-r8, pc}
    # not a scene card: put back what we changed (only our own children: the tiles, the wind-on child, the roll-full child if that was shown)
    a.label('icclean')
    a.lit(R2, A['vars'])
    a.w(ldr(R3, R2, 28), cmp_i(R3, 0))
    a.b(EQ, 'icdone')
    a.w(sub_i(R4, R3, 1), mov_i(R0, 0), str_(R0, R2, 28))
    a.w(lsr_i(R4, R4, 4))                                    # r4 = the state we had set
    for g, (first, last, wind, full, tile) in enumerate(ICON_GROUPS):
        a.lit(R7, tile)
        a.lit(R8, wind + 1)                                  # the twelve tiles and the wind-on child are consecutive
        a.label('icl%d' % g)
        a.w(mov_r(R0, R7), mov_i(R1, 0), mov_i(R2, 0), mov_i(R3, 0))
        a.b(AL, OSD_VIS, link=True)
        a.w(add_i(R7, R7, 1), cmp_r(R7, R8))
        a.b(LO, 'icl%d' % g)
        a.lit(R0, full)
        a.w(cmp_i(R4, 1), mov_i(R1, 0), mov_i(R2, 0), mov_i(R3, 0))
        a.b(NE, 'icn%d' % g)
        a.b(AL, OSD_VIS, link=True)                          # the roll-full child was shown: hide it
        a.label('icn%d' % g)
    a.w(pop(0x81F0))
    # ---- the end of every full redraw: replaces `add sp,sp,#0x14` (the stock epilogue pops {sl, fp, pc} next); the mode icon spot is set again
    a.label('filmdraw')
    a.w(add_i(13, 13, 0x14))
    a.b(AL, 'iconfix', link=True)                            # clobbers r0-r3, ip and lr only (the pop restores the rest)
    a.b(AL, DRAW_BACK)
    # ---- look-11 pop-up with a full icon redraw (the stock shots-left number is recalculated when it is redrawn)
    a.label('popup11')
    a.w(push(0x4000), mov_i(R0, LOOK_ON))
    a.b(AL, ui.ARM_NAME, link=True)
    a.w(mov_i(R0, 0))
    a.b(AL, ui.DRAW_ICONS, link=True)
    a.b(AL, 'iconfix', link=True)
    a.w(mov_i(R0, LOOK_ON))
    a.b(AL, ui.TOAST_CODE, link=True)
    a.w(pop(0x8000))
    # ---- apply the look r0 (PHOTO STYLE menu value) like the stock FILM SIM key does: setUiValue(0x41), apply, refresh the menu masks,
    # GUI event 0x42, the two notifications (tools/fauxji_ui.py film_routine; no name pop-up, the roll message follows); clobbers r0-r3, ip
    a.label('applylook')
    a.w(push(0x4010), mov_r(R4, R0), mov_i(R0, ui.PSS_ID), mov_r(R1, R4))
    a.b(AL, ui.SET_UI, link=True)
    a.w(mov_i(R0, ui.PSS_ID), mov_r(R1, R4))
    a.b(AL, ui.APPLY, link=True)
    a.b(AL, ui.REFRESH_MASKS, link=True)
    a.w(mov_i(R0, 0x42), mov_i(R1, 0))
    a.b(AL, ui.GUI_EVENT, link=True)
    a.w(mov_i(R0, ui.PSS_ID))
    a.b(AL, ui.NOTIFY1, link=True)
    a.w(mov_i(R0, ui.PSS_ID))
    a.b(AL, ui.NOTIFY2, link=True)
    a.w(pop(0x8010))                                         # pop {r4, pc}
    # ---- "ACRO001 nn left" for r5 files in the roll (0 left for a full roll or a failed scan); clobbers r0-r3, ip
    a.label('msgleft')
    a.w(push(0x4000))
    a.lit(R2, A['text_on'])
    a.lit(R3, SLOT0)
    a.w(mov_i(R1, 32))
    a.b(AL, H['copy'], link=True)
    a.lit(R2, A['buf'])
    for k in range(7):                                       # the roll's name (after "FILMS/"), as UTF-16
        a.w(ldrb(R0, R2, NAME_LET + k), strh(R0, R3, 2 * k))
    a.w(cmp_i(R5, FRAMES), mov_i(R5, FRAMES, HI))
    a.w(mov_i(R0, FRAMES), dp_r(SUB, R0, R0, R5), mov_i(R2, 0x30))
    a.label('ltens')
    a.w(cmp_i(R0, 10), sub_i(R0, R0, 10, GE), add_i(R2, R2, 1, GE))
    a.b(GE, 'ltens')
    a.w(strh(R2, R3, 16), add_i(R0, R0, 0x30), strh(R0, R3, 18))
    a.b(AL, 'popup11', link=True)
    a.w(pop(0x8000))
    # ---- film-themed "roll full". Replaces `mov r2,r0` at the entry of GetStaticString (r0 = context, r1 = id): in SCENE the id of "Memory Full" (687)
    # returns our own text; everything else falls through to the stock code (leaf function: r2, r3 and ip are free).
    a.label('filmstr')
    a.lit(IP, STR_MEMFULL)
    a.w(cmp_r(R1, IP))
    a.b(NE, 'sorig')
    a.lit(IP, A['vars'])
    a.w(ldr(IP, IP, 4), cmp_i(IP, 0))
    a.b(EQ, 'sorig')
    a.lit(R0, A['text_full'])
    a.w(MOV_PC_LR)
    a.label('sorig')
    a.w(mov_r(R2, R0))                                       # the replaced instruction
    a.b(AL, STR_BACK)
    # ---- SCENE reads as P. Replaces `ldr r0,[sp]` at the end of GET_SYSVAL (fp = the index, [sp] = the value it fetched): for index 3 (the
    # shooting mode) the value 10 (SCENE) becomes 2 (P), so the exposure program (1/60 floor, auto ISO, bias), the menus and the screens all
    # behave as in P. Everything else is passed through; only r0 and the flags change.
    a.label('filmget')
    a.w(ldr(R0, 13, 0), cmp_i(11, 3))
    a.b(NE, 'gvback')
    a.w(cmp_i(R0, SCENE_MODE))
    a.b(LO, 'gvback')
    a.w(cmp_i(R0, SCENE_MODE + SCENE_COUNT), mov_i(R0, MODE_P, LO))                     # any scene card (10..22) reads as P; flags only, no scratch register
    a.label('gvback')
    a.b(AL, GETVAL_BACK)
    # ---- entry: replaces `bl key_call`; r0 = key, r1 = state, lr = back into the dispatcher
    a.label('filmhook')
    a.w(push(0x47FF))                                        # push {r0-r10, lr}
    a.b(AL, H['rawmode'], link=True)                         # the real shooting mode (the camera's own reads see SCENE as P)
    a.w(sub_i(R1, R0, SCENE_MODE), cmp_i(R1, SCENE_COUNT - 1), mov_i(R6, 0), mov_i(R6, 1, LS))   # r6 = want film mode (any of the 13 scene cards)
    # The live-view state object (fp = r11 in the dispatcher) caches the shooting mode at +0xC, and the direction-key handlers (0xC04C0424 flash
    # etc., 0xC04C0554, 0xC04C05DC, 0xC04C0628: macro, flash, self-timer, display) only act when it is 2..5 (P, A, S, M) or 6: a scene card (10..22)
    # locked them. In a scene card the cache is made 2 (P) before the dispatcher goes on, as every other read of the mode already is.
    a.w(cmp_i(R6, 0))
    a.b(EQ, 'nofix')
    a.w(ldr(R2, 11, 12), sub_i(R3, R2, SCENE_MODE), cmp_i(R3, SCENE_COUNT - 1), mov_i(R3, MODE_P, LS), str_c(R3, 11, 12, LS))
    a.label('nofix')
    a.lit(R7, A['vars'])
    a.lit(R2, A['tab_id'])
    a.w(mov_i(R8, 0), cmp_i(R6, 0), ldrb_x(R8, R2, R1, NE))  # r8 = the look the chosen card stands for
    a.w(ldr(R2, R7, 4), cmp_r(R2, R6))
    a.b(NE, 'change')
    a.w(cmp_i(R6, 0))
    a.b(EQ, 'plain')                                         # no change: the common case, a handful of instructions
    a.w(ldr(R3, R7, 24), cmp_r(R3, R8))
    a.b(EQ, 'plain')                                         # same card as before
    a.label('change')                                        # entering SCENE, leaving it, or a different card (= a different film)
    a.w(mov_i(R2, 0), str_(R2, R7, 20))                      # no new-roll request
    a.w(cmp_i(R6, 0), str_c(R8, R7, 24, NE), str_c(R2, R7, 16, NE))   # a film: its look, and its roll count starts from the first roll
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
    a.w(ldr(R0, R7, 24))
    a.b(AL, 'applylook', link=True)                          # the camera's film look = the chosen card's
    a.b(AL, 'msgleft', link=True)
    a.label('fpop')
    a.w(pop(0x47FF))
    a.b(AL, ui.KEY_CALL[1])                                  # pop-up shown: skip the stock key hook (it would hide the box again)
    a.label('plain')
    a.w(pop(0x47FF))
    a.b(AL, ui.KEYHOOK)                                      # the stock key hook, which ends in the original call
    # ---- no playback in SCENE: replaces the entry of the state-change function (r0 = fsm, r1 = the requested state id). Playback (5) is dropped
    # with a "No playback" pop-up (the call returns 0); every other request, and every request outside SCENE, runs the stock function.
    a.label('filmstate')                                     # r2 / r3 / the stack are arguments: only ip is touched before the stock code
    a.lit(IP, A['vars'])
    a.w(ldr(IP, IP, 4), cmp_i(IP, 0))
    a.b(EQ, 'storig')
    a.w(cmp_i(R1, STATE_PLAYBACK))
    a.b(NE, 'storig')
    a.label('sdrop')
    a.w(push(0x47FF))
    a.lit(R2, A['text_noplay'])
    a.lit(R3, SLOT1)
    a.w(mov_i(R1, 32))
    a.b(AL, H['copy'], link=True)
    a.w(mov_i(R0, LOOK_MSG))
    a.b(AL, ui.ARM_NAME, link=True)
    a.w(mov_i(R0, LOOK_MSG))
    a.b(AL, ui.TOAST_CODE, link=True)
    a.w(pop(0x47FF), mov_i(R0, 0), MOV_PC_LR)
    a.label('storig')
    a.w(STATE_STOCK)                                         # the replaced instruction: push {r4-r8, sb, sl, fp, lr}
    a.b(AL, STATE_BACK)
    # ---- the PLAY event: replaces the entry of the handler 0xC0494984 (r0 = state, r1 = event; the event's method +8 returns its type). In SCENE an
    # event of type 0x11 (PLAY) is dropped with the "No playback" pop-up (returns 0); anything else runs the handler.
    a.label('filmevent')
    a.lit(IP, A['vars'])
    a.w(ldr(IP, IP, 4), cmp_i(IP, 0))
    a.b(EQ, 'eorig')
    a.w(push(0x401F), mov_r(R4, R1))                         # push {r0-r4, lr}: r2 / r3 stay as the caller left them
    a.w(ldr(R2, R4, 0), add_i(R2, R2, 8), ldr(IP, R2, 4), ldrsh0(R0, R2), dp_r(ADD, R0, R4, R0), mov_r(LR, PC), mov_r(PC, IP))
    a.w(cmp_i(R0, EVENT_PLAY), pop(0x401F))                  # (pop keeps the flags)
    a.b(EQ, 'sdrop')
    a.label('eorig')
    a.w(EVENT_STOCK)                                         # the replaced instruction: push {r4-r8, sb, sl, fp, lr}
    a.b(AL, EVENT_BACK)
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
    a.b(EQ, 'gstop')                                         # empty roll: nothing to do (the film is the scene card's)
    a.w(lsr_i(IP, R3, 16), cmp_i(IP, 0))                     # (ip, not r1: r0 / r1 must reach the stock call intact)
    a.b(NE, 'gstop')                                         # garbage count: swallowed too
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
    a.label('gstop')                                         # swallowed: the film is chosen with the mode dial, AE-L only reloads
    a.w(mov_i(R0, 0), MOV_PC_LR)
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
    a.b(AL, 'iconfix', link=True)
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
    a.w(mov_i(R0, 0))
    a.b(AL, ui.DRAW_ICONS, link=True)                        # the stock tile back ...
    a.b(AL, 'iconfix', link=True)                            # ... or the roll-full icon
    a.lit(R2, A['vars'])
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
    H0 = helpers(b4, b)[1]                                       # first pass: the helpers' own labels (the call into the code block is patched next)
    c, labels = code(b, H0)
    hbytes, H = helpers(b4, b, labels['iconlazy'])
    assert H == H0 and len(hbytes) == len(helpers(b4, b)[0])
    out = bytearray(CODE_AT)
    out[BUF:BUF + BUFSZ] = _table('DCIM')
    out[TAB_DCIM:TAB_DCIM + BUFSZ] = _table('DCIM')
    out[TAB_FILM:TAB_FILM + BUFSZ] = _table('FILMS/AAAA000')
    out[TAB_LOOK:TAB_LOOK + 44] = ''.join(LOOK_CODES).encode()
    for card, look in CARD_LOOK.items():
        out[TAB_ID + card - SCENE_MODE] = look
    out[TEXT_ON:TEXT_ON + 32] = _utf16('AAAAAAA 00 left', 32)
    out[TEXT_OFF:TEXT_OFF + 20] = _utf16('Film off', 20)
    out[TEXT_WIND:TEXT_WIND + 20] = _utf16('Wind on >', 20)
    out[TEXT_WOUND:TEXT_WOUND + 12] = _utf16('Wound', 12)
    out[TEXT_USE:TEXT_USE + 24] = _utf16('Roll in use', 24)
    out[TEXT_FULL:TEXT_FULL + 48] = _utf16(TEXT_FULL_STR, 48)
    out[TEXT_NOPLAY:TEXT_NOPLAY + 32] = _utf16('No playback', 32)
    out[ROOT_SUFFIX:ROOT_SUFFIX + 8] = PARENT
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
    import fauxji
    if struct.unpack_from('<I', d, LIVE_POOL - B)[0] == LIVE_TABLE_STOCK:        # first time: copy the stock-patched live table
        tab_at, tab = live_table(d, b, len(data))
    else:                                                                       # already patched: the pool word holds the address
        tab_at = struct.unpack_from('<I', d, LIVE_POOL - B)[0]
        tab = bytes(d[tab_at - B:tab_at - B + 360])
    assert tab_at + len(tab) <= FILM_END, hex(tab_at + len(tab))
    d[tab_at - B:tab_at - B + len(tab)] = tab
    struct.pack_into('<I', d, LIVE_POOL - B, tab_at)
    assert struct.unpack_from('<I', d, LIVE_KEY_SITE - B)[0] in (LIVE_KEY_OLD, LIVE_KEY_NEW), 'live default case changed'
    struct.pack_into('<I', d, LIVE_KEY_SITE - B, LIVE_KEY_NEW)                    # Bleach Bypass previews with its own slot
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
    assert struct.unpack_from('<I', d, STR_SITE - B)[0] in (STR_STOCK, ui._b(STR_SITE, labels['filmstr'])), hex(STR_SITE)
    struct.pack_into('<I', d, STR_SITE - B, ui._b(STR_SITE, labels['filmstr']))          # "Memory Full" reads as the roll-full text in SCENE
    assert struct.unpack_from('<I', d, STATE_SITE - B)[0] in (STATE_STOCK, ui._b(STATE_SITE, labels['filmstate'])), hex(STATE_SITE)
    struct.pack_into('<I', d, STATE_SITE - B, ui._b(STATE_SITE, labels['filmstate']))     # no playback in SCENE
    assert struct.unpack_from('<I', d, EVENT_SITE - B)[0] in (EVENT_STOCK, ui._b(EVENT_SITE, labels['filmevent'])), hex(EVENT_SITE)
    struct.pack_into('<I', d, EVENT_SITE - B, ui._b(EVENT_SITE, labels['filmevent']))     # PLAY does nothing in SCENE
    assert struct.unpack_from('<I', d, DRAW_END - B)[0] in (DRAW_END_STOCK, ui._b(DRAW_END, labels['filmdraw'])), hex(DRAW_END)
    struct.pack_into('<I', d, DRAW_END - B, ui._b(DRAW_END, labels['filmdraw']))      # the mode icon spot after every full redraw
    clamp = labels['rollclamp']                                    # shots left: min(stock, 36 - files in the roll) while in SCENE
    assert struct.unpack_from('<I', d, ROLL_SITE - B)[0] in (ROLL_STOCK, ui._b(ROLL_SITE, clamp)), hex(ROLL_SITE)
    struct.pack_into('<I', d, ROLL_SITE - B, ui._b(ROLL_SITE, clamp))
    return bytes(d)

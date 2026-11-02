"""FAUXJI UI features in the TL500 program: AE-L button cycles favourite film looks.

Key handling (live-view state dispatcher 0xC04C18CC, switch on the logical key):
key 0 -> AE-lock handler 0xC04C1414 (UI value 0x63), key 14 -> AF-lock handler
0xC04C1624 (UI value 0x64). The "AE-L Button" setting picks which logical key the
button sends, so its AF-L option is repurposed as FILM SIM: key 14's case calls the
routine below instead of the AF-lock handler.

The routine copies the menu's own commit sequence for a setting (seen in the menu
handler around 0xC050C494): setUiValue(0x41 = Photo Style, v) -> apply 0xC04D2A18 ->
menu-disable refresh 0xC04D2000 -> GUI event 0x42 -> 0xC04DC174(id) -> 0xC04CDB70(id).
Photo Style menu values are quick-menu positions (0 PROVIA, 1 Bleach Bypass,
2 Nostalgic Neg., 3 ASTIA, 4 Velvia, 5 Reala Ace, 6 Classic Chrome, 7 Classic Neg.,
8 Eterna, 9 ACROS, 10 Sepia); the cached value is at 0xC0D7F300+0x40.
The menu sequence doesn't touch the live-view icons (leaving the menu re-enters the
live-view state, whose onEnter 0xC049FAF0 redraws them), so the routine then calls the
redraw-all-icons loop 0xC04B7444 itself (WB850F's CAPPGUIPreviewView::drawViewfinderIcon).
GUI events don't help: the live-view GUI handler 0xC049F1CC only redraws fixed items,
and the handlers that answer events 2 / 0x42 with a full redraw belong to other states
(0x42: CAPPGUIPictbridgeState). Item 7 (GUI value 0x47 = UI 0x41) is the film icon;
its draw 0xC04B9C3C shows child v of the OSD item, hiding the old child first.

Also: the Photo-Style apply function 0xC04D1538 forces settings for Sketch (1) and
Defog (2): photo size >= index 5 (the Bleach Bypass 5 MP) and two more minimums;
those three checks are pointed at an impossible value.
"""
import struct

B = 0xC0003FF5
FILM_CODE = 0xC0425FA0          # tail of the factory-only BATTERY.CSV function (after the PCSE tables)
FILM_END = 0xC04260A0
KEY14_CALL = (0xC04C1AE8, 0xC04C1624)   # `bl 0xC04C1624` in key 14's case
UI_CACHE = 0xC0D7F300
PSS_ID = 0x41
SET_UI, APPLY, REFRESH_MASKS, GUI_EVENT, NOTIFY1, NOTIFY2 = \
    0xC048F630, 0xC04D2A18, 0xC04D2000, 0xC048FD5C, 0xC04DC174, 0xC04CDB70
DRAW_ICONS = 0xC04B7444         # redraw every icon of the current live-view list

#            PROVIA Chrome Velvia ASTIA ClassicNeg ACROS Nostalgic
FAVOURITES = [0,    6,     4,     3,    7,         9,    2]

SKETCH_RULES = [(0xC04D15BC, 0xE35B0001, 0xE35B00FF),   # cmp fp,#1: size >= 5 for Sketch
                (0xC04D1608, 0xE35B0001, 0xE35B00FF),   # cmp fp,#1 } +0x6C >= 3, +0x70 >= 7
                (0xC04D1610, 0xE35B0002, 0xE35B00FF)]   # cmp fp,#2 } for Sketch / Defog


def _b(src, dst, cond=0xE, link=False):
    return (cond << 28) | ((0xB if link else 0xA) << 24) | (((dst - (src + 8)) >> 2) & 0xFFFFFF)


def film_routine():
    a = FILM_CODE
    EQ, NE = 0x0, 0x1
    w = {}
    pc = lambda k: a + 4 * k
    code = [0xE92D4010,        # 0  push {r4, lr}
            0xE5913000,        # 1  ldr r3,[r1]           event vtable
            0xE2832010,        # 2  add r2,r3,#0x10
            0xE592C004,        # 3  ldr ip,[r2,#4]
            0xE1D230F0,        # 4  ldrsh r3,[r2]
            0xE0810003,        # 5  add r0,r1,r3
            0xE1A0E00F,        # 6  mov lr,pc
            0xE1A0F00C,        # 7  mov pc,ip            "is this a press?" (as the stock handlers)
            0xE3500001,        # 8  cmp r0,#1
            None,              # 9  bne done
            None,              # 10 ldr r3,=UI_CACHE
            0xE5930040,        # 11 ldr r0,[r3,#0x40]   current Photo Style
            None,              # 12 add r2,pc,#FAV
            0xE3A01000,        # 13 mov r1,#0
            0xE7D2C001,        # 14 loop: ldrb ip,[r2,r1]
            0xE35C00FF,        # 15 cmp ip,#0xff
            None,              # 16 beq first
            0xE15C0000,        # 17 cmp ip,r0
            None,              # 18 beq found
            0xE2811001,        # 19 add r1,r1,#1
            None,              # 20 b loop
            0xE2811001,        # 21 found: add r1,r1,#1
            0xE7D24001,        # 22 ldrb r4,[r2,r1]
            0xE35400FF,        # 23 cmp r4,#0xff
            None,              # 24 bne have
            0xE5D24000,        # 25 first: ldrb r4,[r2]
            0xE3A00041,        # 26 have: mov r0,#0x41
            0xE1A01004,        # 27 mov r1,r4
            None,              # 28 bl setUiValue
            0xE3A00041,        # 29 mov r0,#0x41
            0xE1A01004,        # 30 mov r1,r4
            None,              # 31 bl apply
            None,              # 32 bl refresh menu masks
            0xE3A00042,        # 33 mov r0,#0x42
            0xE3A01000,        # 34 mov r1,#0
            None,              # 35 bl GUI event
            0xE3A00041,        # 36 mov r0,#0x41
            None,              # 37 bl notify1
            0xE3A00041,        # 38 mov r0,#0x41
            None,              # 39 bl notify2
            None,              # 40 bl redraw live-view icons
            0xE3A00000,        # 41 done: mov r0,#0
            0xE8BD8010]        # 42 pop {r4, pc}
    lit, fav = pc(43), pc(44)
    code[9] = _b(pc(9), pc(41), NE)
    code[10] = 0xE59F3000 | (lit - (pc(10) + 8))
    code[12] = 0xE28F2000 | (fav - (pc(12) + 8))
    code[16] = _b(pc(16), pc(25), EQ)
    code[18] = _b(pc(18), pc(21), EQ)
    code[20] = _b(pc(20), pc(14))
    code[24] = _b(pc(24), pc(26), NE)
    code[28] = _b(pc(28), SET_UI, link=True)
    code[31] = _b(pc(31), APPLY, link=True)
    code[32] = _b(pc(32), REFRESH_MASKS, link=True)
    code[35] = _b(pc(35), GUI_EVENT, link=True)
    code[37] = _b(pc(37), NOTIFY1, link=True)
    code[39] = _b(pc(39), NOTIFY2, link=True)
    code[40] = _b(pc(40), DRAW_ICONS, link=True)
    out = b''.join(struct.pack('<I', x) for x in code) + struct.pack('<I', UI_CACHE)
    out += bytes(FAVOURITES) + b'\xff'
    out += b'\0' * (-len(out) % 4)
    assert a + len(out) <= FILM_END
    return out


def patch(d):
    d = bytearray(d)
    code = film_routine()
    d[FILM_CODE - B:FILM_CODE - B + len(code)] = code
    site, old_target = KEY14_CALL
    cur = struct.unpack_from('<I', d, site - B)[0]
    assert cur in (_b(site, old_target, link=True), _b(site, FILM_CODE, link=True))
    struct.pack_into('<I', d, site - B, _b(site, FILM_CODE, link=True))
    for addr, old, new in SKETCH_RULES:
        assert struct.unpack_from('<I', d, addr - B)[0] in (old, new), hex(addr)
        struct.pack_into('<I', d, addr - B, new)
    return bytes(d)

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

# Name pop-up: the live-view help-text box (frame 0xCE12A81D, 0x49032BE5, text 0x96879B21)
TOAST_CODE = 0xC0426810         # tail of the factory E2PR.CSV function, after the matrices
TOAST_END = 0xC042689C
TOAST_NODES = (0xCE12A81D, 0x49032BE5, 0x96879B21)
STRING_CTX = 0xC0CA6C90
GET_STRING, OSD_SET_UNICODE_TEXT, OSD_TEXT_PROPERTY, OSD_SET_VISIBLE = \
    0xC05BA87C, 0xC0201488, 0xC0202004, 0xC0201CAC
#               PROVIA Bleach Nostalgic ASTIA Velvia Reala Chrome Neg. Eterna ACROS Sepia
NAME_STRINGS = [182,   911,   986,      183,  184,   185,  186,   187, 188,   189,  190]

# PROVIA's live-view icon: the film item (7) draws child v of its OSD node but hides the
# node for v = 0 (Samsung shows no icon for Standard). Child 0 is the STD canister.
PROVIA_SHOW = (0xC04B9C48, 0x0A000004, 0xE1A00000)   # beq hide -> nop

# The help-text box is item 44 of the live-view list; its draw 0xC04B7BB8 runs on every
# full redraw and on GUI event 0xC (value = Help Text setting), which wiped the name.
# So item 44's table entry points at a wrapper: while NAME_FLAG holds look+1 it draws the
# name instead. The live-view key dispatcher's first call (0xC04C1938, `bl 0xC04DE310`
# with r0 = key) goes through a hook that, for any key but 14 (FILM SIM), clears the flag
# and hides the box with the stock draw(0). All in the factory-only "ChineseCheck
# Adjustment" function 0xC042620C (called only from the factory command switch at
# 0xC0427870, like the E2PR.CSV function).
EXTRA_CODE, EXTRA_END = 0xC042620C, 0xC0426438
NAME_FLAG = EXTRA_CODE
WRAP44 = EXTRA_CODE + 4
KEYHOOK = EXTRA_CODE + 24
ITEM44_ENTRY = (0xC09BDF84, 0xC04B7BB8)       # viewfinder item table, item 44's draw
ITEM44_DRAW = 0xC04B7BB8
KEY_CALL = (0xC04C1938, 0xC04DE310)           # `bl 0xC04DE310` at the dispatcher's start
FILM_KEY = 14
# 2-second hide: the control timer service start(id, ms, cb, arg) 0xC048F3EC / cancel(id)
# 0xC048F37C sits on the OS timers (ids 0-39; 0-24 control, 25, 27, 38, 39 taken). Stock
# callback 0xC048F4E4 posts a timer event (class 0xC0759C48, id = arg) to the control app;
# the live-view state's handler 0xC04C1F04 passes those to 0xC04BF54C (switch on id
# < 0x19), in the same task as the key dispatcher. A hook on that call takes id 30.
NAME_TIMER, NAME_MS = 30, 2000
TIMER_START, TIMER_CANCEL, TIMER_POST = 0xC048F3EC, 0xC048F37C, 0xC048F4E4
TIMER_CALL = (0xC04C2188, 0xC04BF54C)
ARM_NAME = KEYHOOK + 48
TIMERHOOK = ARM_NAME + 40

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
            0xE1A00004,        # 40 mov r0,r4
            None,              # 41 bl arm_name: name shows until a key or 2 s
            0xE1A00000,        # 42 nop
            None,              # 43 bl redraw live-view icons
            0xE1A00004,        # 44 mov r0,r4
            None,              # 45 bl toast (look's name in the help-text box)
            0xE3A00000,        # 46 done: mov r0,#0
            0xE8BD8010]        # 47 pop {r4, pc}
    lit, fav = pc(48), pc(49)
    code[9] = _b(pc(9), pc(46), NE)
    code[41] = _b(pc(41), ARM_NAME, link=True)
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
    code[43] = _b(pc(43), DRAW_ICONS, link=True)
    code[45] = _b(pc(45), TOAST_CODE, link=True)
    out = b''.join(struct.pack('<I', x) for x in code) + struct.pack('<I', UI_CACHE)
    out += bytes(FAVOURITES) + b'\xff'
    out += b'\0' * (-len(out) % 4)
    return out


def toast_data_addr():
    return FILM_CODE + len(film_routine())


def toast_data():
    """Name string index per menu value, then the help-box nodes to show (0-ended)."""
    out = struct.pack('<%dH' % len(NAME_STRINGS), *NAME_STRINGS)
    out += b'\0' * (-len(out) % 4)
    return out + struct.pack('<4I', *TOAST_NODES, 0)


def toast_routine():
    """toast(v): put the look's name in the live-view help-text box and show it, as the
    stock mode-description item (0xC04B7BB8) does with the mode's description."""
    a = TOAST_CODE
    pc = lambda k: a + 4 * k
    names = toast_data_addr()
    nodes = names + len(toast_data()) - 16
    code = [0xE92D4010,        # 0  push {r4, lr}
            0xE1A04000,        # 1  mov r4,r0
            None,              # 2  ldr r0,=TEXT node
            0xE3A01041,        # 3  mov r1,#0x41        text property, as stock (left-to-right)
            0xE3A02000,        # 4  mov r2,#0
            0xE3A03000,        # 5  mov r3,#0
            None,              # 6  bl osd text property
            None,              # 7  ldr r0,=string-manager context
            0xE5900000,        # 8  ldr r0,[r0]
            None,              # 9  ldr r1,=names
            0xE0811084,        # 10 add r1,r1,r4,lsl #1
            0xE1D110B0,        # 11 ldrh r1,[r1]
            None,              # 12 bl StringMgr_GetStaticString  -> current-language text
            0xE1A01000,        # 13 mov r1,r0
            None,              # 14 ldr r0,=TEXT node
            0xE3A02000,        # 15 mov r2,#0
            0xE3A03000,        # 16 mov r3,#0
            0xE92D000C,        # 17 push {r2, r3}        5th/6th strings: none
            None,              # 18 bl osd_set_unicode_text
            0xE28DD008,        # 19 add sp,sp,#8
            None,              # 20 ldr r4,=nodes
            0xE4940004,        # 21 loop: ldr r0,[r4],#4
            0xE3500000,        # 22 cmp r0,#0
            0x08BD8010,        # 23 popeq {r4, pc}
            0xE3A01001,        # 24 mov r1,#1
            0xE3A02001,        # 25 mov r2,#1
            0xE3A03000,        # 26 mov r3,#0
            None,              # 27 bl osd_set_item_visible
            None]              # 28 b loop
    lits = [TOAST_NODES[2], STRING_CTX, names, nodes]
    L = lambda i: pc(len(code) + i)
    ldr = lambda k, reg, i: 0xE59F0000 | (reg << 12) | (L(i) - (pc(k) + 8))
    code[2], code[14] = ldr(2, 0, 0), ldr(14, 0, 0)
    code[7], code[9], code[20] = ldr(7, 0, 1), ldr(9, 1, 2), ldr(20, 4, 3)
    code[6] = _b(pc(6), OSD_TEXT_PROPERTY, link=True)
    code[12] = _b(pc(12), GET_STRING, link=True)
    code[18] = _b(pc(18), OSD_SET_UNICODE_TEXT, link=True)
    code[27] = _b(pc(27), OSD_SET_VISIBLE, link=True)
    code[28] = _b(pc(28), pc(21))
    out = b''.join(struct.pack('<I', x) for x in code + lits)
    assert a + len(out) <= TOAST_END
    return out


def _ldr_pc(src, reg, target, store=False):
    """ldr/str reg,[pc,#+-off] addressing `target` from the instruction at `src`."""
    off = target - (src + 8)
    base = 0xE50F0000 if store else 0xE51F0000          # P=1, W=0, U=0 (subtract)
    if off >= 0:
        base |= 1 << 23
    return base | (reg << 12) | abs(off)


def extra_routines():
    """NAME_FLAG, the item-44 wrapper and the key hook (see EXTRA_CODE)."""
    out = struct.pack('<I', 0)                          # NAME_FLAG: 0 = no name showing
    a = WRAP44
    wrap = [_ldr_pc(a, 2, NAME_FLAG),                   # ldr r2,NAME_FLAG
            0xE3520000,                                 # cmp r2,#0
            _b(a + 8, ITEM44_DRAW, cond=0x0),           # beq stock draw (help text)
            0xE2420001,                                 # sub r0,r2,#1   look
            _b(a + 16, TOAST_CODE)]                     # b toast        (returns to caller)
    out += b''.join(struct.pack('<I', x) for x in wrap)
    a = KEYHOOK
    pc = lambda k: a + 4 * k
    hook = [0xE92D4013,                                 # 0 push {r0, r1, r4, lr}
            0xE3500000 | FILM_KEY,                      # 1 cmp r0,#14
            None,                                       # 2 beq skip
            None,                                       # 3 ldr r2,NAME_FLAG
            0xE3520000,                                 # 4 cmp r2,#0
            None,                                       # 5 beq skip
            0xE3A02000,                                 # 6 mov r2,#0
            None,                                       # 7 str r2,NAME_FLAG
            0xE3A00000,                                 # 8 mov r0,#0
            None,                                       # 9 bl stock item-44 draw(0): hide
            0xE8BD4013,                                 # 10 skip: pop {r0, r1, r4, lr}
            None]                                       # 11 b original call
    hook[2] = _b(pc(2), pc(10), cond=0x0)
    hook[3] = _ldr_pc(pc(3), 2, NAME_FLAG)
    hook[5] = _b(pc(5), pc(10), cond=0x0)
    hook[7] = _ldr_pc(pc(7), 2, NAME_FLAG, store=True)
    hook[9] = _b(pc(9), ITEM44_DRAW, link=True)
    hook[11] = _b(pc(11), KEY_CALL[1])
    out += b''.join(struct.pack('<I', x) for x in hook)
    a = ARM_NAME
    pc = lambda k: a + 4 * k
    arm = [0xE92D4010,                                  # 0 push {r4, lr}
           0xE2800001,                                  # 1 add r0,r0,#1
           _ldr_pc(pc(2), 0, NAME_FLAG, store=True),    # 2 str r0,NAME_FLAG
           0xE3A00000 | NAME_TIMER,                     # 3 mov r0,#30
           0xE3A01E7D,                                  # 4 mov r1,#2000
           None,                                        # 5 ldr r2,=post callback
           0xE3A03000 | NAME_TIMER,                     # 6 mov r3,#30
           None,                                        # 7 bl timer start
           0xE8BD8010,                                  # 8 pop {r4, pc}
           TIMER_POST]                                  # 9 literal
    arm[5] = _ldr_pc(pc(5), 2, pc(9))
    arm[7] = _b(pc(7), TIMER_START, link=True)
    assert NAME_MS == 0x7D << 4
    out += b''.join(struct.pack('<I', x) for x in arm)
    a = TIMERHOOK
    pc = lambda k: a + 4 * k
    th = [0xE92D4013,                                   # 0 push {r0, r1, r4, lr}
          0xE5913000,                                   # 1 ldr r3,[r1]      event vtable
          0xE2832008,                                   # 2 add r2,r3,#8
          0xE592C004,                                   # 3 ldr ip,[r2,#4]
          0xE1D230F0,                                   # 4 ldrsh r3,[r2]
          0xE0810003,                                   # 5 add r0,r1,r3
          0xE1A0E00F,                                   # 6 mov lr,pc
          0xE1A0F00C,                                   # 7 mov pc,ip        timer id
          0xE3500000 | NAME_TIMER,                      # 8 cmp r0,#30
          0x18BD4013,                                   # 9 popne {r0, r1, r4, lr}
          None,                                         # 10 bne stock handler
          0xE3A00000 | NAME_TIMER,                      # 11 mov r0,#30
          None,                                         # 12 bl timer cancel
          None,                                         # 13 ldr r2,NAME_FLAG
          0xE3520000,                                   # 14 cmp r2,#0
          0x08BD8013,                                   # 15 popeq {r0, r1, r4, pc}
          0xE3A02000,                                   # 16 mov r2,#0
          None,                                         # 17 str r2,NAME_FLAG
          0xE3A00000,                                   # 18 mov r0,#0
          None,                                         # 19 bl stock item-44 draw(0): hide
          0xE8BD8013]                                   # 20 pop {r0, r1, r4, pc}
    th[10] = _b(pc(10), TIMER_CALL[1], cond=0x1)
    th[12] = _b(pc(12), TIMER_CANCEL, link=True)
    th[13] = _ldr_pc(pc(13), 2, NAME_FLAG)
    th[17] = _ldr_pc(pc(17), 2, NAME_FLAG, store=True)
    th[19] = _b(pc(19), ITEM44_DRAW, link=True)
    out += b''.join(struct.pack('<I', x) for x in th)
    assert EXTRA_CODE + len(out) <= EXTRA_END
    return out


def patch(d):
    d = bytearray(d)
    code = film_routine()
    code += toast_data()
    assert FILM_CODE + len(code) <= FILM_END
    d[FILM_CODE - B:FILM_CODE - B + len(code)] = code
    t = toast_routine()
    d[TOAST_CODE - B:TOAST_CODE - B + len(t)] = t
    addr, old, new = PROVIA_SHOW
    assert struct.unpack_from('<I', d, addr - B)[0] in (old, new), hex(addr)
    struct.pack_into('<I', d, addr - B, new)
    x = extra_routines()
    d[EXTRA_CODE - B:EXTRA_CODE - B + len(x)] = x
    entry, stock = ITEM44_ENTRY
    assert struct.unpack_from('<I', d, entry - B)[0] in (stock, WRAP44)
    struct.pack_into('<I', d, entry - B, WRAP44)
    site, target = KEY_CALL
    assert struct.unpack_from('<I', d, site - B)[0] in (_b(site, target, link=True),
                                                          _b(site, KEYHOOK, link=True))
    struct.pack_into('<I', d, site - B, _b(site, KEYHOOK, link=True))
    site, target = TIMER_CALL
    assert struct.unpack_from('<I', d, site - B)[0] in (_b(site, target, link=True),
                                                          _b(site, TIMERHOOK, link=True))
    struct.pack_into('<I', d, site - B, _b(site, TIMERHOOK, link=True))
    site, old_target = KEY14_CALL
    cur = struct.unpack_from('<I', d, site - B)[0]
    assert cur in (_b(site, old_target, link=True), _b(site, FILM_CODE, link=True))
    struct.pack_into('<I', d, site - B, _b(site, FILM_CODE, link=True))
    for addr, old, new in SKETCH_RULES:
        assert struct.unpack_from('<I', d, addr - B)[0] in (old, new), hex(addr)
        struct.pack_into('<I', d, addr - B, new)
    return bytes(d)

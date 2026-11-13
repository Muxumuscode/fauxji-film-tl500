"""The film camera gets P's exposure fixes (build_fauxji.py --film).

Bug (owner, TL-F65t): in the film camera the minimum shutter still rose from 1/60 to 1/90 or 1/125 when zoomed in. The exposure engine does not ask
GET_SYSVAL for the mode: it keeps its own mode number (AE sysinfo, *0xC03EDB1C() + 0xA; 0 P, 2 A, 3 S, 4 M), set from the mode change, so
the film camera (a scene card) is not P to it, although `filmget` makes it P for every GET_SYSVAL reader. Two FAUXJI fixes are keyed on that
number and did not apply:
  * the zoom hand-shake shift skip in AeCalcCaptureCommon (fauxji_ui ZOOM_HOOK at the `cmp lr,#3` 0xC053FDC4: skip for 0, 2, 3), and
  * the flash shutter floor (fauxji_rot `plzoom` at 0xC0542014: no zoom shift on the flash floor for 0, 2, 3).
The other fixes are not keyed on it (the 1/60 floor and the ISO cap are in the program line table, the -0.3 EV bias applies to every mode, the
menu unlock reads GET_SYSVAL).

Fix: both checks first look at the film camera's flag (film_mode vars[4], set by the key hook before every shot) and, with the film camera
on, take the P path. The stock P / A / S test of the zoom hook moves to the spare end of fauxji_rot's R1; the flash check gets its film test
in 16 bytes reserved in R4 before film_mode's helpers. Tests: python tools/test_film.py (section 15).
"""
import struct

import fauxji_rot as R
import fauxji_ui as ui

B = ui.B
ZG_AT = 0xC04261C0                    # spare end of R1 (after film_mode's "Roll full" text, up to R1_END)
STOCK_ZOOM = [0xE3DEC002, 0x135E0003]  # bics ip,lr,#2 ; cmpne lr,#3 (then beq skip ; b back): fauxji_ui's zoom hook
PLZ_FIRST = 0xE1DBE0FA                 # `ldrsh lr,[fp,#0xa]`: the first word of fauxji_rot's plzoom
RESERVE = 16                           # bytes kept free in R4 for `plfilm` (film_mode.base_r4 starts its helpers after them)


def _ldr_pc(rd, at, target):
    off = target - (at + 8)
    assert 0 <= off < 4096, hex(off)
    return 0xE59F0000 | (rd << 12) | off


def blocks(vars_addr):
    """[(address, bytes)] and the labels: the film zoom hook (in place of fauxji_ui's), its moved stock test, the film flash test."""
    flag = vars_addr + 4
    _, rl = R.build()
    rot_r4_end = max(x + len(c) for x, c in R.build()[0] if R.R4 <= x < R.R4_END)
    zh = ui.ZOOM_HOOK
    zoom = [_ldr_pc(12, zh, flag),                    # ldr ip, film camera on?
            0xE35C0000,                               # cmp ip,#0
            ui._b(zh + 8, ui.ZOOM_SKIP, cond=0x1),    # bne skip the zoom shift (the film camera is P)
            ui._b(zh + 12, ZG_AT)]                    # b the stock P / A / S test
    zg = STOCK_ZOOM + [ui._b(ZG_AT + 8, ui.ZOOM_SKIP, cond=0x0), ui._b(ZG_AT + 12, ui.ZOOM_BACK)]
    pf = rot_r4_end
    plfilm = [_ldr_pc(14, pf, flag),                  # ldr lr, film camera on?
              0xE35E0000,                             # cmp lr,#0
              ui._b(pf + 8, rl['plnone'], cond=0x1),  # bne plnone: no zoom shift on the flash floor
              PLZ_FIRST,                              # ldrsh lr,[fp,#0xa]  (plzoom's own first word)
              ui._b(pf + 16, rl['plzoom'] + 4)]       # b plzoom's P / A / S test
    pack = lambda ws: b''.join(struct.pack('<I', x) for x in ws)
    assert ZG_AT + 16 <= R.R1_END
    labels = dict(zoom=zh, zg=ZG_AT, plfilm=pf, plzoom=rl['plzoom'], plnone=rl['plnone'])
    return [(zh, pack(zoom)), (ZG_AT, pack(zg)), (pf, pack(plfilm))], labels


def patch(d, vars_addr):
    d = bytearray(d)
    import film_mode
    blks, lab = blocks(vars_addr)
    pf, pf_end = lab['plfilm'], lab['plfilm'] + 20
    assert pf_end <= film_mode.base_r4(), 'plfilm reaches film_mode helpers: %x > %x' % (pf_end, film_mode.base_r4())
    zh_stock = STOCK_ZOOM + [ui._b(ui.ZOOM_HOOK + 8, ui.ZOOM_SKIP, cond=0x0), ui._b(ui.ZOOM_HOOK + 12, ui.ZOOM_BACK)]
    have = list(struct.unpack_from('<4I', d, ui.ZOOM_HOOK - B))
    assert have in (zh_stock, list(struct.unpack('<4I', blks[0][1]))), [hex(x) for x in have]
    for at, blk in blks:
        d[at - B:at - B + len(blk)] = blk
    first = struct.unpack_from('<I', d, lab['plzoom'] - B)[0]
    assert first in (PLZ_FIRST, ui._b(lab['plzoom'], pf)), hex(first)
    struct.pack_into('<I', d, lab['plzoom'] - B, ui._b(lab['plzoom'], pf))
    return bytes(d)

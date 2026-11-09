"""The film camera's date stamp (build_fauxji.py --film): an orange '98-style date, "26 11 08", in seven-segment digits.

The camera's Imprint setting (Setup > Imprint: Off / Date / Date & Time) still switches the stamp on; in a scene card (the film camera) it is
drawn orange and as YY MM DD whatever the date order, outside the film camera it keeps Samsung's colour and text. The seven-segment digits are
used in every mode of the film build (the stamp font is shared).

How Samsung draws it (static, stock 008264; the WB850F's mmfImPrint, found in the TL500 for the first time):
  * The capture code 0xC03C5B70 calls 0xC03CC96C(image + 0xA8, size [+0x1BC], layout [+0x1EC]) when bit 0x400000 of the capture flags
    [+0x1C8] is set. Layouts 2..4 are the date (Y.M.D, D.M.Y, M.D.Y: "%04d.%02d.%02d" / "%02d.%02d.%04d"), 5..7 add the time; registers at
    the layout switch (0xC03CCA08 `ldr r2, [sp, #0x118]`): r6 year, r5 month, r4 day, r8 hour, r7 minute; the text goes to sp+0xCC with its
    length at [sp+0xDC]; the switch's common tail is 0xC03CCB70.
  * 0xC03CC28C picks one of six 1-bit fonts by image size: (index, width x height, advance) = (0, 48x80, 46), (1, 40x72, 40), (2, 40x72,
    unused), (3, 32x56, 32), (4, 24x48, 24), (5, 16x24, 14); tables FONTS below, 12 glyphs each (0-9, '.', ':'), rows of width/8 bytes, MSB
    first. Any other character (space, apostrophe) has no glyph and is left blank (0xC03CC4E4 returns 0, the pen still advances).
  * The draw 0xC03CC7B0 calls the blitter 0xC03CC5F0(Y, UV, width, height, [sp] = glyph) for each character. The blitter writes every set
    pixel as Y = 0xE1 and, in the interleaved chroma plane, U = 0x00 on even / V = 0x94 on odd pixels (8 + 4 + 4 `mov` immediates).
What the film build changes:
  * the 16 colour `mov`s become `ldrb` from the stack: Y [sp+0x2C], U [sp+0x2D], V [sp+0x2E] (the blitter's sp after its 40-byte prologue,
    i.e. the word above its glyph argument), and the draw's call becomes a call to `stampwrap`, which passes the glyph plus a colour word:
    Samsung's colour, or orange while the film camera is on (film_mode vars[4], set by the key hook before the shot);
  * `fmt98` replaces the layout switch's first instruction: in the film camera, for any date layout (2..7), the text is "%02d %02d %02d" of
    (year % 100, month, day) with length 8, and the switch is skipped;
  * the digit glyphs of all six fonts become seven-segment digits ('.' and ':' stay).
Code in fauxji_rot's R2 after tools/film_exif.py, data (colours, format) at the end of R3. Not confirmed on a camera yet.
Tests: python tools/test_film.py (section 14).
"""
import struct

import fauxji_ui as ui
from diag_probe import Asm, R0, R1, R2, R3, R4, R5, R6, IP, LR, EQ, NE, LO, HS, AL, mov_i, mov_r, cmp_i, add_i, sub_i, ldr, str_, push, pop
import diag_probe as P

B = ui.B
BLIT, BLIT_END = 0xC03CC5F0, 0xC03CC7A8
BLIT_CALL = 0xC03CC880                         # `bl BLIT` in the draw (its only caller)
SWITCH, SWITCH_STOCK, SWITCH_NEXT, SWITCH_TAIL = 0xC03CCA08, 0xE59D2118, 0xC03CCA0C, 0xC03CCB70
SPRINTF = 0xC066D894
FONTS = ((0xC079F3E4, 48, 80), (0xC07A0A64, 40, 72), (0xC07A1B44, 40, 72), (0xC07A2C24, 32, 56), (0xC07A36A4, 24, 48), (0xC07A3D64, 16, 24))

STOCK_YUV = (0xE1, 0x00, 0x94)
ORANGE_YUV = (0x8F, 0x3A, 0xD0)                # RGB about (255, 110, 20): the glowing orange of a 90s date back
MOV_Y, MOV_U, MOV_V = 0xE3A0C0E1, 0xE3A03000, 0xE3A03094            # mov ip,#0xe1 / mov r3,#0 / mov r3,#0x94
LDR_Y, LDR_U, LDR_V = 0xE5DDC02C, 0xE5DD302D, 0xE5DD302E            # ldrb ip,[sp,#0x2c] / ldrb r3,[sp,#0x2d] / ldrb r3,[sp,#0x2e]
FMT = '%02d %02d %02d'
TEXT_LEN = 8

CODE_AT, CODE_END = 0xC0426390, 0xC0426438     # R2 after film_exif's block, to the end of R2
COLOURS_AT, FMT_AT, DATA_END = 0xC04265F8, 0xC0426600, 0xC042661C   # end of R3, after film_mode's mystery table and "No playback"


def data():
    col = bytes(STOCK_YUV) + b'\0' + bytes(ORANGE_YUV) + b'\0'
    fmt = FMT.encode() + b'\0'
    assert len(fmt) <= 16 and FMT_AT + 16 <= DATA_END
    return col, fmt.ljust(16, b'\0')


def ldr_c(rd, rn, off, cond):
    return (cond << 28) | 0x05900000 | (rn << 16) | (rd << 12) | off


def code(vars_addr):
    a = Asm(CODE_AT)
    # ---- replaces `bl BLIT` in the draw: the blitter's glyph argument plus the colour word above it
    a.label('stampwrap')
    a.w(push(0x4000), ldr(LR, 13, 4), sub_i(13, 13, 8), str_(LR, 13, 0))     # [sp] = the glyph (the draw's [sp])
    a.lit(IP, vars_addr)
    a.w(ldr(IP, IP, 4), cmp_i(IP, 0))                     # the film camera on?
    a.lit(IP, COLOURS_AT)
    a.w(ldr(LR, IP, 0), ldr_c(LR, IP, 4, NE), str_(LR, 13, 4))
    a.b(AL, BLIT, link=True)
    a.w(add_i(13, 13, 8), pop(0x8000))
    # ---- replaces `ldr r2, [sp, #0x118]` (the layout) at the layout switch of 0xC03CC96C
    a.label('fmt98')
    a.w(ldr(R2, 13, 0x118))
    a.lit(IP, vars_addr)
    a.w(ldr(IP, IP, 4), cmp_i(IP, 0))
    a.b(EQ, 'fback')                                      # not the film camera: Samsung's text
    a.w(cmp_i(R2, 2))
    a.b(LO, 'fback')                                      # no date in this layout
    a.w(cmp_i(R2, 8))
    a.b(HS, 'fback')
    a.w(mov_r(R0, R6))
    a.label('fyy')
    a.w(cmp_i(R0, 100), sub_i(R0, R0, 100, HS))
    a.b(HS, 'fyy')                                        # r0 = year % 100
    a.w(mov_r(R2, R0), mov_r(R3, R5), str_(R4, 13, 0), add_i(R0, 13, 0xCC))
    a.lit(R1, FMT_AT)
    a.b(AL, SPRINTF, link=True)                           # sprintf(text, "%02d %02d %02d", yy, month, day)
    a.w(mov_i(IP, TEXT_LEN), str_(IP, 13, 0xDC))
    a.b(AL, SWITCH_TAIL)
    a.label('fback')
    a.b(AL, SWITCH_NEXT)
    out = a.build()
    assert CODE_AT + len(out) <= CODE_END, hex(CODE_AT + len(out))
    return out, a.labels


# ---------------------------------------------------------------- seven-segment digits
SEVEN_MIN_H = 50                                # 48 px and smaller: the stock digits (seven segments get blobby)
SEGS = {0: 'abcdef', 1: 'bc', 2: 'abdeg', 3: 'abcdg', 4: 'bcfg', 5: 'acdfg', 6: 'acdefg', 7: 'abc', 8: 'abcdefg', 9: 'abcdfg'}


def seven(digit, w, h, ss=8):
    """A 1-bit seven-segment digit in a w x h glyph box (rows of w bits, MSB first), slightly slanted like a date-back LCD."""
    from PIL import Image, ImageDraw
    W, H = w * ss, h * ss
    im = Image.new('L', (W, H), 0)
    d = ImageDraw.Draw(im)
    t = max(2 * ss, round(h * ss * 0.15))                # segment thickness
    mx, my = round(w * ss * 0.10), round(h * ss * 0.06)
    x0, x1, y0, y1 = mx, W - mx - round(w * ss * 0.06), my, H - my
    ym = (y0 + y1) // 2
    gap = max(ss // 2, t // 7)
    slant = 0.08

    def sx(x, y):                                        # italic: shift right towards the top
        return x + (H - y) * slant - H * slant / 2

    def hseg(xa, xb, y):
        h2 = t / 2
        pts = [(xa + gap, y), (xa + gap + h2, y - h2), (xb - gap - h2, y - h2), (xb - gap, y), (xb - gap - h2, y + h2), (xa + gap + h2, y + h2)]
        d.polygon([(sx(x, yy), yy) for x, yy in pts], fill=255)

    def vseg(x, ya, yb):
        h2 = t / 2
        pts = [(x, ya + gap), (x + h2, ya + gap + h2), (x + h2, yb - gap - h2), (x, yb - gap), (x - h2, yb - gap - h2), (x - h2, ya + gap + h2)]
        d.polygon([(sx(xx, y), y) for xx, y in pts], fill=255)

    xl, xr = x0 + t / 2, x1 - t / 2
    yt, yb = y0 + t / 2, y1 - t / 2
    for s in SEGS[digit]:
        {'a': lambda: hseg(xl, xr, yt), 'g': lambda: hseg(xl, xr, ym), 'd': lambda: hseg(xl, xr, yb),
         'f': lambda: vseg(xl, yt, ym), 'b': lambda: vseg(xr, yt, ym), 'e': lambda: vseg(xl, ym, yb), 'c': lambda: vseg(xr, ym, yb)}[s]()
    small = im.resize((w, h), Image.BOX)
    px = small.load()
    out = bytearray(w // 8 * h)
    for r in range(h):
        for c in range(w):
            if px[c, r] >= 100:
                out[r * (w // 8) + c // 8] |= 0x80 >> (c % 8)
    return bytes(out)


def glyph_tables(stock_elf):
    """[(address, bytes)]: each font's ten digits redrawn, '.' and ':' kept from the stock table. The
    two smallest fonts (24 x 48, 16 x 24) keep Samsung's digits: seven segments are not readable at those sizes."""
    out = []
    for base, w, h in FONTS:
        if h < SEVEN_MIN_H:
            continue
        g = w // 8 * h
        tab = bytearray(stock_elf[base - B:base - B + 12 * g])
        for n in range(10):
            tab[n * g:(n + 1) * g] = seven(n, w, h)
        out.append((base, bytes(tab)))
    return out


def preview(path, stock_elf):
    """The six fonts' new digits, white on black, for docs (docs/images/film-mode/stamp_digits.png)."""
    from PIL import Image
    tabs = glyph_tables(stock_elf)
    sheet = Image.new('RGB', (12 * 52 + 8, sum(h + 6 for _, _, h in FONTS) + 6), (20, 20, 22))
    y = 6
    tabs = dict(tabs)
    for base, w, h in FONTS:
        g = w // 8 * h
        tab = tabs.get(base, stock_elf[base - B:base - B + 12 * g])
        for n in range(12):
            im = Image.new('RGB', (w, h), (20, 20, 22))
            px = im.load()
            for r in range(h):
                for c in range(w):
                    if tab[n * g + r * (w // 8) + c // 8] & (0x80 >> (c % 8)):
                        px[c, r] = (255, 110, 20)
            sheet.paste(im, (6 + n * 52, y))
        y += h + 6
    sheet.save(path)


FORCE_IN_FILM = True                           # the film camera stamps every photo even with Setup > Imprint Off (film_mode `forcestamp`)
STAMP_BEQ, STAMP_BEQ_STOCK = 0xC03C5C54, 0x0A000004  # capture code: `beq 0xC03C5C6C` (skip the stamp when the Imprint flag is clear)


def patch(d, vars_addr):
    """Apply to a film-build .elf. vars_addr = film_mode's vars (vars[4] = the film camera is on)."""
    d = bytearray(d)
    c, lab = code(vars_addr)
    d[CODE_AT - B:CODE_AT - B + len(c)] = c
    col, fmt = data()
    d[COLOURS_AT - B:COLOURS_AT - B + 8] = col
    d[FMT_AT - B:FMT_AT - B + 16] = fmt
    n = {MOV_Y: 0, MOV_U: 0, MOV_V: 0}
    for a in range(BLIT, BLIT_END, 4):
        wd = struct.unpack_from('<I', d, a - B)[0]
        new = {MOV_Y: LDR_Y, MOV_U: LDR_U, MOV_V: LDR_V}.get(wd)
        if new:
            n[wd] += 1
            struct.pack_into('<I', d, a - B, new)
    have = [struct.unpack_from('<I', d, a - B)[0] for a in range(BLIT, BLIT_END, 4)]
    assert (n[MOV_Y], n[MOV_U], n[MOV_V]) in ((8, 4, 4), (0, 0, 0)) and have.count(LDR_Y) == 8 and have.count(LDR_U) == 4 and \
        have.count(LDR_V) == 4, n
    for site, stock, new in ((BLIT_CALL, ui._b(BLIT_CALL, BLIT, link=True), ui._b(BLIT_CALL, lab['stampwrap'], link=True)),
                             (SWITCH, SWITCH_STOCK, ui._b(SWITCH, lab['fmt98']))):
        assert struct.unpack_from('<I', d, site - B)[0] in (stock, new), hex(site)
        struct.pack_into('<I', d, site - B, new)
    for base, tab in glyph_tables(bytes(d)):
        d[base - B:base - B + len(tab)] = tab
    if FORCE_IN_FILM:
        import film_mode
        to = film_mode.blob()[1]['forcestamp']
        assert struct.unpack_from('<I', d, STAMP_BEQ - B)[0] in (STAMP_BEQ_STOCK, ui._b(STAMP_BEQ, to, cond=0x0)), hex(STAMP_BEQ)
        struct.pack_into('<I', d, STAMP_BEQ - B, ui._b(STAMP_BEQ, to, cond=0x0))       # beq forcestamp
    return bytes(d)

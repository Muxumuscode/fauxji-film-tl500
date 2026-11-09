"""EXIF names for the film build (build_fauxji.py --film): every photo says which camera and which film made it.

  Make      "FAUXJI FILM"                    (stock "SAMSUNG"; earlier FAUXJI builds wrote "MODDED!")
  Model     "TL500 Classic Chrome" ...       the camera and the film look the photo was taken with, filled in as each photo is written
  Software  "FAUXJI TL-F65q"                 the build label (the Model used to carry it; the version screen still shows the label)

How (static, from the stock 008264 .elf). The IFD0 writer 0xC03773E0 walks an 11-entry tag table at 0xC091D044 (0x14-byte records: tag, type,
count at +8). Make (record 0), Model (1) and Software (6) are ASCII; their bytes come from 8- and 9-byte stack copies (sp+0x6c, sp+0x74,
sp+0xdc) that are handed to the data writer as `add r3, sp, #..` right before an indirect call (r0-r2 and ip are its arguments). The IFD0 data
size is summed from the same table's counts (0xC03792D8 .. 0xC0379410, counts above 4), so longer strings only need larger counts; nothing
else hard-codes them. So:
  * the three counts become 12 / 24 / 16 (even, so the following values stay word-aligned);
  * Make and Software: the `add r3, sp, #..` becomes `ldr r3, [pc, #..]` of the function's own pool words for the stock strings
    (0xC0377C38, 0xC0377C40), which are pointed at our strings (the stock copy loops then copy our first bytes into the unused stack copies);
  * Model: the `add r3, sp, #0x74` becomes a branch to `exifmodel`, which writes "TL500 " + the current look's name (PHOTO STYLE value,
    UI_CACHE + 0x40, the same value the FILM SIM key reads) into a RAM buffer, sets r3 to it and returns into the writer.
The mystery roll's look is therefore revealed in the photos only. Code and data: the start of fauxji_rot's R2 (free since the tilt tag is
off) and the look names in the spare end of R4. Not confirmed on a camera yet: check the EXIF of the first photos (any EXIF viewer).
Tests: python tools/test_film.py (section 12).
"""
import struct

import diag_probe as P
import fauxji_ui as ui
from diag_probe import Asm, R0, R2, R3, R4, R5, EQ, LT, AL, mov_i, cmp_i, add_i, ldr, push, pop

HI = 0x8

B = ui.B
TABLE = 0xC091D044                                # IFD0 tag table: (tag u16 + pad, type, count, ...) x 11, 0x14 bytes each
REC_MAKE, REC_MODEL, REC_SOFT = 0, 1, 6
STOCK_COUNTS = {REC_MAKE: (0x10F, 8), REC_MODEL: (0x110, 8), REC_SOFT: (0x131, 9)}
MAKE_SITE, MAKE_POOL = 0xC03776A8, 0xC0377C38     # `add r3, sp, #0x6c` (stock 0xE28D306C); pool word of the stock Make string
MODEL_SITE, MODEL_BACK = 0xC0377784, 0xC0377788   # `add r3, sp, #0x74` (stock 0xE28D3074)
SOFT_SITE, SOFT_POOL = 0xC0377860, 0xC0377C40     # `add r3, sp, #0xdc` (stock 0xE28D30DC); pool word of the stock version digits
SITE_STOCK = {MAKE_SITE: 0xE28D306C, MODEL_SITE: 0xE28D3074, SOFT_SITE: 0xE28D30DC}

MAKE = 'FAUXJI FILM'
MODEL_PREFIX = 'TL500 '
MAKE_N, MODEL_N, SOFT_N = 12, 24, 16              # the new counts (bytes incl. the NUL padding)
NAMES = ('Provia', 'Bleach Bypass', 'Nostalgic Neg.', 'Astia', 'Velvia', 'Reala Ace', 'Classic Chrome', 'Classic Neg.', 'Eterna',
         'Acros', 'Sepia')                        # PHOTO STYLE value 0 .. 10 (same order as fauxji.LOOKS / film_mode.LOOK_NAMES)
NAME_MAX = MODEL_N - len(MODEL_PREFIX)            # 18 bytes for the name + NUL padding

CODE_AT, CODE_END = 0xC04262F0, 0xC0426390        # fauxji_rot R2 (tilt code, off) up to tools/film_stamp.py
NAMES_AT, NAMES_END = 0xC0426E70, 0xC0426EE8      # spare end of fauxji_rot R4, after film_mode's helpers


def ldr_pc(rd, at, pool):
    off = pool - (at + 8)
    assert 0 <= off < 4096
    return 0xE59F0000 | (rd << 12) | off


def ldrb_x(rd, rn, rm, cond=0xE):
    return (cond << 28) | 0x07D00000 | (rn << 16) | (rd << 12) | rm


def strb_x(rd, rn, rm):
    return 0xE7C00000 | (rn << 16) | (rd << 12) | rm


def _asc(text, n):
    raw = text.encode('ascii') + b'\0'
    assert len(raw) <= n, text
    return raw.ljust(n, b'\0')


def names_block():
    """(name offsets: 11 bytes + pad to 12) + the NUL-terminated names."""
    offs, blob = [], b''
    for n in NAMES:
        assert len(n) + 1 <= NAME_MAX
        offs.append(12 + len(blob))
        blob += n.encode('ascii') + b'\0'
    assert max(offs) < 256
    out = bytes(offs).ljust(12, b'\0') + blob
    return out + b'\0' * (-len(out) % 4)


def blob(label):
    """[(address, bytes), ...], labels. label = the build's version label (bytes, as in build_fauxji.FILM_LABEL)."""
    soft = 'FAUXJI ' + label.rstrip(b'\0').decode('ascii')
    make_at, soft_at, model_at = CODE_AT, CODE_AT + MAKE_N, CODE_AT + MAKE_N + SOFT_N
    data = _asc(MAKE, MAKE_N) + _asc(soft, SOFT_N) + _asc(MODEL_PREFIX + NAMES[0], MODEL_N)
    a = Asm(CODE_AT + len(data))
    # ---- replaces `add r3, sp, #0x74` (r0-r2, ip: the data writer's arguments and address, kept; lr is set by the next `mov lr, pc`)
    a.label('exifmodel')
    a.w(push(0x1037))                                     # push {r0-r2, r4, r5, ip}
    a.lit(R3, ui.UI_CACHE)
    a.w(ldr(R4, R3, 0x40), cmp_i(R4, len(NAMES) - 1), mov_i(R4, 0, HI))   # the look (a value out of range: PROVIA)
    a.lit(R3, NAMES_AT)
    a.w(ldrb_x(R4, R3, R4), P.dp_r(P.ADD, R4, R3, R4))   # r4 = the name (offset table, then the names)
    a.lit(R3, model_at + len(MODEL_PREFIX))
    a.w(mov_i(R5, 0), mov_i(R2, 1))                       # r5 = index, r2 = still copying
    a.label('xl')
    a.w(ldrb_x(R0, R4, R5), cmp_i(R2, 0), mov_i(R0, 0, EQ), cmp_i(R0, 0), mov_i(R2, 0, EQ), strb_x(R0, R3, R5))
    a.w(add_i(R5, R5, 1), cmp_i(R5, NAME_MAX))
    a.b(LT, 'xl')                                          # the name, then NULs up to the end of the buffer
    a.w(pop(0x1037))
    a.lit(R3, model_at)
    a.b(AL, MODEL_BACK)
    code = a.build()
    out = data + code
    assert CODE_AT + len(out) <= CODE_END, hex(CODE_AT + len(out))
    nb = names_block()
    assert NAMES_AT + len(nb) <= NAMES_END, hex(NAMES_AT + len(nb))
    labels = dict(a.labels, make=make_at, soft=soft_at, model=model_at)
    return [(CODE_AT, out), (NAMES_AT, nb)], labels


def patch(d, label):
    """Apply to a film-build .elf (after film_mode.patch, which places its helpers in R4 before NAMES_AT)."""
    import film_mode
    d = bytearray(d)
    blocks, lab = blob(label)
    h_end = film_mode.base_r4() + len(film_mode.blob()[0][1][1])
    assert h_end <= NAMES_AT, 'film_mode helpers reach the EXIF names: %x' % h_end
    for at, blk in blocks:
        d[at - B:at - B + len(blk)] = blk
    for rec, n in ((REC_MAKE, MAKE_N), (REC_MODEL, MODEL_N), (REC_SOFT, SOFT_N)):
        tag, stock = STOCK_COUNTS[rec]
        o = TABLE + 0x14 * rec - B
        assert struct.unpack_from('<H', d, o)[0] == tag, hex(tag)
        assert struct.unpack_from('<I', d, o + 8)[0] in (stock, n), (hex(tag), struct.unpack_from('<I', d, o + 8)[0])
        struct.pack_into('<I', d, o + 8, n)
    new = {MAKE_SITE: ldr_pc(R3, MAKE_SITE, MAKE_POOL), MODEL_SITE: ui._b(MODEL_SITE, lab['exifmodel']),
           SOFT_SITE: ldr_pc(R3, SOFT_SITE, SOFT_POOL)}
    for site, word in new.items():
        have = struct.unpack_from('<I', d, site - B)[0]
        assert have in (SITE_STOCK[site], word), hex(site)
        struct.pack_into('<I', d, site - B, word)
    for pool, stock, to in ((MAKE_POOL, 0xC0796480, lab['make']), (SOFT_POOL, 0xC0796C14, lab['soft'])):
        have = struct.unpack_from('<I', d, pool - B)[0]
        assert have in (stock, to), (hex(pool), hex(have))
        struct.pack_into('<I', d, pool - B, to)
    return bytes(d)

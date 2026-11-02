"""Read/write the TL500 GUI skin (skin.bin inside SPID.Rom).

Layout (section 0, images): at skin+0x20 a 0x28-byte header (..., transparent key
0xFFFF00FF, ..., image count at +0x2C), then a u32 offset table (offsets from the
table start), then images. Each image: u32 width, height, total size (incl. this
16-byte header), type (3 = RLE). Rows: 0xFF, u16 row length (incl. these 3 bytes),
then tokens: c < 0x80 -> run of c pixels of the next RGBA pixel; c >= 0x80 -> c-0x80
literal RGBA pixels. Magenta (255,0,255) is the transparent key.

Run from project root:
  python tools/skin.py dump <SPID.Rom> <out_dir>   # every image as PNG + a contact sheet
"""
import os, struct, sys

TABLE = 0x50          # offset table start inside skin.bin
COUNT_AT = 0x4C       # u32 image count


def images(k):
    n = struct.unpack_from('<I', k, COUNT_AT)[0]
    offs = struct.unpack_from('<%dI' % n, k, TABLE)
    return [TABLE + o for o in offs]


def decode(k, a):
    w, h, size, typ = struct.unpack_from('<4I', k, a)
    if typ != 3:
        return w, h, typ, None
    p = a + 16
    rows = []
    for _ in range(h):
        assert k[p] == 0xFF, 'row marker'
        n = struct.unpack_from('<H', k, p + 1)[0]
        q, end, row = p + 3, p + n, []
        while q < end:
            c = k[q]; q += 1
            if c < 0x80:
                row += [k[q:q + 4]] * c; q += 4
            else:
                m = c - 0x80
                row += [k[q + 4 * i:q + 4 * i + 4] for i in range(m)]; q += 4 * m
        assert len(row) == w, 'row width %d != %d' % (len(row), w)
        rows.append(b''.join(row)); p = end
    return w, h, typ, b''.join(rows)


def encode(w, h, rgba):
    """RGBA bytes -> type-3 image block (header + rows), same RLE as Samsung's."""
    out = []
    for y in range(h):
        px = [rgba[(y * w + x) * 4:(y * w + x) * 4 + 4] for x in range(w)]
        toks, x = [], 0
        while x < w:
            r = 1
            while x + r < w and px[x + r] == px[x] and r < 0x7F:
                r += 1
            if r >= 2:
                toks.append(bytes([r]) + px[x]); x += r
            else:
                lit = [px[x]]; x += 1
                while x < w and len(lit) < 0x7F and not (x + 1 < w and px[x + 1] == px[x]):
                    lit.append(px[x]); x += 1
                toks.append(bytes([0x80 + len(lit)]) + b''.join(lit))
        body = b''.join(toks)
        out.append(b'\xff' + struct.pack('<H', len(body) + 3) + body)
    data = b''.join(out)
    return struct.pack('<4I', w, h, len(data) + 16, 3) + data


if __name__ == '__main__':
    from PIL import Image, ImageDraw
    sys.path.insert(0, os.path.dirname(__file__))
    import spid_files as F
    d = open(sys.argv[2], 'rb').read()
    r, o, s, sl = F.directory(d)['skin.bin']
    k = d[o:o + s]
    out = sys.argv[3]; os.makedirs(out, exist_ok=True)
    tiles = []
    for i, a in enumerate(images(k)):
        w, h, typ, px = decode(k, a)
        if px is None:
            continue
        im = Image.frombytes('RGBA', (w, h), px)
        im.save(os.path.join(out, '%03d_%dx%d.png' % (i, w, h)))
        if w <= 120 and h <= 120:
            tiles.append((i, im))
    cols = 24
    sheet = Image.new('RGB', (cols * 64, ((len(tiles) + cols - 1) // cols) * 76), (40, 40, 40))
    dr = ImageDraw.Draw(sheet)
    for n, (i, im) in enumerate(tiles):
        t = im.copy(); t.thumbnail((60, 60))
        x, y = (n % cols) * 64, (n // cols) * 76
        sheet.paste(t.convert('RGB'), (x + 2, y + 2))
        dr.text((x + 2, y + 63), str(i), fill=(255, 255, 0))
    sheet.save(os.path.join(out, 'sheet_small.png'))
    print('decoded', len(images(k)), 'images;', len(tiles), 'small ones on the sheet')

"""FAUXJI film-simulation badges for the TL500 GUI skin.

Replaces Samsung's Photo Style icons (painter's palette + letters) in skin.bin with
Fuji-style badges showing each look's short code. Three sets exist: large 115x115
(images 72-82), small white 64x64 (live view) and small grey 64x64 (disabled).
Each new image is RLE-encoded with tools/skin.py and written back in place (it must
not be larger than the original block; the offset table is left untouched).

Run from project root:  python tools/badges.py preview <out.png>
"""
import os, struct, sys
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
import skin

FONT = r'C:\Windows\Fonts\bahnschrift.ttf'
KEY = (255, 0, 255, 255)                 # Samsung's transparent key colour

# Samsung icon -> FAUXJI badge text, per set: {skin image index: text}
CODES = {'NOR': 'STD', 'V': 'V', 'S': 'S', 'F': 'RA', 'R': 'Cc', 'CO': 'Nc',
         'CA': 'ET', 'CL': 'A', 'N': 'SEP', 'SK': 'EB', 'FD': 'NN'}
SETS = {
    'large': {72: 'V', 73: 'NOR', 74: 'CA', 75: 'CL', 76: 'CO', 77: 'F', 78: 'FD',
              79: 'N', 80: 'R', 81: 'S', 82: 'SK'},
    # white set found by matching the grey set's exact transparency outline
    'white': {414: 'CA', 415: 'CL', 416: 'CO', 417: 'FD', 418: 'F', 419: 'N', 420: 'NOR',
              421: 'R', 422: 'SK', 423: 'S', 424: 'V'},
    'grey':  {326: 'S', 327: 'V', 337: 'CA', 338: 'CL', 339: 'CO', 340: 'FD', 341: 'F',
              342: 'N', 343: 'NOR', 344: 'R', 345: 'SK'},
}
STYLE = {  # fill top, fill bottom, outline, text
    'large': ((246, 246, 244), (196, 198, 200), (40, 40, 42), (34, 34, 36)),
    'white': ((246, 246, 244), (196, 198, 200), (40, 40, 42), (34, 34, 36)),
    'grey':  ((150, 150, 150), (118, 118, 118), (56, 56, 56), (70, 70, 70)),
}


def _font(size):
    f = ImageFont.truetype(FONT, size)
    try:
        f.set_variation_by_name('Bold Condensed')
    except Exception:
        pass
    return f


CANISTER = {  # canister fill, ink
    'large': ((244, 244, 242), (18, 18, 20)),
    'white': ((244, 244, 242), (18, 18, 20)),
    'grey':  ((150, 150, 150), (60, 60, 60)),
}


def canister(size, text, style):
    """Film-canister icon in the spirit of Fuji's film-simulation icons (own drawing):
    canister body with a spool knob, film leader with sprocket holes to the right,
    bold code on the body: big first letter, small second (C c, R a, N h ...)."""
    fill, ink = CANISTER[style]
    aa = size >= 100
    s = 4 if aa else 1
    W = size * s
    im = Image.new('RGBA', (W, W), (0, 0, 0, 0) if aa else KEY)
    d = ImageDraw.Draw(im)
    if not aa:
        d.fontmode = '1'
    u = W / 64.0                                    # design grid: 64 units
    F = lambda *v: [round(x * u) for x in v]
    body = F(6, 14, 46, 54)
    d.rectangle(F(13, 9, 21, 14), fill=fill + (255,))          # spool knob
    d.rounded_rectangle(body, round(3 * u), fill=fill + (255,))  # canister body
    d.polygon([tuple(F(45, 20)), tuple(F(58, 20)), tuple(F(58, 23)), tuple(F(56, 25)),
               tuple(F(58, 27)), tuple(F(58, 47)), tuple(F(45, 47))], fill=fill + (255,))  # leader
    for y in (23, 30, 37, 43):                                   # sprocket holes
        d.rectangle(F(51, y, 54, y + 3), fill=(0, 0, 0, 0) if aa else KEY)
    big, small = (text, '') if len(text) != 2 else (text[0], text[1])
    if len(text) == 3:
        f = _font(round(17 * u)); x0, y0 = 26, 34
        l, t, r, b = d.textbbox((0, 0), text, font=f)
        d.text((round(x0 * u) - (r - l) / 2 - l, round(y0 * u) - (b - t) / 2 - t), text, font=f, fill=ink + (255,))
    else:
        f = _font(round(34 * u))
        l, t, r, b = d.textbbox((0, 0), big, font=f)
        bx = round((22 if small else 26) * u) - (r - l) / 2 - l
        d.text((bx, round(34 * u) - (b - t) / 2 - t), big, font=f, fill=ink + (255,))
        if small:
            f2 = _font(round(21 * u))
            l2, t2, r2, b2 = d.textbbox((0, 0), small, font=f2)
            d.text((round(38 * u) - (r2 - l2) / 2 - l2, round(46 * u) - (b2 - t2) - t2), small,
                   font=f2, fill=ink + (255,))
    if not aa:
        return im
    im = im.resize((size, size), Image.LANCZOS)
    px = im.load(); out = Image.new('RGBA', (size, size), KEY); op = out.load()
    for y in range(size):
        for x in range(size):
            r_, g_, b_, a_ = px[x, y]
            if a_ >= 128:
                op[x, y] = tuple(min(255, v * 255 // a_) // 16 * 16 for v in (r_, g_, b_)) + (255,)
    return out


def small_badge(size, text, style):
    """64 px badge drawn pixel-exact in a few solid colours (no anti-aliasing), so the
    RLE stays small enough for Samsung's slots."""
    top, bottom, outline, ink = STYLE[style]
    fill = tuple((a + b) // 2 for a, b in zip(top, bottom))
    im = Image.new('RGBA', (size, size), KEY)
    d = ImageDraw.Draw(im)
    d.fontmode = '1'
    box = [5, 13, size - 6, size - 14]
    d.rounded_rectangle(box, 8, fill=outline + (255,))
    d.rounded_rectangle([box[0] + 3, box[1] + 3, box[2] - 3, box[3] - 3], 6, fill=fill + (255,))
    f = _font(int(size * (0.44 if len(text) <= 2 else 0.34)))
    l, t, r, b = d.textbbox((0, 0), text, font=f)
    d.text(((size - (r - l)) / 2 - l, (size - (b - t)) / 2 - t), text, font=f, fill=ink + (255,))
    return im


def badge(size, text, style):
    """Current design: film canister (owner's request, after Fuji's reference)."""
    return canister(size, text, style)


def plate_badge(size, text, style):
    """First design (film-frame plate), kept for reference."""
    if size < 100:
        return small_badge(size, text, style)
    top, bottom, outline, ink = STYLE[style]
    s = 4                                     # supersample, then snap the edge to the key
    W = H = size * s
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    m = int(W * 0.10); r = int(W * 0.14)
    box = [m, int(H * 0.20), W - m, int(H * 0.80)]
    d.rounded_rectangle(box, r, fill=outline + (255,))
    inner = [box[0] + 3 * s, box[1] + 3 * s, box[2] - 3 * s, box[3] - 3 * s]
    grad = Image.new('RGBA', (W, H))
    gd = ImageDraw.Draw(grad)
    flat = size < 100            # small icons: flat fill (a gradient defeats the RLE)
    for y in range(H):
        t = 0.35 if flat else min(1, max(0, (y - inner[1]) / max(1, inner[3] - inner[1])))
        gd.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
    mask = Image.new('L', (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle(inner, r - 3 * s, fill=255)
    im.paste(grad, (0, 0), mask)
    # sprocket notches along top and bottom edges (film strip feel); the 64 px icons
    # skip them so the letters stay readable
    if size >= 100:
        for i in range(5):
            x = inner[0] + (inner[2] - inner[0]) * (i + 0.5) / 5
            for y in (inner[1] + 3 * s, inner[3] - 3 * s - 4 * s):
                d.rounded_rectangle([x - 3 * s, y, x + 3 * s, y + 4 * s], s, fill=outline + (255,))
        fs = int(H * (0.36 if len(text) <= 2 else 0.30))
    else:
        fs = int(H * (0.44 if len(text) <= 2 else 0.36))
    f = _font(fs)
    tw = d.textlength(text, font=f)
    l, t_, rr, b = d.textbbox((0, 0), text, font=f)
    d.text(((W - tw) / 2, (H - (b - t_)) / 2 - t_), text, font=f, fill=ink + (255,))
    im = im.resize((size, size), Image.LANCZOS)
    px = im.load()
    out = Image.new('RGBA', (size, size), KEY)
    op = out.load()
    for y in range(size):
        for x in range(size):
            r_, g_, b_, a_ = px[x, y]
            if a_ >= 128:                    # hard edge against the transparent key
                c = [v * 255 // max(a_, 1) for v in (r_, g_, b_)]
                if size < 100:               # fewer shades in the anti-aliasing -> longer runs
                    c = [min(255, (v + 12) // 24 * 24) for v in c]
                op[x, y] = tuple(c) + (255,)
    return out


def patch_skin(k):
    """Return skin.bin bytes with every Photo Style icon replaced by its badge."""
    k = bytearray(k)
    offs = skin.images(bytes(k))
    for style, icons in SETS.items():
        for idx, code in icons.items():
            a = offs[idx]
            w, h, size, typ = struct.unpack_from('<4I', k, a)
            assert typ == 3 and w == h, (idx, w, h, typ)
            img = badge(w, CODES[code], style)
            blk = skin.encode(w, h, img.tobytes())
            if len(blk) > size:
                raise ValueError('badge for image %d is %d bytes, slot %d' % (idx, len(blk), size))
            k[a:a + len(blk)] = blk
    return bytes(k)


if __name__ == '__main__':
    tiles = []
    for style, icons in SETS.items():
        size = 115 if style == 'large' else 64
        for idx, code in sorted(icons.items(), key=lambda x: x[1]):
            tiles.append(badge(size, CODES[code], style))
    W = sum(t.size[0] + 8 for t in tiles)
    sheet = Image.new('RGB', (W, 124), (60, 60, 60)); x = 4
    for t in tiles:
        sheet.paste(t.convert('RGB'), (x, 4)); x += t.size[0] + 8
    sheet.save(sys.argv[2])

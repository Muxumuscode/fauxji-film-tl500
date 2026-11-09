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

import fonts
FONT = fonts.find_font()
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


# badge text (CODES) -> index of the look in tools/film_mode_art.FILMS (the Photo Style menu order)
CART_FILM = {'STD': 0, 'EB': 1, 'NN': 2, 'S': 3, 'V': 4, 'RA': 5, 'Cc': 6, 'Nc': 7, 'ET': 8, 'A': 9, 'SEP': 10}


def cartridge(size, text, style):
    """The 35 mm cartridge of the film mode (tools/film_mode_art.canister, drawn from the owner's photos of the real packaging: black
    plastic caps, white strip with the look's code, Fuji-green foot, the look's colour field or band, leader with sprocket holes),
    for the 115 px menu icons, the 64 px live-view icon and the grey 64 px 'not available' icon, in the transparent key colour.
    Drawn large and scaled down, hard edge against the key, colours snapped so the RLE fits Samsung's slots."""
    import film_mode_art as fma
    film = CART_FILM[text]
    dim = style == 'grey'
    name = fma.FILMS[film][1]                                # the picker's names: PRO, BB, NN, AST, VEL, RA, CC, CN, ET, ACR, SEP (stacked upright)
    out = Image.new('RGBA', (size, size), KEY)
    op = out.load()
    if size < 100:                                           # crisp at the real size: no anti-aliasing, flat colours (the RLE must fit the slot)
        im = fma.canister(size - 2, None, film, dim=dim, ss=1, code=name, detail=False, flat=True, vcode=True, crisp=True)
        px = im.load()
        ox, oy = (size - im.width) // 2, (size - im.height) // 2
        for y in range(im.height):
            for x in range(im.width):
                r_, g_, b_, a_ = px[x, y]
                if a_ >= 128:
                    op[ox + x, oy + y] = (r_ // 8 * 8, g_ // 8 * 8, b_ // 8 * 8, 255)
        return out
    big = fma.canister(size * 4, None, film, dim=dim, ss=2, code=name, detail=True, vcode=True)
    h = size - 4
    w = max(1, round(big.width * h / big.height))
    im = big.resize((w, h), Image.LANCZOS)
    px = im.load()
    ox, oy = (size - w) // 2, (size - h) // 2
    for y in range(h):
        for x in range(w):
            r_, g_, b_, a_ = px[x, y]
            if a_ >= 128:
                op[ox + x, oy + y] = tuple(min(255, (min(255, v * 255 // a_) + 8) // 16 * 16) for v in (r_, g_, b_)) + (255,)
    return out


DESIGN = 'canister'          # build_fauxji.py sets 'cartridge' for the --film build; plain builds keep the earlier canister badges


def badge(size, text, style):
    """The badge for a skin icon: the film cartridge (see cartridge()) in the film build, else the earlier canister()."""
    return cartridge(size, text, style) if DESIGN == 'cartridge' else canister(size, text, style)


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


def card(film, w=256, h=285):
    """A scene-picker card as a film card: the dark card of the FAUXJI scene cards with the look's cartridge, large, in the middle."""
    import film_mode_art as fma
    im = Image.new('RGBA', (w, h), (50, 50, 51, 255))
    ImageDraw.Draw(im).rectangle([0, 0, w - 1, h - 1], outline=(99, 100, 102, 255), width=2)
    ch = h - 40
    if film >= len(fma.FILMS):                               # the mystery roll (film_mode.MYSTERY): a blank dark cartridge and a big orange '?'
        return mystery_card(w, h)
    cart = fma.canister(ch * 2, None, film, ss=2, code=fma.FILMS[film][1], detail=True, vcode=True)
    cart = cart.resize((round(cart.width * ch / cart.height), ch), Image.LANCZOS)
    im.alpha_composite(cart, ((w - cart.width) // 2, (h - ch) // 2))
    q = im.convert('RGB').quantize(colors=48, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).convert('RGBA')
    return q


def patch_cards(k, card_image, card_look):
    """Film build: skin.bin with each scene card image (card_image: card -> image number) replaced by that card's look's cartridge card."""
    k = bytearray(k)
    offs = skin.images(bytes(k))
    ends = sorted(offs)
    for c, idx in card_image.items():
        a = offs[idx]
        w, h, _, typ = struct.unpack_from('<4I', k, a)
        size = ends[ends.index(a) + 1] - a                    # the room is up to the next image (the header size shrank when the flat scene cards were written)
        blk = skin.encode(w, h, card(card_look[c], w, h).tobytes())
        if len(blk) > size:
            raise ValueError('card image %d is %d bytes, slot %d' % (idx, len(blk), size))
        k[a:a + len(blk)] = blk
    return bytes(k)


def mystery_card(w=256, h=285):
    """The mystery roll's picker card: the ACROS cartridge body (near-black, says nothing about the film) with '?' on the strip, and a large
    orange question mark over the colour field."""
    import film_mode_art as fma
    im = Image.new('RGBA', (w, h), (50, 50, 51, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w - 1, h - 1], outline=(99, 100, 102, 255), width=2)
    ch = h - 40
    fma.FILMS.append(('', '?', (40, 40, 44), (18, 18, 20), 'mystery: no name, plain dark field'))   # a nameless film, for this drawing only
    try:
        cart = fma.canister(ch * 2, None, len(fma.FILMS) - 1, ss=2, code='?', detail=True, vcode=False)
    finally:
        fma.FILMS.pop()
    cart = cart.resize((round(cart.width * ch / cart.height), ch), Image.LANCZOS)
    x0, y0 = (w - cart.width) // 2, (h - ch) // 2
    im.alpha_composite(cart, (x0, y0))
    q = fma.font(int(ch * 0.55))
    cx, cy = x0 + cart.width * 0.58, y0 + ch * 0.50
    for dx, dy, col in ((3, 3, (0, 0, 0, 200)), (0, 0, ORANGE_TILE)):
        d.text((cx + dx, cy + dy), '?', font=q, fill=col, anchor='mm', stroke_width=2, stroke_fill=(20, 20, 20, 255))
    return im.convert('RGB').quantize(colors=48, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).convert('RGBA')


def scene_tile(film, w=58, h=54):
    """The live view's mode icon (58 x 54, group 803) for a film: the crisp small cartridge in the transparent key colour."""
    text = {v: k for k, v in CART_FILM.items()}[film]
    cart = cartridge(h, text, 'white')
    out = Image.new('RGBA', (w, h), KEY)
    out.paste(cart, ((w - cart.width) // 2, 0))
    return out


def patch_scene_tiles(k, tile_look):
    """Film build: the live view shows the scene's own icon as the mode icon in SCENE (Beauty Shot's face for the first card ...). Each of the
    twelve scene icons (skin images, tile_look: image -> look) becomes that card's film cartridge."""
    k = bytearray(k)
    offs = skin.images(bytes(k))
    for idx, look in tile_look.items():
        a = offs[idx]
        w, h, size, typ = struct.unpack_from('<4I', k, a)
        blk = skin.encode(w, h, scene_tile(look, w, h).tobytes())
        if len(blk) > size:
            raise ValueError('scene tile %d is %d bytes, slot %d' % (idx, len(blk), size))
        k[a:a + len(blk)] = blk
    return bytes(k)


ORANGE_TILE = (255, 128, 0, 255)


def _tile_base(w, h):
    from PIL import ImageDraw
    out = Image.new('RGBA', (w, h), KEY)
    ImageDraw.Draw(out).rounded_rectangle([0, 0, w - 1, h - 1], 7, fill=(28, 28, 30, 255), outline=ORANGE_TILE, width=2)
    return out


def _crisp(im, step=32):
    """alpha >= 128 -> opaque, colours snapped (flat colours keep the RLE small)"""
    px = im.load()
    out = Image.new('RGBA', im.size, (0, 0, 0, 0))
    op = out.load()
    for y in range(im.height):
        for x in range(im.width):
            r_, g_, b_, a_ = px[x, y]
            if a_ >= 128:
                op[x, y] = tuple(min(255, (v + step // 2) // step * step) for v in (r_, g_, b_)) + (255,)
    return out


def wind_tile(w=58, h=54):
    """Live-view mode icon spot while the film must be wound on: the front dial with a curved arrow, orange on a dark tile (drawn at its real
    size without anti-aliasing: the slot of this skin image is small)."""
    import math
    from PIL import ImageDraw
    out = _tile_base(w, h)
    d = ImageDraw.Draw(out)
    cx, cy = w // 2 - 2, h // 2 + 3
    r = 11
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(60, 60, 64, 255), outline=ORANGE_TILE, width=3)
    d.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=ORANGE_TILE)
    R = 17
    d.arc([cx - R, cy - R, cx + R, cy + R], 200, 335, fill=ORANGE_TILE, width=3)
    a = math.radians(335)
    tip = (cx + math.cos(a) * R, cy + math.sin(a) * R)
    tx, ty = -math.sin(a), math.cos(a)
    nx, ny = math.cos(a), math.sin(a)
    d.polygon([(tip[0] + tx * 8, tip[1] + ty * 8), (tip[0] + nx * 5, tip[1] + ny * 5), (tip[0] - nx * 5, tip[1] - ny * 5)], fill=ORANGE_TILE)
    return out


def full_tile(w=58, h=54):
    """Mode icon spot for a full roll: the greyed cartridge with an orange cross."""
    from PIL import ImageDraw
    out = _tile_base(w, h)
    cart = cartridge(h - 6, 'STD', 'grey')
    keyed = Image.new('RGBA', cart.size, (0, 0, 0, 0))
    cp, kp = cart.load(), keyed.load()
    for y in range(cart.height):
        for x in range(cart.width):
            if cp[x, y][:3] != KEY[:3]:
                kp[x, y] = cp[x, y]
    out.paste(keyed, ((w - cart.width) // 2 - 3, 3), keyed)
    d = ImageDraw.Draw(out)
    cx, cy, r = w - 17, h - 17, 8
    d.line([cx - r, cy - r, cx + r, cy + r], fill=ORANGE_TILE, width=4)
    d.line([cx - r, cy + r, cx + r, cy - r], fill=ORANGE_TILE, width=4)
    return out


def patch_state_tiles(k, tiles):
    """Film build: skin images (tiles: image -> function drawing it) replaced; each must fit its slot."""
    k = bytearray(k)
    offs = skin.images(bytes(k))
    ends = sorted(offs)
    for idx, fn in tiles.items():
        a = offs[idx]
        w, h, _, typ = struct.unpack_from('<4I', k, a)
        size = ends[ends.index(a) + 1] - a
        blk = skin.encode(w, h, fn(w, h).tobytes())
        if len(blk) > size:
            raise ValueError('state tile %d is %d bytes, slot %d' % (idx, len(blk), size))
        k[a:a + len(blk)] = blk
    return bytes(k)


BIG_W, BIG_H = 80, 96                      # the film mode's big cartridge (live view), pixels
BIG_HOLE = (10, 20, 40, 44)                # x0, y0, x1, y1 of the window in the white strip where the shots-left digits show through


def big_cartridge(film, w=BIG_W, h=BIG_H):
    """The live view's film icon in the film build: a bigger, crisp cartridge with a BLANK white strip and a transparent window in it; the
    camera's own shots-left digits (a layout group drawn below this one) show through the window."""
    import film_mode_art as fma
    im = fma.canister(h, None, film, ss=1, code=None, detail=False, flat=True, vcode=False, crisp=True)
    out = Image.new('RGBA', (w, h), KEY)
    px, op = im.load(), out.load()
    for y in range(min(h, im.height)):
        for x in range(min(w, im.width)):
            r_, g_, b_, a_ = px[x, y]
            if a_ >= 128:
                op[x, y] = (r_ // 8 * 8, g_ // 8 * 8, b_ // 8 * 8, 255)
    x0, y0, x1, y1 = BIG_HOLE
    for y in range(y0, y1):
        for x in range(x0, x1):
            op[x, y] = KEY
    return out


def patch_big_cartridges(k):
    """Film build: the white 64 px film icons (images 414-424) become the big cartridge; the images change size (the layout nodes must follow)."""
    k = bytearray(k)
    offs = skin.images(bytes(k))
    ends = sorted(offs)
    for idx, code in SETS['white'].items():
        a = offs[idx]
        size = ends[ends.index(a) + 1] - a
        blk = skin.encode(BIG_W, BIG_H, big_cartridge(CART_FILM[CODES[code]]).tobytes())
        if len(blk) > size:
            raise ValueError('big cartridge %d is %d bytes, slot %d' % (idx, len(blk), size))
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

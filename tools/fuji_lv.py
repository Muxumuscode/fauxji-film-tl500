"""FAUXJI shooting screen (live view) and mode dial, Fuji-style.

Found by drawing the live-view layout tree (root node 742) image by image:
- mode icon, bottom left (group 803 at (5,426), one child per mode): 115 SMART, 1 P,
  8 A, 116 S, 9 M, 231 DUAL IS, 0 movie, 17 playback (blue cameras, 58x54). The mode
  dial shows the same images for the selected mode and grey ones for the others:
  107 A, 108 DUAL, 109 M, 110 movie, 111 P, 113 S (112 SCENE text, kept).
- 119: bottom info bar 640x54 (dark gradient); 92: 640x46 title bar of the guide screens.
- 43: the box behind aperture / shutter (151x39); the digits are separate images.
- 278 / 312: exposure scale, stacked at (260,436): 278 is a light panel with the numbers
  -2..2 cut out (y 3-20) and a window over 312, which holds a darker band and the ticks
  (y 21-33). 561: AEL tag (50x38, light panel with the letters cut out).
- 317 SCENE (selected, blue text), 226 SMART and 112 SCENE (grey, unselected): dial icons.
- 140-155, 316, 520: orange scene icons Smart Auto shows when it detects a scene; the
  scene-mode ones (239-251) are already white tiles with dark glyphs.
- 195-206, 559: the scene picker's sample photos (256x285, own icon top left).
- gadget_modedial_bg.raw (SPID.Rom): the mode dial wheel, 310x308 straight RGBA, no
  header (white gear-edged disc, white selection band from the left edge to the hub).
Fuji (X-T20 manual): no panels over the picture, thin black strips, flat white marks,
the mode shown as a letter.

Run from project root:  python tools/fuji_lv.py preview <out.png>
"""
import os, struct, sys
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
import skin, spid_files

KEY = (255, 0, 255, 255)
CLEAR = (0, 0, 0, 0)
WHITE = (240, 240, 240, 255)
GREY = (150, 150, 152, 255)
INK = (34, 31, 31, 255)
FONT = r'C:\Windows\Fonts\bahnschrift.ttf'

MODE_TAGS = {115: 'SR+', 1: 'P', 8: 'A', 116: 'S', 9: 'M', 231: 'DUAL', 0: 'movie', 17: 'play',
             317: 'SCN'}
DIAL_TAGS = {107: 'A', 108: 'DUAL', 109: 'M', 110: 'movie', 111: 'P', 113: 'S', 226: 'SR+',
             112: 'SCN'}
ORANGE_TILES = tuple(range(140, 156)) + (316, 520)
SCENE_CARDS = tuple(range(195, 207)) + (559,)
STRIPS = {119: (640, 54), 92: (640, 46)}
STRIP = (0, 0, 0, 150)                  # ~60% black
CLEARED = (43,)                          # aperture/shutter box: numbers only
LINE_ART = ()
EV_NUMBERS, EV_TICKS, AEL = 278, 312, 561
DIAL = 'gadget_modedial_bg.raw'
DIAL_SIZE = (310, 308)


def _font(size):
    f = ImageFont.truetype(FONT, size)
    try:
        f.set_variation_by_name('Bold Condensed')
    except Exception:
        pass
    return f


def _glyph(d, kind, box, ink):
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if kind == 'movie':
        d.rectangle([cx - 13, cy - 6, cx + 5, cy + 8], fill=ink)
        d.polygon([(cx + 5, cy - 2), (cx + 13, cy - 7), (cx + 13, cy + 9), (cx + 5, cy + 4)], fill=ink)
        d.ellipse([cx - 13, cy - 15, cx - 5, cy - 7], fill=ink)
        d.ellipse([cx - 4, cy - 15, cx + 4, cy - 7], fill=ink)
    else:                                       # play
        d.polygon([(cx - 7, cy - 10), (cx - 7, cy + 10), (cx + 10, cy)], fill=ink)


def tag(text, selected, size=(58, 54)):
    """Fuji-style mode tag: white with a black letter, or a grey outline when not selected."""
    w, h = size
    im = Image.new('RGBA', size, KEY)
    d = ImageDraw.Draw(im)
    d.fontmode = '1'
    box = [6, 9, w - 7, h - 10]
    if selected:
        d.rounded_rectangle(box, 5, fill=WHITE)
        ink = INK
    else:
        d.rounded_rectangle(box, 5, outline=GREY, width=2)
        ink = GREY
    if text in ('movie', 'play'):
        _glyph(d, text, box, ink)
    else:
        f = _font(30 if len(text) == 1 else 20 if len(text) <= 3 else 15)
        l, t, r, b = d.textbbox((0, 0), text, font=f)
        d.text(((box[0] + box[2] - (r - l)) / 2 - l, (box[1] + box[3] - (b - t)) / 2 - t), text,
               font=f, fill=ink)
    return im


def line_art(im):
    """Dark marks -> white, everything else transparent (keeps the exact layout)."""
    im = im.convert('RGBA')
    out = Image.new('RGBA', im.size, KEY)
    src, dst = im.load(), out.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = src[x, y]
            if (r, g, b) == (255, 0, 255) or a < 128:
                continue
            lum = (r * 3 + g * 6 + b) / 10
            if lum < 110:
                dst[x, y] = WHITE
            elif r > 150 and g < 90:                       # red marks (the -2 warning) stay red
                dst[x, y] = (230, 40, 30, 255)
    return out


def cutouts(im, y0, y1, margin):
    """Letters cut out of a light panel (278 numbers, 561 AEL) become white, the panel clear."""
    im = im.convert('RGBA')
    out = Image.new('RGBA', im.size, KEY)
    src, dst = im.load(), out.load()
    for y in range(y0, y1):
        for x in range(margin, im.width - margin):
            if src[x, y][:3] == (255, 0, 255):
                dst[x, y] = WHITE
    return out


def ev_ticks(im):
    """312: the ticks (darker than their strip) become white, the rest clear."""
    im = im.convert('RGBA')
    out = Image.new('RGBA', im.size, KEY)
    src, dst = im.load(), out.load()
    for y in range(21, im.height):
        for x in range(im.width):
            r, g, b, a = src[x, y]
            if (r, g, b) != (255, 0, 255) and (r * 3 + g * 6 + b) / 10 < 135:
                dst[x, y] = WHITE
    return out


def white_tile(im):
    """Orange tile with a white glyph -> white tile with a dark glyph (like 239-251)."""
    im = im.convert('RGBA')
    src = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = src[x, y]
            if (r, g, b) == (255, 0, 255):
                continue
            if r > 180 and 70 < g < 200 and b < 90:                       # orange
                src[x, y] = WHITE
            elif r > 200 and g > 200 and b > 200:                         # white glyph
                src[x, y] = INK
    return im


def scene_card(im):
    """Sample photo -> flat dark card with the photo's own corner icon, large and white."""
    W, H = im.size
    corner = im.convert('RGBA').crop((0, 0, 48, 44))
    mask = Image.new('L', corner.size, 0)
    cp, mp = corner.load(), mask.load()
    for y in range(corner.height):
        for x in range(corner.width):
            r, g, b, a = cp[x, y]
            if (r, g, b) != (255, 0, 255) and (r * 3 + g * 6 + b) / 10 > 105:
                mp[x, y] = 255
    card = Image.new('RGBA', (W, H), (50, 50, 51, 255))
    d = ImageDraw.Draw(card)
    d.rectangle([0, 0, W - 1, H - 1], outline=(99, 100, 102, 255), width=2)
    box = mask.getbbox()
    if box:
        g = mask.crop(box)
        s = 120 / max(g.width, g.height)
        g = g.resize((round(g.width * s), round(g.height * s)), Image.LANCZOS).point(lambda v: 255 if v > 110 else 0)
        card.paste(WHITE, ((W - g.width) // 2, (H - g.height) // 2 - 10), g)
    return card


def dial():
    """Flat dark wheel, grey ring with white dots, grey selection band, flat hub."""
    W, H = DIAL_SIZE
    s = 3
    im = Image.new('RGBA', (W * s, H * s), CLEAR)
    d = ImageDraw.Draw(im)
    cx, cy, R = 155 * s, 150 * s, 149 * s
    d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=(28, 27, 27, 225), outline=(99, 100, 102, 255),
              width=3 * s)
    import math
    for k in range(72):                                    # dotted ring, like the stock dial
        a = 2 * math.pi * k / 72
        x, y = cx + 137 * s * math.cos(a), cy + 137 * s * math.sin(a)
        d.ellipse([x - 1.6 * s, y - 1.6 * s, x + 1.6 * s, y + 1.6 * s], fill=(150, 150, 152, 255))
    d.rounded_rectangle([4 * s, 117 * s, cx, 185 * s], 10 * s, fill=(99, 100, 102, 240))   # band
    r = 44 * s
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(70, 70, 71, 255), outline=(150, 150, 152, 255),
              width=2 * s)
    return im.resize((W, H), Image.LANCZOS)


def patch_skin(k):
    k = bytearray(k)
    offs = skin.images(bytes(k))
    new = {}
    for i, t in MODE_TAGS.items():
        new[i] = tag(t, True)
    for i, t in DIAL_TAGS.items():
        new[i] = tag(t, False)
    for i, (w, h) in STRIPS.items():
        new[i] = Image.new('RGBA', (w, h), STRIP)
    for i in ORANGE_TILES + SCENE_CARDS:
        w, h, typ, px = skin.decode(bytes(k), offs[i])
        src = Image.frombytes('RGBA', (w, h), px)
        new[i] = white_tile(src) if i in ORANGE_TILES else scene_card(src)
    for i in CLEARED + LINE_ART + (EV_NUMBERS, EV_TICKS, AEL):
        w, h, typ, px = skin.decode(bytes(k), offs[i])
        src = Image.frombytes('RGBA', (w, h), px)
        if i in CLEARED:
            new[i] = Image.new('RGBA', (w, h), KEY)
        elif i == EV_NUMBERS:
            new[i] = cutouts(src, 3, 21, 8)
        elif i == AEL:
            new[i] = cutouts(src, 4, h - 4, 4)
        elif i == EV_TICKS:
            new[i] = ev_ticks(src)
        else:
            new[i] = line_art(src)
    for i, im in new.items():
        a = offs[i]
        w, h, size, typ = struct.unpack_from('<4I', k, a)
        assert (w, h) == im.size and typ == 3, (i, (w, h), im.size)
        blk = skin.encode(w, h, im.tobytes())
        assert len(blk) <= size, (i, len(blk), size)
        k[a:a + len(blk)] = blk
    return bytes(k)


def patch_rom(d):
    data = dial().tobytes()
    rec, off, size, slot = spid_files.directory(d)[DIAL]
    assert len(data) == size
    return spid_files.replace(d, DIAL, data)


if __name__ == '__main__':
    sheet = Image.new('RGBA', (900, 330), (60, 110, 60, 255))
    sheet.alpha_composite(dial(), (0, 0))
    x = 320
    for i, (t) in list(MODE_TAGS.items()) + list(DIAL_TAGS.items()):
        im = tag(t, i in MODE_TAGS)
        m = im.copy(); px = m.load()
        for yy in range(m.height):
            for xx in range(m.width):
                if px[xx, yy] == KEY:
                    px[xx, yy] = CLEAR
        sheet.alpha_composite(m, (x, 10 + 60 * ((x - 320) // 580)))
        x += 60
        if x > 860:
            x = 320
    sheet.save(sys.argv[2])

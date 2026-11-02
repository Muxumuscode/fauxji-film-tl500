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
# Status icons of the live-view tree (58x58, 64x64, 58x54; grey-white shaded glyphs with a
# dark edge, mean saturation <= 20): flattened to white with a near-black edge. Excludes
# the film canisters (414-424) and the opaque scene tiles (239-251).
FLAT_ICONS = (3, 10, 12, 15, 36, 37, 61, 63, 90, 141, 156, 211, 212, 213, 214, 215, 216, 217,
              232, 319, 320, 321, 322, 323, 324, 325, 346, 347, 348, 349, 350, 351, 352, 353,
              354, 355, 373, 374, 375, 376, 377, 378, 379, 380, 381, 382, 383, 385, 386, 387,
              388, 396, 397, 398, 399, 400, 401, 402, 410, 411, 425, 426, 427, 428, 434, 439,
              440, 444, 454, 455, 456, 457, 458, 459, 460, 461, 483, 484, 485, 535, 539, 541,
              545, 546, 547, 551, 552, 553, 554, 555, 556, 582, 588, 589, 590, 596, 666, 667,
              668, 672, 695)
EDGE = (20, 20, 20)
POPUP_PANELS = (13, 14, 565)             # glossy white pop-up panels -> flat dark
# Processing / formatting: 53 (4192x319, only x 0-523 used) = glossy white box; 38
# (2168x51, x 0-541 used) = white | cyan 271x51 button pair; the busy animation = dark knob
# 583 with cyan arcs 644-648 (the "blue eye"). Other leftover cyan: slider knobs and dots
# 42, 103, 615, 689, focus frame 6, sliders 104, 710.
WIDE_PANEL = (53, 524)                   # image, used width
BUTTON_PAIR = (38, 542)
DESAT = (644, 645, 646, 647, 648, 42, 103, 615, 689, 6, 104, 710)
# Help bar key caps (tree 1941 and the menus' Menu / OK / Fn / move / zoom ... keys): 74x37
# (542: 104x37) navy caps with a light edge and white legend, stored as type 1 images
# (runs only, same token scheme). Fuji: grey chip, dark legend ("BACK" chip, (143,145,147)).
KEY_CAPS = (44, 45, 46, 47, 48, 49, 50, 51, 670, 602, 617, 578, 542, 218, 252, 591)
CHIP = (143, 145, 147, 255)
# Other 640x480 screens still in Samsung blue: desaturated and darkened
NEUTRAL_BGS = ('bg_datetime_dmy.jpg', 'bg_datetime_mdy.jpg', 'bg_datetime_ymd.jpg',
               'bg_facelist.jpg', 'bg_firmware_update_01.jpg', 'bg_firmware_update_02.jpg',
               'bg_firmware_update_03.jpg', 'bg_language.jpg', 'bg_menu_hdmi_main.jpg',
               'bg_menu_hdmi_slideshow.jpg', 'bg_timezone.jpg', 'bg_voicerecord.jpg')
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


def popup_panel(size):
    w, h = size
    im = Image.new('RGBA', size, KEY)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], 10, fill=(50, 50, 51, 245), outline=(99, 100, 102, 255),
                        width=2)
    return im


def key_chip(im):
    im = im.convert('RGBA')
    p = im.load()
    W, H = im.size
    for y in range(H):
        for x in range(W):
            r, g, b, a = p[x, y]
            if (r, g, b) == (255, 0, 255):
                continue
            edge = x < 2 or y < 2 or x >= W - 2 or y >= H - 2
            glyph = min(r, g, b) > 150 and not edge
            p[x, y] = INK[:3] + (a,) if glyph else CHIP[:3] + (a,)
    return im


def _decode_any(k, a):
    """Decode a type 1 or 3 image (same tokens)."""
    w, h, size, typ = struct.unpack_from('<4I', k, a)
    raw = bytearray(k[a:a + size])
    struct.pack_into('<I', raw, 12, 3)
    return skin.decode(bytes(raw), 0)


def desat(im):
    """Cyan / blue -> neutral white-grey, same brightness (a little lifted), same alpha."""
    im = im.convert('RGBA')
    p = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = p[x, y]
            if (r, g, b) == (255, 0, 255):
                continue
            v = min(255, int(((r * 3 + g * 6 + b) / 10) * 1.2))
            p[x, y] = (v, v, v, a)
    return im


def wide_panel(size, used):
    w, h = size
    im = Image.new('RGBA', size, KEY)
    im.paste(popup_panel((used, h)), (0, 0))
    return im


def button_pair(size, used):
    w, h = size
    im = Image.new('RGBA', size, KEY)
    d = ImageDraw.Draw(im)
    half = used // 2
    d.rectangle([0, 0, half - 2, h - 1], fill=(70, 70, 71, 255))
    d.rectangle([half, 0, used - 1, h - 1], fill=WHITE)
    return im


def flat_icon(im):
    im = im.convert('RGBA')
    p = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = p[x, y]
            if (r, g, b) == (255, 0, 255):
                continue
            p[x, y] = WHITE[:3] + (a,) if (r * 3 + g * 6 + b) / 10 >= 105 else EDGE + (a,)
    return im


def neutral(data):
    """Samsung-blue JPEG -> neutral dark grey (luminance kept, scaled to 80%)."""
    import io
    im = Image.open(io.BytesIO(data)).convert('L').point(lambda v: int(v * 0.8)).convert('RGB')
    for q in range(90, 30, -5):
        b = io.BytesIO()
        im.save(b, 'JPEG', quality=q, subsampling=1)
        out = b.getvalue()
        if out[2:4] == b'\xff\xe0':                       # stock files start with DQT
            out = out[:2] + out[4 + int.from_bytes(out[4:6], 'big'):]
        if len(out) <= len(data) + 2048:
            return out
    raise ValueError('cannot fit')


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
    for i in KEY_CAPS:
        w, h, typ, px = _decode_any(bytes(k), offs[i])
        new[i] = key_chip(Image.frombytes('RGBA', (w, h), px))
    for i in POPUP_PANELS:
        w, h = struct.unpack_from('<2I', k, offs[i])
        new[i] = popup_panel((w, h))
    for (i, used), fn in ((WIDE_PANEL, wide_panel), (BUTTON_PAIR, button_pair)):
        w, h = struct.unpack_from('<2I', k, offs[i])
        new[i] = fn((w, h), used)
    for i in DESAT:
        w, h, typ, px = _decode_any(bytes(k), offs[i])
        new[i] = desat(Image.frombytes('RGBA', (w, h), px))
    for i in FLAT_ICONS:
        w, h, typ, px = skin.decode(bytes(k), offs[i])
        new[i] = flat_icon(Image.frombytes('RGBA', (w, h), px))
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
        assert (w, h) == im.size and typ in (1, 3), (i, (w, h), im.size)   # written as type 3
        blk = skin.encode(w, h, im.tobytes())
        assert len(blk) <= size, (i, len(blk), size)
        k[a:a + len(blk)] = blk
    return bytes(k)


def patch_rom(d):
    for name in NEUTRAL_BGS:
        rec, off, size, slot = spid_files.directory(d)[name]
        d = spid_files.replace(d, name, neutral(d[off:off + size]))
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

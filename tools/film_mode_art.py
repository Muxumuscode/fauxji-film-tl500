"""Mock-ups of the planned FILM CAMERA mode (docs/FEATURES.md item 11b) on the 640x480 screen, drawn on the PC only.

    python tools/film_mode_art.py <out dir>

Writes film_ready.png, film_wind.png, film_full.png, film_picker.png and film_sheet.png. Nothing here touches the firmware yet:
the art is drawn on a stand-in live view so the layout, sizes and colours can be judged before any skin.bin work. The real build
would need the canister without its number (one RLE image, magenta key colour as in badges.py) plus 10 digit sprites for the
tens and ones places, because the skin has no text size big enough (see the notes in FEATURES.md).

Design from photos of the real 35 mm cartridges (Fujifilm product photos, Velvia 100 and Provia 100F, Superia / QuickSnap row): black
plastic end caps and spool knob, the paper label wrapped round the body with a WHITE strip down the left carrying the frame count
(on the real cartridge "36" sits there, so the counter is where the real number is), and the film name running vertically in white
on the right, either on an identification-colour field (Provia: violet-blue) or on Fuji green with a colour band (Velvia: purple band,
Superia: red band). Colours sampled from the photos: Fuji green about #1F963D, Velvia band #6352B1, black plastic #121317, white strip
about #F2F2F4 (lit). Looks with no real stock behind them (marked in FILMS) use colours chosen to fit the same system. Fujifilm's
logo and packaging typeface are not used (the wordmark is custom artwork and the typeface is not published): names are in a bold
DIN-style sans. The counter digits are a bold condensed sans, like the printed "36".
"""
import math, os, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
import fonts

W, H = 640, 480
FONT = fonts.find_font()
SERIF_IT = r'C:\Windows\Fonts\palai.ttf'              # "Professional" italic serif (Palatino Italic), closest installed match
NAME_FONT = r'C:\Windows\Fonts\segoeuib.ttf'          # film names: humanist bold sans, Frutiger-like like the printed names
NAME_SQUEEZE = 0.88                                     # the printed names are a little narrower than Segoe UI Bold

FUJI_GREEN = (31, 150, 61)                           # cartridge label green sampled from the product photos
FUJI_GREEN_D = (22, 124, 50)
CREAM = (236, 241, 224)
WHITE_STRIP = (244, 244, 246)

# (name, short code, field top colour, field bottom colour, source)  -- Photo Style menu order.
# BANDS: a horizontal identification band across the field (index into FILMS).
FILMS = [
    ('PROVIA',         'PRO', (74, 63, 168),   (44, 42, 122),  'photo: Provia 100F cartridge, violet-blue field'),
    ('BLEACH BYPASS',  'BB',  (132, 136, 140), (74, 76, 80),   'chosen: neutral steel'),
    ('NOSTALGIC NEG.', 'NN',  (122, 54, 150),  (86, 38, 114),  'inspired by Pro 400H purple (#6B2C89 sampled from its box)'),
    ('ASTIA',          'AST', (196, 70, 128),  (134, 42, 90),  'chosen: pink magenta, not checked against a real Astia'),
    ('VELVIA',         'VEL', FUJI_GREEN,      FUJI_GREEN_D,   'photo: Velvia 100 cartridge, green field with a purple band'),
    ('REALA ACE',      'RA',  FUJI_GREEN,      FUJI_GREEN_D,   'chosen: green field with a teal band'),
    ('CLASSIC CHROME', 'CC',  (150, 126, 70),  (96, 78, 42),   'chosen: olive khaki'),
    ('CLASSIC NEG.',   'CN',  FUJI_GREEN,      FUJI_GREEN_D,   'photo: Superia cartridges, green with a red band'),
    ('ETERNA',         'ET',  (84, 118, 152),  (48, 72, 102),  'chosen: cinema steel blue'),
    ('ACROS',          'ACR', (56, 52, 50),    (22, 20, 20),   'Neopan Acros box: near-black with brown'),
    ('SEPIA',          'SEP', (164, 116, 70),  (106, 70, 40),  'chosen: sepia brown'),
]
BANDS = {4: (99, 82, 177), 5: (0, 150, 150), 7: (214, 60, 48)}
ORANGE = (255, 138, 28)
CAN_H = 150            # canister height on the shooting screen (px of 480). 372 -> 236 -> 150: no viewfinder, the shot is framed here


def font(size, bold=True):
    f = ImageFont.truetype(FONT, max(1, int(size)))
    try:
        f.set_variation_by_name('Bold Condensed' if bold else 'Condensed')
    except Exception:
        pass
    return f


def name_font(size):
    try:
        return ImageFont.truetype(NAME_FONT, max(1, int(size)))
    except Exception:
        f = ImageFont.truetype(FONT, max(1, int(size)))
        try:
            f.set_variation_by_name('Bold SemiCondensed')
        except Exception:
            pass
        return f


def serif(size):
    try:
        return ImageFont.truetype(SERIF_IT, max(1, int(size)))
    except Exception:
        return font(size, False)


def live_view():
    """A made-up live view (sky, hills, a lamp post) so the overlay can be judged against something."""
    im = Image.new('RGB', (W, H))
    d = ImageDraw.Draw(im)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=(round(70 + 120 * t), round(120 + 90 * t), round(190 + 40 * t)))
    d.ellipse([90, 70, 170, 150], fill=(250, 236, 190))
    for k, (c, base, amp) in enumerate((((72, 94, 80), 330, 40), ((52, 72, 60), 380, 55), ((36, 50, 44), 430, 30))):
        pts = [(x, base - amp * math.sin(x / (110 + 30 * k) + k)) for x in range(0, W + 8, 8)] + [(W, H), (0, H)]
        d.polygon(pts, fill=c)
    d.rectangle([506, 210, 512, 440], fill=(30, 30, 34))
    d.ellipse([498, 196, 520, 218], fill=(255, 230, 150))
    return im.filter(ImageFilter.GaussianBlur(1.2))


def slanted(layer, text, fnt, cx, cy, fill, shear=0.22):
    """Centre `text` at (cx, cy) on an RGBA layer, sheared to the right like the italic names on the boxes."""
    l, t, r, b = fnt.getbbox(text)
    w, h = r - l + 8, b - t + 8
    tmp = Image.new('RGBA', (w + int(h * shear) + 8, h), (0, 0, 0, 0))
    ImageDraw.Draw(tmp).text((4 - l, 4 - t), text, font=fnt, fill=fill + (255,))
    tmp = tmp.transform(tmp.size, Image.AFFINE, (1, shear, -shear * h / 2, 0, 1, 0), Image.BICUBIC)
    layer.alpha_composite(tmp, (round(cx - tmp.width / 2), round(cy - tmp.height / 2)))


def gradient(w, h, top, bot):
    g = Image.new('RGBA', (w, h))
    gd = ImageDraw.Draw(g)
    for y in range(h):
        t = y / max(1, h - 1)
        gd.line([(0, y), (w, y)], fill=tuple(round(top[i] + (bot[i] - top[i]) * t) for i in range(3)) + (255,))
    return g


def grey(c):
    v = round(sum(c) / 3 * 0.55 + 30)
    return (v, v, v)


def vtext(layer, text, fnt, cx, cy, fill, squeeze=1.0):
    """Text rotated to read bottom-to-top (like the vertical wordmarks on the Superia cartridges), centred at (cx, cy)."""
    l, t, r, b = fnt.getbbox(text)
    tmp = Image.new('RGBA', (r - l + 6, b - t + 6), (0, 0, 0, 0))
    ImageDraw.Draw(tmp).text((3 - l, 3 - t), text, font=fnt, fill=fill + (255,))
    if squeeze != 1.0:
        tmp = tmp.resize((max(1, round(tmp.width * squeeze)), tmp.height), Image.LANCZOS)
    tmp = tmp.rotate(90, expand=True)
    layer.alpha_composite(tmp, (round(cx - tmp.width / 2), round(cy - tmp.height / 2)))


def fit(text, make, max_w, max_h, start, squeeze=1.0):
    """Largest font size (from `start` down) whose text fits max_w x max_h (width measured after the squeeze)."""
    s = start
    while s > 4:
        f = make(s)
        l, t, r, b = f.getbbox(text)
        if (r - l) * squeeze <= max_w and b - t <= max_h:
            return f
        s -= 1
    return make(4)


def canister(h, number, film, dim=False, ss=3, code=None, detail=True, flat=False, vcode=False, crisp=False):
    """35 mm cartridge from the product photos (see the module docstring): black plastic caps and spool knob, label with a white strip
    on the left (the frame count, or `code` in the picker), the film name vertical in white on the colour field, an optional band,
    a green foot, the leader with sprocket holes out of the slit. number = None: no digits. Returns an RGBA image h tall."""
    S = ss
    gw, gh = 100, 120
    u = h * S / gh
    name, short, ftop, fbot, _ = FILMS[film]
    band = BANDS.get(film)
    green, strip, white = FUJI_GREEN, WHITE_STRIP, (250, 250, 250)
    plastic, plastic_hi, leader, ink = (22, 23, 26), (74, 76, 84), (66, 66, 74), (14, 14, 16)
    if dim:
        ftop, fbot, green, strip, white = grey(ftop), grey(fbot), grey(green), (168, 168, 168), (205, 205, 205)
        band = grey(band) if band else None
        plastic, plastic_hi, leader, ink = (58, 58, 60), (96, 96, 98), (84, 84, 86), (52, 52, 54)
    im = Image.new('RGBA', (round(gw * u), round(gh * u)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    X = lambda *v: [round(x * u) for x in v]
    # leader out of the slit, transparent sprocket holes
    d.polygon([tuple(X(66, 44)), tuple(X(96, 44)), tuple(X(96, 48)), tuple(X(93, 52)), tuple(X(96, 56)), tuple(X(96, 98)),
               tuple(X(66, 98))], fill=leader + (255,))
    for yy in range(50, 96, 8):
        d.rounded_rectangle(X(90, yy, 94.5, yy + 4), round(0.8 * u), fill=(0, 0, 0, 0))
    # spool knob and black plastic caps (a lighter rim line, as on the moulded cap)
    d.rounded_rectangle(X(30, 2, 50, 13), round(2 * u), fill=plastic + (255,), outline=plastic_hi + (255,), width=max(1, round(0.6 * u)))
    for y0 in (11, 105):
        d.rounded_rectangle(X(6, y0, 74, y0 + 11), round(4.5 * u), fill=plastic + (255,), outline=plastic_hi + (255,),
                            width=max(1, round(0.7 * u)))
    d.rectangle(X(8, 22, 72, 105), fill=plastic + (255,))
    # label: 62 x 80 units
    lw, lh = round(60 * u), round(80 * u)
    label = Image.new('RGBA', (lw, lh), (0, 0, 0, 0))
    ld = ImageDraw.Draw(label)
    if crisp:
        ld.fontmode = '1'                                               # skin icons: no anti-aliasing (few flat colours, long runs)
    sw = round(28 * u)                                                  # white strip width
    ld.rectangle([0, 0, sw, lh], fill=strip + (255,))
    fx0 = sw
    if flat:                                                             # small skin icons: one colour (a gradient bands badly at 64 px)
        mid = tuple((a_ + b_) // 2 for a_, b_ in zip(ftop, fbot))
        ld.rectangle([fx0, 0, lw, round(64 * u)], fill=mid + (255,))
    else:
        label.alpha_composite(gradient(lw - fx0, round(64 * u), ftop, fbot), (fx0, 0))
    ld.rectangle([fx0, round(64 * u), lw, lh], fill=green + (255,))      # green foot
    if band:
        ld.rectangle([fx0, round(52 * u), lw, round(62 * u)], fill=band + (255,))
        ld.line([fx0, round(52 * u), lw, round(52 * u)], fill=white + (255,), width=max(1, round(0.6 * u)))
    ld.line([fx0, 0, fx0, lh], fill=(0, 0, 0, 40), width=max(1, round(0.5 * u)))
    field_h = (50 if band else 62) * u
    cx = fx0 + (lw - fx0) / 2
    if h >= 110 and detail:
        fnm = fit(name, name_font, field_h - 8 * u, 15 * u, round(16 * u), NAME_SQUEEZE)
        vtext(label, name, fnm, cx, field_h / 2 + 1 * u, white, NAME_SQUEEZE)
    # frame count (or the picker's short code) on the white strip
    if number is not None:
        txt = '%02d' % number
        fn = fit(txt, font, sw - 10 * u, 36 * u, round(60 * u))
        l, t, r, b = fn.getbbox(txt)
        ld.text((sw / 2 - (r - l) / 2 - l, 22 * u - (b - t) / 2 - t), txt, font=fn, fill=ink + (255,))
        if h >= 110:
            ld.line([4 * u, 43 * u, sw - 4 * u, 43 * u], fill=ink + (255,), width=max(1, round(0.7 * u)))
            fs = font(5.2 * u)
            for k, tx in enumerate(('135', 'EXP.')):
                l, t, r, b = fs.getbbox(tx)
                ld.text((sw / 2 - (r - l) / 2 - l, (50 + 7 * k) * u - t), tx, font=fs, fill=(70, 70, 74, 255))
    elif code and vcode:                                                # icons: the code as upright letters, one above the other, down the strip
        n = len(code)
        cell = (lh - 8 * u) / n                                         # room for each letter
        fv = fit('W', font, sw - 6 * u, cell * 0.92, round(60 * u))     # the widest letter must fit the strip, every letter its cell
        for k, ch in enumerate(code):
            l, t, r, b = fv.getbbox(ch)
            cy = 4 * u + cell * (k + 0.5)
            ld.text((sw / 2 - (r - l) / 2 - l, cy - (b - t) / 2 - t), ch, font=fv, fill=ink + (255,))
    elif code:
        fc = fit(code, font, sw - 9 * u, 20 * u, round(30 * u))
        l, t, r, b = fc.getbbox(code)
        ld.text((sw / 2 - (r - l) / 2 - l, 30 * u - (b - t) / 2 - t), code, font=fc, fill=ink + (255,))
    # cylinder shading: darker towards both edges
    for k in range(0 if crisp else round(4 * u)):
        a = round(46 * (1 - k / (4 * u)) ** 2)
        ld.line([k, 0, k, lh], fill=(0, 0, 0, a))
        ld.line([lw - 1 - k, 0, lw - 1 - k, lh], fill=(0, 0, 0, a))
    im.alpha_composite(label, (round(10 * u), round(23 * u)))
    return im.resize((round(gw * h / gh), h), Image.LANCZOS)


def wind_icon(size, lit=True, ss=4):
    """The front-dial wind-on icon: a dial wheel (knurled rim) seen from the side with a curved arrow turning it."""
    n = size * ss
    im = Image.new('RGBA', (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = ORANGE if lit else (120, 120, 120)
    cx = cy = n / 2
    r = n * 0.30
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(30, 30, 32, 255), outline=c + (255,), width=round(n * 0.045))
    for k in range(12):
        a = k * math.pi / 6
        d.line([cx + math.cos(a) * r * 0.62, cy + math.sin(a) * r * 0.62, cx + math.cos(a) * r * 0.9, cy + math.sin(a) * r * 0.9],
               fill=c + (255,), width=max(2, round(n * 0.03)))
    d.ellipse([cx - r * 0.22, cy - r * 0.22, cx + r * 0.22, cy + r * 0.22], fill=c + (255,))
    R = n * 0.43
    d.arc([cx - R, cy - R, cx + R, cy + R], 205, 335, fill=c + (255,), width=round(n * 0.07))
    a = math.radians(335)
    tip = (cx + math.cos(a) * R, cy + math.sin(a) * R)
    tx, ty = -math.sin(a), math.cos(a)
    nx, ny = math.cos(a), math.sin(a)
    hw, hl = n * 0.10, n * 0.16
    d.polygon([(tip[0] + tx * hl, tip[1] + ty * hl), (tip[0] + nx * hw, tip[1] + ny * hw), (tip[0] - nx * hw, tip[1] - ny * hw)],
              fill=c + (255,))
    return im.resize((size, size), Image.LANCZOS)


def paste(base, im, xy):
    base.paste(im, xy, im)


def hud(im, film_idx):
    d = ImageDraw.Draw(im)
    name, short, ptop, pbot, _ = FILMS[film_idx]
    d.rounded_rectangle([8, 8, 8 + 164, 8 + 36], 6, fill=(14, 14, 16))
    d.rectangle([8, 8, 14, 44], fill=ptop)
    d.text((24, 26), name, font=font(20), fill=(240, 240, 240), anchor='lm')
    d.rectangle([0, 426, W, H], fill=(10, 10, 12))
    for x, t in ((70, '1/125'), (200, 'F4.0'), (320, 'ISO 200')):
        d.text((x, 454), t, font=font(26), fill=(250, 250, 250), anchor='lm')
    d.text((W - 24, 454), 'AF', font=font(22), fill=(150, 150, 154), anchor='rm')


def screen(state, film_idx=6, left=24):
    base = live_view().convert('RGBA')
    hud(base, film_idx)
    full = state == 'full'
    can = canister(CAN_H, 0 if full else left, film_idx, dim=full)
    paste(base, can, (W - can.width - 6, 52))
    d = ImageDraw.Draw(base)
    if state == 'wind':
        ic = wind_icon(80)
        paste(base, ic, (12, 340))
        d.rounded_rectangle([88, 356, 262, 410], 10, fill=(14, 14, 16))
        d.text((102, 374), 'WIND ON', font=font(26), fill=ORANGE, anchor='lm')
        d.text((102, 397), 'turn the front dial', font=font(15, False), fill=(215, 215, 218), anchor='lm')
    elif full:
        d.rounded_rectangle([12, 330, 252, 416], 10, fill=(14, 14, 16))
        d.text((26, 354), 'ROLL FULL', font=font(32), fill=ORANGE, anchor='lm')
        d.text((26, 382), 'pick a new roll', font=font(20, False), fill=(235, 235, 238), anchor='lm')
        d.text((26, 402), 'press any button', font=font(14, False), fill=(150, 150, 154), anchor='lm')
    return base.convert('RGB')


# what each look is and what it suits (written from Fujifilm's own descriptions of the film simulations; the TL500 versions in
# this project are approximations of them). (kind, what it is, good for)
INFO = [
    ('SLIDE FILM  \u00b7  after Fujichrome Provia', 'Natural, balanced colour. The all-round standard.', 'everyday shooting, travel, landscapes'),
    ('EFFECT  \u00b7  cinema grit', 'Washed-out colour with hard, gritty contrast.', 'street, moody portraits, rainy cities'),
    ('COLOUR NEGATIVE  \u00b7  retro print', 'Warm amber highlights, deep shadows, 70s print feel.', 'family memories, golden hour, small towns'),
    ('SLIDE FILM  \u00b7  after Fujichrome Astia', 'Soft contrast and gentle colour, kind to skin.', 'portraits, fashion, people in soft light'),
    ('SLIDE FILM  \u00b7  after Fujichrome Velvia', 'Rich, saturated, punchy colour.', 'landscapes, flowers, autumn, big skies'),
    ('COLOUR NEGATIVE  \u00b7  Reala', 'True-to-life colour with crisp, firm contrast.', 'travel, interiors, products, daylight'),
    ('SLIDE FILM  \u00b7  muted', 'Muted colour with deep tones and a documentary mood.', 'street, documentary, overcast days'),
    ('COLOUR NEGATIVE  \u00b7  snapshot', 'Strong contrast, cool shadows, vintage snapshot colour.', 'street, everyday life, a retro look'),
    ('CINEMA FILM  \u00b7  Eterna', 'Subdued colour with a wide tonal range and rich shadows.', 'video, flat light, shots you will grade later'),
    ('BLACK & WHITE  \u00b7  after Neopan Acros', 'Sharp, fine grain and rich gradation of greys.', 'street, architecture, landscapes, portraits'),
    ('MONOCHROME  \u00b7  sepia', 'Warm brown single-tone, like an old print.', 'portraits, still life, nostalgic scenes'),
]


def picker(sel=6):
    im = Image.new('RGB', (W, H), (16, 16, 18))
    d = ImageDraw.Draw(im)
    d.text((24, 24), 'LOAD A ROLL', font=font(28), fill=(245, 245, 245), anchor='lm')
    d.text((W - 24, 24), '36 EXP.', font=font(22), fill=ORANGE, anchor='rm')
    d.line([24, 46, W - 24, 46], fill=(70, 70, 74), width=2)
    cols, cw, pitch = 4, 152, 90
    x0, y0 = (W - cols * cw) // 2, 54
    for i, (name, short, *_rest) in enumerate(FILMS):
        r, c = divmod(i, cols)
        x, y = x0 + c * cw, y0 + r * pitch
        if i == sel:
            d.rounded_rectangle([x + 3, y - 2, x + cw - 3, y + 84], 10, fill=(40, 40, 44), outline=ORANGE, width=3)
        can = canister(60, None, i, code=short)
        paste(im, can, (x + (cw - can.width) // 2, y + 3))
        f = font(15)
        while d.textlength(name, font=f) > cw - 14 and f.size > 9:
            f = font(f.size - 1)
        d.text((x + cw // 2, y + 72), name, font=f, fill=(245, 245, 245) if i == sel else (150, 150, 154), anchor='mm')
    # info panel for the highlighted film
    name, short, ftop, fbot, _src = FILMS[sel]
    kind, what, good = INFO[sel]
    px0, py0, px1, py1 = 24, 330, W - 24, 450
    d.rounded_rectangle([px0, py0, px1, py1], 10, fill=(28, 28, 32))
    d.rectangle([px0, py0 + 8, px0 + 6, py1 - 8], fill=ftop if sum(ftop) > 150 else (150, 150, 154))
    d.text((px0 + 22, py0 + 24), name, font=font(30), fill=(250, 250, 250), anchor='lm')
    d.text((px1 - 16, py0 + 24), kind, font=font(15, False), fill=(165, 165, 170), anchor='rm')
    d.text((px0 + 22, py0 + 60), what, font=name_font(18), fill=(235, 235, 238), anchor='lm')
    d.text((px0 + 22, py0 + 92), 'GOOD FOR', font=font(16), fill=ORANGE, anchor='lm')
    d.text((px0 + 22 + d.textlength('GOOD FOR', font=font(16)) + 12, py0 + 92), good, font=name_font(18), fill=(235, 235, 238), anchor='lm')
    d.text((W // 2, H - 14), 'front dial to choose  \u2022  shutter to load', font=font(15, False), fill=(150, 150, 154), anchor='mm')
    return im


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else 'out_film'
    os.makedirs(out, exist_ok=True)
    pics = {'film_ready': screen('ready', left=36), 'film_wind': screen('wind', left=35),
            'film_full': screen('full'), 'film_picker': picker()}
    for k, v in pics.items():
        v.save(os.path.join(out, k + '.png'))
    sheet = Image.new('RGB', (W * 2 + 30, H * 2 + 30), (60, 60, 64))
    for n, k in enumerate(pics):
        sheet.paste(pics[k], (10 + (n % 2) * (W + 10), 10 + (n // 2) * (H + 10)))
    sheet.save(os.path.join(out, 'film_sheet.png'))
    # big single canisters for judging the detail (the real size is CAN_H)
    strip = Image.new('RGB', (len(FILMS) * 130 + 10, 330), (30, 30, 34))
    for i in range(len(FILMS)):
        c = canister(300, 36, i)
        c = c.resize((round(c.width * 120 / c.width), round(c.height * 120 / c.width)), Image.LANCZOS) if False else c
        small = c.resize((round(c.width * 0.43), round(c.height * 0.43)), Image.LANCZOS)
        paste(strip, small, (10 + i * 130, 10))
    strip.save(os.path.join(out, 'film_canisters_detail.png'))
    print('written to', out)


if __name__ == '__main__':
    main()

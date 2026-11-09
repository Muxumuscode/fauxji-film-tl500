"""Render the FAUXJI boot screen (640x480 JPEG that fits the TL500 power-on slot).

The camera's power-on image is `bg_power_on_off_422.jpg` in SPID.Rom: 640x480,
baseline, 4:2:2, slot of 22,528 bytes. This renders the design and lowers JPEG
quality until it fits.

Run from project root:  python tools/bootscreen.py <out.jpg> [variant]
"""
import io, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, SLOT = 640, 480, 22528
import fonts
FONT = fonts.find_font()
RED = (226, 30, 40)

TAGLINES = {
    'original': ['SAMSUNG HARDWARE. SCHNEIDER-KREUZNACH LENS.',
                 'FAUXJI COLOR SCIENCE.',
                 'ABSOLUTELY NO IDEA WHO IS IN CHARGE.'],
    'firmware': ['KOREAN BODY. GERMAN GLASS. JAPANESE COLORS.',
                 'FIRMWARE BY AN ECONOMIST AND A CHATBOT.',
                 'WARRANTY VOID SINCE 2026.'],
    'committee': ['SAMSUNG HARDWARE. SCHNEIDER-KREUZNACH LENS.',
                  'FAUXJI COLOR SCIENCE.',
                  'DESIGNED BY COMMITTEE. NONE OF THEM AGREED.'],
}


def font(size, style='Bold'):
    f = ImageFont.truetype(FONT, size)
    try:
        f.set_variation_by_name(style)
    except Exception:
        pass
    return f


def render(variant='original'):
    im = Image.new('RGB', (W, H), (12, 12, 13))
    # faint vignette so the black isn't flat
    glow = Image.new('L', (W, H), 0)
    ImageDraw.Draw(glow).ellipse([-120, -60, W + 120, H + 60], fill=26)
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    im = Image.composite(Image.new('RGB', (W, H), (34, 34, 36)), im, glow)
    d = ImageDraw.Draw(im)

    # wordmark: "FAUXJI FILM X20", red wedge across the J
    title = font(64, 'Bold')
    parts = [('FAUX', None), ('J', 'wedge'), ('I FILM X20', None)]
    widths = [d.textlength(t, font=title) for t, _ in parts]
    x = (W - sum(widths)) / 2
    y = 118
    for (t, mark), w in zip(parts, widths):
        d.text((x, y), t, font=title, fill=(244, 244, 240))
        if mark == 'wedge':
            # recolour the top of the letter red, split on a diagonal, clipped to the glyph
            glyph = Image.new('L', (W, H), 0)
            ImageDraw.Draw(glyph).text((x, y), t, font=title, fill=255)
            l, top, r, bot = d.textbbox((x, y), t, font=title)
            mid = top + (bot - top) * 0.45
            cut = Image.new('L', (W, H), 0)
            ImageDraw.Draw(cut).polygon([(l - 2, top - 2), (r + 2, top - 2),
                                         (r + 2, mid - 10), (l - 2, mid + 10)], fill=255)
            from PIL import ImageChops
            im.paste(RED, mask=ImageChops.multiply(glyph, cut))
        x += w

    sub = font(30, 'SemiBold')
    t = 'Digital Camera'
    d.text(((W - d.textlength(t, font=sub)) / 2, 214), t, font=sub, fill=(222, 222, 218))

    # divider with a small chevron
    yl = 268
    for i, c in enumerate((70, 120, 170)):
        d.line([(60 + i * 40, yl), (W - 60 - i * 40, yl)], fill=(c, c, c), width=1)
    d.line([(304, yl), (320, yl + 12), (336, yl)], fill=(170, 170, 170), width=3)

    body = font(21, 'SemiBold Condensed')
    for i, line in enumerate(TAGLINES[variant]):
        d.text(((W - d.textlength(line, font=body)) / 2, 300 + i * 30), line,
               font=body, fill=(232, 232, 228))
    return im


ORANGE = (255, 138, 20)
FILM_BASE = (52, 30, 16)                 # a developed negative's orange-brown base, darkened


def _wordmark(im, d, text_parts, y, size):
    """The FAUXJI wordmark with the red wedge across the J; text_parts = [(text, mark)], centred."""
    from PIL import ImageChops
    title = font(size, 'Bold')
    widths = [d.textlength(t, font=title) for t, _ in text_parts]
    x = (W - sum(widths)) / 2
    for (t, mark), w in zip(text_parts, widths):
        d.text((x, y), t, font=title, fill=(244, 244, 240))
        if mark == 'wedge':
            glyph = Image.new('L', (W, H), 0)
            ImageDraw.Draw(glyph).text((x, y), t, font=title, fill=255)
            l, top, r, bot = d.textbbox((x, y), t, font=title)
            mid = top + (bot - top) * 0.45
            cut = Image.new('L', (W, H), 0)
            ImageDraw.Draw(cut).polygon([(l - 2, top - 2), (r + 2, top - 2), (r + 2, mid - 10), (l - 2, mid + 10)], fill=255)
            im.paste(RED, mask=ImageChops.multiply(glyph, cut))
        x += w


def _spaced(d, xy_centre_y, text, fnt, fill, tracking):
    """Centred text with extra letter spacing (tracking in px)."""
    widths = [d.textlength(ch, font=fnt) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x = (W - total) / 2
    for ch, w in zip(text, widths):
        d.text((x, xy_centre_y), ch, font=fnt, fill=fill)
        x += w + tracking


def render_tl500():
    """The FAUXJI boot screen with its original text ('original' taglines), model TL500, redrawn: a dark lens-aperture backdrop, a red
    light-leak glow from the right, tracked lettering, a fading divider with a red chevron."""
    import math
    from PIL import ImageChops
    im = Image.new('RGB', (W, H), (9, 9, 10))
    # soft centre lift and a red light leak bleeding in from the right edge
    glow = Image.new('L', (W, H), 0)
    ImageDraw.Draw(glow).ellipse([60, 40, W - 60, H - 40], fill=44)
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    im = Image.composite(Image.new('RGB', (W, H), (30, 30, 33)), im, glow)
    leak = Image.new('L', (W, H), 0)
    ImageDraw.Draw(leak).ellipse([W - 150, -140, W + 260, H + 60], fill=120)
    leak = leak.filter(ImageFilter.GaussianBlur(90))
    im = Image.composite(Image.new('RGB', (W, H), (150, 22, 26)), im, leak)
    leak2 = Image.new('L', (W, H), 0)
    ImageDraw.Draw(leak2).ellipse([W - 40, 60, W + 120, 300], fill=110)
    leak2 = leak2.filter(ImageFilter.GaussianBlur(40))
    im = Image.composite(Image.new('RGB', (W, H), (240, 110, 40)), im, leak2)
    d = ImageDraw.Draw(im)

    # the lens: an aperture of seven blades, ring markings, very dark, behind the wordmark
    cx, cy, R = W / 2, 158, 200
    ring = (34, 34, 38)
    d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=ring, width=2)
    d.ellipse([cx - R + 14, cy - R + 14, cx + R - 14, cy + R - 14], outline=(26, 26, 29), width=1)
    for k in range(60):                                          # the focus ring's ticks
        a = 2 * math.pi * k / 60
        r0 = R - (8 if k % 5 else 12)
        d.line([(cx + r0 * math.cos(a), cy + r0 * math.sin(a)), (cx + (R - 2) * math.cos(a), cy + (R - 2) * math.sin(a))],
               fill=(40, 40, 44), width=1)
    r_in, r_out = 70, R - 18
    for k in range(7):                                           # blade edges, tangent to the opening
        a = 2 * math.pi * k / 7 + 0.3
        px, py = cx + r_in * math.cos(a), cy + r_in * math.sin(a)
        tx, ty = -math.sin(a), math.cos(a)
        L = math.sqrt(r_out ** 2 - r_in ** 2)
        d.line([(px - tx * 8, py - ty * 8), (px + tx * L, py + ty * L)], fill=(38, 38, 42), width=2)

    # wordmark: FAUXJI FILM TL500 with the red wedge on the J
    _wordmark(im, d, [('FAUX', None), ('J', 'wedge'), ('I FILM TL500', None)], 116, 60)
    d = ImageDraw.Draw(im)
    sub = font(28, 'Light')
    _spaced(d, 198, 'Digital Camera', sub, (215, 215, 210), 5)

    # divider: a line that fades out to both sides, a small red chevron in the middle
    yl = 262
    for x in range(56, W - 56):
        t = 1 - abs(x - W / 2) / (W / 2 - 56)
        c = int(40 + 150 * t ** 1.5)
        d.point((x, yl), fill=(c, c, c))
    d.line([(306, yl - 5), (320, yl + 7), (334, yl - 5)], fill=RED, width=3)

    body = font(20, 'SemiBold Condensed')
    lines = TAGLINES['original']
    for i, line in enumerate(lines):
        col = (236, 236, 232) if i == 0 else (176, 176, 172) if i == 1 else (226, 70, 70)
        _spaced(d, 292 + i * 32, line, body, col, 1.5)
    return im


def render_film():
    """Film-build boot screen: a strip of developed 35 mm film across the top (sprocket holes, frame numbers and edge print in orange, four
    frames glowing in the colours of four looks), the FAUXJI FILM wordmark, TL500 and a film-camera tagline."""
    im = Image.new('RGB', (W, H), (10, 10, 11))
    glow = Image.new('L', (W, H), 0)
    ImageDraw.Draw(glow).ellipse([-160, 120, W + 160, H + 200], fill=40)
    glow = glow.filter(ImageFilter.GaussianBlur(110))
    im = Image.composite(Image.new('RGB', (W, H), (46, 30, 18)), im, glow)      # warm darkroom-safelight glow from below
    d = ImageDraw.Draw(im)

    # the strip
    y0, y1 = 22, 210
    d.rectangle([0, y0, W, y1], fill=FILM_BASE)
    hole_w, hole_h, pitch = 14, 18, 26
    for x in range(-6, W, pitch):
        for yy in (y0 + 6, y1 - 6 - hole_h):
            d.rounded_rectangle([x, yy, x + hole_w, yy + hole_h], 3, fill=(8, 8, 9))
    looks = [((58, 120, 70), (190, 200, 120)),     # Velvia: green to warm light
             ((40, 70, 120), (230, 180, 120)),     # Provia: blue dusk to sun
             ((70, 70, 72), (215, 215, 210)),      # Acros: greys
             ((90, 70, 40), (220, 170, 110))]      # Classic Chrome: khaki
    fw, gap, fy0, fy1 = 136, 14, y0 + 46, y1 - 46
    x = (W - (4 * fw + 3 * gap)) // 2
    for top, bot in looks:
        frame = Image.new('RGB', (fw, fy1 - fy0))
        fd = ImageDraw.Draw(frame)
        for k in range(frame.height):
            t = k / max(1, frame.height - 1)
            fd.line([(0, k), (fw, k)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bot)))
        sun = Image.new('L', frame.size, 0)
        ImageDraw.Draw(sun).ellipse([fw * 0.55, frame.height * 0.48, fw * 0.85, frame.height * 0.48 + fw * 0.3], fill=170)
        sun = sun.filter(ImageFilter.GaussianBlur(9))
        frame = Image.composite(Image.new('RGB', frame.size, (255, 236, 200)), frame, sun)
        im.paste(frame, (x, fy0))
        x += fw + gap
    edge = font(13, 'SemiBold Condensed')
    for k, x in enumerate(range(40, W, 150)):                 # edge print between the holes and the frames
        d.text((x, y0 + 27), 'FAUXJI 400', font=edge, fill=ORANGE)
        d.text((x + 92, y0 + 27), '%d' % (12 + k), font=edge, fill=ORANGE)
        ty = y1 - 41
        d.polygon([(x + 34, ty + 3), (x + 34, ty + 13), (x + 42, ty + 8)], fill=ORANGE)     # the frame arrow
        d.text((x + 46, ty), '%dA' % (12 + k), font=edge, fill=ORANGE)

    _wordmark(im, d, [('FAUX', None), ('J', 'wedge'), ('I FILM', None)], 234, 66)
    sub = font(38, 'Light')
    t = 'TL500'
    d.text(((W - d.textlength(t, font=sub)) / 2, 318), t, font=sub, fill=(226, 226, 222))
    d.line([(W / 2 - 150, 376), (W / 2 + 150, 376)], fill=(110, 76, 40), width=1)
    body = font(19, 'SemiBold Condensed')
    for i, line in enumerate(['36 EXPOSURES.  NO SECOND TAKES.', 'WIND ON, AND DEVELOP IT LATER.']):
        d.text(((W - d.textlength(line, font=body)) / 2, 388 + i * 28), line, font=body,
               fill=ORANGE if i == 0 else (222, 222, 218))
    return im


def fit(im):
    for q in range(95, 30, -3):
        b = io.BytesIO()
        im.save(b, 'JPEG', quality=q, subsampling=1)     # 4:2:2 like the stock image
        data = b.getvalue()
        if data[2:4] == b'\xff\xe0':                     # drop the JFIF APP0: stock starts with DQT
            data = data[:2] + data[4 + int.from_bytes(data[4:6], 'big'):]
        if len(data) <= SLOT:
            return data, q
    raise SystemExit('cannot fit the slot')


if __name__ == '__main__':
    out = sys.argv[1]
    variant = sys.argv[2] if len(sys.argv) > 2 else 'original'
    data, q = fit(render(variant))
    open(out, 'wb').write(data)
    print('%s: %d bytes (slot %d), quality %d' % (out, len(data), SLOT, q))

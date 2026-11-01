"""Render the FAUXJI boot screen (640x480 JPEG that fits the TL500 power-on slot).

The camera's power-on image is `bg_power_on_off_422.jpg` in SPID.Rom: 640x480,
baseline, 4:2:2, slot of 22,528 bytes. This renders the design and lowers JPEG
quality until it fits.

Run from project root:  python tools/bootscreen.py <out.jpg> [variant]
"""
import io, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, SLOT = 640, 480, 22528
FONT = r'C:\Windows\Fonts\bahnschrift.ttf'
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


def fit(im):
    for q in range(95, 30, -3):
        b = io.BytesIO()
        im.save(b, 'JPEG', quality=q, subsampling=1)     # 4:2:2 like the stock image
        if b.tell() <= SLOT:
            return b.getvalue(), q
    raise SystemExit('cannot fit the slot')


if __name__ == '__main__':
    out = sys.argv[1]
    variant = sys.argv[2] if len(sys.argv) > 2 else 'original'
    data, q = fit(render(variant))
    open(out, 'wb').write(data)
    print('%s: %d bytes (slot %d), quality %d' % (out, len(data), SLOT, q))

"""Icon designs for Sajin Genzō. Each function returns a 512 x 512 RGBA image.
python packaging/icons.py <out.png>   writes a comparison sheet (big and taskbar size)."""
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

S = 512
RED = (224, 55, 47, 255)
DARK = (27, 26, 26, 255)


def _font(names, size):
    for n in names:
        for base in ('', os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts')):
            try:
                return ImageFont.truetype(os.path.join(base, n) if base else n, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _tile(bg=DARK, radius=0.22):
    im = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * radius), fill=bg)
    return im


def _mask_to_tile(im, radius=0.22):
    m = Image.new('L', (S, S), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * radius), fill=255)
    out = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    out.paste(im, (0, 0), m)
    return out


def seal():
    """A red hanko seal (Japanese name stamp) with 現像 (genzō, developing) and 사진 (sajin, photo) under it."""
    im = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([12, 12, S - 12, S - 12], radius=70, fill=RED)
    d.rounded_rectangle([40, 40, S - 40, S - 40], radius=50, outline=(255, 244, 236, 255), width=12)
    k = _font(['YuGothB.ttc', 'msgothic.ttc', 'malgunbd.ttf'], 190)
    for i, ch in enumerate('現像'):
        d.text((S / 2, 160 + i * 185), ch, font=k, fill=(255, 246, 238, 255), anchor='mm')
    return im


def canister():
    """A 35 mm film cartridge (the FAUXJI cartridges), red band, film leader out of the slit."""
    im = _tile()
    d = ImageDraw.Draw(im)
    # leader
    d.rectangle([300, 190, 470, 330], fill=(70, 56, 46, 255))
    for x in range(312, 470, 34):
        d.rounded_rectangle([x, 198, x + 16, 214], radius=3, fill=DARK)
        d.rounded_rectangle([x, 306, x + 16, 322], radius=3, fill=DARK)
    # body
    d.rounded_rectangle([110, 70, 320, 110], radius=10, fill=(30, 30, 33, 255))            # top cap
    d.rounded_rectangle([110, 410, 320, 450], radius=10, fill=(30, 30, 33, 255))           # bottom cap
    d.rectangle([180, 40, 250, 72], fill=(30, 30, 33, 255))                                 # spool knob
    d.rectangle([122, 106, 308, 414], fill=(242, 238, 228, 255))                            # label
    d.rectangle([122, 106, 168, 414], fill=(250, 250, 250, 255))
    d.rectangle([168, 106, 308, 414], fill=RED)                                              # colour field
    d.rectangle([168, 340, 308, 414], fill=(40, 140, 70, 255))                              # green foot
    f = _font(['bahnschrift.ttf', 'arialbd.ttf'], 54)
    t = Image.new('RGBA', (300, 80), (0, 0, 0, 0))
    ImageDraw.Draw(t).text((150, 40), 'GENZŌ', font=f, fill=(255, 255, 255, 255), anchor='mm')
    t = t.rotate(90, expand=True)
    im.alpha_composite(t, (198, 105))
    return im


def tank():
    """A darkroom developing tank with a red lid, a strip of film curling out of it."""
    im = _tile()
    d = ImageDraw.Draw(im)
    glow = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([60, 20, 452, 300], fill=(224, 55, 47, 70))
    im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(40)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([140, 180, 372, 450], radius=34, fill=(52, 50, 54, 255))          # the tank
    for y in range(220, 440, 36):
        d.line([150, y, 362, y], fill=(66, 64, 68, 255), width=6)                         # grip rings
    d.rounded_rectangle([124, 130, 388, 196], radius=24, fill=RED)                        # the lid
    d.rounded_rectangle([222, 92, 290, 136], radius=12, fill=(190, 40, 34, 255))          # the funnel cap
    # film strip curling out
    d.arc([300, 230, 500, 470], start=200, end=330, fill=(196, 128, 74, 255), width=46)
    for a in range(212, 326, 16):
        x = 400 + 100 * math.cos(math.radians(a))
        y = 350 + 120 * math.sin(math.radians(a))
        d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=DARK)
    return im


def frame():
    """One frame of developed negative (orange base, sprocket holes) with a red rising sun inside: a photo, and the darkroom."""
    im = _tile((196, 128, 74, 255))
    d = ImageDraw.Draw(im)
    for x in range(28, S - 20, 62):
        d.rounded_rectangle([x, 26, x + 32, 70], radius=7, fill=(40, 26, 18, 255))
        d.rounded_rectangle([x, S - 70, x + 32, S - 26], radius=7, fill=(40, 26, 18, 255))
    d.rectangle([40, 100, S - 40, S - 100], fill=(24, 18, 16, 255))
    g = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(g).ellipse([150, 150, 362, 362], fill=(224, 55, 47, 160))
    im.alpha_composite(g.filter(ImageFilter.GaussianBlur(26)))
    d = ImageDraw.Draw(im)
    d.ellipse([176, 176, 336, 336], fill=RED)
    f = _font(['bahnschrift.ttf', 'arialbd.ttf'], 26)
    d.text((56, 86), 'GENZŌ 400', font=f, fill=(255, 220, 160, 255), anchor='lm')
    return _mask_to_tile(im)


DESIGNS = {'A  seal 現像': seal, 'B  film cartridge': canister, 'C  developing tank': tank, 'D  negative + red sun': frame}


def sheet(path):
    cell = 300
    out = Image.new('RGB', (cell * len(DESIGNS), cell + 120), (236, 234, 228))
    d = ImageDraw.Draw(out)
    f = _font(['bahnschrift.ttf', 'arial.ttf'], 22)
    for k, (name, fn) in enumerate(DESIGNS.items()):
        big = fn().resize((220, 220), Image.LANCZOS)
        out.paste(big, (k * cell + 40, 30), big)
        for j, sz in enumerate((48, 32, 16)):
            sm = fn().resize((sz, sz), Image.LANCZOS)
            out.paste(sm, (k * cell + 60 + j * 70, 262 + (48 - sz)), sm)
        d.text((k * cell + 40, 330), name, font=f, fill=(30, 30, 30))
    out.save(path)


if __name__ == '__main__':
    sheet(sys.argv[1])

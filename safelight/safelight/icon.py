"""Sajin Genzō's icon: a 35 mm film cartridge (like the FAUXJI camera's film icons) on a dark tile, the film leader coming out.

Two drawings: the full one (48 px and up) with the GENZŌ label and the leader's sprocket holes, and a bolder simplified one for the
small sizes (16-32 px: the taskbar, the window title), where thin details would turn to mush.
"""
import os

from PIL import Image, ImageDraw, ImageFont

S = 512
RED = (224, 55, 47, 255)
GREEN = (40, 140, 70, 255)
DARK = (27, 26, 26, 255)
CAP = (34, 34, 38, 255)
WHITE = (250, 250, 250, 255)


def _font(size):
    for n in ('bahnschrift.ttf', 'arialbd.ttf', 'DejaVuSans-Bold.ttf'):
        for base in ('', os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts')):
            try:
                return ImageFont.truetype(os.path.join(base, n) if base else n, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _tile():
    im = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.22), fill=DARK)
    return im


def full():
    im = _tile()
    d = ImageDraw.Draw(im)
    d.rectangle([300, 190, 470, 330], fill=(70, 56, 46, 255))                       # the leader
    for x in range(312, 470, 34):
        d.rounded_rectangle([x, 198, x + 16, 214], radius=3, fill=DARK)
        d.rounded_rectangle([x, 306, x + 16, 322], radius=3, fill=DARK)
    d.rounded_rectangle([110, 70, 320, 110], radius=10, fill=CAP)                  # caps and spool knob
    d.rounded_rectangle([110, 410, 320, 450], radius=10, fill=CAP)
    d.rectangle([180, 40, 250, 72], fill=CAP)
    d.rectangle([122, 106, 168, 414], fill=WHITE)                                   # the label: white strip, red field, green foot
    d.rectangle([168, 106, 308, 414], fill=RED)
    d.rectangle([168, 340, 308, 414], fill=GREEN)
    t = Image.new('RGBA', (300, 80), (0, 0, 0, 0))
    ImageDraw.Draw(t).text((150, 40), 'GENZŌ', font=_font(54), fill=WHITE, anchor='mm')
    im.alpha_composite(t.rotate(90, expand=True), (198, 105))
    return im


def small():
    im = _tile()
    d = ImageDraw.Draw(im)
    d.rectangle([330, 200, 490, 312], fill=(150, 110, 80, 255))                     # a short, bright leader
    d.rounded_rectangle([60, 56, 350, 116], radius=16, fill=(70, 70, 76, 255))     # caps
    d.rounded_rectangle([60, 396, 350, 456], radius=16, fill=(70, 70, 76, 255))
    d.rectangle([76, 108, 334, 404], fill=RED)                                      # a big red field
    d.rectangle([76, 108, 140, 404], fill=WHITE)
    d.rectangle([140, 320, 334, 404], fill=GREEN)
    return im


def image(size):
    """The icon at `size` pixels (RGBA)."""
    src = full() if size >= 48 else small()
    return src.resize((size, size), Image.LANCZOS)


ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def save_ico(path):
    """A Windows .ico with every size drawn from the right design."""
    imgs = [image(s) for s in ICO_SIZES]
    imgs[-1].save(path, sizes=[(s, s) for s in ICO_SIZES], append_images=imgs[:-1])


def save_png(path, size=512):
    image(size).save(path)

"""Film-look .cube LUTs for DxO PhotoLab (or any editor that loads 3D .cube files), built from the FAUXJI firmware look maths.

The camera's looks are, in order: a 3x3 colour matrix on linear RGB (tools/fauxji.py LOOKS; PROVIA = identity), a display-referred tone
curve (custom curves or Samsung's stock ones, read from your own stock .elf), and per-hue saturation (HUE deltas: band value v scales
chroma by 1 + v / 3500). A LUT is that same chain written as a table, relative to PROVIA, so it can sit on top of any neutral sRGB
render of the RAW (DxO's, for example) and give the look the camera's JPEG has. Input and output are sRGB.

Run from the project root:
    python tools/make_luts.py <stock .elf> <output dir>            write the 11 LUTs (size 64)
    python tools/make_luts.py --norm <stock .elf> <output dir>     same, but first match DxO's richer neutral colour to the camera's
                                                                    PROVIA (tools/dxo_norm.json, from tools/fit_dxo_norm.py)
    python tools/make_luts.py --check <stock .elf> <photo dir>     compare with the camera's own JPEGs: one scene, PROVIA first, then
                                                                    the other looks (camera JPEGs, they carry the look in the MakerNote)
"""
import os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fauxji as F

NAMES = {0: 'PROVIA', 1: 'ACROS', 2: 'Eterna', 3: 'Classic Neg', 4: 'Classic Chrome', 5: 'Reala Ace', 6: 'Velvia',
         7: 'ASTIA', 8: 'Sepia', 9: 'Bleach Bypass', 10: 'Nostalgic Neg'}
# hue band centres in degrees (HSV hue) for the camera's band order R, B, G, C, M, Y, and the kernel width
BAND_CENTRE = (15.0, 255.0, 120.0, 185.0, 325.0, 60.0)
BAND_WIDTH = 40.0
SAT_DIV = 3500.0
SIZE = 64
NORM = None                                                     # set by --norm: {'chroma', 'curve_x', 'curve_y'}


def srgb_to_lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def stock_curves(elf_path):
    d = open(elf_path, 'rb').read()
    o = F.STOCK_CURVES - F.B
    return [np.frombuffer(d[o + 256 * s:o + 256 * (s + 1)], dtype=np.uint8).astype(float) for s in range(9)]


def curve_for(look, stock):
    slot = F.STYLE_CURVE[look]
    if slot is None:
        return np.arange(256, dtype=float)                      # Contrast 0: identity (stock curve 2)
    for name, s in F.CURVE_SLOT.items():
        if s == slot:
            return np.frombuffer(F.monotone(F.CURVE_POINTS[name]), dtype=np.uint8).astype(float)
    return stock[slot]


def hue_of(rgb):
    mx, mn = rgb.max(-1), rgb.min(-1)
    d = mx - mn + 1e-9
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
    return h % 360


def normalise(rgb):
    """DxO neutral render -> the camera's PROVIA (luma tone curve, then chroma scale in gamma space)."""
    l = (rgb * np.array([0.299, 0.587, 0.114])).sum(-1, keepdims=True)
    l2 = np.interp(l, NORM['curve_x'], NORM['curve_y'])
    v = np.clip(rgb + (l2 - l), 0, 1)
    y = (v * np.array([0.299, 0.587, 0.114])).sum(-1, keepdims=True)
    return np.clip(y + (v - y) * NORM['chroma'], 0, 1)


def apply_look(rgb, look, stock):
    """rgb: (..., 3) sRGB 0..1 -> same shape, with the look on top of PROVIA."""
    if NORM:
        rgb = normalise(rgb)
    m = np.array(F.LOOKS[look])
    lin = srgb_to_lin(rgb) @ m.T
    v = lin_to_srgb(lin)
    cv = curve_for(look, stock)
    v = np.interp(v * 255.0, np.arange(256), cv) / 255.0
    delta = F.HUE[look]
    if any(delta):
        h = hue_of(v)
        f = np.ones(v.shape[:-1])
        for centre, dv in zip(BAND_CENTRE, delta):
            if dv:
                dh = np.abs((h - centre + 180) % 360 - 180)
                f += np.exp(-(dh / BAND_WIDTH) ** 2) * dv / SAT_DIV
        y = (v * np.array([0.299, 0.587, 0.114])).sum(-1, keepdims=True)
        v = np.clip(y + (v - y) * f[..., None], 0, 1)
    return np.clip(v, 0, 1)


def write_cube(path, title, size, fn):
    g = np.linspace(0, 1, size)
    b, gg, r = np.meshgrid(g, g, g, indexing='ij')               # .cube: red varies fastest
    rgb = np.stack([r, gg, b], -1).reshape(-1, 3)
    out = fn(rgb)
    with open(path, 'w', newline='\n') as f:
        f.write('TITLE "%s"\nLUT_3D_SIZE %d\nDOMAIN_MIN 0.0 0.0 0.0\nDOMAIN_MAX 1.0 1.0 1.0\n' % (title, size))
        np.savetxt(f, np.clip(out, 0, 1), fmt='%.6f')


def build(elf_path, out_dir):
    stock = stock_curves(elf_path)
    os.makedirs(out_dir, exist_ok=True)
    for k, name in NAMES.items():
        p = os.path.join(out_dir, 'FAUXJI %02d %s.cube' % (k + 1, name))
        write_cube(p, 'FAUXJI %s' % name, SIZE, lambda rgb, k=k: apply_look(rgb, k, stock))
        print('wrote', p)


def check(elf_path, photo_dir):
    """Compare the LUT maths with the camera's own JPEGs: a run of shots of one scene, the first in PROVIA and the rest in other looks
    (the look is the MakerNote byte 15650). Registration-free: the distance between per-channel quantile curves of the camera's shot
    and of the LUT applied to the PROVIA shot, against plain PROVIA. Smaller is closer."""
    import glob
    from PIL import Image
    stock = stock_curves(elf_path)
    q = np.linspace(2, 98, 25)

    def load(f):
        im = Image.open(f)
        style = im._getexif().get(37500)[15650]
        return np.asarray(im.convert('RGB').resize((480, 360))).astype(float) / 255, style

    def dist(a, b):
        return np.mean([np.abs(np.percentile(a[..., c], q) - np.percentile(b[..., c], q)).mean() for c in range(3)])
    shots = sorted(glob.glob(os.path.join(photo_dir, '*.JPG')) + glob.glob(os.path.join(photo_dir, '*.jpg')))
    res, base = {}, None
    for f in shots:
        im, k = load(f)
        if k == 0:
            base = im
            continue
        if base is None or k not in NAMES:
            continue
        res.setdefault(k, []).append((dist(base, im), dist(apply_look(base, k, stock), im)))
    print('look              PROVIA vs camera   LUT vs camera')
    for k in sorted(res):
        r = np.array(res[k])
        print('%-16s  %.4f             %.4f   %s' % (NAMES[k], r[:, 0].mean(), r[:, 1].mean(), 'closer' if r[:, 1].mean() < r[:, 0].mean() else 'FURTHER'))


if __name__ == '__main__':
    args = sys.argv[1:]
    if args[0] == '--norm':
        import json
        NORM = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dxo_norm.json')))
        args = args[1:]
    if args[0] == '--check':
        check(args[1], args[2])
    else:
        build(args[0], args[1])

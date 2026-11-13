"""The lab: negatives for the light table, development (what a real lab could do to a roll), prints and contact sheets.

Everything works on float32 RGB in 0..1 (display-referred, like the camera's JPEGs) with numpy, and uses Pillow for blurs and resizing.
Nothing here changes an original file.
"""
import hashlib
import random
from dataclasses import dataclass, asdict

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


# ---------------------------------------------------------------- recipe

PUSH_PULL = (-1, 0, 1, 2)
DEVELOPERS = {
    'standard': 'Standard',
    'fine': 'Fine grain',
    'acutance': 'High acutance',
    'contrast': 'High contrast',
}
PROCESSES = {
    'normal': 'Normal (as the film was meant)',
    'cross': 'Cross-processed',
    'bleach': 'Bleach bypass',
}
PAPERS = {
    'vintage': 'Vintage print (faded, warm)',
    'glossy': 'Glossy',
    'matte': 'Matte (soft blacks)',
    'warm': 'Warm-tone fibre',
    'neutral': 'Neutral fibre (black and white)',
}
# Black and white only. A coloured filter on the lens changes which colours come out light or dark (a red filter: dark skies, light
# skin); it works on photos from any camera (the FAUXJI camera already made its B&W frames). Weights on R, G, B before the mix.
BW_FILTERS = {
    'none': 'No filter',
    'yellow': 'Yellow (a little darker sky)',
    'orange': 'Orange (dark sky, smooth skin)',
    'red': 'Red (dramatic sky, light skin)',
    'green': 'Green (darker skin, light foliage)',
}
FILTER_WEIGHTS = {'none': (1.0, 1.0, 1.0), 'yellow': (1.15, 1.05, 0.55), 'orange': (1.45, 0.95, 0.30), 'red': (1.9, 0.6, 0.12),
                  'green': (0.7, 1.35, 0.6)}
TONES = {
    'none': 'Untoned',
    'selenium': 'Selenium (deeper, cool blacks)',
    'sepia': 'Sepia (warm brown)',
}
BORDERS = {
    'none': 'No border',
    'white': 'White border',
    'black': 'Black film-holder edge',
    'instant': 'Instant-print frame',
}


@dataclass
class Recipe:
    push: int = 0                 # stops: -1 pull, +1 / +2 push
    developer: str = 'standard'
    process: str = 'normal'
    # The defaults are the 'Vintage print' look: a roll a few years past its date, printed on faded warm paper with a white border, a little
    # more grain and halation than the film alone: what a box of old-school prints looks like.
    expired: int = 3              # years past the date
    grain: float = 1.15           # multiplier on the film's own grain
    halation: float = 1.25        # multiplier on the film's own halation
    leaks: bool = True            # light leaks on the first frames (and now and then)
    paper: str = 'vintage'
    border: str = 'white'
    auto_levels: bool = False     # gentle lab correction
    bw_filter: str = 'none'       # black and white: a coloured filter (photos from any camera)
    tone: str = 'none'            # black and white: toning of the print
    authentic: bool = True        # authentic scan (photos from other cameras): film-like softness and a soft highlight shoulder
    seed: int = 0                 # the roll's own randomness (leaks, expired-film cast)

    def describe(self):
        bits = []
        if self.push:
            bits.append('%s%d' % ('push +' if self.push > 0 else 'pull ', self.push))
        if self.developer != 'standard':
            bits.append(DEVELOPERS[self.developer].lower())
        if self.process != 'normal':
            bits.append(PROCESSES[self.process].lower())
        if self.expired:
            bits.append('expired %d yr' % self.expired)
        if self.paper != 'glossy':
            bits.append(PAPERS[self.paper].lower().split(' (')[0])
        if self.bw_filter != 'none':
            bits.append('%s filter' % self.bw_filter)
        if self.tone != 'none':
            bits.append('%s toned' % self.tone)
        if not self.authentic:
            bits.append('every pixel kept')
        return ', '.join(bits) or 'box speed, standard developer'

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# Ready-made looks (the 'Look' menu). 'Vintage print' is Recipe()'s defaults.
PRESETS = {
    'Vintage print': Recipe(),
    'Faded 70s snapshot': Recipe(push=-1, expired=8, grain=1.2, halation=1.3, paper='vintage', border='instant'),
    'Clean lab print': Recipe(expired=0, grain=1.0, halation=1.0, leaks=False, paper='glossy', border='none'),
    'Gritty push': Recipe(push=2, developer='contrast', expired=0, grain=1.4, halation=1.2, paper='glossy', border='black'),
    'Cross-processed': Recipe(push=1, process='cross', expired=0, grain=1.1, halation=1.3, paper='glossy', border='none'),
    'Darkroom fibre': Recipe(developer='acutance', expired=0, grain=1.0, halation=1.0, leaks=False, paper='warm', border='black'),
}


def preset_name(recipe):
    """The look a recipe matches (ignoring its seed), or None."""
    d = {k: v for k, v in recipe.to_dict().items() if k != 'seed'}
    for name, r in PRESETS.items():
        if {k: v for k, v in r.to_dict().items() if k != 'seed'} == d:
            return name
    return None


def surprise(rng=None):
    """A random recipe: the 'surprise me' lab mode."""
    rng = rng or random.Random()
    return Recipe(push=rng.choice(PUSH_PULL), developer=rng.choice(list(DEVELOPERS)),
                  process=rng.choices(list(PROCESSES), weights=(6, 2, 2))[0], expired=rng.choice((0, 0, 0, 2, 5, 10)),
                  grain=rng.choice((0.8, 1.0, 1.3)), halation=rng.choice((0.6, 1.0, 1.4)), leaks=rng.random() < 0.6,
                  paper=rng.choice(list(PAPERS)), border=rng.choice(list(BORDERS)),
                  bw_filter=rng.choice(('none', 'none', 'yellow', 'orange', 'red', 'green')),
                  tone=rng.choice(('none', 'none', 'selenium', 'sepia')), seed=rng.randrange(1 << 30))


# ---------------------------------------------------------------- helpers

def load(path, max_side=None):
    """RGB float32 0..1. max_side: decode at reduced size (fast JPEG draft) for previews."""
    with Image.open(path) as im:
        if max_side:
            im.draft('RGB', (max_side, max_side))
        im = ImageOps.exif_transpose(im)             # phones store upright photos sideways with a note: turn them (TL500: no note)
        im = im.convert('RGB')
        if max_side and max(im.size) > max_side:
            im.thumbnail((max_side, max_side), Image.LANCZOS)
        return np.asarray(im, dtype=np.float32) / 255.0


def to_image(a):
    return Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8), 'RGB')


def luma(a):
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


def _blur_l(mask, radius):
    """Gaussian blur of a 0..1 single-channel array (through an 8-bit image; fine for masks and glows)."""
    im = Image.fromarray((np.clip(mask, 0, 1) * 255).astype(np.uint8), 'L').filter(ImageFilter.GaussianBlur(radius))
    return np.asarray(im, dtype=np.float32) / 255.0


def _curve(x, contrast, pivot=0.5):
    """S-shaped contrast around a pivot; contrast 1 = unchanged."""
    if contrast == 1:
        return x
    y = (x - pivot) * contrast + pivot
    return y if contrast < 1 else pivot + np.tanh((y - pivot) * 1.6) / 1.6


def _seed(*parts):
    return int(hashlib.sha1(repr(parts).encode()).hexdigest()[:8], 16)


# ---------------------------------------------------------------- the negative (light table)

ORANGE_MASK = np.array([0.92, 0.62, 0.40], dtype=np.float32)


def negative(a, film):
    """How the developed negative looks on a light table: colour films inverted on an orange mask, B&W as a grey negative."""
    if film.mono:
        n = 1.0 - luma(a)
        n = 0.12 + 0.78 * n
        return np.repeat(n[..., None], 3, axis=2) * np.array([0.96, 0.96, 0.98], dtype=np.float32)
    inv = 1.0 - a
    inv = 0.10 + 0.72 * inv                               # a negative's density range is lower than a print's
    return inv * ORANGE_MASK + np.array([0.06, 0.03, 0.0], dtype=np.float32)


# ---------------------------------------------------------------- development

LEAK_CHANCE = 0.05

# The films' colour, for photos from any camera (FAUXJI rolls already have it: the camera applied the look). Per film: saturation,
# contrast, a tint for the shadows and one for the highlights (RGB offsets), and for black and white the channel mix.
LOOKS = {
    'PROV': dict(sat=1.06, contrast=1.06, shadows=(0, 0, 0.01), highlights=(0.01, 0.005, 0)),
    'VELV': dict(sat=1.38, contrast=1.16, shadows=(0.01, -0.01, 0.02), highlights=(0.02, 0.01, -0.01)),
    'ASTI': dict(sat=1.04, contrast=0.92, shadows=(0.005, 0, 0.01), highlights=(0.02, 0.01, 0)),
    'CCHR': dict(sat=0.74, contrast=1.10, shadows=(-0.01, 0.01, 0.02), highlights=(0.03, 0.02, -0.01)),
    'CNEG': dict(sat=0.92, contrast=1.20, shadows=(-0.02, 0.01, 0.03), highlights=(0.03, 0.0, 0.0)),
    'NOST': dict(sat=0.94, contrast=1.06, shadows=(0.0, -0.005, 0.01), highlights=(0.05, 0.03, -0.03)),
    'REAL': dict(sat=1.00, contrast=1.08, shadows=(-0.005, 0.005, 0.01), highlights=(0.0, 0.0, 0.0)),
    'ETRN': dict(sat=0.70, contrast=0.86, shadows=(-0.02, 0.01, 0.02), highlights=(0.01, 0.01, 0.0)),
    'BLCH': dict(sat=0.45, contrast=1.32, shadows=(0, 0, 0.01), highlights=(0.01, 0.01, 0.0)),
    'ACRO': dict(mix=(0.36, 0.50, 0.14), contrast=1.10),
    'SEPI': dict(mix=(0.30, 0.59, 0.11), contrast=1.0),
}


def film_look(a, film, bw_filter='none'):
    """The film's colour on a photo from any camera (the in-camera FAUXJI looks, approximated in sRGB). bw_filter: a coloured lens
    filter for the black-and-white films (BW_FILTERS)."""
    look = LOOKS.get(film.code)
    if not look:
        return a
    if 'mix' in look:
        fw = FILTER_WEIGHTS.get(bw_filter, FILTER_WEIGHTS['none'])
        r, g, b = (m * w for m, w in zip(look['mix'], fw))
        s = r + g + b
        r, g, b = r / s, g / s, b / s
        l = a[..., 0] * r + a[..., 1] * g + a[..., 2] * b
        l = _curve(l, look['contrast'])
        return np.clip(np.repeat(l[..., None], 3, axis=2), 0, 1)
    l = luma(a)[..., None]
    a = l + (a - l) * look['sat']
    a = _curve(a, look['contrast'])
    lum = luma(np.clip(a, 0, 1))[..., None]
    a = a + np.array(look['shadows'], np.float32) * (1 - lum) * 2 + np.array(look['highlights'], np.float32) * lum * 2
    return np.clip(a, 0, 1)


def develop(a, film, recipe, frame=1, roll_seed=0, emulate=False):
    """A developed print of one frame (float RGB in, float RGB out). frame: 1-based frame number (the first frame catches a light leak).
    emulate: the photo comes from another camera, so the film's colour (film_look) is applied first."""
    a = a.astype(np.float32, copy=True)
    if emulate:                                       # a photo from another camera: the film's colour first
        a = film_look(a, film, recipe.bw_filter)
    h, w = a.shape[:2]
    scan = emulate and recipe.authentic
    if scan:                                          # authentic scan: no film resolves a phone's hair-sharp detail
        a = _soften(a)
    rng = np.random.default_rng(_seed(roll_seed, recipe.seed, frame))
    grain = film.grain * recipe.grain
    contrast = 1.0

    # push / pull: longer development = denser and harder, more grain; pull = softer
    if recipe.push:
        a = 1.0 - (1.0 - a) ** (2 ** (0.30 * recipe.push))
        contrast *= 1.0 + 0.14 * recipe.push
        grain *= 1.0 + 0.45 * max(recipe.push, 0) - 0.2 * max(-recipe.push, 0)

    # developer
    if recipe.developer == 'fine':
        grain *= 0.6
    elif recipe.developer == 'contrast':
        contrast *= 1.25
        grain *= 1.15
    elif recipe.developer == 'acutance':
        grain *= 1.1

    # process
    if recipe.process == 'cross':
        # slide film in negative chemistry: harsh contrast, yellow-green highlights, blue-cyan shadows, saturated
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        r = np.clip(_curve(r, 1.35, 0.45) + 0.03, 0, 1)
        g = np.clip(_curve(g, 1.25, 0.5) + 0.02, 0, 1)
        b = np.clip(b * 0.78 + 0.10 * (1 - b) * 0.6, 0, 1)
        a = np.stack([r, g, b], axis=2)
        l = luma(a)[..., None]
        a = l + (a - l) * 1.35
    elif recipe.process == 'bleach':
        l = luma(a)[..., None]
        a = a * 0.45 + l * 0.55
        contrast *= 1.3

    if contrast != 1.0:
        a = _curve(a, contrast)

    # expired film: fogged blacks, lower contrast, a colour cast that drifts with age
    if recipe.expired:
        y = recipe.expired
        r2 = random.Random(_seed('cast', roll_seed, recipe.seed))
        cast = np.array([0.04 + r2.uniform(-0.02, 0.05), r2.uniform(-0.04, 0.02), r2.uniform(-0.05, 0.04)], dtype=np.float32)
        fog = min(0.02 * y, 0.22)
        a = fog + a * (1.0 - fog - 0.015 * min(y, 10))
        if not film.mono:
            a = a + cast * min(y / 8.0, 1.5) * (1.0 - a * 0.6)
        grain *= 1.0 + 0.12 * min(y, 12)

    # halation: highlights bleed a red-orange glow through the film base
    hal = film.halation * recipe.halation
    if hal > 0:
        l = luma(a)
        mask = np.clip((l - 0.72) / 0.28, 0, 1)
        if mask.max() > 0:
            glow = _blur_l(mask, max(2.0, w * 0.006))
            a = a + glow[..., None] * np.array([0.55, 0.16, 0.04], dtype=np.float32) * hal

    # acutance developer: edge sharpening (the adjacency effect)
    if recipe.developer == 'acutance':
        im = to_image(a).filter(ImageFilter.UnsharpMask(radius=max(1.5, w / 1400), percent=70, threshold=2))
        a = np.asarray(im, dtype=np.float32) / 255.0

    # light leaks: the first frames of a roll (loaded in daylight), and now and then
    # light leaks: the first frame of a roll is wound on in daylight and catches a leak; later frames only now and then (about 1 in 20)
    if recipe.leaks and not film.mono and (frame == 1 or rng.random() < LEAK_CHANCE):
        a = _leak(a, rng, strong=frame == 1)

    # monochrome films stay neutral (or sepia)
    # toning (black and white): selenium deepens the blacks and cools them a little; sepia turns the print brown
    if film.mono:
        l = luma(a)
        if film.code == 'SEPI' or recipe.tone == 'sepia':
            a = np.stack([l * 1.07 + 0.02, l * 0.95 + 0.01, l * 0.78], axis=2)
        elif recipe.tone == 'selenium':
            l = np.clip(l, 0, 1) ** 1.12
            shade = (1 - l) * l * 4                                  # strongest in the dark mid-tones
            a = np.stack([l + 0.010 * shade, l - 0.006 * shade, l + 0.022 * shade], axis=2)
        else:
            a = np.repeat(l[..., None], 3, axis=2)

    # authentic scan, tones: a film print has a shorter range than a phone's HDR file: a soft shoulder in the highlights (each film
    # kind has its own latitude) and a touch of lift in the blacks. Float throughout: nothing is lost, the curve only rolls off.
    if scan:
        a = _shoulder(a, SHOULDER.get(film.kind, 0.74))

    # grain: clumpy, strongest in the mid-tones. A grain clump is 2 px of the camera's 3648 px frame; a smaller image (a preview) gets
    # finer noise with the amplitude a downscale would leave, so previews look like the full-size print scaled down.
    if grain > 0:
        l = luma(a)
        amp = grain * (0.35 + 2.6 * l * (1 - l))
        a = a + (_noise(rng, h, w, 2.0 * w / FULL_WIDTH) * amp)[..., None]
        if not film.mono:
            c = np.stack([_noise(rng, h, w, 4.0 * w / FULL_WIDTH) for _ in range(3)], axis=2)
            a = a + c * grain * 0.25

    # gentle lab correction
    if recipe.auto_levels:
        lo = np.percentile(a, 0.5, axis=(0, 1))
        hi = np.percentile(a, 99.5, axis=(0, 1))
        stretched = (a - lo) / np.maximum(hi - lo, 1e-3)
        a = a * 0.4 + stretched * 0.6

    # paper
    if recipe.paper == 'vintage':
        # an old minilab print: colour a little faded, blacks lifted, highlights warm, a soft fall-off at the edges (enlarger lens)
        l = luma(a)[..., None]
        a = l + (a - l) * 0.88
        a = 0.05 + a * 0.90
        a = a * np.array([1.04, 1.0, 0.90], dtype=np.float32) + np.array([0.02, 0.01, 0.0], dtype=np.float32)
        yy = np.linspace(-1, 1, h, dtype=np.float32)[:, None]
        xx = np.linspace(-1, 1, w, dtype=np.float32)[None, :]
        a = a * (1.0 - 0.10 * np.clip(xx * xx + yy * yy - 0.35, 0, None))[..., None]
    elif recipe.paper == 'matte':
        a = 0.035 + a * 0.93
    elif recipe.paper == 'warm':
        a = a * np.array([1.03, 1.0, 0.92], dtype=np.float32) + np.array([0.015, 0.008, 0.0], dtype=np.float32)
    elif recipe.paper == 'neutral':
        # a neutral fibre print: no colour of its own, deep but not crushed blacks, a slight sheen roll-off in the highlights
        a = 0.015 + a * 0.975
        a = a - 0.03 * np.clip(a - 0.85, 0, None)

    return np.clip(a, 0, 1)


SOFT_SIGMA = 0.00045                                       # film / lens softness: 1.6 px at the camera's 3648 px frame, in proportion at any size
SHOULDER = {'slide': 0.80, 'effect': 0.78, 'bw': 0.72, 'negative': 0.68, 'cine': 0.62}   # where the highlights start to roll off


def _soften(a):
    """The softness of a film frame (lens, grain and scanner): detail finer than about 3600 px across is not there, whatever the
    phone's sensor recorded. Proportional to the image width, so a preview and a print agree."""
    sigma = a.shape[1] * SOFT_SIGMA
    if sigma < 0.35:
        return a
    im = to_image(a).filter(ImageFilter.GaussianBlur(sigma))
    return np.asarray(im, dtype=np.float32) / 255.0


def _shoulder(a, t):
    """Highlights roll off softly above t instead of clipping hard (and the blacks lift a little): the range of a print."""
    a = np.clip(a, 0, None)
    k = 0.8                                           # below t nothing changes; above, the slope eases from 1 smoothly
    u = np.maximum(a - t, 0) / (1 - t)
    y = np.where(a > t, t + (1 - t) * np.tanh(k * u) / k, a)
    return np.clip(0.010 + y * 0.990, 0, 1)


FULL_WIDTH = 3648                                         # the TL500's full-size frame


def _noise(rng, h, w, clump):
    """Unit gaussian noise of size h x w with grain clumps `clump` pixels across; below 1 px the amplitude is scaled down as a resize would."""
    if clump >= 1:
        gh, gw = max(2, int(round(h / clump))), max(2, int(round(w / clump)))
        n = rng.standard_normal((gh, gw)).astype(np.float32)
        return np.asarray(Image.fromarray(n, 'F').resize((w, h), Image.BILINEAR), dtype=np.float32)
    return rng.standard_normal((h, w)).astype(np.float32) * clump


def _leak(a, rng, strong=False):
    h, w = a.shape[:2]
    side = rng.integers(0, 4)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    if side == 0:
        d = xx / w
    elif side == 1:
        d = (w - xx) / w
    elif side == 2:
        d = yy / h
    else:
        d = (h - yy) / h
    cy = rng.uniform(0.2, 0.8)
    across = (yy / h - cy) if side < 2 else (xx / w - cy)
    reach = rng.uniform(0.18, 0.35) * (1.6 if strong else 1.0)
    m = np.exp(-(d / reach) ** 2) * np.exp(-(across / rng.uniform(0.25, 0.5)) ** 2)
    m = m * (0.85 if strong else rng.uniform(0.35, 0.6))
    colour = np.array([1.0, rng.uniform(0.35, 0.55), rng.uniform(0.05, 0.2)], dtype=np.float32)
    return 1.0 - (1.0 - a) * (1.0 - m[..., None] * colour)                 # screen blend


# ---------------------------------------------------------------- prints and sheets

def _font(size, bold=True):
    names = (['bahnschrift.ttf', 'arialbd.ttf', 'DejaVuSans-Bold.ttf', 'LiberationSans-Bold.ttf'] if bold
             else ['bahnschrift.ttf', 'arial.ttf', 'DejaVuSans.ttf', 'LiberationSans-Regular.ttf'])
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default()


def bordered(im, border, caption=''):
    """A print with its border (PIL image in, PIL image out)."""
    w, h = im.size
    if border == 'white':
        m = int(min(w, h) * 0.05)
        out = Image.new('RGB', (w + 2 * m, h + 2 * m), (244, 242, 236))
        out.paste(im, (m, m))
    elif border == 'black':
        m = int(min(w, h) * 0.035)
        out = Image.new('RGB', (w + 2 * m, h + 2 * m), (10, 10, 10))
        d = ImageDraw.Draw(out)
        rng = random.Random(w * 7 + h)
        for k in range(60):                                     # a rough, filed-out edge around the frame
            x = rng.randint(m - 6, m + w - 6)
            d.rectangle([x, m - rng.randint(2, 6), x + rng.randint(3, 20), m + 2], fill=(10, 10, 10))
            d.rectangle([x, m + h - 2, x + rng.randint(3, 20), m + h + rng.randint(2, 6)], fill=(10, 10, 10))
        out.paste(im, (m, m), _rough_mask(w, h, rng))
        if caption:
            d.text((m, m + h + m * 0.18), caption, font=_font(max(10, m // 2)), fill=(230, 120, 30))
    elif border == 'instant':
        m = int(w * 0.06)
        out = Image.new('RGB', (w + 2 * m, h + m + int(h * 0.22)), (246, 245, 240))
        out.paste(im, (m, m))
        if caption:
            ImageDraw.Draw(out).text((m, h + m + int(h * 0.06)), caption, font=_font(max(12, int(h * 0.045)), bold=False),
                                     fill=(60, 60, 70))
    else:
        out = im
    return out


def _rough_mask(w, h, rng):
    mask = Image.new('L', (w, h), 255)
    d = ImageDraw.Draw(mask)
    for k in range(40):
        x = rng.randint(0, w - 1)
        d.rectangle([x, 0, x + rng.randint(2, 12), rng.randint(1, 4)], fill=0)
        d.rectangle([x, h - rng.randint(1, 4), x + rng.randint(2, 12), h], fill=0)
    return mask


def strip(frames, film, positive=True, frame_w=360, edge=True, start=1):
    """A strip of 35 mm film: frames (list of PIL images or None), sprocket holes, edge print and frame numbers. Returns a PIL image."""
    fh = int(frame_w * 2 / 3)
    band = int(fh * 0.20)
    gap = int(frame_w * 0.06)
    n = len(frames)
    W = n * (frame_w + gap) + gap
    H = fh + 2 * band
    base = (18, 16, 16) if positive else ((150, 150, 152) if film.mono else (196, 128, 74))
    out = Image.new('RGB', (W, H), base)
    d = ImageDraw.Draw(out)
    hole_w, hole_h = max(4, int(frame_w * 0.05)), max(5, int(band * 0.38))
    pitch = frame_w / 8
    x = gap / 2
    while x < W:
        for y in (int(band * 0.18), H - int(band * 0.18) - hole_h):
            d.rounded_rectangle([x, y, x + hole_w, y + hole_h], radius=max(1, hole_w // 4), fill=(4, 4, 4) if positive else (240, 238, 230))
        x += pitch
    ink = (255, 150, 40) if positive else (250, 230, 200)
    fnt = _font(max(9, int(band * 0.30)))
    name = 'FAUXJI ' + film.name.upper()
    for k, im in enumerate(frames):
        x0 = gap + k * (frame_w + gap)
        if im is not None:
            t = im.copy()
            t.thumbnail((frame_w, fh), Image.LANCZOS)
            out.paste(t, (x0 + (frame_w - t.width) // 2, band + (fh - t.height) // 2))
        else:
            d.rectangle([x0, band, x0 + frame_w, band + fh], fill=(30, 28, 28) if positive else base)
        if edge:
            num = start + k
            ty = band + fh + int(band * 0.12) - int(band * 0.70) + int(band * 0.62)
            d.text((x0 + 4, band - int(band * 0.44)), name if k % 2 == 0 else '', font=fnt, fill=ink)
            d.text((x0 + frame_w // 2, ty), '%d' % num, font=fnt, fill=ink)
            d.polygon([(x0 + frame_w // 2 - 14, ty + 3), (x0 + frame_w // 2 - 14, ty + 3 + fnt.size * 0.6),
                       (x0 + frame_w // 2 - 6, ty + 3 + fnt.size * 0.3)], fill=ink)
            d.text((x0 + frame_w - fnt.size * 2.2, ty), '%dA' % num, font=fnt, fill=ink)
    return out


def contact_sheet(images, film, title, per_row=6, frame_w=420, positive=True):
    """A contact sheet: the roll cut into strips of `per_row`, on a sheet with a title. images: PIL thumbnails in frame order."""
    strips = []
    for s in range(0, len(images), per_row):
        part = images[s:s + per_row]
        part = part + [None] * (per_row - len(part))
        strips.append(strip(part, film, positive=positive, frame_w=frame_w, start=s + 1))
    if not strips:
        strips = [strip([None] * per_row, film, positive=positive, frame_w=frame_w)]
    sw, sh = strips[0].size
    pad = int(sw * 0.03)
    head = int(sh * 0.45)
    sheet = Image.new('RGB', (sw + 2 * pad, head + len(strips) * (sh + pad) + pad), (236, 234, 228))
    d = ImageDraw.Draw(sheet)
    d.text((pad, int(head * 0.25)), title, font=_font(int(head * 0.38)), fill=(30, 30, 34))
    for k, s in enumerate(strips):
        sheet.paste(s, (pad, head + k * (sh + pad)))
    return sheet


def rotate(im, degrees):
    """A PIL image turned clockwise by 0 / 90 / 180 / 270 degrees (lossless pixel transpose)."""
    d = degrees % 360
    if not d:
        return im
    return im.transpose({90: Image.ROTATE_270, 180: Image.ROTATE_180, 270: Image.ROTATE_90}[d])


def thumb_image(a, size=480):
    im = to_image(a)
    im.thumbnail((size, size), Image.LANCZOS)
    return im


def tank_stages(push):
    """The developing steps and their (pretend) times, for the progress display."""
    dev = 7.0 * (1.4 ** push)
    m, s = int(dev), int(round((dev % 1) * 60))
    return [('Developer', '%d:%02d' % (m, s)), ('Stop bath', '0:30'), ('Fixer', '5:00'), ('Wash', '10:00'), ('Dry', '')]


def frame_caption(film, frame_no, taken):
    d = taken.strftime("'%y %m %d") if taken else ''
    return ('%s  %02d  %s' % (film.name.upper(), frame_no, d)).strip()


__all__ = ['Recipe', 'surprise', 'load', 'to_image', 'negative', 'develop', 'bordered', 'rotate', 'strip', 'contact_sheet', 'thumb_image',
           'tank_stages', 'frame_caption', 'DEVELOPERS', 'PROCESSES', 'PAPERS', 'BORDERS', 'PUSH_PULL', 'BW_FILTERS', 'TONES']

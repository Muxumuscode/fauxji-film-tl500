"""A small fake FAUXJI card made of synthetic JPEGs, with EXIF written the way the camera writes it."""
import os
from datetime import datetime, timedelta

import numpy as np
from PIL import Image


def frame(seed, w=480, h=360):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    r = 0.5 + 0.5 * np.sin(x / w * 6.3 + seed)
    g = y / h
    b = 0.5 + 0.5 * np.cos((x + y) / (w + h) * 9.0 + seed * 0.7)
    a = np.stack([r, g, b], axis=2) * 0.85 + rng.random((h, w, 3)).astype(np.float32) * 0.05
    a[h // 3:h // 3 + 40, w // 2:w // 2 + 60] = 1.0                    # a highlight (halation)
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8), 'RGB')


def write(path, im, model, taken):
    ex = Image.Exif()
    ex[0x10F] = 'FAUXJI FILM'
    ex[0x110] = model
    ex[0x132] = taken.strftime('%Y:%m:%d %H:%M:%S')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path, quality=90, exif=ex)


def make_card(root, rolls=(('PROV001', 'TL500 Provia', 5), ('MYST001', 'TL500 Classic Chrome', 4), ('ACRO002', 'TL500 Acros', 3))):
    t0 = datetime(2026, 11, 8, 14, 0, 0)
    n = 832
    for code, model, frames in rolls:
        for k in range(frames):
            write(os.path.join(root, 'FILMS', code, '100PHOTO', 'SAM_%04d.JPG' % n), frame(n), model, t0 + timedelta(minutes=n - 832))
            n += 1
    os.makedirs(os.path.join(root, 'DCIM'), exist_ok=True)
    return root

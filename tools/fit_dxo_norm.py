"""Fit tools/dxo_norm.json: the step that turns DxO PhotoLab's neutral render of a RAW into the camera's own PROVIA JPEG of the same shot.

DxO's default colour is richer than Samsung's PROVIA (owner's test shot SAM_0904: a red curtain at saturation 0.96 in DxO, 0.71 in the
camera's JPEG), so a look LUT built on top of PROVIA starts from the wrong place. make_luts.py --norm puts this step in front of every look.

The model is two numbers' worth of correction, chosen because it held up across hues on the test shot (a 3x3 matrix fitted a little
better but leaned on the one scene's red curtain):
  * a luma tone curve (16 control points from binned medians), then
  * one chroma scale in gamma space (distance from luma times k).

Pairs: a DxO export of the RAW with no colour changes, and the camera's JPEG of the same shot, shot in PROVIA (RAW+JPEG). The camera
crops about 4 % for its lens-distortion correction, so the JPEG is scaled into the DxO frame first (scale and shift by edge correlation)
and only the middle of the frame is compared (the correction bends the edges).

    python tools/fit_dxo_norm.py <out.json> <dxo1.jpg> <camera1.jpg> [<dxo2.jpg> <camera2.jpg> ...]
    python tools/fit_dxo_norm.py --selftest <any photo>        recover a known correction from a synthetic pair
"""
import sys, json
import numpy as np
from PIL import Image, ImageFilter

LUMA = np.array([0.299, 0.587, 0.114])
W, H = 1000, 750


def load(src):
    im = src if isinstance(src, Image.Image) else Image.open(src)
    return im.convert('RGB').resize((W, H), Image.LANCZOS)


def edges(im):
    a = np.asarray(im.convert('L').filter(ImageFilter.GaussianBlur(1.0))).astype(float)
    gy, gx = np.gradient(a)
    return np.hypot(gx, gy)


def shrink(im, s, dx=0, dy=0):
    """The camera image scaled by s about the centre, on a W x H canvas (NaN outside)."""
    w2, h2 = int(round(W * s)), int(round(H * s))
    r = np.asarray(im.resize((w2, h2), Image.LANCZOS)).astype(float) / 255
    out = np.full((H, W, 3), np.nan)
    y0, x0 = (H - h2) // 2 + dy, (W - w2) // 2 + dx
    ys, xs = slice(max(y0, 0), min(y0 + h2, H)), slice(max(x0, 0), min(x0 + w2, W))
    out[ys, xs] = r[ys.start - y0:ys.stop - y0, xs.start - x0:xs.stop - x0]
    return out


def align(dxo, cam):
    e = edges(dxo)[180:570, 250:750]
    e = e - e.mean()

    def score(s, dx, dy):
        o = shrink(cam, s, dx, dy).mean(-1)
        o = np.nan_to_num(np.asarray(Image.fromarray(np.nan_to_num(o * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.0))).astype(float))
        gy, gx = np.gradient(o)
        g = np.hypot(gx, gy)[180:570, 250:750]
        g = g - g.mean()
        return (e * g).sum() / np.sqrt((e * e).sum() * (g * g).sum() + 1e-9)
    best = max((score(s, 0, 0), s) for s in np.arange(0.90, 1.0001, 0.005))[1]          # coarse scale
    return max((score(s, dx, dy), s, dx, dy) for s in np.arange(best - 0.006, best + 0.0061, 0.001)
               for dx in range(-3, 4) for dy in range(-3, 4))


def samples(dxo, cam):
    r, s, dx, dy = align(dxo, cam)
    print('  aligned: scale %.3f, shift (%d, %d), edge correlation %.3f' % (s, dx, dy, r))
    b = np.asarray(dxo).astype(float) / 255
    o = shrink(cam, s, dx, dy)
    c = (slice(120, 630), slice(150, 850))                            # middle of the frame only
    X, Y = b[c].reshape(-1, 3), o[c].reshape(-1, 3)
    ok = ~np.isnan(Y).any(1)
    X, Y = X[ok], Y[ok]
    ok = (X.max(1) < 0.98) & (Y.max(1) < 0.98) & (Y.min(1) > 0.02)    # no clipped or noise-floor pixels
    return X[ok], Y[ok]


def tone_curve(X, Y):
    lx, ly = X @ LUMA, Y @ LUMA
    xs, ys = [0.0], [0.0]
    edges_ = np.linspace(0.02, 0.98, 17)
    for lo, hi in zip(edges_[:-1], edges_[1:]):
        m = (lx >= lo) & (lx < hi)
        if m.sum() > 200:
            xs.append(float(np.median(lx[m]))); ys.append(float(np.median(ly[m])))
    xs.append(1.0); ys.append(1.0)
    return xs, [float(v) for v in np.maximum.accumulate(ys)]


def apply(P, norm):
    l = P @ LUMA
    v = np.clip(P + (np.interp(l, norm['curve_x'], norm['curve_y']) - l)[:, None], 0, 1)
    y = v @ LUMA
    return np.clip(y[:, None] + (v - y[:, None]) * norm['chroma'], 0, 1)


def fit(X, Y):
    xs, ys = tone_curve(X, Y)
    best = min((np.abs(apply(X, {'curve_x': xs, 'curve_y': ys, 'chroma': k}) - Y).mean(), k) for k in np.arange(0.30, 1.0001, 0.01))
    return {'chroma': round(float(best[1]), 2), 'curve_x': xs, 'curve_y': ys}


def main(out, files):
    X, Y = [], []
    for i in range(0, len(files), 2):
        print('pair', files[i], files[i + 1])
        x, y = samples(load(files[i]), load(files[i + 1]))
        X.append(x); Y.append(y)
    X, Y = np.concatenate(X), np.concatenate(Y)
    norm = fit(X, Y)
    print('mean abs error vs the camera: DxO as is %.4f, corrected %.4f, chroma scale %.2f'
          % (np.abs(X - Y).mean(), np.abs(apply(X, norm) - Y).mean(), norm['chroma']))
    norm['note'] = 'DxO PhotoLab neutral render -> Samsung PROVIA: luma tone curve + chroma scale in gamma space; %d pair(s)' % (len(files) // 2)
    json.dump(norm, open(out, 'w'), indent=1)
    print('wrote', out)


def selftest(photo):
    """Make a fake 'camera JPEG' from a photo with a known correction and a 4 % crop, and check the fit finds it."""
    dxo = load(photo)
    true = {'chroma': 0.65, 'curve_x': [0, 0.25, 0.5, 0.75, 1], 'curve_y': [0, 0.21, 0.47, 0.76, 1]}
    a = np.asarray(dxo).astype(float) / 255
    cam = (apply(a.reshape(-1, 3), true).reshape(a.shape) * 255).astype(np.uint8)
    crop = 0.04
    big = Image.fromarray(cam)
    cw, ch = int(W * (1 - crop)), int(H * (1 - crop))
    cam_im = big.crop(((W - cw) // 2, (H - ch) // 2, (W + cw) // 2, (H + ch) // 2)).resize((W, H), Image.LANCZOS)
    X, Y = samples(dxo, cam_im)
    norm = fit(X, Y)
    err = np.abs(np.interp([0.25, 0.5, 0.75], norm['curve_x'], norm['curve_y']) - np.array([0.21, 0.47, 0.76])).max()
    ok = abs(norm['chroma'] - 0.65) <= 0.05 and err <= 0.03
    print('selftest: chroma %.2f (true 0.65), tone curve error %.3f -> %s' % (norm['chroma'], err, 'ok' if ok else 'FAILED'))
    return ok


if __name__ == '__main__':
    if sys.argv[1] == '--selftest':
        sys.exit(0 if selftest(sys.argv[2]) else 1)
    main(sys.argv[1], sys.argv[2:])

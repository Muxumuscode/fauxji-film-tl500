"""FAUXJI sounds for the TL500: a leaf-shutter click and a start-up chime.

The camera's sounds live in SPID.Rom as headerless 16-bit little-endian mono PCM at
32 kHz (confirmed by ear against the camera). Everything here is synthesized; no
samples from any other camera are used. Each replaces one of Samsung's three
user-selectable options, so the originals stay available in the menu.

Run from project root:
  python tools/sounds.py preview <out_dir>          # write WAVs to listen to
  python tools/sounds.py patch <SPID.Rom in> <out>  # write them into the ROM
"""
import os, sys, wave
import numpy as np

RATE = 32000
SLOTS = {'shutter': 'Shutter3_32m.snd', 'chime': 'PowerOn3_mono.snd'}


def _t(seconds):
    return np.arange(int(seconds * RATE)) / RATE


def _bandpass_noise(n, lo, hi, rng):
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / RATE)
    spec[(f < lo) | (f > hi)] = 0
    x = np.fft.irfft(spec, n)
    return x / (np.abs(x).max() + 1e-9)


def _impact(n, modes, rng, bounces=((0, 1.0),), click=0.0007):
    """Metal parts hitting a stop: a short excitation (plus a few bounces) driving
    damped resonators. modes: [(freq Hz, decay s, gain)]."""
    exc = np.zeros(n)
    for delay, amp in bounces:
        k = int(delay * RATE); m = max(2, int(click * RATE))
        if k + m < n:
            exc[k:k + m] += amp * rng.standard_normal(m) * np.hanning(m)
    t = np.arange(n) / RATE
    out = np.zeros(n)
    for f, decay, g in modes:
        h = np.sin(2 * np.pi * f * t) * np.exp(-t / decay)       # impulse response of one mode
        out += g * np.convolve(exc, h)[:n]
    return out


def _clack(n, rng, bright, size, rattle=4):
    """One mechanical impact, v3: noisy, not tonal. Dense inharmonic modes that die in
    1-4 ms (no pitch to hear), a broadband crack, a few rattle micro-hits, a short thump.
    bright: centre of the metal band (Hz); size: 1 = small part, 2 = big part."""
    t = np.arange(n) / RATE
    exc = np.zeros(n)
    hits = [(0.0, 1.0)] + [(rng.uniform(0.0012, 0.012) * size, rng.uniform(0.15, 0.5)) for _ in range(rattle)]
    for d, a in hits:
        k = int(d * RATE); m = int(0.0006 * RATE) + 2
        if k + m < n:
            exc[k:k + m] += a * rng.standard_normal(m)
    out = np.zeros(n)
    for _ in range(40):
        f = np.exp(rng.uniform(np.log(bright / 3), np.log(bright * 2.5)))
        decay = rng.uniform(0.0008, 0.004) * size
        h = np.sin(2 * np.pi * f * t[:int(0.03 * RATE)] + rng.uniform(0, 6.28)) * np.exp(-t[:int(0.03 * RATE)] / decay)
        out += rng.uniform(0.3, 1.0) * np.convolve(exc, h)[:n]
    out /= np.abs(out).max() + 1e-9
    crack = _bandpass_noise(n, 800, 12000, rng) * np.exp(-t / (0.0025 * size))
    thump = np.sin(2 * np.pi * rng.uniform(110, 170) / size * t) * np.exp(-t / (0.006 * size))
    return out + 0.9 * crack + 0.35 * thump


SHUTTERS_V3 = {
    # (event start s, level, brightness Hz, size)
    'A': dict(events=((0.003, 1.0, 4500, 1.0), (0.030, 0.8, 5200, 0.9)), length=0.08),            # leaf
    'B': dict(events=((0.003, 1.0, 3000, 1.3), (0.024, 0.5, 3600, 1.0), (0.070, 0.9, 2700, 1.4)),  # rangefinder
              length=0.12),
    'C': dict(events=((0.003, 1.0, 2000, 1.8), (0.034, 0.6, 3200, 1.2), (0.105, 0.9, 1800, 2.0),   # SLR
                      (0.128, 0.4, 2400, 1.4)), length=0.19),
}


def shutter_v3(kind):
    p = SHUTTERS_V3[kind]
    rng = np.random.default_rng(11)
    n = int(p['length'] * RATE)
    out = np.zeros(n)
    for start, level, bright, size in p['events']:
        s = int(start * RATE)
        out[s:] += level * _clack(n - s, rng, bright, size)
    fade = np.ones(n); fade[-int(0.006 * RATE):] = np.linspace(1, 0, int(0.006 * RATE))
    return out * fade / np.abs(out).max() * 22000


SHUTTERS = {
    # leaf shutter: small blades, bright metallic modes, two quick events 28 ms apart
    'A': dict(events=((0.003, 1.0), (0.031, 0.75)),
              modes=[(2150, 0.010, 1.0), (3480, 0.008, 0.8), (5230, 0.006, 0.6), (7900, 0.004, 0.4),
                     (980, 0.014, 0.5), (420, 0.020, 0.35)],
              bounces=((0, 1.0), (0.0021, 0.45), (0.0044, 0.2)), length=0.11),
    # cloth/metal focal-plane rangefinder: softer, lower, a little spring zing
    'B': dict(events=((0.004, 1.0), (0.020, 0.55), (0.062, 0.9)),
              modes=[(1250, 0.016, 1.0), (1900, 0.012, 0.7), (2950, 0.009, 0.5), (4400, 0.006, 0.3),
                     (610, 0.024, 0.55), (260, 0.030, 0.4)],
              bounces=((0, 1.0), (0.0030, 0.4), (0.0065, 0.18)), length=0.16),
    # SLR: mirror slap + shutter + mirror return, low body thump
    'C': dict(events=((0.004, 1.0), (0.030, 0.6), (0.095, 0.85), (0.118, 0.45)),
              modes=[(860, 0.022, 1.0), (1420, 0.016, 0.7), (2310, 0.011, 0.55), (3600, 0.007, 0.35),
                     (330, 0.040, 0.8), (150, 0.050, 0.5)],
              bounces=((0, 1.0), (0.0035, 0.5), (0.0080, 0.25), (0.013, 0.1)), length=0.24),
}
SHUTTER = 'A'


def shutter(kind=None):
    p = SHUTTERS[kind or SHUTTER]
    rng = np.random.default_rng(7)
    n = int(p['length'] * RATE)
    out = np.zeros(n)
    for start, level in p['events']:
        s = int(start * RATE)
        out[s:] += level * _impact(n - s, p['modes'], rng, p['bounces'])
    fade = np.ones(n); fade[-int(0.01 * RATE):] = np.linspace(1, 0, int(0.01 * RATE))
    out *= fade
    return out / np.abs(out).max() * 22000


def chime():
    """Two soft bell notes, A5 then E6, with a few inharmonic overtones."""
    out = np.zeros(int(1.25 * RATE))
    for start, f0, level in ((0.0, 880.0, 1.0), (0.14, 1318.5, 0.85)):
        s = int(start * RATE)
        t = np.arange(len(out) - s) / RATE
        env = (1 - np.exp(-t / 0.004)) * np.exp(-t / 0.42)
        tone = (np.sin(2 * np.pi * f0 * t) + 0.32 * np.sin(2 * np.pi * 2.0 * f0 * t) * np.exp(-t / 0.18)
                + 0.12 * np.sin(2 * np.pi * 3.01 * f0 * t) * np.exp(-t / 0.09))
        out[s:] += level * env * tone
    fade = np.ones_like(out); fade[-int(0.08 * RATE):] = np.linspace(1, 0, int(0.08 * RATE))
    out *= fade
    return out / np.abs(out).max() * 20000


def pcm(x):
    return np.clip(np.round(x), -32768, 32767).astype('<i2').tobytes()


SOUNDS = {'shutter': shutter, 'chime': chime}

if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'preview':
        os.makedirs(sys.argv[2], exist_ok=True)
        clips = {'chime': chime()}
        clips.update({'shutter_%s' % k: shutter(k) for k in SHUTTERS})
        clips.update({'shutter_v3_%s' % k: shutter_v3(k) for k in SHUTTERS_V3})
        for name, x in clips.items():
            w = wave.open(os.path.join(sys.argv[2], 'fauxji_%s.wav' % name), 'wb')
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(pcm(x)); w.close()
    elif cmd == 'patch':
        sys.path.insert(0, os.path.dirname(__file__))
        import spid_files as F
        d = open(sys.argv[2], 'rb').read()
        for name, fn in SOUNDS.items():
            d = F.replace(d, SLOTS[name], pcm(fn()))
            print('%-8s -> %s (%d bytes)' % (name, SLOTS[name], len(pcm(fn()))))
        open(sys.argv[3], 'wb').write(d)

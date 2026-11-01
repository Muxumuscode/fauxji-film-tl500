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


def shutter():
    """Leaf shutter: crisp open tick, softer close tick 35 ms later, faint ring, body."""
    rng = np.random.default_rng(1)
    out = np.zeros(int(0.16 * RATE))
    for start, level, decay in ((0.004, 1.0, 0.0022), (0.039, 0.62, 0.0030)):
        t = _t(0.03)
        tick = _bandpass_noise(len(t), 2500, 9000, rng) * np.exp(-t / decay)
        ring = np.sin(2 * np.pi * 4200 * t) * np.exp(-t / 0.012) * 0.18
        body = np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.010) * 0.30
        s = int(start * RATE)
        out[s:s + len(t)] += level * (tick + ring + body)
    return out / np.abs(out).max() * 21000


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
        for name, fn in SOUNDS.items():
            w = wave.open(os.path.join(sys.argv[2], 'fauxji_%s.wav' % name), 'wb')
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(pcm(fn())); w.close()
    elif cmd == 'patch':
        sys.path.insert(0, os.path.dirname(__file__))
        import spid_files as F
        d = open(sys.argv[2], 'rb').read()
        for name, fn in SOUNDS.items():
            d = F.replace(d, SLOTS[name], pcm(fn()))
            print('%-8s -> %s (%d bytes)' % (name, SLOTS[name], len(pcm(fn()))))
        open(sys.argv[3], 'wb').write(d)

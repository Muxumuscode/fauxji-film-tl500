"""Sounds for the developing animation: a swish as a print goes in, running water in the wash, a bell when the roll is dry.

They are made in code (no sound files to ship), written once as small WAV files in the temp folder, and played without waiting.
Windows plays them with the standard library; elsewhere Qt Multimedia is used when it is installed (otherwise it stays silent).
The Sound button in the header turns them off (remembered); SAJIN_SILENT=1 silences everything (the tests).
"""
import math
import os
import sys
import tempfile
import time
import wave

import numpy as np

RATE = 22050
enabled = not os.environ.get('SAJIN_SILENT')
_last = {}
_files = {}
_qt = {}


def _noise(n, seed):
    return np.random.default_rng(seed).standard_normal(n).astype(np.float32)


def _hump(t):
    """0 at both ends, 1 in the middle (never a hair below 0: that would make NaN in a power)."""
    return np.clip(np.sin(math.pi * t), 0, None)


def _swish():
    """A print sliding into the tray: a soft, rising then falling whoosh of filtered noise."""
    n = int(RATE * 0.42)
    t = np.linspace(0, 1, n, dtype=np.float32)
    a = 0.04 + 0.34 * _hump(t) ** 1.5                          # how open the filter is
    x, y, out = _noise(n, 1), 0.0, np.empty(n, dtype=np.float32)
    for i in range(n):
        y += a[i] * (x[i] - y)
        out[i] = y
    return out * _hump(t) ** 0.8 * 1.9


def _water():
    """Water running in the wash: bright noise with a bubbling ripple, fading in and out."""
    n = int(RATE * 1.6)
    t = np.linspace(0, 1, n, dtype=np.float32)
    x = _noise(n, 2)
    low = np.convolve(x, np.ones(6, dtype=np.float32) / 6, mode='same')
    band = (low - np.convolve(x, np.ones(40, dtype=np.float32) / 40, mode='same')) * 1.6
    bubbles = 0.75 + 0.25 * np.sin(2 * math.pi * (7 * t + 2 * np.sin(2 * math.pi * 1.3 * t)))
    return band * bubbles * _hump(t) ** 0.6 * 0.55


def _bell():
    """The timer's bell: a clear tone with two overtones, ringing out."""
    n = int(RATE * 1.5)
    t = np.arange(n, dtype=np.float32) / RATE
    y = (np.sin(2 * math.pi * 1046.5 * t) + 0.5 * np.sin(2 * math.pi * 2093.0 * t * 1.003) + 0.25 * np.sin(2 * math.pi * 3136.0 * t))
    return y * np.exp(-t * 3.2) * np.minimum(1, t * 400) * 0.33


def _clink():
    """Tongs touching the tray: a short, metallic tick."""
    n = int(RATE * 0.16)
    t = np.arange(n, dtype=np.float32) / RATE
    return (np.sin(2 * math.pi * 2650 * t) + 0.7 * np.sin(2 * math.pi * 3720 * t)) * np.exp(-t * 38) * 0.28


MAKERS = {'swish': _swish, 'water': _water, 'bell': _bell, 'clink': _clink}


PEAK = {'swish': 0.40, 'water': 0.34, 'bell': 0.45, 'clink': 0.40}      # how loud each one is (of full scale): comfortable, never clipping


def samples(name):
    """The sound as float samples in -1..1, brought to its own comfortable level."""
    x = MAKERS[name]()
    return (x / max(1e-6, float(np.abs(x).max())) * PEAK[name]).astype(np.float32)


def wav_file(name):
    """The path of the sound as a 16-bit mono WAV file (written on first use)."""
    if name not in _files or not os.path.exists(_files[name]):
        folder = os.path.join(tempfile.gettempdir(), 'sajingenzo-sounds')
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, name + '.wav')
        with wave.open(path, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes((samples(name) * 32000).astype('<i2').tobytes())
        _files[name] = path
    return _files[name]


def play(name, gap=0.0):
    """Play a sound without waiting (never raises). gap: seconds that must pass since the same sound last played."""
    if not enabled:
        return
    now = time.monotonic()
    if now - _last.get(name, -1e9) < gap:
        return
    _last[name] = now
    try:
        path = wav_file(name)
        if sys.platform == 'win32':
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        else:
            from PySide6.QtCore import QUrl
            from PySide6.QtMultimedia import QSoundEffect
            if name not in _qt:
                fx = QSoundEffect()
                fx.setSource(QUrl.fromLocalFile(path))
                _qt[name] = fx
            _qt[name].play()
    except Exception:
        pass

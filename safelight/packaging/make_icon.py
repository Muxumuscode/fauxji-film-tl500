"""Writes Sajin Genzō's icon (safelight/icon.py: the film cartridge) as .ico (Windows) and .png (Linux).
python packaging/make_icon.py <out dir>"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from safelight import icon                                       # noqa: E402

if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else '.'
    os.makedirs(out, exist_ok=True)
    icon.save_ico(os.path.join(out, 'safelight.ico'))
    icon.save_png(os.path.join(out, 'safelight.png'))
    print('icons written to', out)

"""Font lookup for the artwork generators (badges, boot screen, mode tags, menu text).

FAUXJI's artwork was drawn with Windows' Bahnschrift (a DIN-style font). To keep builds byte-identical on Windows it is still
the first choice. Elsewhere, set FAUXJI_FONT to any .ttf (a DIN-like open font such as Barlow or D-DIN looks closest), or put
one in tools/fonts/ named font.ttf.
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CANDIDATES = [
    os.environ.get('FAUXJI_FONT', ''),
    r'C:\Windows\Fonts\bahnschrift.ttf',
    os.path.join(HERE, 'fonts', 'font.ttf'),
]


def find_font():
    for p in CANDIDATES:
        if p and os.path.exists(p):
            return p
    raise SystemExit('No font found for the artwork. Set FAUXJI_FONT to a .ttf file (a DIN-style font such as Barlow or D-DIN '
                     'works), or put one at tools/fonts/font.ttf. On Windows, Bahnschrift is used automatically.')

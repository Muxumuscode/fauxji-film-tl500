"""Checks of the film build's skin tiles (wind-on, roll-full and the scene tiles that show the look's cartridge) on a built SPID.Rom.
From the project root:  python tools/test_film_layout.py <SPID.Rom of a --film build>"""
import sys
sys.path.insert(0, 'tools')
import spid_files, skin, film_mode as F

bad = 0
d = open(sys.argv[1], 'rb').read()
rec, off, size, slot = spid_files.directory(d)['skin.bin']
k = bytes(d[off:off + size])
offs = skin.images(k)
for idx in (F.IMG_WIND, F.IMG_FULL) + tuple(F.SCENE_TILES.values()):
    w, h, t, px = skin.decode(k, offs[idx])
    if (w, h) != (58, 54):
        bad += 1
        print('BAD tile size', idx, w, h)
print('tile checks, bad', bad)

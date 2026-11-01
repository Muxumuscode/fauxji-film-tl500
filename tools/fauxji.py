"""FAUXJI FILM PRO: write Fuji-style colour matrices into the TL500 Photo Styles.

Each Photo Style has a 3x3 colour matrix (int32, 256 = 1.0) that the image pipeline
multiplies with the sensor colour matrix (TL500 CCMatrix stage 0xC0448FF4 reads
0xC07BB28C[style]; live view uses the copy at 0xC07B3C40). This script builds the
FAUXJI matrices from a few readable knobs and patches both copies.

Knobs per look: per-row saturation (R, G, B rows; 1.0 = unchanged, 0 = mono),
channel gains (warmth/tint), extra cross-mixes for hue shifts, overall gain.
Saturation is luminance-preserving around Samsung's own luma weights.

Run from project root:  python tools/fauxji.py <elf in> <elf out>
"""
import struct, sys

B = 0xC0003FF5                       # runtime = file offset + B
STILL, LIVE = 0xC07BB28C, 0xC07B3C40
LUMA = (78 / 256, 150 / 256, 28 / 256)   # Samsung's B&W row

# internal style number -> (menu name before, FAUXJI name)
SLOTS = {0: ('Normal', 'PROVIA'), 1: ('Classic', 'ACROS'), 2: ('Soft', 'ASTIA'),
         3: ('Cool', 'Classic Neg.'), 4: ('Retro', 'Classic Chrome'),
         5: ('Forest', 'Reala Ace'), 6: ('Vivid', 'Velvia'), 7: ('Calm', 'Eterna'),
         8: ('Negative', 'Sepia')}


def look(sat=(1, 1, 1), gain=(1, 1, 1), mix=(), overall=1.0, mono=None):
    """Return a 3x3 float matrix. mix: (out_row, in_col, amount) cross-terms."""
    if mono is not None:                       # black and white from custom weights
        m = [list(mono) for _ in range(3)]
    else:
        m = [[(1 - s) * LUMA[c] + (s if c == r else 0) for c in range(3)]
             for r, s in enumerate(sat)]
    for r, c, a in mix:
        m[r][c] += a
        m[r][r] -= a                           # keep the row's sum (no brightness change)
    return [[v * gain[r] * overall for v in row] for r, row in enumerate(m)]


R, G, Bl = 0, 1, 2
LOOKS = {
    0: look(),                                                  # PROVIA: Samsung standard
    1: look(mono=(0.35, 0.55, 0.10)),                           # ACROS: R/G mix, cleaner than blue
    2: look(sat=(1.00, 1.10, 1.10), gain=(1.01, 1, 0.99)),      # ASTIA: soft skin, clean sky/green
    3: look(sat=(0.95, 0.70, 0.90), gain=(0.98, 1, 1.03),       # Classic Neg.: yellow-ish greens,
            mix=[(R, G, 0.05)], overall=0.97),                  #   cool cast, muted greens
    4: look(sat=(0.70, 0.80, 0.80), gain=(1.02, 1, 0.97),       # Classic Chrome: muted, cyan blues,
            mix=[(G, Bl, 0.06)], overall=0.92),                 #   darker (style also gets bright curve 5)
    5: look(sat=(1.08, 1.08, 1.08)),                            # Reala Ace: natural, slightly richer
    6: look(sat=(1.20, 1.40, 1.40)),                            # Velvia: big greens/blues, reds held back
    7: look(sat=(0.65, 0.65, 0.65), mix=[(G, Bl, 0.03)],        # Eterna: low saturation, teal greens
            overall=0.95),
    8: look(mono=(0.33, 0.57, 0.10), gain=(1.08, 1.0, 0.80)),   # Sepia: warm-toned monochrome
}


def fixed(m):
    return [int(round(v * 256)) for row in m for v in row]


def patch(d):
    d = bytearray(d)
    for base in (STILL, LIVE):
        for k, m in LOOKS.items():
            struct.pack_into('<9i', d, base - B + 36 * k, *fixed(m))
    # Sepia uses the Negative slot: switch off its colour-inversion stage
    # (0xC044AE2C `cmp lr,#8` -> `cmp lr,#0xFF`, a style number that never occurs)
    o = 0xC044AE2C - B
    assert struct.unpack_from('<I', d, o)[0] in (0xE35E0008, 0xE35E00FF)
    struct.pack_into('<I', d, o, 0xE35E00FF)
    return bytes(d)


if __name__ == '__main__':
    src, dst = sys.argv[1], sys.argv[2]
    d = open(src, 'rb').read()
    for base in (STILL, LIVE):
        assert struct.unpack_from('<9i', d, base - B + 36)[0:3] in ((78, 150, 28), tuple(fixed(LOOKS[1])[0:3])), \
            'style table not where expected'
    out = patch(d)
    open(dst, 'wb').write(out)
    for k, (old, new) in SLOTS.items():
        f = fixed(LOOKS[k])
        print('%d %-9s -> %-15s %s' % (k, old, new, [f[0:3], f[3:6], f[6:9]]))

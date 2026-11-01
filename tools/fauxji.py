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
# (2 and 7 confirmed by the FAUXJI3 test shots: Soft is 7, Calm is 2)
SLOTS = {0: ('Normal', 'PROVIA'), 1: ('Classic', 'ACROS'), 2: ('Calm', 'Eterna'),
         3: ('Cool', 'Classic Neg.'), 4: ('Retro', 'Classic Chrome'),
         5: ('Forest', 'Reala Ace'), 6: ('Vivid', 'Velvia'), 7: ('Soft', 'ASTIA'),
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
    2: look(sat=(0.62, 0.62, 0.62), mix=[(G, Bl, 0.03)],        # Eterna: low saturation, teal greens
            overall=0.98),
    3: look(sat=(0.95, 0.70, 0.90), gain=(0.98, 1, 1.03),       # Classic Neg.: yellow-ish greens,
            mix=[(R, G, 0.05)], overall=0.98),                  #   cool cast, muted greens
    4: look(sat=(0.68, 0.78, 0.80), gain=(1.02, 1, 0.97),       # Classic Chrome: muted, cyan blues
            mix=[(G, Bl, 0.06)], overall=0.97),                 #   (density now comes from its curve)
    5: look(sat=(1.08, 1.08, 1.08)),                            # Reala Ace: natural, slightly richer
    6: look(sat=(1.20, 1.40, 1.40)),                            # Velvia: big greens/blues, reds held back
    7: look(sat=(1.00, 1.10, 1.10), gain=(1.01, 1, 0.99)),      # ASTIA: soft skin, clean sky/green
    8: look(mono=(0.33, 0.57, 0.10), gain=(1.08, 1.0, 0.80)),   # Sepia: warm-toned monochrome
}

# Tone curves (display-referred, 0..255 in and out; stock curve 2 is the identity).
# Control points are joined with a monotone cubic. Every curve keeps a soft shoulder
# above ~224 (this CCD has ~11 EV, so highlights are rolled off rather than clipped)
# and never lifts the black point (lifted blacks would show CCD noise).
CURVE_POINTS = {
    'velvia':  [(0, 0), (32, 22), (64, 52), (128, 134), (192, 208), (224, 234), (255, 255)],
    'chrome':  [(0, 0), (32, 19), (64, 46), (128, 120), (192, 192), (224, 222), (255, 250)],
    'neg':     [(0, 0), (32, 17), (64, 45), (128, 128), (192, 210), (224, 236), (255, 255)],
    'eterna':  [(0, 0), (32, 31), (64, 65), (128, 128), (192, 185), (224, 213), (255, 246)],
    'astia':   [(0, 0), (32, 32), (64, 66), (128, 131), (192, 191), (224, 221), (255, 253)],
    'reala':   [(0, 0), (32, 28), (64, 60), (128, 129), (192, 197), (224, 227), (255, 255)],
}
CURVE_ORDER = ['velvia', 'chrome', 'neg', 'eterna', 'astia', 'reala']
# internal style -> curve name, or None = keep the camera's own choice
STYLE_CURVE = {0: None, 1: None, 2: 'eterna', 3: 'neg', 4: 'chrome', 5: 'reala',
               6: 'velvia', 7: 'astia', 8: None, 9: None, 10: None, 11: None}

# cave layout (free zeros after the Manual auto-ISO routine, 0xC070373C-0xC0703E28)
CURVE_CODE = 0xC0703740
HOOK = 0xC0449864          # gamma stage: `ldr ip,=0xC07B9AD4` (curve base) -> b CURVE_CODE
HOOK_RET = 0xC0449870
STOCK_BASE = 0xC07B9AD4
CAVE_END = 0xC0703E28


def monotone(points):
    """256-entry monotone cubic (Fritsch-Carlson) through the control points."""
    xs, ys = zip(*points)
    n = len(xs)
    dk = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) for i in range(n - 1)]
    m = [dk[0]] + [0 if dk[i - 1] * dk[i] <= 0 else (dk[i - 1] + dk[i]) / 2 for i in range(1, n - 1)] + [dk[-1]]
    for i in range(n - 1):
        if dk[i] == 0:
            m[i] = m[i + 1] = 0
        else:
            a, b = m[i] / dk[i], m[i + 1] / dk[i]
            s = a * a + b * b
            if s > 9:
                t = 3 / s ** 0.5
                m[i], m[i + 1] = t * a * dk[i], t * b * dk[i]
    out = []
    for x in range(256):
        i = max(k for k in range(n - 1) if xs[k] <= x) if x < xs[-1] else n - 2
        h = xs[i + 1] - xs[i]; t = (x - xs[i]) / h
        h00, h10 = 2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t
        h01, h11 = -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2
        y = h00 * ys[i] + h10 * h * m[i] + h01 * ys[i + 1] + h11 * h * m[i + 1]
        out.append(max(0, min(255, int(round(y)))))
    for k in range(255):
        out[k + 1] = max(out[k + 1], out[k])
    return bytes(out)


def arm_b(src, dst, cond=0xE, link=False):
    return (cond << 28) | ((0xB if link else 0xA) << 24) | (((dst - (src + 8)) >> 2) & 0xFFFFFF)


def ldr_pc(rd, src, lit):
    return 0xE59F0000 | (rd << 12) | (lit - (src + 8))


def curve_routine():
    """Pick a FAUXJI curve for this style (unless Samsung's special mode is on)."""
    base = CURVE_CODE
    lits = base + 21 * 4                       # three literal words after the code
    table = lits + 12
    curves = table + 16
    EQ, NE, HS = 0x0, 0x1, 0x2
    stock = base + 17 * 4
    w = [0xE59B200C,                           # ldr r2,[fp,#0xc]    style
         0xE352000C,                           # cmp r2,#12
         None,                                 # bhs stock
         0xE59B3044,                           # ldr r3,[fp,#0x44]   special tone mode?
         0xE3530003,                           # cmp r3,#3
         None,                                 # beq stock
         None,                                 # ldr ip,=table
         0xE7DCC002,                           # ldrb ip,[ip,r2]
         0xE35C00FF,                           # cmp ip,#0xff
         None,                                 # beq stock
         None,                                 # ldr r3,=curves
         0xE083A40C,                           # add sl,r3,ip,lsl #8   curve pointer
         0xE28CC020,                           # add ip,ip,#0x20       distinct parameter key
         0xE58DC010,                           # str ip,[sp,#0x10]
         0xE3A0C000,                           # mov ip,#0
         0xE58DC014,                           # str ip,[sp,#0x14]
         None,                                 # b HOOK_RET
         None,                                 # stock: ldr ip,=STOCK_BASE
         0xE59DE010,                           # ldr lr,[sp,#0x10]
         0xE08CA40E,                           # add sl,ip,lr,lsl #8
         None]                                 # b HOOK_RET
    w[2] = arm_b(base + 8, stock, HS)
    w[5] = arm_b(base + 20, stock, EQ)
    w[6] = ldr_pc(12, base + 24, lits)
    w[9] = arm_b(base + 36, stock, EQ)
    w[10] = ldr_pc(3, base + 40, lits + 4)
    w[16] = arm_b(base + 64, HOOK_RET)
    w[17] = ldr_pc(12, base + 68, lits + 8)
    w[20] = arm_b(base + 80, HOOK_RET)
    code = b''.join(struct.pack('<I', x) for x in w)
    code += struct.pack('<III', table, curves, STOCK_BASE)
    tbl = bytes(0xFF if STYLE_CURVE[s] is None else CURVE_ORDER.index(STYLE_CURVE[s]) for s in range(12))
    code += tbl + b'\xff' * 4
    assert len(code) == curves - base
    code += b''.join(monotone(CURVE_POINTS[c]) for c in CURVE_ORDER)
    assert base + len(code) <= CAVE_END, 'cave overflow'
    return code


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
    # ...and make style 8 use its own matrix: the CCMatrix switch only covers 0-7 and
    # its default case picked matrix 8 only when flag this+0x3E was set.
    # `ldrb lr,[fp,#0x3e]; cmp lr,#0; beq` -> `ldr lr,[fp,#0xc]; cmp lr,#8; bne`
    for addr, old, new in ((0xC044937C, 0xE5DBE03E, 0xE59BE00C),
                           (0xC0449380, 0xE35E0000, 0xE35E0008),
                           (0xC0449384, 0x0A000016, 0x1A000016)):
        assert struct.unpack_from('<I', d, addr - B)[0] in (old, new)
        struct.pack_into('<I', d, addr - B, new)
    # per-style tone curves: routine + table + curves in the cave, hooked at the
    # point where the gamma stage computes its curve pointer
    code = curve_routine()
    o = CURVE_CODE - B
    assert all(c in (0,) for c in d[o:o + len(code)]) or d[o:o + 4] == code[:4], 'cave not free'
    d[o:o + len(code)] = code
    h = struct.unpack_from('<I', d, HOOK - B)[0]
    assert h in (0xE59FCED8, arm_b(HOOK, CURVE_CODE))
    struct.pack_into('<I', d, HOOK - B, arm_b(HOOK, CURVE_CODE))
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

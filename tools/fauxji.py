"""FAUXJI FILM PRO: Fuji-style colour matrices and tone curves for the TL500 Photo Styles.

Each Photo Style has a 3x3 colour matrix (int32, 256 = 1.0) that the image pipeline
multiplies with the sensor colour matrix (TL500 CCMatrix stage 0xC0448FF4 reads
0xC07BB28C[style]; live view uses the copy at 0xC07B3C40). The tone stage
(0xC0449730) picks one of nine 256-byte curves at 0xC07B9AD4 + n*256.

This script builds the FAUXJI matrices from a few readable knobs, gives each style
its own curve by rewriting the tone stage's style checks *in place* as a table
lookup, and writes three custom curves into slots 6-8 (otherwise used only by the
Beauty Shot face-tone levels 1-3). It also moves the Manual auto-ISO routine out of
0xC0703704 (a driver's hardware-register shadow area, not free space) into the
factory-only EEPROM-dump function 0xC042661C, and restores the shadow area to zeros.

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
            mix=[(G, Bl, 0.06)], overall=0.97),                 #   (density comes from its curve)
    5: look(sat=(1.08, 1.08, 1.08)),                            # Reala Ace: natural, slightly richer
    6: look(sat=(1.20, 1.40, 1.40)),                            # Velvia: big greens/blues, reds held back
    7: look(sat=(1.00, 1.10, 1.10), gain=(1.01, 1, 0.99)),      # ASTIA: soft skin, clean sky/green
    8: look(mono=(0.33, 0.57, 0.10), gain=(1.08, 1.0, 0.80)),   # Sepia: warm-toned monochrome
}

# Custom tone curves (display-referred, 0..255; stock curve 2 is the identity),
# joined with a monotone cubic. Soft shoulder above ~224 (this CCD has ~11 EV) and
# the black point is never lifted (lifted blacks would show CCD noise).
CURVE_POINTS = {
    'velvia': [(0, 0), (32, 22), (64, 52), (128, 134), (192, 208), (224, 234), (255, 255)],
    'chrome': [(0, 0), (32, 19), (64, 46), (128, 120), (192, 192), (224, 222), (255, 250)],
    'neg':    [(0, 0), (32, 17), (64, 45), (128, 128), (192, 210), (224, 236), (255, 255)],
}
CURVE_SLOT = {'velvia': 6, 'chrome': 7, 'neg': 8}   # Beauty Shot face-tone slots 6-8
STOCK_CURVES = 0xC07B9AD4
# internal style -> curve slot (0-8), or None = keep the camera's own choice (Contrast).
# Stock slots: 0/1 = Contrast -2/-1 (soft), 3 = Contrast +1, 4 = Contrast +2 (B&W).
STYLE_CURVE = {0: None, 1: 4, 2: 0, 3: CURVE_SLOT['neg'], 4: CURVE_SLOT['chrome'], 5: 3,
               6: CURVE_SLOT['velvia'], 7: 1, 8: 4, 9: None, 10: None, 11: None}

# Tone stage: Samsung's style checks (19 words) become a table lookup, same place.
TONE_BLOCK, TONE_DONE = 0xC0449788, 0xC04497D4

# Manual auto-ISO routine (AeCalcCaptureManual 0xC05408C8, ISO-Auto fallback hook)
ISO_HOOK, ISO_RET = 0xC0540938, 0xC0540940
ISO_HOME = 0xC042661C        # factory-only "Check EEPROM" dump (E2PR.CSV), never runs normally
OLD_CAVE, OLD_CAVE_LEN = 0xC0703704, 0x3C   # driver register shadows: must stay zero
EVC_SHIFT = 0xC03ECCF8       # AeSystemEVCSetToAeEVCShift -> EV comp, x16


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


def tone_block():
    """In-place replacement for the tone stage's style -> curve checks."""
    EQ, HS = 0x0, 0x2
    a = TONE_BLOCK
    table = a + 11 * 4
    w = [0xE59B200C,                                  # ldr r2,[fp,#0xc]   style
         0xE352000C,                                  # cmp r2,#12
         arm_b(a + 8, TONE_DONE, HS),                 # bhs done (keep Contrast curve)
         0xE28F3000 | (table - (a + 12 + 8)),         # add r3,pc,#table
         0xE7D33002,                                  # ldrb r3,[r3,r2]
         0xE35300FF,                                  # cmp r3,#0xff
         arm_b(a + 24, TONE_DONE, EQ),                # beq done
         0xE58D3010,                                  # str r3,[sp,#0x10]  curve index
         0xE3A03000,                                  # mov r3,#0
         0xE58D3014,                                  # str r3,[sp,#0x14]
         arm_b(a + 40, TONE_DONE)]                    # b done (Beauty Shot check follows)
    tbl = bytes(0xFF if STYLE_CURVE[s] is None else STYLE_CURVE[s] for s in range(12))
    code = b''.join(struct.pack('<I', x) for x in w) + tbl
    code += struct.pack('<I', 0xE1A00000) * ((TONE_DONE - a - len(code)) // 4)   # nop fill
    assert len(code) == TONE_DONE - a
    return code


def iso_routine():
    """Manual auto-ISO: Sv = Tv + Av - Ev + 80 + EVcomp, clamped ISO80..ISO3200."""
    a = ISO_HOME
    w = [arm_b(a, EVC_SHIFT, link=True),              # bl AeSystemEVCSetToAeEVCShift -> r0
         0xE1DAE0F0, 0xE1DAC0F2, 0xE08EE00C,          # lr = Tv + Av
         0xE1DDC2F8, 0xE04EE00C,                      # lr -= metered Ev [sp,#0x28]
         0xE28EE050, 0xE08EE000,                      # lr += 80 + EV comp
         0xE35E004B, 0xB3A0E04B,                      # min ISO80
         0xE35E00A0, 0xC3A0E0A0,                      # max ISO3200
         0xE1CAE0B4]                                  # strh lr,[sl,#4]
    w.append(arm_b(a + 4 * len(w), ISO_RET))
    return b''.join(struct.pack('<I', x) for x in w)


def fixed(m):
    return [int(round(v * 256)) for row in m for v in row]


def put(d, addr, data):
    d[addr - B:addr - B + len(data)] = data


def word(d, addr):
    return struct.unpack_from('<I', d, addr - B)[0]


def patch(d):
    d = bytearray(d)
    # colour matrices, capture and live view
    for base in (STILL, LIVE):
        for k, m in LOOKS.items():
            struct.pack_into('<9i', d, base - B + 36 * k, *fixed(m))
    # Sepia uses the Negative slot: switch off its colour-inversion stage
    assert word(d, 0xC044AE2C) in (0xE35E0008, 0xE35E00FF)
    struct.pack_into('<I', d, 0xC044AE2C - B, 0xE35E00FF)
    # ...and make style 8 use its own matrix (CCMatrix default case only took matrix 8
    # when flag this+0x3E was set): `ldrb lr,[fp,#0x3e]; cmp lr,#0; beq`
    #   -> `ldr lr,[fp,#0xc]; cmp lr,#8; bne`
    for addr, old, new in ((0xC044937C, 0xE5DBE03E, 0xE59BE00C),
                           (0xC0449380, 0xE35E0000, 0xE35E0008),
                           (0xC0449384, 0x0A000016, 0x1A000016)):
        assert word(d, addr) in (old, new)
        struct.pack_into('<I', d, addr - B, new)
    # tone: undo the FAUXJI5 cave hook if present, then the in-place table lookup
    if word(d, 0xC0449864) == arm_b(0xC0449864, 0xC0703740):
        struct.pack_into('<I', d, 0xC0449864 - B, 0xE59FCED8)     # stock `ldr ip,=curve base`
    assert word(d, 0xC0449864) == 0xE59FCED8
    assert word(d, TONE_BLOCK) == 0xE59B200C                       # `ldr r2,[fp,#0xc]` in both
    put(d, TONE_BLOCK, tone_block())
    for name, slot in CURVE_SLOT.items():
        put(d, STOCK_CURVES + 256 * slot, monotone(CURVE_POINTS[name]))
    # Manual auto-ISO: move routine to the factory-only function, zero the shadow area
    hook = word(d, ISO_HOOK)
    assert hook in (0xE3A0E050, arm_b(ISO_HOOK, OLD_CAVE), arm_b(ISO_HOOK, ISO_HOME))
    put(d, ISO_HOME, iso_routine())
    struct.pack_into('<I', d, ISO_HOOK - B, arm_b(ISO_HOOK, ISO_HOME))
    o = OLD_CAVE - B
    d[o:o + 0x724] = b'\0' * 0x724                                 # 0xC0703704-0xC0703E28, as stock
    return bytes(d)


if __name__ == '__main__':
    src, dst = sys.argv[1], sys.argv[2]
    d = open(src, 'rb').read()
    out = patch(d)
    open(dst, 'wb').write(out)
    for k, (old, new) in SLOTS.items():
        f = fixed(LOOKS[k])
        print('%d %-9s -> %-15s curve %-4s %s' % (k, old, new, STYLE_CURVE[k], [f[0:3], f[3:6], f[6:9]]))

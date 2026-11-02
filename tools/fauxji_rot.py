"""FAUXJI tilt tag: put EXIF Orientation on vertical shots (the TL500 has no tilt sensor).

Live EXIF writer: 0xC0385868 (the CMux/ExifMux component; the writers at 0xC03773E0,
0xC0383120 and 0xC0388668 are never called, see tools/liveness.py). Its Orientation case
(tag 0x112, 0xC0385ED8) stores the constant 1 at `mov lr,#1` (0xC0385F00): hooked.

Face detector: SDIC_FaceDetection 0xC058F798 already scans rotated faces. A frame counter
(0xC09F51F0) cycles 13 calls; its angle r6 is 0, -30, +30, -90, +90, -60, +60. The +-90 scans
rotate the luma image with 0xC0595A18 (r6 = -90: 90 degrees CCW) or 0xC0595A94 (r6 = +90:
CW) and then detect upright faces. A face found with r6 = +90 was rotated CCW in the frame
(camera top to the right): EXIF Orientation 6; r6 = -90: Orientation 8. At the function's
end (0xC058FA0C, r6 = scan angle, r8 = result block with the face count at +0x2FC) a hook
remembers that (FACE_ORI) for 60 upright scans.

Menu unlock: the menu's per-setting "allowed options" masks (21 words, 0xFFFFFF = all allowed,
set through 0xC04CE83C by ~117 call sites, mostly 0xC04D2000) are forced to all-allowed while
the shooting mode (sysvalue 3, the AE sysmode enum: 0 P, 1 Auto, 2 A, 3 S, 4 M, 5 Bulb, 8 Movie,
9 Smart Auto, 10+ scenes) is P, A, S or M.

Control: a state STATE cycles on a button press and shows a pop-up (fauxji_ui.ROT_TEXTS):
0 Off, 1 Auto (from faces), 2 Auto flipped (6 <-> 8), 3 always 6 (top right), 4 always 8,
5 "press a key": the next key pressed and released is learned (ROT_KEY) as the tilt key.
Buttons: AE-L's "AE-L" option (logical key 0; call at 0xC04C1A98) always works; a learned key
is caught in the live-view key dispatcher (0xC04C1944, the "is this key handled" call) and
swallowed, so its stock action (e.g. start recording) does not run.
Code: the dead factory function 0xC04260A0 (+ its two small neighbours) and the tail of
the "ChineseCheck" function (after the zoom hook).
"""
import struct

import fauxji_ui as ui

B = ui.B
R1, R1_END = 0xC04260A0, 0xC042620C
R2, R2_END = ui.ZOOM_HOOK + 16, ui.EXTRA_END
STATE, FACE_ORI, FACE_TTL, KEY = R1, R1 + 4, R1 + 8, R1 + 12
assert STATE == ui.ROT_STATE and KEY == ui.ROT_KEY
KEY_DEFAULT = 0xFF                    # no learned key (set to the video button's number later)
DIAG = True                           # FAUXJI41 test build: pop-up shows the number of any pressed key
WRITER_SITE, WRITER_BACK = 0xC0385F00, 0xC0385F04
FD_SITE, FD_BACK = 0xC058FA0C, 0xC058FA10
KEY_SITE, KEY_STOCK = 0xC04C1A98, 0xC04C1414
MASK_SITE, MASK_BACK, GET_SYSVAL = 0xC04CE844, 0xC04CE848, 0xC048F81C
# Highlight bias: AeSystemEVCSetToAeEVCShift (0xC03ECCF8) returns the EV compensation x16 that
# the AE adds (AeUpdateSysInfo; manual-mode ISO routine too). Subtracting AE_BIAS makes the
# camera meter that much darker in every mode while the EV comp scale still shows 0.
EV_SITE, EV_BACK = 0xC03ECD54, 0xC03ECD58
AE_BIAS = 5                           # 1/16 EV steps: 5 = -0.3 EV, 8 = -0.5 EV
DISP_SITE, DISP_STOCK = 0xC04C1944, 0xC04BFF98
TTL = 60
STATES = 6
FIRST_TEXT = 11                       # NAME_STRINGS index of the first tilt text
BUF_TEXT = FIRST_TEXT + STATES        # "Tilt key = NN" (index 17)
BUF_DIGITS = ui.STR_BASE + 6 * ui.STR_SLOT + 22
PRESS_CHECK = [0xE5913000, 0xE2832010, 0xE592C004, 0xE1D230F0,     # event vtable -> is-press call
               0xE0810003, 0xE1A0E00F, 0xE1A0F00C]


class Asm:
    def __init__(self, base, end):
        self.base, self.end, self.w, self.fix = base, end, [], []

    def here(self):
        return self.base + 4 * len(self.w)

    def emit(self, *ws):
        self.w.extend(ws)

    def br(self, cond, name, link=False):
        self.fix.append((len(self.w), cond, name, link))
        self.w.append(0)

    def ldr(self, reg, target):
        self.emit(ui._ldr_pc(self.here(), reg, target))

    def str(self, reg, target):
        self.emit(ui._ldr_pc(self.here(), reg, target, store=True))


def build():
    labels = {}
    r1, r2 = Asm(R1, R1_END), Asm(R2, R2_END)

    def label(a, n):
        labels[n] = a.here()

    # ---------------- region 1: data, writer hook, face hook, AE-L key routine -------------
    a = r1
    a.emit(0, 0, 0, KEY_DEFAULT)                   # STATE, FACE_ORI, FACE_TTL, KEY

    label(a, 'writer')                             # replaces `mov lr,#1` at 0xC0385F00
    a.emit(0xE3A0E001)                             # mov lr,#1        (stock)
    a.ldr(12, STATE)                               # ldr ip,STATE
    a.emit(0xE35C0003, 0x03A0E006)                 # cmp ip,#3 ; moveq lr,#6
    a.br(0x0, 'wdone')
    a.emit(0xE35C0004, 0x03A0E008)                 # cmp ip,#4 ; moveq lr,#8
    a.br(0x0, 'wdone')
    a.emit(0xE35C0002)                             # cmp ip,#2
    a.br(0x8, 'wdone')                             # bhi wdone   (state 5: off)
    a.emit(0xE35C0000)                             # cmp ip,#0
    a.br(0x0, 'wdone')                             # beq wdone   (off)
    a.ldr(3, FACE_ORI)                             # ldr r3,FACE_ORI
    a.emit(0xE3530000)                             # cmp r3,#0
    a.br(0x0, 'wdone')                             # no sideways face seen
    a.emit(0xE35C0002, 0x0263300E)                 # cmp ip,#2 ; rsbeq r3,r3,#14   (6 <-> 8)
    a.emit(0xE1A0E003)                             # mov lr,r3
    label(a, 'wdone')
    a.br(0xE, 'WRITER_BACK')

    label(a, 'face')                               # replaces `ldr r0,[r8,#0x2fc]` at 0xC058FA0C
    a.emit(0xE59802FC, 0xE3500000)                 # ldr r0,[r8,#0x2fc] ; cmp r0,#0   (face count)
    a.br(0xD, 'nofaces')                           # ble
    a.emit(0xE356005A, 0x03A01006)                 # cmp r6,#90 ; moveq r1,#6
    a.br(0x0, 'setv')
    a.emit(0xE376005A, 0x03A01008)                 # cmn r6,#90 ; moveq r1,#8
    a.br(0x0, 'setv')
    a.emit(0xE3560000)                             # cmp r6,#0
    a.br(0x1, 'fdone')                             # 30/60 degree scans: ignore
    a.emit(0xE3A01000, 0xE3A02000)                 # upright face: clear
    a.br(0xE, 'store')
    label(a, 'setv')
    a.emit(0xE3A02000 | TTL)
    a.br(0xE, 'store')
    label(a, 'nofaces')
    a.emit(0xE3560000)                             # cmp r6,#0
    a.br(0x1, 'fdone')                             # only upright scans age the tag
    a.ldr(2, FACE_TTL)
    a.emit(0xE2522001, 0xD3A02000)                 # subs r2,r2,#1 ; movle r2,#0
    a.ldr(1, FACE_ORI)
    a.emit(0xE3520000, 0x03A01000)                 # cmp r2,#0 ; moveq r1,#0
    label(a, 'store')
    a.str(1, FACE_ORI)
    a.str(2, FACE_TTL)
    label(a, 'fdone')
    a.emit(0xE59802FC)                             # ldr r0,[r8,#0x2fc]
    a.br(0xE, 'FD_BACK')

    label(a, 'key0')                               # replaces the AE-lock call for logical key 0
    a.emit(0xE92D4010)                             # push {r4, lr}
    a.emit(*PRESS_CHECK)
    a.emit(0xE3500001)                             # cmp r0,#1
    a.br(0x1, 'k0done')
    a.br(0xE, 'cycle', link=True)
    label(a, 'k0done')
    a.emit(0xE3A00000, 0xE8BD8010)                 # mov r0,#0 ; pop {r4, pc}

    label(a, 'evbias')                             # replaces `lsl r0,fp,#16` at 0xC03ECD54
    a.emit(0xE24BB000 | AE_BIAS)                   # sub fp,fp,#AE_BIAS
    a.emit(0xE1A0080B)                             # lsl r0,fp,#16   (stock)
    a.br(0xE, 'EV_BACK')

    label(a, 'unlock')                             # replaces `mov sl,r1` in the menu-mask setter
    a.emit(0xE92D000F, 0xE3A00003)                 # push {r0-r3} ; mov r0,#3  (shooting mode)
    a.br(0xE, 'GET_SYSVAL', link=True)
    a.emit(0xE1A0C000, 0xE8BD000F)                 # mov ip,r0 ; pop {r0-r3}
    a.emit(0xE35C0004)                             # cmp ip,#4
    a.br(0x8, 'mkeep')                             # bhi: scenes, movie, smart auto ...
    a.emit(0xE35C0001)                             # cmp ip,#1  (auto)
    a.br(0x0, 'mkeep')
    a.emit(0xE3E0A4FF)                             # mvn sl,#0xff000000  = 0xFFFFFF: all options allowed
    a.br(0xE, 'MASK_BACK')
    label(a, 'mkeep')
    a.emit(0xE1A0A001)                             # mov sl,r1  (stock)
    a.br(0xE, 'MASK_BACK')

    # ---------------- region 2: cycle(), dispatcher hook ------------------------------------
    a = r2
    label(a, 'cycle')                              # state++, clear the face tag, show the pop-up
    a.emit(0xE92D4010)                             # push {r4, lr}
    a.ldr(4, STATE)
    a.emit(0xE2844001, 0xE3540000 | STATES, 0xA3A04000)   # add r4,r4,#1 ; cmp ; movge r4,#0
    a.str(4, STATE)
    a.emit(0xE3A00000)                             # mov r0,#0
    a.str(0, FACE_ORI)
    a.str(0, FACE_TTL)
    a.emit(0xE2840000 | FIRST_TEXT)                # add r0,r4,#FIRST_TEXT
    a.br(0xE, 'ARM_NAME', link=True)
    a.emit(0xE2840000 | FIRST_TEXT)
    a.br(0xE, 'TOAST', link=True)
    a.emit(0xE8BD8010)                             # pop {r4, pc}

    label(a, 'disp')                               # replaces `bl 0xC04BFF98` (r0 = state, r1 = key)
    a.emit(0xE92D4013)                             # push {r0, r1, r4, lr}
    a.emit(0xE59A3000, 0xE2832010, 0xE592C004, 0xE1D230F0,   # same press check, event = sl
           0xE08A0003, 0xE1A0E00F, 0xE1A0F00C)
    a.emit(0xE1A04000)                             # mov r4,r0         1 = press, 0 = release
    a.emit(0xE59D1004)                             # ldr r1,[sp,#4]    key
    a.ldr(2, STATE)
    a.emit(0xE3520005)                             # cmp r2,#5
    a.br(0x1, 'dchk')
    a.emit(0xE3510000)                             # cmp r1,#0         AE-L still leaves the mode
    a.br(0x0, 'pass')
    a.emit(0xE3540000)                             # cmp r4,#0
    a.br(0x1, 'swallow')                           # press: wait for the release
    a.str(1, KEY)                                  # release: learn the key
    a.emit(0xE3A02000)                             # mov r2,#0
    a.str(2, STATE)
    a.str(2, FACE_ORI)
    a.str(2, FACE_TTL)
    a.ldr(3, 0)                                    # placeholder, fixed below (literal pool)
    pool_load = len(a.w) - 1
    a.emit(0xE351000A, 0xB3A02030, 0xA3A02031, 0xA241100A, 0xE2811030,
           0xE1C320B0, 0xE1C310B2)                 # digits "NN" into the pop-up text
    a.emit(0xE3A00000 | BUF_TEXT)                  # mov r0,#BUF_TEXT
    a.br(0xE, 'ARM_NAME', link=True)
    a.emit(0xE3A00000 | BUF_TEXT)
    a.br(0xE, 'TOAST', link=True)
    a.br(0xE, 'swallow')
    label(a, 'dchk')
    a.ldr(3, KEY)
    a.emit(0xE1510003)                             # cmp r1,r3
    a.br(0x1, 'diag' if DIAG else 'pass')
    a.emit(0xE3540001)                             # cmp r4,#1
    a.br(0x1, 'swallow')
    a.br(0xE, 'cycle', link=True)
    if DIAG:                                       # test build: show the key number of every other press
        label(a, 'diag')
        a.emit(0xE3540001)                         # cmp r4,#1  (press only)
        a.br(0x1, 'pass')
        a.emit(0xE351000E)                         # cmp r1,#14 (AE-L = film sim: leave alone)
        a.br(0x0, 'pass')
        a.emit(0xE3510000)                         # cmp r1,#0
        a.br(0x0, 'pass')
        a.ldr(3, 0)
        pool_load2 = len(a.w) - 1
        a.emit(0xE3A02030,                         # mov r2,#'0'
               0xE351000A, 0xA241100A, 0xA2822001, 0xAAFFFFFB,   # tens loop: cmp r1,#10; subge; addge; bge
               0xE2811030, 0xE1C320B0, 0xE1C310B2)               # digits "NN" into the pop-up text
        a.emit(0xE3A00000 | BUF_TEXT)
        a.br(0xE, 'ARM_NAME', link=True)
        a.emit(0xE3A00000 | BUF_TEXT)
        a.br(0xE, 'TOAST', link=True)
        a.br(0xE, 'pass')
    label(a, 'swallow')
    a.emit(0xE8BD4013, 0xE3A00000, 0xE1A0F00E)     # pop {r0,r1,r4,lr} ; mov r0,#0 ; mov pc,lr
    label(a, 'pass')
    a.emit(0xE8BD4013)
    a.br(0xE, 'DISP_STOCK')
    pool = a.here()
    a.emit(BUF_DIGITS)
    a.w[pool_load] = ui._ldr_pc(R2 + 4 * pool_load, 3, pool)
    if DIAG:
        a.w[pool_load2] = ui._ldr_pc(R2 + 4 * pool_load2, 3, pool)

    ext = {'WRITER_BACK': WRITER_BACK, 'FD_BACK': FD_BACK, 'ARM_NAME': ui.ARM_NAME,
           'TOAST': ui.TOAST_CODE, 'DISP_STOCK': DISP_STOCK,
           'GET_SYSVAL': GET_SYSVAL, 'EV_BACK': EV_BACK, 'MASK_BACK': MASK_BACK}
    blobs = []
    for a in (r1, r2):
        for idx, cond, name, link in a.fix:
            dst = labels[name] if name in labels else ext[name]
            a.w[idx] = ui._b(a.base + 4 * idx, dst, cond=cond, link=link)
        blob = b''.join(struct.pack('<I', w) for w in a.w)
        assert a.base + len(blob) <= a.end, (hex(a.base), hex(a.base + len(blob)))
        blobs.append((a.base, blob))
    return blobs, labels


def patch(d):
    d = bytearray(d)
    blobs, lab = build()
    for base, blob in blobs:
        d[base - B:base - B + len(blob)] = blob
    for site, stock, new in (
            (WRITER_SITE, 0xE3A0E001, ui._b(WRITER_SITE, lab['writer'])),
            (FD_SITE, 0xE59802FC, ui._b(FD_SITE, lab['face'])),
            (KEY_SITE, ui._b(KEY_SITE, KEY_STOCK, link=True), ui._b(KEY_SITE, lab['key0'], link=True)),
            (EV_SITE, 0xE1A0080B, ui._b(EV_SITE, lab['evbias'])),
            (MASK_SITE, 0xE1A0A001, ui._b(MASK_SITE, lab['unlock'])),
            (DISP_SITE, ui._b(DISP_SITE, DISP_STOCK, link=True), ui._b(DISP_SITE, lab['disp'], link=True))):
        cur = struct.unpack_from('<I', d, site - B)[0]
        assert cur in (stock, new), (hex(site), hex(cur))
        struct.pack_into('<I', d, site - B, new)
    return bytes(d)


if __name__ == '__main__':
    import capstone as cs
    blobs, lab = build()
    print({k: hex(v) for k, v in lab.items()})
    md = cs.Cs(cs.CS_ARCH_ARM, cs.CS_MODE_ARM)
    for base, blob in blobs:
        print('--', hex(base), len(blob), 'bytes')
        for k in range(len(blob) // 4):
            for i in md.disasm(blob[4 * k:4 * k + 4], base + 4 * k):
                print('%08x: %s %s' % (i.address, i.mnemonic, i.op_str))

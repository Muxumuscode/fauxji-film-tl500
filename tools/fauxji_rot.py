"""FAUXJI tilt tag: put EXIF Orientation on vertical shots (the TL500 has no tilt sensor).

Live EXIF writer: 0xC0385868 (the CMux/ExifMux component; the writers at 0xC03773E0,
0xC0383120 and 0xC0388668 are never called). Its Orientation case (tag 0x112, 0xC0385ED8)
stores the constant 1 at `mov lr,#1` (0xC0385F00). We hook that site.

Face detector: SDIC_FaceDetection 0xC058F798 already scans rotated faces. A frame counter
(0xC09F51F0) cycles 13 calls; its angle r6 is 0, -30, +30, -90, +90, -60, +60. The ±90 scans
rotate the luma image with 0xC0595A18 (r6 = -90: 90 degrees CCW) or 0xC0595A94 (r6 = +90:
CW) and then detect upright faces. A face found with r6 = +90 was rotated CCW in the frame
(camera top to the right): EXIF Orientation 6; r6 = -90: Orientation 8. At the function's
end (0xC058FA0C, r6 = scan angle, r8 = result block with the face count at +0x2FC) a hook
remembers that (FACE_ORI) for 60 upright scans.

AE-L button: its "AE-L" option (logical key 0) cycles the tilt-tag state instead of AE
lock; the pop-up shows the state (texts: fauxji_ui.ROT_TEXTS). States:
0 Off, 1 Auto (from faces), 2 Auto flipped (6 <-> 8), 3 always 6 (top right), 4 always 8.
Code lives in the factory-only function at 0xC04260A0 (called only from the factory switch).
"""
import struct

import fauxji_ui as ui

B = ui.B
ROT = 0xC04260A0
ROT_END = 0xC042620C
STATE, FACE_ORI, FACE_TTL = ROT, ROT + 4, ROT + 8
WRITER_SITE, WRITER_BACK = 0xC0385F00, 0xC0385F04
FD_SITE, FD_BACK = 0xC058FA0C, 0xC058FA10
KEY_SITE, KEY_STOCK = 0xC04C1A98, 0xC04C1414
TTL = 60
STATES = 5
FIRST_TEXT = 11            # NAME_STRINGS index of the first tilt text


def _ldr(src, reg, target):
    return ui._ldr_pc(src, reg, target)


def _str(src, reg, target):
    return ui._ldr_pc(src, reg, target, store=True)


def build():
    """Return (bytes at ROT, dict of symbol addresses)."""
    out = []
    here = lambda: ROT + 4 * len(out)
    labels, fix = {}, []

    def emit(w):
        out.append(w)

    def label(n):
        labels[n] = here()

    def br(cond, name, link=False):
        fix.append((len(out), cond, name, link))
        out.append(0)

    emit(0); emit(0); emit(0)                      # STATE, FACE_ORI, FACE_TTL

    # ---- writer hook: replaces `mov lr,#1` at 0xC0385F00 ----
    label('writer')
    emit(0xE3A0E001)                               # mov lr,#1        (stock)
    emit(_ldr(here(), 12, STATE))                  # ldr ip,STATE
    emit(0xE35C0003)                               # cmp ip,#3
    emit(0x03A0E006)                               # moveq lr,#6
    br(0x0, 'wdone')                               # beq wdone
    emit(0xE35C0004)                               # cmp ip,#4
    emit(0x03A0E008)                               # moveq lr,#8
    br(0x0, 'wdone')                               # beq wdone
    emit(0xE35C0000)                               # cmp ip,#0
    br(0x0, 'wdone')                               # beq wdone (off)
    emit(_ldr(here(), 3, FACE_ORI))                # ldr r3,FACE_ORI
    emit(0xE3530000)                               # cmp r3,#0
    br(0x0, 'wdone')                               # beq wdone (no sideways face)
    emit(0xE35C0002)                               # cmp ip,#2
    emit(0x0263300E)                               # rsbeq r3,r3,#14  (6 <-> 8)
    emit(0xE1A0E003)                               # mov lr,r3
    label('wdone')
    br(0xE, 'WRITER_BACK')                         # b back

    # ---- face hook: replaces `ldr r0,[r8,#0x2fc]` at 0xC058FA0C ----
    label('face')
    emit(0xE59802FC)                               # ldr r0,[r8,#0x2fc]   face count
    emit(0xE3500000)                               # cmp r0,#0
    br(0xD, 'nofaces')                             # ble nofaces
    emit(0xE356005A)                               # cmp r6,#90
    emit(0x03A01006)                               # moveq r1,#6
    br(0x0, 'setv')                                # beq setv
    emit(0xE376005A)                               # cmn r6,#90
    emit(0x03A01008)                               # moveq r1,#8
    br(0x0, 'setv')                                # beq setv
    emit(0xE3560000)                               # cmp r6,#0
    br(0x1, 'fdone')                               # bne fdone (30/60 degree scans: ignore)
    emit(0xE3A01000)                               # mov r1,#0   upright face: clear
    emit(0xE3A02000)                               # mov r2,#0
    br(0xE, 'store')
    label('setv')
    emit(0xE3A02000 | TTL)                         # mov r2,#TTL
    br(0xE, 'store')
    label('nofaces')
    emit(0xE3560000)                               # cmp r6,#0
    br(0x1, 'fdone')                               # bne fdone (only upright scans age it)
    emit(_ldr(here(), 2, FACE_TTL))                # ldr r2,TTL
    emit(0xE2522001)                               # subs r2,r2,#1
    emit(0xD3A02000)                               # movle r2,#0
    emit(_ldr(here(), 1, FACE_ORI))                # ldr r1,ORI
    emit(0xE3520000)                               # cmp r2,#0
    emit(0x03A01000)                               # moveq r1,#0
    label('store')
    emit(_str(here(), 1, FACE_ORI))                # str r1,ORI
    emit(_str(here(), 2, FACE_TTL))                # str r2,TTL
    label('fdone')
    emit(0xE59802FC)                               # ldr r0,[r8,#0x2fc]
    br(0xE, 'FD_BACK')

    # ---- key routine: replaces the AE-lock call for logical key 0 ----
    label('key')
    emit(0xE92D4010)                               # push {r4, lr}
    emit(0xE5913000)                               # ldr r3,[r1]      event vtable
    emit(0xE2832010)                               # add r2,r3,#0x10
    emit(0xE592C004)                               # ldr ip,[r2,#4]
    emit(0xE1D230F0)                               # ldrsh r3,[r2]
    emit(0xE0810003)                               # add r0,r1,r3
    emit(0xE1A0E00F)                               # mov lr,pc
    emit(0xE1A0F00C)                               # mov pc,ip        "is this a press?"
    emit(0xE3500001)                               # cmp r0,#1
    br(0x1, 'kdone')                               # bne kdone
    emit(_ldr(here(), 4, STATE))                   # ldr r4,STATE
    emit(0xE2844001)                               # add r4,r4,#1
    emit(0xE3540000 | STATES)                      # cmp r4,#STATES
    emit(0xA3A04000)                               # movge r4,#0
    emit(_str(here(), 4, STATE))                   # str r4,STATE
    emit(0xE3A00000)                               # mov r0,#0
    emit(_str(here(), 0, FACE_ORI))                # str r0,FACE_ORI
    emit(_str(here(), 0, FACE_TTL))                # str r0,FACE_TTL
    emit(0xE2840000 | FIRST_TEXT)                  # add r0,r4,#FIRST_TEXT
    br(0xE, 'ARM_NAME', link=True)                 # bl arm_name
    emit(0xE2840000 | FIRST_TEXT)                  # add r0,r4,#FIRST_TEXT
    br(0xE, 'TOAST', link=True)                    # bl toast
    label('kdone')
    emit(0xE3A00000)                               # mov r0,#0
    emit(0xE8BD8010)                               # pop {r4, pc}
    emit(0)                                        # (padding)

    ext = {'WRITER_BACK': WRITER_BACK, 'FD_BACK': FD_BACK,
           'ARM_NAME': ui.ARM_NAME, 'TOAST': ui.TOAST_CODE}
    for idx, cond, name, link in fix:
        src = ROT + 4 * idx
        dst = labels[name] if name in labels else ext[name]
        out[idx] = ui._b(src, dst, cond=cond, link=link)
    blob = b''.join(struct.pack('<I', w) for w in out)
    assert ROT + len(blob) <= ROT_END, hex(ROT + len(blob))
    return blob, labels


def patch(d):
    d = bytearray(d)
    blob, lab = build()
    d[ROT - B:ROT - B + len(blob)] = blob
    for site, stock, new in (
            (WRITER_SITE, 0xE3A0E001, ui._b(WRITER_SITE, lab['writer'])),
            (FD_SITE, 0xE59802FC, ui._b(FD_SITE, lab['face'])),
            (KEY_SITE, ui._b(KEY_SITE, KEY_STOCK, link=True), ui._b(KEY_SITE, lab['key'], link=True))):
        cur = struct.unpack_from('<I', d, site - B)[0]
        assert cur in (stock, new), (hex(site), hex(cur))
        struct.pack_into('<I', d, site - B, new)
    return bytes(d)


if __name__ == '__main__':
    import capstone as cs
    blob, lab = build()
    print({k: hex(v) for k, v in lab.items()}, len(blob), 'bytes of', ROT_END - ROT)
    md = cs.Cs(cs.CS_ARCH_ARM, cs.CS_MODE_ARM)
    for k in range(3, len(blob) // 4):
        for i in md.disasm(blob[4 * k:4 * k + 4], ROT + 4 * k):
            print('%08x: %s %s' % (i.address, i.mnemonic, i.op_str))

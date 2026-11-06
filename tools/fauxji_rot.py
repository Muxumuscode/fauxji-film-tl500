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
R1, R1_END = 0xC04260A0, ui.TOAST_DATA
R2, R2_END = ui.ZOOM_HOOK + 16, ui.EXTRA_END
R3, R3_END = ui.STR_BASE + len(ui.ROT_TEXTS) * ui.STR_SLOT, ui.STRWRAP_END    # spare end of the string area
R4, R4_END = 0xC0426C50, 0xC0426EE8            # factory-only "waitEXStrobeSignal" + its only caller 0xC0426E3C
                                               # (both reached only from CProductionModeAdjustFunc, 0xC04278D4)
R5, R5_END = 0xC0426EE8, 0xC04272C0            # more of the same dead factory code: 0xC0426EE8 / 0xC0426FDC (tools/liveness.py: no
                                               # caller but 0xC0427304, inside 0xC04272C0 <- 0xC04274B8, which nothing calls)
SKY_LATCH = R5 + 8                              # 0 / 6 / 8: last live-view sky guess
ROLL_COUNT, ROLL_N = R5, R5 + 4                  # R5 data (RAM): photos taken this roll (built as 0), roll size; code follows
STATE, FACE_ORI, FACE_TTL, KEY, LAST = R1, R1 + 4, R1 + 8, R1 + 12, R1 + 16   # LAST: text index drawn by tiltdraw
assert STATE == ui.ROT_STATE and KEY == ui.ROT_KEY and R2 == ui.TILT_FORCE
KEY_DEFAULT = 9                       # the VIDEO button (found with the FAUXJI41 test build)
DIAG = False                          # True = FAUXJI41 test build: pop-up shows the number of any pressed key
# FAUXJI59: the sky guess is LATCHED from the live-view indicator (every beat, SKY_LATCH) and the EXIF writer uses the latch instead of
# reading the AE grid at write time. Owner's night shots SAM_0640-0653 (FAUXJI54): a replay of the same band rules on each photo's own
# 17 x 13 luma gets 13 of 14 right, the camera's tags only 8 of 14 (4 missed sideways shots, 1 false tag), so the grid at write time is
# not the frame that was shot, while the live indicator (same code, live frames) was verified.
SKY_COLOUR_CHECK = False               # FAUXJI57 colour check: off (the same replay shows it never rejects a correct tag, and its value is unproven)
SKY_COLOUR_CHECK_UNUSED = True                # FAUXJI57: the brighter side must also be bluer (False = FAUXJI56 behaviour)
# Film roll (FAUXJI58): the shots-left number is capped at ROLL_SIZE minus the photos taken since power-on (a new roll = switch
# the camera off and on). CUSLCommonFileManager::getRemainPhotoNum = 0xC047B3CC (WB850F 0xC0442FF0: free bytes / bytes per shot);
# every path ends at 0xC047B6B8 (`add sp,sp,#0x58`) with the count in r0: hooked. A shot is counted where the EXIF writer
# stub runs (`wcommon`, once per JPEG). 0 = film roll off (stock counter).
ROLL_SIZE = 0                          # film roll (FAUXJI58): off
ROLL_SITE, ROLL_BACK = 0xC047B6B8, 0xC047B6BC
# FAUXJI62: the name / tilt box now sits top left, where the movie timer is shown: in movie mode (AE sysmode 8) nothing is drawn there.
# Three gates in front of the box code: the tilt-indicator entries (TILT_FORCE, TILT_DRAW: hide the box with the stock draw(0)) and the
# toast (film name / tilt pop-up: return without showing). Each replaces the entry's first instruction with a branch to a gate in R5.
MOVIE_MODE = 8
MOVIE_HIDE = True
STATE_DEFAULT = 2                     # tilt tag state at power-on: 2 = Auto+ (sideways faces, else sky is up)
# Sky is up (FAUXJI53): the AE's live preview statistics, 17 x 13 cells of u16 (planes Y, R, G, B at +0, +0x1BA, +0x374,
# +0x52E; getter 0xC03EDB04 = 0xC0CFA7A8, same layout as WB850F's AeDebugDisplayYRGB), row 0 = top of the frame.
# With no sideways face, Auto+ (state 2) compares the mean Y of the two left columns, two right columns, two top rows and
# two bottom rows: a side band 1.5x the opposite side and 1.125x both the top and the bottom band is taken to be the sky,
# i.e. the top of the scene (left -> Orientation 6, right -> 8; same sense as the face tag). Auto flip is gone (the face
# direction is verified), its slot is Auto+.
YGRID = 0xC0CFA7A8
WRITER_SITE, WRITER_BACK = 0xC0385F00, 0xC0385F04
# The three EXIF writers' orientation sites (only one is live; FAUXJI44 showed 0xC0385F00 alone is not it)
W2_SITE, W2_BACK = 0xC03779DC, 0xC03779E0      # ldr lr,[sl,#0xe4]
W3_SITE, W3_BACK = 0xC0383470, 0xC0383474      # mov lr,#1
WRITERS = [('writer', 0xE3A0E001, 'WRITER_BACK'), ('writer2', 0xE59AE0E4, 'W2_BACK'), ('writer3', 0xE3A0E001, 'W3_BACK')]
FD_SITE, FD_BACK = 0xC058FA0C, 0xC058FA10
KEY_SITE, KEY_STOCK = 0xC04C1A98, 0xC04C1414
MASK_SITE, MASK_BACK, GET_SYSVAL = 0xC04CE844, 0xC04CE848, 0xC048F81C
# Highlight bias: AeSystemEVCSetToAeEVCShift (0xC03ECCF8) returns the EV compensation x16 that
# the AE adds (AeUpdateSysInfo; manual-mode ISO routine too). Subtracting AE_BIAS makes the
# camera meter that much darker in every mode while the EV comp scale still shows 0.
EV_SITE, EV_BACK = 0xC03ECD54, 0xC03ECD58
AE_BIAS = 5                           # 1/16 EV steps: 5 = -0.3 EV, 8 = -0.5 EV
DISP_SITE, DISP_STOCK = 0xC04C1944, 0xC04BFF98
# Keeping the indicator on screen. The live-view redraw (DRAW_ICONS 0xC04B7444) walks the current item
# list (pointer at 0xC09BDAD4; 11 lists at 0xC09BDAD8..0xC09BDE08) and item 44 (the help-text box we use)
# is in none of them, so a full redraw (e.g. back from a photo) never re-draws the indicator. Fix: the
# end of DRAW_ICONS (0xC04B74AC) falls into `tiltpost`, which re-draws it, and arms a 1 s heartbeat
# (control timer 31, same task as the key dispatcher) whose tick re-shows it (cached text). The VIDEO
# press now runs DRAW_ICONS like the FILM SIM button does (a swallowed key skips the dispatcher's own
# screen update).
# Flash shutter floor: AeReadPLParam (0xC0541EA0) copies the program line's flagged row (flag 0xFF; PL_Capt_Program
# row 3, Tv 96 = 1/60) to [pl+0xFA/0xFC/0xFE] and adds the zoom shift (AE sysinfo +0x12) to its Tv at 0xC0542014.
# The capture code (0xC0540294, flash modes Auto / Red-eye / Fill-in / Red-eye fix = sysinfo +0xC 0,1,2,5) then
# raises the shutter to that Tv: 1/60 -> 1/90 -> 1/125 as you zoom. Hook: no zoom shift in P, A and S.
PLZ_SITE, PLZ_STOCK, PLZ_BACK = 0xC0542014, 0xE1DBE1F2, 0xC0542018       # ldrsh lr,[fp,#0x12]
DI_SITE, DI_STOCK = 0xC04B74AC, 0xE28DD014     # `add sp,sp,#0x14` before DRAW_ICONS returns
BEAT_ID, BEAT_MS = 31, 400
DIRECT_SITES = (0xC04BA8E4, 0xC04BA904)        # GUI event 0xC calls the stock help-text draw directly: route to tiltdraw
TTL = 60
STATES = 5
FIRST_TEXT = 11                       # NAME_STRINGS index of the first tilt text
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


def build_full():
    labels = {}
    r1, r2, r3, r4, r5 = Asm(R1, R1_END), Asm(R2, R2_END), Asm(R3, R3_END), Asm(R4, R4_END), Asm(R5, R5_END)

    def label(a, n):
        labels[n] = a.here()

    # ---------------- region 1: data, writer hook, face hook, AE-L key routine -------------
    a = r1
    a.emit(STATE_DEFAULT, 0, 0, KEY_DEFAULT, 0xFFFFFFFF)   # STATE, FACE_ORI, FACE_TTL, KEY, LAST

    for wname, wstock, wback in WRITERS:           # stub at each EXIF orientation writer
        label(a, wname)
        a.emit(wstock)                             # stock: mov lr,#1  or  ldr lr,[sl,#0xe4]
        a.emit(0xE28F3000)                         # add r3,pc,#0     return address = the `b wback` below
        a.br(0xE, 'wcommon')
        a.br(0xE, wback)

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

    # ---------------- region 2: indicator, EXIF routine, cycle(), dispatcher hook ------------
    a = r2
    label(a, 'tiltforce')                          # forget the cached text, fall into tiltdraw
    a.emit(0xE3E01000)                             # mvn r1,#0
    a.str(1, LAST)
    label(a, 'tiltdraw')                           # item-44 draw (r0 = help value, kept): tilt indicator or stock
    assert a.here() == ui.TILT_DRAW
    a.emit(0xE92D4011)                             # push {r0, r4, lr}
    a.ldr(1, STATE)                                # ldr r1,STATE
    a.emit(0xE3510003, 0x03A04012)                 # cmp r1,#3 ; moveq r4,#18  (top right)
    a.br(0x0, 'tshow')
    a.emit(0xE3510004, 0x03A04013)                 # cmp r1,#4 ; moveq r4,#19  (top left)
    a.br(0x0, 'tshow')
    a.emit(0xE3510001, 0x13510002)                 # cmp r1,#1 ; cmpne r1,#2   (Auto / Auto flip only)
    a.br(0x1, 'tstock')
    a.br(0xE, 'combo', link=True)                  # r2 = face orientation, or (Auto+) the sky guess
    a.emit(0xE3A04000, 0xE3520000)                 # mov r4,#0 ; cmp r2,#0
    a.br(0x0, 'tcalc')                             # upright
    a.emit(0xE3510002, 0xE1A00000)                 # cmp r1,#2 ; nop   (Auto+ does not flip)
    a.emit(0xE3520006, 0x03A04001, 0x13A04002)     # cmp r2,#6 ; moveq r4,#1 ; movne r4,#2
    label(a, 'tcalc')
    a.emit(0xE284400C, 0xE3510002, 0x02844003)     # add r4,r4,#12 ; cmp r1,#2 ; addeq r4,r4,#3
    label(a, 'tshow')
    a.ldr(1, LAST)
    a.emit(0xE1510004)                             # cmp r1,r4
    a.br(0x0, 'tvis')                              # same text as last time: only show the nodes again
    a.str(4, LAST)
    a.emit(0xE1A00004)                             # mov r0,r4
    a.br(0xE, 'TOAST', link=True)
    a.emit(0xE8BD8011)                             # pop {r0, r4, pc}
    label(a, 'tvis')
    a.emit(0xE28DD004)                             # add sp,sp,#4      drop the saved r0: stack = {r4, lr} as the toast expects
    a.br(0xE, 'TOAST_VIS')                         # toast's node loop (shows frame, panel and text), returns to our caller
    label(a, 'tstock')
    a.emit(0xE8BD4011)                             # pop {r0, r4, lr}
    a.br(0xE, 'ITEM44_DRAW')

    a = r3
    label(a, 'wcommon')                            # lr = orientation (stock); r3 = return address
    a.emit(0xE92D0001)                             # push {r0}
    a.ldr(12, ROLL_COUNT)                          # one more frame on the roll
    a.emit(0xE28CC001)                             # add ip,ip,#1
    a.str(12, ROLL_COUNT)
    a.ldr(12, STATE)                               # ldr ip,STATE
    a.emit(0xE35C0003, 0x03A0E006)                 # cmp ip,#3 ; moveq lr,#6
    a.br(0x0, 'wcdone')
    a.emit(0xE35C0004, 0x03A0E008)                 # cmp ip,#4 ; moveq lr,#8
    a.br(0x0, 'wcdone')
    a.emit(0xE35C0002)                             # cmp ip,#2
    a.br(0x8, 'wcdone')                            # bhi done
    a.emit(0xE35C0000)                             # cmp ip,#0
    a.br(0x0, 'wcdone')                            # beq done   (off)
    a.br(0xE, 'wauto')                             # Auto / Auto+: face, else (Auto+) sky; returns to wcdone
    a.emit(0xE3500000)                             # (not reached)
    a.br(0x0, 'wcdone')                            # no sideways face seen
    a.emit(0xE35C0002, 0x0260000E)                 # cmp ip,#2 ; rsbeq r0,r0,#14   (6 <-> 8)
    a.emit(0xE1A0E000)                             # mov lr,r0
    label(a, 'wcdone')
    a.emit(0xE8BD0001, 0xE1A0F003)                 # pop {r0} ; mov pc,r3

    a = r2
    label(a, 'cycle')                              # state++ (mod 5), clear the face tag, update the indicator
    a.emit(0xE92D4010)                             # push {r4, lr}
    a.ldr(4, STATE)
    a.emit(0xE2844001, 0xE3540000 | STATES, 0xA3A04000)   # add r4,r4,#1 ; cmp ; movge r4,#0
    a.str(4, STATE)
    a.emit(0xE3A00000)                             # mov r0,#0
    a.str(0, FACE_ORI)
    a.str(0, FACE_TTL)
    a.emit(0xE3540000)                             # cmp r4,#0
    a.br(0x1, 'cpersist')
    a.emit(0xE3A00000 | FIRST_TEXT)                # off: "Tilt: Off" for 2 s
    a.br(0xE, 'ARM_NAME', link=True)
    a.br(0xE, 'DRAW_ICONS', link=True)
    a.emit(0xE3A00000 | FIRST_TEXT)
    a.br(0xE, 'TOAST', link=True)
    a.emit(0xE8BD8010)                             # pop {r4, pc}
    label(a, 'cpersist')
    a.emit(0xE3A00000)                             # mov r0,#0
    a.br(0xE, 'DRAW_ICONS', link=True)             # full redraw; its end (tiltpost) re-draws the indicator
    a.emit(0xE8BD8010)                             # pop {r4, pc}

    label(a, 'disp')                               # replaces `bl 0xC04BFF98` (r0 = state, r1 = key)
    a.emit(0xE92D4013)                             # push {r0, r1, r4, lr}
    a.emit(0xE59A3000, 0xE2832010, 0xE592C004, 0xE1D230F0,   # same press check, event = sl
           0xE08A0003, 0xE1A0E00F, 0xE1A0F00C)
    a.emit(0xE1A04000)                             # mov r4,r0         1 = press, 0 = release
    a.emit(0xE59D1004)                             # ldr r1,[sp,#4]    key
    a.ldr(3, KEY)
    a.emit(0xE1510003)                             # cmp r1,r3
    a.br(0x1, 'pass')
    a.emit(0xE3540001)                             # cmp r4,#1
    a.br(0x1, 'swallow')
    a.br(0xE, 'cycle', link=True)
    label(a, 'swallow')
    a.emit(0xE8BD4013, 0xE3A00000, 0xE1A0F00E)     # pop {r0,r1,r4,lr} ; mov r0,#0 ; mov pc,lr
    label(a, 'pass')
    a.emit(0xE8BD4013)
    a.br(0xE, 'DISP_STOCK')

    # ---------------- region 4: redraw hook and heartbeat ----------------------------------------
    a = r4
    label(a, 'dihook')                             # replaces `add sp,sp,#0x14` at the end of DRAW_ICONS
    a.emit(0xE28DD014, 0xE8BD4C00)                 # add sp,sp,#0x14 ; pop {sl, fp, lr}
    label(a, 'tiltpost')                           # after a full redraw: arm the heartbeat, re-draw the indicator
    a.emit(0xE92D4010)                             # push {r4, lr}
    a.br(0xE, 'tarm', link=True)
    a.br(0xE, 'tok', link=True)
    a.br(0x1, 'tpout')                             # bne: nothing to draw
    a.br(0xE, 'tiltforce', link=True)              # set the text again (the screen was rebuilt)
    label(a, 'tpout')
    a.emit(0xE8BD8010)                             # pop {r4, pc}

    label(a, 'hbhook')                             # replaces `bl TIMERHOOK` in the live-view timer handler
    a.emit(0xE92D4013)                             # push {r0, r1, r4, lr}
    a.emit(0xE5913000, 0xE2832008, 0xE592C004, 0xE1D230F0,   # timer id (same call as TIMERHOOK)
           0xE0810003, 0xE1A0E00F, 0xE1A0F00C)
    a.emit(0xE3500000 | BEAT_ID)                   # cmp r0,#31
    a.emit(0x18BD4013)                             # popne {r0, r1, r4, lr}
    a.br(0x1, 'TIMERHOOK')                         # bne: not ours
    a.br(0xE, 'tarm', link=True)                   # next tick
    a.br(0xE, 'tok', link=True)
    a.br(0x1, 'hbout')
    a.br(0xE, 'tiltdraw', link=True)               # cached: re-shows the nodes, new text only if it changed
    label(a, 'hbout')
    a.emit(0xE8BD8013)                             # pop {r0, r1, r4, pc}

    label(a, 'tarm')                               # (re)start timer 31: 1 s, posts a timer event to the control app
    a.emit(0xE92D4010)                             # push {r4, lr}
    a.emit(0xE3A00000 | BEAT_ID, 0xE3A01FFA)       # mov r0,#31 ; mov r1,#1000
    a.ldr(2, 0)                                    # ldr r2,=TIMER_POST   (fixed below)
    beat_lit = len(a.w) - 1
    a.emit(0xE3A03000 | BEAT_ID)                   # mov r3,#31
    a.br(0xE, 'TIMER_START', link=True)
    a.emit(0xE8BD8010)                             # pop {r4, pc}

    label(a, 'plzoom')                             # replaces `ldrsh lr,[fp,#0x12]` (fp = AE sysinfo)
    a.emit(0xE1DBE0FA, 0xE35E0003)                 # ldrsh lr,[fp,#0xa] (AE mode) ; cmp lr,#3   (S)
    a.br(0x0, 'plnone')
    a.emit(0xE3DEE002)                             # bics lr,lr,#2   (P = 0, A = 2)
    a.br(0x0, 'plnone')
    a.emit(0xE1DBE1F2)                             # ldrsh lr,[fp,#0x12]   (stock: zoom shift)
    a.br(0xE, 'PLZ_BACK')
    label(a, 'plnone')
    a.emit(0xE3A0E000)                             # mov lr,#0
    a.br(0xE, 'PLZ_BACK')

    label(a, 'combo')                              # r1 = state -> r2 = orientation; keeps r1, r3, r4
    a.emit(0xE92D400A)                             # push {r1, r3, lr}
    a.ldr(2, FACE_ORI)
    a.emit(0xE3520000)                             # cmp r2,#0
    a.br(0x1, 'cbdone')                            # a sideways face wins
    a.emit(0xE3510002)                             # cmp r1,#2
    a.br(0x1, 'cbdone')                            # plain Auto: faces only
    a.br(0xE, 'skyori', link=True)
    a.str(0, SKY_LATCH)                            # remember the live guess for the EXIF writer
    a.emit(0xE1A02000)                             # mov r2,r0
    label(a, 'cbdone')
    a.emit(0xE8BD800A)                             # pop {r1, r3, pc}

    label(a, 'wauto')                              # EXIF: ip = state (1/2), lr = stock value, r3 = return, r0 saved
    a.emit(0xE92D500E)                             # push {r1, r2, r3, ip, lr}
    a.ldr(0, FACE_ORI)
    a.emit(0xE3500000)                             # cmp r0,#0
    a.br(0x1, 'waset')
    a.emit(0xE35C0002)                             # cmp ip,#2
    a.br(0x1, 'wakeep')
    a.ldr(0, SKY_LATCH)                            # FAUXJI59: the live-view guess, not the AE grid after the shot
    a.emit(0xE3500000)                             # cmp r0,#0
    a.br(0x0, 'wakeep')
    label(a, 'waset')
    a.emit(0xE8BD500E, 0xE1A0E000)                 # pop {r1, r2, r3, ip, lr} ; mov lr,r0
    a.br(0xE, 'wcdone')
    label(a, 'wakeep')
    a.emit(0xE8BD500E)                             # pop {r1, r2, r3, ip, lr}
    a.br(0xE, 'wcdone')

    label(a, 'skyori')                             # -> r0 = 0, 6 (sky on the left) or 8 (sky on the right)
    a.emit(0xE92D41F0)                             # push {r4-r8, lr}
    a.ldr(0, 0)                                    # ldr r0,=YGRID   (literal fixed below)
    sky_lit = len(a.w) - 1
    a.emit(0xE3A01000, 0xE3A02000, 0xE3A03000)     # r1 left, r2 right, r3 top = 0
    a.emit(0xE3A04000, 0xE3A05000)                 # r4 bottom = 0 ; r5 row = 0
    label(a, 'skrow')
    a.emit(0xE1D060B0, 0xE1D0C0B2, 0xE086600C)     # ldrh r6,[r0] ; ldrh ip,[r0,#2] ; add r6,r6,ip
    a.emit(0xE0811006)                             # add r1,r1,r6        left  += cells 0, 1
    a.emit(0xE1D061BE, 0xE1D0C2B0, 0xE086600C)     # ldrh r6,[r0,#30] ; ldrh ip,[r0,#32] ; add r6,r6,ip
    a.emit(0xE0822006)                             # add r2,r2,r6        right += cells 15, 16
    a.emit(0xE3550001)                             # cmp r5,#1
    a.br(0x9, 'skdo')                              # bls: top rows 0, 1
    a.emit(0xE355000B)                             # cmp r5,#11
    a.br(0x3, 'sknext')                            # blo: middle rows
    label(a, 'skdo')
    a.emit(0xE3A07000, 0xE3A08000)                 # mov r7,#0 ; mov r8,#0
    label(a, 'skcell')
    a.emit(0xE1A0C088, 0xE19060BC, 0xE0877006)     # mov ip,r8,lsl #1 ; ldrh r6,[r0,ip] ; add r7,r7,r6
    a.emit(0xE2888001, 0xE3580011)                 # add r8,r8,#1 ; cmp r8,#17
    a.br(0xB, 'skcell')                            # blt
    a.emit(0xE3550001, 0x90833007, 0x80844007)     # cmp r5,#1 ; addls r3,r3,r7 ; addhi r4,r4,r7
    label(a, 'sknext')
    a.emit(0xE2800022, 0xE2855001, 0xE355000D)     # add r0,r0,#34 ; add r5,r5,#1 ; cmp r5,#13
    a.br(0xB, 'skrow')                             # blt
    # equal weights: side bands (26 cells) x17, top/bottom bands (34 cells) x13
    a.emit(0xE0811201, 0xE0822202)                 # add r1,r1,r1,lsl #4 ; add r2,r2,r2,lsl #4
    a.emit(0xE083C103, 0xE08C3183)                 # add ip,r3,r3,lsl #2 ; add r3,ip,r3,lsl #3
    a.emit(0xE084C104, 0xE08C4184)                 # add ip,r4,r4,lsl #2 ; add r4,ip,r4,lsl #3
    a.emit(0xE3A00000)                             # mov r0,#0
    for side, other, tag in ((1, 2, 6), (2, 1, 8)):
        nxt = 'sk%d' % tag
        a.emit(0xE1A05080 | side)                  # mov r5,rS,lsl #1         2 x side
        a.emit(0xE0806080 | (other << 16) | other) # add r6,rO,rO,lsl #1      3 x other side
        a.emit(0xE1550006)                         # cmp r5,r6
        a.br(0xD, nxt)                             # ble
        a.emit(0xE1A05180 | side)                  # mov r5,rS,lsl #3         8 x side
        a.emit(0xE0836183, 0xE1550006)             # add r6,r3,r3,lsl #3 (9 x top) ; cmp r5,r6
        a.br(0xD, nxt)
        a.emit(0xE0846184, 0xE1550006)             # add r6,r4,r4,lsl #3 (9 x bottom) ; cmp r5,r6
        a.br(0xD, nxt)
        a.emit(0xE3A00000 | tag)                   # mov r0,#tag
        a.br(0xE, 'skdone')
        label(a, nxt)
    label(a, 'skdone')
    if SKY_COLOUR_CHECK:
        a.emit(0xE3500000)                         # cmp r0,#0
        a.br(0x1, 'skycol', link=True)             # blne: colour check of the sky guess (r0 = tag in, tag or 0 out)
    a.emit(0xE8BD81F0)                             # pop {r4-r8, pc}

    label(a, 'tok')                                # Z set = draw: no film name showing and state 1-4
    a.ldr(1, ui.NAME_FLAG)
    a.emit(0xE3510000, 0x11A0F00E)                 # cmp r1,#0 ; movne pc,lr  (Z clear)
    a.ldr(1, STATE)
    a.emit(0xE2411001, 0xE3510003)                 # sub r1,r1,#1 ; cmp r1,#3
    a.emit(0x93A01000, 0x83A01001, 0xE3510000)     # movls r1,#0 ; movhi r1,#1 ; cmp r1,#0
    a.emit(0xE1A0F00E)                             # mov pc,lr
    pool = a.here()
    a.emit(ui.TIMER_POST, YGRID)
    a.w[beat_lit] = ui._ldr_pc(R4 + 4 * beat_lit, 2, pool)
    a.w[sky_lit] = ui._ldr_pc(R4 + 4 * sky_lit, 0, pool + 4)

    # FAUXJI57: colour check of the sky guess. The brighter side band is only the sky if it is also bluer than the opposite
    # band: (B/R of the sky side) >= SKY_BLUE (9/8) x (B/R of the opposite side), from the AE grid's R and B planes
    # (+0x1BA, +0x52E; same 2 side columns x 13 rows as the brightness test). A lamp or a bright wall (neutral / warm)
    # fails, a window onto the sky may still pass. Fail = no tag (r0 = 0), the stock Orientation 1.
    a = r5
    a.emit(0, ROLL_SIZE, 0)                        # ROLL_COUNT, ROLL_N, SKY_LATCH

    def movie_check():                             # sets the flags: Z = movie mode; keeps r0-r3 and lr
        a.emit(0xE92D400F, 0xE3A00003)             # push {r0-r3, lr} ; mov r0,#3  (shooting mode)
        a.br(0xE, 'GET_SYSVAL', link=True)
        a.emit(0xE1A0C000, 0xE8BD400F)             # mov ip,r0 ; pop {r0-r3, lr}
        a.emit(0xE35C0000 | MOVIE_MODE)            # cmp ip,#8

    label(a, 'gate1')                              # entry of tiltforce (first word was `mvn r1,#0`)
    movie_check()
    a.br(0x1, 'g1ok')                              # bne
    a.emit(0xE3A00000)                             # mov r0,#0
    a.br(0xE, 'ITEM44_DRAW')                       # stock draw(0): hide the box, return to the caller
    label(a, 'g1ok')
    a.emit(0xE3E01000)                             # mvn r1,#0   (the replaced word)
    a.br(0xE, 'TILTFORCE4')
    label(a, 'gate2')                              # entry of tiltdraw (first word was `push {r0, r4, lr}`)
    movie_check()
    a.br(0x1, 'g2ok')
    a.emit(0xE3A00000)
    a.br(0xE, 'ITEM44_DRAW')
    label(a, 'g2ok')
    a.emit(0xE92D4011)                             # push {r0, r4, lr}   (the replaced word)
    a.br(0xE, 'TILTDRAW4')
    label(a, 'gate3')                              # entry of the toast (first word was `push {r4, lr}`)
    movie_check()
    a.br(0x1, 'g3ok')
    a.emit(0xE1A0F00E)                             # mov pc,lr: no pop-up in movie mode
    label(a, 'g3ok')
    a.emit(0xE92D4010)                             # push {r4, lr}   (the replaced word)
    a.br(0xE, 'TOAST4')
    label(a, 'skycol')                             # r0 = 6 (sky left) or 8 (sky right) -> r0 = same or 0
    a.emit(0xE92D43FE)                             # push {r1-r9, lr}
    a.emit(0xE1A09000, 0xE3500006)                 # mov r9,r0 ; cmp r0,#6
    a.emit(0x03A06000, 0x03A0701E)                 # moveq r6,#0 ; moveq r7,#30   (chosen / opposite column offset, bytes)
    a.emit(0x13A0601E, 0x13A07000)                 # movne r6,#30 ; movne r7,#0
    a.ldr(0, 0)                                    # ldr r0,=YGRID (literal fixed below)
    col_lit = len(a.w) - 1
    a.emit(0xE3A01000, 0xE3A02000, 0xE3A03000)     # r1 = R chosen, r2 = B chosen, r3 = R opposite
    a.emit(0xE3A04000, 0xE3A05000)                 # r4 = B opposite ; r5 = row
    label(a, 'scrow')
    for off_reg, r_acc, b_acc in ((6, 1, 2), (7, 3, 4)):
        a.emit(0xE080C000 | off_reg)               # add ip,r0,rOFF            (row start + column offset)
        a.emit(0xE28CCC01, 0xE28CC0BA)             # add ip,ip,#0x100 ; add ip,ip,#0xBA     -> R plane (+0x1BA)
        a.emit(0xE1DC80B0, 0xE0800008 | (r_acc << 16) | (r_acc << 12))      # ldrh r8,[ip] ; add rR,rR,r8
        a.emit(0xE1DC80B2, 0xE0800008 | (r_acc << 16) | (r_acc << 12))      # ldrh r8,[ip,#2] ; add rR,rR,r8
        a.emit(0xE28CCC03, 0xE28CC074)             # add ip,ip,#0x300 ; add ip,ip,#0x74     -> B plane (+0x52E)
        a.emit(0xE1DC80B0, 0xE0800008 | (b_acc << 16) | (b_acc << 12))      # ldrh r8,[ip] ; add rB,rB,r8
        a.emit(0xE1DC80B2, 0xE0800008 | (b_acc << 16) | (b_acc << 12))      # ldrh r8,[ip,#2] ; add rB,rB,r8
    a.emit(0xE2800022, 0xE2855001, 0xE355000D)     # add r0,r0,#34 ; add r5,r5,#1 ; cmp r5,#13
    a.br(0xB, 'scrow')                             # blt
    a.emit(0xE1A02182, 0xE0844184)                 # mov r2,r2,lsl #3 (8 x B chosen) ; add r4,r4,r4,lsl #3 (9 x B opposite)
    a.emit(0xE0865392, 0xE0887194)                 # umull r5,r6,r2,r3 ; umull r7,r8,r4,r1    8 Bc Ro  vs  9 Bo Rc
    a.emit(0xE1560008, 0x01550007)                 # cmp r6,r8 ; cmpeq r5,r7
    a.emit(0x33A09000)                             # movlo r9,#0               less blue than the opposite side: no tag
    a.emit(0xE1A00009, 0xE8BD83FE)                 # mov r0,r9 ; pop {r1-r9, pc}
    a.emit(YGRID)
    a.w[col_lit] = ui._ldr_pc(R5 + 4 * col_lit, 0, a.here() - 4)

    a = r5
    label(a, 'rollclamp')                          # replaces `add sp,sp,#0x58` at the end of getRemainPhotoNum; r0 = shots left
    a.ldr(12, ROLL_N)
    a.emit(0xE35C0000)                             # cmp ip,#0
    a.br(0x0, 'rcdone')                            # beq: film roll off
    a.ldr(1, ROLL_COUNT)
    a.emit(0xE05CC001, 0xB3A0C000)                 # subs ip,ip,r1 ; movlt ip,#0      frames left on the roll
    a.emit(0xE150000C, 0x81A0000C)                 # cmp r0,ip ; movhi r0,ip          min(card, roll)
    label(a, 'rcdone')
    a.emit(0xE28DD058)                             # add sp,sp,#0x58   (stock)
    a.br(0xE, 'ROLL_BACK')

    ext = {'TILTFORCE4': ui.TILT_FORCE + 4, 'TILTDRAW4': ui.TILT_DRAW + 4, 'TOAST4': ui.TOAST_CODE + 4, 'ROLL_BACK': ROLL_BACK, 'PLZ_BACK': PLZ_BACK, 'TIMERHOOK': ui.TIMERHOOK, 'TIMER_START': ui.TIMER_START, 'WRITER_BACK': WRITER_BACK, 'W2_BACK': W2_BACK, 'W3_BACK': W3_BACK, 'FD_BACK': FD_BACK, 'ARM_NAME': ui.ARM_NAME,
           'TOAST': ui.TOAST_CODE, 'DRAW_ICONS': ui.DRAW_ICONS, 'ITEM44_DRAW': ui.ITEM44_DRAW, 'TOAST_VIS': ui.TOAST_CODE + 4 * 20, 'TILT_DRAW': ui.TILT_DRAW, 'DISP_STOCK': DISP_STOCK,
           'GET_SYSVAL': GET_SYSVAL, 'EV_BACK': EV_BACK, 'MASK_BACK': MASK_BACK}
    blobs = []
    for a in (r1, r2, r3, r4, r5):
        for idx, cond, name, link in a.fix:
            dst = labels[name] if name in labels else ext[name]
            a.w[idx] = ui._b(a.base + 4 * idx, dst, cond=cond, link=link)
        blob = b''.join(struct.pack('<I', w) for w in a.w)
        assert a.base + len(blob) <= a.end, (hex(a.base), hex(a.base + len(blob)))
        blobs.append((a.base, blob))
    return blobs, labels


TILT = ui.TILT_ENABLED


def build():
    return build_full() if TILT else build_lite()


def build_lite():
    """FAUXJI63: no tilt tag. Only the hooks that stay: EV bias, menu unlock, flash shutter floor, and the movie gate
    in front of the film-name toast. The tilt data block (STATE, KEY...) is kept at R1 because the key hook in
    fauxji_ui reads ROT_KEY (0xFF = no key)."""
    labels = {}
    r1, r4, r5 = Asm(R1, R1_END), Asm(R4, R4_END), Asm(R5, R5_END)

    def label(a, n):
        labels[n] = a.here()

    a = r1
    a.emit(0, 0, 0, 0xFF, 0xFFFFFFFF)              # STATE, FACE_ORI, FACE_TTL, KEY (none), LAST: unused

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

    a = r4
    label(a, 'plzoom')                             # replaces `ldrsh lr,[fp,#0x12]` (fp = AE sysinfo)
    a.emit(0xE1DBE0FA, 0xE35E0003)                 # ldrsh lr,[fp,#0xa] (AE mode) ; cmp lr,#3   (S)
    a.br(0x0, 'plnone')
    a.emit(0xE3DEE002)                             # bics lr,lr,#2   (P = 0, A = 2)
    a.br(0x0, 'plnone')
    a.emit(0xE1DBE1F2)                             # ldrsh lr,[fp,#0x12]   (stock: zoom shift)
    a.br(0xE, 'PLZ_BACK')
    label(a, 'plnone')
    a.emit(0xE3A0E000)                             # mov lr,#0
    a.br(0xE, 'PLZ_BACK')

    a = r5
    label(a, 'gate3')                              # entry of the toast (first word was `push {r4, lr}`)
    a.emit(0xE92D400F, 0xE3A00003)                 # push {r0-r3, lr} ; mov r0,#3  (shooting mode)
    a.br(0xE, 'GET_SYSVAL', link=True)
    a.emit(0xE1A0C000, 0xE8BD400F)                 # mov ip,r0 ; pop {r0-r3, lr}
    a.emit(0xE35C0000 | MOVIE_MODE)                # cmp ip,#8
    a.br(0x1, 'g3ok')                              # bne
    a.emit(0xE1A0F00E)                             # mov pc,lr: no pop-up in movie mode
    label(a, 'g3ok')
    a.emit(0xE92D4010)                             # push {r4, lr}   (the replaced word)
    a.br(0xE, 'TOAST4')

    ext = {'TOAST4': ui.TOAST_CODE + 4, 'PLZ_BACK': PLZ_BACK, 'GET_SYSVAL': GET_SYSVAL, 'EV_BACK': EV_BACK,
           'MASK_BACK': MASK_BACK}
    blobs = []
    for a in (r1, r4, r5):
        for idx, cond, name, link in a.fix:
            dst = labels[name] if name in labels else ext[name]
            a.w[idx] = ui._b(a.base + 4 * idx, dst, cond=cond, link=link)
        blob = b''.join(struct.pack('<I', w) for w in a.w)
        assert a.base + len(blob) <= a.end, (hex(a.base), hex(a.base + len(blob)))
        blobs.append((a.base, blob))
    return blobs, labels



def _put(d, site, stock, new):
    cur = struct.unpack_from('<I', d, site - B)[0]
    assert cur in (stock, new), (hex(site), hex(cur))
    struct.pack_into('<I', d, site - B, new)


def patch(d):
    d = bytearray(d)
    blobs, lab = build()
    for base, blob in blobs:
        d[base - B:base - B + len(blob)] = blob
    _put(d, EV_SITE, 0xE1A0080B, ui._b(EV_SITE, lab['evbias']))
    _put(d, MASK_SITE, 0xE1A0A001, ui._b(MASK_SITE, lab['unlock']))
    _put(d, PLZ_SITE, PLZ_STOCK, ui._b(PLZ_SITE, lab['plzoom']))
    if MOVIE_HIDE:
        _put(d, ui.TOAST_CODE, 0xE92D4010, ui._b(ui.TOAST_CODE, lab['gate3']))
    if not TILT:
        # every tilt-tag hook is back to Samsung's code; film-name box draws go through the box wrapper
        for site, stock in ((WRITER_SITE, 0xE3A0E001), (W2_SITE, 0xE59AE0E4), (W3_SITE, 0xE3A0E001), (FD_SITE, 0xE59802FC),
                            (KEY_SITE, ui._b(KEY_SITE, KEY_STOCK, link=True)),
                            (DISP_SITE, ui._b(DISP_SITE, DISP_STOCK, link=True)), (DI_SITE, DI_STOCK),
                            (ui.TIMER_CALL[0], ui._b(ui.TIMER_CALL[0], ui.TIMERHOOK, link=True))):
            _put(d, site, stock, stock)
        for site in DIRECT_SITES:                  # GUI event 0xC draws the box directly: let it show the film name too
            _put(d, site, ui._b(site, ui.ITEM44_DRAW, link=True), ui._b(site, ui.WRAP44, link=True))
        return bytes(d)
    for site, stock, new in (
            (WRITER_SITE, 0xE3A0E001, ui._b(WRITER_SITE, lab['writer'])),
            (W2_SITE, 0xE59AE0E4, ui._b(W2_SITE, lab['writer2'])),
            (W3_SITE, 0xE3A0E001, ui._b(W3_SITE, lab['writer3'])),
            (FD_SITE, 0xE59802FC, ui._b(FD_SITE, lab['face'])),
            (KEY_SITE, ui._b(KEY_SITE, KEY_STOCK, link=True), ui._b(KEY_SITE, lab['key0'], link=True)),
            (DISP_SITE, ui._b(DISP_SITE, DISP_STOCK, link=True), ui._b(DISP_SITE, lab['disp'], link=True)),
            (ROLL_SITE, 0xE28DD058, ui._b(ROLL_SITE, lab['rollclamp'])) if ROLL_SIZE else (ROLL_SITE, 0xE28DD058, 0xE28DD058),
            (DI_SITE, DI_STOCK, ui._b(DI_SITE, lab['dihook'])),
            (ui.TIMER_CALL[0], ui._b(ui.TIMER_CALL[0], ui.TIMERHOOK, link=True), ui._b(ui.TIMER_CALL[0], lab['hbhook'], link=True))):
        _put(d, site, stock, new)
    if MOVIE_HIDE:
        for site, stock, gate in ((ui.TILT_FORCE, 0xE3E01000, 'gate1'), (ui.TILT_DRAW, 0xE92D4011, 'gate2')):
            _put(d, site, stock, ui._b(site, lab[gate]))
    for site in DIRECT_SITES:
        _put(d, site, ui._b(site, ui.ITEM44_DRAW, link=True), ui._b(site, ui.TILT_DRAW, link=True))
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

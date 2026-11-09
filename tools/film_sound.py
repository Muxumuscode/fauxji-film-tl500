"""The wind-on ratchet for the film build (build_fauxji.py --film): film_mode's `filmdial` calls RATCHET when the front dial winds the film on.

How the camera plays its own sounds (static, stock 008264; corrected in TL-F65t after the owner heard nothing from TL-F65r):
  * 0xC0476F3C(type) is the player the camera calls for its effect sounds (38 callers, many in the control app's UI code, e.g. 0xC04CD298,
    0xC04DDD78). It (1) reads the sound VOLUME setting *0xC09B5380 (0 = Off .. 3): Off stops any sound (0xC01BBB60(0)) and returns,
    (2) applies that level with 0xC01BC6B8(level) (it writes the mixer globals 0xC08B56DC.. and returns 0; 0x80000000 for a level of 4 or
    more, then the player gives up), (3) picks an output value `sb` from two audio-route bytes: 0 unless *0xC09B5018 (0xC0471258) is set,
    then from *0xC09B501C (0xC047127C, 0..5, set by the mode code at 0xC041C50C / 0xC0482260): 4 and 5 give 2, 0..3 give 1 if
    0xC043A494(0xC043A1B4()) == 2 else 2, other values 0; it plays whatever `sb` is, and (4) plays a [u32 length][PCM] block with
    0xC01BCA50(block, sb, stereo = 0, 0, [sp] = sample rate) (the shutters: 0x7D00 = 32 kHz; [sp+4] is not read).
    TL-F65r misread (1) as a pointer to a sound object and (2) as "a sound is playing", and returned when *0xC09B5018 was 0: in shooting
    mode it is, so the ratchet never played. RATCHET now follows the player step by step.
  * The factory sound test (CAPPFactoryInitMenuState, handler 0xC0512610 -> 0xC0512070) calls the same players straight from the control app's
    message handler, the task our key and dial hooks run in; 0xC01BCA50 hands the sound to the camera's sound task (BeepQueue / PlaySoundTask
    in CBIMMSound.cpp), so the call returns at once.
RATCHET plays the ratchet block exactly as the player plays a shutter sound: silent when the volume setting is Off.

The block ([u32 length][16-bit mono PCM, 32 kHz], tools/sounds.ratchet, 12.8 KB) sits in the unused end of the program's built-in Shutter 3
slot (0xC097CE4C, 64474 bytes; FAUXJI's shutter fills only the first 8 KB, tools/sounds.patch_elf). The code sits in fauxji_rot's R1 after its
small data block (dead factory code: 0xC04260A0 and its neighbours; up to 0xC04261C4, where the next factory function starts).
Not confirmed on a camera yet. Tests: python tools/test_film.py (section 13).
"""
import struct

import fauxji_ui as ui
import sounds
from diag_probe import Asm, R0, R1, R2, R3, R4, EQ, NE, HS, AL, mov_i, cmp_i, push, pop, str_, sub_i, add_i
import diag_probe as P

B = ui.B
SND_LEVEL = 0xC09B5380                   # the sound volume setting: 0 = Off .. 3
SET_LEVEL = 0xC01BC6B8                   # (level) -> 0 when applied, 0x80000000 for a level of 4 or more
SND_ON = 0xC0471258                      # () -> audio-route flag (low byte); 0: output value 0
SND_VOL = 0xC047127C                     # () -> audio route 0..5
DEV_GET, DEV_KIND = 0xC043A1B4, 0xC043A494
PLAY_BLOCK = 0xC01BCA50                  # (block, output value, stereo, 0, [sp] rate); the player also stores 0x46 at [sp+4]
RATE, GAIN = 0x7D00, 0x46

SLOT = sounds.ELF_SHUTTER3               # [u32 length][PCM] of the FAUXJI shutter, 64474 bytes of room after the length
BLOCK_AT = (SLOT + 4 + 0x2000 + 15) & ~15      # after the first 8 KB (the shutter), 16-byte aligned
SLOT_END = SLOT + 4 + sounds.ELF_SHUTTER3_SIZE
CODE_AT, CODE_END = 0xC04260F4, 0xC0426190      # then film_mode.TEXT_FULL_AT (48 bytes) up to 0xC04261C4
RATCHET = CODE_AT


def block():
    pcm = sounds.pcm(sounds.ratchet())
    return struct.pack('<I', len(pcm)) + pcm


def code():
    """RATCHET: play the wind-on sound the way the camera plays a shutter sound (silent with the volume Off). Clobbers r0-r3, ip (r4, lr
    saved)."""
    a = Asm(CODE_AT)
    a.w(push(0x4010), sub_i(13, 13, 8))                  # push {r4, lr}; stack argument space
    a.lit(R0, SND_LEVEL)
    a.w(P.ldr(R0, R0, 0), cmp_i(R0, 0))
    a.b(EQ, 'out')                                       # volume Off: silent
    a.b(AL, SET_LEVEL, link=True)                        # apply the level, as the player does
    a.w(cmp_i(R0, 0))
    a.b(NE, 'out')                                       # a level the mixer refuses
    a.w(mov_i(R4, 0))                                    # output value: 0 unless the route says otherwise
    a.b(AL, SND_ON, link=True)
    a.w(P.dp_i(P.AND, R0, R0, 0xFF), cmp_i(R0, 0))
    a.b(EQ, 'play')
    a.b(AL, SND_VOL, link=True)
    a.w(cmp_i(R0, 6))
    a.b(HS, 'play')                                      # an unknown route: 0
    a.w(mov_i(R4, 2), cmp_i(R0, 4))
    a.b(HS, 'play')                                      # routes 4, 5: 2
    a.b(AL, DEV_GET, link=True)
    a.b(AL, DEV_KIND, link=True)
    a.w(cmp_i(R0, 2), mov_i(R4, 1, EQ))                  # routes 0..3: 1 on output kind 2, else 2
    a.label('play')
    a.lit(R0, RATE)
    a.w(str_(R0, 13, 0), mov_i(R0, GAIN), str_(R0, 13, 4))
    a.lit(R0, BLOCK_AT)
    a.w(P.mov_r(R1, R4), mov_i(R2, 0), mov_i(R3, 0))
    a.b(AL, PLAY_BLOCK, link=True)
    a.label('out')
    a.w(add_i(13, 13, 8), pop(0x8010))                   # pop {r4, pc}
    out = a.build()
    assert CODE_AT + len(out) <= CODE_END, hex(CODE_AT + len(out))
    return out, a.labels


def patch(d):
    """Apply to a film-build .elf (after sounds.patch_elf has written the shutter into the slot)."""
    d = bytearray(d)
    shutter = struct.unpack_from('<I', d, SLOT - B)[0]
    blk = block()
    assert SLOT + 4 + shutter <= BLOCK_AT and BLOCK_AT + len(blk) <= SLOT_END, (shutter, len(blk))
    assert BLOCK_AT + len(blk) <= 0xC098C094                  # stays clear of the one word in the program that points into this slot
    d[BLOCK_AT - B:BLOCK_AT - B + len(blk)] = blk
    c, _ = code()
    d[CODE_AT - B:CODE_AT - B + len(c)] = c
    return bytes(d)

# FAUXJI FILM PRO: feature list, easiest to hardest

A ranked plan of modern features for the Samsung TL500 (EX1), plus a **resume guide**
so a fresh session can pick up without the old chat. Everything here builds on what
the camera already has inside (found in its menu texts, layout tree and code).

Effort: **XS** under a session, **S** one session, **M** a few, **L** many.
Risk: how likely the camera fights us (unknown code paths, timing, crashes).

---

## Resume guide (read this first in a new session)

**Project:** Fuji-style firmware mod for the Samsung TL500 (EX1), firmware 008264.
Maintainer notes: explain things in plain language; never redistribute Samsung firmware (share only tools and
patches); the person who owns the camera does the flashing.

**Repo:** github.com/Muxumuscode/fauxji-film-tl500. Full log of findings:
`docs/RESEARCH-LOG.md` (long, chronological). Ideas summary: `ROADMAP.md`. This file: the plan.

**Build:** `python tools/build_fauxji.py extracted/tl500_008264 extracted/tl500_008264_FAUXJIxx`
(needs the owner's stock 008264 files in `extracted/tl500_008264/`, not in git). Then set
the version label (8 bytes at .elf file offset 0x792493, e.g. `TL-F36\0\0`) and copy the
five files (EX1-DSP-SR-008264.elf, SPID.Rom, ONBL1.bin, ONBL2.bin, FWUP) to the SD card
root (for example `E:` on Windows). Commit and push after each build.

**Where things are:**
- `tools/fauxji.py`: colour looks (matrices, tone curves, per-hue PCSE), exposure fixes.
- `tools/fauxji_ui.py`: FILM SIM button, name pop-up + 2 s timer, key hook, zoom-shift fix.
  Free code space used: 0xC0425FA0-0xC04260A0, 0xC0426810-0xC042689C,
  0xC042620C-0xC0426438 (factory-only functions; check what is left before adding).
- `tools/fauxji_layout.py`: layout-tree edits (node positions, text colours).
- `tools/fuji_menu.py`, `tools/fuji_lv.py`: menu and shooting-screen artwork.
- `tools/badges.py`, `bootscreen.py`, `sounds.py`: canisters, boot screen, shutter sound.
- Address rule: .elf runtime = file offset + 0xC0003FF5. Disassembler helpers lived in
  the old scratchpad (not in git): rebuild with capstone as needed.

**DIAG01 (`TL-D01`, 6 Nov 2026, built, NOT flashed): film-camera mode stage 1, key-number diagnostic (item 11b).** Spec agreed with the
owner: SCENE dial position = film mode, live view only (playback + review locked); picker of all 11 looks ONLY on a new card or when a roll
hits 0 (same look again allowed), otherwise power-on / SCENE continues the current roll; 36 frames per roll, JPEG only, each roll its own
numbered folder outside DCIM (e.g. `FILM\R0007_CLASSIC_CHROME`, next number = highest on card + 1, frames left = 36 - files in the folder,
so no state in the camera); hard wind-on lock (shutter blocked until the front dial turns); no mid-roll film change, no escape hatch.
Build: `python tools/build_fauxji.py <stock> <out> --diag-keys` (normal builds are unchanged: checked byte-identical to FAUXJI63 apart from
the label). The key dispatcher call (0xC04C1938) goes to `fauxji_ui.diag_hook` (code in tilt-text slots 1-4 at 0xC0426480, text = slot 0)
and the name pop-up shows `Key kk st s` (logical key 0-15, press state) on EVERY key event. `python tools/test_diag.py` runs the emitted
code in the ARM interpreter (160 cases, registers and stack preserved). Static facts: the dispatcher has 16 logical keys; 0 = AE-L, 14 =
AF-L (FILM SIM), 10 and 11 look like the shutter (handler 0xC04C0B68, states 1/2), 12 and 13 share 0xC04C16E8 which compares the key with
12 (probably the zoom lever); 1, 2, 3, 15 share the default handler 0xC04C1300. NOT known: which key the front dial sends (it may not come
through this dispatcher at all). Test (live view, any shooting mode): turn the front dial both ways, half-press and full-press the shutter,
press every other button, and write down the pop-up. If the dial shows nothing, the dial is a different event class and the next probe
goes into the live-view state's event handler (0xC04C1F04).

**Capture path trace (6 Nov 2026, static, nothing built).** Module CSDCFList/CSDCFDir lives at about 0xC01AD000-0xC01B4500 (string
area 0xC074FED8-0xC07501B8; runtime word addresses are file offset = 3 mod 4). Facts:
- JPEG path builder 0xC01ADCA4 is `snprintf(buf, size, "%s/%s/%03d%s/%s%04d.JPG", root, "DCIM", folder, suffix, prefix, n)`:
  root = string field at object+0x40 (set from `/ext/sd0`, literal at 0xC01B44F0), "DCIM" = pool word 0xC01AEC58, folder = 3-digit
  number, suffix = the 5 chars after the number in the folder record (`PHOTO`), prefix (`SAM_`) is a caller parameter, not a literal.
  MP4 twin uses the same arguments; a generic `.%s` builder is at 0xC01B05B4-0xC01B0680.
- Every place the name DCIM is baked in: pool words 0xC01AEC58, 0xC01B1210, 0xC01B181C (all point at the `DCIM` string 0xC074FF08;
  0xC01B3664 points at CSDCFDir's own `DCIM` 0xC07500AC, no loader found) and the formats `%s/DCIM` (pool 0xC01B10FC) and
  `%s/DCIM/100PHOTO` (0xC01B1104). A different CSFileList module (0xC01A5xxx, `CAM_`, own `/ext/sd0/DCIM`) exists too; not shown to be used for capture.
- Missing folders are created: 0xC01B015C formats `%s/DCIM`, `%s/DCIM/100PHOTO`, `%s/MISC` and passes each to 0xC01B0140 -> 0xC03BCD4C ->
  0xC0157F1C (one path argument: almost certainly mkdir; failure on "exists" is ignored). It is called from the folder scan 0xC01B1460, which has
  no direct callers (vtable) and opens `root/DCIM` with the directory iterator 0xC03BCE4C, then builds an in-RAM list of 32-byte folder records.
- Plan that follows: point those pool words at small RAM buffers in the known-writable code area (as the toast text slot already is):
  four-byte `DCIM`/`FILM` and 7- and 16-byte format copies, which hold `DCIM` normally and `FILM` in film mode. Then normal playback scans
  /DCIM and never sees film frames, with no extra work. Roll folders = DCF folder numbers inside FILM (`101PHOTO`, `102PHOTO`...), because
  the folder record format is fixed (3 digits + 5 chars); the film look is not part of the folder name.
- **Rescan trace (6 Nov 2026, static).** Call chain: `CSFileList::Open(this, mediaType)` = 0xC01A5BA4 (vtable slot +0x40 of vptr
  0xC074EA7C; the vtable is (0, fn) word pairs, fn at vptr+8k+4) -> DCF mount wrapper 0xC01ABD04 (manager = this+0x118, path buffer = this+0x10)
  -> constructs the DCF list object if missing (0xC01AD104), sets media type, then the folder scan 0xC01B145C (real entry; 0xC01B1460 is its
  push) which runs the mkdir routine 0xC01B015C, opens `root/DCIM` and rebuilds the folder records. Nothing calls Open by BL or by a stored
  pointer: its static wrapper 0xC01A514C is unused, so the real caller is a vtable call on a CSFileList object I could not trace (the
  vcall pattern is too common to search blindly). The CSFileList constructor 0xC01A5690 (real entry 0xC01A568C) also has no direct caller.
  The CSFileList object keeps its own copies of the defaults: +0x90 `/ext/sd0/DCIM`, +0xB0 `PHOTO`, +0xD0 `CAM_` (runtime strings, so
  they can be edited in RAM). Global 0xC08B439C (read by the instance getter 0xC01A4E00) is never loaded by a second literal, so it is
  set by code I have not found. Static wrappers over the same instance: slot 0x28 = 0xC01A508C (11 callers), 0x38 = 0xC01A50EC (9),
  0x58 = 0xC01A52D4 (8), 0x40 = 0xC01A514C (0), 0x48 = 0xC01A5234.
- **Cache hazard found.** The new-file search 0xC01AEA54 registers the new file in the RAM folder list (flag byte [sp+0x64] = 1 ->
  0xC01AD0D4 before, 0xC01AE554 after). If film frames are written to a different top folder while the list is the DCIM list, normal
  playback could show ghost entries for files that are not in DCIM until the next scan. So leaving film mode must rescan (or the film
  shots need their own list object).
- **DIAG02 (`TL-D02`, 6 Nov 2026, built, NOT flashed) is that probe**, folded into the diagnostic build
  (`build_fauxji.py <stock> <out> --diag-keys`; code `tools/diag_probe.py`, 576 bytes at 0xC0426F10 in the dead factory region, hooked at the key
  dispatcher call 0xC04C1938; `python tools/test_diag.py` runs it in the ARM interpreter: every key and state, the finder at 6 manager
  offsets, junk and out-of-range pointers never dereferenced, registers and stack preserved). Normal builds are unchanged (byte-identical to
  FAUXJI63 apart from the label). What it shows (name pop-up, now 8 s long):
  * every key event: `Key kk st s` (logical key 0-15, press state);
  * AE-L press (key 0, `DIAG_FINDER_KEY` in fauxji_ui.py): `O:oooooooo tttttttt` = address of the CSFileList object found by scanning the
    manager at *0xC08B439C (first 256 words, and the global itself) for a pointer whose target starts with vptr 0xC074EA7C (0 = not found),
    and the media type [[[obj+0x118]+0x10]+0x20] (FFFFFFFF = chain invalid);
  * second AE-L press: calls CSFileList::Open(obj, type) 0xC01A5BA4, the rescan, with the arguments the list already has, and shows
    `R:rrrrrrrr` (return value); a third press searches again. Open is only ever called after a successful find.
  Test on the camera: put a card with a few photos in; press AE-L, write down `O:` and the type; take a photo, open playback and note
  the count; press AE-L twice more and check playback still works and the count is unchanged. If `O:00000000`, the object is not under
  the manager: send me the key numbers anyway and the next probe widens the search. Risk: a pointer inside the 0xC0000000-0xC4000000
  window that is not actually mapped would fault (the camera hangs; switch off and on).
  Other option that avoids the rescan: make no mid-session switch, i.e. film mode only
  takes effect after the next power-on (the DCIM/FILM name chosen once at mount from the dial position), which gives up "turn the dial to
  SCENE and shoot".
- Unknowns: (1) see the rescan trace above: a rescan has to be callable at SCENE entry and exit, and file numbers may carry on from the old list until then; (2) whether
  playback and the RAW writer (`.SRW`, strings at 0xC07BDD13) use the same module; (3) whether the buffers are really writable (the code
  area is: NAME_FLAG and the toast text already live there); (4) how a card with no FILM folder behaves at power-on.

**FAUXJI62 (`TL-F62`, 3 Nov 2026, flashed, checked good by the owner): name / tilt box sized from a photo, top left, hidden in movie mode.** Owner flashed FAUXJI61 (248 x 48): "Classic Chrome"
fits on one line but the box is too big. Measured on the owner's photo of the screen: box 527 px wide, "Classic Chrome" (the longest name)
302 px, so about 142 screen px of text in a 248 px box; box height was fine for one line. Now 164 x 36, text area 156 x 36
(about 10 % spare), moved to the TOP LEFT corner (8, 8) at the owner's request (empty in P/A/S/M, balances the screen). Movie mode (AE sysmode 8, read with GET_SYSVAL(3) as the menu unlock does) hides the box and skips the pop-ups, because the movie
timer uses that corner: three gates in fauxji_rot.py (`gate1`/`gate2` hide with the stock draw(0), `gate3` skips the toast), tested
in `tools/test_sky.py`; that movie is mode 8 is from the research notes, not yet seen on the camera. Caveat: in
Smart Auto / scene modes the stock top-left status icons (live-view nodes 1001-1008, 1155-1162 ...) can appear under it; the 172 px
right edge stays clear of the text node at x 172. Only SPID.Rom changes; the .elf differs in the label only. If "Classic Chrome" wraps, add ~10 px.

**Earlier: FAUXJI61 (`TL-F61`, 3 Nov 2026, flashed: too big): name / tilt box wider AND taller.** FAUXJI60's 196 x 36 box still cut names off
(owner: "needs to be taller or longer still"). `BOX_POS` is now (84, 374) 248 x 48, text area 240 x 48: room for the longest names on one
line and for two lines if one still wraps. Same bottom edge (y 422). Only SPID.Rom changes; the .elf differs in the label only.

**Earlier: FAUXJI60 (`TL-F60`, 3 Nov 2026, built, NOT flashed): wider name / tilt box.** Owner: two-word film names (Classic Chrome, Nostalgic Neg.,
Bleach Bypass, Classic Neg.) wrapped onto two lines and got cut off in the 120 px box. `BOX_POS` in fauxji_layout.py is now 196 x 36
(text area 188), estimated from the 23 px text size (node 992 trailer) and font metrics: the longest name needs about 150-175 px.
Only the SPID.Rom layout and the panel image change; the .elf differs in the label only. If a name still wraps, widen BOX_POS further
(the box starts at x 84 and the area to its right is free up to about x 250). FAUXJI59 was flashed and checked good by the owner.

**FAUXJI59 (`TL-F59`, 3 Nov 2026, built, NOT flashed): auto-rotate fix from the owner's night photos.** Owner: Auto+ worse indoors at night.
Analysis of SAM_0640-0653 (card, FAUXJI54; raw pixels viewed unrotated): the camera's tags were right on 8 of 14 (4 sideways shots
missed: 642, 647, 649, 653 + 651; 1 false tag: 646 upright tagged 6), but replaying the SAME band rules on each photo's own 17 x 13 luma
(linear light) gives 13 of 14. So the rules are fine and the AE grid read at EXIF-write time is not the frame that was shot (the live
indicator, same code on live frames, was verified). Fix: `combo` (live-view draw, every beat) stores the guess in SKY_LATCH
(0xC0426EF0); the EXIF stub uses the latch instead of re-reading the grid; beat 1000 -> 400 ms. The FAUXJI57 colour check is OFF
(`SKY_COLOUR_CHECK = False`): on the same photos it never rejects a correct tag, so it adds nothing, and its value is unproven.
Film roll is OFF too (`ROLL_SIZE = 0`, owner does not want it). Only the .elf differs from FAUXJI56 (and 57/58). `python tools/test_sky.py`
covers the latch. Test: indoors at night, vertical shots with a lamp or window near the top edge and horizontal shots: the tags
should now agree with what the indicator showed just before the shot. If still wrong, the live grid itself is the problem there.

**Earlier: FAUXJI58 (`TL-F58`, 3 Nov 2026, built, NOT flashed): film roll mode, "36 EXP" (item 11) + FAUXJI57's colour check.** Only the .elf differs
from FAUXJI57. The shots-left number is capped at `ROLL_SIZE` (36; 24 or 0 = off in fauxji_rot.py) minus the photos taken since
power-on: hook at the end of getRemainPhotoNum 0xC047B6B8 (`rollclamp`), one frame counted per run of the EXIF writer stub
(`wcommon`), counter and size in RAM at 0xC0426EE8 / EC. A new roll = switch the camera off and on. `python tools/test_sky.py`
covers the clamp (2000 cases) and the stub. UNKNOWN until flashed: (1) the shooting-screen counter really follows that getter,
(2) one count per shot (not two), (3) the camera refuses to shoot at 0 (a "memory full"-type message). Not done: "review off"
(the Quick View / Image Disp. setting was not located), a menu to pick the roll size (build option only), roll state surviving
power-off (stateless idea for later: derive from the DCF file number). Test: power on, note the counter (36 or less), shoot 3,
expect 33; shoot to 0 and see what the shutter does. If it counts 2 per shot, the stub is hit twice per photo.

**Earlier: FAUXJI57 (`TL-F57`, 3 Nov 2026, built, NOT flashed): indoor colour check for the Auto+ sky tag.** Only the .elf differs from FAUXJI56.
The brighter side band must now also be bluer than the opposite side (B/R at least 9/8 of it, AE grid planes R +0x1BA and B +0x52E);
a lamp or bright wall that fails gets no tag (Orientation 1). Code `skycol` at 0xC0426EE8 (dead factory code, liveness-checked),
call from `skdone`; `SKY_COLOUR_CHECK = False` in fauxji_rot.py gives FAUXJI56 behaviour. `python tools/test_sky.py` runs the real
emitted machine code in a small ARM interpreter against a reference (1500 random grids, 0 mismatches). NOT verified on the
camera: the plane order (Y,R,G,B) comes from the WB850F's AeDebugDisplayYRGB. Test: vertical shots of a sky scene must still tag;
vertical shots under a ceiling lamp or toward a lit window should tag less. If outdoor tags vanish, the plane order is wrong.

**FAUXJI56 (`TL-F56`, 3 Nov 2026, flashed, verified: playback and dial good): playback restyle + mode-dial wheel centre x 162, radius 147.**

**Earlier (3 Nov 2026): FAUXJI55 (`TL-F55`) built, NOT flashed yet: playback restyle only (SPID.Rom; the .elf differs from
FAUXJI54 in the version label only).** `tools/fauxji_playback.py`: 79 glossy grey 3-D icons of the playback edit wheels
(ISO plates, metering, focus, flash, slideshow arrows, brightness dial discs) -> flat white, dimmed variants flat grey, the
two cyan arrows white, and 10 cyan list rows in the playback layout -> white. Shared (live-view) icons untouched. Test:
play a photo, open the edit wheels and the option pickers; look for icons that vanish or turn solid black. The film
canister in playback is parked (see the playback code map under item 15). Also: the mode-dial wheel is re-centred (x 155 -> 159,
the stock wheel's centre measured from its rim and hub) because the dial's icons are placed by code and looked ~4 px right.

**Earlier (2 Nov 2026, night): FAUXJI54 (`TL-F54`) is ON THE CAMERA and VERIFIED by the owner ("it worked great").**
It includes everything: looks, exposure (1/60 floor in P/A/S unaffected by zoom or flash floor, M auto-ISO, -0.3 EV bias),
menu unlock in P/A/S/M, Fuji UI incl. FAUXJI52 icon restyle and the 120 px tilt box, and the tilt tag: Auto+ at power-on
(sideways faces, else sky-is-up from the AE 17x13 grid), VIDEO cycles Off / Auto / Auto+ / top right / top left, arrow
points at the sky. Next ideas (owner's choice): orange date stamp, grain strength, C1/C2 recipes, film look in playback,
film-roll mode, colour check for indoor sky false tags, FILM BKT names, playback restyle; big: lightning trigger, RAW develop.
Tip: copy only the changed files to the card and check their hashes.
change the indicator and it vanished after a photo. Cause found: the help-text box (item 44) is in none of the 11 live-view
redraw lists, so every full redraw leaves it out; and the swallowed VIDEO key skipped the redraw. FAUXJI50 re-draws the
indicator at the end of every live-view redraw, refreshes it every second (timer 31), and VIDEO runs the full redraw
like FILM SIM. Only the .elf differs from FAUXJI49 (SPID.Rom identical). Fallback FAUXJI50_OFF (`TL-F50o`): tilt Off at
power-on. Test plan: README "FAUXJI50". Decision rule from the owner: if the indicator still isn't clear and steady,
use the OFF build (or Auto without caring about the indicator) and rotate in playback.
Stock files live in extracted/tl500_008264/ (not in git).

**Current state (2 Nov 2026): FAUXJI46 (`TL-F46`) is the working build. Tilt tag Auto verified on camera (SAM_0634 tag 6, SAM_0635 tag 8); VIDEO = key 9 cycles states; the writer hooks are verified. Open: VIDEO pop-up shows only on the first press; rename "DR Auto" (playback ACB); AE-L Button menu and 3-step D-Range do not exist on this camera.**

- On camera and confirmed: everything through FAUXJI34 (looks, menus, shooting screen,
  pop-ups, busy animation).
- **FAUXJI38 built (NOT flashed): tilt tag = auto-rotate on a learnable button, see the section at the end.**
- **FAUXJI36 built (text only, NOT flashed):** DR names (menu title "D-Range", options
  Off / DR200 / DR400 with matching help lines). Test: shoot a high-contrast scene at each
  setting and check whether highlights really differ; if Exp.1 is not ~1 stop, rename.
- **FAUXJI35 (superseded, DONE and verified on the camera since FAUXJI54):** the minimum shutter is 1/60 with auto ISO in P, A and S, and zooming
  no longer pushes it to 1/125 (Samsung's zoom hand-shake shift is skipped; FAUXJI35 covered AE modes 2 and 3, FAUXJI51 and later P, A and S).
- Auto-rotate research in progress (see item 13).

---

## Tier 1: quick wins (XS-S, low risk)

### 1. Auto Rotate setting check (XS): DONE, negative
**Result:** the TL500 has no AUTO_ROTATE setting (only 29 `SETUP_MENU_*` names, none for it);
the string is shared Samsung text. Item 13 stays open.

The string table has an **"Auto Rotate"** setting (Settings menu). The strings are shared
with other Samsung models, so it may not apply to the TL500, but if the menu shows it,
switch it on and shoot a vertical frame: if the photo comes out tagged vertical, the
camera has a sensor after all and item 13 is solved for free.

### 2. Film grain (S)
Samsung's **Special Effect -> Add Noise** already adds noise to the JPEG. Rename it
"Grain Effect" (half done: menu text exists) and tune its strength into Fuji-like
Weak / Strong grain. Pairs well with ACROS and Classic Neg.

### 3. Dynamic range modes (S): names DONE in FAUXJI36, behaviour untested
**D-Range Exp.** (Off / 1 / 2) exists: Samsung's highlight-protecting tone mode. Rename
to Fuji's **DR100 / DR200 / DR400** and check what each step does to highlights.

### 4. Orange date stamp, film-camera style (S): research, not done
Findings (2 Nov): the WB850F link map (`extracted/wb850f/partialImage.o.map`) names the
stamp fonts: `gImprint{1m,3m,5m,10m,16m,VGA}{0-9,A,P,M,Colon,Dot,Slash}Font` (+ `...FontTbl`),
in Library_CaptureFramework; `mmfImPrint` draws them. Glyph sizes: 192 / 600 / 912 / 2400 /
3264 / 72 bytes, which fits 1-bit bitmaps (32x48, 60x80, 76x96, 120x160, 136x192, 24x24).
FOUND 8 Nov 2026 (FILM26 entry): the fonts and the draw are at 0xC079F3E4 ... and 0xC03CC96C. Earlier: a plain stride-pointer-table scan and an entropy scan found
nothing, so the glyph tables are probably reached through structs. Next: find the code that
reads `SETUP_MENU_IMPRINT`, or search the .elf for the WB850F glyph bytes (same library).
Colour is probably set at draw time (mmfImPrint), not in the bitmaps, so orange may be a
small code patch rather than art.
**Imprint** (Off / Date / Date & Time) burns the date into the JPEG. Redraw its digit
images as orange seven-segment digits and use a film-camera format (`'26 11 02`).
JPEG only, RAW untouched. Best fun-per-effort item.

### 5. Intervalometer upgrade (S): premise corrected, not done
The 1 / 3 / 5 / 10 s strings (SPID 359-363, help 1214-1218) are the **slideshow** interval, not
the drive mode. The drive-mode Interval has its own setup screen (hours, minutes, shot count,
start time: `CAPTURE_MENU_INTERVAL_*`), so it is already a time-lapse timer; a "30 s" step
needs its screen code, not a table. Test on camera what the shortest interval is first.
Drive mode **Interval** has 1 / 3 / 5 / 10 s. Find its small table and add 30 s, 1 min,
5 min (and a shot count), for time-lapse, clouds, sunsets, stars.

### 6. Recipes (S)
**User Mode 1 / 2** (renamed C1 / C2 Recipe) store whole settings. Ship a few classic
recipes (Kodachrome-ish on Classic Chrome, Portra-ish on Classic Neg., Tri-X-ish on
ACROS: look + WB shift + tone + colour + sharpness) and show the recipe name with the
film pop-up.

### 7. Framing tools (XS-S): no overlay image in skin.bin, lines are drawn by code (not done)
**Grid Line 3x3** exists. Add a Fuji-style "24x36" frame guide and a centre cross; restyle
the lines thin white.

### 8. Higher ISO choices (XS): not done
ISO 3200 already reachable in M auto-ISO (FAUXJI EVC build). ISO 4800/6400 strings are leftovers; a
Sv 176 row would need the sensor-gain path checked first.
Strings for **ISO 4800 / 6400 / 64** exist. Check whether the sensor path accepts them
(EXIF oracle test); offer ISO 6400 as an "emergency" setting.

---

## Tier 2: medium (M, low-medium risk)

### 9. Auto ISO settings in the menu (M)
Today the P/A floor is fixed (1/60, ISO cap 1600). Make Fuji-style choices: minimum
shutter 1/30 / 1/60 / 1/125 / Auto (1/focal length), max ISO 800 / 1600 / 3200. The
program-line table is understood (`PL_Capt_Program` at 0xC094AA18); this needs a
setting and a small routine that rewrites the table rows.

### 10. Live histogram + blinking highlights (M)
A histogram display exists ("Displays histogram information."). Restyle it as Fuji's
small white histogram; add blinking blown highlights in playback.

### 11. Film roll mode, "36 EXP" (M)
Choose a 24 or 36 exposure roll: the shots-left counter on the shooting screen counts
down like film; at zero the roll is "finished" until you load a new one in the menu.
Optional: no review after the shot (Quick View Off), so you can't chimp. Built on the
shots-left counter, Quick View and the file counter.

### 11b. "Film camera" mode in place of SCENE (L, back burner, owner idea 3 Nov 2026)
The owner never uses scene mode: replace the SCENE dial position with a film-camera mode instead of a toggle. Idea: dial on SCENE
= film mode (the shooting mode is readable already: sysvalue 3 via GET_SYSVAL 0xC048F81C, 10+ = scenes, as the menu-unlock hook
does). In that mode: shots-left capped by the roll (FAUXJI58's `rollclamp`, built and parked), no review (Quick View forced Off:
the setting reader is NOT located yet, see the FAUXJI58 notes), and the scene picker (layout trees 1751 etc., 12 cards 195-206 + 559)
becomes a film-stock picker whose choice is applied with the FILM SIM routine (SET_UI 0xC048F630, ui id 0x41). Open: which scene id
gives a plain exposure program, the hook where a scene card is chosen, forcing the menus open in that mode, a bigger retro counter
(needs new art; the digit images are separate skin images). Several builds, medium-high risk: parked until the owner asks.
Owner's wish (3 Nov, later): a simpler custom GUI with a BIG roll number ("an event"), and the front scroll wheel winds the film
between shots. Plan in stages, each stage one flash: (1) diagnostic build: pop-up shows the logical key numbers of the front
wheel (both directions) and of the shutter half/full press (FAUXJI41 technique), and test the Quick View candidates; (2) a minimal
item list for the SCENE position (the 11 viewfinder item lists at 0xC09BDAD8 are plain data; a new list = battery, film icon,
counter) and the big number (static strings "0".."36" in the SPID string table, or the digit skin images in repurposed nodes);
(3) wind mechanic: after a shot swallow the shutter keys in the live-view dispatcher (0xC04C1944 hook, as the VIDEO key is
swallowed) until the wheel has turned N detents, "WIND" prompt, ratchet click from tools/sounds.py. Unknowns: the key numbers,
the review setting, text size of a node (or digit images), whether swallowing the shutter key is clean.

**DIAG02 first camera result (7 Nov 2026, owner), corrected:** the shutter showed key 10. The "Key 14 st 0" the owner first reported for the
front dial was most likely the FILM SIM name pop-up (key 14 is the FILM SIM / AF-L key and its pop-up uses the same box), not the dial: the
dial gave no key information. That fits the code: the live-view state handler 0xC04C1F04 tells event classes apart by type name and the
front dial is not a key at all, it is a `CSAFWheelDialEvent`. Classes it knows: CSAFKeyEvent (to the key dispatcher 0xC04C18CC),
CSAFWheelDialEvent -> handler 0xC04BF860 (call at 0xC04C21FC; the payload object, event+0x10, has a method at vtable +8 that returns the
direction bool, which the stock handler turns into +1 / -1 on a setting; it acts when the AE mode state [+0xC] is 3 or 5), CSAFClickDialEvent ->
0xC04C06E0 (0xC04C2228), CSAFDriveDialEvent and CSAFHSDialEvent -> 0xC04BFBF8 (0xC04C22D0, they set [state+0x15] = 1), CSAFModeDialEvent -> the
same 0xC04BFBF8 (0xC04C2328), CSAFFlashEvent 0xC04BFD94, CSAFGUICallbackEvent 0xC04C0978, CSAFConnectEvent 0xC04BFE7C, CSAFBatteryEvent
0xC04BFCE8, CSAFScreenRotationEvent 0xC04BFF38, CSAFTimerEvent, CSAFDisplayEvent, CSAFCallbackEvent, CSAFRemoteEvent.

**DIAG03 (`TL-D03`, 7 Nov 2026, built, NOT yet on the card):** DIAG02 plus (1) the FILM SIM routine is OFF (key 14 goes back to Samsung's
AF-lock handler, so the name box is only written by the probe), (2) each of the four dial event call sites (wheel, click, drive / half-
shutter, mode) goes through a trampoline that shows `Dial L d` in the pop-up (L = W wheel, C click, D drive / HS, M mode; d = the wheel's
direction flag, 0 for the others) and then runs the stock handler unchanged (tools/diag_probe.py, 820 bytes, still inside the dead factory
region; `python tools/test_diag.py` covers every trampoline, the direction call and register / stack preservation). Test: turn the front dial
both ways (expect `Dial W 0` one way and `Dial W 1` the other), turn the other dials, press the shutter (key 10, states), press AE-L for the
finder. Wind-on can then watch CSAFWheelDialEvent (any direction) and the shutter key 10.

**TL-D03 camera result (7 Nov 2026, owner) - the TL500 control map:** FRONT dial = CSAFClickDialEvent (`Dial C 0`); REAR dial = CSAFWheelDialEvent
(`Dial W 0` / `Dial W 1` for the two directions); zoom lever = key 6 (wide) and key 5 (tele), both state 1 on press; AE-L button = key 14, state 1
(the AE-L button setting picks key 0 or 14: this camera sends 14, so the finder on key 0 never fired); shutter = key 10 (half / full states not
yet read; the stock handler 0xC04C0B68 uses 1 and 2). Wind-on therefore watches the CLICK dial (front dial) event, any direction; its handler
0xC04C06E0 asks the event (vtable +0x10) for 1 / 0 (the two turn directions) or 2 (a press of the dial).

**DIAG04 (`TL-D04`, 7 Nov 2026, built; was NOT on the card when written):** DIAG03 plus (1) the finder moved to key 14 (`DIAG_FINDER_KEY`), (2)
the front dial's pop-up now shows the event's value (`Dial C 0` / `Dial C 1` direction, `Dial C 2` a press of the dial). (3) every key pop-up now ends with the shooting mode, `Key kk st s Mnn` (GET_SYSVAL(3); scene modes are 10 and up per the menu-unlock notes, but the number the SCENE dial position gives has never been seen on the camera: read it by turning the mode dial to SCENE and pressing any key). Probe 916 bytes, ends 0xC04272A4 (limit 0xC04272C0); tests in tools/test_diag.py. Test: front dial both ways, AE-L once (`O:` line) and twice (`R:` = rescan result;
check playback afterwards).

**TL-D04 camera result (7 Nov 2026, owner):** shooting-mode numbers (GET_SYSVAL(3), shown as `Mnn`): **P = 2, A = 3, S = 4, M = 5, SCENE = 10**
(scenes are 10 and up, as the notes said). Zoom lever keys 6 / 5 (state 1). Front dial = click dial, `Dial C 0` / `Dial C 1` by direction (the
owner wants turning it to the RIGHT to wind: confirmed, RIGHT = `Dial C 1`, left = `Dial C 0`). Shutter half-press = key 10; the full press shows no number because it takes the photo straight away (the pop-up is not seen). The finder line `O:oooooooo tttttttt` wrapped to two rows and was cut off in the pop-up box (it holds about 13
characters on one line), so nothing could be read: TL-D05 shows one short value per press.
Side finding: fauxji_rot's menu unlock (`cmp ip,#4; bhi mkeep`) was written for the AE enum (P 0, A 2, S 3, M 4); with the numbering above
(P 2, A 3, S 4, M 5) it unlocks P, A and S but skips Manual (5), which keeps Samsung's stock limits. Stock may already allow everything in M
(the owner reported the unlock "worked great"): check for greyed menu items in M before changing the cut-off to 5.

**DIAG05 (`TL-D05`, 7 Nov 2026, built; NOT on the card when written):** TL-D04 with the finder split into short lines: AE-L press 1 = `O:oooooooo`
(object, 0 = not found), press 2 = `T:tttttttt` (media type), press 3 = rescan, `R:rrrrrrrr` (result), press 4 searches again. The three
display blocks share one routine (probe 892 bytes, ends 0xC042728C, limit 0xC04272C0; tests updated).

**TL-D05 camera result (7 Nov 2026, owner) - THE RESCAN WORKS:** `O:C159F664` (the CSFileList object, a heap address, found by the manager scan),
`T:00000064` (media type 0x64, matches the DCF code's `[list+0x20] == 0x64` branches), and the rescan `CSFileList::Open(obj, 0x64)` returned
`R:0000001B` = 27 with playback still working afterwards. The card then held exactly 27 files in DCIM/100PHOTO, so **Open's return value is the
file count of the folder it scanned**. Consequences: (1) the camera can be told to rescan at runtime with no side effects seen; (2) after
switching to a roll folder and rescanning, `36 - result` is the number of frames left, with no directory iteration code and no state kept
in the camera; (3) a shot count by file count survives power-off, card swaps and deleting files on a PC.

**Camera check of TL-F65r (8 Nov 2026, owner's card, FILMS/PROV001, SAM_0832-0835):** EXIF confirmed on the camera: Make 'FAUXJI FILM', Model 'TL500 Provia' (NUL-padded to 24 bytes), Software 'FAUXJI TL-F65r', photos read normally. The date stamp works: orange seven-segment '26 11 08' in the bottom-right corner (48x80 font on 3648x2736). The wind-on ratchet was silent (fixed in TL-F65t, below).

**FILM28 (`TL-F65t`, 8 Nov 2026, NOT yet flashed): the ratchet fixed, the TL500 boot screen.** Owner (TL-F65r): no wind-on sound, with the sounds on. Cause: `film_sound.RATCHET` misread the stock player 0xC0476F3C. *0xC09B5380 is the volume SETTING (0 = Off .. 3), not a sound object, and 0xC01BC6B8(level) applies that level to the mixer (returns 0), it is not a 'still playing' test; the bytes *0xC09B5018 / *0xC09B501C are an audio route set by the mode code (0xC041C50C, 0xC0482260), used only to pick the output value passed to 0xC01BCA50, and the player plays whatever that value is. RATCHET returned when *0xC09B5018 was 0, which it is in shooting mode. Now it follows the player step by step: silent with the volume Off, else level applied, output value from the route (0 when the flag is clear), block played. Also (from reading 0xC01BCA50): its only stack argument is the sample rate; r2 is the stereo flag. Boot screen (TL-F65s): the original text ('original' taglines) with the model TL500, redrawn (`bootscreen.render_tl500`, lens aperture, red light leak; preview docs/images/film-mode/boot_tl500.jpg). Tests: `python tools/test_film.py` (bad 0, ratchet cases rewritten).

**FILM29 (`TL-F65u`, 9 Nov 2026, NOT yet flashed): the film camera gets P's exposure fixes.** Owner (TL-F65t): in the film camera the minimum shutter still rose from 1/60 to 1/90 or 1/125 when zoomed in. Cause: the exposure engine keeps its own mode number (AE sysinfo *0xC03EDB1C()+0xA: 0 P, 2 A, 3 S, 4 M), set from the mode change and not read through GET_SYSVAL, so `filmget` making the film camera P did not reach it, and the two fixes keyed on that number did not apply: the zoom hand-shake shift skip (fauxji_ui ZOOM_HOOK 0xC053FDC4) and the flash shutter floor (fauxji_rot `plzoom`). `tools/film_ae.py`: both first test the film camera flag (film_mode vars[4]) and take the P path when it is set; the stock P/A/S test moves to the spare end of R1 (0xC04261C0), the flash test sits in 16 bytes reserved in R4 (0xC0426C74; film_mode's helpers start 16 bytes later). Checked the other fixes: the 1/60 floor and ISO cap (program line table), the -0.3 EV bias (all modes) and the menu unlock (GET_SYSVAL) are not keyed on that number. Tests: `python tools/test_film.py` section 15 (film on/off x modes, zoom and flash paths, bad 0); the plain build is still identical to FAUXJI63.

**FILM26 (`TL-F65r`, 8 Nov 2026, NOT yet flashed): wind-on ratchet, orange '90s date stamp.** (1) *How the camera plays sounds* (static): 0xC0476F3C(type) is the effect-sound player (38 callers in the control app): it returns if the sound object *0xC09B5380 is 0 or 0xC01BC6B8(object) says a sound is playing, takes the level from 0xC0471258 (sounds on) and 0xC047127C (volume 0..5; 4, 5 -> 2; 0..3 -> 1 if 0xC043A494(0xC043A1B4()) == 2 else 2) and plays a [u32 length][PCM] block with 0xC01BCA50(block, level, 0, 0, [sp] rate, [sp+4] gain) or a SPID file with 0xC01BC934(path, ...). The factory sound test (CAPPFactoryInitMenuState, 0xC0512610 -> 0xC0512070, categories 1/2/3 -> 0xC0478168 / 0xC0477FAC / 0xC0477D64) calls the same players from the control app's message handler, the task our hooks run in; the sound itself plays in CBIMMSound's BeepQueue / PlaySoundTask. `film_sound.RATCHET` (R1, 148 bytes) does the same checks and plays the ratchet block, which sits in the unused end of the built-in Shutter 3 slot (0xC097EE50, 12.8 KB; FAUXJI's shutter uses the first 8 KB). `filmdial` calls it when the dial winds on. (2) *The date stamp* (the WB850F's mmfImPrint, found in the TL500): capture code 0xC03C5B70 calls 0xC03CC96C(image + 0xA8, size [+0x1BC], layout [+0x1EC]) when bit 0x400000 of [+0x1C8] is set; layouts 2..7 = date (Y.M.D / D.M.Y / M.D.Y) and date + time, formatted with sprintf 0xC066D894 ('%04d.%02d.%02d' ...); 0xC03CC28C picks one of six 1-bit fonts (48x80, 40x72, 40x72 unused, 32x56, 24x48, 16x24; tables at 0xC079F3E4 / 0xC07A0A64 / 0xC07A1B44 / 0xC07A2C24 / 0xC07A36A4 / 0xC07A3D64, glyphs 0-9 '.' ':'; other characters are blank); the draw 0xC03CC7B0 calls the blitter 0xC03CC5F0 per glyph, which writes Y 0xE1 and U 0x00 / V 0x94 (8 + 4 + 4 `mov` immediates). The film build: the blitter's colour `mov`s read Y/U/V from [sp+0x2C..0x2E], filled by `stampwrap` (Samsung's colour, or orange Y 0x8F U 0x3A V 0xD0 in the film camera); `fmt98` (the layout switch, 0xC03CCA08) writes '%02d %02d %02d' of (year % 100, month, day) in the film camera; `forcestamp` (film_mode, at the `beq` 0xC03C5C54 that skips the stamp) makes the call in the film camera with layout 2 even with Imprint Off; the four large fonts get seven-segment digits (`film_stamp.seven`, preview docs/images/film-mode/stamp_digits.png; 24x48 and 16x24 keep Samsung's digits). Unknown until flashed: whether the image-size selector [+0x1BC] is filled with Imprint Off (any value is safe: unknown sizes use the 48x80 font) and whether the stamp lands where Samsung's does. Tests: `python tools/test_film.py` (bad 0; new: the ratchet's checks and levels, Samsung's patched blitter run through `stampwrap` in both colours, `fmt98`, `forcestamp`, the fonts), `python tools/test_sky.py` (the interpreter now knows `asr` and three-operand shifts).

**FILM25 (`TL-F65q`, 8 Nov 2026, NOT yet flashed): mystery roll, counter counting up, EXIF names, film boot screen.** (1) *Mystery roll.* Card 22 (the spare twelfth card) is film 11, MYST: folders MYST001 ...; the look of each roll is `TAB_MYST[roll & 31]` (a 32-entry shuffle, every look at least twice, no repeats in a row, fixed seed so builds stay reproducible), applied on entering the card (`filmlook` before `applylook`) and again when AE-L loads the next roll. Nothing is stored, so a part-shot mystery roll has the same look after power-off. `iconcore` shows no tile for it and hides the live view's film icon (group 1009, `FILM_GROUP`); it is shown again once when the film changes or SCENE is left (`icunhide`, keyed on the last mode-spot code). The picker card is a nameless dark cartridge with an orange '?' (`badges.mystery_card`, preview docs/images/film-mode/mystery_card.png), named Mystery with its own blurb. (2) *Counter counts up.* `rollclamp` returns 37 - frames left (the frame about to be shot) when the card has room for the rest of the roll, 0 on a full roll, and the stock number when the card has less room. Found statically: the shots-left wrapper 0xC04DE748 stores the value as GUI value 0x7E (0xC04CDAB4) and sets sysval 0xC (card full) from `value == 0`, and the shutter gate 0xC04DD728 refuses to shoot only at 0, so a non-zero count-up value shoots normally. The pop-up reads 'PROV001 #01' / 'PROV001 full'. Unknown until flashed: whether anything shows the raw value elsewhere (e.g. burst count limits read 0x7E at 0xC04DBBB0). (3) *EXIF names* (tools/film_exif.py, film build only, every mode): the IFD0 writer 0xC03773E0 walks the tag table 0xC091D044 (count at +8) and passes 8/9-byte stack copies of Make / Model / Software to its data writer; counts become 12 / 24 / 16 (the IFD0 data size is summed from the same counts at 0xC03792D8), Make and Software load our strings through the function's own pool words, Model goes through `exifmodel`, which writes 'TL500 ' + the look's name (UI_CACHE + 0x40) into a RAM buffer. Code in R2 (free since the tilt tag is off), names in R4's spare end. (4) *Boot screen* `bootscreen.render_film` (film strip with edge print and four look-coloured frames, FAUXJI FILM, TL500), preview docs/images/film-mode/boot_film.jpg; the plain build keeps its screen and stays byte-identical to FAUXJI63. (5) *Space*: the R5 block was full, so the mystery table and 'No playback' moved to R3, 'Roll full - press AE-L' to the end of R2, and the block's data was repacked (TAB_LAST in the old text slot); 44 bytes left before FILM_END. (6) *Ratchet sound* made (`sounds.ratchet`, docs/sounds/ratchet.wav) but not played: see ROADMAP 'Wind-on sound'. Tests: `python tools/test_film.py` (bad 0; new: mystery look per roll and on a new roll, mystery icons, count-up values, frame pop-up, EXIF hook in the interpreter and on a real image), `python tools/test_sky.py` (the interpreter now knows `and` / `rsb`).

**FILM24 (`TL-F65p`, 8 Nov 2026, NOT yet flashed): audit fixes.** From a code audit of FILM23: (1) *Full card vs. full roll.* "Memory Full" read "Roll full - press AE-L" whenever the film camera was on, also when the SD card was full with frames left on the roll (AE-L then said "Roll in use"). `filmstr` now returns the film text only when the roll has 36 files and the real mode is a scene card. (2) *Real mode in the playback and text hooks.* `filmevent`, `filmstate` and `filmstr` checked only the film flag, which changes on the next key press after the dial moves; they now also read the real mode (`scene_test`), so PLAY works as soon as the dial leaves SCENE. (3) *DUAL IS icon.* The roll-full icon was painted over skin image 231, the DUAL IS mode's own tile, so DUAL IS showed a crossed cartridge in the film build, and leaving a full roll for DUAL IS hid its icon. The roll-full icon is now the spare twelfth scene tile (child 822 / 894, image 241: iconfix only shows tiles 0-10), image 231 is back to the plain build's DUAL tile and `icclean` touches only our own children. (4) *Roll memory.* Each film remembers the roll it was last on since power-on (`tab_last`, 11 words before the code, CODE_AT 0x258), so re-entering a film with many full rolls probes from there instead of rescanning every roll from 001 (each probe is a rescan and leaves an empty next folder). (5) `filmdraw` keeps the redraw's return value in r0. (6) Dead load in `filmdial` removed; the module docstring rewritten (FILMS/ folders, AE-L only reloads). Build tool: argparse (unknown flags are an error, `--film` and `--diag-keys` exclusive), `--check` says when only the version label differs, skin.bin is patched in one pass, the plain label is TL-F63 (the plain output is byte-identical to FAUXJI63; it said TL-F62 before). Tests: `python tools/test_film.py` (bad 0, new cases: full card, dial moved without a key, roll memory, twelfth-tile icon, r0 kept), `python tools/test_film_layout.py <SPID.Rom of a --film build>` (bad 0).

**FILM23 (`TL-F65o`, 8 Nov 2026, owner's card, NOT yet flashed): the icons paint at once.** Owner (FILM22): the wind-on icon and the film cartridge in the corner only paint after a repaint (e.g. pressing the display key); the wind-on must show right after a shot. Cause: `iconfix` ran only from our own redraws, but after a shot the camera redraws just the counter, and when the dial moves to a scene card the stock draw shows P until the key hook has switched the roll. Fixes: (1) the counter's hook (`rollclamp`, `crest`) calls `iconlazy` after every shots-left calculation in film mode; the shot that raises the file count sets the lock in that same call, so the wind-on icon is drawn in the redraw that follows the shot (a call into the code block by absolute address, `helpers(..., icon)` is built twice). (2) `iconcore` now follows the REAL mode (raw getter) and takes the look from the card (tab_id), so it needs neither the roll switch nor the film flag for the tile: the DRAW_ICONS epilogue hook (which every live-view re-entry runs) paints the look's cartridge as soon as the camera is in a scene card, without waiting for the first key. (3) `vars[28]` remembers the state set last (state * 16 + look + 1) so the lazy entry draws only when something changed (the 40 OSD calls are not repeated for every counter calculation); the forced entry (`iconfix`, the DRAW_ICONS hook, pop-ups, the dial) always draws since a stock redraw may have reset the spot. (4) In any other mode our own children (the tiles, the wind-on child, and the roll-full child if it was shown) are hidden again once, after the stock draw has run. Unknown until flashed: whether the counter's hook runs in the GUI task (OSD calls from another task could misbehave), whether DRAW_ICONS runs when the dial moves, whether the sub-second gap between a shot and the counter redraw is acceptable. Tests: `python tools/test_film.py` (bad 0: tile per card, clean-up, lazy, counter-after-shot, DRAW_ICONS hook).

**FILM22 (`TL-F65n`, 8 Nov 2026, owner's card, NOT yet flashed): the big cartridge is dropped, the mode icon spot is the look's cartridge, the icons are persistent.** Owner (FILM21): the film icon was gone completely; the wound icon showed once, at the bottom where "P" shows; "this did not work very well, if not we go back". Conclusions: (a) the big-cartridge layout (group 1009 moved out of its parent column 994, the digit group 797 moved out of the bottom bar 744) made the icon vanish, most likely because the OSD clips a node to its parent's rectangle (both left their parents' bounds); `film_mode.layout` and `badges.patch_big_cartridges` stay in the tools but the build no longer applies them, so the film icon is back to the FILM20 one (the 64 px cartridge in the left column) and the counter stays in the bottom bar. A cartridge with the count inside would have to stay inside the left column's 100 px (the count would then be in the column, not the bar: not possible without moving the digits) or the digits would need their own parent: not attempted. (b) The wind-on icon showing "where the P shows up" proves the show/hide by node index works and that the mode icon spot shows P in SCENE (the camera's SCENE-as-P hides the scene tiles, so the FILM17 tiles never showed). `iconfix` now always sets the spot in SCENE: the look's cartridge tile (tile = first scene tile + look, both icon groups), the wind-on icon while locked, the roll-full icon while the roll is full; and a hook at the end of every full redraw (DRAW_ICONS 0xC04B74AC, `filmdraw`) re-applies it, so the stock P tag cannot come back after a redraw and the wind-on icon is no longer a one-off. Unknown until flashed: whether a redraw that does not go through DRAW_ICONS (single item updates) shows P for a moment, whether the half-press AF redraw reverts it. Tests: `python tools/test_film.py` (bad 0, iconfix / filmdraw cases) and `python tools/test_film_layout.py <SPID.Rom>`.

**FILM21 (`TL-F65m`, 8 Nov 2026, owner's card, NOT yet flashed): the overlay concept, first version (wind-on / roll-full icons, big cartridge with the shots left in it).** Owner chose "icons + big cartridge". Findings: (1) The OSD show/hide call 0xC0201CAC(node, visible, 0, 0) maps its first argument with 0xC020011C: a value with bits above 0xFFFF is a hash looked up in the skin's hash table (records (hash, node index, runtime pointer) in the section at 0x974000-0x980B4C of skin.bin; each node has two records, the code's constants are one or the other), a value below 0x10000 is used as the node index directly, so our code can show or hide any layout node by index. (2) *Icons:* the live view's mode icon group (803, twin 874; one 58 x 54 child each: 804 SMART, 805 P ... 811-822 the twelve scene tiles, 823 'play'; 875-895 for the twin) shows the card's cartridge tile in SCENE. `iconfix` (film_mode.py) hides every child and shows the 'play' child (skin image 17, repainted as the wind-on dial with a curved arrow) while the roll is locked, or the 'DUAL IS' child (image 231, repainted as a greyed cartridge with an orange cross) while the roll is full and wound; neither mode shows in the live view of the film camera. It runs after the pop-up redraw (`popup11`), when a shutter press is swallowed (`gshow`) and when the front dial winds on (after a full redraw that brings the stock tile back, so a full roll then shows its icon). Not persistent across stock redraws that do not go through our code (the icon returns at the next shutter press or key-driven redraw). Art: `badges.wind_tile` / `full_tile` (crisp, orange on dark; image 17's slot is only 2768 bytes), preview docs/images/film-mode/state_tiles.png. (3) *Big cartridge with the count:* group 1009 (the film icon, in the left column 994) moves to the top right (BIG_AT 484, 6), its eleven children (images 414-424) become 80 x 96 crisp cartridges with a BLANK white strip and a transparent window (`badges.big_cartridge`; 3 KB against slots of 4-5.7 KB); the shots-left digits (group 797 in the bottom bar 744: five right-aligned digits at x 2, 16, 30, 44, 57) are moved up behind the window. The left column is drawn after the bar (tree order), so a hole in the cartridge is the way to see the digits through it; the digits are white with a dark outline, readable on any background. Preview: docs/images/film-mode/big_cart_count.png (digits '34' as a stand-in). `film_mode.layout` edits the node rectangles; `python tools/test_film_layout.py <SPID.Rom>` checks rectangles, image sizes, the window and tile sizes. UNKNOWN until flashed: that 797 really is the shots-left counter (it sits between the AE-L tag and the battery in the bar), that the OSD does not clip children to their parent's rectangle (group 1009 and 797 both leave their parents), that the film icon the owner sees is the left-column one (a right-column twin 1065 also references image 420), the draw order, and whether anything else sits in the top right. The counter leaves the bottom bar in every mode of the film build. Tests: `python tools/test_film.py` (bad 0, with the iconfix cases) and the layout checks above.

**FILM20 (`TL-F65k`, 8 Nov 2026, owner's card, NOT yet flashed): short texts for the display (up) key.** Owner (FILM19): the direction keys work; up cycles the information display and names each view in the little text box, but the 27-78 character stock descriptions wrap into two unreadable rows (the box is 164 px, about 14 characters, sized for the film names). Rather than turning the text off or growing the box (it sits over the picture), the film build shortens the display-mode description strings (`film_mode.DISPLAY_TEXT`: ids 1011/1018 Full info, 1012/1019 Basic info, 1015 Info + grid, 1016/1021 Grid+histogram, 1334 Histogram, 1335 Info hidden, 1014 Function help). Which of these the key really shows is inferred from the wording (they are the only display-mode descriptions in the table); a view that still wraps would be another string, or the box can be widened for it (`BOX_POS` in fauxji_layout.py). Plain builds are unchanged. Tests: `python tools/test_film.py` (bad 0).

**FILM19 (`TL-F65j`, 8 Nov 2026, owner's card, NOT yet flashed): macro, flash and the other direction keys in the film mode.** Owner (FILM18): shot placement and the counter are right; macro (down) and flash cannot be chosen in the film mode (ISO staying auto is fine). Cause (static): the live-view key dispatcher 0xC04C18CC (fp = the live-view state object) sends the keys 1, 2, 3 and 15 to one handler, 0xC04C1300, which asks a per-direction function whether the key acts: 0xC04C05DC (key 2), 0xC04C0424 (key 3, a jump table of 23 modes), 0xC04C0554 (key 1) and 0xC04C0628 (else). They test `[fp+0xC]`, the shooting mode cached in the state object, against 2, 3, 4, 5 (P, A, S, M) and 6, so every scene card (10..22) was locked out even though every GET_SYSVAL(3) read already says P. `filmhook` (it runs first in the dispatcher and keeps fp = r11) now makes `[fp+0xC]` equal 2 whenever the real mode is a scene card (values outside 10..22 are never touched; tests cover modes 0..39 and a repeated key). Inferred, not confirmed on the camera: that +0xC really is that mode cache and nothing else (it matches the comparisons with 2-6). ISO: the menu behaves like P, so ISO is selectable there; locking it to auto is not done (an AE-mode or menu-mask hook, not started). Tests: `python tools/test_film.py` (bad 0).

**FILM18 (`TL-F65i`, 8 Nov 2026, owner's card, NOT yet flashed): parent folder, second try; the counter after leaving SCENE.** Owner (FILM17): photos fine, but "when I switch to P it still says 23 shots until I take a shot". Card check (8 Nov): FILM17's FILMS folder was created but EMPTY; the three new SCENE photos (SAM_0820-0822) went to PROV001 in the root, the two photos taken in P (0823, 0824) to DCIM. So the list object's root string (list+0x40) is used by the folder creator and the scan formats but NOT by the save path: appending '/FILMS' to it made the folder and nothing else. All 8 path builders (0xC01ADD8C, 0xC01ADDDC, 0xC01ADF90, 0xC01B0298/05B4/0674, 0xC01B14C0, 0xC01B3208) call snprintf(buf, size, fmt, list+0x40 (root), name ...) with the folder name pointers, so a name with a slash is just a deeper path: the roll folder name is now "FILMS/ACRO001" (buffers: name 16 | fmt1 "%s/FILMS/ACRO001" 24 | fmt2 "%s/FILMS/ACRO001/100PHOTO" 32; NAME_LET/FMT_LET offsets of the letters and digits; layout constants moved). The parent is made once when entering SCENE with the camera's creator 0xC01B0140(list, path), the root string getting '/FILMS' for that one call and put back at once (`mkparent`). Unknown until flashed: whether the scan handles a nested name (it opens the path; if it compares directory names the film mode will find no photos and report 36 left), whether DCF copies the name into a short field somewhere. Counter: the camera computes the shots-left number when the mode changes, while our flag (film active) is still set until the next key press; `rollclamp` now also reads the real mode (the raw getter) and keeps the stock number unless it is a scene card (tests: film active, camera in P: stock; scene card: clamped). Rolls made so far sit in the root (PROV001, BLCH001, FILM001, FILM002): move them into FILMS to continue them. Tests: `python tools/test_film.py` (bad 0).

**FILM17 (`TL-F65h`, 8 Nov 2026, owner's card, NOT yet flashed): the live-view mode icon.** Owner asked to work on the overlay concept and the mode icon before testing. Finding: the live view's mode icon group (803, bottom left, 58 x 54) has one child per mode; for the scene modes it has twelve children, the scene's own icons (skin images 242 Beauty Shot, 248 Night, 250 Portrait, 243 Children, 247 Landscape, 244 Close Up, 239 Text, 251 Sunset, 245 Dawn, 240 Backlight, 246 Fireworks, 241 Beach & Snow, in card order 10, 12-22: viewed with tools, preview docs/images/film-mode/scene_tiles.png). Since the film mode uses the scene cards, the live view therefore showed e.g. the face icon of Beauty Shot for PROVIA (this is inferred from the layout and the card order, not yet seen on the camera: my earlier note that it shows P was a guess). In the film build those twelve images are now the cartridge of the card's look (`badges.scene_tile`, the crisp small cartridge on the transparent key, preview docs/images/film-mode/scene_tiles_film.png). Everything else from FILM16 is included. Overlay concept: not built (see the ROADMAP investigation): the live-view layout tree was dumped (root 742: the film icon is group 1009 at (10,184) in the left column group 994, children 1010-1020 are the white 64 px cartridges 414-424; the shots-left digits are probably group 797 at (458,17); the help-text box is group 990). A big cartridge with the count inside needs a new image bigger than the 64 px slots (about 75 px fits the byte budget), a free place (the columns are full: icons every 60 px) and a decision on how the count is drawn (the camera's own digits, group 797, moved onto the strip, or an image per count), and none of that can be checked off the camera. The wind-on / roll-full art needs an icon node that can be shown and hidden by our code, not found yet. Tests: `python tools/test_film.py` (bad 0).

**FILM16 (`TL-F65g`, 8 Nov 2026, owner's card, NOT yet flashed): one parent folder for the rolls, FILM on the mode dial.** Owner (FILM15): the freeze is gone; PLAY's file error stays (accepted for now: no photos are shown, which is the goal; a "develop your film on the computer" screen is a wish) and the photos are on the card (BLCH001 5, PROV001 10 files, 2.3-4.2 MB each). Owner asked for: (1) *Parent folder.* The DCF list object keeps the card root as an inline string at +0x40 (the folder creator formats "%s/DCIM" from it with `add r3, fp, #0x40`, 0xC01B015C; its single-folder creator is 0xC01B0140(list, path) -> 0xC03BCD4C). A nested folder name does not work (the scan compares one directory entry with the name pointer), so in SCENE `/FILMS` is appended to the root string (`rootenter`: backup copy of the 48 bytes, append, make the folder with the camera's creator before the first scan; `rootleave` puts the backup back before the DCIM rescan). The camera then scans, creates and saves under <root>/FILMS/ACRO001/100PHOTO and does not see the root's other folders. A new roll or another film (same film state) leaves the root alone; a root too long to extend (40+ characters) or a missing object leaves everything untouched. Rolls made by earlier builds sit in the root (PROV001, BLCH001, FILM001 ...): move them into a FILMS folder to see them continue. Unknown until flashed: whether the camera's folder creator makes the parent as assumed, whether anything else caches the root, and whether the free-space / card-info code is affected. (2) *Mode icon.* The mode dial's SCENE position (skin images 317 selected, 112 grey) reads FILM in the film build (`fuji_lv.FILM_BUILD`; preview docs/images/film-mode/mode_tags.png). The live-view mode icon (group 803 child 1, "P") still shows P because the camera reports SCENE as P to every reader: the item draws in 0xC04B7xxx-0xC04BAxxx do not call GET_SYSVAL(3) themselves (no hit in 0x300 bytes of any of the 50 item draws, none of the 104 reads of the mode is in that range), so the icon follows a GUI value whose source is not found yet. (3) *Overlay concept* (big cartridge with the shots left, wind-on and roll-full banners): see the investigation notes below. Tests: `python tools/test_film.py` (bad 0, with the parent-folder cases).

**FILM15 (`TL-F65f`, 7 Nov 2026, owner's card, NOT yet flashed): the freeze after a couple of shots, probably fixed.** Owner (FILM14): still the file error, and still a freeze after about the second shot, although the 3-drop was gone. Cause found by reading my own hook: `filmstate` (the entry of the state-change function, hit on every screen change, including after a shot) used r2 and r3 as scratch, but those are arguments of that function (callers pass 0, 0, and sometimes more), so the stock function ran with r2 = the vars address and r3 = 1. `filmstate`, `filmevent` and `filmstr` (GetStaticString) now use only ip before the stock code (`filmevent` keeps r0-r4 on the stack); the tests now check that r2 and r3 reach the stock function unchanged (`bad 0`; they would have failed on FILM12-14). The first freeze report was FILM13 (after the hook was added in FILM12). NOT fixed: the blue "File Error" screen on PLAY in SCENE (it also shows with state 5, 3 and the 0x11 event of handler 0xC0494984 dropped). Findings so far: PLAY is an event of type 0x11; the handler at 0xC0498EA8 answers types 1, 2, 0x11 with a request for 3, whose enter handler 0xC049D7E4 asks 0xC04A051C which screen comes next and requests 5 for code 0x13; request 7 follows 5 in the log and is probably the error dialog. The string "File Error" is SPID string 683, "No Image File" 721. Next step: find what else receives PLAY (the mode manager?) or let playback work in SCENE instead of blocking it.

**FILM14 (`TL-F65e`, 7 Nov 2026, owner's card, NOT yet flashed): PLAY event dropped at its handler; the state-3 drop removed.** Owner (FILM13): "No playback" shows, but the blue file-error screen still appears, and the camera froze after a couple of shots (the 3-after-12 drop: 3 is also requested after a shot, the review state `CAPPGUIPreviewState`). Static findings: PLAY is an event of type 0x11, not a key (so the live-view key dispatcher never sees it: why D06 showed no key number). The handler 0xC0494984 (event type via the event's method +8; r0 = state, r1 = event) answers 0x11 with a request for state 5, 5 (MENU) with 0x12, 0x10 and 1 with 12; the handler at 0xC0498EA8 answers 1, 2 and 0x11 with a request for 3 (probably the playback state's way back). `filmevent` replaces the entry of 0xC0494984: in SCENE an event of type 0x11 is dropped (returns 0, "No playback" pop-up), every other type runs the handler; `filmstate` keeps dropping a request for 5 and no longer touches 3. Unknown: whether the file error comes from this handler's path at all (it also appeared with state 5 and 3 dropped, so something else may react to the same PLAY event, for example the mode manager); if the blue screen still comes, the next step is to find what else receives event 0x11. Tests: `python tools/test_film.py` (bad 0, with the event-type tests).

**FILM13 (`TL-F65d`, 7 Nov 2026, owner's card, NOT yet flashed): PLAY in SCENE, second try.** FILM12 still gave the file error in SCENE (PLAY is fine in every other mode). Owner's D06 reading after PLAY, back to live view, AE-L: `S:12 11 03 07  T:05 03 12 11`, i.e. the requested state ids, oldest first: 11, 12 (live view), 03, 05 (playback), 07, 03, 11, 12 (the way back). So PLAY requests state 3 first and 5 second; FILM12 dropped only 5 and the camera stayed in 3, which already opens the file list. `filmstate` now also drops a request for 3 that directly follows 12 (vars[28] = the last request that went through); a 3 after any other state (the way back, a mode change: 12, 30, 3) passes. Unknown: whether that is exactly the PLAY path (a legit 12 -> 3 would be dropped too: if a screen sticks, that is why) and what 7 is. Owner (FILM12): the picker's live view behind the cards does not show the look (logged in the ROADMAP; not researched yet). Tests: `python tools/test_film.py` (bad 0).

**FILM12 (`TL-F65c`, 7 Nov 2026, owner's card, NOT yet flashed): no playback in SCENE.** Owner (FILM10): PLAY in SCENE gives a file error (the roll folder is the camera's folder there). The state-change function 0xC0491150(fsm, id) is hooked at its entry (`filmstate`, the diagnostic's hook site; the replaced `push {r4-r8,sb,sl,fp,lr}` runs at the pass-through): in SCENE a request for state 5 (Playback) is dropped, returns 0 and shows "No playback"; all other ids and all requests outside SCENE run the stock function. Unknown until flashed: whether the PLAY key reaches the Playback state through this function (the owner's FILM10 key readout showed no key number in playback, the D06 log is not read), and whether the caller copes with a dropped request. Owner (FILM11): Bleach Bypass still previews black and white (logged in the ROADMAP). Tests: `python tools/test_film.py` (bad 0).

**FILM11 (`TL-F65b`, 7 Nov 2026, owner's card, NOT yet flashed): Bleach Bypass previews desaturated, not black and white.** Owner (FILM10): the live view of Bleach Bypass looked black and white, the look is only very desaturated. Cause: the live CCMatrix stage (loader at 0xC044636C: `mla r7, slot, 0x24, table`, table pool word 0xC0447174 -> 0xC07B3C40, slot = byte 1 of the key built in the live default case) has 9 slots and none for FAUXJI's style 9, which was mapped to slot 1 (the B&W matrix) in FAUXJI8. The film build copies the 9 patched slots to a 10-slot table in the dead region (after block 1), appends Bleach Bypass's capture matrix as slot 9, redirects the pool word and changes the style-9 case's `orreq r0,r0,#0x100` (0x03800C01) to `#0x900` (0x03800C09). Film build only (film_mode.patch); the plain build is unchanged. Tests check the table, slot 9 and both words. Not done: previewing the look behind the picker (it needs the picker state's cursor-move handler: SelectScene state vtable near 0xC07C5844, not read yet; a diagnostic that logs its events would find it).

**FILM10 (`TL-F65a`, 7 Nov 2026, owner's card, NOT yet flashed): the scene picker is the film picker; rolls are named after the film.** Owner's D06 readings of the picker (cards left to right, modes): Beauty Shot 10, Night 12, Portrait 13, Children 14, Landscape 15, Close Up 16, Text 17, Sunset 18, Dawn 19, Backlight 20, Fireworks 21, Beach & Snow 22 (there is no 11). Each card is now one look: 10 PROVIA, 12 Bleach Bypass, 13 Nostalgic Neg., 14 ASTIA, 15 VELVIA, 16 Reala Ace, 17 Classic Chrome, 18 Classic Neg., 19 ETERNA, 20 ACROS, 21 Sepia, 22 PROVIA again. (1) *Look:* on the first key press after the pick (or whenever the card changes) `filmhook` maps the card (rawmode - 10 through a 16-byte table) to the look and applies it with the stock FILM SIM sequence (`applylook`: setUiValue 0x41, apply, menu masks, GUI event 0x42, two notifications). (2) *Roll names:* the folder is now four letters of the look plus a three-digit roll number, PROV001, BLCH001, NOST001, ASTI001, VELV001, REAL001, CCHR001, CNEG001, ETRN001, ACRO001, SEPI001, in the card's root (7 characters, the name buffer's size). Rolls are counted per film: a card change starts from roll 1 of that film and takes the first one with room, so a part-shot roll resumes when its film comes back and a film change mid-roll is allowed (that is the picker's job now). The pop-up reads "ACRO001 36 left". (3) *AE-L* no longer cycles looks in SCENE: it is swallowed (an empty roll: nothing, a part-shot roll: "Roll in use"), and on a full roll it starts the next roll of the same film. (4) *Cards:* film build only: SPID strings 19..47 (scene names) are the film names and their descriptions the blurbs; skin images 195-206 are cartridge cards (tools/badges.py `card`, 48 colours, fitted into the room up to the next image; the stock scene cards had shrunk the header sizes, so the room is measured from the offset table). Dead code region extended: the function at 0xC04274B8 (factory command switch) has no caller, FILM_END is now 0xC0427D24; `setnames` moved to the R5 block (R4 was full). Tests: `python tools/test_film.py` (bad 0, now with ldrb in the interpreter). Preview: docs/images/film-mode/film_cards.png. Not done: the single parent folder (the camera's folder creator may only make the last path part: untested), review lock, big counter screens, mode icon. Unknown until flashed: whether the picker's captions come from strings 19..47 (Beauty Shot and Dawn also exist as 119 and 369), and whether the card image sizes fit in the picker layout.

**FILM07 (`TL-F64g`, 7 Nov 2026, owner's card, NOT yet flashed): roll-full message, cartridge artwork, all 13 scene cards.** (1) *Roll full:* GetStaticString (0xC05BA87C, a leaf
function that every UI text goes through: r0 = string context, r1 = id, returns a pointer to the UTF-16 text) has its entry `mov r2,r0` replaced by a branch (`filmstr`): in SCENE,
for id 687 (SPID "Memory Full", the camera's message at 0 frames) it returns our text "Roll full - press AE-L"; every other id and every other mode falls through to the stock code
(whether the text fits the message box is not known: shorten it if it clips). (2) *Artwork:* `tools/badges.py` replaces the three skin icon sets of the looks (large 115 px menu icons
72-82, white 64 px live-view icons 414-424, grey 64 px "unavailable" icons 326-345) with the film cartridge of tools/film_mode_art.py (`cartridge()`: drawn large, hard edge against
the key colour, colours snapped; the 64 px sets use a flat field and no name, the grey set is the dimmed cartridge). All fit their slots (worst fill: large 86 %, white 91 %, grey 62 %).
Applied only with `--film` (`badges.DESIGN`), so a plain build stays byte-identical to FAUXJI63 (elf label byte only, ROM identical). Preview: docs/images/film-mode/film_icons_skin.png.
(3) *Scene cards:* the 13 scene cards are the modes 10..22 (the mode-change enter handler 0xC04CC140 takes the stored scene id, sysval 4, when the dial code is 9); the hooks now cover the
whole range (`filmget` reports any of them as P, the film hook enters film mode for any of them), before only the card numbered 10 did.
Not done yet (they need what the diagnostic below reads): skipping the scene picker, the review lock, the big counter / picker screens and the mode icon.

**FILM07 camera result (owner, 7 Nov): the cartridge icons "look great except they have no text, just the colors"** (the 64 px live-view / greyed icons were drawn flat on purpose: a horizontal code does not fit a strip about 14 px wide). **FILM08 (`TL-F64h`, owner's card):** the small icons now carry the look's code (STD, EB, NN, S, V, RA, Cc, Nc, ET, A, SEP) running VERTICALLY along the white strip (`vcode` in film_mode_art.canister, bottom-to-top like the names on the real cartridges; 3 letters over about 40 px of strip height), black on white, dimmed in the grey set. The 115 px menu icons keep the horizontal code plus the full vertical name. Slot fill with the text: large 86 %, white 99 % (the RLE is deterministic and the build refuses an icon that does not fit), grey 69 %. Preview: docs/images/film-mode/film_icons_skin.png (the bottom row is the white set at its real 1:1 size).

**DIAG06 (`TL-D06`, built, not on the card): state-change log for the scene picker and the review.** The camera's state machine is requested through 0xC0491150(fsm, id, ...) (133 callers;
fsm from 0xC04910D4). Known ids (parent, id; accessor): GUIState 2, Preview/review 3 (0xC049D254), SelectScene 4 (0xC049E780, parent 3), Playback 5 (0xC049C834), ViewfinderMain 12
(0xC049FC0C), Menu 18, ModeChange 30 (0xC049BA8C, parent 2). Three places request id 4: 0xC049870C (in a menu event function 0xC04984B0), 0xC049A320 (event function 0xC049A020)
and 0xC049D8D0 (a next-screen dispatcher 0xC049D7E4 that maps a code to a state: 0x13 -> 5 playback, 0x14 -> 0x11, 0x17 -> 0x20, 0x1A -> 4). The diagnostic hooks the function's entry and keeps
the last 8 requested ids; AE-L shows them (press 1: newest four as `S:` + four 2-digit ids, newest first; press 2: the four before as `T:`). The key / mode / dial readouts stay.
Plan: turn the dial to SCENE, press AE-L; shoot a photo and press AE-L (what the review does); press PLAY, press AE-L; read the ids: that gives the state id of the picker request
and of the review and playback entries, then patch those requests (picker -> straight to live view, review/playback -> swallowed in film mode).

**FILM06 camera result (7 Nov 2026, owner): it worked** (SCENE behaves like P). Roll folders, the new-roll key, the counter and the wind-on lock all work on the camera (FILM05 and earlier), and the SCENE-reads-as-P hook works on top of them.

**FILM05 camera result (7 Nov 2026, owner): it worked** (FILM001 filled with 36 photos, AE-L started FILM002). **Owner's requirement (7 Nov):** the SCENE position must behave like P
(program exposure with the 1/60 minimum shutter and auto ISO, the unlocked menus), not like a scene: the owner only ever picked a plain scene (portrait) to get
past the picker and wants none of the scene behaviour. **FILM06 (`TL-F64f`, owner's card, NOT yet flashed): SCENE reads as P.** The camera reads the shooting mode through
GET_SYSVAL(3) at 104 call sites (exposure, menus, item lists ...; GET_SYSVAL = 0xC048F81C, a wrapper over the raw getter 0xC049094C(index, &out)). A hook at the end of
GET_SYSVAL (0xC048F83C, `ldr r0,[sp]` -> branch to `filmget`; fp = the index) turns the value 10 (SCENE) into 2 (P) for index 3 only (a test checks every index and 15
values), so every reader sees P; the film code reads the real value with `rawmode` (the raw getter). Only the single value 10 is translated (the value the owner measured for
the SCENE position; other scene numbers, Smart Auto and every other mode are untouched). The scene picker still appears when the dial reaches SCENE (the owner picks any
card, it no longer matters). Expected: the same readings as P in the same light, the menus unlocked, the screen showing P's items and possibly P's mode icon. Unknown: whether the
exposure engine's own mode (AE sysinfo +0xA, 0 P, 2 A, 3 S, 4 M; the 1/60 floor and the zoom-shift skip are keyed on it) is derived through GET_SYSVAL(3): if SCENE still
meters like a scene, that is where to look next (no translation table was found by byte pattern, so it is code). Also unknown: whether anything in the scene-picker flow compares
the mode it stored with the one it reads back (a hang or a re-opening picker would show it). 1196 + 548 bytes; `python tools/test_film.py` covers filmget and the raw read.

**FILM05 (`TL-F64e`, 7 Nov 2026, built, owner's card, NOT yet flashed): roll folders and starting a new roll.** FILM04 plus: each roll is its own top-level folder
on the card, FILM001, FILM002 ... (flat, so no nested mkdir; the camera's folder creator makes it; playback never reads it). The name buffers are now
48 bytes (name 8 | "%s/FILMnnn" 16 | "%s/FILMnnn/100PHOTO" 24; the FMT2 pool points at buffer+24) and `setnames` writes the roll number (vars[16], 1-999) as three
digits with `strb`. `doswitch` (r6 = want film, vars[20] = new-roll request; out r0 = ok, r5 = files in the folder) finds the object, validates the chain,
commits the flag, then for film: starts at the cached roll (or 1), +1 if a new roll was requested, and PROBES upward: rescan FILMnnn, if it holds 36 or more
files (and fewer than 65536: a failure code or garbage stops the loop) look at the next one, capped at 999; if it ends on an EMPTY folder that follows a
full roll and no new roll was asked for, it steps back to the full roll (nothing starts silently; the probe has created an empty folder, harmless). The count
the rescan returns drives "Film nn left", the counter and the lock exactly as before. Film-look key (14, press) in SCENE, in `filmgate`: empty roll = free choice
(stock FILM SIM cycles the look); part-shot roll = swallowed with "Roll in use" (no mid-roll film change; releases pass); full roll (>= 36) = `doswitch` with a
new-roll request (FILMnnn+1, "Film 36 left" pop-up and redraw) and then the key goes on to the stock handler, so the look cycles: that is the picker for now.
Found by the tests: the gate's garbage-count check clobbered r1 (the key) before the tail call to the stock handler; it now uses ip. Code: 1176 bytes at
0xC0426F10 (extended to 0xC04274B8: the functions at 0xC04272C0 and 0xC04274B8 have no live caller, tools/liveness.py) and 508 bytes at 0xC0426C80 (R4).
`python tools/test_film.py` covers the probe cases (first roll, several full rolls, a new empty folder after a full roll, failure code, garbage, cap),
entering and leaving, the new-roll key, "Roll in use", the garbage count, a missing object, the clamp, shot detection, the lock and the dial. The owner's old
test folder FILM (3 photos) is no longer used. Test: SCENE, shoot, fill a roll (or watch the counter), AE-L when full.

**FILM03 camera result (7 Nov 2026, owner): the wind-on lock works** (shutter blocked after a shot until the front dial is turned right). One bug: the stock
bottom shots-left number did not show the right value until the first shot was taken, while the pop-up box ("Film 36 left", drawn directly) was right on the
half-press. Cause: the stock number is only recalculated (through `rollclamp`) when the icons are redrawn, and after the SCENE switch nothing redrew them
until a shot did. **FILM04 (`TL-F64d`, owner's card):** the switch now calls the full icon redraw (`DRAW_ICONS 0xC04B7444`, r0 = 0, as the FILM SIM button does
after changing a look) between arming the pop-up and drawing it, after the new state is committed (test_film.py checks the flag, files seen and lock at the
moment of the redraw, for entering and leaving SCENE). The switch still only happens on a key press after the dial moves (the mode dial raises no key
event): an idea for later is to run it right after the mode-dial event's stock handler (0xC04C2328 site) so the counter updates as soon as the dial moves.
The owner's backup of a full 36-photo test roll: C:\dev\TL-500ilm-test-backup\FILM-roll-20261107-2009 (outside the repo).

**FILM03 (`TL-F64c`, 7 Nov 2026, built, owner's card, NOT yet flashed): wind-on lock.** FILM02 plus: (1) shot detection: the shots-left hook also compares the DCF
list's file count [list+0x24] with the last one seen (vars[8]); a rising count means a photo was saved, so vars[12] (locked) is set; entering SCENE starts
unlocked (a loaded camera is ready for frame 1) with the count the rescan returned, leaving SCENE clears it; (2) `filmgate` replaces the dispatcher's
`bl 0xC04BFF98` at 0xC04C1944 ("is this key handled"; returning 0 swallows the key, the trick the old tilt code used for the VIDEO key): in SCENE and
locked it swallows presses of keys 10 and 11 in states 1 and 2 (the only states the stock key 10 / 11 handlers act on, so releases still pass and
nothing can stay "held") and shows the pop-up "Wind on >" (text slot 1, look 12); (3) `filmdial` replaces `bl 0xC04C06E0` at 0xC04C2228 (the click dial =
front dial event): when locked and the event's method +0x10 returns 1 (a turn to the RIGHT, `Dial C 1`) it clears the lock and shows "Wound"; it always hands
on to the stock handler. The code no longer fits in one dead region: the hooks and data are at 0xC0426F10-0xC04271FC (R5) and the shared routines (copy,
valid, findobj, rollclamp) at 0xC0426C80-0xC0426E04 (R4, free after `plzoom`). `python tools/test_film.py` covers shot detection, the gate for every key
and state, the dial for values 0-3 and the full cycle (shoot, locked, shutter blocked, turn left: still blocked, turn right: free). Unknowns: whether a
second shutter press can slip in between the exposure and the file being registered; whether key 11 is anything else (it is swallowed too); whether the
half-press is blocked cleanly (the pop-up should show). NOTE for testing: the owner's FILM folder holds 36 photos (a full roll, counter 0), so the folder
must be emptied or moved first.

**FILM02 camera result (7 Nov 2026, owner): the counter works.** In SCENE the shots-left number goes down with every shot (so [list+0x24] moves live, no
rescan fallback needed), and at 0 the camera shows its stock "Memory Full" message (SPID string 687) and will not shoot any more, so the 36-frame limit
is enforced by the camera itself. To do: that message must read as the film's ("Roll full, pick a new roll", on the canister art) while in SCENE and stay
"Memory Full" in every other mode: the string comes from the string manager's GetStaticString 0xC05BA87C, which can be wrapped to serve our own text for id 687
while the film flag is on (the name pop-up already does the same for ids 0xF000+ through STRWRAP).

**FILM02 (`TL-F64b`, 7 Nov 2026, built, owner's card): stage 2a = FILM01 + the camera's own shots-left number counts the roll.** FILM01 was tried on the
camera and worked: pressing a key in SCENE showed "Film 36 left", six photos went to FILM@PHOTO (valid 3648x2736 JPEGs, numbering continuous with DCIM:
683 then 684-689), and normal playback hid them. New in FILM02: `rollclamp` at the end of getRemainPhotoNum (0xC047B6B8, `add sp,sp,#0x58` -> branch) makes
the shots-left value min(stock, 36 - files in the roll) while in SCENE, the roll size being the DCF list's running file total [list+0x24] (the same value
Open returns; several functions in the DCF module add to it as files are registered, but that it moves live after a shot is NOT yet seen on the camera).
No pointers are trusted: object, manager and list are validated each call and r0 is left alone if any is bad. Test: in SCENE the small stock shots-left
number should read 36 minus the files in FILM (the owner's FILM folder holds 6 now, so 30), count down by one per shot, and at 0 it is unknown whether the
camera refuses to shoot (test it) or keeps shooting. Fallback if the number does not move after a shot: rescan on the half-press (Open returns the count).
Still not in: roll folders, wind-on lock, review lock, canister art (see the ROADMAP to-do), picker. `python tools/test_film.py` covers the clamp.

**FILM01 (`TL-F64a`, 7 Nov 2026, built and put on the owner's card, NOT yet flashed): film camera mode stage 1, SCENE saves into its own folder.**
Build: `python tools/build_fauxji.py <stock> <out> --film` (code `tools/film_mode.py`, 716 bytes in the dead factory region after `gate3`; the plain build
without the flag is still byte-identical to FAUXJI63 apart from the label). It is the FAUXJI63 firmware plus: (1) the key dispatcher's first call goes
through `filmhook`, which reads GET_SYSVAL(3) and, when the mode changes between SCENE (10) and anything else, (2) switches the camera's "DCIM" folder
name to "FILM" (or back) and rescans with CSFileList::Open(obj, type), and (3) shows "Film nn left" (36 minus the file count the rescan returns) or
"Film off" on the next key press (the stock key hook is skipped for that one key, it would hide the box at once). The name is switched by six code
pointers (pool words 0xC01AEC58, 0xC01B1210, 0xC01B181C, 0xC01B3664 = the "DCIM" string; 0xC01B10FC / 0xC01B1104 = the "%s/DCIM" and
"%s/DCIM/100PHOTO" formats) that now point at three RAM buffers holding the stock strings; in SCENE the buffers hold FILM. Verified: those six words
are the only references to those strings in the whole image; the build changes only the six pointers, the block, the key site and the label.
`python tools/test_film.py` runs the emitted code in the interpreter (enter, stay, leave, object found at any manager offset, stale or junk
cache, broken chain, bad manager, buffers equal to the stock strings, idempotent patch on the real image) after fixing the interpreter for
`stmdb sp!,{lr}` / `ldm sp!,{pc}` (capstone lists sp as an operand). Not in stage 1: roll folders (/FILM/R0001...), the 36-frame limit, the wind-on lock,
the review lock, canister screens, the film picker. Test on the camera: (a) P mode: shoot one photo, check it goes to DCIM as always; (b) turn to SCENE,
press any key (half-press the shutter): expect "Film 36 left"; (c) shoot 2 photos; (d) back to P, press any key: expect "Film off"; open playback: the old photos
are there, the 2 new ones are NOT; (e) on a PC: G:\FILM@PHOTO\SAM_nnnn.JPG should hold the 2 photos; (f) back in SCENE the pop-up should say 34 left.
Risks: a shot in SCENE could fail to save (the DCF list object has other state not yet checked), or the rescan could misbehave; P/A/S/M are untouched. Go back
by copying extracted/tl500_008264_FAUXJI63/EX1-DSP-SR-008264.elf to the card and flashing.

**Film mode prep, 6 Nov 2026 (static research + PC mock-ups, nothing flashed).**
- *Quick View (the picture review after a shot), statically.* Setup item `SETUP_MENU_Q_VIEW`: setup record at 0xC0917048 (0x28-byte records,
  name pointer at +0x10, setup index +0x18 = 0xA, UI id +0xC = 0x19A, max value +4 = 3: Off / 0.5 s / 1 s / 3 s; menu string 572, shown as
  "Image Disp."). The main UI setter 0xC048F630 only handles ids up to 0x101, so setup items (0x191-0x1AC) go through some other store that I
  did not find; the first record word is 0 for every item, so it is not obviously the live value. The review itself is the GUI state
  `CAPPGUIPreviewState` (descriptor 0xC07C5428, singleton accessor 0xC049D254, event handler 0xC049D294 which switches on the event type:
  5, 0x17 = key (key code - 0x64, 12 entries), 0x2B, 0x2C, 0x41). It is registered as state id 3 under id 2 by the builder at 0xC0491EA4 (registrar
  0xC0491E2C). Other states that matter: `CAPPGUISelectSceneState` (0xC07C580C, the scene picker, the natural host for the film picker),
  `CAPPGUIPlaybackState` / `PlaybackMainState` (the PLAY key target), `CAPPGUIViewfinderMainState`. The log string "SetDisplayEvent [to QView off]"
  (0xC07577C4) belongs to the display driver, not to the setting. Options for the review lock, cheapest first: (a) tell the user to set
  "Image Disp." to Off (no code, but global, not film-mode-only); (b) find the setup store and force the item to 0 on entering film mode, restore
  on leaving; (c) hook the Preview state's handler 0xC049D294 and swallow its events in film mode; (d) swallow the PLAY key in the live-view
  dispatcher (already hooked at 0xC04C1938) so playback cannot be entered.
- *Screens.* `python tools/film_mode_art.py docs/images/film-mode` draws four 640x480 mock-ups (docs/images/film-mode/): ready, wind-on
  needed, roll full, and the roll picker (11 looks, 4 x 3 grid). Canister at the right edge of the live view (150 px tall, 125 wide, 6 % of the
  screen; `CAN_H` in the script; 372 px, then 236 px, were too big because there is no viewfinder and the shot is framed on this screen).
  Design from photos of the real 35 mm cartridges (owner's reference photos of Velvia 100, Provia 100F and a Superia / QuickSnap row, plus Fujifilm's product pages): black plastic caps and spool knob; the paper label has a WHITE strip down the left with the frame count at the top (on the real cartridge the "36" sits there), and the film name vertical in white on the right, either on an identification-colour field (Provia: violet-blue) or on Fuji green with a colour band (Velvia: purple band, Superia: red band) over a green foot. Sampled: Fuji green about #1F963D, Velvia band #6352B1, black plastic #121317. Looks with no real stock behind them (Astia, Reala Ace, Classic Chrome, Eterna, Bleach Bypass, Sepia, Nostalgic Neg. from Pro 400H purple) use colours chosen to fit; the source per look is in `FILMS`. Fujifilm's logo is not used and its packaging typeface is not published (a search found nothing), so type was matched by eye against the owner's photos (docs/images/film-mode/font_compare.png): the printed names look like a Frutiger-style humanist bold sans, so the names are Segoe UI Bold squeezed to 88 % (`NAME_FONT`), the frame count stays in the tall narrow Bahnschrift Bold Condensed (like the printed "36"), and "Professional" would be Palatino Italic (`SERIF_IT`, not drawn at this size). Both fonts are Windows fonts: on other systems the script falls back to Bahnschrift, and a free Frutiger-like face (for example Open Sans or Hind) could be bundled later. The picker shows an info panel for the highlighted look (`INFO` in the script: kind, what it is, what it is good for), written from Fujifilm's own descriptions of the film simulations; the TL500 versions are approximations of them. The leader with
  sprocket holes comes out of the slit; wind-on icon (front dial wheel with a
  curved arrow) plus "WIND ON / turn the front dial" at bottom left; roll full greys the canister, shows 00 and "ROLL FULL / pick a new roll /
  press any button". The picker's "press the shutter to load" is a placeholder: the loading key is not decided.
- *What the real build needs from this.* The skin has no text size this big and no alpha, so: one RLE canister image without the number
  (magenta key colour, as tools/badges.py), 10 digit sprites for tens and ones placed over the white counter strip (two repurposed nodes), a dimmed
  canister for roll full, the wind icon as one image, and 11 small picker canisters (one per look, with the code in the window). Node count
  (2034) is fixed, so repurposed nodes are needed; the free-space audit says about 2.7 MB of skin can be repacked.

### 12. Night sky preset (M)
**Long Time Shutter** (stock up to about 16 s) plus Manual Focus and the 2 s timer.
One-press preset: focus infinity, 15-30 s, ISO 400, timer 2 s. Look for 30 s.
Combined with the intervalometer: star trails (stack on the computer).

### 13. Auto-rotate from faces (M, medium risk)
No orientation sensor (unless item 1 surprises us). Found so far:
- The JPEG writer takes EXIF Orientation from a data field (`[sl+0xE4]` in the writer
  0xC03773E0, tag case 0xC03779B4), not a constant; a second writer (0xC0383120,
  probably RAW or thumbnail) writes a constant 1.
- Face detection searches **upright, 90 left and 90 right** (3-angle detector at about
  0xC05901D0; face angle at about 0xC0596C64).
- Plan: at capture, if the face was found sideways, set Orientation 6 or 8 in both writers.
- **Needed first:** hold the camera vertically at a person: does the face box appear? If
  not, fall back to a quick "vertical" toggle (e.g. on a button).

### 14. Smile / self-portrait trigger, Fuji-flavoured (M)
**Smile Shot**, **Blink Detection**, **Self-Portrait** exist. Expose them in a clean menu:
"fire when someone smiles", "warn on blinks", "fire when a second face enters".

### 15. Fuji "film simulation" previews in playback (M)
In playback, show the film look a photo was shot with (MakerNote byte 15650 = look) as the
canister icon and name.

**Playback code map (3 Nov 2026, static research, nothing built):**
- Playback state `CAPPGUIPlaybackMainState::handle` = **0xC049C1D4** (jump table 0xC049C270; its name string sits at
  0xC049C6E0). Found with `tools/match_funcs.py` on the WB850F name. It draws items of the shared viewfinder item
  table (0xC09BDE20, 51 items: show/hide an OSD node by hash) and calls DRAW_ICONS 0xC04B7444 in the case at 0xC049C560 (event 2 per the FAUXJI22 notes).
- Playback layout = root group **1219** (nodes 1219-1750, 532 nodes, ~20 screens). The main photo screen looks like
  group 1220: text 1221 (top, 625x60) and bar 1222 at y 362 with text 1223. Groups 1224/1262 are the edit wheels.
- Node hash table (skin.bin +0x974760) is (hash, node id, pointer) triples. 136 playback nodes are referenced by
  code; the view code is about **0xC04AC000-0xC04B0600**, node pointers cached at `*0xC09B9760` (+0x20, +0x2c).
  Hash literals for 1221 / 1223 are at 0xC04ACAC8 / 0xC04ACACC and 0xC04AE490 / 0xC04AE330.
- Playback orientation fix exists in the same family: `PCBIEXIFParser::replaceOrientation` (see item 13).
- NOT found yet: where the small shot-info overlay is drawn; where playback parses the photo's MakerNote (we need
  byte 15650 = look); a free node to host a canister (best bet: repurpose an unused playback icon node, since the
  node count 2034 is fixed). Next: trace who calls the text writers on nodes 1221/1223, then the EXIF reader.
- **Follow-up trace (3 Nov, same day):** the shared viewfinder item table (51 items) draws LIVE-VIEW nodes only (root
  742; item 32 uses root 288), so playback info is NOT built from it, and the 11 item lists at 0xC09BDAD8 are all
  shooting-mode lists. The code at 0xC04AC654+ that I first took for the playback view is the generic list widget
  (rows of 0x30 bytes at *0xC09B8E60), and nodes 1221/1223 are only listed in node tables there. Text nodes carry no
  string id (set at run time), so the info text is written by code not yet found. WB850F names for the neighbours:
  CAPPGUIDCMView::drawPbStateIcon (0x4d8a68 there) draws thumbnail-grid state icons, CAPPGUIPreviewView is the
  review/live view; the single-photo overlay is probably the USL/CBIMM layer, i.e. more work than expected.
- Verdict: the canister in playback is a multi-session job with a real chance of failing; the layout-only part of item
  16 (text colours, panels, dialog styling, as in fauxji_layout.py) needs no code and is the cheap first step.
- Still unknown whether the canister is feasible; the restyle of the dialogs (groups in 1531+/1708+) is easier.

### 16. Playback screens restyle (M)
Fuji-style info overlay, index view, delete/protect dialogs (pop-up styling already done).

---

## Tier 3: big projects (L, medium-high risk)

### 17. Lightning trigger (L)
Point at the storm; fire when the sky lights up.
- **Building blocks:** **Motion Timer** already watches the live view frame by frame and
  fires by itself; the AE loop measures live brightness every frame.
- **Mode A, trigger:** fire when live brightness jumps above the running average by a
  set amount, then re-arm; strip shows ARMED and a strike count. Limited by shutter lag
  (about 0.1-0.3 s on a CCD compact), so it catches long and multi-stroke flashes.
- **Mode B, catch-all:** continuous 1-2 s exposures at low ISO, back to back; keep only
  frames brighter than the last few (delete the rest). Catches nearly everything.
- Needs: the capture-trigger call (find through Motion Timer / Smile Shot) and a hook in
  the live AE loop. Same engine gives **motion trigger** (wildlife, birds at a feeder).

### 18. MF focus assist: magnify + peaking (L)
Magnify the centre while turning the focus ring in manual focus (live-view zoom path
needed). Focus peaking (edge highlight) would need per-frame image processing: probably
too slow on this CPU; magnify is the realistic part.

### 19. Multiple exposure (L)
Fuji has double exposure. The TL500 has image blending for HDR and panorama. Plan:
shoot frame 1, show it ghosted over the live view, shoot frame 2, blend. Hard: needs the
HDR merge path and a live-view overlay.

### 20. In-camera RAW develop with film looks (L)
Fuji's "RAW conversion": re-render a RAW in another film look in playback. The camera
already re-processes images (Photo Style Selector in playback, Smart Filter, resize).
Plan: route a RAW through the capture pipeline with a chosen look. Hard but very Fuji.

### 21. Names on the FILM BKT 9-look chooser (L, later pile)
Grid = layout group 1207 (cells 1208-1216), filled by code; order is internal look 0-8:
PROVIA, ACROS, Eterna / Classic Neg., Classic Chrome, Reala / Velvia, ASTIA, Sepia.
Plan: a test build that shows key numbers, then track the cursor and show the name.

### 22. Pixel shift / handheld stacking for low noise (L, research)
Burst 10 fps exists. Average several frames to cut noise (night handheld). Needs
memory and merge code: research only.

---

## Polish backlog (any time)
- Shutter / aperture digit colours (cyan = adjustable, red = warning; keep or restyle).
- Startup "film loading" animation (menu animation format is decoded: JPEG frames).
- Retire leftover Samsung art: remaining scene photos, swirl, glossy bits (room audit in
  README: about 2.7 MB of skin can be repacked if new art needs space).

## Suggested next order
1. Flash and test **FAUXJI35** (zoom fix).
2. **Item 1** (Auto Rotate setting check) + the face-box test for item 13.
3. **Items 2-5** (grain, DR names, orange date, intervals): a fun batch.
4. **Item 13** auto-rotate, then **item 17** lightning trigger.

## Auto-rotate working notes (2 Nov, remote session)
- New helpers: `tools/armdis.py ADDR [n]` (disassemble at a runtime address; instruction
  addresses are file offset + 0xC0003FF5 with offset = 3 mod 4), `tools/xref.py ADDR` (BL/B callers).
- JPEG EXIF writer 0xC03773E0 is called only from 0xC0377F00 (r3 there = the info struct whose
  +0xE4 is the Orientation); 0xC0377F00 has no direct callers or pointer-table entries (reached
  via a computed call). The orientation read is `ldr lr,[sl,#0xe4]` at 0xC03779DC: patchable
  to read our own global instead (deterministic, needs no face detection).
- Face detectors 0xC05901D0 / 0xC0596C64 also have no direct callers.
- Two routes: (A) manual: a flag the user sets (Off / 90 CW / 90 CCW) feeds the writer;
  (B) automatic: face angle from the detector -> flag. B needs one on-camera fact first:
  does the face box appear when the camera is held vertically?

## FAUXJI38: tilt tag on any button (`TL-F38`) - test plan
(FAUXJI37 + the video button.) How it works: the AE-L Button menu setting picks what the AE-L
button does; its "TILT TAG" option (the old AE-L) cycles the tilt tag. That option and FILM SIM
are different options of the same setting, so they do not coexist on AE-L; pick one in the menu.
Better: any other button can be *learned* as the tilt button, so FILM SIM stays on AE-L:
1. Menu > AE-L Button > pick the FILM SIM option for normal use; pick TILT TAG once to get to
   the learn state: press the button repeatedly until the pop-up says "Tilt: press a key"
   (order: Off, Auto, Auto flip, top right, top left, press a key).
2. In that state press the VIDEO button: pop-up "Tilt key = NN" shows its logical key number
   (tell me NN: I will hard-code it so it survives power-off; until then re-learn each boot).
   If nothing happens, the video button does not go through the live-view key dispatcher.
3. From then on the video button cycles the five tilt states with the pop-up, and no longer
   starts a recording (its stock action is swallowed).
Then the tests: states 3/4 tag vertical shots as Orientation 6 / 8 (check on PC and playback);
Auto needs Face Detection ON and a few seconds aimed at the face (+-90 scan runs once per
13 detector frames); Auto flip if Auto is backwards; upright shots stay 1.
Facts behind it: live EXIF writer 0xC0385868 (constant 1 at 0xC0385F00), writers at 0xC03773E0,
0xC0383120, 0xC0388668 are dead (tools/liveness.py); stock detector SDIC_FaceDetection
0xC058F798 scans 0/-30/+30/-90/+90/-60/+60 degrees in a 13-call cycle (r6); hook at its end.
Risks: pop-up text from our own UTF-16 strings; face tag can go stale if FD is switched off
right after a sideways face.

## FAUXJI39: menu unlock (`TL-F39`)
Everything in the menus should now be selectable in P, A, S and M (scene, movie and Smart Auto keep
Samsung's limits). Test: switch P -> A -> M -> back, open the shooting menu: RAW, Face Detection,
the AE-L Button item etc. should never be grey. Report anything still grey (mode + item) or
any strange behaviour from an option that used to be blocked (e.g. RAW with burst).

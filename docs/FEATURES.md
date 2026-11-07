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
- **FAUXJI35 built and pushed, NOT flashed yet:** P/A keep 1/60 when zoomed (Samsung's
  zoom hand-shake shift skipped for AE modes 2 and 3). First thing next session: copy it
  to the card; test A mode, dark room, zoomed in: expect 1/60, not 1/125.
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
Not yet located in the TL500 .elf: a plain stride-pointer-table scan and an entropy scan found
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

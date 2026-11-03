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

# FAUXJI FILM PRO: feature list, easiest to hardest

A ranked plan of modern features for the Samsung TL500 (EX1), plus a **resume guide**
so a fresh session can pick up without the old chat. Everything here builds on what
the camera already has inside (found in its menu texts, layout tree and code).

Effort: **XS** under a session, **S** one session, **M** a few, **L** many.
Risk: how likely the camera fights us (unknown code paths, timing, crashes).

---

## Resume guide (read this first in a new session)

**Project:** Fuji-style firmware mod for the Samsung TL500 (EX1), firmware 008264.
Owner: economist, not a programmer: explain in plain language. Owner flashes; never
flash for them. Never redistribute Samsung firmware: share only tools and patches.
Ask before downloading anything.

**Repo:** github.com/Muxumuscode/fauxji-film-tl500 (private). Full log of findings:
`README.md` (long, chronological). Ideas summary: `ROADMAP.md`. This file: the plan.

**Build:** `python tools/build_fauxji.py extracted/tl500_008264 extracted/tl500_008264_FAUXJIxx`
(needs the owner's stock 008264 files in `extracted/tl500_008264/`, not in git). Then set
the version label (8 bytes at .elf file offset 0x792493, e.g. `TL-F36\0\0`) and copy the
five files (EX1-DSP-SR-008264.elf, SPID.Rom, ONBL1.bin, ONBL2.bin, FWUP) to the SD card
root (`E:` on the owner's PC). Commit and push after each build.

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

**Current state (2 Nov 2026):**
- On camera and confirmed: everything through FAUXJI34 (looks, menus, shooting screen,
  pop-ups, busy animation).
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

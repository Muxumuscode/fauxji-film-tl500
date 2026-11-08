# FAUXJI FILM PRO: what's next

Ideas for making this the coolest little firmware around, ranked by how much fun they are
against how hard they'd be on this camera. Every idea is built on something the TL500
**already has inside**, found in its own menu texts and code, so nothing here needs
hardware it doesn't have.

**Ratings.** Effort: S = a session or two, M = several sessions, L = a long project.
Risk = how likely it is to fight us (unknown code paths, timing, crashes).

---

## Status right now (2 Nov 2026)

| Item | State |
|---|---|
| 11 film looks, live preview, FILM SIM button with name pop-up | done, on camera |
| Fuji-style menus, shooting screen, mode dial, pop-ups | done, on camera |
| Minimum shutter 1/60 with auto ISO in P, A and S (the camera raises ISO, cap 1600, instead of slowing down); auto ISO in M | done, on camera |
| **1/125 problem fixed**: stock raised the minimum shutter to 1/125 and more when zoomed in (the zoom hand-shake shift) and with the flash; skipped for P, A and S since FAUXJI51 | done, verified on camera (FAUXJI54, "it worked great") |
| **Film camera mode** (`--film` build, latest TL-F65o) | working on camera, open items below |
| Auto-rotate | researching (see below) |
| Names on the FILM BKT 9-look chooser | later pile |
| Playback screens | later pile |

---

## Film camera mode: state and what is left (8 Nov 2026)

Build it with `python tools/build_fauxji.py <stock dir> <out dir> --film` (latest label **TL-F65o**; the plain build is unchanged and differs from
FAUXJI63 only in the version label). Notes per build are in docs/FEATURES.md (FILM01 ... FILM23), tests: `python tools/test_film.py`,
`python tools/test_film_layout.py <SPID.Rom>`.

**Works on the camera (owner-verified):** SCENE is the film camera and behaves like P (1/60 minimum shutter, auto ISO, menus open, macro / flash /
self-timer keys work); the scene picker is the film picker (12 cards = the 11 looks, PROVIA twice) with cartridge cards and film names; each roll is
its own folder named after the film (PROV001, ACRO002 ...) under `FILMS/` on the card, counted per film; shots left counts down and the counter is
right as soon as the dial moves; wind-on lock (front dial right); AE-L starts the next roll when full; "Roll full" text; no playback in SCENE; no
quick review after a shot; short texts for the display (up) key; FILM on the mode dial.

**Built, waiting for the owner's test (TL-F65o):** the look's cartridge in the bottom-left mode-icon spot (instead of "P"), the wind-on icon right
after a shot, the roll-full icon, all painted without waiting for a key.

**Left to do** (suggested order):
- [ ] **Lock ISO to Auto in the film camera, no way to change it (owner's decision, 8 Nov 2026).** Considered and rejected: a fixed ISO 400 for
  authenticity (the film feel), auto ISO capped at 400, and a speed chosen per roll. The owner chose plain Auto: the camera keeps choosing the ISO
  (80 to 1600 as in P) and the user cannot change it in this mode. Today the menu behaves like P, so ISO can still be changed there. Needs a
  menu-mask or setter hook (force the ISO setting to Auto and grey the item while a scene card is the mode).
- [ ] **Bleach Bypass previews black and white in live view** (the saved photo is right). TL-F65b gave style 9 its own live matrix slot (slot 9 of a
  relocated 10-slot table, key word 0x03800C09) and it did not help. Look for another live stage that desaturates for style 9 (live tone / PCSE / the
  invert stage at 0xC0447100), the key byte not reaching the loader (the slot is read as a signed byte), or the table pool word 0xC0447174 not
  being the one this path uses. A diagnostic that shows the live slot would settle it.
- [ ] **PLAY in SCENE shows the blue "File Error" screen** (the photos stay hidden, which is the goal). Dropping the PLAY event (type 0x11 in handler
  0xC0494984) and the state requests 3 and 5 did not remove it: something else reacts to the same press (the mode manager?). Wanted: a friendly
  "develop your film on a computer" screen instead. Note: dropping state 3 froze the camera after a few shots (3 is also the review after a shot).
- [ ] **Show the look behind the picker.** While the highlight moves over the film cards the live view behind should preview that film. Needs the
  SelectScene state's cursor-move handler (vtable near 0xC07C5844); not read yet. Probably needs a short diagnostic build that logs its events.
  Also check that the card captions really come from strings 19..47 (Beauty Shot and Dawn also exist as strings 119 and 369).
- [ ] **Big cartridge with the shots left inside** (owner's mock-up, docs/images/film-mode/film_sheet.png). TL-F65m moved the film icon (group 1009)
  and the digit group (797) out of their parents; the icon vanished (the OSD probably clips a node to its parent's rectangle). `film_mode.layout` and
  `badges.patch_big_cartridges` are kept in the tools, not applied. Ideas: keep everything inside the left column (100 px wide), or find a group
  that can host both. Also still open from the mock-up: a larger wind-on / roll-full banner with art (today: the small icon plus the text pop-up).
- [ ] **The live-view icon item** (the film cartridge in the left column) and the mode-icon spot both wait for redraws in places we do not hook;
  check TL-F65o on the camera first.
- [ ] **Housekeeping on the card:** rolls made before TL-F65i sit in the card root (PROV001, BLCH001, FILM001, FILM002 ...); move them into `FILMS`
  to continue them. The DUAL IS and "play" mode tiles are reused for the roll-full and wind-on icons in the film build (neither mode shows in the
  film camera's live view).
- [ ] **Take the film camera into the plain build as an option** ("Pick what you want": separate switches for the fixes, the Fuji extras and the
  film camera).

Older notes from the first film-mode items (all done or superseded) are in docs/FEATURES.md.


## Headline features

### 1. Lightning trigger
Point the camera at the storm; it fires the instant the sky lights up.

- **Building block:** the TL500's **Motion Timer**, which already analyses the live view
  frame by frame for movement and then triggers the shutter by itself. There's also a
  continuous live-view brightness measurement (the AE loop updates every frame).
- **Plan:** a "Lightning" drive mode that watches the live-view brightness each frame and
  fires as soon as it jumps by more than a set amount (for example +1 stop against the
  running average), then re-arms. The film-name strip shows "ARMED" and a strike counter.
- **The catch, honestly:** shutter lag. A CCD compact takes roughly 0.1-0.3 s to start the
  exposure after deciding to fire. Most lightning flashes last 0.2-1 s with several return
  strokes, so we'd catch many but not all.
- **Trick to improve it:** in a dark storm, use a 1-2 s exposure at low ISO and fire
  *back to back* continuously (like a film camera on bulb), keeping only frames with a
  strike. The brightness check after each frame decides keep or delete. That catches
  nearly everything and doesn't depend on lag.
- Effort **M-L**, risk **medium** (needs the capture-trigger call and the per-frame
  brightness hook).

### 2. Film roll mode ("36 EXP")
The most film-like feature possible: pick a roll of 24 or 36 exposures, and a frame
counter counts *down* on the shooting screen like a film camera. When the roll is done,
it's done: no more shots until you "load" a new roll from the menu. Optional: no
image review after the shot, so you can't chimp, just like film.
- **Building blocks:** the remaining-shots counter on the shooting screen (digits are
  images we already restyle), Quick View setting (review on/off), the file counter.
- Effort **M**, risk **low-medium**.

### 3. Orange date stamp, '98 style
The classic film-camera date in the corner, orange seven-segment digits, in the
photo itself.
- **Building block:** the TL500's **Imprint** setting (Off / Date / Date & Time) already
  burns the date into the JPEG. Its digit images live in SPID.Rom
  (`datetime_*.raw` and skin digit sets), so they can be redrawn as orange LCD digits,
  with a film-camera format like `'26 11 02`.
- RAW files are untouched (imprint is JPEG only), which suits how you shoot.
- Effort **S-M**, risk **low**. Probably the best fun-per-effort item on the list.

### 4. Intervalometer / time-lapse
- **Building block:** drive mode **Interval** already exists (1, 3, 5, 10 s between
  photos; "Interval shooting..."). The intervals are almost certainly a small table.
- **Plan:** add 30 s, 1 min, 5 min, and a shot count, for sunsets, clouds and stars.
- Effort **S**, risk **low**.

### 5. Night sky / long exposure
- **Building block:** **Long Time Shutter** (up to 16 s in stock) and Smart Night.
- **Plan:** look for a 30 s option and a "night sky" preset: manual focus to infinity,
  30 s, ISO 400, 2 s self-timer, our dark menus already help night vision. Combined with
  the intervalometer this gives star trails (stack the frames on the computer).
- Effort **S-M**, risk **medium** (the sensor's long-exposure noise handling may cap it).

---

## Fuji-flavoured extras

### 6. Auto-rotate for portrait shots (in progress)
- No orientation sensor, but the firmware has a **face detector that searches upright,
  90 left and 90 right**, and the photo writer takes its EXIF orientation from a data
  field instead of hard-coding it.
- Plan: when a face is found sideways, tag the photo as vertical (JPEG and RAW).
- Next step: on the camera, hold it vertically at a person. Does the face box appear?
- Fallback if not: a quick "vertical" toggle.
- Effort **M**, risk **medium**.

### 7. Recipes, Fuji style
Fuji shooters save "recipes": film look + white balance shift + tone + colour + sharpness
as a named preset. The TL500's C1/C2 custom slots (already renamed "C1 Recipe" /
"C2 Recipe") store full settings. Plan: ship a few classic recipes (Kodachrome-ish,
Portra-ish, Tri-X-ish) as one-press presets, and show the recipe name with the pop-up.
- Effort **S-M**, risk **low**.

### 8. Film BKT chooser with names
(later pile) Show the look's name under the cursor on the 9-look chooser.
- Effort **M**, risk **medium**.

### 9. Smile / face trigger
- **Building block:** **Smile Shot** and Blink Detection exist.
- Plan: a self-portrait helper (fire when a face smiles, or when a second face enters the
  frame). Mostly re-exposing Samsung's feature in a Fuji-style menu.
- Effort **S**, risk **low**.

---

## Pro tools

### 10. Live histogram and highlight warning
- A histogram display exists ("Displays histogram information."). Plan: make it the
  Fuji-style small white histogram, and add **blinking highlights** in playback.
- Effort **S-M**, risk **low-medium**.

### 11. MF assist
- Magnify the centre while turning the focus ring in manual focus. Depends on finding the
  live-view zoom path. Effort **M**, risk **medium-high**.

### 12. ISO ceilings / minimum shutter as menu settings
- Right now the 1/60 floor and ISO 1600 cap are fixed in the table. Plan: menu choices
  (1/30, 1/60, 1/125; ISO 800/1600/3200), the way Fuji's Auto ISO settings work.
- Effort **M**, risk **low** (the table is already understood).

---

## Polish still open
- Playback screens: Fuji-style info overlay and index view.
- Shutter/aperture digit colours.
- The 9-look chooser names (above).
- Startup: optional Fuji-style "film loading" animation using the menu animation format
  we decoded (frames as JPEGs).

---

## Suggested order
1. **P/A zoom fix** (flash FAUXJI35, test).
2. **Orange date stamp** (quick, high fun).
3. **Intervalometer** upgrade.
4. **Auto-rotate** (once the face-box test is done).
5. **Lightning trigger** (the big one).
6. **Film roll mode.**

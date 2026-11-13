# Sajin Genzō 사진現像

**A photo lab for your FAUXJI film rolls, and for photos from any camera.** 사진 (*sajin*) is Korean for photo, 現像 (*genzō*) is Japanese for developing: a Samsung
camera with Fuji film looks gets a half-Korean, half-Japanese lab. (Working name and Python package: `safelight`.) The FAUXJI film camera (the TL500's SCENE position) shoots rolls of 36 into `FILMS/` on the card and
won't show you a single frame. Sajin Genzō is the other half: it finds the rolls, lays them out as negatives on a light table, and develops
whole rolls the way a lab would, with the results as prints and a contact sheet.

Windows and Linux. Your originals are never changed.

## What it does

- **Two ways in.** The start screen asks how you want to develop your photos (tick the box to skip it next time; **PHOTO LAB /
  DARKROOM** at the top switches at any time, and the name at the top left goes back to the start screen):
  - **Photo Lab**, like sending a roll to a lab: drop off your photos (or pick a roll to reprint), choose one film (each previewed on
    your first photo), choose a lab (the lab looks and your own recipes, previewed too; print size and border), **Send to the lab**.
    The prints come back in full screen; export the roll as a folder or a zip, reprint with another film or lab, or open it in the
    Darkroom. Frames given their own settings in the Darkroom keep them, unless you tick to print every frame the same.
  - **Darkroom**: everything below: every setting, frame by frame, single prints, versions and picks.
- **Finds the rolls.** Put the card in the reader and start Sajin Genzō: it opens the card by itself (a `FILMS` folder at the root).
  Or use **Open folder…** for a card copy, a `FILMS` folder, one roll, or any folder of JPEGs.
  The film of each roll comes from the photos' EXIF (`TL500 Classic Chrome`, written by the camera since TL-F65q), older rolls fall back
  to the folder code (PROV, ACRO ...).
- **Light table, Lightroom-style.** The roll runs along the bottom as a filmstrip of developed negatives (orange-masked colour, grey B&W,
  sprocket holes, edge print, frame numbers). Click a frame and it fills the big view above, in the main window. Switch the big view
  between **NEGATIVE**, **ORIGINAL** (as the camera saved it) and **PRINT PREVIEW** (that frame printed with the current lab settings,
  following every change). Keys: **← →** frame, **Space** next view.
- **Full screen.** **⛶ Full screen**, the **F** key or a double-click puts the picture (light table or print) on the whole screen:
  **← →** step, **R / L** rotate, hold **Space** for the original, **I** for film, lab and date, **V** switches the view, **Esc** back.
- **Rotate.** The TL500 has no orientation sensor, so upright shots come out sideways. **⟲ Rotate left (L)** / **⟳ Rotate right (R)** sit
  above the picture (or right-click a frame). The turn is instant and shown ("↻ 90°", then a "Rotated 90° · saved" badge); it stays on
  the filmstrip, in previews, every development and the contact sheet. Prints are turned the same way in the PRINTS tab (the file and the
  contact sheet are rewritten a moment after the last click).
- **Every setting is explained:** hover over it, or open **? Lab guide**.
- **Authentic scan** (photos from other cameras; on by default, in the lab and in the Photo Lab's order): a film frame cannot hold a
  phone's hair-sharp detail or HDR range, so the lab softens the photo to what film could resolve (before the grain, so grain and detail
  belong together) and rolls the highlights off softly like a print. Untick it to keep every pixel.
- **The Film menu** is always in the lab. For your own photos it picks the film (a whole roll, or THIS FRAME); for a FAUXJI roll it is
  greyed out, because the camera already gave those photos their film's look. A folder of ordinary photos opened with **Open folder…**
  is loaded as your own photos, with the film to choose.
- **Phone photos come in upright** (the phone's orientation note is followed), broken files are left out, and very large photos
  are printed at up to 6000 px. iPhone HEIC photos open too (with the `pillow-heif` package, part of the requirements and the build);
  without it the app says to export them as JPEG.
- **Photos from any camera.** Drop photos or a folder on the window, or use **Load photos…**, to turn any photos (JPEG, PNG, TIFF, WebP, HEIC; any camera or phone) into a roll: choose the
  photos or a folder, name the roll, pick a film (or **Mystery**). Unlike the FAUXJI rolls, these photos have no film look yet, so the
  lab gives them the film's colour (an approximation of the in-camera looks) and then develops them the same way. The **Film** menu at
  the top of the lab changes a loaded roll's film at any time. So anyone who likes the processing can use the app.
- **Mystery rolls stay secret** (MYST001 ...): no film name anywhere until the roll is developed, then the reveal.
- **Vintage print by default.** Out of the box every roll is printed like a box of old-school prints: the film a few years past its date
  (faded blacks, a slight colour drift), a little more grain and halation, on **Vintage print** paper (colour slightly faded, blacks
  lifted, highlights warm, a soft fall-off at the edges) with a white border.
- **Recipe cards.** The **Recipe** menu has the lab looks for any film (Vintage print, Faded 70s snapshot, Clean lab print, Gritty push,
  Cross-processed, Darkroom fibre), cards for kinds of photography that come with their film (Portrait, Landscape, Street, Night & city,
  Summer snapshot, and for black and white: Silver gelatin, Dramatic sky, Gritty B&W street, Heirloom), and your own. **＋** saves the
  current settings as your own recipe (with the film, for your own photos); **⋯** imports, exports (to share) or deletes recipes. A
  card's film applies to your own photos; a FAUXJI roll keeps the film the camera gave it. Change any setting and it becomes Custom.
- **The lab**, applied to the whole roll:
  - development: pull −1, box speed, push +1 / +2 (denser, harder, grainier)
  - developer: standard, fine grain, high acutance (sharper edges), high contrast
  - process: normal, cross-processed, bleach bypass
  - expired film (0–30 years: fog, colour drift, more grain)
  - grain and halation strength (each film has its own; ACROS and Sepia have no halation)
  - light leaks: the first frame of every roll, later frames only now and then (about 1 in 20)
  - paper: vintage print, glossy, matte, warm-tone fibre, neutral fibre (black and white); border: none, white, black film-holder
    edge, instant-print frame
  - black and white: a coloured filter (yellow, orange, red, green; photos from other cameras) and toning (selenium, sepia)
  - lab correction (gentle auto levels), print size (full 3648 px, 2400 px, 1600 px)
  - **Surprise me** lets the lab pick.
- **Developing is animated** (tongs carry each print in and out, the picture comes up shadows first, the room light flashes on at the fixer, a darkroom clock
  runs the real step times, expired film is foggy, a light leak glows into the first frame; click to speed up, again to skip, move the mouse over the tray to rock it; sounds (a swish, running water, a bell; **♪ Sound** turns them
  off); at the end the lights come on and the prints fan out; a mystery roll's film name appears in red) in the big view: under a red safelight each print comes up in the developer tray (the liquid moving over
  it), goes through the stop bath, fixer and wash, and is hung on a drying line with a clothespin; a stage bar and the frame counter
  run along the bottom. Click to skip to the end.
- **Prints and contact sheet.** The prints tab works like the light table: the print big, the prints along the bottom. **Export prints…** copies them anywhere.
- **The Darkroom: frame by frame.** At the top of the lab, **WHOLE ROLL** / **THIS FRAME** says what the settings are for. Under THIS
  FRAME, anything you change (the film too, for your own photos) becomes the selected frame's own setting (● on the filmstrip); select
  several frames with Ctrl / Shift + click to set them together. Right-click a frame (or Ctrl+C / Ctrl+V) to copy its settings to
  others, or to give it the roll's settings again. **PRINT THIS FRAME** prints the selected frame(s) on their own: the single prints
  show in PRINTS, by frame, next to the frame's other prints, and can be exported one by one (right-click a print). **Develop roll**
  keeps every frame's own settings.
- **Versions.** Develop a roll as often as you like: every development is kept, named after its film, recipe and time (rename it,
  ★ favourite it, or move it to the Recycle Bin with **⋯**, which also shows the disk use and cleans up developments that are neither
  ★ nor hold a pick). **BY FRAME** shows every print of each frame across all developments: choose one with **✓ Use this print**, and
  **Export my picks…** exports one print per frame as a final roll. In full screen on a print, **C** compares it with another print of
  the same frame (drag the line; **↑ ↓** another one; side by side when the borders differ).
- **Lab log**: every development, how many frames, your favourite film.

## Download

Windows: **SajinGenzo.exe** from the [Releases page](https://github.com/Muxumuscode/fauxji-film-tl500/releases) (one file, no install;
Windows may warn that the app is from an unknown publisher: More info, Run anyway). Linux: build it (below).

> Not affiliated with Samsung or Fujifilm. Fujifilm's film names (Provia, Velvia, Acros, Classic Chrome ...) are their trademarks; they are
> used only to say which look each setting imitates.

## Photo Lab and Darkroom

Two ways of working for people without the FAUXJI camera (a simple lab order, and a darkroom with every setting per frame), with
versions, a full-screen viewer and your own recipe cards: the plan, what was built and what is left are in [WORKFLOWS.md](WORKFLOWS.md).

## Android (planned)

An Android version is planned for later: see [ANDROID.md](ANDROID.md).

## Where things go

The library (default `Pictures/Sajin Genzo`; a `Pictures/Safelight` library from version 0.1 is kept, change it with **Library folder…**):

```
<library>/<roll>_<date>/originals/              the camera's files, copied untouched
<library>/<roll>_<date>/develop-<time>/         frame_01.jpg ..., contact_sheet.jpg, labcard.json (what was done)
<library>/lablog.json
<library>/presets/<name>.json                   your own recipe cards
```

Developing a roll from the card imports it first, so the card can go back into the camera.

## Run from source

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt      # Linux: .venv/bin/python
.venv/Scripts/python -m safelight [folder]
```

## Build

- **Windows:** `powershell -ExecutionPolicy Bypass -File build.ps1` → `dist\SajinGenzo.exe` (one file, about 57 MB).
- **Linux:** `./build.sh` → `dist/SajinGenzo` plus `dist/sajingenzo.desktop` (copy it to `~/.local/share/applications/`).
  Build on Linux itself (PyInstaller does not cross-compile). Needs `python3-venv` and Qt's runtime libraries
  (Debian/Ubuntu: `sudo apt install libxcb-cursor0 libgl1 libegl1`).

Both scripts run the tests first.

## Tests

```bash
.venv/Scripts/python -m unittest discover -s tests       # 45 tests (and the GUI smoke test covers both ways in): card scanning, film detection, the lab, B&W, recipe cards, versions, the Darkroom, the library
.venv/Scripts/python tests/gui_smoke.py <out dir>         # the whole app headless, with screenshots
dist/SajinGenzo.exe --selftest <folder> <shot.png>         # a packaged build end to end (exit code 0 = good)
```

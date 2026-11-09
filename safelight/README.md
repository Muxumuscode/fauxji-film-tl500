# Sajin Genzō 사진現像

**A photo lab for your FAUXJI film rolls, and for photos from any camera.** 사진 (*sajin*) is Korean for photo, 現像 (*genzō*) is Japanese for developing: a Samsung
camera with Fuji film looks gets a half-Korean, half-Japanese lab. (Working name and Python package: `safelight`.) The FAUXJI film camera (the TL500's SCENE position) shoots rolls of 36 into `FILMS/` on the card and
won't show you a single frame. Sajin Genzō is the other half: it finds the rolls, lays them out as negatives on a light table, and develops
whole rolls the way a lab would, with the results as prints and a contact sheet.

Windows and Linux. Your originals are never changed.

## What it does

- **Finds the rolls.** Put the card in the reader and start Sajin Genzō: it opens the card by itself (a `FILMS` folder at the root).
  Or use **Open folder…** for a card copy, a `FILMS` folder, one roll, or any folder of JPEGs.
  The film of each roll comes from the photos' EXIF (`TL500 Classic Chrome`, written by the camera since TL-F65q), older rolls fall back
  to the folder code (PROV, ACRO ...).
- **Light table, Lightroom-style.** The roll runs along the bottom as a filmstrip of developed negatives (orange-masked colour, grey B&W,
  sprocket holes, edge print, frame numbers). Click a frame and it fills the big view above, in the main window. Switch the big view
  between **NEGATIVE**, **ORIGINAL** (as the camera saved it) and **PRINT PREVIEW** (that frame printed with the current lab settings,
  following every change). Keys: **← →** frame, **Space** next view.
- **Rotate.** The TL500 has no orientation sensor, so upright shots come out sideways. **⟲ Rotate left (L)** / **⟳ Rotate right (R)** sit
  above the picture (or right-click a frame). The turn is instant and shown ("↻ 90°", then a "Rotated 90° · saved" badge); it stays on
  the filmstrip, in previews, every development and the contact sheet. Prints are turned the same way in the PRINTS tab (the file and the
  contact sheet are rewritten a moment after the last click).
- **Every setting is explained:** hover over it, or open **? Lab guide**.
- **Photos from any camera.** **Load photos…** turns any photos (JPEG, PNG, TIFF, WebP; any camera or phone) into a roll: choose the
  photos or a folder, name the roll, pick a film (or **Mystery**). Unlike the FAUXJI rolls, these photos have no film look yet, so the
  lab gives them the film's colour (an approximation of the in-camera looks) and then develops them the same way. The **Film** menu at
  the top of the lab changes a loaded roll's film at any time. So anyone who likes the processing can use the app.
- **Mystery rolls stay secret** (MYST001 ...): no film name anywhere until the roll is developed, then the reveal.
- **Vintage print by default.** Out of the box every roll is printed like a box of old-school prints: the film a few years past its date
  (faded blacks, a slight colour drift), a little more grain and halation, on **Vintage print** paper (colour slightly faded, blacks
  lifted, highlights warm, a soft fall-off at the edges) with a white border. The **Look** menu has others: Faded 70s snapshot, Clean lab
  print, Gritty push, Cross-processed, Darkroom fibre; change any setting and it becomes Custom.
- **The lab**, applied to the whole roll:
  - development: pull −1, box speed, push +1 / +2 (denser, harder, grainier)
  - developer: standard, fine grain, high acutance (sharper edges), high contrast
  - process: normal, cross-processed, bleach bypass
  - expired film (0–30 years: fog, colour drift, more grain)
  - grain and halation strength (each film has its own; ACROS and Sepia have no halation)
  - light leaks: the first frame of every roll, later frames only now and then (about 1 in 20)
  - paper: vintage print, glossy, matte, warm-tone fibre; border: none, white, black film-holder edge, instant-print frame
  - lab correction (gentle auto levels), print size (full 3648 px, 2400 px, 1600 px)
  - **Surprise me** lets the lab pick.
- **Developing is animated** in the big view: under a red safelight each print comes up in the developer tray (the liquid moving over
  it), goes through the stop bath, fixer and wash, and is hung on a drying line with a clothespin; a stage bar and the frame counter
  run along the bottom. Click to skip to the end.
- **Prints and contact sheet.** The prints tab works like the light table: the print big, the prints along the bottom. **Export prints…** copies them anywhere.
- **Lab log**: every development, how many frames, your favourite film.

## Download

Windows: **SajinGenzo.exe** from the [Releases page](https://github.com/Muxumuscode/fauxji-film-tl500/releases) (one file, no install;
Windows may warn that the app is from an unknown publisher: More info, Run anyway). Linux: build it (below).

> Not affiliated with Samsung or Fujifilm. Fujifilm's film names (Provia, Velvia, Acros, Classic Chrome ...) are their trademarks; they are
> used only to say which look each setting imitates.

## Android (planned)

An Android version is planned for later: see [ANDROID.md](ANDROID.md).

## Where things go

The library (default `Pictures/Sajin Genzo`; a `Pictures/Safelight` library from version 0.1 is kept, change it with **Library folder…**):

```
<library>/<roll>_<date>/originals/              the camera's files, copied untouched
<library>/<roll>_<date>/develop-<time>/         frame_01.jpg ..., contact_sheet.jpg, labcard.json (what was done)
<library>/lablog.json
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
.venv/Scripts/python -m unittest discover -s tests       # 18 tests: card scanning, film detection, the lab, the library
.venv/Scripts/python tests/gui_smoke.py <out dir>         # the whole app headless, with screenshots
dist/SajinGenzo.exe --selftest <folder> <shot.png>         # a packaged build end to end (exit code 0 = good)
```

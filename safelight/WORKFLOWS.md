# Sajin Genzō for everyone: Photo Lab and Darkroom (plan)

Status: **built** (13 Nov 2026): every part below is in the desktop app; each section says what was done and what differs from the plan.

Sajin Genzō started as the other half of the FAUXJI film camera. Most people who would enjoy it do not have that camera: they have photos
from a phone or any other camera. This plan makes the app work as a film photo editor for them, with two ways of working:

- **Photo Lab**: like sending a roll to a lab. Few choices: drop off the photos, pick one film and one lab, get the prints back.
- **Darkroom**: everything adjustable, per frame, single prints, your own recipes.

A FAUXJI card is a *source* in both modes, not a third workflow (its film is fixed by the camera, so only the lab part applies).

## Audit before the first hands-on test (13 Nov 2026)

A code check and a walk through every screen found and fixed: phone photos loading sideways (the EXIF orientation is now followed);
thumbnails of the roll or development shown before landing on the next one; no way back to the start screen once skipped (the name
at the top left); grain / halation sliders with no value and deaf to keys and the wheel; the lab panel too tall for small laptop
screens (it scrolls; the window fits 1240 × 700); the tab names squeezed by a long roll name; exports always starting in the home
folder; the Mystery reveal on every re-development; the Photo Lab stuck on its animation after an error; broken files stopping a
whole development; no word about HEIC. Still open: HEIC support (needs the `pillow-heif` package).

## What is wrong today (for people without the camera)

1. **Camera first.** At start the app opens the card or the last folder; the empty view says "Open a card or a folder"; the FAUXJI buttons
   come first and **＋ Load photos…** is the third button, under an "ANY CAMERA OR PHONE" label (and again as the last line of LIBRARY).
2. **Photos open on NEGATIVE**, a fun view for camera rolls but not useful for a phone photo. ORIGINAL and PRINT PREVIEW are.
3. **"Import roll to library"** is shown for loaded photos, which are already in the library.
4. **The film is a plain dropdown** in the load dialog: you cannot see what it does to *your* photos until later.
5. **No full-screen view.** Prints are only seen in the PRINTS tab, squeezed between the roll list and the lab panel.
6. **One recipe for the whole roll.** No per-frame settings, no printing or exporting a single frame.
7. **Several developments of one roll are hard to tell apart.** Each is kept (`develop-<time>/`), but the picker shows only a time and a
   short description (not the film, which can change on loaded rolls); no rename, favourite, delete or compare.
   **Bug:** *Export prints…* names the folder `<roll>_<film>`, so exporting two developments with the same film to the same place
   overwrites the first one's `frame_01.jpg` ... (`app.py`, `export_prints`).
8. **Presets are fixed.** The six looks are in the code (`lab.PRESETS`); any change becomes "Custom", which cannot be saved.
9. **Black and white is a side effect.** The default *Vintage print* paper adds its warm tint after the B&W conversion, so Acros comes out
   warm by default. There is no neutral B&W paper, no contrast filter, no toning.

## Start screen

**Done 13 Nov 2026** (`photolab.StartPage`). It shows at every start, the last way used marked, unless *Next time, open straight in
the one I choose* is ticked; then the app opens in the remembered way. Photos dropped on the start screen go to the Photo Lab.

Two large cards when the app opens:

- **Photo Lab**: "Drop off your photos, pick a film and a lab, get prints back."
- **Darkroom**: "Every setting, every frame, your call."

If a FAUXJI card is in the reader, a small banner on top: "FAUXJI card found: 3 rolls". The app remembers the last mode and opens in it
next time; a switch in the header changes mode at any time. Both modes use the same library, rolls and prints.

## Workflow 1: Photo Lab

**Done 13 Nov 2026** (`photolab.PhotoLab`, covered by `tests/gui_smoke.py`). Step 1 also lists the rolls on the card and in the
library to reprint; a FAUXJI roll skips the film step. The lab step offers the lab looks and your own recipes (their lab settings;
the film is the one chosen in step 2); the previews of a Mystery roll use a neutral film so they keep the secret. The prints open in
full screen as soon as the first one is in. Darkroom settings: "N frames keep the settings given in the Darkroom", with a box to
print every frame the same (which clears them).

A short series of steps, no sliders.

1. **Drop off.** Drag photos or a folder onto the window, or **Choose photos**. Name the roll. This step fills the window, so nobody can
   miss how to bring photos in.
2. **Film.** One film for the whole roll, shown as cards, each previewed on *your first photo* (not a sample image). Mystery is one of
   the cards.
3. **Lab.** The lab presets and your own recipe cards as lab services ("Vintage print · 4×6 with white border"). Print size and border
   are part of the order.
4. **Send to the lab.** The developing animation, then a "Your prints are back" envelope that opens into the full-screen viewer.
5. **Collect.** Export the roll (a folder or a zip, with the contact sheet). Rotating is allowed here (sideways photos are common).

**Reprint with another film or lab** makes a new version; nothing is overwritten.

**Darkroom changes apply in Photo Lab** (decided). The film and lab picked in Photo Lab become the roll's defaults; frames changed in the
Darkroom keep their own settings on top. Because Photo Lab hides per-frame settings, it says so before sending: "4 frames keep their
Darkroom settings", with **Use the same settings for all** to clear them.

## Workflow 2: Darkroom

**Done 13 Nov 2026**, in the current window (the start screen that chooses between Photo Lab and Darkroom comes with the Photo Lab
steps). WHOLE ROLL / THIS FRAME at the top of the lab; frames' own settings in `<library>/frame_settings.json` (a FAUXJI frame's own
film is ignored: the camera's counts); single prints in `<roll>/darkroom/`, a mystery roll is revealed by its first print, single or
whole. Before / after is the full screen's held Space (and ORIGINAL on the light table). Mystery per frame was left out: Mystery is
chosen for a whole roll.

The current three-panel layout (rolls, light table, the lab), plus:

- **Roll defaults and frame changes.** The roll has a default film and lab settings; any frame can change either. Changed frames get a dot
  on the filmstrip.
- **Copy / paste settings** between frames, and **apply to selected frames**.
- **Print** one frame, the selected frames, or the whole roll. **Export a single print.**
- **Before / after**: hold a key to see the original, also in full screen.
- **Save as recipe card** from the lab panel.
- Loaded photos open on PRINT PREVIEW; NEGATIVE stays as an optional view.

## Versions: several developments of one roll

**Done 13 Nov 2026** (covered by the unit tests and `tests/gui_smoke.py`). Picks are kept per roll in `<roll>/picks.json`; a
development's name and ★ in its `labcard.json`, which also records the recipe card it was made with (`look`). Compare draws one print
over the other with a split line when both have the same shape, side by side when they do not (another border). Single Darkroom prints
join the by-frame view when the Darkroom is built.

On disk, keep one folder per development (`develop-<time>/` with `labcard.json`), which stays compatible with the Android plan.

- **The version list holds whole-roll developments only**: every Photo Lab run and every *Print roll* in the Darkroom.
- **Single prints only appear in the "by frame" view** (decided). They go to a per-roll darkroom folder as numbered versions of each frame
  (frame 7: v1, v2, v3), each with a small lab card (film and settings), so you can see how it was made and print it again.
- **Names**: each version is named automatically from film, look and date ("Acros · Silver gelatin · 13 Nov"). Rename, ★ favourite, and
  delete (to the Recycle Bin).
- **By frame view** in PRINTS: each frame with all its prints stacked ("3 prints"), from any development or single print. Pick the best
  one per frame, then **Export my picks**: a final roll mixed from several versions.
- **Compare** a frame across two versions with a split slider, in full screen.
- **Export folders carry the version name or date** (fixes the overwrite bug).
- **Disk use per roll** is shown (36 full-size prints are about 100 MB or more), with a clean-up.

## Full-screen viewer (both modes)

**Done 13 Nov 2026** (`viewer.FullScreen`, covered by `tests/gui_smoke.py`). It follows the light table's big view in whatever view is
chosen (**V** switches it) or the prints; Photo Lab opening it when the prints are back comes with the Photo Lab steps.

Open by double-click, **F**, or a button on the picture. **Esc** closes, **← →** next / previous, **R / L** rotate, hold **Space** for the
original, **I** shows film, recipe and date. Works on the light table (print preview) and on prints. Photo Lab opens it when the prints
are back.

## Mystery film (both modes, decided)

- Offered in Photo Lab and in the Darkroom.
- **Revealed at the first print**, single frame or whole roll.
- In the Darkroom the print preview shows the mystery film's real colour (the name stays hidden): accepted, since you adjust by eye there.
  Photo Lab has no preview of the film, so the surprise stays complete.
- Possible extra for the Darkroom: **Mystery per frame**, every frame its own secret film.

## Recipe cards (presets)

**Done 13 Nov 2026** (`recipes.py`, the B&W additions in `lab.py`; covered by the unit tests and `tests/gui_smoke.py`), with one extra
built-in B&W card, **Dramatic sky** (Acros, red filter, selenium). Photo Lab's "My recipes" lab services come with the Photo Lab steps.

Two layers, kept visible: **film** (the stock's colour and tone, `lab.LOOKS`) and **lab** (development and printing, `lab.Recipe`).
A preset is a **recipe card**: lab settings plus an optional film.

- Name, a short note, and a tag for what it is for (portrait, landscape, street, night, B&W ...).
- Stored as JSON files in the library (`<library>/presets/`), so they can be shared (export / import a card) and used on Android later.
- **Store the film as its code** (`ACRO`), not its name, so renaming the films for Android does not break saved or shared cards.
- On a FAUXJI roll the card's film is ignored (the camera fixed it), and the app says so.
- Built-in and own cards appear in both modes; in Photo Lab yours show as lab services under **My recipes**.

### Built-in cards by kind of photography

| Card | Film | Lab |
|---|---|---|
| Portrait | Astia / Reala Ace | fine grain, matte, no leaks, gentle auto levels |
| Landscape | Velvia | fine grain, glossy, no leaks, no border |
| Street / documentary | Classic Chrome | push +1, glossy, black film edge |
| Night & city | Eterna | push +1, strong halation |
| Summer snapshot | Classic Neg. | Faded 70s, instant frame |
| **Silver gelatin (B&W)** | **Acros** | fine grain or high acutance, **neutral** paper, black edge, expired 0, no leaks, grain about 1.1 |
| Gritty B&W street | Acros | push +2, high-contrast developer, grain 1.4, glossy |
| Heirloom | Sepia | warm-tone fibre, matte, expired about 10 |

### Black and white needs three lab additions

- **Neutral paper** (for example *neutral fibre*), so B&W is not warmed by the vintage paper.
- **Contrast filter**: none, yellow, orange, red, green, which change the B&W channel mix (red: dark skies, smooth skin), as in a real
  darkroom.
- **Toning**: none, selenium, sepia.

## Quick wins (useful whatever is built first)

**Done 13 Nov 2026** (covered by `tests/gui_smoke.py`). A FAUXJI card copy dropped on the window opens as a card; anything else
opens Load photos with the photos filled in.

- Drag and drop photos onto the window.
- Do not auto-open the last folder for people who do not use the camera.
- Hide *Import roll to library* for loaded photos.
- PRINT PREVIEW by default for loaded photos.
- Fix the export overwrite bug.

## Suggested order

1. Quick wins and the export fix.
2. Full-screen viewer.
3. Recipe cards (save / load / built-in by kind) and the B&W additions.
4. Versions: names, favourite, delete, the by-frame view, Export my picks, compare.
5. Darkroom: frame changes, copy / paste, single prints.
6. Start screen and the Photo Lab steps.

## Queue (agreed 13 Nov 2026, not started)

**Developing animation: make the fun part cooler.**
Done 13 Nov 2026 (`viewer.Canvas`): prints come up shadows first, then mid-tones, highlights last; the room light flashes on at the
fixer; dust drifts in the safelight beam; a click speeds the animation up and a second click skips the rest (hint at the bottom edge);
it shows the user's choices: expired film comes up foggy and clears, a light leak glows into frame 1, black and white runs under a
dimmer red, cross-processing in a green developer.

Also done 13 Nov 2026: tongs carry each print in and lift it out; a darkroom clock beside the tray shows the real time of each step (the
developer's follows push / pull: 5:30 pulled, 7:00 box speed, 9:00 / 11:00 pushed) with a sweeping hand; drips from the pegged prints;
steam over the developer and the fixer.

Also done 13 Nov 2026: sounds made in code (`sounds.py`: a swish as a print goes in, running water in the wash, the bell at the end, no
sound files; the *♪ Sound* button in the header turns them off); the finale (lights on, the prints leave the line and fan out over the
tray, then the next screen); a mystery roll's film name in big red letters in the finale (before the reveal window); moving the mouse
over the tray rocks it (bigger waves, the print sways).

Still in the queue: a GPU tray with real reflections (a bigger job: it means moving the animation to a GPU widget).

**Scan authenticity: DONE 13 Nov 2026** (`lab._soften`, `lab._shoulder`, `Recipe.authentic`; unit-tested). The idea was: soften and resample very sharp, high-resolution or
HDR photos to a film-scan-like effective resolution *before* the grain, add a highlight shoulder and a shorter, lifted tonal range, and
keep the processing in float (no real data loss). A setting such as *Authentic scan* (default on in the Photo Lab, a plain choice in
the Darkroom), with a way to keep every pixel.

## Decided

| Question | Decision |
|---|---|
| Darkroom frame changes in Photo Lab | They apply (Photo Lab says how many frames keep their own settings) |
| Single Darkroom prints | Only in the by-frame view, not in the version list |
| Mystery film | In both modes; Darkroom preview shows the colour, not the name |
| Fuji film names in recipe cards | Kept for now; renamed for the Android version (cards store film codes) |

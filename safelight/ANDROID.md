# Sajin Genzō for Android: project plan (for later)

Status: **planned, not started** (9 Nov 2026). The desktop app (this folder) is the full version and the reference for everything below.

## The decision

A **native Android rewrite** (Kotlin, Jetpack Compose), with the image processing on the **GPU** (AGSL / OpenGL ES shaders). Not a port:
Python on Android (PySide6 for Android, Kivy, BeeWare) means big, slow, fragile apps. If an iPhone version is wanted too, **Flutter**
(one codebase, image processing in fragment shaders) is the alternative, at a somewhat higher cost for the image work.

What carries over is the *what*, not the code: every recipe in `safelight/lab.py` is simple per-pixel math plus blurs, and is the
specification for the shaders.

| Desktop (`safelight/lab.py`) | Android |
|---|---|
| `film_look` (saturation, contrast, split toning, B&W mix) | one fragment shader with per-film uniforms (`LOOKS` table as data) |
| `develop`: push/pull curve, developers, cross / bleach, expired fog and cast, paper | the same shader (all per-pixel) |
| halation (threshold + blur + red) | two passes: threshold, separable Gaussian blur, add |
| acutance (unsharp mask) | blur pass + combine |
| grain (clumpy noise scaled to 3648 px) | noise texture / hash noise in the shader, clump size from the output width |
| light leaks (frame 1, then 1 in 20, seeded per roll) | gradient in the shader; same seeding rules (`_seed`) so results match |
| `negative` (orange mask / grey) | tiny shader for the light table |
| `bordered`, `strip`, `contact_sheet` | Canvas drawing (Android `Canvas` / Compose `DrawScope`) |
| `Recipe`, `PRESETS`, Mystery, rolls of 36, rotation memory | plain Kotlin data classes; same JSON lab cards, so libraries can be shared |

Expected speed: a 10 MP frame in well under a second on a mid-range phone (the desktop needs about 3 s on the CPU), so the print
preview can follow sliders live.

## What the phone version does

1. **Photos in.** The system photo picker (gallery, Google Photos): the main use on a phone ("Load photos" on the desktop).
   FAUXJI rolls: from a USB card reader (OTG) through the Storage Access Framework, or from a copy of the card on the phone
   (the TL500 has no Wi-Fi). Same `FILMS/<CODE><nnn>/` rules as `card.py`.
2. **The light table.** Big view on top, a swipeable filmstrip below, NEGATIVE / ORIGINAL / PRINT PREVIEW, rotate buttons and gestures.
3. **The lab** in a bottom sheet: Look, Film (loaded photos), development, developer, process, expired, grain, halation, leaks, paper,
   border. Vintage print is the default, as on the desktop.
4. **Developing** a roll as a WorkManager job with a progress notification (so it survives the screen turning off), with the darkroom
   animation in the app (tray, stop / fix / wash, drying line).
5. **Prints** saved to a "Sajin Genzō" album (MediaStore), contact sheet, share sheet, lab log.

## Milestones and rough effort (one experienced developer)

| | Scope | Effort |
|---|---|---|
| 1. MVP | photo picker → film + vintage look → develop a roll on the GPU → prints in the gallery | 2–3 weeks |
| 2. Full | light table, negatives, rotation, Mystery, the developing animation, contact sheets, lab log, FAUXJI cards over OTG | +3–5 weeks |
| 3. Store | polish, testing on several phones (GPU differences), Play listing, privacy policy, signing | +1–2 weeks, $25 Play account |

## Before publishing on the Play Store

- **Film names.** Provia, Velvia, Astia, Acros, Classic Chrome, Eterna are Fujifilm trademarks, and the store acts on trademark
  complaints. Use own names that describe the look (for example "Slide 100", "Vivid 50", "Portrait 160", "Mono 100", "Chrome") in the
  store build. The FAUXJI branding is close to Fujifilm too: keep it out of a public listing. (Fine for personal builds and GitHub,
  with the disclaimer.)
- **Privacy.** Everything stays on the phone: no network permission needed. Say so in the listing.

## Open questions

- Android only, or Android + iPhone (Kotlin vs Flutter)?
- Should a roll developed on the phone and one developed on the desktop give the same prints (shared seeds and recipes)? Recommended:
  yes, keep `labcard.json` compatible.

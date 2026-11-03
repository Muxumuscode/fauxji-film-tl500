# FAUXJI FILM PRO: custom firmware builder for the Samsung TL500 / EX1

A hobby project that patches **your own** official Samsung TL500 firmware (version **008264**) into a
build with Fuji-style film looks, restyled menus and a few genuine shooting fixes.
**No Samsung firmware is included here.** This repository only holds the build tools and the patches.
The tool refuses any input that is not the exact official 008264 file set (it checks SHA-256).

> **Read this first**
> - Flashing modified firmware **can brick your camera**. Use a fully charged battery and keep your own
>   untouched copies of the official files, so you can put them back.
> - Everything here is **at your own risk**, with no warranty. Not affiliated with Samsung or Fujifilm.
>   The film names are a homage.
> - Tested by one person, on **one TL500 running 008264**. If your EX1 has a different firmware build, the tool
>   will refuse it. Please do not try to force it.

## What it does

Confirmed working on the author's camera:
- **11 film-style colour looks** with live preview, switched with the **AE-L button**, with a name pop-up.
- **Fuji-style menus, shooting screen and mode dial**, new boot screen and shutter sound.
- **P/A modes keep a usable minimum shutter (1/60)** and **Auto ISO works in M**.
- **Vertical-shot tag.** The camera has no tilt sensor, so the build uses its face detector: a portrait
  held vertically is tagged as such in the JPEG (EXIF Orientation 6 or 8), and **VIDEO** cycles
  Off / Auto / Auto flip / top right / top left by hand.

Built in but only lightly tested or not yet verified on a camera:
- A small on-screen **tilt indicator** (text and an arrow) at the bottom-left.
- All menu options **unlocked in P/A/S/M** (no more greyed-out RAW or Face Detection); seems to work.
- P/A keeping 1/60 when zoomed in.
- A **0.3 EV darker metering bias** for highlight protection. To turn it off, set `AE_BIAS = 0` in
  `tools/fauxji_rot.py` before building.

Things that are *not* in this camera, whatever the menu text suggests: an AE-L button assignment menu
and a three-step D-Range (those strings are leftovers from other Samsung models).

## How to build

You need Python 3.11 and `pip install pillow numpy capstone`, plus **your own** untouched official
008264 files in one folder: `EX1-DSP-SR-008264.elf`, `SPID.Rom`, `ONBL1.bin`, `ONBL2.bin`, `FWUP`.

```
python tools/build_fauxji.py path/to/stock path/to/output
```

Copy the five files from the output folder to the root of a FAT32 SD card and power the camera on
to flash, the same way as an official update.

## What is where

- `tools/`: the build tool and generators (colour looks, menu art, boot screen, sounds, tilt tag, UI).
- `patches/`: the program patches and menu text changes.
- `RESEARCH-LOG.md`: the long, chronological log of how the firmware was figured out.
- `FEATURES.md`, `ROADMAP.md`: the plan and the ideas list. `TEST-PLAN.md`: an old (historical) safety plan.

## Feedback

Bug reports and test results are welcome in the issues, especially from anyone who knows these cameras'
internals or has a different firmware build. Licence: MIT (the tools and patches only; Samsung's firmware
stays Samsung's).

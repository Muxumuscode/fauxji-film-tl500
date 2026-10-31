# Samsung TL500 / EX1 firmware research

Goal: understand the camera's firmware and judge whether adding features is feasible.
Rule: no Samsung firmware is ever redistributed (`firmware-original/`, `docs-original/`, `extracted/` are git-ignored). Only notes, patches and tools are shared. Nothing here is flashed to a camera.

## Where the firmware comes from
Samsung's Africa EX1 support page still hosts the files on Samsung's own server:
https://www.samsung.com/africa_en/support/model/EC-EX1ZZZBPBZA/

| Version | Date | File | Size |
|---|---|---|---|
| 108091 | 16 May 2011 | EX1_DSP_G_SR_F108091.zip | 42.4 MB |
| 110271 | 2 Feb 2012 | EX1_DSP_G_S1_F110271.zip | 42.5 MB |
| guide | 2012 | EX1_Firmware_manual_eng.pdf | 0.19 MB |

Samsung's guide says 110271 is for cameras with a changed hardware part ("after part change"); if 110271 refuses to install, the camera is a "before part change" unit and 108091 is its latest. Older 2010 builds (005251/005254/006254/006291) are not on Samsung's site.
Open question: the files are listed for the EX1, and the owner's camera says TL500. The two are the same hardware sold under different names but had separate firmware builds; whether these files are accepted by a TL500 is unknown.

## How to see the camera's current version (safe, no flashing)
Per Samsung's guide: put a card containing the firmware files in the camera and power it on. A blue "FW Version" screen shows `DSC: FULL <current> -> <new>`. Do not press the shutter; just turn the camera off. (Be careful: the shutter button starts the update.) This is only a view of the version, but use a fully charged battery anyway.

## Owner's camera (checked 2026-10-31)
The camera's FW Version screen showed `DSC: FULL 008264`, OIS 1.0 (a TL500). 008264 appears to be the latest TL500 build (Samsung's TL500 firmware manual, via manualslib, describes 008264 as the update; US model only). Numbering pattern (inference): TL500 builds end in 4 (005254, 006254, 008264), EX1 builds end in 1 (005251, 006291, 108091, 110271). So the downloaded files are EX1 builds and must NOT be flashed to this camera.
Samsung's US and Canada TL500 support pages list no files any more. A third-party copy of the old TL500 005254 exists on userdrivers.com (unverified). The 008264 file itself was not found online; the camera already runs it.
Consequence: for reverse engineering, 108091/110271 (same VxWorks code family) are good stand-ins; a dump of the camera's own firmware is a later problem.

## First structure analysis (plain language)

**Package layout**
- 108091 (old style) is 5 files: two small boot loaders (`ONBL1.bin` 520 bytes, `ONBL2.bin` 62 KB), the main program (`EX1-DSP-SR-108091.elf`, 10.6 MB), a data file with pictures, sounds, menus (`SPID.Rom`, 69 MB), and a tiny instruction file `FWUP` ("upgrade all"/"keep").
- 110271 (new style) is a single 80 MB `.bin` that bundles the same parts, with a small table at the start listing each part by name (ONBL1, ONBL2, main image, `RomFS/SPID.Rom`, `EX1.HEX`).
- The ".elf" is not a real ELF file. It is a raw ARM program image with the version string "108091" glued on the front.

**What runs on it**
- The main program is raw ARM machine code, and it is **not compressed and not encrypted** (entropy 5.9, typical of plain code; the boot loaders start with normal ARM instructions).
- It is the **VxWorks 6.6** real-time OS (strings include Wind River paths). So it is not Linux, but it is a well-known OS and the file carries a lot of readable debug text (function and error names such as `INT_SetICCR`, shading tables, MP4/WAV handling). That is a big help for reverse engineering.
- The 69 MB `SPID.Rom` and the 80 MB bin contain compressed media (high-entropy sections are probably images/sounds) next to readable filenames (`skin.bin`, `.snd`, `.JPG`).
- Earlier "RSA/SHA" string hits were false alarms (words like "SHADING"). No signature or key text was found.

**Not yet determined (most important unknown)**
- Whether the camera checks a checksum or signature on the file. The guide mentions an ALZip-format `.bin`, which hints at a packed container, but I have not yet found a checksum field. The 110271 header has size/offset-looking fields still to decode.

## Feasibility (first impression)
- Reading and understanding the code looks **quite feasible**: plain ARM code, VxWorks, lots of symbols/strings, Ghidra can load it directly.
- Making the camera **accept a modified file** is still unknown. Positive signs: no encryption, simple "put a file on the SD card" updater, readable container table. Risks: possible checksum/CRC per part (should be fixable), or a signature check inside the boot loader (would be a hard stop, and bricks if wrong).
- Brick risk is real: Samsung's own guide warns a failed update can need a board repair. Test only on a spare body.

## Recommended next steps
1. Owner: check the camera's current version (above) and confirm if EX1 files are accepted by a TL500 (do not press shutter yet).
2. Install Ghidra (needs Java 17, already on this PC) and load the main image as raw ARM at the right base address (found from the boot loader).
3. Decode the 110271 container table and look for CRC/checksum fields; compare 108091 vs 110271 to see what differs.
4. Read `ONBL2.bin` (62 KB, small) to see how it verifies the upgrade file. That decides feasibility.
5. Look for a recovery or serial/debug mode before any flash test (hidden USB port mentioned in forums).

Tools: `tools/analyze.py` (entropy/strings summary).

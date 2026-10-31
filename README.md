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

## Sourcing the TL500 firmware (hunt results, 31 Oct 2026)

Tried to find a trustworthy copy of the TL500 firmware (ideally 008264, the version
the owner's camera runs). Outcome: **no reliable official source is available.**

- **Samsung official:** the US TL500 support page now lists no downloads. Only one
  Internet Archive snapshot exists (8 Jan 2013), and it loaded its download list
  dynamically, so the archive captured no direct firmware link. The Canada page is
  dead. (The EX1 files we already have came from Samsung's still-live Africa page;
  the US TL500 equivalent is gone.)
- **Internet Archive index:** the archive's URL index was overloaded (503/timeout)
  and couldn't be enumerated for archived download-center files. Worth retrying
  another day.
- **Third-party mirrors (userdrivers.com etc.):** list a "008264" entry, but the
  page is ad-wrapped with no verifiable Samsung-origin link and no file metadata.
  Downloading from these is risky and we have no known-good copy to check it
  against, so this is not recommended.

**Useful fact learned:** the TL500 package's main-program file is named
`EX1-ESP-SR-008264.elf` (note **ESP**, where the EX1 build uses **DSP**), alongside
the same `ONBL1.bin`, `ONBL2.bin`, `SPID.Rom`, `FWUP` files. So the TL500 and EX1
share the `EX1-` filename prefix but differ in the middle tag. This is exactly the
filename-pattern detail the updater checks.

**Best path to a genuine TL500 firmware: dump it from the camera itself.** The
owner's working TL500 already holds 008264 in its flash — that is the authentic,
exact-match source, with no untrusted download. Reading it out requires a
camera-side method (a USB/service download mode if one exists, or a NAND read),
which is the **same recovery-mode research already listed as Phase 2 of the test
plan**. So this goal and the safety groundwork are the same piece of work. Until
then, the EX1 files we have serve as a close stand-in for understanding the format.

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

## How the firmware updater works (found by reading embedded text, 31 Oct 2026)

The camera's own code (inside the big firmware image) contains many readable English messages that describe, step by step, what happens when you put update files on an SD card. Reading them in order tells the story without needing to trace machine code by hand:

1. On startup, the camera checks `/ext/sd0/FWUP` (the small text file we saw, containing a word like "upgrade all" or "keep"). This is literally read as a **script**: a message `Invalid script command!` exists for when it doesn't understand the word.
2. It looks for a file whose name starts with `EX1-IC` and ends in `.bin` (that pattern is for the EX1; the TL500 files use a different prefix — we don't yet know the exact TL500 one, maybe `TL500-IC` or similar, since we don't have a TL500 file to check).
2. It prints `Checking F/W file Full Path : %s` and, if nothing matches, ` There is no Firmware Binary in SD Card`.
3. It reads a **header** from the file (`F/W Versione: %s ,Get Hedaer Info Completed`) that gives, per part, a `file_offset` and `file_size` — this is the table we already found at the start of the `.bin` file, which simply lists where each part (boot loader 1, boot loader 2, main image, resource) sits inside the big file.
4. It copies each part into its place in flash memory one at a time, printing progress like `BootLoader Upgrade...`, `Image File Upgrade... Done`, `Resource Upgrade...`, and reports `...Update Fail` if a part doesn't look right (`Invalid File Format` is one such message).

**What I did not find anywhere in either firmware file:** any mention of a cryptographic signature, a public key, RSA, SHA, or a "signed by Samsung" style check. The earlier `RSA`/`SHA` keyword hits were false alarms — they were just part of longer words like "SHADING" (a camera calibration term). The one "CRC mismatch" string I found belongs to a **different, unrelated program**: a Windows PC installer (Samsung's "Intelli-studio" software) that happens to be bundled inside the same download archive — it never runs on the camera.

**In plain terms:** the update process looks like a simple, unencrypted, unsigned file-copy mechanism driven by a plain-text script and a small header table. That is good news for someone wanting to build custom firmware: there is no obvious cryptographic wall to break through. It does **not** mean it is risk-free — the updater may still check file sizes, a simple checksum we haven't located yet, or the exact filename pattern, and any of those could refuse (or worse, half-accept) a modified file. The next concrete step is finding and reading the `file_offset`/`file_size` header-parsing code itself, to see exactly what it validates before writing to flash.

Also confirmed: the camera's internal name for its chip platform is **"DRIMeIII"** (found in an embedded XML template: `<Platform value="DRIMeIII"/>`), matching the SoC family suspected at the start of this project.

## Container format of the single-file update (VERIFIED 31 Oct 2026)

The 80 MB `EX1-IC-S1-110271.bin` is a simple archive. The first few KB are a
plain **table of contents** listing each part by name with its size and its
offset inside the big file; the parts (boot loader 1, boot loader 2, main
program, resource data) then follow one after another, stored **raw and
uncompressed**.

I verified this rather than guessing: the table says boot loader 1 (ONBL1) is
520 bytes long and starts at offset 0x800. At that exact spot the bytes are a
perfect, byte-for-byte match for the standalone ONBL1 file. Boot loader 2 lands
where the table points too. So the format is confirmed: a readable directory +
concatenated parts, with no scrambling.

**Why this matters for adding features:** to make a modified firmware you would
rebuild this archive with your changed part swapped in and fix up the size/offset
numbers in the table. There is no encryption and no signature standing in the way
of doing that. The one thing still unconfirmed is whether a simple **checksum**
is verified somewhere before the camera commits the new data to flash; if so it
would need to be recomputed, which is routine once located.

## Checksum hunt results (31 Oct 2026)

Question: before the camera writes new firmware to its flash memory, does it
verify a checksum that a modified file would have to match?

**At the container (archive) level: no checksum and no signature. Confirmed
exhaustively.**
- The table of contents stores only a path, a size, and an offset for each of the
  5 components. There is no checksum field. (Header even starts `110271` + a byte
  `05` = "5 components".)
- There is no checksum appended at the end of the file: the file ends exactly
  where the last component ends, with zero trailing bytes.
- The space between the table and the first component is just padding (zeros).

So the archive carries nothing that a checksum could be hiding in. The updater's
`Invalid File Format` rejection is therefore almost certainly a **structure/magic
check** (is this a valid archive with the right version tag and sane offsets),
which a correctly rebuilt archive would pass.

**One check still to confirm (needs interactive Ghidra):** the main program file
begins with a magic marker (`ff 77 ff 77`) after its version tag, and has a small
structured block at its very end. The running firmware also contains a generic
message `Checksum error in ... section ...`, which hints the code may verify its
own sections when loading into RAM **at boot time**. If that self-check is active,
a modified main program could be rejected at startup — but it would be an ordinary
checksum (not cryptographic), locatable and recomputable. This is the single
remaining thing to pin down before trusting a modified main image, and it is the
natural job for a focused Ghidra session.

**Note on misleading strings:** the `CHECKSUM_1/2` and `ADJUST_CHECKSUM` strings
seen earlier belong to the factory *adjustment-data* files (lens/sensor
calibration), not the firmware archive. The `header crc mismatch` string belongs
to bundled Windows PC software, not the camera.

## Boot-check trace results (31 Oct 2026)

I tried to recover the main program's load address (needed to point Ghidra at the
exact self-check instruction) by two rigorous methods. Both were inconclusive,
which is itself a finding: the main program is **not** a simple flat load. It
rebuilds its own memory layout at boot (consistent with the magic marker at its
start). Pinpointing the exact self-check instruction would mean first reverse-
engineering that layout — a larger job.

So I went at the integrity question a more direct way: searched every real
firmware component for the fingerprint of a genuine CRC routine (the standard
256-entry CRC32 lookup table has an unmistakable signature). Result:

| Component | CRC table present? |
|---|---|
| ONBL1 (boot loader 1) | none |
| ONBL2 (boot loader, the part that loads the main program) | none |
| Main program (108091) | none |
| 80 MB bundle | only one, and it sits inside the bundled **Windows PC software** (zlib), not camera code |

**What this tells us, in order of importance:**
1. **The boot loaders contain no checksum, no CRC, and no verify logic at all** — no
   integrity strings, no CRC table. ONBL2 loads the main program and jumps to it;
   nothing between "file sitting in flash" and "code runs" checks a checksum. This
   is the architecturally decisive fact: there is **no integrity gate in the boot
   path**.
2. **The main program has no CRC table either.** Its generic `Checksum error in
   section` message, if that feature is even switched on, could only be a **simple
   additive checksum** (adding bytes together) — which is trivial to recompute when
   rebuilding, and in any case is your own code to patch once you control it.
3. The only real CRC routine in the entire download belongs to bundled Windows PC
   software and never runs on the camera.

**Bottom line of the trace:** nothing cryptographic, and no CRC, stands between a
modified firmware file and the camera running it. At worst there is a simple,
recomputable additive self-check inside the main program. The boot path itself is
unguarded.

## FEASIBILITY VERDICT (plain language)

**Reading/understanding the firmware: feasible.** It is ordinary ARM code running
the VxWorks 6.6 operating system, uncompressed, and packed with readable function
and error names. Standard tools (Ghidra) can open it directly.

**Modifying it and getting the camera to accept it: promising, not yet proven.**
The updater is a simple, unsigned, unencrypted file-copy driven by a plain-text
script (`FWUP`) and the offset/size table above. No cryptographic signature check
was found anywhere. That removes the single biggest obstacle that stops most
modern cameras from being modified. Remaining unknowns are small by comparison:
a possible plain checksum, and the exact filename pattern a TL500 (vs EX1) expects.

**Brick risk is real and unchanged.** Samsung's own guide warns a failed update
can require mainboard service. Any real test must be on a spare body, never your
main camera, and only after a recovery path is understood.

## Recommended next steps
1. Owner: check the camera's current version (above) and confirm if EX1 files are accepted by a TL500 (do not press shutter yet).
2. Install Ghidra (needs Java 17, already on this PC) and load the main image as raw ARM at the right base address (found from the boot loader).
3. Decode the 110271 container table and look for CRC/checksum fields; compare 108091 vs 110271 to see what differs.
4. Read `ONBL2.bin` (62 KB, small) to see how it verifies the upgrade file. That decides feasibility.
5. Look for a recovery or serial/debug mode before any flash test (hidden USB port mentioned in forums).

Tools: `tools/analyze.py` (entropy/strings summary).

# Samsung TL500 / EX1 firmware research

## 🔑 BREAKTHROUGH: exposure encoding cracked via EXIF MakerNote (31 Oct 2026)

## CORRECTION + real progress: exposure IS on the ARM, clamp is reachable (31 Oct 2026)

## First functional patch TEST: code injection works! (31 Oct 2026)

## v2 test: missed again — many copies of the shutter value (31 Oct 2026)

## Shotgun test: bust — static approach exhausted (31 Oct 2026)

Clamped FOUR distinct +0x72 exposure-write sites at once (0xC03DED80, 0xC03DF1B8,
0xC0222798, 0xC05C099C). Result: booted fine, but EVERY shot still recorded slow
shutters (1/6..1/45, Tv 24..88, all < 96) across Program/Aperture/Manual, and
brightness tracked the real exposures. No effect.

**Decisive finding:** even clamping four sites that write offset 0x72, the EXIF
MakerNote 0x72 field never changed. So the recorded/capture shutter comes from a
buffer that NONE of the findable write sites touches. Across the session we clamped
~6 separate copies (getter +0x38, two conversion sites, four +0x72 writers) — all
display/recording/debug copies. The real capture value's buffer is not locatable by
static reading.

**Conclusion: blind static analysis is exhausted.** The value that drives the sensor
hides behind the ARM/DSP exposure messaging and likely uses a raw sensor encoding.
Next step requires **observation** — a 3.3V USB-TTL serial adapter on the camera's
UART to watch the live capture path. (Owner is ordering one; pick up here when it
arrives: find UART pads, get a console, trace the real exposure apply, then clamp it.)

### Session scorecard (what's proven and reusable)
- Firmware is moddable: custom code flashes, runs, recovers (verified).
- Exposure encoding cracked: APEX x16, 1/60 = 96 (via EXIF, zero-risk).
- Code injection works: data-region caves execute.
- Zero-risk test oracle: EXIF MakerNote Tv + image brightness.
- Full map of the firmware, exposure getters, and ~6 shutter-value copies.
Remaining blocker: locating the single capture-apply value — needs serial.


Clamped the x128->x16 conversion sites (0xC03DED80/0xC03DF1B8). Result: booted fine,
but recorded Tv still unclamped (43,64,48,...) AND image brightness tracks the actual
set speeds (Manual 1/8 -> dark 30/255, 3" -> bright 190/255). So that struct is yet
another copy, not the capture/EXIF one.

**The real lesson:** this camera keeps the shutter value in *many* separate structs
(logging, display, several AE-internal conversion buffers, the EXIF source, and the
actual sensor-config value). Each looks plausible statically, but we've now hooked
two and both were the wrong copy. Blindly guessing among them is low-odds (each flash
rules out one of ~7+ candidates, and the true capture-apply site may not be in that
list at all).

**Confirmed assets (real and reusable):** code injection works (caves execute),
the x16 encoding (1/60=96), and the EXIF brightness/Tv **test oracle**.

**This is the genuine longshot threshold.** Distinguishing the many copies and
finding the one that drives the sensor is exactly what the **serial console** makes
easy (watch the live capture path, see which code runs). Blind static iteration can
continue but is slow and low-yield from here.



Built and flashed a test clamp: redirected the shutter getter (0xC03CAEC4) through a
code cave (data-region padding at 0xC0703704) doing `cmp r0,#96; movlt r0,#96`.

**Result: the camera booted and ran normally — our injected code executes.** This
confirms two big things: (1) the data-region **cave is executable** (we can inject
code), and (2) the branch+clamp encoding is correct.

**But the clamp didn't change exposure:** test shots still recorded 1/20, 1", 0.7s
(MakerNote Tv field 0x72 = 72, 0, 11 — all < 96, unclamped). So the getter we hooked
feeds a **logging/display copy** of the shutter, not the real exposure value. The
camera keeps (at least) two copies: the getter-fed struct (+0x38) that we clamped,
and the actual AE-state copy recorded in EXIF (MakerNote +0x72) that drives capture.

**Next (v2):** find where the real exposure Tv is written/applied (the value that
lands at MakerNote +0x72 and configures the sensor), and clamp there instead. The
injection mechanism and the EXIF test-oracle are both proven, so iteration is now a
known loop.



**Important correction:** the earlier "the AE decision runs on the DSP" conclusion was
WRONG — it came from a bug in my scan (an invalid no-index operand check that silently
matched nothing). The corrected scan finds **2,658 writes** and **4,086 reads** of the
shutter field in the main firmware (and it correctly finds the known log read). So the
exposure values are very much handled in the ARM code we can patch.

**What the exposure path actually looks like:**
- The main chip builds the exposure struct by calling **getter functions**:
  `0xC03CAE30` -> ISO/Sv (struct +0x30), `0xC03CAEC4` -> shutter/Tv (struct +0x38),
  with `0xC03CAE7C` / `0xC03CAF0C` for the neighbouring fields.
- Each getter reads from a **table of 40-byte (0x28) entries** (shared base pointer),
  indexed by a frame/zone index, with a sub-index (clamped to <=0x12=18). So the live
  exposure values sit in ordinary ARM memory tables.
- There are ~27 sites across the AE region that call these getters to populate an
  exposure struct (for logging, EXIF, capture, preview, etc.).

**Why this matters:** a minimum-shutter clamp (and the Auto-ISO-in-M math) is now
reachable in ARM code. Cleanest candidate approach: clamp in the shutter getter
(return max(raw, 96)) and compensate in the ISO getter (add the same delta, both
derivable from the same raw Tv) — which would also make the displayed value and the
EXIF reflect the clamp, i.e. correct behaviour. Caveats to resolve next:
- Must be **mode-conditional** (only auto-ISO modes / the intended mode), or it would
  override Manual mode's user-set values.
- Confirm the getters feed the actual **capture** exposure (not just logging/preview).

We also have the **EXIF MakerNote as a zero-risk test oracle**: flash a candidate,
shoot in dim light, read the Tv/Sv fields, see if it held 1/60 and raised ISO.



## Write-site hunt result: the AE decision is on the DSP, not the ARM (31 Oct 2026)

## Intercept-lead probe (31 Oct 2026)

Checked the capture-exposure path on the ARM side. The labels `Capt.Tvalue`,
`Capt.Svalue`, `eAE_IF_M_SHUT_1_REQ`, `eAE_IF_CCD_GAIN_2_CAP_REQ` are each referenced
only from **debug name-tables** (string-pointer arrays used for logging), not from
plain computation sites. This reinforces the DSP conclusion: the ARM treats Tv/Sv as
values it *receives and forwards*, not values it derives.

A clean ARM intercept point (clamp Tv/Sv after the DSP delivers them, before the
hardware is configured) **may** exist, but finding it means tracing the
inter-processor message/receive path and confirming the ARM — not the DSP — applies
the final shutter/gain. That is deep, multi-hop work with uncertain payoff, and it is
exactly the kind of thing the serial console (declined) would make easy by letting us
watch the message flow live.

**Practical ceiling reached (without new inputs):** the realistic ways forward are
(a) reverse-engineer the DSP/SPID side (big new project), (b) the serial console
(needs opening the camera), or (c) a long, uncertain ARM message-boundary trace. The
encoding, the moddability, and the EXIF observation tool are all banked and real.



Hunted for where the shutter/ISO fields get written. Scanned the **entire** main
image (2.6M instructions, 276k stores): **zero** instructions write `[Rn,#0x38]`
(the shutter field) — the ARM code only ever *reads* those values (to log them and
to put them in the EXIF MakerNote). They are never computed by a normal store here.

**Conclusion:** the actual auto-exposure *decision* (the program line that picks
Tv/Sv/Av) runs on the camera's **DSP / image co-processor** (the "SPID" side), and
the ARM firmware just *receives* the finished values via an inter-processor
message/copy. The ARM `eAE_IF_*` strings and `CAEMainController` are the ARM-side
*interface* to that engine, not the engine itself.

**What this means for the min-shutter clamp:** it can't be dropped into the ARM
code at the decision point, because the decision isn't there. Realistic options are
all harder:
- **Reverse-engineer the DSP** (its code lives in the SPID side, which we have not
  analysed and is a separate, bigger project).
- **Intercept the inter-processor message** on the ARM side and clamp Tv/Sv on
  receipt — only works if the ARM then forwards the (clamped) values to configure the
  sensor, rather than the DSP applying them directly. Uncertain.
- **Auto-ISO-in-Manual** may be more reachable: it's about the ARM middleware's
  *mode -> request* logic (what Sv the ARM asks the DSP to use in M mode), which is
  ARM-side — but still needs locating.

**Net:** the encoding is solved and is real and reusable; the patch is blocked not by
math but by the exposure decision living on a co-processor we haven't reversed.



Recovered the camera's internal exposure encoding with **zero flashing and zero
hardware** — just by reading the MakerNote of a controlled set of photos (fixed ISO
+ aperture, shutter stepped 1" -> 1/500). The MakerNote tag 0x0060 is a ~7000-byte
dump of live internal state; two fields decode cleanly:

**Shutter = APEX Tv x 16** (MakerNote offset 0x0072, perfect r2=1.000 fit):
| shutter | 1" | 1/8 | 1/15 | 1/30 | 1/60 | 1/125 | 1/250 | 1/500 |
|---|---|---|---|---|---|---|---|---|
| value | 0 | 48 | 64 | 80 | **96** | 112 | 128 | 144 |
So **1/60 = Tv 6 = value 96 (0x60)**; each full stop = 16; slower shutter = lower value.

**ISO = APEX Sv x 16** (MakerNote offset 0x0076): ISO100=80, ISO400=112, ISO800=128;
each ISO stop = +16 (ISO200=96, ISO1600=144, ...).

**APEX identity:** Ev = Av + Tv = Bv + Sv. So raising the shutter by delta (in Tvx16
units) and raising ISO by the *same* delta keeps exposure constant — a clean 1:1
transfer, because both are the same x16 scale.

**This matches the AE struct fields we already located** (SHR/shutter at +0x38,
SVR/ISO at +0x30 — "SHR"=Tv, "SVR"=Sv), so the minimum-shutter clamp is now fully
specified in code terms:

    if (shutter_Tv < 96) {        // slower than 1/60
        delta = 96 - shutter_Tv;
        shutter_Tv = 96;          // clamp to 1/60  (write +0x38)
        iso_Sv   += delta;        // raise ISO to compensate (write +0x30)
    }

The only remaining engineering piece for the patch is locating the AE write-site that
finalizes these fields (now searchable: look for the value 96 / 1/60 handling). The
exposure math itself is fully understood. Same understanding directly enables the
Auto-ISO-in-Manual idea (compute Sv = Av + Tv - Bv from the metered scene).



## 🎯 MILESTONE: camera accepts MODIFIED firmware (31 Oct 2026)

## Honest status / effort assessment (31 Oct 2026)

## Image-quality + Auto-ISO-in-M research (31 Oct 2026)

**Auto ISO in Manual mode (the owner's preferred near-term feature):** still a hard
target. The ISO option strings (ISOAUTO, ISO80..ISO6400) found in the .elf are the
**AE debug-log** name table, not the menu. The real gating — whether "Auto" is
offered in M mode, and whether the AE computes Sv (ISO) from fixed Tv+Av — lives in
the glyph-rendered SPID.Rom menus and the AE state machine (the hard parts). No
simple per-mode flag was findable by string search.

**regset.txt (image tuning):** confirmed hook, but narrow. Its parser reads 18
values (`%d x4, %x x14`) into the **lens-distortion-correction / post-process** block
(CCpoLdc, with NR/WDR/HDR adjacent). Using it to improve image quality requires
reverse-engineering the 18 parameters' meanings and experimenting for good values —
a project in itself, not a quick setting.

## BOTTOM LINE (31 Oct 2026)

- **Proven and done:** the camera is moddable (custom firmware flashes, runs,
  recovers; a 1-byte edit demonstrated). Full file analyzed; exposure code located;
  debug avenues mapped. This is a real result on a camera with no prior hacking
  scene.
- **The honest wall:** every *specific* exposure/ISO/image-quality feature the owner
  wants lands in the firmware's hard parts (multi-state AE engine, glyph-rendered
  menus, undocumented post-process params). **Without hardware observation (serial
  console, which the owner declined), each one is a large, slow, iterative RE+patch
  effort — not a quick edit.**
- **The lever that would change this:** the serial console (cheap adapter + opening
  the camera) makes the exposure values and the aedebug/programline commands
  directly observable, turning these features from blind grinding into tractable work.
- **Realistic options:** (a) treat this as a successful proof-of-concept and stop;
  (b) revisit the serial route if the owner reconsiders opening the camera;
  (c) continue as a slow hobby project, accepting many flash-test iterations per
  feature.



**Proven:** the camera is moddable — we flash custom firmware and it runs, recovery
works, and we have the real file fully analyzed (base, exposure code, struct fields).

**The min-shutter-for-auto-ISO feature specifically is a large lift**, for concrete
reasons found this session:
- The shutter/ISO decision lives inside a **multi-state AE convergence machine**;
  the exact instruction that finalizes the shutter is a cross-function dataflow trace
  that kept stalling statically.
- The shutter encoding (what value = 1/60) passes through several representations
  (APEX Tv -> conversions -> display denominator); no plain shutter table is stored.
- There is **no labeled min-shutter parameter** to simply edit (searched: only
  WB gain min/max and the debug-drawable program line exist by name).
- Getting observation **without hardware** means injecting file-I/O or screen code at
  the AE site — real, risky, iterative patch engineering. (Serial console would make
  all of this easy but requires opening the camera, which the owner declined.)

**Easier high-value mods that are more achievable near-term:**
- **`regset.txt` image tuning** (noise reduction / WDR / HDR / lens correction) — a
  no-patch SD-card file; needs its 18-value format decoded.
- A **findable value edit** (e.g., max Auto-ISO ceiling / ISO steps) if the constant
  can be located.
- Extending the **intervalometer** or **bracketing** ranges.

**Recommendation:** the concept is proven. For a satisfying next win, tackle an
easier mod first (builds capability and confidence), and treat min-shutter as a
longer-term goal best done once observation is available.



Flashed a main image with a single deliberate 1-byte change (day-name string
"Saturday" -> "Caturday", offset 0x765ac1). The camera **flashed it, booted, and
works normally.** This proves:
- There is **no integrity check** (checksum/signature) blocking a modified main
  image. Our edit was accepted and is running.
- The full **edit -> flash -> run** pipeline works on the real camera, and the
  **recover** path (reflash official) was already proven just before.

Conclusion: custom firmware is not just theoretically feasible on this camera — it
is **demonstrated**. The minimum-shutter exposure patch is now an engineering task,
not an open question. (Visual confirmation of the day-name change is incidental; the
accepted flash is the proof. UI text is largely glyph-rendered from SPID.Rom, and
only the long-form day name was changed, so it may not appear on screen.)



## ✅ STATUS: genuine TL500 008264 firmware ACQUIRED and verified (31 Oct 2026)

The owner located and downloaded `TL500_FW_file_008264.zip` (44.6 MB). Verified:
- **Intact** (zip integrity OK) and the correct multi-file set: `EX1-DSP-SR-008264.elf`
  (main program), `ONBL1.bin`, `ONBL2.bin`, `SPID.Rom`, `FWUP`, plus an empty `DCIM/`.
  (The forum's "EX1-ESP-SR" was a typo; the real name is `EX1-DSP-SR-008264.elf`.)
- **Authentic:** `ONBL1.bin` is **byte-for-byte identical** (SHA-256) to the official
  Samsung EX1 bootloader we already had; the main `.elf` carries the correct `008264`
  version stamp and the expected `ff77ff77` magic. Strong evidence it is genuine and
  untampered.
- Kept out of git (Samsung firmware is never redistributed; `firmware-original/` and
  `extracted/` are ignored).

**This file is BOTH:** (1) the known-good **restore image** (the safety-net
prerequisite is now met), and (2) the real **patch target**.

**Patch target confirmed present in the real TL500 file** (same as the EX1 analysis):
`Exposure value - SVR: %d, SHR: %d` (file 0x7a0197), `ExposureG`,
`eAE_IF_CCD_GAIN_2_CAP_REQ`, `eAE_IF_M_SHUT_1_REQ`, `AeMiddlewareSystem.cpp` — the
auto-exposure module and the ISO(gain)/shutter levers are all there.

**One refinement pending:** the standalone `.elf` (multi-file format) loads at a
different base than the EX1 single-file bundle I first analysed (it is a low-memory
load, ~0x0076xxxx, not 0xC0004000; 35/40 AE labels already correlate). Pinning its
exact base is the immediate next step, then the write-site + encoding + patch, all on
this real target.

**Safety note:** because `ONBL1` is the official bootloader and we will not modify
the bootloaders, the recovery path (re-flash the official set from an SD card via the
intact bootloader) is viable. The first real flash should still be the *unmodified*
rebuild, to prove the round-trip before any modified image.




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

## Debug-access research (31 Oct 2026) — all confirmed in the real TL500 008264 file

## regset.txt + Production Mode findings (31 Oct 2026)

## Shutter encoding findings (31 Oct 2026)

Two shutter representations exist in the firmware:

1. **Human/UI representation — solved.** The shutter-display routine (string ref at
   file 0x4B577F, formatter at 0xC04B88AC) does `sprintf(buf, "1/%d", value)` for
   fast shutters, where the value **is the denominator directly** — so a display of
   `1/60` means the value is literally `60`. Shutters of 1 s or longer use a
   `"%d.%d"` seconds format instead. So in this representation, "never slower than
   1/60" is simply "denominator >= 60".

2. **AE internal representation — APEX.** The exposure engine works in APEX units:
   a debug string `" Av %x Tv %x Sv %x "` prints Aperture / Time-value / Sensitivity
   (gain) in hex. Shutter there is **Tv = log2(1/seconds)**; for 1/60 s, Tv ~= 5.907,
   stored as a fixed-point (scale factor — x8/x16/x32/... — not yet pinned). The AE
   result struct field `+0x38` (SHR) is in this internal domain.

**What this means for the clamp:** there are two clean places it could go —
- in the UI/denominator domain (trivial: keep denominator >= 60), or
- in the AE/Tv domain (clamp Tv to the 1/60 value), which is where the auto-ISO
  trade-off actually happens, so that's the right one for the feature.

**The one remaining number** — the exact internal value that equals 1/60 — is a
**one-minute on-camera read**: put the camera in Manual at 1/60 and observe the
SHR/Tv value (via the exposure log once debug output is reachable), or trace the
Tv<->denominator conversion one more hop statically. Either pins the constant. The
encoding question is otherwise understood (APEX Tv; UI is direct denominator).



**`regset.txt` = image-quality tuning override (not an AE-debug hook).** Its parser
uses the format `%d, %d, %d, %d, %x ×14` and lives in the image **post-processing**
module (CCpoLdc = lens-distortion correction, CCpoNr = noise reduction, CCpoWdr =
wide dynamic range, CCpoHdr = HDR, CCpoIMixer = image mixer). So dropping a
`regset.txt` on the card overrides post-processing parameters — a genuine
**no-hardware, no-patch image-tuning** avenue (bonus feature idea), but it does not
enable exposure logging.

**The real no-hardware avenue = Production / Factory Mode.** The flag files
`check_ev.txt` (exposure-value check) and `check_afstep.txt` (AF check) belong to the
camera's factory test system (`CProductionMode`, `runProductionMode`,
`CProductionModeAdjustFunc.cpp`). This mode:
- reads a command-list XML (`EX1_CMD_LIST.XML`) — checked at `/int/rom`, `/int/nand`,
  and **`/ext/sd0/`** (the SD card), which hints the command list can be supplied from
  the card;
- runs checks/adjustments: Battery, EEPROM, OB, Lens Shading, Defective Pixel, DSP
  version, Ext Flash, MCP, OIS, and an **EV (exposure) check** (`check_ev.txt`);
- writes results to CSV/log files on the card (`E2PR.CSV`, `BATTERY.CSV`,
  `E2P_DATA_SYSTEM.CSV`, "Save Log File") — readable with no hardware.

Recall the command list (found earlier) indexes `iso`, `shutter_speed`, `f_number`,
`metering`, `evc` as first-class commands. If the SD-card `EX1_CMD_LIST.XML` is
honoured, Production Mode could let us read/set exposure parameters and dump results
to CSV — a powerful no-hardware observe/control path.

**IMPORTANT CAUTION:** Production Mode is the *factory calibration* system. Some of
its commands only *read/check* (safe), but others *write calibration data* (OB, lens
shading, defective-pixel, EEPROM adjustments). Running the wrong command could
mis-calibrate the camera. This avenue must be used read-only first, with the exact
command set understood before anything that writes.

**Still to determine (next desk steps):** how Production Mode is triggered (likely a
key combo at power-on, or the presence of the command XML / flag files); and the
`EX1_CMD_LIST.XML` format, to know which commands are safe read-only EV checks.



Three ways the camera's debug facilities can be reached, easiest first:

**1. SD-card flag files — NO hardware, just put a file on the card.**
The firmware checks the card for specific files and changes behaviour:
- `saverawmode.txt` -> enables raw/YUV capture dump (near `global_enable`,
  `raw_simulation`, `preview_capture_raw`, `capture_save_yuv`; dumps to `/ext/sd0/*.raw`).
- `regset.txt` -> the firmware reads **hardware register settings from this file**
  (it prints `regset.txt doesnot exist!!` when absent). A powerful no-hardware hook
  for poking/reading registers; file format still to be worked out.
- also `ptpautotesting.txt`, `log_hw_test.txt`.

**2. Log-to-SD — NO hardware.**
A logging system (`PA_LOG_SAVE` / `DSC_LOG_SAVE` / `SAVELOG`, `LogFile_DumpTxt`)
writes logs to `/ext/sd0/log.txt`, `DSC_Log.txt`, and `/ext/sd0/LOG_DUMP/Log_###.txt`.
It records `LOG_TYPE_SHUTTER_OPERATION`, `LOG_TYPE_IRIS_OPERATION`,
`LOG_TYPE_OIS_STATUS`, mode changes, etc. — i.e. real exposure-related events the
camera chose. These are higher-level events (not necessarily every frame). Trigger
appears to be a factory/service function ("Save Log File"); exact trigger still TBD.

**3. VxWorks serial shell — needs a hardware UART connection.**
There is a full VxWorks command shell (`shellLib`, prompt `[spid@release_shell]$`,
C interpreter) on a serial console (`/tyCo/` tty devices). **This is where `aedebug`
and `programline` live**, and where the frame-by-frame `Exposure value - SVR/SHR`
debug line is emitted (log channel 0x2000). Reaching it means opening the camera,
finding the UART test pads, and attaching a 3.3 V serial adapter. Richest debug,
hardest access. A **factory/service mode** also exists (`BOOT_MODE_FACTORY_INIT`,
the `ADJ_*` adjustment system).

**Bottom line for the patch work:**
- A genuine **no-hardware** path exists (flag files + log-to-SD) that can capture the
  real shutter/ISO values the camera picks — enough to work out the 1/60 encoding and
  watch exposure behaviour from the SD card.
- The **frame-by-frame AE console** (ideal for pinning the exact clamp instruction)
  needs the **UART hardware** connection.
- `regset.txt` is the most promising no-hardware lead to investigate next (if it can
  enable verbose AE logging or read exposure registers, it could substitute for the
  serial console).

## AE state machine mapped + draft patch plan + the key insight (31 Oct 2026)

Traced further on the real TL500 file:
- The exposure-logging routine (0xC03D136C) receives the AE context struct as its
  argument (`mov fp, r0`) and only *reads* ISO(+0x30)/shutter(+0x38) to log them.
- Its callers sit inside an **AE state machine** (a dispatcher that switches on a
  state field `[ctx]` = 0/1/2/3 and calls per-state handlers). The shutter/ISO are
  computed across these states, in the convergence loop — not at a single `str`
  instruction a pattern scan can catch. The context struct is passed by pointer
  through the whole machine.

**Draft patch plan (concept, confirmed targets):** insert, at the point where the
AE's chosen shutter is final for a frame, a clamp:
`if shutter(+0x38) is slower than the 1/60 threshold -> set it to 1/60 and raise
ISO(+0x30) to compensate.` The struct fields are known; the exact state/instruction
and the 1/60 encoding are what remain.

**The key insight — the camera is the right tool for the last mile.** This firmware
has a **built-in `aedebug` console** that logs the exposure decision every frame
(the very `"Exposure value - SVR: %d, SHR: %d"` line we traced). On the camera, you
enable that log, watch the real SVR/SHR numbers as you point at bright/dark scenes,
and that *immediately* reveals (a) the shutter encoding (what number shows for a
1/60 shot) and (b) exactly which state finalizes the shutter. That turns the last
mile from blind multi-hop tracing into direct observation — far faster and far more
reliable than guessing statically. This is the textbook reason firmware work goes
hardware-in-the-loop at this stage.

**Status:** static analysis has done its job — real file fully readable, AE
subsystem and the ISO/shutter struct fields located, patch designed. The remaining
work (pin the exact clamp site + encoding, assemble bytes, verify) is the hands-on
phase, and the camera's own debug console is the tool for it. Safety prerequisites
are met (genuine restore image in hand, official bootloader untouched).

## Patch development on the REAL TL500 008264 file (31 Oct 2026)

Now working the genuine target. Key results:

**Load base locked: 0xC0004000** (B = 0xC0003FF5; `runtime = file_offset + B`).
The main `.elf` has a 7-byte version header (`008264 `) then a `ff77ff77` magic
word, so the image proper is 4-aligned from file offset 7. With that alignment, all
40 `eAE_IF_*` labels resolve as real pointers (40/40) — base confirmed, same as the
EX1. Tool note: read words aligned to the 7-byte header; disassemble starting after
the magic word.

**The exposure routine is identical to the EX1 and located:** at runtime 0xC03D1824
(file 0x3CD82F) the code reads `[fp,#0x30]` = ISO/gain (SVR) and `[fp,#0x38]` =
shutter (SHR) and logs them, then reads `[fp,#0x3c]`/`[fp,#0x40]`. **So the patch
target struct offsets are confirmed on the real file: ISO at +0x30, shutter at
+0x38.**

**Where it stands / what's left:**
- The log site only *reads* the struct; the shutter value is *written* upstream.
  A simple instruction-pattern scan for a routine writing both +0x30 and +0x38 found
  nothing, which means the struct is populated through a data-flow path (filled via a
  different base register/offset, or copied) — locating the exact write needs proper
  data-flow tracing from this routine back through its caller(s).
- Still also needed: the shutter *encoding* (what integer = 1/60 s).

**Honest assessment of the finish line:** everything that *static* analysis can
confirm is confirmed — the feature is implementable, the real target is fully
readable at a known base, and the exact data to change (ISO/shutter struct fields)
and the routine are located. Turning this into *validated* patch bytes is naturally
a **hardware-in-the-loop** task: you locate a candidate write-site, patch it, flash a
test, observe the camera, and refine. Doing the last mile blind (no camera) risks a
subtly wrong patch. And a patch cannot be *proven* without the camera regardless.

**Safety prerequisites are now MET:** we hold the genuine TL500 restore image, and
`ONBL1` is the official bootloader (we will not modify bootloaders), so the SD-card
recovery path is available. The first flash should be the *unmodified* rebuild, to
prove the round-trip, before any modified image.

## Trace refinement + honest stopping point for the analysis phase (31 Oct 2026)

Pushed one level further on the EX1 firmware:
- **Shutter is stored as a real time value**, displayed via a `"1/%d"` format (the
  code holds the shutter time and computes the "60" in "1/60"). So a minimum-shutter
  clamp compares the stored shutter time to a 1/60 threshold value. The exact
  numeric encoding (microseconds vs APEX fixed-point) is read off the shutter table
  when we work on the real target.
- **The exposure result is a context struct passed between functions.** At the
  logging site the fields are only *read* (`ldr [fp,#0x30]`=ISO, `[fp,#0x38]`=shutter);
  `fp` holds a pointer to a struct created upstream. The *write* to the shutter
  field lives in the AE computation function that fills this struct, reached by
  following the struct pointer across calls.

**Why this is a sensible place to stop the pure-analysis phase (not wasted, but
complete for its purpose):**
- Finding the exact write instruction is a cross-function data-structure trace, and
  the exact addresses/offsets **shift between builds** (EX1 vs TL500). Pinning them
  to the byte on the EX1 now would largely be redone on the TL500 file.
- Everything that *transfers* is already done: the feasibility verdict, the format
  and tooling, the base-recovery method, the string-driven locate technique, the
  struct layout concept (ISO & shutter as adjacent fields), and the patch design
  (clamp shutter / raise ISO).
- The remaining byte-level work (exact write site, exact 1/60 value, assembled patch)
  is best done **once, on the genuine TL500 file**, and then validated on a camera.

So the analysis has reached its natural goal: the feature is confirmed implementable,
the patch is designed, and the method to finish it is proven. The next real input
needed is the TL500 firmware file (the auto-watch is hunting it) and, eventually, a
test camera.

## Patch target identified for the minimum-shutter feature (31 Oct 2026)

Traced the exposure-output routine (the `ldr` that references the SVR/SHR string is
at runtime 0xC03D33C8). Just before it logs the result, the code does:

    ldr  r2, [fp, #0x30]   ; SVR  = sensitivity/gain  (this is ISO)
    ldr  r3, [fp, #0x38]   ; SHR  = shutter
    ldr  r1, <"Exposure value - SVR: %d, SHR: %d">
    bl   <log>
    ldr  r2, [fp, #0x3c]   ; further exposure fields
    ldr  r3, [fp, #0x40]

**So the exposure result is a structure** whose fields we now know by offset:
`+0x30 = ISO/gain (SVR)`, `+0x38 = shutter (SHR)`, with related values at `+0x3c /
+0x40`. These are the *final* computed values (they are being logged as the answer).

**What the minimum-shutter patch would do:** find where field `+0x38` (shutter) is
*written* with its final value (upstream of this logging site, inside the same AE
routine) and insert a clamp:

    if (shutter is slower than the 1/60 threshold):
        shutter = 1/60 threshold            # write capped value to +0x38
        raise ISO/gain (+0x30) to compensate  # keep exposure correct

This is a small, local, well-understood change — the kind firmware patches are made
of — inserted into code we can now read at a known address.

**Still to pin down (next iteration, PC-only):**
1. The exact instruction/site where `+0x38` gets its final value (vs. just being
   logged here).
2. The shutter *encoding* — what integer value represents 1/60 s (likely an APEX/Tv
   fixed-point or a microsecond count). Found by reading the nearby shutter table or
   the SHR->exposure conversion.
Both are ordinary reverse-engineering, not blockers. Conclusion stands: the feature
is implementable; we have located the exact data and the routine that handles it.

## BREAKTHROUGH: exposure code located and base address recovered (31 Oct 2026)

The one thing that had blocked deep analysis — not knowing where the main program
loads in memory — is now solved.

**Load base = 0xC0004000.** Recovered by finding the values that make the 40
`eAE_IF_*` auto-exposure labels resolve as real pointers (all 40 matched at this
base; the alternative candidates were false positives from instruction bytes).
Conversion: `runtime_address = file_offset + 0xBFFF3474` (for the 110271 main
image). Tool: `tools/findtable.py`.

**Verified by disassembly.** Disassembling at this base produces clean, textbook
ARM: proper function prologues/epilogues (`push {fp,lr}` / `pop {fp,pc}`),
switch-style dispatch chains, and `bl` calls. A wrong base yields noise, so this
confirms the base is correct and the code is now readable.

**The exposure-decision code is pinpointed.** Each exposure marker string resolves
to exactly one referencing code site:
- `Exposure value - SVR: %d, SHR: %d` (SVR = sensitivity/gain = ISO, SHR = shutter)
  -> printed by the routine that outputs the final exposure. Reference near runtime
  0xC03D3xxx.
- `ExposureG : %d` -> a second exposure-math site.
- `eAE_IF_CCD_GAIN_2_CAP_REQ`, `eAE_IF_M_SHUT_1_REQ`, `eAE_IF_IRIS_REQ` sit as
  consecutive entries in the AE command-dispatch table (gain / shutter / iris),
  i.e. the levers the AE pulls.

The code around the exposure site is dense `cmp` / conditional-branch logic — a
state machine making numeric decisions. That is exactly the shape of code where a
"if the chosen shutter is slower than the floor, raise gain instead" rule would be
inserted.

**What this means:** we have moved from "the exposure logic exists" to "we can find
it, read it, and it is ordinary modifiable ARM code at a known address." The
remaining work for the minimum-shutter feature is ordinary patch development:
trace the specific routine that compares/sets shutter vs gain, identify the exact
instruction(s) to change, and build the patch. No cryptographic or structural
barrier stands in the way. (Still to do before any camera: a test body + a genuine
TL500 restore image, per the single-camera constraint.)

## Feature-feasibility analysis from the firmware (31 Oct 2026)

Studied the EX1 firmware (same code family as the TL500) to judge which features
are realistically addable. Findings are strong and encouraging.

**The single biggest enabler:** this firmware is compiled with **source-file paths
and module names left in** (e.g. `Base/BLModules/ImageQuality/AE/SPID_Interface/
CAEMainController.cpp`, and matching AF / AWB controllers). That means code can be
attributed to the exact subsystem it came from. For reverse engineering, this is
about as good as it gets short of having the source.

**The exposure brain is fully present and labelled.** The auto-exposure (AE) module
is modular and named: `AeMain`, `CAEMainController`, `AECompController`,
`AeMiddlewareSystem.cpp`. ISO is handled internally as sensor **gain**
(`CCD_GAIN_1/2_LIVE/CAP`). The AE interface explicitly exposes the levers:
half-press, AE-lock, gain (ISO), mechanical shutter, iris (aperture), pre-flash,
and bracketing. The exposure "program line" (the curve that trades off
shutter/aperture/ISO) is a real in-firmware structure (`DrawProgram`, `programline`),
and there is an `AE_PATCH` bank mechanism suggesting AE parameters live in
patchable tables. There is also a built-in `aedebug` console.

**There is an internal control API** indexing every function: `iso`, `shutter_speed`,
`f_number`, `evc` (exposure comp), `metering`, plus every physical button (FN,
AEL, etc. — buttons look remappable). This is a clean set of hook points.

### Your two requested features
- **Minimum shutter speed for Auto ISO** ("never below 1/60, raise ISO instead"):
  **feasible.** It is a rule added to the AE program-line logic, which already
  computes shutter + gain together. The module is named and the parameters appear
  table-driven (`AE_PATCH`). Hardcoding a floor is the easy version; a user-pickable
  floor needs new menu UI (harder).
- **Auto ISO available in every mode (incl. Manual):** **feasible.** The gain-
  control machinery exists and runs; availability per mode is a policy/flag, and the
  mode logic is also labelled.

### What else is realistic (building blocks already in the firmware)
- **Extend the intervalometer / time-lapse** — one already exists
  (`CAPTURE_MENU_INTERVAL_*`: hours, minutes, shot count, start time). Longer/more
  shots, finer control.
- **Wider exposure bracketing** (`BRK_AE_STEP`, `AEB`) — more frames / bigger steps,
  which also feeds better HDR (an `HDR` menu already exists).
- **Raise the Auto-ISO ceiling, change ISO steps, change default limits.**
- **Unlock / expand white-balance fine-tuning** — already very complete (Kelvin,
  per-preset amber-blue & green-magenta shift, custom WB).
- **Button / FN remapping** to surface hidden functions.
- **Longer maximum exposures** (if the shutter-control range allows; `SCENE_NIGHT`
  path exists) — to be confirmed by checking the shutter limit.
- RAW already exists (Samsung `.SRW`), so RAW-related tweaks are on the table.

### Harder (new code, big effort) — possible in principle, not a tweak
- **Focus peaking, zebra stripes, live histogram overlay:** no peaking/zebra code
  found. These need NEW real-time live-view image processing hooked into the preview
  pipeline — a major undertaking, not a parameter change.
- **MF focus magnification:** uncertain; depends on an existing live-view zoom path.

### Not feasible (hardware ceilings, not software)
- 4K or higher-bitrate video beyond the 2010 DRIMe III chip's capability.
- New autofocus *hardware* behaviour (phase-detect / advanced tracking) — it's
  contrast-AF hardware.
- WiFi / Bluetooth / phone-app connectivity — no radio in the camera.
- Fundamentally better high-ISO image quality — sensor-limited.

**Overall:** the features you care about most are not just possible — they are the
*best-matched* kind of modification for this camera, because they tune exposure
logic that already exists, in a firmware that is unusually well-labelled. The limit
is reverse-engineering labour (finding and changing the exact code safely), not
capability. Features requiring new hardware or whole new image-processing pipelines
remain out of reach.

## Phase 0 rebuild tooling

## Phase 0 rebuild tooling — DONE and proven (31 Oct 2026)

Wrote `tools/drime_fw.py` (Windows-friendly; no camera involved). It unpacks and
repacks the firmware archive, and the round-trip is **byte-for-byte identical** to
the original on the 110271 file — so our tooling reproduces exactly what the camera
expects, losing nothing.

Two firmware layouts exist in this family:
- **Newer single-file** (110271, and the EX2F/WB850F siblings): one big `.bin` with
  a header + name/size/offset table + raw parts. `drime_fw.py` handles this;
  round-trip verified identical.
- **Older multi-file** (EX1 108091, and — per forums — the **TL500 008264**): the
  parts are already separate files on the SD card (`...-SR-00xxxx.elf`, `ONBL1.bin`,
  `ONBL2.bin`, `SPID.Rom`, `FWUP`). Nothing to pack — you edit one file and copy the
  set to the card. Even simpler, and still no checksum/signature.

So for a TL500 (older format), modifying firmware = editing the main `.elf` (or
resource file) and copying the standard file set to the card. The rebuild step is
essentially free.

## TL500 firmware hunt — round 2 (31 Oct 2026)

Still no genuine TL500 008264 file obtained. Status of each avenue:
- **Internet Archive (Wayback): temporarily OFFLINE** during this session ("Internet
  Archive: Temporarily Offline" / 503s). This is the most promising source for an
  archived Samsung-hosted copy, so it is *blocked, not exhausted* — **worth
  retrying in a few days.**
- **Samsung official:** gone (US page lists nothing; sole 2013 archive snapshot had
  no direct link).
- **GitHub / community mirrors:** none exist for this camera line (the DRIMe III
  tool `drime3-firmware.py` targets WB850F/EX2F and ships no sample firmware).
- **dpreview forum thread:** blocked by a bot challenge in the automated browser;
  could be read manually in a normal browser (thread 2946806) in case a member's
  link or mirror is still live.
- **Third-party driver mirrors:** ad-wrapped, unverifiable, not recommended.

Confirmed detail: the TL500 package's main file is `EX1-ESP-SR-008264.elf` (vs the
EX1's `EX1-DSP-SR-...`), plus the standard ONBL1/ONBL2/SPID/FWUP set.

**Where this leaves the single-camera plan:** flashing the one TL500 still needs a
genuine TL500 restore image first, and we don't have one yet. Two realistic paths:
(1) retry the Internet Archive in a few days for the official file; or (2) get a
cheap used **EX1** body after all — we already have its firmware and the tooling is
proven, so it needs none of this hunting and keeps the TL500 safe.

## Firmware dump-method research (31 Oct 2026)

Question: can we read the firmware out of the camera (to get a genuine TL500 copy,
and to understand recovery)?

**Honest answer: there is no known software or USB method to dump these cameras.**
- The Samsung camera-hacking community (ge0rg/samsung-nx-hacks) worked almost
  entirely on the *later, Linux-based* NX models (NX300/NX500, a newer "DRIMe4"
  chip). Even there, getting a serial console or a flash dump was never achieved
  (their UART issue is still open: resistor tricks on the USB port produced no
  serial output).
- The older **DRIMe III, VxWorks** compact cameras — EX1, TL500, WB2000, WB850F,
  EX2F — have essentially no public hacking work and no documented USB/service
  dump mode.
- Getting firmware *onto* the camera is the easy, understood path (the SD-card
  updater we fully analysed). Getting it *off* would require **hardware work**:
  finding UART test pads (location unknown for this model; needs a 3.3 V serial
  adapter and soldering) or reading the NAND flash chip directly. Both mean opening
  the camera and are unproven on this exact model — an advanced, later-stage task.

**Big win from this research:** a community tool, `drime3-firmware.py` (written for
the WB850F and EX2F, our camera's DRIMe III siblings), parses our firmware format
**exactly**. Verified against our file: header is a 7-byte version string + 1-byte
count, then per part a 32-byte path, 4-byte size, 4-byte offset, 20-byte name. Our
5 parts decode cleanly:

| part file | role | size | offset |
|---|---|---|---|
| FW_UP/ONBL1.bin | boot loader 1 | 520 | 0x800 |
| FW_UP/ONBL2.bin | boot loader 2 | 65,924 | 0xa08 |
| [EX1]DSC_5KEY_EX1 | **main program** | 10,678,220 | 0x10b8c |
| RomFS/SPID.Rom | resource data | 69,218,304 | 0xa3fb58 |
| FW_UP/EX1.HEX | OIS (lens stabiliser) firmware | 17,046 | 0x4c42b58 |

The tool confirms (again) there is no checksum/signature in the format, and gives
us a ready reference for the Phase 0 rebuild tool (it is Linux-only as written, but
trivial to port to Windows).

**What this means for the plan (important):** we do **not** need to dump the camera
to move forward. The lowest-risk route is:
1. Do Phase 0 (PC-only unpack/repack tooling) now, using the EX1 files we have and
   the reference parser — zero risk, no camera.
2. Plan the first real flash on a spare **EX1** body (our files match it directly) —
   no dump needed at all.
3. Dumping a TL500 is only necessary if you specifically want to modify a TL500
   body instead of an EX1, and that is the advanced hardware route (UART/NAND),
   best deferred until the EX1 path is proven to work.

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


## Research while waiting for the serial adapter (1 Nov 2026)

**Lead 1 (highest value): a sibling firmware ships real function names.**
Georg Lukas reverse-engineered the WB850F (same DRIMe III chip, same Samsung SPID
platform, same container format and same 0xC0004000 base as ours):
https://op-co.de/blog/posts/samsung_wb850f_firmware/ . Its firmware ZIP includes
`partialImage.o.map`, a GNU-ld linker map with ~77k named functions, which he loaded
into Ghidra. Our EX1/TL500 ZIPs have no map, but the WB850F firmware (210086,
~59 MB) is still listed on Samsung Austria:
https://www.samsung.com/at/support/model/EC-WB850FBPBE3/ (not yet downloaded).
Plan: get the named WB850F functions, find the AE/exposure functions by name (the
real sensor-apply path), then match them into the TL500 by shared strings, call
structure and code similarity. This could identify the elusive capture-apply site
without any hardware.

**Lead 2: service documentation for the serial session.**
- Free "Samsung EX1 Training" PDF (103 pages, disassembly instructions):
  https://elektrotanya.com/samsung_ex1_training.pdf/download.html
- Paid official TL500/EX1/EX1-VE service manual (block diagram, PCB diagrams,
  schematics): https://www.emanualonline.com/electronics/cameras-photo/cameras/samsung/samsung-tl500-ex1-ex1-ve-service-manual-repair-guide-emo-75210
These may show test points / UART pads and the safe disassembly route.

No public UART/serial notes exist for DRIMe III cameras (searched).


### Downloaded: WB850F firmware 210086 with symbol map (1 Nov 2026)
`firmware-original/wb850f/WB850F_FW_210086.zip` (62 MB, zip OK, link verified on
Samsung AT page), extracted to `extracted/wb850f/` (both git-ignored). Contains
`partialImage.o.map` (36.5 MB, ~95.5k symbols). Named exposure functions include:
- Decision: `AeCalcProgramLine`, `AeCalcProgramLine2`, `STW_AE_CalcProgramLine`,
  `LimitProgramLineMaxSV` (an existing program-line limit hook)
- Capture shutter: `AeCalcCaptureTV`, `AeSetCaptureEShutter`,
  `AeDriverEShutterSetCapTV`, `AeHWSetShutterConfig`, `CalcClkFromTv256`
- Gain/ISO: `AeHWSetCaptureAGCGain`, `AeSetCaptureGain`, `AeSetSVTo`,
  `CalcSv256FromISO`, `AeSetLiveSvMin`
- Conversions: `CalcTv256FromTime`, `CalcShutterTime`

**Key insight:** the AE works internally in **Tv256 / Sv256 (APEX x256)**. The x16
values we kept clamping were downstream copies (EXIF/log), which explains every miss.

Caveats: the WB850F is ~2 years newer and uses a Sony CMOS sensor (TL500 is CCD),
so code differs; names must be matched into the TL500 by strings/structure.

**EX1 Training PDF** (Part 1 Firmware, Part 2 Adjustment, Part 3 Disassembly) is
behind a CAPTCHA on elektrotanya — owner to download manually into `docs-original/`.


## Function matching WB850F -> TL500: the real AE engine located (1 Nov 2026)

String matching failed (the AE core uses no text), so `tools/fuzzy_match.py`
fingerprints each named WB850F function as mnemonic 6-grams and votes for the best
TL500 alignment. Validation: WiFi/SSL functions (absent on the TL500) score 3-16%,
and matched AE functions appear in the **same order with byte-identical spacing**
(e.g. AeSearchBiggerfloor->AeFlashModeAvCheck = 0xAC in both; ->AeReadPLParam =
0x11C in both). The AE program-line module sits at **0xC0538000-0xC0546000** in the
TL500 — a region not examined before.

| WB850F function | TL500 address | score |
|---|---|---|
| STW_AE_CalcProgramLineTable | 0xC0538A3C | 100% |
| STW_AE_CalcProgramLine | 0xC05385DC | 90% |
| STW_AE_CalcProgramLineTable2 | 0xC0538CFC | 91% |
| AeCalcCaptureTV | 0xC0540644 | 68% |
| AeCalcCaptureLTTV | 0xC05406D0 | 80% |
| AeSearchBiggerfloor | 0xC0541CD4 | 100% |
| AeAdjustAVtoDefaultAV | 0xC0541D3C | 90% |
| AeFlashModeAvCheck | 0xC0541D80 | 100% |
| AeReadPLParam | 0xC0541E9C | 96% |
| AeCalcProgramLine / ...2 | 0xC05420B0 / 0xC05420DC | 100% |
| AeSetSVTo | 0xC05426F8 | 100% |
| LimitProgramLineMaxSV | 0xC0542788 | 50% |
| CalcHandShakeTv256FromFL35 | 0xC05454F8 | 40% (to confirm) |
| AeSetCaptureGain | 0xC03E5F7C | 26% (weak) |

**Why this matters:** these are the functions that *decide* exposure (Tv256/Sv256),
upstream of every copy we clamped before. The camera also has a built-in
"hand-shake Tv" concept (minimum handheld shutter from focal length) — the same idea
as the owner's min-shutter feature, so the feature may reduce to raising an existing
floor rather than injecting new logic.

**Next:** confirm the hand-shake function and read how AeReadPLParam /
LimitProgramLineMaxSV apply limits; then design a clamp at the decision (Tv256 for
1/60 = 6*256 = 1536) and test with the EXIF oracle.


## The program-line tables: the feature becomes a data edit (1 Nov 2026)

Using WB850F data names (data base 0xC1835BC0, validated: 258/277 getters land
exactly on named variables), the exposure decision reads per-mode **program-line
tables** `PL_Capt_<Mode>`: `int16 count` then `count` rows of
`(Av index, Tv x16, Sv x16, flag)`, ordered dark -> bright. Same x16 units as EXIF
(1/60 = 96, ISO100 = 80, ISO80 = 75). (`aeHandshakeTVZm` turned out to feed only the
camera-shake *warning* via AeCalcExpOutWarning, not exposure.)

14 such tables exist in the TL500 at 0xC094A892..0xC094ACC8. Names come from aligning
the capture pointer arrays (WB `0xC0A26F30` vs TL `0xC05407EC`; same order, TL lacks
Panorama) and the AeReadPLInfo arrays, confirmed by content:

| TL500 runtime | name | low-light behaviour |
|---|---|---|
| 0xC094AA18 | PL_Capt_Program (P/A) | holds 1/30, ISO to 400, then 1/15 -> 1 s |
| 0xC094AAAC | PL_Capt_Beauty | ISO cap 200 |
| 0xC094AB0E | PL_Capt_Auto | starts 1/8 @ ISO800 |
| 0xC094AB78 | PL_Capt_SmartAuto | = Auto |
| 0xC094ACC8 | PL_Capt_ASR (Dual IS) | holds ~1/45, ISO to 800 |
| 0xC094ABE2 / 0xC094AC34 | PL_Capt_Night / Night_Redeye | ISO80, long exposure |
| 0xC094AC86 | PL_Capt_Portrait | |
| 0xC094AA82 | PL_Capt_TV (S mode) | from 16 s |
| 0xC094A940..0xC094A9E6 | live / AF / lock tables | |

Owner's Program-mode test shots (1/15 ISO320, 1/6 ISO400) sit exactly on
PL_Capt_Program — confirming the table drives real capture exposure.

**Min-shutter feature = edit PL_Capt_Program (13 rows, same size):** hold Tv 96
(1/60) while Sv rises to 128 (ISO800, a value the Auto table already uses), only then
slow the shutter. No code injection.

### Build: MINSHUT (1 Nov 2026) — ready to flash, not yet tested
`extracted/tl500_008264_MINSHUT/` = demo build + new PL_Capt_Program (11 bytes vs
demo). EXIF Model stamp `TL500-M` identifies this build in photos. New table holds
Tv96 (1/60) from ISO100 up to ISO800 (Sv128); below that the shutter slows toward 1 s.
Brighter half of the table unchanged. Test: Program/A mode in a dim room -> expect
1/60 with ISO rising to 800; only very dark scenes go slower. If capture still lands
at 1/15, the half-press lock tables (PL_Lock_*) may also need the same edit.

### MINSHUT field test #1 (1 Nov 2026): the table edit changes real exposure
Photos SAM_0393-0398 carry EXIF Model `TL500-M` (build confirmed). In Program and
Aperture modes the camera now uses **ISO 800** — it never exceeded ISO 400 in these
modes before — so PL_Capt_Program is live and drives capture. Same dark spot:
demo build 1/3 @ ISO400 (brightness 87) vs MINSHUT 1/3 @ ISO800 (brightness 126).
All test scenes were very dark (1/3-1/6 even at ISO800), i.e. the 'ISO maxed, slow
the shutter' segment, which is correct per the new table. Still to verify: the 1/60
hold in moderately dim light (expect 1/60 with ISO 200-800).

### Build: HOLD60 (1 Nov 2026) — 1/60 never slower in P/A, ISO cap 1600
Owner's spec: in P and A ("run and gun") the shutter never goes below 1/60; Manual
stays fully manual (auto-ISO *selectable* in M is the next project). Build
`extracted/tl500_008264_HOLD60/` = MINSHUT + 3 bytes: PL_Capt_Program darkest row
`(0,0,128,0)` (1 s @ ISO800) -> `(0,96,144,0)` (1/60 @ ISO1600); EXIF Model stamp
`TL500-6`. Every row now has Tv >= 96, so the program line contains no shutter
slower than 1/60. Darker scenes should underexpose rather than blur.
Evidence the darkest row acts as a hard floor: PL_Capt_Auto's darkest row is 1/8,
matching Auto mode's real slowest shutter. Evidence ISO1600 is accepted: the live/AF
tables already use Sv150. Open risks: a separate max-ISO limiter
(LimitProgramLineMaxSV) could cap at 800, and flash or slow-sync paths may bypass
the table. Test: P and A in dim and very dark rooms, flash off -> expect 1/60 with
ISO up to 1600, darker photos in very dark scenes.

### HOLD60 field test (1 Nov 2026): SUCCESS — 1/60 floor works in P and A
| photo | mode | shutter | ISO | aperture | brightness |
|---|---|---|---|---|---|
| SAM_0399 | A | 1/60 | 1600 | f/1.8 | 30 |
| SAM_0400 | A | 1/60 | 1600 | f/1.8 | 55 |
| SAM_0401 | P | 1/60 | 1600 | f/1.8 | 47 |
| SAM_0402 | P | 1/60 | 200 | f/1.8 | 73 |
| SAM_0403 | P | 1/60 | 640 | f/1.8 | 129 |

All five carry Model `TL500-6`. Every shot is 1/60; ISO moves freely (200, 640,
1600) to match the light, so the camera is doing auto-ISO with a minimum shutter
speed. In the darkest scenes it stops at ISO1600 and underexposes instead of
slowing down, as designed. ISO1600 is reached, so no hidden 800 limiter applies.
**The owner's main feature is done: a pure data edit of 11 bytes in one table**
(the build differs from stock by 51 bytes; the other 40 are the cosmetic
EXIF/day-name changes). Not yet checked: flash-on behaviour.
Next project: auto-ISO selectable in Manual mode.


## Auto-ISO in Manual mode (1 Nov 2026)

### Where Manual forces ISO 100 (two places)
1. **UI layer**, WB850F `CAPPCaptureUiValue::setISOBackupValue(mode)` = TL500
   **0xC04D0D34** (exact structure; TL mode numbers 2/3/4 = P/A/S, **5 = Manual**).
   When switching modes it restores the saved ISO index into `[0xC0D7F300+0x88]`
   (0 = Auto, 1 = 100, 2 = 200 ... per WB `changeISOInfo`), but for Manual only:
   `if ISO == Auto: ISO = 1`. `setISOinitValue` = TL **0xC04D16D8** sets Manual's
   default to index 1 (others 0 = Auto).
2. **Exposure engine**, WB `AeCalcCaptureManual` = TL **0xC05408C8** (94%). It fills
   the capture exposure: `[sl]` = Tv, `[sl+2]` = Av, `[sl+4]` = Sv from system info;
   `if Sv == 0 (Auto): Sv = 80 (ISO100)`. It then computes the meter's "proper Tv":
   `[sl+0xA] = Ev - Av + Sv - 80` (arg0 = metered Ev on an ISO100 basis; Tv is
   also compared with the hand-shake Tv for the shake warning, which confirms `[sl]` is Tv).

The menu-disable mechanism (`setMenuDisableFlag` -> `setCapDisableMenuInfo(id, mask)`,
item enabled unless bit set) was looked at; which id is ISO isn't pinned down yet.
If the M-mode menu still greys out Auto, there's a workaround: select Auto in P, then turn the dial to M
(patch 1 makes the saved Auto survive the switch).

### Build: MAUTO (`extracted/tl500_008264_MAUTO/`, HOLD60 + 53 bytes, EXIF `TL500-A`)
- 0xC04D0DA4 and 0xC04D16EC: `mov ip,#1` -> `mov ip,#0` (Manual keeps / defaults to Auto).
- 0xC0540938: the ISO100 fallback -> `b 0xC0703704` (cave, proven executable), which
  solves the meter equation for ISO: `Sv = Tv + Av - Ev + 80`, clamped to
  80..144 (ISO100..1600), stores `[sl+4]`, returns to 0xC0540940. Only runs when
  ISO is Auto in Manual; a fixed ISO in Manual is untouched.
- Test: M mode, ISO Auto, same shutter/aperture in brighter and darker spots ->
  EXIF ISO should change with the light and brightness should stay similar.

### MAUTO field test (1 Nov 2026): SUCCESS — auto-ISO works in Manual
Menu: Auto is still greyed out in M, but selecting Auto in another mode and turning
to M keeps it (patch 1 works). All shots Manual, 1/60, f/1.8, model `TL500-A`:

| photo | scene | ISO | brightness |
|---|---|---|---|
| SAM_0404 | room against bright windows | 200 | 48 (metered for windows; normal) |
| SAM_0405 | dark under a desk | 1600 (cap) | 39 |
| SAM_0406 | red wall / TV | 1600 | 105 |
| SAM_0407 | floor and sofa | 640 | 112 |
| SAM_0408 | legs on tiles | 1280 | 123 |

ISO follows the light with the shutter and aperture fixed, and normal scenes land at
brightness 105-123 (P-mode reference: 129), so the injected formula
`Sv = Tv + Av - Ev + 80` has the right sign and scale. Remaining polish: un-grey
Auto in the M-mode ISO menu (menu-disable mask; ISO's id still to identify).

### Build: MAUTO2 — un-grey Auto in the Manual ISO menu (MAUTO + 4 bytes, EXIF `TL500-U`)
The TL500's menu-disable routine (WB `setMenuDisableFlag`, TL around 0xC04D2000)
writes per-menu masks through 0xC04CE83C(id, mask) (TL ids 0x88..0x9B = WB
0x148..0x167). **Id 0x99 is ISO, and its mask is an allow-list** (bit n set = item n
selectable): every mode gets 0xFFFFFF, but `if mode == 5 (Manual)` it gets
**0xFFFE** (everything except item 0 = Auto). In a restricted sub-state, Manual gets
0xE and the other modes 0xF (Auto..200). The WB850F has the same rule (`mode 8 ->
0x15A = 0xFFFE`), which supports reading it as ISO.
Patch: the two `bne` after `cmp fp,#5` at 0xC04D2108 / 0xC04D2258 -> `b` (Manual
never gets the 0xFFFE mask), and 0xC04D2320 `mov r1,#0xE` -> `#0xF`. GUI-only change.
Test: M mode -> ISO menu -> Auto should be selectable, not greyed.

### MAUTO2 field test (1 Nov 2026): SUCCESS
Owner confirms: in M mode, ISO Auto is now selectable directly in the menu (no longer
greyed out). Feature complete: P/A hold 1/60 with auto-ISO 100-1600; M offers Auto
ISO (camera picks ISO for the chosen shutter/aperture, 100-1600) or any fixed ISO.
Current firmware on the camera: `extracted/tl500_008264_MAUTO2/` (model `TL500-U`).


## Exposure compensation everywhere + Manual ISO 3200 (1 Nov 2026)

Owner's request: leave EV comp at e.g. -0.3 in every mode, with the camera picking
ISO. (Selectable minimum shutter / settings GUI is **dropped**: P/A keep the 1/60
floor; for slower shutters the owner uses M with auto-ISO.)

**Fine ISO steps already happen:** MakerNote Sv x16 shows ISO 209, 673, 183, 591,
1131 for shots whose EXIF ISO tag reads 200/640/200/640/1280 (the tag rounds to
standard 1/3-stop values; the AE works in 1/16 stops).

**Where Manual blocks EV comp (three places):**
- AE: `AeUpdateSysInfo` (TL 0xC03EEED0) stores the EV comp shift (x16, from
  `AeSystemEVCSetToAeEVCShift` = TL **0xC03ECCF8**, 90%) into sysinfo
  `0xC0CF8660+0x16`, but forces 0 when sysinfo+0xA == 4 (AE manual mode).
- UI live-view check (WB `checkEVCEnableMode` = TL **0xC04C0688**): allowed in
  modes 2,3,4,6 only (not 5 = M).
- UI store (WB `setEVCValue`, inline in TL at **0xC04D0400**): saves the EV setting
  (capture menu 7) only in modes 2,3,4,7,6.

### Build: EVC (`extracted/tl500_008264_EVC/`, MAUTO2 + 58 bytes, EXIF `TL500-E`)
- 0xC04C069C..A4: mode check becomes `2 <= mode <= 6` (adds 5).
- 0xC04D0404..10: store check becomes `2 <= mode <= 7` (adds 5).
- Cave 0xC0703704 rewritten: `bl 0xC03ECCF8` (EV comp, x16) then
  `Sv = Tv + Av - Ev + 80 + EVcomp`, clamp 80..160 (ISO100..**3200**). The AE
  forcing to 0 for AE-manual is left alone, so EV comp in M affects only auto-ISO
  (fixed ISO in M behaves exactly as stock).
- Test: (a) M, ISO Auto, EV comp button usable? (b) same scene/settings at 0 and
  -1 -> MakerNote Sv should drop ~16 and the photo darken; (c) P at 0 vs -1;
  (d) M auto-ISO very dark -> ISO 3200: check the picture size isn't reduced.

### EVC field test #1 (1 Nov 2026): runs; EV comp usable in M; ISO3200 full size
| photo | mode | shutter | EV comp | ISO (MakerNote) | size | brightness |
|---|---|---|---|---|---|---|
| SAM_0410 | M auto-ISO | 1/30 | -0.7 | 2263 | 3648x2736 | 60 |
| SAM_0411 | M auto-ISO | 1/45 | -0.7 | 3200 (cap) | 3648x2736 | 68 |
| SAM_0412/13 | P | 1/60 | -1.0 | 1600 (cap) | 3648x2736 | 33/42 |
| SAM_0414/15 | M auto-ISO | 1/250 | 0 | 3200 (cap) | 3648x2736 | 23/19 |

Confirmed: the EV comp setting can be set and saved in Manual (EXIF shows -0.7 in
M); M auto-ISO now reaches 3200 (and values between, e.g. 2263); **ISO 3200 keeps
full 10 MP resolution**. Not yet confirmed: the *size* of the EV comp effect. Every
shot was in dim light at or near the ISO cap, and there's no 0 vs -1 pair of the
same scene. Next: matched pairs in a medium-lit scene (M auto-ISO and P).

### EVC field test #2 (1 Nov 2026): EV comp acts on Manual auto-ISO
Same room/window view as SAM_0404 (M auto-ISO, EV 0, 1/60 f/1.8 -> ISO 183).
At EV -1: SAM_0416 1/90 -> ISO 100 (floor; ~137 expected), SAM_0417 1/125 ->
ISO 161 (~190 expected with -1, ~380 without). The ISO lands near the "-1"
prediction, about 1.2 stops below the no-comp value, and brightness drops 48 -> 37-40
(about -1 stop after JPEG gamma). Framing differs between the shots, so this is a cross-shot estimate,
but the comp is clearly applied with the right sign. P-mode comp is the camera's
stock behaviour.


## Build: S80 — auto-ISO in S mode to 3200, Manual auto-ISO floor ISO 80 (1 Nov 2026)
`extracted/tl500_008264_S80/` = EVC + 5 bytes, EXIF model `TL500-S`.
- PL_Capt_TV (S mode, 0xC094AA82) rows 0-1: Sv 112 (ISO400) -> 160 (ISO3200). New
  table `[(0,-64,160),(0,80,160),(0,80,75),(4,80,75),(4,168,75)]`: in dim light ISO
  now rises to 3200 before anything else gives.
- Cave 0xC0703724/28: auto-ISO floor Sv 80 -> 75 (ISO 80, the cleanest RAW).
- Test: S mode, ISO Auto, 1/60 in a dim room -> ISO above 400 (was capped at 400);
  M auto-ISO in bright light -> ISO 80 possible.


## FAUXJI FILM PRO — Fuji-style JPEG looks (investigation, 1 Nov 2026)

Idea: rewrite some of the TL500's built-in **Photo Styles** (Normal, Soft, Vivid,
Forest, Retro, Cool, Calm, Classic, Custom RGB) into Fuji-like film simulations
(Provia, Velvia, Astia, Classic Chrome, Classic Neg, Acros, Eterna). JPEG only; RAW
is untouched (shoot RAW+JPEG to get both).

**What the sister firmware shows (WB850F names):** styles are applied in the
DRIMe III image pipeline by `CIpcDrimeIII::Update*4Still` (capture) / `*4Draft`
(live view), one per pipeline block. The blocks a film look needs:
| block | WB function | film-look use |
|---|---|---|
| colour matrix | UpdateCCMatrix4Still -> IPCS_ColorCorrection_param | hue shifts / channel mix (Classic Chrome, Neg) |
| tone curve | UpdateGamma4Still -> IPCS_Tone_LUT (curves at ~0xC1400624.. in WB) | contrast, faded blacks, highlight roll-off |
| colour LUT | UpdateCLUT4Still -> IPCS_ChromaLUT | per-hue saturation (Velvia, muted greens/blues) |
| saturation | UpdatePCSE4Still (primary colour sat. enhance) | overall vividness |
| monochrome | UpdateMono4Still | Acros (with a tone curve) |
The firmware's own art effects (`ADE_LOMO_*`, `ADE_OldFaded_*`, `ADE_OldMovie_*`)
drive exactly these blocks (Tone_LUT + ChromaLUT), which shows a "film look" is
achievable with them. Playback-side style tables `g_tPss{Soft,Vivid,Forest,Retro,
Cool,Calm}{Y,C}` (60 bytes each) exist too (for editing existing photos in playback).

**TL500 side:** the matching code sits at 0xC0443000-0xC044B000 (fuzzy matches:
UpdateCLUT4Still ~0xC044A4F4 42%, UpdateMono4Still ~0xC0447070 73%,
UpdateCCMatrix4Still ~0xC0448FF4, UpdatePCSE4Still ~0xC0448940).

**Feasibility:** good, and low-risk: if the per-style parameters are stored as data
tables (likely, as in the playback tables and the AE program lines), each film sim
is a **data edit** of one existing style: worst case, odd colours in the JPEG. Next steps:
(1) find the per-style tables those TL functions index by the Photo Style value;
(2) decode their format (matrix 3x3 ints, tone LUT, chroma LUT); (3) write
recipes for each Fuji look; (4) test with the EXIF/pixel oracle (colour checks).
Mapping proposal: Vivid->Velvia, Soft->Astia, Classic->Acros (mono + punchy curve),
Retro->Classic Chrome, Calm->Eterna, Cool->Classic Neg; Normal stays Provia-like.

### S80 field test #1 (1 Nov 2026): ISO 80 floor works; S-mode test still to shoot
SAM_0418 (`TL500-S`, M auto-ISO, 1/15 f/1.8, EV 0): MakerNote Sv 75 = **ISO 80**,
brightness 118 (well exposed). The S-mode auto-ISO-to-3200 change isn't tested yet
(no S-mode shot on the card).


## GUI modding: the menu text is editable (1 Nov 2026)

**Where the words live:** `SPID.Rom` (69 MB resource ROM) holds ~40 language
string tables back to back (each preceded by `?, total_size, count=1390`). English
starts at file 0x683110 (header 12 bytes before), 1390 entries, ends 0x692AB8.
Entry = `uint32 n` + n bytes UTF-16LE, NUL, padded with 0xAB to 4 bytes. Strings
are addressed by **index**; no precomputed offset index exists in SPID.Rom or the
.elf (searched for consecutive entry offsets in every encoding), so the camera
walks the table at runtime: entries may change length **as long as the table's
total size is unchanged** (the next language table must not move).
Tool: `tools/spid_strings.py` (list / size-preserving rewrite, self-verifying).

Photo Style strings: capture menu idx 181 (title) and 182-191 (Normal..Custom RGB),
playback-edit copy idx 290-300, help lines idx 987-997.

### Build: FAUXJI0, names only (S80 + edited SPID.Rom; .elf identical to S80)
Title "Photo Style Selector" -> **FAUXJI FILM PRO**; Normal->PROVIA, Soft->ASTIA,
Vivid->Velvia, Forest->Reala Ace, Retro->Classic Chrome, Cool->Classic Neg.,
Calm->Eterna, Classic->ACROS, Negative->Sepia; help lines rewritten. Colours are
still Samsung's at this stage (note: "Sepia" is still the Negative effect until
the colour work lands). **First edit of SPID.Rom ever**: if the GUI shows wrong or
garbled text, re-flash S80's SPID.Rom (original) to restore.

## FAUXJI colour pipeline — what's known (1 Nov 2026)
- Menu choice -> internal style: TL `GetSmartFilter` (0xC0443A90) reads the effect
  mode and maps it through a **13-byte table at 0xC07B0198** =
  `[0,0,1,2,...,11]` (menu value -> style number). Result stored at info+0xC
  (Custom RGB triple at info+0x10) by 0xC0444880 (TL `UpdateInfo`).
- Colour constant tables: 0xC07B0000-0xC07BB900, used by the TL Update* functions
  (CLUT 0xC044A4F4 -> 0xC07BA3D4/0xC07BA7D4; CCMatrix 0xC0448FF4 -> 0xC07BB190;
  tone-LUT candidates 0xC07B6804 / 0xC07B8804 / 0xC07B9804; Mono 0xC0447070).
- **Colour matrix format decoded** (0xC07BB190): 3x3 int32, fixed point /128
  (rows sum to 128). First: `[[225,-104,7],[-30,190,-32],[11,-86,203]]`; the
  following sets fall off (225,220,216,212,208...), apparently the camera already
  lowering colour saturation as ISO rises to hide chroma noise.
- Per-style tables (likely CLUT and tone curves indexed by the style number) are
  next to decode.

## FAUXJI recipes, tuned for this sensor
Sensor: Sony 10 MP 1/1.7" CCD (same as Canon G11/S90). DxO: **11.1 EV** dynamic
range at base, low-light score ~ISO 130. Real Fuji X sensors have ~13-14 EV, so
the recipes are adapted:
1. **Protect highlights first.** Every curve gets a soft shoulder (roll-off over
   the top ~1.5 EV) instead of Fuji's harder clip; pairs well with the owner's
   habit of -0.3 EV. Velvia/Classic Neg contrast comes from the mid-tones, not
   from pushing highlights.
2. **Shadows: crush a little, never lift.** Deeper shadows hide CCD read noise
   and JPEG blocking; lifted (faded) blacks would show noise. Eterna's "fade" is
   done as lower mid-contrast, not raised blacks.
3. **Saturation follows ISO.** Keep Samsung's per-ISO matrix falloff and apply
   each look's saturation on top, so Velvia at ISO 1600 doesn't amplify colour noise.
4. **Reds are the first to clip on this CCD**, so Velvia boosts greens/blues more
   than reds (via the per-hue CLUT); skin stays close to PROVIA.
5. **ACROS from red+green, not blue.** The blue channel is the noisiest on small
   CCDs, so the mono mix weights R/G (like a yellow filter, ~0.35R/0.55G/0.10B),
   cleaner and punchier, close to Acros+Ye.

| look | tone curve (mid contrast / shoulder) | saturation | hue notes |
|---|---|---|---|
| PROVIA | Samsung Normal, soft shoulder | 0 | neutral |
| Velvia | +2 mid / soft shoulder | +2 (greens/blues), +1 reds | slight warm, deep blue skies |
| ASTIA | -1 mid, gentle shadows | +1 | skin protected, clean blues/greens |
| Classic Chrome | +1 mid, deeper shadows, -1 highlights | -2 | muted reds, cyan-ish blues, slightly warm |
| Classic Neg. | +2 mid, hard toe | -1 | cyan/teal shadows, magenta-warm highlights, desaturated greens |
| Eterna | -2 mid, soft everywhere | -3 | teal-greens, muted |
| Reala Ace | +1 mid, crisp | +1 | neutral, accurate |
| ACROS | +1 mid, rich blacks | mono | R/G-weighted mix |
| Sepia | ACROS curve | mono + warm tint | brown cast |
Numbers are relative steps (like Fuji's -4..+4 scale), turned into table values
once the per-style formats are decoded.

### FAUXJI0 field test (1 Nov 2026): SUCCESS, the GUI text edit works
Owner: the new names and title show correctly and the text looks fine, so
SPID.Rom string edits (with length changes) are safe and the runtime walks the
table. Observation: in the quick (Fn) menu **two styles appear greyed out**; which
ones and in which mode is still to check. Text-only build, so this is stock
per-mode/per-setting behaviour (candidates: the two "effects" Classic/Negative
being disabled with RAW quality, or a mode restriction via the menu-disable masks).


## FAUXJI1: two more looks in the Sketch/Defog slots, allowed in RAW+JPEG
Owner: the greyed pair in the quick menu was **Sketch and Defog** (with RAW+JPEG).
- Text: idx 911 `Sketch` -> **Bleach Bypass**, idx 986 `Defog` -> **Nostalgic
  Neg.**; help lines 1295/1296 rewritten. (Both strings were appended late in the
  table, i.e. added by a Samsung update.)
- RAW rule: capture setting 6 = QUALITY is cached at UI `0xC0D7F300+0x14`; values
  >= 3 are RAW. In setMenuDisableFlag the RAW branch (0xC04D226C) writes allow-masks:
  0 for the JPEG-only menus and **0x5F for menu 0x8F** (items 5 and 7 blocked).
  0x8F is taken to be the list holding Sketch/Defog. Patch 0xC04D22BC
  `mov r1,#0x5F` -> `#0xFF`. EXIF model `TL500-F`.
- Descriptor table at 0xC0916330 (40-byte rows) names every capture setting; the
  capture-menu index is the printed index - 1 (ISO = 0xB, EV = 7, QUALITY = 6,
  PSS = 0x1E). UI `+0x40` caches PSS.
- Open: Sketch and Defog are probably Smart-Filter effects with their own processing
  (WB: ADE_SKETCH, defog), not plain table slots, so making them real film looks
  needs their processing redirected to a colour-style slot (or the 13-byte
  menu->style map at 0xC07B0198, if they go through it). Test first whether they
  can be selected in RAW+JPEG and what the JPEG looks like.

### FAUXJI1 field test: names fine, Sketch/Defog still greyed with RAW
Owner: greyed in RAW and RAW+JPEG (selectable with JPEG only). So menu 0x8F wasn't
the list. Checked and ruled out: other reads of the quality cache (`+0x14`,
0xC04D0FE0 / 0xC04D2C54 / 0xC04D2D0C = mode -> force non-RAW, not greying), UI value
0x30 (a camera-state flag set from 0xC041xxxx with values 4-9, not quality).

### Build: FAUXJI2 (`extracted/tl500_008264_FAUXJI2/`, EXIF `TL500-G`)
FAUXJI1 text + .elf = S80 with one instruction changed: the 0x8F change is undone, and in
the RAW branch menu **0x88**'s allow-mask 0xFFFFF9 (blocks exactly items 1 and 2,
i.e. two entries, as observed) becomes 0xFFFFFF: 0xC04D2298
`ldr r1,=0xFFFFF9` -> `mvn r1,#0xFF000000`.

### FAUXJI2 field test: SUCCESS, Bleach Bypass / Nostalgic Neg. unlock with RAW
Owner confirms both are selectable in RAW and RAW+JPEG. So menu **0x88 is the
Photo Style / filter list** whose items 1 and 2 are the two late-added entries
(Sketch, Defog), and its RAW allow-mask was 0xFFFFF9. Still to check: a shot with
each in RAW+JPEG (capture completes, the JPEG gets the effect, the RAW is unaffected).

### FAUXJI2 capture test (1 Nov 2026): RAW+JPEG works with both
SAM_0419 (Sketch slot, "Bleach Bypass"): JPEG 2592x1944, i.e. Samsung's Sketch effect
renders at 5 MP; pencil-hatch black and white. SAM_0420 (Defog slot, "Nostalgic
Neg."): JPEG full 3648x2736, contrast/clarity boost. Both wrote normal-size SRW files
(24.9 / 24.3 MB) and the camera didn't hang. RAW cleanliness not yet viewed (no RAW
decoder installed here). Sketch is a structural effect (edge hatching, reduced
size), so a real film look in that slot means redirecting its processing.


## FAUXJI colour decode (1 Nov 2026): every Photo Style is a 3x3 matrix + flags

Capture pipeline order (TL `UpdateStillParams` 0xC0444A98): BNR 0xC0447DB0, LCA
0xC04480E0, WBC 0xC0448128, CFAI 0xC0448420, PCSE 0xC04484B0, **CCMatrix
0xC0448FF4**, **Gamma/tone 0xC0449730**, FC, CM, CS, ETC, HPF, EE, EGLUT, YCNR,
**CLUT 0xC044A4F4**, **Mono 0xC044AD9C**, **Nega 0xC044AE1C**, Moire, CA. Live view
has its own list at 0xC04449C8. The internal style number is `this+0xC`.

- **Colour matrix:** final = sensor CCM (per ISO, 0xC07BB190, /128) x **style matrix
  0xC07BB28C[style]** (3x3 int32, 256 = 1.0; live-view copy 0xC07B3C40). Each
  stage builds a 64-bit key (byte 1 = style) and registers its parameter block with
  0xC0444204; 0xC04446D8 = 3x3 multiply.
  Stock style matrices, identified by character (internal order != menu order):
  0 identity (Normal), 1 all rows (78,150,28) = B&W (Classic), 2 mild desat +12%
  (Soft?), 3 blue +22% (Cool), 4 warm desat (Retro), 5 green up (Forest), 6
  saturating (Vivid), 7 mild desat (Calm?), 8 near identity (Negative).
- **Tone curve:** 9 curves of 256 bytes at 0xC07B9AD4 + n*256 (0-4 = Contrast -2..+2
  via table 0xC07BB4DC; 2 is linear; 5-8 brighter variants). Code picks: style 1 ->
  curve 4, styles 4/5/7 -> curve 5, special mode (this+0x44 == 3) -> this+0x54 + 5,
  else Contrast. Per-style curves therefore need a code change (later).
- **Mono stage** on only for style 1; **Nega (invert) stage** on only for style 8.

### Build: FAUXJI3 (`extracted/tl500_008264_FAUXJI3/`, FAUXJI2 + 230 bytes, EXIF `TL500-H`)
`tools/fauxji.py` writes the FAUXJI matrices (both copies) from readable knobs
(per-row saturation, channel gains, hue cross-mixes, overall gain) and switches off
the invert stage for the Sepia slot (0xC044AE2C `cmp lr,#8` -> `#0xFF`).
PROVIA identity; ACROS mono (0.35R/0.55G/0.10B); ASTIA sat 1.0/1.1/1.1, slightly
warm; Classic Neg. green sat 0.7, yellow-ish greens, cool; Classic Chrome sat
0.7-0.8, cyan blues, -8%; Reala Ace sat 1.08; Velvia sat 1.2/1.4/1.4; Eterna sat
0.65, teal; Sepia warm mono.
Open: the menu-name -> style-number mapping is inferred from the stock matrices,
so Soft/Calm (2/7) and Cool/Forest (3/5) need confirming with test shots.
Bleach Bypass / Nostalgic Neg. (Sketch/Defog, styles 10/11) aren't in the matrix
table (the CCMatrix switch only handles 0-7, default for others), so they still need a code change.


## FAUXJI expansion study (1 Nov 2026, desk research while away from the camera)

### Resource ROM file system (SPID.Rom)
SPID.Rom starts with a directory of named files (`/int/rom/...`): **record = 128-byte
name + u32 offset + u32 size** (stride 144; verified on all 36 JPEGs). Contents:
58 .raw images, 36 .jpg backgrounds, 26 .snd sounds, plus PNG icons and **7 XML
screen-layout documents** (`page/layer/region/group/div/bitmap` with id, resource,
x, y, width, height), so screens can be re-laid-out as text.
- **Boot screen** = `bg_power_on_off_422.jpg` at 0x01A92800, 640x480 baseline JPEG
  (4:2:2), 21,504 bytes, **slot 22,528 bytes**. A FAUXJI draft
  (`research-out/fauxji_boot_draft.jpg`, original design, no Fujifilm marks) is
  21,275 bytes, so it fits as-is (update the size field). Menu backgrounds
  `bg_menu*.jpg` can be themed the same way.
- **Sounds**: `Shutter1/2/3_32m.snd`, `ShutterShort_32m.snd`, `PowerOn1/2/3_mono.snd`:
  headerless, likely 16-bit mono at 32 kHz (0.15-1.5 s; rate to confirm by ear);
  each slot has a little spare room. A synthesized leaf-shutter click and a short
  power-on chime can replace them (Shutter/Start Sound 1/2/3 are user-selectable).
- **No-flash option today:** Setup > Start Image > *User Image* shows any photo at
  power-on: shoot or copy a FAUXJI logo image and select it.

### What the firmware already has that maps to Fuji features
| Fuji feature | TL500 equivalent found | FAUXJI plan | effort |
|---|---|---|---|
| Film simulations | Photo Style (9 slots + Sketch/Defog) | done: names + matrices (FAUXJI3) | done / tune |
| Custom settings C1-C7 (recipes) | **User Mode 1 / User Mode 2** ("save current settings") | rename "C1 Recipe"/"C2 Recipe"; store e.g. a Classic Chrome and an ACROS recipe | text only |
| Film simulation bracketing | **PSS BKT** (Photo Style bracket) | rename "FILM BKT"; find which 3 styles it shoots and point them at three sims | text + small data/code |
| Dynamic Range DR100/200/400 | **Smart Range**, **ACB** | rename "D-Range" / "DR Auto" | text |
| Highlight / Shadow tone | 9 tone curves + Contrast setting | per-style curves (code patch: style -> curve table; new curves in a cave); repurpose Contrast as "Tone" | code, medium |
| Grain effect | "Add Noise" (playback edit, aged look) | rename "Grain Effect"; capture-time grain = long shot | text / hard |
| Colour Chrome effect | CLUT stage (per-hue saturation) 0xC044A4F4 | decode CLUT tables, deepen reds/blues per sim | decode, medium |
| WB shift per recipe | WB detail (BA/GM shifts) saved in User Mode | include in recipes | none |
| Q menu | Fn panel + XML layouts | reorder / relabel via the layout XML | medium |
| Fuji-like shutter sound | Shutter Sound 1/2/3 | replace one with a synthesized click | data |
| Boot logo | Start Image Logo / power-on JPEG | FAUXJI boot screen | data, easy |
| Assignable button | "User can designate the function of AEL button" | assign to Photo Style for a one-press film sim | none / check |

### Suggested order (lowest risk first, each a data edit)
1. Boot screen JPEG + renames (User Mode -> C1/C2, PSS BKT -> FILM BKT, Smart
   Range -> D-Range, Add Noise -> Grain Effect): one flash, text/image only.
2. Confirm the style-number mapping with the FAUXJI3 test shots; fix swaps.
3. Shutter/start sounds (after confirming the .snd sample rate).
4. Per-style tone curves (small code patch) -> real Classic Chrome shadows, Eterna
   softness, Velvia punch.
5. Real colour for Bleach Bypass / Nostalgic Neg. (styles 10/11 -> matrix + curve slots).
6. CLUT (Colour Chrome-like) and film-sim bracketing.


## Build: FAUXJI4 — boot screen + Fuji-style renames (1 Nov 2026)
`extracted/tl500_008264_FAUXJI4/` = FAUXJI3 (colour matrices, not yet tested) +
SPID.Rom edits, EXIF model `TL500-I`.
- **Boot screen:** `bg_power_on_off_422.jpg` replaced via `tools/spid_files.py`
  (in place, size field updated) with `tools/bootscreen.py firmware`: "FAUXJI FILM
  X20 / Digital Camera / Korean body. German glass. Japanese colors. / Firmware by
  an economist and a chatbot. / Warranty void since 2026." 22,116 bytes (slot
  22,528), baseline 4:2:2, JFIF APP0 stripped so the marker layout matches the stock
  file (DQT, DQT, SOF0 2x1/1x1/1x1, 4 DHT, SOS).
- **Renames:** User -> Recipes, User Mode Set -> Save Recipe, User Mode 1/2 -> C1/C2
  Recipe (+ help lines), playback Photo Style Selector -> FAUXJI FILM PRO, PSS BKT
  -> FILM BKT, Smart Range -> D-Range, Add Noise -> Grain Effect (+ help).
- Changed bytes are confined to: the one directory size field, the English text table, and
  the image slot. First change to a SPID.Rom *file* (not text): if the power-on
  screen shows garbage or stays black, re-flash FAUXJI3's SPID.Rom.


## FAUXJI3/4 field test (1 Nov 2026) and FAUXJI5 retune
Owner: boot screen and renamed menus fine. 11 test shots SAM_0421-0431 (same room,
P mode, ISO200 1/60, Daylight WB). Mean HSV saturation / luma:
PROVIA 0.40/0.44, ASTIA **0.27**/0.50, Velvia 0.55/0.46, Reala 0.44/0.49,
Classic Chrome 0.31/0.51, Classic Neg. 0.30/0.51, Eterna **0.42**/0.49, ACROS 0/0.48,
Sepia **0.39 (colour)**, Bleach Bypass = Sketch (mono hatching), Nostalgic Neg. = Defog.
Findings: (1) **Soft = style 7, Calm = style 2** (ASTIA came out desaturated, Eterna
normal), so the data is swapped. (2) **Style 8 never used its matrix**: the CCMatrix switch
covers 0-7 and its default only picked matrix 8 when flag this+0x3E was set. (3)
Tone is the main gap from Fuji: Classic Chrome sits on the brightening curve 5 and
Velvia has no extra contrast.

### Build: FAUXJI5 (`extracted/tl500_008264_FAUXJI5/`, EXIF `TL500-J`)
All in `tools/fauxji.py` (reproducible from FAUXJI4):
- ASTIA/Eterna data swapped to the real slots.
- Sepia: CCMatrix default case `ldrb lr,[fp,#0x3e]; cmp lr,#0; beq` (0xC044937C) ->
  `ldr lr,[fp,#0xc]; cmp lr,#8; bne`, so style 8 uses its matrix (capture only; live
  view has no such branch).
- **Per-style tone curves:** hook 0xC0449864 (gamma stage, curve-base load) ->
  `b 0xC0703740`; routine: if style < 12, special tone mode off (this+0x44 != 3) and
  table[style] != 0xFF, point at a FAUXJI curve (key 0x20+n so the parameter refreshes),
  else stock `0xC07B9AD4 + n*256`. Table 0xC07037A0, six 256-byte monotone-cubic
  curves at 0xC07037B0-0xC0703DB0 (velvia, chrome, neg, eterna, astia, reala).
  PROVIA/ACROS/Sepia keep the camera's own curve. Curves never lift black and keep a
  soft shoulder above ~224 (11 EV CCD).
  Samples (in 0,32,64,128,192,224,255): Velvia 0,22,52,134,208,234,255;
  Chrome 0,19,46,120,192,222,250; Neg 0,17,45,128,210,236,255;
  Eterna 0,31,65,128,185,213,246; Astia 0,32,66,131,191,221,253; Reala 0,28,60,129,197,227,255.
- Classic Chrome / Classic Neg. / Eterna overall gain back near 1 (density now from the curve).
- Caveat: curves live in the zero area beyond the proven cave (0xC0703740+); if a
  look's tone is odd/corrupt, that area is being written at runtime. Live view
  doesn't get the custom curves (its gamma stage is separate).


## FAUXJI5 broke live view: 0xC0703704+ is NOT free space (lesson learned)
Owner photo: menus/overlays fine, live image a field of garbage. Cause: the "cave"
zeros at 0xC0703704-0xC0703E28 are a **driver's RAM shadow of hardware registers**:
the literal pool at 0xC004E718 pairs each RAM slot with a register (0xC0703704 <->
0x800B3A00, 0xC0703718 <-> 0x800B3A04, 0xC070372C <-> 0x800B3A10, 0xC0703740 <->
0x800B3D00, 0xC0703774 <-> 0x800B3D04, ...; 54 references into the area). FAUXJI5's
curve code/data at 0xC0703740+ was pushed into image-pipeline registers, which garbled
the live view. The Manual auto-ISO code (since MAUTO) also sat on three shadow slots
(0x800B3A00/04/10). That block appears unused on this camera (no visible effect
across many builds), but it's wrong all the same. Unreferenced zero runs elsewhere all turned
out to be gaps *inside* larger tables, so they're also unsafe.
**Rule from now on: no zero-filled "caves". Use code that provably never runs.**

### Build: FAUXJI6 (`extracted/tl500_008264_FAUXJI6/`, from FAUXJI4, EXIF `TL500-K`)
`tools/fauxji.py` rewritten:
- **0xC0703704-0xC0703E28 restored to stock zeros.**
- Manual auto-ISO routine (EV comp, ISO 80-3200) moved to **0xC042661C**, the
  factory "Check EEPROM" E2PR.CSV dump. Only caller 0xC04278A8 inside
  CProductionModeAdjustFunc (0xC04274BC), reached only via the production command
  table at 0xC0843EF8. Hook 0xC0540938 -> `b 0xC042661C`.
- Tone: the stage's own 19-word style check (0xC0449788-0xC04497D4) rewritten in
  place as `if style<12 and table[style]!=0xFF: curve=table[style]`, table inline at
  0xC04497B4 = [FF,4,0,8,7,3,6,1,4,FF,FF,FF]. The Beauty Shot override after it is
  untouched. Custom curves written into stock slots **6/7/8** (Velvia / Classic
  Chrome / Classic Neg.), which costs Beauty Shot face-tone levels 1-3 their brighter
  curves. Eterna/ASTIA/Reala use stock Contrast -2/-1/+1 curves; ACROS/Sepia curve 4.
- Matrices, ASTIA/Eterna swap and Sepia fixes as in FAUXJI5.


## FAUXJI6 field test (1 Nov 2026): live view fixed, all looks distinct; FAUXJI7 retune
SAM_0432-0441 (`TL500-K`; live view back to normal). Scenes vary, so I compare
yellow-shirt saturation (fixed subject) and tone percentiles rather than whole-frame means:
| look | yellow sat | median Y | p10 / p98 | IQR (mid contrast) | verdict |
|---|---|---|---|---|---|
| PROVIA | 0.70 | 0.37 | 0.10 / 1.00 | 0.55 | baseline |
| ASTIA | 0.72 | 0.48 | 0.15 / 1.00 | 0.50 | soft, slightly richer: ok |
| Velvia | 0.85 | 0.48 | 0.07 / 1.00 | 0.65 | ok |
| Reala Ace | 0.80 | 0.45 | 0.08 / 1.00 | 0.62 | too saturated |
| Classic Chrome | 0.69 | 0.36 | 0.05 / 0.97 | 0.58 | dense/held highlights ok, colour not muted enough |
| Classic Neg. | 0.73 | 0.45 | 0.04 / 1.00 | 0.72 | hard ok, colour too strong |
| Eterna | (none) p90 0.23 | 0.48 | 0.14 / 1.00 | 0.43 | soft ok, too grey |
| ACROS | mono | 0.42 | 0.06 / 1.00 | 0.68 | ok |
| Sepia | warm mono | 0.39 | 0.05 / 1.00 | 0.67 | **fix works** |
| Nostalgic Neg. (Defog) | 0.60 | 0.41 | 0.07 / 0.91 | 0.52 | warm, soft highlights: close enough for now |
The contrast curves raise display saturation, so muted looks need a lower matrix
saturation. **FAUXJI7** (`TL500-L`, 109 bytes vs FAUXJI6, matrices only):
Reala Ace sat 1.08 -> 1.00 (curve-only difference from PROVIA); Classic Chrome
(0.68,0.78,0.80) -> (0.55,0.65,0.70); Classic Neg. (0.95,0.70,0.90) -> (0.80,0.58,0.80);
Eterna 0.62 -> 0.78. Bleach Bypass wasn't shot this round (still Sketch).


## Build: FAUXJI8 — all 11 looks real + gentler high-ISO sharpening (1 Nov 2026)
`extracted/tl500_008264_FAUXJI8/` (EXIF `TL500-M`), all via `tools/fauxji.py`
(idempotent: re-running on its own output changes nothing).

**Sketch/Defog are effects 10/11 -> internal styles 9/10** (GetSmartFilter map
0xC07B0198 = [0,0,1..11]); **style 11 = Custom RGB** (CLUT stage 0xC044A5AC uses
the RGB triple only when style == 11). Samsung's art-effect engine is off for them:
- effect->art-type table 0xC0766518: [10]=5 (Sketch), [11]=6 (Defog) -> 0;
- "heavy effect" helper 0xC03CBB28 compares effect with 10/11 (0xC03CBB58/64) -> #0xFF;
- Sketch capture-size rule (forced 5 MP) 0xC01D2060 `cmp lr,#0xa` -> #0xFF.
**Matrices for 12 styles:** the CCMatrix stage's only literal for the style table
(0xC044A63C, was 0xC07BB28C) now points at a 12-slot table at **0xC0426660**
(inside the factory-only EEPROM-dump function, after the ISO routine; ends 0xC0426810
< function end 0xC0426898). The default case handles every style >= 8:
`blt` at 0xC0449384, and `orr r2,r2,lr,lsl #8` at 0xC04493C4 (key byte = style).
Live view keeps its stock 9-slot table (styles 9-11 preview neutral).
- Bleach Bypass (9): sat 0.38-0.40, faint cool, hard curve (slot 8).
- Nostalgic Neg. (10): warm amber gains (1.06, 1.01, 0.88), red sat 1.05, soft curve (slot 1).
- Custom RGB (11): identity (unchanged behaviour).

**Noise/sharpening study:**
- Sharpening EE (0xC0449FBC): 25 rows x 6 int32 at 0xC07B987C, row = (Sv-62)/4 cap
  24. Stock already tapers: coring 32 -> 48, gain 15 -> 8 (ISO 100 -> 800+). FAUXJI8:
  rows 16-24 (ISO 800+) gain 8 -> 7, coring +2 (+4 at 1600+). Low ISO untouched.
- Luma/chroma NR YCNR (0xC044A2E4): 6 rows x 96 B at 0xC09AFD84, row =
  (Sv-56)/16 clamped to 5. Only fields 0-1 vary: (1,26) (2,32) (6,42) (8,60) (12,72)
  (18,112) = strength/threshold by ISO. **ISO 3200 reuses the ISO 1600 row** (the
  clamp), so 3200 gets 1600-level NR. Not changed yet; tune from a high-ISO test.
- Recommendation for a Fuji-like rendering with zero risk: Image Adjust >
  Sharpness -1 (Samsung's own control).


## FAUXJI8 field test (1 Nov 2026) and FAUXJI9
SAM_0442-0452 = the 11 looks, SAM_0453-0454 = ISO 3200 1/30 in a very dark room.
**New tool: MakerNote byte 15650 = internal style number** (0-11), so every test
shot now identifies its own look. The quick-menu order is Normal, Sketch, Defog,
Soft, Vivid, Forest, Retro, Cool, Calm, Classic, Negative (Sketch/Defog = positions 1-2,
which is why the 0x88 RAW mask blocked items 1-2).
Results: 442 PROVIA, 445 ASTIA, 446 Velvia (red R-G 0.65 vs PROVIA 0.26), 447 Reala,
448 Classic Chrome (darkest), 449 Classic Neg. (hardest), 450 Eterna (low sat, soft),
451 ACROS, 452 Sepia: all as designed. **443 (style 9, Bleach Bypass) = Sepia colour
at 5 MP; 444 (style 10, Nostalgic Neg.) = soft Sepia.** Causes:
1. the capture CCMatrix stage clamps the key's style byte to 8 (0xC0449584-0xC04495DC,
   `mov r0,#8` limit / `mov sb,#8` cap), so 9 and 10 used matrix 8;
2. the 5 MP: UI rule "PSS menu position == 1 (Sketch)" -> menu 0x91 (photo size)
   allow-mask 0xFFF3E0 (0xC04D24FC).
Also, live view's default case (0xC0446194) clears the style byte, so styles >= 8
previewed in colour (owner: "it looks color until I shoot").
ISO 3200 at 100%: fine luma grain + moderate red/green chroma speckle in deep
shadows; the scenes were >1 stop below what ISO 3200 can expose (median Y 0.07).
NR left stock (stronger NR would smear the fine grain; this is near the CCD's limit).

### Build: FAUXJI9 (`extracted/tl500_008264_FAUXJI9/`, FAUXJI8 + 29 bytes, EXIF `TL500-N`)
- still clamp: limit 8 -> 12, cap 8 -> 11 (0xC0449588, 0xC04495DC);
- Sketch photo-size rule off: 0xC04D24FC `ldr r1,=0xFFF3E0` -> `mvn r1,#0xFF000000`;
- live default case 0xC04461BC: 6 stack-shuffle words -> `ldr r2,[fp,#0xc]; cmp r2,#8;
  orreq r0,r0,#0x800; cmp r2,#9; orreq r0,r0,#0x100; strd r0,r1,[sp,#0x10]`, so Sepia
  previews in sepia (live slot 8) and Bleach Bypass in B&W (live slot 1, ACROS);
  Nostalgic Neg. and Custom RGB preview neutral (colour looks, per the owner's request).

### FAUXJI9 field test (1 Nov 2026): all looks reach their own colour
SAM_0455-0464 (`TL500-N`, MakerNote style byte checked): style 9 Bleach Bypass is now
desaturated/hard (sat90 0.58 vs PROVIA 0.91) instead of Sepia; style 10 Nostalgic
Neg. is warm and soft (IQR 0.38, p10 0.15); every other style as designed. Bleach
Bypass still saved at 2592x1944: most likely the Photo Size setting the old Sketch rule
set to 5M is still stored (the rule itself is now off); owner to set 10M and see if it sticks.
Recipe tweak queued for the next build: Bleach Bypass saturation 0.38 -> ~0.30 (reds
still a bit strong after the hard curve).


## Per-hue colour: what the hardware offers (1 Nov 2026)
- The **CLUT stage (0xC044A4F4) is not per-hue**: it sets a (u,v) colour shift (only
  Custom RGB / Beauty Shot use one) and points at a 1 KB table 0xC07BA3D4 + n*1024
  (256 int32) chosen by ISO. The tables are an identity ramp, a flat gain 64 and a
  16 -> 64 ramp: a saturation-dependent chroma gain, i.e. chroma-noise suppression.
- **Per-hue saturation is the PCSE stage** ("Primary Color Saturation Enhancement",
  WB names IPCM_PCSE_PrimaryGain/GeneralGain/SPRange/GrayTH; TL stage 0xC04484B0).
  It picks 6-column delta rows from three tables by ISO (this+0x28) and light level
  (this+0x30/+0x34 vs 0x40/0x80/0xA0), **not by style**:
  0xC07BAD8C (10 rows: column 2 cut -250 -> -1000 as ISO rises), 0xC07BAE7C (18
  rows: cols 1/3/4), 0xC07BB02C (14 rows: cols 0/5); base gains/ranges near
  0xC07BACD4-0xC07BAD2C ((2100,3000)x3, (500,1000), (200,500), (100,250)).
  The 6 columns are taken to be hue bands; which column is which hue is unknown.
- Space for per-style per-hue code + table: the factory-only BATTERY.CSV function
  0xC0425430 (3,184 bytes; only caller 0xC04277E8 inside the production dispatcher
  0xC04274BC, reached via the factory command table 0xC0843E20-0xC0843F00).

### Build: CAL (`extracted/tl500_008264_CAL/`, EXIF `TL500-C`) — one-off calibration
FAUXJI9 + Bleach Bypass sat ~0.30 + every AD8C row = (-300, -600, -900, -1200,
-1500, -1800). Photograph `research-out/fauxji_colour_chart.png` (12 hues + skin
+ greys) on a screen in PROVIA: how much each hue loses tells which column is which band.

### CAL field test: chart shot SAM_0465-0467 (ISO 100, Daylight WB, PROVIA)
Measured patch saturation (HSV S): red 0.82, orange 0.79, **yellow 0.27**, lime 0.57,
green 0.67, spring 0.83, cyan 0.97, azure 0.76, blue 0.69, violet 0.50, magenta
0.44, rose 0.51. Yellow is clearly the hardest hit, but the screen's bluish white point also
desaturates yellow, so a **baseline shot without the cuts is needed** to separate the two.
FAUXJI10 (`TL500-O`) = FAUXJI9 + Bleach Bypass sat ~0.30, PCSE tables stock: flash it,
shoot the same chart the same way, then diff the two per patch.

### Baseline (SAM_0468, FAUXJI10) vs CAL: saturation kept per patch
yellow 0.39, lime 0.60, rose 0.66, green 0.71, blue 0.85, magenta 0.86, violet 0.87,
orange 0.88, red 0.89, azure 0.89, spring 0.95, cyan 0.99 (red/cyan patches clip,
hiding small cuts). Settled: **col5 (-1800) = yellow**, **col4 (-1500) = magenta/rose**,
**col2 (-900) = blue** (matches Samsung cutting col2 at high ISO: the CCD's noisiest channel).
Cols 0/1/3 (red/green/cyan, some order) still ambiguous.
**CAL2** (`TL500-D`): AD8C rows = (-1800, +1200, 0, -600, 0, 0): big cut / boost / small
cut on cols 0/1/3 only, which also checks that positive values add saturation.

### CAL2 vs baseline -> PCSE band map (1 Nov 2026)
CAL2 (cols 0/1/3 = -1800/+1200/-600) kept: red 0.47, orange 0.42, skin 0.57, rose
0.71 (col 0 cut); blue 1.23, violet 1.29, magenta 1.32, azure 1.17, spring 1.14 (col 1
boost); green/yellow/lime ~1.0. Combined with CAL1: **column order R, B, G, C, M, Y**
(0 red/orange/skin, 1 blue/violet/magenta, 2 green, 3 cyan (clips on the screen chart),
4 rose, 5 yellow); positive = more saturation; roughly x(1 + v/3500).
Stage detail: AD8C stride is 48 bytes = 5 entries x 12 int32 (two linked halves of 6
bands; stock halves near-equal; the calibration changed both, so deltas go to both).

## Build: FAUXJI11 — per-look per-hue colour (`TL500-P`)
`tools/fauxji.py`: AD8C restored to stock; 12 per-style copies (stock + HUE[style]
deltas on both halves, 240 bytes each) at 0xC0425460 inside the factory-only
BATTERY.CSV function (routine at 0xC0425430: `r7 = tables + style*240`, then the
stage adds entry*48); hook 0xC0448E1C `ldr r7,=0xC07BAD8C` -> `b 0xC0425430`.
Deltas (R, B, G, C, M, Y): Eterna (-300,0,-200,+250,-200,-300); Classic Neg.
(-150,+100,-700,+250,-300,-450); Classic Chrome (-450,+500,-350,+250,-250,-400);
Reala (-100,+100,+100,0,0,0); Velvia (-250,+450,+450,+300,+150,+250);
ASTIA (-150,+300,+200,+200,0,0); Nostalgic Neg. (+200,-300,-250,-250,0,+350);
others 0. Capture only (live view has its own PCSE stage).

### FAUXJI11 field test (garden set SAM_0476-0486 + PROVIA selfie SAM_0487)
Shots aligned to PROVIA by phase correlation, then region saturation vs PROVIA:
Velvia orange +36% / green +56% / blue +15%; ASTIA ~0; Reala ~+2%; Classic Chrome
orange -36% / green -17% / blue -30%; Classic Neg. -26% / -8% / -16%; Eterna
-48% / -46% / -34%; Nostalgic Neg. orange 0 but hue 30 -> 42 (amber), green -19%,
blue -28%, neutrals warm; Bleach Bypass -69/-63/-48%, neutrals clean.
PROVIA skin (owner, brown skin, shade): hue 19.5, sat 0.30, value 0.66 = natural.
Skin sits in band R, so Velvia would push skin orange and Classic Chrome / Eterna would
grey it. **FAUXJI12** (`TL500-Q`, PCSE copies only): Velvia R -550, B +600, G +400;
Classic Chrome R -300, B +1000, C +450, M -400; Classic Neg. G -1100, Y -600, R -50;
Eterna R -100, B +150, G 0, Y -150; ASTIA B +450, G +350.

### FAUXJI12 field test: flowers / selfies (sky and no sky) / sunset, SAM_0488-0533
Flowers (aligned, vs PROVIA): Velvia pink +35% orange +29% green +58%; Classic Chrome
pink -35% yellow -49%; Classic Neg. pink -32% yellow -48% green -10%; Eterna -37..-65%;
Bleach -58..-76%; Reala ~0..+8%; ASTIA ~-15% warm, +4% green. **Neutral road tinted**
in strong looks (PROVIA sat 0.02 -> Velvia 0.13 green, Reala 0.08, ASTIA 0.07 yellow-green).
Selfies (face pixels, centre crop): PROVIA skin hue ~22 sat 0.47 (warm evening light);
Classic Chrome 0.45 (alive, not grey), Eterna 0.32, Classic Neg. hue 27 (slightly yellow);
Velvia skin mostly beyond 0.58 sat, orange wall 0.51 -> 0.73 (too hot).
Sunset (similar exposures except PROVIA/Bleach at 1/1500): sky sat Velvia 0.55,
Reala 0.40, Classic Neg. 0.36, ASTIA 0.31, Classic Chrome 0.30, Nostalgic 0.26,
Eterna 0.19; clipping lowest in Classic Chrome (0.4%), highest Classic Neg. (4.8%);
sun halo PROVIA hue 50 (warm) vs 71-98 (yellow-green) in Reala/Neg/ASTIA/Velvia/Eterna,
from red cuts plus green boosts acting on near-neutrals.
**FAUXJI13** (`TL500-R`): Reala PCSE all 0; ASTIA (0,+450,+150,+200,0,0); Velvia
(-750,+600,+250,+300,+150,-150) and matrix red row 1.2 -> 1.1; Classic Chrome
B +1300, C +600. Bleach Bypass still 2592x1944: no other UI size rule found (the
PSS==1/2 check at 0xC04D2D28 only resets the style in some modes); most likely the
stored Photo Size is still 5M.

### FAUXJI13 final colour check (SAM_0534-0566: sunset garden / flowers / selfie on green)
Selfie skin (green background, centre crop): PROVIA hue 17.7 sat 0.43; Velvia 0.48
(fixed, was > 0.58), Reala 0.49, Nostalgic 0.44 (hue 21.6), ASTIA 0.39, Classic Neg.
0.39, Classic Chrome 0.32, Eterna 0.25. Sunset halo hue back to warm (13-32) in all
colour looks (was 71-98 yellow-green); Classic Chrome clips least (1.5% vs 7-8%).
Grey road: Classic Chrome/Eterna clean (0.02-0.03), Velvia 0.10 (slight green, mostly
its matrix boost). Backlit sky: Classic Chrome 0.17 vs PROVIA 0.27 (a bit pale).
**Colours declared done.** Queued micro-tweaks for the next (UI) build: Velvia PCSE
G +250 -> 0; Classic Chrome matrix blue row 0.70 -> ~0.80.

## Portrait orientation: the TL500 has no orientation sensor
Every portrait shot has EXIF Orientation = 1. The firmware has no accelerometer /
orientation code (the WB850F has LibProduct_AccelManager + GetOrientation; the TL500
has none), and the TL500's settings list (29 `SETUP_MENU_*` names) has no
AUTO_ROTATE; the "Auto Rotate" string in SPID.Rom comes from Samsung's shared string
table. `acc_rotation.c` is the 2D graphics accelerator (playback rotate), "AF TILT" a
factory lens check. So the camera can't know how it was held. Options: Playback >
Rotate in camera; rotate on import; or (long shot) a firmware feature that sets the EXIF
orientation from face detection (FD handles rotated faces: SetRotateFace) or a
manual portrait toggle.


## Build: FAUXJI14 — live view previews each look (`TL500-S`)
- **Live tone:** the live gamma stage 0xC04463C4 mirrors the capture one (style 1 -> 4,
  4/5/7 -> 5, else Contrast map 0xC07B3E40) with its own curve table 0xC07B2C88 (an
  exact copy of the capture curves). Its 19-word style check (0xC044640C-0xC0446458)
  is now the same in-place table lookup ([FF,4,0,8,7,3,6,1,4,8,1,FF]) and live slots
  6-8 hold the Velvia / Classic Chrome / Classic Neg. curves.
- **Live matrices:** Reala's live case (0xC04460BC `orr r2,r2,#0x500` -> `#0`) uses slot
  0 (its matrix is the identity anyway), freeing live slot 5 for **Nostalgic Neg.**; the
  live default case (12 stack-shuffle words at 0xC04461BC) maps 8 -> slot 8 (Sepia),
  9 -> 1 (B&W, Bleach Bypass), 10 -> 5 (Nostalgic), with the same stack/register state
  as stock (`strd` to [sp,#0x10] and [sp,#0xe0], r2:r3 = r0:r1).
- **Not in the preview:** per-hue saturation. Live view's PCSE stage (0xC0445DB0)
  registers one fixed block (0xC09AF7B0), no per-ISO/per-style tables; the per-hue
  deltas are moderate (~ +/-10-30% on specific hues), so the preview is close.
- Queued micro-tweaks folded in: Velvia PCSE G +250 -> 0; Classic Chrome matrix blue
  row 0.70 -> 0.80.
- Added to the UI list (last): auto-rotate from face detection (no orientation sensor).


## Build: FAUXJI15 — Sepia preview fix + film-look cheat sheet (`TL500-T`)
- Owner (FAUXJI14): the preview matches the photos, except Sepia still previewed as a negative.
  Live view has its own invert stage (0xC04470F0, `cmp lr,#8` at 0xC0447100) -> #0xFF.
- Help lines now say what each look is **best for**, about 56-60 chars, e.g. Velvia "Vivid
  slide film. Best for: landscapes, flowers, sunsets." (idx 988-996, 1295, 1296).
  Space came from strings for hardware/features this camera lacks: 751 (alkaline-battery
  warning), 838 (engineering sample), 966 (front-display demo), 1126 (touchscreen), 1310
  (map/music format warning), 1369/1370 (composite modes from other models); 700 bytes
  still spare. Whether ~60 chars fit on screen without clipping is still to check.

## UI rework: order of work
1. Check the cheat-sheet lines fit on screen (shorten if they clip).
2. Bleach Bypass 5 MP: owner sets Photo Size to 10M once, see if it sticks.
3. Shutter + start-up sounds (confirm .snd format by ear, then synthesized click/chime).
4. Finish the Fuji-style menu pass (check C1/C2 Recipe, FILM BKT, D-Range, Grain Effect
   screens; rename anything else the owner wants).
5. FILM BKT: point Photo Style bracketing at three chosen looks.
6. Menu theming: backgrounds (bg_menu*.jpg) and layouts (the 7 XML documents).
7. Reproducible patch script: one command rebuilds FAUXJI from Samsung's official file.
8. (Last) Auto-rotate portraits from face detection (no orientation sensor).

### FAUXJI15 field test: SUCCESS
Owner: the cheat-sheet lines fit on screen and look great; Sepia previews correctly.
UI steps 1 and the Sepia preview are done.


## Sounds (1 Nov 2026)
SPID.Rom holds 26 `.snd` files: **headerless 16-bit little-endian mono PCM at 32 kHz**
(the byte order shows in waveform smoothness; the rate was confirmed by ear by the owner): Shutter1-3,
ShutterShort, PowerOn1-3, Beep/AF/Menu/Self-timer cues, NoBattery, Warning and five
slideshow music tracks (2.4-4.2 MB each). Stock shutter peak 14-33k / rms 1-2k, start
sounds peak ~25k.
`tools/sounds.py` synthesizes (no samples from any other camera):
- **shutter** (-> Shutter3_32m.snd, so menu Shutter Sound 3): leaf-shutter open tick +
  softer close tick 35 ms later (2.5-9 kHz noise bursts), faint 4.2 kHz ring, 190 Hz
  body; 0.16 s, peak 21k.
- **chime** (-> PowerOn3_mono.snd, menu Start Sound 3): A5 then E6 soft bell with 2x
  and 3.01x partials, 0.42 s decay; 1.25 s, peak 20k.
Build **FAUXJI16** (`TL500-U`) = FAUXJI15 + these two files (only those two slots and
their size fields changed). Select Setup > Sound > Shutter Sound 3 / Start Sound 3.

### Shutter sound: owner's pick F2 (FAUXJI16 rebuilt)
Three rounds of synthesized shutters were rejected ("doesn't sound mechanical", then "sounds
musical", then "none of these sound like a camera"): sinusoidal modes read as pitch, and
even dense noise models didn't sound like a real mechanism. What worked is **reshaping
Samsung's own Shutter1 recording**: its two mechanical events (~42 ms and ~349 ms) pulled
60 ms apart, played 15% faster (smaller mechanism), high-passed at ~350 Hz, 0.13 s, peak 20k.
`tools/sounds.py shutter_f2()` rebuilds it from the stock ROM (matches the approved
preview within 1 LSB). FAUXJI16 (`TL500-U`) = FAUXJI15 + F2 as Shutter Sound 3 + the
chime as Start Sound 3.


## One-command build (1 Nov 2026)
`python tools/build_fauxji.py <stock dir> <out dir> [--check <ref dir>]` rebuilds the
complete FAUXJI firmware from Samsung's official 008264 files:
1. verifies all five stock files by SHA-256;
2. .elf: applies `patches/fauxji_elf_runs.json` (203 runs, 5,459 bytes of FAUXJI code
   and data), then re-runs `tools/fauxji.py` (idempotent colour recipes, so tuning
   there flows straight into the build);
3. SPID.Rom: replays the text passes in `patches/fauxji_text.json` (same order as the
   original builds, so the layout is byte-identical), renders the boot screen
   (`bootscreen.py`), synthesizes the chime and reshapes the shutter from the user's
   own stock ROM (`sounds.py`);
4. copies ONBL1/ONBL2/FWUP unchanged.
Verified: output is **byte-identical to FAUXJI16**. The patch package contains no
Samsung files (the stock firmware is the user's input).

## FILM BKT (Photo Style bracket): how it picks styles (in progress)
TL GetSmartFilter (0xC0443A90): when bracket type == 4 (PSS), the effect comes from
capture-info item 0x57 (getBracketCaptureInfo 0xC01C60B4 -> 0xC01C74C4(store, 0x57))
instead of the menu value. The writer of item 0x57 isn't found yet (the call chain goes
through function-pointer tables). Plan: one FILM BKT burst on the camera; MakerNote
byte 15650 of the three frames gives Samsung's three styles, then search the firmware
for that sequence.


## FAUXJI17/18: Fuji-style menu names + AE-L button cycles film looks (1 Nov 2026)
**Renames (text pass FAUXJI17, 31 strings):** Metering -> Photometry, Drive -> Drive
Setting, Image Adjust -> Image Settings, Contrast -> Tone Curve, Saturation -> Color,
OIS -> IS Mode, Photo Size -> Image Size, Quality -> Image Quality, Quick View -> Image
Disp., Grid/Guide Line -> Framing Guide, ACB -> DR Auto, Key mapping -> AE-L Button
(AE-L / **FILM SIM** / AE-L/AF-L), Smart Filter -> Advanced Filter, Bracket ->
Bracketing, Start Image -> Startup Screen, Function Description -> Help Text.

**AE-L button -> FILM SIM** (`tools/fauxji_ui.py`, wired into the builder):
- Live-view key dispatcher 0xC04C18CC switches on the logical key (16-entry table at
  0xC04C19F0): key 0 -> AE-lock handler 0xC04C1414 (UI 0x63), key 14 -> AF-lock
  handler 0xC04C1624 (UI 0x64). The "AE-L Button" setting chooses which key the button
  sends, so the AF-L option is repurposed: key 14's case (0xC04C1AE8) calls a new routine
  at 0xC0425FA0 (tail of the factory-only BATTERY.CSV function, after the PCSE tables).
- Routine: on a press (same event virtual call as the stock handlers), read the Photo
  Style at 0xC0D7F300+0x40, step to the next entry of FAVOURITES = PROVIA, Classic
  Chrome, Velvia, ASTIA, Classic Neg., ACROS, Nostalgic Neg. (menu values 0,6,4,3,7,9,2),
  then the menu's own commit sequence (menu handler ~0xC050C494): setUiValue(0x41, v)
  0xC048F630 -> apply 0xC04D2A18 -> menu masks 0xC04D2000 -> GUI event 0x42
  (0xC048FD5C) -> 0xC04DC174(0x41) -> 0xC04CDB70(0x41).
- Setting IDs found on the way: capture setter 0xC04CFD28 (switch on id-0x30; **0x41 =
  Photo Style**, stores the +0x40 cache and capture menu 0x1E); apply dispatcher
  0xC04D2A18 (0x41 -> 0xC04D1538).
- **Bleach Bypass 5 MP solved:** 0xC04D1538 (applied whenever the style is applied) forced
  photo size >= index 5 for Sketch (menu value 1) and two more minimums (+0x6C >= 3,
  +0x70 >= 7) for Sketch/Defog; checks at 0xC04D15BC / 0xC04D1608 / 0xC04D1610 ->
  #0xFF. (The owner setting 10M couldn't stick because this rule re-applied.)
Build **FAUXJI18** (`TL500-V`) = everything so far (FAUXJI16 + renames + FILM SIM +
5 MP fix). Not flashed. Test: Setup > AE-L Button > FILM SIM, press AE-L in P mode.


## FAUXJI18 field test + FAUXJI19
Owner: FILM SIM cycling **works**, but nothing on screen says which look is active;
Shutter Sound 3 didn't sound like F2.
- **Why the shutter didn't change:** the shutter sounds the camera plays are built into
  the program: pointer tables at 0xC0477E24 (copy at 0xC04781EC) -> `[u32 length][PCM]`
  blocks Shutter1 0xC095DBA8, Shutter2 0xC096B3E8, **Shutter3 0xC097CE4C** (64,474 B),
  plus AF OK/fail and warning cues. The SPID.Rom copies of the shutter sounds aren't used
  (start-up sounds aren't built in, so the chime in SPID.Rom is right).
  `sounds.patch_elf()` writes F2 into the built-in Shutter3 block (length 8068, rest
  zero); wired into the builder. **FAUXJI19** (`TL500-W`).
- **Which look is active:** the routine already calls 0xC04DC174(0x41), which reads the
  Photo Style and redraws its icon, but the icons are Samsung's style pictures (in
  `skin.bin`, a 9.9 MB custom bitmap container, not decoded). Leads for a text read-out:
  pop-up message event 0x0B (params 0x190+, flags in the upper bits; the AE-lock path
  already sends 0x1019E) and a GUI string-ID -> text-index table near 0xC07B67C0
  (3,090 entries). Not finished.


## GUI skin decoded + FAUXJI film badges (FAUXJI20, `TL500-X`)
**skin.bin** (SPID.Rom, 9.96 MB; `tools/skin.py`): header at +0 lists 6 section
offsets (0x20, 0x662F8C, 0x87FF44, 0x945754, 0x9740F0, 0x974760). Section 0 = images:
0x28-byte header (transparent key 0xFFFF00FF, ...), **711 images** with a u32 offset
table at skin+0x50 (offsets from the table start). Image = u32 width, height, size
(incl. the 16-byte header), type (3 = RLE). Each row: 0xFF + u16 row length (incl. 3),
tokens `c < 0x80` = run of c x next RGBA pixel, `c >= 0x80` = c-0x80 literal RGBA
pixels; magenta = transparent. All 711 decode with exact row widths; the encoder is
Samsung's scheme.
**Photo Style icons** (painter's palette + letters NOR V S F R CO CA CL N SK FD), three
sets: large 115x115 images 72-82 (quick menu), white 64x64 **414-424** (live view;
found by exact transparency outline against the grey set), grey 64x64 326/327/337-345
(disabled). `tools/badges.py` draws Fuji-style badges: STD (PROVIA), V, S (ASTIA), RA,
CC, NC, ET (Eterna), A (ACROS), SEP, EB (Bleach Bypass), NN (Nostalgic Neg.). The large
set gets film-frame plates with sprocket holes; the 64 px sets are pixel-exact solid
colours so the RLE fits (largest uses 95% of its slot). Written in place, offset table
untouched; the other 678 images are verified unchanged; only skin.bin bytes change.
Wired into `build_fauxji.py`. FAUXJI20 = FAUXJI19 + badges (label TL500-X).

### FAUXJI21: film-canister icons (`TL500-Y`)
Owner sent a Fuji film-simulation menu for reference (white film-canister silhouettes:
spool knob, film leader with sprocket holes, bold code with a big first letter and a
small second one). `badges.canister()` is our own drawing in that spirit: canister body
+ spool knob + leader with four sprocket holes on a 64-unit grid; codes STD, V, S, C c,
R a, N c, E t, A, SEP, E b, N n. The 115 px set is anti-aliased; the 64 px sets are
pixel-exact. All 33 fit in under half of their slots. The plate design is kept as
`plate_badge()`.
Flashed and confirmed: the canisters show in the quick menu and on the shooting screen.
But the live-view icon only changed after leaving live view (playback, mode switch),
not on each FILM SIM press.

### FAUXJI22: live-view icon follows FILM SIM (`TL500-Z`)
The menu commit sequence the FILM SIM routine copies never redraws live view: leaving a
menu re-enters the live-view state, and that state's entry redraws every icon. WB850F
symbols located the drawing: `CAPPGUIPreviewView::drawViewfinderIcon(bool)` walks the
current viewfinder item list and calls each item's draw function with its system value.
The TL500 copy is **0xC04B7444** (fuzzy match, same loop, without the blink timer); its
helper getViewfinderSystemIndex is 0xC04B6EAC, and 0xC04B74B4 draws a single item. One of
its callers is case 2 of the GUI handler **0xC049C1D4** (jump table 0xC049C270,
switch on the event id). GUI event 2 is posted with param 0 from 28 places in the
control layer, so the FILM SIM routine now ends with `0xC048FD5C(2, 0)` after its menu
sequence. The event is queued to the GUI task, so no drawing happens from the key task.
Only the routine (32 bytes) and the label differ from FAUXJI21; SPID.Rom is identical.
Flashed: Shutter Sound 3 = F2 confirmed, Bleach Bypass now saves full size (FAUXJI18
fix confirmed). The live-view icon still stayed on the first-drawn look.

### FAUXJI23: draw the icons directly (`TL-F23`)
Why event 2 (and the menu's 0x42) did nothing: the GUI states were identified by their
vtables. The live-view state is onEnter 0xC049FAF0 / onExit 0xC049FBC0 / handle
0xC049F1CC; its handler switches on event ids 0..0x2D and only redraws fixed items.
The handlers that answer events 2 and 0x42 with drawViewfinderIcon belong to other
states (vtables 0xC07C5048 and 0xC07C4EC8, the latter CAPPGUIPictbridgeState). Only the
live-view onEnter calls the redraw loop, hence "updates after playback/mode change".
The icon path itself is sound: GUI value 0x47 maps to UI 0x41 (table 0xC09B7420),
item 7 of the viewfinder list (table 0xC09BDE20) draws with 0xC04B9C3C(v) ->
0xC04B7550, which takes child v of the OSD item, hides the item's children if that
child isn't showing, then shows it; the value is read live via 0xC048F74C. TL osd
functions: get_child 0xC0200D84, get_item_visible 0xC0200AF4, clear_item 0xC0201694,
set_item_visible 0xC0201CAC.
The FILM SIM routine now ends with a direct `bl 0xC04B7444` (redraw every icon of the
current live-view list), in place of the GUI event.
Flashed: works, the canister now follows every press. Two issues: PROVIA showed no
icon, and the owner (not a Fuji shooter) wants the look's name shown on each press.

### FAUXJI24: PROVIA icon + name pop-up (`TL-F24`)
**Layout tree** (skin.bin section at +0x945754: u32 size, u32 count 2034, offsets, node
records): record = u16 length, u16 id, type, x, y, w, h, ..., parent id, ..., child count
and child ids; image nodes end with the skin image index. Hash table at +0x974760
((u32, hash, index) triples, 4177 = nodes + images + strings + ...). Film icon node
0x0CB9A7B4 = id 0x3F1 at (10,184), 58x58, 12 children in menu order -> white images
420 (STD), 422, 417, 423, 424, 418, 421, 416, 414, 415, 419, custom RGB 535.
- **PROVIA**: item 7's draw 0xC04B9C3C hides the node for value 0 (Samsung shows nothing
  for Standard); its `beq` at 0xC04B9C48 is now a nop, so child 0 (STD canister) shows.
- **Name pop-up**: the live-view help-text box (the mode description, item 44, drawn by
  0xC04B7BB8: frame nodes 0xCE12A81D + 0x49032BE5, text node 0x96879B21) is reused. New
  routine at 0xC0426810 (tail of the factory E2PR.CSV function, after the matrices):
  text property (0xC0202004, as stock), StringMgr_GetStaticString 0xC05BA87C(ctx
  [0xC0CA6C90], string index) for the look's name in the current language,
  osd_set_unicode_text 0xC0201488, then shows the three nodes (0xC0201CAC). Name indices
  per menu value: 182, 911, 986, 183-190. The FILM SIM routine calls it after the icon
  redraw. When the box hides is not known yet (stock hides it on a full live-view
  redraw: item 40 clears the live-view root 0xAFB3FC35); to be seen on the camera.

## Theming survey (for the Fuji look)
What draws the GUI, and what we can change (all in SPID.Rom; nothing is shipped):
- **Full-screen backgrounds**: 36 JPEGs, Samsung's blue glow and swoosh. 640x480:
  bg_menu, bg_language, bg_datetime_*, bg_timezone, bg_facelist, bg_firmware_update_*,
  bg_menu_hdmi_*, bg_voicerecord, bg_power_on_off (boot, done). 160x480 menu side panels
  with the tab icons baked in: bg_menu_{shooting 1-5, movie 1-4, playback 1-5, scene
  1-5, setting, bkt, pictbridge}. Each is replaced in its slot (sizes 9.6-41 KB). Plain
  dark designs compress far below that.
- **skin.bin images**: 711 RLE images, magenta = transparent. About 560 icons (live-view
  status, quick menu, settings values); widgets that set the Samsung look: cyan and blue
  selection bars and buttons (123, 126, 136, 312, 585), glossy grey panels (13, 14, 256,
  565), sliders and scales (219-223, 257/258, 627), dials (583, 613), popup frames,
  swirl animations (644-648), the scene-mode photos (195-206, 559). New images must
  fit the original byte block; flat colour designs do.
- **Layout tree** (2034 nodes, decoded above): positions and sizes; text colours and
  fonts not decoded yet. **Font**: section 1 of skin.bin is a TrueType font.
- **Strings**: renames done (FAUXJI17).

### What can go (room audit)
New pictures normally must fit the block of the one they replace. Two ways to get
more room:
1. **Inside skin.bin** (where every icon and widget lives): section 0 holds 711 images
   back to back (6.69 MB, offsets strictly increasing, no gaps), addressed only through
   the offset table at +0x50 (layout nodes refer to image numbers, not addresses). So
   section 0 can be **repacked**: shrink what we don't want to a 1x1 transparent image,
   write the rest one after another, rewrite the offset table. Total must stay under
   0x662F8C so the font, layout and hash sections stay where they are. Untested on the
   camera; one build will tell.
   Candidates: the 13 scene-mode photos (195-206, 559): **1.83 MB**; glossy panels,
   dials, colour wheel (13, 14, 557, 565, 583, 592): **0.69 MB**; swirl animations
   (644-648): **0.21 MB**. About 2.7 MB in all, 40% of the section.
2. **Whole files in SPID.Rom**: `cd.iso` (24.2 MB, the Samsung PC-software CD the camera
   shows over USB when "PC Software" is on) and the five slideshow music tracks
   (Slide_*.snd, 14.4 MB). Blanking them is easy; using the space means moving other
   files' directory offsets, which needs its own test.
Keep: calibration masks/RAWs (Mask_*, MASK_FOR_LSC_*, RAW_FOR_LSC_*), Ace.*, the
date/time and language screens, and the beeps.

### Fuji reference: X-T20 manual (owner's copy, not stored here)
Menu structure from its text: a full-screen list with the section title on top in
capitals (e.g. IMAGE QUALITY SETTING), items in capitals (IMAGE SIZE, IMAGE QUALITY,
RAW RECORDING, FILM SIMULATION, GRAIN EFFECT, DYNAMIC RANGE, WHITE BALANCE, HIGHLIGHT
TONE...), tabs in a column on the left, EXIT bottom right. Pictures rendered with PyMuPDF (installed with the owner's OK) and
sampled. The manual's screens are neutral greyscale:
- **Menu**: near-black frame and title bar (34,31,31); list rows dark grey (70,70,71),
  white capital text, thin separators; **selected row solid white with black text** and
  a right arrow for sub-menus; tab column on the left mid grey (99,100,102) with white
  glyph icons; page count "1/3" top right; "BACK EXIT" chip (143,145,147) bottom right.
- **Quick menu (Q)**: 4x4 grid of tiles (87,88,91) on (64,64,65), each a flat white
  glyph + value; the selected tile turns near-black with an inverted label; title top
  left ("SELECT CUSTOM SETTING"), "SET" bar at the bottom.
- **Shooting screen**: no panels over the picture, thin black strips top and bottom,
  flat white glyphs and plain numbers (S.S. 12000, F 5.6, ISO 51200), exposure scale
  bottom, histogram right.
Mapping to the TL500: menu backgrounds -> flat near-black JPEGs (tab icons redrawn as
white glyphs on grey); cyan/blue selection bars (123, 126, 312, 585, 136) -> white;
glossy panels (13, 14, 256, 565) -> flat dark grey; menu text in capitals (strings).
Flashed FAUXJI24: PROVIA's canister shows; no name appeared.

### FAUXJI25: name box survives redraws, hides on the next key (`TL-F25`)
The help box nodes sit where expected (frame 990 at (100,158) 440x118 under the
live-view root 742; text node 992), so the box was most likely shown and then wiped:
it is viewfinder item 44, whose draw 0xC04B7BB8 runs on every full redraw and on GUI
event 0xC (live-view handler case 0xC: item 44 drawn with the Help Text setting,
sysval 0x85). Changes:
- item 44's entry in the item table (0xC09BDF84) now points at a wrapper: while
  NAME_FLAG = look+1 it draws the name (the toast routine) instead of the stock box;
- FILM SIM sets NAME_FLAG before the icon redraw;
- key hook on the live-view dispatcher's first call (0xC04C1938 -> 0xC04DE310, r0 =
  logical key): any key other than 14 clears NAME_FLAG and hides the box via the stock
  draw(0), then continues as stock.
Code space: factory "ChineseCheckAdjustment" function 0xC042620C-0xC0426438, called only
from the factory command switch (0xC0427870), the same switch as the E2PR.CSV dump.
Timers were considered and dropped: the control timer service (0xC048F3EC id, ms, cb,
arg; ids 0-24, bitmask 0xC09B622C) sits on 40 OS timers (0xC00DB0B8; 25, 27, 38, 39
also taken) whose callbacks may not run in the GUI task.
Flashed FAUXJI25: the name shows and a half-press hides it. Owner: move it off the
centre, and hide it after ~2 s if that's safe.

### FAUXJI26: 2-second name, lower and Fuji-styled (`TL-F26`)
- **Timer**: timer events reach the live-view control state's handler 0xC04C1F04 (a
  chain of class checks via 0xC06529C4; class 0xC0759C48 = timer) and go to 0xC04BF54C
  (switch on id < 0x19), the same task as the key dispatcher, so hiding from there is
  as safe as from a key. FILM SIM now calls arm_name: NAME_FLAG = look+1 and control
  timer 30 for 2000 ms with the stock post callback 0xC048F4E4. A hook on the handler
  call (0xC04C2188) takes id 30: cancel the timer, clear the flag, stock draw(0).
  Other ids continue to 0xC04BF54C. Free OS timer ids: 26, 28-37 (30 used here).
- **Box** (`tools/fauxji_layout.py`, layout nodes edited in place): group 990 to (100,360)
  440x56 (was (100,158) 440x118), image 991 and text 992 to 56 px high; skin image 121
  (the panel) redrawn as a 440x56 near-black strip at ~70% opacity; text node colours
  at +44 (8 states) to white and the outline colours at +76 to black. Samsung's own
  mode descriptions (Help Text) use the same box and change with it.
Flashed FAUXJI26: perfect; low on the screen, discreet, gone after 3-4 s (the OS
timer works in whole seconds, so 2000 ms lands later than asked).

### FAUXJI27: Fuji-style menus, first pass (`TL-F27`)
`tools/fuji_menu.py`. The menu's left column and its animations live in SPID.Rom:
bg_menu_<group>_0N.jpg (160x480, tab N selected) and 61 `menu_*.info` files that are
animations: frame sizes as text, zero-padded to 2048, then 160x480 baseline JPEG frames
(4:2:2, no APP0, padded to 8) back to back; the directory size field is the text length.
`_0N` = opening on tab N (15 frames), `_ab` = tab a to b (15; first half shows a, second
half b, so playing it either way ends right), `_roll_0N` = idle ring (5).
- bg_menu.jpg: near-black, rows (70,70,71) between Samsung's row lines from x 155.
- Tab column: 96 px, Fuji grey (99,100,102) cells of 58 px, own flat white glyphs (camera,
  movie, sound, display, wrench for set-up, play, slideshow, edit, SP for scene, BKT,
  printer); selected tab = white cell, dark glyph. All animation frames are still images.
- skin.bin: selection bar 131 and pop-up option 585 = flat grey (128,128,130) with a white
  left edge; option list 136 = (50,50,51) with grey border and black separators.
The selected-row text colour is not known yet, so the bar is mid grey, not Fuji white.
Flashed FAUXJI27 (owner's photos): tab column and greys work; the list really has seven
rows from y 9 (the first sat on black), and the mid-grey bar looks almost white on the
AMOLED, so the white selected text vanished.

### FAUXJI28: menu rows aligned, Fuji white bar with black text (`TL-F28`)
Menu list layout (group 1 at x 65): row buttons nodes 3-9 at (113, 9 + 58n) 475x61, row
caps 588-635, values nodes 17-23 at x 468, selection bar node 2 = image 131. Text nodes
hold 8 text colours (+44) and 8 outline colours (+76): states normal, focused,
disabled, pressed, twice. Stock labels pale blue-grey (197,212,223) / white / grey with
a navy outline; values cyan (156,215,239) / cyan / grey with a white outline.
- Background rows now 113-635 x seven rows (9-415); tab cells stay at 67-357.
- Selection bar 131 = white; labels white, **black when selected** (outline black / white);
  values the same (were cyan).
- Row caps 132/133 (">") and 134/135 (">>"): white chevrons, black on white when selected.
Flashed FAUXJI28: menus done ("good job"). Next: the shooting screen and the mode dial.

### FAUXJI29: shooting screen and mode dial, first pass (`TL-F29`)
`tools/fuji_lv.py`. Mapped by drawing every image node of the live-view tree (root 742)
at its place, and the other top-level trees (scene picker 1751, guide screens 1768,
1882, 1917, popups 1962, ...). Live view: mode icon group 803 at (5,426), bottom bar
745 = image 119 at (0,426), aperture/shutter box 747 = 43, digits are images, exposure
scale 312 under 278 at (260,436), AEL 561 at (404,436), film icon 1009 at (10,184).
The mode dial wheel is SPID file gadget_modedial_bg.raw: 310x308 RGBA, no header
(other gadget_*.raw files are the same kind: mf 199x199, lens01 225x225, ...).
- Mode icons (115 SMART, 1 P, 8 A, 116 S, 9 M, 231 DUAL, 0 movie, 17 play): white Fuji
  tags with a black letter (SR+ for Smart Auto); the dial's grey ones (107-111, 113) as
  grey outline tags.
- 119 and 92 (guide title bar): flat black at ~60%. 43: removed (numbers only).
- Exposure scale: 278's cut-out numbers -> white, panel clear; 312's ticks -> white.
  AEL: letters white, panel clear.
- Mode dial: flat dark wheel (~88% opaque), grey rim with a dotted ring, grey selection
  band, flat hub.
Not touched yet: the mode description box on the dial screen (its white panel isn't
an image found so far; its text is black, so it stays as is), right-column icons,
the red/white digit sets, OIS and the other status icons.
Flashed FAUXJI29: "looking good". Left: the blue SCENE (and grey SMART) on the dial, and
the scene picker's sample photos (Beauty Shot, fireworks...): the stock Scene picker,
shown when the dial is on SCENE.

### FAUXJI30: scene icons and the scene picker (`TL-F30`)
The dial's icons are not layout nodes (the dial is drawn by code), so they were found by
look: 317 SCENE (selected), 226 SMART and 112 SCENE (unselected) -> SCN / SR+ tags.
Smart Auto's orange scene tiles (140-155, 316, 520) -> white tiles with dark glyphs, like
the scene-mode icons 239-251. Scene picker cards (195-206, 559, 256x285 photos) -> flat
dark cards (50,50,51) with a grey edge and each photo's own corner icon, large, in white.

### FAUXJI31: status icons, guide description box, neutral backgrounds (`TL-F31`)
- **Status icons**: the 101 grey-white shaded glyphs used in the live-view tree (58x58,
  64x64, 58x54, mean saturation <= 20; not the canisters or scene tiles) flattened: light
  pixels white, the rest near-black (keeps a thin edge for bright scenes).
- **Guide screens** (dial, scene picker; trees 1751/1768/1882/1917): below y 400, text
  lists (type 6) with black text at +132 get white text and +44..+108 set to near-black
  at ~70% (assumed to be the list's background: these are white in stock, behind the
  black description); black text nodes get white text with a black outline.
  Unconfirmed: if +44..+108 are not the background, the text is white on white.
- **Backgrounds**: date/time, face list, firmware update, language, HDMI menus, world
  map, voice memo: converted to neutral grey at 80% brightness.
Remaining: pop-ups (565 glossy panel, black text), "Menu Exit / Move" help bar, playback
screens, FILM BKT, face-based auto-rotate.
Flashed FAUXJI31: all good; the guide strip (~70% black) is too light for white text.

### FAUXJI32: darker guide strip, dark pop-ups, grey key chips (`TL-F32`)
- Guide description strip: near-black at ~90%.
- **Pop-ups** (tree 1785: windows on panels 13 524x260, 14 524x319, 565 604x384, icons
  100-102): panels flat (50,50,51) with a grey edge; message texts (black / 373737) white
  with a black outline; buttons (type 2) light grey, white when focused (the focus
  highlight behind them is drawn by code and was left alone).
- **Key chips** of the help bars (tree 1941: Menu, OK, Fn, Shutter, Zoom, d-pad, play,
  ...; 44-51, 218, 252, 542, 578, 591, 602, 617, 670): stored as **type 1** images, which
  decode with the same tokens (all 44 type-1 images do); rewritten as type 3: Fuji grey
  chip (143,145,147) with a dark legend.
Flashed FAUXJI32 (photos of Format): pop-up panel and text fine, but its buttons and the
menu's option list sit on their own images: unselected white rows, selected cyan.

### FAUXJI33: option lists and dialog buttons (`TL-F33`)
Menu option list (tree 0 group 32 at x 251): rows 33-39 = images 256/255 (328x58 white),
selected = node 40 image 707 (cyan, type 1), edges 257/258 (328x11); labels nodes 41-47
(type 2: 4d5052 / white / b3b3b3 grey ...). Dialog buttons: selected = image 238 (229x60
cyan, type 1; also used by group 454), unselected on the same white rows.
- 255/256 -> dark row (70,70,71) with a black separator; 257/258 -> (70,70,71);
  707 and 238 -> white (written as type 3).
- Option labels: white, black when selected, grey (7f7f7f) when disabled.
- Pop-up buttons: white, black when selected.
Flashed FAUXJI33: option lists and Yes/No fine. Owner: the formatting box is still
Samsung-like; a blue "eye" shows while processing; tried FILM BKT and got a picker with
9 choices. Card photos SAM_0578-0581: all style 0 (PROVIA), two pairs: not a FILM BKT burst.
The 9-choice picker fits the bracket's own style picker: 11 styles minus Sketch/Defog
(the two FAUXJI added) = the 9 stock-era choices, so FILM BKT's three looks are already
the owner's to pick there; the burst itself needs Drive Setting -> Bracketing.

### FAUXJI34: busy animation, formatting box, leftover cyan (`TL-F34`)
- 53 (4192x319 strip, x 0-523 used) = the formatting / processing box: flat dark panel.
- 38 (2168x51, x 0-541 used) = button pair white | cyan (271x51 each): dark | white.
- Busy animation ("blue eye"): dark knob 583 with cyan arcs 644-648 -> arcs neutral grey.
- Other cyan left: knobs / dots 42, 103, 615, 689, frame 6, sliders 104, 710 -> neutral.

## Later pile (owner, 2 Nov 2026)
- **Names on the FILM BKT 9-look chooser.** Grid = layout group 1207 (live-view tree),
  cells 1208-1216 (160x120 at x 40/240/440, y 30/160/290), empty groups filled by code;
  cell hashes are consecutive (0xD1D86B7F + n) and appear nowhere in the program, so the
  cursor code wasn't found statically. Order = internal style 0-8: PROVIA, ACROS, Eterna /
  Classic Neg., Classic Chrome, Reala / Velvia, ASTIA, Sepia (matches the owner's photo).
  Plan if resumed: a test build that shows logical key numbers in the name strip, to see
  whether the chooser's keys pass the live-view key hook; then track the cursor (starts
  top-left) and show the look's name there.
- Playback screens (not mapped yet).
- Face-based auto-rotate.

## FAUXJI35: P/A keep 1/60 when zoomed (`TL-F35`, 2 Nov 2026)
Owner: zooming in A mode raised the slowest shutter to 1/125, useless in the dark.
Card evidence (TL-F33 shots, A mode, ISO capped at 1600): 24 mm -> 1/60, 57 mm and
72 mm -> 1/125 at the same ISO (one stop darker).
Cause, in AeCalcCaptureCommon (TL 0xC053FAA8): after loading the program line, every
row's shutter is shifted by a zoom amount from AE sysinfo +0x12 (rows where the aperture
changes by +0x10), then clamped to [Tv[0], Tv max]. At the long end the shift is one
stop (16), so HOLD60's 1/60 rows (Tv 96) became 1/125 (112). Stock already skips the
shift for AE mode 3 (`cmp lr,#3; beq 0xC053FF04` at 0xC053FDC4); the A-mode shots were
shifted, so A is mode 2. Hook at 0xC053FDC4 -> 0xC04262D0: `cmp lr,#3; cmpne lr,#2; beq
skip; b back`. Other modes (Auto, scenes) keep Samsung's zoom protection.

## Auto-rotate research (2 Nov 2026)
No orientation sensor; owner's vertical shots (SAM_0588-0594) carry EXIF Orientation 1.
- EXIF writers switch on tag; Orientation (0x112) cases: 0xC03779B4 (writer 0xC03773E0)
  takes the value from the info struct, `[sl+0xE4]`, so the main JPEG's orientation is
  data-driven; 0xC0383448 (writer 0xC0383120) writes a constant 1 (second writer: RAW or
  thumbnail, to check). Writers 0xC0385868 / 0xC0388668 also handle 0x112; 0xC03A7C28 =
  PCBIEXIFParser::replaceOrientation (100% match; playback rotate).
- Face detection: TL has the WB850F's 3-angle detector (SDIC_FaceDetection_3Angle ->
  0xC05901D0, 41%; SDIC_FaceAngle -> 0xC0596C64, 36%), which searches upright, 90 left
  and 90 right.
Plan: at capture, if a face was found at +-90 degrees, set `[sl+0xE4]` to 6 or 8 (and the
same for the RAW writer). First check on the camera: hold it vertical facing a person;
does the face box appear? If not, the detector runs upright only and this route is out.

## FAUXJI36: D-Range names (`TL-F36`, 2 Nov 2026)
Text only (patches/fauxji_text.json pass "FAUXJI36"): SPID 875 "D-Range Exp." -> "D-Range",
877/878 "D-Range Exp.1/2" -> "DR200" / "DR400", help lines 1252-1255 reworded. "Off" is a shared
string and stays. Unverified: that Exp.1 is about one stop of highlight protection.
Batch review of FEATURES.md items 1-8: item 1 negative (no AUTO_ROTATE), item 5's 1/3/5/10 s are
the slideshow, item 7's grid is code-drawn, item 4's stamp fonts are named in the WB850F map
(gImprint*Font) but not yet found in the TL500 .elf. See FEATURES.md.

## FAUXJI37: tilt tag / auto-rotate (`TL-F37`, 2 Nov 2026)
New: tools/fauxji_rot.py (+ STRWRAP and tilt texts in fauxji_ui.py), tools/liveness.py (dead-code finder),
armdis.py, xref.py, litref.py. Facts: live EXIF writer 0xC0385868 (Orientation constant 1 at
0xC0385F00); stock detector SDIC_FaceDetection 0xC058F798 scans rotated faces (r6 = 0/-30/+30/-90/+90/
-60/+60 by a frame counter 0xC09F51F0; r6 = -90 rotates the luma image CCW with 0xC0595A18, +90 CW
with 0xC0595A94). Hook at its end stores 6 (r6=+90) or 8 (r6=-90) for 60 upright scans. AE-L button
option "AE-L" (logical key 0, call at 0xC04C1A98) cycles Off/Auto/Auto flip/top right/top left.
Code in the dead factory function 0xC04260A0..0xC042620C. See FEATURES.md for the test plan.

### FAUXJI38 (`TL-F38`): learnable tilt button
Dispatcher hook at 0xC04C1944 (`bl 0xC04BFF98` "is this key handled", r1 = logical key, sl = event)
swallows the learned key (ROT_KEY at 0xC04260AC, default 0xFF) and cycles the tilt state. State 5 =
"press a key": the next released key is learned and its number shown ("Tilt key = NN"). The key
hook (0xC04C1938) no longer hides the pop-up on release of keys 14, 0 and the learned key.
Strings moved to the dead function at 0xC0426438. AE-L option "TILT TAG" and FILM SIM are still
two options of one setting.

## FAUXJI39: menu unlock in P/A/S/M (`TL-F39`)
Owner: RAW, face detect etc. grey out depending on mode. The menu keeps 21 "allowed options"
bitmasks (setter 0xC04CE83C, switch on id 0x88-0x9C; defaults 0xFFFFFF = all allowed, set up by
0xC04CE714; refreshed mainly by 0xC04D2000 with a big per-mode switch, ~117 callers). Hook at
0xC04CE844 (`mov sl,r1`): when the shooting mode (sysvalue 3 via 0xC048F81C: AE sysmode enum,
0 P, 2 A, 3 S, 4 M; 1 Auto, 5 Bulb, 8 Movie, 9 Smart Auto, 10+ scenes) is P/A/S/M the value
becomes 0xFFFFFF. Other modes unchanged. Unverified on camera; other greying paths (not via
these masks) would remain.

## FAUXJI40: meter lower (`TL-F40`)
AeSystemEVCSetToAeEVCShift (0xC03ECCF8, x16 units) is the EV compensation the AE applies; its
only caller is AeUpdateSysInfo (0xC03EEED0, forced to 0 in AE-manual) and the manual auto-ISO
routine also uses it. Hook at its return (0xC03ECD54): subtract AE_BIAS (tools/fauxji_rot.py, 5 =
-0.3 EV; 8 = -0.5 EV). The EV comp scale still shows 0. Trade-off: shadows get 0.3 EV noisier.

## FAUXJI41: key-number test build (`TL-F41`, 2 Nov 2026)
Field test of FAUXJI40: the AE-L Button menu item has never existed on this camera (the setting can't be
changed in menus), so the learn state of the tilt button was unreachable. The D-Range Exp. 3-step setting
is from a newer firmware and does not exist on the TL500 (the on/off item is Smart Range, renamed D-Range).
FAUXJI41 = FAUXJI40 + `DIAG` in tools/fauxji_rot.py: any key reaching the live-view dispatcher (except
AE-L, key 0/14) pops up "Tilt key = NN" on press. Test: press VIDEO and read NN; if no pop-up, VIDEO does
not pass the dispatcher. Next: hard-code NN as KEY_DEFAULT and set DIAG = False.

## FAUXJI42: VIDEO button hard-coded as the tilt button (`TL-F42`, 2 Nov 2026)
FAUXJI41 test: the VIDEO button's logical key is 9 (it does pass the live-view dispatcher). `KEY_DEFAULT = 9`,
`DIAG = False` in tools/fauxji_rot.py. VIDEO now cycles Off / Auto / Auto flip / top right / top left / press-a-key
with a pop-up and no longer starts a recording (state "press a key" can still re-learn another button).
Unverified on camera.

## FAUXJI43: tilt tag Auto by default (`TL-F43`, 2 Nov 2026)
FAUXJI42 field test: a vertical portrait with Face Detection came out tagged Orientation 6 (correct: face
sideways in the raw pixels, rotate CW to view); a vertical shot before it had no tag. The VIDEO button showed no
visible pop-up and the stock recording did not start (unclear whether key 9 cycled the state).
`STATE_DEFAULT = 1` (Auto) so the tag works from power-on without any button.

## FAUXJI44: tilt-tag writer test (`TL-F44`, 2 Nov 2026)
FAUXJI43 field test (Auto default, Face Detection on, face-lock icon shown): four sideways-face portraits
(SAM_0624-0627, heads left x2 / right x2) all Orientation 1; VIDEO showed no pop-up in 7 presses. SAM_0622 (tag 6)
was rotated by the owner in playback, so nothing in the tilt chain is verified on camera yet.
`STATE_DEFAULT = 3` (always 6) isolates the EXIF writer hook (0xC0385F00). Test: shot A, VIDEO, shot B, VIDEO,
shot C expect tags 6, 8, 1 (this also tests the button without the pop-up). Restore STATE_DEFAULT = 1 afterwards.

## FAUXJI45: all three EXIF orientation writers hooked (`TL-F45`, 2 Nov 2026)
FAUXJI44 test (state forced to 3, button works: first press showed "top left" = state 4): SAM_0628-0630 all
Orientation 1, so the writer at 0xC0385F00 is not the one that produces the JPEG tag. FAUXJI45 hooks all
three candidates through short stubs + one shared routine (tools/fauxji_rot.py `wcommon`): 0xC0385F00 (mov lr,#1),
0xC03779DC (ldr lr,[sl,#0xe4]), 0xC0383470 (mov lr,#1). Still STATE_DEFAULT = 3. Test: shot A, VIDEO, shot B,
VIDEO, shot C = tags 6, 8, 1. If still all 1 the tag comes from somewhere else (0xC0388668 or a template).

## FAUXJI46: tilt tag Auto by default, writer fixed (`TL-F46`, 2 Nov 2026)
FAUXJI45 field test PASSED: SAM_0631/0632/0633 = Orientation 6 / 8 / 1 (state 3, VIDEO -> 4, VIDEO -> 5),
so the EXIF writer hooks work and VIDEO cycles the state (key 9). The pop-up shows only on the first press (open).
FAUXJI43's Auto failure was the dead writer hook, so Auto (face detection) is untested with a working writer.
FAUXJI46 = FAUXJI45 with STATE_DEFAULT = 1 (Auto). Test: vertical face shots, heads left/right, Face Detection on.

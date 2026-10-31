# Safe test plan — modifying Samsung TL500 / EX1 firmware

Goal: prove we can put custom firmware on the camera **without ever risking a
camera you care about**, and with a recovery path ready before any flash.

This plan is ordered so that risk only rises step by step, and every risky step
has a way back. Read the whole thing before doing any of it. **Nothing here should
be done on your main TL500.**

---

## The three safety rules (never break these)

1. **Never test on your main camera.** Every flash happens on a separate,
   sacrificial body you would not miss if it bricked.
2. **Never modify the boot loaders (ONBL1 / ONBL2) in early tests.** As long as the
   boot loader stays Samsung-original and intact, it can always re-load a fresh
   main program from an SD card. The boot loader is the lifeline; leave it alone
   and a bad main program is recoverable. Modifying the boot loader is the one
   change that can truly brick the camera — that comes much later, if ever.
3. **Never cut power during a flash.** Full battery only. Samsung's own guide warns
   a power loss mid-flash can need mainboard repair.

---

## Match the file to the body

We currently have **EX1** firmware files (108091, 110271). Your main camera is a
**TL500**, and TL500 and EX1 use different builds. So the sacrificial test body
should be an **EX1** (then the files we already have apply directly), **or** we
first obtain/dump a **TL500** firmware and test on a spare TL500.

Recommendation: acquire a cheap, used **EX1** body as the test mule. They are the
same hardware as your TL500, so everything learned transfers, and we already have
its firmware.

---

## Phase 0 — Zero risk, software only (no camera touched)

Prove our rebuild tooling is correct before any flash exists.

- Write a small tool that **unpacks** the official container (we already know its
  format: a table of name/size/offset entries + raw parts) and **repacks** it.
- Success test: the repacked file is **byte-for-byte identical** to the official
  file. If it is, we know our tool reproduces exactly what the camera expects.
- **Go/no-go:** do not proceed until repack == original, exactly.

Risk: none. This is just file manipulation on the PC.

---

## Phase 1 — Prepare the sacrificial body

- Acquire a spare EX1 (or spare TL500 if we go the TL500 route).
- Check its current firmware version the safe way (the FW Version screen, like we
  did on your TL500 — power off, never press shutter).
- **Prove the normal update works on it**: flash the **official, unmodified** file
  the normal way. Confirm it completes and the camera works. This both confirms the
  body is healthy and rehearses the exact procedure.

Risk: low — this is the manufacturer's own supported update.

---

## Phase 2 — Know the recovery paths *before* risking anything

Confirm, in writing, how we rescue a camera that won't boot — before we ever make
one that might not:

1. **SD re-flash (primary):** because we never touch the boot loader, a bad main
   program should still let the intact boot loader re-run the official update from
   an SD card. Confirm the camera still reaches the update screen with a bad main
   image (we may deliberately induce a mild failure to test this).
2. **USB / mask-ROM recovery (secondary):** research whether this chip family
   (DRIMe III) has a built-in USB download mode reachable by a button combo
   (forums mention a hidden USB port and a multi-button trick on the EX1). Document
   it if it exists — it is the deeper safety net.
3. **Hardware recovery (last resort):** note that a NAND reader / JTAG could restore
   a fully bricked unit. Advanced; only relevant if 1 and 2 fail.

**Go/no-go:** do not attempt a modified flash until at least path 1 is confirmed
working on the test body.

---

## Phase 3 — First flash: a byte-identical rebuild

- Flash the Phase 0 repack (which is identical to the official file) onto the test
  body.
- Expected result: camera behaves exactly as with the official file — because the
  bytes are identical.
- This proves the camera accepts a file produced by **our** tooling, not just
  Samsung's download. If it bricks (it shouldn't), recover via Phase 2.

Risk: very low — identical bytes.

---

## Phase 4 — Smallest possible real change: one text string

- Change a single on-screen **text string** inside the main program — for example a
  menu label — keeping it **exactly the same length** so no sizes or offsets move
  and no code logic is touched. Just different letters in the same slots.
- Rebuild the container, fixing any size/offset fields (unchanged here since length
  is identical), and — if the main program turns out to have the simple additive
  self-check we flagged — recompute that one number.
- Flash to the test body.
- **Success = the camera boots and shows your changed text.** That single result
  proves the entire pipeline end to end, with essentially zero logic risk.

Risk: low. No code behaviour changed; worst case recovered via Phase 2.

---

## Phase 5 and beyond — actual features (only after Phase 4 succeeds)

Once a trivial change is proven to boot, real work begins and is ordinary
engineering rather than code-breaking:
- Reconstruct the main program's memory layout (the piece that blocked exact
  tracing), so code — not just text — can be understood and changed.
- Make one small *behaviour* change (e.g. raise a limit, change a default).
- Build up from there.

Each new capability is its own small, reversible experiment on the test body,
never the main camera.

---

## What we need from you to start

- A decision on the test body: buy a spare **EX1** (uses the files we have), or go
  the TL500 route (needs a TL500 firmware file we still have to locate/dump).
- Then Phase 0 (the PC-only rebuild tool) can begin immediately — it needs no
  camera and carries no risk.

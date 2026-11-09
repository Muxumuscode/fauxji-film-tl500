"""Build FAUXJI FILM PRO firmware from Samsung's official TL500 008264 files.

Nothing of Samsung's is shipped here: the patch data is FAUXJI's own code/data (program
changes as byte runs), the menu text as ordered rewrite passes, and generators for the
boot screen and sounds that work on your own copy of the stock ROM.

Steps
  1. check the input is the untouched official 008264 set (SHA-256);
  2. program (.elf): apply patches/fauxji_elf_runs.json, then re-run tools/fauxji.py
     (colour recipes; idempotent, so tuning there carries into the build);
  3. resources (SPID.Rom): text passes (patches/fauxji_text.json), boot screen
     (tools/bootscreen.py 'firmware'), sounds (tools/sounds.py);
  4. copy ONBL1/ONBL2/FWUP unchanged.

Run from project root:  python tools/build_fauxji.py <stock dir> <out dir> [--film | --diag-keys] [--check <ref dir>]
Put the five output files in the root of an SD card and power the camera on to flash.
"""
import hashlib, json, os, sys

sys.path.insert(0, os.path.dirname(__file__))
import fauxji, fauxji_ui, fauxji_rot, fauxji_layout, fuji_menu, fuji_lv, spid_files, spid_strings, sounds, bootscreen, badges, fauxji_playback

ELF, ROM = 'EX1-DSP-SR-008264.elf', 'SPID.Rom'
STOCK_SHA256 = {
    ELF: '53a17829c71a7ab1609dbafe2371f23fc6f0a49e4dcba35028d82946106c626b',
    ROM: '28da03005858e5bda32ae7761acb2634ab4b13b651177b1d7b36c7622393b928',
    'ONBL1.bin': '5a5b4e99a3f7f9a83ead297b842e0019a656a1a977db7dcc96acd8ad77a00b20',
    'ONBL2.bin': 'd3c558c7fbc793c3cae9aef707e6ab0d9f24c8fdda65e2eeab12f36feafac703',
    'FWUP': '9ded3061aeb5f25ae36e5d17ce935549632933ba041515ad90dfcf9115f92036',
}
HERE = os.path.dirname(os.path.abspath(__file__))
PATCHES = os.path.join(HERE, '..', 'patches')


LABEL_AT, LABEL = 0x792493, b'TL-F63\0\0'          # version string the camera shows (8 bytes; stock 'TL500-U'). TL-F63 = FAUXJI63, the
                                                   # build the plain output is byte-identical to (it said TL-F62 by mistake before)
KNOWN_LABELS = (b'TL500-U\0', b'TL-F62\0\0', LABEL)  # what the label bytes may hold before it is set (stock, or the patch runs' older label)


DIAG_LABEL = b'TL-D06\0\0'                      # --diag-keys build: key numbers, dial events, file-list finder (tools/diag_probe.py)


FILM_LABEL = b'TL-F65t\0'                       # --film build: film camera mode (film_mode), EXIF names (film_exif), ratchet (film_sound), stamp (film_stamp)


def build_elf(stock, diag_keys=False, film=False):
    assert not (diag_keys and film), 'the diagnostic probe and film mode use the same free region'
    d = bytearray(stock)
    with open(os.path.join(PATCHES, 'fauxji_elf_runs.json'), encoding='utf-8') as f:
        runs = json.load(f)['runs']
    for run in runs:
        b = bytes.fromhex(run['bytes'])
        d[run['offset']:run['offset'] + len(b)] = b
    d = bytearray(sounds.patch_elf(fauxji_rot.patch(fauxji_ui.patch(fauxji.patch(bytes(d))))))
    label = LABEL
    if diag_keys:
        d = bytearray(fauxji_ui.patch_diag(bytes(d)))
        label = DIAG_LABEL
    if film:
        import film_mode, film_exif
        d = bytearray(film_mode.patch(bytes(d)))
        d = bytearray(film_exif.patch(bytes(d), FILM_LABEL))     # EXIF: Make FAUXJI FILM, Model "TL500 <film>", Software = the label
        import film_sound
        assert film_sound.RATCHET == film_mode.RATCHET
        d = bytearray(film_sound.patch(bytes(d)))                 # the wind-on ratchet: its sample and its player
        import film_stamp
        d = bytearray(film_stamp.patch(bytes(d), film_mode.addrs()['vars']))   # orange '98 date stamp in the film camera
        label = FILM_LABEL
    assert bytes(d[LABEL_AT:LABEL_AT + 8]) in KNOWN_LABELS, 'unexpected version label'
    d[LABEL_AT:LABEL_AT + 8] = label
    return bytes(d)


def build_rom(stock, film=False):
    d = stock
    with open(os.path.join(PATCHES, 'fauxji_text.json'), encoding='utf-8') as f:
        passes = json.load(f)['passes']
    for p in passes:
        ents, _ = spid_strings.read_table(d)
        changes = {int(i): (ents[int(i)][2] if t is None else t) for i, t in p['changes'].items()}
        d, _ = spid_strings.rewrite(d, changes)
    if film:                                       # the scene picker is the film picker: films' names and blurbs on the 12 cards
        import film_mode, film_mode_art
        d, _ = spid_strings.rewrite(d, {**film_mode.card_strings([t[1] for t in film_mode_art.INFO]), **film_mode.DISPLAY_TEXT})
    boot, _ = bootscreen.fit(bootscreen.render_tl500() if film else bootscreen.render('firmware'))   # the film build: the TL500 boot screen
    d = spid_files.replace(d, 'bg_power_on_off_422.jpg', boot)
    for name, fn in sounds.SOUNDS.items():
        d = spid_files.replace(d, sounds.SLOTS[name], sounds.pcm(fn()))
    # FAUXJI film-simulation badges in place of Samsung's Photo Style icons, and the rest of the interface artwork: skin.bin is taken out
    # once, every artwork patch runs on it in turn, and it goes back in once
    rec, off, size, slot = spid_files.directory(d)['skin.bin']
    k = fauxji_playback.patch_skin(fuji_lv.patch_skin(fuji_menu.patch_skin(fauxji_layout.patch_skin(badges.patch_skin(d[off:off + size])))))
    if film:
        import film_mode
        k = badges.patch_cards(k, film_mode.CARD_IMAGE, film_mode.CARD_LOOK)          # cartridge cards in the picker
        # the live view's mode icon: each scene card's own icon becomes its film's cartridge (the spare twelfth tile is the roll-full icon)
        k = badges.patch_scene_tiles(k, {img: film_mode.CARD_LOOK[c] for c, img in film_mode.SCENE_TILES.items() if img != film_mode.IMG_FULL})
        k = badges.patch_state_tiles(k, {film_mode.IMG_WIND: badges.wind_tile, film_mode.IMG_FULL: badges.full_tile})   # wind-on, roll-full
    d = spid_files.replace(d, 'skin.bin', k)
    # (the big cartridge with the count moved the film icon out of its parent group and the owner saw no icon at all: film_mode.layout and
    #  badges.patch_big_cartridges stay in the tools but are not applied)
    d = fuji_menu.patch_rom(d)                     # Fuji-style menu background, tabs, animations
    d = fuji_lv.patch_rom(d)                       # Fuji-style mode dial wheel
    return d


def read(path):
    with open(path, 'rb') as f:
        return f.read()


def compare(check, files):
    """'identical', 'label' (only the .elf's version label differs) or 'differs'."""
    label_only = True
    for f, data in files.items():
        ref = read(os.path.join(check, f))
        if ref == data:
            continue
        if f != ELF or len(ref) != len(data) or ref[:LABEL_AT] != data[:LABEL_AT] or ref[LABEL_AT + 8:] != data[LABEL_AT + 8:]:
            label_only = False
    if all(read(os.path.join(check, f)) == data for f, data in files.items()):
        return 'identical'
    return 'label' if label_only else 'differs'


def main():
    import argparse
    ap = argparse.ArgumentParser(description='Build FAUXJI firmware from the official TL500 008264 files.')
    ap.add_argument('stock', help='folder with the five official 008264 files')
    ap.add_argument('out', help='folder for the five files to put on the SD card')
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument('--film', action='store_true', help='film camera mode on the SCENE dial position (experimental)')
    mode.add_argument('--diag-keys', action='store_true', help='diagnostic build: key numbers, dial events, file-list finder')
    ap.add_argument('--check', metavar='REF_DIR', help='compare the output with an earlier build in REF_DIR (exit 1 if it differs)')
    args = ap.parse_args()
    src, out = args.stock, args.out
    for f, h in STOCK_SHA256.items():
        path = os.path.join(src, f)
        if not os.path.exists(path):
            raise SystemExit('%s is missing from %s' % (f, src))
        got = hashlib.sha256(read(path)).hexdigest()
        if got != h:
            raise SystemExit('%s is not the official 008264 file (sha256 %s)' % (f, got))
    os.makedirs(out, exist_ok=True)
    fauxji.STOCK_ELF = os.path.join(src, ELF)      # the recipes read stock tables from here
    sounds.STOCK_ROM = os.path.join(src, ROM)      # the shutter sound is reshaped from here
    badges.DESIGN = 'cartridge' if args.film else 'canister'     # the film build gets the cartridge artwork everywhere the looks are shown
    fuji_lv.FILM_BUILD = args.film                 # the mode dial's SCENE position reads FILM
    files = {ELF: build_elf(read(os.path.join(src, ELF)), args.diag_keys, args.film),
             ROM: build_rom(read(os.path.join(src, ROM)), args.film)}
    for f in ('ONBL1.bin', 'ONBL2.bin', 'FWUP'):
        files[f] = read(os.path.join(src, f))
    for f, data in files.items():
        with open(os.path.join(out, f), 'wb') as fh:
            fh.write(data)
        print('%-24s %9d bytes  sha256 %s' % (f, len(data), hashlib.sha256(data).hexdigest()[:16]))
    if args.check:
        result = compare(args.check, files)
        print({'identical': 'identical to %s', 'label': 'same as %s apart from the version label',
               'differs': 'DIFFERENT from %s'}[result] % args.check)
        if result != 'identical':
            raise SystemExit(1)


if __name__ == '__main__':
    main()

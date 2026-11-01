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

Run from project root:  python tools/build_fauxji.py <stock dir> <out dir> [--check <ref dir>]
Put the five output files in the root of an SD card and power the camera on to flash.
"""
import hashlib, json, os, shutil, sys

sys.path.insert(0, os.path.dirname(__file__))
import fauxji, fauxji_ui, spid_files, spid_strings, sounds, bootscreen

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


def build_elf(stock):
    d = bytearray(stock)
    for run in json.load(open(os.path.join(PATCHES, 'fauxji_elf_runs.json')))['runs']:
        b = bytes.fromhex(run['bytes'])
        d[run['offset']:run['offset'] + len(b)] = b
    return fauxji_ui.patch(fauxji.patch(bytes(d)))


def build_rom(stock):
    d = stock
    for p in json.load(open(os.path.join(PATCHES, 'fauxji_text.json')))['passes']:
        ents, _ = spid_strings.read_table(d)
        changes = {int(i): (ents[int(i)][2] if t is None else t) for i, t in p['changes'].items()}
        d, _ = spid_strings.rewrite(d, changes)
    boot, _ = bootscreen.fit(bootscreen.render('firmware'))
    d = spid_files.replace(d, 'bg_power_on_off_422.jpg', boot)
    for name, fn in sounds.SOUNDS.items():
        d = spid_files.replace(d, sounds.SLOTS[name], sounds.pcm(fn()))
    return d


def main():
    args = sys.argv[1:]
    check = args[args.index('--check') + 1] if '--check' in args else None
    src, out = args[0], args[1]
    for f, h in STOCK_SHA256.items():
        got = hashlib.sha256(open(os.path.join(src, f), 'rb').read()).hexdigest()
        if got != h:
            raise SystemExit('%s is not the official 008264 file (sha256 %s)' % (f, got))
    os.makedirs(out, exist_ok=True)
    fauxji.STOCK_ELF = os.path.join(src, ELF)      # the recipes read stock tables from here
    sounds.STOCK_ROM = os.path.join(src, ROM)      # the shutter sound is reshaped from here
    files = {ELF: build_elf(open(os.path.join(src, ELF), 'rb').read()),
             ROM: build_rom(open(os.path.join(src, ROM), 'rb').read())}
    for f in ('ONBL1.bin', 'ONBL2.bin', 'FWUP'):
        files[f] = open(os.path.join(src, f), 'rb').read()
    for f, data in files.items():
        open(os.path.join(out, f), 'wb').write(data)
        print('%-24s %9d bytes  sha256 %s' % (f, len(data), hashlib.sha256(data).hexdigest()[:16]))
    if check:
        ok = all(open(os.path.join(check, f), 'rb').read() == data for f, data in files.items())
        print('identical to %s: %s' % (check, ok))
        if not ok:
            raise SystemExit(1)


if __name__ == '__main__':
    main()

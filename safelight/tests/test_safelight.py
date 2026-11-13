"""python -m unittest discover -s tests   (from the safelight folder)"""
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))

from safelight import card, films, lab                      # noqa: E402
from safelight.library import Library                       # noqa: E402
import fixtures                                             # noqa: E402


class Films(unittest.TestCase):
    def test_model_names(self):
        self.assertEqual(films.from_model('TL500 Classic Chrome').code, 'CCHR')
        self.assertEqual(films.from_model('TL500 Provia\x00\x00\x00').code, 'PROV')
        self.assertEqual(films.from_model('TL500 nostalgic neg.').code, 'NOST')
        self.assertIsNone(films.from_model('TL-F64a'))
        self.assertIsNone(films.from_model(''))
        self.assertIs(films.from_code('MYST001'), films.MYSTERY)
        self.assertIs(films.from_code('ZZZZ001'), films.UNKNOWN)
        self.assertEqual(len({f.code for f in films.FILMS}), 11)


class Card(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.root = fixtures.make_card(os.path.join(cls.tmp, 'card'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_scan_card_root(self):
        rolls = card.scan(self.root)
        self.assertEqual([r.code for r in rolls], ['ACRO002', 'MYST001', 'PROV001'])
        prov = rolls[2]
        self.assertEqual((prov.film.code, len(prov.frames), prov.frames[0].number), ('PROV', 5, 1))
        self.assertEqual(prov.roll_id, 'PROV001_20261108')
        self.assertEqual(prov.frames[0].film.code, 'PROV')

    def test_mystery(self):
        myst = [r for r in card.scan(self.root) if r.code == 'MYST001'][0]
        self.assertTrue(myst.mystery)
        self.assertIs(myst.film, films.MYSTERY)
        self.assertEqual(myst.true_film.code, 'CCHR')               # the EXIF tells, the app keeps it secret until developed

    def test_scan_films_folder_and_single_roll(self):
        self.assertEqual(len(card.scan(os.path.join(self.root, 'FILMS'))), 3)
        rolls = card.scan(os.path.join(self.root, 'FILMS', 'ACRO002'))
        self.assertEqual([(r.code, len(r.frames)) for r in rolls], [('ACRO002', 3)])

    def test_loose_folder(self):
        loose = os.path.join(self.tmp, 'backup', '100PHOTO')
        shutil.copytree(os.path.join(self.root, 'FILMS', 'PROV001', '100PHOTO'), loose)
        rolls = card.scan(os.path.dirname(loose))
        self.assertEqual(len(rolls), 1)
        self.assertEqual(rolls[0].film.code, 'PROV')                  # every frame says Provia
        self.assertEqual(len(rolls[0].frames), 5)

    def test_empty(self):
        self.assertEqual(card.scan(os.path.join(self.tmp, 'nothing-here')), [])


class Lab(unittest.TestCase):
    def setUp(self):
        self.a = np.asarray(fixtures.frame(3), dtype=np.float32) / 255.0

    def test_develop_shapes_and_range(self):
        for f in films.FILMS:
            for r in (lab.Recipe(), lab.Recipe(push=2, process='cross', expired=8, developer='acutance', paper='warm'),
                      lab.Recipe(push=-1, process='bleach', developer='fine', paper='matte', auto_levels=True)):
                out = lab.develop(self.a, f, r, frame=1)
                self.assertEqual(out.shape, self.a.shape)
                self.assertGreaterEqual(out.min(), 0.0)
                self.assertLessEqual(out.max(), 1.0)

    def test_mono_is_neutral(self):
        out = lab.develop(self.a, films.BY_CODE['ACRO'], lab.Recipe(paper='glossy'), frame=3)     # (warm papers tint B&W, as real ones do)
        self.assertLess(np.abs(out[..., 0] - out[..., 1]).max(), 1e-6)
        sep = lab.develop(self.a, films.BY_CODE['SEPI'], lab.Recipe(paper='glossy'), frame=3)
        self.assertGreater((sep[..., 0] - sep[..., 2]).mean(), 0.05)  # sepia is warm

    def test_repeatable(self):
        r = lab.Recipe(seed=42)
        a1 = lab.develop(self.a, films.BY_CODE['CNEG'], r, frame=1, roll_seed=7)
        a2 = lab.develop(self.a, films.BY_CODE['CNEG'], r, frame=1, roll_seed=7)
        self.assertTrue(np.array_equal(a1, a2))

    def test_push_is_brighter_pull_darker(self):
        f = films.BY_CODE['PROV']
        base = lab.develop(self.a, f, lab.Recipe(grain=0, halation=0, leaks=False)).mean()
        push = lab.develop(self.a, f, lab.Recipe(push=2, grain=0, halation=0, leaks=False)).mean()
        pull = lab.develop(self.a, f, lab.Recipe(push=-1, grain=0, halation=0, leaks=False)).mean()
        self.assertGreater(push, base)
        self.assertLess(pull, base)

    def test_halation_is_red(self):
        f = films.BY_CODE['ETRN']
        no = lab.develop(self.a, f, lab.Recipe(grain=0, halation=0, leaks=False))
        yes = lab.develop(self.a, f, lab.Recipe(grain=0, halation=2, leaks=False))
        d = (yes - no).mean(axis=(0, 1))
        self.assertGreater(d[0], d[2])

    def test_leaks_first_frame_then_rare(self):
        f = films.BY_CODE['VELV']
        small = self.a[::4, ::4]
        base = {k: lab.develop(small, f, lab.Recipe(grain=0, halation=0, leaks=False, seed=9), frame=k, roll_seed=3).mean() for k in range(1, 41)}
        leak = {k: lab.develop(small, f, lab.Recipe(grain=0, halation=0, leaks=True, seed=9), frame=k, roll_seed=3).mean() for k in range(1, 41)}
        leaked = [k for k in base if leak[k] > base[k] + 0.003]
        self.assertIn(1, leaked)                                        # the first frame always
        self.assertLessEqual(len(leaked), 5, leaked)                    # later ones only now and then (about 1 in 20)
        self.assertNotIn(2, leaked)

    def test_film_looks_for_other_cameras(self):
        a = self.a
        for f in films.FILMS:
            out = lab.film_look(a, f)
            self.assertEqual(out.shape, a.shape)
        sat = lambda x: (x.max(axis=2) - x.min(axis=2)).mean()
        self.assertGreater(sat(lab.film_look(a, films.BY_CODE['VELV'])), sat(a))          # Velvia is saturated
        self.assertLess(sat(lab.film_look(a, films.BY_CODE['CCHR'])), sat(a))            # Classic Chrome is muted
        mono = lab.film_look(a, films.BY_CODE['ACRO'])
        self.assertLess(np.abs(mono[..., 0] - mono[..., 2]).max(), 1e-6)
        r = lab.Recipe(grain=0, halation=0, leaks=False)
        self.assertFalse(np.allclose(lab.develop(a, films.BY_CODE['VELV'], r, emulate=True), lab.develop(a, films.BY_CODE['VELV'], r)))

    def test_leak_on_first_frame_only_when_enabled(self):
        f = films.BY_CODE['VELV']
        on = lab.develop(self.a, f, lab.Recipe(grain=0, halation=0, leaks=True, seed=5), frame=1)
        off = lab.develop(self.a, f, lab.Recipe(grain=0, halation=0, leaks=False, seed=5), frame=1)
        self.assertGreater(on.mean(), off.mean() + 0.005)

    def test_grain_scale_matches_resolution(self):
        # a preview's grain is about what the full-size print's grain becomes when scaled down
        f = films.BY_CODE['CNEG']
        flat = np.full((720, 960, 3), 0.5, np.float32)
        big = lab.develop(np.full((2736, 3648, 3), 0.5, np.float32), f, lab.Recipe(halation=0, leaks=False))
        small = lab.develop(flat, f, lab.Recipe(halation=0, leaks=False))
        from PIL import Image
        big_small = np.asarray(lab.to_image(big).resize((960, 720), Image.BOX), np.float32) / 255
        self.assertLess(abs(small.std() - big_small.std()) / big_small.std(), 0.6)

    def test_negative(self):
        n = lab.negative(self.a, films.BY_CODE['CNEG'])
        self.assertGreater(n[..., 0].mean(), n[..., 2].mean())          # orange mask
        m = lab.negative(self.a, films.BY_CODE['ACRO'])
        self.assertLess(np.abs(m[..., 0] - m[..., 1]).max(), 0.02)

    def test_borders_strip_sheet(self):
        im = lab.to_image(self.a)
        for b in lab.BORDERS:
            out = lab.bordered(im, b, 'PROVIA  01')
            self.assertGreaterEqual(out.width, im.width)
        s = lab.strip([im, None, im], films.BY_CODE['PROV'], positive=False, frame_w=200)
        self.assertEqual(s.height, int(200 * 2 / 3) + 2 * int(int(200 * 2 / 3) * 0.20))
        sheet = lab.contact_sheet([im] * 8, films.BY_CODE['PROV'], 'TEST')
        self.assertGreater(sheet.height, sheet.width / 4)

    def test_rotate(self):
        im = lab.to_image(self.a)
        self.assertEqual(lab.rotate(im, 90).size, (im.height, im.width))
        self.assertEqual(lab.rotate(im, -90).size, (im.height, im.width))
        self.assertIs(lab.rotate(im, 360), im)
        r = lab.rotate(im, 90)                       # clockwise: the top-left corner goes to the top-right
        self.assertEqual(r.getpixel((r.width - 1, 0)), im.getpixel((0, 0)))

    def test_defaults_and_looks(self):
        r = lab.Recipe()
        self.assertEqual((r.paper, r.border, r.expired), ('vintage', 'white', 3))       # the vintage print is the default
        self.assertEqual(lab.preset_name(r), 'Vintage print')
        self.assertEqual(lab.preset_name(lab.Recipe(push=2)), None)
        for name, p in lab.PRESETS.items():
            self.assertEqual(lab.preset_name(p), name)
            out = lab.develop(self.a, films.BY_CODE['PROV'], p, frame=4)
            self.assertTrue(0 <= out.min() and out.max() <= 1)
        v = lab.develop(self.a, films.BY_CODE['PROV'], lab.Recipe(grain=0, leaks=False), frame=4)
        g = lab.develop(self.a, films.BY_CODE['PROV'], lab.Recipe(grain=0, leaks=False, paper='glossy'), frame=4)
        self.assertGreater(v.min(), g.min())                                            # vintage paper lifts the blacks
        self.assertGreater((v[..., 0] - v[..., 2]).mean(), (g[..., 0] - g[..., 2]).mean())   # and is warmer

    def test_surprise(self):
        import random
        r = lab.surprise(random.Random(1))
        self.assertIn(r.developer, lab.DEVELOPERS)
        self.assertEqual(lab.Recipe.from_dict(r.to_dict()), r)


class OwnPhotos(unittest.TestCase):
    """Photos from any camera, loaded by hand."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.lib = Library(os.path.join(self.tmp, 'lib'))
        from datetime import datetime, timedelta
        self.src = os.path.join(self.tmp, 'phone')
        os.makedirs(self.src)
        self.paths = []
        for k, ext in enumerate(('jpg', 'png', 'jpg')):                 # named out of order: the roll follows the time taken
            p = os.path.join(self.src, 'IMG_%d.%s' % (9 - k, ext))
            fixtures.frame(k).save(p, exif=self._exif(datetime(2026, 5, 1, 12, 0) + timedelta(minutes=k)) if ext == 'jpg' else None)
            self.paths.append(p)
        with open(os.path.join(self.src, 'notes.txt'), 'w') as f:
            f.write('not a photo')

    @staticmethod
    def _exif(t):
        from PIL import Image
        ex = Image.Exif()
        ex[0x110] = 'Pixel 9'
        ex[0x132] = t.strftime('%Y:%m:%d %H:%M:%S')
        return ex

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_load_develop_change_film(self):
        rid = self.lib.import_files(self.paths + [os.path.join(self.src, 'notes.txt')], 'VELV', 'Beach day')
        self.assertTrue(rid.startswith('BEACH-DAY_2026050'))
        r = self.lib.load_roll(rid)
        self.assertTrue(r.own)
        self.assertEqual((r.name, r.film.code, r.true_film.code, len(r.frames)), ('Beach day', 'VELV', 'VELV', 3))
        self.assertTrue(all(f.film is None for f in r.frames))
        folder, lc = self.lib.develop(r, lab.Recipe(), max_side=None)
        self.assertEqual((lc['film'], len(lc['frames'])), ('Velvia', 3))
        self.lib.set_film(rid, 'ACRO')
        r2 = self.lib.load_roll(rid)
        self.assertEqual(r2.true_film.code, 'ACRO')
        folder2, lc2 = self.lib.develop(r2, lab.Recipe(paper='glossy', border='none'))
        from PIL import Image
        px = np.asarray(Image.open(os.path.join(folder2, 'frame_01.jpg')).convert('RGB'), np.float32)
        self.assertLess(np.abs(px[..., 0] - px[..., 2]).mean(), 3.0)      # developed as ACROS: black and white
        rid2 = self.lib.import_files(self.paths, 'VELV', 'Beach day')
        self.assertNotEqual(rid2, rid)                                    # a second roll with the same name gets its own folder

    def test_mystery(self):
        import random
        rid = self.lib.import_files(self.paths, 'MYST', 'Surprise', rng=random.Random(4))
        r = self.lib.load_roll(rid)
        self.assertTrue(r.mystery)
        self.assertIn(r.true_film, films.FILMS)                            # a real film, kept secret by the app until developed
        self.assertFalse(self.lib.revealed(rid))
        folder, lc = self.lib.develop(r, lab.Recipe())
        self.assertEqual(lc['film'], r.true_film.name)
        self.assertTrue(lc['mystery'])

    def test_no_photos(self):
        with self.assertRaises(ValueError):
            self.lib.import_files([os.path.join(self.src, 'notes.txt')], 'PROV', 'x')


class Library_(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = fixtures.make_card(os.path.join(self.tmp, 'card'))
        self.lib = Library(os.path.join(self.tmp, 'lib'))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_import_and_develop(self):
        rolls = {r.code: r for r in card.scan(self.root)}
        myst = rolls['MYST001']
        libroll = self.lib.import_roll(myst)
        self.assertEqual(self.lib.rolls(), ['MYST001_20261108'])
        self.assertEqual(len(libroll.frames), 4)
        self.assertFalse(self.lib.revealed('MYST001_20261108'))
        before = {f.path: os.path.getsize(f.path) for f in myst.frames}
        seen = []
        folder, lc = self.lib.develop(libroll, lab.Recipe(push=1, border='black'), progress=lambda d, n, s, t: seen.append(d))
        self.assertEqual(seen, [1, 2, 3, 4])
        self.assertEqual(lc['film'], 'Classic Chrome')
        self.assertTrue(lc['mystery'] and lc['complete'])
        for fr in lc['frames']:
            self.assertTrue(os.path.exists(os.path.join(folder, fr['file'])))
        self.assertTrue(os.path.exists(os.path.join(folder, 'contact_sheet.jpg')))
        self.assertTrue(self.lib.revealed('MYST001_20261108'))
        self.assertEqual({f.path: os.path.getsize(f.path) for f in myst.frames}, before)       # originals untouched
        self.assertEqual(self.lib.stats()['frames'], 4)
        self.assertEqual(self.lib.stats()['favourite'], 'Classic Chrome')
        # rotation: remembered per frame, used by the next development, and a print can be turned afterwards
        rid = 'MYST001_20261108'
        self.assertEqual(self.lib.rotate(rid, 2, 90), 90)
        self.assertEqual(self.lib.rotate(rid, 3, -90), 270)
        self.assertEqual(self.lib.rotate(rid, 3, 90), 0)                 # back to straight: forgotten
        self.assertEqual(self.lib.rotations(rid), {2: 90})
        folder2, lc2 = self.lib.develop(libroll, lab.Recipe(), max_side=None)
        from PIL import Image
        w1, h1 = Image.open(os.path.join(folder2, 'frame_01.jpg')).size
        w2, h2 = Image.open(os.path.join(folder2, 'frame_02.jpg')).size
        self.assertGreater(w1, h1)
        self.assertGreater(h2, w2)                                        # frame 2 came out upright
        self.assertEqual(lc2['frames'][1]['rotation'], 90)
        sheet_before = os.path.getmtime(os.path.join(folder2, 'contact_sheet.jpg'))
        self.lib.rotate_print(folder2, 1, 90)
        w1b, h1b = Image.open(os.path.join(folder2, 'frame_01.jpg')).size
        self.assertEqual((w1b, h1b), (h1, w1))
        self.assertEqual(self.lib.rotations(rid), {1: 90, 2: 90})
        self.assertGreaterEqual(os.path.getmtime(os.path.join(folder2, 'contact_sheet.jpg')), sheet_before)
        # importing again does not duplicate
        self.lib.import_roll(myst)
        self.assertEqual(len(os.listdir(os.path.join(self.lib.roll_dir('MYST001_20261108'), 'originals'))), 4)



class Versions(unittest.TestCase):
    """Several developments of one roll: names, favourites, picks per frame, clean-up candidates."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        root = fixtures.make_card(os.path.join(self.tmp, 'card'))
        self.lib = Library(os.path.join(self.tmp, 'lib'))
        roll = {r.code: r for r in card.scan(root)}['PROV001']
        self.libroll = self.lib.import_roll(roll)
        self.rid = os.path.basename(self.libroll.path)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_versions(self):
        L = self.lib
        f1, lc1 = L.develop(self.libroll, lab.Recipe(), max_side=400, look='Vintage print')
        f2, lc2 = L.develop(self.libroll, lab.Recipe(push=2), max_side=400)          # (the same second: still its own folder)
        f3, lc3 = L.develop(self.libroll, lab.Recipe(paper='matte'), max_side=400)
        self.assertEqual(len({f1, f2, f3}), 3)
        self.assertEqual([f for f, _ in L.developments(self.rid)], [f3, f2, f1])         # newest first
        self.assertTrue(L.version_name(lc1).startswith('Provia  ·  Vintage print  ·  '))   # film, recipe card, when
        self.assertIn('push +2', L.version_name(lc2))                                      # no card: what was done
        L.set_version(f2, name='  Contrasty  ')
        L.set_version(f3, favourite=True)
        devs = dict(L.developments(self.rid))
        self.assertEqual(L.version_name(devs[f2]), 'Contrasty')
        self.assertTrue(devs[f3]['favourite'])
        L.set_version(f2, name='')
        self.assertNotIn('name', dict(L.developments(self.rid))[f2])                    # back to the automatic name
        # by frame: every print of each frame, newest first; the newest is chosen until you pick
        fp = L.frame_prints(self.rid)
        n = len(self.libroll.frames)
        self.assertEqual(sorted(fp), list(range(1, n + 1)))
        self.assertEqual([x[1] for x in fp[1]], [f3, f2, f1])
        self.assertEqual(L.chosen_prints(self.rid)[2], os.path.join(f3, 'frame_02.jpg'))
        L.set_pick(self.rid, 2, f1)
        self.assertEqual(L.picks(self.rid), {2: os.path.basename(f1)})
        self.assertEqual(L.chosen_prints(self.rid)[2], os.path.join(f1, 'frame_02.jpg'))
        # clean-up keeps favourites and developments that hold a pick
        self.assertEqual([f for f, _ in L.cleanup_candidates(self.rid)], [f2])
        self.assertGreater(L.folder_size(f2), 0)
        shutil.rmtree(f1)                                                               # a development gone: its picks go too
        self.assertEqual(L.picks(self.rid), {})
        self.assertEqual(L.chosen_prints(self.rid)[2], os.path.join(f3, 'frame_02.jpg'))


class AuthenticScan(unittest.TestCase):
    """Authentic scan: a sharp, high-range phone photo is softened and its highlights roll off; FAUXJI photos are left alone."""

    def setUp(self):
        rng = np.random.default_rng(4)
        h, w = 120, 1600
        a = rng.random((h, w, 3)).astype(np.float32) * 0.25 + 0.55           # a noisy, bright, hair-sharp frame
        a[:, 800:] = np.clip(a[:, 800:] + 0.35, 0, 1)                        # with a clipped highlight half
        self.a = a
        self.prov = films.BY_CODE['PROV']
        self.base = dict(grain=0, leaks=False, expired=0, paper='glossy', border='none')

    def dev(self, authentic, emulate=True, film=None):
        return lab.develop(self.a, film or self.prov, lab.Recipe(**self.base, authentic=authentic), frame=3, emulate=emulate)

    def test_softens_and_rolls_off(self):
        on, off = self.dev(True), self.dev(False)
        hf = lambda x: np.abs(np.diff(x[..., 1], axis=1)).mean()             # noqa: E731
        self.assertLess(hf(on), hf(off) * 0.9)                               # less fine detail
        clipped = lambda x: (x[:, 810:] >= 0.999).mean()                   # noqa: E731
        self.assertLess(clipped(on), clipped(off) * 0.5)                      # far fewer highlights pinned at pure white
        self.assertGreater(on.min(), off.min() - 1e-6)                       # blacks never go lower
        self.assertTrue(0 <= on.min() and on.max() <= 1)

    def test_latitude_depends_on_the_film(self):
        self.assertLess(lab.SHOULDER['cine'], lab.SHOULDER['slide'])          # a cinema film holds highlights longer than a slide film
        slide, cine = (self.dev(True, film=films.BY_CODE[c])[:, 810:].mean() for c in ('VELV', 'ETRN'))
        self.assertNotAlmostEqual(float(slide), float(cine), places=3)       # and each film gets its own curve

    def test_midtones_are_left_alone(self):
        x = np.linspace(0, 0.6, 50, dtype=np.float32)[None, :, None].repeat(3, axis=2)
        y = lab._shoulder(x, 0.68)
        self.assertLess(np.abs(y - x).max(), 0.011)                          # only the small black lift below the shoulder
        h = np.linspace(0.7, 1.0, 50, dtype=np.float32)[None, :, None].repeat(3, axis=2)
        top = h[0, :, 0] >= 0.85
        self.assertTrue((lab._shoulder(h, 0.68)[0, top, 0] < h[0, top, 0]).all())            # the highlights roll off ...
        self.assertTrue((np.diff(lab._shoulder(h, 0.68)[0, :, 0]) > 0).all())                # ... and still rise

    def test_not_for_fauxji_photos(self):
        self.assertTrue(np.allclose(self.dev(True, emulate=False), self.dev(False, emulate=False)))   # already film-like
        self.assertIn('every pixel kept', lab.Recipe(authentic=False).describe())
        self.assertTrue(lab.Recipe.from_dict({k: v for k, v in lab.Recipe().to_dict().items() if k != 'authentic'}).authentic)


class PhonePhotos(unittest.TestCase):
    """Photos from phones: turned the way the phone says, broken files left out, very large ones brought down."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_exif_orientation(self):
        im = Image.new('RGB', (80, 40), (200, 30, 30))                   # stored lying down ...
        ex = im.getexif()
        ex[0x112] = 6                                                    # ... with the note "turn me 90° clockwise"
        p = os.path.join(self.tmp, 'portrait.jpg')
        im.save(p, exif=ex)
        self.assertEqual(lab.load(p).shape[:2], (80, 40))                # loaded upright
        self.assertEqual(lab.load(p, 40).shape[:2], (40, 20))
        plain = os.path.join(self.tmp, 'plain.jpg')
        Image.new('RGB', (80, 40)).save(plain)
        self.assertEqual(lab.load(plain).shape[:2], (40, 80))            # no note (the TL500): as stored

    def test_broken_files_are_left_out(self):
        good = os.path.join(self.tmp, 'a.jpg')
        fixtures.frame(1).save(good)
        bad = os.path.join(self.tmp, 'b.jpg')
        with open(bad, 'wb') as f:
            f.write(b'this is not a photo')
        lib = Library(os.path.join(self.tmp, 'lib'))
        rid = lib.import_files([good, bad], 'PROV', 'Mixed')
        self.assertEqual(len(lib.load_roll(rid).frames), 1)
        with self.assertRaises(ValueError):
            lib.import_files([bad], 'PROV', 'Broken')

    def test_full_size_has_a_ceiling(self):
        from safelight import library
        old = library.MAX_FULL
        library.MAX_FULL = 200
        try:
            src = os.path.join(self.tmp, 'big.jpg')
            Image.new('RGB', (900, 600), (90, 120, 150)).save(src)
            lib = Library(os.path.join(self.tmp, 'lib'))
            roll = lib.load_roll(lib.import_files([src], 'PROV', 'Big'))
            folder, lc = lib.develop(roll, lab.Recipe(border='none', leaks=False))
            self.assertEqual(max(Image.open(os.path.join(folder, 'frame_01.jpg')).size), 200)
        finally:
            library.MAX_FULL = old


class Darkroom(unittest.TestCase):
    """Frames with their own settings, single prints, picks of single prints."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.lib = Library(os.path.join(self.tmp, 'lib'))
        src = os.path.join(self.tmp, 'phone')
        os.makedirs(src)
        for k in range(4):
            fixtures.frame(10 + k).save(os.path.join(src, 'IMG_%d.jpg' % k))
        self.rid = self.lib.import_files([os.path.join(src, n) for n in sorted(os.listdir(src))], 'VELV', 'Trip')
        self.roll = self.lib.load_roll(self.rid)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_frame_settings_and_develop(self):
        L, rid = self.lib, self.rid
        L.set_frame_settings(rid, [2], lab.Recipe(paper='neutral', grain=0, leaks=False, seed=99), 'ACRO')
        L.set_frame_settings(rid, [3], lab.Recipe(push=1), None)
        fs = L.frame_settings(rid)
        self.assertEqual(sorted(fs), [2, 3])
        self.assertEqual((fs[2]['film'], fs[2]['recipe']['paper']), ('ACRO', 'neutral'))
        self.assertNotIn('seed', fs[2]['recipe'])
        folder, lc = L.develop(self.roll, lab.Recipe(grain=0, leaks=False), max_side=300)
        by = {fr['frame']: fr for fr in lc['frames']}
        self.assertEqual(by[1]['film'], 'Velvia')
        self.assertNotIn('own_settings', by[1])
        self.assertEqual(by[2]['film'], 'Acros')                          # frame 2: its own film ...
        self.assertTrue(by[2]['own_settings'] and by[2]['recipe']['paper'] == 'neutral')
        self.assertEqual(by[3]['film'], 'Velvia')                         # frame 3: own lab settings, the roll's film
        a = np.asarray(Image.open(os.path.join(folder, by[2]['file'])).convert('RGB'), np.float32)
        self.assertLess(np.abs(a[..., 0] - a[..., 2]).mean(), 2.0)         # ... printed in black and white
        L.set_frame_settings(rid, [2, 3], None)
        self.assertEqual(L.frame_settings(rid), {})

    def test_fauxji_frames_keep_their_film(self):
        root = fixtures.make_card(os.path.join(self.tmp, 'card'))
        prov = self.lib.import_roll({r.code: r for r in card.scan(root)}['PROV001'])
        rid = os.path.basename(prov.path)
        self.lib.set_frame_settings(rid, [1], lab.Recipe(push=2), 'ACRO')
        r, film = self.lib.effective(prov, prov.frames[0], lab.Recipe(seed=5), self.lib.frame_settings(rid)[1])
        self.assertEqual((film.code, r.push, r.seed), ('PROV', 2, 5))   # the lab settings count, the film is the camera's

    def test_single_prints_and_picks(self):
        L, rid = self.lib, self.rid
        self.assertFalse(L.revealed(rid))
        made = L.print_frames(self.roll, [2], lab.Recipe(), max_side=300, look='Vintage print')
        made += L.print_frames(self.roll, [2, 4], lab.Recipe(push=1), max_side=300)
        names = [os.path.basename(m) for m in made]
        self.assertEqual(names, ['frame_02-v1.jpg', 'frame_02-v2.jpg', 'frame_04-v1.jpg'])
        self.assertTrue(L.revealed(rid))                                  # a single print reveals a mystery roll too
        self.assertEqual(L.developments(rid), [])                         # single prints are not developments
        fp = L.frame_prints(rid)
        self.assertEqual(sorted(fp), [2, 4])
        self.assertEqual(len(fp[2]), 2)
        lc, fr = L.print_info(made[0])
        self.assertTrue(lc['single'] and fr['frame'] == 2 and lc['look'] == 'Vintage print')
        self.assertTrue(L.version_name(lc).startswith('Single print v1  ·  Velvia  ·  Vintage print'))
        folder, _ = L.develop(self.roll, lab.Recipe(), max_side=300)
        self.assertEqual(len(L.frame_prints(rid)[2]), 3)
        L.set_pick(rid, 2, made[0])                                       # a single print as the pick
        self.assertEqual(L.picks(rid), {2: 'darkroom/frame_02-v1.jpg'})
        self.assertEqual(L.chosen_prints(rid)[2], made[0])
        self.assertEqual(L.chosen_prints(rid)[1], os.path.join(folder, 'frame_01.jpg'))
        self.assertEqual([f for f, _ in L.cleanup_candidates(rid)], [folder])
        w, h = Image.open(made[0]).size
        L.rotate_print_path(made[0], 90)
        self.assertEqual(Image.open(made[0]).size, (h, w))
        self.assertEqual(L.rotations(rid), {2: 90})
        os.remove(made[0])
        self.assertEqual(L.picks(rid), {})                                 # a pick of a print that is gone is forgotten


class BlackAndWhite(unittest.TestCase):
    """The B&W lab additions: a coloured filter (photos from any camera), toning, neutral paper."""

    def setUp(self):
        h, w = 60, 90
        a = np.zeros((h, w, 3), np.float32)
        a[:30] = (0.25, 0.45, 0.85)                  # blue sky on top
        a[30:] = (0.85, 0.55, 0.40)                  # skin-ish below
        self.a = a
        self.acros = films.BY_CODE['ACRO']
        self.plain = dict(grain=0, leaks=False, expired=0, paper='glossy', border='none')

    def dev(self, **kw):
        return lab.develop(self.a, self.acros, lab.Recipe(**{**self.plain, **kw}), frame=3, emulate=True)

    def test_filters(self):
        none, red, green = self.dev(), self.dev(bw_filter='red'), self.dev(bw_filter='green')
        sky = lambda x: x[:30].mean()                                 # noqa: E731
        skin = lambda x: x[30:].mean()                                # noqa: E731
        self.assertLess(sky(red), sky(none) - 0.05)                    # a red filter darkens the blue sky ...
        self.assertGreater(skin(red), skin(none))                      # ... and lightens skin
        self.assertLess(skin(green), skin(none))                       # green darkens skin
        for out in (none, red):
            self.assertLess(np.abs(out[..., 0] - out[..., 2]).max(), 1e-5)    # still neutral grey

    def test_tones_and_neutral_paper(self):
        neutral = self.dev(paper='neutral')
        self.assertLess(np.abs(neutral[..., 0] - neutral[..., 2]).max(), 1e-5)  # neutral fibre adds no colour
        vintage = self.dev(paper='vintage')
        self.assertGreater((vintage[..., 0] - vintage[..., 2]).mean(), 0.02)    # the vintage paper warms B&W (why neutral exists)
        sel = self.dev(tone='selenium')
        self.assertGreater((sel[..., 2] - sel[..., 1]).mean(), 0.001)          # selenium: a cool cast
        sep = self.dev(tone='sepia')
        self.assertGreater((sep[..., 0] - sep[..., 2]).mean(), 0.05)            # sepia: brown
        self.assertIn('red filter', lab.Recipe(bw_filter='red').describe())
        self.assertIn('selenium toned', lab.Recipe(tone='selenium').describe())

    def test_colour_films_ignore_bw_settings(self):
        prov = films.BY_CODE['PROV']
        a = lab.develop(self.a, prov, lab.Recipe(**self.plain), frame=3, emulate=True)
        b = lab.develop(self.a, prov, lab.Recipe(**self.plain, bw_filter='red', tone='selenium'), frame=3, emulate=True)
        self.assertTrue(np.allclose(a, b))

    def test_old_labcards_still_load(self):
        old = {k: v for k, v in lab.Recipe().to_dict().items() if k not in ('bw_filter', 'tone')}
        r = lab.Recipe.from_dict(old)
        self.assertEqual((r.bw_filter, r.tone), ('none', 'none'))


class RecipeCards(unittest.TestCase):
    def setUp(self):
        from safelight import recipes
        self.recipes = recipes
        self.tmp = tempfile.mkdtemp()
        self.lib = Library(os.path.join(self.tmp, 'lib'))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_builtin(self):
        R = self.recipes
        names = [c.name.lower() for c in R.LOOKS + R.BUILTIN]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual([c.name for c in R.LOOKS], list(lab.PRESETS))
        for c in R.BUILTIN:
            self.assertIn(c.film, films.BY_CODE)
            self.assertIn(c.kind, R.KINDS)
            self.assertTrue(c.note)
        bw = [c for c in R.BUILTIN if c.kind == 'bw']
        self.assertTrue(bw and all(films.BY_CODE[c.film].mono for c in bw))
        silver = next(c for c in R.BUILTIN if c.name == 'Silver gelatin')
        self.assertEqual((silver.film, silver.recipe.paper), ('ACRO', 'neutral'))

    def test_find(self):
        R = self.recipes
        cards = R.LOOKS + R.BUILTIN
        silver = next(c for c in R.BUILTIN if c.name == 'Silver gelatin')
        self.assertIs(R.find(cards, silver.recipe, 'ACRO'), silver)
        self.assertIsNone(R.find(cards, silver.recipe, 'PROV'))         # the card's film is not the roll's: Custom
        self.assertIs(R.find(cards, silver.recipe, None), silver)       # no roll yet: the lab settings decide
        self.assertEqual(R.find(cards, lab.Recipe(), 'PROV').name, 'Vintage print')
        self.assertIsNone(R.find(cards, lab.Recipe(push=2, expired=1), 'PROV'))

    def test_save_list_import_delete(self):
        R = self.recipes
        c = R.Card('Moody nights', lab.Recipe(push=1, halation=2.0, bw_filter='red', seed=1234), 'ETRN', 'night', 'For rain.')
        self.lib.save_card(c)
        mine = self.lib.recipe_cards()
        self.assertEqual([x.name for x in mine], ['Moody nights'])
        self.assertEqual((mine[0].film, mine[0].kind, mine[0].recipe.halation, mine[0].recipe.seed), ('ETRN', 'night', 2.0, 0))
        self.assertTrue(mine[0].matches(c.recipe, 'ETRN'))
        # a shared card from a newer version, with values this one doesn't know: still loads
        shared = os.path.join(self.tmp, 'shared.json')
        d = c.to_dict()
        d.update(name='From a friend', film='ZZZZ')
        d['recipe'].update(paper='platinum', future_setting=3)
        Library._write(shared, d)
        got = self.lib.import_card(shared)
        self.assertEqual((got.film, got.recipe.paper), (None, 'vintage'))
        bad = os.path.join(self.tmp, 'bad.json')
        Library._write(bad, {'hello': 1})
        with self.assertRaises(ValueError):
            self.lib.import_card(bad)
        self.assertEqual(len(self.lib.recipe_cards()), 2)
        self.lib.delete_card('Moody nights')
        self.assertEqual([x.name for x in self.lib.recipe_cards()], ['From a friend'])
        self.assertEqual(self.lib.rolls(), [])                          # the presets folder is not a roll


if __name__ == '__main__':
    unittest.main()

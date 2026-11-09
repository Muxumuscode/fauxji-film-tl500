"""python -m unittest discover -s tests   (from the safelight folder)"""
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

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


if __name__ == '__main__':
    unittest.main()

"""The library on disk (default: ~/Pictures/Safelight):

  <library>/<roll id>/originals/          the camera's files, copied untouched (the card can go back in the camera)
  <library>/<roll id>/roll.json           what the roll is (film, frames, dates, where it came from)
  <library>/<roll id>/develop-<time>/     one development: prints (frame_01.jpg ...), contact_sheet.jpg, labcard.json
  <library>/lablog.json                   every development, newest last (the lab log)
"""
import json
import os
import shutil
import time
from datetime import datetime

from PIL import Image

from . import card, films, lab

ROLL_JSON = 'roll.json'
LABCARD = 'labcard.json'


def default_root():
    pics = os.path.join(os.path.expanduser('~'), 'Pictures')
    base = pics if os.path.isdir(pics) else os.path.expanduser('~')
    old = os.path.join(base, 'Safelight')                     # the library of version 0.1 (the app's working name) is kept
    return old if os.path.isdir(old) else os.path.join(base, 'Sajin Genzo')


class Library:
    def __init__(self, root=None):
        self.root = root or default_root()
        os.makedirs(self.root, exist_ok=True)

    # ------------------------------------------------------------ rolls
    def roll_dir(self, roll_id):
        return os.path.join(self.root, roll_id)

    def import_roll(self, roll, progress=None):
        """Copy the roll's originals into the library (skips files already there). Returns the library roll (paths in the library)."""
        rd = self.roll_dir(roll.roll_id)
        od = os.path.join(rd, 'originals')
        os.makedirs(od, exist_ok=True)
        for k, f in enumerate(roll.frames):
            dst = os.path.join(od, '%02d_%s' % (f.number, os.path.basename(f.path)))
            if not (os.path.exists(dst) and os.path.getsize(dst) == os.path.getsize(f.path)):
                shutil.copy2(f.path, dst)
            if progress:
                progress(k + 1, len(roll.frames))
        meta = {'code': roll.code, 'film_code': roll.film.code, 'source': roll.path, 'imported': datetime.now().isoformat(timespec='seconds'),
                'frames': len(roll.frames), 'first': roll.first.isoformat() if roll.first else None,
                'last': roll.last.isoformat() if roll.last else None}
        old = self._read(os.path.join(rd, ROLL_JSON)) or {}
        old.update(meta)
        self._write(os.path.join(rd, ROLL_JSON), old)
        return self.load_roll(roll.roll_id)

    def load_roll(self, roll_id):
        rd = self.roll_dir(roll_id)
        meta = self._read(os.path.join(rd, ROLL_JSON)) or {}
        r = card.load_roll(os.path.join(rd, 'originals'), code=meta.get('code', roll_id.split('_')[0]))
        r.code = meta.get('code', r.code)
        r.film = films.from_code(meta.get('film_code', r.code))
        r.path = rd
        r.own = bool(meta.get('own'))
        r.name = meta.get('name', '')
        if meta.get('secret_film'):
            r.secret_film = films.from_code(meta['secret_film'])
        if r.own:
            for f in r.frames:
                f.film = None                       # other cameras' EXIF says nothing about the film: the roll's film counts
        return r

    # ------------------------------------------------------------ photos from any camera
    def import_files(self, paths, film_code, name, progress=None, rng=None):
        """Make a roll of any photos (any camera): copied into the library in the order they were taken, developed as `film_code`
        (MYST: a film picked at random and kept secret until the roll is developed). Returns the roll id."""
        import random
        paths = [p for p in paths if p.lower().endswith(card.IMAGE_EXT)]
        if not paths:
            raise ValueError('no photos (JPEG, PNG, TIFF, WebP or BMP) among the files')
        dated = sorted(((card.read_exif(p)[0] or datetime.max), os.path.basename(p).lower(), p) for p in paths)
        first = next((d for d, _, _ in dated if d != datetime.max), datetime.now())
        slug = ''.join(c if c.isalnum() else '-' for c in name.upper()).strip('-')[:20] or 'MYROLL'
        rid = '%s_%s' % (slug, first.strftime('%Y%m%d'))
        k = 2
        while self.has_roll(rid):
            rid = '%s-%d_%s' % (slug, k, first.strftime('%Y%m%d'))
            k += 1
        od = os.path.join(self.roll_dir(rid), 'originals')
        os.makedirs(od, exist_ok=True)
        for n, (_, _, p) in enumerate(dated, 1):
            shutil.copy2(p, os.path.join(od, '%03d_%s' % (n, os.path.basename(p))))
            if progress:
                progress(n, len(dated))
        meta = {'code': rid.split('_')[0], 'name': name, 'own': True, 'film_code': film_code, 'source': os.path.dirname(paths[0]),
                'imported': datetime.now().isoformat(timespec='seconds'), 'frames': len(dated),
                'first': None if first is None else first.isoformat(),
                'last': max((d for d, _, _ in dated if d != datetime.max), default=first).isoformat()}
        if film_code == films.MYSTERY.code:
            meta['secret_film'] = (rng or random.Random()).choice(films.FILMS).code
        self._write(os.path.join(self.roll_dir(rid), ROLL_JSON), meta)
        return rid

    def set_film(self, roll_id, film_code):
        """Change the film of a roll of own photos (the next previews and developments use it)."""
        path = os.path.join(self.roll_dir(roll_id), ROLL_JSON)
        meta = self._read(path) or {}
        meta['film_code'] = film_code
        meta.pop('secret_film', None)
        if film_code == films.MYSTERY.code:
            import random
            meta['secret_film'] = random.Random().choice(films.FILMS).code
        self._write(path, meta)

    def rolls(self):
        """Roll ids in the library, newest import first."""
        out = []
        for n in os.listdir(self.root):
            meta = self._read(os.path.join(self.root, n, ROLL_JSON))
            if meta:
                out.append((meta.get('imported', ''), n))
        return [n for _, n in sorted(out, reverse=True)]

    def has_roll(self, roll_id):
        return os.path.exists(os.path.join(self.roll_dir(roll_id), ROLL_JSON))

    # ------------------------------------------------------------ rotation (the camera has no orientation sensor: upright shots
    # come out sideways). Kept per roll and frame in <library>/rotations.json, for rolls still on the card too.
    def rotations(self, roll_id):
        """{frame number: clockwise degrees (90, 180, 270)}"""
        d = (self._read(os.path.join(self.root, 'rotations.json')) or {}).get(roll_id, {})
        return {int(k): v for k, v in d.items() if v % 360}

    def rotate(self, roll_id, frame, delta):
        """Turn a frame by `delta` degrees clockwise (multiples of 90). Returns the new rotation."""
        path = os.path.join(self.root, 'rotations.json')
        allr = self._read(path) or {}
        r = allr.setdefault(roll_id, {})
        new = (r.get(str(frame), 0) + delta) % 360
        if new:
            r[str(frame)] = new
        else:
            r.pop(str(frame), None)
        self._write(path, allr)
        return new

    def rotate_print(self, folder, frame, delta):
        """Turn a developed print (the JPEG in the development folder) and remake the contact sheet. The frame's rotation is remembered
        for the next development too."""
        lc = self._read(os.path.join(folder, LABCARD)) or {}
        rid = lc.get('roll_id') or os.path.basename(os.path.dirname(folder))
        self.rotate(rid, frame, delta)
        name = 'frame_%02d.jpg' % frame if frame < 100 else 'frame_%d.jpg' % frame
        p = os.path.join(folder, name)
        with Image.open(p) as im:
            out = lab.rotate(im.convert('RGB'), delta)
        out.save(p, quality=93, subsampling=0)
        self.remake_sheet(folder)
        return p

    def remake_sheet(self, folder):
        lc = self._read(os.path.join(folder, LABCARD)) or {}
        thumbs = []
        for fr in lc.get('frames', []):
            with Image.open(os.path.join(folder, fr['file'])) as im:
                im.draft('RGB', (700, 700))
                t = im.convert('RGB')
                t.thumbnail((600, 600))
                thumbs.append(t)
        film = films.BY_NAME.get(lc.get('film', '').lower(), films.UNKNOWN)
        lab.contact_sheet(thumbs, film, '%s  ·  %s  ·  %s' % (lc.get('roll', ''), film.name, lc.get('description', ''))).save(
            os.path.join(folder, 'contact_sheet.jpg'), quality=90)

    # ------------------------------------------------------------ developments
    def developments(self, roll_id):
        """[(folder, labcard dict)] newest first."""
        rd = self.roll_dir(roll_id)
        out = []
        if os.path.isdir(rd):
            for n in sorted(os.listdir(rd), reverse=True):
                lc = self._read(os.path.join(rd, n, LABCARD))
                if n.startswith('develop-') and lc:
                    out.append((os.path.join(rd, n), lc))
        return out

    def revealed(self, roll_id):
        return bool(self.developments(roll_id))

    def develop(self, roll, recipe, progress=None, cancelled=lambda: False, max_side=None):
        """Develop every frame of a library roll. progress(done, total, stage, preview PIL image). Returns (folder, labcard)."""
        stamp = time.strftime('%Y%m%d-%H%M%S')
        rid = os.path.basename(os.path.normpath(roll.path)) if os.path.normpath(roll.path).startswith(os.path.normpath(self.root))             else roll.roll_id
        out = os.path.join(self.roll_dir(rid), 'develop-' + stamp)
        os.makedirs(out, exist_ok=True)
        film = roll.true_film
        if not recipe.seed:
            recipe.seed = lab._seed(roll.code, stamp) & 0x3FFFFFFF
        n = len(roll.frames)
        thumbs, done = [], []
        turns = self.rotations(rid)
        for k, f in enumerate(roll.frames):
            if cancelled():
                break
            a = lab.load(f.path, max_side)
            p = lab.develop(a, f.film or film, recipe, frame=f.number, roll_seed=lab._seed(roll.code), emulate=roll.own)
            im = lab.rotate(lab.to_image(p), turns.get(f.number, 0))
            im = lab.bordered(im, recipe.border, lab.frame_caption(f.film or film, f.number, f.taken))
            name = 'frame_%02d.jpg' % f.number if f.number < 100 else 'frame_%d.jpg' % f.number
            im.save(os.path.join(out, name), quality=93, subsampling=0)
            t = im.copy()
            t.thumbnail((600, 600))
            thumbs.append(t)
            done.append({'frame': f.number, 'file': name, 'original': os.path.basename(f.path), 'rotation': turns.get(f.number, 0),
                         'taken': f.taken.isoformat() if f.taken else None, 'film': (f.film or film).name})
            if progress:
                progress(k + 1, n, None, t)
        sheet = lab.contact_sheet([t for t in thumbs], film, '%s  ·  %s  ·  %s' % (roll.code, film.name, recipe.describe()))
        sheet.save(os.path.join(out, 'contact_sheet.jpg'), quality=90)
        labcard = {'roll': roll.code, 'roll_id': rid, 'film': film.name, 'film_code': film.code,
                   'mystery': roll.mystery, 'developed': datetime.now().isoformat(timespec='seconds'), 'recipe': recipe.to_dict(),
                   'description': recipe.describe(), 'frames': done, 'complete': len(done) == n}
        self._write(os.path.join(out, LABCARD), labcard)
        log = self._read(os.path.join(self.root, 'lablog.json')) or []
        log.append({k: labcard[k] for k in ('roll', 'roll_id', 'film', 'developed', 'description', 'mystery')} | {'frames': len(done)})
        self._write(os.path.join(self.root, 'lablog.json'), log)
        return out, labcard

    def lablog(self):
        return self._read(os.path.join(self.root, 'lablog.json')) or []

    def stats(self):
        log = self.lablog()
        byfilm = {}
        for e in log:
            byfilm[e['film']] = byfilm.get(e['film'], 0) + e.get('frames', 0)
        fav = max(byfilm, key=byfilm.get) if byfilm else None
        return {'developments': len(log), 'frames': sum(e.get('frames', 0) for e in log), 'favourite': fav, 'by_film': byfilm}

    # ------------------------------------------------------------ io
    @staticmethod
    def _read(path):
        try:
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    @staticmethod
    def _write(path, data):
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
        os.replace(tmp, path)

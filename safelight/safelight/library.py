"""The library on disk (default: ~/Pictures/Safelight):

  <library>/<roll id>/originals/          the camera's files, copied untouched (the card can go back in the camera)
  <library>/<roll id>/roll.json           what the roll is (film, frames, dates, where it came from)
  <library>/<roll id>/develop-<time>/     one development: prints (frame_01.jpg ...), contact_sheet.jpg, labcard.json
  <library>/lablog.json                   every development, newest last (the lab log)
  <library>/presets/<name>.json           your own recipe cards
  <library>/frame_settings.json           Darkroom: frames with their own film / lab settings, per roll
  <library>/<roll id>/darkroom/           Darkroom: single prints (frame_07-v2.jpg) with what was done (frame_07-v2.json)
  <library>/<roll id>/picks.json          your pick of print for each frame
"""
import json
import os
import re
import shutil
import time
from datetime import datetime

from PIL import Image

from . import card, films, lab, recipes

ROLL_JSON = 'roll.json'
LABCARD = 'labcard.json'
MAX_FULL = 6000                           # 'full size' prints: at most this many pixels on the long side (24 MP at 3:2)
DARKROOM = 'darkroom'                     # <roll>/darkroom/: single prints made in the Darkroom, frame_07-v2.jpg with frame_07-v2.json


def frame_number(path):
    """The frame a print is of, from its file name (frame_07.jpg, frame_07-v2.jpg); None if it is not a print."""
    m = re.match(r'frame_(\d+)', os.path.basename(path))
    return int(m.group(1)) if m else None


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
        paths = [p for p in paths if p.lower().endswith(card.IMAGE_EXT) and self.readable(p)]
        if not paths:
            raise ValueError('no photos (JPEG, PNG, TIFF, WebP or BMP) that can be opened among the files')
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

    @staticmethod
    def readable(path):
        """Can this photo be opened? (A broken file would stop a whole development.)"""
        try:
            with Image.open(path) as im:
                im.verify()
            return True
        except Exception:
            return False

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
        """A mystery roll's film is revealed by its first print: a development or a single print."""
        return bool(self.developments(roll_id)) or bool(self.single_prints(roll_id))

    def develop(self, roll, recipe, progress=None, cancelled=lambda: False, max_side=None, look=None):
        """Develop every frame of a library roll. progress(done, total, stage, preview PIL image). Returns (folder, labcard).
        look: the recipe card it was developed with (for the version's name)."""
        stamp = time.strftime('%Y%m%d-%H%M%S')
        rid = os.path.basename(os.path.normpath(roll.path)) if os.path.normpath(roll.path).startswith(os.path.normpath(self.root))             else roll.roll_id
        out = os.path.join(self.roll_dir(rid), 'develop-' + stamp)
        k = 2
        while os.path.exists(out):                                   # two developments in the same second: never mix them
            out = os.path.join(self.roll_dir(rid), 'develop-%s-%d' % (stamp, k))
            k += 1
        os.makedirs(out)
        film = roll.true_film
        if not recipe.seed:
            recipe.seed = lab._seed(roll.code, stamp) & 0x3FFFFFFF
        n = len(roll.frames)
        thumbs, done = [], []
        turns = self.rotations(rid)
        own = self.frame_settings(rid)
        for k, f in enumerate(roll.frames):
            if cancelled():
                break
            name = 'frame_%02d.jpg' % f.number if f.number < 100 else 'frame_%d.jpg' % f.number
            im, entry = self._print_frame(roll, f, recipe, own.get(f.number), turns, max_side, os.path.join(out, name))
            t = im.copy()
            t.thumbnail((600, 600))
            thumbs.append(t)
            done.append(entry)
            if progress:
                progress(k + 1, n, None, t)
        sheet = lab.contact_sheet([t for t in thumbs], film, '%s  ·  %s  ·  %s' % (roll.code, film.name, recipe.describe()))
        sheet.save(os.path.join(out, 'contact_sheet.jpg'), quality=90)
        labcard = {'roll': roll.code, 'roll_id': rid, 'film': film.name, 'film_code': film.code,
                   'mystery': roll.mystery, 'developed': datetime.now().isoformat(timespec='seconds'), 'recipe': recipe.to_dict(),
                   'description': recipe.describe(), 'frames': done, 'complete': len(done) == n}
        if look:
            labcard['look'] = look
        self._write(os.path.join(out, LABCARD), labcard)
        log = self._read(os.path.join(self.root, 'lablog.json')) or []
        log.append({k: labcard[k] for k in ('roll', 'roll_id', 'film', 'developed', 'description', 'mystery')} | {'frames': len(done)})
        self._write(os.path.join(self.root, 'lablog.json'), log)
        return out, labcard

    def effective(self, roll, f, recipe, settings=None):
        """(recipe, film) a frame is printed with: its own Darkroom settings when it has them (the roll's randomness kept), else the
        roll's. A frame's own film counts for photos from other cameras only (a FAUXJI frame keeps the camera's film)."""
        film = f.film or roll.true_film
        if not settings:
            return recipe, film
        r = lab.Recipe.from_dict(settings['recipe'])
        r.seed = recipe.seed
        if roll.own and settings.get('film') in films.BY_CODE and settings['film'] != films.MYSTERY.code:
            film = films.BY_CODE[settings['film']]
        return r, film

    def _print_frame(self, roll, f, recipe, settings, turns, max_side, path):
        """Print one frame to `path`. Returns (the print, its entry for the lab card)."""
        r, film = self.effective(roll, f, recipe, settings)
        a = lab.load(f.path, max_side or MAX_FULL)
        p = lab.develop(a, film, r, frame=f.number, roll_seed=lab._seed(roll.code), emulate=roll.own)
        im = lab.rotate(lab.to_image(p), turns.get(f.number, 0))
        im = lab.bordered(im, r.border, lab.frame_caption(film, f.number, f.taken))
        im.save(path, quality=93, subsampling=0)
        entry = {'frame': f.number, 'file': os.path.basename(path), 'original': os.path.basename(f.path),
                 'rotation': turns.get(f.number, 0), 'taken': f.taken.isoformat() if f.taken else None, 'film': film.name}
        if settings:
            d = r.to_dict()
            d.pop('seed', None)
            entry.update(own_settings=True, recipe=d, description=r.describe())
        return im, entry

    # ------------------------------------------------------------ the Darkroom: frames with their own settings, single prints
    def frame_settings(self, roll_id):
        """{frame number: {'recipe': dict, 'film': film code or None}}: frames with their own settings (the Darkroom)."""
        d = (self._read(os.path.join(self.root, 'frame_settings.json')) or {}).get(roll_id, {})
        return {int(k): v for k, v in d.items() if isinstance(v, dict) and isinstance(v.get('recipe'), dict)}

    def set_frame_settings(self, roll_id, frames, recipe, film=None):
        """Give frames their own lab settings (and film, for photos from other cameras). recipe None: back to the roll's."""
        path = os.path.join(self.root, 'frame_settings.json')
        allr = self._read(path) or {}
        r = allr.setdefault(roll_id, {})
        for n in frames:
            if recipe is None:
                r.pop(str(n), None)
            else:
                d = recipe.to_dict()
                d.pop('seed', None)
                r[str(n)] = {'recipe': d, 'film': film}
        if not r:
            allr.pop(roll_id, None)
        self._write(path, allr)

    def print_frames(self, roll, numbers, recipe, progress=None, max_side=None, look=None):
        """Single prints of some frames (the Darkroom), each with its own settings when it has them, else the roll's `recipe`.
        They go to <roll>/darkroom/ as new versions (frame_07-v1.jpg, -v2 ...) with a small lab card each, and show in the prints'
        by-frame view. Returns [print path]."""
        rid = os.path.basename(os.path.normpath(roll.path))
        out = os.path.join(self.roll_dir(rid), DARKROOM)
        os.makedirs(out, exist_ok=True)
        recipe = lab.Recipe.from_dict(recipe.to_dict())
        if not recipe.seed:
            recipe.seed = lab._seed(roll.code, 'darkroom') & 0x3FFFFFFF
        own, turns, made = self.frame_settings(rid), self.rotations(rid), []
        frames = [f for f in roll.frames if f.number in set(numbers)]
        for k, f in enumerate(frames):
            v = 1
            while os.path.exists(os.path.join(out, 'frame_%02d-v%d.jpg' % (f.number, v))):
                v += 1
            path = os.path.join(out, 'frame_%02d-v%d.jpg' % (f.number, v))
            im, entry = self._print_frame(roll, f, recipe, own.get(f.number), turns, max_side, path)
            r, film = self.effective(roll, f, recipe, own.get(f.number))
            d = r.to_dict()
            d.pop('seed', None)
            card_ = dict(entry, single=True, roll=roll.code, roll_id=rid, film=film.name, film_code=film.code, version=v,
                         developed=datetime.now().isoformat(timespec='seconds'), recipe=d, description=r.describe())
            if look and not own.get(f.number):
                card_['look'] = look
            self._write(path[:-4] + '.json', card_)
            made.append(path)
            if progress:
                t = im.copy()
                t.thumbnail((600, 600))
                progress(k + 1, len(frames), None, t)
        log = self._read(os.path.join(self.root, 'lablog.json')) or []
        if made:
            log.append({'roll': roll.code, 'roll_id': rid, 'film': roll.true_film.name, 'developed': datetime.now().isoformat(timespec='seconds'),
                        'description': 'single print%s (darkroom)' % ('' if len(made) == 1 else 's'), 'mystery': roll.mystery, 'single': True,
                        'frames': len(made)})
            self._write(os.path.join(self.root, 'lablog.json'), log)
        return made

    def single_prints(self, roll_id):
        """[(print path, its lab card)] of the Darkroom's single prints."""
        d = os.path.join(self.roll_dir(roll_id), DARKROOM)
        out = []
        if os.path.isdir(d):
            for n in sorted(os.listdir(d)):
                if n.lower().endswith('.jpg'):
                    c = self._read(os.path.join(d, n[:-4] + '.json'))
                    if c:
                        out.append((os.path.join(d, n), c))
        return out

    def print_info(self, path):
        """(lab card, frame entry) of any print: a development's or a single print's."""
        if os.path.basename(os.path.dirname(path)) == DARKROOM:
            c = self._read(path[:-4] + '.json') or {}
            return c, c
        lc = self._read(os.path.join(os.path.dirname(path), LABCARD)) or {}
        fr = next((x for x in lc.get('frames', []) if x.get('file') == os.path.basename(path)), {})
        return lc, fr

    def rotate_print_path(self, path, delta):
        """Turn any print (a development's: its contact sheet is remade too; or a single print). The frame's rotation is remembered."""
        if os.path.basename(os.path.dirname(path)) != DARKROOM:
            return self.rotate_print(os.path.dirname(path), frame_number(path), delta)
        c = self._read(path[:-4] + '.json') or {}
        self.rotate(c.get('roll_id') or os.path.basename(os.path.dirname(os.path.dirname(path))), frame_number(path), delta)
        with Image.open(path) as im:
            out = lab.rotate(im.convert('RGB'), delta)
        out.save(path, quality=93, subsampling=0)
        return path

    def lablog(self):
        return self._read(os.path.join(self.root, 'lablog.json')) or []

    def stats(self):
        log = self.lablog()
        byfilm = {}
        for e in log:
            byfilm[e['film']] = byfilm.get(e['film'], 0) + e.get('frames', 0)
        fav = max(byfilm, key=byfilm.get) if byfilm else None
        return {'developments': sum(1 for e in log if not e.get('single')), 'frames': sum(e.get('frames', 0) for e in log), 'favourite': fav, 'by_film': byfilm}

    # ------------------------------------------------------------ versions: the developments of one roll, and the picks across them
    @staticmethod
    def version_name(lc):
        """A development's name: the one you gave it, else film · recipe (or what was done) · when."""
        if lc.get('name'):
            return lc['name']
        if lc.get('single'):
            try:
                when = datetime.fromisoformat(lc.get('developed', '')).strftime('%d %b %H:%M')
            except ValueError:
                when = ''
            return 'Single print v%s  ·  %s  ·  %s  ·  %s' % (lc.get('version', '?'), lc.get('film', '?'),
                                                            lc.get('look') or lc.get('description', ''), when)
        try:
            when = datetime.fromisoformat(lc.get('developed', '')).strftime('%d %b %H:%M')
        except ValueError:
            when = lc.get('developed', '')
        return '%s  ·  %s  ·  %s' % (lc.get('film', '?'), lc.get('look') or lc.get('description', ''), when)

    def set_version(self, folder, **changes):
        """Rename a development (name='' goes back to the automatic name) or mark it as a favourite (favourite=True / False)."""
        path = os.path.join(folder, LABCARD)
        lc = self._read(path)
        if lc is None:
            return None
        for k, v in changes.items():
            if k in ('name', 'favourite'):
                if v in ('', None, False):
                    lc.pop(k, None)
                else:
                    lc[k] = v.strip()[:80] if k == 'name' else True
        self._write(path, lc)
        return lc

    def picks(self, roll_id):
        """{frame number: development folder name}: the print you chose for each frame (Export my picks). Picks of developments
        that are gone are left out."""
        rd = self.roll_dir(roll_id)
        p = self._read(os.path.join(rd, 'picks.json')) or {}
        return {int(k): v for k, v in p.items()
                if (v.startswith(DARKROOM + '/') and os.path.isfile(os.path.join(rd, v))) or os.path.isfile(os.path.join(rd, v, LABCARD))}

    @staticmethod
    def pick_key(path):
        """How a pick names a print: its development folder, or darkroom/<file> for a single print."""
        if os.path.basename(os.path.dirname(path)) == DARKROOM:
            return DARKROOM + '/' + os.path.basename(path)
        return os.path.basename(os.path.dirname(path))

    def set_pick(self, roll_id, frame, target):
        """Your pick for a frame: a print (any) or a development folder."""
        path = os.path.join(self.roll_dir(roll_id), 'picks.json')
        p = self._read(path) or {}
        p[str(frame)] = os.path.basename(os.path.normpath(target)) if os.path.isdir(target) else self.pick_key(target)
        self._write(path, p)

    def frame_prints(self, roll_id):
        """{frame number: [(print path, development folder, labcard)], newest development first}: every print of each frame."""
        out = {}
        for folder, lc in self.developments(roll_id):
            for fr in lc.get('frames', []):
                p = os.path.join(folder, fr['file'])
                if os.path.isfile(p):
                    out.setdefault(fr['frame'], []).append((p, folder, lc))
        for p, c in self.single_prints(roll_id):                       # the Darkroom's single prints
            out.setdefault(c.get('frame') or frame_number(p), []).append((p, os.path.dirname(p), c))
        for prints in out.values():
            prints.sort(key=lambda x: x[2].get('developed', ''), reverse=True)     # (stable: same second keeps the order)
        return dict(sorted(out.items()))

    def chosen_prints(self, roll_id):
        """{frame number: print path}: your pick for each frame, else the print from the newest development."""
        picks, out = self.picks(roll_id), {}
        for n, prints in self.frame_prints(roll_id).items():
            want = picks.get(n)
            out[n] = next((p for p, _, _ in prints if self.pick_key(p) == want), prints[0][0])
        return out

    @staticmethod
    def folder_size(folder):
        total = 0
        for dirpath, _, names in os.walk(folder):
            for n in names:
                try:
                    total += os.path.getsize(os.path.join(dirpath, n))
                except OSError:
                    pass
        return total

    def cleanup_candidates(self, roll_id):
        """Developments that are neither a favourite nor hold one of your picks: what a clean-up would remove."""
        keep = set(self.picks(roll_id).values())
        return [(folder, lc) for folder, lc in self.developments(roll_id)
                if not lc.get('favourite') and os.path.basename(folder) not in keep]

    # ------------------------------------------------------------ recipe cards (<library>/presets/<name>.json)
    def presets_dir(self):
        return os.path.join(self.root, 'presets')

    def recipe_cards(self):
        """Your own recipe cards, by name. Files that are not cards are skipped."""
        out = []
        d = self.presets_dir()
        if os.path.isdir(d):
            for n in sorted(os.listdir(d)):
                if n.lower().endswith('.json'):
                    try:
                        out.append(recipes.Card.from_dict(self._read(os.path.join(d, n))))
                    except ValueError:
                        pass
        return sorted(out, key=lambda c: c.name.lower())

    def save_card(self, c):
        """Save (or replace) one of your recipe cards. Returns its file."""
        os.makedirs(self.presets_dir(), exist_ok=True)
        path = os.path.join(self.presets_dir(), recipes.slug(c.name) + '.json')
        self._write(path, c.to_dict())
        return path

    def delete_card(self, name):
        path = os.path.join(self.presets_dir(), recipes.slug(name) + '.json')
        if os.path.exists(path):
            os.remove(path)

    def import_card(self, path):
        """A recipe card from a file (someone else's), saved among yours. Raises ValueError when the file is not a card."""
        c = recipes.Card.from_dict(self._read(path))
        self.save_card(c)
        return c

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

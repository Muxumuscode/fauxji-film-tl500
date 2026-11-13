"""Finding rolls: the FAUXJI film camera saves each roll as FILMS/<CODE><nnn>/100PHOTO/SAM_nnnn.JPG on the card.

scan(path) accepts a card root, its FILMS folder, a single roll folder, or any folder of JPEGs (a "loose" roll, e.g. a backup copy).
The film of each frame comes from its EXIF Model ("TL500 Classic Chrome", written by the camera since TL-F65q); older rolls fall back to
the folder code. Mystery rolls (MYST) are resolved the same way, but the app keeps them secret until they are developed.
"""
import os
import re
from dataclasses import dataclass, field
from datetime import datetime

from PIL import Image

from . import films

ROLL_RE = re.compile(r'^([A-Z]{4})(\d{3})$')
IMAGE_EXT = ('.jpg', '.jpeg', '.png', '.tif', '.tiff', '.webp', '.bmp')
try:                                                  # HEIC / HEIF (the iPhone's photos) when pillow-heif is installed
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIC_OK = True
    IMAGE_EXT += ('.heic', '.heif')
except Exception:
    HEIC_OK = False
PHOTO_FILTER = 'Photos (%s)' % ' '.join('*%s *%s' % (e, e.upper()) for e in IMAGE_EXT)
RAW_EXT = ('.srw', '.dng')
FRAMES_PER_ROLL = 36


@dataclass
class Frame:
    path: str
    number: int                  # 1-based frame number within the roll
    taken: datetime = None
    model: str = ''
    film: films.Film = None      # from EXIF (may differ from the roll's code for mystery rolls)


@dataclass
class Roll:
    code: str                    # 'PROV001', or a folder name for loose rolls
    film: films.Film             # the film as the folder says (MYSTERY for mystery rolls)
    path: str
    frames: list = field(default_factory=list)
    raws: int = 0
    own: bool = False             # photos from any camera loaded by hand (the film's colour is applied when developing)
    secret_film: films.Film = None    # the film a mystery roll of own photos was given (kept secret until it is developed)
    name: str = ''                # the roll's name for own photos

    @property
    def mystery(self):
        return self.film is films.MYSTERY

    @property
    def true_film(self):
        """The film the frames were shot on (from EXIF), else the folder's."""
        if self.mystery and self.secret_film is not None:
            return self.secret_film
        for f in self.frames:
            if f.film:
                return f.film
        return self.film if not self.mystery else films.UNKNOWN

    @property
    def first(self):
        ts = [f.taken for f in self.frames if f.taken]
        return min(ts) if ts else None

    @property
    def last(self):
        ts = [f.taken for f in self.frames if f.taken]
        return max(ts) if ts else None

    @property
    def roll_id(self):
        """A library key that stays unique across cards: PROV001_20261108."""
        d = self.first.strftime('%Y%m%d') if self.first else 'undated'
        return '%s_%s' % (re.sub(r'[^A-Za-z0-9_-]', '_', self.code), d)


def read_exif(path):
    """(datetime taken or None, Model string)."""
    try:
        with Image.open(path) as im:
            ex = im.getexif()
            model = str(ex.get(0x110, '') or '').replace('\x00', '').strip()
            raw = ex.get_ifd(0x8769).get(0x9003) or ex.get(0x132)
    except Exception:
        return None, ''
    taken = None
    if raw:
        try:
            taken = datetime.strptime(str(raw).strip('\x00 ')[:19], '%Y:%m:%d %H:%M:%S')
        except ValueError:
            pass
    return taken, model


def _images_under(folder):
    imgs, raws = [], 0
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames.sort()
        for n in sorted(filenames):
            low = n.lower()
            if low.endswith(IMAGE_EXT) and not n.startswith('._'):
                imgs.append(os.path.join(dirpath, n))
            elif low.endswith(RAW_EXT):
                raws += 1
    return imgs, raws


def load_roll(folder, code=None):
    code = code or os.path.basename(os.path.normpath(folder))
    m = ROLL_RE.match(code.upper())
    film = films.from_code(m.group(1)) if m else films.UNKNOWN
    imgs, raws = _images_under(folder)
    roll = Roll(code=code.upper() if m else code, film=film, path=folder, raws=raws)
    for k, p in enumerate(imgs, 1):
        taken, model = read_exif(p)
        roll.frames.append(Frame(path=p, number=k, taken=taken, model=model, film=films.from_model(model)))
    if not m:                                        # a loose folder: take the film from the EXIF if every frame agrees
        names = {f.film.code for f in roll.frames if f.film}
        if len(names) == 1:
            roll.film = films.BY_CODE[names.pop()]
    return roll


def find_roll_folders(path):
    """[(code, folder)] for every roll folder at or under `path` (a card root, FILMS, or a roll)."""
    path = os.path.normpath(path)
    base = os.path.basename(path).upper()
    if ROLL_RE.match(base):
        return [(base, path)]
    candidates = []
    for parent in (os.path.join(path, 'FILMS'), path):
        if os.path.isdir(parent):
            for n in sorted(os.listdir(parent)):
                full = os.path.join(parent, n)
                if os.path.isdir(full) and ROLL_RE.match(n.upper()):
                    candidates.append((n.upper(), full))
            if candidates:
                break
    return candidates


def scan(path):
    """All rolls at `path`. A folder with no roll folders but with JPEGs is one loose roll."""
    rolls = [load_roll(folder, code) for code, folder in find_roll_folders(path)]
    rolls = [r for r in rolls if r.frames]
    if not rolls and os.path.isdir(path):
        r = load_roll(path)
        if r.frames:
            rolls = [r]
    return rolls


def is_plain_folder(rolls):
    """True for a folder of ordinary photos: no FAUXJI roll folder, and no photo that the FAUXJI camera made (no film in its EXIF).
    Such photos have no film look yet, so they are loaded as a roll of 'photos from any camera' where the film is chosen."""
    return bool(rolls) and all(not ROLL_RE.match(r.code.upper()) and not any(f.film for f in r.frames) for r in rolls)


def find_cards():
    """Mounted folders that look like a FAUXJI card (a FILMS folder at the root)."""
    roots = []
    if os.name == 'nt':
        import string
        for letter in string.ascii_uppercase:
            root = '%s:\\' % letter
            try:
                if os.path.isdir(os.path.join(root, 'FILMS')):
                    roots.append(root)
            except OSError:
                pass
    else:
        user = os.environ.get('USER', '')
        for base in ('/media/%s' % user, '/run/media/%s' % user, '/media', '/mnt', '/Volumes'):
            if os.path.isdir(base):
                for n in sorted(os.listdir(base)):
                    full = os.path.join(base, n)
                    if os.path.isdir(os.path.join(full, 'FILMS')):
                        roots.append(full)
    return roots

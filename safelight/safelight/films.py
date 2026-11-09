"""The FAUXJI films: what the camera writes (folder codes, EXIF Model names) and how each behaves in the lab."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Film:
    code: str            # roll folder prefix on the card (PROV001 ...)
    name: str            # as written in EXIF Model after "TL500 "
    kind: str            # 'slide', 'negative', 'cine', 'bw', 'effect'
    grain: float         # base grain strength (fraction of full scale)
    halation: float      # red glow around highlights (0 = none)
    colour: tuple        # cartridge colour for the UI (RGB)
    blurb: str = ''

    @property
    def mono(self):
        return self.kind == 'bw'


FILMS = [
    Film('PROV', 'Provia', 'slide', 0.022, 0.25, (74, 63, 168), 'Natural, balanced slide film.'),
    Film('BLCH', 'Bleach Bypass', 'effect', 0.040, 0.20, (132, 136, 140), 'Washed-out colour, hard contrast.'),
    Film('NOST', 'Nostalgic Neg.', 'negative', 0.034, 0.50, (122, 54, 150), 'Warm amber highlights, 70s print feel.'),
    Film('ASTI', 'Astia', 'slide', 0.020, 0.25, (196, 70, 128), 'Soft slide film, kind to skin.'),
    Film('VELV', 'Velvia', 'slide', 0.018, 0.30, (40, 140, 70), 'Rich, saturated, punchy colour.'),
    Film('REAL', 'Reala Ace', 'negative', 0.028, 0.40, (40, 150, 140), 'True-to-life negative colour.'),
    Film('CCHR', 'Classic Chrome', 'slide', 0.030, 0.30, (150, 126, 70), 'Muted documentary colour.'),
    Film('CNEG', 'Classic Neg.', 'negative', 0.040, 0.50, (40, 140, 70), 'Strong contrast, vintage snapshot colour.'),
    Film('ETRN', 'Eterna', 'cine', 0.030, 0.60, (84, 118, 152), 'Cinema film, wide tonal range.'),
    Film('ACRO', 'Acros', 'bw', 0.030, 0.0, (56, 52, 50), 'Fine-grain black and white.'),
    Film('SEPI', 'Sepia', 'bw', 0.034, 0.0, (164, 116, 70), 'Warm brown single tone.'),
]
MYSTERY = Film('MYST', 'Mystery', 'negative', 0.035, 0.4, (60, 60, 64), 'A surprise film. Develop it to find out.')
UNKNOWN = Film('FILM', 'Unknown film', 'negative', 0.030, 0.3, (90, 90, 96), '')
BY_CODE = {f.code: f for f in FILMS}
BY_CODE[MYSTERY.code] = MYSTERY
BY_NAME = {f.name.lower(): f for f in FILMS}


def from_model(model):
    """The film from an EXIF Model such as 'TL500 Classic Chrome' (None if it is not a FAUXJI film name)."""
    if not model:
        return None
    m = model.replace('\x00', '').strip()
    if m.upper().startswith('TL500 '):
        m = m[6:]
    return BY_NAME.get(m.strip().lower())


def from_code(code):
    return BY_CODE.get((code or '')[:4].upper(), UNKNOWN)

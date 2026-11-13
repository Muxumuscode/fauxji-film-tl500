"""Recipe cards: a named set of lab settings, with a film if the card wants one, and what kind of photography it is for.

Three groups: the lab looks (any film: the old Look menu), built-in cards for kinds of photography (each with its film), and your own
cards, kept as JSON files in <library>/presets/ so they can be shared. A card names its film by code (ACRO), never by name, so renaming
the films (the Android version) does not break saved cards. A FAUXJI roll keeps the film the camera gave it: only a card's lab settings
apply to it.
"""
import re
from dataclasses import dataclass, field

from . import films, lab

FORMAT = 'sajin-genzo-recipe'
KINDS = {
    'any': 'Any photos',
    'portrait': 'Portrait',
    'landscape': 'Landscape',
    'street': 'Street / documentary',
    'night': 'Night & city',
    'snapshot': 'Snapshots',
    'bw': 'Black and white',
}


@dataclass
class Card:
    name: str
    recipe: lab.Recipe = field(default_factory=lab.Recipe)
    film: str = None              # film code (ACRO ...), or None: any film
    kind: str = 'any'
    note: str = ''
    builtin: bool = False

    @property
    def film_obj(self):
        return films.BY_CODE.get(self.film) if self.film else None

    def label(self):
        f = self.film_obj
        return '%s  ·  %s' % (self.name, f.name) if f else self.name

    def matches(self, recipe, film_code=None):
        """Does a lab setting (and the roll's film, when the card has one and a film is known) match this card? The seed is not
        compared."""
        if self.film and film_code and self.film != film_code:
            return False
        a = {k: v for k, v in self.recipe.to_dict().items() if k != 'seed'}
        b = {k: v for k, v in recipe.to_dict().items() if k != 'seed'}
        return a == b

    def to_dict(self):
        r = self.recipe.to_dict()
        r.pop('seed', None)
        return {'format': FORMAT, 'version': 1, 'name': self.name, 'kind': self.kind, 'note': self.note, 'film': self.film, 'recipe': r}

    @classmethod
    def from_dict(cls, d):
        """A card from its JSON (raises ValueError when it is not a recipe card)."""
        if not isinstance(d, dict) or d.get('format') != FORMAT or not str(d.get('name', '')).strip():
            raise ValueError('not a Sajin Genzō recipe card')
        r = lab.Recipe.from_dict(d.get('recipe') or {})
        r.seed = 0
        for attr, options in (('developer', lab.DEVELOPERS), ('process', lab.PROCESSES), ('paper', lab.PAPERS), ('border', lab.BORDERS),
                              ('bw_filter', lab.BW_FILTERS), ('tone', lab.TONES)):
            if getattr(r, attr) not in options:                              # a card from a newer version: fall back, don't fail
                setattr(r, attr, getattr(lab.Recipe(), attr))
        if r.push not in lab.PUSH_PULL:
            r.push = 0
        film = d.get('film')
        film = film.upper() if isinstance(film, str) and film.upper() in films.BY_CODE and film.upper() != films.MYSTERY.code else None
        kind = d.get('kind') if d.get('kind') in KINDS else 'any'
        return cls(str(d['name']).strip()[:60], r, film, kind, str(d.get('note', ''))[:400])


def slug(name):
    """A file name for a card's name."""
    s = re.sub(r'[^A-Za-z0-9]+', '-', name).strip('-').lower()
    return s or 'recipe'


LOOK_NOTES = {
    'Vintage print': 'The default: a roll a few years past its date, printed on faded warm paper with a white border.',
    'Faded 70s snapshot': 'Pulled, long expired film on an instant-print frame: a shoebox of 70s prints.',
    'Clean lab print': 'Fresh film, glossy paper, no border or leaks: the film as it is.',
    'Gritty push': 'Pushed two stops in a high-contrast developer: hard, grainy, black film edge.',
    'Cross-processed': 'Slide film in negative chemistry: wild colour, hard contrast.',
    'Darkroom fibre': 'Sharp developer on warm-tone fibre paper with a black film edge.',
}

# The lab looks (any film), in the order of the old Look menu.
LOOKS = [Card(name, r, None, 'any', LOOK_NOTES.get(name, ''), True) for name, r in lab.PRESETS.items()]

R = lab.Recipe
# Built-in cards for kinds of photography, each with the film it is made for.
BUILTIN = [
    Card('Portrait', R(developer='fine', expired=0, grain=0.9, halation=1.0, leaks=False, paper='matte', border='white', auto_levels=True),
         'ASTI', 'portrait', 'Astia on fine-grain developer and matte paper: soft, kind to skin, no leaks.', True),
    Card('Landscape', R(developer='fine', expired=0, grain=0.9, halation=1.0, leaks=False, paper='glossy', border='none'),
         'VELV', 'landscape', 'Velvia, fine grain, glossy and borderless: rich colour, crisp detail.', True),
    Card('Street', R(push=1, expired=0, grain=1.1, halation=1.0, leaks=False, paper='glossy', border='black'),
         'CCHR', 'street', 'Classic Chrome pushed one stop, black film edge: muted documentary colour with bite.', True),
    Card('Night & city', R(push=1, expired=0, grain=1.2, halation=1.8, leaks=False, paper='glossy', border='none'),
         'ETRN', 'night', 'Eterna pushed one stop with strong halation: cinema glow around the lights.', True),
    Card('Summer snapshot', R(push=-1, expired=8, grain=1.2, halation=1.3, paper='vintage', border='instant'),
         'CNEG', 'snapshot', 'Classic Neg. on long-expired film in an instant-print frame.', True),
    Card('Silver gelatin', R(developer='fine', expired=0, grain=1.1, halation=1.0, leaks=False, paper='neutral', border='black',
                             bw_filter='yellow'),
         'ACRO', 'bw', 'Acros through a yellow filter, fine-grain developer, neutral fibre paper: a classic darkroom print.', True),
    Card('Dramatic sky', R(developer='acutance', expired=0, grain=1.0, halation=1.0, leaks=False, paper='neutral', border='none',
                           bw_filter='red', tone='selenium'),
         'ACRO', 'bw', 'Acros through a red filter (dark skies, bright clouds), sharp developer, selenium toned.', True),
    Card('Gritty B&W street', R(push=2, developer='contrast', expired=0, grain=1.4, halation=1.0, leaks=False, paper='glossy',
                                border='black', bw_filter='orange'),
         'ACRO', 'bw', 'Acros pushed two stops in a high-contrast developer, orange filter: hard and grainy.', True),
    Card('Heirloom', R(expired=10, grain=1.1, halation=1.0, leaks=False, paper='warm', border='white'),
         'SEPI', 'bw', 'Sepia on warm-tone fibre, ten years past its date: a family album print.', True),
]
del R


def find(cards, recipe, film_code=None, prefer=None):
    """The card a lab setting matches (a card with a film only when the film matches too), `prefer` first; None for Custom."""
    if prefer is not None and prefer.matches(recipe, film_code):
        return prefer
    with_film = [c for c in cards if c.film and c.matches(recipe, film_code)]
    if with_film:
        return with_film[0]
    return next((c for c in cards if not c.film and c.matches(recipe, film_code)), None)

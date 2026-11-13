"""The start screen and the Photo Lab: the simple way, like sending a roll to a lab.

Photo Lab is a few steps with no sliders: drop off the photos (or pick a roll to reprint), choose one film for the whole roll (each film
previewed on your own first photo), choose a lab (the lab looks and your own recipes, previewed too), send it to the lab, and collect
the prints (full screen, export the roll as a folder or a zip). The Darkroom (the main window's lab) has every setting; frames given their
own settings there keep them here, unless you ask for the same settings for all.
"""
import os
import shutil
import tempfile
from datetime import datetime

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPushButton, QScrollArea, QSizePolicy, QStackedWidget,
                               QToolButton, QVBoxLayout, QWidget)

from . import films, lab, recipes
from .library import frame_number
from .viewer import Canvas, FrameView, FullScreen, filmstrip

RED = '#e0372f'
STYLE = """
QFrame#drop { border: 2px dashed #5a2b28; border-radius: 14px; background: #181616; }
QFrame#drop[hot="true"] { border-color: %(red)s; background: #201716; }
QLabel#big { font-size: 20pt; font-weight: 600; letter-spacing: 2px; }
QLabel#step { color: #6a655e; font-size: 9pt; letter-spacing: 2px; padding: 4px 10px; }
QLabel#stepon { color: #fff; font-size: 9pt; letter-spacing: 2px; padding: 4px 10px; border-bottom: 2px solid %(red)s; }
QToolButton#choice { background: #1b1a1a; border: 2px solid #2a2828; border-radius: 8px; padding: 6px; color: #e8e4dc; }
QToolButton#choice:hover { border-color: #5a2b28; }
QToolButton#choice:checked { border-color: %(red)s; background: #2a1715; }
QLineEdit { background: #262424; border: 1px solid #383535; border-radius: 4px; padding: 4px 6px; }
QPushButton#mode { font-size: 13pt; padding: 24px; text-align: left; border-radius: 12px; }
""" % {'red': RED}

DROP_SUB = 'a folder, or any photos from any camera or phone (JPEG, PNG, TIFF, WebP).\nThe originals are copied, never changed.'
PREVIEW_RECIPE = dict(expired=0, grain=0, halation=1.0, leaks=False, paper='glossy', border='none', seed=1)
FILM_ICON, LAB_ICON = QSize(232, 158), QSize(232, 176)


def _app():
    from . import app                                                    # (app imports this module: import it when used)
    return app


def _first_line(text, n=70):
    return text if len(text) <= n else text[:n - 1].rsplit(' ', 1)[0] + '…'


class StartPage(QWidget):
    """Two ways in: the Photo Lab (few choices) or the Darkroom (every setting)."""
    chosen = Signal(str)

    def __init__(self, last='photolab'):
        super().__init__()
        self.setStyleSheet(STYLE)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(60, 40, 60, 40)
        lay.addStretch(1)
        t = QLabel('How do you want to develop your photos?')
        t.setObjectName('big')
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        self.banner = QLabel('')
        self.banner.setAlignment(Qt.AlignCenter)
        self.banner.setStyleSheet('color:#f0a49c; padding: 8px;')
        self.banner.setVisible(False)
        lay.addWidget(self.banner)
        lay.addSpacing(20)
        row = QHBoxLayout()
        row.setSpacing(24)
        self.b_lab = QPushButton('PHOTO LAB\n\nDrop off your photos, pick a film and a lab,\nget the prints back. A few choices, no sliders.')
        self.b_dark = QPushButton('DARKROOM\n\nEvery setting, every frame, your call: frame by frame\nsettings, single prints, versions and picks.')
        for b, mode in ((self.b_lab, 'photolab'), (self.b_dark, 'darkroom')):
            b.setObjectName('mode')
            b.setMinimumHeight(170)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.clicked.connect(lambda _=False, mode=mode: self.chosen.emit(mode))
            row.addWidget(b)
        lay.addLayout(row)
        lay.addSpacing(16)
        self.always = QCheckBox('Next time, open straight in the one I choose (the switch at the top changes it at any time)')
        self.always.setObjectName('muted')
        lay.addWidget(self.always, 0, Qt.AlignCenter)
        lay.addStretch(2)
        self.set_last(last)

    def set_last(self, last):
        (self.b_lab if last != 'darkroom' else self.b_dark).setDefault(True)
        for b, mode in ((self.b_lab, 'photolab'), (self.b_dark, 'darkroom')):
            b.setStyleSheet('QPushButton#mode { border: 2px solid %s; }' % (RED if mode == last else '#383535'))

    def set_card(self, n):
        self.banner.setText('FAUXJI card found: %d roll%s. Both ways can develop them.' % (n, '' if n == 1 else 's') if n else '')
        self.banner.setVisible(bool(n))


class PhotoLab(QWidget):
    """Drop off → film → lab → developing → prints. Uses the main window's library and background jobs."""
    open_darkroom = Signal(str, str)        # roll id, development folder

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.setStyleSheet(STYLE)
        self.roll = None                    # the roll being ordered (a card roll, or a library roll)
        self.in_lib = False
        self.pending = []                   # photos chosen, not yet imported
        self.first = None                   # the roll's first photo (float array, small) for the previews
        self.token = None
        self.folder = None                  # the development being collected
        self.fs = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        steps = QHBoxLayout()
        self.step_labels = []
        for k, name in enumerate(('1  DROP OFF', '2  FILM', '3  LAB', '4  PRINTS')):
            lbl = QLabel(name)
            lbl.setObjectName('step')
            steps.addWidget(lbl)
            self.step_labels.append(lbl)
            if k < 3:
                arrow = QLabel('›')
                arrow.setObjectName('step')
                steps.addWidget(arrow)
        steps.addStretch(1)
        lay.addLayout(steps)
        self.pages = QStackedWidget()
        lay.addWidget(self.pages, 1)
        self.pages.addWidget(self._drop_page())
        self.pages.addWidget(self._film_page())
        self.pages.addWidget(self._lab_page())
        self.pages.addWidget(self._developing_page())
        self.pages.addWidget(self._collect_page())
        self.go(0)

    # ------------------------------------------------------------ pages
    def go(self, page):
        self.pages.setCurrentIndex(page)
        step = {0: 0, 1: 1, 2: 2, 3: 3, 4: 3}[page]
        for k, lbl in enumerate(self.step_labels):
            lbl.setObjectName('stepon' if k == step else 'step')
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)
        if page == 0:
            self.refresh_rolls()

    def _buttons(self, back, nxt, nxt_text, red=False):
        row = QHBoxLayout()
        if back:
            b = QPushButton('‹  Back')
            b.clicked.connect(back)
            row.addWidget(b)
        row.addStretch(1)
        n = QPushButton(nxt_text)
        if red:
            n.setObjectName('develop')
        n.setMinimumWidth(220)
        n.clicked.connect(nxt)
        row.addWidget(n)
        return row, n

    def _drop_page(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(16)
        left = QVBoxLayout()
        self.drop = QFrame()
        self.drop.setObjectName('drop')
        dl = QVBoxLayout(self.drop)
        dl.addStretch(1)
        t = QLabel('Drop your photos here')
        t.setObjectName('big')
        t.setAlignment(Qt.AlignCenter)
        dl.addWidget(t)
        self.drop_title = t
        sub = QLabel(DROP_SUB)
        sub.setObjectName('muted')
        sub.setAlignment(Qt.AlignCenter)
        dl.addWidget(sub)
        self.drop_sub = sub
        dl.addSpacing(14)
        br = QHBoxLayout()
        br.addStretch(1)
        b1 = QPushButton('Choose photos…')
        b1.clicked.connect(self.pick_files)
        b2 = QPushButton('Choose a folder…')
        b2.clicked.connect(self.pick_folder)
        br.addWidget(b1)
        br.addWidget(b2)
        br.addStretch(1)
        dl.addLayout(br)
        dl.addStretch(1)
        left.addWidget(self.drop, 1)
        row = QHBoxLayout()
        self.count = QLabel('No photos yet')
        self.count.setObjectName('muted')
        row.addWidget(self.count)
        row.addWidget(QLabel('Roll name'))
        self.name = QLineEdit()
        self.name.setMaximumWidth(260)
        row.addWidget(self.name)
        row.addStretch(1)
        self.btn_drop_next = QPushButton('Next: choose the film  ›')
        self.btn_drop_next.setObjectName('develop')
        self.btn_drop_next.setMinimumWidth(240)
        self.btn_drop_next.setEnabled(False)
        self.btn_drop_next.clicked.connect(self.drop_off)
        row.addWidget(self.btn_drop_next)
        left.addLayout(row)
        lay.addLayout(left, 3)
        right = QVBoxLayout()
        h = QLabel('OR REPRINT A ROLL')
        h.setObjectName('h2')
        right.addWidget(h)
        self.rolls = QListWidget()
        self.rolls.itemDoubleClicked.connect(lambda *_: self.reprint_selected())
        right.addWidget(self.rolls, 1)
        b = QPushButton('Reprint this roll  ›')
        b.clicked.connect(self.reprint_selected)
        right.addWidget(b)
        lay.addLayout(right, 1)
        return w

    def _grid_page(self, title, sub):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        t = QLabel(title)
        t.setObjectName('big')
        lay.addWidget(t)
        s = QLabel(sub)
        s.setObjectName('muted')
        s.setWordWrap(True)
        lay.addWidget(s)
        area = QScrollArea()
        area.setWidgetResizable(True)
        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setSpacing(12)
        area.setWidget(inner)
        lay.addWidget(area, 1)
        return w, lay, grid, s

    def _choice(self, text, icon_size):
        b = QToolButton()
        b.setObjectName('choice')
        b.setCheckable(True)
        b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        b.setIconSize(icon_size)
        b.setText(text)
        b.setMinimumWidth(icon_size.width() + 20)
        blank = QPixmap(icon_size)
        blank.fill(QColor('#232121'))
        b.setIcon(QIcon(blank))
        return b

    def _film_page(self):
        w, lay, grid, self.film_sub = self._grid_page('Choose the film', 'One film for the whole roll, shown on your first photo.')
        self.film_group = QButtonGroup(self)
        self.film_buttons = {}
        for k, f in enumerate(films.FILMS + [films.MYSTERY]):
            b = self._choice('%s\n%s' % (f.name, _first_line(f.blurb, 40)), FILM_ICON)
            self.film_group.addButton(b)
            self.film_buttons[f.code] = b
            grid.addWidget(b, k // 4, k % 4)
        row, _ = self._buttons(lambda: self.go(0), self.film_next, 'Next: choose the lab  ›', red=True)
        lay.addLayout(row)
        return w

    def _lab_page(self):
        w, lay, self.lab_grid, self.lab_sub = self._grid_page('Choose the lab', '')
        self.lab_group = QButtonGroup(self)
        self.lab_buttons = {}
        order = QHBoxLayout()
        order.addWidget(QLabel('Print size'))
        self.size = QComboBox()
        for label, v in (('Full size', 0), ('Large (2400 px)', 2400), ('Web (1600 px)', 1600)):
            self.size.addItem(label, v)
        order.addWidget(self.size)
        order.addSpacing(16)
        order.addWidget(QLabel('Border'))
        self.border = QComboBox()
        self.border.addItem('As the lab prints it', None)
        for k, v in lab.BORDERS.items():
            self.border.addItem(v, k)
        self.border.activated.connect(lambda *_: self.lab_previews())
        order.addWidget(self.border)
        order.addSpacing(16)
        self.scan = QCheckBox('Authentic scan')
        self.scan.setChecked(True)
        self.scan.setToolTip('Softens a sharp phone photo to what film could resolve and rolls the highlights off like a print. '
                             'Untick to keep every pixel.')
        self.scan.toggled.connect(lambda *_: self.lab_previews())
        order.addWidget(self.scan)
        order.addStretch(1)
        lay.addLayout(order)
        self.dark_note = QCheckBox('')
        self.dark_note.setVisible(False)
        lay.addWidget(self.dark_note)
        row, self.btn_send = self._buttons(self.lab_back, self.send, 'Send to the lab', red=True)
        lay.addLayout(row)
        return w

    def _developing_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        self.canvas = Canvas()
        lay.addWidget(self.canvas, 1)
        return w

    def _collect_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        self.collect_title = QLabel('')
        self.collect_title.setStyleSheet('font-size: 13pt; font-weight: 600; letter-spacing: 2px;')
        self.collect_title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        lay.addWidget(self.collect_title)
        top = QHBoxLayout()
        top.addStretch(1)
        for text, fn, tip in (('Export the roll…', self.export_folder, 'Copy every print (and the contact sheet) to a folder'),
                              ('Export as zip…', self.export_zip, 'Every print and the contact sheet in one zip file, to send'),
                              ('Contact sheet', self.show_sheet, 'The whole roll on one sheet'),
                              ('Reprint with another film or lab', self.reprint, 'A new development: the prints you have now are kept'),
                              ('Open in the Darkroom', self.to_darkroom, 'Every setting, frame by frame'),
                              ('New roll', lambda: self.reset(), 'Drop off another roll')):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            top.addWidget(b)
        lay.addLayout(top)
        self.view = FrameView(None, '←  →  print      R / L  rotate      F  full screen')
        self.view.rotate.connect(self.rotate)
        self.view.fullscreen.connect(self.open_fullscreen)
        lay.addWidget(self.view, 1)
        self.strip = filmstrip(QSize(128, 100), '#1b1a1a')
        self.strip.currentItemChanged.connect(lambda *_: self.show_print())
        self.strip.itemDoubleClicked.connect(lambda *_: self.open_fullscreen())
        lay.addWidget(self.strip)
        return w

    # ------------------------------------------------------------ 1  drop off
    def refresh_rolls(self):
        """Rolls to reprint: on the card, and in the library (newest first)."""
        m = self.main
        self.rolls.clear()
        for r in getattr(m, 'source_rolls', []):
            secret = r.mystery and not m.library.revealed(r.roll_id)
            it = QListWidgetItem('FAUXJI card  ·  %s  ·  %s  ·  %d frames' % (r.code, 'Mystery' if secret else r.true_film.name,
                                                                              len(r.frames)))
            it.setData(Qt.UserRole, ('card', r))
            self.rolls.addItem(it)
        for rid in m.library.rolls():
            meta = m.library._read(os.path.join(m.library.roll_dir(rid), 'roll.json')) or {}
            devs = m.library.developments(rid)
            film = films.from_code(meta.get('film_code', rid[:4]))
            shown = 'Mystery' if film is films.MYSTERY and not m.library.revealed(rid) else (
                devs[0][1].get('film') if devs else film.name)
            it = QListWidgetItem('%s  ·  %s  ·  %d frames%s' % (meta.get('name') or meta.get('code', rid), shown, meta.get('frames', 0),
                                                              '  ·  developed' if devs else ''))
            it.setData(Qt.UserRole, ('library', rid))
            self.rolls.addItem(it)

    def pick_files(self):
        start = self.main.settings.value('photos') or os.path.expanduser('~')
        paths, _ = QFileDialog.getOpenFileNames(self, 'Choose photos', start,
                                                'Photos (*.jpg *.jpeg *.png *.tif *.tiff *.webp *.bmp *.JPG *.JPEG *.PNG)')
        if paths:
            self.main.settings.setValue('photos', os.path.dirname(paths[0]))
            self.take_photos(paths)

    def pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, 'Choose a folder of photos', self.main.settings.value('photos') or os.path.expanduser('~'))
        if d:
            self.main.settings.setValue('photos', d)
            self.take_photos(_app().photos_in(d), os.path.basename(os.path.normpath(d)))

    def take_photos(self, paths, name=None):
        """Photos dropped or chosen: shown on step 1 with a name for the roll, ready for Next."""
        from .card import IMAGE_EXT
        self.pending = [p for p in paths if p.lower().endswith(IMAGE_EXT)]
        n = len(self.pending)
        self.count.setText('%d photo%s ready%s' % (n, '' if n == 1 else 's', '  (a long roll)' if n > 36 else '') if n else 'No photos yet')
        self.name.setText(name or datetime.now().strftime('My roll %d %b'))
        self.btn_drop_next.setEnabled(n > 0)
        self.drop_title.setText('%d photo%s ready' % (n, '' if n == 1 else 's') if n else 'Drop your photos here')
        self.drop_sub.setText('Name the roll below, then Next. Drop or choose again to take other photos instead.' if n else DROP_SUB)
        self.go(0)
        if n:
            self.btn_drop_next.setFocus()

    def drop_off(self):
        """Step 1 → 2: the photos are copied into the library as a roll."""
        if not self.pending or self.main.busy:
            return
        paths, name = list(self.pending), self.name.text().strip() or 'My roll'
        self.btn_drop_next.setEnabled(False)
        self.count.setText('Copying the photos…')

        def work(report):
            return self.main.library.import_files(paths, 'CNEG', name, progress=lambda d, n: report((d, n)))

        def done(rid):
            self.pending = []
            self.main.library_dirty = True
            self.main.refresh_library()
            self.take_roll(self.main.library.load_roll(rid), True)

        self.main.run(work, done, progress=lambda p: self.count.setText('Copying the photos…  %d / %d' % p))

    def reprint_selected(self):
        it = self.rolls.currentItem()
        if it is None:
            return
        kind, ref = it.data(Qt.UserRole)
        if kind == 'card':
            if self.main.library.has_roll(ref.roll_id):                  # copied already: the library's copy
                self.take_roll(self.main.library.load_roll(ref.roll_id), True)
            else:
                self.take_roll(ref, False)
        else:
            self.take_roll(self.main.library.load_roll(ref), True)

    def take_roll(self, roll, in_lib):
        """A roll to order prints of: its own photos choose a film first; a FAUXJI roll has its film already."""
        self.roll, self.in_lib = roll, in_lib
        self.first = None
        if roll.own:
            cur = roll.film.code
            self.film_buttons.get(cur, self.film_buttons['CNEG']).setChecked(True)
            self.film_sub.setText('One film for the whole roll "%s", shown on your first photo. Mystery: a surprise film, revealed when '
                                  'the prints are back.' % (roll.name or roll.code))
            self.go(1)
            self.film_previews()
        else:
            self.go_lab()

    def rid(self):
        if self.roll is None:
            return None
        return os.path.basename(os.path.normpath(self.roll.path)) if self.in_lib else self.roll.roll_id

    # ------------------------------------------------------------ 2  film
    def _first(self):
        if self.first is None and self.roll is not None and self.roll.frames:
            self.first = lab.load(self.roll.frames[0].path, 420)
        return self.first

    def film_previews(self):
        token = self.token = object()
        own = self.roll.own

        def work(report):
            a = self._first()
            for f in films.FILMS:
                if a is None:
                    break
                im = lab.to_image(lab.develop(a, f, lab.Recipe(**PREVIEW_RECIPE), frame=2, emulate=own))
                report((token, f.code, im))
            return token

        def ready(item):
            tok, code, im = item
            if tok is self.token:
                self.film_buttons[code].setIcon(QIcon(self._fit(im, FILM_ICON)))

        self.mystery_icon()
        self.main.run(work, lambda _: None, progress=ready)

    def mystery_icon(self):
        pm = QPixmap(FILM_ICON)
        pm.fill(QColor('#232121'))
        from PySide6.QtGui import QFont, QPainter
        p = QPainter(pm)
        f = QFont(self.font())
        f.setPointSize(54)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(RED))
        p.drawText(pm.rect(), Qt.AlignCenter, '?')
        p.end()
        self.film_buttons[films.MYSTERY.code].setIcon(QIcon(pm))

    def _fit(self, im, size):
        im = im.copy()
        im.thumbnail((size.width(), size.height()))
        return _app().to_pixmap(im)

    def chosen_film(self):
        b = self.film_group.checkedButton()
        return next((c for c, x in self.film_buttons.items() if x is b), 'CNEG')

    def film_next(self):
        self.go_lab()

    # ------------------------------------------------------------ 3  lab
    def lab_cards(self):
        """The lab services: the lab looks, and your own recipes (their lab settings: the film is chosen in step 2)."""
        return [('look:' + c.name, c) for c in recipes.LOOKS] + [('my:' + c.name, c) for c in self.main.library.recipe_cards()]

    def go_lab(self):
        for b in self.lab_buttons.values():
            self.lab_group.removeButton(b)
            b.deleteLater()
        self.lab_buttons = {}
        cards = self.lab_cards()
        for k, (key, c) in enumerate(cards):
            mine = key.startswith('my:')
            b = self._choice('%s%s\n%s' % ('★ ' if mine else '', c.name, _first_line(c.note or c.recipe.describe(), 40)), LAB_ICON)
            b.setToolTip(c.note or c.recipe.describe())
            self.lab_group.addButton(b)
            self.lab_buttons[key] = b
            self.lab_grid.addWidget(b, k // 4, k % 4)
        self.lab_buttons['look:Vintage print'].setChecked(True)
        film = self.order_film()
        if self.roll.own:
            what = 'Mystery film (a secret until the prints are back)' if film is films.MYSTERY else film.name
        else:
            what = '%s (the FAUXJI camera chose it)' % ('a mystery film' if self.secret() else self.roll.true_film.name)
        self.lab_sub.setText('How the lab develops and prints "%s" on %s. Shown on your first photo.' % (
            self.roll.name or self.roll.code, what))
        own = self.main.library.frame_settings(self.rid())
        n = len(own)
        self.dark_note.setVisible(bool(n))
        self.dark_note.setChecked(False)
        self.dark_note.setText('%d frame%s keep%s the settings given in the Darkroom.  Tick to print every frame the same.'
                               % (n, '' if n == 1 else 's', 's' if n == 1 else ''))
        self.go(2)
        self.lab_previews()

    def secret(self):
        return self.roll is not None and self.roll.mystery and not self.main.library.revealed(self.rid())

    def order_film(self):
        """The film the order is printed on."""
        if self.roll.own:
            return films.BY_CODE.get(self.chosen_film(), films.MYSTERY)
        return self.roll.true_film

    def lab_back(self):
        if self.roll is not None and self.roll.own:
            self.go(1)
        else:
            self.go(0)

    def lab_previews(self):
        token = self.token = object()
        film = self.order_film()
        if film is films.MYSTERY or self.secret():
            film = films.BY_CODE['CNEG']                                  # a neutral film: the previews keep the secret
        own = self.roll.own
        border = self.border.currentData()
        cards = self.lab_cards()

        def work(report):
            a = self._first()
            for key, c in cards:
                if a is None:
                    break
                r = lab.Recipe.from_dict(c.recipe.to_dict())
                r.seed = 3
                r.authentic = self.scan.isChecked()
                if border:
                    r.border = border
                im = lab.to_image(lab.develop(a, film, r, frame=2, emulate=own))
                report((token, key, lab.bordered(im, r.border, lab.frame_caption(film, 2, None))))
            return token

        def ready(item):
            tok, key, im = item
            if tok is self.token and key in self.lab_buttons:
                self.lab_buttons[key].setIcon(QIcon(self._fit(im, LAB_ICON)))

        self.main.run(work, lambda _: None, progress=ready)

    def chosen_card(self):
        b = self.lab_group.checkedButton()
        key = next((k for k, x in self.lab_buttons.items() if x is b), 'look:Vintage print')
        return dict(self.lab_cards()).get(key, recipes.LOOKS[0])

    # ------------------------------------------------------------ 4  the lab
    def send(self):
        """Develop the roll: the film (own photos), the lab's recipe, the order's size and border."""
        if self.roll is None or self.main.busy:
            return
        m, roll, in_lib, rid = self.main, self.roll, self.in_lib, self.rid()
        c = self.chosen_card()
        recipe = lab.Recipe.from_dict(c.recipe.to_dict())
        recipe.seed = 0
        recipe.authentic = self.scan.isChecked()
        if self.border.currentData():
            recipe.border = self.border.currentData()
        if self.dark_note.isVisible() and self.dark_note.isChecked():
            m.library.set_frame_settings(rid, list(m.library.frame_settings(rid)), None)
        if roll.own:
            code = self.chosen_film()
            if code != roll.film.code or code == films.MYSTERY.code:
                m.library.set_film(rid, code)
            roll = m.library.load_roll(rid)
        # a mystery film chosen here is a surprise each time; a FAUXJI mystery roll only until its first print
        was_secret = roll.mystery and (roll.own or not m.library.revealed(rid))
        max_side = self.size.currentData() or None
        m.library_dirty = True
        m.busy = True
        m._update_buttons()
        self.go(3)
        film = self.order_film()
        self.canvas.start_develop('AT THE LAB  ·  %s  ·  %s' % ((roll.name or roll.code).upper(), c.name.upper()),
                                  m.dev_mood(recipe, films.UNKNOWN if film is films.MYSTERY or self.secret() else film))

        def work(report):
            libroll = roll if in_lib else m.library.import_roll(roll, progress=lambda d, n: report(('load', d, n, None)))
            report(('load', 0, 0, None))
            return m.library.develop(libroll, recipe, progress=lambda d, n, s_, t: report(('dev', d, n, t)), max_side=max_side,
                                     look=c.name), libroll

        def prog(p):
            kind, d, n, t = p
            if kind == 'load':
                self.canvas.dev_note('Loading the film into the tank…  %d / %d' % (d, n) if n else 'Developer in, tank closed…')
            else:
                self.canvas.dev_feed(_app().to_pixmap(t), d, n)

        def done(res):
            (folder, labcard), libroll = res

            def after():
                m.busy = False
                m._update_buttons()
                self.roll, self.in_lib = libroll, True
                m.refresh_library()
                self.collect(folder)
                if was_secret:
                    _app().Reveal(self, films.BY_NAME.get(labcard['film'].lower(), films.UNKNOWN)).exec()
                self.want_fs = True                                    # the envelope opens: the prints, big (once one is in)
                self.show_print()

            self.canvas.dev_finish(after, 'YOUR PRINTS ARE BACK  ·  %d PRINTS' % len(labcard['frames']))

        m.run(work, done, progress=prog)

    def failed(self):
        """A job failed (the main window says what): the animation stops and the step before comes back."""
        self.canvas.dev_cancel()
        self.btn_drop_next.setEnabled(bool(self.pending))
        if self.pending:
            self.count.setText('%d photos ready' % len(self.pending))
        if self.pages.currentIndex() == 3:
            self.go(2 if self.roll is not None else 0)

    # ------------------------------------------------------------ 5  collect
    def collect(self, folder):
        self.folder = folder
        lc = self.main.library._read(os.path.join(folder, 'labcard.json')) or {}
        self.labcard = lc
        self.collect_title.setText('YOUR PRINTS ARE BACK  ·  %s  ·  %s  ·  %s' % (
            (self.roll.name or self.roll.code), lc.get('film', ''), lc.get('look') or lc.get('description', '')))
        self.pix = {}
        self.strip.blockSignals(True)
        self.strip.clear()
        self.strip.blockSignals(False)
        blank = QPixmap(128, 100)
        blank.fill(QColor('#232121'))
        paths = [os.path.join(folder, fr['file']) for fr in lc.get('frames', [])]
        for p in paths:
            it = QListWidgetItem(QIcon(blank), '')
            it.setData(Qt.UserRole, p)
            self.strip.addItem(it)

        def work(report):
            for k, p in enumerate(paths):
                report((k, self.main._print_thumb(p)))

        def ready(item):
            k, im = item
            if k < self.strip.count():
                self.strip.item(k).setIcon(_app().strip_icon(_app().to_pixmap(im)))

        self.main.run(work, lambda _: None, progress=ready)
        self.go(4)
        if self.strip.count():
            self.strip.setCurrentRow(0)
        self.strip.setFocus()                                           # ← → R L F work at once

    def current(self):
        it = self.strip.currentItem()
        return it.data(Qt.UserRole) if it is not None else None

    def show_print(self):
        p = self.current()
        if p is None:
            return
        cap = '%s  ·  print %d / %d' % (self.roll.name or self.roll.code, self.strip.currentRow() + 1, self.strip.count())
        if p in self.pix:
            self.view.show_picture(self.pix[p], 0, cap)
            if getattr(self, 'want_fs', False):
                self.want_fs = False
                QTimer.singleShot(0, self.open_fullscreen)
            return
        self.view.show_picture(None, 0, cap, loading='loading…')

        def work(report):
            from PIL import Image
            with Image.open(p) as im:
                im.draft('RGB', (2000, 2000))
                return p, im.convert('RGB')

        def done(res):
            path, im = res
            self.pix[path] = _app().to_pixmap(im)
            if self.current() == path:
                self.show_print()

        self.main.run(work, done)

    def step(self, d):
        if self.strip.count():
            self.strip.setCurrentRow(max(0, min(self.strip.count() - 1, self.strip.currentRow() + d)))

    def rotate(self, delta):
        """Turn a print (the file is rewritten, and the contact sheet; the frame's rotation is remembered for the next order)."""
        p = self.current()
        if p is None or getattr(self, 'rotating', False):
            return
        self.rotating = True
        self.view.set_rotation(delta % 360, delta)

        def work(report):
            self.main.library.rotate_print_path(p, delta)
            return self.main._print_thumb(p)

        def done(thumb):
            self.rotating = False
            self.pix.pop(p, None)
            it = self.strip.currentItem()
            if it is not None and it.data(Qt.UserRole) == p:
                it.setIcon(_app().strip_icon(_app().to_pixmap(thumb)))
            self.show_print()

        self.main.run(work, done)

    def keyPressEvent(self, e):
        if self.pages.currentIndex() == 4:
            k = e.key()
            if k in (Qt.Key_Left, Qt.Key_Right):
                return self.step(1 if k == Qt.Key_Right else -1)
            if k in (Qt.Key_R, Qt.Key_L):
                return self.rotate(90 if k == Qt.Key_R else -90)
            if k == Qt.Key_F:
                return self.open_fullscreen()
        super().keyPressEvent(e)

    def open_fullscreen(self):
        if self.pages.currentIndex() != 4 or self.view.canvas.pm is None:
            return
        fs = FullScreen(self.main, self.view, self.info,
                        'Esc  close      ←  →  print      R / L  rotate      hold Space  original      I  info')
        fs.step.connect(self.step)
        fs.rotate.connect(self.rotate)
        fs.original.connect(self.original)
        self.fs = fs
        fs.showFullScreen()
        fs.activateWindow()
        fs.setFocus()

    def info(self):
        p = self.current()
        if not p:
            return ''
        lc, fr = self.main.library.print_info(p)
        lines = ['%s  ·  print of frame %s' % (fr.get('film') or lc.get('film', ''), fr.get('frame', '?')),
                 'Lab: %s  (%s)' % (lc.get('look') or '', fr.get('description') or lc.get('description', '')),
                 'Developed %s' % lc.get('developed', '').replace('T', '  ')]
        if fr.get('taken'):
            lines.append('Taken %s' % fr['taken'].replace('T', '  '))
        lines.append('From %s' % fr.get('original', ''))
        return '\n'.join(lines)

    def original(self, on):
        """Space held in full screen: the photo as it was before the lab."""
        fs, p = self.fs, self.current()
        if not on or fs is None or not p:
            return
        n = frame_number(p)
        f = next((x for x in self.roll.frames if x.number == n), None)
        if f is None:
            return
        turn = self.main.library.rotations(self.rid()).get(n, 0)

        def work(report):
            return lab.to_image(lab.load(f.path, 2400))

        def done(im):
            if self.fs is fs and fs.holding:
                fs.show_original(_app().to_pixmap(im), turn)

        self.main.run(work, done)

    def show_sheet(self):
        p = os.path.join(self.folder or '', 'contact_sheet.jpg')
        if self.folder and os.path.exists(p):
            self.view.show_picture(QPixmap(p), 0, '%s  ·  contact sheet' % (self.roll.name or self.roll.code))

    def _export_name(self):
        lc = self.labcard
        return '%s_%s_%s' % (recipes.slug(self.roll.name or self.roll.code), recipes.slug(lc.get('film', '')),
                             os.path.basename(self.folder).replace('develop-', ''))

    def export_folder(self):
        if not self.folder:
            return
        d = QFileDialog.getExistingDirectory(self, 'Export the roll to', self.main.export_dir())
        if not d:
            return
        self.main.settings.setValue('export', d)
        dst = os.path.join(d, self._export_name())
        os.makedirs(dst, exist_ok=True)
        for n in os.listdir(self.folder):
            if n.lower().endswith('.jpg'):
                shutil.copy2(os.path.join(self.folder, n), dst)
        self.main.notify('Exported to %s' % dst, 8000)
        QDesktopServices.openUrl(QUrl.fromLocalFile(dst))

    def export_zip(self):
        if not self.folder:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Export as zip', os.path.join(self.main.export_dir(), self._export_name() + '.zip'),
                                              'Zip (*.zip)')
        if not path:
            return
        self.main.settings.setValue('export', os.path.dirname(path))
        tmp = tempfile.mkdtemp(prefix='sajingenzo-')
        try:
            for n in os.listdir(self.folder):
                if n.lower().endswith('.jpg'):
                    shutil.copy2(os.path.join(self.folder, n), tmp)
            made = shutil.make_archive(path[:-4] if path.lower().endswith('.zip') else path, 'zip', tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.main.notify('Exported %s' % made, 8000)

    def reprint(self):
        """Another film or lab for the same roll: a new development, the prints you have now are kept."""
        if self.roll is not None:
            self.take_roll(self.main.library.load_roll(self.rid()), True)

    def to_darkroom(self):
        if self.roll is not None:
            self.open_darkroom.emit(self.rid(), self.folder or '')

    def reset(self):
        self.roll, self.folder, self.pending = None, None, []
        self.take_photos([])

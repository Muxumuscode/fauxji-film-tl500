"""Sajin Genzō's window: rolls on the left, the big view with the filmstrip (light table, prints) and the contact sheet in the middle,
the lab on the right. Developing plays in the big view."""
import os
import random
import shutil
import sys
import traceback
from datetime import datetime

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, QSettings, QSize, Qt, QThreadPool, QTimer, Signal, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QImage, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (QSizePolicy, QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
                               QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton,
                               QScrollArea, QSlider, QSpinBox, QSplitter, QTabWidget, QTableWidget, QTableWidgetItem, QTreeWidget,
                               QTextBrowser, QTreeWidgetItem, QVBoxLayout, QWidget, QLineEdit)

from . import APP_NAME, APP_NATIVE, __version__, card, films, lab
from .library import Library
from .viewer import FrameView, filmstrip

RED = '#e0372f'
STYLE = """
* { font-family: 'Segoe UI', 'Bahnschrift', 'Noto Sans', 'DejaVu Sans', sans-serif; font-size: 10pt; }
QMainWindow, QWidget { background: #141313; color: #e8e4dc; }
QFrame#panel, QTreeWidget, QListWidget, QTableWidget, QScrollArea { background: #1b1a1a; border: 1px solid #2a2828; border-radius: 6px; }
QLabel, QCheckBox { background: transparent; }
QLabel#h1 { font-size: 15pt; font-weight: 600; letter-spacing: 3px; }
QLabel#h2 { color: #b5aea3; font-size: 9pt; letter-spacing: 2px; }
QLabel#muted { color: #8d877d; }
QPushButton, QToolButton { background: #262424; border: 1px solid #383535; border-radius: 5px; padding: 6px 12px; color: #e8e4dc; }
QPushButton:hover, QToolButton:hover { border-color: %(red)s; }
QPushButton:disabled { color: #6a655e; border-color: #2a2828; }
QPushButton#develop { background: %(red)s; border: none; font-weight: 600; font-size: 11pt; letter-spacing: 2px; padding: 10px; color: #fff; }
QPushButton#develop:hover { background: #f04a40; }
QPushButton#develop:disabled { background: #4a2725; color: #a08c88; }
QComboBox, QSpinBox { background: #262424; border: 1px solid #383535; border-radius: 4px; padding: 4px 6px; }
QComboBox QAbstractItemView { background: #222020; selection-background-color: %(red)s; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: transparent; color: #8d877d; padding: 8px 16px; letter-spacing: 1px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #f2eee6; border-bottom: 2px solid %(red)s; }
QProgressBar { background: #221f1f; border: none; border-radius: 4px; height: 8px; text-align: center; color: transparent; }
QProgressBar::chunk { background: %(red)s; border-radius: 4px; }
QSlider::groove:horizontal { height: 4px; background: #333; border-radius: 2px; }
QSlider::handle:horizontal { background: %(red)s; width: 14px; margin: -6px 0; border-radius: 7px; }
QTreeWidget::item { padding: 6px 2px; }
QTreeWidget::item:selected, QListWidget::item:selected { background: #3a1d1b; color: #fff; }
QHeaderView::section { background: #1b1a1a; color: #8d877d; border: none; padding: 4px; }
QCheckBox::indicator { width: 14px; height: 14px; }
QPushButton#seg { border-radius: 0; padding: 6px 14px; letter-spacing: 1px; }
QPushButton#seg:checked { background: #3a1d1b; border-color: %(red)s; color: #fff; }
""" % {'red': RED}


# ---------------------------------------------------------------- what every setting does

TIPS = {
    'look': 'Ready-made recipes. Vintage print (the default): a roll a few years past its date, printed on faded warm paper with a white '
            'border: old-school prints. Faded 70s snapshot, Clean lab print, Gritty push, Cross-processed, Darkroom fibre. Change any '
            'setting and the look becomes Custom.',
    'push': 'How long the film stays in the developer.\nBox speed: as the film was meant to be developed.\n'
            'Push +1 / +2: longer, as if you had shot at a higher ISO and the lab compensated: brighter, harder contrast, more grain.\n'
            'Pull -1: shorter: softer, flatter, finer grain.',
    'developer': 'The developer chemistry.\nStandard: neutral.\nFine grain: smaller, smoother grain, a touch softer.\n'
                 'High acutance: crisper edges (adjacency effect), slightly more grain.\nHigh contrast: deeper blacks, brighter whites.',
    'process': 'Normal: the film in its own chemistry.\nCross-processed: slide film developed as a negative (or the other way round): '
               'hard contrast, yellow-green highlights, cyan shadows, strong colour.\nBleach bypass: the bleach step is skipped, so silver '
               'stays in the film: washed-out colour, hard contrast, a gritty cinema look.',
    'expired': 'How many years past its date the film is.\nOld film has fogged (grey) blacks, less contrast, more grain and a colour drift '
               'that is different for each roll.\n0 = fresh.',
    'grain': 'How much grain, compared with the film\'s own (100 % in the middle). Each film has its own grain: Velvia and Astia are fine, '
             'Classic Neg. and Bleach Bypass are coarse. Push and expired film add more.',
    'halation': 'The red-orange glow around bright lights (light that bounces back through the film base). 100 % = the film\'s own amount; '
                'ACROS and Sepia have none (black-and-white film has an anti-halation layer).',
    'leaks': 'Light leaks: the first frame of a roll was wound on in daylight, so it catches a warm glow from an edge; later frames '
             'only now and then (about 1 in 20). Each roll gets its own leaks.',
    'paper': 'What the prints are made on.\nVintage print (default): an old minilab print: colour a little faded, blacks lifted, highlights '
             'warm, a soft fall-off at the edges.\nGlossy: deep blacks.\nMatte: slightly lifted, softer blacks.\nWarm-tone fibre: a warm cream '
             'tint, like a darkroom fibre print.',
    'border': 'The border around each print.\nWhite: a plain white border.\nBlack film-holder edge: the rough black edge of a negative '
              'carrier filed out for full-frame prints, with the film, frame and date in orange.\nInstant-print frame: a wide bottom, '
              'with the caption.',
    'auto': 'A gentle lab correction: stretches the darkest and brightest tones a little so flat frames get some snap. Leave it off for '
            'the film\'s own look.',
    'size': 'The size of the prints: full (3648 px, the camera\'s own size, about 3 s a frame), large (2400 px) or web (1600 px, fastest).',
    'surprise': 'Let the lab pick every setting at random.',
    'reset': 'Back to the default look: Vintage print.',
    'develop': 'Develop every frame of the roll with these settings: the roll is copied into the library first (the originals are never '
               'changed), then the prints and a contact sheet are made. You can develop a roll as often as you like; each development '
               'is kept.',
}

GUIDE = """<h2>%(name)s &nbsp;<span style='color:#8d877d'>%(native)s</span></h2>
<p><i>사진 (sajin)</i> is Korean for <b>photo</b>, <i>現像 (genzō)</i> is Japanese for <b>developing</b>: a Samsung camera with Fuji film
looks, and this is its photo lab.</p>
<h3>How it works</h3>
<ol>
<li><b>Open card</b> (or <b>Open folder…</b>): every roll the FAUXJI film camera shot is in the card's <code>FILMS</code> folder.
Photos from any other camera: <b>Load photos…</b> (below).</li>
<li>Pick a roll: its negatives run along the bottom. Click one and it fills the big view. Above the picture, switch between
<b>NEGATIVE</b>, <b>ORIGINAL</b> and <b>PRINT PREVIEW</b> (that frame printed with the lab settings; it follows every change), and
<b>rotate</b> it.</li>
<li><b>Develop roll</b>: the big view becomes the darkroom: under the red safelight each print comes up in the developer tray, goes
through the stop bath, fixer and wash, and is hung on the drying line.</li>
<li>The <b>prints</b> and the <b>contact sheet</b> appear in their tabs. The prints tab works like the light table: click a print to see it
big, rotate it with the buttons or R / L;
<b>Export prints…</b> copies them anywhere.</li>
</ol>
<h3>The lab settings</h3>
<table cellpadding=4>
<tr><td valign=top><b>Look</b></td><td>%(look)s</td></tr>
<tr><td valign=top><b>Development</b></td><td>%(push)s</td></tr>
<tr><td valign=top><b>Developer</b></td><td>%(developer)s</td></tr>
<tr><td valign=top><b>Process</b></td><td>%(process)s</td></tr>
<tr><td valign=top><b>Expired</b></td><td>%(expired)s</td></tr>
<tr><td valign=top><b>Grain</b></td><td>%(grain)s</td></tr>
<tr><td valign=top><b>Halation</b></td><td>%(halation)s</td></tr>
<tr><td valign=top><b>Light leaks</b></td><td>%(leaks)s</td></tr>
<tr><td valign=top><b>Paper</b></td><td>%(paper)s</td></tr>
<tr><td valign=top><b>Border</b></td><td>%(border)s</td></tr>
<tr><td valign=top><b>Lab correction</b></td><td>%(auto)s</td></tr>
<tr><td valign=top><b>Print size</b></td><td>%(size)s</td></tr>
<tr><td valign=top><b>Surprise me</b></td><td>%(surprise)s</td></tr>
</table>
<h3>Photos from any camera</h3>
<p><b>Load photos…</b> makes a roll of any photos (JPEG, PNG, TIFF, WebP) from any camera or phone: choose the photos or a folder, name
the roll and pick the film it is developed as, or <b>Mystery</b> for a secret one. These photos don't carry a film look yet (the FAUXJI
camera puts it in the photo when it is taken), so the lab gives them the film's colour first, then develops them exactly like a roll
from the film camera. The <b>Film</b> menu at the top of the lab changes the film of such a roll at any time.</p>
<h3>Rotating</h3>
<p>The TL500 has no orientation sensor, so upright photos come out lying on their side. Turn a frame on the light table (right-click,
or <b>R</b> / <b>L</b> in the large view) and it stays turned: on the light table, in the test strip, in every development and on the
contact sheet. Prints that are already developed can be turned the same way.</p>
<h3>Mystery rolls</h3>
<p>A <b>MYST</b> roll keeps its film a secret: no name on the roll, a neutral negative on the light table. Develop it to find out.</p>
<h3>Where things go</h3>
<p>The library (<b>Library folder…</b>) holds a copy of each roll (<code>originals</code>) and one folder per development with the prints,
the contact sheet and a lab card of what was done. <b>Lab log</b> lists every development.</p>
<h3>Keys</h3>
<p>Large view: <b>← →</b> previous / next, <b>R</b> rotate right, <b>L</b> rotate left, <b>Space</b> negative / print, <b>Esc</b> close.</p>
"""


def guide_html():
    d = {k: v.replace('\n', '<br>') for k, v in TIPS.items()}
    d.update(name=APP_NAME, native=APP_NATIVE)
    return GUIDE % d


class Guide(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle('Lab guide')
        self.resize(760, 720)
        lay = QVBoxLayout(self)
        t = QTextBrowser()
        t.setHtml(guide_html())
        t.setStyleSheet('QTextBrowser { background:#1b1a1a; border:none; padding:10px; font-size:10.5pt; }')
        lay.addWidget(t)


# ---------------------------------------------------------------- background work

class _Signals(QObject):
    progress = Signal(object)
    done = Signal(object)
    failed = Signal(str)


class Job(QRunnable):
    """Runs fn(report) on the thread pool; report(x) emits progress(x) on the GUI thread."""

    def __init__(self, fn):
        super().__init__()
        self.fn, self.signals, self.cancelled = fn, _Signals(), False

    def run(self):
        try:
            self.signals.done.emit(self.fn(self.signals.progress.emit))
        except Exception:
            self.signals.failed.emit(traceback.format_exc())


def to_pixmap(im):
    im = im.convert('RGB')
    data = im.tobytes('raw', 'RGB')
    q = QImage(data, im.width, im.height, im.width * 3, QImage.Format_RGB888)
    return QPixmap.fromImage(q.copy())


def app_icon():
    """The film-cartridge icon (safelight/icon.py) at every size the window and the taskbar ask for."""
    from . import icon
    ic = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(to_pixmap_rgba(icon.image(size)))
    return ic


def to_pixmap_rgba(im):
    im = im.convert('RGBA')
    q = QImage(im.tobytes('raw', 'RGBA'), im.width, im.height, im.width * 4, QImage.Format_RGBA8888)
    return QPixmap.fromImage(q.copy())


# ---------------------------------------------------------------- small widgets

class LoadPhotos(QDialog):
    """Photos from any camera: pick files or a folder, name the roll, choose the film it is developed as (or a mystery film)."""

    def __init__(self, parent, start_dir):
        super().__init__(parent)
        self.setWindowTitle('Load photos from any camera')
        self.setMinimumWidth(520)
        self.paths, self.start_dir = [], start_dir
        lay = QVBoxLayout(self)
        intro = QLabel('Any photos (JPEG, PNG, TIFF, WebP) from any camera or phone become a roll: the lab gives them the film\'s colour '
                       'and develops them like the FAUXJI rolls. The originals are copied, never changed.')
        intro.setWordWrap(True)
        intro.setObjectName('muted')
        lay.addWidget(intro)
        row = QHBoxLayout()
        b1 = QPushButton('Choose photos…')
        b1.clicked.connect(self.pick_files)
        b2 = QPushButton('Choose a folder…')
        b2.clicked.connect(self.pick_folder)
        row.addWidget(b1)
        row.addWidget(b2)
        self.count = QLabel('No photos chosen yet')
        self.count.setObjectName('muted')
        row.addWidget(self.count, 1)
        lay.addLayout(row)
        form = QFormLayout()
        self.name = QLineEdit(datetime.now().strftime('My roll %d %b'))
        self.film = QComboBox()
        for f in films.FILMS:
            self.film.addItem('%s  ·  %s' % (f.name, f.blurb), f.code)
        self.film.addItem('Mystery  ·  a surprise film, revealed when you develop it', films.MYSTERY.code)
        self.film.setCurrentIndex(self.film.findData('CNEG'))
        form.addRow('Roll name', self.name)
        form.addRow('Film', self.film)
        lay.addLayout(form)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton('Cancel')
        cancel.clicked.connect(self.reject)
        self.ok = QPushButton('Load the roll')
        self.ok.setObjectName('develop')
        self.ok.setEnabled(False)
        self.ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(self.ok)
        lay.addLayout(row)

    def _set(self, paths):
        self.paths = [p for p in paths if p.lower().endswith(card.IMAGE_EXT)]
        n = len(self.paths)
        self.count.setText('%d photo%s chosen%s' % (n, '' if n == 1 else 's', '  (more than 36: a long roll)' if n > 36 else ''))
        self.ok.setEnabled(n > 0)

    def pick_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Choose photos', self.start_dir,
                                                'Photos (*.jpg *.jpeg *.png *.tif *.tiff *.webp *.bmp *.JPG *.JPEG *.PNG)')
        if paths:
            self.start_dir = os.path.dirname(paths[0])
            self._set(paths)

    def pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, 'Choose a folder of photos', self.start_dir)
        if d:
            self.start_dir = d
            paths = []
            for dirpath, dirnames, filenames in os.walk(d):
                dirnames.sort()
                paths += [os.path.join(dirpath, n) for n in sorted(filenames)]
            self._set(paths)
            if self.name.text().startswith('My roll'):
                self.name.setText(os.path.basename(os.path.normpath(d)))


class Reveal(QDialog):
    """The mystery roll's film, revealed after developing."""

    def __init__(self, parent, film):
        super().__init__(parent)
        self.setWindowTitle('Mystery roll')
        self.setFixedSize(420, 260)
        lay = QVBoxLayout(self)
        a = QLabel('YOUR MYSTERY ROLL WAS')
        a.setObjectName('h2')
        a.setAlignment(Qt.AlignCenter)
        b = QLabel(film.name.upper())
        b.setAlignment(Qt.AlignCenter)
        b.setStyleSheet('font-size: 26pt; font-weight: 700; letter-spacing: 3px; color: rgb%s' % (tuple(min(255, c + 60) for c in film.colour),))
        c = QLabel(film.blurb)
        c.setObjectName('muted')
        c.setAlignment(Qt.AlignCenter)
        ok = QPushButton('See the prints')
        ok.clicked.connect(self.accept)
        for w in (a, b, c):
            lay.addWidget(w)
        lay.addWidget(ok)


class LabLog(QDialog):
    def __init__(self, parent, library):
        super().__init__(parent)
        self.setWindowTitle('Lab log')
        self.resize(760, 460)
        lay = QVBoxLayout(self)
        st = library.stats()
        head = QLabel('%d developments  ·  %d frames printed  ·  favourite film: %s' % (st['developments'], st['frames'], st['favourite'] or '—'))
        head.setObjectName('h2')
        lay.addWidget(head)
        log = list(reversed(library.lablog()))
        t = QTableWidget(len(log), 5)
        t.setHorizontalHeaderLabels(['Developed', 'Roll', 'Film', 'Frames', 'Lab'])
        for r, e in enumerate(log):
            for c, v in enumerate((e['developed'].replace('T', ' '), e['roll'], e['film'] if not e.get('mystery') else e['film'] + ' (mystery)',
                                   str(e.get('frames', '')), e['description'])):
                t.setItem(r, c, QTableWidgetItem(v))
        t.horizontalHeader().setStretchLastSection(True)
        t.verticalHeader().setVisible(False)
        lay.addWidget(t)


# ---------------------------------------------------------------- the window

class MainWindow(QMainWindow):
    def __init__(self, settings=None, autoload=True):
        super().__init__()
        self.settings = settings or QSettings('FAUXJI', 'SajinGenzo')
        self.library = Library(os.environ.get('SAFELIGHT_LIBRARY') or self.settings.value('library') or None)
        self.pool = QThreadPool.globalInstance()
        self.source_rolls = []          # rolls on the opened card / folder
        self.roll = None                # the selected roll (card or library)
        self.roll_in_library = False
        self.neg_cache = {}             # (path, film code) -> the small negative, unrotated
        self.render_cache = {}          # (path, mode, recipe) -> the big picture, unrotated (PIL)
        self.render_order = []
        self.arrays = {}                # path -> the 1600 px float image, for quick re-renders
        self.print_pending = {}         # print path -> rotation shown on screen but not yet written to the file
        self.print_pix = {}             # print path -> the big picture (QPixmap)
        self._render_token = None
        self.rot_timer = QTimer(self)
        self.rot_timer.setSingleShot(True)
        self.rot_timer.setInterval(700)
        self.rot_timer.timeout.connect(self.write_print_rotations)
        self.busy = False
        self.jobs = []
        self.setWindowTitle('%s %s' % (APP_NAME, __version__))
        self.setWindowIcon(app_icon())
        self.resize(1400, 880)
        self._build()
        self.refresh_library()
        if autoload:                                                    # a card in the reader, else the folder opened last time
            last = self.settings.value('source')
            cards = card.find_cards()
            if cards:
                QTimer.singleShot(200, lambda: self.open_source(cards[0]))
            elif last and os.path.isdir(last):
                QTimer.singleShot(200, lambda: self.open_source(last))

    # ------------------------------------------------------------ layout
    def _build(self):
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(12, 8, 12, 8)
        outer.setSpacing(6)

        top = QHBoxLayout()
        logo = QLabel('●  SAJIN GENZŌ')
        logo.setObjectName('h1')
        logo.setStyleSheet('color:%s' % RED)
        top.addWidget(logo)
        native = QLabel(APP_NATIVE)
        native.setStyleSheet('color:#b5aea3; font-size:13pt; font-family: "Malgun Gothic", "Yu Gothic", "Noto Sans CJK KR", sans-serif;')
        native.setToolTip('사진 (sajin, Korean): photo  ·  現像 (genzō, Japanese): developing')
        top.addWidget(native)
        sub = QLabel('  photo lab for film rolls and any photos')
        sub.setObjectName('muted')
        top.addWidget(sub)
        top.addStretch(1)
        self.note = QLabel('')
        self.note.setStyleSheet('color:#d9a19a; padding-right:10px')
        self.note.setMaximumWidth(460)
        self.note.setMinimumWidth(0)
        self.note.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        top.addWidget(self.note)
        self.note_timer = QTimer(self)
        self.note_timer.setSingleShot(True)
        self.note_timer.timeout.connect(lambda: self.note.setText(''))
        self.btn_card = QPushButton('Open card')
        self.btn_card.clicked.connect(self.pick_card)
        self.btn_folder = QPushButton('Open folder…')
        self.btn_folder.clicked.connect(self.pick_folder)
        self.btn_photos = QPushButton('Load photos…')
        self.btn_photos.clicked.connect(self.load_photos)
        self.btn_photos.setToolTip('Photos from any camera or phone: make a roll of them and develop it on a film of your choice')
        self.btn_log = QPushButton('Lab log')
        self.btn_log.clicked.connect(lambda: LabLog(self, self.library).exec())
        self.btn_lib = QPushButton('Library folder…')
        self.btn_lib.clicked.connect(self.pick_library)
        self.btn_guide = QPushButton('?  Lab guide')
        self.btn_guide.clicked.connect(lambda: Guide(self).exec())
        self.btn_card.setToolTip('FAUXJI film camera: open the card in the card reader (its FILMS folder)')
        self.btn_folder.setToolTip('FAUXJI film camera: open a copy of a card, a FILMS folder or one roll')
        self.btn_log.setToolTip('Every development so far, and your favourite film')
        self.btn_lib.setToolTip('Where the copied rolls and the prints are kept')
        self.btn_guide.setToolTip('What every setting does, and how the lab works')
        for b in (self.btn_log, self.btn_lib, self.btn_guide):
            top.addWidget(b)
        outer.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        # rolls
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        h = QLabel('ROLLS')
        h.setObjectName('h2')
        ll.addWidget(h)
        ll.setSpacing(4)
        # where rolls come from, right above the rolls
        k1 = QLabel('FAUXJI FILM CAMERA')
        k1.setStyleSheet('color:#8d877d; font-size:8pt; letter-spacing:1px; padding-top:2px')
        ll.addWidget(k1)
        row = QHBoxLayout()
        row.setSpacing(4)
        self.btn_card.setText('Open card')
        self.btn_folder.setText('Open folder…')
        row.addWidget(self.btn_card)
        row.addWidget(self.btn_folder)
        ll.addLayout(row)
        k2 = QLabel('ANY CAMERA OR PHONE')
        k2.setStyleSheet('color:#8d877d; font-size:8pt; letter-spacing:1px; padding-top:4px')
        ll.addWidget(k2)
        self.btn_photos.setText('＋  Load photos…')
        self.btn_photos.setStyleSheet('QPushButton { border-color: #5a2b28; } QPushButton:hover { border-color: %s; }' % RED)
        ll.addWidget(self.btn_photos)
        ll.addSpacing(4)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemSelectionChanged.connect(self.roll_selected)
        ll.addWidget(self.tree, 1)
        self.btn_import = QPushButton('Import roll to library')
        self.btn_import.clicked.connect(self.import_selected)
        ll.addWidget(self.btn_import)
        split.addWidget(left)

        # middle
        mid = QWidget()
        ml = QVBoxLayout(mid)
        ml.setContentsMargins(0, 0, 0, 0)
        self.roll_title = QLabel('Open a card or a folder')
        self.roll_title.setStyleSheet('font-size: 12pt; font-weight: 600; letter-spacing: 2px;')
        self.roll_sub = QLabel('')
        self.roll_sub.setObjectName('muted')
        for lbl, mw in ((self.roll_title, 330), (self.roll_sub, 230)):
            lbl.setMaximumWidth(mw)
            lbl.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        corner = QWidget()
        cl = QHBoxLayout(corner)
        cl.setContentsMargins(0, 0, 4, 0)
        cl.addWidget(self.roll_title)
        cl.addSpacing(10)
        cl.addWidget(self.roll_sub)
        self.tabs = QTabWidget()
        self.tabs.setCornerWidget(corner, Qt.TopRightCorner)
        hint = '←  →  frame      R / L  rotate      Space  switch view'
        # light table: the selected frame big, the roll's negatives along the bottom
        self.dview = FrameView([('negative', 'NEGATIVE', 'The developed negative, as it lies on the light table'),
                                ('original', 'ORIGINAL', 'The photo as the camera saved it'),
                                ('print', 'PRINT PREVIEW', 'A test print of this frame with the lab settings on the right; it follows every '
                                                           'change')], hint)
        self.dview.rotate.connect(self.rotate_current)
        self.dview.mode_changed.connect(lambda m: self.update_view())
        self.dview.clear('Open a card or a folder, then pick a roll')
        self.lighttable = filmstrip(QSize(128, 119), '#efe9dc')
        self.lighttable.currentItemChanged.connect(lambda *_: self.update_view())
        self.lighttable.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lighttable.customContextMenuRequested.connect(self.lighttable_menu)
        self.lighttable.setToolTip('Click a frame to see it big. Right-click (or R / L) to rotate it.')
        lt = QWidget()
        ltl = QVBoxLayout(lt)
        ltl.setContentsMargins(0, 0, 0, 0)
        ltl.addWidget(self.dview, 1)
        ltl.addWidget(self.lighttable)
        # prints: the selected print big, the prints along the bottom
        self.pview = FrameView(None, '←  →  print      R / L  rotate')
        self.pview.rotate.connect(self.rotate_current)
        self.pview.clear('No prints yet: develop the roll')
        self.prints = filmstrip(QSize(128, 100), '#1b1a1a')
        self.prints.currentItemChanged.connect(lambda *_: self.show_print())
        self.prints.setContextMenuPolicy(Qt.CustomContextMenu)
        self.prints.customContextMenuRequested.connect(self.prints_menu)
        self.prints.setToolTip('Click a print to see it big. Right-click (or R / L) to rotate it.')
        self.sheet_area = QScrollArea()
        self.sheet_area.setWidgetResizable(True)
        self.sheet_label = QLabel()
        self.sheet_label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.sheet_area.setWidget(self.sheet_label)
        self.tabs.addTab(lt, 'LIGHT TABLE')
        pw = QWidget()
        pl = QVBoxLayout(pw)
        pl.setContentsMargins(0, 6, 0, 0)
        prow = QHBoxLayout()
        self.dev_pick = QComboBox()
        self.dev_pick.currentIndexChanged.connect(self.show_development)
        prow.addWidget(QLabel('Development:'))
        prow.addWidget(self.dev_pick, 1)
        self.btn_export = QPushButton('Export prints…')
        self.btn_export.clicked.connect(self.export_prints)
        self.btn_openf = QPushButton('Show in folder')
        self.btn_openf.clicked.connect(self.open_dev_folder)
        prow.addWidget(self.btn_export)
        prow.addWidget(self.btn_openf)
        pl.addLayout(prow)
        pl.addWidget(self.pview, 1)
        pl.addWidget(self.prints)
        self.tabs.addTab(pw, 'PRINTS')
        self.tabs.addTab(self.sheet_area, 'CONTACT SHEET')
        ml.addWidget(self.tabs, 1)
        split.addWidget(mid)
        for keys, fn in ((('R',), lambda: self.rotate_current(90)), (('L',), lambda: self.rotate_current(-90)),
                         (('Space',), self.switch_view), (('Right',), lambda: self.step(1)), (('Left',), lambda: self.step(-1))):
            for k in keys:
                sc = QShortcut(QKeySequence(k), mid)
                sc.setContext(Qt.WidgetWithChildrenShortcut)
                sc.activated.connect(fn)

        # lab
        right = QFrame()
        right.setObjectName('panel')
        rl = QVBoxLayout(right)
        hrow = QHBoxLayout()
        h = QLabel('THE LAB')
        h.setObjectName('h2')
        hrow.addWidget(h)
        hrow.addStretch(1)
        q = QPushButton('?')
        q.setFixedSize(30, 26)
        q.setStyleSheet('padding:0; font-weight:600')
        q.setToolTip('What every setting does')
        q.clicked.connect(lambda: Guide(self).exec())
        hrow.addWidget(q)
        rl.addLayout(hrow)
        tip = QLabel('PRINT PREVIEW (above the picture) shows these\nsettings on the selected frame.')
        tip.setObjectName('muted')
        rl.addWidget(tip)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        self.c_look = QComboBox()
        for name in lab.PRESETS:
            self.c_look.addItem(name + ('   (default)' if name == 'Vintage print' else ''), name)
        self.c_look.addItem('Custom', None)
        self.c_look.activated.connect(lambda i: self.c_look.itemData(i) and self.set_recipe(lab.PRESETS[self.c_look.itemData(i)]))
        self.c_film = QComboBox()
        for f in films.FILMS:
            self.c_film.addItem(f.name, f.code)
        self.c_film.addItem('Mystery (secret)', films.MYSTERY.code)
        self.c_film.setToolTip('The film this roll of photos is developed as (rolls loaded with "Load photos…" only: FAUXJI rolls '
                               'already carry their film from the camera). Mystery picks a new secret film.')
        self.c_film.activated.connect(self.film_changed)
        form.addRow('Film', self.c_film)
        self.film_row_label = form.labelForField(self.c_film)
        form.addRow('Look', self.c_look)
        self.c_push = QComboBox()
        for p in lab.PUSH_PULL:
            self.c_push.addItem({-1: 'Pull −1', 0: 'Box speed', 1: 'Push +1', 2: 'Push +2'}[p], p)
        self.c_push.setCurrentIndex(1)
        self.c_dev = self._combo(lab.DEVELOPERS)
        self.c_proc = self._combo(lab.PROCESSES)
        self.c_exp = QSpinBox()
        self.c_exp.setRange(0, 30)
        self.c_exp.setSuffix(' years')
        self.c_grain = self._slider(0, 250, 100)
        self.c_hal = self._slider(0, 250, 100)
        self.c_leaks = QCheckBox('Light leaks on the first frames')
        self.c_leaks.setChecked(True)
        self.c_paper = self._combo(lab.PAPERS)
        self.c_border = self._combo(lab.BORDERS)
        self.c_auto = QCheckBox('Lab correction (auto levels)')
        self.c_size = QComboBox()
        for label, v in (('Full size (3648 px)', 0), ('Large (2400 px)', 2400), ('Web (1600 px)', 1600)):
            self.c_size.addItem(label, v)
        form.addRow('Development', self.c_push)
        form.addRow('Developer', self.c_dev)
        form.addRow('Process', self.c_proc)
        form.addRow('Expired', self.c_exp)
        form.addRow('Grain', self.c_grain)
        form.addRow('Halation', self.c_hal)
        form.addRow('', self.c_leaks)
        form.addRow('Paper', self.c_paper)
        form.addRow('Border', self.c_border)
        form.addRow('', self.c_auto)
        form.addRow('Print size', self.c_size)
        rl.addLayout(form)
        for w, key in ((self.c_look, 'look'), (self.c_push, 'push'), (self.c_dev, 'developer'), (self.c_proc, 'process'), (self.c_exp, 'expired'),
                       (self.c_grain, 'grain'), (self.c_hal, 'halation'), (self.c_leaks, 'leaks'), (self.c_paper, 'paper'),
                       (self.c_border, 'border'), (self.c_auto, 'auto'), (self.c_size, 'size')):
            w.setToolTip(TIPS[key])
            lbl = form.labelForField(w)
            if lbl is not None:
                lbl.setToolTip(TIPS[key])
        for w in (self.c_push, self.c_dev, self.c_proc, self.c_paper, self.c_border):
            w.currentIndexChanged.connect(lambda *_: self.recipe_changed())
        for w in (self.c_grain, self.c_hal):
            w.sliderReleased.connect(self.recipe_changed)
        self.c_exp.valueChanged.connect(lambda *_: self.recipe_changed())
        self.c_leaks.toggled.connect(lambda *_: self.recipe_changed())
        self.c_auto.toggled.connect(lambda *_: self.recipe_changed())
        row = QHBoxLayout()
        b = QPushButton('Surprise me')
        b.setToolTip(TIPS['surprise'])
        b.clicked.connect(self.surprise)
        b2 = QPushButton('Reset')
        b2.setToolTip(TIPS['reset'])
        b2.clicked.connect(lambda: self.set_recipe(lab.Recipe()))
        row.addWidget(b)
        row.addWidget(b2)
        rl.addLayout(row)
        rl.addStretch(1)
        self.btn_develop = QPushButton('DEVELOP ROLL')
        self.btn_develop.setObjectName('develop')
        self.btn_develop.clicked.connect(self.develop)
        self.btn_develop.setToolTip(TIPS['develop'])
        rl.addWidget(self.btn_develop)
        right.setMinimumWidth(320)
        right.setMaximumWidth(380)
        split.addWidget(right)
        split.setSizes([280, 800, 340])
        outer.addWidget(split, 1)
        self.setCentralWidget(root)
        self.set_recipe(lab.Recipe())                                    # the vintage print look
        self.c_film.setVisible(False)                                     # the film selector is for loaded photos only
        if self.film_row_label is not None:
            self.film_row_label.setVisible(False)
        self._update_buttons()

    def _combo(self, options):
        c = QComboBox()
        for k, v in options.items():
            c.addItem(v, k)
        return c

    def _slider(self, lo, hi, v):
        s = QSlider(Qt.Horizontal)
        s.setRange(lo, hi)
        s.setValue(v)
        return s

    def notify(self, text, ms=6000):
        """A short message in the header (there is no status bar: the picture gets the room)."""
        self.note.setText(self.note.fontMetrics().elidedText(text, Qt.ElideRight, 450))
        self.note.setToolTip(text)
        self.note_timer.start(ms)

    # ------------------------------------------------------------ recipe
    def recipe(self):
        return lab.Recipe(push=self.c_push.currentData(), developer=self.c_dev.currentData(), process=self.c_proc.currentData(),
                          expired=self.c_exp.value(), grain=self.c_grain.value() / 100.0, halation=self.c_hal.value() / 100.0,
                          leaks=self.c_leaks.isChecked(), paper=self.c_paper.currentData(), border=self.c_border.currentData(),
                          auto_levels=self.c_auto.isChecked())

    def set_recipe(self, r):
        self._quiet = True
        for combo, v in ((self.c_push, r.push), (self.c_dev, r.developer), (self.c_proc, r.process), (self.c_paper, r.paper),
                         (self.c_border, r.border)):
            combo.setCurrentIndex(max(0, combo.findData(v)))
        self.c_exp.setValue(r.expired)
        self.c_grain.setValue(round(r.grain * 100))
        self.c_hal.setValue(round(r.halation * 100))
        self.c_leaks.setChecked(r.leaks)
        self.c_auto.setChecked(r.auto_levels)
        self._quiet = False
        self.recipe_changed()

    def surprise(self):
        self.set_recipe(lab.surprise(random.Random()))
        self.notify('The lab picked: ' + self.recipe().describe(), 6000)

    def recipe_changed(self):
        if getattr(self, '_quiet', False):
            return
        name = lab.preset_name(self.recipe())
        self.c_look.setCurrentIndex(self.c_look.findData(name) if name else self.c_look.count() - 1)
        if self.dview.mode == 'print':
            self.update_view()

    # ------------------------------------------------------------ sources and rolls
    def pick_card(self):
        cards = card.find_cards()
        if not cards:
            QMessageBox.information(self, APP_NAME, 'No FAUXJI card found.\n\nPut the card in the reader (a FILMS folder at its root), '
                                    'or use "Open folder…" for a copy of the card.')
            return
        if len(cards) == 1:
            self.open_source(cards[0])
            return
        m = QMenu(self)
        for c in cards:
            m.addAction(c, lambda c=c: self.open_source(c))
        m.exec(self.btn_card.mapToGlobal(self.btn_card.rect().bottomLeft()))

    def pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, 'Open a card, a FILMS folder, a roll or any folder of photos',
                                             self.settings.value('source') or os.path.expanduser('~'))
        if d:
            self.open_source(d)

    def load_photos(self):
        dlg = LoadPhotos(self, self.settings.value('photos') or os.path.expanduser('~'))
        if not dlg.exec() or not dlg.paths:
            return
        self.settings.setValue('photos', dlg.start_dir)
        paths, code, name = dlg.paths, dlg.film.currentData(), dlg.name.text().strip() or 'My roll'
        self.busy = True
        self._update_buttons()
        self.notify('Loading %d photos…' % len(paths))

        def work(report):
            return self.library.import_files(paths, code, name, progress=lambda d, n: report((d, n)))

        def done(rid):
            self.busy = False
            self.refresh_library()
            self.select_library_roll(rid)
            self.notify('"%s" is on the light table: %d photos' % (name, len(paths)))
            self._update_buttons()

        self.run(work, done, progress=lambda p: self.notify('Loading photos…  %d / %d' % p))

    def select_library_roll(self, rid):
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                d = top.child(j).data(0, Qt.UserRole)
                if d and d[0] == 'library' and d[1] == rid:
                    self.tree.setCurrentItem(top.child(j))
                    return True
        return False

    def film_changed(self, i):
        if self.roll is None or not self.roll.own:
            return
        code = self.c_film.itemData(i)
        rid = self.roll_key()
        self.library.set_film(rid, code)
        self.refresh_library()
        self.select_library_roll(rid)
        self.notify('Developed as %s from now on' % (self.c_film.itemText(i)))

    def pick_library(self):
        d = QFileDialog.getExistingDirectory(self, 'Library folder (imported rolls and prints)', self.library.root)
        if d:
            self.library = Library(d)
            self.settings.setValue('library', d)
            self.refresh_library()

    def open_source(self, path):
        self.settings.setValue('source', path)
        self.notify('Reading %s …' % path)
        self.run(lambda report: card.scan(path), self._source_loaded, extra=path)

    def _source_loaded(self, rolls, path):
        self.source_rolls = rolls
        self.source_path = path
        self.notify('%d roll%s in %s' % (len(rolls), '' if len(rolls) == 1 else 's', path), 8000)
        self.refresh_tree()
        if rolls:
            self.tree.setCurrentItem(self.tree.topLevelItem(0).child(0))

    def refresh_library(self):
        self.library_ids = self.library.rolls()
        self.refresh_tree()

    def roll_label(self, film, code, frames, first, secret):
        name = 'Mystery  ???' if secret else film.name
        when = first.strftime('%d %b') if first else ''
        return '%s\n%s  ·  %d%s  ·  %s' % (name, code, frames, '/36' if frames <= 36 else ' frames', when)

    def refresh_tree(self):
        self.tree.clear()
        if self.source_rolls:
            top = QTreeWidgetItem(['ON THE CARD' if os.path.basename(os.path.normpath(getattr(self, 'source_path', ''))) == '' or
                                   os.path.isdir(os.path.join(getattr(self, 'source_path', ''), 'FILMS')) else 'IN THE FOLDER'])
            top.setFlags(Qt.ItemIsEnabled)
            self.tree.addTopLevelItem(top)
            for r in self.source_rolls:
                secret = r.mystery and not self.library.revealed(r.roll_id)
                it = QTreeWidgetItem([self.roll_label(r.film if not r.mystery else r.true_film, r.code, len(r.frames), r.first, secret)])
                it.setData(0, Qt.UserRole, ('card', r))
                it.setIcon(0, self._swatch(films.MYSTERY.colour if secret else r.true_film.colour))
                if self.library.has_roll(r.roll_id):
                    it.setToolTip(0, 'Already in the library')
                top.addChild(it)
            top.setExpanded(True)
        if not self.source_rolls:
            top = QTreeWidgetItem(['FAUXJI FILM CAMERA'])
            top.setFlags(Qt.ItemIsEnabled)
            self.tree.addTopLevelItem(top)
            top.addChild(self._action_item('Open the card…   (or a copy: Open folder…)', 'card'))
            top.setExpanded(True)
        top = QTreeWidgetItem(['LIBRARY'])
        top.setFlags(Qt.ItemIsEnabled)
        self.tree.addTopLevelItem(top)
        for rid in self.library_ids:
            meta = self.library._read(os.path.join(self.library.roll_dir(rid), 'roll.json')) or {}
            film = films.from_code(meta.get('film_code', rid[:4]))
            devs = self.library.developments(rid)
            secret = film is films.MYSTERY and not devs
            shown = films.BY_NAME.get(devs[0][1]['film'].lower(), film) if devs else film
            first = datetime.fromisoformat(meta['first']) if meta.get('first') else None
            it = QTreeWidgetItem([self.roll_label(shown, meta.get('name') or meta.get('code', rid), meta.get('frames', 0), first, secret) +
                                  ('  ·  developed' if devs else '')])
            it.setData(0, Qt.UserRole, ('library', rid))
            it.setIcon(0, self._swatch(films.MYSTERY.colour if secret else shown.colour))
            top.addChild(it)
        top.addChild(self._action_item('＋  Load photos from any camera…', 'photos'))
        top.setExpanded(True)
        self.tree.setIconSize(QSize(14, 30))

    def _action_item(self, text, action):
        """A clickable line in the roll list that opens something (not a roll)."""
        it = QTreeWidgetItem([text])
        it.setData(0, Qt.UserRole, ('action', action))
        it.setForeground(0, QColor('#d9a19a'))
        it.setToolTip(0, {'card': 'Open the FAUXJI card in the card reader', 'photos': 'Make a roll of photos from any camera or phone'}[action])
        return it

    def _swatch(self, rgb):
        pm = QPixmap(14, 30)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setBrush(QColor(*rgb))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(1, 3, 12, 24, 3, 3)
        p.end()
        return QIcon(pm)

    def roll_selected(self):
        items = self.tree.selectedItems()
        if not items or not items[0].data(0, Qt.UserRole):
            return
        kind, ref = items[0].data(0, Qt.UserRole)
        if kind == 'action':
            self.tree.blockSignals(True)
            self.tree.clearSelection()
            self.tree.blockSignals(False)
            QTimer.singleShot(0, self.pick_card if ref == 'card' else self.load_photos)
            return
        if kind == 'card':
            self.roll, self.roll_in_library = ref, False
        else:
            self.roll, self.roll_in_library = self.library.load_roll(ref), True
            self.roll.code = (self.library._read(os.path.join(self.library.roll_dir(ref), 'roll.json')) or {}).get('code', self.roll.code)
        self.show_roll()

    def roll_key(self):
        if self.roll is None:
            return None
        return os.path.basename(os.path.normpath(self.roll.path)) if self.roll_in_library else self.roll.roll_id

    def secret(self):
        return self.roll is not None and self.roll.mystery and not self.library.revealed(self.roll_key())

    def shown_film(self):
        return films.MYSTERY if self.secret() else self.roll.true_film

    def show_roll(self):
        r = self.roll
        own = bool(getattr(r, 'own', False))
        self.c_film.setVisible(own)
        if self.film_row_label is not None:
            self.film_row_label.setVisible(own)
        if own:
            self.c_film.setCurrentIndex(max(0, self.c_film.findData(r.film.code)))
        film = self.shown_film()
        self.roll_title.setText('%s  ·  %s' % (film.name.upper() if not self.secret() else 'MYSTERY  ???', r.name or r.code))
        span = ''
        if r.first:
            span = r.first.strftime('%d %b %Y') + ('' if not r.last or r.last.date() == r.first.date() else ' – ' + r.last.strftime('%d %b %Y'))
        parts = ['%d / 36' % len(r.frames) if len(r.frames) <= 36 else '%d frames' % len(r.frames), span,
                 'my photos' if r.own else ('library' if self.roll_in_library else 'card')]
        self.roll_sub.setText('  ·  '.join(x for x in parts if x))
        self.roll_sub.setToolTip('%s%s' % (r.path, ('\n%d RAW files are left on the card' % r.raws) if r.raws else ''))
        self.lighttable.clear()
        placeholder = QPixmap(250, 233)
        placeholder.fill(QColor('#d8d0c0'))
        self.dview.clear('Developing the negatives…')
        for f in r.frames:
            it = QListWidgetItem(QIcon(placeholder), '')
            it.setData(Qt.UserRole, f)
            self.lighttable.addItem(it)
        key = self.roll_key()
        turns = self.library.rotations(key)

        def work(report):
            for k, f in enumerate(r.frames):
                report((k, self.neg_thumb(f, turns.get(f.number, 0))))
            return key

        self.run(work, lambda key: None, progress=self._neg_ready)
        self.load_developments()
        self.tabs.setCurrentIndex(0)
        self._update_buttons()

    def neg_film(self, f):
        """The film a frame's negative is drawn as: a mystery roll's negatives never give the film away."""
        film = self.shown_film()
        return films.from_code('CNEG') if (self.secret() or film is films.MYSTERY) else (f.film or film)

    def neg_thumb(self, f, turn):
        """The filmstrip picture of a frame: its negative, turned, in a piece of film with sprocket holes."""
        ck = (f.path, self.neg_film(f).code)
        if ck not in self.neg_cache:
            a = lab.load(f.path, 360)
            self.neg_cache[ck] = lab.to_image(lab.negative(a, self.neg_film(f)))
        return lab.strip([lab.rotate(self.neg_cache[ck], turn)], self.shown_film(), positive=False, frame_w=250, start=f.number)

    def turn(self, f):
        return self.library.rotations(self.roll_key()).get(f.number, 0)

    def selected_frame(self):
        it = self.lighttable.currentItem()
        return it.data(Qt.UserRole) if it is not None else None

    def step(self, d):
        lst = self.prints if self.tabs.currentIndex() == 1 else self.lighttable
        if lst.count():
            lst.setCurrentRow(max(0, min(lst.count() - 1, lst.currentRow() + d)))
            lst.scrollToItem(lst.currentItem())

    def switch_view(self):
        if self.tabs.currentIndex() == 0:
            self.dview.next_mode()

    def rotate_current(self, delta):
        """R / L / the rotate buttons: turn the selected frame (light table) or print (prints). Instant on screen."""
        if self.tabs.currentIndex() == 1:
            return self.rotate_print_current(delta)
        if self.tabs.currentIndex() != 0:
            return
        f = self.selected_frame()
        if f is None or self.roll is None:
            return
        new = self.library.rotate(self.roll_key(), f.number, delta)
        self.dview.set_rotation(new, delta)
        it = self.lighttable.currentItem()
        it.setIcon(QIcon(to_pixmap(self.neg_thumb(f, new))))
        self.notify('Frame %d turned to %d°. Saved: it stays turned in the filmstrip, previews, prints and the '
                                     'contact sheet.' % (f.number, new), 5000)

    def lighttable_menu(self, pos):
        it = self.lighttable.itemAt(pos)
        if it is None:
            return
        self.lighttable.setCurrentItem(it)
        f = it.data(Qt.UserRole)
        m = QMenu(self)
        m.addAction('⟳  Rotate right (clockwise)        R', lambda: self.rotate_current(90))
        m.addAction('⟲  Rotate left                            L', lambda: self.rotate_current(-90))
        m.addAction('Turn upside down', lambda: self.rotate_current(180))
        if self.turn(f):
            m.addAction('Straighten (no rotation)', lambda: self.rotate_current(-self.turn(f)))
        m.exec(self.lighttable.viewport().mapToGlobal(pos))

    def recipe_key(self):
        return tuple(sorted(self.recipe().to_dict().items()))

    def update_view(self):
        """Show the selected frame big in the chosen view; renders in the background, cached, always unrotated."""
        f = self.selected_frame()
        if f is None or self.roll is None:
            self.dview.clear('Pick a frame in the filmstrip below')
            return
        mode = self.dview.mode
        key = (f.path, mode, self.neg_film(f).code if mode == 'negative' else '',
               (self.recipe_key(), self.roll.true_film.code) if mode == 'print' else ())
        turn = self.turn(f)
        cap = '%s  ·  frame %d / %d  ·  %s' % (self.roll.code, f.number, len(self.roll.frames),
                                                f.taken.strftime('%d %b %Y  %H:%M') if f.taken else os.path.basename(f.path))
        if key in self.render_cache:
            self.dview.show_picture(self.render_cache[key][1], turn, cap)
            return
        older = [v for k, v in self.render_cache.items() if k[0] == f.path]
        label = {'negative': 'developing the negative…', 'original': 'loading…', 'print': 'printing a test strip…'}[mode]
        self.dview.show_picture(older[-1][1] if older else None, turn, cap, loading=label)
        recipe = self.recipe()
        recipe.seed = 1
        neg_film = self.neg_film(f)
        real_film = f.film or self.roll.true_film
        own = self.roll.own
        token = self._render_token = object()

        def work(report):
            a = self.arrays.get(f.path)
            if a is None:
                a = lab.load(f.path, 1600)
                self.arrays = {**{k: v for k, v in list(self.arrays.items())[-2:]}, f.path: a}
            if mode == 'negative':
                im = lab.to_image(lab.negative(a, neg_film))
            elif mode == 'original':
                im = lab.to_image(a)
            else:
                im = lab.to_image(lab.develop(a, real_film, recipe, frame=f.number, emulate=own))
            return token, key, im

        def done(res):
            tok, k, im = res
            self.render_cache[k] = (im, to_pixmap(im))
            self.render_order.append(k)
            while len(self.render_order) > 24:
                self.render_cache.pop(self.render_order.pop(0), None)
            if tok is self._render_token:
                self.update_view()

        self.run(work, done)

    def _neg_ready(self, item):
        k, im = item
        if k < self.lighttable.count():
            self.lighttable.item(k).setIcon(QIcon(to_pixmap(im)))
            if k == 0 and self.lighttable.currentRow() < 0:
                self.lighttable.setCurrentRow(0)

    # ------------------------------------------------------------ import / develop
    def import_selected(self):
        if self.roll is None or self.roll_in_library:
            return
        r = self.roll

        def work(report):
            return self.library.import_roll(r, progress=lambda d, n: report((d, n)))

        self.busy = True
        self._update_buttons()
        self.notify('Copying %s into the library…' % r.code)
        self.run(work, self._imported, progress=lambda p: self.notify('Copying %s into the library…  %d / %d' % (r.code, p[0], p[1])))

    def _imported(self, libroll):
        self.busy = False
        self.notify('%s is in the library' % libroll.code)
        self.refresh_library()
        self._update_buttons()

    def develop(self):
        """Develop the whole roll. The big view becomes the darkroom: each print comes up in the developer tray, goes through the stop
        bath, fixer and wash, and is hung on the drying line; then the prints tab opens."""
        if self.roll is None or self.busy:
            return
        r, in_lib = self.roll, self.roll_in_library
        recipe = self.recipe()
        max_side = self.c_size.currentData() or None
        self.busy = True
        self._update_buttons()
        was_secret = self.secret()
        self.tabs.setCurrentIndex(0)
        canvas = self.dview.canvas
        canvas.start_develop('DEVELOPING  %s  ·  %s' % (r.code, recipe.describe().upper()))

        def work(report):
            libroll = r if in_lib else self.library.import_roll(r, progress=lambda d, n: report(('load', d, n, None)))
            report(('load', 0, 0, None))
            return self.library.develop(libroll, recipe, progress=lambda d, n, s_, t: report(('dev', d, n, t)), max_side=max_side), libroll

        def prog(p):
            kind, d, n, t = p
            if kind == 'load':
                canvas.dev_note('Loading the film into the tank…  %d / %d' % (d, n) if n else 'Developer in, tank closed…')
            else:
                canvas.dev_feed(to_pixmap(t), d, n)

        def done(res):
            (folder, labcard), libroll = res

            def after():
                self.busy = False
                self.refresh_library()
                for i in range(self.tree.topLevelItemCount()):
                    top = self.tree.topLevelItem(i)
                    for j in range(top.childCount()):
                        d = top.child(j).data(0, Qt.UserRole)
                        if d and d[0] == 'library' and d[1] == labcard['roll_id']:
                            self.tree.setCurrentItem(top.child(j))
                self.load_developments()
                self.tabs.setCurrentIndex(1)
                self.notify('%d prints dry  ·  %s' % (len(labcard['frames']), labcard['description']))
                self._update_buttons()
                if was_secret or (r.mystery and labcard.get('mystery')):
                    Reveal(self, films.BY_NAME.get(labcard['film'].lower(), films.UNKNOWN)).exec()

            canvas.dev_finish(after, 'DRY  ·  %d PRINTS' % len(labcard['frames']))

        self.run(work, done, progress=prog)

    # ------------------------------------------------------------ prints
    def load_developments(self):
        self.dev_pick.blockSignals(True)
        self.dev_pick.clear()
        self.devs = self.library.developments(self.roll_key()) if self.roll is not None else []
        for folder, lc in self.devs:
            self.dev_pick.addItem('%s  ·  %s' % (lc['developed'].replace('T', ' '), lc['description']), folder)
        self.dev_pick.blockSignals(False)
        self.show_development()

    def show_development(self, *_):
        self.prints.clear()
        self.sheet_label.clear()
        self.print_pix = {}
        folder = self.dev_pick.currentData()
        if not folder:
            self.sheet_label.setText('No contact sheet yet: develop the roll.')
            self.pview.clear('No prints yet: develop the roll')
            self._update_buttons()
            return
        lc = dict(self.devs)[folder]
        self.print_paths = [os.path.join(folder, fr['file']) for fr in lc['frames']]
        blank = QPixmap(128, 100)
        blank.fill(QColor('#232121'))
        for p in self.print_paths:
            it = QListWidgetItem(QIcon(blank), '')
            it.setToolTip(os.path.basename(p))
            it.setData(Qt.UserRole, p)
            self.prints.addItem(it)
        paths = list(self.print_paths)

        def work(report):
            for k, p in enumerate(paths):
                report((k, self._print_thumb(p)))
            return os.path.join(folder, 'contact_sheet.jpg')

        def ready(item):
            k, im = item
            if k < self.prints.count():
                self.prints.item(k).setIcon(QIcon(to_pixmap(im)))

        self.run(work, self._show_sheet, progress=ready)
        if self.prints.count():
            self.prints.setCurrentRow(0)
        self._update_buttons()

    def _print_thumb(self, p):
        with Image.open(p) as im:
            im.draft('RGB', (500, 500))
            im = im.convert('RGB')
        im.thumbnail((300, 236))
        return im

    def _show_sheet(self, path):
        if os.path.exists(path):
            pm = QPixmap(path)
            self.sheet_label.setPixmap(pm.scaledToWidth(min(pm.width(), max(600, self.sheet_area.width() - 30)), Qt.SmoothTransformation))

    def selected_print(self):
        it = self.prints.currentItem()
        return it.data(Qt.UserRole) if it is not None else None

    def show_print(self):
        p = self.selected_print()
        if p is None:
            self.pview.clear('No prints yet: develop the roll')
            return
        cap = '%s  ·  %s  (%d / %d)' % (self.roll.code if self.roll else '', os.path.basename(p), self.prints.currentRow() + 1,
                                         self.prints.count())
        pending = self.print_pending.get(p, 0)
        if p in self.print_pix:
            self.pview.show_picture(self.print_pix[p], pending, cap)
            return
        self.pview.show_picture(None, pending, cap, loading='loading…')

        def work(report):
            with Image.open(p) as im:
                im.draft('RGB', (2000, 2000))
                return p, im.convert('RGB')

        def done(res):
            path, im = res
            self.print_pix[path] = to_pixmap(im)
            if self.selected_print() == path:
                self.show_print()

        self.run(work, done)

    def rotate_print_current(self, delta):
        """Turn the selected print: at once on screen; the JPEG and the contact sheet are rewritten a moment after the last click."""
        p = self.selected_print()
        if p is None:
            return
        new = (self.print_pending.get(p, 0) + delta) % 360
        self.print_pending[p] = new
        self.pview.set_rotation(new, delta)
        self.notify('Print turned. Saving the print and the contact sheet…', 3000)
        self.rot_timer.start()

    def write_print_rotations(self):
        todo = {p: d for p, d in self.print_pending.items() if d % 360}
        if not todo:
            return

        def work(report):
            done = []
            for p, d in todo.items():
                folder, frame = os.path.dirname(p), int(os.path.basename(p).split('_')[1].split('.')[0])
                self.library.rotate_print(folder, frame, d)
                done.append((p, d, self._print_thumb(p)))
            return done

        def finished(done):
            folder = None
            for p, d, thumb in done:
                self.print_pending[p] = (self.print_pending.get(p, 0) - d) % 360
                self.print_pix.pop(p, None)
                for k in range(self.prints.count()):
                    if self.prints.item(k).data(Qt.UserRole) == p:
                        self.prints.item(k).setIcon(QIcon(to_pixmap(thumb)))
                folder = os.path.dirname(p)
            if self.selected_print() in [p for p, _, _ in done]:
                self.show_print()
            if folder:
                self._show_sheet(os.path.join(folder, 'contact_sheet.jpg'))
            self.notify('Saved: the print, the contact sheet, and the frame\'s rotation for the next development.', 5000)
            if any(self.print_pending.values()):
                self.rot_timer.start()

        self.run(work, finished)

    def prints_menu(self, pos):
        it = self.prints.itemAt(pos)
        if it is None:
            return
        self.prints.setCurrentItem(it)
        m = QMenu(self)
        m.addAction('⟳  Rotate right (clockwise)        R', lambda: self.rotate_print_current(90))
        m.addAction('⟲  Rotate left                            L', lambda: self.rotate_print_current(-90))
        m.addAction('Turn upside down', lambda: self.rotate_print_current(180))
        m.exec(self.prints.viewport().mapToGlobal(pos))

    def export_prints(self):
        folder = self.dev_pick.currentData()
        if not folder:
            return
        d = QFileDialog.getExistingDirectory(self, 'Export the prints to', os.path.expanduser('~'))
        if not d:
            return
        lc = dict(self.devs)[folder]
        dst = os.path.join(d, '%s_%s' % (lc['roll'], lc['film'].replace(' ', '_').replace('.', '')))
        os.makedirs(dst, exist_ok=True)
        for n in os.listdir(folder):
            if n.lower().endswith('.jpg'):
                shutil.copy2(os.path.join(folder, n), dst)
        self.notify('Exported to %s' % dst, 8000)
        QDesktopServices.openUrl(QUrl.fromLocalFile(dst))

    def open_dev_folder(self):
        folder = self.dev_pick.currentData() or (self.library.roll_dir(self.roll_key()) if self.roll is not None else self.library.root)
        if folder and os.path.isdir(folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    # ------------------------------------------------------------ plumbing
    def _update_buttons(self):
        has = self.roll is not None
        self.btn_develop.setEnabled(has and not self.busy and bool(self.roll.frames))
        self.btn_import.setEnabled(has and not self.busy and not self.roll_in_library)
        dev = bool(getattr(self, 'devs', None))
        self.btn_export.setEnabled(dev)
        self.btn_openf.setEnabled(has)

    def run(self, fn, done, progress=None, extra=None):
        job = Job(fn)
        if progress:
            job.signals.progress.connect(progress)
        job.signals.done.connect((lambda r: done(r, extra)) if extra is not None else done)
        job.signals.failed.connect(self._failed)
        self.jobs.append(job)
        job.signals.done.connect(lambda *_: self.jobs.remove(job) if job in self.jobs else None)
        self.pool.start(job)

    def _failed(self, tb):
        self.busy = False
        self._update_buttons()
        self.dview.canvas.dev_cancel()
        self.notify('Something went wrong in the lab')
        sys.stderr.write(tb)
        QMessageBox.warning(self, APP_NAME, 'Something went wrong:\n\n' + tb.strip().splitlines()[-1])


def main(argv=None):
    argv = sys.argv if argv is None else argv
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName('FAUXJI')
    app.setStyleSheet(STYLE)
    app.setWindowIcon(app_icon())
    if '--selftest' in argv:
        return selftest(app, argv[argv.index('--selftest') + 1:])
    w = MainWindow()
    if len(argv) > 1 and os.path.isdir(argv[1]):                       # a folder given on the command line (or dropped on the icon)
        QTimer.singleShot(300, lambda: w.open_source(argv[1]))
    w.show()
    return app.exec()


def selftest(app, args):
    """Safelight --selftest <folder> <screenshot.png>: open the folder, develop its first roll at web size into a temporary library,
    save a screenshot of the prints, exit 0 (1 on any failure). Checks a packaged build end to end."""
    import tempfile
    import time
    folder, shot = args[0], args[1]
    tmp = tempfile.mkdtemp(prefix='safelight-selftest-')
    os.environ['SAFELIGHT_LIBRARY'] = os.path.join(tmp, 'library')
    Reveal.exec = lambda self: 0
    w = MainWindow(QSettings(os.path.join(tmp, 'settings.ini'), QSettings.IniFormat), autoload=False)
    w.resize(1400, 880)
    w.show()
    failed = []
    w._failed = lambda tb: failed.append(tb)

    def wait(cond, secs):
        t = time.time()
        while not cond() and not failed:
            app.processEvents()
            time.sleep(0.02)
            if time.time() - t > secs:
                failed.append('timeout')
    w.open_source(folder)
    wait(lambda: w.source_rolls, 60)
    if not failed:
        w.tree.setCurrentItem(w.tree.topLevelItem(0).child(0))
        wait(lambda: not w.jobs, 60)
        w.c_size.setCurrentIndex(w.c_size.findData(1600))
        w.develop()
        wait(lambda: not w.busy and not w.jobs, 600)
        wait(lambda: w.prints.count() > 0, 30)
        wait(lambda: not w.jobs, 30)
    for _ in range(30):
        app.processEvents()
    w.grab().save(shot)
    print('selftest:', 'FAILED ' + failed[0].strip().splitlines()[-1] if failed else 'OK, %d prints' % w.prints.count(), flush=True)
    return 1 if failed else 0

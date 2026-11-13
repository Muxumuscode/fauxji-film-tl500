"""Sajin Genzō's window: rolls on the left, the big view with the filmstrip (light table, prints) and the contact sheet in the middle,
the lab on the right. Developing plays in the big view."""
import os
import random
import shutil
import sys
import traceback
from datetime import datetime

from PIL import Image
from PySide6.QtCore import QEvent, QFile, QObject, QRunnable, QSettings, QSize, Qt, QThreadPool, QTimer, Signal, QUrl
from PySide6.QtGui import QColor, QFont, QDesktopServices, QIcon, QImage, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (QSizePolicy, QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
                               QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton,
                               QScrollArea, QSlider, QSpinBox, QSplitter, QTabWidget, QTableWidget, QTableWidgetItem, QTreeWidget,
                               QTextBrowser, QTreeWidgetItem, QVBoxLayout, QWidget, QLineEdit, QButtonGroup, QInputDialog, QAbstractItemView, QStackedWidget)

from . import APP_NAME, APP_NATIVE, __version__, card, films, lab, recipes
from .library import DARKROOM, Library, frame_number
from .photolab import PhotoLab, StartPage
from .viewer import ElidedLabel, FrameView, FullScreen, filmstrip

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
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle { background: #3a3737; border-radius: 4px; min-height: 28px; min-width: 28px; }
QScrollBar::handle:hover { background: #5a2b28; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QPushButton#seg { border-radius: 0; padding: 6px 14px; letter-spacing: 1px; }
QPushButton#seg:checked { background: #3a1d1b; border-color: %(red)s; color: #fff; }
""" % {'red': RED}


# ---------------------------------------------------------------- what every setting does

TIPS = {
    'look': 'Recipe cards: ready-made lab settings.\nLab looks work with any film: Vintage print (the default: a roll a few years past '
            'its date, printed on faded warm paper with a white border), Faded 70s snapshot, Clean lab print, Gritty push, '
            'Cross-processed, Darkroom fibre.\nCards for kinds of photography (portrait, landscape, street, night, black and white ...) '
            'come with their film: picking one also sets the film of a roll of your own photos (a FAUXJI roll keeps its own film).\n'
            '＋ saves the current settings as your own recipe; ⋯ imports, exports (to share) or deletes recipes. Change any setting and '
            'the recipe becomes Custom.',
    'scope': 'WHOLE ROLL: the settings below are for every frame (except frames with their own, ● on the filmstrip).\n'
             'THIS FRAME: they are for the selected frame(s) only: change anything (film too, for your own photos) and those frames '
             'get their own settings. Select several frames with Ctrl / Shift + click. Right-click a frame to copy its settings and '
             'paste them to others (Ctrl+C, Ctrl+V).',
    'print': 'Print the selected frame(s) on their own, each with its own settings (else the roll\'s). The prints come up in PRINTS, '
             'by frame, next to the frame\'s other prints; Develop roll is not needed.',
    'save_card': 'Save these lab settings (and the film, for your own photos) as a recipe of your own.',
    'filter': 'Black and white only, photos from other cameras. A coloured filter on the lens changes which colours come out light or '
              'dark.\nYellow: a slightly darker sky.\nOrange: dark sky, smooth skin.\nRed: dramatic black sky, white clouds, light skin.\n'
              'Green: light foliage, darker skin.\n(FAUXJI black-and-white frames were already made in the camera.)',
    'tone': 'Black and white only. Toning the print after it is made.\nSelenium: deeper blacks with a slightly cool, purple-brown cast.\n'
            'Sepia: warm brown all over.',
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
             'tint, like a darkroom fibre print.\nNeutral fibre: no colour of its own, for black and white (the vintage and warm '
             'papers tint black and white prints warm).',
    'border': 'The border around each print.\nWhite: a plain white border.\nBlack film-holder edge: the rough black edge of a negative '
              'carrier filed out for full-frame prints, with the film, frame and date in orange.\nInstant-print frame: a wide bottom, '
              'with the caption.',
    'scan': 'Photos from other cameras only. Authentic scan: a film frame cannot hold the hair-sharp detail and the HDR range of a '
            'modern phone photo, so the lab softens it to what film could resolve (before the grain goes on, so grain and detail belong '
            'together) and rolls the highlights off softly like a print instead of clipping them. Nothing is thrown away: it is a tone '
            'curve. Untick it to keep every pixel.',
    'auto': 'A gentle lab correction: stretches the darkest and brightest tones a little so flat frames get some snap. Leave it off for '
            'the film\'s own look.',
    'size': 'The size of the prints: full (the photo\'s own size: 3648 px from the FAUXJI camera, about 3 s a frame; very large photos '
            'are brought down to 6000 px), large (2400 px) or web (1600 px, fastest).',
    'surprise': 'Let the lab pick every setting at random.',
    'reset': 'Back to the default look: Vintage print.',
    'develop': 'Develop every frame of the roll with these settings: the roll is copied into the library first (the originals are never '
               'changed), then the prints and a contact sheet are made. You can develop a roll as often as you like; each development '
               'is kept.',
}

GUIDE = """<h2>%(name)s &nbsp;<span style='color:#8d877d'>%(native)s</span></h2>
<p><i>사진 (sajin)</i> is Korean for <b>photo</b>, <i>現像 (genzō)</i> is Japanese for <b>developing</b>: a Samsung camera with Fuji film
looks, and this is its photo lab.</p>
<h3>Two ways in</h3>
<p><b>Photo Lab</b> (the switch at the top): like sending a roll to a lab. Drop off your photos, choose one film and a lab, send it, and
collect the prints. <b>Darkroom</b> (this guide is mostly about it): every setting, frame by frame.</p>
<h3>How it works (Darkroom)</h3>
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
<tr><td valign=top><b>Recipe</b></td><td>%(look)s</td></tr>
<tr><td valign=top><b>Development</b></td><td>%(push)s</td></tr>
<tr><td valign=top><b>Developer</b></td><td>%(developer)s</td></tr>
<tr><td valign=top><b>Process</b></td><td>%(process)s</td></tr>
<tr><td valign=top><b>Expired</b></td><td>%(expired)s</td></tr>
<tr><td valign=top><b>Grain</b></td><td>%(grain)s</td></tr>
<tr><td valign=top><b>Halation</b></td><td>%(halation)s</td></tr>
<tr><td valign=top><b>Light leaks</b></td><td>%(leaks)s</td></tr>
<tr><td valign=top><b>B&amp;W filter</b></td><td>%(filter)s</td></tr>
<tr><td valign=top><b>Toning</b></td><td>%(tone)s</td></tr>
<tr><td valign=top><b>Paper</b></td><td>%(paper)s</td></tr>
<tr><td valign=top><b>Border</b></td><td>%(border)s</td></tr>
<tr><td valign=top><b>Lab correction</b></td><td>%(auto)s</td></tr>
<tr><td valign=top><b>Authentic scan</b></td><td>%(scan)s</td></tr>
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
<h3>The Darkroom: frame by frame</h3>
<p>At the top of the lab, <b>WHOLE ROLL</b> / <b>THIS FRAME</b> says what the settings are for. Under THIS FRAME, anything you change
(the film too, for your own photos) becomes the selected frame's own setting, marked ● on the filmstrip; Ctrl / Shift + click selects
several frames. Right-click a frame to copy its settings and paste them to others (Ctrl+C, Ctrl+V), or to give it the roll's settings
again. <b>PRINT THIS FRAME</b> prints the selected frames on their own: they show in PRINTS, by frame. <b>Develop roll</b> keeps every
frame's own settings.</p>
<h3>Recipe cards</h3>
<p>The <b>Recipe</b> menu holds the lab looks (any film), cards for kinds of photography with their film (portrait, landscape, street,
night, and black and white: Silver gelatin, Dramatic sky, Gritty B&amp;W street, Heirloom), and your own. <b>＋</b> saves the current
settings as a recipe of your own (with the film, for your own photos); <b>⋯</b> imports a recipe someone shared, exports one, or
deletes one of yours. Your recipes are kept in the library's <code>presets</code> folder.</p>
<h3>Mystery rolls</h3>
<p>A <b>MYST</b> roll keeps its film a secret: no name on the roll, a neutral negative on the light table. Develop it to find out.</p>
<h3>Where things go</h3>
<p>The library (<b>Library folder…</b>) holds a copy of each roll (<code>originals</code>) and one folder per development with the prints,
the contact sheet and a lab card of what was done. <b>Lab log</b> lists every development.</p>
<h3>Keys</h3>
<p>Light table and prints: <b>← →</b> previous / next, <b>R</b> / <b>L</b> rotate right / left, <b>Space</b> next view (negative,
original, print preview), <b>F</b> full screen (or double-click). Ctrl / Shift + click selects several frames; <b>Ctrl+C</b> /
<b>Ctrl+V</b> copy and paste a frame's settings.<br>
Full screen: <b>← →</b>, <b>R</b> / <b>L</b>, hold <b>Space</b> for the original, <b>I</b> info, <b>V</b> next view (light table),
<b>C</b> compare two prints of a frame (<b>↑ ↓</b> another, drag the line), <b>Esc</b> close.<br>
The name at the top left goes back to the start screen.</p>
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
        except Exception as e:
            if isinstance(e, RuntimeError) and 'Signal source has been deleted' in str(e):
                return                                                  # the window closed while this was running: nothing to tell
            try:
                self.signals.failed.emit(traceback.format_exc())
            except RuntimeError:
                pass


def mb(n):
    """Bytes as MB (or GB) for people."""
    return '%.1f GB' % (n / 1e9) if n >= 1e9 else '%d MB' % max(1, round(n / 1e6)) if n else '0 MB'


def strip_icon(pm):
    """A filmstrip picture that looks the same selected (Qt would tint a selected icon blue; the red frame shows the selection)."""
    ic = QIcon()
    for mode in (QIcon.Normal, QIcon.Selected, QIcon.Active):
        ic.addPixmap(pm, mode)
    return ic


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

def heic_count(paths):
    """How many HEIC / HEIF photos (the iPhone's format, not supported) are among these files and folders."""
    n = 0
    for p in paths:
        if os.path.isdir(p):
            for _, _, names in os.walk(p):
                n += sum(1 for x in names if x.lower().endswith(('.heic', '.heif')))
        elif p.lower().endswith(('.heic', '.heif')):
            n += 1
    return n


def photos_in(folder):
    """Every photo under a folder (sub-folders too), in name order."""
    paths = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames.sort()
        paths += [os.path.join(dirpath, n) for n in sorted(filenames) if n.lower().endswith(card.IMAGE_EXT)]
    return paths


class LoadPhotos(QDialog):
    """Photos from any camera: pick files or a folder, name the roll, choose the film it is developed as (or a mystery film).
    paths / name: photos already chosen (dropped on the window)."""

    def __init__(self, parent, start_dir, paths=None, name=None):
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
        if paths:
            self._set(paths)
        if name:
            self.name.setText(name)

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
            self._set(photos_in(d))
            if self.name.text().startswith('My roll'):
                self.name.setText(os.path.basename(os.path.normpath(d)))


class SaveCard(QDialog):
    """Save the lab settings as one of your recipe cards: a name, what it is for, a note, and the film (for a roll of your own photos)."""

    def __init__(self, parent, recipe, film=None):
        super().__init__(parent)
        self.setWindowTitle('Save as a recipe card')
        self.setMinimumWidth(460)
        self.recipe = recipe
        lay = QVBoxLayout(self)
        intro = QLabel('Your recipe goes in the Recipe menu under MY RECIPES, and can be exported to share it. Lab settings: %s.'
                       % recipe.describe())
        intro.setWordWrap(True)
        intro.setObjectName('muted')
        lay.addWidget(intro)
        form = QFormLayout()
        self.name = QLineEdit('My recipe')
        self.name.selectAll()
        self.kind = QComboBox()
        for k, v in recipes.KINDS.items():
            self.kind.addItem(v, k)
        if film is not None and film.mono:
            self.kind.setCurrentIndex(self.kind.findData('bw'))
        self.note = QLineEdit()
        self.note.setPlaceholderText('What it is good for (optional)')
        self.with_film = QCheckBox('Include the film (%s)' % film.name if film else 'Include the film (a roll of your own photos only)')
        self.with_film.setChecked(film is not None)
        self.with_film.setEnabled(film is not None)
        self.with_film.setToolTip('With the film, picking this recipe also sets the film of a roll of your own photos. Without it, the '
                                  'recipe is lab settings only, for any film. FAUXJI rolls always keep the film the camera gave them.')
        self.film = film
        form.addRow('Name', self.name)
        form.addRow('For', self.kind)
        form.addRow('Note', self.note)
        form.addRow('', self.with_film)
        lay.addLayout(form)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton('Cancel')
        cancel.clicked.connect(self.reject)
        ok = QPushButton('Save recipe')
        ok.setObjectName('develop')
        ok.clicked.connect(lambda: self.name.text().strip() and self.accept())
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)

    def card(self):
        r = lab.Recipe.from_dict(self.recipe.to_dict())
        r.seed = 0
        return recipes.Card(self.name.text().strip()[:60], r, self.film.code if self.film and self.with_film.isChecked() else None,
                            self.kind.currentData(), self.note.text().strip())


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
        self.setAcceptDrops(True)                                       # photos or a folder dropped anywhere on the window
        self._build()
        self.refresh_library()
        if self.settings.value('skip_start') in (True, 'true') and self.settings.value('mode') in ('photolab', 'darkroom'):
            self.set_mode(self.settings.value('mode'))
        else:
            self.stack.setCurrentWidget(self.start)
        if autoload:                    # a card in the reader, else the FAUXJI card copy / roll opened last time
            last = self.settings.value('source')
            cards = card.find_cards()
            if cards:
                QTimer.singleShot(200, lambda: self.open_source(cards[0]))
            elif last and os.path.isdir(last) and card.find_roll_folders(last):    # not a plain folder of photos: start clean
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
        logo.setCursor(Qt.PointingHandCursor)
        logo.setToolTip('Back to the start screen (Photo Lab or Darkroom)')
        logo.mousePressEvent = lambda e: self.show_start()
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
        self.btn_photos.clicked.connect(lambda: self.load_photos())
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
        # the two ways of working: the switch is always there
        mgroup = QButtonGroup(self)
        self.btn_mode_lab = QPushButton('PHOTO LAB')
        self.btn_mode_dark = QPushButton('DARKROOM')
        self.btn_mode_lab.setToolTip('The simple way: drop off your photos, pick a film and a lab, get the prints back')
        self.btn_mode_dark.setToolTip('Every setting, frame by frame: single prints, versions, picks')
        for b, mode in ((self.btn_mode_lab, 'photolab'), (self.btn_mode_dark, 'darkroom')):
            b.setObjectName('seg')
            b.setCheckable(True)
            mgroup.addButton(b)
            b.clicked.connect(lambda _=False, mode=mode: self.set_mode(mode))
            top.addWidget(b)
        top.addSpacing(10)
        for b in (self.btn_log, self.btn_lib, self.btn_guide):
            top.addWidget(b)
        outer.addLayout(top)
        self.stack = QStackedWidget()                                     # the start screen, the Photo Lab, the Darkroom
        self.start = StartPage(self.settings.value('mode') or 'photolab')
        self.start.always.setChecked(self.settings.value('skip_start') in (True, 'true'))
        self.mode_group = mgroup
        self.start.chosen.connect(self.start_chosen)
        self.photolab = PhotoLab(self)
        self.photolab.open_darkroom.connect(self.darkroom_roll)
        self.stack.addWidget(self.start)
        self.stack.addWidget(self.photolab)
        outer.addWidget(self.stack, 1)

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
        self.roll_title = ElidedLabel('Drop photos to start')
        self.roll_title.setStyleSheet('font-size: 12pt; font-weight: 600; letter-spacing: 2px;')
        self.roll_title.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.roll_sub = ElidedLabel('')
        self.roll_sub.setObjectName('muted')
        corner = QWidget()
        cl = QHBoxLayout(corner)
        cl.setContentsMargins(0, 0, 4, 0)
        cl.addWidget(self.roll_title, 1)
        cl.addSpacing(10)
        cl.addWidget(self.roll_sub)
        self.corner = corner
        self.tabs = QTabWidget()
        self.tabs.tabBar().setUsesScrollButtons(False)
        self.tabs.tabBar().setElideMode(Qt.ElideNone)
        self.tabs.setCornerWidget(corner, Qt.TopRightCorner)
        self.tabs.installEventFilter(self)
        hint = '←  →  frame      R / L  rotate      Space  switch view'
        # light table: the selected frame big, the roll's negatives along the bottom
        self.dview = FrameView([('negative', 'NEGATIVE', 'The developed negative, as it lies on the light table'),
                                ('original', 'ORIGINAL', 'The photo as the camera saved it'),
                                ('print', 'PRINT PREVIEW', 'A test print of this frame with the lab settings on the right; it follows every '
                                                           'change')], hint)
        self.dview.rotate.connect(self.rotate_current)
        self.dview.fullscreen.connect(self.open_fullscreen)
        self.dview.mode_changed.connect(lambda m: self.update_view())
        self.dview.clear('Drop photos or a folder here, or  ＋ Load photos…\n(FAUXJI film camera: Open card)')
        self.lighttable = filmstrip(QSize(128, 119), '#efe9dc')
        self.lighttable.currentItemChanged.connect(lambda *_: self.frame_changed())
        self.lighttable.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.lighttable.itemSelectionChanged.connect(self.selection_changed)
        for keys, fn in (('Ctrl+C', self.copy_settings), ('Ctrl+V', self.paste_settings)):
            sc = QShortcut(QKeySequence(keys), self.lighttable)
            sc.setContext(Qt.WidgetShortcut)
            sc.activated.connect(fn)
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
        self.pview.fullscreen.connect(self.open_fullscreen)
        self.pview.clear('No prints yet: develop the roll')
        self.prints = filmstrip(QSize(128, 100), '#1b1a1a')
        self.prints.currentItemChanged.connect(lambda *_: (self.show_print(), self.update_versions_combo()))
        self.prints.setContextMenuPolicy(Qt.CustomContextMenu)
        self.prints.customContextMenuRequested.connect(self.prints_menu)
        self.lighttable.itemDoubleClicked.connect(lambda *_: self.open_fullscreen())      # a double-clicked frame: full screen
        self.prints.itemDoubleClicked.connect(lambda *_: self.open_fullscreen())
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
        prow.setSpacing(4)
        # two ways to look at the prints: one development at a time, or frame by frame across every development (your picks)
        self.print_mode = 'dev'
        group = QButtonGroup(self)
        self.btn_by_dev = QPushButton('DEVELOPMENTS')
        self.btn_by_frame = QPushButton('BY FRAME')
        self.btn_by_dev.setToolTip('One development at a time: every print it made.')
        self.btn_by_frame.setToolTip('Frame by frame: every print of each frame, from every development. Choose the one you like best '
                                     '(✓ Use this print) and export your picks as one roll.')
        for b, mode in ((self.btn_by_dev, 'dev'), (self.btn_by_frame, 'frame')):
            b.setObjectName('seg')
            b.setCheckable(True)
            group.addButton(b)
            b.clicked.connect(lambda _=False, mode=mode: self.set_print_mode(mode))
            prow.addWidget(b)
        self.btn_by_dev.setChecked(True)
        prow.addSpacing(6)
        self.dev_pick = QComboBox()
        self.dev_pick.setToolTip('Every development of this roll is kept: pick one to see its prints. ★ = a favourite.')
        self.dev_pick.currentIndexChanged.connect(self.show_development)
        self.ver_pick = QComboBox()
        self.ver_pick.setToolTip('Every print of this frame, newest first. ✓ = your pick (what Export my picks uses), ★ = a favourite '
                                 'development.')
        self.ver_pick.activated.connect(self.version_chosen)
        self.ver_pick.setVisible(False)
        for c in (self.dev_pick, self.ver_pick):
            c.view().setMinimumWidth(460)                           # the names are long: the open menu shows them whole
        prow.addWidget(self.dev_pick, 1)
        prow.addWidget(self.ver_pick, 1)
        self.btn_use = QPushButton('✓ Use this print')
        self.btn_use.setStyleSheet('padding: 6px 8px')
        self.btn_use.setToolTip('Make this print your pick for the frame: Export my picks takes it.')
        self.btn_use.clicked.connect(self.use_this_print)
        self.btn_use.setVisible(False)
        prow.addWidget(self.btn_use)
        self.btn_versions = QPushButton('⋯')
        self.btn_versions.setFixedWidth(28)
        self.btn_versions.setStyleSheet('padding: 4px 0')
        self.btn_versions.setToolTip('This development: rename, favourite, delete; clean up old developments; disk use')
        self.btn_versions.clicked.connect(self.versions_menu)
        prow.addWidget(self.btn_versions)
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
        for keys, fn in ((('R',), lambda: self.rotate_current(90)), (('L',), lambda: self.rotate_current(-90)), (('F',), self.open_fullscreen),
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
        # the Darkroom: the settings are the whole roll's, or the selected frame's (frames can have their own film and lab settings)
        self.scope = 'roll'
        srow = QHBoxLayout()
        srow.setSpacing(0)
        sgroup = QButtonGroup(self)
        self.btn_scope_roll = QPushButton('WHOLE ROLL')
        self.btn_scope_frame = QPushButton('THIS FRAME')
        self.btn_scope_roll.setToolTip(TIPS['scope'])
        self.btn_scope_frame.setToolTip(TIPS['scope'])
        for b, sc in ((self.btn_scope_roll, 'roll'), (self.btn_scope_frame, 'frame')):
            b.setObjectName('seg')
            b.setCheckable(True)
            sgroup.addButton(b)
            b.clicked.connect(lambda _=False, sc=sc: self.set_scope(sc))
            srow.addWidget(b, 1)
        self.btn_scope_roll.setChecked(True)
        rl.addLayout(srow)
        self.scope_note = QLabel('')
        self.scope_note.setObjectName('muted')
        self.scope_note.setWordWrap(True)
        rl.addWidget(self.scope_note)
        self.btn_roll_settings = QPushButton("Use the roll's settings again")
        self.btn_roll_settings.setToolTip("Forget this frame's own settings: it is printed like the rest of the roll")
        self.btn_roll_settings.clicked.connect(self.clear_frame_settings)
        rl.addWidget(self.btn_roll_settings)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        # the recipe: lab looks (any film), cards for kinds of photography (with their film), your own cards; Custom when nothing matches
        self.c_look = QComboBox()
        self.c_look.setMaxVisibleItems(30)
        self.c_look.activated.connect(self.apply_card)
        self.btn_save_card = QPushButton('＋')
        self.btn_save_card.setStyleSheet('padding: 4px 0')
        self.btn_save_card.setFixedWidth(28)
        self.btn_save_card.setToolTip(TIPS['save_card'])
        self.btn_save_card.clicked.connect(self.save_card_dialog)
        self.btn_cards = QPushButton('⋯')
        self.btn_cards.setStyleSheet('padding: 4px 0')
        self.btn_cards.setFixedWidth(28)
        self.btn_cards.setToolTip('Recipe cards: import one, export this one to share it, delete one of yours')
        self.btn_cards.clicked.connect(self.cards_menu)
        look_row = QWidget()
        lr = QHBoxLayout(look_row)
        lr.setContentsMargins(0, 0, 0, 0)
        lr.setSpacing(4)
        lr.addWidget(self.c_look, 1)
        lr.addWidget(self.btn_save_card)
        lr.addWidget(self.btn_cards)
        self.c_film = QComboBox()
        for f in films.FILMS:
            self.c_film.addItem(f.name, f.code)
        self.c_film.addItem('Mystery (secret)', films.MYSTERY.code)
        self.c_film.setToolTip('The film this roll of photos is developed as (rolls loaded with "Load photos…" only: FAUXJI rolls '
                               'already carry their film from the camera). Mystery picks a new secret film.')
        self.c_film.activated.connect(self.film_changed)
        form.addRow('Film', self.c_film)
        self.film_row_label = form.labelForField(self.c_film)
        form.addRow('Recipe', look_row)
        self.look_label = form.labelForField(look_row)
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
        self.recipe_timer = QTimer(self)                                # a moved slider: the preview follows a moment later
        self.recipe_timer.setSingleShot(True)
        self.recipe_timer.setInterval(250)
        self.recipe_timer.timeout.connect(self.recipe_changed)
        slider_rows = {}
        for s in (self.c_grain, self.c_hal):
            w = QWidget()
            hl = QHBoxLayout(w)
            hl.setContentsMargins(0, 0, 0, 0)
            val = QLabel('100 %')
            val.setObjectName('muted')
            val.setFixedWidth(46)
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            hl.addWidget(s, 1)
            hl.addWidget(val)
            s.valueChanged.connect(lambda v, val=val: (val.setText('%d %%' % v),
                                                       None if getattr(self, '_quiet', False) else self.recipe_timer.start()))
            slider_rows[s] = w
        self.c_leaks = QCheckBox('Light leaks')
        self.c_leaks.setChecked(True)
        self.c_paper = self._combo(lab.PAPERS)
        self.c_border = self._combo(lab.BORDERS)
        self.c_auto = QCheckBox('Lab correction')
        self.c_scan = QCheckBox('Authentic scan')
        self.c_filter = self._combo(lab.BW_FILTERS)
        self.c_tone = self._combo(lab.TONES)
        self.c_size = QComboBox()
        for label, v in (('Full size', 0), ('Large (2400 px)', 2400), ('Web (1600 px)', 1600)):
            self.c_size.addItem(label, v)
        form.addRow('Development', self.c_push)
        form.addRow('Developer', self.c_dev)
        form.addRow('Process', self.c_proc)
        form.addRow('Expired', self.c_exp)
        form.addRow('Grain', slider_rows[self.c_grain])
        form.addRow('Halation', slider_rows[self.c_hal])
        self.slider_labels = {self.c_grain: form.labelForField(slider_rows[self.c_grain]),
                              self.c_hal: form.labelForField(slider_rows[self.c_hal])}
        form.addRow('', self.c_leaks)
        form.addRow('B&&W filter', self.c_filter)
        form.addRow('Toning', self.c_tone)
        form.addRow('Paper', self.c_paper)
        form.addRow('Border', self.c_border)
        form.addRow('', self.c_auto)
        form.addRow('', self.c_scan)
        form.addRow('Print size', self.c_size)
        lab_inner = QWidget()
        lab_inner.setObjectName('labform')
        lab_inner.setStyleSheet('QWidget#labform { background: #1b1a1a; }')
        self.lab_inner_layout = QVBoxLayout(lab_inner)
        self.lab_inner_layout.setContentsMargins(0, 0, 4, 0)
        self.lab_inner_layout.addLayout(form)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        for c in lab_inner.findChildren(QComboBox):                     # the menus shorten their text instead of widening the panel
            c.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            c.setMinimumContentsLength(8)
        lab_area = QScrollArea()
        lab_area.setWidgetResizable(True)
        lab_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lab_area.setStyleSheet('QScrollArea { border: none; background: #1b1a1a; }')
        lab_area.setWidget(lab_inner)
        rl.addWidget(lab_area, 1)
        self.look_label.setToolTip(TIPS['look'])
        self.c_look.setToolTip(TIPS['look'])
        for w, key in ((self.c_push, 'push'), (self.c_dev, 'developer'), (self.c_proc, 'process'), (self.c_exp, 'expired'),
                       (self.c_grain, 'grain'), (self.c_hal, 'halation'), (self.c_leaks, 'leaks'), (self.c_paper, 'paper'),
                       (self.c_border, 'border'), (self.c_auto, 'auto'), (self.c_scan, 'scan'), (self.c_size, 'size'), (self.c_filter, 'filter'),
                       (self.c_tone, 'tone')):
            w.setToolTip(TIPS[key])
            lbl = form.labelForField(w)
            if lbl is not None:
                lbl.setToolTip(TIPS[key])
        for w in (self.c_push, self.c_dev, self.c_proc, self.c_paper, self.c_border, self.c_filter, self.c_tone):
            w.currentIndexChanged.connect(lambda *_: self.recipe_changed())
        for w, key in ((self.c_grain, 'grain'), (self.c_hal, 'halation')):
            self.slider_labels[w].setToolTip(TIPS[key])
        self.c_exp.valueChanged.connect(lambda *_: self.recipe_changed())
        self.c_leaks.toggled.connect(lambda *_: self.recipe_changed())
        self.c_auto.toggled.connect(lambda *_: self.recipe_changed())
        self.c_scan.toggled.connect(lambda *_: self.recipe_changed())
        row = QHBoxLayout()
        b = QPushButton('Surprise me')
        b.setToolTip(TIPS['surprise'])
        b.clicked.connect(self.surprise)
        b2 = QPushButton('Reset')
        b2.setToolTip(TIPS['reset'])
        b2.clicked.connect(lambda: self.set_recipe(lab.Recipe()))
        row.addWidget(b)
        row.addWidget(b2)
        self.lab_inner_layout.addLayout(row)
        self.lab_inner_layout.addStretch(1)
        self.btn_print = QPushButton('PRINT THIS FRAME')
        self.btn_print.setToolTip(TIPS['print'])
        self.btn_print.setStyleSheet('QPushButton { font-weight: 600; letter-spacing: 2px; padding: 9px; border-color: #5a2b28; }'
                                     ' QPushButton:hover { border-color: %s; }' % RED)
        self.btn_print.clicked.connect(self.print_selected)
        rl.addWidget(self.btn_print)
        self.btn_develop = QPushButton('DEVELOP ROLL')
        self.btn_develop.setObjectName('develop')
        self.btn_develop.clicked.connect(self.develop)
        self.btn_develop.setToolTip(TIPS['develop'])
        rl.addWidget(self.btn_develop)
        right.setMinimumWidth(300)
        right.setMaximumWidth(380)
        split.addWidget(right)
        split.setSizes([280, 800, 340])
        self.stack.addWidget(split)
        self.darkroom = split
        self.mode = 'start'
        self.setCentralWidget(root)
        self.refresh_cards()
        self.set_recipe(lab.Recipe())                                    # the vintage print look
        self.show_film_menu(None)
        self.update_scope_ui()

    def show_film_menu(self, r):
        """The Film menu is always in the lab. Photos from any camera: pick the film. A FAUXJI roll: the camera already applied its
        film's look, so the menu shows that film, greyed out, and says why."""
        own = bool(r is not None and getattr(r, 'own', False))
        self.c_film.setEnabled(own)
        if r is None:
            self.c_film.setToolTip('The film a roll of your own photos is developed as. Open or load a roll first.')
            return
        film = r.film if own else r.true_film
        i = self.c_film.findData(film.code)
        if i >= 0:
            self.c_film.setCurrentIndex(i)
        if own:
            self.c_film.setToolTip('The film this roll is developed as. Mystery picks a new secret film. THIS FRAME: the film of the '
                                   'selected frame(s) only.')
        else:
            name = 'a secret film' if self.secret() else film.name
            self.c_film.setToolTip('The FAUXJI camera already gave these photos the look of %s when it took them, so the lab cannot '
                                   'change the film. Photos from another camera (Load photos…) can be developed on any film.' % name)

    def eventFilter(self, obj, e):
        if obj is getattr(self, 'tabs', None) and e.type() == QEvent.Resize:
            self.fit_corner()
        return super().eventFilter(obj, e)

    def fit_corner(self):
        """The roll's name and details beside the tabs get the room the tabs leave: the details go first, then the name shortens."""
        room = self.tabs.width() - self.tabs.tabBar().sizeHint().width() - 24
        title = self.roll_title.sizeHint().width()
        sub = self.roll_sub.sizeHint().width() if self.roll_sub.text() else 0
        self.roll_sub.setVisible(bool(sub) and room >= title + sub + 14)
        self.corner.setFixedWidth(max(60, min(room, title + (sub + 14 if self.roll_sub.isVisible() or (sub and room >= title + sub + 14)
                                                              else 0) + 8)))

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
                          auto_levels=self.c_auto.isChecked(), bw_filter=self.c_filter.currentData(), tone=self.c_tone.currentData(),
                          authentic=self.c_scan.isChecked())

    def set_recipe(self, r):
        self._quiet = True
        for combo, v in ((self.c_push, r.push), (self.c_dev, r.developer), (self.c_proc, r.process), (self.c_paper, r.paper),
                         (self.c_border, r.border), (self.c_filter, r.bw_filter), (self.c_tone, r.tone)):
            combo.setCurrentIndex(max(0, combo.findData(v)))
        self.c_exp.setValue(r.expired)
        self.c_grain.setValue(round(r.grain * 100))
        self.c_hal.setValue(round(r.halation * 100))
        self.c_leaks.setChecked(r.leaks)
        self.c_auto.setChecked(r.auto_levels)
        self.c_scan.setChecked(r.authentic)
        self._quiet = False
        self.recipe_changed()

    def surprise(self):
        self.set_recipe(lab.surprise(random.Random()))
        self.notify('The lab picked: ' + self.recipe().describe(), 6000)

    def recipe_changed(self):
        if getattr(self, '_quiet', False):
            return
        if self.scope == 'frame' and not getattr(self, '_loading', False):
            self.save_frame_settings()
        self.show_matching_card()
        if self.dview.mode == 'print':
            self.update_view()

    # ------------------------------------------------------------ recipe cards
    def roll_film_code(self):
        """The film the selected roll (THIS FRAME: the frame) is developed as, for matching cards (None when there is no roll or it is
        a secret)."""
        if self.roll is None or self.secret():
            return None
        f = self.selected_frame()
        if self.scope == 'frame' and f is not None:
            return self.frame_effective(f)[1].code
        return self.roll.true_film.code

    # ------------------------------------------------------------ the Darkroom: frames with their own settings
    def roll_recipe_now(self):
        """The whole roll's lab settings (THIS FRAME keeps them aside while the panel shows the frame's)."""
        return self.recipe() if self.scope == 'roll' else lab.Recipe.from_dict(self.roll_recipe.to_dict())

    def frame_effective(self, f):
        """(recipe, film) the frame is printed with: its own settings, else the roll's."""
        return self.library.effective(self.roll, f, self.roll_recipe_now(), getattr(self, 'fsettings', {}).get(f.number))

    def selected_frames(self):
        """The frames selected on the light table (the current one when nothing else is), in roll order."""
        fs = [it.data(Qt.UserRole) for it in self.lighttable.selectedItems()]
        cur = self.selected_frame()
        if cur is not None and cur not in fs:
            fs.append(cur)
        return sorted(fs, key=lambda f: f.number)

    def set_scope(self, scope):
        """WHOLE ROLL / THIS FRAME: what the lab panel's settings are for."""
        if self.roll is None and scope == 'frame':
            scope = 'roll'
        if scope == self.scope:
            self.update_scope_ui()
            return
        if scope == 'frame':
            self.roll_recipe = self.recipe()
            self.scope = 'frame'
            self.load_frame_panel()
        else:
            self.scope = 'roll'
            self._load_panel(self.roll_recipe)
            if self.roll is not None and self.roll.own:
                self.c_film.setCurrentIndex(max(0, self.c_film.findData(self.roll.film.code)))
            self.show_matching_card()
            if self.dview.mode == 'print':
                self.update_view()
        self.update_scope_ui()

    def _load_panel(self, r):
        self._loading = True
        try:
            self.set_recipe(r)
        finally:
            self._loading = False

    def load_frame_panel(self):
        """THIS FRAME: the panel shows the selected frame's settings (its own, else the roll's until something is changed)."""
        f = self.selected_frame()
        if f is None:
            return
        r, film = self.frame_effective(f)
        self._load_panel(r)
        if self.roll.own and not self.secret():
            self.c_film.setCurrentIndex(max(0, self.c_film.findData(film.code)))
        self.show_matching_card()
        self.update_scope_ui()
        if self.dview.mode == 'print':
            self.update_view()

    def frame_changed(self):
        if self.scope == 'frame':
            self.load_frame_panel()
        else:
            self.update_view()
        self.update_scope_ui()

    def selection_changed(self):
        self.update_scope_ui()

    def save_frame_settings(self, film=None):
        """THIS FRAME: the panel's settings become the selected frames' own (the same as the roll's: they follow the roll again)."""
        if self.roll is None:
            return
        frames = self.selected_frames()
        if not frames:
            return
        r = self.recipe()
        rid = self.roll_key()
        changed = []
        for f in frames:
            old = self.fsettings.get(f.number)
            code = film or (old or {}).get('film') if self.roll.own else None
            same_film = not code or code == (f.film or self.roll.true_film).code
            same = {k: v for k, v in r.to_dict().items() if k != 'seed'} == \
                {k: v for k, v in self.roll_recipe.to_dict().items() if k != 'seed'}
            self.library.set_frame_settings(rid, [f.number], None if (same and same_film) else r, None if same_film else code)
            changed.append(f.number)
        self.fsettings = self.library.frame_settings(rid)
        self.refresh_marks(changed)
        self.update_scope_ui()

    def clear_frame_settings(self, frames=None):
        """Selected frames back to the roll's settings."""
        if self.roll is None:
            return
        nums = [f.number for f in (frames or self.selected_frames())]
        self.library.set_frame_settings(self.roll_key(), nums, None)
        self.fsettings = self.library.frame_settings(self.roll_key())
        self.refresh_marks(nums)
        if self.scope == 'frame':
            self.load_frame_panel()
        elif self.dview.mode == 'print':
            self.update_view()
        self.update_scope_ui()
        self.notify("%s printed with the roll's settings again" % self.frames_text(nums), 5000)

    @staticmethod
    def frames_text(nums):
        nums = sorted(nums)
        return 'Frame %d' % nums[0] if len(nums) == 1 else 'Frames ' + ', '.join(str(n) for n in nums)

    def copy_settings(self):
        f = self.selected_frame()
        if f is None or self.roll is None:
            return
        r, film = self.frame_effective(f) if self.scope == 'roll' else (self.recipe(), self.frame_effective(f)[1])
        self.clip = (lab.Recipe.from_dict(r.to_dict()), film.code if self.roll.own else None, f.number)
        self.notify('Copied the settings of frame %d: select frames and paste them (Ctrl+V, or right-click)' % f.number, 6000)
        self.update_scope_ui()

    def paste_settings(self):
        clip = getattr(self, 'clip', None)
        if clip is None or self.roll is None:
            return
        r, code, src = clip
        frames = [f for f in self.selected_frames() if f.number != src] or self.selected_frames()
        rid = self.roll_key()
        roll_r = self.roll_recipe_now()
        same = {k: v for k, v in r.to_dict().items() if k != 'seed'} == {k: v for k, v in roll_r.to_dict().items() if k != 'seed'}
        for f in frames:
            film = code if (self.roll.own and code and code != (f.film or self.roll.true_film).code) else None
            self.library.set_frame_settings(rid, [f.number], None if (same and not film) else r, film)
        self.fsettings = self.library.frame_settings(rid)
        self.refresh_marks([f.number for f in frames])
        if self.scope == 'frame':
            self.load_frame_panel()
        elif self.dview.mode == 'print':
            self.update_view()
        self.update_scope_ui()
        self.notify('Pasted the settings of frame %d to %s' % (src, self.frames_text([f.number for f in frames]).lower()), 5000)

    def refresh_marks(self, nums):
        """Redraw the filmstrip pictures of these frames (the ● for a frame with its own settings)."""
        turns = self.library.rotations(self.roll_key())
        items = [(k, self.lighttable.item(k).data(Qt.UserRole)) for k in range(self.lighttable.count())
                 if self.lighttable.item(k).data(Qt.UserRole).number in set(nums)]

        token = getattr(self, '_neg_token', None)

        def work(report):
            for k, f in items:
                report((token, k, self.neg_thumb(f, turns.get(f.number, 0))))

        self.run(work, lambda _: None, progress=self._neg_ready)

    def update_scope_ui(self):
        """The scope buttons, the note under them, and the print button's text."""
        frames = self.selected_frames() if self.roll is not None else []
        own = getattr(self, 'fsettings', {}) if self.roll is not None else {}
        n = len(frames)
        self.btn_scope_frame.setText('THIS FRAME' if n <= 1 else '%d FRAMES' % n)
        self.btn_scope_frame.setEnabled(self.roll is not None)
        (self.btn_scope_roll if self.scope == 'roll' else self.btn_scope_frame).setChecked(True)
        mine = [f.number for f in frames if f.number in own]
        if self.roll is None:
            note = 'Settings for the whole roll. PRINT PREVIEW (above the picture) shows them on the selected frame.'
        elif self.scope == 'roll':
            note = 'Settings for the whole roll%s. PRINT PREVIEW shows a frame as it will print.' % (
                ' except %s (● on the filmstrip: their own settings)' % self.frames_text(own).lower() if own else '')
        else:
            what = self.frames_text([f.number for f in frames])
            note = '%s only%s. Change anything and it is %s own; the rest of the roll keeps its settings.' % (
                what, ': its own settings' if mine and n == 1 else (': own settings' if mine else ": the roll's so far"),
                'its' if n == 1 else 'their')
        self.scope_note.setText(note)
        self.btn_roll_settings.setVisible(self.scope == 'frame' and bool(mine))
        self.btn_print.setText('PRINT THIS FRAME' if n <= 1 else 'PRINT %d FRAMES' % n)
        self._update_buttons()

    def refresh_cards(self):
        """Fill the recipe menu: lab looks, cards for kinds of photography, your own cards, Custom."""
        self.cards = {}
        self.c_look.blockSignals(True)
        self.c_look.clear()
        model = self.c_look.model()

        def header(text):
            self.c_look.addItem(text, None)
            it = model.item(self.c_look.count() - 1)
            it.setEnabled(False)
            it.setForeground(QColor('#d9a19a'))
            f = it.font()
            f.setPointSize(8)
            f.setLetterSpacing(QFont.AbsoluteSpacing, 1)
            it.setFont(f)

        def add(key, c, text):
            self.cards[key] = c
            self.c_look.addItem(text, key)
            self.c_look.setItemData(self.c_look.count() - 1, c.note or c.label(), Qt.ToolTipRole)

        header('LAB LOOKS  ·  any film')
        for c in recipes.LOOKS:
            add(c.name, c, c.name + ('   (default)' if c.name == 'Vintage print' else ''))
        header('FOR KINDS OF PHOTOGRAPHY')
        for c in recipes.BUILTIN:
            add('card:' + c.name, c, c.label())
        mine = self.library.recipe_cards()
        if mine:
            header('MY RECIPES')
            for c in mine:
                add('my:' + c.name, c, c.label())
        self.c_look.addItem('Custom', 'custom')
        self.c_look.blockSignals(False)
        self.show_matching_card()

    def current_card(self):
        return self.cards.get(self.c_look.currentData())

    def show_matching_card(self, prefer=None):
        """Show the card the lab settings (and the roll's film) match, else Custom."""
        c = recipes.find(list(self.cards.values()), self.recipe(), self.roll_film_code(), prefer=prefer or self.current_card())
        key = next((k for k, v in self.cards.items() if v is c), 'custom')
        self.c_look.blockSignals(True)
        self.c_look.setCurrentIndex(self.c_look.findData(key))
        self.c_look.blockSignals(False)
        self.update_bw_controls()

    def apply_card(self, i):
        """A card picked in the recipe menu: its lab settings, and its film for a roll of your own photos."""
        c = self.cards.get(self.c_look.itemData(i))
        if c is None:
            self.show_matching_card()
            return
        self.set_recipe(c.recipe)
        if c.film and self.roll is not None:
            if getattr(self.roll, 'own', False) and self.scope == 'frame':
                self.set_frame_film(c.film)
            elif getattr(self.roll, 'own', False):
                if self.roll.true_film.code != c.film or self.secret():
                    self.set_roll_film(c.film)
            else:
                self.notify('%s is a %s card: a FAUXJI roll keeps the film the camera gave it, so only its lab settings are used'
                            % (c.name, c.film_obj.name), 8000)
        self.show_matching_card(prefer=c)

    def update_bw_controls(self):
        """The B&W filter works on black-and-white films for photos from other cameras; toning on any black-and-white film. A secret
        film keeps both open (greying them out would give it away)."""
        r = self.roll
        if r is None:
            filt = tone = True
        else:
            mono = self.secret() or r.true_film.mono
            filt, tone = mono and bool(getattr(r, 'own', False)), mono
        self.c_filter.setEnabled(filt)
        self.c_tone.setEnabled(tone)

    def save_card_dialog(self):
        own = self.roll is not None and getattr(self.roll, 'own', False) and not self.secret()
        dlg = SaveCard(self, self.recipe(), self.roll.true_film if own else None)
        if not dlg.exec():
            return
        c = dlg.card()
        if c.name.lower() in {x.name.lower() for x in recipes.LOOKS + recipes.BUILTIN}:
            QMessageBox.information(self, APP_NAME, '"%s" is the name of a built-in recipe: please pick another name.' % c.name)
            return
        if any(x.name.lower() == c.name.lower() for x in self.library.recipe_cards()):
            if QMessageBox.question(self, APP_NAME, 'You already have a recipe called "%s". Replace it?' % c.name) != QMessageBox.Yes:
                return
        self.library.save_card(c)
        self.refresh_cards()
        self.c_look.setCurrentIndex(self.c_look.findData('my:' + c.name))
        self.notify('Saved "%s" to your recipes' % c.name)

    def cards_menu(self):
        c = self.current_card()
        m = QMenu(self)
        m.addAction('Import a recipe card…', self.import_card)
        a = m.addAction('Export "%s" to share it…' % c.name if c else 'Export… (save the settings as a recipe first)', self.export_card)
        a.setEnabled(c is not None)
        mine = self.c_look.currentData() or ''
        d = m.addAction('Delete "%s"' % c.name if c and mine.startswith('my:') else 'Delete (only your own recipes)', self.delete_card)
        d.setEnabled(bool(c) and mine.startswith('my:'))
        m.addSeparator()
        m.addAction('Show the recipes folder', lambda: (os.makedirs(self.library.presets_dir(), exist_ok=True),
                                                        QDesktopServices.openUrl(QUrl.fromLocalFile(self.library.presets_dir()))))
        m.exec(self.btn_cards.mapToGlobal(self.btn_cards.rect().bottomLeft()))

    def import_card(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Import a recipe card', os.path.expanduser('~'), 'Recipe cards (*.json)')
        if not path:
            return
        try:
            c = self.library.import_card(path)
        except ValueError:
            QMessageBox.information(self, APP_NAME, 'That file is not a Sajin Genzō recipe card.')
            return
        self.refresh_cards()
        i = self.c_look.findData('my:' + c.name)
        self.c_look.setCurrentIndex(i)
        self.apply_card(i)
        self.notify('Imported "%s"' % c.name)

    def export_card(self):
        c = self.current_card()
        if c is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Export the recipe card', os.path.join(os.path.expanduser('~'),
                                              recipes.slug(c.name) + '.json'), 'Recipe cards (*.json)')
        if path:
            Library._write(path, c.to_dict())
            self.notify('Exported "%s" to %s' % (c.name, path), 8000)

    def delete_card(self):
        c = self.current_card()
        if c is None or not (self.c_look.currentData() or '').startswith('my:'):
            return
        if QMessageBox.question(self, APP_NAME, 'Delete your recipe "%s"? Prints made with it are kept.' % c.name) != QMessageBox.Yes:
            return
        self.library.delete_card(c.name)
        self.refresh_cards()
        self.notify('Deleted "%s"' % c.name)

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

    # ------------------------------------------------------------ the two ways: Photo Lab and Darkroom
    def set_mode(self, mode):
        """Show the Photo Lab or the Darkroom (remembered for next time)."""
        self.mode = mode
        self.stack.setCurrentWidget(self.photolab if mode == 'photolab' else self.darkroom)
        (self.btn_mode_lab if mode == 'photolab' else self.btn_mode_dark).setChecked(True)
        self.settings.setValue('mode', mode)
        if mode == 'photolab' and self.photolab.pages.currentIndex() == 0:
            self.photolab.refresh_rolls()
        if mode == 'darkroom' and getattr(self, 'library_dirty', False):   # the Photo Lab developed or loaded something meanwhile
            self.library_dirty = False
            key = self.roll_key() if self.roll is not None and self.roll_in_library else None
            self.refresh_library()
            if key:
                self.select_library_roll(key)

    def show_start(self):
        """The start screen again (the name at the top left): choose the way, or change 'open straight in'."""
        if self.busy:
            return
        self.mode = 'start'
        self.start.set_last(self.settings.value('mode') or 'photolab')
        self.start.always.setChecked(self.settings.value('skip_start') in (True, 'true'))
        self.mode_group.setExclusive(False)
        self.btn_mode_lab.setChecked(False)
        self.btn_mode_dark.setChecked(False)
        self.mode_group.setExclusive(True)
        self.stack.setCurrentWidget(self.start)

    def start_chosen(self, mode):
        self.settings.setValue('skip_start', self.start.always.isChecked())
        self.set_mode(mode)

    def darkroom_roll(self, rid, folder):
        """From the Photo Lab's prints: the same roll in the Darkroom, on that development."""
        self.library_dirty = False
        self.set_mode('darkroom')
        self.refresh_library()
        self.select_library_roll(rid)
        if folder:
            self.set_print_mode('dev')
            i = self.dev_pick.findData(folder)
            if i >= 0:
                self.dev_pick.setCurrentIndex(i)
            self.tabs.setCurrentIndex(1)

    # ------------------------------------------------------------ drag and drop: photos (or a FAUXJI card copy) onto the window
    def dragEnterEvent(self, e):
        if not self.busy and e.mimeData().hasUrls() and any(u.isLocalFile() for u in e.mimeData().urls()):
            e.acceptProposedAction()

    def dropEvent(self, e):
        dropped = [os.path.normpath(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()]
        e.acceptProposedAction()
        if self.busy:
            self.notify('The lab is busy: drop the photos again when it is done')
        if self.busy or not dropped:
            return
        if len(dropped) == 1 and os.path.isdir(dropped[0]) and card.find_roll_folders(dropped[0]):
            self.open_source(dropped[0])                                # a FAUXJI card copy, FILMS folder or roll
            if self.mode == 'start':
                self.set_mode('photolab')
            return
        paths = []
        for p in dropped:
            paths += photos_in(p) if os.path.isdir(p) else ([p] if p.lower().endswith(card.IMAGE_EXT) else [])
        heic = heic_count(dropped)
        if not paths:
            self.notify('No photos in what was dropped (JPEG, PNG, TIFF, WebP)' if not heic else
                        'HEIC photos (iPhone) cannot be opened yet: export them as JPEG first', 10000)
            if heic:
                QMessageBox.information(self, APP_NAME, 'These are HEIC photos (the iPhone\'s format), which Sajin Genzō cannot open '
                                        'yet.\n\nExport or send them as JPEG first (on the iPhone: Settings, Camera, Formats, Most '
                                        'Compatible; or share them as JPEG), then drop them again.')
            return
        if heic:
            self.notify('%d HEIC photo%s left out (cannot be opened yet: export as JPEG)' % (heic, '' if heic == 1 else 's'), 10000)
        name = os.path.basename(dropped[0]) if len(dropped) == 1 and os.path.isdir(dropped[0]) else None
        if self.mode != 'darkroom':                                     # the start screen and the Photo Lab: its drop off
            self.set_mode('photolab')
            self.photolab.take_photos(paths, name)
            return
        QTimer.singleShot(0, lambda: self.load_photos(paths, name))     # after the drop, so the file manager is not held up

    def load_photos(self, paths=None, name=None):
        if self.busy:
            self.notify('The lab is busy: load the photos when it is done')
            return
        dlg = LoadPhotos(self, self.settings.value('photos') or os.path.expanduser('~'), paths, name)
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
        if self.scope == 'frame':
            return self.set_frame_film(self.c_film.itemData(i))
        self.set_roll_film(self.c_film.itemData(i))

    def set_frame_film(self, code):
        """THIS FRAME: the selected frames are printed on another film (photos from other cameras). Mystery is for whole rolls."""
        f = self.selected_frame()
        if f is None or self.roll is None or not self.roll.own:
            return
        if code == films.MYSTERY.code:
            self.notify('Mystery film is for a whole roll: choose it under WHOLE ROLL', 6000)
            self.c_film.setCurrentIndex(max(0, self.c_film.findData(self.frame_effective(f)[1].code)))
            return
        self.save_frame_settings(film=code)
        self.c_film.setCurrentIndex(max(0, self.c_film.findData(code)))
        self.show_matching_card()
        self.update_bw_controls()
        if self.dview.mode == 'print':
            self.update_view()
        self.notify('%s on %s' % (self.frames_text([x.number for x in self.selected_frames()]), films.BY_CODE[code].name), 5000)

    def set_roll_film(self, code):
        """Develop the selected roll of your own photos as another film (the Film menu, or a recipe card with a film)."""
        if self.roll is None or not self.roll.own:
            return
        rid = self.roll_key()
        self.library.set_film(rid, code)
        self.refresh_library()
        self.select_library_roll(rid)
        self.notify('Developed as %s from now on' % (self.c_film.itemText(max(0, self.c_film.findData(code)))))

    def pick_library(self):
        d = QFileDialog.getExistingDirectory(self, 'Library folder (imported rolls and prints)', self.library.root)
        if d:
            self.library = Library(d)
            self.settings.setValue('library', d)
            self.refresh_library()
            self.refresh_cards()

    def open_source(self, path):
        self.settings.setValue('source', path)
        self.notify('Reading %s …' % path)
        self.run(lambda report: card.scan(path), self._source_loaded, extra=path)

    def _source_loaded(self, rolls, path):
        if card.is_plain_folder(rolls):                                 # ordinary photos: Load photos, with the film to choose
            self.source_rolls = []
            self.refresh_tree()
            paths = [f.path for r in rolls for f in r.frames]
            self.notify('%d photos from another camera: choose the film they are developed on' % len(paths), 8000)
            QTimer.singleShot(0, lambda: self.load_photos(paths, os.path.basename(os.path.normpath(path))))
            return
        self.source_rolls = rolls
        self.source_path = path
        self.start.set_card(len(rolls) if card.find_roll_folders(path) else 0)
        if self.photolab.pages.currentIndex() == 0:
            self.photolab.refresh_rolls()
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
            secret = film is films.MYSTERY and not self.library.revealed(rid)
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
        if self.scope == 'frame':                                       # another roll: back to the whole roll's settings
            self.scope = 'roll'
            self._load_panel(self.roll_recipe)
        self.fsettings = self.library.frame_settings(self.roll_key())
        own = bool(getattr(r, 'own', False))
        self.show_film_menu(r)
        # photos from another camera have no negative worth looking at: they open on the print preview. A FAUXJI roll opened after
        # them goes back to its negatives.
        if own:
            self.dview.set_mode('print')
        elif getattr(self, '_own_shown', False):
            self.dview.set_mode('negative')
        self._own_shown = own
        film = self.shown_film()
        self.roll_title.setText('%s  ·  %s' % (film.name.upper() if not self.secret() else 'MYSTERY  ???', r.name or r.code))
        span = ''
        if r.first:
            span = r.first.strftime('%d %b %Y') + ('' if not r.last or r.last.date() == r.first.date() else ' – ' + r.last.strftime('%d %b %Y'))
        parts = ['%d / 36' % len(r.frames) if len(r.frames) <= 36 else '%d frames' % len(r.frames), span,
                 'my photos' if r.own else ('library' if self.roll_in_library else 'card')]
        self.roll_sub.setText('  ·  '.join(x for x in parts if x))
        self.roll_sub.setToolTip('%s%s' % (r.path, ('\n%d RAW files are left on the card' % r.raws) if r.raws else ''))
        self.roll_title.setToolTip('%s\n%s' % (self.roll_title.text(), self.roll_sub.text()))
        self.fit_corner()
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
        token = self._neg_token = object()

        def work(report):
            for k, f in enumerate(r.frames):
                if token is not self._neg_token:                        # another roll was opened meanwhile
                    break
                report((token, k, self.neg_thumb(f, turns.get(f.number, 0))))
            return key

        self.run(work, lambda key: None, progress=self._neg_ready)
        self.load_developments()
        self.tabs.setCurrentIndex(0)
        self.show_matching_card()                                       # the roll's film decides which recipe cards match
        self.update_scope_ui()

    def neg_film(self, f):
        """The film a frame's negative is drawn as: a mystery roll's negatives never give the film away."""
        film = self.shown_film()
        if self.secret() or film is films.MYSTERY:
            return films.from_code('CNEG')
        own = getattr(self, 'fsettings', {}).get(f.number)               # the Darkroom: a frame on its own film
        if own and self.roll.own and own.get('film') in films.BY_CODE:
            return films.BY_CODE[own['film']]
        return f.film or film

    def neg_thumb(self, f, turn):
        """The filmstrip picture of a frame: its negative, turned, in a piece of film with sprocket holes."""
        ck = (f.path, self.neg_film(f).code)
        if ck not in self.neg_cache:
            a = lab.load(f.path, 360)
            self.neg_cache[ck] = lab.to_image(lab.negative(a, self.neg_film(f)))
        im = lab.strip([lab.rotate(self.neg_cache[ck], turn)], self.shown_film(), positive=False, frame_w=250, start=f.number)
        if f.number in getattr(self, 'fsettings', {}):                 # the Darkroom: this frame has its own settings
            from PIL import ImageDraw
            d = ImageDraw.Draw(im)
            r = max(9, im.height // 14)
            x, y = im.width - 2 * r - 8, im.height // 2 - im.height // 3
            d.ellipse((x - 3, y - 3, x + 2 * r + 3, y + 2 * r + 3), fill=(255, 255, 255))
            d.ellipse((x, y, x + 2 * r, y + 2 * r), fill=(224, 55, 47))
        return im

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
        it.setIcon(strip_icon(to_pixmap(self.neg_thumb(f, new))))
        self.notify('Frame %d turned to %d°. Saved: it stays turned in the filmstrip, previews, prints and the '
                                     'contact sheet.' % (f.number, new), 5000)

    def lighttable_menu(self, pos):
        it = self.lighttable.itemAt(pos)
        if it is None:
            return
        if not it.isSelected():
            self.lighttable.setCurrentItem(it)
        f = it.data(Qt.UserRole)
        m = QMenu(self)
        m.addAction('⟳  Rotate right (clockwise)        R', lambda: self.rotate_current(90))
        m.addAction('⟲  Rotate left                            L', lambda: self.rotate_current(-90))
        m.addAction('Turn upside down', lambda: self.rotate_current(180))
        if self.turn(f):
            m.addAction('Straighten (no rotation)', lambda: self.rotate_current(-self.turn(f)))
        m.addSeparator()
        frames = self.selected_frames()
        n = len(frames)
        m.addAction('Print this frame' if n == 1 else 'Print these %d frames' % n, self.print_selected).setEnabled(not self.busy)
        m.addAction('Settings for this frame…' if n == 1 else 'Settings for these %d frames…' % n, lambda: self.set_scope('frame'))
        m.addAction('Copy this frame\'s settings        Ctrl+C', self.copy_settings)
        clip = getattr(self, 'clip', None)
        targets = [x for x in frames if clip is None or x.number != clip[2]] or frames
        m.addAction(('Paste frame %d\'s settings to %s        Ctrl+V' % (clip[2], self.frames_text([x.number for x in targets]).lower()))
                    if clip else 'Paste settings (copy a frame\'s first)', self.paste_settings).setEnabled(clip is not None)
        if any(x.number in self.fsettings for x in frames):
            m.addAction("Use the roll's settings again", lambda: self.clear_frame_settings(frames))
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
        eff_recipe, real_film = self.frame_effective(f) if mode == 'print' else (None, None)
        if mode == 'print' and self.scope == 'frame':
            eff_recipe = self.recipe()                                  # the panel is this frame's
        key = (f.path, mode, self.neg_film(f).code if mode == 'negative' else '',
               (tuple(sorted(eff_recipe.to_dict().items())), real_film.code) if mode == 'print' else ())
        turn = self.turn(f)
        cap = '%s  ·  frame %d / %d  ·  %s' % (self.roll.code, f.number, len(self.roll.frames),
                                                f.taken.strftime('%d %b %Y  %H:%M') if f.taken else os.path.basename(f.path))
        if key in self.render_cache:
            self.dview.show_picture(self.render_cache[key][1], turn, cap)
            return
        older = [v for k, v in self.render_cache.items() if k[0] == f.path]
        label = {'negative': 'developing the negative…', 'original': 'loading…', 'print': 'printing a test strip…'}[mode]
        self.dview.show_picture(older[-1][1] if older else None, turn, cap, loading=label)
        recipe = lab.Recipe.from_dict(eff_recipe.to_dict()) if eff_recipe is not None else self.recipe()
        recipe.seed = 1
        neg_film = self.neg_film(f)
        real_film = real_film or f.film or self.roll.true_film
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
        token, k, im = item
        if token is not getattr(self, '_neg_token', None):               # a picture of the roll shown before: not for this one
            return
        if k < self.lighttable.count():
            self.lighttable.item(k).setIcon(strip_icon(to_pixmap(im)))
            if k == 0 and self.lighttable.currentRow() < 0:
                self.lighttable.setCurrentRow(0)

    # ------------------------------------------------------------ full screen
    def open_fullscreen(self):
        """The light table's big view (in its current view) or the selected print on the whole screen."""
        tab = self.tabs.currentIndex()
        view = {0: self.dview, 1: self.pview}.get(tab)
        if view is None or view.canvas.pm is None or view.canvas.dev is not None or self.busy:
            return
        hint = 'Esc  close      ←  →  %s      R / L  rotate      hold Space  original      I  info%s' % (
            'frame' if tab == 0 else 'print', '      V  view' if tab == 0 else '      C  compare (↑ ↓ another, drag the line)')
        fs = FullScreen(self, view, self.fullscreen_info, hint)
        fs.step.connect(self.step)
        fs.rotate.connect(self.rotate_current)
        fs.switch_view.connect(self.switch_view)
        fs.original.connect(self.fullscreen_original)
        fs.compare.connect(self.fullscreen_compare)
        self.fs = fs
        fs.showFullScreen()
        fs.activateWindow()
        fs.setFocus()

    def fullscreen_compare(self, direction):
        """C in full screen on the prints: this print against another print of the same frame from another development (your pick
        first); Up / Down go through the others."""
        fs = getattr(self, 'fs', None)
        p = self.selected_print()
        if fs is None or self.tabs.currentIndex() != 1 or not p or self.roll is None:
            return
        n = frame_number(p)
        if n is None:
            return
        others = [x for x in self.library.frame_prints(self.roll_key()).get(n, []) if x[0] != p]
        if not others:
            fs.end_compare()
            fs.canvas.flash('Only one print of this frame', 1400)
            return
        if direction == 0:
            pick = self.library.picks(self.roll_key()).get(n)
            self.cmp_index = next((k for k, x in enumerate(others) if self.library.pick_key(x[0]) == pick), 0)
        else:
            self.cmp_index = (getattr(self, 'cmp_index', 0) + direction) % len(others)
        q, folder, lc = others[self.cmp_index]
        here = self.library.print_info(p)[0]
        left, right = self.library.version_name(here) if here else '', '%s  (%d / %d)' % (
            self.library.version_name(lc), self.cmp_index + 1, len(others))

        def show(pm):
            if getattr(self, 'fs', None) is fs and self.selected_print() == p:
                fs.show_compare(pm, left, right)

        if q in self.print_pix:
            return show(self.print_pix[q])

        def work(report):
            with Image.open(q) as im:
                im.draft('RGB', (2000, 2000))
                return im.convert('RGB')

        def done(im):
            self.print_pix[q] = to_pixmap(im)
            show(self.print_pix[q])

        self.run(work, done)

    def _frame_of_print(self, p):
        """The roll's frame a print was made from (by its file name, frame_07.jpg)."""
        n = frame_number(p)
        if n is None:
            return None
        return next((f for f in self.roll.frames if f.number == n), None) if self.roll is not None else None

    def fullscreen_original(self, on):
        """Space held in full screen: the frame as it was before the lab (turned like the picture)."""
        fs = getattr(self, 'fs', None)
        if not on or fs is None or self.roll is None:
            return
        if self.tabs.currentIndex() == 1:
            p = self.selected_print()
            f = self._frame_of_print(p) if p else None
            turn = (self.turn(f) + self.print_pending.get(p, 0)) if f else 0
        else:
            f = self.selected_frame()
            turn = self.turn(f) if f else 0
        if f is None:
            return
        cache = self.__dict__.setdefault('orig_pix', {})
        if f.path in cache:
            fs.show_original(cache[f.path], turn)
            return

        def work(report):
            return f.path, lab.to_image(lab.load(f.path, 2400))

        def done(res):
            path, im = res
            if len(cache) > 6:
                cache.pop(next(iter(cache)))
            cache[path] = to_pixmap(im)
            if getattr(self, 'fs', None) is fs and fs.holding:
                fs.show_original(cache[path], turn)

        self.run(work, done)

    def fullscreen_info(self):
        """Key I in full screen: what this picture is (film, lab, date)."""
        if self.roll is None:
            return ''
        if self.tabs.currentIndex() == 1:
            p = self.selected_print()
            lc, fr = self.library.print_info(p) if p else ({}, {})
            taken = fr.get('taken')
            lines = ['%s  ·  print of frame %s' % (lc.get('film', ''), fr.get('frame', '?')),
                     ('Development: %s%s' % ('★  ' if lc.get('favourite') else '', self.library.version_name(lc))) if lc else '',
                     'Lab: %s' % (fr.get('description') or lc.get('description', '')),
                     'Developed %s' % lc.get('developed', '').replace('T', '  ')]
            if taken:
                lines.append('Taken %s' % taken.replace('T', '  '))
            lines.append('From %s  ·  %s' % (fr.get('original', ''), os.path.basename(p or '')))
            return '\n'.join(x for x in lines if x)
        f = self.selected_frame()
        if f is None:
            return ''
        film = self.shown_film()
        view = {'negative': 'Negative', 'original': 'Original', 'print': 'Print preview'}[self.dview.mode]
        lines = ['%s  ·  %s  ·  frame %d of %d' % (view, 'Mystery  ???' if self.secret() else (f.film or film).name, f.number,
                                                  len(self.roll.frames))]
        if self.dview.mode == 'print':
            if f.number in self.fsettings and self.scope == 'roll':
                lines.append('Lab: this frame\'s own settings  (%s)' % self.frame_effective(f)[0].describe())
            else:
                lines.append('Lab: %s  (%s)' % (self.c_look.currentText().replace('   (default)', '').strip(), self.recipe().describe()))
        if f.taken:
            lines.append('Taken %s' % f.taken.strftime('%d %b %Y  %H:%M'))
        lines.append(os.path.basename(f.path))
        return '\n'.join(lines)

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

    @staticmethod
    def dev_mood(recipe, film):
        """What the developing animation shows of the choices made (expired film, a light leak, black and white, cross-processing)."""
        return {'expired': recipe.expired, 'leak': bool(recipe.leaks and not film.mono), 'mono': film.mono,
                'cross': recipe.process == 'cross'}

    def develop(self):
        """Develop the whole roll. The big view becomes the darkroom: each print comes up in the developer tray, goes through the stop
        bath, fixer and wash, and is hung on the drying line; then the prints tab opens."""
        if self.roll is None or self.busy:
            return
        r, in_lib = self.roll, self.roll_in_library
        recipe = self.roll_recipe_now()
        look = self.current_card().name if self.current_card() is not None and self.scope == 'roll' else None
        max_side = self.c_size.currentData() or None
        self.busy = True
        self._update_buttons()
        was_secret = self.secret()
        self.tabs.setCurrentIndex(0)
        canvas = self.dview.canvas
        canvas.start_develop('DEVELOPING  %s  ·  %s' % (r.code, recipe.describe().upper()), self.dev_mood(recipe, self.shown_film()))

        def work(report):
            libroll = r if in_lib else self.library.import_roll(r, progress=lambda d, n: report(('load', d, n, None)))
            report(('load', 0, 0, None))
            return self.library.develop(libroll, recipe, progress=lambda d, n, s_, t: report(('dev', d, n, t)), max_side=max_side,
                                        look=look), libroll

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
                if was_secret:
                    Reveal(self, films.BY_NAME.get(labcard['film'].lower(), films.UNKNOWN)).exec()

            canvas.dev_finish(after, 'DRY  ·  %d PRINTS' % len(labcard['frames']))

        self.run(work, done, progress=prog)

    # ------------------------------------------------------------ prints
    def load_developments(self):
        self.dev_pick.blockSignals(True)
        self.dev_pick.clear()
        self.devs = self.library.developments(self.roll_key()) if self.roll is not None else []
        for folder, lc in self.devs:
            self.dev_pick.addItem(('★  ' if lc.get('favourite') else '') + self.library.version_name(lc), folder)
            self.dev_pick.setItemData(self.dev_pick.count() - 1, '%s\nDeveloped %s  ·  %d prints' % (
                lc.get('description', ''), lc.get('developed', '').replace('T', '  '), len(lc.get('frames', []))), Qt.ToolTipRole)
        self.dev_pick.blockSignals(False)
        self.show_development()

    def set_print_mode(self, mode):
        """BY DEVELOPMENT or BY FRAME in the prints tab."""
        self.print_mode = mode
        (self.btn_by_dev if mode == 'dev' else self.btn_by_frame).setChecked(True)
        self.dev_pick.setVisible(mode == 'dev')
        self.ver_pick.setVisible(mode == 'frame')
        self.btn_use.setVisible(mode == 'frame')
        self.btn_export.setText('Export prints…' if mode == 'dev' else 'Export my picks…')
        self.btn_export.setToolTip('Copy the prints of this development to a folder' if mode == 'dev' else
                                   'Copy one print of every frame to a folder: your pick (✓), else the newest')
        self.show_development()

    def show_development(self, *_):
        if self.print_mode == 'frame':
            return self.show_by_frame()
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
        token = self._print_token = object()

        def work(report):
            for k, p in enumerate(paths):
                if token is not self._print_token:
                    break
                report((k, self._print_thumb(p)))
            return os.path.join(folder, 'contact_sheet.jpg')

        def ready(item):
            k, im = item
            if token is self._print_token and k < self.prints.count():
                self.prints.item(k).setIcon(strip_icon(to_pixmap(im)))

        self.run(work, lambda path: self._show_sheet(path) if token is self._print_token else None, progress=ready)
        if self.prints.count():
            self.prints.setCurrentRow(0)
        self._update_buttons()

    def show_by_frame(self):
        """The prints tab frame by frame: one print per frame (the one shown, your pick, else the newest), with its count."""
        cur = self.prints.currentItem()
        keep = cur.data(Qt.UserRole + 1) if cur is not None else None
        self.prints.blockSignals(True)
        self.prints.clear()
        self.prints.blockSignals(False)
        self.print_pix = {}
        rid = self.roll_key() if self.roll is not None else None
        self.fprints = self.library.frame_prints(rid) if rid else {}
        chosen = self.library.chosen_prints(rid) if rid else {}
        shown = getattr(self, 'frame_shown', {})
        self.frame_shown = {n: p for n, p in shown.items() if n in self.fprints and any(p == x[0] for x in self.fprints[n])}
        folder = self.dev_pick.currentData()
        if folder:
            self._show_sheet(os.path.join(folder, 'contact_sheet.jpg'))
        else:
            self.sheet_label.setText('No contact sheet yet: develop the roll.')
        if not self.fprints:
            self.pview.clear('No prints yet: develop the roll')
            self.ver_pick.clear()
            self._update_buttons()
            return
        blank = QPixmap(128, 100)
        blank.fill(QColor('#232121'))
        todo = []
        for n, prints in self.fprints.items():
            p = self.frame_shown.get(n) or chosen[n]
            it = QListWidgetItem(QIcon(blank), '')
            it.setData(Qt.UserRole, p)
            it.setData(Qt.UserRole + 1, n)
            it.setToolTip('Frame %d  ·  %d print%s' % (n, len(prints), '' if len(prints) == 1 else 's'))
            self.prints.addItem(it)
            todo.append(p)

        token = self._print_token = object()

        def work(report):
            for k, p in enumerate(todo):
                if token is not self._print_token:
                    break
                report((k, self._thumb_for(p)))
            return None

        def ready(item):
            k, im = item
            if token is self._print_token and k < self.prints.count():
                self.prints.item(k).setIcon(strip_icon(to_pixmap(im)))

        self.run(work, lambda _: None, progress=ready)
        row = next((k for k in range(self.prints.count()) if self.prints.item(k).data(Qt.UserRole + 1) == keep), 0)
        self.prints.setCurrentRow(row)
        self.update_versions_combo()
        self._update_buttons()

    def selected_frame_no(self):
        it = self.prints.currentItem()
        return it.data(Qt.UserRole + 1) if it is not None else None

    def update_versions_combo(self):
        """By frame: the prints of the selected frame, newest first, with your pick marked."""
        if self.print_mode != 'frame':
            return
        n = self.selected_frame_no()
        self.ver_pick.clear()
        if n is None or n not in getattr(self, 'fprints', {}):
            return
        pick = self.library.picks(self.roll_key()).get(n)
        cur = self.selected_print()
        for p, folder, lc in self.fprints[n]:
            mark = ('✓  ' if self.library.pick_key(p) == pick else '') + ('★  ' if lc.get('favourite') else '')
            self.ver_pick.addItem(mark + self.library.version_name(lc), p)
            self.ver_pick.setItemData(self.ver_pick.count() - 1, lc.get('description', ''), Qt.ToolTipRole)
        self.ver_pick.setCurrentIndex(max(0, self.ver_pick.findData(cur)))
        self.btn_use.setEnabled(bool(cur) and self.library.pick_key(cur) != pick)

    def version_chosen(self, i):
        """By frame: another print of this frame chosen in the menu: show it (it becomes your pick only with ✓ Use this print)."""
        p, it = self.ver_pick.itemData(i), self.prints.currentItem()
        if not p or it is None:
            return
        n = it.data(Qt.UserRole + 1)
        self.frame_shown[n] = p
        it.setData(Qt.UserRole, p)
        self.show_print()
        self.update_versions_combo()
        self._refresh_thumb(it, p)

    def _refresh_thumb(self, it, p):
        def done(im):
            for k in range(self.prints.count()):
                if self.prints.item(k) is it and it.data(Qt.UserRole) == p:
                    it.setIcon(strip_icon(to_pixmap(im)))
        self.run(lambda report: self._thumb_for(p), done)

    def use_this_print(self):
        n, p = self.selected_frame_no(), self.selected_print()
        if n is None or not p:
            return
        self.library.set_pick(self.roll_key(), n, p)
        self.update_versions_combo()
        self._refresh_thumb(self.prints.currentItem(), p)
        self.notify('Frame %d: this print is your pick (Export my picks takes it)' % n, 5000)

    def _thumb_for(self, p):
        """A print's thumbnail; by frame with a badge: how many prints the frame has, ✓ when it is your pick."""
        im = self._print_thumb(p)
        if self.print_mode != 'frame' or self.roll is None:
            return im
        from PIL import ImageDraw
        n = frame_number(p)
        if n is None:
            return im
        count = len(getattr(self, 'fprints', {}).get(n, []))
        picked = self.library.picks(self.roll_key()).get(n) == self.library.pick_key(p)
        text = ('PICK  ' if picked else '') + ('×%d' % count if count > 1 else '')
        if text.strip():
            d = ImageDraw.Draw(im)
            f = lab._font(max(14, im.height // 9))
            box = d.textbbox((0, 0), text, font=f)
            w, h = box[2] - box[0] + 12, box[3] - box[1] + 10
            x, y = im.width - w - 4, im.height - h - 4
            d.rounded_rectangle((x, y, x + w, y + h), 6, fill=(224, 55, 47) if picked else (20, 18, 18))
            d.text((x + 6 - box[0], y + 5 - box[1]), text, font=f, fill=(255, 255, 255))
        return im

    def trash(self, path):
        """Move a file or folder to the Recycle Bin (the Trash). True when it is gone."""
        res = QFile.moveToTrash(path)
        ok = res[0] if isinstance(res, tuple) else bool(res)
        return ok and not os.path.exists(path)

    def current_version(self):
        """(folder, labcard) of the development in view: the chosen one (by development) or the shown print's (by frame)."""
        if self.print_mode == 'frame':
            p = self.selected_print()
            folder = os.path.dirname(p) if p else None
        else:
            folder = self.dev_pick.currentData()
        lc = dict(getattr(self, 'devs', [])).get(folder) if folder else None
        return (folder, lc) if lc is not None else (None, None)

    def versions_menu(self):
        folder, lc = self.current_version()
        devs = getattr(self, 'devs', [])
        m = QMenu(self)
        if self.roll is not None and devs:
            total = sum(self.library.folder_size(f) for f, _ in devs)
            head = m.addAction('%d development%s of this roll  ·  %s on disk' % (len(devs), '' if len(devs) == 1 else 's', mb(total)))
            head.setEnabled(False)
            m.addSeparator()
        p = self.selected_print()
        if p:
            m.addAction('Export this print…', self.export_one)
        if p and os.path.basename(os.path.dirname(p)) == DARKROOM:
            m.addAction('Delete this single print (to the Recycle Bin)…', self.delete_single)
            m.addSeparator()
        if lc is not None:
            name = self.library.version_name(lc)
            m.addAction('Rename "%s"…' % name, lambda: self.rename_version(folder, lc))
            if lc.get('favourite'):
                m.addAction('☆  Not a favourite any more', lambda: self.favourite_version(folder, False))
            else:
                m.addAction('★  Favourite (kept by Clean up)', lambda: self.favourite_version(folder, True))
            m.addAction('Delete this development (to the Recycle Bin)…', lambda: self.delete_versions([(folder, lc)]))
            m.addSeparator()
        if self.roll is not None and devs:
            old = self.library.cleanup_candidates(self.roll_key())
            a = m.addAction('Clean up: %d development%s not ★ and holding none of your picks (%s)…' % (
                len(old), '' if len(old) == 1 else 's', mb(sum(self.library.folder_size(f) for f, _ in old))),
                lambda: self.delete_versions(old, cleanup=True))
            a.setEnabled(bool(old))
        else:
            m.addAction('No prints yet: develop the roll').setEnabled(False)
        m.exec(self.btn_versions.mapToGlobal(self.btn_versions.rect().bottomLeft()))

    def rename_version(self, folder, lc):
        name, ok = QInputDialog.getText(self, 'Rename the development', 'Name (empty: the automatic name)', QLineEdit.Normal,
                                        lc.get('name', ''))
        if ok:
            self.library.set_version(folder, name=name)
            self.reload_versions()

    def favourite_version(self, folder, on):
        self.library.set_version(folder, favourite=on)
        self.reload_versions()
        self.notify('★  Favourite: kept by Clean up' if on else 'Not a favourite any more', 4000)

    def delete_versions(self, items, cleanup=False):
        """Move developments to the Recycle Bin, after asking. The originals and the other developments stay."""
        if not items:
            return
        size = mb(sum(self.library.folder_size(f) for f, _ in items))
        if cleanup:
            q = ('Move %d development%s of this roll to the Recycle Bin (%s)?\n\nKept: ★ favourites and every development that holds '
                 'one of your picks. The originals are never touched.' % (len(items), '' if len(items) == 1 else 's', size))
        else:
            q = 'Move "%s" to the Recycle Bin (%s)?\n\nThe originals and the other developments are kept.' % (
                self.library.version_name(items[0][1]), size)
        if QMessageBox.question(self, APP_NAME, q) != QMessageBox.Yes:
            return
        folders = {os.path.normpath(f) for f, _ in items}
        self.print_pending = {p: d for p, d in self.print_pending.items() if os.path.normpath(os.path.dirname(p)) not in folders}
        gone = [f for f, _ in items if self.trash(f)]
        self.reload_versions()
        if len(gone) < len(items):
            QMessageBox.warning(self, APP_NAME, '%d of %d could not be moved to the Recycle Bin (open in another program?).'
                                % (len(items) - len(gone), len(items)))
        self.notify('%d development%s moved to the Recycle Bin' % (len(gone), '' if len(gone) == 1 else 's'), 6000)

    def reload_versions(self):
        """After a rename, favourite or delete: the development menu and the prints again, staying on the same development."""
        keep = self.dev_pick.currentData()
        self.dev_pick.blockSignals(True)
        self.load_developments()
        self.dev_pick.blockSignals(True)
        i = self.dev_pick.findData(keep)
        if i >= 0:
            self.dev_pick.setCurrentIndex(i)
        self.dev_pick.blockSignals(False)
        self.show_development()

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
        if self.print_mode == 'frame':
            lc = self.library.print_info(p)[0]
            if lc:
                cap += '  ·  ' + self.library.version_name(lc)
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
                self.library.rotate_print_path(p, d)
                done.append((p, d, self._thumb_for(p)))
            return done

        def finished(done):
            folder = None
            for p, d, thumb in done:
                self.print_pending[p] = (self.print_pending.get(p, 0) - d) % 360
                self.print_pix.pop(p, None)
                for k in range(self.prints.count()):
                    if self.prints.item(k).data(Qt.UserRole) == p:
                        self.prints.item(k).setIcon(strip_icon(to_pixmap(thumb)))
                folder = os.path.dirname(p)
            if self.selected_print() in [p for p, _, _ in done]:
                self.show_print()
            if folder and os.path.basename(folder) != DARKROOM:
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
        m.addSeparator()
        m.addAction('Export this print…', self.export_one)
        if self.print_mode == 'frame':
            m.addAction('✓  Use this print', self.use_this_print)
        m.exec(self.prints.viewport().mapToGlobal(pos))

    def export_prints(self):
        if self.print_mode == 'frame':
            return self.export_picks()
        folder = self.dev_pick.currentData()
        if not folder:
            return
        d = QFileDialog.getExistingDirectory(self, 'Export the prints to', self.export_dir())
        if not d:
            return
        self.settings.setValue('export', d)
        lc = dict(self.devs)[folder]
        # one folder per development (its time is in the name), so exporting two developments on the same film never mixes them up;
        # a development you named carries its name
        stamp = os.path.basename(os.path.normpath(folder)).replace('develop-', '')
        what = recipes.slug(lc['name']) if lc.get('name') else lc['film'].replace(' ', '_').replace('.', '')
        dst = os.path.join(d, '%s_%s_%s' % (lc['roll'], what, stamp))
        os.makedirs(dst, exist_ok=True)
        for n in os.listdir(folder):
            if n.lower().endswith('.jpg'):
                shutil.copy2(os.path.join(folder, n), dst)
        self.notify('Exported to %s' % dst, 8000)
        QDesktopServices.openUrl(QUrl.fromLocalFile(dst))

    def export_one(self):
        """Export the selected print on its own."""
        p = self.selected_print()
        if not p or self.roll is None:
            return
        lc = self.library.print_info(p)[0]
        name = '%s_%s_%s' % (recipes.slug(self.roll.name or self.roll.code), os.path.splitext(os.path.basename(p))[0],
                             recipes.slug(lc.get('film', '')) if lc else 'print')
        path, _ = QFileDialog.getSaveFileName(self, 'Export this print', os.path.join(self.export_dir(), name + '.jpg'),
                                              'JPEG (*.jpg)')
        if path:
            self.settings.setValue('export', os.path.dirname(path))
            shutil.copy2(p, path)
            self.notify('Exported to %s' % path, 8000)

    def delete_single(self):
        p = self.selected_print()
        if not p or os.path.basename(os.path.dirname(p)) != DARKROOM:
            return
        if QMessageBox.question(self, APP_NAME, 'Move this single print to the Recycle Bin?') != QMessageBox.Yes:
            return
        self.print_pending.pop(p, None)
        ok = self.trash(p)
        if ok and os.path.exists(p[:-4] + '.json'):
            self.trash(p[:-4] + '.json')
        self.reload_versions()
        self.notify('Single print moved to the Recycle Bin' if ok else 'The print could not be moved to the Recycle Bin', 5000)

    def print_selected(self):
        """The Darkroom: print the selected frames on their own (each with its own settings, else the roll's). They come up in the
        prints' by-frame view; the developments are not touched."""
        if self.roll is None or self.busy:
            return
        frames = self.selected_frames()
        if not frames:
            return
        nums = [f.number for f in frames]
        r, in_lib = self.roll, self.roll_in_library
        recipe = self.roll_recipe_now()
        look = self.current_card().name if self.current_card() is not None and self.scope == 'roll' else None
        max_side = self.c_size.currentData() or None
        was_secret = self.secret()
        self.busy = True
        self._update_buttons()
        self.tabs.setCurrentIndex(0)
        canvas = self.dview.canvas
        canvas.start_develop('PRINTING  %s  ·  %s' % (r.code, self.frames_text(nums).upper()), self.dev_mood(recipe, self.shown_film()))

        def work(report):
            libroll = r if in_lib else self.library.import_roll(r, progress=lambda d, n: report(('load', d, n, None)))
            report(('load', 0, 0, None))
            return self.library.print_frames(libroll, nums, recipe, progress=lambda d, n, s_, t: report(('dev', d, n, t)),
                                             max_side=max_side, look=look), libroll

        def prog(p):
            kind, d, n, t = p
            if kind == 'load':
                canvas.dev_note('Into the enlarger…  %d / %d' % (d, n) if n else 'Focusing the enlarger…')
            else:
                canvas.dev_feed(to_pixmap(t), d, n)

        def done(res):
            made, libroll = res

            def after():
                self.busy = False
                rid = os.path.basename(os.path.normpath(libroll.path))
                if not in_lib:
                    self.refresh_library()
                    self.select_library_roll(rid)
                self.set_print_mode('frame')
                for path in made:
                    self.frame_shown[frame_number(path)] = path
                self.show_by_frame()
                first = frame_number(made[0]) if made else None
                for k in range(self.prints.count()):
                    if self.prints.item(k).data(Qt.UserRole + 1) == first:
                        self.prints.setCurrentRow(k)
                self.tabs.setCurrentIndex(1)
                self.notify('%d single print%s dry: in PRINTS, by frame (✓ Use this print to make one your pick)'
                            % (len(made), '' if len(made) == 1 else 's'), 7000)
                self._update_buttons()
                if was_secret:
                    Reveal(self, libroll.true_film).exec()

            canvas.dev_finish(after, 'DRY  ·  %d PRINT%s' % (len(made), '' if len(made) == 1 else 'S'))

        self.run(work, done, progress=prog)

    def export_dir(self):
        """Where exports start: where the last one went, else the home folder."""
        d = self.settings.value('export')
        return d if d and os.path.isdir(d) else os.path.expanduser('~')

    def export_picks(self):
        """By frame: one print of every frame (your pick, else the newest) into one folder: the final roll."""
        if self.roll is None:
            return
        chosen = self.library.chosen_prints(self.roll_key())
        if not chosen:
            return
        d = QFileDialog.getExistingDirectory(self, 'Export my picks to', self.export_dir())
        if not d:
            return
        self.settings.setValue('export', d)
        dst = os.path.join(d, '%s_picks_%s' % (recipes.slug(self.roll.name or self.roll.code), datetime.now().strftime('%Y%m%d-%H%M%S')))
        os.makedirs(dst, exist_ok=True)
        for n, p in chosen.items():
            shutil.copy2(p, os.path.join(dst, os.path.basename(p)))
        picked = len(self.library.picks(self.roll_key()))
        self.notify('Exported %d prints (%d of your picks, the rest the newest) to %s' % (len(chosen), picked, dst), 8000)
        QDesktopServices.openUrl(QUrl.fromLocalFile(dst))

    def open_dev_folder(self):
        folder = self.dev_pick.currentData() or (self.library.roll_dir(self.roll_key()) if self.roll is not None else self.library.root)
        if folder and os.path.isdir(folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    # ------------------------------------------------------------ plumbing
    def _update_buttons(self):
        has = self.roll is not None
        self.btn_develop.setEnabled(has and not self.busy and bool(self.roll.frames))
        self.btn_print.setEnabled(has and not self.busy and self.selected_frame() is not None)
        self.btn_import.setEnabled(has and not self.busy and not self.roll_in_library)
        self.btn_import.setVisible(not (has and self.roll_in_library))        # library rolls (and loaded photos) are in already
        dev = bool(getattr(self, 'devs', None))
        self.btn_export.setEnabled(dev or (self.print_mode == 'frame' and bool(getattr(self, 'fprints', None))))
        self.btn_versions.setEnabled(has)
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
        self.photolab.failed()
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
    w.set_mode('darkroom')
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

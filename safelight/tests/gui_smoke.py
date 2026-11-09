"""Headless run of the whole app: open a fake card, light table, test strip, develop a mystery roll, prints, contact sheet, lab log.
python tests/gui_smoke.py <screenshot dir>     (uses Qt's offscreen platform; writes PNG screenshots)"""
import os
import sys
import tempfile
import time

sys.stdout.reconfigure(errors='replace')                            # (the console may not print every character)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
if os.name == 'nt':
    os.environ.setdefault('QT_QPA_FONTDIR', os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))
import fixtures                                                     # noqa: E402

out = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()
tmp = tempfile.mkdtemp()
os.environ['SAFELIGHT_LIBRARY'] = os.path.join(tmp, 'lib')
root = fixtures.make_card(os.path.join(tmp, 'card'), rolls=(('PROV001', 'TL500 Provia', 12), ('MYST001', 'TL500 Classic Chrome', 6)))

from PySide6.QtWidgets import QApplication                         # noqa: E402
from safelight import app as A, card                                # noqa: E402

card.find_cards = lambda: []
revealed = []
A.Reveal.exec = lambda self: revealed.append(self.findChildren(A.QLabel)[1].text())
qa = QApplication([])
qa.setStyleSheet(A.STYLE)
from PySide6.QtCore import QSettings                                # noqa: E402
w = A.MainWindow(QSettings(os.path.join(tmp, 'settings.ini'), QSettings.IniFormat), autoload=False)
w.resize(1400, 880)
w.show()


def wait(cond, secs=60):
    t = time.time()
    while not cond():
        qa.processEvents()
        time.sleep(0.02)
        if time.time() - t > secs:
            raise SystemExit('timeout')
    for _ in range(20):
        qa.processEvents()
        time.sleep(0.01)


def shot(name):
    qa.processEvents()
    w.grab().save(os.path.join(out, name))


w.open_source(root)
wait(lambda: w.source_rolls)
assert w.c_look.currentData() == 'Vintage print' and w.recipe() == A.lab.Recipe(), w.c_look.currentText()   # the vintage defaults
from PySide6.QtWidgets import QStatusBar                          # noqa: E402
assert not w.findChildren(QStatusBar)                               # no status bar: the picture gets the room
assert w.btn_photos.parent() is not w.btn_log.parent()                # Load photos sits with the rolls, not in the top bar
shot('0b_start.png')
names = [w.tree.topLevelItem(0).child(k).text(0) for k in range(w.tree.topLevelItem(0).childCount())]
print('tree:', [n.replace('\n', ' | ') for n in names])
assert 'Mystery  ???' in names[0] and 'Provia' in names[1], names
w.tree.setCurrentItem(w.tree.topLevelItem(0).child(1))             # PROV001
wait(lambda: not w.jobs and w.lighttable.count() == 12)
wait(lambda: w.dview.canvas.pm is not None and not w.dview.canvas.loading)
assert w.dview.mode == 'negative'
shot('1_light_table.png')
# rotation: R pressed five times quickly turns at once, no queue, the big view and the filmstrip follow, the setting is saved
from PySide6.QtTest import QTest                                   # noqa: E402
w.activateWindow()
qa.setActiveWindow(w) if hasattr(qa, 'setActiveWindow') else None
w.lighttable.setFocus()
w.lighttable.setCurrentRow(1)
wait(lambda: not w.jobs and not w.dview.canvas.loading)
assert qa.activeWindow() is w, qa.activeWindow()
f2 = w.selected_frame()
t0 = time.time()
for _ in range(5):
    QTest.keyClick(w.lighttable, A.Qt.Key_R)
quick = time.time() - t0
assert quick < 1.0, quick                                           # five turns in well under a second: nothing is re-rendered
assert w.turn(f2) == 90 and w.dview.canvas.rotation == 90, (w.turn(f2), w.dview.canvas.rotation)   # 5 x 90 = 450 = 90
assert w.dview.canvas.flash_text and 'turned 90' in w.dview.rot_label.text(), (w.dview.canvas.flash_text, w.dview.rot_label.text())
shot('1b_rotated.png')
assert not w.dview.b_right.text().find('R') < 0 and 'L' in w.dview.b_left.text()   # the keys are written on the buttons
QTest.keyClick(w.lighttable, A.Qt.Key_L)
assert w.turn(f2) == 0
w.rotate_current(90)                                               # leave frame 2 turned for the development below
# switching views: Space cycles negative -> original -> print preview
QTest.keyClick(w.lighttable, A.Qt.Key_Space)
assert w.dview.mode == 'original', w.dview.mode
QTest.keyClick(w.lighttable, A.Qt.Key_Space)
assert w.dview.mode == 'print'
wait(lambda: not w.jobs and not w.dview.canvas.loading)
shot('2_print_preview.png')
w.c_push.setCurrentIndex(w.c_push.findData(2))
w.c_proc.setCurrentIndex(w.c_proc.findData('cross'))
wait(lambda: not w.jobs and not w.dview.canvas.loading)
shot('2b_print_preview_cross.png')
QTest.keyClick(w.lighttable, A.Qt.Key_Right)
assert w.lighttable.currentRow() == 2
g = A.Guide(w)
g.resize(760, 720)
g.grab().save(os.path.join(out, '0_lab_guide.png'))
print('big view, rotation, views and guide: ok')
w.set_recipe(A.lab.Recipe(border='black'))
w.tree.setCurrentItem(w.tree.topLevelItem(0).child(0))             # MYST001
wait(lambda: not w.jobs and w.lighttable.count() == 6)
assert w.roll_title.text().startswith('MYSTERY'), w.roll_title.text()
shot('3_mystery_light_table.png')
w.c_size.setCurrentIndex(w.c_size.findData(1600))
w.develop()
wait(lambda: w.dview.canvas.dev is not None and w.dview.canvas.dev['cur'] is not None, 60)
time.sleep(0.9)
shot('3b_developing.png')
wait(lambda: w.dview.canvas.dev is not None and len(w.dview.canvas.dev['line']) >= 2, 60)
shot('3c_developing_line.png')
wait(lambda: not w.busy and not w.jobs, 180)
print('revealed:', revealed)
assert revealed == ['CLASSIC CHROME'], revealed
wait(lambda: w.prints.count() == 6)
wait(lambda: not w.jobs and w.pview.canvas.pm is not None)
shot('4_prints.png')
w.prints.setCurrentRow(0)
wait(lambda: not w.jobs and w.pview.canvas.pm is not None)
p0 = w.selected_print()
from PIL import Image as _I                                         # noqa: E402
size0 = _I.open(p0).size
for _ in range(3):
    QTest.keyClick(w.prints, A.Qt.Key_R)                           # 270 on screen at once ...
assert w.pview.canvas.rotation == 270
wait(lambda: not w.rot_timer.isActive() and not w.jobs and not any(w.print_pending.values()), 60)
assert _I.open(p0).size == (size0[1], size0[0]), (_I.open(p0).size, size0)    # ... then written to the file once
shot('4b_print_rotated.png')
assert w.width() <= 1500, w.width()                                 # the window must not grow (tank labels used to pile up)
assert w.prints.item(0).icon().actualSize(w.prints.iconSize()).height() > 80
assert w.roll_in_library and 'CLASSIC CHROME' in w.roll_title.text(), w.roll_title.text()
w.tabs.setCurrentIndex(2)
wait(lambda: w.sheet_label.pixmap() is not None and not w.sheet_label.pixmap().isNull())
shot('5_contact_sheet.png')
lib_items = [w.tree.topLevelItem(1).child(k).text(0) for k in range(w.tree.topLevelItem(1).childCount())]
print('library:', [n.replace('\n', ' | ') for n in lib_items])
assert any('Classic Chrome' in n and 'developed' in n for n in lib_items)
# photos from any camera: Load photos… -> a named roll on a chosen film, the film selector shows for it, the film can be changed
phone = os.path.join(tmp, 'phone')
os.makedirs(phone)
for k in range(5):
    fixtures.frame(100 + k).save(os.path.join(phone, 'IMG_%04d.jpg' % k))


def fake_dialog(self):
    self._set([os.path.join(phone, n) for n in sorted(os.listdir(phone))])
    self.name.setText('Phone pics')
    self.film.setCurrentIndex(self.film.findData('VELV'))
    return 1


A.LoadPhotos.exec = fake_dialog
w.tabs.setCurrentIndex(0)
lib = w.tree.topLevelItem(w.tree.topLevelItemCount() - 1)
action = lib.child(lib.childCount() - 1)
assert action.data(0, A.Qt.UserRole) == ('action', 'photos'), action.text(0)    # the last line of the library opens Load photos
w.tree.setCurrentItem(action)
wait(lambda: w.busy or w.roll is not None and w.roll.own, 10)
wait(lambda: not w.busy and not w.jobs, 60)
assert w.roll is not None and w.roll.own and w.roll.name == 'Phone pics', w.roll
assert w.c_film.isVisible() and w.c_film.currentData() == 'VELV', w.c_film.currentData()
assert 'PHONE PICS' in w.roll_title.text().upper(), w.roll_title.text()
wait(lambda: not w.jobs and w.lighttable.count() == 5)
w.dview.set_mode('print', emit=True)
wait(lambda: not w.jobs and not w.dview.canvas.loading)
shot('7_own_photos_velvia.png')
w.c_film.setCurrentIndex(w.c_film.findData('ACRO'))
w.film_changed(w.c_film.currentIndex())
wait(lambda: not w.jobs and w.lighttable.count() == 5)
w.dview.set_mode('print', emit=True)
wait(lambda: not w.jobs and not w.dview.canvas.loading)
assert w.roll.true_film.code == 'ACRO'
shot('7b_own_photos_acros.png')
w.tree.setCurrentItem(w.tree.topLevelItem(0).child(1))               # a FAUXJI roll: no film selector
wait(lambda: not w.jobs)
assert not w.c_film.isVisible()
print('own photos: ok')
log = A.LabLog(w, w.library)
log.resize(760, 300)
log.grab().save(os.path.join(out, '6_lab_log.png'))
print('lab log rows:', len(w.library.lablog()), 'stats', w.library.stats())
print('GUI SMOKE OK ->', out)

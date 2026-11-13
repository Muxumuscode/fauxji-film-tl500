"""Headless run of the whole app: open a fake card, light table, test strip, develop a mystery roll, prints, contact sheet, lab log.
python tests/gui_smoke.py <screenshot dir>     (uses Qt's offscreen platform; writes PNG screenshots)"""
import os
import shutil
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
assert w.stack.currentWidget() is w.start                          # first start: the two ways
w.start.set_card(2)
qa.processEvents()
w.grab().save(os.path.join(out, '00_start.png'))
w.start.set_card(0)
w.start.always.setChecked(False)
w.start.b_dark.click()
assert w.mode == 'darkroom' and w.stack.currentWidget() is w.darkroom and w.btn_mode_dark.isChecked()


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
# full screen on the prints: F opens it, it follows the prints view, → steps, R turns, I shows the info, held Space shows the
# original, Esc closes
QTest.keyClick(w.prints, A.Qt.Key_F)
fs = w.fs
assert fs.isVisible() and w.pview.full is fs and fs.canvas.pm is w.pview.canvas.pm
fs.resize(1280, 800)
QTest.keyClick(fs, A.Qt.Key_Right)
assert w.prints.currentRow() == 1, w.prints.currentRow()
wait(lambda: not w.jobs and fs.canvas.pm is w.pview.canvas.pm and fs.canvas.pm is not None)
assert 'frame_02' in fs.canvas.caption, fs.canvas.caption
QTest.keyClick(fs, A.Qt.Key_I)
assert 'Classic Chrome' in fs.canvas.info and 'print of frame 2' in fs.canvas.info, fs.canvas.info
fs.grab().save(os.path.join(out, '4c_fullscreen_print.png'))
QTest.keyPress(fs, A.Qt.Key_Space)
assert fs.holding and fs.canvas.badge.startswith('ORIGINAL')
wait(lambda: not w.jobs and fs.canvas.pm is not w.pview.canvas.pm, 30)
fs.grab().save(os.path.join(out, '4d_fullscreen_original.png'))
QTest.keyRelease(fs, A.Qt.Key_Space)
assert not fs.holding and fs.canvas.pm is w.pview.canvas.pm and not fs.canvas.badge
QTest.keyClick(fs, A.Qt.Key_R)
assert w.pview.canvas.rotation == 90 and fs.canvas.rotation == 90
QTest.keyClick(fs, A.Qt.Key_L)
wait(lambda: not w.rot_timer.isActive() and not w.jobs, 30)
QTest.keyClick(fs, A.Qt.Key_Escape)
qa.processEvents()
assert w.pview.full is None                                         # closed (and deleted: the window is not kept)
print('full screen: ok')
# versions: two more developments of the same roll (pushed, then a clean lab print with no border)
first_dev = w.dev_pick.currentData()
for r in (A.lab.Recipe(push=2, border='black'), A.lab.PRESETS['Clean lab print']):
    w.set_recipe(r)
    w.develop()
    wait(lambda: not w.busy and not w.jobs, 180)
wait(lambda: w.dev_pick.count() == 3 and not w.jobs)
names = [w.dev_pick.itemText(k) for k in range(3)]
print('versions:', names)
assert 'Clean lab print' in names[0] and 'push +2' in names[1], names               # named by recipe card, else what was done
# by frame: one print per frame, every print of the frame in the menu, choose one and make it the pick
w.set_print_mode('frame')
wait(lambda: not w.jobs and w.prints.count() == 6)
assert w.ver_pick.isVisible() and not w.dev_pick.isVisible() and w.btn_export.text() == 'Export my picks…'
w.prints.setCurrentRow(0)
assert w.ver_pick.count() == 3, w.ver_pick.count()
w.ver_pick.setCurrentIndex(1)
w.version_chosen(1)                                                  # the pushed one
assert os.path.dirname(w.selected_print()) == w.dev_pick.itemData(1)
w.use_this_print()
rid = w.roll_key()
assert w.library.picks(rid) == {1: os.path.basename(w.dev_pick.itemData(1))}
assert w.ver_pick.itemText(1).startswith('✓'), w.ver_pick.itemText(1)
wait(lambda: not w.jobs and w.pview.canvas.pm is not None)
shot('9_by_frame.png')
# compare in full screen: C against another print of the frame (side by side: other border), ↓ the next (same shape: split line)
w.open_fullscreen()                                                  # (the F key was checked above)
fs = w.fs
assert w.pview.full is fs
fs.resize(1280, 800)
QTest.keyClick(fs, A.Qt.Key_C)
wait(lambda: not w.jobs and fs.canvas.pm2 is not None, 30)
assert fs.comparing and 'Clean lab print' in fs.canvas.labels[1], fs.canvas.labels
fs.grab().save(os.path.join(out, '9b_compare_side_by_side.png'))
QTest.keyClick(fs, A.Qt.Key_Down)
wait(lambda: not w.jobs and '2 / 2' in fs.canvas.labels[1], 30)
fs.canvas.split = 0.35
fs.grab().save(os.path.join(out, '9c_compare_split.png'))
assert fs.canvas._cmp_rect is not None                              # the same shape: one over the other with the split line
QTest.keyClick(fs, A.Qt.Key_C)
assert not fs.comparing and fs.canvas.pm2 is None
QTest.keyClick(fs, A.Qt.Key_Escape)
qa.processEvents()
# favourite, rename, clean-up (to the Recycle Bin: here simply deleted), export my picks
A.QMessageBox.question = staticmethod(lambda *a, **k: A.QMessageBox.Yes)
w.trash = lambda path: (shutil.rmtree(path), True)[1]
w.set_print_mode('dev')
w.dev_pick.setCurrentIndex(0)
w.favourite_version(w.dev_pick.itemData(0), True)
assert w.dev_pick.itemText(0).startswith('★'), w.dev_pick.itemText(0)
w.library.set_version(first_dev, name='The first one')
w.reload_versions()
assert any(w.dev_pick.itemText(k) == 'The first one' for k in range(w.dev_pick.count()))
old = w.library.cleanup_candidates(rid)
assert [f for f, _ in old] == [first_dev], old                       # not ★, holds no pick
w.delete_versions(old, cleanup=True)
wait(lambda: not w.jobs and w.dev_pick.count() == 2)
w.set_print_mode('frame')
wait(lambda: not w.jobs and w.prints.count() == 6)
pexp = os.path.join(tmp, 'picks')
os.makedirs(pexp)
A.QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: pexp)
A.QDesktopServices.openUrl = staticmethod(lambda *a: True)
w.export_prints()
got = os.listdir(os.path.join(pexp, os.listdir(pexp)[0]))
assert sorted(got) == ['frame_%02d.jpg' % k for k in range(1, 7)], got
w.set_print_mode('dev')
print('versions: ok')
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
assert w.c_film.isVisible() and w.c_film.isEnabled() and w.c_film.currentData() == 'VELV', w.c_film.currentData()
assert 'PHONE PICS' in w.roll_title.text().upper(), w.roll_title.text()
wait(lambda: not w.jobs and w.lighttable.count() == 5)
assert w.dview.mode == 'print', w.dview.mode                        # loaded photos open on the print preview, not the negative
assert not w.btn_import.isVisible()                                 # and they are in the library already: no Import button
wait(lambda: not w.jobs and not w.dview.canvas.loading)
shot('7_own_photos_velvia.png')
w.c_film.setCurrentIndex(w.c_film.findData('ACRO'))
w.film_changed(w.c_film.currentIndex())
wait(lambda: not w.jobs and w.lighttable.count() == 5)
w.dview.set_mode('print', emit=True)
wait(lambda: not w.jobs and not w.dview.canvas.loading)
assert w.roll.true_film.code == 'ACRO'
shot('7b_own_photos_acros.png')
# recipe cards: Silver gelatin (an Acros card) on this Acros roll: its lab settings, the B&W filter is open
assert w.c_filter.isEnabled() and w.c_tone.isEnabled()
i = w.c_look.findData('card:Silver gelatin')
w.c_look.setCurrentIndex(i)
w.apply_card(i)
assert w.c_paper.currentData() == 'neutral' and w.c_filter.currentData() == 'yellow', w.recipe()
assert w.c_look.currentData() == 'card:Silver gelatin', w.c_look.currentData()
wait(lambda: not w.jobs and not w.dview.canvas.loading)
shot('8_recipe_silver_gelatin.png')
# a card with another film sets the film of a roll of own photos
i = w.c_look.findData('card:Portrait')
w.c_look.setCurrentIndex(i)
w.apply_card(i)
wait(lambda: not w.jobs and w.lighttable.count() == 5)
assert w.roll.true_film.code == 'ASTI' and w.c_film.currentData() == 'ASTI', w.roll.true_film
assert w.c_look.currentData() == 'card:Portrait', w.c_look.currentData()
assert not w.c_filter.isEnabled()                                    # a colour film: no B&W filter
w.c_grain.setValue(180)
w.recipe_changed()
assert w.c_look.currentData() == 'custom'                            # a change makes it Custom
# save as your own recipe (with the film), it shows under MY RECIPES and is picked
A.SaveCard.exec = lambda self: (self.name.setText('Soft grainy portrait'), self.note.setText('test'), 1)[-1]
w.save_card_dialog()
assert w.c_look.currentData() == 'my:Soft grainy portrait', w.c_look.currentData()
mine = w.library.recipe_cards()
assert [(c.name, c.film, c.recipe.grain) for c in mine] == [('Soft grainy portrait', 'ASTI', 1.8)], mine
assert any(w.c_look.itemText(k) == 'MY RECIPES' for k in range(w.c_look.count()))
w.set_recipe(A.lab.Recipe())
assert w.c_look.currentData() == 'Vintage print'
print('recipe cards: ok')
# the Darkroom on the roll of own photos: frame 2 gets its own film and paper, copied to frame 3, frames 2 and 3 printed on their own
w.set_recipe(A.lab.Recipe())
roll_paper = w.c_paper.currentData()
w.lighttable.setCurrentRow(1)
wait(lambda: not w.jobs)
w.set_scope('frame')
assert w.scope == 'frame' and w.btn_scope_frame.isChecked() and 'Frame 2 only' in w.scope_note.text(), w.scope_note.text()
w.c_film.setCurrentIndex(w.c_film.findData('ACRO'))
w.film_changed(w.c_film.currentIndex())
w.c_paper.setCurrentIndex(w.c_paper.findData('neutral'))
fsets = w.library.frame_settings(w.roll_key())
assert fsets[2]['film'] == 'ACRO' and fsets[2]['recipe']['paper'] == 'neutral', fsets
assert w.roll.true_film.code == 'ASTI'                               # the roll keeps its film
assert w.btn_roll_settings.isVisible()
w.dview.set_mode('print', emit=True)
wait(lambda: not w.jobs and not w.dview.canvas.loading)
shot('10_darkroom_frame.png')
w.copy_settings()
w.lighttable.setCurrentRow(2)
w.paste_settings()
assert sorted(w.library.frame_settings(w.roll_key())) == [2, 3]
w.lighttable.setCurrentRow(0)
wait(lambda: not w.jobs)
assert w.c_paper.currentData() == roll_paper                         # frame 1 has the roll's settings (shown in THIS FRAME)
w.set_scope('roll')
assert w.c_paper.currentData() == roll_paper and w.c_film.currentData() == 'ASTI'
assert 'except frames 2, 3' in w.scope_note.text(), w.scope_note.text()
w.lighttable.setCurrentRow(1)
w.lighttable.item(2).setSelected(True)
assert [f.number for f in w.selected_frames()] == [2, 3] and w.btn_print.text() == 'PRINT 2 FRAMES', w.btn_print.text()
wait(lambda: not w.jobs)
shot('10b_darkroom_marks.png')
w.print_selected()
wait(lambda: not w.busy and not w.jobs, 120)
assert w.tabs.currentIndex() == 1 and w.print_mode == 'frame'
wait(lambda: not w.jobs and w.pview.canvas.pm is not None)
assert 'darkroom' in w.selected_print() and w.selected_frame_no() == 2, w.selected_print()
assert w.ver_pick.itemText(0).startswith('Single print v1'), w.ver_pick.itemText(0)
shot('10c_single_print.png')
w.use_this_print()
assert w.library.picks(w.roll_key()) == {2: 'darkroom/frame_02-v1.jpg'}
# developing the whole roll: frames 2 and 3 keep their own settings
w.tabs.setCurrentIndex(0)
w.lighttable.setCurrentRow(0)
w.develop()
wait(lambda: not w.busy and not w.jobs, 180)
lc = w.library.developments(w.roll_key())[0][1]
by = {fr['frame']: fr for fr in lc['frames']}
assert by[1]['film'] == 'Astia' and by[2]['film'] == 'Acros' and by[3]['own_settings'], by
w.clear_frame_settings([f for f in w.roll.frames if f.number in (2, 3)])
assert w.library.frame_settings(w.roll_key()) == {}
w.set_print_mode('dev')
print('darkroom: ok')
w.tree.setCurrentItem(w.tree.topLevelItem(0).child(1))               # a FAUXJI roll: no film selector
wait(lambda: not w.jobs)
assert w.c_film.isVisible() and not w.c_film.isEnabled()        # a FAUXJI roll: the film menu is there, greyed out
assert w.dview.mode == 'negative', w.dview.mode                     # a FAUXJI roll after loaded photos: back to its negatives
assert w.btn_import.isVisible()                                     # a roll still on the card can be imported
i = w.c_look.findData('card:Silver gelatin')                         # an Acros card on a FAUXJI Provia roll: lab settings only
w.c_look.setCurrentIndex(i)
w.apply_card(i)
assert w.roll.true_film.code == 'PROV' and w.c_paper.currentData() == 'neutral'
assert w.c_look.currentData() == 'custom' and not w.c_filter.isEnabled() and not w.c_tone.isEnabled()
w.set_recipe(A.lab.Recipe())
print('own photos: ok')
# drag and drop: a folder of photos dropped on the window opens Load photos with the photos and the folder's name filled in
from PySide6.QtCore import QMimeData, QPointF, QUrl                # noqa: E402
from PySide6.QtGui import QDropEvent                               # noqa: E402
seen = {}


def drop_dialog(self):
    seen['paths'], seen['name'] = list(self.paths), self.name.text()
    return 0                                                        # cancelled: nothing is loaded


A.LoadPhotos.exec = drop_dialog
mime = QMimeData()
mime.setUrls([QUrl.fromLocalFile(phone)])
w.dropEvent(QDropEvent(QPointF(20, 20), A.Qt.CopyAction, mime, A.Qt.LeftButton, A.Qt.NoModifier))
wait(lambda: 'paths' in seen, 10)
assert len(seen['paths']) == 5 and seen['name'] == 'phone', seen
# exporting a development: its own folder, named with the development's time (two developments on one film never overwrite)
exp = os.path.join(tmp, 'export')
os.makedirs(exp)
A.QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: exp)
A.QDesktopServices.openUrl = staticmethod(lambda *a: True)
w.tree.setCurrentItem(next(w.tree.topLevelItem(1).child(k) for k in range(w.tree.topLevelItem(1).childCount())
                           if 'developed' in w.tree.topLevelItem(1).child(k).text(0)))
wait(lambda: not w.jobs and w.dev_pick.count() > 0)
w.export_prints()
stamp = os.path.basename(w.dev_pick.currentData()).replace('develop-', '')
outs = os.listdir(exp)
assert len(outs) == 1 and outs[0].endswith('_' + stamp), outs
print('drop and export: ok', outs)
log = A.LabLog(w, w.library)
log.resize(760, 300)
log.grab().save(os.path.join(out, '6_lab_log.png'))
# the Photo Lab: drop off a folder, pick a film (previews on the first photo), a lab, send it, collect the prints
pl = w.photolab
w.set_mode('photolab')
assert w.stack.currentWidget() is pl and pl.pages.currentIndex() == 0
lab_src = os.path.join(tmp, 'holiday')
os.makedirs(lab_src)
for k in range(4):
    fixtures.frame(200 + k).save(os.path.join(lab_src, 'DSC_%04d.jpg' % k))
mime = QMimeData()
mime.setUrls([QUrl.fromLocalFile(lab_src)])
w.dropEvent(QDropEvent(QPointF(20, 20), A.Qt.CopyAction, mime, A.Qt.LeftButton, A.Qt.NoModifier))
assert pl.pending and len(pl.pending) == 4 and pl.name.text() == 'holiday' and pl.btn_drop_next.isEnabled(), pl.pending
shot('11_photolab_drop.png')
pl.drop_off()
wait(lambda: pl.pages.currentIndex() == 1 and not w.jobs, 60)
assert pl.roll.own and pl.roll.name == 'holiday'
wait(lambda: not w.jobs, 60)
shot('11b_photolab_film.png')
pl.film_buttons['VELV'].setChecked(True)
pl.film_next()
assert pl.pages.currentIndex() == 2 and 'Velvia' in pl.lab_sub.text(), pl.lab_sub.text()
assert any(k.startswith('my:') for k in pl.lab_buttons)               # your own recipes are lab services too
assert not pl.dark_note.isVisible()
wait(lambda: not w.jobs, 60)
shot('11c_photolab_lab.png')
pl.lab_buttons['look:Faded 70s snapshot'].setChecked(True)
pl.size.setCurrentIndex(pl.size.findData(1600))
pl.send()
wait(lambda: not w.busy and not w.jobs and pl.pages.currentIndex() == 4, 180)
wait(lambda: pl.fs is not None and pl.fs.isVisible(), 10)                # the prints come back big
fs = pl.fs
fs.resize(1280, 800)
wait(lambda: not w.jobs and fs.canvas.pm is not None, 30)
QTest.keyClick(fs, A.Qt.Key_I)
assert 'Velvia' in fs.canvas.info and 'Faded 70s snapshot' in fs.canvas.info, fs.canvas.info
fs.grab().save(os.path.join(out, '11d_photolab_fullscreen.png'))
QTest.keyClick(fs, A.Qt.Key_Right)
assert pl.strip.currentRow() == 1
QTest.keyClick(fs, A.Qt.Key_Escape)
qa.processEvents()
lc = pl.labcard
assert lc['film'] == 'Velvia' and lc['look'] == 'Faded 70s snapshot' and len(lc['frames']) == 4, lc
assert pl.strip.count() == 4
wait(lambda: not w.jobs and pl.view.canvas.pm is not None)
shot('11e_photolab_prints.png')
lexp = os.path.join(tmp, 'labexport')
os.makedirs(lexp)
A.QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: lexp)
pl_zip = os.path.join(lexp, 'roll.zip')
A.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (pl_zip, ''))
pl.export_folder()
pl.export_zip()
import zipfile                                                      # noqa: E402
assert len([n for n in os.listdir(os.path.join(lexp, [d for d in os.listdir(lexp) if os.path.isdir(os.path.join(lexp, d))][0]))]) == 5
assert len(zipfile.ZipFile(pl_zip).namelist()) == 5                  # four prints and the contact sheet
# Darkroom settings of a frame are kept in the Photo Lab unless every frame should print the same
rid = pl.rid()
w.library.set_frame_settings(rid, [2], A.lab.Recipe(push=2), None)
pl.reprint()
assert pl.pages.currentIndex() == 1 and pl.film_buttons['VELV'].isChecked()
pl.film_buttons['ACRO'].setChecked(True)
pl.film_next()
assert pl.dark_note.isVisible() and '1 frame keeps' in pl.dark_note.text(), pl.dark_note.text()
pl.dark_note.setChecked(True)
pl.send()
wait(lambda: not w.busy and not w.jobs and pl.pages.currentIndex() == 4, 180)
if pl.fs is not None:
    pl.fs.close()
qa.processEvents()
assert w.library.frame_settings(rid) == {} and pl.labcard['film'] == 'Acros'
assert len(w.library.developments(rid)) == 2                          # the first prints are kept
pl.to_darkroom()
assert w.mode == 'darkroom' and w.roll is not None and w.roll_key() == rid and w.tabs.currentIndex() == 1
assert w.dev_pick.currentData() == pl.folder
print('photo lab: ok')
# audit fixes: the sliders show their value and count however they are moved; the name at the top goes back to the start screen;
# the window fits a small laptop screen (the lab's settings scroll, the tabs are never squeezed)
w.tabs.setCurrentIndex(0)
w.c_grain.setValue(140)
assert w.c_grain.parentWidget().findChildren(A.QLabel)[0].text() == '140 %'
wait(lambda: not w.recipe_timer.isActive() and not w.jobs, 10)
assert w.c_look.currentData() == 'custom'
w.set_recipe(A.lab.Recipe())
assert w.tabs.tabBar().tabRect(2).width() >= w.tabs.tabBar().tabSizeHint(2).width() - 1     # CONTACT SHEET is not cut off
w.resize(1240, 700)
for _ in range(20):
    qa.processEvents()
assert w.height() <= 700 and w.width() <= 1240, (w.width(), w.height())
shot('12_small_window.png')
w.resize(1400, 880)
w.show_start()
assert w.stack.currentWidget() is w.start and not w.btn_mode_dark.isChecked() and not w.btn_mode_lab.isChecked()
w.start.b_dark.click()
assert w.mode == 'darkroom'
print('audit fixes: ok')
# an ordinary folder opened with "Open folder…" becomes a roll of own photos, with the film to choose (the Film menu is always there)
plain = os.path.join(tmp, 'plainfolder')
os.makedirs(plain)
for k in range(3):
    fixtures.frame(300 + k).save(os.path.join(plain, 'IMG_%d.jpg' % k))
seen2 = {}
A.LoadPhotos.exec = lambda self: (seen2.update(paths=list(self.paths), name=self.name.text()), 0)[-1]
w.set_mode('darkroom')
w.open_source(plain)
wait(lambda: 'paths' in seen2, 20)
assert len(seen2['paths']) == 3 and seen2['name'] == 'plainfolder' and w.source_rolls == [], seen2
assert w.c_film.isVisible()
print('plain folder: ok')
# the developing animation paints at every moment of every step, with every mood, without a hitch (tongs, clock, steam, drips, fog)
from safelight import viewer as V                                   # noqa: E402
cv = V.Canvas()
cv.resize(900, 560)
cv.show()
pm_a = A.to_pixmap(fixtures.frame(7))
for mood in ({}, {'expired': 12, 'leak': True, 'mono': True, 'cross': True, 'push': 2}, {'push': -1}):
    cv.start_develop('TEST', mood)
    cv.dev['line'] = [pm_a] * 3
    cv.dev['cur'], cv.dev['started'], cv.dev['total'] = pm_a, 1, 12
    for ph in (0.0, 0.05, 0.2, 0.5, 0.59, 0.72, 0.9, 0.97, 1.0):
        cv.dev['t0'] = time.monotonic() - ph * 2.4
        cv.grab()
    cv.dev['fast'] = True
    cv.grab()
    cv.dev_cancel()
cv.close()
print('animation paints: ok')
print('lab log rows:', len(w.library.lablog()), 'stats', w.library.stats())
print('GUI SMOKE OK ->', out)

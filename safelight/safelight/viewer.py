"""The big view and the filmstrip (Lightroom-style): one frame large, the roll along the bottom, everything in the main window.

FrameView draws its picture rotated on the fly (QPainter), so turning a frame is instant however often it is clicked: the slow work (a
preview render, rewriting a print) happens once, in the background, on the unrotated picture.
"""
import math
import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QListView, QListWidget, QPushButton, QVBoxLayout, QWidget

RED = '#e0372f'


class Canvas(QWidget):
    """The picture, fitted and rotated, with overlays: a flash after each rotation, a 'rotated' badge, a 'developing' note."""

    def __init__(self):
        super().__init__()
        self.pm = None
        self.rotation = 0
        self.flash_text = ''
        self.loading = ''
        self.empty = ''
        self._flash_id = 0
        self.caption = ''
        self.hint = ''
        self.dev = None                      # the developing animation's state while a roll is in the lab
        self.dev_timer = QTimer(self)
        self.dev_timer.setInterval(33)
        self.dev_timer.timeout.connect(self._tick)
        self.setMinimumSize(320, 220)

    def set_picture(self, pm, rotation=0):
        self.pm, self.rotation = pm, rotation % 360
        self.update()

    def flash(self, text, ms=1000):
        self._flash_id += 1
        fid = self._flash_id
        self.flash_text = text
        self.update()
        QTimer.singleShot(ms, lambda: self._unflash(fid))

    def _unflash(self, fid):
        if fid == self._flash_id:
            self.flash_text = ''
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setRenderHint(QPainter.Antialiasing)
        if self.dev is not None:
            self._paint_develop(p)
            p.end()
            return
        p.fillRect(self.rect(), QColor('#0d0c0c'))
        W, H = self.width(), self.height()
        if self.pm is not None and not self.pm.isNull():
            pw, ph = self.pm.width(), self.pm.height()
            side = self.rotation in (90, 270)
            bw, bh = (ph, pw) if side else (pw, ph)                 # the box the turned picture needs
            s = min((W - 24) / bw, (H - 24) / bh)
            p.save()
            p.translate(W / 2, H / 2)
            p.rotate(self.rotation)
            p.drawPixmap(QRectF(-pw * s / 2, -ph * s / 2, pw * s, ph * s), self.pm, QRectF(0, 0, pw, ph))
            p.restore()
        elif self.empty:
            p.setPen(QColor('#6a655e'))
            p.drawText(self.rect(), Qt.AlignCenter, self.empty)
        if self.caption and self.pm is not None:
            self._pill(p, QPointF(10, 8), self.caption, '#171515', '#b5aea3', anchor='tl')
            if self.hint:
                self._pill(p, QPointF(W - 10, H - 10), self.hint, '#171515', '#8d877d', anchor='br')
        if self.rotation and self.pm is not None:
            self._pill(p, QPointF(10, H - 10), 'Rotated %d°  ·  saved' % self.rotation, '#2a1715', '#f0a49c', anchor='bl')
        if self.loading:
            self._pill(p, QPointF(10, 36), self.loading, '#262424', '#e8e4dc', anchor='tl')
        if self.flash_text:
            f = QFont(self.font())
            f.setPointSize(30)
            f.setBold(True)
            p.setFont(f)
            r = p.fontMetrics().boundingRect(self.flash_text).adjusted(-28, -16, 28, 16)
            r.moveCenter(self.rect().center())
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(20, 18, 18, 215))
            p.drawRoundedRect(QRectF(r), 14, 14)
            p.setPen(QColor(RED))
            p.drawText(r, Qt.AlignCenter, self.flash_text)
        p.end()

    # ------------------------------------------------------------ the developing animation
    # Under a red safelight: each print is lowered into the developer tray and its picture slowly comes up on the paper (with the
    # liquid moving over it), then it goes through the stop bath, the fixer (the room light may go on) and the wash, and is hung on the
    # drying line with a clothespin. The stage bar and the frame counter run along the bottom. Prints arrive from the lab job; when they
    # arrive faster than the animation, it speeds up so it never falls behind.
    STAGES = (('DEVELOPER', 0.0), ('STOP BATH', 0.58), ('FIXER', 0.70), ('WASH', 0.86), ('DRY', 1.0))

    def start_develop(self, title):
        self.dev = {'title': title, 'queue': [], 'cur': None, 't0': 0.0, 'line': [], 'done': 0, 'total': 0,
                    'note': 'Loading the film into the tank…', 'finish': None, 'finished_at': None, 'start': time.monotonic()}
        self.dev_timer.start()
        self.update()

    def dev_note(self, text):
        if self.dev is not None:
            self.dev['note'] = text
            self.update()

    def dev_feed(self, pm, done, total):
        if self.dev is not None:
            self.dev['queue'].append(pm)
            self.dev['done'], self.dev['total'] = done, total
            self.dev['note'] = ''

    def dev_finish(self, callback, text):
        """Called when the lab job is done: the animation plays out the prints still in the queue, shows `text`, then calls back."""
        if self.dev is None:
            callback()
            return
        self.dev['finish'], self.dev['end_text'] = callback, text

    def dev_cancel(self):
        self.dev = None
        self.dev_timer.stop()
        self.update()

    def mousePressEvent(self, e):
        """A click during developing hangs the prints still in the queue at once (skips the rest of the animation)."""
        d = self.dev
        if d is not None and d['finish']:
            d['line'].extend(([d['cur']] if d['cur'] is not None else []) + d['queue'])
            d['cur'], d['queue'] = None, []
            self.update()
        super().mousePressEvent(e)

    def _tick(self):
        d = self.dev
        if d is None:
            self.dev_timer.stop()
            return
        now = time.monotonic()
        if d['cur'] is not None and self._phase(now) >= 1.0:
            d['line'].append(d['cur'])
            d['cur'] = None
        if d['cur'] is None and d['queue']:                    # the next print goes in at once (no empty-tray flicker)
            d['cur'], d['t0'] = d['queue'].pop(0), now
        if d['finish'] and d['cur'] is None and not d['queue']:
            if d['finished_at'] is None:
                d['finished_at'] = now
            elif now - d['finished_at'] > 1.2:
                cb = d['finish']
                self.dev_cancel()
                cb()
                return
        self.update()

    def _phase(self, now):
        d = self.dev
        dur = 2.4 / (1.0 + 0.6 * len(d['queue']))        # a backlog makes the prints move faster
        return (now - d['t0']) / dur if d['cur'] is not None else 0.0

    def _paint_develop(self, p):
        d = self.dev
        W, H = self.width(), self.height()
        now = time.monotonic()
        ph = self._phase(now)
        stage = max(k for k, (_, at) in enumerate(self.STAGES[:-1]) if ph >= at) if d['cur'] is not None else (4 if d['finish'] else 0)
        lights_on = d['cur'] is not None and ph >= 0.70                  # after the fixer the room light may go on
        # the darkroom: black, a red safelight glowing from the top
        p.fillRect(self.rect(), QColor('#0a0808'))
        g = QRadialGradient(QPointF(W * 0.5, -H * 0.15), H * 1.1)
        glow = QColor(170, 20, 18, 120 if not lights_on else 60)
        g.setColorAt(0.0, glow)
        g.setColorAt(1.0, QColor(10, 8, 8, 0))
        p.fillRect(self.rect(), g)
        f = QFont(self.font())
        f.setPointSize(10)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        p.setFont(f)
        p.setPen(QColor('#d9a19a'))
        p.drawText(QRectF(16, 8, W - 32, 22), Qt.AlignLeft | Qt.AlignVCenter, d['title'])
        if d['total']:
            p.drawText(QRectF(16, 8, W - 32, 22), Qt.AlignRight | Qt.AlignVCenter, 'FRAME %d / %d' % (min(d['done'], d['total']), d['total']))
        # the drying line with the prints hung so far (the latest ones that fit)
        ly = 54
        p.setPen(QPen(QColor(150, 120, 110, 160), 1.5))
        p.drawLine(QPointF(10, ly), QPointF(W - 10, ly))
        th = max(40, min(90, int(H * 0.15)))
        x, hung = W - 16, []
        for pm in reversed(d['line']):
            tw = th * pm.width() / max(1, pm.height())
            if x - tw < 16:
                break
            x -= tw + 12
            hung.append((x + 12, tw, pm))
        for k, (hx, tw, pm) in enumerate(reversed(hung)):
            p.save()
            p.translate(hx + tw / 2, ly)
            p.rotate((-1.5 if k % 2 else 1.5))
            p.drawPixmap(QRectF(-tw / 2, 4, tw, th), pm, QRectF(0, 0, pm.width(), pm.height()))
            p.fillRect(QRectF(-tw / 2, 4, tw, th), QColor(150, 20, 15, 40))
            p.setBrush(QColor('#b88a5a'))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(-4, -6, 8, 16), 2, 2)                # the clothespin
            p.restore()
        # the tray
        top = ly + th + 26
        bar_h = 56
        tray = QRectF(W * 0.12, top, W * 0.76, max(80, H - top - bar_h - 14))
        p.setPen(QPen(QColor('#2b2a2c'), 3))
        p.setBrush(QColor('#151416'))
        p.drawRoundedRect(tray, 14, 14)
        liquid = tray.adjusted(10, 10, -10, -10)
        lg = QLinearGradient(liquid.topLeft(), liquid.bottomRight())
        tint = {0: QColor(40, 30, 20), 1: QColor(30, 30, 34), 2: QColor(26, 34, 30), 3: QColor(22, 30, 40)}.get(stage, QColor(20, 20, 22))
        lg.setColorAt(0, tint.lighter(140))
        lg.setColorAt(1, tint)
        p.setPen(Qt.NoPen)
        p.setBrush(lg)
        p.drawRoundedRect(liquid, 8, 8)
        if d['cur'] is not None:
            pm = d['cur']
            s = min(liquid.width() * 0.86 / pm.width(), liquid.height() * 0.86 / pm.height())
            pw, phh = pm.width() * s, pm.height() * s
            # the print slides in at the start and out at the end
            slide = 0.0
            if ph < 0.08:
                slide = (1 - ph / 0.08) * (liquid.width() * 0.6)
            elif ph > 0.94:
                slide = -((ph - 0.94) / 0.06) * (liquid.width() * 0.6)
            r = QRectF(liquid.center().x() - pw / 2 + slide, liquid.center().y() - phh / 2, pw, phh)
            p.setBrush(QColor('#f3eee2'))
            p.drawRect(r)                                                 # the paper
            emerge = min(1.0, max(0.0, (ph - 0.06) / 0.50))
            emerge = emerge * emerge * (3 - 2 * emerge)                   # the picture comes up slowly, then fast
            p.setOpacity(emerge)
            p.drawPixmap(r, pm, QRectF(0, 0, pm.width(), pm.height()))
            p.setOpacity(1.0)
            if not lights_on:
                p.fillRect(r, QColor(170, 20, 15, 70))                    # everything is red under the safelight
            # the liquid moving over the print (the tray is rocked)
            p.setBrush(Qt.NoBrush)                                        # (the paper's brush would fill the waves)
            p.setPen(QPen(QColor(255, 240, 230, 40), 1.5))
            for k in range(4):
                path = QPainterPath()
                y0 = liquid.top() + liquid.height() * (0.18 + 0.21 * k) + math.sin(now * 1.6 + k) * 6
                path.moveTo(liquid.left() + 6, y0)
                for i in range(1, 25):
                    xx = liquid.left() + 6 + i * (liquid.width() - 12) / 24
                    path.lineTo(xx, y0 + math.sin(now * 2.3 + i * 0.6 + k * 1.3) * 3)
                p.drawPath(path)
        elif d['note'] or d['finish']:
            p.setPen(QColor('#d9a19a'))
            f2 = QFont(self.font())
            f2.setPointSize(13)
            p.setFont(f2)
            p.drawText(liquid, Qt.AlignCenter, d.get('end_text') if d['finish'] else d['note'])
        # the stages and the progress
        y = H - bar_h
        n = len(self.STAGES)
        f3 = QFont(self.font())
        f3.setPointSize(9)
        f3.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        p.setFont(f3)
        cw = (W - 32) / n
        for k, (name, _) in enumerate(self.STAGES):
            on = k == stage and (d['cur'] is not None or d['finish'])
            p.setPen(QColor('#e0372f') if on else (QColor('#a8a197') if k < stage else QColor('#5d5952')))
            p.drawText(QRectF(16 + k * cw, y, cw, 20), Qt.AlignCenter, ('●  ' if on else '') + name)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor('#221f1f'))
        p.drawRoundedRect(QRectF(16, y + 28, W - 32, 6), 3, 3)
        frac = (d['done'] / d['total']) if d['total'] else 0.0
        p.setBrush(QColor('#e0372f'))
        p.drawRoundedRect(QRectF(16, y + 28, (W - 32) * frac, 6), 3, 3)

    def _pill(self, p, at, text, bg, fg, anchor):
        f = QFont(self.font())
        f.setPointSize(9)
        p.setFont(f)
        r = p.fontMetrics().boundingRect(text).adjusted(-10, -5, 10, 5)
        if anchor == 'bl':
            r.moveBottomLeft(at.toPoint())
        elif anchor == 'br':
            r.moveBottomRight(at.toPoint())
        else:
            r.moveTopLeft(at.toPoint())
        p.setPen(QPen(QColor(fg).darker(160)))
        p.setBrush(QColor(bg))
        p.drawRoundedRect(QRectF(r), 8, 8)
        p.setPen(QColor(fg))
        p.drawText(r, Qt.AlignCenter, text)


class FrameView(QWidget):
    """Toolbar (view modes, rotate buttons with their keys), the canvas, and a caption with the keyboard hints."""
    rotate = Signal(int)
    mode_changed = Signal(str)

    def __init__(self, modes=None, hint=''):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 0)
        lay.setSpacing(4)
        bar = QHBoxLayout()
        self.mode = modes[0][0] if modes else None
        self.mode_buttons = {}
        if modes:
            group = QButtonGroup(self)
            group.setExclusive(True)
            for k, (key, label, tip) in enumerate(modes):
                b = QPushButton(label)
                b.setCheckable(True)
                b.setToolTip(tip)
                b.setObjectName('seg')
                b.setChecked(k == 0)
                b.clicked.connect(lambda _=False, key=key: self.set_mode(key, emit=True))
                group.addButton(b)
                bar.addWidget(b)
                self.mode_buttons[key] = b
        bar.addStretch(1)
        self.rot_label = QLabel('')
        self.rot_label.setObjectName('muted')
        bar.addWidget(self.rot_label)
        self.b_left = QPushButton('⟲  Rotate left   L')
        self.b_right = QPushButton('⟳  Rotate right   R')
        self.b_left.setToolTip('Turn this frame 90° anticlockwise (key L). It stays turned everywhere: filmstrip, previews, prints, '
                               'contact sheet.')
        self.b_right.setToolTip('Turn this frame 90° clockwise (key R). It stays turned everywhere: filmstrip, previews, prints, '
                                'contact sheet.')
        self.b_left.clicked.connect(lambda: self.rotate.emit(-90))
        self.b_right.clicked.connect(lambda: self.rotate.emit(90))
        bar.addWidget(self.b_left)
        bar.addWidget(self.b_right)
        lay.addLayout(bar)
        self.canvas = Canvas()
        self.canvas.hint = hint
        lay.addWidget(self.canvas, 1)
        self.set_enabled(False)

    def set_mode(self, key, emit=False):
        if key not in self.mode_buttons:
            return
        self.mode = key
        self.mode_buttons[key].setChecked(True)
        if emit:
            self.mode_changed.emit(key)

    def next_mode(self):
        keys = list(self.mode_buttons)
        if keys:
            self.set_mode(keys[(keys.index(self.mode) + 1) % len(keys)], emit=True)

    def set_enabled(self, on):
        self.b_left.setEnabled(on)
        self.b_right.setEnabled(on)
        for b in self.mode_buttons.values():
            b.setEnabled(on)

    def show_picture(self, pm, rotation, caption, loading=''):
        self.canvas.loading = loading
        self.canvas.caption = caption
        self.canvas.set_picture(pm, rotation)
        self.rot_label.setText(('turned %d°   ' % (rotation % 360)) if rotation % 360 else '')
        self.set_enabled(pm is not None)

    def set_rotation(self, rotation, delta):
        self.canvas.rotation = rotation % 360
        self.canvas.flash('↻  %d°' % (rotation % 360) if delta > 0 else '↺  %d°' % (rotation % 360))
        self.rot_label.setText(('turned %d°   ' % (rotation % 360)) if rotation % 360 else 'straight   ')

    def clear(self, text=''):
        self.canvas.empty = text
        self.canvas.loading = ''
        self.canvas.caption = ''
        self.canvas.set_picture(None)
        self.rot_label.setText('')
        self.set_enabled(False)


def filmstrip(icon, bg):
    """A one-row, horizontally scrolling strip of frames."""
    w = QListWidget()
    w.setViewMode(QListView.IconMode)
    w.setFlow(QListView.LeftToRight)
    w.setWrapping(False)
    w.setMovement(QListView.Static)
    w.setResizeMode(QListView.Adjust)
    w.setIconSize(icon)
    w.setGridSize(QSize(icon.width() + 6, icon.height() + 8))
    w.setUniformItemSizes(True)
    w.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    w.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    w.setFixedHeight(icon.height() + 30)
    w.setStyleSheet('QListWidget { background: %s; border-radius: 6px; } QListWidget::item { border: 2px solid transparent; border-radius: 4px; }'
                    ' QListWidget::item:selected { background: transparent; border: 2px solid %s; }' % (bg, RED))
    return w

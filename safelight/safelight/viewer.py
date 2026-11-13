"""The big view and the filmstrip (Lightroom-style): one frame large, the roll along the bottom, everything in the main window.

FrameView draws its picture rotated on the fly (QPainter), so turning a frame is instant however often it is clicked: the slow work (a
preview render, rewriting a print) happens once, in the background, on the unrotated picture.
"""
import math
import time

import numpy as np

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QListView, QListWidget, QPushButton, QVBoxLayout, QWidget

RED = '#e0372f'


class ElidedLabel(QLabel):
    """A one-line label that shortens its text with … when there is no room, instead of pushing its neighbours away."""

    def minimumSizeHint(self):
        return QSize(24, super().minimumSizeHint().height())

    def paintEvent(self, e):
        p = QPainter(self)
        p.setFont(self.font())
        p.setPen(self.palette().color(self.foregroundRole()))
        r = self.contentsRect()
        p.drawText(r, int(self.alignment()) | Qt.TextSingleLine, self.fontMetrics().elidedText(self.text(), Qt.ElideRight, r.width()))
        p.end()


class Canvas(QWidget):
    """The picture, fitted and rotated, with overlays: a flash after each rotation, a 'rotated' badge, a 'developing' note."""
    double_clicked = Signal()

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
        self.info = ''                       # full screen: film, recipe, date (key I), in a box at the bottom
        self.badge = ''                      # full screen: 'ORIGINAL' while Space is held
        self.margin = 24                     # room around the picture (full screen: none)
        self.pm2 = None                      # full screen, compare: the other print (split slider, or side by side)
        self.labels = ('', '')               # compare: what the left and the right picture are
        self.split = 0.5
        self._cmp_rect = None
        self.dev = None                      # the developing animation's state while a roll is in the lab
        self.dev_timer = QTimer(self)
        self.dev_timer.setInterval(33)
        self.dev_timer.timeout.connect(self._tick)
        self.setMinimumSize(320, 220)

    def set_picture(self, pm, rotation=0):
        self.pm, self.rotation = pm, rotation % 360
        self.update()

    def flash(self, text, ms=1000):
        if not hasattr(self, '_flash_timer'):              # owned by the canvas, so it never fires after the canvas is gone
            self._flash_timer = QTimer(self)
            self._flash_timer.setSingleShot(True)
            self._flash_timer.timeout.connect(self._unflash)
        self.flash_text = text
        self.update()
        self._flash_timer.start(ms)

    def _unflash(self):
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
        if self.pm is not None and not self.pm.isNull() and self.pm2 is not None and not self.pm2.isNull():
            self._paint_compare(p, W, H)
        elif self.pm is not None and not self.pm.isNull():
            pw, ph = self.pm.width(), self.pm.height()
            side = self.rotation in (90, 270)
            bw, bh = (ph, pw) if side else (pw, ph)                 # the box the turned picture needs
            s = min((W - self.margin) / bw, (H - self.margin) / bh)
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
        if self.rotation and self.pm is not None and self.pm2 is None:
            self._pill(p, QPointF(10, H - 10), 'Rotated %d°  ·  saved' % self.rotation, '#2a1715', '#f0a49c', anchor='bl')
        if self.loading:
            self._pill(p, QPointF(10, 36), self.loading, '#262424', '#e8e4dc', anchor='tl')
        if self.badge and self.pm is not None:
            self._pill(p, QPointF(W - 10, 8), self.badge, '#2a1715', '#f0a49c', anchor='tr')
        if self.info and self.pm is not None:
            f = QFont(self.font())
            f.setPointSize(10)
            p.setFont(f)
            r = p.fontMetrics().boundingRect(0, 0, int(W * 0.8), H, Qt.AlignLeft | Qt.TextWordWrap, self.info)
            box = QRectF(r).adjusted(-16, -12, 16, 12)
            box.moveCenter(QPointF(W / 2, H - 48 - box.height() / 2))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(20, 18, 18, 225))
            p.drawRoundedRect(box, 10, 10)
            p.setPen(QColor('#e8e4dc'))
            p.drawText(box.adjusted(16, 12, -16, -12), Qt.AlignLeft | Qt.TextWordWrap, self.info)
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

    def start_develop(self, title, mood=None):
        """mood: what the animation shows of the user's choices: expired (years: the prints come up foggy and clear), leak (the first
        print catches a light leak), mono (black and white: a dimmer red), cross (cross-processing: a green developer)."""
        self.dev = {'title': title, 'queue': [], 'cur': None, 't0': 0.0, 'line': [], 'done': 0, 'total': 0, 'mood': dict(mood or {}),
                    'fast': False, 'started': 0, 'img': None,
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

    @staticmethod
    def _fit(pm, box):
        s = min(box.width() / pm.width(), box.height() / pm.height())
        w, h = pm.width() * s, pm.height() * s
        return QRectF(box.center().x() - w / 2, box.center().y() - h / 2, w, h)

    def _paint_compare(self, p, W, H):
        """Two prints of one frame. Same shape: one over the other with a split line to drag. Different shapes (another border,
        another turn): side by side."""
        a1, a2 = self.pm.width() / self.pm.height(), self.pm2.width() / self.pm2.height()
        top, bottom = 44, 70
        if abs(a1 / a2 - 1) < 0.004:                                      # (another border changes the shape a little)
            r = self._fit(self.pm, QRectF(self.margin, top, W - 2 * self.margin, H - top - bottom))
            self._cmp_rect = r
            p.drawPixmap(r, self.pm, QRectF(self.pm.rect()))
            x = r.left() + r.width() * self.split
            p.save()
            p.setClipRect(QRectF(x, r.top(), r.right() - x, r.height()))
            p.drawPixmap(r, self.pm2, QRectF(self.pm2.rect()))
            p.restore()
            p.setPen(QPen(QColor('#f2eee6'), 2))
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
            p.setBrush(QColor(RED))
            p.setPen(QPen(QColor('#f2eee6'), 2))
            p.drawEllipse(QPointF(x, r.center().y()), 11, 11)
        else:
            self._cmp_rect = None
            half = (W - 3 * 12) / 2
            r1 = self._fit(self.pm, QRectF(12, top, half, H - top - bottom))
            r2 = self._fit(self.pm2, QRectF(24 + half, top, half, H - top - bottom))
            p.drawPixmap(r1, self.pm, QRectF(self.pm.rect()))
            p.drawPixmap(r2, self.pm2, QRectF(self.pm2.rect()))
        # what each side is: left at the left edge, right at the right edge, above the key hints, each at most half the width
        f = QFont(self.font())
        f.setPointSize(9)
        fm = QFontMetrics(f)
        room = int(W / 2 - 40)
        self._pill(p, QPointF(10, H - 40), fm.elidedText('◀  ' + self.labels[0], Qt.ElideMiddle, room), '#171515', '#e8e4dc', anchor='bl')
        self._pill(p, QPointF(W - 10, H - 40), fm.elidedText(self.labels[1] + '  ▶', Qt.ElideMiddle, room), '#2a1715', '#f0a49c',
                   anchor='br')

    def mouseMoveEvent(self, e):
        r = self._cmp_rect
        if self.pm2 is not None and r is not None and e.buttons() & Qt.LeftButton:
            self.split = min(1.0, max(0.0, (e.position().x() - r.left()) / max(1.0, r.width())))
            self.update()
        super().mouseMoveEvent(e)

    def mouseDoubleClickEvent(self, e):
        if self.dev is None and self.pm is not None:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(e)

    def mousePressEvent(self, e):
        """A click during developing hangs the prints still in the queue at once (skips the rest of the animation)."""
        d = self.dev
        if d is not None and d['finish']:
            d['line'].extend(([d['cur']] if d['cur'] is not None else []) + d['queue'])
            d['cur'], d['queue'] = None, []
            self.update()
        elif d is not None and not d['fast']:
            d['fast'] = True                                              # a click speeds the animation up (a second skips the rest)
            self.update()
        if self.pm2 is not None and self._cmp_rect is not None and e.button() == Qt.LeftButton:
            self.mouseMoveEvent(e)                                       # a click moves the split line there
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
            d['started'] += 1
            d['img'] = None
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
        if d['fast']:
            dur /= 3.0
        return (now - d['t0']) / dur if d['cur'] is not None else 0.0

    PAPER = np.array([243.0, 238.0, 226.0], dtype=np.float32)

    def _prepare(self, pm, first):
        """The current print as arrays, once: its colours, how light each pixel is, and (the first print, with leaks) a light leak."""
        im = pm.toImage().convertToFormat(QImage.Format_RGB888)
        if im.width() > 560:
            im = im.scaledToWidth(560, Qt.SmoothTransformation)
        w, h = im.width(), im.height()
        ptr = im.constBits()
        rgb = np.frombuffer(ptr, dtype=np.uint8, count=im.bytesPerLine() * h).reshape(h, im.bytesPerLine())[:, :w * 3].reshape(h, w, 3)
        rgb = rgb.astype(np.float32)
        light = (rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114) / 255.0
        leak = None
        if first and self.dev['mood'].get('leak'):
            xs = np.linspace(0, 1, w, dtype=np.float32)[None, :]
            ys = np.linspace(0, 1, h, dtype=np.float32)[:, None]
            g = np.clip(1.0 - np.sqrt((xs - 0.0) ** 2 * 1.0 + (ys - 0.25) ** 2 * 1.6) * 1.7, 0, 1) ** 1.6
            leak = g[..., None] * np.array([255.0, 120.0, 40.0], dtype=np.float32)
        return rgb, light, leak

    def _emerged(self, emerge):
        """The print as it looks at this moment in the developer: the darkest tones appear first, then the mid-tones, the highlights
        last (as on real paper); expired film is foggy at first; a light leak glows in late. Returns a QImage."""
        d = self.dev
        if d['img'] is None:
            d['img'] = self._prepare(d['cur'], d['started'] == 1)
        rgb, light, leak = d['img']
        a = np.clip((emerge - 0.6 * light) / 0.4, 0, 1)[..., None]
        out = self.PAPER * (1 - a) + rgb * a
        if leak is not None:
            out = out + leak * (emerge ** 3) * 0.55 * a
        years = d['mood'].get('expired', 0)
        if years:
            v = min(0.45, years * 0.035) * (1 - 0.75 * emerge)            # fog: it clears as the print comes up
            out = out * (1 - v) + np.array([150.0, 138.0, 128.0], dtype=np.float32) * v
        out = np.ascontiguousarray(np.clip(out, 0, 255).astype(np.uint8))
        h, w = out.shape[:2]
        return QImage(out.data, w, h, w * 3, QImage.Format_RGB888).copy()

    def _paint_develop(self, p):
        d = self.dev
        W, H = self.width(), self.height()
        now = time.monotonic()
        ph = self._phase(now)
        stage = max(k for k, (_, at) in enumerate(self.STAGES[:-1]) if ph >= at) if d['cur'] is not None else (4 if d['finish'] else 0)
        lights_on = d['cur'] is not None and ph >= 0.70                  # after the fixer the room light may go on
        mood = d['mood']
        # the darkroom: black, a red safelight glowing from the top (dimmer for black and white); the room light goes on after the fixer
        p.fillRect(self.rect(), QColor('#1d1a18' if lights_on else '#0a0808'))
        g = QRadialGradient(QPointF(W * 0.5, -H * 0.15), H * 1.1)
        glow = QColor(170, 20, 18, (70 if mood.get('mono') else 120) if not lights_on else 40)
        g.setColorAt(0.0, glow)
        g.setColorAt(1.0, QColor(10, 8, 8, 0))
        p.fillRect(self.rect(), g)
        if not lights_on:                                                # dust drifting in the safelight beam
            p.setPen(Qt.NoPen)
            for i in range(34):
                x = (i * 97.3 + now * (5 + (i % 4) * 3)) % W
                y = (i * 53.1 + math.sin(now * 0.5 + i) * 18 + now * (3 + i % 5)) % H
                beam = max(0.0, 1.0 - abs(x - W * 0.5) / (W * (0.12 + 0.45 * y / H)))      # a cone from the lamp
                if beam > 0:
                    p.setBrush(QColor(255, 190, 180, int(70 * beam * (0.5 + 0.5 * math.sin(now * 1.3 + i)))))
                    p.drawEllipse(QPointF(x, y), 1.2 + (i % 3) * 0.5, 1.2 + (i % 3) * 0.5)
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
            if not d['fast']:                                             # a drop forms at the bottom edge, falls, fades
                t = (now * 0.45 + k * 0.37) % 1.0
                if t < 0.55:
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(210, 180, 170, int(190 * (1 - t / 0.55))))
                    dy = ly + 4 + th + (t ** 2) * 70
                    p.drawEllipse(QPointF(hx + tw * (0.3 + 0.4 * ((k * 7) % 3) / 2), dy), 1.6, 2.4 + t * 3)
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
        if mood.get('cross') and stage == 0:
            tint = QColor(26, 46, 28)                                    # cross-processing: slide film in the wrong (green) developer
        lg.setColorAt(0, tint.lighter(140))
        lg.setColorAt(1, tint)
        p.setPen(Qt.NoPen)
        p.setBrush(lg)
        p.drawRoundedRect(liquid, 8, 8)
        if stage in (0, 2) and not d['fast']:                            # the warm developer and the fixer steam a little
            for i in range(9):
                t = (now * 0.12 + i * 0.113) % 1.0
                sx = liquid.left() + liquid.width() * (0.08 + 0.84 * ((i * 0.381) % 1.0)) + math.sin(now * 0.9 + i) * 14
                sy = liquid.top() + 6 - t * 46
                p.setBrush(QColor(235, 215, 210, int(20 * math.sin(math.pi * t))))
                p.drawEllipse(QPointF(sx, sy), 10 + t * 16, 6 + t * 9)
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
            if emerge > 0:
                p.drawImage(r, self._emerged(emerge))
            if not lights_on:
                p.fillRect(r, QColor(170, 20, 15, 70))                    # everything is red under the safelight
            if ph < 0.16 or ph > 0.90:                                    # tongs carry the print in, and lift it out
                self._tongs(p, r, ph)
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
        if d['cur'] is not None and tray.left() >= 64:                    # the darkroom clock, in the margin beside the tray
            self._clock(p, tray.left() / 2, top + 34, min(26.0, tray.left() / 2 - 8), ph, stage, mood.get('push', 0), now)
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
        # the room light comes on: a quick white flash as the print goes into the fixer
        if d['cur'] is not None and 0.70 <= ph < 0.80:
            p.fillRect(self.rect(), QColor(255, 250, 240, int(150 * (1 - (ph - 0.70) / 0.10))))
        # a hint that the animation can be sped up
        hint = ('click: skip the rest' if d['fast'] else 'click: speed up') if not d['finish'] else 'click: skip the rest'
        fh = QFont(self.font())
        fh.setPointSize(8)
        p.setFont(fh)
        p.setPen(QColor('#6a655e'))
        p.drawText(QRectF(16, H - 20, W - 32, 16), Qt.AlignRight | Qt.AlignVCenter, hint)

    @staticmethod
    def _tongs(p, r, ph):
        """A pair of steel tongs holding the print by its top edge: they bring it in, let go, and come back to take it out."""
        cx, top = r.center().x(), r.top()
        if ph < 0.16:
            lift = max(0.0, (ph - 0.08) / 0.08) * 70                      # after sliding in they let go and rise away
            grip = 1.0 - max(0.0, (ph - 0.08) / 0.08) * 0.6
        else:
            lift = max(0.0, (0.94 - ph) / 0.04) * 70                      # they come back down, grip, and the print slides out
            grip = 0.4 + 0.6 * (1 - max(0.0, (0.94 - ph) / 0.04))
        if lift >= 69.5:
            return
        pad = 5 + (1 - grip) * 9
        tip_y = top + 3 - lift
        piv = QPointF(cx + 38, tip_y - 78)
        steel = QColor(176, 170, 168)
        p.save()
        p.setBrush(Qt.NoBrush)
        for s in (-1, 1):
            tip = QPointF(cx + s * pad, tip_y)
            p.setPen(QPen(QColor(60, 58, 58), 7, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(tip, piv)
            p.setPen(QPen(steel, 4.5, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(tip, piv)
            p.setPen(QPen(QColor(110, 20, 16), 4.5, Qt.SolidLine, Qt.RoundCap))   # (red in the safelight)
            p.drawLine(QPointF(tip.x(), tip.y()), QPointF(tip.x(), tip.y() + 9))
        p.setPen(QPen(QColor(60, 58, 58), 7, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(piv, QPointF(piv.x() + 30, piv.y() - 36))
        p.setPen(QPen(steel, 4.5, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(piv, QPointF(piv.x() + 30, piv.y() - 36))
        p.restore()

    def _clock(self, p, cx, cy, rad, ph, stage, push, now):
        """The darkroom clock: shows the real time this step would take (the developer's follows push / pull), the hand sweeping through
        it as the step plays."""
        starts = (0.0, 0.58, 0.70, 0.86)
        ends = (0.58, 0.70, 0.86, 1.0)
        dev = {-1: 330, 0: 420, 1: 540, 2: 660}.get(push, 420)             # seconds: pull is shorter, push longer
        secs = (dev, 30, 300, 600)
        if stage > 3:
            return
        frac = max(0.0, min(1.0, (ph - starts[stage]) / (ends[stage] - starts[stage])))
        p.save()
        p.setPen(QPen(QColor(90, 30, 28), 2))
        p.setBrush(QColor(20, 14, 14))
        p.drawEllipse(QPointF(cx, cy), rad, rad)
        p.setPen(QPen(QColor(140, 60, 55), 1))
        for i in range(12):
            a = math.radians(i * 30)
            p.drawLine(QPointF(cx + math.sin(a) * rad * 0.82, cy - math.cos(a) * rad * 0.82),
                       QPointF(cx + math.sin(a) * rad * 0.94, cy - math.cos(a) * rad * 0.94))
        a = math.radians(360 * frac)                                       # the step's own sweep
        p.setPen(QPen(QColor(224, 55, 47), 2.2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx, cy), QPointF(cx + math.sin(a) * rad * 0.78, cy - math.cos(a) * rad * 0.78))
        p.setPen(QPen(QColor(200, 150, 145), 1))
        a2 = math.radians((now * 36) % 360)                                # a seconds hand that never stops
        p.drawLine(QPointF(cx, cy), QPointF(cx + math.sin(a2) * rad * 0.62, cy - math.cos(a2) * rad * 0.62))
        p.setBrush(QColor(224, 55, 47))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), 2.6, 2.6)
        f = QFont(self.font())
        f.setPointSize(8)
        p.setFont(f)
        p.setPen(QColor('#d9a19a'))
        e, t = int(secs[stage] * frac), secs[stage]
        p.drawText(QRectF(cx - 40, cy + rad + 4, 80, 14), Qt.AlignCenter, '%d:%02d / %d:%02d' % (e // 60, e % 60, t // 60, t % 60))
        p.restore()

    def _pill(self, p, at, text, bg, fg, anchor):
        f = QFont(self.font())
        f.setPointSize(9)
        p.setFont(f)
        r = p.fontMetrics().boundingRect(text).adjusted(-10, -5, 10, 5)
        if anchor == 'bl':
            r.moveBottomLeft(at.toPoint())
        elif anchor == 'br':
            r.moveBottomRight(at.toPoint())
        elif anchor == 'tr':
            r.moveTopRight(at.toPoint())
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
    fullscreen = Signal()

    def __init__(self, modes=None, hint=''):
        super().__init__()
        self.full = None                     # the FullScreen window showing this view, while it is open
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
        self.b_left = QPushButton('⟲  Rotate  L')
        self.b_right = QPushButton('⟳  Rotate  R')
        self.b_left.setToolTip('Turn this frame 90° anticlockwise (key L). It stays turned everywhere: filmstrip, previews, prints, '
                               'contact sheet.')
        self.b_right.setToolTip('Turn this frame 90° clockwise (key R). It stays turned everywhere: filmstrip, previews, prints, '
                                'contact sheet.')
        self.b_left.clicked.connect(lambda: self.rotate.emit(-90))
        self.b_right.clicked.connect(lambda: self.rotate.emit(90))
        self.b_full = QPushButton('⛶  Full screen  F')
        self.b_full.setToolTip('See this picture on the whole screen (key F, or double-click the picture). Esc to come back.')
        self.b_full.clicked.connect(self.fullscreen.emit)
        bar.addWidget(self.b_left)
        bar.addWidget(self.b_right)
        bar.addWidget(self.b_full)
        lay.addLayout(bar)
        self.canvas = Canvas()
        self.canvas.hint = hint
        self.canvas.double_clicked.connect(self.fullscreen.emit)
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
        self.b_full.setEnabled(on)
        for b in self.mode_buttons.values():
            b.setEnabled(on)

    def show_picture(self, pm, rotation, caption, loading=''):
        self.canvas.loading = loading
        self.canvas.caption = caption
        self.canvas.set_picture(pm, rotation)
        self.rot_label.setText(('turned %d°   ' % (rotation % 360)) if rotation % 360 else '')
        self.set_enabled(pm is not None)
        if self.full is not None:
            self.full.follow()

    def set_rotation(self, rotation, delta):
        self.canvas.rotation = rotation % 360
        text = '↻  %d°' % (rotation % 360) if delta > 0 else '↺  %d°' % (rotation % 360)
        self.canvas.flash(text)
        self.rot_label.setText(('turned %d°   ' % (rotation % 360)) if rotation % 360 else 'straight   ')
        if self.full is not None:
            self.full.follow()
            self.full.canvas.flash(text)

    def clear(self, text=''):
        self.canvas.empty = text
        self.canvas.loading = ''
        self.canvas.caption = ''
        self.canvas.set_picture(None)
        self.rot_label.setText('')
        self.set_enabled(False)
        if self.full is not None:
            self.full.follow()


class FullScreen(QWidget):
    """One picture on the whole screen, following a FrameView (the light table's big view or the prints'): whatever that view shows,
    this shows, so stepping and rotating go through the main window as usual.
    Keys: Esc / F close, ← → previous / next, R / L rotate, V switch view (light table), hold Space for the original, I info."""
    step = Signal(int)
    rotate = Signal(int)
    original = Signal(bool)                  # Space pressed (True) / released (False)
    switch_view = Signal()
    compare = Signal(int)                    # C: start (0); Up / Down: the other print to compare with (-1 / +1)
    closed = Signal()

    def __init__(self, parent, view, info, hint):
        super().__init__(parent, Qt.Window)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle('Full screen')
        self.view, self.info_fn = view, info
        self.holding = False                 # Space held: the original is shown
        self.show_info = False
        self.comparing = False
        self.setStyleSheet('background: #000;')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.canvas = Canvas()
        self.canvas.margin = 0
        self.canvas.hint = hint
        self.canvas.double_clicked.connect(self.close)
        lay.addWidget(self.canvas)
        view.full = self
        self.follow()
        self.setFocusPolicy(Qt.StrongFocus)

    def follow(self):
        """Show what the followed view shows (unless the original is up)."""
        if self.holding:
            return
        src = self.view.canvas
        self.canvas.caption, self.canvas.loading, self.canvas.empty = src.caption, src.loading, src.empty or 'Nothing to show'
        self.canvas.badge = ''
        self.canvas.info = self.info_fn() if self.show_info and src.pm is not None else ''
        self.canvas.set_picture(src.pm, src.rotation)

    def show_compare(self, pm2, left, right):
        """Compare the print on screen with another print of the same frame (pm2)."""
        self.comparing = True
        self.canvas.pm2, self.canvas.labels = pm2, (left, right)
        self.canvas.update()

    def end_compare(self):
        self.comparing = False
        self.canvas.pm2 = None
        self.canvas.update()

    def show_original(self, pm, rotation):
        if self.holding:
            self.canvas.badge = 'ORIGINAL  ·  as it was before the lab'
            self.canvas.loading = ''
            self.canvas.set_picture(pm, rotation)

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key_Escape, Qt.Key_F):
            self.close()
        elif k in (Qt.Key_Left, Qt.Key_Right) and not self.holding:
            self.end_compare()
            self.step.emit(1 if k == Qt.Key_Right else -1)
        elif k == Qt.Key_C and not self.holding:
            if self.comparing:
                self.end_compare()
            else:
                self.compare.emit(0)
        elif k in (Qt.Key_Up, Qt.Key_Down) and self.comparing:
            self.compare.emit(1 if k == Qt.Key_Down else -1)
        elif k in (Qt.Key_R, Qt.Key_L) and not self.holding and not self.comparing:
            self.rotate.emit(90 if k == Qt.Key_R else -90)
        elif k == Qt.Key_V and not self.holding:
            self.switch_view.emit()
        elif k == Qt.Key_I:
            self.show_info = not self.show_info
            self.follow()
        elif k == Qt.Key_Space and not e.isAutoRepeat() and not self.holding and not self.comparing and self.view.canvas.pm is not None:
            self.holding = True
            self.canvas.badge = 'ORIGINAL'
            self.canvas.loading = 'loading the original…'
            self.canvas.update()
            self.original.emit(True)
        else:
            super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key_Space and not e.isAutoRepeat() and self.holding:
            self.holding = False
            self.original.emit(False)
            self.follow()
        else:
            super().keyReleaseEvent(e)

    def closeEvent(self, e):
        if self.view.full is self:
            self.view.full = None
        self.closed.emit()
        super().closeEvent(e)


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

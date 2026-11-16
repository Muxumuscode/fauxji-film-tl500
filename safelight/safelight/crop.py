"""The crop and straighten editor: a picture with a tilt slider, a choice of shapes, and a crop box to drag.

The picture is shown as the photo is turned on the light table; the crop is stored in the photo's own orientation (lab.turn_box maps
between the two), so a frame can be turned later and keeps its crop.
"""
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget)

from . import lab

RED = '#e0372f'
ASPECTS = [('Free', None), ('Original shape', 'orig'), ('Square  1:1', 1.0), ('3:2', 3 / 2), ('2:3', 2 / 3), ('4:3', 4 / 3), ('3:4', 3 / 4),
           ('5:4', 5 / 4), ('4:5', 4 / 5), ('16:9', 16 / 9), ('9:16', 9 / 16)]
HANDLE = 9
MIN_SIDE = 0.06


def _pix(im):
    im = im.convert('RGB')
    q = QImage(im.tobytes('raw', 'RGB'), im.width, im.height, im.width * 3, QImage.Format_RGB888)
    return QPixmap.fromImage(q.copy())


class CropCanvas(QWidget):
    """The picture with its crop box: drag inside to move it, drag a corner or an edge to resize (keeping the shape when one is chosen)."""
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.pm = None
        self.box = [0.0, 0.0, 1.0, 1.0]                 # left, top, right, bottom as fractions of the picture, as shown
        self.aspect = None                              # width / height in pixels, or None (free)
        self.mode = None
        self.grab_at = None
        self.start_box = None
        self.setMouseTracking(True)
        self.setMinimumSize(420, 320)

    # ---- geometry
    def image_rect(self):
        if self.pm is None:
            return QRectF()
        W, H = self.width() - 24, self.height() - 24
        s = min(W / self.pm.width(), H / self.pm.height())
        w, h = self.pm.width() * s, self.pm.height() * s
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def box_rect(self):
        r = self.image_rect()
        l, t, rr, b = self.box
        return QRectF(r.left() + l * r.width(), r.top() + t * r.height(), (rr - l) * r.width(), (b - t) * r.height())

    def norm_ratio(self):
        """The box's width / height in fractions of the picture, for the chosen pixel shape."""
        return self.aspect * self.pm.height() / self.pm.width()

    def handles(self):
        r = self.box_rect()
        cx, cy = r.center().x(), r.center().y()
        return {'tl': QPointF(r.left(), r.top()), 't': QPointF(cx, r.top()), 'tr': QPointF(r.right(), r.top()),
                'r': QPointF(r.right(), cy), 'br': QPointF(r.right(), r.bottom()), 'b': QPointF(cx, r.bottom()),
                'bl': QPointF(r.left(), r.bottom()), 'l': QPointF(r.left(), cy)}

    def hit(self, pos):
        for name, p in self.handles().items():
            if abs(p.x() - pos.x()) <= HANDLE + 3 and abs(p.y() - pos.y()) <= HANDLE + 3:
                return name
        return 'move' if self.box_rect().contains(pos) else None

    # ---- the picture and the shape
    def set_picture(self, pm):
        self.pm = pm
        self.update()

    def set_aspect(self, aspect):
        """A new shape: the box keeps its centre and becomes the biggest box of that shape inside the old one."""
        self.aspect = aspect
        if aspect is not None and self.pm is not None:
            l, t, r, b = self.box
            ratio = self.norm_ratio()
            w, h = r - l, b - t
            if w / h > ratio:
                w = h * ratio
            else:
                h = w / ratio
            cx, cy = (l + r) / 2, (t + b) / 2
            self.box = self._inside([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2])
            self.changed.emit()
        self.update()

    def swap_shape(self):
        """Turn the chosen shape on its side (3:2 becomes 2:3)."""
        if self.aspect:
            self.set_aspect(1.0 / self.aspect)

    @staticmethod
    def _inside(box):
        l, t, r, b = box
        w, h = r - l, b - t
        l, t = min(max(l, 0.0), 1.0 - w), min(max(t, 0.0), 1.0 - h)
        return [l, t, l + w, t + h]

    # ---- the mouse
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.pm is not None:
            self.mode = self.hit(e.position())
            self.grab_at = e.position()
            self.start_box = list(self.box)

    def mouseReleaseEvent(self, e):
        self.mode = None
        self.update()

    def mouseMoveEvent(self, e):
        if self.pm is None:
            return
        if self.mode is None or not (e.buttons() & Qt.LeftButton):
            h = self.hit(e.position())
            self.setCursor({'tl': Qt.SizeFDiagCursor, 'br': Qt.SizeFDiagCursor, 'tr': Qt.SizeBDiagCursor, 'bl': Qt.SizeBDiagCursor,
                            't': Qt.SizeVerCursor, 'b': Qt.SizeVerCursor, 'l': Qt.SizeHorCursor, 'r': Qt.SizeHorCursor,
                            'move': Qt.SizeAllCursor}.get(h, Qt.ArrowCursor))
            return
        ir = self.image_rect()
        dx, dy = (e.position().x() - self.grab_at.x()) / ir.width(), (e.position().y() - self.grab_at.y()) / ir.height()
        l, t, r, b = self.start_box
        if self.mode == 'move':
            self.box = self._inside([l + dx, t + dy, r + dx, b + dy])
        else:
            m = self.mode
            nl, nt, nr, nb = l, t, r, b
            if 'l' in m:
                nl = min(max(l + dx, 0.0), r - MIN_SIDE)
            if 'r' in m:
                nr = max(min(r + dx, 1.0), l + MIN_SIDE)
            if 't' in m:
                nt = min(max(t + dy, 0.0), b - MIN_SIDE)
            if 'b' in m:
                nb = max(min(b + dy, 1.0), t + MIN_SIDE)
            if self.aspect:
                nl, nt, nr, nb = self._keep_shape(m, nl, nt, nr, nb)
            self.box = [nl, nt, nr, nb]
        self.changed.emit()
        self.update()

    def _keep_shape(self, m, l, t, r, b):
        """Resize with the chosen shape: a corner keeps the opposite corner fixed; an edge keeps the box centred on the other axis."""
        ratio = self.norm_ratio()
        w, h = r - l, b - t
        if len(m) == 2:                                   # a corner
            w = max(w, h * ratio)
            h = w / ratio
            ax = l if 'r' in m else r                       # the fixed corner
            ay = t if 'b' in m else b
            maxw = (1 - ax) if 'r' in m else ax
            maxh = (1 - ay) if 'b' in m else ay
            if w > maxw:
                w, h = maxw, maxw / ratio
            if h > maxh:
                h, w = maxh, maxh * ratio
            nl, nr = (ax, ax + w) if 'r' in m else (ax - w, ax)
            nt, nb = (ay, ay + h) if 'b' in m else (ay - h, ay)
            return nl, nt, nr, nb
        if m in ('l', 'r'):                                # an edge: the other dimension follows, centred
            h = w / ratio
            cy = (self.start_box[1] + self.start_box[3]) / 2
            if h > 1:
                h, w = 1.0, ratio
            cy = min(max(cy, h / 2), 1 - h / 2)
            return (l, cy - h / 2, r, cy + h / 2) if m == 'r' else (r - w, cy - h / 2, r, cy + h / 2)
        w = h * ratio
        cx = (self.start_box[0] + self.start_box[2]) / 2
        if w > 1:
            w, h = 1.0, 1.0 / ratio
        cx = min(max(cx, w / 2), 1 - w / 2)
        return (cx - w / 2, t, cx + w / 2, b) if m == 'b' else (cx - w / 2, b - h, cx + w / 2, b)

    # ---- drawing
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor('#0d0c0c'))
        if self.pm is None:
            return
        ir = self.image_rect()
        p.drawPixmap(ir, self.pm, QRectF(self.pm.rect()))
        br = self.box_rect()
        shade = QColor(0, 0, 0, 150)                       # outside the crop: dimmed
        p.fillRect(QRectF(ir.left(), ir.top(), ir.width(), br.top() - ir.top()), shade)
        p.fillRect(QRectF(ir.left(), br.bottom(), ir.width(), ir.bottom() - br.bottom()), shade)
        p.fillRect(QRectF(ir.left(), br.top(), br.left() - ir.left(), br.height()), shade)
        p.fillRect(QRectF(br.right(), br.top(), ir.right() - br.right(), br.height()), shade)
        p.setPen(QPen(QColor(255, 255, 255, 90), 1))       # the thirds
        for i in (1, 2):
            p.drawLine(QPointF(br.left() + br.width() * i / 3, br.top()), QPointF(br.left() + br.width() * i / 3, br.bottom()))
            p.drawLine(QPointF(br.left(), br.top() + br.height() * i / 3), QPointF(br.right(), br.top() + br.height() * i / 3))
        p.setPen(QPen(QColor('#f2eee6'), 1.6))
        p.setBrush(Qt.NoBrush)
        p.drawRect(br)
        p.setBrush(QColor(RED))
        p.setPen(QPen(QColor('#f2eee6'), 1.4))
        for pt in self.handles().values():
            p.drawRect(QRectF(pt.x() - 4.5, pt.y() - 4.5, 9, 9))
        p.end()


class CropDialog(QDialog):
    """Crop and straighten one photo. exec() is true when the user applies; crop() is then the result (None: back to the whole photo)."""

    def __init__(self, parent, path, turn=0, crop=None, title=''):
        super().__init__(parent)
        self.setWindowTitle('Crop and straighten' + ('  ·  ' + title if title else ''))
        self.resize(1040, 760)
        self.turn = turn % 360
        self.small = lab.load(path, 1300)                   # as the photo is stored: the crop is made on this orientation
        crop = crop or {}
        self.angle = float(crop.get('angle') or 0)
        lay = QVBoxLayout(self)
        self.canvas = CropCanvas()
        self.canvas.changed.connect(self.refresh_info)
        lay.addWidget(self.canvas, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel('Straighten'))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(int(-lab.MAX_TILT * 10), int(lab.MAX_TILT * 10))
        self.slider.setValue(int(round(self.angle * 10)))
        self.slider.setToolTip('Tilt the photo to put a horizon level (up to 15° either way). The edges are trimmed so no empty corners '
                               'show. Double-click the slider to go back to 0°.')
        self.slider.mouseDoubleClickEvent = lambda e: self.slider.setValue(0)
        self.slider.valueChanged.connect(self.tilt)
        row.addWidget(self.slider, 1)
        self.angle_label = QLabel('0.0°')
        self.angle_label.setFixedWidth(52)
        row.addWidget(self.angle_label)
        row.addSpacing(16)
        row.addWidget(QLabel('Shape'))
        self.shape = QComboBox()
        for label, v in ASPECTS:
            self.shape.addItem(label, v)
        self.shape.setToolTip('Keep the crop to a common shape. Free: any shape. Drag the corners or edges; drag inside to move.')
        self.shape.activated.connect(self.pick_shape)
        row.addWidget(self.shape)
        self.btn_swap = QPushButton('⇄')
        self.btn_swap.setFixedWidth(34)
        self.btn_swap.setToolTip('Turn the shape on its side (3:2 → 2:3)')
        self.btn_swap.clicked.connect(self.canvas.swap_shape)
        row.addWidget(self.btn_swap)
        lay.addLayout(row)
        row = QHBoxLayout()
        self.info = QLabel('')
        self.info.setObjectName('muted')
        row.addWidget(self.info, 1)
        reset = QPushButton('Reset')
        reset.setToolTip('The whole photo, not tilted')
        reset.clicked.connect(self.reset)
        cancel = QPushButton('Cancel')
        cancel.clicked.connect(self.reject)
        ok = QPushButton('Apply')
        ok.setObjectName('develop')
        ok.setMinimumWidth(140)
        ok.clicked.connect(self.accept)
        for b in (reset, cancel, ok):
            row.addWidget(b)
        lay.addLayout(row)
        self.timer = QTimer(self)                            # re-draw the straightened picture a moment after the slider stops
        self.timer.setSingleShot(True)
        self.timer.setInterval(45)
        self.timer.timeout.connect(self.render)
        self.render()
        box = crop.get('box') or [0.0, 0.0, 1.0, 1.0]
        self.canvas.box = lab.clean_box(lab.turn_box(box, self.turn))   # the stored box (the photo's own orientation) as it is shown
        self.refresh_info()

    # ---- the picture
    def render(self):
        s = lab.straighten(self.small, self.angle)
        im = lab.rotate(lab.to_image(s), self.turn)
        pm = _pix(im)
        self.canvas.set_picture(pm)
        if self.canvas.aspect == 'orig':
            self.canvas.aspect = pm.width() / pm.height()
        self.refresh_info()

    def tilt(self, v):
        self.angle = v / 10.0
        self.angle_label.setText('%+.1f°' % self.angle if v else '0.0°')
        self.timer.start()

    def pick_shape(self, i):
        v = self.shape.itemData(i)
        if v == 'orig':
            v = self.canvas.pm.width() / self.canvas.pm.height()
        self.canvas.set_aspect(v)

    def reset(self):
        self.slider.setValue(0)
        self.shape.setCurrentIndex(0)
        self.canvas.aspect = None
        self.canvas.box = [0.0, 0.0, 1.0, 1.0]
        self.render()
        self.canvas.update()

    def refresh_info(self):
        if self.canvas.pm is None:
            return
        l, t, r, b = self.canvas.box
        w, h = (r - l) * self.canvas.pm.width(), (b - t) * self.canvas.pm.height()
        self.info.setText('Crop %d%% × %d%% of the picture%s' % (round((r - l) * 100), round((b - t) * 100),
                                                               '' if not self.angle else '   ·   tilted %+.1f°' % self.angle))
        self.info.setToolTip('about %d × %d px of this preview' % (w, h))

    # ---- the result
    def crop(self):
        """{'angle', 'box'} in the photo's own orientation, or None when nothing is cropped or tilted."""
        box = lab.clean_box(lab.turn_box(self.canvas.box, (360 - self.turn) % 360))
        if abs(self.angle) < 0.02 and box == [0.0, 0.0, 1.0, 1.0]:
            return None
        return {'angle': round(self.angle, 2), 'box': [round(v, 4) for v in box]}

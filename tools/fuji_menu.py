"""FAUXJI menu look for the TL500: Fuji-style flat greys instead of Samsung's blue swoosh.

What the menu is made of (all in SPID.Rom):
- bg_menu.jpg, 640x480: the list background. Samsung draws row lines at y = 67, 125,
  183, 241, 299, 357 (rows 58 px, the height of the selection bar, skin image 131,
  485x58 at x = 155) and a footer line at 427.
- bg_menu_<group>_0N.jpg, 160x480: the tab column on the left with tab N selected.
- menu_<group>_*.info: animations. Text = one frame size per line, zero-padded to 2048
  bytes, then the frames (baseline JPEGs, 160x480, each padded to a multiple of 8)
  back to back. The directory's size field is the text length. `_0N` = opening the menu
  on tab N (15 frames), `_ab` = moving from tab a to b (15), `_roll_0N` = the glowing
  ring on tab N (5). FAUXJI frames are still images, so tab changes are instant.

Fuji reference (X-T20 manual, sampled): near-black frame (34,31,31), list rows (70,70,71)
with white text, tab column (99,100,102) with white glyphs, selected tab white.

Run from project root:  python tools/fuji_menu.py preview <out.png>
"""
import io, os, re, struct, sys
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
import spid_files

BLACK = (34, 31, 31)
ROW = (70, 70, 71)
TABCOL = (99, 100, 102)
WHITE = (240, 240, 240)
FOOT = (90, 90, 92)
LINES = (67, 125, 183, 241, 299, 357)
LIST_X = 155
TAB_W = 96
FONT = r'C:\Windows\Fonts\bahnschrift.ttf'

TABS = {'shooting': ['camera', 'movie', 'sound', 'display', 'setup'],
        'playback': ['play', 'slideshow', 'edit', 'sound', 'display'],
        'scene': ['scene', 'camera', 'movie', 'sound', 'display'],
        'movie': ['movie', 'sound', 'display', 'setup'],
        'setting': ['setup'],
        'bkt': ['bkt'],
        'pictbridge': ['print']}


def _font(size):
    f = ImageFont.truetype(FONT, size)
    try:
        f.set_variation_by_name('Bold Condensed')
    except Exception:
        pass
    return f


def glyph(name, ink, size=44):
    """White-on-transparent tab glyph, drawn at 4x and reduced."""
    s = 4
    W = size * s
    im = Image.new('RGBA', (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    u = W / 44.0
    F = lambda *v: [round(x * u) for x in v]
    c = ink + (255,)
    hole = (0, 0, 0, 0)
    if name == 'camera':
        d.rounded_rectangle(F(4, 12, 40, 36), round(4 * u), fill=c)
        d.rectangle(F(15, 8, 29, 13), fill=c)
        d.ellipse(F(14, 15, 30, 31), fill=hole)
        d.ellipse(F(17, 18, 27, 28), fill=c)
    elif name == 'movie':
        d.rounded_rectangle(F(3, 18, 30, 38), round(3 * u), fill=c)
        d.polygon([tuple(F(30, 24)), tuple(F(41, 18)), tuple(F(41, 38)), tuple(F(30, 32))], fill=c)
        d.ellipse(F(4, 4, 16, 16), fill=c)
        d.ellipse(F(16, 4, 28, 16), fill=c)
    elif name == 'sound':
        d.polygon([tuple(F(4, 16)), tuple(F(12, 16)), tuple(F(22, 7)), tuple(F(22, 37)),
                   tuple(F(12, 28)), tuple(F(4, 28))], fill=c)
        for r in (8, 14):
            d.arc(F(22 - r, 22 - r, 22 + r, 22 + r) if False else
                  [round((24 - r) * u), round((22 - r) * u), round((24 + r) * u), round((22 + r) * u)],
                  -50, 50, fill=c, width=round(3 * u))
    elif name == 'display':
        d.rounded_rectangle(F(4, 7, 40, 31), round(3 * u), outline=c, width=round(3 * u))
        d.rectangle(F(19, 31, 25, 36), fill=c)
        d.rectangle(F(12, 36, 32, 39), fill=c)
    elif name == 'setup':                       # wrench, as on Fuji's set-up tab
        d.line([tuple(F(10, 36)), tuple(F(28, 18))], fill=c, width=round(6 * u))
        d.ellipse(F(22, 4, 42, 24), fill=c)
        d.polygon([tuple(F(30, 3)), tuple(F(43, 3)), tuple(F(43, 10)), tuple(F(36, 15))], fill=hole)
        d.ellipse(F(6, 32, 14, 40), fill=c)
    elif name in ('play', 'slideshow', 'edit'):
        if name == 'slideshow':
            d.rounded_rectangle(F(10, 4, 42, 28), round(3 * u), outline=c, width=round(2.5 * u))
            box = F(3, 12, 35, 38)
        else:
            box = F(4, 8, 40, 36)
        d.rounded_rectangle(box, round(3 * u), fill=ink + (255,))
        x0, y0, x1, y1 = [v / u for v in box]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        d.polygon([tuple(F(cx - 5, cy - 7)), tuple(F(cx - 5, cy + 7)), tuple(F(cx + 7, cy))], fill=hole)
        if name == 'edit':
            d.rectangle(F(28, 26, 44, 44), fill=hole)
            d.line([tuple(F(30, 42)), tuple(F(42, 30))], fill=c, width=round(4 * u))
    elif name == 'print':
        d.rectangle(F(12, 4, 32, 14), fill=c)
        d.rounded_rectangle(F(4, 14, 40, 32), round(3 * u), fill=c)
        d.rectangle(F(12, 26, 32, 40), fill=c)
        d.rectangle(F(15, 29, 29, 37), fill=hole)
    else:                                       # text tabs, Fuji style
        text = {'scene': 'SP', 'bkt': 'BKT'}[name]
        f = _font(round((22 if len(text) <= 2 else 17) * u))
        l, t, r, b = d.textbbox((0, 0), text, font=f)
        d.text(((W - (r - l)) / 2 - l, (W - (b - t)) / 2 - t), text, font=f, fill=c)
    return im.resize((size, size), Image.LANCZOS)


def _rows(d, x0, x1):
    for a, b in zip(LINES, LINES[1:]):
        d.rectangle([x0, a + 1, x1, b - 1], fill=ROW)


def background():
    im = Image.new('RGB', (640, 480), BLACK)
    d = ImageDraw.Draw(im)
    _rows(d, LIST_X, 639)
    d.line([0, 427, 639, 427], fill=FOOT, width=1)
    return im


def panel(tabs, sel):
    """Tab column, tab `sel` (0-based) selected."""
    im = Image.new('RGB', (160, 480), BLACK)
    d = ImageDraw.Draw(im)
    _rows(d, LIST_X, 159)
    d.line([0, 427, 159, 427], fill=FOOT, width=1)
    for i, (a, b) in enumerate(zip(LINES, LINES[1:])):
        cell = [0, a + 1, TAB_W - 1, b - 1]
        on = i == sel
        d.rectangle(cell, fill=WHITE if on else TABCOL)
        if i < len(tabs):
            g = glyph(tabs[i], BLACK if on else WHITE)
            im.paste(g, ((TAB_W - g.width) // 2, (a + b) // 2 - g.height // 2), g)
    return im


def jpeg(im, limit=None):
    for q in range(92, 30, -4):
        b = io.BytesIO()
        im.save(b, 'JPEG', quality=q, subsampling=1)          # 4:2:2 like the stock files
        data = b.getvalue()
        if data[2:4] == b'\xff\xe0':                          # stock files start with DQT
            data = data[:2] + data[4 + int.from_bytes(data[4:6], 'big'):]
        if limit is None or len(data) <= limit:
            return data
    raise ValueError('JPEG does not fit %d bytes' % limit)


def animation(frames):
    """.info blob (text, zero pad to 2048, frames padded to 8) and its text length."""
    blobs = [f + b'\0' * (-len(f) % 8) for f in frames]
    text = ''.join('%d\n' % len(b) for b in blobs).encode()
    assert len(text) <= 2048
    return text + b'\0' * (2048 - len(text)) + b''.join(blobs), len(text)


def _put(d, name, blob, size_field):
    rec, off, size, slot = spid_files.directory(d)[name]
    if len(blob) > slot:
        raise ValueError('%s: %d bytes, slot %d' % (name, len(blob), slot))
    out = bytearray(d)
    out[off:off + slot] = blob + b'\0' * (slot - len(blob))
    struct.pack_into('<I', out, rec + 132, size_field)
    return bytes(out)


# skin.bin widgets (index: what it is)
SEL_BAR = 131        # 485x58 menu row highlight (cyan gloss)
POPUP = 136          # 236x321 option list panel, rows of 60 (separators at 70/130/190/250)
POPUP_SEL = 585      # 200x60 selected option in that list (cyan button)
SEL = (128, 128, 130)
POPUP_BG = (50, 50, 51)


def widgets():
    bar = Image.new('RGBA', (485, 58), SEL + (255,))
    ImageDraw.Draw(bar).rectangle([0, 0, 3, 57], fill=WHITE + (255,))      # white edge
    pop = Image.new('RGBA', (236, 321), POPUP_BG + (255,))
    d = ImageDraw.Draw(pop)
    d.rectangle([0, 0, 235, 320], outline=TABCOL + (255,), width=2)
    for y in (70, 130, 190, 250):
        d.line([2, y, 233, y], fill=BLACK + (255,), width=2)
    sel = Image.new('RGBA', (200, 60), SEL + (255,))
    ImageDraw.Draw(sel).rectangle([0, 0, 3, 59], fill=WHITE + (255,))
    return {SEL_BAR: bar, POPUP: pop, POPUP_SEL: sel}


def patch_skin(k):
    import skin
    k = bytearray(k)
    offs = skin.images(bytes(k))
    for idx, im in widgets().items():
        a = offs[idx]
        w, h, size, typ = struct.unpack_from('<4I', k, a)
        assert (w, h) == im.size and typ == 3, idx
        blk = skin.encode(w, h, im.tobytes())
        assert len(blk) <= size, (idx, len(blk), size)
        k[a:a + len(blk)] = blk
    return bytes(k)


def patch_rom(d):
    files = spid_files.directory(d)
    d = spid_files.replace(d, 'bg_menu.jpg', jpeg(background(), files['bg_menu.jpg'][3]))
    panels = {g: [jpeg(panel(t, i)) for i in range(len(t))] for g, t in TABS.items()}
    for g, ps in panels.items():
        for i, p in enumerate(ps):
            name = 'bg_menu_%s_%02d.jpg' % (g, i + 1)
            if name in files:
                d = spid_files.replace(d, name, p)
    for name in sorted(n for n in files if n.endswith('.info')):
        m = re.match(r'menu_([a-z]+)_(roll_)?(\d\d)\.info$', name)
        g, roll, ab = m.group(1), m.group(2), m.group(3)
        ps = panels[g]
        rec, off, size, slot = files[name]
        count = len(d[off:off + size].split())
        a, b = int(ab[0]), int(ab[1])
        pick = lambda n: ps[(n - 1) % len(ps)]
        if roll or a == 0:
            frames = [pick(b)] * count
        else:                                     # first half old tab, then the new one
            frames = [pick(a)] * (count // 2) + [pick(b)] * (count - count // 2)
        blob, tlen = animation(frames)
        d = _put(d, name, blob, tlen)
    return d


if __name__ == '__main__':
    bg = background()
    p = panel(TABS['shooting'], 0)
    bg.paste(p, (0, 0))
    sheet = Image.new('RGB', (640 + 7 * 168, 480), (255, 0, 0))
    sheet.paste(bg, (0, 0))
    x = 648
    for g in ('shooting', 'playback', 'scene', 'movie', 'setting', 'bkt', 'pictbridge'):
        sheet.paste(panel(TABS[g], min(1, len(TABS[g]) - 1)), (x, 0)); x += 168
    sheet.save(sys.argv[2])

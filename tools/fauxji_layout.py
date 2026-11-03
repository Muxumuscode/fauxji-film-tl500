"""FAUXJI changes to the TL500 GUI layout tree (skin.bin, section at +0x945754).

Layout records: u32 size, u32 count (2034), u32 offsets, then per node (at offset+8):
u16 length, u16 id, u32 type (0 group, 1 image, 9 text, ...), s16 x, y, w, h, ...,
u16 parent id at +28, ...; image nodes end with the skin image index; text nodes carry
eight RGBA colours (one per state) after the header.

Help-text box (Samsung's mode description, reused for the FILM SIM name): group 990 at
(100,158) 440x118, image 991 = skin image 121 (440x118 white at 50% alpha), text 992 at
(10,0) 420x118, text black with a white outline (8 colours per state each, at +44 and +76). FAUXJI: a slim dark strip low on the screen, white text with a black outline.

Run from project root:  python tools/fauxji_layout.py preview <out.png>
"""
import os, struct, sys
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
import skin

LAYOUT = 0x945754
BOX, BOX_IMG, BOX_TEXT, BOX_IMAGE_INDEX = 990, 991, 992, 121
BOX_POS = (8, 8, 164, 36)           # FAUXJI62: top left corner (owner: empty, balances the screen), 164 x 36 sized from the owner's photo of FAUXJI61 (Classic Chrome, the longest name, ~142 px); was (84, 386) at the bottom; FAUXJI61: 248 x 48 (too big), FAUXJI60: 196 x 36, FAUXJI52-59: 120 x 36
TEXT_POS = (4, 0, 156, 36)
PANEL = (20, 20, 20, 0xB0)             # near-black at ~70%, Fuji-like
BLACK, WHITE = bytes.fromhex('000000ff'), bytes.fromhex('ffffffff')
TEXT_STOCK = BLACK * 8 + WHITE * 8     # text colour x8 states, then outline colour x8
TEXT_FAUXJI = WHITE * 8 + BLACK * 8


def node_at(k, i):
    n = struct.unpack_from('<I', k, LAYOUT + 4)[0]
    off = struct.unpack_from('<I', k, LAYOUT + 8 + 4 * i)[0]
    b = LAYOUT + off + 8
    length, nid = struct.unpack_from('<HH', k, b)
    assert nid == i, (i, nid)
    return b, length


def set_rect(k, i, rect):
    b, _ = node_at(k, i)
    struct.pack_into('<4h', k, b + 8, *rect)


# Menu list text (layout nodes): 8 text colours (+44) and 8 outline colours (+76); the
# first four are the states normal, focused, disabled, pressed, repeated once.
# Row labels (nodes 3-9): pale blue-grey / white / grey, navy outline. Values (17-24):
# cyan / cyan / grey, white outline. Fuji: white text, black on the white selection bar.
def _c(*hexes):
    return b''.join(bytes.fromhex(h) for h in hexes)


ROW_LABELS = range(3, 10)
ROW_STOCK = _c('c5d4dfff', 'ffffffff', '686868ff', 'ffffffff') * 2 +     _c('0a2231ff', '0a2231ff', '0a2231ff', '000000ff') * 2
ROW_FUJI = _c('ffffffff', '000000ff', '686868ff', '000000ff') * 2 +     _c('000000ff', 'ffffffff', '000000ff', 'ffffffff') * 2
ROW_VALUES = range(17, 25)


def _value_fuji(stock):
    cols = bytearray(stock)
    cols[0:4], cols[4:8] = bytes.fromhex('ffffffff'), bytes.fromhex('000000ff')       # text
    cols[32:36], cols[36:40] = bytes.fromhex('000000ff'), bytes.fromhex('ffffffff')   # outline
    return bytes(cols)


def patch_menu_text(k):
    for i in ROW_LABELS:
        b, length = node_at(k, i)
        assert k[b + 44:b + 108] in (ROW_STOCK, ROW_FUJI), i
        k[b + 44:b + 108] = ROW_FUJI
    for i in ROW_VALUES:
        b, length = node_at(k, i)
        cur = bytes(k[b + 44:b + 108])
        assert cur[0:4] in (bytes.fromhex('9cd7efff'), bytes.fromhex('ffffffff')), i
        k[b + 44:b + 108] = _value_fuji(cur)


# Guide screens (mode dial, scene picker, ...: trees 1751, 1768, 1882, 1917). At the bottom
# a dark title bar (image 92 + white text) and the description. The description area is
# a text list (type 6, e.g. node 1760) whose colours at +44..+108 are all white and whose
# text colour at +132 is black (the title's list, 1759, has white text there), plus a
# plain text node (e.g. 1765) in black. Assumed: +44..+108 = the list's background.
GUIDE_TREES = (1751, 1768, 1882, 1917)
GUIDE_BG = bytes.fromhex('0a0a0ae6') * 16          # near-black, ~90% (owner: ~70% too light)
GUIDE_TEXT = bytes.fromhex('ffffffff')


def tree(k):
    n = struct.unpack_from('<I', k, LAYOUT + 4)[0]
    rec, kids = {}, {}
    for i in range(n):
        b, length = node_at(k, i)
        typ = struct.unpack_from('<I', k, b + 4)[0]
        x, y = struct.unpack_from('<2h', k, b + 8)
        parent = struct.unpack_from('<h', k, b + 28)[0]
        rec[i] = (typ, x, y, parent)
        kids.setdefault(parent, []).append(i)
    return rec, kids


def patch_guides(k):
    rec, kids = tree(k)
    for root in GUIDE_TREES:
        todo = [(root, 0)]
        while todo:
            i, y0 = todo.pop()
            typ, x, y, parent = rec[i]
            ay = y0 + y
            todo += [(c, ay) for c in kids.get(i, [])]
            b, length = node_at(k, i)
            if ay < 400:
                continue
            if typ == 6 and length >= 136 and k[b + 132:b + 136] in (bytes.fromhex('000000ff'), GUIDE_TEXT):
                k[b + 44:b + 108] = GUIDE_BG
                k[b + 132:b + 136] = GUIDE_TEXT
            elif typ == 9 and length >= 108 and k[b + 44:b + 48] == bytes.fromhex('000000ff'):
                k[b + 44:b + 108] = WHITE * 8 + BLACK * 8


# Pop-ups (tree 1785: warning / confirm / info windows on glossy panels 13, 14, 565): the
# message text is black or dark grey (373737), buttons (type 2) black with white when
# focused. With the panels made dark (fuji_lv), messages go white and unfocused buttons
# light grey; focused stays white (whatever highlight the code draws behind it).
POPUP_TREE = 1785
BTN_GREY = bytes.fromhex('aaaaacff')
# FAUXJI33: the buttons sit on images after all (unselected = white row 255/256, selected =
# 238 cyan), now dark grey / white: buttons white, black when selected.
SUB_TEXTS = range(41, 48)       # option-list labels: 4d5052 / white / b3b3b3 / white ...
SUB_FUJI = _c('ffffffff', '000000ff', '7f7f7fff', '000000ff') * 2


def patch_options(k):
    for i in SUB_TEXTS:
        b, length = node_at(k, i)
        k[b + 44:b + 76] = SUB_FUJI


def patch_popups(k):
    rec, kids = tree(k)
    todo = [POPUP_TREE]
    while todo:
        i = todo.pop()
        todo += kids.get(i, [])
        typ = rec[i][0]
        b, length = node_at(k, i)
        if length < 108:
            continue
        if typ == 9:
            k[b + 44:b + 108] = WHITE * 8 + BLACK * 8
        elif typ == 2:
            cols = bytearray(k[b + 44:b + 108])
            for s in range(8):
                cols[4 * s:4 * s + 4] = BLACK if s % 4 == 1 else WHITE
                cols[32 + 4 * s:36 + 4 * s] = BLACK
            k[b + 44:b + 108] = bytes(cols)


def panel():
    w, h = BOX_POS[2], BOX_POS[3]
    im = Image.new('RGBA', (w, h), PANEL)
    px = im.load()
    for y in range(h):                       # square corners keyed out, 1 px
        for x in (0, w - 1):
            if y in (0, h - 1):
                px[x, y] = (255, 0, 255, 255)
    return im


def patch_skin(k):
    k = bytearray(k)
    set_rect(k, BOX, BOX_POS)
    b, _ = node_at(k, BOX_IMG)
    struct.pack_into('<2h', k, b + 12, BOX_POS[2], BOX_POS[3])
    set_rect(k, BOX_TEXT, TEXT_POS)
    b, length = node_at(k, BOX_TEXT)
    rec = k[b:b + length]
    colours = rec[44:108]
    assert colours in (TEXT_STOCK, TEXT_FAUXJI), colours.hex()
    k[b + 44:b + 108] = TEXT_FAUXJI
    a = skin.images(bytes(k))[BOX_IMAGE_INDEX]
    w, h, size, typ = struct.unpack_from('<4I', k, a)
    im = panel()
    blk = skin.encode(im.width, im.height, im.tobytes())
    assert len(blk) <= size and typ == 3
    k[a:a + len(blk)] = blk
    patch_menu_text(k)
    patch_guides(k)
    patch_popups(k)
    patch_options(k)
    return bytes(k)


if __name__ == '__main__':
    im = Image.new('RGB', (640, 480), (120, 140, 110))
    p = panel()
    im.paste(p, BOX_POS[:2], p)
    im.save(sys.argv[2])

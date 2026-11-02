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
BOX_POS = (100, 360, 440, 56)          # x, y, w, h  (stock 100, 158, 440, 118)
TEXT_POS = (10, 0, 420, 56)
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
    return bytes(k)


if __name__ == '__main__':
    im = Image.new('RGB', (640, 480), (120, 140, 110))
    p = panel()
    im.paste(p, BOX_POS[:2], p)
    im.save(sys.argv[2])

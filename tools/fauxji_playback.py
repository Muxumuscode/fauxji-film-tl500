"""FAUXJI playback screens (layout group 1219: edit wheels, option pickers) restyled, no code changes.

The playback tree is dark already. What is left of Samsung's look: glossy grey 3-D icons on the edit
wheels (115x115 selected, 64x64 / 102x82 selected and dimmed variants) and cyan text / arrows. Fuji:
flat white marks, grey when not selected. Same recipe as the live-view icons (fuji_lv.flat_icon).

Only images used by the playback tree and by no other tree are touched (the shared ones are the
live-view icons, restyled by fuji_lv). Image index of a type 1 node: u32 count at +44, indices from +52.

Run from project root:  python tools/fauxji_playback.py preview <SPID.Rom> <out.png>
"""
import os, struct, sys
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(__file__))
import skin, fuji_lv, fauxji_layout as L

PLAYBACK = 1219
GREY = (150, 150, 152, 255)
# Cyan list text (type 6 nodes, state-0 colour 00fffeff): Samsung's "selected row" cyan -> white.
CYAN = bytes.fromhex('00fffeff')
WHITE = bytes.fromhex('ffffffff')
# Coloured arrows / plates (cyan arrows 599, 601): neutral white-grey. Everything else listed
# below is grey-white gloss. Bright ones (selected, 95th percentile luminance >= 200) go flat
# white with a near-black edge, dim ones (dimmed variants, about 150) flat grey.
COLOURED = (599, 601)
SKIP = (503, 592, 597, 613, 625, 626)   # colour wheel, markers, ring: left alone


def tree_images(k):
    """Skin image indices used by type 1 nodes of the playback tree, and the ones used elsewhere."""
    rec, kids = L.tree(k)
    inside, outside = set(), set()

    def sub(i):
        return [i] + [x for c in kids.get(i, []) for x in sub(c)]
    pb = set(sub(PLAYBACK))
    for i in rec:
        if rec[i][0] != 1:
            continue
        b, length = L.node_at(k, i)
        n = struct.unpack_from('<I', k, b + 44)[0]
        for j in range(n):
            ix = struct.unpack_from('<I', k, b + 52 + 4 * j)[0]
            (inside if i in pb else outside).add(ix)
    return inside - outside


def _p95(im):
    lum = sorted((r * 3 + g * 6 + b) // 10 for r, g, b, a in im.getdata()
                 if (r, g, b) != (255, 0, 255) and a >= 40)
    return lum[int(len(lum) * 0.95)] if lum else 0


def flat_grey(im):
    im = im.convert('RGBA')
    p = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = p[x, y]
            if (r, g, b) == (255, 0, 255):
                continue
            p[x, y] = GREY[:3] + (a,) if (r * 3 + g * 6 + b) / 10 >= 70 else fuji_lv.EDGE + (a,)
    return im


def restyle(im, i):
    if i in COLOURED:
        return fuji_lv.white_glyph(im)
    return fuji_lv.flat_icon(im) if _p95(im) >= 200 else flat_grey(im)


def selection(k, offs):
    sel = []
    for i in sorted(tree_images(k)):
        if i in SKIP:
            continue
        w, h, typ, px = fuji_lv._decode_any(bytes(k), offs[i])
        im = Image.frombytes('RGBA', (w, h), px)
        px = [c for c in im.getdata() if c[:3] != (255, 0, 255) and c[3] >= 40]
        sat = sum(max(c[:3]) - min(c[:3]) for c in px) / max(len(px), 1)
        if sat < 1 and i not in COLOURED:               # already flat (the film canisters, fuji_lv)
            continue
        sel.append(i)
    return sel


def patch_text(k):
    """Cyan list rows of the playback screens -> white (outline stays)."""
    rec, kids = L.tree(k)
    todo = [PLAYBACK]
    while todo:
        i = todo.pop()
        todo += kids.get(i, [])
        if rec[i][0] != 6:
            continue
        b, length = L.node_at(k, i)
        for off in range(44, min(length, 108), 4):
            if k[b + off:b + off + 4] == CYAN:
                k[b + off:b + off + 4] = WHITE


def patch_skin(k):
    k = bytearray(k)
    offs = skin.images(bytes(k))
    for i in selection(bytes(k), offs):
        w, h, typ, px = fuji_lv._decode_any(bytes(k), offs[i])
        new = restyle(Image.frombytes('RGBA', (w, h), px), i)
        a = offs[i]
        w0, h0, size, typ0 = struct.unpack_from('<4I', k, a)
        assert (w0, h0) == new.size and typ0 in (1, 3), i
        blk = skin.encode(w0, h0, new.tobytes())
        assert len(blk) <= size, (i, len(blk), size)
        k[a:a + len(blk)] = blk
    patch_text(k)
    return bytes(k)


if __name__ == '__main__':
    import spid_files as F
    d = open(sys.argv[2], 'rb').read()
    r, o, s, sl = F.directory(d)['skin.bin']
    k = d[o:o + s]
    offs = skin.images(k)
    sel = selection(k, offs)
    print(len(sel), 'images:', sel)
    cell = 130
    cols = 10
    sheet = Image.new('RGB', (cols * cell, ((len(sel) + cols - 1) // cols) * 2 * cell), (40, 40, 40))
    dr = ImageDraw.Draw(sheet)
    for n, i in enumerate(sel):
        w, h, typ, px = fuji_lv._decode_any(k, offs[i])
        src = Image.frombytes('RGBA', (w, h), px)
        for row, im in enumerate((src, restyle(src, i))):
            t = im.copy()                              # the magenta key colour shows as in the camera's art
            t.thumbnail((cell - 10, cell - 20))
            x, y = (n % cols) * cell, ((n // cols) * 2 + row) * cell
            sheet.paste(t, (x + 5, y + 3))
        dr.text(((n % cols) * cell + 3, ((n // cols) * 2) * cell + cell - 14), str(i), fill=(255, 255, 0))
    sheet.save(sys.argv[3])

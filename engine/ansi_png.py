"""Truecolor ANSI frame -> PNG, braille-aware — the recorder's cell renderer.

Grown up from the throwaway `ansi2png2.py` that the design gates used to
eyeball `.ans` captures. It exists because the recorder must not screen-grab:
`tui_corewar.py` writes an exact frame to stdout, and this turns THAT text
into pixels, so the master video is the pane's own output rather than a
photograph of a terminal that happened to be running.

Braille (U+2800..U+28FF) is drawn as a real 2x4 dot grid rather than a font
glyph. At master density a font would decide the dot weight for us — and the
whole atlas encoding is dot occupancy, so the dots have to be geometry we
control. Block elements (the faction bars) are drawn as rectangles and shade
blocks as blends; everything else goes through a monospace face.

Cell metrics are chosen by the caller. `metrics_for(cols, rows, w, h)` picks
a cell size that lands an exact frame inside a delivery raster — the repo's
"render natively at delivery dimensions, never upscale a finished render"
law, applied to a terminal grid.
"""
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

BG_DEF = (26, 30, 40)
FG_DEF = (208, 216, 232)
SGR = re.compile(r'\x1b\[([0-9;]*)m')
OTHER_ESC = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')

# braille bit -> (dot column, dot row) in the 2x4 grid
DOT_POS = ((0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (0, 3), (1, 3))
BLOCKS = {'█': 1.0, '▉': .875, '▊': .75, '▋': .625,
          '▌': .5, '▍': .375, '▎': .25, '▏': .125}
SHADES = {'░': .25, '▒': .5, '▓': .75}
# Set ARCADE_FONT to a .ttf/.ttc path to pick the face explicitly. The
# rendered PNGs are pixel-deterministic FOR A GIVEN FONT and no further: a
# different face, or a different version of the same face, moves pixels. That
# matters because these frames are published, so the fallback is loud rather
# than silent — a master rendered on a machine without Menlo should say so in
# the build log, not quietly ship in a different typeface.
FONT_CANDIDATES = ('/System/Library/Fonts/Menlo.ttc',
                   '/System/Library/Fonts/SFNSMono.ttf',
                   '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',
                   '/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf')
_font_warned = set()


def parse(text):
    """ANSI text -> rows of (char, fg, bg) cells. Cursor moves and erases are
    skipped rather than emulated: a frame from `render()` is written top to
    bottom in one pass, so the text IS the grid."""
    rows, cur = [], []
    fg, bg = FG_DEF, BG_DEF
    i = 0
    while i < len(text):
        m = SGR.match(text, i)
        if m:
            params = [int(x) for x in m.group(1).split(';') if x] or [0]
            j = 0
            while j < len(params):
                p = params[j]
                if p == 0:
                    fg, bg = FG_DEF, BG_DEF
                elif p == 38 and params[j + 1:j + 2] == [2]:
                    fg = tuple(params[j + 2:j + 5])
                    j += 4
                elif p == 48 and params[j + 1:j + 2] == [2]:
                    bg = tuple(params[j + 2:j + 5])
                    j += 4
                j += 1
            i = m.end()
            continue
        ch = text[i]
        if ch == '\n':
            rows.append(cur)
            cur = []
        elif ch == '\x1b':
            m2 = OTHER_ESC.match(text, i)
            i += m2.end() - i if m2 else 1
            continue
        elif ch >= ' ':
            cur.append((ch, fg, bg))
        i += 1
    if cur:
        rows.append(cur)
    return rows


def metrics_for(cols, rows, width, height):
    """Cell size + margins that centre a cols x rows grid in a width x height
    raster at native density. Cells stay 1:2 (the terminal's own aspect), and
    the leftover pixels become margin rather than a resample."""
    # Floored to even numbers so the dot grid lands on whole pixels, but
    # never floored UP past what the raster can hold: at a degenerate size
    # `max(2, ...)` used to hand back cells wider than width/cols and the
    # right-hand columns fell off the canvas silently.
    cw = max(2, (width // cols) // 2 * 2)
    ch = max(4, min(cw * 2, (height // rows) // 2 * 2))
    if cols * cw > width or rows * ch > height:
        cw = max(1, width // cols)
        ch = max(1, min(cw * 2, height // rows))
    # Margins never go negative: a raster with room for less than one pixel
    # per cell cannot be centred, and a negative margin would draw the grid
    # off the left edge instead of clipping it at the right (the renderer
    # stops at the canvas boundary on its own).
    return cw, ch, max(0, (width - cols * cw) // 2), \
        max(0, (height - rows * ch) // 2)


class CellRenderer:
    """Reusable across frames: the font and the anti-aliased dot sprite are
    built once. A recorder draws thousands of frames, and rebuilding a dot
    mask per frame is most of the cost."""

    def __init__(self, cell_w, cell_h, margin_x=0, margin_y=0,
                 width=None, height=None, page=BG_DEF, ss=4):
        self.cw, self.chh = cell_w, cell_h
        self.mx, self.my = margin_x, margin_y
        self.width, self.height = width, height
        self.page = page
        size = max(8, int(cell_h * 0.62))
        self.font = self._load(size)
        # The dot: drawn once, huge, downsampled to an alpha mask, then
        # pasted per lit dot. Anti-aliasing a 5px circle by supersampling it
        # 4x costs nothing here and everything if done per dot per frame.
        r = max(1.0, min(cell_w / 2.0, cell_h / 4.0) * 0.42)
        d = max(3, int(round(r * 2)))
        big = Image.new('L', (d * ss, d * ss), 0)
        ImageDraw.Draw(big).ellipse([0, 0, d * ss - 1, d * ss - 1], fill=255)
        self.dot = big.resize((d, d), Image.LANCZOS)
        self.dot_d = d

    @staticmethod
    def _load(size, index=0):
        wanted = os.environ.get('ARCADE_FONT')
        paths = ([wanted] if wanted else []) + list(FONT_CANDIDATES)
        for i, path in enumerate(paths):
            try:
                font = ImageFont.truetype(path, size, index=index)
            except Exception:
                if wanted and i == 0 and 'env' not in _font_warned:
                    _font_warned.add('env')
                    sys.stderr.write(
                        f'NOTE: ARCADE_FONT={wanted!r} could not be loaded; '
                        f'falling back to the built-in candidates.\n')
                continue
            if i > (1 if wanted else 0) and path not in _font_warned:
                _font_warned.add(path)
                sys.stderr.write(
                    f'NOTE: rendering chrome in {path} — the preferred face '
                    f'was unavailable. Frames stay deterministic, but they '
                    f'will not be pixel-identical to a master rendered with '
                    f'{FONT_CANDIDATES[0]}. Set ARCADE_FONT to choose.\n')
            return font
        if index == 0 and 'default' not in _font_warned:
            _font_warned.add('default')
            sys.stderr.write(
                'NOTE: no monospace face found; chrome falls back to '
                "Pillow's bitmap default and will look wrong at master "
                'density. Set ARCADE_FONT to a .ttf/.ttc path.\n')
        return ImageFont.load_default() if index == 0 else None

    def size_for(self, rows):
        if self.width and self.height:
            return self.width, self.height
        cols = max((len(r) for r in rows), default=1)
        return cols * self.cw + 2 * self.mx, len(rows) * self.chh + 2 * self.my

    def render(self, rows):
        w, h = self.size_for(rows)
        img = Image.new('RGB', (w, h), self.page)
        draw = ImageDraw.Draw(img)
        cw, chh = self.cw, self.chh
        half, quarter = cw / 2.0, chh / 4.0
        off = self.dot_d / 2.0
        for y, row in enumerate(rows):
            py = self.my + y * chh
            if py >= h:
                break
            for x, (ch, fg, bg) in enumerate(row):
                px = self.mx + x * cw
                if px >= w:
                    break
                if bg != self.page:
                    draw.rectangle([px, py, px + cw - 1, py + chh - 1],
                                   fill=bg)
                o = ord(ch)
                if 0x2800 <= o <= 0x28FF:
                    bits = o - 0x2800
                    if not bits:
                        continue
                    for b in range(8):
                        if bits >> b & 1:
                            dx, dy = DOT_POS[b]
                            cx = px + quarter * 0 + half * (dx + 0.5)
                            cy = py + quarter * (dy + 0.5)
                            img.paste(fg, (int(cx - off), int(cy - off)),
                                      self.dot)
                elif ch in BLOCKS:
                    draw.rectangle([px, py,
                                    px + int(cw * BLOCKS[ch]) - 1,
                                    py + chh - 1], fill=fg)
                elif ch in SHADES:
                    k = SHADES[ch]
                    draw.rectangle(
                        [px, py, px + cw - 1, py + chh - 1],
                        fill=tuple(int(bg[i] + (fg[i] - bg[i]) * k)
                                   for i in range(3)))
                elif ch.strip():
                    draw.text((px + cw * 0.08, py + chh * 0.12), ch,
                              font=self.font, fill=fg)
        return img


def render_ansi(text, renderer):
    return renderer.render(parse(text))

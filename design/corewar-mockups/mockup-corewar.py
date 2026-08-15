#!/usr/bin/env python3
"""Core War furniture mockup — THE CORE IS THE FIELD.

Design-gate artifact (STREAM E phase 1): a static mid-battle frame of a real
imp-vs-dwarf battle, rendered in the arcade's braille dot-field material, to
be reviewed side by side with the chess/xiangqi checkpoint frames before any
tui_corewar.py work begins.

The core is 8000 cells of circular memory, laid out row-major as a 100x80
grid (8000 = 80x100 exactly; address = row*100 + col). One memory cell is one
braille cell (2x4 dots, density 0-8 via the exact BAYER kernel) — the same
"braille cell IS a 2x4 ordered-dither cell" unlock as tui_dots.py §8.1.

Visual encoding (all constants reused verbatim from tui_dots.py — zero new):
  untouched core    DENS_D 2 dots, AMBIENT fg on SQD plate — the calm field
  owned by A (imp)  EMBER tint, saturation scaled by heat — never wallpaper
  owned by B (dwarf) ICE tint, same rule
  heat              exp decay on last-write age; recent activity is denser,
                    brighter, more saturated; old trail cools toward the field
  DAT bomb          cleared pit (bg drops to PANEL, dots clear); fresh craters
                    glow ICE and cool to bare pits — scars persist
  processes         FULL 8-dot solid cells at near-white owner hue with a
                    1-dot keep-out moat (§8.2: the moat, not the colour,
                    guarantees contrast) — always the brightest objects

Battle content is authentic: corewar.py is imported and the battle is
re-simulated step by step to SNAPSHOT_CYCLE with SEED, tracking last-writer
ownership and write age per cell. Deterministic: same seed, same frame.

Run:  uv run --with pillow python mockup-corewar.py
Deps: stdlib + Pillow (same pattern as docs/xiangqi-studio/kimi/ansi2png.py;
the xiangqi mockup scripts themselves were stdlib-only and screenshotted —
here the PNG is rendered synthetically at the checkpoint's exact 9x18 px
terminal-cell metrics so the grain compares 1:1).

Outputs (next to this script):
  mockup-furniture.ans   ANSI frame (truecolor SGR + braille)
  mockup-furniture.txt   same frame, escapes stripped
  mockup-furniture.png   rendered at 9x18 px/cell (checkpoint-chess-ref class)
  side-by-side.png       chess checkpoint (left) next to this frame (right)
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'engine'))
from corewar import Battle, parse_warrior, IMP, DWARF, CORE_FILL, CORE_SIZE

HERE = Path(__file__).resolve().parent
CHESS_REF = HERE.parent / 'xiangqi-mockups' / 'checkpoint-chess-ref.png'

SEED = 1                 # battle seed (offsets drawn from random.Random(SEED))
SNAPSHOT_CYCLE = 1000    # frame frozen after this many full cycles
TAU = 300.0              # heat decay constant, in cycles

# ---------------------------------------------------------------------------
# Battle replay — track last-writer ownership and write/execute age per cell.
# Execution claims a cell as much as writing does ("last written/executed").
# ---------------------------------------------------------------------------

def replay(seed, snap_cycle):
    wa, wb = parse_warrior(IMP), parse_warrior(DWARF)
    b = Battle(wa, wb, seed=seed)
    owner = [None] * CORE_SIZE      # None | 0 (A) | 1 (B)
    age = [-1] * CORE_SIZE          # last cycle the cell was written/executed
    for i in range(len(wa.instructions)):
        owner[(b.off_a + i) % CORE_SIZE] = 0
        age[(b.off_a + i) % CORE_SIZE] = 0
    for i in range(len(wb.instructions)):
        owner[(b.off_b + i) % CORE_SIZE] = 1
        age[(b.off_b + i) % CORE_SIZE] = 0
    while not b.over and b.cycles < snap_cycle:
        ev = b.step()
        if ev is None:
            break
        owner[ev.pc] = ev.warrior
        age[ev.pc] = ev.cycle
        for w in ev.writes:
            owner[w] = ev.warrior
            age[w] = ev.cycle
    res = b.result()
    body = set()
    for off, w in ((b.off_a, wa), (b.off_b, wb)):
        for i in range(len(w.instructions)):
            body.add((off + i) % CORE_SIZE)
    return {
        'battle': b, 'owner': owner, 'age': age, 'body': body,
        'procs': (list(b.procs[0]), list(b.procs[1])),
        'cycles': b.cycles, 'seed': seed,
        'off_a': b.off_a, 'off_b': b.off_b,
        'name_a': wa.name or 'A', 'name_b': wb.name or 'B',
        'procs_a': res.procs_a, 'procs_b': res.procs_b,
    }

# ---------------------------------------------------------------------------
# Dot material — BAYER/cell_bits/Grid forked from tui_dots.py via
# tui_xiangqi.py ("forked verbatim" pattern), trimmed to a static frame's
# needs. Palette constants are tui_dots.py's, verbatim.
# ---------------------------------------------------------------------------
BAYER = ((0, 4), (6, 2), (1, 5), (7, 3))
BITS = ((0x01, 0x02, 0x04, 0x40), (0x08, 0x10, 0x20, 0x80))  # BITS[dx][dy]
FULL = 0xFF

PANEL = (18, 21, 28)
SQL, SQD = (34, 39, 50), (26, 30, 39)
NEUTRAL = (104, 116, 138)
AMBIENT = (52, 58, 72)
ICE, EMBER = (125, 212, 236), (240, 162, 74)
W_SOLID = (240, 249, 255)
WINDOW_BG = (14, 18, 24)                # tui_xiangqi: the darkest plate tier
TEXT, TDIM, LABEL = (204, 212, 228), (118, 128, 148), (92, 102, 122)
SLATE = (136, 145, 164)
DENS_D, DENS_AMB = 2, 1
SAT_CAP = 0.75

CORE_COLS, CORE_ROWS = 100, 80          # 8000 = 100 x 80, row-major
GUTTER = 4                              # left label gutter, char cols
TOP = 2                                 # header + blank row above the board
RULER_ROW = TOP + CORE_ROWS             # column ruler under the board
FOOTER_ROW = RULER_ROW + 1
BW, BH = GUTTER + CORE_COLS, FOOTER_ROW + 1


def blend(a, b, t):
    t = max(0.0, min(1.0, t))
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def scale(c, k):
    return tuple(min(255, int(v * k)) for v in c)


def cell_bits(cx, cy, level):
    """Forked verbatim from tui_dots.py: light dots whose Bayer threshold falls
    under `level` (a float), so the halftone is exact and never speckles."""
    if level <= 0:
        return 0
    if level >= 8:
        return FULL
    bits = 0
    for dx in (0, 1):
        for dy in range(4):
            if BAYER[dy][dx] < level:
                bits |= BITS[dx][dy]
    return bits


class Grid:
    """Cell buffer — forked from tui_dots.py (via tui_xiangqi.py). Dots
    accumulate; higher priority wins the single fg colour each braille cell
    is allowed. bg is per-cell here because craters are pits in the plate."""
    def __init__(self):
        self.b = [[0] * BW for _ in range(BH)]
        self.f = [[None] * BW for _ in range(BH)]
        self.p = [[-99] * BW for _ in range(BH)]
        self.bg = [[PANEL] * BW for _ in range(BH)]
        self.ch = {}

    def cell(self, cx, cy, bits, col, pri):
        if 0 <= cx < BW and 0 <= cy < BH:
            self.b[cy][cx] |= bits
            if pri >= self.p[cy][cx]:
                self.p[cy][cx] = pri
                self.f[cy][cx] = col

    def set_cell(self, cx, cy, bits, col, pri, bg=None):
        if 0 <= cx < BW and 0 <= cy < BH:
            self.b[cy][cx] = bits
            self.f[cy][cx] = col
            self.p[cy][cx] = pri
            if bg is not None:
                self.bg[cy][cx] = bg

    def clear(self, x, y):
        x, y = int(x), int(y)
        if 0 <= x < BW * 2 and 0 <= y < BH * 4:
            self.b[y // 4][x // 2] &= ~BITS[x % 2][y % 4] & 0xFF

    def text(self, cx, cy, text, col, bold=False):
        for i, char in enumerate(text):
            if 0 <= cx + i < BW and 0 <= cy < BH:
                self.ch[(cx + i, cy)] = (char, col, bold)


# priorities: field lowest, craters above field, processes on top
FIELD_PRI, CRATER_PRI, PROC_PRI = -1, 1, 3


def draw_core(g, snap):
    """The core IS the field: one braille cell per memory cell."""
    core = snap['battle'].core
    owner, age, now = snap['owner'], snap['age'], snap['cycles']
    for addr in range(CORE_SIZE):
        row, col = divmod(addr, CORE_COLS)
        cx, cy = GUTTER + col, TOP + row
        ins = core[addr]
        own = owner[addr]
        heat = math.exp(-(now - age[addr]) / TAU) if age[addr] >= 0 else 0.0
        # Battle-written DAT = bomb crater. A warrior's own loaded cells are
        # never craters: dwarf's bomb magazine is a DAT that its `add` loop
        # rewrites every cycle, so an age test alone misfiles it as a crater.
        is_bomb = (ins.opcode == 'DAT' and own is not None
                   and addr not in snap['body'])
        if is_bomb:
            # Cleared pit that cools: a crater is a hole in the plate, never
            # dotted — a fresh hit GLOWS (bg lifts toward the owner's hue),
            # a cold scar stays as a dark pit. "Cleared" is literal. The glow
            # is squared so only the freshest wounds carry light; a linear
            # falloff lit the whole swept band and outshouted the processes.
            hue = ICE if own == 1 else EMBER
            g.set_cell(cx, cy, 0, AMBIENT, CRATER_PRI,
                       bg=blend(WINDOW_BG, hue, 0.45 * heat * heat))
        elif own is not None:
            # Ownership is a haze, not wallpaper: cold-owned sinks to field
            # brightness with a whisper of hue; only recent activity is dense,
            # bright, saturated. Heat carries the read.
            hue = EMBER if own == 0 else ICE
            level = min(7.0, 2.0 + 2.6 * heat)
            tint = min(SAT_CAP, 0.18 + 0.57 * heat)
            base = blend(AMBIENT, NEUTRAL, heat)
            col = scale(blend(base, hue, tint), 0.95 + 0.45 * heat)
            g.set_cell(cx, cy, cell_bits(cx, cy, level), col, FIELD_PRI, bg=SQD)
        else:
            g.set_cell(cx, cy, cell_bits(cx, cy, float(DENS_D)), AMBIENT,
                       FIELD_PRI, bg=SQD)


def draw_process(g, addr, hue, hot):
    """A process is a 2-cell solid comet with a 1-dot keep-out moat (§8.2):
    head = the PC cell at near-white, tail = PC+1 dimmer (direction reads as
    increasing address). Cells are CLAIMED (bits replaced, not OR-ed) so no
    stray field dot shares the cursor's bright fg — the same reason chess
    sprites dominate every cell their box touches. Always the brightest
    object on the board; a single 2x4 cell failed the glance test at this
    grain. The moat clears only COLD ground: cutting it through hot owned
    cells (the process's own body) shreds them into orphan dots (§11's
    "dangling dots" failure), and a hot neighbour already separates by value.
    """
    row, col = divmod(addr, CORE_COLS)
    cx, cy = GUTTER + col, TOP + row
    tx, ty = cx + 1, cy                      # tail cell wraps with the core row
    if col == CORE_COLS - 1:
        tx, ty = GUTTER, (cy + 1 - TOP) % CORE_ROWS + TOP
    x0, x1 = cx * 2, (cx + 2) * 2 - 1        # dot box of the two cells
    y0, y1 = cy * 4, cy * 4 + 3
    for x in range(x0 - 1, x1 + 2):
        for y in range(y0 - 1, y1 + 2):
            if x0 <= x <= x1 and y0 <= y <= y1:
                continue
            mcx, mcy = x // 2, y // 4
            if (GUTTER <= mcx < GUTTER + CORE_COLS
                    and TOP <= mcy < TOP + CORE_ROWS):
                maddr = (mcy - TOP) * CORE_COLS + (mcx - GUTTER)
                if maddr in hot:
                    continue               # hot body cell: no moat cut
            g.clear(x, y)
    g.set_cell(cx, cy, FULL, blend(hue, W_SOLID, 0.72), PROC_PRI, bg=SQD)
    g.set_cell(tx, ty, FULL, blend(hue, W_SOLID, 0.30), PROC_PRI, bg=SQD)


def draw_chrome(g, snap):
    """Names + status, chess-checkpoint style: no ornament, only identity and
    state. Ruler ticks are functional (memory is addressed in absolute cells)."""
    name_a, name_b = snap['name_a'].upper(), snap['name_b'].upper()
    g.text(2, 0, name_a, EMBER, bold=True)
    g.text(2 + len(name_a) + 2, 0, name_b, ICE, bold=True)
    g.text(2 + len(name_a) + 2 + len(name_b) + 2, 0,
           f'· core war · seed {snap["seed"]}', TDIM)
    for r in range(0, CORE_ROWS, 10):
        g.text(0, TOP + r, f'{r * CORE_COLS:>4}', LABEL)
    for c in range(0, CORE_COLS, 10):
        g.text(GUTTER + c, RULER_ROW, str(c), LABEL)
    foot = f'   cycle {snap["cycles"]}'
    g.text(0, FOOTER_ROW, foot, TEXT)
    x = len(foot) + 2
    g.text(x, FOOTER_ROW, name_a, EMBER, bold=True)
    x += len(name_a)
    g.text(x, FOOTER_ROW, f' procs {snap["procs_a"]} · ', TDIM)
    x += len(f' procs {snap["procs_a"]} · ')
    g.text(x, FOOTER_ROW, name_b, ICE, bold=True)
    x += len(name_b)
    g.text(x, FOOTER_ROW, f' procs {snap["procs_b"]}', TDIM)


def build_frame(snap):
    g = Grid()
    draw_core(g, snap)
    now = snap['cycles']
    hot = {a for a in range(CORE_SIZE)
           if snap['owner'][a] is not None and snap['age'][a] >= 0
           and math.exp(-(now - snap['age'][a]) / TAU) > 0.5}
    for pc in snap['procs'][0]:
        draw_process(g, pc, EMBER, hot)
    for pc in snap['procs'][1]:
        draw_process(g, pc, ICE, hot)
    draw_chrome(g, snap)
    return g

# ---------------------------------------------------------------------------
# Emitters — one buffer, two outputs: ANSI text and PNG.
# ---------------------------------------------------------------------------

def fg(c):
    return f'\x1b[38;2;{c[0]};{c[1]};{c[2]}m'


def bg(c):
    return f'\x1b[48;2;{c[0]};{c[1]};{c[2]}m'


def to_ansi(g):
    out = []
    for cy in range(BH):
        row, pf, pb, pbold = '', None, None, False
        for cx in range(BW):
            gl = g.ch.get((cx, cy))
            col = gl[1] if gl else (g.f[cy][cx] or AMBIENT)
            cbg = PANEL if gl else g.bg[cy][cx]
            bold = bool(gl and gl[2])
            if col != pf:
                row += fg(col)
                pf = col
            if cbg != pb:
                row += bg(cbg)
                pb = cbg
            if bold != pbold:
                row += '\x1b[1m' if bold else '\x1b[22m'
                pbold = bold
            row += gl[0] if gl else chr(0x2800 + g.b[cy][cx])
        out.append(row + '\x1b[0m')
    return '\n'.join(out) + '\n'


def strip_ansi(s):
    import re
    return re.sub(r'\x1b\[[0-9;]*m', '', s)


def to_png(g, path, cell_w=9, cell_h=18, margin=14, ss=2):
    """Synthetic terminal capture at the checkpoint frames' exact cell
    metrics (9x18 px). Braille dots are drawn as geometry, not font glyphs,
    so the render does not depend on any font's braille coverage."""
    from PIL import Image, ImageDraw, ImageFont
    w, h = BW * cell_w + 2 * margin, BH * cell_h + 2 * margin
    img = Image.new('RGB', (w * ss, h * ss), scale(PANEL, 0.6))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype('/System/Library/Fonts/Menlo.ttc', 13 * ss)
    try:
        bold_font = ImageFont.truetype('/System/Library/Fonts/Menlo.ttc',
                                       13 * ss, index=1)
    except Exception:
        bold_font = font
    dot_r = 1.45 * ss
    for cy in range(BH):
        for cx in range(BW):
            px = (margin + cx * cell_w) * ss
            py = (margin + cy * cell_h) * ss
            d.rectangle([px, py, px + cell_w * ss, py + cell_h * ss],
                        fill=g.bg[cy][cx])
            gl = g.ch.get((cx, cy))
            if gl:
                ch, col, bold = gl
                d.text((px + 1 * ss, py + 1 * ss), ch,
                       font=bold_font if bold else font, fill=col)
                continue
            bits = g.b[cy][cx]
            if not bits:
                continue
            col = g.f[cy][cx] or AMBIENT
            for dx in (0, 1):
                for dy in range(4):
                    if bits & BITS[dx][dy]:
                        ox = px + (cell_w * ss) * (0.25 + 0.5 * dx)
                        oy = py + (cell_h * ss) * (0.125 + 0.25 * dy)
                        d.ellipse([ox - dot_r, oy - dot_r, ox + dot_r,
                                   oy + dot_r], fill=col)
    img = img.resize((w, h), Image.LANCZOS)
    img.save(path)
    print(f'{path.name}: {w}x{h}px, {BW}x{BH} cells')


def composite(g_png_path, out_path):
    """The §6 gate discipline: this frame next to the chess checkpoint at the
    same cell metrics, top-aligned, on a dark window-coloured ground."""
    from PIL import Image
    chess = Image.open(CHESS_REF)
    mine = Image.open(g_png_path)
    gap = 28
    w = chess.width + gap + mine.width
    h = max(chess.height, mine.height)
    img = Image.new('RGB', (w, h), (10, 13, 18))
    img.paste(chess, (0, 0))
    img.paste(mine, (chess.width + gap, 0))
    img.save(out_path)
    print(f'{out_path.name}: {w}x{h}px')


def main():
    snap = replay(SEED, SNAPSHOT_CYCLE)
    g = build_frame(snap)
    ansi = to_ansi(g)
    (HERE / 'mockup-furniture.ans').write_text(ansi)
    (HERE / 'mockup-furniture.txt').write_text(strip_ansi(ansi))
    to_png(g, HERE / 'mockup-furniture.png')
    if CHESS_REF.exists():
        composite(HERE / 'mockup-furniture.png', HERE / 'side-by-side.png')
    owned_a = sum(1 for o in snap['owner'] if o == 0)
    owned_b = sum(1 for o in snap['owner'] if o == 1)
    print(f'seed={SEED} cycle={snap["cycles"]} '
          f'off_a={snap["off_a"]} off_b={snap["off_b"]} '
          f'A-owned={owned_a} B-owned={owned_b} '
          f'procs A={snap["procs_a"]} B={snap["procs_b"]}')


if __name__ == '__main__':
    main()

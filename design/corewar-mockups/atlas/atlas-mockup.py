#!/usr/bin/env python3
"""Atlas mockup — the WHOLE core, stationary, at pane size.

Design-gate artifact. The Core War board's default identity flips: instead of
an activity-following 1:1 camera, the atlas draws all 8000 memory cells at
**1 dot = 1 memory cell**, stationary, sized to a normal herdr pane (87x23).

Geometry: core is 100 cols x 80 rows (address = row*100 + col). A braille
char is 2x4 dots, so one char covers 2 core cols x 4 core rows = 8 memory
cells, and the field is exactly 50 chars wide x 20 chars tall. Dot (dx, dy)
of char (cx, cy) IS memory cell (4*cy+dy)*100 + 2*cx+dx — the mapping is
positional and exact, never resampled.

This relaxes the locked "1 memory cell = 1 braille cell" rule for the atlas
tier only (sanctioned). The known objection — averaging two factions'
colours fabricates a muddy third hue at contested borders — is answered by
splitting the two questions into two channels that never mix:

  fg (dots)   WHO holds this block: a dot is lit iff its memory cell is
              owned, and the char's single fg is the MAJORITY owner of the
              lit dots, at that owner's hue on the deep ramp. Never an
              average; a blend between EMBER and ICE is never computed.
  bg (plate)  WHAT IS HAPPENING to this block: pits darken it toward
              WINDOW_BG by their footprint, fresh damage glows in its
              bomber's hue by its cratered footprint, and a genuinely
              contested block (both factions hold ground here AND someone
              has been here recently) lifts toward SLATE — a neutral grey
              off both faction ramps, so it can never be read as a mix.

A moving front therefore reads as a jittering pale seam with each side's
own hue burning brighter along it — "fighting here", ownership intact.

Processes: the 2-cell comet grammar dies at this grain (one PC = one dot =
invisible). A char holding a PC renders FULL near-white on a deterministic
pulse — the board's brightest object, and its one admitted lie.

Run:  uv run --with pillow python atlas-mockup.py
Deps: stdlib + Pillow (PNG capture only, at the checkpoint frames' exact
9x18 px terminal-cell metrics, same as ../mockup-corewar.py).

Outputs (next to this script): atlas-{mid,front,late}.{ans,txt,png} plus
variants-{mid,late}.png, the encoding-fork evidence sheets. notes.md is the
design record — read it for the self-review rounds and the open questions.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'engine'))
from corewar import Battle, parse_warrior, CORE_SIZE

HERE = Path(__file__).resolve().parent
MATCH = Path(__file__).resolve().parents[3] / 'games' / 'corewar' / 'match-002'

# match-002 round 1, verbatim from its moves.txt (tie at 80000)
SEED = 18042764757958431666
OFF_A, OFF_B = 549, 6448
# mid + late are the brief's two required moments. `front` is the third the
# design needed: at cycle 12,000 the two territories are the same size and
# the boundary is actively moving — the only place the contested treatment
# is under real load. A treatment nobody can see working is not a treatment.
SNAPSHOTS = (('mid', 3000), ('front', 12000), ('late', 40000))
ROUND_N, ROUND_TOTAL, CYCLE_CAP = 1, 3, 80000

# ---------------------------------------------------------------------------
# Palette / material — tui_corewar.py verbatim. Zero new constants.
# ---------------------------------------------------------------------------
BAYER = ((0, 4), (6, 2), (1, 5), (7, 3))
BITS = ((0x01, 0x02, 0x04, 0x40), (0x08, 0x10, 0x20, 0x80))  # BITS[dx][dy]
FULL = 0xFF

PANEL = (18, 21, 28)
SQD = (26, 30, 39)
NEUTRAL = (104, 116, 138)
AMBIENT = (52, 58, 72)
ICE, EMBER = (125, 212, 236), (240, 162, 74)
W_SOLID = (240, 249, 255)
WINDOW_BG = (14, 18, 24)
TEXT, TDIM, LABEL = (204, 212, 228), (118, 128, 148), (92, 102, 122)
SLATE = (136, 145, 164)
HUES = (EMBER, ICE)
EMBER_DEEP, ICE_DEEP = (158, 42, 20), (30, 84, 168)
HUES_DEEP = (EMBER_DEEP, ICE_DEEP)
SAT_CAP = 0.75
TAU = 300.0
WAVE_PERIOD, WAVE_AMP = 30.0, 0.5

# ---------------------------------------------------------------------------
# Frame geometry — 87x23, the real pane.
#   row 0        header (names + what this is)
#   rows 1..20   the field: 50x20 chars = the whole 8000-cell core
#   row 21       the two faction bars, side by side
#   row 22       status
# The field cannot grow (it is a fixed 50x20 for all time), so the surplus
# 32 columns are pure margin: the block is centred and the chrome rows below
# it spend the width the field cannot.
# ---------------------------------------------------------------------------
FW, FH = 87, 23
CORE_COLS, CORE_ROWS = 100, 80
FIELD_W, FIELD_H = CORE_COLS // 2, CORE_ROWS // 4     # 50 x 20
GUTTER = 4
BLOCK_W = GUTTER + 1 + FIELD_W                        # 55
BLOCK_X = (FW - BLOCK_W) // 2                         # 16: the field block
FIELD_X = BLOCK_X + GUTTER + 1                        # 21
# The chrome rows sit wider than the block they describe — the broadcast
# lower third. The field can never use those columns (it is 50 wide for
# ever), so the text spends them instead of leaving the frame lopsided.
CHROME_X = 8
FIELD_Y = 1
BARS_ROW, STATUS_ROW = FIELD_Y + FIELD_H, FIELD_Y + FIELD_H + 1

FIELD_PRI, PROC_PRI = -1, 3


def blend(a, b, t):
    t = max(0.0, min(1.0, t))
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def scale(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


class Grid:
    """Cell buffer — forked from tui_corewar.py, plus the mockup's chrome
    layer (chrome is composed as strings in the real renderer; here it shares
    the buffer so one emitter serves both ANSI and PNG)."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.b = [[0] * w for _ in range(h)]
        self.f = [[None] * w for _ in range(h)]
        self.p = [[-99] * w for _ in range(h)]
        self.bg = [[PANEL] * w for _ in range(h)]
        self.ch = {}

    def set_cell(self, cx, cy, bits, col, pri, back=None):
        if 0 <= cx < self.w and 0 <= cy < self.h:
            self.b[cy][cx] = bits
            self.f[cy][cx] = col
            self.p[cy][cx] = pri
            if back is not None:
                self.bg[cy][cx] = back

    def text(self, cx, cy, s, col, bold=False):
        for i, char in enumerate(s):
            if 0 <= cx + i < self.w and 0 <= cy < self.h:
                self.ch[(cx + i, cy)] = (char, col, bold)


# ---------------------------------------------------------------------------
# Battle replay — the real engine, the locked transcript's seed and offsets.
# ---------------------------------------------------------------------------

def replay(snapshots):
    wa = parse_warrior((MATCH / 'warriors' / 'A.red').read_text())
    wb = parse_warrior((MATCH / 'warriors' / 'B.red').read_text())
    # Chrome names the PLAYERS, not the warriors: names.txt is the bus's
    # `<red> <blue>`, red is warrior A (tui_corewar.py's refresh_names).
    parts = (MATCH / 'names.txt').read_text().split()
    players = (parts[0].upper(), parts[1].upper()) if len(parts) == 2 else ('A', 'B')
    b = Battle(wa, wb, seed=SEED, off_a=OFF_A, off_b=OFF_B)
    if (b.off_a, b.off_b) != (OFF_A, OFF_B):
        print(f'! offsets disagree with transcript: {b.off_a},{b.off_b}')
    owner = [None] * CORE_SIZE
    age = [-1] * CORE_SIZE
    body = set()
    for off, w, tag in ((b.off_a, wa, 0), (b.off_b, wb, 1)):
        for i in range(len(w.instructions)):
            a = (off + i) % CORE_SIZE
            owner[a], age[a] = tag, 0
            body.add(a)
    out = {}
    want = dict(snapshots)
    targets = sorted(want.values())
    ti = 0
    while not b.over and ti < len(targets):
        if b.cycles >= targets[ti]:
            label = [k for k, v in snapshots if v == targets[ti]][0]
            out[label] = snap(b, owner, age, body, players)
            ti += 1
            continue
        ev = b.step()
        if ev is None:
            break
        owner[ev.pc] = ev.warrior
        age[ev.pc] = ev.cycle
        for w in ev.writes:
            owner[w] = ev.warrior
            age[w] = ev.cycle
    while ti < len(targets):                 # battle ended early: freeze here
        label = [k for k, v in snapshots if v == targets[ti]][0]
        out[label] = snap(b, owner, age, body, players)
        ti += 1
    return out


def snap(b, owner, age, body, players):
    """Freeze the state a frame needs. A crater is a battle-written DAT that
    is not part of a warrior's loaded body (the body exclusion is
    ../notes.md round 5: a bomber's magazine is a DAT its own loop rewrites,
    and an age test alone misfiles it as damage)."""
    crater = [False] * CORE_SIZE
    for a in range(CORE_SIZE):
        if owner[a] is not None and a not in body and b.core[a].opcode == 'DAT':
            crater[a] = True
    return {
        'owner': list(owner), 'age': list(age), 'crater': crater,
        'cycles': b.cycles,
        'procs': (list(b.procs[0]), list(b.procs[1])),
        'name_a': players[0], 'name_b': players[1],
    }


# ---------------------------------------------------------------------------
# The field encoder — 8 memory cells per braille char, two channels.
# ---------------------------------------------------------------------------

def draw_field(g, s, t=0.0, variant='occupancy', ambient=False):
    """variant 'occupancy': a dot is lit iff the cell is OWNED — a bomb is a
    write, so bombed ground still shows its bomber's colour and territory
    survives late-game saturation. Damage lives entirely in the plate.
    variant 'clearing': the brief's recommended start — a crater kills its
    dot, so damage also reads as absence. Both are rendered; see notes.md."""
    owner, age, crater, now = s['owner'], s['age'], s['crater'], s['cycles']
    for cy in range(FIELD_H):
        for cx in range(FIELD_W):
            n = [0, 0]
            bits = 0
            hmax = [0.0, 0.0]
            npit = 0
            glow_h, glow_o, glow_sum = 0.0, 0, 0.0
            for dx in (0, 1):
                col = 2 * cx + dx
                for dy in range(4):
                    addr = (4 * cy + dy) * CORE_COLS + col
                    o = owner[addr]
                    if o is None:
                        continue
                    h = math.exp(-(now - age[addr]) / TAU) if age[addr] >= 0 else 0.0
                    if crater[addr]:
                        npit += 1
                        glow_sum += h * h
                        if h > glow_h:
                            glow_h, glow_o = h, o
                        if variant == 'clearing':
                            continue
                    n[o] += 1
                    bits |= BITS[dx][dy]
                    if h > hmax[o]:
                        hmax[o] = h

            # --- plate: damage, contest, glow. Never carries ownership. ----
            wave = 0.5 + 0.5 * math.sin(
                (cx * 0.7 + cy * 1.9) / WAVE_PERIOD * 2 * math.pi + t)
            back = blend(SQD, AMBIENT, 0.40 * WAVE_AMP * wave) if not bits \
                else SQD
            if npit:
                back = blend(back, WINDOW_BG, npit / 8.0)
            lo, hi = min(n), max(n)
            contest = 0.0
            if lo and lo / float(lo + hi) >= 0.25:
                # Both factions genuinely hold ground in these 8 cells AND
                # someone has been here recently: the plate lights up. Two
                # gates, both necessary. Strength is the DISPUTED FOOTPRINT
                # (twice the minority's cells, capped) — not the ratio, which
                # scores a near-empty 1-vs-1 block as hard-fought as a 4-vs-4
                # one and litters the field with bright cards over nothing.
                # Heat gating turns a map of every old overlap into a picture
                # of the front: a border nobody has touched in a thousand
                # cycles is a settled line, not a fight. The hue question is
                # answered by the dots, so nothing is ever averaged.
                contest = min(1.0, 2.0 * lo / 8.0) * max(hmax[0], hmax[1])
                # A flat lift draws a clean rectangle, which reads as a UI
                # card sitting on the board. The sin-hash jitter (pure in
                # cx, cy, t — never RNG, so headless frames stay byte-stable)
                # makes neighbouring contested cells disagree slightly, and
                # the seam reads as unstable ground instead of a panel. In
                # the live renderer this is the flicker, REDUCED_MOTION-gated.
                jit = 0.78 + 0.22 * math.sin(cx * 3.1 + cy * 5.7 + t * 3.0)
                back = blend(back, SLATE, 0.55 * contest * jit)
            if glow_sum > 0.0:
                # Fresh damage glows from the pit, per ../notes.md round 3's
                # 0.45h^2 — but at atlas grain "the freshest cell in the
                # block" lights all 8 cells' worth of plate, so one bomb
                # painted a bright card and a bombing run became a forest of
                # them: exactly the failure round 3 fixed, recurring at the
                # coarser grain. The glow now carries the CRATERED FOOTPRINT
                # (sum of h^2 over the block's pits, over 8), so one hit is a
                # whisper and only a carpeted block burns.
                back = blend(back, HUES[glow_o], 0.55 * glow_sum / 8.0)

            # --- dots: who holds this block, at what heat. -----------------
            if not bits:
                if ambient:
                    stipple = int((math.sin(cx * 12.9898 + cy * 78.233) * 43758.5453) % 1.0 * 8)
                    if stipple == 0:
                        bits = BITS[cx % 2][cy % 4]
                g.set_cell(FIELD_X + cx, FIELD_Y + cy, bits, AMBIENT,
                           FIELD_PRI, back=back)
                continue
            o = 0 if n[0] > n[1] else 1 if n[1] > n[0] else (0 if hmax[0] >= hmax[1] else 1)
            h = hmax[o]
            col = scale(blend(HUES_DEEP[o], HUES[o], h), 0.58 + 0.66 * h)
            if contest:
                # Contest reads in both channels or in neither: a lit plate
                # alone looks like a UI card dropped on the field. The dots
                # burn brighter in the owner's own hue — no third colour is
                # invented, the front just glows.
                col = scale(col, 1.0 + 0.30 * contest)
            g.set_cell(FIELD_X + cx, FIELD_Y + cy, bits, col, FIELD_PRI, back=back)


def draw_processes(g, s, t=0.0):
    """A process is ONE memory cell = one dot, which is invisible among 8000.
    So the marker is promoted to the whole braille char: FULL 8 dots at
    near-white, the brightest object on the board, pulsing on a deterministic
    tick. This is the atlas's one admitted lie — it claims 8 cells for a
    marker that owns 1 — and it is cheap because a PC almost always sits
    inside its own warrior's hot code. Co-located PCs collapse into one
    marker; an imp train becomes a white worm, which is the point.
    Returns the number of distinct marker cells drawn."""
    cells = {}
    for w, pcs in enumerate(s['procs']):
        for pc in pcs:
            row, col = divmod(pc % CORE_SIZE, CORE_COLS)
            key = (col // 2, row // 4)
            cells.setdefault(key, [0, 0])[w] += 1
    for (cx, cy), cnt in sorted(cells.items()):
        o = 0 if cnt[0] >= cnt[1] else 1
        pulse = 0.62 + 0.20 * (0.5 + 0.5 * math.sin(t * 2.0 + (cx * 7 + cy * 13) * 0.9))
        g.set_cell(FIELD_X + cx, FIELD_Y + cy, FULL,
                   blend(HUES[o], W_SOLID, pulse), PROC_PRI)
    return len(cells)


# ---------------------------------------------------------------------------
# Chrome — plain language, lowercase, names in faction hues.
# ---------------------------------------------------------------------------
BAR_W = 9


def bar(frac):
    fill = int(round(frac * BAR_W))
    return '█' * fill + '░' * (BAR_W - fill)


def draw_chrome(g, s):
    """Plain language, lowercase, players named in their faction hue. The
    bars ARE the legend: "held" and "running" say in words what the two
    bright things on the field mean, so no separate key row is needed (there
    is no row to spare — 1 + 20 + 1 + 1 is exactly 23)."""
    a, b = s['name_a'], s['name_b']
    x = CHROME_X
    g.text(x, 0, a, EMBER, bold=True)
    x += len(a)
    g.text(x, 0, ' vs ', TDIM)
    x += 4
    g.text(x, 0, b, ICE, bold=True)
    x += len(b)
    g.text(x, 0, '  ·  all 8,000 cells of memory, one dot each', TDIM)

    own = [sum(1 for o in s['owner'] if o == 0),
           sum(1 for o in s['owner'] if o == 1)]
    run = [len(s['procs'][0]), len(s['procs'][1])]
    half = (FW - CHROME_X) // 2
    pad = max(len(a), len(b))
    for i, hue in enumerate(HUES):
        x = CHROME_X + i * half
        g.text(x, BARS_ROW, (a, b)[i], hue, bold=True)
        x += pad + 1
        g.text(x, BARS_ROW, bar(own[i] / float(CORE_SIZE)), hue)
        x += BAR_W + 1
        pct = f'{own[i] * 100.0 / CORE_SIZE:.0f}% held'
        g.text(x, BARS_ROW, pct, TEXT)
        x += len(pct)
        g.text(x, BARS_ROW, f' · {run[i]} running', TDIM)

    g.text(CHROME_X, STATUS_ROW,
           f'round {ROUND_N} of {ROUND_TOTAL} · step {s["cycles"]:,} '
           f'of {CYCLE_CAP:,}', TEXT)

    for r in range(0, FIELD_H, 5):
        g.text(BLOCK_X, FIELD_Y + r, f'{r * 4 * CORE_COLS:>4}', LABEL)


def build(s, t=0.0, variant='occupancy', ambient=False):
    g = Grid(FW, FH)
    draw_field(g, s, t, variant, ambient)
    draw_processes(g, s, t)
    draw_chrome(g, s)
    return g


# ---------------------------------------------------------------------------
# Emitters
# ---------------------------------------------------------------------------

def fg(c):
    return f'\x1b[38;2;{c[0]};{c[1]};{c[2]}m'


def bgc(c):
    return f'\x1b[48;2;{c[0]};{c[1]};{c[2]}m'


def to_ansi(g):
    out = []
    for cy in range(g.h):
        row, pf, pb, pbold = '', None, None, False
        for cx in range(g.w):
            gl = g.ch.get((cx, cy))
            col = gl[1] if gl else (g.f[cy][cx] or AMBIENT)
            cbg = PANEL if gl else g.bg[cy][cx]
            bold = bool(gl and gl[2])
            if col != pf:
                row += fg(col)
                pf = col
            if cbg != pb:
                row += bgc(cbg)
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


def to_png(g, path, cell_w=9, cell_h=18, margin=14, ss=2, label=None):
    from PIL import Image, ImageDraw, ImageFont
    lab_h = 22 if label else 0
    w, h = g.w * cell_w + 2 * margin, g.h * cell_h + 2 * margin + lab_h
    img = Image.new('RGB', (w * ss, h * ss), scale(PANEL, 0.6))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype('/System/Library/Fonts/Menlo.ttc', 13 * ss)
    try:
        bold_font = ImageFont.truetype('/System/Library/Fonts/Menlo.ttc',
                                       13 * ss, index=1)
    except Exception:
        bold_font = font
    dot_r = 1.45 * ss
    for cy in range(g.h):
        for cx in range(g.w):
            px = (margin + cx * cell_w) * ss
            py = (margin + lab_h + cy * cell_h) * ss
            d.rectangle([px, py, px + cell_w * ss, py + cell_h * ss],
                        fill=g.bg[cy][cx])
            gl = g.ch.get((cx, cy))
            if gl:
                ch, col, bold = gl
                d.rectangle([px, py, px + cell_w * ss, py + cell_h * ss],
                            fill=PANEL)
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
    if label:
        d.text((margin * ss, 4 * ss), label, font=font, fill=TDIM)
    img = img.resize((w, h), Image.LANCZOS)
    if path is not None:
        img.save(path)
    return img


def stack(images, path, gap=10):
    from PIL import Image
    w = max(i.width for i in images)
    h = sum(i.height for i in images) + gap * (len(images) - 1)
    out = Image.new('RGB', (w, h), (10, 13, 18))
    y = 0
    for i in images:
        out.paste(i, (0, y))
        y += i.height + gap
    out.save(path)
    print(f'{path.name}: {w}x{h}px')


def main():
    snaps = replay(SNAPSHOTS)
    for label, _ in SNAPSHOTS:
        s = snaps[label]
        g = build(s)
        ansi = to_ansi(g)
        (HERE / f'atlas-{label}.ans').write_text(ansi)
        (HERE / f'atlas-{label}.txt').write_text(strip_ansi(ansi))
        to_png(g, HERE / f'atlas-{label}.png')
        own_a = sum(1 for o in s['owner'] if o == 0)
        own_b = sum(1 for o in s['owner'] if o == 1)
        pits = sum(1 for c in s['crater'] if c)
        print(f'{label}: cycle={s["cycles"]} ownedA={own_a} ownedB={own_b} '
              f'craters={pits} running={len(s["procs"][0])}/'
              f'{len(s["procs"][1])} untouched='
              f'{sum(1 for o in s["owner"] if o is None)}')

    # Round-1 evidence sheets: the two encoding forks, side by side at both
    # moments (see notes.md). Rendered in memory, only the sheets are kept.
    for label, _ in (('mid', 0), ('late', 0)):
        imgs = []
        for variant in ('occupancy', 'clearing'):
            for amb in (False, True):
                g = build(snaps[label], variant=variant, ambient=amb)
                imgs.append(to_png(g, None,
                                   label=f'{label} · dots = {variant} · '
                                         f'ambient stipple '
                                         f'{"on" if amb else "off"}'))
        stack(imgs, HERE / f'variants-{label}.png')


if __name__ == '__main__':
    main()

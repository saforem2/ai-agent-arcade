"""Xiangqi arcade — a dot-native board with native traditional-CJK pieces.

The production visual system keeps tui_dots.py's ambient field material but
uses xiangqi-specific furniture: interrupted river files, a drifting 楚河・漢界
band, palace diagonals, position marks, and a live gold flying-general spine.
At grand/cozy widths, pieces are pitch-derived solid BONE dot seals with
native K3 text faces (帥/將, 仕/士, etc.); smaller panes degrade first to a
two-cell face chip and then to equal-disc movement seals, never chess sprites.
Capture motion is the five-beat face-out/pinch/debris/reclaim/settle sequence.

Move generation and legality come from xiangqi.py (XiangqiBoard, ICCS
throughout).  The renderer preserves moves.txt as replay truth and treats
fen.txt only as a consistency cache.

Same contract as chess, different live dir. ARCADE_LIVE defaults to /tmp/xiangqi.
    fen.txt      current-position consistency cache
    moves.txt    one space-joined ICCS move log, e.g. h2e2 h7e7
    pending.txt  <agent>\t<iccs> staged for referee approval
    ctl          replay [n] | reset | banner <text> | names <r> <b>
                 | size cozy|grand
    names.txt, banner.txt, results.txt, size.txt   unchanged semantics

When stdin is a tty, a `[ ▶ replay ]` button lives on the status row: click it
(SGR mouse) or press `r` for a full replay (same path as a ctl `replay`
command), or `q` to quit cleanly. Purely additive -- headless/file-driven use
(stdin not a tty) never touches termios and renders exactly as before.
"""
import math, os, random, re, select, shutil, sys, time, unicodedata
from pathlib import Path
from xiangqi import XiangqiBoard, IllegalMove, STARTING_FEN, parse_iccs

try:
    import termios, tty
except ImportError:          # non-POSIX: input feature quietly disables itself
    termios = tty = None

D = Path(os.environ.get('ARCADE_LIVE', '/tmp/xiangqi'))
MOVES, FEN, BANNER, CTL = D / 'moves.txt', D / 'fen.txt', D / 'banner.txt', D / 'ctl'
CHAT, MATCH_JSON = D / 'chat.log', D / 'match.json'

# ---- geometry -------------------------------------------------------------
# 9 files x 10 ranks = 8 x 9 intervals. Same GEOM tiers and pane-fit formula
# as the brief (§5) — one interval taller than chess's 8x8 squares.
#
# Disc size follows the braille dots-per-cell ratio (2 wide, 4 tall).  The
# ladder is largest-first; render_tier() chooses circle, face chip, or seal
# after the real pitch has been fitted.
GEOM = ((10, 5), (8, 4), (6, 3), (5, 3), (4, 2), (3, 2))
GEOM_COZY = ((6, 3), (5, 3), (4, 2), (3, 2))
CW, CH = 4, 2                  # character cells per interval (set by fit_geometry)
SQW, SQH = CW * 2, CH * 4      # dots per interval (nominal pitch)
MARGIN_CH, MARGIN_CV = 1, 1    # char-cell margin around the lattice (set below) —
                                # edge points (file a/i, rank 0/9) sit ON the lattice
                                # boundary, so a full sprite box centred there needs
                                # this much canvas beyond the lattice itself or it's
                                # clipped in half by Grid's bounds check.
BW, BH = CW * 8, CH * 9        # canvas size in char cells: lattice span + margin
DOTW, DOTH = BW * 2, BH * 4    # dot canvas

FILES, RANKS = 9, 10           # intersections
GRAND_MIN_COLS, COZY_MIN_COLS = 113, 87
RACK_W, RACK_GAP = 29, 2
REDUCED_MOTION = os.environ.get('ARCADE_REDUCED_MOTION', '').lower() in {
    '1', 'true', 'yes', 'on',
}

def fit_geometry(cols, rows):
    """Pick the largest pitch the pane can hold — same tier-selection pattern
    as tui_dots.py, sized for 8x9 intervals (build risk #1: one interval
    taller than chess) PLUS a sprite-radius margin on every side so edge
    pieces (a0/i0/a9/i9) render whole instead of clipped at the canvas edge."""
    global CW, CH, SQW, SQH, MARGIN_CH, MARGIN_CV, BW, BH, DOTW, DOTH
    # cozy/grand remain pitch vocabulary.  Narrow panes fall to cozy even
    # when grand is preferred; an explicit cozy request never selects the
    # (8,4) grand pitch merely because surplus space happens to exist.
    geom = GEOM_COZY if SIZE == 'cozy' or cols < COZY_MIN_COLS else GEOM
    def margins_for(cw, ch):
        sqw, sqh = cw * 2, ch * 4
        box = min(sqw, sqh) - 2          # same box calc as draw_piece
        half = box // 2 + 2              # +2: moat dot + rounding slack
        return -(-half // 2), -(-half // 4)   # ceil to char cols / rows
    chosen = None
    wants_rack = cols >= GRAND_MIN_COLS and SIZE != 'cozy'
    for cw, ch in geom:
        mch, mcv = margins_for(cw, ch)
        bw, bh = cw * 8 + 2 * mch, ch * 9 + 2 * mcv
        rack_cost = RACK_GAP + RACK_W if wants_rack else 0
        if bw + 5 + rack_cost <= cols and bh + 3 <= rows:
            chosen = (cw, ch, mch, mcv, bw, bh)
            break
    if chosen is None:
        cw, ch = geom[-1]
        mch, mcv = margins_for(cw, ch)
        chosen = (cw, ch, mch, mcv, cw * 8 + 2 * mch, ch * 9 + 2 * mcv)
    cw, ch, mch, mcv, bw, bh = chosen
    changed = (cw, ch) != (CW, CH)
    CW, CH = cw, ch
    SQW, SQH = CW * 2, CH * 4
    MARGIN_CH, MARGIN_CV = mch, mcv
    BW, BH = bw, bh
    DOTW, DOTH = BW * 2, BH * 4
    return changed

# Ordered dither on the exact braille dot grid — forked verbatim from
# tui_dots.py for the ambient field. Piece seals deliberately do not use it.
BAYER = ((0, 4), (6, 2), (1, 5), (7, 3))
BITS = ((0x01, 0x02, 0x04, 0x40), (0x08, 0x10, 0x20, 0x80))  # BITS[dx][dy]
FULL = 0xFF

# ---- palette -------------------------------------------------------------
# Base field values match tui_dots.py; river, spine, and lacquer values are
# the xiangqi table's own locked material palette.
PANEL = (18, 21, 28)
NEUTRAL = (104, 116, 138)               # tui_dots' ambient field colour; plays
                                         # the lattice/node/palace-diagonal role here
AMBIENT = (52, 58, 72)                  # tui_dots' "world outside the board"
SQL, SQD = (34, 39, 50), (26, 30, 39)   # tui_dots' light/dark square plate tiers
RED_SOLID = (255, 100, 60)              # K3 vermillion identity ink
BLK_SOLID = (246, 240, 226)             # K3 warm-ivory identity ink
CHECKC = (242, 84, 94)
TEXT, TDIM, LABEL = (204, 212, 228), (118, 128, 148), (92, 102, 122)
SLATE = (136, 145, 164)
RIVER, RIVER_BG = (44, 183, 190), (12, 32, 46)
GOLD, LAST = (214, 170, 86), (245, 202, 92)
BONE, WOOD = (226, 214, 186), (206, 168, 116)
WINDOW_BG = (14, 18, 24)
INK_R, INK_B = RED_SOLID, BLK_SOLID
DISC_RADIUS_INSET = 0.6
DISC_CLEAR_SLACK = 0.8
DISC_FACE_BG = WINDOW_BG
CHECK_PRI, DEBRIS_PRI = 7, 6


def _dot_circle_k():
    """Braille already compensates for a standard terminal's 1:2 cells.

    A measured cell aspect can be supplied directly; otherwise the dot-space
    correction remains the calibrated 1.0.  Keeping this a startup parameter
    makes non-standard terminal fonts configurable without double-counting
    braille's own 2x4 dot packing.
    """
    try:
        aspect = os.environ.get('XQ_CELL_ASPECT')
        if aspect is not None:
            return max(0.5, min(1.5, float(aspect) / 2.0))
        return max(0.5, min(1.5, float(os.environ.get('XQ_CIRCLE_K', '1.0'))))
    except ValueError:
        return 1.0


def _replay_dwell_seconds():
    try:
        value = float(os.environ.get('XQ_REPLAY_DWELL', '0.7'))
    except ValueError:
        return 0.7
    if not math.isfinite(value):
        return 0.7
    return min(60.0, max(0.0, value))


DOT_CIRCLE_K = _dot_circle_k()
REPLAY_DWELL = _replay_dwell_seconds()

# Field densities, locked to tui_dots.py's own scale (§5 table).
DENS_D = 2          # open board interior — tui_dots' dark-square tier
DENS_AMB = 1         # outside the board / river band
DENS_QUIET = 1       # under an occupied intersection (moat handles contrast)
WAVE_PERIOD, WAVE_AMP = 30.0, 0.5       # unchanged from tui_dots.py

# Brightness/priority hierarchy (§6.1 point 2): pieces are always the
# brightest, drawn-last, highest-priority thing on the board; lattice lines
# sit below the nodes, which sit below pieces. Field dither is lowest (-1,
# as in tui_dots.py).
LAT_PRI, NODE_PRI, PIECE_PRI = 1, 2, 3

FACE = {
    ('K', 'r'): '帥', ('K', 'b'): '將',
    ('A', 'r'): '仕', ('A', 'b'): '士',
    ('B', 'r'): '相', ('B', 'b'): '象',
    ('R', 'r'): '俥', ('R', 'b'): '車',
    ('N', 'r'): '傌', ('N', 'b'): '馬',
    ('C', 'r'): '炮', ('C', 'b'): '砲',
    ('P', 'r'): '兵', ('P', 'b'): '卒',
}


def display_width(text):
    """Terminal-cell width without depending on wcwidth at runtime."""
    return sum(2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1
               for ch in text)


def clip_display(text, width):
    out, used = [], 0
    for ch in text:
        step = 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1
        if used + step > width:
            break
        out.append(ch)
        used += step
    return ''.join(out)


def render_tier(cols):
    """One responsive gate for every piece renderer.

    Approved layout widths get the full dot circle; narrower squares keep a
    native face on a two-cell chip, and the smallest reachable geometry uses
    the xiangqi-native void seals.
    """
    if min(SQW, SQH) - 2 >= 10:
        return 'disc'
    if CW >= 4:
        return 'chip'
    return 'seal'


def show_broadcast_rack(cols):
    return (cols >= GRAND_MIN_COLS and SIZE != 'cozy' and CW >= 8
            and render_tier(cols) == 'disc')

# Palaces: files 3-5 (d/e/f), ranks 0-2 red / 7-9 black.
PALACE_DIAGS = (
    (((3, 0), (5, 2))), (((5, 0), (3, 2))),
    (((3, 7), (5, 9))), (((5, 7), (3, 9))),
)
# Traditional position marks (cannon platforms + soldier points), (file, rank).
POS_MARKS = {(1, 2), (7, 2), (0, 3), (2, 3), (4, 3), (6, 3), (8, 3),
             (1, 7), (7, 7), (0, 6), (2, 6), (4, 6), (6, 6), (8, 6)}

SIZE = 'grand'
_s = D / 'size.txt'
if _s.exists():
    _v = _s.read_text().strip()
    if _v in ('cozy', 'grand'):
        SIZE = _v

NAMES = D / 'names.txt'
names = {'r': 'TBD', 'b': 'TBD'}
# Populated by refresh_names() (defined below, after read_cached) on the first
# render() call -- not eagerly here, since read_cached needs _fcache, which is
# initialized later in this file. Until then `names` holds these defaults,
# same as the pre-fix import-time read did before any board was ever shown.

# ---- clickable replay button + keyboard shortcuts (tty only) --------------
# Headless/file-driven use (piped output, recordings) never enters any of
# this: INPUT_ENABLED is decided once, at import time, from stdin itself.
INPUT_ENABLED = bool(termios) and sys.stdin.isatty()
BTN_TEXT = '[ ▶ replay ]'
_orig_termios = None
_btn_bounds = None   # (row, col_start, col_end), 1-indexed terminal coords -- set
                      # each render() call the button is drawn, matching how the
                      # SGR mouse protocol reports click position.
_MOUSE_RE = re.compile(rb'\x1b\[<(\d+);(\d+);(\d+)([Mm])')

def enable_input():
    """Best-effort: any failure just leaves input disabled, never crashes."""
    global _orig_termios, INPUT_ENABLED
    if not INPUT_ENABLED:
        return
    try:
        _orig_termios = termios.tcgetattr(sys.stdin.fileno())
        tty.setcbreak(sys.stdin.fileno())
        sys.stdout.write('\x1b[?1000h\x1b[?1006h')   # click tracking, SGR coords
        sys.stdout.flush()
    except Exception:
        INPUT_ENABLED = False

def disable_input():
    if not (termios and _orig_termios is not None):
        return
    try:
        sys.stdout.write('\x1b[?1006l\x1b[?1000l')
        sys.stdout.flush()
    except Exception:
        pass
    try:
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _orig_termios)
    except Exception:
        pass

def poll_input():
    """Non-blocking. Returns 'replay', 'quit', or None. Never raises or blocks
    the render cadence -- any failure degrades to render-only (returns None)."""
    if not INPUT_ENABLED:
        return None
    try:
        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if not ready:
            return None
        data = os.read(sys.stdin.fileno(), 4096)
    except Exception:
        return None
    if not data:
        return None
    for m in _MOUSE_RE.finditer(data):
        _btn, cx, cy, kind = m.groups()
        if kind == b'M' and _btn_bounds and int(cy) == _btn_bounds[0] \
                and _btn_bounds[1] <= int(cx) <= _btn_bounds[2]:
            return 'replay'
    for b in _MOUSE_RE.sub(b'', data):    # leftover plain bytes: keyboard fallback
        ch = chr(b)
        if ch in ('r', 'R'):
            return 'replay'
        if ch in ('q', 'Q'):
            return 'quit'
    return None


def read_input():
    """Return the next non-blocking replay/quit action, if any."""
    return poll_input()

ctl_mtime = 0
particles = []
move_list = []
last_move_t = time.monotonic()
last_pair = ()
_fcache = {}

def bg(c): return f'\x1b[48;2;{c[0]};{c[1]};{c[2]}m'
def fg(c): return f'\x1b[38;2;{c[0]};{c[1]};{c[2]}m'
R = '\x1b[0m'

def read(p, default=''):
    try: return p.read_text().strip()
    except OSError: return default

def read_cached(p):
    try:
        st = p.stat().st_mtime_ns
    except OSError:
        return ''
    hit = _fcache.get(p)
    if hit and hit[0] == st:
        return hit[1]
    v = read(p)
    _fcache[p] = (st, v)
    return v

def refresh_names():
    """Re-read names.txt if it changed since the last check (mtime-cached via
    read_cached: one stat() per call, a real read+parse only when the file's
    mtime moves). A viewer left running across a pairing change -- `arcade
    start` rewrites names.txt fresh for every match -- must not keep showing
    the old players forever; ported verbatim from tui_dots.py's own fix for
    the identical bug (hit live in game 6, patched there first). Missing,
    empty, or malformed content leaves `names` at its last known-good value;
    it never raises, so a bad write mid-match can't crash a running viewer."""
    parts = read_cached(NAMES).split()
    if len(parts) == 2:
        names['r'], names['b'] = parts[0].upper(), parts[1].upper()


def live_match_id():
    """Resolve the match identity from real live-dir state, with fallback.

    Normal ``arcade start`` rooms expose it in the seeded chat/banner. A
    manually assembled room may instead carry match.json or be named
    match-NNN. Before any of those exist the header stays honest.
    """
    probes = (
        (read_cached(MATCH_JSON), r'"match"\s*:\s*(\d+)'),
        (read_cached(CHAT), r'(?i)\bmatch-(\d+)\b'),
        (read_cached(BANNER), r'(?i)\bgame\s+(\d+)\b'),
        (D.name, r'(?i)^match-(\d+)$'),
    )
    for text, pattern in probes:
        match = re.search(pattern, text)
        if match:
            return f'MATCH-{int(match.group(1)):03d}'
    return 'MATCH-???'

def blend(a, b, t):
    t = max(0.0, min(1.0, t))
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))

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
    """Cell buffer — forked verbatim from tui_dots.py. Dots accumulate; higher
    priority wins the single fg colour each braille cell is allowed."""
    def __init__(self):
        self.b = [[0] * BW for _ in range(BH)]
        self.f = [[None] * BW for _ in range(BH)]
        self.p = [[-1] * BW for _ in range(BH)]
        self.ch = {}
        self.cont = set()

    def cell(self, cx, cy, bits, col, pri):
        if 0 <= cx < BW and 0 <= cy < BH:
            self.b[cy][cx] |= bits
            if pri >= self.p[cy][cx]:
                self.p[cy][cx] = pri
                self.f[cy][cx] = col

    def clear(self, x, y):
        x, y = int(x), int(y)
        if 0 <= x < DOTW and 0 <= y < DOTH:
            self.b[y // 4][x // 2] &= ~BITS[x % 2][y % 4] & 0xFF

    def dot(self, x, y, col, pri=3):
        x, y = int(x), int(y)
        if 0 <= x < DOTW and 0 <= y < DOTH:
            self.cell(x // 2, y // 4, BITS[x % 2][y % 4], col, pri)

    def glyph(self, cx, cy, char, col):
        self.text(cx, cy, char, col)

    def clear_cell(self, cx, cy):
        if 0 <= cx < BW and 0 <= cy < BH:
            self.b[cy][cx] = 0

    def purge_text_cell(self, cx, cy):
        """Remove any text glyph owning this cell, including wide continuations."""
        cx, cy = int(cx), int(cy)
        if not (0 <= cx < BW and 0 <= cy < BH):
            return
        for (text_x, text_y), glyph in list(self.ch.items()):
            if text_y != cy:
                continue
            width = 2 if unicodedata.east_asian_width(glyph[0]) in ('W', 'F') else 1
            if text_x <= cx < text_x + width:
                self.ch.pop((text_x, text_y), None)
                for dx in range(1, width):
                    self.cont.discard((text_x + dx, text_y))
        self.cont.discard((cx, cy))

    def set_cell(self, cx, cy, bits, col, pri):
        if 0 <= cx < BW and 0 <= cy < BH:
            self.b[cy][cx] = bits
            self.f[cy][cx] = col
            self.p[cy][cx] = pri

    def text(self, cx, cy, text, col, back=None, bold=False):
        """Overlay terminal text while accounting for double-width CJK.

        `cont` marks the second terminal cell owned by a wide glyph so the
        row composer does not print an extra board cell underneath it.
        """
        cx, cy = int(cx), int(cy)
        for char in text:
            width = 2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1
            if 0 <= cx < BW and 0 <= cy < BH and cx + width <= BW:
                self.ch[(cx, cy)] = (char, col, back, bold)
                self.b[cy][cx] = 0
                for dx in range(1, width):
                    self.cont.add((cx + dx, cy))
                    self.b[cy][cx + dx] = 0
            cx += width

def px(f):
    """Dot-x of file f (0=a..8=i): an exact multiple of SQW from the left
    margin. §6.2 point 1's canvas margin (MARGIN_CH, set in fit_geometry)
    gives every point — including files a/i on the canvas boundary — room
    for a full sprite box, so the earlier "distribute across DOTW-1" fencepost
    dodge is no longer needed now that there's headroom on both sides."""
    return MARGIN_CH * 2 + f * SQW

def py(r):
    """Dot-y of rank r (0=red back rank, 9=black back rank): an exact
    multiple of SQH from the top margin — and because SQH is by construction
    a multiple of 4, every rank's dot-y is an exact multiple of 4, landing
    EXACTLY on a char-row boundary with zero sub-cell offset. This is also
    the §6.2 point 3 fix: the previous "distribute across DOTH-1" fencepost
    formula rounded to uneven sub-row offsets per rank — 0 for ranks 5-9,
    3 for ranks 0-4 — which is exactly why the black-side rows read as
    sitting high relative to their labels while the red-side rows read true.
    y grows downward, so rank 9 (black) draws nearer the top."""
    return MARGIN_CV * 4 + (RANKS - 1 - r) * SQH


def _travel_center(x0, y0, x1, y1, eased):
    """Snap a glide sample onto the same 2x4 dot lattice as static discs."""
    center_x = 2 * round((x0 + (x1 - x0) * eased + 0.5) / 2) - 0.5
    center_y = 4 * round((y0 + (y1 - y0) * eased - 1.5) / 4) + 1.5
    return center_x, center_y

def draw_line(g, x0, y0, x1, y1, col, pri=1):
    """Exact 1-dot-wide line, axis-aligned or 45-degree only (all lattice and
    palace-diagonal segments are). Walking dot-by-dot keeps the line crisp
    and, because it never touches cell_bits/the wave, exempts it from the
    shimmer risk the brief calls out (§5, §7.3)."""
    dx, dy = x1 - x0, y1 - y0
    n = max(abs(dx), abs(dy))
    if n == 0:
        g.dot(x0, y0, col, pri)
        return
    for i in range(n + 1):
        g.dot(x0 + dx * i / n, y0 + dy * i / n, col, pri)

def draw_lattice(g):
    """The lattice IS the dot field made denser along the 9x10 grid lines —
    drawn as literal dots (exempt from the wave by construction), coloured
    NEUTRAL (no new "LATTICE" constant — §0 permits only RED_SOLID)."""
    # verticals: files 0 and 8 run the full board; files 1-7 stop at both
    # riverbanks, per §5 "the river is a quiet break, not a labelled banner."
    for f in range(FILES):
        x = px(f)
        if f in (0, FILES - 1):
            draw_line(g, x, py(0), x, py(9), NEUTRAL, LAT_PRI)
        else:
            draw_line(g, x, py(0), x, py(4), NEUTRAL, LAT_PRI)
            draw_line(g, x, py(5), x, py(9), NEUTRAL, LAT_PRI)
    # horizontals: every rank line, edge to edge.
    for r in range(RANKS):
        y = py(r)
        bank = RIVER if r in (4, 5) else NEUTRAL
        draw_line(g, px(0), y, px(FILES - 1), y, bank, LAT_PRI)
    # palace diagonals: §6.1 point 5 — raised to FULL lattice brightness
    # (they were noise-level at 60%); one dot wide, structure not speckle.
    for (f0, r0), (f1, r1) in PALACE_DIAGS:
        draw_line(g, px(f0), py(r0), px(f1), py(r1), NEUTRAL, LAT_PRI)
    # position marks: four short dot ticks around the intersection, same
    # brightness tier as the lattice/diagonals above (§6.1 point 5's raise
    # applies to this too — "palace-diagonal brightness" now equals full).
    for (f, r) in POS_MARKS:
        x, y = px(f), py(r)
        for sx in (-1, 1):
            if f == 0 and sx < 0: continue
            if f == FILES - 1 and sx > 0: continue
            for sy in (-1, 1):
                if r == 0 and sy < 0: continue
                if r == RANKS - 1 and sy > 0: continue
                g.dot(x + sx * 2, y + sy * 1, NEUTRAL, LAT_PRI)
                g.dot(x + sx * 1, y + sy * 2, NEUTRAL, LAT_PRI)
    # node clusters: 2x2 dots at every intersection so play points read as
    # points — same NEUTRAL, one tier brighter-priority than plain lattice
    # lines (still strictly below piece priority, §6.1 point 2).
    for f in range(FILES):
        for r in range(RANKS):
            x, y = px(f), py(r)
            for ox in (0, 1):
                for oy in (0, 1):
                    g.dot(x + ox, y + oy, NEUTRAL, NODE_PRI)


def draw_river(g, t):
    """Three water rows drift at ~2 fps, alternating direction by row."""
    top, bottom = sorted((py(5) // 4, py(4) // 4))
    patterns = (
        (0x04, 0x24, 0x20, 0x40, 0x60, 0x80),
        (0x01, 0x09, 0x08, 0x02, 0x12, 0x10),
        (0x40, 0xC0, 0x80, 0x04, 0x24, 0x20),
    )
    drift = 0 if REDUCED_MOTION else int(t * 2)
    left, right = px(0) // 2, px(FILES - 1) // 2
    for row, cy in enumerate(range(top + 1, bottom)):
        direction = 1 if row % 2 == 0 else -1
        pattern = patterns[row % len(patterns)]
        for cx in range(left, right + 1):
            # Leave every fourth cell as the low RIVER_BG dot-matter band;
            # the remaining cells carry the brighter moving current.  Grid
            # has one foreground colour per braille cell, so this cadence is
            # how both river tones coexist without a background-fill stripe.
            if (cx + row) % 4 == 0:
                continue
            g.set_cell(cx, cy, pattern[(cx + direction * drift) % len(pattern)],
                       RIVER, NODE_PRI)


def flying_general_state(board):
    red, black = board.red_general, board.black_general
    if red[1] != black[1]:
        return 'offset', None
    col = red[1]
    lo, hi = sorted((red[0], black[0]))
    screens = sum(board.board[r][col] is not None for r in range(lo + 1, hi))
    return ('open' if screens == 0 else 'sealed'), screens


def draw_spine(g, board):
    state, screens = flying_general_state(board)
    live = state == 'open' or (state == 'sealed' and screens == 1)
    color = LAST if live else GOLD
    for y in range(py(9), py(0) + 1):
        if y % 4 in (0, 1):
            g.dot(px(4), y, color, NODE_PRI)


def draw_move_trails(g, moves):
    """Keep three plies of gold route memory; older routes fade by ply."""
    strengths = (0.22, 0.42, 0.82)
    for move, strength in zip(moves[-3:], strengths[-len(moves[-3:]):]):
        try:
            (r0, f0), (r1, f1) = parse_iccs(move)
        except (ValueError, IndexError):
            continue
        x0, y0, x1, y1 = px(f0), py(r0), px(f1), py(r1)
        steps = max(abs(x1 - x0), abs(y1 - y0), 1)
        color = blend(PANEL, GOLD, strength)
        for i in range(steps + 1):
            if i % 4 in (0, 1):
                g.dot(x0 + (x1 - x0) * i / steps,
                      y0 + (y1 - y0) * i / steps, color, NODE_PRI)


def draw_river_labels(g):
    mid = (py(5) // 4 + py(4) // 4) // 2
    left = max(0, px(2) // 2 - 3)
    center = max(0, px(4) // 2)
    right = min(BW - 8, px(6) // 2 - 3)
    for start, width in ((left, 8), (center, 2), (right, 8)):
        for cx in range(start, min(BW, start + width)):
            g.clear_cell(cx, mid)
            g.text(cx, mid, ' ', RIVER, RIVER_BG)
    g.text(left, mid, '楚  河', GOLD, RIVER_BG, True)
    g.text(center, mid, '◆', GOLD, RIVER_BG, True)
    g.text(right, mid, '漢  界', GOLD, RIVER_BG, True)

def draw_field(g, t):
    """Resident field breathing plus palace/river identity as dot matter.

    The substrate stays uniform. Palaces gain one density step; the river
    drops to RIVER_BG undertow dots whose horizontal phase drifts through the
    same slow wave. draw_river() adds the brighter ~2 fps opposing currents.
    """
    river_top, river_bot = py(5), py(4)
    palace_x0, palace_x1 = sorted((px(3) // 2, px(5) // 2))
    red_y0, red_y1 = sorted((py(0) // 4, py(2) // 4))
    black_y0, black_y1 = sorted((py(7) // 4, py(9) // 4))
    for cy in range(BH):
        for cx in range(BW):
            in_river = river_top <= cy * 4 < river_bot
            in_palace = (palace_x0 <= cx <= palace_x1
                          and (red_y0 <= cy <= red_y1
                               or black_y0 <= cy <= black_y1))
            base = DENS_AMB if in_river else DENS_D + (1 if in_palace else 0)
            phase = 2 * math.pi * t / WAVE_PERIOD
            if in_river:
                phase += 2 * math.pi * (cx / max(1, BW)) * 3   # horizontal drift
            wave = math.sin(phase)
            lvl = max(0.0, min(7.0, base + WAVE_AMP * wave))
            matter = RIVER_BG if in_river else AMBIENT
            g.cell(cx, cy, cell_bits(cx, cy, lvl), matter, -1)

def board_plate():
    """Uniform substrate; palace and river identity now lives in dot matter."""
    return [[SQD] * BW for _ in range(BH)]

def rank_label_rows():
    """char-row -> rank digit, for the left-margin prefix in render(). Kept
    OUT of the Grid entirely (glyph() into an edge cell would clobber the
    file-0 lattice line it sits on) — chess prefixes its rank label the same
    way, as a string, not a board glyph."""
    return {py(r) // 4: str(r) for r in range(RANKS)}

def file_label_row():
    """The bottom file-letter row (a-i), built as its own string aligned to
    each point's column — printed below the board, never inside it."""
    row = [' '] * BW
    for f in range(FILES):
        col = px(f) // 2
        if 0 <= col < BW:
            row[col] = 'abcdefghi'[f]
    return ''.join(row)

def void_seal(sym):
    """Codex's equal-disc movement seals, packed into a 3x2 braille tile."""
    def disc(x, y):
        return ((x - 2.5) / 2.8) ** 2 + ((y - 2.5) / 2.8) ** 2 <= 1

    def hole(x, y):
        if sym == 'K':
            return 1 <= x <= 4 and 1 <= y <= 4 and not (2 <= x <= 3 and 2 <= y <= 3)
        if sym == 'A':
            return x == y or x + y == 5
        if sym == 'B':
            return (x in (1, 2) and y in (2, 3)) or (x in (3, 4) and y in (2, 3))
        if sym == 'R':
            return x in (2, 3) or y in (2, 3)
        if sym == 'N':
            return (x in (1, 2) and 1 <= y <= 4) or (1 <= x <= 4 and y in (3, 4))
        if sym == 'C':
            return 1 <= x <= 4 and 1 <= y <= 4 and not (x in (2, 3) and y in (2, 3))
        return y >= 1 and abs(x - 2.5) <= max(0.6, (y - 1) * 0.65)

    dots = [[disc(x, y) and not hole(x, y) for x in range(6)] for y in range(8)]
    rows = []
    for by in (0, 4):
        row = ''
        for bx in (0, 2, 4):
            bits = 0
            for yy in range(4):
                for xx in range(2):
                    if dots[by + yy][bx + xx]:
                        bits |= BITS[xx][yy]
            row += chr(0x2800 + bits)
        rows.append(row)
    return rows


def piece_material_color(color):
    """Captured dot matter is the physical BONE body, never identity ink."""
    return BONE


def disc_geometry():
    """Return the pitch-derived (box, radius) used by every disc phase."""
    box = min(SQW, SQH) - 2
    return box, box / 2.0 - DISC_RADIUS_INSET


def _face_window(x, y, center_dot_x, face_row_dot_y, box):
    """Cell-quantized sticker well around the two-cell CJK face.

    Four corner dots stay lit: at 4-8 dots of vertical resolution that reads
    as a softened rectangle more reliably than pretending we can draw a
    genuinely curved inner window.  Box 10 (the cozy short-pane disc) has no
    well because it cannot spare a full bone annulus around one.
    """
    if box < 14:
        return False
    pad = 2 if box >= 18 else 1
    # The glyph starts one terminal cell left of center_dot_x and occupies
    # two cells: four dot columns by four dot rows. Build the sticker well
    # outward from those absolute dot coordinates so every rank/file uses
    # exactly the same quantized geometry.
    x0, x1 = center_dot_x - 2 - pad, center_dot_x + 1 + pad
    y0, y1 = face_row_dot_y - pad, face_row_dot_y + 3 + pad
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return False
    return (x, y) not in {(x0, y0), (x0, y1), (x1, y0), (x1, y1)}


def draw_void_seal(g, sym, color, f, r, effect=None):
    if effect in ('hidden', 'field'):
        return
    ink = RED_SOLID if color == 'r' else BLK_SOLID
    rows = void_seal(sym)
    cx0, cy0 = px(f) // 2 - 1, py(r) // 4 - 1
    for dy, row in enumerate(rows):
        for dx in range(3):
            g.clear_cell(cx0 + dx, cy0 + dy)
        g.text(cx0, cy0 + dy, row, ink)


def draw_dot_circle(g, sym, color, f, r, effect=None, *, fill_color=BONE,
                    face_bg=DISC_FACE_BG, radius=None, center=None):
    """Approved solid true-dot-space disc with an absolute sticker well."""
    if effect in ('hidden', 'field'):
        return
    box, natural_radius = disc_geometry()
    radius = natural_radius if radius is None else radius
    if effect == 'pinch':
        radius = max(2.0, radius * 0.48)
    elif effect == 'settle':
        radius = max(2.0, radius * 0.86)
    flying = center is not None
    if not flying:
        center_dot_x, face_row_dot_y = px(f), py(r)
        center_x, center_y = center_dot_x - 0.5, face_row_dot_y + 1.5
    else:
        center_x, center_y = center
        # Travel supplies a center snapped to the static 2x4 lattice. Derive
        # the same absolute face/window anchor as the ordinary static path.
        face_cell_x = math.floor((center_x - 1.5) / 2.0 + 0.5)
        face_cell_y = math.floor((center_y - 1.5) / 4.0 + 0.5)
        center_dot_x = 2 * (face_cell_x + 1)
        face_row_dot_y = 4 * face_cell_y
    moat = radius + DISC_CLEAR_SLACK
    extent = int(math.ceil(moat)) + 1
    for y in range(math.floor(center_y) - extent,
                   math.ceil(center_y) + extent + 1):
        for x in range(center_dot_x - extent, center_dot_x + extent + 1):
            distance = math.hypot(x - center_x, (y - center_y) * DOT_CIRCLE_K)
            if distance <= radius + DISC_CLEAR_SLACK:
                g.clear(x, y)
            if flying and distance <= radius:
                g.purge_text_cell(x // 2, y // 4)
            if distance > radius or _face_window(
                    x, y, center_dot_x, face_row_dot_y, box):
                continue
            g.dot(x, y, fill_color, 5)
    if effect not in ('face_out', 'pinch'):
        ink = INK_R if color == 'r' else INK_B
        g.text(center_dot_x // 2 - 1, face_row_dot_y // 4, FACE[(sym, color)],
               ink, face_bg, True)


def draw_face_chip(g, sym, color, f, r, effect=None, *, face_bg=WINDOW_BG):
    if effect in ('hidden', 'field'):
        return
    cx, cy = px(f) // 2 - 1, py(r) // 4
    for dx in range(2):
        g.clear_cell(cx + dx, cy)
    if effect in ('face_out', 'pinch'):
        g.text(cx, cy, '  ', AMBIENT, face_bg)
    else:
        ink = INK_R if color == 'r' else INK_B
        g.text(cx, cy, FACE[(sym, color)], ink, face_bg, True)


def draw_piece_style(g, sym, color, f, r, t=0.0, checked=False,
                     tier='disc', effect=None):
    """The only production seam for above-floor piece presentation."""
    if tier == 'chip':
        draw_face_chip(g, sym, color, f, r, effect)
    else:
        draw_dot_circle(g, sym, color, f, r, effect)


def draw_piece(g, sym, color, f, r, t=0.0, checked=False, tier=None, effect=None,
               center=None):
    if center is not None and tier == 'disc':
        draw_dot_circle(g, sym, color, f, r, effect, center=center)
    elif tier == 'seal':
        draw_void_seal(g, sym, color, f, r, effect)
    else:
        draw_piece_style(g, sym, color, f, r, t, checked, tier, effect)


def spawn_debris(square, color, n=30, now=None):
    """Spawn captured-shell matter at an ICCS (rank, file) square."""
    rank, file = square
    born = time.monotonic() if now is None else now
    material = piece_material_color(color)
    for _ in range(n):
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(8, 30)
        particles.append([
            px(file) - 0.5, py(rank) + 1.5,
            math.cos(angle) * speed,
            math.sin(angle) * speed * 0.55,
            born, random.uniform(0.4, 0.85), material,
        ])


def draw_particles(g, t):
    live = []
    for particle in particles:
        age = t - particle[4]
        if age >= particle[5]:
            continue
        live.append(particle)
        strength = 1 - age / particle[5]
        g.dot(particle[0] + particle[2] * age,
              particle[1] + particle[3] * age + 18 * age * age,
              blend(PANEL, particle[6], strength), DEBRIS_PRI)
    particles[:] = live

def build(fen, moves):
    """`fen` must be a true STARTING position -- moves replay ON TOP of it,
    same as ref_xq.py's own replay()/verify() ("every apply replays the
    whole log from the start"). Every caller in this file passes
    STARTING_FEN specifically, never fen.txt: fen.txt is the referee's
    CURRENT-position cache (ref_xq.py rewrites it after every ply, for its
    own tamper-detection use, not as a replay base), so treating it as the
    base here double-applies the whole log on top of an already-current
    position and every move after ply 0 comes out illegal -- the cold-start
    crash this fixed (team lead's traceback, 2026-08-11: relaunching the
    viewer against a room with one move played raised IllegalMove on move
    1). See check_fen_consistency() for the correct (read-only) use of
    fen.txt from this file."""
    b = XiangqiBoard.from_fen(fen)
    for mv in moves:
        b.push(mv)
    return b

def check_fen_consistency(board):
    """fen.txt is a CONSISTENCY CHECK, not a replay base (see build()'s
    docstring). If it disagrees with the position we just replayed from the
    true STARTING_FEN, that is exactly the divergence ref_xq.py's own
    TAMPER detection exists to catch on the referee side -- surface it to
    stderr for a human/facilitator (ref_xq.py resolve is the fix on that
    side) but never raise or block rendering: the viewer's job is to show
    the log-replayed position regardless of what fen.txt currently holds."""
    stored = read(FEN)
    if stored and stored != board.fen():
        sys.stderr.write(
            f'NOTE: fen.txt disagrees with the move log replayed from the '
            f'starting position (log: {board.fen()!r}, fen.txt: {stored!r}). '
            f'This is the referee\'s job to resolve (ref_xq.py resolve), not '
            f'the viewer\'s -- rendering the log-replayed position anyway.\n')

def load_state():
    """Cold-start (and reload-after-divergence) board construction: ALWAYS
    replays moves.txt from STARTING_FEN, never from fen.txt -- see build()'s
    docstring for the bug this fixes. Returns (board, seen_moves)."""
    seen = read(MOVES).split()
    board = build(STARTING_FEN, seen)
    check_fen_consistency(board)
    return board, seen


START_COUNTS = {'K': 1, 'A': 2, 'B': 2, 'R': 2, 'N': 2, 'C': 2, 'P': 5}
CAPTURE_ORDER = ('R', 'N', 'C', 'B', 'A', 'P', 'K')


def captured_piece_faces(board):
    """Return captured faces, grouped by the side that took each piece."""
    remaining = {'r': {sym: 0 for sym in START_COUNTS},
                 'b': {sym: 0 for sym in START_COUNTS}}
    for row in board.board:
        for piece in row:
            if piece:
                side = 'r' if piece.isupper() else 'b'
                remaining[side][piece.upper()] += 1
    missing = {
        side: ''.join(
            FACE[(sym, side)] * max(0, START_COUNTS[sym] - remaining[side][sym])
            for sym in CAPTURE_ORDER
        )
        for side in ('r', 'b')
    }
    # Red captures black pieces and vice versa.
    return {'r': missing['b'], 'b': missing['r']}


def _rack_rows(board, over, check):
    """Grand-only spectator data; every line is derived from live state."""
    rows = []

    def add(text='', color=TDIM, bold=False):
        text = clip_display(text, RACK_W)
        rows.append(fg(color) + ('\x1b[1m' if bold else '') + text
                    + ('\x1b[22m' if bold else ''))

    add('┌ BROADCAST', TEXT, True)
    add(f'│ {names["r"]} / {names["b"]}', LABEL, True)
    add('│')
    add('│ SPINE · file e', GOLD, True)
    occupants = []
    for rank in range(9, -1, -1):
        piece = board.board[rank][4]
        if piece:
            color = 'r' if piece.isupper() else 'b'
            occupants.append(f'{FACE[(piece.upper(), color)]}@{rank}')
    add('│ ' + '  '.join(occupants), TDIM)
    state, screens = flying_general_state(board)
    if state == 'offset':
        add('│ OFFSET · no shared file', GOLD)
    elif state == 'open':
        add('│ OPEN · FLYING GENERAL', CHECKC, True)
    else:
        add(f'│ SEALED · {screens} screen' + ('s' if screens != 1 else ''), GOLD)
    add('│')
    add('│ LAST MOVE', LAST, True)
    add('│ ' + (move_list[-1] if move_list else '—'), LAST)
    add('│')
    add('│ SCORECARD', LABEL, True)
    recent = move_list[-6:]
    start = max(0, len(move_list) - len(recent))
    if start % 2:
        start -= 1
        recent = move_list[start:]
    if recent:
        for i in range(0, len(recent), 2):
            ply = start + i
            pair = f'{ply // 2 + 1}. {recent[i]}'
            if i + 1 < len(recent):
                pair += f'  {recent[i + 1]}'
            add('│ ' + pair, TDIM)
    else:
        add('│ 1. …', TDIM)
    add('│')
    red_count = sum(p is not None and p.isupper() for row in board.board for p in row)
    black_count = sum(p is not None and p.islower() for row in board.board for p in row)
    captured = captured_piece_faces(board)
    add('│ CAPTURES', LABEL, True)
    add('│ RED   ' + (captured['r'] or '—'), RED_SOLID)
    add('│ BLACK ' + (captured['b'] or '—'), BLK_SOLID)
    add('│')
    add('│ MATERIAL', LABEL, True)
    add(f'│ RED {red_count:02d} · BLACK {black_count:02d}', TDIM)
    add('│')
    add('│ STATUS', LABEL, True)
    if over:
        add('│ GAME OVER', CHECKC, True)
    elif check:
        add('│ CHECK', CHECKC, True)
    else:
        add('│ IN PLAY', TEXT, True)
    add('└──────────────────────', LABEL)
    return rows


def render(board, status_extra='', event=None, fly=None):
    global _btn_bounds
    refresh_names()
    t = 0.0 if REDUCED_MOTION else time.monotonic()
    cols, rows = shutil.get_terminal_size((46, 30))
    if cols < 29 or rows < 22:
        _btn_bounds = None    # pane too small to draw it -- stale bounds must not fire
        sys.stdout.write('\x1b[H' + bg(PANEL) + fg(TEXT) + ' xiangqi board needs 29x22 '
                         + '\x1b[K' + R + '\x1b[J')
        sys.stdout.flush()
        return
    if fit_geometry(cols, rows):
        sys.stdout.write('\x1b[2J')
    tier = render_tier(cols)
    show_rack = show_broadcast_rack(cols)
    # The 29-column floor has room for the smallest board plus one rank-label
    # cell, not the grand layout's padded three-cell gutter.  Compressing
    # only that gutter preserves the seal tier without ever wrapping.
    label_w = 3 if BW + 3 <= cols else max(1, cols - BW)
    boardw = BW + label_w + (RACK_GAP + RACK_W if show_rack else 0)
    LP = ' ' * max(0, (cols - boardw) // 2)
    show_head, show_ban = boardw >= 44, bool(read_cached(BANNER))
    def budget():
        return BH + 3 + show_head + show_ban   # +1 board rows for the file-letter row
    for drop in ('ban', 'head'):
        if budget() <= rows:
            break
        if drop == 'ban':
            show_ban = False
        else:
            show_head = False
    def line(s):
        return bg(PANEL) + LP + s + bg(PANEL) + '\x1b[K' + R + '\n'

    over = board.is_checkmate() or board.is_stalemate()
    check = board.is_check() and not over
    check_gen = (board.red_general if board.turn == 'r' else board.black_general) if check else None
    g = Grid()
    draw_field(g, t)
    draw_river(g, t)
    draw_lattice(g)
    draw_spine(g, board)
    draw_move_trails(g, move_list)
    draw_river_labels(g)
    disc_fly = fly if (fly and tier == 'disc') else None
    hidden = disc_fly[3] if disc_fly else None
    for r in range(RANKS):
        for f in range(FILES):
            if (r, f) == hidden:
                continue
            p = board.board[r][f]
            if p:
                color = 'r' if p.isupper() else 'b'
                effect = None
                if event and event.get('square') == (r, f):
                    effect = event.get('phase')
                draw_piece(g, p.upper(), color, f, r, t,
                           checked=(check_gen == (r, f)), tier=tier, effect=effect)
    if disc_fly:
        p, center_x, center_y, (r, f) = disc_fly
        color = 'r' if p.isupper() else 'b'
        draw_piece(g, p.upper(), color, f, r, t, tier='disc',
                   center=(center_x, center_y))
    if check:
        gen = check_gen
        ph = (t % 1.4) / 1.4
        rad = 3 + ph * 20
        cxp, cyp = px(gen[1]) - 0.5, py(gen[0]) + 1.5
        col = blend(PANEL, CHECKC, 1 - ph)
        for a in range(0, 360, 12):
            g.dot(cxp + rad * math.cos(math.radians(a)),
                  cyp + rad * 0.7 * math.sin(math.radians(a)), col, CHECK_PRI)
    draw_particles(g, t)

    out = ['\x1b[H\x1b[?25l']
    pad = max(0, min(2, (rows - budget()) // 2))
    for _ in range(pad):
        out.append(line(''))
    if show_head:
        match_id = live_match_id()
        fixed = f'XIANGQI · {match_id} ·  (red) vs  (black)'
        head_name_w = max(1, (boardw - display_width(fixed)) // 2)
        red_name = clip_display(names['r'], head_name_w)
        black_name = clip_display(names['b'], head_name_w)
        out.append(line(fg(TEXT) + f'XIANGQI · {match_id} · '
                        + fg(RED_SOLID) + f'\x1b[1m{red_name}\x1b[22m'
                        + fg(TDIM) + ' (red) vs '
                        + fg(BLK_SOLID) + f'\x1b[1m{black_name}\x1b[22m'
                        + fg(TDIM) + ' (black)'))
    rank_rows = rank_label_rows()
    plate = board_plate()
    rack = _rack_rows(board, over, check) if show_rack else []
    for cy in range(BH):
        if label_w >= 3:
            lab = f' {rank_rows[cy]} ' if cy in rank_rows else ' ' * label_w
        else:
            lab = rank_rows.get(cy, ' ' * label_w)
        row, pf, pb, pbold = fg(LABEL) + bg(PANEL) + lab, None, PANEL, False
        cx = 0
        while cx < BW:
            if (cx, cy) in g.cont:
                cx += 1
                continue
            gl = g.ch.get((cx, cy))
            col = gl[1] if gl else (g.f[cy][cx] or AMBIENT)
            cbg = gl[2] if gl and gl[2] is not None else plate[cy][cx]
            is_bold = bool(gl and gl[3])
            if col != pf:
                row += fg(col); pf = col
            if cbg != pb:
                row += bg(cbg); pb = cbg
            if is_bold != pbold:
                row += '\x1b[1m' if is_bold else '\x1b[22m'
                pbold = is_bold
            row += gl[0] if gl else chr(0x2800 + g.b[cy][cx])
            cx += 2 if gl and unicodedata.east_asian_width(gl[0]) in ('W', 'F') else 1
        if show_rack:
            rack_line = rack[cy] if cy < len(rack) else ''
            row += R + bg(PANEL) + ' ' * RACK_GAP + rack_line
        out.append(line(row + R + bg(PANEL)))
    out.append(line(fg(LABEL) + ' ' * label_w + file_label_row()))
    # The control is useful only when it can coexist with the mandatory turn
    # status. At the 29-column floor it disappears instead of wrapping.
    footer_button = INPUT_ENABLED and cols - len(LP) >= 46
    button_cost = len(BTN_TEXT) + 2 if footer_button else 0
    status_budget = max(1, cols - len(LP) - 3 - button_cost)
    if over:
        winner = names['b'] if board.turn == 'r' else names['r']
        winner = clip_display(winner, max(1, status_budget - len(' WINS')))
        c = BLK_SOLID if board.turn == 'r' else RED_SOLID
        status_colored = f'\x1b[1m{fg(c)}{winner} WINS{R}{bg(PANEL)}'
        status_plain_len = len(f'{winner} WINS')
    else:
        side = names['r'] if board.turn == 'r' else names['b']
        mandatory = ' to move' + ('  CHECK' if check else '')
        side = clip_display(side, max(1, status_budget - display_width(mandatory)))
        segments = [(f'{side} to move', fg(TEXT))]
        if check:
            segments.append(('  CHECK', fg(CHECKC)))
        optional = []
        if move_list:
            optional.append((f'  last {move_list[-1]}', fg(LAST)))
        if status_extra:
            optional.append((status_extra, fg(TDIM)))
        used = sum(display_width(text) for text, _ in segments)
        for text, color_code in optional:
            if used + display_width(text) <= status_budget:
                segments.append((text, color_code))
                used += display_width(text)
        status_colored = ''.join(color_code + text for text, color_code in segments)
        status_plain_len = used
    if footer_button:
        gap = '  '
        row = len(out)   # 1-indexed terminal row this line() call will land on
        col_start = len(LP) + 3 + status_plain_len + len(gap) + 1
        _btn_bounds = (row, col_start, col_start + len(BTN_TEXT) - 1)
        out.append(line(f'   {status_colored}{gap}{fg(SLATE)}{BTN_TEXT}{R}{bg(PANEL)}'))
    else:
        _btn_bounds = None
        out.append(line(f'   {status_colored}'))
    if show_ban:
        ban = read_cached(BANNER)
        out.append(line(f'   {fg(SLATE)}{clip_display(ban, boardw - 4)}' if ban else ''))
    out.append(bg(PANEL) + '\x1b[J' + R)
    sys.stdout.write(''.join(out))
    sys.stdout.flush()

def ctl_changed():
    try:
        return CTL.exists() and CTL.stat().st_mtime_ns > ctl_mtime
    except OSError:
        return False


def _capture_beat(board, square, phase, duration, status_extra, interruptible):
    """Render one capture beat and return an optional replay/input action."""
    render(board, status_extra=status_extra,
           event={'square': square, 'phase': phase})
    if not REDUCED_MOTION and duration:
        time.sleep(duration)
    if interruptible:
        action = poll_input()
        if action:
            return action
        if ctl_changed():
            return 'ctl'
    return None


def animate_move(board, iccs, interruptible=False, status_extra=''):
    """Apply one ICCS move through the locked xiangqi event vocabulary.

    Captures are five beats: victim face out, shell pinch, dot debris, field
    reclaim, then the moving disc settles.  The board push happens exactly
    once between reclaim and settle, so an animation interruption can never
    strand the authoritative position between states.
    """
    global move_list, last_move_t, last_pair
    if iccs not in board.legal_moves():
        board.push(iccs)                 # preserve XiangqiBoard's error text
    src, dst = parse_iccs(iccs)
    mover = board.board[src[0]][src[1]]
    victim = board.board[dst[0]][dst[1]]
    action = None

    if not REDUCED_MOTION:
        x0, y0 = px(src[1]) - 0.5, py(src[0]) + 1.5
        x1, y1 = px(dst[1]) - 0.5, py(dst[0]) + 1.5
        t0, duration = time.monotonic(), 0.5
        debris_spawned = False
        while True:
            if interruptible:
                action = poll_input()
                if action:
                    break
                if ctl_changed():
                    action = 'ctl'
                    break
            travel_elapsed = time.monotonic() - t0
            elapsed = travel_elapsed / duration
            if victim is not None and elapsed >= 0.60 and not debris_spawned:
                victim_color = 'r' if victim.isupper() else 'b'
                spawn_debris(dst, victim_color, now=t0 + duration * 0.60)
                debris_spawned = True
            if travel_elapsed >= duration:
                break
            eased = elapsed * elapsed * (3 - 2 * elapsed)
            center_x, center_y = _travel_center(x0, y0, x1, y1, eased)
            travel_event = None
            if victim is not None:
                if elapsed < 0.45:
                    phase = 'face_out'
                elif elapsed < 0.60:
                    phase = 'pinch'
                elif elapsed < 0.75:
                    phase = 'hidden'
                else:
                    phase = 'field'
                # Elapsed-time windows preserve the 0.5s choreography. A
                # frame slower than one window may skip that visual beat;
                # the guarded hidden transition still spawns debris once.
                travel_event = {'square': dst, 'phase': phase}
            render(board, status_extra=status_extra, event=travel_event,
                   fly=(mover, center_x, center_y, src))
            time.sleep(0.033)

    board.push(iccs)
    move_list = move_list + [iccs]
    last_pair = (src, dst)
    last_move_t = time.monotonic()

    if action is None:
        if REDUCED_MOTION:
            render(board, status_extra=status_extra)
        else:
            action = _capture_beat(board, dst, 'settle',
                                   0.075 if victim is not None else 0.05,
                                   status_extra, interruptible)
    return action

def replay_all(fen, moves, tail=None):
    """Return ``(board, action)`` and never swallow a live replay/quit input."""
    global move_list
    skip = moves[:-tail] if tail and tail < len(moves) else []
    b = build(fen, skip)
    del particles[:]
    move_list = list(skip)
    render(b, status_extra='  replay')
    time.sleep(0.5)
    replay_moves = moves[len(skip):]
    for ply, mv in enumerate(replay_moves):
        if ctl_changed():
            return build(fen, moves), None
        try:
            action = animate_move(b, mv, interruptible=True,
                                  status_extra='  replay')
        except IllegalMove:
            break
        if action:
            move_list = list(moves)
            return build(fen, moves), action
        if ply + 1 < len(replay_moves):
            remaining = REPLAY_DWELL
            while remaining > 0:
                pause = min(0.05, remaining)
                time.sleep(pause)
                remaining = max(0.0, remaining - pause)
                action = read_input()
                changed = ctl_changed()
                if action:
                    move_list = list(moves)
                    return build(fen, moves), action
                if changed:
                    return build(fen, moves), None
    move_list = list(moves)
    return b, None


def do_replay(tail=None):
    """Replay, restarting immediately when replay itself is requested."""
    while True:
        board, action = replay_all(STARTING_FEN, read(MOVES).split(), tail)
        if action == 'quit':
            return board, 'quit'
        if action == 'replay':
            tail = None
            continue
        return board, None


def set_size(value):
    """Apply and persist the public cozy/grand pitch control."""
    global SIZE
    if value not in ('cozy', 'grand') or value == SIZE:
        return False
    SIZE = value
    (D / 'size.txt').write_text(value)
    del particles[:]
    return True

def main():
    global move_list, SIZE, ctl_mtime
    sys.stdout.write('\x1b[2J')
    board, seen = load_state()
    move_list = list(seen)
    ctl_mtime = CTL.stat().st_mtime_ns if CTL.exists() else 0
    enable_input()
    try:
        _main_loop(board, seen)
    finally:
        disable_input()

def _main_loop(board, seen):
    global move_list, SIZE, ctl_mtime
    while True:
        if CTL.exists() and CTL.stat().st_mtime_ns > ctl_mtime:
            ctl_mtime = CTL.stat().st_mtime_ns
            cmd = read(CTL).split(None, 1)
            if cmd:
                if cmd[0] == 'replay':
                    tail = int(cmd[1]) if len(cmd) > 1 and cmd[1].strip().isdigit() else None
                    board, action = do_replay(tail)
                    if action == 'quit':
                        return board
                    seen = read(MOVES).split()
                    move_list = list(seen)
                elif cmd[0] == 'reset':
                    # ref_xq.py's own `init` always resets to XiangqiBoard()
                    # (the true starting position) and clears moves.txt --
                    # STARTING_FEN + [] mirrors that exactly, never fen.txt.
                    seen, board, move_list = [], build(STARTING_FEN, []), []
                    del particles[:]
                elif cmd[0] == 'size' and len(cmd) > 1:
                    set_size(cmd[1].strip())
                elif cmd[0] == 'banner':
                    BANNER.write_text(cmd[1] if len(cmd) > 1 else '')
                elif cmd[0] == 'names' and len(cmd) > 1:
                    parts = cmd[1].split()
                    if len(parts) == 2:
                        names['r'], names['b'] = parts[0].upper(), parts[1].upper()
                        (D / 'names.txt').write_text(f'{names["r"]} {names["b"]}')
        action = poll_input()
        if action == 'replay':      # same path as a ctl `replay` command, full replay
            board, action2 = do_replay(None)
            if action2 == 'quit':
                return board
            seen = read(MOVES).split()
            move_list = list(seen)
        elif action == 'quit':
            return board
        mv = read(MOVES).split()
        if mv[:len(seen)] != seen:
            seen, board, move_list = [], build(STARTING_FEN, []), []
            del particles[:]
        if len(mv) - len(seen) > 3:
            seen, board, move_list = list(mv), build(STARTING_FEN, mv), list(mv)
            render(board)
            time.sleep(0.05)
            continue
        while len(seen) < len(mv):
            iccs = mv[len(seen)]
            try:
                animate_move(board, iccs)
            except IllegalMove:
                seen, board, move_list = list(mv), build(STARTING_FEN, mv), list(mv)
                break
            seen.append(iccs)
        render(board)
        time.sleep(0.05)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.stdout.write('\x1b[0m\x1b[?25h\n')
    except Exception as e:
        sys.stdout.write(f'\x1b[0m\x1b[?25h\nXIANGQI CRASH: {e}\n')
        raise

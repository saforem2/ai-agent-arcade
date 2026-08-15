"""Chess arcade — TOTAL DOT FIELD. Everything is dots; pieces are disturbances.

Not a port of the tile board. The organising idea is that **a braille cell IS a
2x4 ordered-dither cell**, so the halftone lands on exact dot positions with zero
spatial noise. Everything else follows from that.

THE FIELD IS THE MATERIAL. There is no board drawn on a background — the dither
runs edge to edge and the board exists as a DENSITY structure inside it:

  ambient     1 dot/cell, dim  — the world outside the board
  light sq    3 dots/cell      | the checkerboard is a DENSITY difference, not a
  dark sq     1 dot/cell       | colour one. The 2-dot gap is preserved at every
                               | influence level, so the grid can never dissolve
                               | into a blob however hot the pressure gets.
  influence   adds 0..4 dots on top, and only THEN tints
  temperature the base field is NEUTRAL slate; ICE/EMBER saturation is capped at
              0.75 and scales with pressure, so a hot region reads as DEVIATION
              from a cool ambient rather than as wallpaper.

PIECES ARE DISTURBANCES IN THE FIELD, not marks on top of it:
  White       NEGATIVE SPACE — a piece-shaped hole punched clean through the
              field, identified by a pip cluster floating inside the void
  Black       SOLID MASS — saturated ember dots
  both        get a 1-dot keep-out ring, so an edge never shreds against the
              dither. Emit / absorb, the same duality as the classic pedestals.

DATA MANIFESTED
  influence   dither DENSITY = magnitude, HUE = whose
  wave        a density wave travelling the long diagonal (dither phase, not tint)
  material    filled dot-columns from a shared baseline, 8 levels, whole game
  cadence     move-clock dots; thinking time fills the attract meter

TRACES
  wake        particles stream off a moving piece and decay
  debris      a capture disintegrates the victim into particles with velocity
  ghost       the last move's two squares render as DOT-INVERTED dither

INDICATORS
  turn        the side to move owns the lit chevron
  check       king cell inverts and blinks; a dotted ring expands from it
  mate        the king TOPPLES, the board dissolves to noise, then re-crystallises

MODES (separated by time, not by layer)
  PLAY        glyph pieces over the dot field — glyphs own identity, dots own field
  ATTRACT     after idle, glyphs DISSOLVE into dot sprites and the position drifts
              as particle choreography; a live move RE-CRYSTALLISES it to glyphs

Same contract as tui.py: watches /tmp/chess/{moves,banner,ctl,names}.txt
ctl: replay [n] | reset | banner <text> | names <w> <b> | mode dots|glyph
     | size cozy|grand

When stdin is a tty, a `[ ▶ replay ]` button lives on the status row: click it
(SGR mouse) or press `r` for a full replay (same path as a ctl `replay`
command), or `q` to quit cleanly. Purely additive -- headless/file-driven use
(stdin not a tty) never touches termios and renders exactly as before.
"""
import math, os, random, re, select, shutil, sys, time
from pathlib import Path
import chess

try:
    import termios, tty
except ImportError:          # non-POSIX: input feature quietly disables itself
    termios = tty = None

D = Path(os.environ.get('ARCADE_LIVE', '/tmp/chess'))
MOVES, BANNER, CTL = D / 'moves.txt', D / 'banner.txt', D / 'ctl'

# Geometry is chosen to fit the pane: bigger pane -> more dots per square, so the
# same artwork gains resolution instead of just more margin. Candidates are in
# descending size; each is (chars across a square, char rows down a square).
# Largest first. (6,3) = 12x12 dots/square is the CAP, not just the biggest entry:
# it is where the 10x12 masters map 1:1 into the sprite box, so the art is at its
# crispest. A bigger square would only resample the same masters up and go soft, so
# surplus pane space becomes quiet margin instead (the board stays the object).
GEOM = ((6, 3), (5, 3), (4, 2), (3, 2))
# cozy caps the same descending list at (4, 2) = 8x8 dots/square, so the board
# never grows past the small tabletop tier however roomy the pane is.
GEOM_COZY = ((4, 2), (3, 2))
CW, CH = 4, 2                 # character cells per square (set by fit_geometry)
SQW, SQH = CW * 2, CH * 4     # dots per square
BW, BH = CW * 8, CH * 8       # board size in cells
DOTW, DOTH = BW * 2, BH * 4   # dot canvas

def fit_geometry(cols, rows):
    """Pick the largest square size the pane can hold, then rebuild the derived
    geometry. Sprites are resampled to match, so the board scales as one piece."""
    global CW, CH, SQW, SQH, BW, BH, DOTW, DOTH
    geom = GEOM_COZY if SIZE == 'cozy' else GEOM
    for cw, ch in geom:
        if cw * 8 + 5 <= cols and ch * 8 + 3 <= rows:
            break
    else:
        cw, ch = geom[-1]
    if (cw, ch) == (CW, CH):
        return False
    CW, CH = cw, ch
    SQW, SQH = CW * 2, CH * 4
    BW, BH = CW * 8, CH * 8
    DOTW, DOTH = BW * 2, BH * 4
    _shape_cache.clear()
    return True
# Ordered dither on the exact braille dot grid: index [dy][dx], dy 0..3, dx 0..1.
BAYER = ((0, 4), (6, 2), (1, 5), (7, 3))
BITS = ((0x01, 0x02, 0x04, 0x40), (0x08, 0x10, 0x20, 0x80))  # BITS[dx][dy]
FULL = 0xFF

PANEL = (18, 21, 28)
SQL, SQD = (34, 39, 50), (26, 30, 39)   # cell backgrounds stay near-flat now:
                                        # the checkerboard is carried by density
NEUTRAL = (104, 116, 138)               # ambient field colour — cool, quiet
AMBIENT = (52, 58, 72)                  # the world outside the board
ICE, EMBER = (125, 212, 236), (240, 162, 74)
MASS = (255, 176, 62)                   # Black's solid dot mass
PIP = (150, 170, 200)                   # White's marker pips inside the void
W_SOLID = (240, 249, 255)               # White's mass — equal weight to Black's, opposite pole
RIM = (206, 226, 248)                   # outline used when White is drawn hollow
DENS_L, DENS_D, DENS_AMB = 4, 2, 1      # base dots/cell: light sq, dark sq, ambient
DENS_QUIET = 1                          # density under a piece: the sprite carries the square
SAT_CAP = 0.75
W_GLYPH, B_GLYPH = (240, 249, 255), (255, 190, 88)
WAKE_W, WAKE_B = (170, 226, 245), (250, 196, 130)
DEBRIS = (255, 178, 96)
CHECKC = (242, 84, 94)
TEXT, TDIM, LABEL = (204, 212, 228), (118, 128, 148), (92, 102, 122)
SLATE, FOOT = (136, 145, 164), (86, 94, 110)
GLYPH = {'P': '♟', 'N': '♞', 'B': '♝', 'R': '♜', 'Q': '♛', 'K': '♚'}
ORTH = ((1, 0), (-1, 0), (0, 1), (0, -1))
SUPPORT = (0.25, 0.62, 0.86, 1.0, 1.0)
VAL = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
SPARK_N, IDLE_AFTER, DISSOLVE = 20, 18.0, 0.9
# Ambient motion budget. The halftone is visually rich standing still, so the
# field only drifts — one slow pass every half minute at half the old amplitude.
# Event choreography (travel, capture bursts, check, mate, dissolve) is untouched:
# it now reads against a calm ground instead of competing with a busy one.
WAVE_PERIOD, WAVE_AMP = 30.0, 0.5

# 4x8 dot sprites for attract mode. Identity is carried by glyphs in play mode,
# so these only need to read as distinct silhouettes in motion.
SIL_LO = {  # the original braille sprites: 6 wide x 8 tall — small panes
    'P': ("......", "......", "..##..", ".####.", "..##..", ".####.", "######", "......"),
    'N': ("......", "..###.", ".#####", "##.###", "...###", "..####", ".#####", "......"),
    'B': ("..#...", ".###..", ".###..", "..#...", "..#...", ".####.", "######", "......"),
    'R': ("......", "#.##.#", "######", ".####.", ".####.", ".####.", "######", "......"),
    'Q': ("#.##.#", "######", ".####.", "..##..", "..##..", ".####.", "######", "......"),
    'K': ("..##..", "######", "..##..", ".####.", ".####.", "######", "......", "......"),
}

SIL_HI = {  # redrawn at 10x12 for the big board: real contours, not upscaled pixels.
            # rook gets crenellation teeth, bishop a mitre cleft, knight a muzzle and
            # neck, queen a five-point crown against the king's single cross.
    'P': ("..........", "...####...", "..######..", "..######..", "..######..",
          "...####...", "...####...", "..######..", ".########.", ".########.",
          "##########", ".........."),
    'R': ("##..##..##", "##..##..##", "##########", "##########", ".########.",
          "..######..", "..######..", "..######..", ".########.", "##########",
          "##########", ".........."),
    'B': ("....##....", "...####...", "..######..", "..##..##..", "..######..",
          "..######..", "...####...", "..######..", ".########.", ".########.",
          "##########", ".........."),
    'N': ("....####..", "...######.", "..#######.", ".##.#####.", "###..#####",
          "##...#####", ".....#####", "....######", "...#######", "..########",
          "##########", ".........."),
    'Q': ("#.#.##.#.#", "##########", ".########.", ".########.", "..######..",
          "..######..", "..######..", ".########.", ".########.", "##########",
          "##########", ".........."),
    'K': ("....##....", "....##....", ".########.", "....##....", "..######..",
          ".########.", ".########.", ".########.", ".########.", "##########",
          "##########", ".........."),
}
_shape_cache = {}

def shape(sym):
    """(silhouette dots, keep-out dots) in square-local 8x8 coords. The keep-out
    is the silhouette dilated by one dot — the moat that stops the field from
    shredding the edge."""
    hit = _shape_cache.get(sym)
    if hit:
        return hit
    tw, th = SQW - 2, SQH               # sprite box: inset one dot either side
    # a bigger square earns a genuinely more detailed drawing, not a scaled-up one
    master = SIL_HI[sym] if (tw >= 8 and th >= 10) else SIL_LO[sym]
    mh, mw = len(master), len(master[0])
    sil = set()
    for ty in range(th):                # nearest-neighbour resample of the master
        for tx in range(tw):
            if master[ty * mh // th][tx * mw // tw] == '#':
                sil.add((tx + 1, ty))
    ko = {(x + ox, y + oy) for (x, y) in sil for ox in (-1, 0, 1) for oy in (-1, 0, 1)
          if 0 <= x + ox < SQW and 0 <= y + oy < SQH}   # clamped: never bleeds
    edge = {(x, y) for (x, y) in sil
            if not all((x + ox, y + oy) in sil for ox, oy in ORTH)}
    _shape_cache[sym] = (sil, ko, edge)
    return _shape_cache[sym]

MODE = 'dots'          # 'dots' = pieces are dot matter; 'glyph' = pieces are glyphs
_m = D / 'mode.txt'
if _m.exists():
    _v = _m.read_text().strip()
    if _v in ('dots', 'glyph'):
        MODE = _v

SIZE = 'grand'         # 'grand' = current 12x12-capped board; 'cozy' = 8x8 tabletop
_s = D / 'size.txt'
if _s.exists():
    _v = _s.read_text().strip()
    if _v in ('cozy', 'grand'):
        SIZE = _v

NAMES = D / 'names.txt'
names = {'w': 'CODEX', 'b': 'KIMI'}
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

ctl_mtime = 0       # shared with replay_all so a long replay stays interruptible
particles = []      # [x, y, vx, vy, born, life, colour]
move_list = []
last_move_t = time.monotonic()
last_pair = ()      # (from_sq, to_sq) — rendered as inverted dither
topple_t = None
_fcache, _mat_key, _mat_hist = {}, None, [0]

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
    the old players forever; this was hit live in game 6 and patched
    operationally by killing and relaunching the pane. Missing, empty, or
    malformed content leaves `names` at its last known-good value; it never
    raises, so a bad write mid-match can't crash a running viewer."""
    parts = read_cached(NAMES).split()
    if len(parts) == 2:
        names['w'], names['b'] = parts[0].upper(), parts[1].upper()

def blend(a, b, t):
    t = max(0.0, min(1.0, t))
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))

def influence_field(board):
    f = {}
    for sq in chess.SQUARES:
        w = len(board.attackers(chess.WHITE, sq))
        b = len(board.attackers(chess.BLACK, sq))
        f[sq] = (w - b, w, b)
    return f

def _sign(e):
    net, w, _b = e
    return 1 if net > 0 else -1 if net < 0 else (0 if w else None)

def support(field, sq, f, r):
    s = _sign(field[sq])
    if s is None:
        return 0
    n = 0
    for df, dr in ORTH:
        nf, nr = f + df, r + dr
        if 0 <= nf < 8 and 0 <= nr < 8 and _sign(field[chess.square(nf, nr)]) == s:
            n += 1
    return n

def cell_bits(cx, cy, level):
    """Light dots whose Bayer threshold falls under `level` (a float). Because the
    matrix is indexed by the dot's own position, every cell dithers identically —
    the halftone is exact and never speckles."""
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
    """Cell buffer. Dots accumulate; higher priority wins the single fg colour
    each braille cell is allowed."""
    def __init__(self):
        self.b = [[0] * BW for _ in range(BH)]
        self.f = [[None] * BW for _ in range(BH)]
        self.p = [[-1] * BW for _ in range(BH)]
        self.ch = {}

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
        cx, cy = int(cx), int(cy)   # fly coords are floats mid-animation
        if 0 <= cx < BW and 0 <= cy < BH:
            self.ch[(cx, cy)] = (char, col)
            self.b[cy][cx] = 0          # a glyph owns its cell outright

def spawn_wake(x, y, col):
    particles.append([x, y, random.uniform(-6, 6), random.uniform(-4, 2),
                      time.monotonic(), 0.5, col])

def spawn_debris(sq, n=30):
    x0 = chess.square_file(sq) * SQW + SQW // 2
    y0 = (7 - chess.square_rank(sq)) * SQH + SQH // 2
    now = time.monotonic()
    for _ in range(n):
        a = random.uniform(0, 2 * math.pi)
        s = random.uniform(8, 30)
        particles.append([x0, y0, math.cos(a) * s, math.sin(a) * s * 0.55,
                          now, random.uniform(0.4, 0.85), DEBRIS])

def draw_particles(g, t):
    live = []
    for p in particles:
        age = t - p[4]
        if age >= p[5]:
            continue
        live.append(p)
        k = 1 - age / p[5]
        g.dot(p[0] + p[2] * age, p[1] + p[3] * age + 18 * age * age,
              blend(PANEL, p[6], k), 3)
    particles[:] = live

def material(b):
    return sum(VAL[p.piece_type] if p.color else -VAL[p.piece_type] for p in b.piece_map().values())

def material_history(mv):
    global _mat_key, _mat_hist
    key = tuple(mv)
    if key == _mat_key:
        return _mat_hist
    b, hist = chess.Board(), [0]
    for san in mv:
        try:
            b.push_san(san)
        except ValueError:
            break
        hist.append(material(b))
    _mat_key, _mat_hist = key, hist
    return hist

def _downsample(hist, n):
    if len(hist) <= n:
        return [0] * (n - len(hist)) + list(hist)
    mean = sum(hist) / len(hist)
    out = []
    for i in range(n):
        a, b = int(i * len(hist) / n), int((i + 1) * len(hist) / n)
        out.append(max(hist[a:b] or hist[a:a + 1], key=lambda v: abs(v - mean)))
    return out

def spark_rows(hist):
    """Material as dot columns filled from a shared baseline — a bar chart whose
    bars happen to be made of dots. 8 levels across two cell rows."""
    s = _downsample(hist, SPARK_N)
    lo, hi = min(min(s), 0), max(max(s), 0)
    if hi - lo < 2:
        mid = (hi + lo) / 2.0
        lo, hi = mid - 1.0, mid + 1.0
    top, bot = '', ''
    for i in range(0, len(s), 2):
        tb = bb = 0
        for dx, v in enumerate(s[i:i + 2]):
            h = max(1, min(8, int(round((v - lo) / (hi - lo) * 7)) + 1))
            for k in range(h):                    # fill upward from the baseline
                if k < 4:
                    bb |= BITS[dx][3 - k]
                else:
                    tb |= BITS[dx][3 - (k - 4)]
        top += chr(0x2800 + tb)
        bot += chr(0x2800 + bb)
    return top, bot

def build(sans):
    b = chess.Board()
    for s in sans:
        b.push_san(s)
    return b

def render(board, fly=None, status_extra=''):
    global _btn_bounds
    t = time.monotonic()
    refresh_names()
    cols, rows = shutil.get_terminal_size((46, 28))
    if cols < 29 or rows < 19:
        _btn_bounds = None    # pane too small to draw it -- stale bounds must not fire
        sys.stdout.write('\x1b[H' + bg(PANEL) + fg(TEXT) + ' dot board needs 29x19 '
                         + '\x1b[K' + R + '\x1b[J')
        sys.stdout.flush()
        return
    if fit_geometry(cols, rows):
        sys.stdout.write('\x1b[2J')     # geometry changed: repaint from clean
    boardw = BW + 5
    LP = ' ' * max(0, (cols - boardw) // 2)
    # The side panels now carry move history, material and match state, so the
    # board sheds them and keeps only what belongs to the artwork: the position,
    # the coordinates, and whose turn it is.
    show_head, show_spark, show_tick, show_ban = True, False, False, False
    def budget():
        return BH + 2 + show_head + 2 * show_spark + show_tick + show_ban
    for drop in ('spark', 'tick', 'ban', 'head'):
        if budget() <= rows:
            break
        if drop == 'spark':
            show_spark = False
        elif drop == 'tick':
            show_tick = False
        elif drop == 'ban':
            show_ban = False
        else:
            show_head = False
    def line(s):
        return bg(PANEL) + LP + s + bg(PANEL) + '\x1b[K' + R + '\n'

    idle = 0.0
    if not board.is_game_over():
        gap = t - last_move_t - IDLE_AFTER
        if gap > 0:
            idle = min(1.0, gap / DISSOLVE)      # 0 = glyphs, 1 = fully dissolved
    over = board.is_game_over()
    mate = over and board.is_checkmate()
    check_sq = board.king(board.turn) if (board.is_check() and not over) else None
    field = influence_field(board)
    g = Grid()

    # ---- the field: runs edge to edge; the board is a density structure in it ----
    for cy in range(-1, BH + 1):        # a ring of ambient dither around the board
        for cx in range(-1, BW + 1):
            if 0 <= cx < BW and 0 <= cy < BH:
                continue
            g.cell(cx, cy, cell_bits(cx, cy, DENS_AMB), AMBIENT, -1)
    # A piece must never flicker. Its own square stops breathing entirely and drops
    # to minimum density (the sprite is the statement there); the ring around it
    # breathes at a third amplitude, so a piece sits in a calm pocket rather than
    # against a pulsing edge. Attract mode is exempt — dissolving is its point.
    occupied = board.piece_map()
    near = set()
    for osq in occupied:
        f0, r0 = chess.square_file(osq), chess.square_rank(osq)
        for df in (-1, 0, 1):
            for dr in (-1, 0, 1):
                if 0 <= f0 + df < 8 and 0 <= r0 + dr < 8:
                    near.add(chess.square(f0 + df, r0 + dr))
    for sq in chess.SQUARES:
        f, r = chess.square_file(sq), chess.square_rank(sq)
        net, w, b = field[sq]
        sgn = _sign(field[sq])
        base = DENS_L if (f + r) % 2 else DENS_D
        if sq in occupied:
            base = DENS_QUIET        # dark ground under a solid sprite
        sup = SUPPORT[support(field, sq, f, r)] if sgn is not None else 0.0
        wave = math.sin(2 * math.pi * t / WAVE_PERIOD + 2 * math.pi * (f + r) / 14.0)
        mag = 0 if sgn is None else (2.0 if sgn == 0 else min(4, abs(net)))
        wavef = 1.0 if idle else (0.0 if sq in occupied else 0.35 if sq in near else 1.0)
        add = mag * sup + WAVE_AMP * wave * wavef
        sat = 0.0 if sgn is None else min(SAT_CAP, 0.20 * mag * sup)
        inv = sq in last_pair
        for j in range(CH):
            for i in range(CW):
                cx, cy = f * CW + i, (7 - r) * CH + j
                if sgn == 0:
                    # contested: interleave the temperatures cell by cell; the eye
                    # mixes them optically, so no third hue has to exist
                    hue = blend(NEUTRAL, ICE if (cx + cy) % 2 == 0 else EMBER, sat)
                elif sgn is None:
                    hue = NEUTRAL
                else:
                    hue = blend(NEUTRAL, ICE if sgn > 0 else EMBER, sat)
                # density stays CONTINUOUS: the Bayer threshold is compared against a
                # float, so a gentle drift adds or drops one dot at a time instead of
                # stepping a whole level. Rounding here is what made a small-amplitude
                # wave either invisible or a jump.
                lvl = max(0.0, min(7.0, base + add))
                if sq in occupied:
                    lvl = min(lvl, 2.0)   # the moat leaves a few edge dots; keep them dark
                bits = cell_bits(cx, cy, lvl)
                if inv:                              # last move reads as a negative
                    bits ^= FULL
                    hue = blend(hue, (255, 255, 255), 0.5)
                g.cell(cx, cy, bits, hue, 0)

    # ---- pieces: disturbances in the field, not marks upon it ----
    hidden = fly[3] if fly else None
    for sq, pc in board.piece_map().items():
        if sq == hidden:
            continue
        f, r = chess.square_file(sq), chess.square_rank(sq)
        draw_piece(g, pc, f * SQW, (7 - r) * SQH, idle, t,
                   checked=(sq == check_sq),
                   topple=(mate and sq == board.king(board.turn)))
    if fly:
        piece, fx, fy, _o = fly
        draw_piece(g, piece, fx, fy, idle, t)

    # ---- check ring: a dotted circle expanding out of the king ----
    if check_sq is not None:
        ph = (t % 1.4) / 1.4
        rad = 4 + ph * 26
        cxp = chess.square_file(check_sq) * SQW + SQW // 2
        cyp = (7 - chess.square_rank(check_sq)) * SQH + SQH // 2
        col = blend(PANEL, CHECKC, 1 - ph)
        for a in range(0, 360, 9):
            g.dot(cxp + rad * math.cos(math.radians(a)),
                  cyp + rad * 0.55 * math.sin(math.radians(a)), col, 2)
    draw_particles(g, t)

    # ---- compose ----
    out = ['\x1b[H\x1b[?25l']
    pad = max(0, min(2, (rows - budget()) // 2))
    for _ in range(pad):
        out.append(line(''))
    wl = board.turn == chess.WHITE and not over
    bl = board.turn == chess.BLACK and not over
    if show_head:
        out.append(line('  ' + fg(W_GLYPH if wl else blend(W_GLYPH, PANEL, 0.6))
                        + ('▸ ' if wl else '  ') + f'\x1b[1m{names["w"]}\x1b[22m' + R + bg(PANEL)
                        + fg(TDIM) + '  ' + fg(B_GLYPH if bl else blend(B_GLYPH, PANEL, 0.6))
                        + ('▸ ' if bl else '  ') + f'\x1b[1m{names["b"]}\x1b[22m'))
    if show_spark:
        hist = material_history(move_list)
        d = hist[-1] if hist else 0
        st, sb = spark_rows(hist)
        rc = TDIM if not d else blend(TDIM, ICE if d > 0 else EMBER, 0.5)
        out.append(line('   ' + fg(SLATE) + st))
        out.append(line('   ' + fg(SLATE) + sb + fg(rc) + (f' {d:+d}' if d else ' =')))
    for cy in range(BH):
        lab = f' {8 - cy // CH} ' if cy % CH == 0 else '   '
        row, pf, pb = fg(LABEL) + lab, None, None
        for cx in range(BW):
            f, r = cx // CW, 7 - (cy // CH)
            cbg = SQL if (f + r) % 2 else SQD
            gl = g.ch.get((cx, cy))
            col = gl[1] if gl else (g.f[cy][cx] or cbg)
            if col != pf:
                row += fg(col); pf = col
            if cbg != pb:
                row += bg(cbg); pb = cbg
            row += gl[0] if gl else chr(0x2800 + g.b[cy][cx])
        out.append(line(row + R + bg(PANEL)))
    out.append(line(fg(LABEL) + '   ' + ''.join(f'{c:^{CW}}' for c in 'abcdefgh')))
    if show_tick:
        mv = move_list
        pairs = [f'{i//2+1}.{mv[i]} {mv[i+1] if i+1 < len(mv) else ""}' for i in range(0, len(mv), 2)]
        out.append(line('   ' + fg(TDIM) + '  '.join(pairs[-3:])[:boardw - 4]))
    if over:
        res = board.result()
        win = names['w'] if res == '1-0' else names['b'] if res == '0-1' else 'NOBODY'
        c = W_GLYPH if res == '1-0' else B_GLYPH if res == '0-1' else SLATE
        status_colored = f'\x1b[1m{fg(c)}{res}  {win} WINS{R}{bg(PANEL)}'
        status_plain_len = len(f'{res}  {win} WINS')
    else:
        side = names['w'] if board.turn else names['b']
        chk_plain = '  CHECK' if board.is_check() else ''
        chk = f'  {fg(CHECKC)}CHECK' if board.is_check() else ''
        ex, ex_plain = status_extra, status_extra
        if idle > 0 and not ex:
            ex_plain = '  dissolving…'
            ex = '  ' + fg(blend(PANEL, SLATE, 0.4 + 0.5 * idle)) + 'dissolving…'
        status_colored = f'{fg(TEXT)}{side} to move{chk}{fg(TDIM)}{ex}'
        status_plain_len = len(f'{side} to move{chk_plain}{ex_plain}')
    if INPUT_ENABLED:
        # Anchored right after the status text, not the board edge -- its
        # column shifts with the status text's own length, which is why we
        # track plain (escape-free) length alongside the coloured string.
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
        out.append(line(f'   {fg(FOOT)}{ban[:boardw - 4]}' if ban else ''))
    out.append(bg(PANEL) + '\x1b[J' + R)
    sys.stdout.write(''.join(out))
    sys.stdout.flush()

def draw_piece(g, pc, x0, y0, idle, t, checked=False, topple=False):
    """Both sides are SOLID dot sprites — the same braille figures, filled right
    out, told apart by colour alone: saturated ember vs pure bright white.

    Every sprite clears a keep-out moat first, so it always sits on dark ground
    however dense the local field is. That moat is what keeps the cool side from
    dissolving into a bright patch of dither — the contrast fix lives here, not
    in the piece colour."""
    sym = pc.symbol().upper()
    sil, ko, edge = shape(sym)
    heal = idle

    def place(dx, dy):
        return (x0 + 1 + dy, y0 + SQH - 2 - dx) if topple else (x0 + dx, y0 + dy)

    if heal < 1.0:
        for (dx, dy) in ko:      # the moat: field never welds to a silhouette
            g.clear(*place(dx, dy))

    if MODE == 'glyph' and heal < 0.5 and not topple:
        col = W_GLYPH if pc.color else B_GLYPH
        if checked:
            col = blend(col, CHECKC, 0.5 + 0.5 * math.sin(2 * math.pi * t / 0.7))
        g.glyph(x0 // 2 + CW // 2, y0 // 4, GLYPH[sym], col)
        return

    col = W_SOLID if pc.color else MASS
    if checked:
        col = blend(col, CHECKC, 0.5 + 0.5 * math.sin(2 * math.pi * t / 0.7))
    for (dx, dy) in sil:              # solid figure, filled right out
        g.dot(*place(dx, dy), col, 2)

def animate(board, move, interruptible=False):
    """Animate one move. When `interruptible` (replay only -- a live single
    move never needs this), poll_input() is checked every frame of both the
    travel and settle loops, not just between moves, so a click/keypress
    lands the instant it happens instead of queueing behind up to ~1s of
    uninterruptible animation. The move is still applied to `board` either
    way -- only the animation is cut short, state always keeps moving
    forward. Returns 'quit'/'replay' if an interrupt fired, else None."""
    global last_move_t, last_pair
    last_move_t = time.monotonic()
    piece = board.piece_at(move.from_square)
    if piece is None:
        board.push(move)
        return None
    wake = WAKE_W if piece.color else WAKE_B
    x0, y0 = chess.square_file(move.from_square) * SQW, (7 - chess.square_rank(move.from_square)) * SQH
    x1, y1 = chess.square_file(move.to_square) * SQW, (7 - chess.square_rank(move.to_square)) * SQH
    is_cap = board.is_capture(move)
    victim = move.to_square
    if board.is_en_passant(move):
        victim = chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square))
    if is_cap:
        spawn_debris(victim)
    action = None
    t0, dur = time.monotonic(), 0.5
    while True:
        if interruptible:
            action = poll_input()
            if action:
                break
        el = (time.monotonic() - t0) / dur
        if el >= 1:
            break
        e = el * el * (3 - 2 * el)
        x, y = x0 + (x1 - x0) * e, y0 + (y1 - y0) * e
        for _ in range(2):
            spawn_wake(x + SQW / 2 + random.uniform(-2, 2), y + SQH / 2 + random.uniform(-2, 2), wake)
        render(board, fly=(piece, x, y, move.from_square))
        time.sleep(0.033)
    board.push(move)
    last_pair = (move.from_square, move.to_square)
    last_move_t = time.monotonic()
    if action is None:
        end = time.monotonic() + (0.5 if is_cap else 0.08)
        while time.monotonic() < end:
            if interruptible:
                action = poll_input()
                if action:
                    break
            render(board)
            time.sleep(0.033)
    return action

def ctl_changed():
    try:
        return CTL.exists() and CTL.stat().st_mtime_ns > ctl_mtime
    except OSError:
        return False

def replay_all(sans, tail=None):
    """Returns (board, action): action is None on a normal or ctl-abandoned
    finish, or 'quit'/'replay' if a live input event interrupted an
    animate() call mid-flight -- the caller (do_replay) decides what to do
    with that; this function's own job is just to stop immediately and
    report it, exactly like it already does for a ctl file change."""
    global move_list
    skip = sans[:-tail] if tail and tail < len(sans) else []
    b = build(skip)
    del particles[:]
    move_list = list(skip)
    render(b, status_extra='  replay')
    time.sleep(0.7)
    for s in sans[len(skip):]:
        if ctl_changed():      # abandon the replay so the new command lands now
            return build(sans), None
        action = animate(b, b.parse_san(s), interruptible=True)
        move_list = move_list + [s]
        if action:             # 'quit' or 'replay' fired mid-animation
            return build(sans), action
        time.sleep(0.2)
    move_list = list(sans)
    return b, None

def do_replay(tail=None):
    """Run replay_all, immediately restarting from scratch if a live
    'replay' click/keypress interrupted it mid-flight -- a click during a
    replay should feel like "start over," not "silently dropped" (the old
    behaviour: the input was never even polled for during animation, so it
    just sat unconsumed until the replay finished on its own). Bounded loop,
    not recursion -- only continues on repeated 'replay' hits. Returns
    (board, action) where action is 'quit' if the caller should exit."""
    while True:
        board, action = replay_all(read(MOVES).split(), tail)
        if action == 'quit':
            return board, 'quit'
        if action == 'replay':
            tail = None         # a restart always replays the whole game
            continue
        return board, None

def main():
    global move_list, last_pair, MODE, SIZE, ctl_mtime
    sys.stdout.write('\x1b[2J')
    seen = read(MOVES).split()
    move_list = list(seen)
    board = build(seen)
    ctl_mtime = CTL.stat().st_mtime_ns if CTL.exists() else 0
    enable_input()
    try:
        board = _main_loop(board, seen)
    finally:
        disable_input()

def _main_loop(board, seen):
    global move_list, last_pair, MODE, SIZE, ctl_mtime
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
                    seen, board, move_list, last_pair = [], chess.Board(), [], ()
                    del particles[:]
                elif cmd[0] == 'mode' and len(cmd) > 1:
                    v = cmd[1].strip()
                    if v in ('dots', 'glyph'):
                        MODE = v
                        (D / 'mode.txt').write_text(v)
                elif cmd[0] == 'size' and len(cmd) > 1:
                    v = cmd[1].strip()
                    if v in ('cozy', 'grand') and v != SIZE:
                        SIZE = v
                        (D / 'size.txt').write_text(v)
                        del particles[:]   # old-geometry coords would render stale/mis-scaled
                elif cmd[0] == 'banner':
                    BANNER.write_text(cmd[1] if len(cmd) > 1 else '')
                elif cmd[0] == 'names' and len(cmd) > 1:
                    parts = cmd[1].split()
                    if len(parts) == 2:
                        names['w'], names['b'] = parts[0].upper(), parts[1].upper()
                        (D / 'names.txt').write_text(f'{names["w"]} {names["b"]}')
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
            seen, board, move_list, last_pair = [], chess.Board(), [], ()
            del particles[:]
        if len(mv) - len(seen) > 3:  # never grind through history: snap to live
            seen, board, move_list = list(mv), build(mv), list(mv)
            render(board)
            time.sleep(0.05)
            continue
        while len(seen) < len(mv):
            san = mv[len(seen)]
            try:
                m = board.parse_san(san)
            except ValueError:
                seen, board, move_list = list(mv), build(mv), list(mv)
                break
            animate(board, m)
            seen.append(san)
            move_list = list(seen)
        render(board)
        time.sleep(0.05)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.stdout.write('\x1b[0m\x1b[?25h\n')
    except Exception as e:
        sys.stdout.write(f'\x1b[0m\x1b[?25h\nDOTS CRASH: {e}\n')
        raise

"""Chess arcade board v7 — synthesis of Opus + Kimi design specs.

Board-as-lit-object: whole pane painted, no lattice, 4x2 cells, pedestal
squares centred under pieces, net-pressure influence field (ice vs ember,
orchid shimmer when contested), one traveling wave, sub-cell gradient edges,
wall-clock animation, attract-mode sweep when idle, mate cinematic,
material sparkline, state beacon on the frame.
ctl: replay [n] | reset | banner <text> | names <w> <b>
"""
import math, os, shutil, sys, time
from pathlib import Path
import chess

D = Path(os.environ.get('ARCADE_LIVE', '/tmp/chess'))
MOVES, BANNER, CTL = D / 'moves.txt', D / 'banner.txt', D / 'ctl'

GLYPH = {'P': '♟', 'N': '♞', 'B': '♝', 'R': '♜', 'Q': '♛', 'K': '♚'}
PANEL, MATTE = (26, 30, 40), (18, 21, 29)
SQL, SQD = (48, 55, 70), (39, 45, 58)
ICE, EMBER, ORCHID = (120, 210, 235), (240, 160, 70), (205, 130, 235)
PEDW, PEDB = (10, 14, 22), (222, 228, 240)
GW, GB = (236, 246, 255), (22, 24, 34)
CHIP_W, CHIP_B = (44, 51, 66), (149, 155, 168)  # header chips speak the pedestal language
CHECK, CAPTURE, SHOCK = (214, 54, 62), (255, 138, 42), (255, 190, 120)
SWEEP = (200, 216, 238)
HILITE = (232, 238, 250)  # last move wins on luminance; hue belongs to the field alone
TEXT, TDIM, LABEL = (208, 216, 232), (122, 132, 152), (98, 108, 128)
SLATE, FOOT = (138, 147, 166), (90, 98, 114)  # instrumentation, not alarm
BANC, WINC = (150, 200, 255), (255, 210, 120)
ALPHA = {1: 0.20, 2: 0.27, 3: 0.32, 4: 0.36}
ORTH = ((1, 0), (-1, 0), (0, 1), (0, -1))
SUPPORT = (0.22, 0.60, 0.85, 1.0, 1.0)  # by count of same-sign orthogonal neighbours
RINGS = ((0.000, 0.60), (0.075, 0.38), (0.150, 0.22))  # (onset, amplitude) by cheb dist
VAL = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
BARS = ' ▁▂▃▄▅▆▇█'  # index 1..8; solid bars read as one series, braille dots did not
SPARK_N = 20
IDLE_AFTER = 20.0
MIN_COLS, MIN_ROWS = 38, 21

names = {'w': 'CODEX', 'b': 'KIMI'}
_n = (D / 'names.txt')
if _n.exists():
    _p = _n.read_text().split()
    if len(_p) == 2:
        names['w'], names['b'] = _p[0].upper(), _p[1].upper()
hl_from = hl_to = None
hl_hue = ICE
captures = []   # (t, square)
trails = {}     # square -> (t, hue)
last_move_t = time.monotonic()
over_t = None
move_list = []
replaying = False
belled_over = False
_fcache = {}
_mat_key, _mat_hist = None, [0]

def bg(c): return f'\x1b[48;2;{c[0]};{c[1]};{c[2]}m'
def fg(c): return f'\x1b[38;2;{c[0]};{c[1]};{c[2]}m'
R = '\x1b[0m'

def read(p, default=''):
    try: return p.read_text().strip()
    except OSError: return default

def read_cached(p):
    """Re-read only when mtime moves; render runs at ~25fps."""
    try:
        st = p.stat().st_mtime_ns
    except OSError:
        return ''
    hit = _fcache.get(p)
    if hit and hit[0] == st:
        return hit[1]
    val = read(p)
    _fcache[p] = (st, val)
    return val

def blend(a, b, t):
    t = max(0.0, min(1.0, t))
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))

def gray(c, t):
    l = int(0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2])
    return blend(c, (l, l, l), t)

def cheb(a, b):
    return max(abs(chess.square_file(a) - chess.square_file(b)), abs(chess.square_rank(a) - chess.square_rank(b)))

def bell():
    if not replaying:
        sys.stdout.write('\a')

def clear_fx():
    trails.clear()
    del captures[:]

def material(b):
    d = 0
    for pc in b.piece_map().values():
        d += VAL[pc.piece_type] if pc.color else -VAL[pc.piece_type]
    return d

def material_history(mv):
    """Material diff after each ply. Recomputed only when the move list changes."""
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
    """Fit the whole game into n slots, keeping the biggest swing in each bucket
    so early spikes survive compression instead of being averaged flat."""
    if len(hist) <= n:
        return [0] * (n - len(hist)) + list(hist)
    mean = sum(hist) / len(hist)
    out = []
    for i in range(n):
        a, b = int(i * len(hist) / n), int((i + 1) * len(hist) / n)
        chunk = hist[a:b] or hist[a:a + 1]
        out.append(max(chunk, key=lambda v: abs(v - mean)))
    return out

def sparkline(hist, g):
    """Material trace as solid bottom-anchored bars over the whole game. Bars share
    one baseline so it reads as a single series; colour marks who leads. y is
    auto-scaled to the window but always spans zero, so the colour flip is the
    zero crossing. Every bar is at least '▁' — the ribbon never breaks."""
    s = _downsample(hist, SPARK_N)
    lo, hi = min(min(s), 0), max(max(s), 0)  # anchor the scale on the zero line
    if hi - lo < 2:  # floor keeps a level game a flat ribbon, not noise
        mid = (hi + lo) / 2.0
        lo, hi = mid - 1.0, mid + 1.0
    out = ''
    col = fg(gray(SLATE, g))  # neutral: this is instrumentation, the board owns hue
    for v in s:
        h = max(1, min(8, int(round((v - lo) / (hi - lo) * 7)) + 1))
        out += col + BARS[h]
    return out

def influence_field(board):
    """Net pressure per square, computed once per frame instead of per cell."""
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
    """How many orthogonal neighbours share this square's allegiance. A lone
    tinted square is visual noise — a stain; a contiguous run is territory."""
    s = _sign(field[sq])
    if s is None:
        return 0
    n = 0
    for df, dr in ORTH:
        nf, nr = f + df, r + dr
        if 0 <= nf < 8 and 0 <= nr < 8 and _sign(field[chess.square(nf, nr)]) == s:
            n += 1
    return n

def chip(name, glyph, white, dim, g):
    """Name badge drawn as the side's own pedestal, so the header reads in the
    same colour language as the board rather than in the influence hues."""
    c = CHIP_W if white else CHIP_B
    txt = GW if white else GB
    if dim:  # side not to move recedes toward the panel
        c = blend(c, PANEL, 0.35)
        txt = blend(txt, c, 0.40)
    return f'{bg(gray(c, g))}{fg(gray(txt, g))}\x1b[1m {glyph} {name} \x1b[22m{R}'

def cell_color(board, sq, f, r, env, shown):
    """Returns (pedestal, gutter). A 4-col cell cannot centre a 1-col glyph, so
    the pedestal spans cols 1-3 with the glyph at col 2 — dead centre — and col 0
    stays un-pedestalled as a seam gutter. Empty squares get pedestal None."""
    t = env['t']
    plain = SQL if (f + r) % 2 else SQD
    ped = None
    if shown:
        ped = blend(plain, PEDW, 0.45) if shown.color else blend(plain, PEDB, 0.58)
    wv = math.sin(2 * math.pi * t / 6.0 + 2 * math.pi * (f + r) / 14.0)
    field = env['field']
    net, w, b = field[sq]
    hue, alpha = None, 0.0
    if net != 0:
        hue = ICE if net > 0 else EMBER
        alpha = ALPHA[min(4, abs(net))]
    elif w > 0:  # net == 0 implies w == b, so this is already symmetric
        hue = ORCHID
        alpha = ALPHA[min(3, w)] * 0.5 * (1 + 0.30 * math.sin(2 * math.pi * t / 1.8 + (f + r)))
    alpha *= 0.85 + 0.15 * wv
    alpha *= SUPPORT[support(field, sq, f, r)]  # dissolve isolated stains, keep territory
    if shown:
        alpha *= 0.45
    idle = env['idle']
    if idle:
        alpha *= 1 - 0.45 * idle

    def finish(base):
        base = blend(base, (255, 255, 255), 0.022 * (0.5 + 0.5 * wv))
        if hue and alpha > 0:
            base = blend(base, hue, min(0.38, alpha))
        if idle:  # attract mode: slow diagonal light band, position-independent
            d = (f + r) - env['sweep']
            base = blend(base, SWEEP, 0.14 * idle * math.exp(-(d * d) / 12.5))
        tr = trails.get(sq)
        if tr and t - tr[0] < 0.5:
            base = blend(base, tr[1], 0.38 * (1 - (t - tr[0]) / 0.5))
        if sq == hl_from:  # spotlight, not a hue claim — the field owns hue
            base = blend(base, HILITE, 0.15)
        if sq == hl_to:
            base = blend(base, HILITE, 0.34)
        for (et, esq) in captures:
            age = t - et
            if sq == esq:
                if age < 0.35:
                    base = blend(base, CAPTURE, 0.9 * (1 - age / 0.35))
            else:
                d = cheb(sq, esq)
                if 1 <= d <= 3:  # each ring gets its own clock so the wave travels
                    onset, amp = RINGS[d - 1]
                    a = age - onset
                    if 0 <= a < 0.24:
                        base = blend(base, SHOCK, amp * (1 - a / 0.24))
        if sq == env['check_sq']:
            ph = t % 1.13
            beat = 0.10  # low floor keeps the king's own influence tint alive
            for onset, amp in ((0.0, 0.90), (0.23, 0.65)):
                d = ph - onset
                if d >= 0:
                    beat = max(beat, amp * math.exp(-d / 0.11))
            base = blend(base, CHECK, beat)
        if env['gray']:
            base = gray(base, env['gray'])
        if env['over_hue']:  # wash lands after the desaturation, so colour returns
            base = blend(base, env['over_hue'], 0.18 * env['over_breathe'] * env['wash'])
        if env['ring'] is not None and env['focus'] is not None:
            d = cheb(sq, env['focus']) - env['ring']
            base = blend(base, (255, 255, 255), 0.75 * math.exp(-(d * d) / 2.4))
        return base

    return (finish(ped) if ped else None), finish(plain)

def render(board, fly=(), status_extra=''):
    global over_t, belled_over
    t = time.monotonic()
    cols, rows = shutil.get_terminal_size((69, 28))
    if cols < MIN_COLS or rows < MIN_ROWS:
        sys.stdout.write('\x1b[H' + bg(PANEL) + fg(TEXT)
                         + f' board needs {MIN_COLS}x{MIN_ROWS} ' + '\x1b[K' + R + '\x1b[J')
        sys.stdout.flush()
        return
    for show_spark, show_tick, show_banner in ((1, 1, 1), (1, 1, 0), (1, 0, 0), (0, 1, 1), (0, 1, 0), (0, 0, 0)):
        used = 21 + 3 * show_spark + show_tick + show_banner
        if used <= rows:
            break
    pad = max(0, min(2, (rows - used) // 2))
    LP = ' ' * ((cols - 38) // 2)
    hidden = {e[2] for e in fly}

    over = board.is_game_over()
    if over and over_t is None:
        over_t = t
    elif not over:
        over_t = None
        belled_over = False
    env = {'t': t, 'check_sq': None, 'over_hue': None, 'over_breathe': 1.0,
           'wash': 0.0, 'idle': 0.0, 'sweep': 0.0, 'gray': 0.0, 'ring': None,
           'focus': None, 'age': 0.0, 'field': influence_field(board)}
    if over:
        res = board.result()
        mate = board.is_checkmate()
        env['over_hue'] = ICE if res == '1-0' else EMBER if res == '0-1' else ORCHID
        env['over_breathe'] = 0.85 + 0.15 * math.sin(2 * math.pi * t / 3.0)
        age = env['age'] = t - over_t
        env['focus'] = board.king(board.turn) if mate else None
        peak = 1.0 if mate else 0.45  # a draw gets a quieter, partial desaturation
        env['gray'] = min(peak, age / 0.4 * peak) if age < 1.6 else max(0.0, peak * (1 - (age - 1.6) / 0.8))
        env['wash'] = min(1.0, max(0.0, (age - 1.2) / 1.0))
        if mate and 0.45 <= age < 1.0:
            env['ring'] = (age - 0.45) / 0.55 * 9.0
        if not belled_over:
            belled_over = True
            bell()
    else:
        if board.is_check():
            env['check_sq'] = board.king(board.turn)
        gap = t - last_move_t - IDLE_AFTER
        if gap > 0:
            env['idle'] = min(1.0, gap / 2.5)
            env['sweep'] = ((t / 4.0) % 1.0) * 30.0 - 8.0
    g = env['gray']
    G = (lambda c: gray(c, g)) if g else (lambda c: c)
    PB = G(PANEL)

    def line(parts):
        return bg(PB) + LP + parts + bg(PB) + '\x1b[K' + R + '\n'

    frame = MATTE  # state beacon: the board's own frame carries game state
    if over:
        frame = blend(G(MATTE), env['over_hue'], 0.30 + 0.22 * math.sin(2 * math.pi * t / 2.5))
    elif env['check_sq'] is not None:
        frame = blend(MATTE, CHECK, 0.18 + 0.28 * (0.5 + 0.5 * math.sin(2 * math.pi * t / 1.6)))

    out = ['\x1b[H\x1b[?25l']
    for _ in range(pad):
        out.append(line(''))
    turn = None if over else board.turn
    out.append(line('  ' + chip(names['w'], '♔', True, turn is not True, g)
                    + f'{bg(PB)} {fg(G(TDIM))}vs{R}{bg(PB)} '
                    + chip(names['b'], '♚', False, turn is not False, g)))
    if show_spark:
        hist = material_history(move_list)
        d = hist[-1] if hist else 0
        rc = TDIM if not d else blend(TDIM, ICE if d > 0 else EMBER, 0.45)
        out.append(line(''))
        out.append(line('  ' + fg(G(LABEL)) + 'material ' + sparkline(hist, g)
                        + fg(G(rc)) + (f' {d:+d}' if d else ' =')))
        out.append(line(''))
    W = 3 + 32 + 2
    out.append(line(' ' + bg(frame) + ' ' * W))
    for r in range(7, -1, -1):
        cells = []
        for f in range(8):
            sq = chess.square(f, r)
            piece = None
            for pos, fpc, _o in fly:
                if pos == (f, r):
                    piece = fpc
                    break
            if piece is None:
                pc = board.piece_at(sq)
                if pc and sq not in hidden:
                    piece = pc
            ped, gut = cell_color(board, sq, f, r, env, piece)
            cells.append((sq, ped, gut, piece))
        for sub in range(2):
            lab = f' {r+1} ' if sub == 0 else '   '
            row = ' ' + bg(frame) + fg(G(LABEL)) + lab
            for f in range(8):
                sq, ped, gut, piece = cells[f]
                body = ped or gut
                prev = cells[f - 1]
                edge = frame if f == 0 else (prev[1] or prev[2])
                row += bg(gut) + fg(blend(gut, edge, 0.45)) + '▏'
                if sub == 0 and piece:
                    gc = G(GW if piece.color else GB)
                    row += bg(body) + f' {fg(gc)}\x1b[1m{GLYPH[piece.symbol().upper()]}\x1b[22m '
                elif sub == 1 and env['focus'] == sq and env['age'] > 2.4:
                    st = blend(WINC, env['over_hue'], 0.5 + 0.5 * math.sin(2 * math.pi * t / 1.2))
                    row += bg(body) + f' {fg(st)}★ '
                else:
                    row += bg(body) + '   '
            row += bg(frame) + '  '
            out.append(line(row))
    out.append(line(' ' + bg(frame) + ' ' * W))
    out.append(line(' ' + bg(frame) + fg(G(LABEL)) + '    ' + ''.join(f' {c}  ' for c in 'abcdefgh') + ' '))
    if show_tick:
        mv = move_list
        pairs = [(i // 2 + 1, mv[i], mv[i + 1] if i + 1 < len(mv) else '') for i in range(0, len(mv), 2)]
        shade = [(72, 80, 98), (100, 110, 132), (146, 156, 178), TEXT]
        shown, wsum = [], 0
        for p in reversed(pairs[-4:]):
            w = len(f'{p[0]}.{p[1]} {p[2]}'.rstrip()) + 2
            if wsum + w > 36 and shown:
                break
            shown.insert(0, p)
            wsum += w
        tick = ''
        for j, (n, a, b2) in enumerate(shown):
            c = shade[len(shade) - len(shown) + j]
            tick += f'{fg(G(LABEL))}{n}.{fg(G(c))}{a} {b2}  '
        out.append(line('  ' + tick))
    if over:
        res = board.result()
        win = names['w'] if res == '1-0' else names['b'] if res == '0-1' else 'NOBODY'
        star = fg(blend(WINC, env['over_hue'], 0.5 + 0.5 * math.sin(2 * math.pi * t / 1.5)))
        out.append(line(f'  {star}★{R}{bg(PB)} \x1b[1m{fg(WINC)}{res} — {win} WINS{R}{bg(PB)} {star}★'))
    else:
        k = 0.5 + 0.5 * math.sin(2 * math.pi * t / 6.0)
        dot = fg(blend(TDIM, ICE if board.turn else EMBER, k))
        side = names['w'] if board.turn else names['b']
        chk = f' {fg((255, 120, 120))}CHECK!' if board.is_check() else ''
        extra = status_extra
        if env['idle'] > 0 and not extra:  # fades in with the attract sweep
            extra = '   ' + fg(blend(PB, SLATE, env['idle'] * (0.55 + 0.30 * k))) + 'thinking…'
        out.append(line(f'  {dot}◉{R}{bg(PB)} {fg(G(TEXT))}{side} to move{chk}{fg(G(TDIM))}{extra}'))
    if show_banner:
        ban = read_cached(BANNER)
        out.append(line(f'  {fg(G(FOOT))}{ban}' if ban else ''))
    out.append(bg(PB) + '\x1b[J' + R)
    sys.stdout.write(''.join(out))
    sys.stdout.flush()
    now = time.monotonic()
    for s in list(trails):
        if now - trails[s][0] > 0.6:
            del trails[s]
    captures[:] = [(et, sq) for (et, sq) in captures if now - et < 0.5]

def animate(board, move):
    global hl_from, hl_to, hl_hue, last_move_t
    last_move_t = time.monotonic()
    piece = board.piece_at(move.from_square)
    if piece is None:
        board.push(move)
        return
    hue = ICE if piece.color else EMBER
    ff, fr = chess.square_file(move.from_square), chess.square_rank(move.from_square)
    tf, tr = chess.square_file(move.to_square), chess.square_rank(move.to_square)
    is_cap = board.is_capture(move)
    victim = move.to_square
    if board.is_en_passant(move):  # the pawn dies beside the landing square
        victim = chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square))
    rook = None
    if board.is_castling(move):
        bk = chess.square_rank(move.from_square)
        rf, rt = (7, 5) if board.is_kingside_castling(move) else (0, 3)
        rook = (board.piece_at(chess.square(rf, bk)), chess.square(rf, bk), (rf, bk), (rt, bk))
    t0, dur = time.monotonic(), 0.45
    hl_from, hl_to, hl_hue = move.from_square, None, hue
    while True:
        el = (time.monotonic() - t0) / dur
        if el >= 1:
            break
        cf, cr = int(ff + (tf - ff) * el + 0.5), int(fr + (tr - fr) * el + 0.5)
        fly = [((cf, cr), piece, move.from_square)]
        if (cf, cr) not in ((ff, fr), (tf, tr)):
            trails[chess.square(cf, cr)] = (time.monotonic(), hue)
        if rook and rook[0]:
            rp, ro, (r0f, r0r), (r1f, r1r) = rook
            kf, kr = int(r0f + (r1f - r0f) * el + 0.5), int(r0r + (r1r - r0r) * el + 0.5)
            if (kf, kr) not in ((r0f, r0r), (r1f, r1r)):
                trails[chess.square(kf, kr)] = (time.monotonic(), hue)
            fly.append(((kf, kr), rp, ro))
        render(board, fly=fly)
        time.sleep(0.035)
    if is_cap:
        captures.append((time.monotonic(), victim))
    board.push(move)
    hl_from, hl_to = move.from_square, move.to_square
    last_move_t = time.monotonic()
    if board.is_check() and not board.is_game_over():
        bell()
    end = time.monotonic() + (0.4 if is_cap else 0.05)
    while time.monotonic() < end:
        render(board)
        time.sleep(0.04)

def replay_all(mv_sans, tail=None):
    global hl_from, hl_to, over_t, move_list, replaying, belled_over
    skip = mv_sans[:-tail] if tail and tail < len(mv_sans) else []
    b = build(skip)
    hl_from = hl_to = over_t = None
    belled_over = False
    clear_fx()
    replaying = True
    try:
        move_list = list(skip)
        render(b, status_extra='  replay')
        time.sleep(0.8)
        for san in mv_sans[len(skip):]:
            animate(b, b.parse_san(san))
            move_list = move_list + [san]
            time.sleep(0.25)
    finally:
        replaying = False
    move_list = list(mv_sans)
    return b

def build(mv_sans):
    b = chess.Board()
    for san in mv_sans:
        b.push_san(san)
    return b

def main():
    global hl_from, hl_to, over_t, move_list, belled_over
    sys.stdout.write('\x1b[2J')
    seen = read(MOVES).split()
    move_list = list(seen)
    board = build(seen)
    ctl_mtime = CTL.stat().st_mtime_ns if CTL.exists() else 0
    while True:
        if CTL.exists() and CTL.stat().st_mtime_ns > ctl_mtime:
            ctl_mtime = CTL.stat().st_mtime_ns
            cmd = read(CTL).split(None, 1)
            if cmd:
                if cmd[0] == 'replay':
                    tail = int(cmd[1]) if len(cmd) > 1 and cmd[1].strip().isdigit() else None
                    board = replay_all(read(MOVES).split(), tail)
                    seen = read(MOVES).split()
                    move_list = list(seen)
                elif cmd[0] == 'reset':
                    seen, board, hl_from, hl_to, over_t = [], chess.Board(), None, None, None
                    move_list, belled_over = [], False
                    clear_fx()
                elif cmd[0] == 'banner':
                    BANNER.write_text(cmd[1] if len(cmd) > 1 else '')
                elif cmd[0] == 'names' and len(cmd) > 1:
                    parts = cmd[1].split()
                    if len(parts) == 2:
                        names['w'], names['b'] = parts[0].upper(), parts[1].upper()
                        (D / 'names.txt').write_text(f'{names["w"]} {names["b"]}')
        mv = read(MOVES).split()
        if mv[:len(seen)] != seen:
            seen, board, hl_from, hl_to, over_t = [], chess.Board(), None, None, None
            move_list, belled_over = [], False
            clear_fx()
        if len(mv) - len(seen) > 3:  # never grind through history: snap to live
            seen, board, move_list = list(mv), build(mv), list(mv)
            clear_fx()
            render(board)
            time.sleep(0.05)
            continue
        while len(seen) < len(mv):
            san = mv[len(seen)]
            try:
                m = board.parse_san(san)
            except ValueError:
                seen, board = list(mv), build(mv)
                move_list = list(mv)
                clear_fx()
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
        sys.stdout.write(f'\x1b[0m\x1b[?25h\nBOARD CRASH: {e}\n')
        raise

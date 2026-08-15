"""Chess arcade side panels — the information the board sheds so it can be artwork.

Two panels, one file, chosen by argv:
    panel_tui.py moves   scrolling SAN history, newest first, hued by mover
    panel_tui.py info    players, series tally, material trace, ply clock

Same file bus as the boards: /tmp/chess/{moves,names,results}.txt
results.txt is one finished game per line, WHITE-PLAYER-FIRST:
    CODEX 1-0 KIMI      (white won)
    KIMI 0-1 CODEX      (black won)
    CODEX 1/2-1/2 KIMI  (draw)
The seats swap between games, so a bare "1-0" cannot say who actually won — the
tally is computed per NAME, not per colour.
"""
import math, os, shutil, sys, time
from pathlib import Path
import chess

D = Path(os.environ.get('ARCADE_LIVE', '/tmp/chess'))
MOVES, NAMES, RESULTS = D / 'moves.txt', D / 'names.txt', D / 'results.txt'

PANEL = (22, 25, 33)
ICE, EMBER = (125, 212, 236), (240, 162, 74)
W_GLYPH, B_GLYPH = (240, 249, 255), (255, 190, 88)
TEXT, TDIM, LABEL = (204, 212, 228), (118, 128, 148), (92, 102, 122)
SLATE, RULE = (136, 145, 164), (44, 50, 63)
BITS = ((0x01, 0x02, 0x04, 0x40), (0x08, 0x10, 0x20, 0x80))
VAL = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}

def bg(c): return f'\x1b[48;2;{c[0]};{c[1]};{c[2]}m'
def fg(c): return f'\x1b[38;2;{c[0]};{c[1]};{c[2]}m'
R = '\x1b[0m'

def read(p):
    try: return p.read_text().strip()
    except OSError: return ''

def blend(a, b, t):
    t = max(0.0, min(1.0, t))
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))

def names():
    p = read(NAMES).split()
    return (p[0].upper(), p[1].upper()) if len(p) == 2 else ('CODEX', 'KIMI')

def board_from(mv):
    b = chess.Board()
    for s in mv:
        try: b.push_san(s)
        except ValueError: break
    return b

def material(b):
    return sum(VAL[p.piece_type] if p.color else -VAL[p.piece_type] for p in b.piece_map().values())

def mat_history(mv):
    b, h = chess.Board(), [0]
    for s in mv:
        try: b.push_san(s)
        except ValueError: break
        h.append(material(b))
    return h

def spark(hist, n):
    """Material as filled dot columns from a shared baseline — same language as
    the board, so the panels read as part of the same instrument."""
    s = hist[-n * 2:] or [0]
    s = [0] * (n * 2 - len(s)) + s
    lo, hi = min(min(s), 0), max(max(s), 0)
    if hi - lo < 2:
        mid = (hi + lo) / 2.0
        lo, hi = mid - 1.0, mid + 1.0
    top, bot = '', ''
    for i in range(0, len(s), 2):
        tb = bb = 0
        for dx, v in enumerate(s[i:i + 2]):
            h = max(1, min(8, int(round((v - lo) / (hi - lo) * 7)) + 1))
            for k in range(h):
                if k < 4: bb |= BITS[dx][3 - k]
                else:     tb |= BITS[dx][3 - (k - 4)]
        top += chr(0x2800 + tb)
        bot += chr(0x2800 + bb)
    return top, bot

def frame(rows, cols, body):
    out = ['\x1b[H\x1b[?25l']
    for i in range(rows):
        s = body[i] if i < len(body) else ''
        # no trailing newline on the final row: it would scroll the pane and eat
        # the title off the top
        out.append(bg(PANEL) + s + bg(PANEL) + '\x1b[K' + R + ('\n' if i < rows - 1 else ''))
    out.append(bg(PANEL) + '\x1b[J' + R)
    sys.stdout.write(''.join(out))
    sys.stdout.flush()

def head(t, title):
    # deliberately static: the panels are instrumentation, not animation
    return [' ' + fg(SLATE) + '\x1b[1m' + title + '\x1b[22m', ' ' + fg(RULE) + '─' * 30]

def panel_moves(t, cols, rows):
    mv = read(MOVES).split()
    w, b = names()
    body = head(t, 'MOVES')
    if not mv:
        return body + ['', '  ' + fg(TDIM) + 'no moves yet']
    pairs = [(i // 2 + 1, mv[i], mv[i + 1] if i + 1 < len(mv) else '')
             for i in range(0, len(mv), 2)]
    for n, a, c in reversed(pairs):            # newest first: it never scrolls away
        if len(body) >= rows:
            break
        body.append(f'  {fg(LABEL)}{n:>3}.  {fg(ICE)}{a:<8}{fg(EMBER)}{c}')
    return body

def panel_info(t, cols, rows):
    mv = read(MOVES).split()
    w, b = names()
    bd = board_from(mv)
    over = bd.is_game_over()
    wins, drawn = {}, 0
    pair = {w, b}
    for ln in read(RESULTS).split('\n'):
        p3 = ln.split()
        if len(p3) != 3:
            continue
        wn, r, bn = p3[0].upper(), p3[1], p3[2].upper()
        if {wn, bn} != pair:
            # results.txt is cumulative across every pairing that has ever
            # played -- a line from an earlier pairing must not count toward
            # this one's tally (order-insensitive: colours swap between games).
            continue
        wins.setdefault(wn, 0), wins.setdefault(bn, 0)
        if r == '1-0':
            wins[wn] += 1
        elif r == '0-1':
            wins[bn] += 1
        else:
            drawn += 1
    turn_w = bd.turn == chess.WHITE and not over
    body = head(t, 'MATCH')
    # wins are shown per agent, since who sits as White changes every game
    body.append('  ' + fg(W_GLYPH if turn_w else blend(W_GLYPH, PANEL, 0.55))
                + ('▸ ' if turn_w else '  ') + f'\x1b[1m{w:<10}\x1b[22m'
                + fg(TEXT) + f'{wins.get(w, 0):>3}')
    body.append('  ' + fg(B_GLYPH if (not turn_w and not over) else blend(B_GLYPH, PANEL, 0.55))
                + ('▸ ' if (not turn_w and not over) else '  ') + f'\x1b[1m{b:<10}\x1b[22m'
                + fg(TEXT) + f'{wins.get(b, 0):>3}')
    body.append('')
    played = sum(wins.values()) + drawn
    body.append(f'  {fg(LABEL)}SERIES   {fg(TEXT)}{played} played'
                + (f'{fg(LABEL)}, {drawn} drawn' if drawn else ''))
    body.append('')
    hist = mat_history(mv)
    d = hist[-1] if hist else 0
    top, bot = spark(hist, min(14, max(6, cols - 12)))
    lead = TDIM if not d else (ICE if d > 0 else EMBER)
    body.append(f'  {fg(LABEL)}MATERIAL')
    body.append('  ' + fg(SLATE) + top)
    body.append('  ' + fg(SLATE) + bot + fg(lead) + (f' {d:+d}' if d else ' ='))
    body.append('')
    ply = len(mv)
    body.append(f'  {fg(LABEL)}PLY      {fg(TEXT)}{ply}{fg(LABEL)}   MOVE  {fg(TEXT)}{ply // 2 + 1}')
    if over:
        r = bd.result()
        win = w if r == '1-0' else b if r == '0-1' else 'NOBODY'
        c = W_GLYPH if r == '1-0' else B_GLYPH if r == '0-1' else SLATE
        body.append(f'  {fg(LABEL)}STATUS   \x1b[1m{fg(c)}{r}  {win}\x1b[22m')
    else:
        body.append(f'  {fg(LABEL)}STATUS   {fg(TEXT)}playing')
    return body

def main():
    which = sys.argv[1] if len(sys.argv) > 1 else 'info'
    render = panel_moves if which == 'moves' else panel_info
    sys.stdout.write('\x1b[2J')
    while True:
        cols, rows = shutil.get_terminal_size((36, 14))
        frame(rows, cols, render(time.monotonic(), cols, rows))
        time.sleep(0.4)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.stdout.write('\x1b[0m\x1b[?25h\n')
    except Exception as e:
        sys.stdout.write(f'\x1b[0m\x1b[?25h\nPANEL CRASH: {e}\n')
        raise

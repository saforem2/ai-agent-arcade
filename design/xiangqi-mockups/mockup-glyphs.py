#!/usr/bin/env python3
"""Xiangqi mockup A — GLYPHS. Pieces render as their actual Chinese characters,
red vs black distinguished by ANSI color, sitting on a dot-field lattice (box-
drawing lines + sparse braille dither) with a river gap and two palace diagonals.

Design note: CJK glyphs are DOUBLE-WIDTH in a terminal cell grid; plain line
characters (┼ │ ─) are SINGLE-WIDTH. If you don't account for this, the lattice
drifts out of register the moment a piece glyph sits where a "┼" used to be.
This script fixes it by giving every intersection a constant PITCH of visual
COLUMNS (not characters) and computing real display width per glyph
(unicodedata.east_asian_width), so vertical/diagonal connector rows can place
their marks at the same absolute column regardless of what occupies the node
above or below them.
"""
import unicodedata

def vwidth(ch):
    return 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1

def swidth(s):
    return sum(vwidth(c) for c in s)

PITCH = 4          # visual columns owned by each file (intersection)
FILES = 9
RANKS = 10          # 0 = red back rank (bottom), 9 = black back rank (top)
MARGIN = 3

RED = '\x1b[38;2;224;90;79m'
BLACK = '\x1b[38;2;222;228;238m'
DIM = '\x1b[38;2;90;98;116m'
DIMMER = '\x1b[38;2;58;64;78m'
RIVER = '\x1b[38;2;120;150;190m'
BG = '\x1b[48;2;18;21;28m'
LABEL = '\x1b[38;2;92;102;122m'
R = '\x1b[0m'

RED_PIECES = {
    'K': '帥', 'A': '仕', 'B': '相', 'N': '傌', 'R': '俥', 'C': '炮', 'P': '兵',
}
BLACK_PIECES = {
    'K': '將', 'A': '士', 'B': '象', 'N': '馬', 'R': '車', 'C': '砲', 'P': '卒',
}

# board[rank][file] = (side, kind) or None
board = [[None] * FILES for _ in range(RANKS)]

def place(rank, file, side, kind):
    board[rank][file] = (side, kind)

back = ['R', 'N', 'B', 'A', 'K', 'A', 'B', 'N', 'R']
for f, k in enumerate(back):
    place(0, f, 'red', k)
    place(9, f, 'black', k)
for f in (1, 7):
    place(2, f, 'red', 'C')
    place(7, f, 'black', 'C')
for f in (0, 2, 4, 6, 8):
    place(3, f, 'red', 'P')
    place(6, f, 'black', 'P')

def glyph(side, kind):
    return (RED if side == 'red' else BLACK) + (RED_PIECES if side == 'red' else BLACK_PIECES)[kind] + R

def pad(s, total_w, fillchar='─', color=DIM):
    w = swidth(s)
    fill = total_w - w
    return s + (color + fillchar * fill + R if fill > 0 else '')

def is_palace_file(f):
    return 3 <= f <= 5

def rank_line(rank):
    out = []
    for f in range(FILES):
        cell = board[rank][f]
        last = (f == FILES - 1)
        node_w = PITCH if last else PITCH
        if cell:
            side, kind = cell
            node = glyph(side, kind)
        else:
            if rank == 0:
                ch = '└' if f == 0 else ('┘' if f == FILES - 1 else '┴')
            elif rank == RANKS - 1:
                ch = '┌' if f == 0 else ('┐' if f == FILES - 1 else '┬')
            else:
                ch = '├' if f == 0 else ('┤' if f == FILES - 1 else '┼')
            node = DIM + ch + R
        fill_w = 0 if last else (PITCH - swidth(_visible(node)))
        line_run = '' if last else (DIM + '─' * fill_w + R)
        out.append(node + line_run)
    return (' ' * MARGIN) + ''.join(out)

def _visible(s):
    # strip ANSI escapes to get the printable text back
    res, i, skip = [], 0, False
    while i < len(s):
        if s[i] == '\x1b':
            j = s.find('m', i)
            i = j + 1
            continue
        res.append(s[i]); i += 1
    return ''.join(res)

def _visible_last(s):
    v = _visible(s)
    return v[-1] if v else ' '

def connector_line(between_rank_low):
    """The line drawn between rank `between_rank_low` and `between_rank_low+1`."""
    hi = between_rank_low + 1
    lo = between_rank_low
    in_red_palace = lo in (0, 1) and hi in (1, 2)
    in_black_palace = lo in (7, 8) and hi in (8, 9)
    cells = []
    for f in range(FILES):
        col_char = '│'
        color = DIM
        if in_red_palace and f == 3:
            col_char = '╲' if lo == 0 else '╲'
        if in_red_palace and f == 5:
            col_char = '╱' if lo == 0 else '╱'
        if in_red_palace and f == 4:
            col_char = '│'
        if in_black_palace and f == 3:
            col_char = '╱' if lo == 7 else '╱'
        if in_black_palace and f == 5:
            col_char = '╲' if lo == 7 else '╲'
        if in_black_palace and f == 4:
            col_char = '│'
        node = color + col_char + R
        fill_w = PITCH - swidth(_visible(node))
        cells.append(node + (' ' * fill_w if f != FILES - 1 else ''))
    return (' ' * MARGIN) + ''.join(cells)

def river_line(text_left, text_right, dots=True):
    total_w = MARGIN + PITCH * (FILES - 1) + 2   # match a piece-rank's max width
    left_border = MARGIN
    right_border = MARGIN + PITCH * (FILES - 1)
    # sparse ambient dot texture across the gap — only inside the board frame
    import random
    rnd = random.Random(42)
    dot_chars = '⠐⠂⠈⠁⠄⠠'
    line = [' '] * total_w
    if dots:
        for i in range(left_border + 1, right_border):
            if rnd.random() < 0.06:
                line[i] = dot_chars[rnd.randrange(len(dot_chars))]
    # outer border verticals persist through the river
    line[left_border] = '│'
    line[right_border] = '│'
    s = ''.join(line)
    label = f'{text_left}          {text_right}'
    start = (total_w - len(label)) // 2
    s = s[:start] + label + s[start + len(label):]
    colored = []
    for ch in s:
        if ch == '│':
            colored.append(DIM + ch + R)
        elif ch in dot_chars:
            colored.append(DIMMER + ch + R)
        elif ch != ' ':
            colored.append(RIVER + ch + R)
        else:
            colored.append(' ')
    return ''.join(colored)

def main():
    print(BG + '\x1b[2J\x1b[H', end='')
    print()
    print(' ' * MARGIN + LABEL + '  XIANGQI — mockup A: GLYPHS  (double-width CJK on a fixed-pitch lattice)' + R)
    print()
    lines = []
    for rank in range(RANKS - 1, -1, -1):
        lines.append(rank_line(rank))
        if rank == 5:
            lines.append(river_line('楚 河', '漢 界'))
        elif rank > 0:
            lines.append(connector_line(rank - 1))
    file_labels = ' ' * MARGIN + ''.join(
        pad(LABEL + chr(ord('a') + f) + R, PITCH, ' ') if f < FILES - 1 else LABEL + chr(ord('a') + f) + R
        for f in range(FILES)
    )
    for l in lines:
        print(BG + l + '\x1b[K' + R)
    print(file_labels + '\x1b[K' + R)
    print()

if __name__ == '__main__':
    main()

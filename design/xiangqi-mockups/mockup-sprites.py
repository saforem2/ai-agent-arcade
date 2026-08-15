#!/usr/bin/env python3
"""Xiangqi mockup B — SPRITES. Pieces render as small braille silhouettes (2
braille characters each, single-width, no CJK), same lattice furniture as
mockup-glyphs.py: fixed-pitch intersections, river gap with 楚河/漢界, two
palace diagonals. Because braille cells are single-width in every terminal,
sprite nodes and line nodes share the same width class — the alignment
problem that mockup-glyphs.py has to work around mostly does not exist here.

Sprite vocabulary (2 braille chars per piece, read as a tiny glyph):
  King     ⣿⣿  solid mass — the piece worth protecting
  Advisor  ⠿⠶  capped block, softer base — bodyguard
  Elephant ⢾⡷  crossed lens — the elephant-eye motif
  Horse    ⠊⠑  angular, asymmetric — a head/muzzle silhouette
  Chariot  ⡇⢸  two verticals like a tower/wheel pair
  Cannon   ⠶⠿  open barrel over a solid base
  Pawn     ⠐⠂  two light dots — the smallest unit
"""
import random
import unicodedata

def vwidth(ch):
    return 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1

def swidth(s):
    return sum(vwidth(c) for c in s)

PITCH = 4
FILES = 9
RANKS = 10
MARGIN = 3

RED = '\x1b[38;2;224;90;79m'
BLACK = '\x1b[38;2;222;228;238m'
DIM = '\x1b[38;2;90;98;116m'
DIMMER = '\x1b[38;2;58;64;78m'
RIVER = '\x1b[38;2;120;150;190m'
BG = '\x1b[48;2;18;21;28m'
LABEL = '\x1b[38;2;92;102;122m'
R = '\x1b[0m'

SPRITES = {
    'K': '⣿⣿',
    'A': '⠿⠶',
    'B': '⢾⡷',
    'N': '⠊⠑',
    'R': '⡇⢸',
    'C': '⠶⠿',
    'P': '⠐⠂',
}

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

def sprite(side, kind):
    return (RED if side == 'red' else BLACK) + SPRITES[kind] + R

def _visible(s):
    res, i = [], 0
    while i < len(s):
        if s[i] == '\x1b':
            j = s.find('m', i)
            i = j + 1
            continue
        res.append(s[i]); i += 1
    return ''.join(res)

def rank_line(rank):
    out = []
    for f in range(FILES):
        cell = board[rank][f]
        last = (f == FILES - 1)
        if cell:
            side, kind = cell
            node = sprite(side, kind)
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

def connector_line(between_rank_low):
    hi = between_rank_low + 1
    lo = between_rank_low
    in_red_palace = lo in (0, 1) and hi in (1, 2)
    in_black_palace = lo in (7, 8) and hi in (8, 9)
    cells = []
    for f in range(FILES):
        col_char = '│'
        if in_red_palace and f == 3:
            col_char = '╲'
        if in_red_palace and f == 5:
            col_char = '╱'
        if in_black_palace and f == 3:
            col_char = '╱'
        if in_black_palace and f == 5:
            col_char = '╲'
        node = DIM + col_char + R
        fill_w = PITCH - swidth(_visible(node))
        cells.append(node + (' ' * fill_w if f != FILES - 1 else ''))
    return (' ' * MARGIN) + ''.join(cells)

def river_line(text_left, text_right):
    total_w = MARGIN + PITCH * (FILES - 1) + 2   # match a piece-rank's max width
    left_border = MARGIN
    right_border = MARGIN + PITCH * (FILES - 1)
    line = [' '] * total_w
    rnd = random.Random(42)
    dot_chars = '⠐⠂⠈⠁⠄⠠'
    for i in range(left_border + 1, right_border):
        if rnd.random() < 0.06:
            line[i] = dot_chars[rnd.randrange(len(dot_chars))]
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
    print(' ' * MARGIN + LABEL + '  XIANGQI — mockup B: SPRITES  (braille silhouettes, single-width, same lattice)' + R)
    print()
    lines = []
    for rank in range(RANKS - 1, -1, -1):
        lines.append(rank_line(rank))
        if rank == 5:
            lines.append(river_line('楚 河', '漢 界'))
        elif rank > 0:
            lines.append(connector_line(rank - 1))
    file_labels = ' ' * MARGIN + ''.join(
        LABEL + chr(ord('a') + f) + R + (' ' * (PITCH - 1) if f < FILES - 1 else '')
        for f in range(FILES)
    )
    for l in lines:
        print(BG + l + '\x1b[K' + R)
    print(file_labels + '\x1b[K' + R)
    print()
    print(' ' * MARGIN + LABEL + 'legend  K ⣿⣿  A ⠿⠶  B ⢾⡷  N ⠊⠑  R ⡇⢸  C ⠶⠿  P ⠐⠂' + R)
    print()

if __name__ == '__main__':
    main()

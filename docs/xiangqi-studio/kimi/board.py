#!/usr/bin/env python3
"""Xiangqi board mockup — real font-rendered CJK pieces, no braille.

Styles:
  A  bare glyph on the intersection
  B  3-row rounded box disc  ╭─╮││╰─╯
  C  bg-colour chip (TRIZ pick: disc function without disc geometry)
  D  lenticular brackets 【帥】
Usage: board.py [A|B|C|D|all]
"""
import sys

R = "\x1b[0m"
def fg(n): return f"\x1b[38;5;{n}m"
def bg(n): return f"\x1b[48;5;{n}m"

GRID  = fg(180)            # tan / wood line
RED   = "\x1b[1m" + fg(196)  # red side glyphs
BLK   = "\x1b[1m" + fg(252)  # black side glyphs (light on dark terminals)
RIVER = fg(37)
LBL   = fg(244)
CHIP_R = "\x1b[1m" + fg(160) + bg(223)   # red char on light wood chip
CHIP_B = "\x1b[1m" + fg(16)  + bg(223)   # black char on light wood chip

REDPCS = {'K': '帥', 'A': '仕', 'E': '相', 'R': '俥', 'N': '傌', 'C': '炮', 'P': '兵'}
BLKPCS = {'K': '將', 'A': '士', 'E': '象', 'R': '車', 'N': '馬', 'C': '砲', 'P': '卒'}


def opening():
    b = {}
    back = ['R', 'N', 'E', 'A', 'K', 'A', 'E', 'N', 'R']
    for f, k in enumerate(back):
        b[(f, 0)] = ('r', k)
        b[(f, 9)] = ('b', k)
    b[(1, 2)] = ('r', 'C'); b[(7, 2)] = ('r', 'C')
    b[(1, 7)] = ('b', 'C'); b[(7, 7)] = ('b', 'C')
    for f in (0, 2, 4, 6, 8):
        b[(f, 3)] = ('r', 'P')
        b[(f, 6)] = ('b', 'P')
    return b


class Canvas:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.cells = [[None] * w for _ in range(h)]

    def put(self, x, y, g, color=None, w=1):
        if not (0 <= x < self.w and 0 <= y < self.h):
            return
        self.cells[y][x] = (g, color)
        if w == 2 and x + 1 < self.w:
            self.cells[y][x + 1] = ('', color)

    def clear(self, x0, y0, x1, y1):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if 0 <= x < self.w and 0 <= y < self.h:
                    self.cells[y][x] = None

    def render(self):
        out = []
        for row in self.cells:
            line, cur = [], None
            for c in row:
                g, color = c if c else (' ', None)
                if color != cur:
                    line.append(R + (color or ''))
                    cur = color
                line.append(g)
            out.append(''.join(line).rstrip() + R)
        return '\n'.join(out)


def build(style):
    PX = 10 if style == 'D' else 8   # file pitch (cols)
    PY = 4                            # rank pitch (rows)
    RV = 2                            # extra river rows
    LEFT, TOP = 5, 2

    col = lambda f: LEFT + f * PX
    # red (rank 0) at the bottom, black (rank 9) at top, labels 9..0 downward
    row = lambda r: TOP + (9 - r) * PY + (RV if r <= 4 else 0)

    W = col(8) + 6
    H = row(0) + 4
    cv = Canvas(W, H)
    board = opening()

    def lines_udlr(f, r):
        u = r > 0 and not (r == 5 and 0 < f < 8)
        d = r < 9 and not (r == 4 and 0 < f < 8)
        l, rr = f > 0, f < 8
        return u, d, l, rr

    J = {(1,1,1,1):'┼',(0,1,1,1):'┬',(1,0,1,1):'┴',(1,1,0,1):'├',(1,1,1,0):'┤',
         (0,1,0,1):'┌',(0,1,1,0):'┐',(1,0,0,1):'└',(1,0,1,0):'┘',
         (1,1,0,0):'│',(0,0,1,1):'─'}

    # --- grid lines ---
    for r in range(10):
        for x in range(col(0), col(8) + 1):
            cv.put(x, row(r), '─', GRID)
    for f in range(9):
        for r in range(9):
            if r == 4 and 0 < f < 8:
                continue  # verticals do not cross the river
            for y in range(row(r) + 1, row(r + 1)):
                cv.put(col(f), y, '│', GRID)
    for f in range(9):
        for r in range(10):
            cv.put(col(f), row(r), J[lines_udlr(f, r)], GRID)

    # --- palace diagonals (staircase ╲ ╱) ---
    for (f0, r0, f1, r1) in [(3,0,4,1),(4,1,5,2),(5,0,4,1),(4,1,3,2),
                             (3,7,4,8),(4,8,5,9),(5,7,4,8),(4,8,3,9)]:
        dx = 1 if f1 > f0 else -1
        ch = '╲' if dx > 0 else '╱'
        for i in range(1, PY):
            x = col(f0) + dx * round(i * PX / PY)
            y = row(r0) + i
            cv.put(x, y, ch, GRID)

    # --- river caption ---
    ry = (row(4) + row(5)) // 2
    for ch, f in [('楚', 1), ('河', 3), ('漢', 5), ('界', 7)]:
        cv.put(col(f) - 1, ry, ch, RIVER, w=2)

    # --- pieces ---
    for (f, r), (side, k) in board.items():
        ch = (REDPCS if side == 'r' else BLKPCS)[k]
        pc = RED if side == 'r' else BLK
        C, Rw = col(f), row(r)
        u, d, l, rr = lines_udlr(f, r)
        if style == 'A':
            cv.clear(C - 2, Rw, C + 1, Rw)
            cv.put(C - 1, Rw, ch, pc, w=2)
        elif style == 'C':
            chip = CHIP_R if side == 'r' else CHIP_B
            cv.clear(C - 2, Rw, C + 1, Rw)
            cv.put(C - 2, Rw, ' ', chip)
            cv.put(C - 1, Rw, ch, chip, w=2)
            cv.put(C + 1, Rw, ' ', chip)
        elif style == 'D':
            cv.clear(C - 3, Rw, C + 2, Rw)
            cv.put(C - 3, Rw, '【', pc, w=2)
            cv.put(C - 1, Rw, ch, pc, w=2)
            cv.put(C + 1, Rw, '】', pc, w=2)
        elif style == 'B':
            cv.clear(C - 3, Rw - 1, C + 2, Rw + 1)
            cv.put(C - 2, Rw - 1, '╭', pc)
            cv.put(C - 1, Rw - 1, '─', pc)
            cv.put(C,     Rw - 1, '┬' if u else '─', pc)
            cv.put(C + 1, Rw - 1, '╮', pc)
            if l: cv.put(C - 3, Rw, '─', GRID)
            cv.put(C - 2, Rw, '┤' if l else '│', pc)
            cv.put(C - 1, Rw, ch, pc, w=2)
            cv.put(C + 1, Rw, '├' if rr else '│', pc)
            if rr: cv.put(C + 2, Rw, '─', GRID)
            cv.put(C - 2, Rw + 1, '╰', pc)
            cv.put(C - 1, Rw + 1, '─', pc)
            cv.put(C,     Rw + 1, '┴' if d else '─', pc)
            cv.put(C + 1, Rw + 1, '╯', pc)

    # --- labels: ranks left (9 top … 0 bottom, red at bottom), files below ---
    for r in range(10):
        cv.put(1, row(r), str(r), LBL)
    for f in range(9):
        cv.put(col(f), row(0) + 2, 'abcdefghi'[f], LBL)

    return cv.render()


NAMES = {'A': 'bare glyph', 'B': '3-row box disc', 'C': 'bg chip', 'D': 'lenticular brackets'}
if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else 'all'
    styles = list('ABCD') if arg == 'all' else [arg]
    for s in styles:
        print(f"\n=== STYLE {s}: {NAMES[s]} ===")
        print(build(s))

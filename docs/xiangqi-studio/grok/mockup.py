#!/usr/bin/env python3
"""
SPINE & SHORE — xiangqi board mockup (Grok / HOST branch)
=========================================================
Defend-on-air thesis
-------------------
Braille is mass-friendly and line-hostile. The live pane tries to draw
漢字 as dotted strokes and loses. The other branches stay inside
"piece glyph on intersection." This branch leaves that fight.

A host narrating match-001 needs, frame to frame:
  1. Whose move / last move causality
  2. The flying-general SPINE (file e) — always legible
  3. The RIVER as a real climate divide, not a faint rank gap
  4. The two PALACES as architecture (houses with an X)
  5. Instant RED / BLACK identity on every piece
  6. A broadcast rack for scorecard + host tension (not just a board)

So: geography is the identity. Pieces are colour-mass monogram seals
(reverse-video plates — mass from the terminal cell, CJK only as label).
Empty intersections are mostly negative space. No braille field.

Target: 113×53. Unicode + ANSI 256. /tmp only. Proposal, not impl.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from typing import Optional

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


def fg(n: int) -> str:
    return f"\033[38;5;{n}m"


def bg(n: int) -> str:
    return f"\033[48;5;{n}m"


# palette -----------------------------------------------------------
C_FRAME = 238
C_SPINE = 178
C_RIVER = 37
RIVER_BG = 17
C_PAL_R = 174
C_PAL_B = 111
C_RED = 196
C_RED_BG = 88
C_BLK_BG = 236
C_FG = 231
C_GHOST = 242
C_LAST = 220
C_HOST = 151
C_BANNER = 255
C_DIM = 245
C_SHORE_B = 16          # near-black cool
C_SHORE_B2 = 17
C_SHORE_R = 52
C_SHORE_R2 = 53
C_LABEL = 250
C_MUTE = 240

COLS, ROWS = 113, 53
LEFT = 3
FILE_W = 8
BOARD_W = 9 * FILE_W
BOARD_X0 = LEFT + 1
SIDE_X0 = BOARD_X0 + BOARD_W + 1
SIDE_W = COLS - SIDE_X0 - 1
FILES = "abcdefghi"

HDR_ROWS = 2
FILE_TOP = 2
BODY0 = 3
RANK_H = 4
RIVER_H = 6
# footer starts after board
# 5*4 + 6 + 5*4 = 46 body rows → 3+46=49; footer 49-52


GLYPH = {
    ("r", "K"): "帥", ("b", "K"): "將",
    ("r", "A"): "仕", ("b", "A"): "士",
    ("r", "E"): "相", ("b", "E"): "象",
    ("r", "H"): "馬", ("b", "H"): "馬",
    ("r", "R"): "車", ("b", "R"): "車",
    ("r", "C"): "炮", ("b", "C"): "砲",
    ("r", "P"): "兵", ("b", "P"): "卒",
}


@dataclass
class Piece:
    side: str
    kind: str

    @property
    def glyph(self) -> str:
        return GLYPH[(self.side, self.kind)]


def empty_board():
    return [[None for _ in range(10)] for _ in range(9)]


def setup_start():
    b = empty_board()
    order = "RHEAKAEHR"
    for f, k in enumerate(order):
        b[f][9] = Piece("b", k)
        b[f][0] = Piece("r", k)
    b[1][7] = Piece("b", "C")
    b[7][7] = Piece("b", "C")
    b[1][2] = Piece("r", "C")
    b[7][2] = Piece("r", "C")
    for f in (0, 2, 4, 6, 8):
        b[f][6] = Piece("b", "P")
        b[f][3] = Piece("r", "P")
    return b


def setup_midgame():
    b = setup_start()
    b[1][2], b[4][2] = None, Piece("r", "C")          # 炮二平五
    b[7][9], b[6][7] = None, Piece("b", "H")          # 馬8進7
    b[7][0], b[6][2] = None, Piece("r", "H")          # 馬二進三
    b[8][9], b[7][9] = None, Piece("b", "R")          # 車9平8
    b[8][0], b[7][0] = None, Piece("r", "R")          # 車一平二
    b[7][9], b[7][5] = None, Piece("b", "R")          # 車8進4
    b[6][3], b[6][4] = None, Piece("r", "P")          # 兵七進一
    meta = {
        "last": ("r", (6, 3), (6, 4)),
        "last_cn": "兵七進一",
        "last_iccs": "g3 → g4",
        "to_move": "b",
        "move_no": 4,
        "seq": [
            "1. 炮二平五   馬8進7",
            "2. 馬二進三   車9平8",
            "3. 車一平二   車8進4",
            "4. 兵七進一",
        ],
        "host_l1": "Screen horses set. Black rook already rides the river bank.",
        "host_l2": "Spine still cold — but the seven-file just woke. Black to answer.",
    }
    return b, meta


# ── canvas ────────────────────────────────────────────────────────
class Canvas:
    def __init__(self, cols: int, rows: int):
        self.cols, self.rows = cols, rows
        self.ch = [[" "] * cols for _ in range(rows)]
        self.st = [[""] * cols for _ in range(rows)]

    def put_raw(self, x, y, ch, style="", force=True):
        if 0 <= y < self.rows and 0 <= x < self.cols:
            if force or self.ch[y][x] == " ":
                self.ch[y][x] = ch
                self.st[y][x] = style

    def put(self, x, y, s, style="", force=True):
        if not (0 <= y < self.rows):
            return
        cx = x
        for c in s:
            if cx >= self.cols:
                break
            is_cjk = (
                "\u3400" <= c <= "\u9fff"
                or "\uf900" <= c <= "\ufaff"
                or "\u3000" <= c <= "\u303f"
                or c in "帥將仕士相象馬車砲炮兵卒楚河漢界"
            )
            if cx >= 0:
                if force or self.ch[y][cx] == " ":
                    self.ch[y][cx] = c
                    self.st[y][cx] = style
                if is_cjk and cx + 1 < self.cols:
                    self.ch[y][cx + 1] = ""
                    self.st[y][cx + 1] = style
            cx += 2 if is_cjk else 1

    def render(self) -> str:
        lines = []
        for y in range(self.rows):
            parts, prev = [], None
            for x in range(self.cols):
                c = self.ch[y][x]
                if c == "":
                    continue
                st = self.st[y][x]
                if st != prev:
                    if prev is not None:
                        parts.append(RESET)
                    if st:
                        parts.append(st)
                    prev = st
                parts.append(c if c else " ")
            if prev:
                parts.append(RESET)
            lines.append("".join(parts))
        return "\n".join(lines)


def file_cx(f: int) -> int:
    return BOARD_X0 + f * FILE_W + FILE_W // 2


def river_band():
    y0 = BODY0 + 5 * RANK_H
    return y0, y0 + RIVER_H


def rank_cy(r: int) -> int:
    y0, y1 = river_band()
    if r >= 5:
        return BODY0 + (9 - r) * RANK_H + RANK_H // 2
    return y1 + (4 - r) * RANK_H + RANK_H // 2


def footer_y():
    return river_band()[1] + 5 * RANK_H  # first row after rank 0 block


def piece_reserved(board, meta) -> set[tuple[int, int]]:
    cells = set()
    spots = [(f, r) for f in range(9) for r in range(10) if board[f][r]]
    spots += [meta["last"][1], meta["last"][2]]
    for f, r in spots:
        cx, cy = file_cx(f), rank_cy(r)
        for dy in (-1, 0, 1):
            for dx in range(-3, 4):
                cells.add((cx + dx, cy + dy))
    return cells


# ── layers ────────────────────────────────────────────────────────
def draw_shell(cv, meta):
    st = fg(C_FRAME)
    for x in range(COLS):
        cv.put_raw(x, 0, "─", st)
        cv.put_raw(x, ROWS - 1, "─", st)
    for y in range(ROWS):
        cv.put_raw(0, y, "│", st)
        cv.put_raw(COLS - 1, y, "│", st)
    cv.put_raw(0, 0, "┌", st)
    cv.put_raw(COLS - 1, 0, "┐", st)
    cv.put_raw(0, ROWS - 1, "└", st)
    cv.put_raw(COLS - 1, ROWS - 1, "┘", st)

    cv.put(2, 0, " XIANGQI · MATCH-001 · SPINE & SHORE ", fg(C_BANNER) + BOLD)
    side = "BLACK" if meta["to_move"] == "b" else "RED"
    scol = C_BLK_BG if meta["to_move"] == "b" else C_RED_BG
    pill = f" ▶ {side} TO MOVE "
    cv.put(COLS - len(pill) - 2, 0, pill, bg(scol) + fg(C_FG) + BOLD)
    cv.put(
        2, 1,
        f"  geography-first   move {meta['move_no']}   "
        f"last {meta['last_cn']}  ({meta['last_iccs']})   no engine eval",
        fg(C_DIM),
    )


def draw_climate(cv):
    """Two shores, no grid. Climate is the board."""
    y0, y1 = river_band()
    y_end = y1 + 5 * RANK_H
    for y in range(BODY0, y0):
        # subtle vertical gradient via alternating bg
        b = C_SHORE_B if y % 2 == 0 else C_SHORE_B2
        for x in range(BOARD_X0, BOARD_X0 + BOARD_W):
            cv.put_raw(x, y, " ", bg(b) + fg(C_MUTE))
    for y in range(y1, y_end):
        b = C_SHORE_R if y % 2 == 0 else C_SHORE_R2
        for x in range(BOARD_X0, BOARD_X0 + BOARD_W):
            cv.put_raw(x, y, " ", bg(b) + fg(C_MUTE))


def draw_river(cv):
    y0, y1 = river_band()
    for y in range(y0, y1):
        for x in range(BOARD_X0, BOARD_X0 + BOARD_W):
            cv.put_raw(x, y, " ", bg(RIVER_BG) + fg(C_RIVER))

    # density layers — river as MASS (the medium braille was good at)
    patterns = [
        "▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄",
        "·  ~  ·   ~~   ·  ~  ·   ~~   ·  ~  ·   ~~   ·  ~  ·   ~~   ·  ~  · ",
        "  ～    ～    ～    ～    ～    ～    ～    ～    ～    ～    ～    ",
        "                                                                    ",
        "  ～    ～    ～    ～    ～    ～    ～    ～    ～    ～    ～    ",
        "▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀",
    ]
    for i, y in enumerate(range(y0, y1)):
        row = patterns[i]
        for j, x in enumerate(range(BOARD_X0, BOARD_X0 + BOARD_W)):
            ch = row[j % len(row)]
            cv.put_raw(x, y, ch if ch != " " else " ", bg(RIVER_BG) + fg(C_RIVER))

    mid = y0 + RIVER_H // 2
    for x in range(BOARD_X0 + 4, BOARD_X0 + BOARD_W - 4):
        cv.put_raw(x, mid, " ", bg(RIVER_BG) + fg(C_FG))
    spine = file_cx(4)
    cv.put(BOARD_X0 + 10, mid, "楚  河", bg(RIVER_BG) + fg(C_FG) + BOLD)
    cv.put(spine - 1, mid, "◆", bg(RIVER_BG) + fg(C_SPINE) + BOLD)
    cv.put(BOARD_X0 + BOARD_W - 24, mid, "漢  界", bg(RIVER_BG) + fg(C_FG) + BOLD)


def draw_spine(cv, reserved):
    """Flying-general file as the board's protagonist."""
    y0, y1 = river_band()
    y_top, y_bot = rank_cy(9), rank_cy(0)
    cx = file_cx(4)
    for y in range(y_top - 1, y_bot + 2):
        if y0 <= y < y1:
            continue
        if (cx, y) in reserved:
            continue
        shore = C_SHORE_B if y < y0 else C_SHORE_R
        # double-width gold presence
        cv.put_raw(cx, y, "║", bg(shore) + fg(C_SPINE) + BOLD)
        if (cx - 1, y) not in reserved:
            cv.put_raw(cx - 1, y, " ", bg(shore) + fg(C_SPINE))
        if (cx + 1, y) not in reserved:
            cv.put_raw(cx + 1, y, " ", bg(shore) + fg(C_SPINE))

    # spine crown labels
    cv.put(cx - 2, FILE_TOP, " e ", fg(C_SPINE) + BOLD)


def draw_palaces(cv, reserved):
    def house(ranks, color, shore):
        xs = [file_cx(f) for f in (3, 4, 5)]
        ys = [rank_cy(r) for r in ranks]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        st = bg(shore) + fg(color) + BOLD
        # only the frame — architecture, not a filled cage
        for x in range(x0, x1 + 1):
            if (x, y0) not in reserved:
                cv.put_raw(x, y0, "═", st)
            if (x, y1) not in reserved:
                cv.put_raw(x, y1, "═", st)
        for y in range(y0, y1 + 1):
            if (x0, y) not in reserved:
                cv.put_raw(x0, y, "║", st)
            if (x1, y) not in reserved:
                cv.put_raw(x1, y, "║", st)
        for x, y, ch in (
            (x0, y0, "╔"), (x1, y0, "╗"), (x0, y1, "╚"), (x1, y1, "╝")
        ):
            if (x, y) not in reserved:
                cv.put_raw(x, y, ch, st)
        # one clean X, skipping reserved + frame
        steps = max(x1 - x0, y1 - y0, 1)
        for i in range(1, steps):
            x = x0 + round(i * (x1 - x0) / steps)
            y = y0 + round(i * (y1 - y0) / steps)
            if (x, y) not in reserved and x not in (x0, x1):
                cv.put_raw(x, y, "╲", st)
            x2 = x1 - round(i * (x1 - x0) / steps)
            y2 = y0 + round(i * (y1 - y0) / steps)
            if (x2, y2) not in reserved and x2 not in (x0, x1):
                cv.put_raw(x2, y2, "╱", st)

    house([7, 8, 9], C_PAL_B, C_SHORE_B)
    house([0, 1, 2], C_PAL_R, C_SHORE_R)


def draw_quiet_nodes(cv, board, reserved):
    """Empty intersections: a single muted dot. No lattice."""
    y0, y1 = river_band()
    for f in range(9):
        for r in range(10):
            if board[f][r] is not None:
                continue
            if r in (4, 5) and False:
                pass
            cx, cy = file_cx(f), rank_cy(r)
            if y0 <= cy < y1:
                continue
            if (cx, cy) in reserved:
                continue
            if f == 4:
                continue  # spine owns e
            shore = C_SHORE_B if r >= 5 else C_SHORE_R
            cv.put_raw(cx, cy, "·", bg(shore) + fg(C_MUTE))


def draw_file_rank_labels(cv):
    # top letters in header band; bottom letters sit on the footer rule
    # so piece plates can never eat them
    for f, name in enumerate(FILES):
        if f == 4:
            continue  # spine crown already drawn at FILE_TOP
        cx = file_cx(f)
        cv.put(cx, FILE_TOP, name, fg(C_LABEL))
    y_bot = ROWS - 4  # same row as HOST MIC rule — letters left of the tag
    for f, name in enumerate(FILES):
        cx = file_cx(f)
        st = fg(C_SPINE) + BOLD if f == 4 else fg(C_LABEL)
        cv.put(cx, y_bot, name, st)
    for r in range(10):
        cy = rank_cy(r)
        cv.put(1, cy, str(r), fg(C_LABEL) + (BOLD if r in (0, 4, 5, 9) else ""))


def draw_last_move(cv, meta):
    _, (f0, r0), (f1, r1) = meta["last"]
    x0, y0 = file_cx(f0), rank_cy(r0)
    x1, y1 = file_cx(f1), rank_cy(r1)
    shore = C_SHORE_R
    st = bg(shore) + fg(C_LAST) + BOLD
    # ghost origin
    cv.put(x0 - 2, y0 - 1, "╭─╮", fg(C_GHOST) + DIM)
    cv.put(x0 - 2, y0, "│ · │"[:5], fg(C_GHOST) + DIM)
    cv.put(x0 - 2, y0, "│", fg(C_GHOST) + DIM)
    cv.put(x0 + 2, y0, "│", fg(C_GHOST) + DIM)
    cv.put(x0 - 2, y0 + 1, "╰─╯", fg(C_GHOST) + DIM)
    # trail
    if f0 == f1:
        lo, hi = sorted((y0, y1))
        for y in range(lo + 1, hi):
            cv.put_raw(x0, y, "┊", st)
    # destination bracket
    cv.put_raw(x1 - 3, y1 - 1, "┏", fg(C_LAST) + BOLD)
    cv.put_raw(x1 + 3, y1 - 1, "┓", fg(C_LAST) + BOLD)
    cv.put_raw(x1 - 3, y1 + 1, "┗", fg(C_LAST) + BOLD)
    cv.put_raw(x1 + 3, y1 + 1, "┛", fg(C_LAST) + BOLD)


def draw_piece(cv, f, r, p, highlight=False):
    """
    Colour-mass seal. Terminal cells supply MASS; 漢字 supplies name.
    5 wide × 3 tall plate, side chevron encodes army without relying
    on stroke colour alone.
    """
    cx, cy = file_cx(f), rank_cy(r)
    y_riv0, _ = river_band()
    shore = C_SHORE_B if rank_cy(r) < y_riv0 else C_SHORE_R

    if highlight:
        fill = bg(C_LAST) + fg(16) + BOLD
    elif p.side == "r":
        fill = bg(C_RED_BG) + fg(C_FG) + BOLD
    else:
        fill = bg(C_BLK_BG) + fg(C_FG) + BOLD

    # solid plate
    for dx in range(-2, 3):
        cv.put_raw(cx + dx, cy - 1, "▀", fill)
        cv.put_raw(cx + dx, cy + 1, "▄", fill)
    cv.put_raw(cx - 2, cy, " ", fill)
    cv.put(cx - 1, cy, p.glyph, fill)
    cv.put_raw(cx + 1, cy, " ", fill)

    # army chevron outside the plate
    ch_l, ch_r = ("◀", "▶") if p.side == "r" else ("◁", "▷")
    # use simpler ASCII-width chevrons that are width-1
    ch_l = "▌" if p.side == "r" else "│"
    ch_r = "▐" if p.side == "r" else "│"
    cv.put_raw(cx - 3, cy, ch_l, bg(shore) + fg(C_RED if p.side == "r" else 250) + BOLD)
    cv.put_raw(cx + 2, cy, ch_r, bg(shore) + fg(C_RED if p.side == "r" else 250) + BOLD)


def draw_pieces(cv, board, meta):
    dest = meta["last"][2]
    for f in range(9):
        for r in range(10):
            p = board[f][r]
            if p:
                draw_piece(cv, f, r, p, highlight=((f, r) == dest))


def draw_side(cv, board, meta):
    x, y = SIDE_X0, BODY0

    def L(text, st=None):
        nonlocal y
        cv.put(x, y, (text + " " * SIDE_W)[:SIDE_W], st or fg(C_DIM))
        y += 1

    L("┌ BROADCAST RACK", fg(C_BANNER) + BOLD)
    L("│", fg(C_FRAME))
    L("│ SPINE  file e", fg(C_SPINE) + BOLD)
    bits = []
    for r in range(9, -1, -1):
        p = board[4][r]
        if p:
            bits.append(f"{'R' if p.side == 'r' else 'B'}{p.glyph}@{r}")
    L("│ " + (" ".join(bits) if bits else "open"), fg(C_DIM))
    L("│ flying-gen: cold", fg(C_DIM))
    L("│", fg(C_FRAME))
    L("│ LAST MOVE", fg(C_LAST) + BOLD)
    L(f"│ {meta['last_cn']}", fg(C_LAST) + BOLD)
    L(f"│ {meta['last_iccs']}", fg(C_DIM))
    L("│ 7-file pawn push", fg(C_DIM))
    L("│", fg(C_FRAME))
    L("│ SCORECARD", fg(C_LABEL) + BOLD)
    for s in meta["seq"]:
        L("│ " + s, fg(C_DIM))
    L("│", fg(C_FRAME))
    L("│ TENSION", fg(C_HOST) + BOLD)
    for t in (
        "· rook @ h5 on bank",
        "· red storms file 7",
        "· cannon @ e2 on spine",
        "· palaces both shut",
        "· initiative → black",
    ):
        L("│ " + t, fg(C_HOST))
    L("│", fg(C_FRAME))
    L("│ READ AS", fg(C_LABEL) + BOLD)
    L("│  seals = pieces", fg(C_DIM))
    L("│  gold ║ = spine", fg(C_SPINE))
    L("│  teal band = river", fg(C_RIVER))
    L("│  ═ house = palace", fg(C_PAL_R))
    L("│  ┏┓ = last move", fg(C_LAST))
    L("│  climate = side", fg(C_DIM))
    L("└" + "─" * 16, fg(C_FRAME))
    y += 1
    L(" WHY THIS BOARD", fg(C_BANNER) + BOLD)
    for t in (
        "host calls geography",
        "not glyph texture.",
        "river/palace/spine",
        "survive 10ft glance.",
        "pieces: mass plates,",
        "not braille strokes.",
    ):
        L(" " + t, fg(C_MUTE))


def draw_footer(cv, meta):
    y = ROWS - 4
    for x in range(1, COLS - 1):
        cv.put_raw(x, y, "─", fg(C_FRAME))
    # file letters already painted on this row by draw_file_rank_labels;
    # host tag sits in the side-panel column so it never covers a–i
    cv.put(SIDE_X0, y, " HOST MIC ", bg(C_HOST) + fg(16) + BOLD)
    cv.put(2, y + 1, meta["host_l1"][: COLS - 4], fg(C_HOST))
    cv.put(2, y + 2, meta["host_l2"][: COLS - 4], fg(C_HOST))


def main():
    board, meta = setup_midgame()
    cv = Canvas(COLS, ROWS)
    reserved = piece_reserved(board, meta)

    draw_shell(cv, meta)
    draw_climate(cv)
    draw_river(cv)
    draw_spine(cv, reserved)
    draw_palaces(cv, reserved)
    draw_quiet_nodes(cv, board, reserved)
    draw_last_move(cv, meta)
    draw_pieces(cv, board, meta)
    draw_side(cv, board, meta)
    draw_footer(cv, meta)
    draw_file_rank_labels(cv)  # last: a–i must sit above footer rule ink

    out = cv.render().split("\n")
    while len(out) < ROWS:
        out.append("")
    text = "\n".join(out[:ROWS]) + "\n"
    sys.stdout.write(text)

    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "render.ans"), "w", encoding="utf-8") as f:
        f.write(text)
    plain = re.sub(r"\033\[[0-9;]*m", "", text)
    with open(os.path.join(here, "render.plain.txt"), "w", encoding="utf-8") as f:
        f.write(plain)
    with open(os.path.join(here, "README.md"), "w", encoding="utf-8") as f:
        f.write(
            "# SPINE & SHORE (Grok mockup branch)\n\n"
            "```bash\npython3 /tmp/xq-mock-grok/mockup.py\n```\n\n"
            "Geography-first xiangqi spectator board. See script docstring.\n"
        )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""FIELD / RIVER / SEAL — standalone xiangqi TUI synthesis mockup.

Default: full 113x53 opening in ANSI truecolour.
  python3 mockup.py
  python3 mockup.py --plain
  python3 mockup.py --capture
  python3 mockup.py --write
  python3 mockup.py --tier lacquer|compact|text|seals

This file is deliberately standalone and writes only beside itself when
--write is supplied. It does not import or modify the arcade repository.
"""

from __future__ import annotations

import argparse
import math
import random
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

COLS, ROWS = 113, 53
BOARD_X, BOARD_Y = 4, 2
BW, BH = 74, 42
DOTW, DOTH = BW * 2, BH * 4
CW, CH = 8, 4
SQW, SQH = CW * 2, CH * 4
MARGIN_CH, MARGIN_CV = 5, 3
RACK_X, RACK_W = 82, 29
FILES = "abcdefghi"

# Production palette, plus the river/spine accents earned by synthesis.
PANEL = (18, 21, 28)
NEUTRAL = (104, 116, 138)
AMBIENT = (52, 58, 72)
SQL, SQD = (34, 39, 50), (26, 30, 39)
RED = (255, 138, 78)
BLACK = (240, 249, 255)
CHECK = (242, 84, 94)
TEXT, TDIM, LABEL = (204, 212, 228), (118, 128, 148), (92, 102, 122)
RIVER, RIVER_BG = (44, 183, 190), (12, 32, 46)
GOLD = (214, 170, 86)
HOST = (165, 210, 188)
LAST = (245, 202, 92)

BAYER = ((0, 4), (6, 2), (1, 5), (7, 3))
BITS = ((0x01, 0x02, 0x04, 0x40), (0x08, 0x10, 0x20, 0x80))


def fg(c):
    return f"\033[38;2;{c[0]};{c[1]};{c[2]}m"


def bg(c):
    return f"\033[48;2;{c[0]};{c[1]};{c[2]}m"


RESET = "\033[0m"
BOLD = "\033[1m"


def is_wide(ch: str) -> bool:
    return unicodedata.east_asian_width(ch) in ("W", "F")


@dataclass
class Cell:
    ch: str = " "
    front: tuple[int, int, int] = TEXT
    back: tuple[int, int, int] = PANEL
    bold: bool = False
    cont: bool = False


class Surface:
    def __init__(self):
        self.cells = [[Cell() for _ in range(COLS)] for _ in range(ROWS)]

    def put_char(self, x, y, ch, front=TEXT, back=PANEL, bold=False):
        if not (0 <= x < COLS and 0 <= y < ROWS):
            return
        self.cells[y][x] = Cell(ch, front, back, bold, False)
        if is_wide(ch) and x + 1 < COLS:
            self.cells[y][x + 1] = Cell("", front, back, bold, True)

    def put(self, x, y, text, front=TEXT, back=PANEL, bold=False):
        cx = x
        for ch in text:
            self.put_char(cx, y, ch, front, back, bold)
            cx += 2 if is_wide(ch) else 1

    def fill(self, x0, y0, x1, y1, ch=" ", front=TEXT, back=PANEL):
        for y in range(max(0, y0), min(ROWS, y1)):
            for x in range(max(0, x0), min(COLS, x1)):
                self.cells[y][x] = Cell(ch, front, back, False, False)

    def render(self, plain=False):
        lines = []
        for row in self.cells:
            if plain:
                lines.append("".join(c.ch for c in row if not c.cont))
                continue
            out, active = [], None
            for c in row:
                if c.cont:
                    continue
                style = (c.front, c.back, c.bold)
                if style != active:
                    out.append(RESET + fg(c.front) + bg(c.back) + (BOLD if c.bold else ""))
                    active = style
                out.append(c.ch)
            out.append(RESET)
            lines.append("".join(out))
        return "\n".join(lines) + "\n"


class DotGrid:
    def __init__(self):
        self.bits = [[0] * BW for _ in range(BH)]
        self.front = [[AMBIENT] * BW for _ in range(BH)]
        self.pri = [[-2] * BW for _ in range(BH)]
        self.back = [[SQD] * BW for _ in range(BH)]

    def cell(self, cx, cy, bits, front, pri):
        if 0 <= cx < BW and 0 <= cy < BH:
            self.bits[cy][cx] |= bits
            if pri >= self.pri[cy][cx]:
                self.pri[cy][cx] = pri
                self.front[cy][cx] = front

    def dot(self, x, y, front, pri=1):
        x, y = int(round(x)), int(round(y))
        if 0 <= x < DOTW and 0 <= y < DOTH:
            self.cell(x // 2, y // 4, BITS[x % 2][y % 4], front, pri)

    def set_cell(self, cx, cy, bits, front, pri=1):
        if 0 <= cx < BW and 0 <= cy < BH:
            self.bits[cy][cx] = bits
            self.front[cy][cx] = front
            self.pri[cy][cx] = pri


def cell_bits(cx, cy, level):
    if level <= 0:
        return 0
    if level >= 8:
        return 0xFF
    bits = 0
    for dx in (0, 1):
        for dy in range(4):
            if BAYER[dy][dx] < level:
                bits |= BITS[dx][dy]
    return bits


def px(file):
    return MARGIN_CH * 2 + file * SQW


def py(rank):
    return MARGIN_CV * 4 + (9 - rank) * SQH


def cx(file):
    return BOARD_X + px(file) // 2


def cy(rank):
    return BOARD_Y + py(rank) // 4


def line(g, x0, y0, x1, y1, color, pri=1):
    dx, dy = x1 - x0, y1 - y0
    steps = max(abs(dx), abs(dy), 1)
    for i in range(steps + 1):
        g.dot(x0 + dx * i / steps, y0 + dy * i / steps, color, pri)


def field_and_plate(g, phase=0.65):
    top, bottom = sorted((py(5) // 4, py(4) // 4))
    palace_x = sorted((px(3) // 2, px(5) // 2))
    palace_top = sorted((py(9) // 4, py(7) // 4))
    palace_bottom = sorted((py(2) // 4, py(0) // 4))
    for y in range(BH):
        for x in range(BW):
            in_river = top < y < bottom
            if in_river:
                g.back[y][x] = RIVER_BG
                level = 0.0
            elif palace_x[0] <= x <= palace_x[1] and (
                palace_top[0] <= y <= palace_top[1]
                or palace_bottom[0] <= y <= palace_bottom[1]
            ):
                g.back[y][x] = SQL
                level = 2 + 0.45 * math.sin(phase + x * 0.13)
            else:
                g.back[y][x] = SQD
                level = 2 + 0.45 * math.sin(phase + x * 0.13 + y * 0.09)
            g.cell(x, y, cell_bits(x, y, level), AMBIENT, -1)


PALACES = (((3, 0), (5, 2)), ((5, 0), (3, 2)),
           ((3, 7), (5, 9)), ((5, 7), (3, 9)))
MARKS = {(1, 2), (7, 2), (0, 3), (2, 3), (4, 3), (6, 3), (8, 3),
         (1, 7), (7, 7), (0, 6), (2, 6), (4, 6), (6, 6), (8, 6)}


def lattice(g):
    for f in range(9):
        if f in (0, 8):
            line(g, px(f), py(0), px(f), py(9), NEUTRAL)
        else:
            line(g, px(f), py(0), px(f), py(4), NEUTRAL)
            line(g, px(f), py(5), px(f), py(9), NEUTRAL)
    for r in range(10):
        line(g, px(0), py(r), px(8), py(r), NEUTRAL)
    for (f0, r0), (f1, r1) in PALACES:
        line(g, px(f0), py(r0), px(f1), py(r1), NEUTRAL)
    for f, r in MARKS:
        x, y = px(f), py(r)
        for sx in (-1, 1):
            if (f == 0 and sx < 0) or (f == 8 and sx > 0):
                continue
            for sy in (-1, 1):
                g.dot(x + sx * 2, y + sy, NEUTRAL)
                g.dot(x + sx, y + sy * 2, NEUTRAL)
    for f in range(9):
        for r in range(10):
            for ox in (0, 1):
                for oy in (0, 1):
                    g.dot(px(f) + ox, py(r) + oy, NEUTRAL, 2)


def river(g):
    top, bottom = sorted((py(5) // 4, py(4) // 4))
    # Re-colour both banks and lay three rows of directional water mass.
    line(g, px(0), py(5), px(8), py(5), RIVER, 2)
    line(g, px(0), py(4), px(8), py(4), RIVER, 2)
    patterns = (
        (0x04, 0x24, 0x20, 0x40, 0x60, 0x80),
        (0x01, 0x09, 0x08, 0x02, 0x12, 0x10),
        (0x40, 0xC0, 0x80, 0x04, 0x24, 0x20),
    )
    for row, y in enumerate(range(top + 1, bottom)):
        for x in range(px(0) // 2, px(8) // 2 + 1):
            g.set_cell(x, y, patterns[row % len(patterns)][x % 6], RIVER, 2)


def spine(g, live=False):
    color = LAST if live else GOLD
    for y in range(py(9), py(0) + 1):
        # A dotted two-beat cadence, not grok's heavy box-drawn wall.
        if y % 4 in (0, 1):
            g.dot(px(4), y, color, 2)


def check_flash(g, rank, phase=0.5):
    """Dot-ring pulse retained from the production board language."""
    radius = 7.0 + phase * 3.0
    for i in range(40):
        angle = 2 * math.pi * i / 40
        x = px(4) + math.cos(angle) * radius
        y = py(rank) + math.sin(angle) * radius * 0.72
        g.dot(x, y, CHECK, 5)


FACE = {
    ("r", "K"): "帥", ("b", "K"): "將",
    ("r", "A"): "仕", ("b", "A"): "士",
    ("r", "E"): "相", ("b", "E"): "象",
    ("r", "H"): "傌", ("b", "H"): "馬",
    ("r", "R"): "俥", ("b", "R"): "車",
    ("r", "C"): "炮", ("b", "C"): "砲",
    ("r", "P"): "兵", ("b", "P"): "卒",
}


def opening():
    board = {}
    order = "RHEAKAEHR"
    for f, kind in enumerate(order):
        board[(f, 9)] = ("b", kind)
        board[(f, 0)] = ("r", kind)
    for f in (1, 7):
        board[(f, 7)] = ("b", "C")
        board[(f, 2)] = ("r", "C")
    for f in (0, 2, 4, 6, 8):
        board[(f, 6)] = ("b", "P")
        board[(f, 3)] = ("r", "P")
    return board


def capture_position():
    board = opening()
    board.pop((1, 2))
    board[(4, 2)] = ("r", "C")
    return board


def void_seal(kind):
    # Equal 6×6 discs, identity carried by punched movement/role voids.
    def disc(x, y):
        return ((x - 2.5) / 2.8) ** 2 + ((y - 2.5) / 2.8) ** 2 <= 1

    def hole(x, y):
        if kind == "K":  # palace
            return 1 <= x <= 4 and 1 <= y <= 4 and not (2 <= x <= 3 and 2 <= y <= 3)
        if kind == "A":  # diagonals
            return abs(x - y) <= 0 or abs(x + y - 5) <= 0
        if kind == "E":  # paired elephant eyes
            return (x in (1, 2) and y in (2, 3)) or (x in (3, 4) and y in (2, 3))
        if kind == "R":  # orthogonal rails
            return x in (2, 3) or y in (2, 3)
        if kind == "H":  # horse leg
            return (x in (1, 2) and 1 <= y <= 4) or (1 <= x <= 4 and y in (3, 4))
        if kind == "C":  # bore
            return 1 <= x <= 4 and 1 <= y <= 4 and not (x in (2, 3) and y in (2, 3))
        return y >= 1 and abs(x - 2.5) <= max(0.6, (y - 1) * 0.65)  # forward wedge

    dots = [[disc(x, y) and not hole(x, y) for x in range(6)] for y in range(8)]
    rows = []
    for by in (0, 4):
        row = ""
        for bx in (0, 2, 4):
            bits = 0
            for yy in range(4):
                for xx in range(2):
                    if dots[by + yy][bx + xx]:
                        bits |= BITS[xx][yy]
            row += chr(0x2800 + bits)
        rows.append(row)
    return rows


def token(side, kind, tier):
    face = FACE[(side, kind)]
    if tier == "lacquer":
        return [" ⣠⣶⣄ ", f"⣾ {face} ⣷", " ⠙⠛⠋ "]
    if tier == "compact":
        return [f"⣾{face}⣷"]
    if tier == "text":
        return [face]
    return void_seal(kind)


def copy_grid(surface, g):
    for y in range(BH):
        for x in range(BW):
            surface.put_char(
                BOARD_X + x, BOARD_Y + y,
                chr(0x2800 + g.bits[y][x]), g.front[y][x], g.back[y][x]
            )


def clear_piece_area(surface, file, rank, width, height):
    x0 = cx(file) - width // 2
    y0 = cy(rank) - height // 2
    for y in range(y0, y0 + height):
        for x in range(x0, x0 + width):
            if BOARD_X <= x < BOARD_X + BW and BOARD_Y <= y < BOARD_Y + BH:
                back = surface.cells[y][x].back
                surface.cells[y][x] = Cell(" ", AMBIENT, back)


def draw_token(surface, file, rank, side, kind, tier, dim=False):
    art = token(side, kind, tier)
    width = max(sum(2 if is_wide(ch) else 1 for ch in row) for row in art)
    clear_piece_area(surface, file, rank, width, len(art))
    color = RED if side == "r" else BLACK
    if dim:
        color = tuple(int(v * 0.55) for v in color)
    y0 = cy(rank) - len(art) // 2
    for i, row in enumerate(art):
        roww = sum(2 if is_wide(ch) else 1 for ch in row)
        x0 = cx(file) - roww // 2
        back = surface.cells[y0 + i][cx(file)].back
        surface.put(x0, y0 + i, row, color, back, True)


def river_text(surface):
    mid = BOARD_Y + (py(5) // 4 + py(4) // 4) // 2
    # Three calm pockets let the native text sit on water rather than collide
    # with it; current remains visible immediately to either side.
    for left, width in ((BOARD_X + 12, 10), (BOARD_X + 35, 5), (BOARD_X + 52, 10)):
        surface.fill(left, mid, left + width, mid + 1, " ", RIVER, RIVER_BG)
    surface.put(BOARD_X + 14, mid, "楚  河", BLACK, RIVER_BG, True)
    surface.put(BOARD_X + 54, mid, "漢  界", BLACK, RIVER_BG, True)
    surface.put(BOARD_X + px(4) // 2, mid, "◆", GOLD, RIVER_BG, True)


def labels(surface):
    for rank in range(9, -1, -1):
        surface.put(1, cy(rank), str(rank), LABEL)
    for file, name in enumerate(FILES):
        surface.put(cx(file), BOARD_Y + BH + 1, name, GOLD if file == 4 else LABEL,
                    PANEL, file == 4)


def header(surface, mode="opening", frame=None, checked=False):
    surface.put(2, 0, "XIANGQI · MATCH-001 · FIELD / RIVER / SEAL", TEXT, PANEL, True)
    if mode == "opening":
        if checked:
            surface.put(70, 0, "CHECK-FLASH VISUAL TEST", CHECK, PANEL, True)
            surface.put(2, 1, "opening layout retained only to rehearse the pulse", TDIM)
        else:
            surface.put(72, 0, "▶ RED TO MOVE", RED, PANEL, True)
            surface.put(2, 1, "opening position · traditional faces · no engine evaluation", TDIM)
    else:
        surface.put(70, 0, f"CAPTURE STUDY {frame + 1}/5", LAST, PANEL, True)
        surface.put(2, 1, "炮五進四 · e2×e6 · one screen at e3", TDIM)


def rack(surface, board, mode="opening", frame=None):
    x, y = RACK_X, 3
    def put(text="", color=TDIM, bold=False):
        nonlocal y
        surface.put(x, y, text[:RACK_W], color, PANEL, bold)
        y += 1

    put("┌ BROADCAST", TEXT, True)
    put("│ MATCH-001 · OPENING" if mode == "opening" else "│ CAPTURE REHEARSAL", LABEL, True)
    put("│")
    put("│ SPINE · file e", GOLD, True)
    occupants = []
    for rank in range(9, -1, -1):
        if (4, rank) in board:
            side, kind = board[(4, rank)]
            occupants.append(f"{FACE[(side, kind)]}@{rank}")
    put("│ " + "  ".join(occupants), TDIM)
    screens = max(0, len(occupants) - 2)
    put(f"│ SEALED · {screens} screens", GOLD)
    put("│")
    put("│ LAST MOVE", LAST, True)
    put("│ — awaiting RED" if mode == "opening" else "│ 炮五進四  e2×e6", LAST)
    put("│")
    put("│ SCORECARD", LABEL, True)
    put("│ 1. …" if mode == "opening" else "│ capture animation", TDIM)
    put("│")
    put("│ TENSION", HOST, True)
    if mode == "opening":
        put("│ · cannons on b / h", HOST)
        put("│ · both palaces shut", HOST)
        put("│ · river unbroken", HOST)
        put("│ · spine dormant", HOST)
    else:
        beats = ("face intact", "face out · shell pinches", "lacquer scatters",
                 "new disc settles", "field goes quiet")
        put("│ · " + beats[frame], HOST)
        put("│ · no lasting scar", HOST)
    put("│")
    put("│ MATERIAL", LABEL, True)
    if mode == "opening" or frame == 0:
        put("│ full armies · 16 each", TDIM)
    elif frame == 1:
        put("│ capture resolving", TDIM)
    else:
        put("│ black −1 soldier", TDIM)
    put("└──────────────────────", LABEL)


def footer(surface, tier, checked=False):
    surface.put(2, 49, f"RED to move   [ ▶ replay ]   piece tier: {tier}", TEXT)
    state = "check pulse" if checked else "spine sealed"
    surface.put(2, 51, f"river current  ◦  {state}  ◦  press r to replay", TDIM)


def particle_set(age):
    rnd = random.Random(47)
    dots = []
    for _ in range(30):
        angle = rnd.uniform(0, 2 * math.pi)
        speed = rnd.uniform(8, 27)
        life = rnd.uniform(0.38, 0.82)
        if age >= life:
            continue
        x = px(4) + math.cos(angle) * speed * age
        y = py(6) + math.sin(angle) * speed * age * 0.55 + 18 * age * age
        dots.append((x, y, 1 - age / life))
    return dots


def capture_layers(g, frame):
    ages = (0.0, 0.06, 0.18, 0.34, 0.90)
    if frame >= 2:
        for x, y, strength in particle_set(ages[frame]):
            color = tuple(int(PANEL[i] + (BLACK[i] - PANEL[i]) * strength) for i in range(3))
            g.dot(x, y, color, 4)


def capture_pieces(surface, board, tier, frame):
    # Static army, excluding the moving red cannon and captured black soldier.
    for (file, rank), (side, kind) in board.items():
        if (file, rank) in ((4, 2), (4, 6)):
            continue
        draw_token(surface, file, rank, side, kind, tier)
    if frame == 0:
        draw_token(surface, 4, 2, "r", "C", tier)
        draw_token(surface, 4, 6, "b", "P", tier)
    elif frame == 1:
        # The printed name leaves first. Caps pinch inward; one dim node remains.
        clear_piece_area(surface, 4, 6, 6, 3)
        back = surface.cells[cy(6)][cx(4)].back
        surface.put(cx(4) - 3, cy(6) - 1, "  ⣴⣦  ", BLACK, back, True)
        surface.put(cx(4) - 3, cy(6), "  ·   ", TDIM, back)
        surface.put(cx(4) - 3, cy(6) + 1, "  ⠻⠟  ", BLACK, back, True)
        # The cannon jumps its screen as a compact, intact seal.
        surface.put(cx(4) - 2, cy(5), "⣾炮⣷", RED,
                    surface.cells[cy(5)][cx(4)].back, True)
    elif frame == 2:
        clear_piece_area(surface, 4, 6, 6, 3)
        surface.put(cx(4), cy(6), "·", TDIM, surface.cells[cy(6)][cx(4)].back)
        surface.put(cx(4) - 2, cy(6) + 1, "⣾炮⣷", RED,
                    surface.cells[cy(6) + 1][cx(4)].back, True)
    else:
        draw_token(surface, 4, 6, "r", "C", tier)


def render_scene(tier="lacquer", plain=False, mode="opening", frame=None, checked=False):
    surface = Surface()
    g = DotGrid()
    field_and_plate(g, phase=0.65 if frame is None else 0.65 + frame * 0.22)
    lattice(g)
    river(g)
    board = opening() if mode == "opening" else capture_position()
    # At frame 3+, the red cannon has replaced the black soldier on e6.
    if mode == "capture" and frame >= 3:
        board.pop((4, 2), None)
        board.pop((4, 6), None)
        board[(4, 6)] = ("r", "C")
    screens = sum(1 for rank in range(1, 9) if (4, rank) in board)
    spine(g, live=screens <= 1)
    if checked:
        check_flash(g, rank=9, phase=0.55)
    if mode == "capture":
        capture_layers(g, frame)
    copy_grid(surface, g)
    river_text(surface)
    if mode == "opening":
        for (file, rank), (side, kind) in board.items():
            draw_token(surface, file, rank, side, kind, tier)
    else:
        capture_pieces(surface, capture_position(), tier, frame)
    labels(surface)
    header(surface, mode, frame, checked)
    rack(surface, board, mode, frame)
    footer(surface, tier, checked)
    return surface.render(plain)


def strip_ansi(text):
    return re.sub(r"\033\[[0-9;]*m", "", text)


def write_outputs(base: Path, tier):
    base.mkdir(parents=True, exist_ok=True)
    opening_ansi = render_scene(tier, False, "opening")
    (base / "opening.ans").write_text(opening_ansi, encoding="utf-8")
    (base / "opening.plain.txt").write_text(strip_ansi(opening_ansi), encoding="utf-8")
    check_ansi = render_scene(tier, False, "opening", checked=True)
    (base / "check-flash.ans").write_text(check_ansi, encoding="utf-8")
    (base / "check-flash.plain.txt").write_text(strip_ansi(check_ansi), encoding="utf-8")
    for frame in range(5):
        ansi = render_scene(tier, False, "capture", frame)
        (base / f"capture-{frame:02}.ans").write_text(ansi, encoding="utf-8")
        (base / f"capture-{frame:02}.plain.txt").write_text(strip_ansi(ansi), encoding="utf-8")
    fallback = render_scene("seals", True, "opening")
    (base / "fallback-seals.plain.txt").write_text(fallback, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plain", action="store_true")
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--tier", choices=("lacquer", "compact", "text", "seals"), default="lacquer")
    parser.add_argument("--delay", type=float, default=0.55)
    args = parser.parse_args()
    base = Path(__file__).resolve().parent
    if args.write:
        write_outputs(base, args.tier)
    if args.capture:
        for frame in range(5):
            if not args.plain:
                sys.stdout.write("\033[H\033[2J")
            sys.stdout.write(render_scene(args.tier, args.plain, "capture", frame))
            sys.stdout.flush()
            if frame < 4:
                time.sleep(max(0.0, args.delay))
    else:
        sys.stdout.write(render_scene(args.tier, args.plain, "opening", checked=args.check))


if __name__ == "__main__":
    main()

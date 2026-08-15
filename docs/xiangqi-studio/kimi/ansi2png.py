#!/usr/bin/env python3
"""Render ANSI-colored terminal text to PNG for visual inspection.
Each terminal cell drawn as a fixed rect; glyphs centered in their cells,
so alignment mirrors a real terminal regardless of font metrics."""
import re, sys
from PIL import Image, ImageDraw, ImageFont

CW, CH = 11, 22          # cell size px
BG_DEFAULT = (28, 28, 32)
FG_DEFAULT = (220, 220, 220)

def xterm256(n):
    if n < 8:
        return [(0,0,0),(205,0,0),(0,205,0),(205,205,0),(0,0,238),(205,0,205),(0,205,205),(229,229,229)][n]
    if n < 16:
        return [(127,127,127),(255,0,0),(0,255,0),(255,255,0),(92,92,255),(255,0,255),(0,255,255),(255,255,255)][n-8]
    if n < 232:
        n -= 16
        b, g, r = n % 6, (n // 6) % 6, n // 36
        cv = lambda v: 55 + v * 40 if v else 0
        return (cv(r), cv(g), cv(b))
    v = 8 + (n - 232) * 10
    return (v, v, v)

def is_wide(ch):
    o = ord(ch)
    return (0x4E00 <= o <= 0x9FFF or 0x3000 <= o <= 0x303F or
            0xFF00 <= o <= 0xFF60 or 0x3400 <= o <= 0x4DBF)

def parse(text):
    """-> list of rows; each row = list of (char, fg, bg, bold), wide char consumes 2 cells"""
    rows, cur = [], None
    fg = bg = None; bold = False
    for raw in text.split('\n'):
        row = []
        for tok in re.split(r'(\x1b\[[0-9;]*m)', raw):
            if tok.startswith('\x1b['):
                codes = tok[2:-1].split(';')
                for c in codes:
                    c = int(c) if c else 0
                    if c == 0: fg = bg = None; bold = False
                    elif c == 1: bold = True
                    elif c == 38: pass
                    elif c == 48: pass
                    elif c == 39: fg = None
                    elif c == 49: bg = None
                # handle 38;5;n / 48;5;n sequences properly
                m = re.findall(r'(38|48);5;(\d+)', tok[2:-1])
                for kind, n in m:
                    if kind == '38': fg = xterm256(int(n))
                    else: bg = xterm256(int(n))
                if tok == '\x1b[0m': fg = bg = None; bold = False
                continue
            for ch in tok:
                w = 2 if is_wide(ch) else 1
                row.append((ch, fg, bg, bold, w))
                if w == 2:
                    row.append(('', fg, bg, bold, 0))
        rows.append(row)
    return rows

def render(rows, out):
    h = len(rows); w = max(len(r) for r in rows)
    img = Image.new('RGB', (w * CW + 20, h * CH + 20), BG_DEFAULT)
    d = ImageDraw.Draw(img)
    lat = ImageFont.truetype('/System/Library/Fonts/Menlo.ttc', 16)
    cjk = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Unicode.ttf', 18)
    for y, row in enumerate(rows):
        for x, (ch, fg, bg, bold, cw) in enumerate(row):
            px, py = 10 + x * CW, 10 + y * CH
            if bg:
                d.rectangle([px, py, px + CW * max(cw,1) - 1, py + CH - 1], fill=bg)
            if ch.strip():
                font = cjk if is_wide(ch) else lat
                cellw = CW * (cw or 1)
                bb = d.textbbox((0, 0), ch, font=font)
                tw, th = bb[2] - bb[0], bb[3] - bb[1]
                d.text((px + (cellw - tw) / 2 - bb[0], py + (CH - th) / 2 - bb[1]),
                       ch, font=font, fill=fg or FG_DEFAULT)
    img.save(out)
    print(f'{out}: {img.size[0]}x{img.size[1]}, {w}x{h} cells')

if __name__ == '__main__':
    render(parse(open(sys.argv[1]).read()), sys.argv[2])

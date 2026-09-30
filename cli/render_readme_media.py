#!/usr/bin/env python3
"""Render deterministic README stills and an animated replay from an archive."""

import argparse
import contextlib
import io
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from PIL import Image

import ansi_png
import tui_dots


def capture_render(board, cols=96, rows=46, status=""):
    original = shutil.get_terminal_size
    shutil.get_terminal_size = lambda fallback=(80, 24): os.terminal_size((cols, rows))
    try:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            tui_dots.render(board, status_extra=status)
        return stream.getvalue()
    finally:
        shutil.get_terminal_size = original


def ansi_image(text, cols=96, rows=46, scale=1):
    cell_w, cell_h = 10 * scale, 20 * scale
    renderer = ansi_png.CellRenderer(cell_w, cell_h, width=cols * cell_w, height=rows * cell_h)
    return ansi_png.render_ansi(text, renderer)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs/assets")
    args = parser.parse_args()
    archive = args.archive.resolve()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    os.environ["ARCADE_LIVE"] = str(archive)
    tui_dots.D = archive
    tui_dots.MOVES = archive / "moves.txt"
    tui_dots.BANNER = archive / "banner.txt"
    tui_dots.CTL = archive / "ctl"
    tui_dots.INPUT_ENABLED = False
    tui_dots.refresh_names()

    sans = (archive / "moves.txt").read_text().split()
    final = tui_dots.build(sans)
    still = ansi_image(capture_render(final))
    still_path = out / "alcf-chess-board.png"
    still.save(still_path, optimize=True)

    frame_indices = sorted(set(range(0, len(sans) + 1, max(1, len(sans) // 12))))
    if frame_indices[-1] != len(sans):
        frame_indices.append(len(sans))
    frames = []
    for index in frame_indices:
        tui_dots.move_list = sans[:index]
        frame = ansi_image(capture_render(tui_dots.build(sans[:index]), status=f"  replay {index}/{len(sans)}"))
        frames.append(frame)
    gif_path = out / "alcf-chess-replay.gif"
    frames[0].save(
        gif_path,
        save_all=True,
        append_images=frames[1:],
        duration=650,
        loop=0,
        optimize=False,
        disposal=2,
    )
    print(still_path)
    print(gif_path)


if __name__ == "__main__":
    main()

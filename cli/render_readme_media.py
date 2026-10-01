#!/usr/bin/env python3
"""Render deterministic README stills and an animated replay from an archive."""

import argparse
import os
import random
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from PIL import Image
import chess

import ansi_png
import tui_dots


def capture_render(board, cols=96, rows=46, status="", now=0.0, fly=None):
    return tui_dots.render(
        board,
        fly=fly,
        status_extra=status,
        terminal_size=(cols, rows),
        now=now,
        output=False,
        interactive=False,
    )


def ansi_image(text, cols=96, rows=46, scale=1):
    cell_w, cell_h = 10 * scale, 20 * scale
    renderer = ansi_png.CellRenderer(cell_w, cell_h, width=cols * cell_w, height=rows * cell_h)
    return ansi_png.render_ansi(text, renderer)


def replay_frames(sans, cols=96, rows=46, fps=10):
    """Render actual fly/wake/debris frames from the canonical dot renderer."""
    board = tui_dots.build([])
    tui_dots.move_list = []
    tui_dots.last_pair = ()
    tui_dots.particles[:] = []
    random.seed(0)
    frames = [ansi_image(capture_render(board, cols, rows, "  replay 0/" + str(len(sans))))]
    now = 1.0
    travel_frames = max(2, round(0.5 * fps))
    for index, san in enumerate(sans, 1):
        move = board.parse_san(san)
        piece = board.piece_at(move.from_square)
        x0 = chess.square_file(move.from_square) * tui_dots.SQW
        y0 = (7 - chess.square_rank(move.from_square)) * tui_dots.SQH
        x1 = chess.square_file(move.to_square) * tui_dots.SQW
        y1 = (7 - chess.square_rank(move.to_square)) * tui_dots.SQH
        if board.is_capture(move):
            victim = move.to_square
            if board.is_en_passant(move):
                victim = chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square))
            tui_dots.spawn_debris(victim)
            for particle in tui_dots.particles:
                particle[4] = now
        wake = tui_dots.WAKE_W if piece.color else tui_dots.WAKE_B
        for frame_index in range(travel_frames):
            elapsed = frame_index / max(1, travel_frames - 1)
            smooth = elapsed * elapsed * (3 - 2 * elapsed)
            x = x0 + (x1 - x0) * smooth
            y = y0 + (y1 - y0) * smooth
            for _ in range(2):
                tui_dots.particles.append([
                    x + tui_dots.SQW / 2 + random.uniform(-2, 2),
                    y + tui_dots.SQH / 2 + random.uniform(-2, 2),
                    random.uniform(-6, 6), random.uniform(-4, 2), now, 0.5, wake,
                ])
            fly = (piece, x, y, move.from_square)
            status = f"  replay {index}/{len(sans)}"
            frames.append(ansi_image(capture_render(board, cols, rows, status, now, fly)))
            now += 1 / fps
        board.push(move)
        tui_dots.move_list = sans[:index]
        tui_dots.last_pair = (move.from_square, move.to_square)
        frames.append(ansi_image(capture_render(board, cols, rows, f"  replay {index}/{len(sans)}", now)))
        now += 1 / fps
    return frames


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
    still = ansi_image(capture_render(final, now=100.0))
    still_path = out / "alcf-chess-board.png"
    still.save(still_path, optimize=True)

    frames = replay_frames(sans)
    gif_path = out / "alcf-chess-replay.gif"
    frames[0].save(
        gif_path,
        save_all=True,
        append_images=frames[1:],
        duration=100,
        loop=0,
        optimize=False,
        disposal=2,
    )
    print(still_path)
    print(gif_path)


if __name__ == "__main__":
    main()

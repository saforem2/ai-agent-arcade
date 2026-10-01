#!/usr/bin/env python3
"""Record the live Textual app to a GIF using Textual's own SVG screenshot export.

Textual's ``App.export_screenshot()`` serialises the real composited screen --
app chrome, sidebar, and the canonical dot-field board -- as SVG. Driving the
app with ``run_test`` and exporting one SVG per frame gives a recording of the
actual TUI without needing a terminal emulator or screen-capture permission.
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from PIL import Image  # noqa: E402

from arcade_cli.arcade_app import ArcadeApp, BrailleBoard  # noqa: E402


def svg_to_png(svg: Path, png: Path, width: int) -> None:
    converter = shutil.which("rsvg-convert")
    if converter:
        subprocess.run(
            [converter, "--width", str(width), "--output", str(png), str(svg)],
            check=True,
        )
        return
    magick = shutil.which("magick") or shutil.which("convert")
    if not magick:
        raise SystemExit("need rsvg-convert or ImageMagick to rasterise Textual SVGs")
    subprocess.run([magick, "-density", "160", str(svg), "-resize", f"{width}x", str(png)], check=True)


async def record(match: Path, out: Path, scratch: Path, frames: int, fps: int, size, width: int):
    scratch.mkdir(parents=True, exist_ok=True)
    for stale in scratch.glob("frame-*"):
        stale.unlink()

    app = ArcadeApp(match, 1, 1, True, run_matches=False)
    images: list[Path] = []

    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        app.refresh_state()
        await pilot.pause()

        board = app.query_one("#board", BrailleBoard)
        # Drive animation off a virtual clock so each exported frame advances
        # exactly one interval, independent of how long SVG export takes.
        virtual = {"t": 0.0}
        board.clock = lambda: virtual["t"]
        board.start_replay()

        for index in range(frames):
            virtual["t"] = index / fps
            board.tick_frame()
            await pilot.pause()
            svg = scratch / f"frame-{index:03d}.svg"
            png = scratch / f"frame-{index:03d}.png"
            app.save_screenshot(str(svg))
            svg_to_png(svg, png, width)
            images.append(png)

    first, *rest = [Image.open(p).convert("RGB") for p in images]
    out.parent.mkdir(parents=True, exist_ok=True)
    first.save(
        out,
        save_all=True,
        append_images=rest,
        duration=int(1000 / fps),
        loop=0,
        optimize=True,
    )
    return out, len(images)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("match", type=Path, help="archived match directory to replay")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/assets/arcade-tui.gif")
    parser.add_argument("--scratch", type=Path, default=Path("/Users/sam/.hermes/cache/scratch/arcade-tui-frames"))
    parser.add_argument("--frames", type=int, default=140)
    parser.add_argument("--fps", type=int, default=14)
    parser.add_argument("--cols", type=int, default=150)
    parser.add_argument("--rows", type=int, default=46)
    parser.add_argument("--width", type=int, default=1400)
    args = parser.parse_args()

    out, count = asyncio.run(
        record(
            args.match.resolve(),
            args.output.resolve(),
            args.scratch.resolve(),
            args.frames,
            args.fps,
            (args.cols, args.rows),
            args.width,
        )
    )
    print(f"wrote {out} ({count} frames at {args.fps}fps)")


if __name__ == "__main__":
    main()

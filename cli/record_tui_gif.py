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


async def record(match: Path, out: Path, scratch: Path, frames: int, fps: int, size, width: int, theme: str | None = None):
    scratch.mkdir(parents=True, exist_ok=True)
    for stale in scratch.glob("frame-*"):
        stale.unlink()

    app = ArcadeApp(match, 1, 1, True, run_matches=False, theme=theme)
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
        # Replay through the app so the match panel and decision list rewind
        # with the board instead of sitting on the archive's final state.
        app.start_replay()

        for index in range(frames):
            virtual["t"] = index / fps
            board.tick_frame()
            app.refresh_state()
            await pilot.pause()
            svg = scratch / f"frame-{index:03d}.svg"
            png = scratch / f"frame-{index:03d}.png"
            app.save_screenshot(str(svg))
            svg_to_png(svg, png, width)
            images.append(png)

    # Pillow's GIF encoder merges consecutive identical frames into one with
    # a doubled duration (80 inputs -> 75 stored when idle frames are static).
    # That preserves wall-clock time but breaks "80 frames at 10fps" framing.
    # Coalesce ourselves so the reported count is honest and the durations
    # survive a round-trip. The field's drift (WAVE_AMP=0.5 @ 30s period) is
    # intentionally sub-threshold at 10fps, so some idle pairs really are
    # byte-identical — coalescing is the faithful representation.
    import hashlib

    loaded = [Image.open(p).convert("RGB") for p in images]
    hashes = [hashlib.md5(im.tobytes()).hexdigest() for im in loaded]
    coalesced: list[Image.Image] = []
    durations: list[int] = []
    base = int(1000 / fps)
    for idx, im in enumerate(loaded):
        if idx > 0 and hashes[idx] == hashes[idx - 1]:
            durations[-1] += base
        else:
            coalesced.append(im)
            durations.append(base)
    if len(coalesced) < len(loaded):
        print(f"note: {len(loaded) - len(coalesced)} consecutive identical frames coalesced "
              f"({len(loaded)} logical -> {len(coalesced)} stored, total {sum(durations)}ms)")
    first, *rest = coalesced
    out.parent.mkdir(parents=True, exist_ok=True)
    first.save(
        out,
        save_all=True,
        append_images=rest,
        duration=durations,
        loop=0,
        optimize=True,
    )
    return out, len(coalesced), len(loaded)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("match", type=Path, help="archived match directory to replay")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/assets/arcade-tui.gif")
    parser.add_argument("--scratch", type=Path, default=Path("/Users/sam/.hermes/cache/scratch/arcade-tui-frames"))
    parser.add_argument("--frames", type=int, default=260)
    parser.add_argument("--fps", type=int, default=14)
    parser.add_argument("--cols", type=int, default=150)
    parser.add_argument("--rows", type=int, default=46)
    parser.add_argument("--width", type=int, default=1400)
    parser.add_argument("--theme", type=str, default=None, choices=["ansi-dark", "ansi-light", "pbs-dark", "pbs-light"], help="Textual theme (default: auto-detect from terminal)")
    args = parser.parse_args()

    out, stored, logical = asyncio.run(
        record(
            args.match.resolve(),
            args.output.resolve(),
            args.scratch.resolve(),
            args.frames,
            args.fps,
            (args.cols, args.rows),
            args.width,
            args.theme,
        )
    )
    tag = f"{logical} logical/{stored} stored" if stored != logical else f"{stored}"
    print(f"wrote {out} ({tag} frames at {args.fps}fps)")


if __name__ == "__main__":
    main()

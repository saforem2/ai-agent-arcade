from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import chess
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Footer, Header, RichLog, Static

from . import main as arcade
from . import series

ROOT = series.resolve_root()
ENGINE = ROOT / "engine"
DEFAULT_LIVE = Path(os.environ.get("ARCADE_LIVE", ".thunderdome/live"))


@dataclass(frozen=True)
class Snapshot:
    game: int
    games: int
    white: str
    black: str
    ply: int
    board: chess.Board
    rationale: dict | None
    score: str
    status: str


def read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text()
    except OSError:
        return default


def board_from_live(live: Path) -> tuple[chess.Board, list[str]]:
    board = chess.Board()
    moves = read_text(live / "moves.txt").split()
    for san in moves:
        board.push_san(san)
    return board, moves


def latest_rationale(live: Path) -> dict | None:
    rows = [line for line in read_text(live / "decision_log.jsonl").splitlines() if line.strip()]
    if not rows:
        return None
    try:
        return json.loads(rows[-1])
    except json.JSONDecodeError:
        return None


def score_line(live: Path, white: str, black: str, summary: dict | None = None) -> str:
    if summary and summary.get("games_complete") is not None:
        wins = summary.get("wins") or {}
        return (
            f"{wins.get(white, 0)}–{wins.get(black, 0)} · "
            f"{summary.get('draws', 0)} draws · {summary['games_complete']} complete"
        )
    rows = arcade.parse_results(read_text(live / "results.txt"))
    wins_white, wins_black, draws, games = arcade.head_to_head(rows, white, black)
    return f"{wins_white}–{wins_black} · {draws} draws · {games} complete"


def board_markup(board: chess.Board) -> str:
    ranks = []
    symbols = {
        "P": "♙", "N": "♘", "B": "♗", "R": "♖", "Q": "♕", "K": "♔",
        "p": "♟", "n": "♞", "b": "♝", "r": "♜", "q": "♛", "k": "♚",
    }
    for rank in range(7, -1, -1):
        cells = []
        for file in range(8):
            piece = board.piece_at(chess.square(file, rank))
            glyph = symbols[piece.symbol()] if piece else "·"
            color = "#d9f4ff" if piece and piece.color else "#f0a046" if piece else "#566174"
            cells.append(f"[{color}]{glyph}[/]")
        ranks.append(f"[#697386]{rank + 1}[/]  " + "  ".join(cells))
    ranks.append("   [#697386]a  b  c  d  e  f  g  h[/]")
    return "\n".join(ranks)


class Thunderdome(App):
    CSS = """
    Screen { background: #12151c; color: #d0d8e8; }
    Header, Footer { background: #171b24; color: #8a93a6; }
    #body { height: 1fr; }
    #board-wrap { width: 68%; height: 1fr; align: center middle; border: round #334054; }
    #board { width: 38; height: 19; text-align: center; content-align: center middle; text-style: bold; }
    #side { width: 32%; height: 1fr; }
    .panel { border: round #334054; padding: 1 2; margin-left: 1; }
    #match { height: 11; }
    #decision { height: 1fr; min-height: 14; }
    #events { height: 11; }
    .title { color: #78d2eb; text-style: bold; }
    """
    BINDINGS = [("q", "quit", "Quit"), ("p", "pause", "Pause"), ("c", "continue_run", "Continue")]

    def __init__(self, live: Path, games: int, start_index: int, resume_live: bool):
        super().__init__()
        self.live = live.resolve()
        self.games = games
        self.start_index = start_index
        self.resume_live = resume_live
        self.process: subprocess.Popen | None = None
        self.paused = False
        self.last_event_size = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(id="board-wrap"):
                yield Static("Waiting for match state…", id="board")
            with VerticalScroll(id="side"):
                yield Static(id="match", classes="panel")
                yield Static(id="decision", classes="panel")
                yield RichLog(id="events", classes="panel", wrap=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "THUNDERDOME"
        self.sub_title = "referee-verified model chess"
        self.live.mkdir(parents=True, exist_ok=True)
        self.start_runner()
        self.set_interval(0.5, self.refresh_state)

    def start_runner(self) -> None:
        command = [
            sys.executable,
            "-m", "arcade_cli.series",
            "--games", str(self.games),
            "--start-index", str(self.start_index),
            "--live-dir", str(self.live),
        ]
        if self.resume_live:
            command.append("--resume-live")
        env = {**os.environ, "ARCADE_LIVE": str(self.live)}
        env["THUNDERDOME_ROOT"] = str(ROOT)
        self.process = subprocess.Popen(command, cwd=ROOT, env=env)

    def action_pause(self) -> None:
        if self.process and self.process.poll() is None and hasattr(os, "kill"):
            os.kill(self.process.pid, 19)
            self.paused = True
            self.notify("Paused after the current system call")

    def action_continue_run(self) -> None:
        if self.process and self.process.poll() is None and self.paused:
            os.kill(self.process.pid, 18)
            self.paused = False
            self.notify("Continued")

    def on_unmount(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()

    def refresh_state(self) -> None:
        names = read_text(self.live / "names.txt").split()
        if len(names) != 2 or not (self.live / "moves.txt").exists():
            return
        board, moves = board_from_live(self.live)
        rationale = latest_rationale(self.live)
        summary_path = self.live / "series-summary.json"
        summary = json.loads(read_text(summary_path, "{}") or "{}")
        complete = summary.get("games_complete", max(0, self.start_index - 1))
        status = "paused" if self.paused else "running"
        if self.process and self.process.poll() is not None:
            status = "complete" if self.process.returncode == 0 else f"failed ({self.process.returncode})"
        snap = Snapshot(
            game=min(complete + 1, self.games), games=self.games,
            white=names[0], black=names[1], ply=len(moves), board=board,
            rationale=rationale, score=score_line(self.live, names[0], names[1], summary), status=status,
        )
        self.query_one("#board", Static).update(board_markup(board))
        turn = snap.white if board.turn else snap.black
        self.query_one("#match", Static).update(
            f"[bold #78d2eb]MATCH[/]\nGame {snap.game}/{snap.games} · ply {snap.ply}\n"
            f"{snap.white} vs {snap.black}\n{snap.score}\n{turn} to move\nstatus: {snap.status}"
        )
        if rationale:
            candidates = ", ".join(rationale.get("candidate_moves", [])) or "—"
            text = (
                f"[bold #78d2eb]LATEST DECISION[/]\n"
                f"{rationale.get('player')} · ply {rationale.get('ply')}\n"
                f"move: [bold]{rationale.get('move')}[/bold]\n"
                f"candidates: {candidates}\n\n"
                f"{rationale.get('rationale') or 'No rationale supplied.'}\n\n"
                f"expected: {rationale.get('expected_reply') or '—'}\n"
                f"reasoning tokens: {rationale.get('reasoning_tokens', '—')}"
            )
        else:
            text = "[bold #78d2eb]LATEST DECISION[/]\nWaiting for the first move rationale…"
        self.query_one("#decision", Static).update(text)
        events_path = self.live / "series-runner.log"
        size = events_path.stat().st_size if events_path.exists() else 0
        if size != self.last_event_size:
            lines = read_text(events_path).splitlines()
            events = self.query_one("#events", RichLog)
            events.clear()
            events.write("[bold #78d2eb]SERIES[/]")
            for line in lines[-8:]:
                events.write(line)
            self.last_event_size = size


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Single-pane model chess arena")
    parser.add_argument("--games", type=int, default=20)
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--resume-live", action="store_true")
    parser.add_argument("--live-dir", type=Path, default=DEFAULT_LIVE)
    args = parser.parse_args()
    Thunderdome(args.live_dir, args.games, args.start_index, args.resume_live).run()


if __name__ == "__main__":
    main()

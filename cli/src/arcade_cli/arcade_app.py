from __future__ import annotations

import json
import importlib.util
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import chess
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Footer, Header, RichLog, Static
from rich.text import Text

from . import main as arcade
from . import series

ROOT = series.resolve_root()
ENGINE = ROOT / "engine"
DEFAULT_LIVE = Path(os.environ.get("ARCADE_LIVE", ".ai-agent-arcade/live"))


def load_dot_renderer():
    path = ENGINE / "tui_dots.py"
    spec = importlib.util.spec_from_file_location("arcade_dot_renderer", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load dot renderer from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def original_board_frame(renderer, board, moves, white, black, cols, rows, now=None, fly=None):
    renderer.move_list = list(moves)
    ansi = renderer.render(
        board, fly=fly, terminal_size=(cols, rows), now=now, output=False,
        names_override=(white, black), interactive=False,
    )
    return renderer.strip_terminal_controls(ansi)


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


def decision_history(live: Path) -> list[dict]:
    rows = []
    for line in read_text(live / "decision_log.jsonl").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def latest_rationale(live: Path) -> dict | None:
    rows = decision_history(live)
    return rows[-1] if rows else None


def decision_markup(rows: list[dict]) -> str:
    if not rows:
        return "[bold #78d2eb]DECISIONS[/]\nWaiting for the first move rationale…"
    blocks = ["[bold #78d2eb]DECISIONS[/]  [#697386]newest last · j/k scroll · g newest[/]"]
    for row in rows:
        candidates = ", ".join(row.get("candidate_moves", [])) or "—"
        blocks.append(
            f"\n[#697386]ply {row.get('ply')}[/] [bold]{row.get('player')}[/]"
            f"\nmove: [bold #d9f4ff]{row.get('move')}[/]"
            f"\ncandidates: {candidates}"
            f"\n{row.get('rationale') or 'No rationale supplied.'}"
            f"\n[#697386]expected {row.get('expected_reply') or '—'} ·"
            f" reasoning tokens {row.get('reasoning_tokens', '—')}[/]"
        )
    return "\n".join(blocks)


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


class BrailleBoard(Static):
    """Board widget with an original dot-field style and a compact glyph style."""

    GLYPHS = {1: "●", 2: "◆", 3: "▲", 4: "■", 5: "✦", 6: "♚"}
    SPRITES = {
        1: ("  ██  ", " ████ ", "  ██  ", " ████ ", "██████"),
        2: ("  ███ ", " █████", "██ ███", "   ███", " █████"),
        3: ("  ██  ", " ████ ", " ██ █ ", " ████ ", "██████"),
        4: ("██  ██", "██████", " ████ ", " ████ ", "██████"),
        5: ("█ ██ █", "██████", " ████ ", "  ██  ", "██████"),
        6: ("  ██  ", "██████", "  ██  ", " ████ ", "██████"),
    }
    DOT_BITS = ((0x01, 0x02, 0x04, 0x40), (0x08, 0x10, 0x20, 0x80))

    def __init__(self, style: str = "original", **kwargs):
        super().__init__(**kwargs)
        self.phase = 0
        self.style_name = style
        self.board = chess.Board()
        self.white = "WHITE"
        self.black = "BLACK"
        self.moves = []
        self.renderer = load_dot_renderer()
        self.fly_animation = None
        self.replay_moves = []
        self.replay_index = 0
        self.replay_next = 0.0

    def on_mount(self) -> None:
        self.set_interval(0.05, self.tick_frame)

    def tick_frame(self) -> None:
        if self.style_name == "original":
            now = time.monotonic()
            if self.replay_moves and not self.fly_animation and now >= self.replay_next:
                if self.replay_index >= len(self.replay_moves):
                    self.replay_moves = []
                else:
                    before = chess.Board()
                    for san in self.replay_moves[:self.replay_index]:
                        before.push_san(san)
                    move = before.parse_san(self.replay_moves[self.replay_index])
                    after = before.copy(stack=False)
                    after.push(move)
                    self.fly_animation = (now, move, before)
                    self.replay_index += 1
                    self.board = after
                    self.moves = self.replay_moves[:self.replay_index]
                    self.replay_next = now + 0.7
            if self.fly_animation and time.monotonic() - self.fly_animation[0] >= 0.5:
                self.renderer.last_pair = (
                    self.fly_animation[1].from_square,
                    self.fly_animation[1].to_square,
                )
                self.fly_animation = None
            self._paint()

    def start_replay(self) -> None:
        if not self.moves:
            return
        self.replay_moves = list(self.moves)
        self.replay_index = 0
        self.replay_next = 0.0
        self.fly_animation = None
        self.board = chess.Board()
        self.moves = []

    def set_style(self, style: str) -> None:
        self.style_name = style
        self._paint()

    def update_position(self, board: chess.Board, white: str, black: str, moves=None) -> None:
        new_moves = list(moves or [])
        if self.replay_moves:
            return
        if len(new_moves) == len(self.moves) + 1 and new_moves[:-1] == self.moves:
            before = chess.Board()
            for san in self.moves:
                before.push_san(san)
            move = before.parse_san(new_moves[-1])
            self.fly_animation = (time.monotonic(), move, before)
        self.board = board.copy(stack=False)
        self.white = white
        self.black = black
        self.moves = new_moves
        self._paint()

    def _paint(self) -> None:
        if self.style_name == "compact":
            self._paint_compact()
            return
        self._paint_original()

    def _paint_original(self) -> None:
        cols = max(29, self.size.width or 80)
        rows = max(19, self.size.height or 40)
        now = time.monotonic()
        board, fly = self.board, None
        if self.fly_animation:
            started, move, before = self.fly_animation
            elapsed = min(1.0, (now - started) / 0.5)
            smooth = elapsed * elapsed * (3 - 2 * elapsed)
            x0 = chess.square_file(move.from_square) * self.renderer.SQW
            y0 = (7 - chess.square_rank(move.from_square)) * self.renderer.SQH
            x1 = chess.square_file(move.to_square) * self.renderer.SQW
            y1 = (7 - chess.square_rank(move.to_square)) * self.renderer.SQH
            fly = (
                before.piece_at(move.from_square),
                x0 + (x1 - x0) * smooth,
                y0 + (y1 - y0) * smooth,
                move.from_square,
            )
            board = before
        super().update(original_board_frame(
            self.renderer, board, self.moves, self.white, self.black,
            cols=cols, rows=rows, now=now, fly=fly,
        ))

    def _paint_compact(self) -> None:
        text = Text(justify="center")
        text.append(f"{self.black}\n\n", style="bold #f0a046")
        for rank in range(7, -1, -1):
            text.append(f"{rank + 1}  ", style="#697386")
            for file in range(8):
                square = chess.square(file, rank)
                piece = self.board.piece_at(square)
                if piece:
                    glyph = self.GLYPHS[piece.piece_type]
                    style = "bold #d9f4ff" if piece.color else "bold #f0a046"
                    text.append(f" {glyph} ", style=style)
                else:
                    cell = "·" if (file + rank) % 2 else " "
                    text.append(f" {cell} ", style="#33485f")
            text.append("\n")
        text.append("\n   a  b  c  d  e  f  g  h\n", style="#697386")
        text.append(self.white, style="bold #d9f4ff")
        super().update(text)

    def update(self, board: chess.Board, white: str, black: str) -> None:
        self.update_position(board, white, black)


class ArcadeApp(App):
    CSS = """
    Screen { background: #12151c; color: #d0d8e8; }
    Header, Footer { background: #171b24; color: #8a93a6; }
    #body { height: 1fr; }
    #board-wrap { width: 1fr; height: 1fr; align: center middle; border: round #334054; }
    #board { width: auto; height: auto; text-align: center; content-align: center middle; text-style: bold; }
    #side { width: 46; height: 1fr; }
    .panel { border: round #334054; padding: 1 2; margin-left: 1; }
    #match { height: 11; }
    #decisions { height: 1fr; min-height: 16; scrollbar-size: 1 1; }
    #events { height: 9; }
    .title { color: #78d2eb; text-style: bold; }
    """
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("p", "pause", "Pause"),
        ("c", "continue_run", "Continue"),
        ("b", "toggle_board", "Board style"),
        ("r", "replay", "Replay"),
        ("j", "decision_down", "Decision down"),
        ("k", "decision_up", "Decision up"),
        ("g", "decision_newest", "Latest decision"),
        ("G", "decision_oldest", "Oldest decision"),
    ]

    def __init__(
        self,
        live: Path,
        games: int,
        start_index: int,
        resume_live: bool,
        board_style: str = "original",
        config: Path | None = None,
        run_matches: bool = True,
    ):
        super().__init__()
        self.live = live.resolve()
        self.games = games
        self.start_index = start_index
        self.resume_live = resume_live
        self.board_style = board_style
        self.config = config.resolve() if config else None
        self.run_matches = run_matches
        self.process: subprocess.Popen | None = None
        self.paused = False
        self.last_event_size = 0
        self.last_decision_count = 0
        self.decisions_rendered = False
        self.runner_error = ""
        self.runner_error_rendered = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(id="board-wrap"):
                yield BrailleBoard(style=self.board_style, id="board")
            with VerticalScroll(id="side"):
                yield Static(id="match", classes="panel")
                with VerticalScroll(id="decisions", classes="panel", can_focus=True):
                    yield Static(id="decision")
                yield RichLog(id="events", classes="panel", wrap=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "AI AGENT ARCADE"
        self.sub_title = "referee-verified model chess"
        self.live.mkdir(parents=True, exist_ok=True)
        if self.run_matches:
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
        resume = self.resume_live or (
            (self.live / "moves.txt").exists()
            and bool(read_text(self.live / "moves.txt").split())
            and not (self.live / "result.txt").exists()
        )
        if resume:
            command.append("--resume-live")
        if self.config:
            command.extend(("--config", str(self.config)))
        env = {**os.environ, "ARCADE_LIVE": str(self.live)}
        env["AI_AGENT_ARCADE_ROOT"] = str(ROOT)
        self.process = subprocess.Popen(
            command, cwd=ROOT, env=env, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE, text=True, start_new_session=True,
        )

    def stop_runner(self) -> None:
        if not self.process or self.process.poll() is not None:
            return
        os.killpg(self.process.pid, signal.SIGINT)
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait()

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

    def action_toggle_board(self) -> None:
        self.board_style = "compact" if self.board_style == "original" else "original"
        self.query_one("#board", BrailleBoard).set_style(self.board_style)
        self.notify(f"Board style: {self.board_style}")

    def action_replay(self) -> None:
        self.query_one("#board", BrailleBoard).start_replay()

    def action_decision_down(self) -> None:
        self.query_one("#decisions", VerticalScroll).scroll_relative(y=5, animate=False)

    def action_decision_up(self) -> None:
        self.query_one("#decisions", VerticalScroll).scroll_relative(y=-5, animate=False)

    def action_decision_newest(self) -> None:
        self.query_one("#decisions", VerticalScroll).scroll_end(animate=False)

    def action_decision_oldest(self) -> None:
        self.query_one("#decisions", VerticalScroll).scroll_home(animate=False)

    def on_unmount(self) -> None:
        self.stop_runner()

    def refresh_state(self) -> None:
        names = read_text(self.live / "names.txt").split()
        if len(names) != 2 or not (self.live / "moves.txt").exists():
            return
        board, moves = board_from_live(self.live)
        history = decision_history(self.live)
        rationale = history[-1] if history else None
        summary_path = self.live / "series-summary.json"
        summary = json.loads(read_text(summary_path, "{}") or "{}")
        complete = summary.get("games_complete", max(0, self.start_index - 1))
        status = "paused" if self.paused else "running"
        if not self.run_matches and ((self.live / "result.txt").exists() or board.is_game_over(claim_draw=True)):
            status = "complete"
        if self.process and self.process.poll() is not None:
            status = "complete" if self.process.returncode == 0 else f"failed ({self.process.returncode})"
            if self.process.returncode and not self.runner_error and self.process.stderr:
                self.runner_error = self.process.stderr.read().strip()
                if self.runner_error:
                    self.notify(self.runner_error.splitlines()[-1], severity="error", timeout=10)
        snap = Snapshot(
            game=min(complete + 1, self.games), games=self.games,
            white=names[0], black=names[1], ply=len(moves), board=board,
            rationale=rationale, score=score_line(self.live, names[0], names[1], summary), status=status,
        )
        self.query_one("#board", BrailleBoard).update_position(board, snap.white, snap.black, moves)
        turn = snap.white if board.turn else snap.black
        self.query_one("#match", Static).update(
            f"[bold #78d2eb]MATCH[/]\nGame {snap.game}/{snap.games} · ply {snap.ply}\n"
            f"{snap.white} vs {snap.black}\n{snap.score}\n{turn} to move\nstatus: {snap.status}"
        )
        if len(history) != self.last_decision_count or not self.decisions_rendered:
            self.query_one("#decision", Static).update(decision_markup(history))
            self.query_one("#decisions", VerticalScroll).scroll_end(animate=False)
            self.last_decision_count = len(history)
            self.decisions_rendered = True
        events_path = self.live / "series-runner.log"
        size = events_path.stat().st_size if events_path.exists() else 0
        if size != self.last_event_size or (self.runner_error and not self.runner_error_rendered):
            lines = read_text(events_path).splitlines()
            events = self.query_one("#events", RichLog)
            events.clear()
            events.write("[bold #78d2eb]SERIES[/]")
            for line in lines[-8:]:
                events.write(line)
            if self.runner_error:
                events.write(f"[bold red]ERROR[/] {self.runner_error.splitlines()[-1]}")
                self.runner_error_rendered = True
            self.last_event_size = size


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Single-pane model chess arena")
    parser.add_argument("--games", type=int, default=20)
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--resume-live", action="store_true")
    parser.add_argument("--live-dir", type=Path, default=DEFAULT_LIVE)
    parser.add_argument("--config", type=Path, help="TOML matchup configuration")
    parser.add_argument("--view", action="store_true", help="view an existing live directory without starting models")
    parser.add_argument(
        "--board-style",
        choices=("original", "compact"),
        default="original",
        help="original = animated dot field (default); compact = dense glyph grid",
    )
    args = parser.parse_args()
    ArcadeApp(
        args.live_dir,
        args.games,
        args.start_index,
        args.resume_live,
        board_style=args.board_style,
        config=args.config,
        run_matches=not args.view,
    ).run()


if __name__ == "__main__":
    main()

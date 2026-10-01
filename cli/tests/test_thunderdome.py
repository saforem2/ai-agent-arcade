import importlib.util
import signal
from pathlib import Path

import pytest
import chess

pytest.importorskip("textual")

from arcade_cli.arcade_app import (
    ArcadeApp,
    BrailleBoard,
    decision_history,
    load_dot_renderer,
    original_board_frame,
    score_line,
)


def test_score_line_prefers_current_series_summary(tmp_path):
    (tmp_path / "results.txt").write_text("GPT-OSS-120B 1-0 INKLING-BF16\n" * 9)
    summary = {
        "games_complete": 3,
        "wins": {"GPT-OSS-120B": 1, "INKLING-BF16": 0},
        "draws": 2,
    }

    assert score_line(tmp_path, "GPT-OSS-120B", "INKLING-BF16", summary) == (
        "1–0 · 2 draws · 3 complete"
    )


def test_decision_history_keeps_prior_moves(tmp_path):
    rows = [
        {"ply": 1, "player": "A", "move": "e4", "rationale": "Claims the center."},
        {"ply": 2, "player": "B", "move": "e5", "rationale": "Matches the center."},
    ]
    (tmp_path / "decision_log.jsonl").write_text(
        "\n".join(__import__("json").dumps(row) for row in rows) + "\n"
    )

    history = decision_history(tmp_path)

    assert [row["move"] for row in history] == ["e4", "e5"]


@pytest.mark.asyncio
async def test_braille_board_renders_multiple_rows():
    app = ArcadeApp(Path(__file__).resolve().parents[2] / "games/chess/match-009", 20, 1, True)
    app.start_runner = lambda: None
    async with app.run_test(size=(120, 42)) as pilot:
        await pilot.pause()
        board = app.query_one("#board", BrailleBoard)
        board.update_position(chess.Board(), "WHITE", "BLACK")
        lines = str(board.content).splitlines()

        assert len(lines) >= 20
        assert all(f"{rank} " in str(board.content) for rank in range(1, 9))
        assert not any(symbol in str(board.content) for symbol in "♟♞♝♜♛♚")
        assert any("WHITE" in line for line in lines)
        assert any("BLACK" in line for line in lines)
        assert any("⠀" <= char <= "⣿" and char != "⠀" for line in lines for char in line)


@pytest.mark.asyncio
async def test_original_board_keeps_the_full_board_pane_after_content_renders():
    """Auto-sized content used to collapse the board from the pane to 34×21."""
    app = ArcadeApp(Path(__file__).resolve().parents[2] / "games/chess/match-009", 1, 1, True, run_matches=False)
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause()
        board = app.query_one("#board", BrailleBoard)
        board_wrap = app.query_one("#board-wrap")

        assert board.size == board_wrap.size
        assert (board.renderer.CW, board.renderer.CH) == (8, 4)


def test_original_board_uses_canonical_engine_renderer():
    renderer = load_dot_renderer()
    board = chess.Board()

    frame = original_board_frame(
        renderer, board, [], "WHITE", "BLACK", cols=80, rows=40, now=123.0
    )
    ansi = renderer.render(
        board,
        terminal_size=(80, 40),
        now=123.0,
        output=False,
        names_override=("WHITE", "BLACK"),
    )

    assert frame.plain == renderer.strip_terminal_controls(ansi).plain


@pytest.mark.asyncio
async def test_new_move_starts_canonical_fly_animation():
    app = ArcadeApp(Path(__file__).resolve().parents[2] / "games/chess/match-009", 20, 1, True)
    app.start_runner = lambda: None
    async with app.run_test(size=(120, 42)) as pilot:
        await pilot.pause()
        widget = app.query_one("#board", BrailleBoard)
        before = chess.Board()
        after = chess.Board()
        after.push_san("e4")
        widget.update_position(before, "WHITE", "BLACK", [])
        widget.update_position(after, "WHITE", "BLACK", ["e4"])

        assert widget.fly_animation is not None
        assert widget.fly_animation[1].uci() == "e2e4"


@pytest.mark.asyncio
async def test_virtual_clock_drives_replay_deterministically():
    """The recorder swaps in a virtual clock; animation must follow it, not wall time."""
    app = ArcadeApp(Path(__file__).resolve().parents[2] / "games/chess/match-009", 20, 1, True)
    app.start_runner = lambda: None
    async with app.run_test(size=(120, 42)) as pilot:
        await pilot.pause()
        app.refresh_state()
        await pilot.pause()

        widget = app.query_one("#board", BrailleBoard)
        virtual = {"t": 0.0}
        widget.clock = lambda: virtual["t"]
        widget.start_replay()

        widget.tick_frame()
        assert widget.replay_index == 1
        first = widget.fly_animation[1]

        # Mid-flight: still the same move, still animating.
        virtual["t"] = 0.25
        widget.tick_frame()
        assert widget.fly_animation is not None
        assert widget.fly_animation[1] == first

        # Past the 0.5s travel window the move lands and last_pair is set.
        virtual["t"] = 0.6
        widget.tick_frame()
        assert widget.fly_animation is None
        assert widget.renderer.last_pair == (first.from_square, first.to_square)

        # Past the 0.7s cadence the next move starts.
        virtual["t"] = 0.8
        widget.tick_frame()
        assert widget.replay_index == 2
        assert widget.fly_animation[1] != first


@pytest.mark.asyncio
async def test_board_style_can_toggle_between_original_and_compact():
    app = ArcadeApp(
        Path(__file__).resolve().parents[2] / "games/chess/match-009",
        20,
        1,
        True,
        board_style="original",
    )
    app.start_runner = lambda: None
    async with app.run_test(size=(140, 45)) as pilot:
        await pilot.pause()
        assert app.board_style == "original"
        app.action_toggle_board()
        assert app.board_style == "compact"


@pytest.mark.asyncio
async def test_textual_app_renders_single_pane_state():
    live = Path(__file__).resolve().parents[2] / "games/chess/match-009"
    app = ArcadeApp(live, 20, 1, True)
    app.start_runner = lambda: None

    async with app.run_test(size=(120, 42)) as pilot:
        await pilot.pause()
        app.refresh_state()

        assert "GPT-OSS-120B" in str(app.query_one("#match").content)
        assert any(char >= "⠀" and char <= "⣿" for char in str(app.query_one("#board").content))
        assert "DECISIONS" in str(app.query_one("#decision").content)


@pytest.mark.asyncio
async def test_decision_history_is_scrollable_and_navigable():
    live = Path(__file__).resolve().parents[2] / "games/chess/match-009"
    app = ArcadeApp(live, 20, 1, True)
    app.start_runner = lambda: None

    async with app.run_test(size=(120, 42)) as pilot:
        await pilot.pause()

        assert app.query_one("#decisions").can_focus
        assert callable(app.action_decision_down)
        assert callable(app.action_decision_up)


def test_runner_command_forwards_match_config(tmp_path, monkeypatch):
    config = tmp_path / "match.toml"
    config.write_text("version = 1\n")
    captured = {}

    class Process:
        pid = 123

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return Process()

    monkeypatch.setattr("arcade_cli.arcade_app.subprocess.Popen", fake_popen)
    app = ArcadeApp(tmp_path / "live", 3, 1, False, config=config)
    app.start_runner()

    assert captured["command"][-2:] == ["--config", str(config.resolve())]
    assert captured["kwargs"]["start_new_session"] is True


def test_runner_auto_resumes_interrupted_live_game(tmp_path, monkeypatch):
    live = tmp_path / "live"
    live.mkdir()
    (live / "moves.txt").write_text("e4 e5\n")
    (live / "names.txt").write_text("ONE TWO\n")
    captured = {}

    class Process:
        pid = 123

    def fake_popen(command, **kwargs):
        captured["command"] = command
        return Process()

    monkeypatch.setattr("arcade_cli.arcade_app.subprocess.Popen", fake_popen)
    app = ArcadeApp(live, 3, 1, False)
    app.start_runner()

    assert "--resume-live" in captured["command"]


def test_stop_runner_interrupts_process_group_and_reaps(monkeypatch, tmp_path):
    events = []

    class Process:
        pid = 321
        def poll(self): return None
        def wait(self, timeout=None): events.append(("wait", timeout)); return 130

    monkeypatch.setattr("arcade_cli.arcade_app.os.killpg", lambda pid, sig: events.append((pid, sig)))
    app = ArcadeApp(tmp_path / "live", 1, 1, False)
    app.process = Process()

    app.stop_runner()

    assert events[0] == (321, signal.SIGINT)
    assert events[1][0] == "wait"


@pytest.mark.asyncio
async def test_view_only_archive_reports_complete(tmp_path):
    (tmp_path / "names.txt").write_text("WHITE BLACK\n")
    (tmp_path / "moves.txt").write_text("f3 e5 g4 Qh4#\n")
    (tmp_path / "result.txt").write_text("checkmate\n")
    app = ArcadeApp(tmp_path, 1, 1, False, run_matches=False)

    async with app.run_test(size=(120, 42)) as pilot:
        await pilot.pause()
        app.refresh_state()

        assert "status: complete" in str(app.query_one("#match").content)

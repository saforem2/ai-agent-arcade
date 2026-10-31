import importlib.util
import signal
from pathlib import Path

import pytest
from rich.text import Text
from textual.widgets import Static
import chess

pytest.importorskip("textual")

from arcade_cli.arcade_app import (
    ArcadeApp,
    BrailleBoard,
    decision_history,
    load_dot_renderer,
    original_board_frame,
    match_markup,
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


def test_match_markup_restores_material_bar_and_move_history():
    board = chess.Board()
    moves = ["e4", "d5", "exd5", "Qxd5"]
    for san in moves:
        board.push_san(san)

    text = Text.from_markup(match_markup(
        board, moves, "WHITE", "BLACK", 1, 1, "0–0 · 0 draws", "running"
    )).plain

    assert "MATERIAL" in text
    assert "level" in text
    assert "MOVES" in text
    assert "2. BLACK" in text
    assert "Q d8→d5 ×" in text


def test_match_markup_names_material_leader_and_draws_bar():
    board = chess.Board()
    moves = ["e4", "d5", "exd5"]
    for san in moves:
        board.push_san(san)

    text = Text.from_markup(match_markup(
        board, moves, "WHITE", "BLACK", 1, 1, "0–0 · 0 draws", "running"
    )).plain

    assert "WHITE +1" in text
    assert "█" in text
    assert "ahead by 1 point" in text


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
async def test_replay_reveals_match_and_decisions_progressively():
    """A replay must rewind the sidebar too, not sit on the archive's final state."""
    match = Path(__file__).resolve().parents[2] / "games/chess/match-035"
    app = ArcadeApp(match, 1, 1, True, run_matches=False)
    async with app.run_test(size=(150, 46)) as pilot:
        await pilot.pause()
        app.refresh_state()
        await pilot.pause()

        board = app.query_one("#board", BrailleBoard)
        virtual = {"t": 0.0}
        board.clock = lambda: virtual["t"]
        app.start_replay()
        await pilot.pause()

        assert "ply 0" in str(app.query_one("#match", Static).content)
        assert "Waiting for the first move" in str(app.query_one("#decision", Static).content)

        # Two moves in, the sidebar must show exactly those two decisions.
        for step in range(1, 30):
            virtual["t"] = step * 0.05
            board.tick_frame()
            app.refresh_state()
            if board.replay_index == 2 and not board.fly_animation:
                break
        await pilot.pause()

        decisions = str(app.query_one("#decision", Static).content)
        full = decision_history(match)
        assert "ply 2" in decisions
        assert "ply 3" not in decisions
        assert full[0]["rationale"][:30] in decisions
        assert "ply 2" in str(app.query_one("#match", Static).content)


@pytest.mark.asyncio
async def test_reset_key_clears_live_state_and_restarts_the_runner(tmp_path):
    """`R` must abandon the interrupted game and relaunch without --resume-live."""
    live = tmp_path / "live"
    live.mkdir()
    (live / "names.txt").write_text("GPT-OSS-120B INKLING-BF16\n")
    (live / "moves.txt").write_text("e4 e5\n")

    commands = []
    app = ArcadeApp(live, 1, 1, False)
    app.start_runner = lambda: commands.append("start")
    app.stop_runner = lambda: commands.append("stop")

    async with app.run_test(size=(120, 42)) as pilot:
        await pilot.pause()
        commands.clear()
        app.action_reset()
        await pilot.pause()

        assert commands == ["stop", "start"]
        assert (live / "moves.txt").read_text().strip() == ""
        assert list((live / "abandoned").iterdir())


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


def test_match_markup_shows_standings_block_when_complete():
    board = chess.Board()

    text = Text.from_markup(match_markup(
        board, [], "WHITE", "BLACK", 10, 10,
        "6–3 · 1 draws · 10 complete", "complete",
        standings="WHITE won 6/10 games!!! (1 draw)",
    )).plain

    assert "STANDINGS" in text
    assert "WHITE won 6/10 games!!!" in text


def test_match_markup_omits_standings_block_mid_series():
    board = chess.Board()

    text = Text.from_markup(match_markup(
        board, [], "WHITE", "BLACK", 4, 10,
        "2–1 · 0 draws · 3 complete", "running",
    )).plain

    assert "STANDINGS" not in text


def test_match_markup_light_accents_stay_off_pale_cyan():
    board = chess.Board()

    text = match_markup(
        board, [], "WHITE", "BLACK", 1, 1,
        "0–0 · 0 draws", "running", dark=False,
    )

    assert "#78d2eb" not in text
    assert "#1F5BA5" in text


def test_detect_ansi_theme_reads_terminal_background(monkeypatch):
    from arcade_cli.themes import detect_ansi_theme, resolve_theme

    monkeypatch.setenv("COLORFGBG", "0;15")
    assert detect_ansi_theme() == "ansi-light"
    monkeypatch.setenv("COLORFGBG", "15;0")
    assert detect_ansi_theme() == "ansi-dark"
    monkeypatch.delenv("COLORFGBG", raising=False)
    assert detect_ansi_theme() == "ansi-dark"


def test_resolve_theme_prefers_flag_then_env(monkeypatch):
    from arcade_cli.themes import resolve_theme

    monkeypatch.setenv("COLORFGBG", "0;15")
    monkeypatch.setenv("ARCADE_THEME", "pbs-dark")
    assert resolve_theme("ansi-dark") == "ansi-dark"
    assert resolve_theme(None) == "pbs-dark"
    monkeypatch.delenv("ARCADE_THEME", raising=False)
    assert resolve_theme(None) == "ansi-light"


def test_arcade_app_registers_bundled_themes_and_defaults_to_ansi(tmp_path, monkeypatch):
    from arcade_cli.themes import THEME_NAMES

    monkeypatch.delenv("ARCADE_THEME", raising=False)
    monkeypatch.setenv("COLORFGBG", "15;0")
    app = ArcadeApp(tmp_path / "live", 10, 1, False)

    assert app.theme in THEME_NAMES
    assert app.theme == "ansi-dark"
    assert app.is_light is False


@pytest.mark.asyncio
async def test_board_follows_runtime_theme_switch(tmp_path):
    """Switching theme via the palette must repaint the dot field, not just
    the CSS chrome — refresh_state re-derives the background every tick."""
    live = tmp_path / "live"
    live.mkdir()
    (live / "names.txt").write_text("WHITE BLACK\n")
    (live / "moves.txt").write_text("e4 e5\n")
    app = ArcadeApp(live, 1, 1, False, run_matches=False, theme="ansi-dark")
    app.start_runner = lambda: None

    async with app.run_test(size=(120, 42)) as pilot:
        await pilot.pause()
        app.refresh_state()
        widget = app.query_one("#board", BrailleBoard)
        assert widget.dark is True
        assert widget.renderer._palette == "dark"

        app.theme = "ansi-light"
        app.refresh_state()
        await pilot.pause()

        assert app.is_light is True
        assert widget.dark is False
        assert widget.renderer._palette == "light"

        widget.set_style("compact")
        await pilot.pause()

        styles = {span.style for span in widget.content.spans}
        assert any("#0b3d66" in style for style in styles)
        assert not any("#d9f4ff" in style for style in styles)


def test_parse_osc11_background_scales_hex_channels():
    from arcade_cli.themes import parse_osc11_background

    assert parse_osc11_background(b"\x1b]11;rgb:eeee/eeee/eeee\x1b\\") == (238, 238, 238)
    assert parse_osc11_background(b"\x1b]11;rgb:1c/1c/1c\x07") == (28, 28, 28)
    assert parse_osc11_background(b"\x1b]11;rgb:ffff/ffff/ffff\x1b\\") == (255, 255, 255)
    assert parse_osc11_background(b"nothing here") is None


def test_detect_prefers_colorfgbg_over_osc11_probe(monkeypatch):
    import arcade_cli.themes as themes

    monkeypatch.setenv("COLORFGBG", "15;0")
    monkeypatch.setattr(themes, "query_terminal_background", lambda: (238, 238, 238))

    assert themes.detect_ansi_theme() == "ansi-dark"


def test_detect_uses_osc11_luminance_when_colorfgbg_absent(monkeypatch):
    import arcade_cli.themes as themes

    monkeypatch.delenv("COLORFGBG", raising=False)
    monkeypatch.setattr(themes, "query_terminal_background", lambda: (238, 238, 238))
    assert themes.detect_ansi_theme() == "ansi-light"
    monkeypatch.setattr(themes, "query_terminal_background", lambda: (28, 28, 28))
    assert themes.detect_ansi_theme() == "ansi-dark"
    monkeypatch.setattr(themes, "query_terminal_background", lambda: None)
    assert themes.detect_ansi_theme() == "ansi-dark"


def test_read_thinking_reports_elapsed_seconds(tmp_path):
    import time

    from arcade_cli.arcade_app import read_thinking

    assert read_thinking(tmp_path) is None
    (tmp_path / "thinking.txt").write_text(f"MUSE-SPARK-BF16 {time.time() - 42}\n")

    assert read_thinking(tmp_path) == ("MUSE-SPARK-BF16", 42)
    (tmp_path / "thinking.txt").write_text("garbage\n")

    assert read_thinking(tmp_path) is None


def test_match_markup_shows_live_thinking_clock():
    board = chess.Board()

    text = Text.from_markup(match_markup(
        board, [], "WHITE", "BLACK", 1, 20,
        "0–0 · 0 draws", "running",
        thinking=("MUSE-SPARK-BF16", 42),
    )).plain

    assert "thinking: MUSE-SPARK-BF16 42s" in text


def test_match_markup_omits_thinking_clock_when_idle():
    board = chess.Board()

    text = Text.from_markup(match_markup(
        board, [], "WHITE", "BLACK", 1, 20, "0–0 · 0 draws", "running",
    )).plain

    assert "thinking:" not in text


def test_runner_command_forwards_effort_override(tmp_path, monkeypatch):
    captured = {}

    class Process:
        pid = 123

    def fake_popen(command, **kwargs):
        captured["command"] = command
        return Process()

    monkeypatch.setattr("arcade_cli.arcade_app.subprocess.Popen", fake_popen)
    app = ArcadeApp(tmp_path / "live", 3, 1, False, effort="medium")
    app.start_runner()

    assert "--effort" in captured["command"]
    assert captured["command"][captured["command"].index("--effort") + 1] == "medium"


def test_runner_command_omits_effort_by_default(tmp_path, monkeypatch):
    captured = {}

    class Process:
        pid = 123

    def fake_popen(command, **kwargs):
        captured["command"] = command
        return Process()

    monkeypatch.setattr("arcade_cli.arcade_app.subprocess.Popen", fake_popen)
    app = ArcadeApp(tmp_path / "live", 3, 1, False)
    app.start_runner()

    assert "--effort" not in captured["command"]

import importlib.util
from pathlib import Path

import pytest
import chess

pytest.importorskip("textual")

from arcade_cli.thunderdome import BrailleBoard, Thunderdome, decision_history, score_line


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
    app = Thunderdome(Path(__file__).resolve().parents[2] / "games/chess/match-009", 20, 1, True)
    app.start_runner = lambda: None
    async with app.run_test(size=(120, 42)) as pilot:
        await pilot.pause()
        board = app.query_one("#board", BrailleBoard)
        board.update_position(chess.Board(), "WHITE", "BLACK")
        lines = str(board.content).splitlines()

        assert len(lines) == 29
        assert all(len(line) >= 51 for line in lines[2:26])
        assert not any(symbol in str(board.content) for symbol in "♟♞♝♜♛♚")
        assert any("⣿" in line or "⣶" in line for line in lines)
        assert any("WHITE" in line for line in lines)
        assert any("BLACK" in line for line in lines)


@pytest.mark.asyncio
async def test_board_style_can_toggle_between_original_and_compact():
    app = Thunderdome(
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
    app = Thunderdome(live, 20, 1, True)
    app.start_runner = lambda: None

    async with app.run_test(size=(120, 42)) as pilot:
        await pilot.pause()
        app.refresh_state()

        assert "GPT-OSS-120B" in str(app.query_one("#match").content)
        assert "⣿" in str(app.query_one("#board").content)
        assert "DECISIONS" in str(app.query_one("#decision").content)


@pytest.mark.asyncio
async def test_decision_history_is_scrollable_and_navigable():
    live = Path(__file__).resolve().parents[2] / "games/chess/match-009"
    app = Thunderdome(live, 20, 1, True)
    app.start_runner = lambda: None

    async with app.run_test(size=(120, 42)) as pilot:
        await pilot.pause()

        assert app.query_one("#decisions").can_focus
        assert callable(app.action_decision_down)
        assert callable(app.action_decision_up)

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("textual")

from arcade_cli.thunderdome import Thunderdome, score_line


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


@pytest.mark.asyncio
async def test_textual_app_renders_single_pane_state():
    live = Path(__file__).resolve().parents[2] / "games/chess/match-009"
    app = Thunderdome(live, 20, 1, True)
    app.start_runner = lambda: None

    async with app.run_test(size=(120, 42)) as pilot:
        await pilot.pause()
        app.refresh_state()

        assert "GPT-OSS-120B" in str(app.query_one("#match").content)
        assert "♙" in str(app.query_one("#board").content)
        assert "LATEST DECISION" in str(app.query_one("#decision").content)

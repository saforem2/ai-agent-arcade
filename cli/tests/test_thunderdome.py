import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("textual")

from arcade_cli.thunderdome import Thunderdome


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

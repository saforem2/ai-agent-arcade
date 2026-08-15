"""chat_tui.py is shared across games: it must tail the live dir it sits in.

Regression guard for the match-2 room bug — with ARCADE_LIVE unset, the
deployed /tmp/corewar/chat_tui.py silently tailed /tmp/chess/chat.log and the
room showed "nobody has said anything yet" over a live log.
"""
import importlib
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent


def _load(monkeypatch, live):
    if live is None:
        monkeypatch.delenv('ARCADE_LIVE', raising=False)
    else:
        monkeypatch.setenv('ARCADE_LIVE', str(live))
    sys.path.insert(0, str(ENGINE))
    import chat_tui
    return importlib.reload(chat_tui)


def test_default_d_is_script_parent(monkeypatch):
    mod = _load(monkeypatch, None)
    assert mod.D == ENGINE


def test_arcade_live_env_wins(monkeypatch, tmp_path):
    mod = _load(monkeypatch, tmp_path)
    assert mod.D == tmp_path


def test_say_hint_picks_deployed_wrapper(monkeypatch, tmp_path):
    (tmp_path / 'game_cw.sh').write_text('#!/bin/sh\n')
    mod = _load(monkeypatch, tmp_path)
    assert mod.say_hint() == " game_cw.sh say '<message>'"


def test_say_hint_falls_back_to_game_sh(monkeypatch, tmp_path):
    mod = _load(monkeypatch, tmp_path)
    assert mod.say_hint() == " game.sh say '<message>'"

"""Tests for eval.py's story_hint() (game-6 retro backlog item,
docs/seat-feedback-game6.md: "eval.py optional story: one-line color hint
for the booth (log-only)") and its wiring into main()'s printed line.

material_summary()/engine_eval() are pre-existing and untested (this repo's
design-history flags eval.py as having no prior test home) -- out of scope
here; this file covers only the new addition.

Runs as a subprocess (uv run --with chess), matching test_tui_dots.py's
pattern -- the outer pytest env has no chess package installed.
"""
import os
import subprocess
from pathlib import Path

ENGINE = Path(__file__).resolve().parent


def run_probe(live, script):
    full = (
        f"import sys; sys.path.insert(0, {str(ENGINE)!r})\n"
        "import eval as ev, chess\n"
        f"{script}"
    )
    return subprocess.run(
        ["uv", "run", "--quiet", "--with", "chess", "python", "-c", full],
        cwd=live, env={**os.environ, "ARCADE_LIVE": str(live)},
        capture_output=True, text=True,
    )


def test_opening_position_is_opening_and_uncastled(tmp_path):
    script = "print(ev.story_hint(chess.Board()))\n"
    r = run_probe(tmp_path, script)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "opening, mover's king still uncastled"


def test_mover_in_check_is_reported(tmp_path):
    script = (
        "b = chess.Board()\n"
        "for mv in ['e4', 'd5', 'exd5', 'Qxd5', 'Nc3', 'Qe5+']:\n"
        "    b.push_san(mv)\n"
        "assert b.is_check() and b.turn == chess.WHITE, (b.is_check(), b.turn)\n"
        "print(ev.story_hint(b))\n"
    )
    r = run_probe(tmp_path, script)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "opening, mover is in check"


def test_king_left_home_after_castling(tmp_path):
    script = (
        "b = chess.Board()\n"
        "for mv in ['e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'Bc5', 'O-O', 'Nf6']:\n"
        "    b.push_san(mv)\n"
        "assert b.turn == chess.WHITE\n"
        "assert b.king(chess.WHITE) != chess.E1\n"
        "print(ev.story_hint(b))\n"
    )
    r = run_probe(tmp_path, script)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "opening, mover's king has left home"


def test_bare_kings_and_pawns_is_endgame(tmp_path):
    script = (
        "b = chess.Board('8/8/4k3/8/8/4K3/8/8 w - - 0 40')\n"
        "print(ev.story_hint(b))\n"
    )
    r = run_probe(tmp_path, script)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().startswith("endgame, ")


def test_late_fullmove_with_queens_is_middlegame(tmp_path):
    """fullmove_number > 10 alone disqualifies 'opening' even with queens
    still on the board and only a moderate piece count -- the two rules
    (fullmove window AND piece-count floor) both have to hold for 'opening'."""
    script = (
        "b = chess.Board('1k1rbn2/8/8/8/8/8/8/QRRBNK2 w - - 0 15')\n"
        "print(ev.story_hint(b))\n"
    )
    r = run_probe(tmp_path, script)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().startswith("middlegame, ")


def test_main_output_carries_story_segment(tmp_path):
    """End-to-end through main(): the printed line's last pipe segment is
    the story hint, regardless of whether stockfish is installed."""
    (tmp_path / "fen.txt").write_text(chess_start_fen())
    (tmp_path / "names.txt").write_text("KIMI CODEX\n")
    r = run_probe(tmp_path, "ev.main()\n")
    assert r.returncode == 0, r.stderr
    segments = [s.strip() for s in r.stdout.strip().split("|")]
    assert len(segments) == 4
    assert segments[3].startswith("story: opening,")


def chess_start_fen():
    return "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

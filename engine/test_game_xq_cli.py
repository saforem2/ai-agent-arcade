"""Tests for game_xq_cli.py (the player-facing xiangqi wrapper): status,
history, await-turn, and the seat-bound identity hard-refuse (game-5 retro
fix, ported into the xiangqi kit).

Every test runs game_xq_cli.py + ref_xq.py as subprocesses against a pytest
tmp_path with ARCADE_LIVE pointed at it -- never against /tmp/xiangqi.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parent
GAME_XQ_CLI = ENGINE / "game_xq_cli.py"
REF = ENGINE / "ref_xq.py"


@pytest.fixture
def live(tmp_path):
    for fn in ("xiangqi.py", "chat.py"):
        (tmp_path / fn).write_text((ENGINE / fn).read_text())
    (tmp_path / "names.txt").write_text("RED BLACK\n")
    (tmp_path / "seats.txt").write_text("RED white\nBLACK black\n")
    r = run_ref(tmp_path, "init")
    assert r.returncode == 0, r.stderr
    return tmp_path


def _env(live, chess_name=None):
    env = {"ARCADE_LIVE": str(live), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    if chess_name is not None:
        env["CHESS_NAME"] = chess_name
    return env


def run_ref(live, *args):
    return subprocess.run(
        [sys.executable, str(REF), *args],
        cwd=live, env=_env(live), capture_output=True, text=True,
    )


def run_cli(live, *args, chess_name="RED", timeout=30):
    return subprocess.run(
        [sys.executable, str(GAME_XQ_CLI), *args],
        cwd=live, env=_env(live, chess_name), capture_output=True, text=True, timeout=timeout,
    )


def apply_pending(live):
    pending = (live / "pending.txt").read_text()
    r = run_ref(live, "move", pending)
    (live / "pending.txt").unlink(missing_ok=True)
    return r


# ---------------------------------------------------------------------------
# status / history

def test_status_before_any_moves(live):
    r = run_cli(live, "status")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "ply: 0" in out
    assert "side to move: Red" in out
    assert "last move: (none)" in out
    assert "pending: (none)" in out
    assert "gameover: no" in out
    assert "draw offer pending: no" in out


def test_status_reports_pending_and_after_move(live):
    run_cli(live, "submit", "h2e2", chess_name="RED")
    r = run_cli(live, "status", chess_name="BLACK")
    assert "pending: h2e2 (staged by RED)" in r.stdout

    apply_pending(live)
    r = run_cli(live, "status", chess_name="BLACK")
    out = r.stdout
    assert "ply: 1" in out
    assert "side to move: Black" in out
    assert "last move: h2e2" in out
    assert "pending: (none)" in out


def test_status_reports_gameover_after_resignation(live):
    run_cli(live, "resign", chess_name="RED")
    apply_pending(live)
    r = run_cli(live, "status", chess_name="BLACK")
    assert "gameover: yes" in r.stdout
    assert "wins by resignation" in r.stdout


def test_status_reports_draw_offer_pending(live):
    run_cli(live, "offer-draw", chess_name="RED")
    apply_pending(live)
    r = run_cli(live, "status", chess_name="BLACK")
    assert "draw offer pending: yes (from RED)" in r.stdout


def test_history_empty_and_populated(live):
    r = run_cli(live, "history")
    assert "(no moves yet)" in r.stdout

    run_cli(live, "submit", "h2e2", chess_name="RED")
    apply_pending(live)
    run_cli(live, "submit", "h9g7", chess_name="BLACK")
    apply_pending(live)
    run_cli(live, "submit", "c3c4", chess_name="RED")
    apply_pending(live)

    r = run_cli(live, "history")
    assert r.stdout.strip().splitlines() == ["1. h2e2 h9g7", "2. c3c4"]


# ---------------------------------------------------------------------------
# seat-bound identity (game-5 retro fix, ported)

def test_submit_refused_for_unseated_signer(live):
    r = run_cli(live, "submit", "h2e2", chess_name="INTRUDER")
    assert r.returncode == 1
    assert "REFUSED" in r.stdout
    assert "RED (white)" in r.stdout and "BLACK (black)" in r.stdout
    assert not (live / "pending.txt").exists()


def test_submit_allowed_for_seated_signer(live):
    r = run_cli(live, "submit", "h2e2", chess_name="RED")
    assert r.returncode == 0, r.stderr
    assert "STAGED" in r.stdout
    assert (live / "pending.txt").read_text() == "RED\th2e2"


def test_submit_with_say_posts_after_successful_stage(live):
    r = run_cli(live, "submit", "h2e2", "--say", "opening cannon to the center", chess_name="RED")
    assert r.returncode == 0, r.stderr
    assert "STAGED" in r.stdout
    assert "SAID (RED)" in r.stdout and "opening cannon to the center" in r.stdout
    assert (live / "pending.txt").read_text() == "RED\th2e2"
    chat_lines = (live / "chat.log").read_text().splitlines()
    assert any("opening cannon to the center" in ln for ln in chat_lines)


def test_submit_with_say_does_not_post_on_illegal_move(live):
    """--say only posts after a successful stage -- an illegal move must
    never reach the room, matching submit's own STAGED-only-on-success rule."""
    r = run_cli(live, "submit", "z9z9", "--say", "should never post", chess_name="RED")
    assert r.returncode == 1
    assert "ILLEGAL" in r.stdout
    assert "should never post" not in r.stdout
    assert not (live / "chat.log").exists() or "should never post" not in (live / "chat.log").read_text()


def test_resign_refused_for_unseated_signer(live):
    r = run_cli(live, "resign", chess_name="INTRUDER")
    assert r.returncode == 1
    assert "REFUSED" in r.stdout
    assert not (live / "pending.txt").exists()


def test_seat_check_is_a_noop_without_seats_txt(live):
    (live / "seats.txt").unlink()
    r = run_cli(live, "submit", "h2e2", chess_name="ANYONE")
    assert r.returncode == 0, r.stderr
    assert "STAGED" in r.stdout


def test_say_and_show_stay_open_to_unseated_names(live):
    r = run_cli(live, "say", "hello everyone", chess_name="SPECTATOR")
    assert r.returncode == 0, r.stderr
    r = run_cli(live, "show", chess_name="SPECTATOR")
    assert r.returncode == 0, r.stderr


# ---------------------------------------------------------------------------
# await-turn's pure predicate + immediate-return case

def test_my_turn_or_over_pure_predicate(tmp_path):
    for fn in ("game_xq_cli.py", "xiangqi.py", "chat.py"):
        (tmp_path / fn).write_text((ENGINE / fn).read_text())
    script = (
        f"import sys; sys.path.insert(0, {str(tmp_path)!r})\n"
        "from xiangqi import XiangqiBoard\n"
        "import game_xq_cli\n"
        "b = XiangqiBoard()\n"  # starting position, red to move
        "assert game_xq_cli.my_turn_or_over(b, 'white') is True\n"
        "assert game_xq_cli.my_turn_or_over(b, 'black') is False\n"
        "b.push('h2e2')\n"  # now black to move
        "assert game_xq_cli.my_turn_or_over(b, 'black') is True\n"
        "assert game_xq_cli.my_turn_or_over(b, 'white') is False\n"
        "print('OK')\n"
    )
    r = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env={"ARCADE_LIVE": str(tmp_path), "PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "OK" in r.stdout


def test_await_turn_returns_immediately_when_already_my_turn(live):
    r = run_cli(live, "await-turn", chess_name="RED", timeout=10)
    assert r.returncode == 0, r.stderr
    assert "Side to move: RED (Red)" in r.stdout
    assert "Legal moves:" in r.stdout


# ---------------------------------------------------------------------------
# pieces-remaining material tally

def test_show_prints_material_tally_at_start(live):
    r = run_cli(live, "show")
    assert r.returncode == 0, r.stderr
    assert "Material: RED K A×2 B×2 N×2 R×2 C×2 P×5  |  BLACK K A×2 B×2 N×2 R×2 C×2 P×5" in r.stdout


def test_material_tally_reflects_a_capture(live):
    run_cli(live, "submit", "h2e2", chess_name="RED")
    apply_pending(live)
    run_cli(live, "submit", "h9g7", chess_name="BLACK")
    apply_pending(live)
    run_cli(live, "submit", "e2e6", chess_name="RED")   # cannon takes the e6 black soldier
    apply_pending(live)
    r = run_cli(live, "show")
    assert "BLACK K A×2 B×2 N×2 R×2 C×2 P×4" in r.stdout


# ---------------------------------------------------------------------------
# numbered menu + submit by number

def test_show_prints_numbered_menu(live):
    r = run_cli(live, "show")
    assert "Menu (submit by number or by move text):" in r.stdout
    assert "  1. " in r.stdout


def test_submit_by_menu_number_stages_the_right_move(live):
    shown = run_cli(live, "show", chess_name="RED")
    legal_line = next(l for l in shown.stdout.splitlines() if l.startswith("Legal moves:"))
    first_move = legal_line.split(":", 1)[1].split()[0]
    r = run_cli(live, "submit", "1", chess_name="RED")
    assert r.returncode == 0, r.stderr
    assert f"STAGED: {first_move}" in r.stdout
    assert (live / "pending.txt").read_text() == f"RED\t{first_move}"


def test_submit_by_menu_number_refuses_when_stale(live):
    """HARD SAFETY REQUIREMENT: a numeric submit must be refused, not
    silently resolved to a different move, if the ply advanced since the
    menu was printed."""
    run_cli(live, "show", chess_name="RED")   # menu printed at ply 0
    run_cli(live, "submit", "h2e2", chess_name="RED")
    apply_pending(live)                        # ply is now 1
    r = run_cli(live, "submit", "1", chess_name="BLACK")
    assert r.returncode == 1
    assert "ILLEGAL" in r.stdout
    assert "stale menu" in r.stdout
    assert not (live / "pending.txt").exists()


def test_submit_by_menu_number_refuses_without_a_menu_on_record(live):
    r = run_cli(live, "submit", "1", chess_name="RED")
    assert r.returncode == 1
    assert "no legal-move menu on record" in r.stdout


def test_submit_by_menu_number_out_of_range(live):
    run_cli(live, "show", chess_name="RED")
    r = run_cli(live, "submit", "999", chess_name="RED")
    assert r.returncode == 1
    assert "not a valid menu number" in r.stdout


# ---------------------------------------------------------------------------
# flying-general exposure note (xiangqi-only)

def test_show_warns_when_generals_share_a_file_with_one_screen(live):
    (live / "fen.txt").write_text("4k4/9/9/9/4P4/9/9/9/9/4K4 w - - 0 1\n")
    r = run_cli(live, "show")
    assert r.returncode == 0, r.stderr
    assert "NOTE: the generals share file e" in r.stdout
    assert "pinned to the file" in r.stdout


def test_show_does_not_warn_at_the_starting_position(live):
    r = run_cli(live, "show")
    assert "NOTE: the generals share file" not in r.stdout


# ---------------------------------------------------------------------------
# STAGED -> APPLIED / REJECTED

def test_status_reports_staged_before_applied(live):
    run_cli(live, "submit", "h2e2", chess_name="RED")
    r = run_cli(live, "status", chess_name="RED")
    assert "STAGED: h2e2" in r.stdout
    assert "still awaiting the referee" in r.stdout


def test_status_reports_applied_derived_from_moves_txt(live):
    """The core requirement: APPLIED must come from moves.txt, not from
    whatever submit() staged."""
    run_cli(live, "submit", "h2e2", chess_name="RED")
    apply_pending(live)
    r = run_cli(live, "status", chess_name="RED")
    assert "APPLIED: h2e2 confirmed as submitted, ply 1." in r.stdout
    assert "Black to move now." in r.stdout
    assert "FEN:" in r.stdout
    assert "MISMATCH" not in r.stdout


def test_await_turn_reports_applied_transition_of_own_last_move(live):
    """await-turn is the natural home for this: when it returns after the
    opponent replies, it must report the caller's own previous move as
    APPLIED, not just announce whose turn it is."""
    run_cli(live, "submit", "h2e2", chess_name="RED")
    apply_pending(live)
    run_cli(live, "submit", "h9g7", chess_name="BLACK")
    apply_pending(live)
    r = run_cli(live, "await-turn", chess_name="RED", timeout=10)
    assert r.returncode == 0, r.stderr
    assert "APPLIED: h2e2 confirmed as submitted, ply 1." in r.stdout


def test_status_reports_rejected_when_pending_is_cleared_without_a_move_landing(live):
    """REJECTED must be distinguishable from "not yet applied": pending.txt
    being gone is not enough on its own -- moves.txt must also show the move
    never landed. Simulates a referee rejection (the host's `rm -f
    pending.txt` runs after ref_xq.py exits nonzero either way)."""
    run_cli(live, "submit", "h2e2", chess_name="RED")
    (live / "pending.txt").unlink()   # referee rejected it; host cleared pending.txt
    r = run_cli(live, "status", chess_name="RED")
    assert "REJECTED: h2e2 was not applied" in r.stdout


def test_status_reports_applied_mismatch_when_a_different_move_landed(live):
    """The adversarial case this whole feature exists for: what actually got
    applied at the ply this player's move was destined for differs from what
    they staged. Simulated by staging h2e2, then racing pending.txt to a
    different move before it gets applied."""
    run_cli(live, "submit", "h2e2", chess_name="RED")
    (live / "pending.txt").write_text("RED\tc3c4")   # something else got applied instead
    apply_pending(live)
    r = run_cli(live, "status", chess_name="RED")
    assert "APPLIED MISMATCH" in r.stdout
    assert "'h2e2'" in r.stdout and "'c3c4'" in r.stdout
    assert "ply 1" in r.stdout


def test_status_silent_for_a_name_that_never_staged_anything(live):
    r = run_cli(live, "status", chess_name="SPECTATOR")
    assert "your last submission" not in r.stdout


def test_applied_report_resign(live):
    run_cli(live, "resign", chess_name="RED")
    apply_pending(live)
    r = run_cli(live, "status", chess_name="RED")
    assert "APPLIED: resign confirmed" in r.stdout
    assert "wins by resignation" in r.stdout


def test_applied_draw_offer_reports_cleared_after_opponent_plays_on(live):
    run_cli(live, "submit", "h2e2", chess_name="RED")
    apply_pending(live)                       # black to move
    run_cli(live, "offer-draw", chess_name="RED")
    apply_pending(live)
    run_cli(live, "submit", "h9g7", chess_name="BLACK")
    apply_pending(live)                       # clears RED's live offer
    r = run_cli(live, "status", chess_name="RED")
    assert "CLEARED: offer-draw" in r.stdout
    assert "applied, then cleared when play continued" in r.stdout
    assert "REJECTED: offer-draw" not in r.stdout

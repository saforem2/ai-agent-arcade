"""Tests for game_cli.py (the player-facing chess wrapper): status, history,
await-turn, and the seat-bound identity hard-refuse (game-5 retro fix).

Every test runs game_cli.py + ref.py as subprocesses against a pytest
tmp_path with ARCADE_LIVE pointed at it -- never against /tmp/chess.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parent
GAME_CLI = ENGINE / "game_cli.py"
REF = ENGINE / "ref.py"


@pytest.fixture
def live(tmp_path):
    (tmp_path / "chat.py").write_text((ENGINE / "chat.py").read_text())
    (tmp_path / "names.txt").write_text("WHITE BLACK\n")
    (tmp_path / "seats.txt").write_text("WHITE white\nBLACK black\n")
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
        ["uv", "run", "--quiet", "--with", "chess", "python", str(REF), *args],
        cwd=live, env=_env(live), capture_output=True, text=True,
    )


def run_cli(live, *args, chess_name="WHITE", timeout=30):
    return subprocess.run(
        ["uv", "run", "--quiet", "--with", "chess", "python", str(GAME_CLI), *args],
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
    assert "side to move: White" in out
    assert "last move: (none)" in out
    assert "pending: (none)" in out
    assert "gameover: no" in out
    assert "draw offer pending: no" in out


def test_status_reports_pending_and_after_move(live):
    run_cli(live, "submit", "e4", chess_name="WHITE")
    r = run_cli(live, "status", chess_name="BLACK")
    assert "pending: e4 (staged by WHITE)" in r.stdout

    apply_pending(live)
    r = run_cli(live, "status", chess_name="BLACK")
    out = r.stdout
    assert "ply: 1" in out
    assert "side to move: Black" in out
    assert "last move: e4" in out
    assert "pending: (none)" in out


def test_status_reports_gameover_after_resignation(live):
    run_cli(live, "resign", chess_name="WHITE")
    apply_pending(live)
    r = run_cli(live, "status", chess_name="BLACK")
    assert "gameover: yes" in r.stdout
    assert "wins by resignation" in r.stdout


def test_status_reports_draw_offer_pending(live):
    run_cli(live, "offer-draw", chess_name="WHITE")
    apply_pending(live)
    r = run_cli(live, "status", chess_name="BLACK")
    assert "draw offer pending: yes (from WHITE)" in r.stdout


def test_history_empty_and_populated(live):
    r = run_cli(live, "history")
    assert "(no moves yet)" in r.stdout

    run_cli(live, "submit", "e4", chess_name="WHITE")
    apply_pending(live)
    run_cli(live, "submit", "e5", chess_name="BLACK")
    apply_pending(live)
    run_cli(live, "submit", "Nf3", chess_name="WHITE")
    apply_pending(live)

    r = run_cli(live, "history")
    assert r.stdout.strip().splitlines() == ["1. e4 e5", "2. Nf3"]


# ---------------------------------------------------------------------------
# seat-bound identity (game-5 retro fix)

def test_submit_refused_for_unseated_signer(live):
    r = run_cli(live, "submit", "e4", chess_name="INTRUDER")
    assert r.returncode == 1
    assert "REFUSED" in r.stdout
    assert "WHITE (white)" in r.stdout and "BLACK (black)" in r.stdout
    assert not (live / "pending.txt").exists()


def test_submit_allowed_for_seated_signer(live):
    r = run_cli(live, "submit", "e4", chess_name="WHITE")
    assert r.returncode == 0, r.stderr
    assert "STAGED" in r.stdout
    assert (live / "pending.txt").read_text() == "WHITE\te4"


def test_submit_with_say_posts_after_successful_stage(live):
    r = run_cli(live, "submit", "e4", "--say", "opening with the king pawn", chess_name="WHITE")
    assert r.returncode == 0, r.stderr
    assert "STAGED" in r.stdout
    assert "SAID (WHITE)" in r.stdout and "opening with the king pawn" in r.stdout
    assert (live / "pending.txt").read_text() == "WHITE\te4"
    chat_lines = (live / "chat.log").read_text().splitlines()
    assert any("opening with the king pawn" in ln for ln in chat_lines)


def test_submit_with_say_does_not_post_on_illegal_move(live):
    """--say only posts after a successful stage -- an illegal move must
    never reach the room, matching submit's own STAGED-only-on-success rule."""
    r = run_cli(live, "submit", "z9z9", "--say", "should never post", chess_name="WHITE")
    assert r.returncode == 1
    assert "ILLEGAL" in r.stdout
    assert "should never post" not in r.stdout
    assert not (live / "chat.log").exists() or "should never post" not in (live / "chat.log").read_text()


def test_resign_refused_for_unseated_signer(live):
    r = run_cli(live, "resign", chess_name="INTRUDER")
    assert r.returncode == 1
    assert "REFUSED" in r.stdout
    assert not (live / "pending.txt").exists()


def test_offer_draw_and_accept_draw_refused_for_unseated_signer(live):
    r = run_cli(live, "offer-draw", chess_name="INTRUDER")
    assert r.returncode == 1
    assert "REFUSED" in r.stdout
    r = run_cli(live, "accept-draw", chess_name="INTRUDER")
    assert r.returncode == 1
    assert "REFUSED" in r.stdout


def test_seat_check_is_a_noop_without_seats_txt(live):
    """Older deployed matches (or manual/dev use) may not have seats.txt --
    the hard-refuse must not lock everyone out when the file is simply
    absent."""
    (live / "seats.txt").unlink()
    r = run_cli(live, "submit", "e4", chess_name="ANYONE")
    assert r.returncode == 0, r.stderr
    assert "STAGED" in r.stdout


def test_say_and_show_stay_open_to_unseated_names(live):
    """show/say/chat are spectator-open -- only submit/resign/offer-draw/
    accept-draw are seat-gated."""
    r = run_cli(live, "say", "hello everyone", chess_name="SPECTATOR")
    assert r.returncode == 0, r.stderr
    r = run_cli(live, "show", chess_name="SPECTATOR")
    assert r.returncode == 0, r.stderr


# ---------------------------------------------------------------------------
# await-turn's pure predicate (no poll loop -- see engine's own D-import
# fragility note in test_ref_xq.py: ARCADE_LIVE is pinned to ENGINE itself so
# `import chat` resolves the real engine/chat.py, never /tmp/chess)

def test_my_turn_or_over_pure_predicate():
    script = (
        f"import sys; sys.path.insert(0, {str(ENGINE)!r})\n"
        "import chess, game_cli\n"
        "b = chess.Board()\n"  # starting position, White to move
        "assert game_cli.my_turn_or_over(b, 'white') is True\n"
        "assert game_cli.my_turn_or_over(b, 'black') is False\n"
        "b.push_san('e4')\n"  # now Black to move
        "assert game_cli.my_turn_or_over(b, 'black') is True\n"
        "assert game_cli.my_turn_or_over(b, 'white') is False\n"
        "print('OK')\n"
    )
    r = subprocess.run(
        ["uv", "run", "--quiet", "--with", "chess", "python", "-c", script],
        env={"ARCADE_LIVE": str(ENGINE), "PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "OK" in r.stdout


def test_my_turn_or_over_true_when_game_over_regardless_of_role():
    script = (
        f"import sys; sys.path.insert(0, {str(ENGINE)!r})\n"
        "import chess, game_cli\n"
        "b = chess.Board('rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3')\n"
        "assert b.is_checkmate()\n"
        "assert game_cli.my_turn_or_over(b, 'white') is True\n"
        "assert game_cli.my_turn_or_over(b, 'black') is True\n"
        "print('OK')\n"
    )
    r = subprocess.run(
        ["uv", "run", "--quiet", "--with", "chess", "python", "-c", script],
        env={"ARCADE_LIVE": str(ENGINE), "PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "OK" in r.stdout


def test_await_turn_returns_immediately_when_already_my_turn(live):
    """await-turn's poll loop must not sleep at all when the condition is
    already satisfied on the first check -- exercised end to end (not just
    the pure predicate) with a short subprocess timeout as a tripwire against
    an accidental sleep."""
    r = run_cli(live, "await-turn", chess_name="WHITE", timeout=10)
    assert r.returncode == 0, r.stderr
    assert "Side to move: White" in r.stdout
    assert "Legal moves:" in r.stdout


# ---------------------------------------------------------------------------
# pieces-remaining material tally

def test_show_prints_material_tally_at_start(live):
    r = run_cli(live, "show")
    assert r.returncode == 0, r.stderr
    assert "Material: WHITE K Q R×2 B×2 N×2 P×8  |  BLACK K Q R×2 B×2 N×2 P×8" in r.stdout


def test_material_tally_reflects_a_capture(live):
    run_cli(live, "submit", "e4", chess_name="WHITE")
    apply_pending(live)
    run_cli(live, "submit", "d5", chess_name="BLACK")
    apply_pending(live)
    run_cli(live, "submit", "exd5", chess_name="WHITE")
    apply_pending(live)
    r = run_cli(live, "show")
    assert "BLACK K Q R×2 B×2 N×2 P×7" in r.stdout


# ---------------------------------------------------------------------------
# numbered menu + submit by number

def test_show_prints_numbered_menu(live):
    r = run_cli(live, "show")
    assert "Menu (submit by number or by move text):" in r.stdout
    assert "  1. " in r.stdout


def test_submit_by_menu_number_stages_the_right_move(live):
    shown = run_cli(live, "show", chess_name="WHITE")
    legal_line = next(l for l in shown.stdout.splitlines() if l.startswith("Legal moves:"))
    first_san = legal_line.split(":", 1)[1].split()[0]
    r = run_cli(live, "submit", "1", chess_name="WHITE")
    assert r.returncode == 0, r.stderr
    assert f"STAGED: {first_san}" in r.stdout
    assert (live / "pending.txt").read_text() == f"WHITE\t{first_san}"


def test_submit_by_menu_number_refuses_when_stale(live):
    """HARD SAFETY REQUIREMENT: a numeric submit must be refused, not
    silently resolved to a different move, if the ply advanced since the
    menu was printed."""
    run_cli(live, "show", chess_name="WHITE")   # menu printed at ply 0
    run_cli(live, "submit", "e4", chess_name="WHITE")
    apply_pending(live)                          # ply is now 1
    r = run_cli(live, "submit", "1", chess_name="BLACK")
    assert r.returncode == 1
    assert "ILLEGAL" in r.stdout
    assert "stale menu" in r.stdout
    assert not (live / "pending.txt").exists()


def test_submit_by_menu_number_refuses_without_a_menu_on_record(live):
    r = run_cli(live, "submit", "1", chess_name="WHITE")
    assert r.returncode == 1
    assert "no legal-move menu on record" in r.stdout


def test_submit_by_menu_number_out_of_range(live):
    run_cli(live, "show", chess_name="WHITE")
    r = run_cli(live, "submit", "999", chess_name="WHITE")
    assert r.returncode == 1
    assert "not a valid menu number" in r.stdout


# ---------------------------------------------------------------------------
# STAGED -> APPLIED / REJECTED

def test_status_reports_staged_before_applied(live):
    run_cli(live, "submit", "e4", chess_name="WHITE")
    r = run_cli(live, "status", chess_name="WHITE")
    assert "STAGED: e4" in r.stdout
    assert "still awaiting the referee" in r.stdout


def test_status_reports_applied_derived_from_moves_txt(live):
    """The core requirement: APPLIED must come from moves.txt, not from
    whatever submit() staged -- confirmed here by checking that the reported
    FEN/ply/turn are all reconstructed from the log."""
    run_cli(live, "submit", "e4", chess_name="WHITE")
    apply_pending(live)
    r = run_cli(live, "status", chess_name="WHITE")
    assert "APPLIED: e4 confirmed as submitted, ply 1." in r.stdout
    assert "Black to move now." in r.stdout
    assert "FEN: rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1" in r.stdout
    assert "MISMATCH" not in r.stdout


def test_await_turn_reports_applied_transition_of_own_last_move(live):
    """await-turn is the natural home for this: when it returns after the
    opponent replies, it must report the caller's own previous move as
    APPLIED, not just announce whose turn it is."""
    run_cli(live, "submit", "e4", chess_name="WHITE")
    apply_pending(live)
    run_cli(live, "submit", "e5", chess_name="BLACK")
    apply_pending(live)
    r = run_cli(live, "await-turn", chess_name="WHITE", timeout=10)
    assert r.returncode == 0, r.stderr
    assert "APPLIED: e4 confirmed as submitted, ply 1." in r.stdout


def test_status_reports_rejected_when_pending_is_cleared_without_a_move_landing(live):
    """REJECTED must be distinguishable from "not yet applied": pending.txt
    being gone is not enough on its own -- moves.txt must also show the move
    never landed. Simulates a referee rejection (the host's `rm -f
    pending.txt` runs after ref.py exits nonzero either way) without needing
    to reproduce every individual referee-side rejection path."""
    run_cli(live, "submit", "e4", chess_name="WHITE")
    (live / "pending.txt").unlink()   # referee rejected it; host cleared pending.txt
    r = run_cli(live, "status", chess_name="WHITE")
    assert "REJECTED: e4 was not applied" in r.stdout


def test_status_reports_applied_mismatch_when_a_different_move_landed(live):
    """The adversarial case this whole feature exists for: what actually got
    applied at the ply this player's move was destined for differs from what
    they staged. Simulated by staging e4, then racing pending.txt to a
    different move before it gets applied (the WHITE-signed overwrite is
    exactly what a client-side double-submit race would produce)."""
    run_cli(live, "submit", "e4", chess_name="WHITE")
    (live / "pending.txt").write_text("WHITE\tNf3")   # something else got applied instead
    apply_pending(live)
    r = run_cli(live, "status", chess_name="WHITE")
    assert "APPLIED MISMATCH" in r.stdout
    assert "'e4'" in r.stdout and "'Nf3'" in r.stdout
    assert "ply 1" in r.stdout


def test_status_silent_for_a_name_that_never_staged_anything(live):
    r = run_cli(live, "status", chess_name="SPECTATOR")
    assert "your last submission" not in r.stdout


def test_applied_report_resign(live):
    run_cli(live, "resign", chess_name="WHITE")
    apply_pending(live)
    r = run_cli(live, "status", chess_name="WHITE")
    assert "APPLIED: resign confirmed" in r.stdout
    assert "wins by resignation" in r.stdout


def test_applied_draw_offer_reports_cleared_after_opponent_plays_on(live):
    run_cli(live, "submit", "e4", chess_name="WHITE")
    apply_pending(live)                       # black to move
    run_cli(live, "offer-draw", chess_name="WHITE")
    apply_pending(live)
    run_cli(live, "submit", "e5", chess_name="BLACK")
    apply_pending(live)                       # clears WHITE's live offer
    r = run_cli(live, "status", chess_name="WHITE")
    assert "CLEARED: offer-draw" in r.stdout
    assert "applied, then cleared when play continued" in r.stdout
    assert "REJECTED: offer-draw" not in r.stdout

"""Tests for ref_xq.py. Run with: uv run --with pytest pytest test_ref_xq.py

Every test runs ref_xq.py as a subprocess against a pytest tmp_path with
ARCADE_LIVE pointed at it — never against /tmp/chess or /tmp/xiangqi.
"""
import subprocess
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parent
REF = ENGINE / "ref_xq.py"


@pytest.fixture
def live(tmp_path):
    (tmp_path / "chat.py").write_text((ENGINE / "chat.py").read_text())
    (tmp_path / "names.txt").write_text("RED BLACK\n")
    return tmp_path


def run(live, *args):
    return subprocess.run(
        [sys.executable, str(REF), *args],
        cwd=live, env={"ARCADE_LIVE": str(live), "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True,
    )


def init(live, force=False):
    args = ["init"] + (["--force"] if force else [])
    r = run(live, *args)
    assert r.returncode == 0, r.stderr
    return r


def move(live, who, iccs):
    return run(live, "move", f"{who}\t{iccs}" if who else iccs)


def test_arcade_live_propagates_to_chat_module(live):
    """chat.py resolves its own D independently (default /tmp/chess) -- ref_xq.py
    must setdefault ARCADE_LIVE onto os.environ before importing chat so the two
    modules always agree on the live dir. Import-only, no ref_xq CLI dispatch."""
    script = (
        f"import sys; sys.path.insert(0, {str(ENGINE)!r})\n"
        "import ref_xq, chat\n"
        "assert ref_xq.D == chat.D, (ref_xq.D, chat.D)\n"
        "print('OK')\n"
    )
    r = subprocess.run([sys.executable, "-c", script], cwd=live,
                        env={"ARCADE_LIVE": str(live), "PATH": "/usr/bin:/bin"},
                        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "OK" in r.stdout


def test_arcade_live_default_propagates_when_unset():
    """Reproduces the actual regression: with ARCADE_LIVE unset entirely,
    ref_xq.py defaults to /tmp/xiangqi and chat.py must not silently default
    to /tmp/chess instead. Import-only (no file I/O happens on import), so
    this is safe despite touching the /tmp/xiangqi default path in-process.

    FRAGILITY: this test is read-only (it never writes to /tmp/xiangqi
    itself), but `sys.path.insert(0, str(D))` inside ref_xq.py means the
    subprocess's `import chat` resolves to whatever chat.py -- if any --
    already sits in the real /tmp/xiangqi at the moment this runs, not
    necessarily engine/chat.py. If some other process has deployed stub or
    partial files there (e.g. a CLI test that didn't mock its default-live-dir
    path and actually ran cmd_start's deploy loop against the literal
    default), this test fails on THAT contamination, not on a ref_xq.py bug --
    confirmed the actual cause of a real failure here (AttributeError: module
    'chat' has no attribute 'D', from a `# stub chat.py` placeholder). The
    fix for that class of bug lives in whichever test was writing to
    /tmp/xiangqi (see arcade/cli/tests/test_cli.py's now-rewritten
    test_xiangqi_start_falls_back_to_own_default_live_dir), not here."""
    script = (
        f"import sys; sys.path.insert(0, {str(ENGINE)!r})\n"
        "from pathlib import Path\n"
        "import ref_xq, chat\n"
        "assert ref_xq.D == chat.D == Path('/tmp/xiangqi'), (ref_xq.D, chat.D)\n"
        "print('OK')\n"
    )
    env = {"PATH": "/usr/bin:/bin"}  # ARCADE_LIVE deliberately absent
    r = subprocess.run([sys.executable, "-c", script], env=env,
                        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "OK" in r.stdout


def test_init_writes_starting_position(live):
    init(live)
    assert (live / "moves.txt").read_text() == ""
    fen = (live / "fen.txt").read_text().strip()
    assert fen.startswith("rnbakabnr/9/1c5c1/p1p1p1p1p")
    assert " w " in fen


def test_init_refuses_over_nonempty_log_without_force(live):
    init(live)
    r = move(live, "RED", "h2e2")
    assert r.returncode == 0
    r = run(live, "init")
    assert r.returncode == 5
    assert "REFUSING" in r.stderr
    # log untouched
    assert (live / "moves.txt").read_text().strip() == "h2e2"


def test_init_force_overrides(live):
    init(live)
    move(live, "RED", "h2e2")
    (live / "stage_log.txt").write_text("old receipt\n")
    (live / "menu.txt").write_text("17\n")
    r = run(live, "init", "--force")
    assert r.returncode == 0
    assert (live / "moves.txt").read_text() == ""
    assert not (live / "stage_log.txt").exists()
    assert not (live / "menu.txt").exists()


def test_legal_move_appends_and_updates_fen(live):
    init(live)
    r = move(live, "RED", "h2e2")
    assert r.returncode == 0
    assert r.stdout.startswith("OK h2e2 |")
    assert (live / "moves.txt").read_text().strip() == "h2e2"
    assert " b " in (live / "fen.txt").read_text()


def test_illegal_move_rejected_and_not_appended(live):
    init(live)
    # e0e3 moves the general 3 squares — well outside its one-step palace range
    r = move(live, "RED", "e0e3")
    assert r.returncode == 1
    assert r.stdout.strip() == "ILLEGAL"
    assert (live / "moves.txt").read_text() == ""


def test_malformed_move_rejected(live):
    init(live)
    r = move(live, "RED", "zzzz")
    assert r.returncode == 1
    assert r.stdout.strip() == "ILLEGAL"


def test_wrong_author_rejected(live):
    init(live)
    r = move(live, "BLACK", "h2e2")   # it's red's move first
    assert r.returncode == 4
    assert "WRONG AUTHOR" in r.stderr
    assert (live / "moves.txt").read_text() == ""


def test_unsigned_move_skips_author_check(live):
    init(live)
    r = move(live, None, "h2e2")
    assert r.returncode == 0


def test_alternating_signed_moves_succeed(live):
    init(live)
    assert move(live, "RED", "h2e2").returncode == 0
    assert move(live, "BLACK", "h9g7").returncode == 0
    assert (live / "moves.txt").read_text().strip() == "h2e2 h9g7"


def test_verify_matches_replay(live):
    init(live)
    move(live, "RED", "h2e2")
    r = run(live, "verify")
    assert r.returncode == 0
    assert "OK verified 1 plies" in r.stdout


def test_corrupt_fen_triggers_tamper_halt(live):
    init(live)
    move(live, "RED", "h2e2")
    (live / "fen.txt").write_text("not a real fen\n")
    r = run(live, "verify")
    assert r.returncode == 3
    assert "TAMPER DETECTED" in r.stderr
    assert (live / "TAMPER.txt").exists()
    assert "not a valid xiangqi FEN" in (live / "TAMPER.txt").read_text()


def test_mismatched_but_valid_fen_triggers_tamper_halt(live):
    init(live)
    move(live, "RED", "h2e2")
    # a well-formed but wrong FEN (starting position, one ply behind reality)
    from xiangqi import STARTING_FEN
    (live / "fen.txt").write_text(STARTING_FEN + "\n")
    r = run(live, "verify")
    assert r.returncode == 3
    assert "TAMPER DETECTED" in r.stderr


def test_move_refused_while_halted(live):
    init(live)
    move(live, "RED", "h2e2")
    (live / "fen.txt").write_text("garbage\n")
    run(live, "verify")  # halts
    r = move(live, "BLACK", "h9g7")
    assert r.returncode == 3
    assert "halted" in r.stderr


def test_resolve_clears_halt_and_rebuilds_fen(live):
    init(live)
    move(live, "RED", "h2e2")
    (live / "fen.txt").write_text("garbage\n")
    run(live, "verify")
    assert (live / "TAMPER.txt").exists()
    r = run(live, "resolve")
    assert r.returncode == 0
    assert not (live / "TAMPER.txt").exists()
    assert " b " in (live / "fen.txt").read_text()


def test_scripted_checkmate_reports_gameover(live):
    """A real 38-ply random game (found offline via xiangqi.py's own legal_moves,
    replayed here move by move through the referee) that ends in checkmate —
    exercises full-log replay plus the xiangqi-specific 'no legal moves loses'
    scoring (winner is name-carrying '0-1'/'1-0', chess-style, red=white seat)."""
    init(live)
    moves = ("b2b9 a9b9 h2h9 i9h9 c3c4 b7b5 d0e1 f9e8 e0d0 h7h2 a0a2 h2h8 "
             "a2f2 h8i8 f2i2 b5b4 i2a2 i8i3 i0i3 b4a4 i3i6 b9b2 i6i9 h9h0 "
             "i9g9 e8f9 g9f9 e9f9 a2b2 h0g0 b2a2 g0g3 a2a1 g3e3 a3a4 e3c3 "
             "a1d1 c3c0").split()
    last = None
    for i, mv in enumerate(moves, 1):
        who = "RED" if i % 2 == 1 else "BLACK"
        last = move(live, who, mv)
        assert last.returncode in (0, 1), f"ply {i} ({who} {mv}) failed: {last.stdout} {last.stderr}"
    assert "GAMEOVER" in last.stdout
    assert "GAMEOVER 0-1" in last.stdout  # black (second mover) delivered mate


def test_checkmate_appends_ledger_and_banner(live):
    """Game-6 retro fix: mate used to only print GAMEOVER, leaving
    results.txt/result.txt/banner.txt for the host to fill in by hand."""
    init(live)
    moves = ("b2b9 a9b9 h2h9 i9h9 c3c4 b7b5 d0e1 f9e8 e0d0 h7h2 a0a2 h2h8 "
             "a2f2 h8i8 f2i2 b5b4 i2a2 i8i3 i0i3 b4a4 i3i6 b9b2 i6i9 h9h0 "
             "i9g9 e8f9 g9f9 e9f9 a2b2 h0g0 b2a2 g0g3 a2a1 g3e3 a3a4 e3c3 "
             "a1d1 c3c0").split()
    last = None
    for i, mv in enumerate(moves, 1):
        who = "RED" if i % 2 == 1 else "BLACK"
        last = move(live, who, mv)
    assert "GAMEOVER 0-1" in last.stdout
    assert (live / "results.txt").read_text().strip() == "RED 0-1 BLACK"
    assert "BLACK wins by checkmate" in (live / "result.txt").read_text()
    banner = (live / "banner.txt").read_text()
    assert "RED 0-1 BLACK" in banner and "checkmate" in banner


def test_checkmate_ledger_append_is_idempotent(live):
    """finish_native must not double-append when called again over an
    already-recorded result -- exercised directly via import, since a second
    `move` call after checkmate is refused before ever reaching it."""
    init(live)
    script = (
        f"import sys; sys.path.insert(0, {str(ENGINE)!r})\n"
        "import ref_xq\n"
        "ref_xq.finish_native(None, '0-1', 'checkmate')\n"
        "ref_xq.finish_native(None, '0-1', 'checkmate')\n"
        "print('OK')\n"
    )
    r = subprocess.run([sys.executable, "-c", script], cwd=live,
                        env={"ARCADE_LIVE": str(live), "PATH": "/usr/bin:/bin"},
                        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "OK" in r.stdout
    lines = [l for l in (live / "results.txt").read_text().splitlines() if l.strip()]
    assert lines == ["RED 0-1 BLACK"]


def test_unknown_command_errors(live):
    r = run(live, "bogus")
    assert r.returncode == 2
    assert "unknown command" in r.stderr


# ---------------------------------------------------------------------------
# resign / offer-draw / accept-draw (ported from ref.py's apply_special())

def test_resign_red_records_black_win(live):
    init(live)
    r = move(live, "RED", "resign")
    assert r.returncode == 0, r.stderr
    assert "GAMEOVER 0-1" in r.stdout
    assert (live / "results.txt").read_text().strip() == "RED 0-1 BLACK"
    assert "BLACK wins by resignation" in (live / "result.txt").read_text()


def test_resign_black_records_red_win(live):
    init(live)
    r = move(live, "BLACK", "resign")
    assert r.returncode == 0, r.stderr
    assert "GAMEOVER 1-0" in r.stdout
    assert (live / "results.txt").read_text().strip() == "RED 1-0 BLACK"
    assert "RED wins by resignation" in (live / "result.txt").read_text()


def test_resign_clears_pending_draw_offer(live):
    init(live)
    move(live, "RED", "offer-draw")
    assert (live / "draw_offer.txt").exists()
    move(live, "BLACK", "resign")
    assert not (live / "draw_offer.txt").exists()


def test_offer_draw_stages_and_does_not_end_game(live):
    init(live)
    r = move(live, "RED", "offer-draw")
    assert r.returncode == 0, r.stderr
    assert "OK draw offered by RED" in r.stdout
    assert (live / "draw_offer.txt").read_text().strip() == "RED"
    assert not (live / "result.txt").exists()
    # the game is still live -- a normal move still applies afterward
    r = move(live, "RED", "h2e2")
    assert r.returncode == 0, r.stderr


def test_accept_draw_by_opponent_ends_game(live):
    init(live)
    move(live, "RED", "offer-draw")
    r = move(live, "BLACK", "accept-draw")
    assert r.returncode == 0, r.stderr
    assert "GAMEOVER 1/2-1/2" in r.stdout
    assert (live / "results.txt").read_text().strip() == "RED 1/2-1/2 BLACK"
    assert "draw agreed" in (live / "result.txt").read_text()
    assert not (live / "draw_offer.txt").exists()


def test_accept_draw_self_accept_rejected(live):
    init(live)
    move(live, "RED", "offer-draw")
    r = move(live, "RED", "accept-draw")
    assert r.returncode == 4
    assert "own draw offer" in r.stderr
    # offer is still pending, game still live
    assert (live / "draw_offer.txt").exists()
    assert not (live / "result.txt").exists()


def test_accept_draw_with_no_offer_rejected(live):
    init(live)
    r = move(live, "BLACK", "accept-draw")
    assert r.returncode == 4
    assert "no draw offer is pending" in r.stderr


def test_draw_offer_cleared_by_opponents_next_real_move(live):
    """offer-draw doesn't require it being the offerer's turn -- RED can offer
    while it's BLACK to move. BLACK then playing an actual move (rather than
    accepting) implicitly declines it, and the referee clears the offer."""
    init(live)
    move(live, "RED", "h2e2")           # now black to move
    move(live, "RED", "offer-draw")     # RED offers even though it's not RED's turn
    assert (live / "draw_offer.txt").read_text().strip() == "RED"
    r = move(live, "BLACK", "h9g7")     # black's actual move, declining the offer implicitly
    assert r.returncode == 0, r.stderr
    assert not (live / "draw_offer.txt").exists()


def test_special_token_never_reaches_board_push(live):
    """resign/offer-draw/accept-draw must be intercepted before push() ever
    sees them -- moves.txt (the ICCS move log) must stay untouched by any of
    the three special tokens."""
    init(live)
    move(live, "RED", "offer-draw")
    move(live, "BLACK", "accept-draw")
    assert (live / "moves.txt").read_text() == ""


def test_move_after_resignation_refused(live):
    init(live)
    move(live, "RED", "resign")
    r = move(live, "BLACK", "h9g7")
    assert r.returncode == 6
    assert "already over" in r.stderr
    assert (live / "moves.txt").read_text() == ""


def test_move_after_accepted_draw_refused(live):
    init(live)
    move(live, "RED", "offer-draw")
    move(live, "BLACK", "accept-draw")
    r = move(live, "RED", "h2e2")
    assert r.returncode == 6
    assert "already over" in r.stderr


def test_move_after_checkmate_refused(live):
    """Once game_over_result() reports the board itself is over (no result.txt
    needed -- checkmate/stalemate), any further move call must refuse too,
    same exit code/path as the explicit result.txt case."""
    init(live)
    moves = ("b2b9 a9b9 h2h9 i9h9 c3c4 b7b5 d0e1 f9e8 e0d0 h7h2 a0a2 h2h8 "
             "a2f2 h8i8 f2i2 b5b4 i2a2 i8i3 i0i3 b4a4 i3i6 b9b2 i6i9 h9h0 "
             "i9g9 e8f9 g9f9 e9f9 a2b2 h0g0 b2a2 g0g3 a2a1 g3e3 a3a4 e3c3 "
             "a1d1 c3c0").split()
    for i, mv in enumerate(moves, 1):
        who = "RED" if i % 2 == 1 else "BLACK"
        move(live, who, mv)
    r = move(live, "RED", "h2e2")
    assert r.returncode == 6
    assert "already over" in r.stderr


def test_init_clears_stale_result_and_draw_offer(live):
    """A leftover result.txt/draw_offer.txt from a finished match must not
    make a freshly-init'd match refuse its very first move."""
    init(live)
    move(live, "RED", "resign")
    assert (live / "result.txt").exists()
    init(live, force=True)
    assert not (live / "result.txt").exists()
    assert not (live / "draw_offer.txt").exists()
    r = move(live, "RED", "h2e2")
    assert r.returncode == 0, r.stderr


def test_offer_draw_requires_seated_author(live):
    init(live)
    r = move(live, "SOMEONE_ELSE", "offer-draw")
    assert r.returncode == 4
    assert "does not hold a seat" in r.stderr


def test_unsigned_special_token_rejected(live):
    """Unlike a bare (unsigned) move -- which skips the author check entirely
    -- an unsigned special token has no seat to attribute it to and must be
    rejected, not silently applied."""
    init(live)
    r = move(live, None, "resign")
    assert r.returncode == 4

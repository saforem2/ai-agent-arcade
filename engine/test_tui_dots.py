"""Tests for tui_dots.py's file-cache correctness -- the names.txt staleness
class (the viewer backlog, design-history §7 leak class): a
viewer left running across a pairing change must not keep showing the old
players forever. Hit live in game 6 (board kept showing the departed
pairing), patched operationally by killing and relaunching the pane; these
tests lock in the code fix (refresh_names(), called every render()).

Runs as a subprocess (uv run --with chess), matching test_game_cli.py's
pattern -- the outer pytest process is not guaranteed to have the chess
package installed (the shared gate command only requests --with pytest).
"""
import os
import subprocess
from pathlib import Path

ENGINE = Path(__file__).resolve().parent


def run_probe(live, script):
    """Run `script` with tui_dots imported as `td` and ARCADE_LIVE pointed
    at `live`, inside the same uv --with chess env tui_dots.py itself
    needs. Whatever the snippet prints is on stdout.

    Inherits the real PATH (unlike the restricted-PATH subprocess pattern
    used elsewhere in this repo for direct `sys.executable` calls) because
    this needs to actually locate the `uv` binary, not just python."""
    full = (
        f"import sys; sys.path.insert(0, {str(ENGINE)!r})\n"
        "import tui_dots as td\n"
        f"{script}"
    )
    return subprocess.run(
        ["uv", "run", "--quiet", "--with", "chess", "python", "-c", full],
        cwd=live, env={**os.environ, "ARCADE_LIVE": str(live)},
        capture_output=True, text=True,
    )


def test_refresh_names_reads_names_txt(tmp_path):
    (tmp_path / "names.txt").write_text("KIMI CODEX\n")
    r = run_probe(tmp_path, "td.refresh_names(); print(td.names)")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "{'w': 'KIMI', 'b': 'CODEX'}"


def test_refresh_names_picks_up_a_mid_run_rewrite(tmp_path):
    """The core regression: a viewer whose cache is already warm (it has
    already refreshed once) must still notice names.txt changing again
    later -- exactly what happens when `arcade start` deploys a fresh
    pairing under a viewer still running from the previous match."""
    (tmp_path / "names.txt").write_text("KIMI CODEX\n")
    script = (
        "td.refresh_names(); first = dict(td.names)\n"
        "open('names.txt', 'w').write('GEMINI GROK\\n')\n"
        "td.refresh_names(); second = dict(td.names)\n"
        "print(first); print(second)\n"
    )
    r = run_probe(tmp_path, script)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert lines[0] == "{'w': 'KIMI', 'b': 'CODEX'}"
    assert lines[1] == "{'w': 'GEMINI', 'b': 'GROK'}"


def test_refresh_names_missing_file_keeps_last_known_good(tmp_path):
    (tmp_path / "names.txt").write_text("KIMI CODEX\n")
    script = (
        "td.refresh_names(); first = dict(td.names)\n"
        "import os; os.remove('names.txt')\n"
        "td.refresh_names(); second = dict(td.names)\n"  # must not raise
        "print(first); print(second)\n"
    )
    r = run_probe(tmp_path, script)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert lines[0] == lines[1] == "{'w': 'KIMI', 'b': 'CODEX'}"


def test_refresh_names_malformed_content_keeps_last_known_good(tmp_path):
    (tmp_path / "names.txt").write_text("KIMI CODEX\n")
    script = (
        "td.refresh_names(); first = dict(td.names)\n"
        "open('names.txt', 'w').write('ONLYONE\\n')\n"
        "td.refresh_names(); second = dict(td.names)\n"
        "print(first); print(second)\n"
    )
    r = run_probe(tmp_path, script)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert lines[0] == lines[1] == "{'w': 'KIMI', 'b': 'CODEX'}"


def test_render_picks_up_mid_run_names_change(tmp_path):
    """End-to-end through render() itself, not just refresh_names() -- proves
    the actual draw path reflects a mid-run rename, matching the game-6 bug
    report exactly (a long-running viewer kept showing the old players)."""
    (tmp_path / "names.txt").write_text("KIMI CODEX\n")
    script = (
        "import chess, io, contextlib\n"
        "buf1 = io.StringIO()\n"
        "with contextlib.redirect_stdout(buf1): td.render(chess.Board())\n"
        "open('names.txt', 'w').write('GEMINI CODEX\\n')\n"
        "buf2 = io.StringIO()\n"
        "with contextlib.redirect_stdout(buf2): td.render(chess.Board())\n"
        "print('KIMI' in buf1.getvalue())\n"
        "print('GEMINI' in buf2.getvalue())\n"
        "print('KIMI' in buf2.getvalue())\n"
    )
    r = run_probe(tmp_path, script)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert lines == ["True", "True", "False"]


def test_render_names_stable_when_file_unchanged(tmp_path):
    """The mtime-cached refresh must not perturb the displayed identity
    between two renders of an untouched names.txt -- i.e. refresh_names()
    is a no-op read (cache hit), not a re-parse that could drift.

    Not asserting whole-frame byte equality here: tui_dots.py's ambient
    field is deliberately time-varying (module docstring's "one slow
    drift"), so two render() calls a few milliseconds apart legitimately
    differ in the dither bytes even with nothing on disk touched. What must
    stay fixed is the file-driven content -- the names themselves."""
    (tmp_path / "names.txt").write_text("KIMI CODEX\n")
    script = (
        "import chess, io, contextlib\n"
        "b = chess.Board()\n"
        "buf1 = io.StringIO()\n"
        "with contextlib.redirect_stdout(buf1): td.render(b)\n"
        "buf2 = io.StringIO()\n"
        "with contextlib.redirect_stdout(buf2): td.render(b)\n"
        "for buf in (buf1, buf2):\n"
        "    assert 'KIMI' in buf.getvalue() and 'CODEX' in buf.getvalue()\n"
        "print('ok')\n"
    )
    r = run_probe(tmp_path, script)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "ok"


# ---------------------------------------------------------------------------
# replay mid-animation interruptibility (the viewer backlog: "replay
# not q/click-interruptible mid-animation" -- before this fix, poll_input() was
# never even called from inside animate(), so a click/keypress during a move's
# ~0.5-1s animation sat unconsumed until the whole replay finished on its own;
# only a `ctl` file change was checked, and only between moves.)

# render() writes raw ANSI straight to sys.stdout, which would otherwise land
# ahead of a probe script's own print()s in the captured output -- every
# script below wraps its td.* call in redirect_stdout(io.StringIO()) to throw
# that noise away and only print() the values it actually wants checked.

def test_animate_interruptible_stops_immediately_on_input(tmp_path):
    """The core mechanism: with interruptible=True and poll_input() stubbed
    to fire immediately, animate() must return right away instead of
    running its full ~0.5s+0.5s animation -- while still applying the move
    to the board (state always keeps moving, only the animation is cut)."""
    script = (
        "import chess, time, io, contextlib\n"
        "td.poll_input = lambda: 'quit'\n"
        "b = chess.Board()\n"
        "mv = b.parse_san('e4')\n"
        "t0 = time.monotonic()\n"
        "with contextlib.redirect_stdout(io.StringIO()):\n"
        "    action = td.animate(b, mv, interruptible=True)\n"
        "elapsed = time.monotonic() - t0\n"
        "print(action)\n"
        "print(elapsed < 0.3)\n"
        "print(b.piece_at(chess.E4) is not None)\n"
    )
    r = run_probe(tmp_path, script)
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines() == ["quit", "True", "True"]


def test_animate_non_interruptible_ignores_input(tmp_path):
    """Default interruptible=False (live single-move animation, not replay)
    must not poll input at all -- a stubbed poll_input that would fire
    immediately must have zero effect on timing or outcome."""
    script = (
        "import chess, time, io, contextlib\n"
        "td.poll_input = lambda: 'quit'\n"
        "b = chess.Board()\n"
        "mv = b.parse_san('e4')\n"
        "t0 = time.monotonic()\n"
        "with contextlib.redirect_stdout(io.StringIO()):\n"
        "    action = td.animate(b, mv)\n"
        "elapsed = time.monotonic() - t0\n"
        "print(action)\n"
        "print(elapsed > 0.4)\n"   # the full travel animation ran (~0.5s)
    )
    r = run_probe(tmp_path, script)
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines() == ["None", "True"]


def test_replay_all_aborts_mid_replay_when_interrupted(tmp_path):
    """The regression itself, through the real replay loop: an 8-move
    uninterrupted replay takes several seconds (travel + settle + the
    inter-move pause, times 8). Stub poll_input to fire 'replay' shortly
    after the call starts -- well within the first move's own animation --
    and confirm the whole replay aborts almost immediately rather than
    grinding through all 8 moves, while still landing on the true end
    position (matching the existing ctl-abandon contract: always resolve to
    the full replayed state, never a half-animated one)."""
    (tmp_path / "moves.txt").write_text("e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6")
    script = (
        "import time, io, contextlib\n"
        "t_start = time.monotonic()\n"
        "td.poll_input = lambda: 'replay' if time.monotonic() - t_start > 0.1 else None\n"
        "sans = td.read(td.MOVES).split()\n"
        "t0 = time.monotonic()\n"
        "with contextlib.redirect_stdout(io.StringIO()):\n"
        "    board, action = td.replay_all(sans, None)\n"
        "elapsed = time.monotonic() - t0\n"
        "print(action)\n"
        "print(elapsed < 3.0)\n"                        # aborted, not a ~7s full run
        "print(board.fen() == td.build(sans).fen())\n"  # still the true end position
    )
    r = run_probe(tmp_path, script)
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines() == ["replay", "True", "True"]


def test_replay_all_ctl_change_still_abandons_with_none_action(tmp_path):
    """Regression lock on the pre-existing ctl-file interrupt path, now
    wrapped in the (board, action) return shape: a ctl change still
    abandons with action=None (not 'replay'/'quit' -- those are only for
    live input), and still resolves to the full replayed position."""
    (tmp_path / "moves.txt").write_text("e4 e5 Nf3 Nc6")
    (tmp_path / "ctl").write_text("reset")
    script = (
        "import time, io, contextlib\n"
        "sans = td.read(td.MOVES).split()\n"
        "t0 = time.monotonic()\n"
        "with contextlib.redirect_stdout(io.StringIO()):\n"
        "    board, action = td.replay_all(sans, None)\n"
        "elapsed = time.monotonic() - t0\n"
        "print(action)\n"
        "print(elapsed < 2.0)\n"
        "print(board.fen() == td.build(sans).fen())\n"
    )
    r = run_probe(tmp_path, script)
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines() == ["None", "True", "True"]


def test_do_replay_restarts_once_then_completes(tmp_path):
    """A live 'replay' click mid-flight must restart from scratch, not lose
    the request -- do_replay's bounded restart loop. Stub fires 'replay' on
    the very first poll_input() call (immediate abort of attempt #1), then
    None forever after (attempt #2 runs to completion)."""
    (tmp_path / "moves.txt").write_text("e4 e5")
    script = (
        "import io, contextlib\n"
        "calls = {'n': 0}\n"
        "def fake_poll():\n"
        "    calls['n'] += 1\n"
        "    return 'replay' if calls['n'] == 1 else None\n"
        "td.poll_input = fake_poll\n"
        "sans = td.read(td.MOVES).split()\n"
        "with contextlib.redirect_stdout(io.StringIO()):\n"
        "    board, action = td.do_replay(None)\n"
        "print(action)\n"
        "print(calls['n'] > 1)\n"                       # a second attempt happened
        "print(board.fen() == td.build(sans).fen())\n"
    )
    r = run_probe(tmp_path, script)
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines() == ["None", "True", "True"]


def test_do_replay_propagates_quit(tmp_path):
    """A live 'quit' mid-flight must bubble all the way up through
    do_replay -- the caller (main loop) exits instead of resuming."""
    (tmp_path / "moves.txt").write_text("e4 e5 Nf3 Nc6")
    script = (
        "import io, contextlib\n"
        "td.poll_input = lambda: 'quit'\n"
        "with contextlib.redirect_stdout(io.StringIO()):\n"
        "    board, action = td.do_replay(None)\n"
        "print(action)\n"
    )
    r = run_probe(tmp_path, script)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "quit"

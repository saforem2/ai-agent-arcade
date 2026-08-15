"""Tests for game_cw_cli.py and the game_cw.sh wrapper: staging, spar
privacy, status recovery, await-battle, the seat-bound identity hard-refuse,
and the wrapper's auto-poke gating/payloads.

Every test runs game_cw_cli.py / game_cw.sh / ref_cw.py as subprocesses
against a pytest tmp_path with ARCADE_LIVE pointed at it -- never against
/tmp/corewar. Wrapper tests build their own PATH with a stub `herdr` (the
real one talks to live agent panes and must never be exec'd by a test).
"""
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE))
import corewar

CLI = ENGINE / "game_cw_cli.py"
REF = ENGINE / "ref_cw.py"
WRAPPER = ENGINE / "game_cw.sh"

KAMIKAZE = """\
;redcode-94
;name Kamikaze
org start
start   dat     #0, #0
        end
"""


@pytest.fixture
def live(tmp_path):
    for fn in ("corewar.py", "chat.py"):
        (tmp_path / fn).write_text((ENGINE / fn).read_text())
    (tmp_path / "names.txt").write_text("RED BLUE\n")
    (tmp_path / "seats.txt").write_text("RED white\nBLUE black\n")
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
        [sys.executable, str(CLI), *args],
        cwd=live, env=_env(live, chess_name), capture_output=True, text=True, timeout=timeout,
    )


def write_warrior(live, filename, source):
    path = live / filename
    path.write_text(source)
    return path


def apply_pending(live):
    pending = (live / "pending.txt").read_text()
    r = run_ref(live, "stage", pending)
    (live / "pending.txt").unlink(missing_ok=True)
    return r


def stage_and_apply(live, who, filename, source):
    write_warrior(live, filename, source)
    r = run_cli(live, "stage", filename, chess_name=who)
    assert r.returncode == 0, r.stderr
    r = apply_pending(live)
    assert r.returncode == 0, r.stderr


# ---------------------------------------------------------------------------
# stage

def test_stage_happy_path(live):
    path = write_warrior(live, "imp.red", corewar.IMP)
    r = run_cli(live, "stage", "imp.red", chess_name="RED")
    assert r.returncode == 0, r.stderr
    assert "STAGED: imp.red" in r.stdout
    sha = corewar.sha256_warrior(corewar.IMP)
    assert (live / "pending.txt").read_text() == f"RED\tstage {sha}"
    # the inbox copy is byte-identical to the staged file
    assert (live / "stage_inbox/RED.red").read_bytes() == path.read_bytes()


def test_stage_invalid_warrior_refused_client_side(live):
    write_warrior(live, "bad.red", "bogus $0, $0\nend\n")
    r = run_cli(live, "stage", "bad.red", chess_name="RED")
    assert r.returncode == 1
    assert "ILLEGAL" in r.stdout
    assert "unknown opcode" in r.stdout
    assert not (live / "pending.txt").exists()
    assert not (live / "stage_inbox/RED.red").exists()


def test_stage_missing_file(live):
    r = run_cli(live, "stage", "nope.red", chess_name="RED")
    assert r.returncode == 1
    assert "cannot read" in r.stdout
    assert not (live / "pending.txt").exists()


def test_stage_refused_for_unseated_signer(live):
    write_warrior(live, "imp.red", corewar.IMP)
    r = run_cli(live, "stage", "imp.red", chess_name="INTRUDER")
    assert r.returncode == 1
    assert "REFUSED" in r.stdout
    assert "RED (white)" in r.stdout and "BLUE (black)" in r.stdout
    assert not (live / "pending.txt").exists()


def test_seat_check_is_a_noop_without_seats_txt(live):
    (live / "seats.txt").unlink()
    write_warrior(live, "imp.red", corewar.IMP)
    r = run_cli(live, "stage", "imp.red", chess_name="ANYONE")
    assert r.returncode == 0, r.stderr
    assert "STAGED" in r.stdout


# ---------------------------------------------------------------------------
# spar (local exhibition: prints, writes NOTHING to the bus)

def test_spar_prints_outcome_and_writes_nothing(live):
    write_warrior(live, "imp.red", corewar.IMP)
    before_moves = (live / "moves.txt").read_text()
    r = run_cli(live, "spar", "imp.red", "dwarf", chess_name="RED")
    assert r.returncode == 0, r.stderr
    assert "SPAR imp.red vs Dwarf" in r.stdout
    assert "OUT " in r.stdout and "cycles=" in r.stdout
    r = run_cli(live, "spar", "imp.red", chess_name="RED")   # default dummy is imp
    assert "SPAR imp.red vs Imp" in r.stdout
    # pure read/print: no bus writes of any kind
    assert not (live / "chat.log").exists()
    assert not (live / "pending.txt").exists()
    assert not (live / "battle.json").exists()
    assert (live / "moves.txt").read_text() == before_moves
    assert list((live / "stage_inbox").iterdir()) == []


def test_spar_kamikaze_loses(live):
    write_warrior(live, "kamikaze.red", KAMIKAZE)
    r = run_cli(live, "spar", "kamikaze.red", "imp", chess_name="RED")
    assert r.returncode == 0, r.stderr
    assert "OUT 0-1" in r.stdout
    assert "Imp wins" in r.stdout


def test_spar_unknown_dummy_and_bad_warrior(live):
    write_warrior(live, "imp.red", corewar.IMP)
    r = run_cli(live, "spar", "imp.red", "mice", chess_name="RED")
    assert r.returncode == 2
    write_warrior(live, "bad.red", "bogus $0\nend\n")
    r = run_cli(live, "spar", "bad.red", chess_name="RED")
    assert r.returncode == 1
    assert "does not assemble" in r.stdout


# ---------------------------------------------------------------------------
# show / status

def test_status_fresh(live):
    r = run_cli(live, "status")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "phase: workshop" in out
    assert "RED: (nothing staged)" in out and "BLUE: (nothing staged)" in out
    assert "pending: (none)" in out
    assert "locked: no" in out
    assert "rounds: 0" in out
    assert "gameover: no" in out


def test_show_phases(live):
    r = run_cli(live, "show")
    assert "WORKSHOP" in r.stdout
    stage_and_apply(live, "RED", "a.red", corewar.IMP)
    stage_and_apply(live, "BLUE", "b.red", corewar.DWARF)
    r = run_cli(live, "show", chess_name="BLUE")
    assert "RED: warrior in the hold" in r.stdout
    assert "BLUE: warrior in the hold" in r.stdout
    r = run_ref(live, "lock")
    assert r.returncode == 0, r.stderr
    r = run_cli(live, "show")
    assert "LOCKED" in r.stdout
    r = run_ref(live, "battle")
    assert r.returncode == 0, r.stderr
    r = run_cli(live, "show")
    assert "OVER" in r.stdout
    assert "round 1:" in r.stdout
    assert "Result:" in r.stdout


def test_status_reports_pending(live):
    write_warrior(live, "imp.red", corewar.IMP)
    run_cli(live, "stage", "imp.red", chess_name="RED")
    r = run_cli(live, "status", chess_name="BLUE")
    sha = corewar.sha256_warrior(corewar.IMP)
    assert f"pending: stage {sha} (staged by RED)" in r.stdout


# ---------------------------------------------------------------------------
# STAGED -> APPLIED / REJECTED

def test_status_reports_staged_then_applied(live):
    write_warrior(live, "imp.red", corewar.IMP)
    run_cli(live, "stage", "imp.red", chess_name="RED")
    r = run_cli(live, "status", chess_name="RED")
    assert "STAGED: your warrior — still awaiting the referee." in r.stdout
    apply_pending(live)
    r = run_cli(live, "status", chess_name="RED")
    assert "APPLIED: your warrior confirmed — in the hold" in r.stdout


def test_status_reports_applied_locked_after_lock(live):
    stage_and_apply(live, "RED", "a.red", corewar.IMP)
    stage_and_apply(live, "BLUE", "b.red", corewar.DWARF)
    run_ref(live, "lock")
    r = run_cli(live, "status", chess_name="RED")
    assert "APPLIED: your warrior confirmed — locked in" in r.stdout


def test_status_reports_rejected_when_pending_cleared_without_install(live):
    """Simulates a referee rejection: the host's `rm -f pending.txt` runs
    after every apply attempt, success or failure, so pending being gone is
    not enough -- the hold must also show the staged hash never landed."""
    write_warrior(live, "imp.red", corewar.IMP)
    run_cli(live, "stage", "imp.red", chess_name="RED")
    (live / "pending.txt").unlink()      # referee refused; host cleared pending
    (live / "stage_inbox/RED.red").unlink(missing_ok=True)
    r = run_cli(live, "status", chess_name="RED")
    assert "REJECTED: your warrior was not applied" in r.stdout


def test_applied_report_resign(live):
    run_cli(live, "resign", chess_name="RED")
    apply_pending(live)
    r = run_cli(live, "status", chess_name="RED")
    assert "APPLIED: resign confirmed" in r.stdout
    assert "wins by resignation" in r.stdout


def test_status_silent_for_a_name_that_never_staged_anything(live):
    r = run_cli(live, "status", chess_name="SPECTATOR")
    assert "your last submission" not in r.stdout


# ---------------------------------------------------------------------------
# resign / await-battle / say

def test_resign_stages_token(live):
    r = run_cli(live, "resign", chess_name="BLUE")
    assert r.returncode == 0, r.stderr
    assert "STAGED: resign" in r.stdout
    assert (live / "pending.txt").read_text() == "BLUE\tresign"


def test_resign_refused_for_unseated_signer(live):
    r = run_cli(live, "resign", chess_name="INTRUDER")
    assert r.returncode == 1
    assert "REFUSED" in r.stdout
    assert not (live / "pending.txt").exists()


def test_await_battle_returns_immediately_when_over(live):
    run_cli(live, "resign", chess_name="RED")
    apply_pending(live)
    r = run_cli(live, "await-battle", chess_name="RED", timeout=10)
    assert r.returncode == 0, r.stderr
    assert "OVER" in r.stdout


def test_battle_finished_pure_predicate(tmp_path):
    for fn in ("game_cw_cli.py", "corewar.py", "chat.py"):
        (tmp_path / fn).write_text((ENGINE / fn).read_text())
    script = (
        f"import sys; sys.path.insert(0, {str(tmp_path)!r})\n"
        "import json, game_cw_cli\n"
        "assert game_cw_cli.battle_finished() is False\n"
        "game_cw_cli.BATTLE_JSON.write_text(json.dumps({'rounds': [{}, {}]}))\n"
        "assert game_cw_cli.battle_finished() is False\n"
        "game_cw_cli.BATTLE_JSON.write_text(json.dumps({'rounds': [{}, {}, {}]}))\n"
        "assert game_cw_cli.battle_finished() is True\n"
        "game_cw_cli.BATTLE_JSON.unlink()\n"
        "game_cw_cli.RESULT.write_text('RED wins by battle\\n')\n"
        "assert game_cw_cli.battle_finished() is True\n"
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


def test_say_and_chat_stay_open_to_unseated_names(live):
    r = run_cli(live, "say", "hello everyone", chess_name="SPECTATOR")
    assert r.returncode == 0, r.stderr
    assert "SAID (SPECTATOR)" in r.stdout
    r = run_cli(live, "chat", chess_name="SPECTATOR")
    assert "hello everyone" in r.stdout


# ---------------------------------------------------------------------------
# game_cw.sh wrapper: auto-poke gating + payloads. Mirrors the safety rules
# of test_shell_wrappers.py -- a scratch PATH with a stub herdr, never the
# real one.

def _uv_stub_bin(tmp_path):
    stub = tmp_path / "_stub_bin"
    stub.mkdir(exist_ok=True)
    uv_path = shutil.which("uv")
    assert uv_path, "uv not found on PATH -- cannot run these tests"
    link = stub / "uv"
    if not link.exists():
        link.symlink_to(uv_path)
    return stub


def _herdr_stub(bin_dir, succeed=True):
    """A fake herdr that appends its argv (tab-joined) to herdr_calls.log."""
    log = bin_dir.parent / "herdr_calls.log"
    script = bin_dir / "herdr"
    body = (
        "#!/bin/bash\n"
        f'printf "%s\\t" "$@" >> {log}\n'
        f'printf "\\n" >> {log}\n'
        + ("exit 0\n" if succeed else "exit 1\n")
    )
    script.write_text(body)
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return log


@pytest.fixture
def wrapped(tmp_path):
    """A deployed-style live dir (wrapper + cli + ref + engine + chat all in
    it, since game_cw.sh self-locates via BASH_SOURCE) on a scratch PATH."""
    live = tmp_path / "live"
    live.mkdir()
    for fn in ("game_cw.sh", "game_cw_cli.py", "ref_cw.py", "corewar.py", "chat.py"):
        (live / fn).write_text((ENGINE / fn).read_text())
    (live / "names.txt").write_text("RED BLUE\n")
    (live / "seats.txt").write_text("RED white\nBLUE black\n")
    write_warrior(live, "imp.red", corewar.IMP)
    write_warrior(live, "dwarf.red", corewar.DWARF)
    stub_bin = _uv_stub_bin(tmp_path)
    env = {
        "PATH": f"{stub_bin}:/usr/bin:/bin",
        "HOME": os.environ.get("HOME", ""),
        "ARCADE_LIVE": str(live),
        "CHESS_NAME": "RED",
    }
    r = subprocess.run(
        ["uv", "run", "--quiet", "python", str(live / "ref_cw.py"), "init"],
        cwd=live, env=env, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    return live, env, stub_bin


def run_wrapper(live, env, *args, chess_name="RED"):
    return subprocess.run(
        ["bash", str(live / "game_cw.sh"), *args],
        cwd=live, env={**env, "CHESS_NAME": chess_name}, capture_output=True, text=True,
    )


def test_wrapper_no_host_file_yields_not_notified(wrapped):
    live, env, _ = wrapped
    r = run_wrapper(live, env, "stage", "imp.red")
    assert r.returncode == 0, r.stderr
    assert "STAGED:" in r.stdout
    assert "HOST NOT NOTIFIED (no host.txt)" in r.stdout
    assert (live / "pending.txt").exists()


def test_wrapper_notifies_with_staged_payload(wrapped):
    live, env, stub_bin = wrapped
    (live / "host.txt").write_text("grok\n")
    log = _herdr_stub(stub_bin, succeed=True)
    r = run_wrapper(live, env, "stage", "imp.red")
    assert r.returncode == 0, r.stderr
    assert "HOST NOTIFIED" in r.stdout
    calls = log.read_text().strip().splitlines()
    assert len(calls) == 1
    parts = calls[0].split("\t")
    assert parts[:3] == ["agent", "prompt", "grok"]
    assert parts[3] == "STAGED RED warrior"


def test_wrapper_battle_ready_when_both_seats_hold(wrapped):
    """The second seat's stage, with the first seat's warrior already
    referee-installed, is the host's lock->battle cue (FACILITATOR_CW.md)."""
    live, env, stub_bin = wrapped
    (live / "host.txt").write_text("grok\n")
    log = _herdr_stub(stub_bin, succeed=True)
    r = run_wrapper(live, env, "stage", "imp.red", chess_name="RED")
    assert r.returncode == 0, r.stderr
    apply_pending(live)                     # warriors/A.red now installed
    r = run_wrapper(live, env, "stage", "dwarf.red", chess_name="BLUE")
    assert r.returncode == 0, r.stderr
    assert "HOST NOTIFIED" in r.stdout
    calls = log.read_text().strip().splitlines()
    assert [c.split("\t")[3] for c in calls] == ["STAGED RED warrior", "BATTLE READY"]


def test_wrapper_restage_alone_is_not_battle_ready(wrapped):
    live, env, stub_bin = wrapped
    (live / "host.txt").write_text("grok\n")
    log = _herdr_stub(stub_bin, succeed=True)
    run_wrapper(live, env, "stage", "imp.red", chess_name="RED")
    apply_pending(live)
    r = run_wrapper(live, env, "stage", "imp.red", chess_name="RED")   # re-stage same seat
    assert r.returncode == 0, r.stderr
    calls = log.read_text().strip().splitlines()
    assert [c.split("\t")[3] for c in calls] == ["STAGED RED warrior", "STAGED RED warrior"]


def test_wrapper_resign_payload(wrapped):
    live, env, stub_bin = wrapped
    (live / "host.txt").write_text("grok\n")
    log = _herdr_stub(stub_bin, succeed=True)
    r = run_wrapper(live, env, "resign")
    assert r.returncode == 0, r.stderr
    assert "HOST NOTIFIED" in r.stdout
    assert log.read_text().strip().split("\t")[3] == "STAGED RED resign"


def test_wrapper_gameover_yields_not_notified(wrapped):
    live, env, _ = wrapped
    (live / "host.txt").write_text("grok\n")
    (live / "result.txt").write_text("BLUE wins by resignation (RED resigned)\n")
    r = run_wrapper(live, env, "resign")
    assert r.returncode == 0, r.stderr     # staging itself still works
    assert "HOST NOT NOTIFIED (gameover)" in r.stdout


def test_wrapper_herdr_missing_yields_not_notified(wrapped):
    live, env, _ = wrapped
    (live / "host.txt").write_text("grok\n")
    r = run_wrapper(live, env, "stage", "imp.red")
    assert r.returncode == 0, r.stderr
    assert "HOST NOT NOTIFIED (herdr missing)" in r.stdout


def test_wrapper_herdr_failure_yields_not_notified(wrapped):
    live, env, stub_bin = wrapped
    (live / "host.txt").write_text("grok\n")
    _herdr_stub(stub_bin, succeed=False)
    r = run_wrapper(live, env, "stage", "imp.red")
    assert r.returncode == 0, r.stderr
    assert "HOST NOT NOTIFIED (stage failed)" in r.stdout


def test_wrapper_failed_stage_propagates_exit_and_skips_poke(wrapped):
    live, env, stub_bin = wrapped
    (live / "host.txt").write_text("grok\n")
    log = _herdr_stub(stub_bin, succeed=True)
    write_warrior(live, "bad.red", "bogus $0\nend\n")
    r = run_wrapper(live, env, "stage", "bad.red")
    assert r.returncode == 1
    assert "ILLEGAL" in r.stdout
    assert "HOST NOT NOTIFIED (stage failed)" in r.stdout
    assert not log.exists()                # no poke for a failed stage
    assert not (live / "pending.txt").exists()


def test_wrapper_host_txt_wins_over_director_txt(wrapped):
    live, env, stub_bin = wrapped
    (live / "director.txt").write_text("stale-agent\n")
    (live / "host.txt").write_text("fresh-agent\n")
    log = _herdr_stub(stub_bin, succeed=True)
    r = run_wrapper(live, env, "stage", "imp.red")
    assert r.returncode == 0, r.stderr
    assert log.read_text().strip().split("\t")[2] == "fresh-agent"


def test_wrapper_director_txt_fallback(wrapped):
    live, env, stub_bin = wrapped
    (live / "director.txt").write_text("grok\n")   # no host.txt at all
    log = _herdr_stub(stub_bin, succeed=True)
    r = run_wrapper(live, env, "stage", "imp.red")
    assert r.returncode == 0, r.stderr
    assert "HOST NOTIFIED" in r.stdout
    assert log.read_text().strip().split("\t")[2] == "grok"


# ---------------------------------------------------------------------------
# adversarial-review regressions (round 2)

def test_stage_refused_for_traversal_chess_name(live):
    """RISK-3 (CLI layer): a traversal $CHESS_NAME is refused before any
    filename is built from it."""
    write_warrior(live, "imp.red", corewar.IMP)
    r = run_cli(live, "stage", "imp.red", chess_name="../warriors/A")
    assert r.returncode == 1
    assert "REFUSED" in r.stdout
    assert "Traceback" not in r.stderr
    assert not (live / "pending.txt").exists()
    assert list((live / "stage_inbox").iterdir()) == []


def test_stage_traversal_name_clean_refusal_without_seats_txt(live):
    """NIT-3: with seats.txt absent require_seated is a no-op, so the
    filename-safety gate is the only bar -- it must refuse cleanly where the
    old code died with FileNotFoundError on the tmp path (or worse, wrote
    outside the inbox when intermediate dirs existed)."""
    (live / "seats.txt").unlink()
    write_warrior(live, "imp.red", corewar.IMP)
    (live / "warriors/A.red").write_text(corewar.IMP)   # would-be victim
    r = run_cli(live, "stage", "imp.red", chess_name="../warriors/A")
    assert r.returncode == 1
    assert "REFUSED" in r.stdout
    assert "may not contain" in r.stdout
    assert "Traceback" not in r.stderr
    assert not (live / "pending.txt").exists()
    assert (live / "warriors/A.red").read_text() == corewar.IMP   # untouched
    # resign goes through the same gate
    r = run_cli(live, "resign", chess_name="x/y")
    assert r.returncode == 1
    assert "REFUSED" in r.stdout
    assert not (live / "pending.txt").exists()


def test_dotted_chess_name_refused(live):
    """'.' alone is enough for '..' -- dotty names are refused at the CLI too."""
    write_warrior(live, "imp.red", corewar.IMP)
    r = run_cli(live, "stage", "imp.red", chess_name="..")
    assert r.returncode == 1
    assert "REFUSED" in r.stdout
    assert not (live / "pending.txt").exists()


def test_status_and_show_clean_pending_control_bytes(live):
    """NIT-2 (CLI side): a hand-written pending.txt's ESC bytes must never
    reach the terminal via status or show."""
    (live / "pending.txt").write_text("RED\x1b[31mEVIL\x1b[0m\tresign")
    r = run_cli(live, "status", chess_name="BLUE")
    assert r.returncode == 0, r.stderr
    assert "\x1b" not in r.stdout
    assert "pending: resign (staged by RED[31mEVIL[0m)" in r.stdout
    r = run_cli(live, "show", chess_name="BLUE")
    assert r.returncode == 0, r.stderr
    assert "\x1b" not in r.stdout
    assert "NOTE: RED[31mEVIL[0m has already staged resign." in r.stdout

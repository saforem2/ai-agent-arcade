"""Tests for the game.sh / game_xq.sh shell wrappers: the auto-poke gating,
the host.txt/director.txt fallback + ply-arithmetic in the STAGED payload,
and quoting safety around the staged name/move that game_cli.py/
game_xq_cli.py hand back to them.

Backlog item from game-6 retro (docs/seat-feedback-game6.md, kimi review
nit): "Shell-wrapper tests: game.sh/game_xq.sh gating/ply-arithmetic/
quoting is inspection-reviewed only, no pytest coverage." This closes it.

SAFETY: every test builds its own PATH pointing at a stub `herdr` (or none
at all). The real `herdr` lives on this machine's PATH (~/.local/bin,
alongside `uv`) and talks to live agent panes -- it must never be exec'd by
a test. PATH is always constructed from scratch (a stub bin dir symlinking
only `uv`, plus /usr/bin:/bin), never inherited wholesale, so the real
herdr is never reachable unless a test explicitly stubs its own fake one.
"""
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parent

GAMES = {
    "chess": {
        "script": "game.sh",
        "cli": "game_cli.py",
        "ref": "ref.py",
        "extra": ["chat.py"],
        "ref_with_chess": True,
        "names": "WHITE BLACK\n",
        "seats": "WHITE white\nBLACK black\n",
        "move": "e4",
        "chess_name": "WHITE",
    },
    "xiangqi": {
        "script": "game_xq.sh",
        "cli": "game_xq_cli.py",
        "ref": "ref_xq.py",
        "extra": ["chat.py", "xiangqi.py"],
        "ref_with_chess": False,
        "names": "RED BLACK\n",
        "seats": "RED white\nBLACK black\n",
        "move": "h2e2",
        "chess_name": "RED",
    },
    "corewar": {
        "script": "game_cw.sh",
        "cli": "game_cw_cli.py",
        "ref": "ref_cw.py",
        "extra": ["chat.py", "corewar.py"],
        "ref_with_chess": False,
        "names": "RED BLUE\n",
        "seats": "RED white\nBLUE black\n",
        # corewar's staging verb is `stage <file>` (a warrior file, not a
        # move string), so the generic submit-based tests below parametrize
        # ["chess", "xiangqi"] only; corewar wrapper coverage (gating,
        # STAGED/BATTLE READY payloads) lives in test_game_cw_cli.py.
        # "move" is the warrior filename a test writes before staging;
        # "poke" is the expected payload for a first-seat stage.
        "verb": "stage",
        "move": "warrior.red",
        "poke": "STAGED RED warrior",
        "chess_name": "RED",
    },
}


def _uv_stub_bin(tmp_path):
    """A PATH entry that resolves `uv` via a symlink and nothing else --
    never the real `herdr`, which lives in the same real directory."""
    stub = tmp_path / "_stub_bin"
    stub.mkdir(exist_ok=True)
    uv_path = shutil.which("uv")
    assert uv_path, "uv not found on PATH -- cannot run these tests"
    link = stub / "uv"
    if not link.exists():
        link.symlink_to(uv_path)
    return stub


def _herdr_stub(bin_dir, *, succeed=True):
    """Write a fake `herdr` into bin_dir that appends its argv (tab-joined)
    as one line to herdr_calls.log, then exits 0 or 1. Returns the log path."""
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


def setup_live(tmp_path, game):
    spec = GAMES[game]
    live = tmp_path / "live"
    live.mkdir()
    for fn in [spec["script"], spec["cli"], spec["ref"], *spec["extra"]]:
        (live / fn).write_text((ENGINE / fn).read_text())
    (live / "names.txt").write_text(spec["names"])
    (live / "seats.txt").write_text(spec["seats"])
    stub_bin = _uv_stub_bin(tmp_path)
    env = {
        "PATH": f"{stub_bin}:/usr/bin:/bin",
        "HOME": os.environ.get("HOME", ""),
        "ARCADE_LIVE": str(live),
        "CHESS_NAME": spec["chess_name"],
    }
    with_args = ["--with", "chess"] if spec["ref_with_chess"] else []
    r = subprocess.run(
        ["uv", "run", "--quiet", *with_args, "python", str(live / spec["ref"]), "init"],
        cwd=live, env=env, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    return live, env, stub_bin


def run_wrapper(live, env, game, *args):
    spec = GAMES[game]
    return subprocess.run(
        ["bash", str(live / spec["script"]), *args],
        cwd=live, env=env, capture_output=True, text=True,
    )


# ---------------------------------------------------------------------------
# gating

@pytest.mark.parametrize("game", ["chess", "xiangqi"])
def test_no_host_file_yields_not_notified(tmp_path, game):
    live, env, _ = setup_live(tmp_path, game)
    r = run_wrapper(live, env, game, "submit", GAMES[game]["move"])
    assert r.returncode == 0, r.stderr
    assert "STAGED:" in r.stdout
    assert "HOST NOT NOTIFIED (no host.txt)" in r.stdout
    assert (live / "pending.txt").exists()


@pytest.mark.parametrize("game", ["chess", "xiangqi"])
def test_gameover_yields_not_notified(tmp_path, game):
    live, env, _ = setup_live(tmp_path, game)
    (live / "host.txt").write_text("grok\n")
    (live / "result.txt").write_text("WHITE 1-0 BLACK\n")
    r = run_wrapper(live, env, game, "submit", GAMES[game]["move"])
    assert r.returncode == 0, r.stderr
    assert "HOST NOT NOTIFIED (gameover)" in r.stdout


@pytest.mark.parametrize("game", ["chess", "xiangqi"])
def test_stage_failure_yields_not_notified_and_propagates_exit_code(tmp_path, game):
    live, env, _ = setup_live(tmp_path, game)
    (live / "host.txt").write_text("grok\n")
    r = run_wrapper(live, env, game, "submit", "z9z9-not-a-move")
    assert r.returncode == 1
    assert "ILLEGAL" in r.stdout
    assert "HOST NOT NOTIFIED (stage failed)" in r.stdout
    assert not (live / "pending.txt").exists()


@pytest.mark.parametrize("game", ["chess", "xiangqi"])
def test_herdr_missing_yields_not_notified(tmp_path, game):
    live, env, _ = setup_live(tmp_path, game)
    (live / "host.txt").write_text("grok\n")
    r = run_wrapper(live, env, game, "submit", GAMES[game]["move"])
    assert r.returncode == 0, r.stderr
    assert "HOST NOT NOTIFIED (herdr missing)" in r.stdout


@pytest.mark.parametrize("game", ["chess", "xiangqi"])
def test_pending_clear_race_still_yields_receipt(tmp_path, game):
    """The referee/host can consume pending.txt after staging but before the
    wrapper builds its poke. That race must still end with an atomic receipt."""
    live, env, stub_bin = setup_live(tmp_path, game)
    (live / "host.txt").write_text("grok\n")
    uv_link = stub_bin / "uv"
    real_uv = uv_link.resolve()
    uv_link.unlink()
    uv_link.write_text(
        "#!/bin/bash\n"
        f'"{real_uv}" "$@"\n'
        "status=$?\n"
        f'rm -f "{live / "pending.txt"}"\n'
        "exit $status\n"
    )
    uv_link.chmod(uv_link.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    r = run_wrapper(live, env, game, "submit", GAMES[game]["move"])
    assert r.returncode == 0, r.stderr
    assert "HOST NOT NOTIFIED (pending cleared before receipt)" in r.stdout


@pytest.mark.parametrize("game", ["chess", "xiangqi"])
def test_herdr_success_notifies_with_structured_payload(tmp_path, game):
    spec = GAMES[game]
    live, env, stub_bin = setup_live(tmp_path, game)
    (live / "host.txt").write_text("grok\n")
    log = _herdr_stub(stub_bin, succeed=True)
    r = run_wrapper(live, env, game, "submit", spec["move"])
    assert r.returncode == 0, r.stderr
    assert "HOST NOTIFIED" in r.stdout
    assert "HOST NOT NOTIFIED" not in r.stdout
    calls = log.read_text().strip().splitlines()
    assert len(calls) == 1
    parts = calls[0].split("\t")
    assert parts[:3] == ["agent", "prompt", "grok"]
    assert parts[3] == f"STAGED {spec['chess_name']} {spec['move']} ply=1"


@pytest.mark.parametrize("game", ["chess", "xiangqi"])
def test_herdr_poke_failure_yields_not_notified(tmp_path, game):
    """The poke itself can fail (herdr present but errors) -- must still
    report a receipt, never a silent success."""
    live, env, stub_bin = setup_live(tmp_path, game)
    (live / "host.txt").write_text("grok\n")
    _herdr_stub(stub_bin, succeed=False)
    r = run_wrapper(live, env, game, "submit", GAMES[game]["move"])
    assert r.returncode == 0, r.stderr
    assert "HOST NOT NOTIFIED (stage failed)" in r.stdout


@pytest.mark.parametrize("game", ["chess", "xiangqi"])
def test_host_txt_missing_falls_back_to_director_txt(tmp_path, game):
    """2e rename (docs/design-history.md §14): a live dir with only a stale
    director.txt (from an older deploy) must still auto-poke -- the fallback
    lives in game.sh/game_xq.sh itself, not just the CLI that writes the
    file, so it needs its own direct test."""
    spec = GAMES[game]
    live, env, stub_bin = setup_live(tmp_path, game)
    (live / "director.txt").write_text("grok\n")   # no host.txt at all
    log = _herdr_stub(stub_bin, succeed=True)
    r = run_wrapper(live, env, game, "submit", spec["move"])
    assert r.returncode == 0, r.stderr
    assert "HOST NOTIFIED" in r.stdout
    calls = log.read_text().strip().splitlines()
    assert calls[0].split("\t")[2] == "grok"


@pytest.mark.parametrize("game", ["chess", "xiangqi"])
def test_host_txt_present_wins_over_director_txt(tmp_path, game):
    """When both exist (mid-rollout), host.txt is authoritative."""
    spec = GAMES[game]
    live, env, stub_bin = setup_live(tmp_path, game)
    (live / "director.txt").write_text("stale-agent\n")
    (live / "host.txt").write_text("fresh-agent\n")
    log = _herdr_stub(stub_bin, succeed=True)
    r = run_wrapper(live, env, game, "submit", spec["move"])
    assert r.returncode == 0, r.stderr
    calls = log.read_text().strip().splitlines()
    assert calls[0].split("\t")[2] == "fresh-agent"


# ---------------------------------------------------------------------------
# ply arithmetic

@pytest.mark.parametrize("game", ["chess", "xiangqi"])
def test_ply_arithmetic_is_existing_moves_count_plus_one(tmp_path, game):
    """ply=<N> in the STAGED payload is (moves.txt word count) + 1 -- the ply
    being staged right now, one past whatever is already in the log. The
    wrapper computes this purely from `wc -w moves.txt`, independent of
    move legality, so dummy tokens are a legitimate isolated probe."""
    spec = GAMES[game]
    live, env, stub_bin = setup_live(tmp_path, game)
    (live / "host.txt").write_text("grok\n")
    log = _herdr_stub(stub_bin, succeed=True)
    (live / "moves.txt").write_text("a b c d e")   # 5 words already logged
    r = run_wrapper(live, env, game, "submit", spec["move"])
    assert r.returncode == 0, r.stderr
    payload = log.read_text().strip().split("\t")[3]
    assert payload == f"STAGED {spec['chess_name']} {spec['move']} ply=6"


# ---------------------------------------------------------------------------
# quoting

@pytest.mark.parametrize("game", ["chess", "xiangqi"])
def test_metacharacter_laden_name_passes_through_literally(tmp_path, game):
    """Shell-quoting safety: a signer name containing shell metacharacters
    ($(...) `...` ; |) must reach the herdr stub's argv completely
    unevaluated. game.sh interpolates $name inside a double-quoted string
    it builds itself, so ordinary bash variable semantics already make this
    safe -- a variable's stored VALUE is never re-scanned for further
    expansion, only `eval` (not used here) would do that. This test locks
    that in. Uses `id` (harmless, read-only, no side effects) as the
    embedded probe command rather than anything destructive, as
    defense-in-depth in case that reasoning is ever wrong."""
    spec = GAMES[game]
    live, env, stub_bin = setup_live(tmp_path, game)
    (live / "host.txt").write_text("grok\n")
    log = _herdr_stub(stub_bin, succeed=True)

    malicious = "WHITE$(id)`id`;id|id"   # no spaces: keeps seats.txt's naive
                                          # whitespace split() parseable
    (live / "seats.txt").write_text(f"{malicious} white\nBLACK black\n")
    env = {**env, "CHESS_NAME": malicious}

    r = run_wrapper(live, env, game, "submit", spec["move"])
    assert r.returncode == 0, r.stderr
    assert "HOST NOTIFIED" in r.stdout
    calls = log.read_text().strip().splitlines()
    assert len(calls) == 1
    payload = calls[0].split("\t")[3]
    assert payload == f"STAGED {malicious} {spec['move']} ply=1"
    # If the metacharacters had actually been evaluated, `id`'s output
    # (uid=...) would show up somewhere it doesn't belong.
    assert "uid=" not in r.stdout
    assert "uid=" not in r.stderr

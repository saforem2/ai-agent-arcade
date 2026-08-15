"""Tests for ref_cw.py. Run with: uv run --with pytest pytest test_ref_cw.py

Every test runs ref_cw.py as a subprocess against a pytest tmp_path with
ARCADE_LIVE pointed at it — never against /tmp/chess or /tmp/corewar.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE))
import corewar

REF = ENGINE / "ref_cw.py"

KAMIKAZE = """\
;redcode-94
;name Kamikaze
;author Test
;strategy Dies on its first step. A guaranteed loser, for decisive battles.
        org     start
start   dat     #0, #0
        end
"""


def make_live(path):
    path.mkdir(parents=True, exist_ok=True)
    (path / "chat.py").write_text((ENGINE / "chat.py").read_text())
    (path / "names.txt").write_text("RED BLUE\n")
    return path


@pytest.fixture
def live(tmp_path):
    return make_live(tmp_path)


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


def stage_warrior(live, who, source):
    """The CLI + host flow in one step: copy into the inbox, write pending,
    apply via the referee, clear pending (as the host does after every apply
    attempt). Returns the referee's CompletedProcess."""
    sha = corewar.sha256_warrior(source)
    inbox = live / "stage_inbox"
    inbox.mkdir(exist_ok=True)
    (inbox / f"{who}.red").write_text(source)
    (live / "pending.txt").write_text(f"{who}\tstage {sha}")
    r = run(live, "stage", f"{who}\tstage {sha}")
    (live / "pending.txt").unlink(missing_ok=True)
    return r


def stage_both(live, a=corewar.IMP, b=corewar.DWARF):
    r = stage_warrior(live, "RED", a)
    assert r.returncode == 0, r.stderr
    r = stage_warrior(live, "BLUE", b)
    assert r.returncode == 0, r.stderr


def lock(live):
    r = run(live, "lock")
    assert r.returncode == 0, r.stderr
    return r


def battle(live):
    r = run(live, "battle")
    assert r.returncode == 0, r.stderr
    return r


def expected_battle(a_src, b_src):
    """Independently re-derive the whole match from the engine: the seed
    (int.from_bytes(sha256(A+B)[:8], 'big') over LF-normalized sources), then
    per round the engine-drawn offsets and outcome at seed+n. Determinism
    makes this byte-identical to what the referee produced."""
    def norm(s):
        return s.replace("\r\n", "\n").replace("\r", "\n")
    digest = hashlib.sha256((norm(a_src) + norm(b_src)).encode("utf-8")).digest()
    seed = int.from_bytes(digest[:8], "big")
    wa, wb = corewar.parse_warrior(a_src), corewar.parse_warrior(b_src)
    rounds = []
    points_a = 0.0
    for n in range(1, 4):
        b = corewar.Battle(wa, wb, seed=seed + n)
        result = b.run()
        out = "1-0" if result.winner == "A" else "0-1" if result.winner == "B" else "tie"
        rounds.append({"seed": seed + n, "off_a": b.off_a, "off_b": b.off_b,
                       "out": out, "cycles": result.cycles})
        points_a += 1.0 if out == "1-0" else 0.5 if out == "tie" else 0.0
    match = "1-0" if points_a > 1.5 else "0-1" if points_a < 1.5 else "1/2-1/2"
    return seed, rounds, match


# ---------------------------------------------------------------------------
# ARCADE_LIVE plumbing (mirrors test_ref_xq.py)

def test_arcade_live_propagates_to_chat_module(live):
    """chat.py resolves its own D independently (default /tmp/chess) -- ref_cw.py
    must setdefault ARCADE_LIVE onto os.environ before importing chat so the two
    modules always agree on the live dir. Import-only, no ref_cw CLI dispatch."""
    script = (
        f"import sys; sys.path.insert(0, {str(ENGINE)!r})\n"
        "import ref_cw, chat\n"
        "assert ref_cw.D == chat.D, (ref_cw.D, chat.D)\n"
        "print('OK')\n"
    )
    r = subprocess.run([sys.executable, "-c", script], cwd=live,
                       env={"ARCADE_LIVE": str(live), "PATH": "/usr/bin:/bin"},
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "OK" in r.stdout


# ---------------------------------------------------------------------------
# init

def test_init_creates_empty_transcript_and_dirs(live):
    init(live)
    assert (live / "moves.txt").read_text() == ""
    assert (live / "warriors").is_dir() and list((live / "warriors").iterdir()) == []
    assert (live / "stage_inbox").is_dir() and list((live / "stage_inbox").iterdir()) == []
    assert not (live / "result.txt").exists()
    assert not (live / "TAMPER.txt").exists()


def test_init_refuses_over_nonempty_log_without_force(live):
    init(live)
    stage_both(live)
    lock(live)
    before = (live / "moves.txt").read_text()
    r = run(live, "init")
    assert r.returncode == 5
    assert "REFUSING" in r.stderr
    assert (live / "moves.txt").read_text() == before   # transcript untouched


def test_init_force_overrides_and_clears_match_state(live):
    init(live)
    stage_both(live)
    lock(live)
    battle(live)
    assert (live / "result.txt").exists()
    r = init(live, force=True)
    assert "OK" in r.stdout
    assert (live / "moves.txt").read_text() == ""
    for fn in ("result.txt", "battle.json", "pending.txt", "TAMPER.txt"):
        assert not (live / fn).exists(), fn
    assert list((live / "warriors").iterdir()) == []
    # results.txt is the cumulative ledger across matches -- init never touches it
    assert (live / "results.txt").read_text().strip() != ""


# ---------------------------------------------------------------------------
# stage

def test_stage_installs_to_the_right_seats(live):
    init(live)
    stage_both(live)
    assert (live / "warriors/A.red").read_text() == corewar.IMP
    assert (live / "warriors/B.red").read_text() == corewar.DWARF
    # a successful stage clears pending.txt and the inbox copy
    assert not (live / "pending.txt").exists()
    assert list((live / "stage_inbox").iterdir()) == []


def test_stage_rejected_malformed_warrior(live):
    init(live)
    r = stage_warrior(live, "RED", "bogus $0, $0\nend\n")
    assert r.returncode == 1
    assert r.stdout.strip() == "ILLEGAL"
    assert "unknown opcode" in r.stderr          # full reason to the stager
    assert not (live / "warriors/A.red").exists()
    # nothing about the rejection reaches the room
    chatlog = (live / "chat.log").read_text() if (live / "chat.log").exists() else ""
    assert "opcode" not in chatlog


def test_stage_rejected_over_100_instructions(live):
    init(live)
    r = stage_warrior(live, "RED", "loop for 101\nnop\nrof\nend\n")
    assert r.returncode == 1
    assert r.stdout.strip() == "ILLEGAL"
    assert "101 instructions" in r.stderr
    assert not (live / "warriors/A.red").exists()


def test_stage_rejected_on_hash_mismatch(live):
    init(live)
    inbox = live / "stage_inbox"
    inbox.mkdir(exist_ok=True)
    (inbox / "RED.red").write_text(corewar.IMP)
    bogus_sha = "0" * 64
    (live / "pending.txt").write_text(f"RED\tstage {bogus_sha}")
    r = run(live, "stage", f"RED\tstage {bogus_sha}")
    assert r.returncode == 1
    assert "does not match its sha256 receipt" in r.stderr
    assert not (live / "warriors/A.red").exists()


def test_stage_rejected_without_inbox_file(live):
    init(live)
    sha = corewar.sha256_warrior(corewar.IMP)
    r = run(live, "stage", f"RED\tstage {sha}")
    assert r.returncode == 1
    assert "no staged warrior" in r.stderr


def test_stage_wrong_author_rejected(live):
    init(live)
    sha = corewar.sha256_warrior(corewar.IMP)
    inbox = live / "stage_inbox"
    inbox.mkdir(exist_ok=True)
    (inbox / "INTRUDER.red").write_text(corewar.IMP)
    r = run(live, "stage", f"INTRUDER\tstage {sha}")
    assert r.returncode == 4
    assert "WRONG AUTHOR" in r.stderr
    assert not (live / "warriors/A.red").exists()


def test_restage_overwrites_until_lock(live):
    init(live)
    stage_warrior(live, "RED", KAMIKAZE)
    assert (live / "warriors/A.red").read_text() == KAMIKAZE
    stage_warrior(live, "RED", corewar.IMP)
    assert (live / "warriors/A.red").read_text() == corewar.IMP


def test_stage_after_lock_refused(live):
    init(live)
    stage_both(live)
    lock(live)
    r = stage_warrior(live, "RED", KAMIKAZE)
    assert r.returncode == 1
    assert r.stdout.strip() == "ILLEGAL"
    assert "locked" in r.stderr
    assert (live / "warriors/A.red").read_text() == corewar.IMP   # untouched


# ---------------------------------------------------------------------------
# lock

def test_lock_requires_both_seats(live):
    init(live)
    stage_warrior(live, "RED", corewar.IMP)
    r = run(live, "lock")
    assert r.returncode == 1
    assert "both seats" in r.stderr
    assert (live / "moves.txt").read_text() == ""


def test_lock_appends_load_lines_and_prints_hashes(live):
    init(live)
    stage_both(live)
    r = lock(live)
    sha_a, sha_b = corewar.sha256_warrior(corewar.IMP), corewar.sha256_warrior(corewar.DWARF)
    assert r.stdout.splitlines() == ["OK locked", f"A {sha_a}", f"B {sha_b}"]
    assert (live / "moves.txt").read_text() == f"LOAD A {sha_a}\nLOAD B {sha_b}\n"
    data = json.loads((live / "battle.json").read_text())
    assert data["warriors"]["A"]["sha256"] == sha_a
    assert data["warriors"]["A"]["name"] == "Imp"
    assert data["warriors"]["B"]["sha256"] == sha_b
    assert data["rounds"] == []
    assert data["names"] == ["RED", "BLUE"]
    seed, _, _ = expected_battle(corewar.IMP, corewar.DWARF)
    assert data["seed"] == seed


def test_lock_twice_refused(live):
    init(live)
    stage_both(live)
    lock(live)
    r = run(live, "lock")
    assert r.returncode == 1
    assert "already locked" in r.stderr


# ---------------------------------------------------------------------------
# battle + verify + resolve

def test_full_lifecycle_transcript_ledger_and_verify(live):
    """init -> stage IMP/DWARF -> check -> lock -> battle -> the transcript,
    battle.json, result.txt and the results.txt line all agree with an
    independent re-simulation of the same seed -> verify OK."""
    init(live)
    stage_both(live)
    r = run(live, "check")
    assert "BATTLE READY" in r.stdout
    lock(live)
    r = battle(live)
    seed, rounds, match = expected_battle(corewar.IMP, corewar.DWARF)
    lines = (live / "moves.txt").read_text().splitlines()
    assert lines[:2] == [f"LOAD A {corewar.sha256_warrior(corewar.IMP)}",
                         f"LOAD B {corewar.sha256_warrior(corewar.DWARF)}"]
    assert len(lines) == 2 + 6     # LOAD pair + 3 x (ROUND + OUT)
    for i, rd in enumerate(rounds, 1):
        assert f"ROUND {i} seed={rd['seed']} off={rd['off_a']},{rd['off_b']}" in lines
        assert f"ROUND {i} OUT {rd['out']} cycles={rd['cycles']}" in lines
    assert f"GAMEOVER {match}" in r.stdout
    data = json.loads((live / "battle.json").read_text())
    assert [rd["out"] for rd in data["rounds"]] == [rd["out"] for rd in rounds]
    assert (live / "results.txt").read_text().strip() == f"RED {match} BLUE"
    assert (live / "result.txt").exists()
    assert f"RED {match} BLUE" in (live / "banner.txt").read_text()
    # the referee posts the bare result to the room itself
    assert f"RED {match} BLUE (battle)" in (live / "chat.log").read_text()
    r = run(live, "verify")
    assert r.returncode == 0, r.stderr
    assert "OK verified 3 rounds" in r.stdout


def test_battle_decisive_result_line(live):
    """A warrior that dies on its first step loses every round: 0-1."""
    init(live)
    stage_both(live, a=KAMIKAZE, b=corewar.IMP)
    lock(live)
    r = battle(live)
    assert "GAMEOVER 0-1" in r.stdout
    assert (live / "results.txt").read_text().strip() == "RED 0-1 BLUE"
    assert "BLUE wins by battle" in (live / "result.txt").read_text()
    lines = (live / "moves.txt").read_text().splitlines()
    assert sum(1 for ln in lines if ln.endswith("OUT 0-1 cycles=1") or " OUT 0-1 " in ln) == 3


def test_battle_is_deterministic_across_processes(tmp_path):
    """The whole flow twice in two separate live dirs must produce
    byte-identical transcripts -- the archive can re-simulate forever."""
    transcripts = []
    for name in ("d1", "d2"):
        d = make_live(tmp_path / name)
        init(d)
        stage_both(d)
        lock(d)
        battle(d)
        transcripts.append((d / "moves.txt").read_bytes())
    assert transcripts[0] == transcripts[1]


def test_battle_without_lock_refused(live):
    init(live)
    stage_both(live)
    r = run(live, "battle")
    assert r.returncode == 1
    assert "no lock" in r.stderr
    assert (live / "moves.txt").read_text() == ""


def test_second_battle_refused(live):
    init(live)
    stage_both(live)
    lock(live)
    battle(live)
    before = (live / "moves.txt").read_text()
    r = run(live, "battle")
    assert r.returncode == 6
    assert "already over" in r.stderr
    assert (live / "moves.txt").read_text() == before   # the ledger never re-runs


def test_verify_halt_on_transcript_corruption_then_resolve(live):
    init(live)
    stage_both(live)
    lock(live)
    battle(live)
    original = (live / "moves.txt").read_text()
    lines = original.splitlines()
    out_idx = next(i for i, ln in enumerate(lines) if " OUT " in ln)
    lines[out_idx] = "ROUND 1 OUT 0-1 cycles=12"     # a lie about round 1
    (live / "moves.txt").write_text("\n".join(lines) + "\n")
    r = run(live, "verify")
    assert r.returncode == 3
    assert r.stdout.strip() == "ILLEGAL"
    assert "TAMPER DETECTED" in r.stderr
    assert (live / "TAMPER.txt").exists()
    # resolve cannot fix a transcript that contradicts the simulation
    r = run(live, "resolve")
    assert r.returncode == 1
    assert "CANNOT RESOLVE" in r.stdout
    assert (live / "TAMPER.txt").exists()
    # a human restores the transcript; resolve rebuilds the cache and clears
    (live / "moves.txt").write_text(original)
    (live / "battle.json").unlink()
    r = run(live, "resolve")
    assert r.returncode == 0, r.stderr
    assert "OK resolved" in r.stdout
    assert not (live / "TAMPER.txt").exists()
    assert json.loads((live / "battle.json").read_text())["rounds"]
    r = run(live, "verify")
    assert r.returncode == 0


def test_verify_halt_on_warrior_swap(live):
    """A swapped warrior file is as much tampering as an edited transcript:
    it no longer matches its LOAD hash."""
    init(live)
    stage_both(live)
    lock(live)
    battle(live)
    (live / "warriors/A.red").write_text(KAMIKAZE)
    r = run(live, "verify")
    assert r.returncode == 3
    assert "TAMPER DETECTED" in r.stderr
    assert "does not match its LOAD hash" in (live / "TAMPER.txt").read_text()


def test_verify_in_workshop_is_trivially_ok(live):
    init(live)
    r = run(live, "verify")
    assert r.returncode == 0
    assert "OK verified 0 rounds" in r.stdout


# ---------------------------------------------------------------------------
# resign

def test_resign_mid_workshop(live):
    init(live)
    r = run(live, "stage", "RED\tresign")
    assert r.returncode == 0, r.stderr
    assert "GAMEOVER 0-1 — BLUE wins by resignation" in r.stdout
    assert (live / "results.txt").read_text().strip() == "RED 0-1 BLUE"
    assert "BLUE wins by resignation (RED resigned)" in (live / "result.txt").read_text()
    # a workshop resignation means no battle is ever run
    assert (live / "moves.txt").read_text() == ""
    r = run(live, "lock")
    assert r.returncode == 6
    r = run(live, "battle")
    assert r.returncode == 6


def test_resign_post_lock(live):
    init(live)
    stage_both(live)
    lock(live)
    r = run(live, "stage", "BLUE\tresign")
    assert r.returncode == 0, r.stderr
    assert "GAMEOVER 1-0 — RED wins by resignation" in r.stdout
    assert (live / "results.txt").read_text().strip() == "RED 1-0 BLUE"
    r = run(live, "battle")
    assert r.returncode == 6


def test_resign_requires_seated_author(live):
    init(live)
    r = run(live, "stage", "SOMEONE_ELSE\tresign")
    assert r.returncode == 4
    assert "does not hold a seat" in r.stderr


def test_unsigned_resign_rejected(live):
    init(live)
    r = run(live, "stage", "resign")
    assert r.returncode == 4
    assert not (live / "result.txt").exists()


def test_stage_after_resignation_refused(live):
    init(live)
    run(live, "stage", "RED\tresign")
    r = stage_warrior(live, "BLUE", corewar.IMP)
    assert r.returncode == 6
    assert "already over" in r.stderr


# ---------------------------------------------------------------------------
# check (read-only readiness)

def _snapshot(live):
    return {p.relative_to(live): p.read_bytes()
            for p in sorted(live.rglob("*")) if p.is_file()}


def test_check_reports_readiness_and_changes_nothing(live):
    init(live)
    r = run(live, "check")
    assert r.returncode == 0, r.stderr
    assert "phase: workshop" in r.stdout
    assert "RED=empty" in r.stdout and "BLUE=empty" in r.stdout
    assert "BATTLE READY" not in r.stdout
    stage_warrior(live, "RED", corewar.IMP)
    r = run(live, "check")
    assert "RED=staged (valid)" in r.stdout
    assert "BLUE=empty" in r.stdout
    assert "BATTLE READY" not in r.stdout        # one seat is not a battle
    before = _snapshot(live)
    run(live, "check")
    assert _snapshot(live) == before             # read-only, byte for byte


def test_check_reports_pending_and_invalid_hold(live):
    init(live)
    (live / "pending.txt").write_text("RED\tstage " + "ab" * 32)
    (live / "warriors").mkdir(exist_ok=True)
    (live / "warriors/B.red").write_text("bogus $0\nend\n")
    r = run(live, "check")
    # pending.txt is re-cleaned for display (whitespace collapses, control
    # bytes strip) -- the tab between author and token prints as a space.
    assert "pending: RED stage" in r.stdout
    assert "BLUE=staged INVALID" in r.stdout
    assert "BATTLE READY" not in r.stdout


# ---------------------------------------------------------------------------
# misc

def test_unknown_command_errors(live):
    r = run(live, "bogus")
    assert r.returncode == 2
    assert "unknown command" in r.stderr


def test_verbs_refuse_while_halted(live):
    init(live)
    stage_both(live)
    lock(live)
    battle(live)
    (live / "warriors/A.red").write_text(KAMIKAZE)
    run(live, "verify")     # halts
    assert (live / "TAMPER.txt").exists()
    for args in (("stage", "RED\tresign"), ("lock",), ("battle",)):
        r = run(live, *args)
        assert r.returncode == 3, args
        assert "halted" in r.stderr


# ---------------------------------------------------------------------------
# adversarial-review regressions (round 2)

def test_lock_refuses_cleanly_over_invalid_hold(live):
    """BUG-1: a hand-placed invalid warrior in the hold must make lock a
    clean refusal BEFORE any transcript write -- previously warrior_meta's
    parse raised RedcodeError mid-command: traceback + half-written LOAD
    lines + a later mislabeled TAMPER halt."""
    init(live)
    stage_warrior(live, "RED", corewar.IMP)
    (live / "warriors/B.red").write_text("bogus $0\nend\n")   # hand-placed garbage
    r = run(live, "lock")
    assert r.returncode == 1
    assert r.stdout.strip() == "ILLEGAL"
    assert "Traceback" not in r.stderr
    assert "not battle-ready" in r.stderr and "unknown opcode" in r.stderr
    assert (live / "moves.txt").read_text() == ""          # transcript untouched
    assert not (live / "battle.json").exists()
    assert not (live / "TAMPER.txt").exists()
    # and the follow-on battle refuses as "no lock", not as tamper
    r = run(live, "battle")
    assert r.returncode == 1
    assert "no lock" in r.stderr


def test_prefix_name_resign_refused_when_seats_txt_present(live):
    """RISK-1: with seats.txt on disk the referee requires an EXACT seat-name
    match -- chat.role_of's prefix heuristic would otherwise let
    'red-spectator' resign RED's seat."""
    init(live)
    (live / "seats.txt").write_text("RED white\nBLUE black\n")
    r = run(live, "stage", "red-spectator\tresign")
    assert r.returncode == 4
    assert "WRONG AUTHOR" in r.stderr
    assert not (live / "result.txt").exists()
    assert not (live / "results.txt").exists()


def test_exact_seat_names_still_apply_when_seats_txt_present(live):
    init(live)
    (live / "seats.txt").write_text("RED white\nBLUE black\n")
    r = run(live, "stage", "BLUE\tresign")
    assert r.returncode == 0, r.stderr
    assert "GAMEOVER 1-0" in r.stdout


def test_prefix_heuristic_remains_without_seats_txt(live):
    """Documented fallback: no seats.txt (older deploys, manual use) means
    the prefix heuristic is all there is -- 'red-spectator' still maps to
    the red seat, exactly like chat.require_seated's own no-seats no-op."""
    init(live)
    r = run(live, "stage", "red-spectator\tresign")
    assert r.returncode == 0, r.stderr
    assert "GAMEOVER 0-1" in r.stdout


def test_verify_halts_on_attacker_seeded_rounds(live):
    """RISK-2: honestly-simulated OUT lines transplanted onto attacker-chosen
    seeds must halt verify -- the seed/offsets are derived from the locked
    warriors, never trusted from the transcript."""
    init(live)
    stage_both(live)
    lock(live)
    wa, wb = corewar.parse_warrior(corewar.IMP), corewar.parse_warrior(corewar.DWARF)
    lines = (live / "moves.txt").read_text()
    for n in range(1, 4):
        seed = 12345 + n                       # NOT battle_seed(A, B) + n
        b = corewar.Battle(wa, wb, seed=seed)
        result = b.run()
        lines += corewar.battle_transcript(seed, b.off_a, b.off_b, result, round_no=n)
    (live / "moves.txt").write_text(lines)
    r = run(live, "verify")
    assert r.returncode == 3
    assert r.stdout.strip() == "ILLEGAL"
    assert "TAMPER DETECTED" in r.stderr
    assert "does not derive from the locked warriors" in (live / "TAMPER.txt").read_text()


def test_traversal_author_refused_and_deletes_nothing(live):
    """RISK-3: 'RED/../../warriors/A' as a stage author must be a clean
    refusal at the door -- previously it prefix-matched the red seat and the
    resign path's inbox cleanup unlinked warriors/A.red."""
    init(live)
    stage_warrior(live, "RED", corewar.IMP)
    assert (live / "warriors/A.red").exists()
    for token in ("resign", "stage " + corewar.sha256_warrior(corewar.IMP)):
        r = run(live, "stage", f"RED/../../warriors/A\t{token}")
        assert r.returncode == 4, token
        assert "WRONG AUTHOR" in r.stderr
        assert "Traceback" not in r.stderr
        assert (live / "warriors/A.red").read_text() == corewar.IMP   # untouched
        assert not (live / "result.txt").exists()


def test_resign_reapply_never_double_appends(live):
    """NIT-1: the resign path shares finish_native's ledger dedup -- a
    re-applied resignation after a hand-deleted result.txt must not add a
    second results.txt line."""
    init(live)
    r = run(live, "stage", "BLUE\tresign")
    assert r.returncode == 0
    (live / "result.txt").unlink()             # hand-deleted: the gate reopens
    r = run(live, "stage", "BLUE\tresign")
    assert r.returncode == 0, r.stderr
    lines = [l for l in (live / "results.txt").read_text().splitlines() if l.strip()]
    assert lines == ["RED 1-0 BLUE"]


def test_check_cleans_pending_control_bytes(live):
    """NIT-2 (ref side): a hand-written pending.txt's ESC bytes must never
    reach the host's terminal via check."""
    init(live)
    (live / "pending.txt").write_text("RED\x1b[31mEVIL\x1b[0m\tresign")
    r = run(live, "check")
    assert r.returncode == 0, r.stderr
    assert "\x1b" not in r.stdout           # no escape sequence can ever form
    assert "pending: RED[31mEVIL[0m resign" in r.stdout   # printable husk, cleaned

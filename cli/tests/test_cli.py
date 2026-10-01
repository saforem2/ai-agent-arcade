import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from arcade_cli import main as m

ENGINE = Path(__file__).resolve().parents[2] / "engine"


@pytest.fixture(autouse=True, scope="session")
def no_production_live_dirs():
    """Hard safety net: this repo has incident history (design-history.md
    §10) of test/verification runs clobbering the real /tmp/chess. Every
    test must point at a scratch dir via --live-dir/tmp_path; none may rely
    on default_live_for() resolving to a production dir. /tmp/xiangqi and
    /tmp/corewar must never be created at all -- no legitimate test target
    lives there.
    """
    chess_existed = Path("/tmp/chess").exists()
    xiangqi_existed = Path("/tmp/xiangqi").exists()
    corewar_existed = Path("/tmp/corewar").exists()
    chess_chat = Path("/tmp/chess/chat.log")
    chat_mtime_before = chess_chat.stat().st_mtime if chess_chat.exists() else None
    yield
    assert Path("/tmp/xiangqi").exists() == xiangqi_existed, (
        "a test created /tmp/xiangqi -- every xiangqi test must pass an explicit "
        "--live-dir under tmp_path")
    assert Path("/tmp/corewar").exists() == corewar_existed, (
        "a test created /tmp/corewar -- every corewar test must pass an explicit "
        "--live-dir under tmp_path")
    assert Path("/tmp/chess").exists() == chess_existed, (
        "a test created /tmp/chess where it did not exist before")
    if chat_mtime_before is not None and chess_chat.exists():
        assert chess_chat.stat().st_mtime == chat_mtime_before, (
            "a test wrote into the real /tmp/chess/chat.log")


class FakeArgs:
    def __init__(self, root, live, game="chess", **kw):
        self.root = str(root)
        self.live_dir = str(live)
        self.game = game
        self.result = None
        self.keep_room = False
        self.__dict__.update(kw)


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = tmp_path / "arcade"
    (root / "engine").mkdir(parents=True)
    for fn in m.DEPLOY_FILES:
        (root / "engine" / fn).write_text(f"# stub {fn}\n")
    live = tmp_path / "live"
    monkeypatch.setattr(m, "run_ref_init",
                         lambda live, force, game="chess": (live / "moves.txt").write_text(""))
    return root, live


def start(root, live, white="kimi", black="codex", host="grok", force=False, keep_room=False):
    args = FakeArgs(root, live, white=white, black=black, host=host, force=force,
                     keep_room=keep_room)
    m.cmd_start(args)


def test_match_numbering(env, capsys):
    root, live = env
    start(root, live)
    # match-001 is still "live" (never archived) — numbering itself is what's
    # under test here, not the guard, so force through.
    start(root, live.parent / "live2", force=True)
    dirs = sorted(p.name for p in (root / "games/chess").iterdir())
    assert dirs == ["match-001", "match-002"]
    data2 = json.loads((root / "games/chess/match-002/match.json").read_text())
    assert data2["match"] == 2


def test_start_refuses_over_live_match(env, capsys):
    root, live = env
    start(root, live)
    (live / "moves.txt").write_text("e4 e5")

    args = FakeArgs(root, live, white="kimi", black="codex", host="grok", force=False)
    with pytest.raises(SystemExit):
        m.cmd_start(args)

    # only one match dir was created
    assert len(list((root / "games/chess").iterdir())) == 1


def test_start_force_overrides(env):
    root, live = env
    start(root, live)
    (live / "moves.txt").write_text("e4 e5")
    start(root, live, force=True)
    assert len(list((root / "games/chess").iterdir())) == 2


def test_deploy_file_set_lands(env):
    root, live = env
    start(root, live)
    for fn in m.DEPLOY_FILES:
        assert (live / fn).exists(), fn
    names = (live / "names.txt").read_text().split()
    assert names == ["KIMI", "CODEX"]


def test_start_writes_seats_txt(env):
    """seats.txt is the seat-bound identity contract game_cli.py hard-refuses
    submit/resign/offer-draw/accept-draw against (game-5 retro fix)."""
    root, live = env
    start(root, live)
    lines = (live / "seats.txt").read_text().splitlines()
    assert lines == ["KIMI white", "CODEX black"]


def test_archive_round_trip(env):
    root, live = env
    start(root, live)
    (live / "moves.txt").write_text("e4 e5 Nf3")
    (live / "fen.txt").write_text("fake fen")
    (live / "chat.log").write_text("1\tDIRECTOR\thello\n")
    (live / "results.txt").write_text("CODEX 1-0 KIMI\n")
    (live / "names.txt").write_text("KIMI CODEX\n")

    args = FakeArgs(root, live, result=None)
    m.cmd_archive(args)

    match_dir = root / "games/chess/match-001"
    data = json.loads((match_dir / "match.json").read_text())
    assert data["status"] == "complete"
    assert data["result"] == "CODEX 1-0 KIMI"
    assert data["ended"] is not None
    assert (match_dir / "moves.txt").read_text() == "e4 e5 Nf3"
    # live dir untouched
    assert (live / "moves.txt").read_text() == "e4 e5 Nf3"

    # idempotent re-archive with explicit result
    args2 = FakeArgs(root, live, result="CODEX 1-0 KIMI (resign)")
    m.cmd_archive(args2)
    data2 = json.loads((match_dir / "match.json").read_text())
    assert data2["result"] == "CODEX 1-0 KIMI (resign)"


def test_archive_preserves_decision_log(env):
    root, live = env
    start(root, live)
    decision = '{"ply": 1, "move": "e4", "rationale": "Claims the center."}\n'
    (live / "decision_log.jsonl").write_text(decision)

    m.cmd_archive(FakeArgs(root, live, result="KIMI 1-0 CODEX"))

    archived = root / "games/chess/match-001/decision_log.jsonl"
    assert archived.read_text() == decision


def test_start_clears_previous_decision_log(env):
    root, live = env
    start(root, live)
    (live / "decision_log.jsonl").write_text('{"ply": 1}\n')

    start(root, live, force=True)

    assert not (live / "decision_log.jsonl").exists()


@pytest.fixture
def archive_scratch(monkeypatch):
    """Fresh archive-regression tree, made by mktemp under the safe root."""
    scratch_root = Path("/tmp/arcade-scratch")
    scratch_root.mkdir(parents=True, exist_ok=True)
    scratch = Path(subprocess.check_output(
        ["mktemp", "-d", str(scratch_root / "archfix-test.XXXXXX")], text=True
    ).strip()).resolve()
    assert scratch.parent == scratch_root.resolve()

    root = scratch / "arcade"
    live = scratch / "live"
    live.mkdir()
    monkeypatch.setenv("ARCADE_LIVE", str(live))
    try:
        yield root, live, scratch
    finally:
        if scratch.parent == scratch_root.resolve() and scratch.name.startswith("archfix-test."):
            shutil.rmtree(scratch)


def write_archive_match(root, game, number, live, status="live", result=None, ended=None):
    match_dir = root / "games" / game / f"match-{number:03d}"
    match_dir.mkdir(parents=True)
    m.write_match_json(match_dir, {
        "match": number,
        "game": game,
        "live_dir": str(live),
        "status": status,
        "result": result,
        "ended": ended,
    })
    return match_dir


def test_archive_without_game_infers_xiangqi_from_live_dir(archive_scratch):
    root, live, scratch = archive_scratch
    xiangqi_match = write_archive_match(root, "xiangqi", 1, live)
    chess_match = write_archive_match(
        root, "chess", 99, scratch / "other-chess-live", status="complete",
        result="OLD CHESS RESULT", ended="2026-01-01T00:00:00")
    (chess_match / "moves.txt").write_text("protected chess moves")
    chess_json_before = (chess_match / "match.json").read_text()

    (live / "moves.txt").write_text("h2e2 h9g7")
    args = m.build_parser().parse_args(
        ["archive", "--result", "KIMI 1-0 CODEX (xiangqi resign)"])
    args.root = str(root)
    assert args.game is None

    m.cmd_archive(args)

    xiangqi_data = json.loads((xiangqi_match / "match.json").read_text())
    assert xiangqi_data["status"] == "complete"
    assert xiangqi_data["result"] == "KIMI 1-0 CODEX (xiangqi resign)"
    assert (xiangqi_match / "moves.txt").read_text() == "h2e2 h9g7"
    assert (chess_match / "moves.txt").read_text() == "protected chess moves"
    assert (chess_match / "match.json").read_text() == chess_json_before


def test_archive_without_game_refuses_unmatched_live_dir(archive_scratch, capsys):
    root, live, scratch = archive_scratch
    unrelated = write_archive_match(
        root, "chess", 1, scratch / "other-live", status="complete",
        result="ORIGINAL", ended="2026-01-01T00:00:00")
    (unrelated / "moves.txt").write_text("protected")
    json_before = (unrelated / "match.json").read_text()
    (live / "moves.txt").write_text("must not be copied")
    args = m.build_parser().parse_args(["archive", "--result", "WRONG"])
    args.root = str(root)

    with pytest.raises(SystemExit):
        m.cmd_archive(args)

    err = capsys.readouterr().err
    assert f"no live match for {live.resolve()}" in err
    assert "pass --game <game>" in err
    assert (unrelated / "moves.txt").read_text() == "protected"
    assert (unrelated / "match.json").read_text() == json_before


@pytest.mark.parametrize(("status", "message"), [
    ("live", "--game chess selected live match match-001"),
    ("complete", "--game chess's newest match belongs"),
])
def test_archive_with_game_refuses_live_dir_mismatch(
        archive_scratch, capsys, status, message):
    root, live, scratch = archive_scratch
    other_live = scratch / "other-chess-live"
    chess_match = write_archive_match(root, "chess", 1, other_live, status=status)
    (chess_match / "moves.txt").write_text("protected chess moves")
    json_before = (chess_match / "match.json").read_text()
    (live / "moves.txt").write_text("incoming other-game moves")
    args = m.build_parser().parse_args(
        ["archive", "--game", "chess", "--result", "WRONG"])
    args.root = str(root)

    with pytest.raises(SystemExit):
        m.cmd_archive(args)

    err = capsys.readouterr().err
    assert message in err
    assert "refusing cross-game archive" in err
    assert (chess_match / "moves.txt").read_text() == "protected chess moves"
    assert (chess_match / "match.json").read_text() == json_before


def test_archive_idempotent_rearchive_requires_matching_live_dir(archive_scratch):
    root, live, _ = archive_scratch
    chess_match = write_archive_match(
        root, "chess", 1, live, status="complete", result="OLD RESULT",
        ended="2026-01-01T00:00:00")
    (chess_match / "moves.txt").write_text("old archived moves")
    (live / "moves.txt").write_text("current archived moves")
    args = m.build_parser().parse_args(
        ["archive", "--game", "chess", "--result", "UPDATED RESULT"])
    args.root = str(root)

    m.cmd_archive(args)

    data = json.loads((chess_match / "match.json").read_text())
    assert data["status"] == "complete"
    assert data["result"] == "UPDATED RESULT"
    assert data["ended"] != "2026-01-01T00:00:00"
    assert (chess_match / "moves.txt").read_text() == "current archived moves"


def test_start_after_archive_succeeds_without_force(env, capsys):
    """The normal start -> archive -> start path: the prior match's leftover
    non-empty moves.txt in the live dir must not require --force once it's
    archived (status=complete), and the new match gets the next number. Also
    covers the pre-init snapshot: the leftover moves.txt/fen.txt must be
    backed up before ref.py init overwrites them."""
    root, live = env
    start(root, live)
    (live / "moves.txt").write_text("e4 e5 Nf3")
    (live / "fen.txt").write_text("some fen")
    m.cmd_archive(FakeArgs(root, live))

    start(root, live)  # no --force

    dirs = sorted(p.name for p in (root / "games/chess").iterdir())
    assert dirs == ["match-001", "match-002"]
    data2 = json.loads((root / "games/chess/match-002/match.json").read_text())
    assert data2["match"] == 2
    assert data2["status"] == "live"

    backup = live / "backup"
    assert (backup / "moves.match-001.txt").read_text() == "e4 e5 Nf3"
    assert (backup / "fen.match-001.txt").read_text() == "some fen"
    out = capsys.readouterr().out
    assert "snapshotted" in out and str(backup) in out


def test_scratch_guard_blocks_default_live_dir_with_scratch_root(env, monkeypatch):
    """The incident: ARCADE_ROOT points at a scratch tree but no --live-dir /
    ARCADE_LIVE was given, so the live dir silently defaults to the real
    /tmp/chess. Must refuse outright — no --force override."""
    root, live = env
    monkeypatch.setenv("ARCADE_ROOT", str(root))
    monkeypatch.delenv("ARCADE_LIVE", raising=False)
    args = FakeArgs(root, live, white="kimi", black="codex", host="grok", force=True)
    args.live_dir = None  # no --live-dir flag at all

    with pytest.raises(SystemExit):
        m.cmd_start(args)

    games_chess = root / "games/chess"
    assert not games_chess.exists() or list(games_chess.iterdir()) == []


def test_scratch_guard_allows_with_explicit_live_dir_flag(env, monkeypatch):
    root, live = env
    monkeypatch.setenv("ARCADE_ROOT", str(root))
    monkeypatch.delenv("ARCADE_LIVE", raising=False)
    start(root, live)  # FakeArgs always sets --live-dir explicitly
    assert (root / "games/chess/match-001").exists()


def test_scratch_guard_allows_with_arcade_live_env(env, monkeypatch):
    root, live = env
    monkeypatch.setenv("ARCADE_ROOT", str(root))
    monkeypatch.setenv("ARCADE_LIVE", str(live))
    args = FakeArgs(root, live, white="kimi", black="codex", host="grok", force=False)
    args.live_dir = None

    m.cmd_start(args)

    assert (root / "games/chess/match-001").exists()


def test_start_ref_init_failure_leaves_no_orphaned_match_dir(env, monkeypatch):
    root, live = env

    def boom(live, force, game="chess"):
        raise subprocess.CalledProcessError(5, ["ref.py", "init"])

    monkeypatch.setattr(m, "run_ref_init", boom)
    args = FakeArgs(root, live, white="kimi", black="codex", host="grok", force=False)
    with pytest.raises(SystemExit):
        m.cmd_start(args)

    assert list((root / "games/chess").iterdir()) == []


def test_status_reports_ply_and_pending(env, capsys):
    root, live = env
    start(root, live)
    (live / "moves.txt").write_text("e4 e5 Nf3")
    (live / "fen.txt").write_text("fake fen\n")
    (live / "pending.txt").write_text("KIMI\tNc6")
    (live / "results.txt").write_text("CODEX 1-0 KIMI\n")

    m.cmd_status(FakeArgs(root, live))
    out = capsys.readouterr().out
    assert "ply: 3" in out
    assert "to move: black" in out
    assert "last move: Nf3" in out
    assert "fake fen" in out
    assert "Nc6 (staged by KIMI)" in out
    assert "\t" not in out


def test_seat_parses_human_with_name():
    s = m.seat("human:ada")
    assert s == {"agent": "human", "name": "ADA"}


def test_seat_bare_human_errors():
    with pytest.raises(SystemExit):
        m.seat("human")


def test_seat_human_colon_no_name_errors():
    with pytest.raises(SystemExit):
        m.seat("human:")


def test_seat_human_prefix_case_insensitive():
    assert m.seat("HUMAN:ada") == {"agent": "human", "name": "ADA"}
    assert m.seat("Human:ada") == {"agent": "human", "name": "ADA"}
    with pytest.raises(SystemExit):
        m.seat("HUMAN")


def test_seat_human_name_with_whitespace_errors():
    with pytest.raises(SystemExit):
        m.seat("human:ada lovelace")


def test_seat_agent_unchanged():
    assert m.seat("kimi") == {"agent": "kimi", "name": "KIMI"}


def test_start_human_seat_in_match_json(env):
    root, live = env
    start(root, live, white="human:ada", black="codex")
    data = json.loads((root / "games/chess/match-001/match.json").read_text())
    assert data["seats"]["white"] == {"agent": "human", "name": "ADA"}
    assert data["seats"]["black"] == {"agent": "codex", "name": "CODEX"}


def test_start_human_seat_runbook_output(env, capsys):
    root, live = env
    start(root, live, white="human:ada", black="codex")
    out = capsys.readouterr().out

    assert "export CHESS_NAME=ADA" in out
    assert "# You are ADA (white). Play with:" in out
    assert f"bash {live}/game.sh submit '<move>'" in out
    assert f"bash {live}/game.sh say '<message>'" in out
    assert f"bash {live}/game.sh show" in out

    # no herdr seating command was printed for the human seat
    assert "herdr agent start human" not in out
    # the agent (codex) seat still gets its herdr line
    assert "herdr agent start codex --kind codex" in out


def test_start_bare_human_errors(env):
    root, live = env
    with pytest.raises(SystemExit):
        start(root, live, white="human", black="codex")


def test_start_agent_seats_runbook_unchanged(env, capsys):
    root, live = env
    start(root, live, white="kimi", black="codex")
    out = capsys.readouterr().out
    assert "herdr agent start kimi --kind kimi" in out
    assert "herdr agent start codex --kind codex" in out
    assert "CHESS_NAME=ADA" not in out


def test_prompt_host(env, capsys):
    root, live = env
    start(root, live, white="kimi", black="codex", host="grok")
    m.cmd_prompt_host(FakeArgs(root, live))
    out = capsys.readouterr().out
    assert "export CHESS_NAME=HOST" in out
    assert "match 1 (chess)" in out
    assert "KIMI (white, agent kimi)" in out


def test_prompt_host_falls_back_to_legacy_director_key(env, capsys):
    """A match.json seated before the 2e rename stores the host seat under
    the old 'director' key (see docs/design-history.md §14) -- host_prompt
    must still find it and print the identity export."""
    root, live = env
    start(root, live, white="kimi", black="codex", host="grok")
    match_dir = root / "games/chess/match-001"
    data = json.loads((match_dir / "match.json").read_text())
    data["director"] = data.pop("host")
    (match_dir / "match.json").write_text(json.dumps(data))
    m.cmd_prompt_host(FakeArgs(root, live))
    out = capsys.readouterr().out
    assert "export CHESS_NAME=HOST" in out


def test_main_argparse_routing_and_live_dir_after_subcommand(env, monkeypatch):
    root, live = env
    monkeypatch.setattr(m, "default_root", lambda: root)
    m.main(["status", "--live-dir", str(live)])  # must not raise, e.g. no match yet
    live.mkdir(parents=True, exist_ok=True)
    (live / "moves.txt").write_text("e4")
    m.main(["status", "--live-dir", str(live)])


def test_results_aggregation(env, capsys):
    root, live = env
    # results.txt lines are "<WHITE> <score> <BLACK>" — match-001 has codex as
    # white, so both games below are won by codex.
    start(root, live, white="codex", black="kimi")
    (live / "results.txt").write_text("CODEX 1-0 KIMI\n")
    m.cmd_archive(FakeArgs(root, live))

    start(root, live, white="codex", black="kimi")
    (live / "results.txt").write_text("CODEX 1-0 KIMI\nCODEX 1-0 KIMI\n")
    m.cmd_archive(FakeArgs(root, live))

    m.cmd_results(FakeArgs(root, live))
    out = capsys.readouterr().out
    assert "match-001" in out and "match-002" in out
    assert "CODEX 2" in out


def test_run_ref_init_shells_out_with_explicit_arcade_live_for_any_dir(tmp_path, monkeypatch):
    """The engine no longer hardcodes /tmp/chess — every deployed script
    resolves ARCADE_LIVE at import time. So run_ref_init always shells into
    the deployed ref.py, for any live dir, and must pass ARCADE_LIVE
    explicitly in the subprocess env (not rely on inheriting it) so the
    subprocess targets `live` regardless of the caller's own environment."""
    live = tmp_path / "scratch-live"
    live.mkdir()
    calls = []

    def fake_run(cmd, cwd=None, env=None, check=None):
        calls.append((cmd, cwd, env, check))

        class Result:
            returncode = 0
        return Result()

    monkeypatch.setattr(m.subprocess, "run", fake_run)
    monkeypatch.delenv("ARCADE_LIVE", raising=False)

    m.run_ref_init(live, force=True)

    assert len(calls) == 1
    cmd, cwd, env, check = calls[0]
    assert str(live / "ref.py") in cmd
    assert cmd[-2:] == ["init", "--force"]
    assert cwd == live
    assert env["ARCADE_LIVE"] == str(live)
    assert check is True


def test_run_ref_init_arcade_live_overrides_any_inherited_value(tmp_path, monkeypatch):
    """Even if the CLI's own process happens to have ARCADE_LIVE set to
    something else, the subprocess env must carry the target `live` dir, not
    whatever was inherited."""
    live = tmp_path / "scratch-live"
    live.mkdir()
    monkeypatch.setenv("ARCADE_LIVE", str(tmp_path / "some-other-dir"))
    calls = []

    def fake_run(cmd, cwd=None, env=None, check=None):
        calls.append(env)

        class Result:
            returncode = 0
        return Result()

    monkeypatch.setattr(m.subprocess, "run", fake_run)

    m.run_ref_init(live, force=False)

    assert calls[0]["ARCADE_LIVE"] == str(live)


def test_run_ref_init_without_force_omits_flag(monkeypatch):
    calls = []

    def fake_run(cmd, cwd=None, env=None, check=None):
        calls.append(cmd)

        class Result:
            returncode = 0
        return Result()

    monkeypatch.setattr(m.subprocess, "run", fake_run)
    m.run_ref_init(m.DEFAULT_LIVE, force=False)

    assert calls[0][-1] == "init"


def test_start_passes_arcade_live_through_to_ref_init(env, monkeypatch):
    """cmd_start end-to-end with the real run_ref_init (not the fixture's
    lambda stub) — a scratch live dir must still shell out, with ARCADE_LIVE
    set to that scratch dir in the subprocess env."""
    root, live = env
    monkeypatch.undo()  # drop the fixture's run_ref_init monkeypatch, use the real one
    calls = []

    def fake_run(cmd, cwd=None, env=None, check=None):
        calls.append((cmd, cwd, env))
        (live / "moves.txt").write_text("")  # mimic ref.py init's effect

        class Result:
            returncode = 0
        return Result()

    monkeypatch.setattr(m.subprocess, "run", fake_run)

    start(root, live)

    assert len(calls) == 1
    cmd, cwd, env = calls[0]
    assert str(live / "ref.py") in cmd
    assert cwd == live
    assert env["ARCADE_LIVE"] == str(live)
    match_dir = root / "games/chess/match-001"
    assert match_dir.exists()


# ---------------------------------------------------------------------------
# reset + seeding (match-state-spec.md §9)

def test_start_clears_chat_log(env):
    root, live = env
    start(root, live)
    (live / "chat.log").write_text("100\tKIMI\tprior match chat\n200\tCODEX\tmore prior chat\n")
    start(root, live, force=True)
    lines = (live / "chat.log").read_text().splitlines()
    assert len(lines) == 1
    assert "\tARCADE\t" in lines[0]
    assert "KIMI" in lines[0] and "CODEX" in lines[0]


def test_start_snapshots_chat_log_before_clearing(env):
    root, live = env
    start(root, live)
    content = "100\tKIMI\tprior chat line\n"
    (live / "chat.log").write_text(content)
    start(root, live, force=True)
    backup = (live / "backup" / "chat.match-001.log")
    assert backup.exists()
    assert backup.read_text() == content


def test_start_snapshots_stage_log_before_clearing(env):
    """stage_log.txt is genuine match evidence (staged-vs-applied audit
    trail) -- the pre-start snapshot must save it before reset_room()
    unlinks it, same as it already does for chat.log."""
    root, live = env
    start(root, live)
    content = "100\tKIMI\t1\te4\n"
    (live / "stage_log.txt").write_text(content)
    start(root, live, force=True)
    backup = (live / "backup" / "stage_log.match-001.txt")
    assert backup.exists()
    assert backup.read_text() == content


def test_start_snapshots_even_with_empty_moves_txt(env):
    """Regression on the old snapshot_pre_init gate: an empty moves.txt used
    to mean nothing was snapshotted at all, even with a 170-line chat.log."""
    root, live = env
    start(root, live)
    (live / "moves.txt").write_text("")
    (live / "chat.log").write_text("100\tKIMI\tstill here\n")
    start(root, live, force=True)
    assert (live / "backup" / "chat.match-001.log").exists()


def test_start_replaces_stale_banner(env):
    root, live = env
    start(root, live, white="kimi", black="codex")
    (live / "banner.txt").write_text("SERIES 5-0 CODEX — KIMI departed\n")
    start(root, live, white="gemini", black="codex", force=True)
    banner = (live / "banner.txt").read_text()
    assert "5-0" not in banner
    assert "KIMI" not in banner
    assert "GEMINI" in banner and "CODEX" in banner


def test_start_truncates_eval_and_keeper_logs(env):
    root, live = env
    start(root, live)
    (live / "eval.log").write_text("+0.3 CODEX\n")
    (live / "keeper.log").write_text("nudge: KIMI stalled\n")
    start(root, live, force=True)
    assert (live / "eval.log").read_text() == ""
    assert (live / "keeper.log").read_text() == ""


def test_start_unlinks_ref_flag_files(env):
    root, live = env
    start(root, live)
    for fn in ("result.txt", "draw_offer.txt", "TAMPER.txt", "pending.txt"):
        (live / fn).write_text("x")
    start(root, live, force=True)
    for fn in ("result.txt", "draw_offer.txt", "TAMPER.txt", "pending.txt"):
        assert not (live / fn).exists(), fn


def test_start_unlinks_stage_log_and_menu_txt(env):
    """Seat-UX round's two new runtime files (engine/game_cli.py's
    stage_log.txt/menu.txt) are PER_MATCH_UNLINK, same class as
    pending.txt/result.txt -- a fresh start must clear both."""
    root, live = env
    start(root, live)
    (live / "stage_log.txt").write_text("100\tKIMI\t1\te4\n")
    (live / "menu.txt").write_text("0")
    start(root, live, force=True)
    assert not (live / "stage_log.txt").exists()
    assert not (live / "menu.txt").exists()


def test_stage_log_from_previous_match_not_present_in_new_room(env):
    """The actual user-visible failure this closes: if stage_log.txt from a
    finished match survived into the next one, a player's very first
    `status` in the NEW match could resolve their "last submission" against
    a ply from the DEAD match, misreporting APPLIED/APPLIED MISMATCH for a
    move played in a different game -- the same pairing-state-bleed failure
    family the match-state scaffolding round exists to prevent. Simulates
    two full matches back to back and asserts the second's live room has no
    trace of the first's staging history."""
    root, live = env
    start(root, live, white="kimi", black="codex")
    (live / "stage_log.txt").write_text("100\tKIMI\t1\te4\n200\tCODEX\t2\te5\n")
    (live / "menu.txt").write_text("2")
    m.cmd_archive(FakeArgs(root, live))

    start(root, live, white="gemini", black="codex", force=True)
    assert not (live / "stage_log.txt").exists()
    assert not (live / "menu.txt").exists()


def test_start_preserves_results_txt(env):
    root, live = env
    start(root, live)
    content = "CODEX 1-0 KIMI\n"
    (live / "results.txt").write_text(content)
    start(root, live, force=True)
    assert (live / "results.txt").read_text() == content


def test_start_preserves_operator_state(env):
    root, live = env
    start(root, live)
    (live / "mode.txt").write_text("dots\n")
    (live / "panes.txt").write_text("pane-1 pane-2\n")
    start(root, live, force=True)
    assert (live / "mode.txt").read_text() == "dots\n"
    assert (live / "panes.txt").read_text() == "pane-1 pane-2\n"


def test_start_writes_roles_txt(env):
    root, live = env
    start(root, live, white="gemini", black="codex")
    text = (live / "roles.txt").read_text()
    assert "GEMINI white" in text
    assert "CODEX black" in text
    assert "ARCADE facilitator" in text


def test_start_with_host_writes_host_txt(env):
    root, live = env
    start(root, live, host="grok")
    assert (live / "host.txt").read_text() == "grok\n"


def test_start_without_host_unlinks_stale_host_txt(env):
    root, live = env
    start(root, live, host="grok")
    assert (live / "host.txt").exists()
    start(root, live, host=None, force=True)
    assert not (live / "host.txt").exists()


def test_start_without_host_unlinks_stale_legacy_director_txt(env):
    """A live dir deployed under the pre-2e-rename engine could have a stale
    director.txt left over; a hostless start must clear that too (see
    PER_MATCH_UNLINK, docs/design-history.md §14)."""
    root, live = env
    start(root, live, host="grok")
    (live / "director.txt").write_text("grok\n")
    start(root, live, host=None, force=True)
    assert not (live / "director.txt").exists()
    assert not (live / "host.txt").exists()


def test_start_with_legacy_director_flag_writes_host_txt(env):
    """--director must keep working as an alias for --host (2e rename,
    docs/design-history.md §14)."""
    root, live = env
    args = m.build_parser().parse_args(
        ["start", "chess", "--white", "kimi", "--black", "codex", "--director", "grok",
         "--live-dir", str(live)])
    args.root = str(root)
    m.cmd_start(args)
    assert (live / "host.txt").read_text() == "grok\n"
    data = json.loads((root / "games/chess/match-001/match.json").read_text())
    assert data["host"] == {"agent": "grok", "name": "HOST"}


def test_keep_room_skips_reset(env):
    root, live = env
    start(root, live)
    (live / "chat.log").write_text("100\tKIMI\tstill-live chat\n")
    start(root, live, force=True, keep_room=True)
    assert (live / "chat.log").read_text() == "100\tKIMI\tstill-live chat\n"
    assert (live / "series.txt").exists()
    assert (live / "banner.txt").exists()


def test_keep_room_preserves_stage_log_and_menu_txt(env):
    """--keep-room is for re-seating an interrupted match -- the SAME game
    continues, so its staging history (and the pending.txt it already keeps
    alongside it, same PER_MATCH_UNLINK list) must survive too, not just
    the chat log."""
    root, live = env
    start(root, live)
    (live / "stage_log.txt").write_text("100\tKIMI\t1\te4\n")
    (live / "menu.txt").write_text("0")
    start(root, live, force=True, keep_room=True)
    assert (live / "stage_log.txt").read_text() == "100\tKIMI\t1\te4\n"
    assert (live / "menu.txt").read_text() == "0"


def test_failed_ref_init_leaves_room_intact(env, monkeypatch):
    root, live = env
    start(root, live)
    (live / "chat.log").write_text("100\tKIMI\tprior content\n")

    def boom(live, force, game="chess"):
        raise subprocess.CalledProcessError(5, ["ref.py", "init"])

    monkeypatch.setattr(m, "run_ref_init", boom)
    args = FakeArgs(root, live, white="kimi", black="codex", host="grok", force=True)
    with pytest.raises(SystemExit):
        m.cmd_start(args)

    assert (live / "chat.log").read_text() == "100\tKIMI\tprior content\n"
    assert not (root / "games/chess/match-002").exists()


# ---------------------------------------------------------------------------
# series (match-state-spec.md §5, §9)

def test_head_to_head_order_insensitive():
    rows = m.parse_results("CODEX 1-0 KIMI\nKIMI 1-0 CODEX\nCODEX 1/2-1/2 KIMI\n")
    rec = m.head_to_head(rows, "kimi", "codex")
    assert rec == (1, 1, 1, 3)


def test_head_to_head_ignores_other_pairings():
    rows = m.parse_results(
        "CODEX 1-0 KIMI\nCODEX 1-0 KIMI\nCODEX 1-0 KIMI\nCODEX 1-0 KIMI\nCODEX 1-0 KIMI\n"
        "GEMINI 1-0 CODEX\n"
    )
    assert m.head_to_head(rows, "codex", "kimi") == (5, 0, 0, 5)
    assert m.head_to_head(rows, "codex", "gemini") == (0, 1, 0, 1)


def test_series_txt_first_meeting(env):
    root, live = env
    start(root, live, white="kimi", black="codex")
    (live / "results.txt").write_text("CODEX 1-0 KIMI\n" * 5)
    start(root, live, white="gemini", black="codex", force=True)
    series = (live / "series.txt").read_text()
    assert "FIRST MEETING" in series
    assert "5" not in series
    assert "KIMI" not in series


def test_status_series_is_pairing_filtered(env, capsys):
    root, live = env
    start(root, live, white="kimi", black="codex")
    (live / "results.txt").write_text("KIMI 1-0 CODEX\n")
    start(root, live, white="gemini", black="codex", force=True)
    capsys.readouterr()

    m.cmd_status(FakeArgs(root, live))
    out = capsys.readouterr().out
    assert "KIMI" not in out
    assert "GEMINI" in out and "CODEX" in out


def test_results_groups_by_pairing(env, capsys):
    root, live = env
    start(root, live, white="codex", black="kimi")
    (live / "results.txt").write_text("CODEX 1-0 KIMI\n")
    m.cmd_archive(FakeArgs(root, live))

    start(root, live, white="codex", black="gemini")
    (live / "results.txt").write_text("CODEX 1-0 KIMI\nCODEX 1-0 GEMINI\n")
    m.cmd_archive(FakeArgs(root, live))
    capsys.readouterr()

    m.cmd_results(FakeArgs(root, live))
    out = capsys.readouterr().out
    assert "head-to-head:" in out
    assert "CODEX vs KIMI" in out
    assert "CODEX vs GEMINI" in out


def test_results_pairing_flag_filters(env, capsys):
    root, live = env
    start(root, live, white="codex", black="kimi")
    (live / "results.txt").write_text("CODEX 1-0 KIMI\n")
    m.cmd_archive(FakeArgs(root, live))

    start(root, live, white="codex", black="gemini")
    (live / "results.txt").write_text("CODEX 1-0 KIMI\nCODEX 1-0 GEMINI\n")
    m.cmd_archive(FakeArgs(root, live))
    capsys.readouterr()

    m.cmd_results(FakeArgs(root, live, pairing=["codex", "gemini"]))
    out = capsys.readouterr().out
    assert "match-002" in out
    assert "match-001" not in out
    assert "all-time" not in out


# ---------------------------------------------------------------------------
# seat-name validation + widened archive (match-state-spec.md §6, §9)

def test_start_refuses_duplicate_seat_names(env):
    root, live = env
    with pytest.raises(SystemExit):
        start(root, live, white="kimi", black="kimi")


def test_start_refuses_reserved_seat_name(env):
    root, live = env
    with pytest.raises(SystemExit):
        start(root, live, white="ARCADE", black="codex")


def test_start_failed_seat_validation_leaves_no_match_dir(env):
    """Review nit: validate_seats's sys.exit(1) used to fire after match_dir
    (step 4) and the engine file deploy (step 5) already happened, leaving a
    match.json-less match_dir behind that hard-blocked every later `arcade
    start` with "already exists (stale or corrupt match dir?)"."""
    root, live = env
    with pytest.raises(SystemExit):
        start(root, live, white="kimi", black="kimi")

    assert list((root / "games/chess").iterdir()) == []

    start(root, live, white="kimi", black="codex")
    assert (root / "games/chess/match-001").exists()


def test_start_preflight_refuses_when_engine_files_missing(env, capsys):
    """cmd_start's deploy preflight: a missing engine file used to surface as
    a copy2 traceback AFTER the match dir was created -- orphaning a
    match.json-less match-NNN that hard-blocked every later start with
    "already exists (stale or corrupt match dir?)". The preflight refuses
    before ANY filesystem change and names every missing file."""
    root, live = env
    (root / "engine" / "ref.py").unlink()
    (root / "engine" / "eval.py").unlink()
    with pytest.raises(SystemExit):
        start(root, live)
    err = capsys.readouterr().err
    assert "ref.py" in err and "eval.py" in err
    assert "no match dir was created" in err
    # no filesystem changes at all: no games tree, no live dir, no deploys
    assert not (root / "games").exists()
    assert not live.exists()

    # happy path untouched: once the files are back, start works
    (root / "engine" / "ref.py").write_text("# stub ref.py\n")
    (root / "engine" / "eval.py").write_text("# stub eval.py\n")
    start(root, live)
    assert (root / "games/chess/match-001/match.json").exists()


def test_archive_captures_new_per_match_files(env):
    root, live = env
    start(root, live)
    (live / "banner.txt").write_text("GAME 1 — KIMI vs CODEX — FIRST MEETING\n")
    (live / "eval.log").write_text("+0.3\n")
    (live / "keeper.log").write_text("nudge\n")
    (live / "series.txt").write_text("KIMI 0-0 CODEX (0 games)\n")
    (live / "result.txt").write_text("CODEX 1-0 KIMI\n")
    m.cmd_archive(FakeArgs(root, live))
    match_dir = root / "games/chess/match-001"
    for fn in ("banner.txt", "eval.log", "keeper.log", "series.txt", "result.txt"):
        assert (match_dir / fn).exists(), fn


def test_archive_captures_stage_log_but_not_menu_txt(env):
    """stage_log.txt is the staged-vs-applied audit trail the receipt
    feature exists to create -- genuine match evidence, archived. menu.txt
    is ephemeral client-side UI state (which ply a menu was printed at) with
    no evidentiary value -- deliberately excluded from ARCHIVE_FILES."""
    root, live = env
    start(root, live)
    (live / "stage_log.txt").write_text("100\tKIMI\t1\te4\n200\tCODEX\t2\te5\n")
    (live / "menu.txt").write_text("2")
    m.cmd_archive(FakeArgs(root, live))
    match_dir = root / "games/chess/match-001"
    assert (match_dir / "stage_log.txt").read_text() == "100\tKIMI\t1\te4\n200\tCODEX\t2\te5\n"
    assert not (match_dir / "menu.txt").exists()


# ---------------------------------------------------------------------------
# xiangqi

@pytest.fixture
def env_xq(tmp_path, monkeypatch):
    root = tmp_path / "arcade"
    (root / "engine").mkdir(parents=True)
    for fn in m.DEPLOY_FILES_XIANGQI:
        (root / "engine" / fn).write_text(f"# stub {fn}\n")
    live = tmp_path / "live"
    monkeypatch.setattr(m, "run_ref_init",
                         lambda live, force, game="chess": (live / "moves.txt").write_text(""))
    return root, live


def start_xq(root, live, red="kimi", black="codex", host="grok", force=False, keep_room=False):
    args = FakeArgs(root, live, game="xiangqi", white=red, black=black,
                     host=host, force=force, keep_room=keep_room)
    m.cmd_start(args)


def test_xiangqi_start_clears_room(env_xq):
    root, live = env_xq
    start_xq(root, live)
    (live / "chat.log").write_text("100\tKIMI\tprior xq chat\n")
    (live / "banner.txt").write_text("SERIES 5-0 CODEX\n")
    start_xq(root, live, force=True)

    lines = (live / "chat.log").read_text().splitlines()
    assert len(lines) == 1
    assert "\tARCADE\t" in lines[0]
    banner = (live / "banner.txt").read_text()
    assert "5-0" not in banner


def test_xiangqi_start_writes_roles_and_series(env_xq):
    root, live = env_xq
    start_xq(root, live, red="gemini", black="codex")

    roles = (live / "roles.txt").read_text()
    assert "GEMINI white" in roles
    assert "CODEX black" in roles

    chat_line = (live / "chat.log").read_text()
    assert "(Red)" in chat_line and "(Black)" in chat_line

    assert (live / "series.txt").exists()


def test_xiangqi_start_with_host_writes_host_txt(env_xq):
    root, live = env_xq
    start_xq(root, live, host="grok")
    assert (live / "host.txt").read_text() == "grok\n"


def test_xiangqi_start_creates_match_dir_and_deploys_file_set(env_xq):
    root, live = env_xq
    start_xq(root, live)

    match_dir = root / "games/xiangqi/match-001"
    assert match_dir.exists()
    data = json.loads((match_dir / "match.json").read_text())
    assert data["game"] == "xiangqi"
    assert data["seats"]["white"] == {"agent": "kimi", "name": "KIMI"}
    assert data["seats"]["black"] == {"agent": "codex", "name": "CODEX"}

    for fn in m.DEPLOY_FILES_XIANGQI:
        assert (live / fn).exists(), fn
    # chess-only files must not leak into the xiangqi live dir
    assert not (live / "ref.py").exists()
    assert not (live / "game.sh").exists()
    assert not (live / "eval.py").exists()

    names = (live / "names.txt").read_text().split()
    assert names == ["KIMI", "CODEX"]


def test_xiangqi_start_writes_seats_txt(env_xq):
    root, live = env_xq
    start_xq(root, live)
    lines = (live / "seats.txt").read_text().splitlines()
    assert lines == ["KIMI white", "CODEX black"]


def test_xiangqi_default_live_dir_is_tmp_xiangqi(monkeypatch):
    """Pure resolution, no filesystem I/O: default_live_for()/get_live_dir()
    must resolve xiangqi's own default (/tmp/xiangqi), not chess's. Codex's
    minimal rewrite of the escaped test below -- the original drove this
    through cmd_start's real deploy path with only run_ref_init mocked (and
    even that mock wrote moves.txt for real), which is what deployed stub
    engine files into the actual /tmp/xiangqi."""
    monkeypatch.delenv("ARCADE_LIVE", raising=False)
    assert m.default_live_for("xiangqi") == Path("/tmp/xiangqi")

    args = FakeArgs(root="unused", live="unused", game="xiangqi")
    args.live_dir = None
    assert m.get_live_dir(args) == Path("/tmp/xiangqi")


def test_xiangqi_start_falls_back_to_own_default_live_dir(env_xq, monkeypatch):
    """cmd_start's fallback-to-default-live-dir path, exercised end to end --
    but with GAME_DEFAULT_LIVE monkeypatched to a scratch dir first, so this
    never touches the real /tmp/xiangqi even though the code path under test
    is exactly 'no --live-dir, no ARCADE_LIVE'.

    (This replaces an earlier version of this test that monkeypatched only
    run_ref_init and left cmd_start's own mkdir/copy2/names.txt-write calls
    pointed at the literal default -- which deployed stub engine files into
    the real /tmp/xiangqi. Never exercise the unmocked default path again;
    always monkeypatch GAME_DEFAULT_LIVE/DEFAULT_LIVE to a tmp_path first.)
    """
    root, live = env_xq
    scratch_default = live.parent / "scratch-default-xiangqi"
    monkeypatch.setitem(m.GAME_DEFAULT_LIVE, "xiangqi", scratch_default)
    monkeypatch.delenv("ARCADE_LIVE", raising=False)
    calls = []
    monkeypatch.setattr(m, "run_ref_init",
                         lambda live, force, game="chess": (calls.append((live, game)),
                                                             (live / "moves.txt").write_text(""))[-1])
    args = FakeArgs(root, scratch_default, game="xiangqi", white="kimi", black="codex",
                     host=None, force=False)
    args.live_dir = None  # no --live-dir flag: must fall back to xiangqi's own default
    m.cmd_start(args)
    assert calls[0][0] == scratch_default
    assert calls[0][1] == "xiangqi"
    assert (scratch_default / "ref_xq.py").exists()


def test_xiangqi_start_uses_red_flag_alias(env_xq):
    """`--red` is how the CLI is invoked for xiangqi; it must land in the same
    match.json 'white' seat key chess uses (ref_xq.py's own red<->white
    mapping), driven through the real argparse parser this time."""
    root, live = env_xq
    args = m.build_parser().parse_args(
        ["start", "xiangqi", "--red", "kimi", "--black", "codex", "--director", "grok",
         "--live-dir", str(live)])
    args.root = str(root)
    m.cmd_start(args)

    match_dir = root / "games/xiangqi/match-001"
    data = json.loads((match_dir / "match.json").read_text())
    assert data["seats"]["white"] == {"agent": "kimi", "name": "KIMI"}


def test_xiangqi_runbook_uses_red_label_and_game_xq_script(env_xq, capsys):
    root, live = env_xq
    start_xq(root, live, red="human:ada", black="codex")
    out = capsys.readouterr().out
    assert "# You are ADA (red). Play with:" in out
    assert f"bash {live}/game_xq.sh submit '<move>'" in out
    assert f"bash {live}/game_xq.sh show" in out


def test_xiangqi_host_prompt_uses_red_label_and_facilitator_xq(env_xq, capsys):
    root, live = env_xq
    start_xq(root, live, red="kimi", black="codex", host="grok")
    out = capsys.readouterr().out
    assert "Read" in out and "FACILITATOR_XQ.md" in out
    assert "KIMI (red, agent kimi)" in out
    assert "CODEX (black, agent codex)" in out


def test_xiangqi_status_and_archive_round_trip(env_xq, capsys):
    root, live = env_xq
    start_xq(root, live)
    (live / "moves.txt").write_text("h2e2")
    (live / "fen.txt").write_text("fake fen\n")

    m.cmd_status(FakeArgs(root, live, game="xiangqi"))
    out = capsys.readouterr().out
    assert "ply: 1" in out
    assert "to move: black" in out

    (live / "results.txt").write_text("KIMI 1-0 CODEX\n")
    m.cmd_archive(FakeArgs(root, live, game="xiangqi", result=None))
    data = json.loads((root / "games/xiangqi/match-001/match.json").read_text())
    assert data["status"] == "complete"
    assert data["result"] == "KIMI 1-0 CODEX"
    assert (root / "games/xiangqi/match-001/moves.txt").read_text() == "h2e2"


@pytest.fixture
def xq_live(tmp_path):
    """A scratch ARCADE_LIVE with the real engine's xiangqi runtime files
    (not stubs) -- for driving game_xq_cli.py's actual show-verb output."""
    live = tmp_path / "xq-live"
    live.mkdir()
    for fn in ("xiangqi.py", "chat.py", "game_xq_cli.py", "ref_xq.py"):
        (live / fn).write_text((ENGINE / fn).read_text())
    (live / "names.txt").write_text("RED BLACK\n")
    return live


def run_xq_cli(live, *args, chess_name="RED"):
    return subprocess.run(
        [sys.executable, "game_xq_cli.py", *args],
        cwd=live, env={"ARCADE_LIVE": str(live), "CHESS_NAME": chess_name, "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True,
    )


def run_xq_ref(live, *args):
    return subprocess.run(
        [sys.executable, "ref_xq.py", *args],
        cwd=live, env={"ARCADE_LIVE": str(live), "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True,
    )


def test_game_xq_cli_show_contract_board_turn_moves(xq_live):
    """HARD REQUIREMENT: `show` must print the board, whose turn it is, and
    the full legal-move list in ICCS, so a player never has to model
    cannon-screen/flying-general rules -- if a move isn't printed, it's
    illegal."""
    r = run_xq_ref(xq_live, "init")
    assert r.returncode == 0, r.stderr

    r = run_xq_cli(xq_live, "show")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "a b c d e f g h i" in out          # board file header
    assert "Side to move: RED (Red)" in out     # whose turn
    assert "Legal moves:" in out
    assert "h2e2" in out                        # a real opening move, ICCS
    assert "YOU ARE IN CHECK" not in out         # not in check at game start


def test_game_xq_cli_show_check_banner(xq_live):
    """A prominent YOU ARE IN CHECK banner must appear when the side to move
    is in check -- players must never need to work this out themselves."""
    r = run_xq_ref(xq_live, "init")
    assert r.returncode == 0, r.stderr
    # flying-general check: clear file e between the two generals.
    setup = (
        "import sys; sys.path.insert(0, '.')\n"
        "from xiangqi import XiangqiBoard\n"
        "b = XiangqiBoard.from_fen('rnba1abnr/4k4/1c5c1/p1p3p1p/9/9/P1P3P1P/1c5c1/4K4/RNBA1ABNR w - - 0 1')\n"
        "for r_ in range(2, 8): b.board[r_][4] = None\n"
        "open('fen.txt', 'w').write(b.fen())\n"
    )
    r = subprocess.run([sys.executable, "-c", setup], cwd=xq_live,
                        env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    r = run_xq_cli(xq_live, "show")
    assert r.returncode == 0, r.stderr
    assert "YOU ARE IN CHECK" in r.stdout


def test_game_xq_cli_submit_illegal_move_rejected(xq_live):
    r = run_xq_ref(xq_live, "init")
    assert r.returncode == 0, r.stderr
    r = run_xq_cli(xq_live, "submit", "z9z9")
    assert r.returncode == 1
    assert "ILLEGAL" in r.stdout
    assert "Legal moves:" in r.stdout


def test_game_xq_cli_submit_legal_move_stages_signed_pending(xq_live):
    r = run_xq_ref(xq_live, "init")
    assert r.returncode == 0, r.stderr
    r = run_xq_cli(xq_live, "submit", "h2e2")
    assert r.returncode == 0, r.stderr
    assert "STAGED: h2e2" in r.stdout
    assert (xq_live / "pending.txt").read_text() == "RED\th2e2"

    # referee accepts the exact pending.txt contract game_xq_cli.py wrote
    r = run_xq_ref(xq_live, "move", (xq_live / "pending.txt").read_text())
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("OK h2e2 |")


def test_human_xiangqi_seat_uses_same_wrapper_and_referee_flow(tmp_path):
    """2a live gate: a person and an agent use the identical deployed
    wrapper/pending/referee protocol; no separate input loop is required."""
    live = tmp_path / 'human-xq-live'
    live.mkdir()
    for fn in ('xiangqi.py', 'chat.py', 'game_xq_cli.py', 'game_xq.sh', 'ref_xq.py'):
        (live / fn).write_text((ENGINE / fn).read_text())
    (live / 'names.txt').write_text('ADA KIMI\n')
    (live / 'seats.txt').write_text('ADA white\nKIMI black\n')
    base_env = {**os.environ, 'ARCADE_LIVE': str(live)}

    init = subprocess.run(
        [sys.executable, str(live / 'ref_xq.py'), 'init'], cwd=live,
        env=base_env, capture_output=True, text=True,
    )
    assert init.returncode == 0, init.stderr

    def wrapper(name, *args):
        return subprocess.run(
            ['bash', str(live / 'game_xq.sh'), *args], cwd=live,
            env={**base_env, 'CHESS_NAME': name}, capture_output=True, text=True,
        )

    shown = wrapper('ADA', 'show')
    assert shown.returncode == 0 and 'Side to move: ADA (Red)' in shown.stdout
    staged = wrapper('ADA', 'submit', 'h2e2')
    assert staged.returncode == 0 and 'STAGED: h2e2' in staged.stdout
    assert (live / 'pending.txt').read_text() == 'ADA\th2e2'
    applied = subprocess.run(
        [sys.executable, str(live / 'ref_xq.py'), 'move',
         (live / 'pending.txt').read_text()], cwd=live,
        env=base_env, capture_output=True, text=True,
    )
    assert applied.returncode == 0, applied.stderr
    (live / 'pending.txt').unlink()

    staged = wrapper('KIMI', 'submit', 'h9g7')
    assert staged.returncode == 0 and 'STAGED: h9g7' in staged.stdout
    applied = subprocess.run(
        [sys.executable, str(live / 'ref_xq.py'), 'move',
         (live / 'pending.txt').read_text()], cwd=live,
        env=base_env, capture_output=True, text=True,
    )
    assert applied.returncode == 0, applied.stderr
    assert (live / 'moves.txt').read_text() == 'h2e2 h9g7'


def test_seat_flag_mismatch_warns_but_does_not_refuse(env_xq, capsys):
    """--white/--red share one argparse dest (build_parser), so the off-game
    spelling parses silently -- main() should note it on stderr without
    blocking the start (codex review nit, cheapest acceptable fix)."""
    root, live = env_xq
    argv = ["start", "xiangqi", "--white", "kimi", "--black", "codex", "--live-dir", str(live)]
    args = m.build_parser().parse_args(argv)
    args.root = str(root)
    m.warn_seat_flag_mismatch(args, argv)
    err = capsys.readouterr().err
    assert "--white works for xiangqi too" in err


def test_seat_flag_no_warning_when_spelling_matches_game(env, capsys):
    root, live = env
    argv = ["start", "chess", "--white", "kimi", "--black", "codex", "--live-dir", str(live)]
    args = m.build_parser().parse_args(argv)
    args.root = str(root)
    m.warn_seat_flag_mismatch(args, argv)
    err = capsys.readouterr().err
    assert err == ""


# ---------------------------------------------------------------------------
# corewar

@pytest.fixture
def env_cw(tmp_path, monkeypatch):
    root = tmp_path / "arcade"
    (root / "engine").mkdir(parents=True)
    for fn in m.DEPLOY_FILES_COREWAR:
        (root / "engine" / fn).write_text(f"# stub {fn}\n")
    live = tmp_path / "live"
    monkeypatch.setattr(m, "run_ref_init",
                         lambda live, force, game="chess": (live / "moves.txt").write_text(""))
    return root, live


def start_cw(root, live, red="kimi", blue="codex", host="grok", force=False, keep_room=False):
    args = FakeArgs(root, live, game="corewar", white=red, black=blue,
                     host=host, force=force, keep_room=keep_room)
    m.cmd_start(args)


def test_corewar_lookup_dicts_all_cover_corewar():
    """Every per-game lookup defaults to chess on a missing key, so corewar
    must be present in ALL of them -- a missing row makes `arcade start
    corewar` silently deploy/behave like chess."""
    assert m.GAME_DEPLOY_FILES["corewar"] is m.DEPLOY_FILES_COREWAR
    assert m.GAME_DEFAULT_LIVE["corewar"] == Path("/tmp/corewar")
    assert m.GAME_REF_SCRIPT["corewar"] == "ref_cw.py"
    assert m.GAME_UV_WITH["corewar"] == []
    assert m.GAME_SCRIPT["corewar"] == "game_cw.sh"
    assert m.GAME_FACILITATOR["corewar"] == "FACILITATOR_CW.md"
    assert m.GAME_COLORS["corewar"] == ("red", "blue")


def test_corewar_deploy_set_contents():
    assert m.DEPLOY_FILES_COREWAR == [
        "corewar.py", "ref_cw.py", "game_cw_cli.py", "game_cw.sh", "tui_corewar.py",
        "chat.py", "chat_tui.py", "director_keeper.sh", "FACILITATOR_CW.md",
    ]


def test_corewar_start_creates_match_dir_and_deploys_file_set(env_cw):
    root, live = env_cw
    start_cw(root, live)

    match_dir = root / "games/corewar/match-001"
    assert match_dir.exists()
    data = json.loads((match_dir / "match.json").read_text())
    assert data["game"] == "corewar"
    # seats keep the internal white/black keys (same mapping as xiangqi's
    # red<->white); the red/blue labels are display-only, via GAME_COLORS.
    assert data["seats"]["white"] == {"agent": "kimi", "name": "KIMI"}
    assert data["seats"]["black"] == {"agent": "codex", "name": "CODEX"}

    for fn in m.DEPLOY_FILES_COREWAR:
        assert (live / fn).exists(), fn
    # chess/xiangqi-only files must not leak into the corewar live dir
    assert not (live / "ref.py").exists()
    assert not (live / "game.sh").exists()
    assert not (live / "eval.py").exists()
    assert not (live / "ref_xq.py").exists()
    assert not (live / "game_xq.sh").exists()
    assert not (live / "xiangqi.py").exists()

    names = (live / "names.txt").read_text().split()
    assert names == ["KIMI", "CODEX"]


def test_corewar_start_writes_roles_and_series(env_cw):
    root, live = env_cw
    start_cw(root, live, red="gemini", blue="codex")

    roles = (live / "roles.txt").read_text()
    assert "GEMINI white" in roles
    assert "CODEX black" in roles

    chat_line = (live / "chat.log").read_text()
    assert "(Red)" in chat_line and "(Blue)" in chat_line

    assert (live / "series.txt").exists()


def test_corewar_default_live_dir_is_tmp_corewar(monkeypatch):
    """Pure resolution, no filesystem I/O: default_live_for()/get_live_dir()
    must resolve corewar's own default (/tmp/corewar), not chess's. Same
    shape as the xiangqi test -- never drive this through cmd_start's real
    deploy path pointed at the literal default."""
    monkeypatch.delenv("ARCADE_LIVE", raising=False)
    assert m.default_live_for("corewar") == Path("/tmp/corewar")

    args = FakeArgs(root="unused", live="unused", game="corewar")
    args.live_dir = None
    assert m.get_live_dir(args) == Path("/tmp/corewar")


def test_corewar_start_falls_back_to_own_default_live_dir(env_cw, monkeypatch):
    """cmd_start's fallback-to-default-live-dir path, exercised end to end --
    but with GAME_DEFAULT_LIVE monkeypatched to a scratch dir first, so this
    never touches the real /tmp/corewar even though the code path under test
    is exactly 'no --live-dir, no ARCADE_LIVE'."""
    root, live = env_cw
    scratch_default = live.parent / "scratch-default-corewar"
    monkeypatch.setitem(m.GAME_DEFAULT_LIVE, "corewar", scratch_default)
    monkeypatch.delenv("ARCADE_LIVE", raising=False)
    calls = []
    monkeypatch.setattr(m, "run_ref_init",
                         lambda live, force, game="chess": (calls.append((live, game)),
                                                             (live / "moves.txt").write_text(""))[-1])
    args = FakeArgs(root, scratch_default, game="corewar", white="kimi", black="codex",
                     host=None, force=False)
    args.live_dir = None  # no --live-dir flag: must fall back to corewar's own default
    m.cmd_start(args)
    assert calls[0][0] == scratch_default
    assert calls[0][1] == "corewar"
    assert (scratch_default / "ref_cw.py").exists()


def test_corewar_start_uses_red_and_blue_flag_aliases(env_cw):
    """`--red`/`--blue` are corewar's spellings of the seat flags; they must
    land in the same match.json 'white'/'black' seat keys the other games
    use, driven through the real argparse parser."""
    root, live = env_cw
    args = m.build_parser().parse_args(
        ["start", "corewar", "--red", "kimi", "--blue", "codex", "--host", "grok",
         "--live-dir", str(live)])
    args.root = str(root)
    m.cmd_start(args)

    data = json.loads((root / "games/corewar/match-001/match.json").read_text())
    assert data["seats"]["white"] == {"agent": "kimi", "name": "KIMI"}
    assert data["seats"]["black"] == {"agent": "codex", "name": "CODEX"}


def test_corewar_runbook_uses_red_blue_labels_and_game_cw_script(env_cw, capsys):
    root, live = env_cw
    start_cw(root, live, red="human:ada", blue="codex")
    out = capsys.readouterr().out
    assert "# You are ADA (red). Play with:" in out
    assert f"bash {live}/game_cw.sh submit '<move>'" in out
    assert f"bash {live}/game_cw.sh show" in out
    assert f"# blue, cwd {live}" in out


def test_corewar_host_prompt_uses_red_blue_labels_and_facilitator_cw(env_cw, capsys):
    root, live = env_cw
    start_cw(root, live, red="kimi", blue="codex", host="grok")
    out = capsys.readouterr().out
    assert "Read" in out and "FACILITATOR_CW.md" in out
    assert "KIMI (red, agent kimi)" in out
    assert "CODEX (blue, agent codex)" in out


def test_corewar_status_and_archive_round_trip(env_cw, capsys):
    root, live = env_cw
    start_cw(root, live)
    # moves.txt is corewar's battle transcript (LOAD/ROUND/OUT lines), not a
    # SAN move list -- cmd_status counts tokens generically either way.
    (live / "moves.txt").write_text("LOAD A deadbeef")

    m.cmd_status(FakeArgs(root, live, game="corewar"))
    out = capsys.readouterr().out
    assert "ply: 3" in out

    (live / "results.txt").write_text("KIMI 1-0 CODEX\n")
    m.cmd_archive(FakeArgs(root, live, game="corewar", result=None))
    data = json.loads((root / "games/corewar/match-001/match.json").read_text())
    assert data["status"] == "complete"
    assert data["result"] == "KIMI 1-0 CODEX"
    assert (root / "games/corewar/match-001/moves.txt").read_text() == "LOAD A deadbeef"


def test_corewar_start_refuses_reserved_blue_seat(env_cw):
    """BLUE joined RESERVED_NAMES with the other seat-color words."""
    root, live = env_cw
    with pytest.raises(SystemExit):
        start_cw(root, live, red="kimi", blue="blue")


def test_corewar_seat_flag_mismatch_warns_but_does_not_refuse(env_cw, capsys):
    """--white/--black parse for corewar (shared dests), but --red/--blue are
    its conventional spellings -- main() notes the off-game spelling on
    stderr without blocking the start."""
    root, live = env_cw
    argv = ["start", "corewar", "--white", "kimi", "--blue", "codex", "--live-dir", str(live)]
    args = m.build_parser().parse_args(argv)
    args.root = str(root)
    m.warn_seat_flag_mismatch(args, argv)
    err = capsys.readouterr().err
    assert "--white works for corewar too" in err
    assert err.count("note:") == 1  # --blue is conventional for corewar: no second note

    argv = ["start", "corewar", "--red", "kimi", "--black", "codex", "--live-dir", str(live)]
    args = m.build_parser().parse_args(argv)
    m.warn_seat_flag_mismatch(args, argv)
    err = capsys.readouterr().err
    assert "--black works for corewar too" in err
    assert "--blue is the conventional spelling" in err


def test_corewar_seat_flag_no_warning_when_spelling_matches_game(env_cw, capsys):
    root, live = env_cw
    argv = ["start", "corewar", "--red", "kimi", "--blue", "codex", "--live-dir", str(live)]
    args = m.build_parser().parse_args(argv)
    args.root = str(root)
    m.warn_seat_flag_mismatch(args, argv)
    assert capsys.readouterr().err == ""


def test_blue_flag_on_chess_warns_but_does_not_refuse(env, capsys):
    root, live = env
    argv = ["start", "chess", "--white", "kimi", "--blue", "codex", "--live-dir", str(live)]
    args = m.build_parser().parse_args(argv)
    args.root = str(root)
    m.warn_seat_flag_mismatch(args, argv)
    err = capsys.readouterr().err
    assert "--blue is corewar's spelling of the second seat flag" in err
    assert "--black is conventional here" in err


def test_corewar_start_preflight_refuses_on_missing_engine_file(env_cw, capsys):
    """The preflight reads the game's OWN deploy set: a corewar start whose
    engine tree is missing a deploy file refuses before any filesystem
    change instead of orphaning a match dir mid-deploy. (This is today's
    real situation whenever a wave-N engine file hasn't landed yet.)"""
    root, live = env_cw
    # env_cw stubs every DEPLOY_FILES_COREWAR entry; drop one to simulate an
    # engine file that hasn't landed yet (tui_corewar.py is wave 3).
    (root / "engine" / "tui_corewar.py").unlink()
    with pytest.raises(SystemExit):
        start_cw(root, live)
    err = capsys.readouterr().err
    assert "tui_corewar.py" in err
    assert "no match dir was created" in err
    assert not (root / "games").exists()
    assert not live.exists()


# ---------------------------------------------------------------------------
# corewar -- real-engine wiring (mirrors the xiangqi xq_live fixture pattern:
# actual engine files from arcade/engine, not stubs)

CW_ENGINE_FILES = ("corewar.py", "ref_cw.py", "chat.py")


@pytest.fixture
def cw_live(tmp_path):
    """A scratch live dir with the real corewar engine runtime -- for driving
    ref_cw.py through the CLI's own run_ref_init."""
    missing = [fn for fn in CW_ENGINE_FILES if not (ENGINE / fn).exists()]
    if missing:
        pytest.skip(f"corewar engine files not in {ENGINE} yet: {', '.join(missing)}")
    live = tmp_path / "cw-live"
    live.mkdir()
    for fn in CW_ENGINE_FILES:
        (live / fn).write_text((ENGINE / fn).read_text())
    return live


def test_run_ref_init_drives_real_ref_cw_init(cw_live):
    """The REAL run_ref_init (not monkeypatched) must resolve ref_cw.py via
    GAME_REF_SCRIPT, shell out with ARCADE_LIVE pointed at the scratch live
    dir, and land ref_cw.py init's real effects there -- the exact wiring
    cmd_start depends on (ref_cw.py imports corewar and chat at module load,
    so all three must be deployable together)."""
    m.run_ref_init(cw_live, True, game="corewar")
    assert (cw_live / "moves.txt").read_text() == ""
    assert (cw_live / "warriors").is_dir()
    assert (cw_live / "stage_inbox").is_dir()


def test_corewar_archive_captures_warriors_and_battle_json(env_cw):
    """GAME_ARCHIVE_EXTRA: corewar's staged warriors ARE the match evidence --
    the transcript's LOAD sha256 lines are unverifiable without them, and
    battle.json is the renderer's cache -- so archive must carry all three,
    nested warriors/ paths included. Driven with game=None (inferred from the
    live dir) to prove the extras lookup resolves the game on that path too."""
    root, live = env_cw
    start_cw(root, live)
    (live / "warriors").mkdir()
    (live / "warriors/A.red").write_text(";redcode-94\nMOV 0, 1\n")
    (live / "warriors/B.red").write_text(";redcode-94\nADD #4, 3\n")
    (live / "battle.json").write_text('{"rounds": []}\n')
    (live / "results.txt").write_text("KIMI 1-0 CODEX\n")

    m.cmd_archive(FakeArgs(root, live, game=None, result=None))

    match_dir = root / "games/corewar/match-001"
    assert (match_dir / "warriors/A.red").read_text() == ";redcode-94\nMOV 0, 1\n"
    assert (match_dir / "warriors/B.red").read_text() == ";redcode-94\nADD #4, 3\n"
    assert (match_dir / "battle.json").read_text() == '{"rounds": []}\n'
    data = json.loads((match_dir / "match.json").read_text())
    assert data["status"] == "complete"
    assert data["result"] == "KIMI 1-0 CODEX"


def test_chess_archive_has_no_game_extras(env):
    """GAME_ARCHIVE_EXTRA is keyed per game: stray warriors//battle.json files
    in a chess live dir must NOT leak into a chess archive -- the chess
    archive set is exactly ARCHIVE_FILES, unchanged."""
    root, live = env
    start(root, live)
    (live / "warriors").mkdir()
    (live / "warriors/A.red").write_text("not chess evidence\n")
    (live / "battle.json").write_text("{}\n")

    m.cmd_archive(FakeArgs(root, live))

    match_dir = root / "games/chess/match-001"
    assert not (match_dir / "warriors").exists()
    assert not (match_dir / "battle.json").exists()

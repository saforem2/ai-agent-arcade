import json
import subprocess
from pathlib import Path

import chess
import pytest

from arcade_cli import series


def test_load_config_supports_arbitrary_openai_players(tmp_path, monkeypatch):
    config = tmp_path / "match.toml"
    config.write_text('''
version = 1
[players.one]
name = "MODEL-ONE"
harness = "openai"
base_url = "http://localhost:8000/v1"
model = "model-one"
effort = "medium"
api_key_env = "MODEL_ONE_KEY"
[players.two]
name = "MODEL-TWO"
harness = "openai"
base_url = "http://localhost:9000/v1/chat/completions"
model = "model-two"
''')
    monkeypatch.setenv("MODEL_ONE_KEY", "secret")

    players = series.load_players(config)

    assert players[0]["endpoint"] == "http://localhost:8000/v1/chat/completions"
    assert players[0]["api_key"] == "secret"
    assert players[0]["effort"] == "medium"
    assert players[1]["api_key"] is None


def test_load_config_rejects_missing_api_key_env(tmp_path):
    config = tmp_path / "match.toml"
    config.write_text('''
version = 1
[players.one]
name = "One"
harness = "openai"
base_url = "http://localhost:8000/v1"
model = "one"
api_key_env = "MISSING_ARCADE_KEY"
[players.two]
name = "Two"
harness = "openai"
base_url = "http://localhost:9000/v1"
model = "two"
''')

    with pytest.raises(ValueError, match="MISSING_ARCADE_KEY"):
        series.load_players(config)


def test_request_decision_omits_optional_auth_and_effort(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self):
            return json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode()

    def fake_urlopen(request, timeout):
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.data)
        return Response()

    monkeypatch.setattr(series.urllib.request, "urlopen", fake_urlopen)
    series.request_decision({
        "name": "Local", "harness": "openai", "endpoint": "http://localhost/v1/chat/completions",
        "model": "local", "api_key": None, "effort": None,
    }, "choose", 10)

    assert "Authorization" not in captured["headers"]
    assert "reasoning_effort" not in captured["payload"]


def test_reconcile_pending_applies_staged_current_move(tmp_path, monkeypatch):
    (tmp_path / "pending.txt").write_text("WHITE\tNf3\n")
    applied = []
    monkeypatch.setattr(series, "apply_move", lambda live, player, san, log: applied.append(san))

    handled = series.reconcile_pending(
        tmp_path, {"name": "WHITE"}, chess.Board(), tmp_path / "model.log"
    )

    assert handled is True
    assert applied == ["Nf3"]


def test_terminal_result_recognizes_claimable_threefold_draw():
    board = chess.Board()
    for san in "Nf3 Nf6 Ng1 Ng8 Nf3 Nf6 Ng1 Ng8".split():
        board.push_san(san)

    assert not board.is_game_over()
    assert board.can_claim_threefold_repetition()
    assert series.terminal_result(board) == ("1/2-1/2", "threefold repetition")


def test_terminal_result_uses_native_checkmate():
    board = chess.Board()
    for san in "f3 e5 g4 Qh4#".split():
        board.push_san(san)

    assert series.terminal_result(board) == ("0-1", "checkmate")


def test_parse_decision_keeps_concise_self_reported_rationale():
    raw = json.dumps({
        "move": "Nf3",
        "candidate_moves": ["Nf3", "e4"],
        "rationale": "Develops a piece and controls e5.",
        "expected_reply": "Nf6",
    })

    decision = series.parse_decision(raw, ["Nf3", "e4", "d4"])

    assert decision == {
        "move": "Nf3",
        "candidate_moves": ["Nf3", "e4"],
        "rationale": "Develops a piece and controls e5.",
        "expected_reply": "Nf6",
    }


def test_parse_decision_rejects_move_outside_legal_list():
    raw = json.dumps({"move": "Qh5", "rationale": "Attack f7."})

    assert series.parse_decision(raw, ["Nf3", "e4"]) is None


def test_parse_decision_accepts_json_from_reasoning_field():
    body = {
        "choices": [{"message": {"content": "", "reasoning": json.dumps({
            "move": "e4",
            "candidate_moves": ["e4"],
            "rationale": "Claims the center.",
            "expected_reply": "e5",
        })}}],
        "usage": {},
    }

    raw, _ = series.decision_response(body)

    assert series.parse_decision(raw, ["e4", "Nf3"])["move"] == "e4"


def test_decision_request_uses_low_reasoning_and_room_for_visible_json(monkeypatch):
    captured = {}

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return self.payload

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.headers["Authorization"]
        captured.update(json.loads(request.data))
        return Response(json.dumps({
            "choices": [{"message": {"content": '{"move":"e4"}'}}],
            "usage": {},
        }).encode())

    monkeypatch.setattr(series.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(series, "get_inference_token", lambda: "secret-token")

    series.request_decision(series.PLAYERS["gpt-oss"], "choose", 180)

    assert captured["reasoning_effort"] == "low"
    assert captured["max_tokens"] == 8192
    assert captured["url"].endswith("/resource_server/metis/api/v1/chat/completions")
    assert captured["model"] == "gpt-oss-120b"
    assert captured["authorization"] == "Bearer secret-token"


def test_ask_retries_timeout_and_records_reasoning_usage(tmp_path, monkeypatch):
    board = chess.Board()
    calls = []

    def fake_request(player, prompt, timeout):
        calls.append(timeout)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(["gateway"], timeout)
        return (
            json.dumps({
                "move": "Nf3",
                "candidate_moves": ["Nf3", "e4"],
                "rationale": "Develops and controls e5.",
                "expected_reply": "Nf6",
            }),
            {"reasoning_tokens": 23},
        )

    monkeypatch.setattr(series, "request_decision", fake_request)
    model_log = tmp_path / "model.log"
    decision_log = tmp_path / "decision_log.jsonl"

    decision = series.ask(
        series.PLAYERS["gpt-oss"], board, [], model_log, decision_log
    )

    assert decision["move"] == "Nf3"
    assert calls == [180, 180]
    row = json.loads(decision_log.read_text())
    assert row["reasoning_tokens"] == 23
    assert row["rationale"] == "Develops and controls e5."
    assert "timeout" in model_log.read_text().lower()


def test_current_live_match_requires_matching_seats(tmp_path, monkeypatch):
    match_dir = tmp_path / "games/chess/match-026"
    match_dir.mkdir(parents=True)
    (match_dir / "match.json").write_text(json.dumps({
        "match": 26,
        "status": "live",
        "seats": {
            "white": {"name": "INKLING-BF16"},
            "black": {"name": "GPT-OSS-120B"},
        },
    }))
    monkeypatch.setattr(series, "ROOT", tmp_path)

    match = series.current_live_match(
        series.PLAYERS["inkling"], series.PLAYERS["gpt-oss"]
    )

    assert match["match"] == 26


def test_current_live_match_falls_back_to_installed_live_directory(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    (root / "games/chess").mkdir(parents=True)
    live = tmp_path / "live"
    live.mkdir()
    (live / "names.txt").write_text("GPT-OSS-120B INKLING-BF16\n")
    (live / "moves.txt").write_text("Nf3 Nf6\n")
    (live / "series.txt").write_text("1\n")
    monkeypatch.setattr(series, "ROOT", root)

    match = series.current_live_match(
        series.PLAYERS["gpt-oss"], series.PLAYERS["inkling"], live
    )

    assert match == {"match": 1, "status": "live"}


def test_main_turns_keyboard_interrupt_into_clean_exit(monkeypatch):
    monkeypatch.setattr(series, "run_series", lambda: (_ for _ in ()).throw(KeyboardInterrupt()))

    with pytest.raises(SystemExit) as stopped:
        series.main()

    assert stopped.value.code == 130


LEGAL = ["Nf3", "e4", "d4"]


@pytest.mark.parametrize(
    "raw, expected",
    [
        ('```json\n{"move":"Nf3","candidate_moves":["Nf3"],"rationale":"r","expected_reply":"Nf6"}\n```', "Nf3"),
        ('```\n{"move":"e4","candidate_moves":[],"rationale":"r","expected_reply":""}\n```', "e4"),
        ('Here is my move:\n{"move":"Nf3","candidate_moves":[],"rationale":"r","expected_reply":""}', "Nf3"),
        ('{"move":"d4","candidate_moves":[],"rationale":"r","expected_reply":""}\nThat should work.', "d4"),
        ('reasoning...\n```json\n{"move":"e4","candidate_moves":[],"rationale":"r","expected_reply":""}\n```\ndone', "e4"),
    ],
    ids=["fenced-json", "fenced-bare", "prose-prefix", "prose-suffix", "fence-inside-prose"],
)
def test_parse_decision_recovers_json_wrapped_in_fences_or_prose(raw, expected):
    """Reasoning models wrap JSON in markdown; a strict whole-body json.loads
    rejected every attempt and aborted the match with 'did not return legal SAN'."""
    decision = series.parse_decision(raw, LEGAL)

    assert decision is not None
    assert decision["move"] == expected


@pytest.mark.parametrize(
    "raw",
    ["", "I will play Nf3 because it controls the center.", '{"move":"Qh5"}', "{not json at all}"],
    ids=["empty", "prose-only", "illegal-move", "malformed"],
)
def test_parse_decision_still_rejects_unusable_responses(raw):
    assert series.parse_decision(raw, LEGAL) is None


def test_ask_reports_the_last_raw_response_when_every_attempt_fails(tmp_path, monkeypatch):
    """The old error named only the player, so the actual model output was lost."""
    monkeypatch.setattr(series, "request_decision", lambda *a, **k: ("no json here", {}))
    board = chess.Board()
    log = tmp_path / "log.txt"

    with pytest.raises(RuntimeError) as failure:
        series.ask(series.PLAYERS["gpt-oss"], board, [], log, tmp_path / "decisions.jsonl")

    assert "no json here" in str(failure.value)


def test_reset_live_archives_an_interrupted_game_then_clears_it(tmp_path):
    """Resetting must preserve the partial transcript, never silently delete it."""
    live = tmp_path / "live"
    live.mkdir()
    (live / "names.txt").write_text("GPT-OSS-120B INKLING-BF16\n")
    (live / "moves.txt").write_text("e4 e5\n")
    (live / "decision_log.jsonl").write_text('{"ply": 1}\n')
    (live / "series-runner.log").write_text("GAME 1/1\n")

    saved = series.reset_live(live)

    assert saved is not None and saved.exists()
    assert (saved / "moves.txt").read_text().split() == ["e4", "e5"]
    assert (live / "moves.txt").read_text().strip() == ""
    assert not (live / "decision_log.jsonl").read_text().strip()
    assert not (live / "pending.txt").exists()


def test_reset_live_on_an_empty_directory_archives_nothing(tmp_path):
    live = tmp_path / "live"
    live.mkdir()
    (live / "moves.txt").write_text("")

    assert series.reset_live(live) is None


def test_reset_live_marks_the_orphaned_match_abandoned(tmp_path, monkeypatch):
    """Clearing the live dir alone leaves match.json 'live', and the next
    `arcade start` then refuses with 'match-NNN is still live'."""
    root = tmp_path / "runtime"
    match_dir = root / "games/chess/match-002"
    match_dir.mkdir(parents=True)
    (match_dir / "match.json").write_text(json.dumps({
        "game": "chess", "match": 2, "status": "live", "result": None, "ended": None,
    }))
    monkeypatch.setattr(series, "ROOT", root)
    live = tmp_path / "live"
    live.mkdir()
    (live / "moves.txt").write_text("e4 e5\n")

    series.reset_live(live)

    record = json.loads((match_dir / "match.json").read_text())
    assert record["status"] == "abandoned"
    assert record["ended"]
    assert "reset" in (record.get("result") or "")


def test_reset_live_leaves_completed_matches_untouched(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    match_dir = root / "games/chess/match-002"
    match_dir.mkdir(parents=True)
    record = {"game": "chess", "match": 2, "status": "complete", "result": "A 1-0 B"}
    (match_dir / "match.json").write_text(json.dumps(record))
    monkeypatch.setattr(series, "ROOT", root)
    live = tmp_path / "live"
    live.mkdir()
    (live / "moves.txt").write_text("e4\n")

    series.reset_live(live)

    assert json.loads((match_dir / "match.json").read_text()) == record


def _summary(wins, draws, complete, requested=None):
    return {
        "games_requested": requested if requested is not None else complete,
        "games_complete": complete,
        "wins": wins,
        "draws": draws,
    }


def test_standings_line_calls_out_a_decisive_winner():
    line = series.standings_line(
        _summary({"INKLING-BF16": 6, "GPT-OSS-120B": 3}, 1, 10)
    )

    assert line == "INKLING-BF16 won 6/10 games!!! (1 draw)"


def test_standings_line_omits_the_draw_suffix_when_there_are_none():
    line = series.standings_line(
        _summary({"INKLING-BF16": 6, "GPT-OSS-120B": 4}, 0, 10)
    )

    assert line == "INKLING-BF16 won 6/10 games!!!"


def test_standings_line_reports_ties_and_all_draw_series():
    tied = series.standings_line(
        _summary({"INKLING-BF16": 3, "GPT-OSS-120B": 3}, 2, 8)
    )
    drawn = series.standings_line(
        _summary({"INKLING-BF16": 0, "GPT-OSS-120B": 0}, 10, 10)
    )

    assert tied == "Dead even: GPT-OSS-120B 3 — 3 INKLING-BF16 across 8 games (+2 draws)"
    assert drawn == "All 10 games drawn — dead even"
    assert series.standings_line(_summary({}, 0, 0)) == "No games complete yet."


def test_write_summary_stores_the_standings_line(tmp_path):
    path = tmp_path / "series-summary.json"
    rows = [(1, "INKLING-BF16 1-0 GPT-OSS-120B"), (2, "GPT-OSS-120B 1/2-1/2 INKLING-BF16")]

    series.write_summary(path, rows, 2)

    payload = json.loads(path.read_text())
    assert payload["standings"] == "INKLING-BF16 won 1/2 games!!! (1 draw)"


def test_ask_records_thinking_seconds_and_cleans_up_thinking_file(tmp_path, monkeypatch):
    """The live turn clock: thinking.txt exists while the model thinks (so
    the TUI can show elapsed), lands in the decision row, then is removed."""
    import time as time_module

    def fake_request(player, prompt, timeout):
        assert (tmp_path / "thinking.txt").read_text().split()[0] == "GPT-OSS-120B"
        return (
            json.dumps({
                "move": "Nf3",
                "candidate_moves": ["Nf3"],
                "rationale": "Develops.",
                "expected_reply": "Nf6",
            }),
            {},
        )

    monkeypatch.setattr(series, "request_decision", fake_request)
    decision_log = tmp_path / "decision_log.jsonl"

    series.ask(series.PLAYERS["gpt-oss"], chess.Board(), [], tmp_path / "model.log", decision_log)

    row = json.loads(decision_log.read_text())
    assert row["thinking_seconds"] >= 0
    assert not (tmp_path / "thinking.txt").exists()


def test_ask_removes_thinking_file_when_every_attempt_fails(tmp_path, monkeypatch):
    """Otherwise a dead runner leaves the TUI clock climbing forever."""
    monkeypatch.setattr(series, "request_decision", lambda *a, **k: ("no json", {}))

    with __import__("pytest").raises(RuntimeError):
        series.ask(
            series.PLAYERS["gpt-oss"], chess.Board(), [],
            tmp_path / "log.txt", tmp_path / "decisions.jsonl",
        )

    assert not (tmp_path / "thinking.txt").exists()



def test_ask_retries_http_502_with_backoff_and_succeeds(tmp_path, monkeypatch):
    """A transient 502 on first attempt should log, back off, and retry."""
    import urllib.error
    board = chess.Board()
    calls = []

    def fake_request(player, prompt, timeout):
        calls.append(timeout)
        if len(calls) == 1:
            raise urllib.error.HTTPError(
                "https://example.com", 502, "Bad Gateway", {}, None
            )
        return (
            json.dumps({
                "move": "Nf3",
                "candidate_moves": ["Nf3"],
                "rationale": "Dev.",
                "expected_reply": "Nf6",
            }),
            {},
        )

    monkeypatch.setattr(series, "request_decision", fake_request)
    # Speed up the test: don't actually sleep on backoff
    monkeypatch.setattr(series.time, "sleep", lambda s: None)

    decision = series.ask(series.PLAYERS["gpt-oss"], board, [], tmp_path / "log.txt", tmp_path / "decisions.jsonl")
    assert decision["move"] == "Nf3"
    assert calls == [180, 180]
    log = (tmp_path / "log.txt").read_text().lower()
    assert "502" in log or "bad gateway" in log
    assert "backoff" in log


def test_ask_retries_oserror_and_http_error_as_transient(tmp_path, monkeypatch):
    """OSError / URLError / HTTPError should all be retried, not crash."""
    import urllib.error
    board = chess.Board()
    attempts = []

    def fake_request(player, prompt, timeout):
        attempts.append(1)
        if len(attempts) == 1:
            raise OSError("connection reset")
        if len(attempts) == 2:
            raise urllib.error.URLError("timed out")
        return (
            json.dumps({"move": "e4", "candidate_moves": ["e4"], "rationale": "r", "expected_reply": ""}),
            {},
        )

    monkeypatch.setattr(series, "request_decision", fake_request)
    monkeypatch.setattr(series.time, "sleep", lambda s: None)
    decision = series.ask(series.PLAYERS["gpt-oss"], board, [], tmp_path / "log.txt", tmp_path / "decisions.jsonl")
    assert decision["move"] == "e4"
    assert len(attempts) == 3


def test_game_failed_is_runtime_error_with_match_number():
    """GameFailed must be catchable as RuntimeError but carry match_number."""
    cause = RuntimeError("boom")
    exc = series.GameFailed(42, cause)
    assert isinstance(exc, RuntimeError)
    assert exc.match_number == 42
    assert exc.cause is cause


def test_play_one_wraps_exhausted_ask_as_game_failed(tmp_path, monkeypatch):
    """play_one should raise GameFailed (not bare RuntimeError) on exhausted retries."""
    # Minimal plumbing: need a live dir with match.json and board state
    import subprocess
    root = tmp_path / "root"
    live = tmp_path / "live"
    live.mkdir()
    (root / "games/chess").mkdir(parents=True)
    # Fake a match record so play_one can find it
    match_dir = root / "games/chess/match-001"
    match_dir.mkdir(parents=True)
    (match_dir / "match.json").write_text(json.dumps({
        "game": "chess", "match": 1, "status": "live",
        "seats": {"white": {"name": "A"}, "black": {"name": "B"}},
        "host": {"name": "HOST"}, "live_dir": str(live),
    }))
    monkeypatch.setattr(series, "ROOT", root)
    # Mock start_match / post / board_from_log to avoid engine deps
    monkeypatch.setattr(series, "start_match", lambda *a, **k: type("R", (), {"stdout": ""})())
    # Use a real board with moves
    (live / "moves.txt").write_text("")
    (live / "fen.txt").write_text(chess.Board().fen())
    (live / "names.txt").write_text("A B\n")
    (live / "series.txt").write_text("1\n")
    (live / "results.txt").write_text("")
    # Patch series.next_match_number to return 1 so play_one finds match-001
    monkeypatch.setattr(series, "next_match_number", lambda: 1)
    # Make ask always fail
    def failing_ask(*a, **k):
        raise RuntimeError("did not return legal SAN after 3 attempts; last response: boom")
    monkeypatch.setattr(series, "ask", failing_ask)
    monkeypatch.setattr(series, "post", lambda *a, **k: None)

    series_log = live / "series-runner.log"
    series_log.write_text("")
    white = {"name": "A"}
    black = {"name": "B"}
    try:
        series.play_one(live, 1, 1, white, black, series_log, resume_live=False)
        assert False, "should have raised GameFailed"
    except series.GameFailed as exc:
        assert exc.match_number == 1
        assert "did not return legal SAN" in str(exc.cause)
    except RuntimeError:
        assert False, "should be GameFailed, not bare RuntimeError"


def test_run_series_continues_after_one_game_failure(tmp_path, monkeypatch):
    """run_series with --continue-on-failure should keep going after a GameFailed."""
    root = tmp_path / "root"
    live = tmp_path / "live"
    live.mkdir()
    (root / "games/chess").mkdir(parents=True)
    # two match records
    for n in (1, 2):
        d = root / f"games/chess/match-{n:03d}"
        d.mkdir(parents=True)
        d.joinpath("match.json").write_text(json.dumps({
            "game": "chess", "match": n, "status": "live",
            "seats": {"white": {"name": "A"}, "black": {"name": "B"}},
            "host": {"name": "HOST"}, "live_dir": str(live),
        }))
    monkeypatch.setattr(series, "ROOT", root)
    monkeypatch.setattr(series, "resolve_root", lambda live=None: root)
    (live / "moves.txt").write_text("")
    (live / "fen.txt").write_text(chess.Board().fen())
    (live / "names.txt").write_text("A B\n")
    (live / "series.txt").write_text("1\n")
    (live / "results.txt").write_text("")
    (live / "series-runner.log").write_text("")
    monkeypatch.setattr(series, "reset_live", lambda live: None)
    monkeypatch.setattr(series, "abandon_live_matches", lambda reason="": ["match-001"])
    monkeypatch.setattr(series, "write_summary", lambda *a, **k: None)
    # Make play_one succeed on second game, fail on first
    calls = []
    def fake_play_one(live, game_index, games_requested, white, black, series_log, resume_live=False):
        calls.append(game_index)
        if game_index == 1:
            raise series.GameFailed(1, RuntimeError("transient 502"))
        return (2, "A 1-0 B")
    monkeypatch.setattr(series, "play_one", fake_play_one)
    monkeypatch.setattr(series, "existing_series_rows", lambda n: [])
    monkeypatch.setattr(series, "next_match_number", lambda: 3)

    import sys
    orig_argv = sys.argv[:]
    try:
        sys.argv = ["series", "--games", "2", "--live-dir", str(live)]
        # run_series will use ROOT override above
        series.run_series()
    finally:
        sys.argv = orig_argv

    assert calls == [1, 2]
    log = (live / "series-runner.log").read_text()
    assert "ABANDONED" in log
    assert "SERIES COMPLETE" in log


def test_continue_on_failure_flag_parsing():
    """--continue-on-failure is on by default, --no-continue-on-failure turns it off."""
    import sys
    orig = sys.argv[:]
    try:
        sys.argv = ["prog", "--games", "5"]
        assert series.parse_args().continue_on_failure is True
        sys.argv = ["prog", "--games", "5", "--continue-on-failure"]
        assert series.parse_args().continue_on_failure is True
        sys.argv = ["prog", "--games", "5", "--no-continue-on-failure"]
        assert series.parse_args().continue_on_failure is False
    finally:
        sys.argv = orig


def test_apply_effort_override_replaces_every_player():
    players = [
        {"name": "A", "effort": "low"},
        {"name": "B", "effort": "high"},
    ]

    overridden = series.apply_effort_override(players, "medium")

    assert [player["effort"] for player in overridden] == ["medium", "medium"]
    assert [player["effort"] for player in players] == ["low", "high"]

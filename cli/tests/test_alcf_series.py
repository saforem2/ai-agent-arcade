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

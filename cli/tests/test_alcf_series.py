import importlib.util
import json
import subprocess
from pathlib import Path

import chess

MODULE_PATH = Path(__file__).resolve().parents[1] / "run_alcf_series.py"
spec = importlib.util.spec_from_file_location("run_alcf_series", MODULE_PATH)
series = importlib.util.module_from_spec(spec)
spec.loader.exec_module(series)


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
        captured.update(json.loads(request.data))
        return Response(json.dumps({
            "choices": [{"message": {"content": '{"move":"e4"}'}}],
            "usage": {},
        }).encode())

    monkeypatch.setattr(series.urllib.request, "urlopen", fake_urlopen)

    series.request_decision(series.PLAYERS["gpt-oss"], "choose", 180)

    assert captured["reasoning_effort"] == "low"
    assert captured["max_tokens"] == 4096


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

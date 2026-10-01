#!/usr/bin/env python3
"""Run a referee-verified ALCF chess series through arcade's file bus."""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
import shutil
from importlib.resources import as_file, files
from pathlib import Path

import chess

DEFAULT_LIVE = Path(os.environ.get("ARCADE_LIVE", "/tmp/alcf-chess-series"))
PLAYERS = {
    "gpt-oss": {
        "name": "GPT-OSS-120B",
        "provider": "llm-rosetta",
        "model": "gpt-oss-120b",
        "endpoint": "https://inference-api.alcf.anl.gov/resource_server/metis/api/v1/chat/completions",
    },
    "inkling": {
        "name": "INKLING-BF16",
        "provider": "llm-rosetta",
        "model": "inkling-bf16",
        "endpoint": "https://inference-api.alcf.anl.gov/resource_server/minerva/api/v1/chat/completions",
    },
}


def resolve_root(live=DEFAULT_LIVE):
    explicit = os.environ.get("THUNDERDOME_ROOT")
    if explicit:
        return Path(explicit).resolve()
    checkout = Path(__file__).resolve().parents[3]
    if (checkout / "engine").is_dir() and (checkout / "cli").is_dir():
        return checkout
    root = Path(live).resolve().parent / "thunderdome-runtime"
    engine = root / "engine"
    if not engine.exists():
        with as_file(files("arcade_cli").joinpath("_engine")) as packaged:
            shutil.copytree(packaged, engine)
    (root / "cli").mkdir(parents=True, exist_ok=True)
    (root / "games/chess").mkdir(parents=True, exist_ok=True)
    return root


ROOT = resolve_root()


def run(command, *, cwd=ROOT, env=None, timeout=300, check=True):
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        timeout=timeout,
        check=check,
        text=True,
        capture_output=True,
    )


def append(path, text):
    with path.open("a") as handle:
        handle.write(text.rstrip() + "\n")
        handle.flush()


def board_from_log(live):
    board = chess.Board()
    moves = (live / "moves.txt").read_text().split()
    for san in moves:
        board.push_san(san)
    return board, moves


def terminal_result(board):
    outcome = board.outcome(claim_draw=True)
    if outcome is None:
        return None
    reason = outcome.termination.name.lower().replace("_", " ")
    return outcome.result(), reason


def parse_decision(raw, legal):
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    move = data.get("move")
    if move not in legal:
        return None
    candidates = [item for item in data.get("candidate_moves", []) if item in legal][:3]
    rationale = " ".join(str(data.get("rationale", "")).split())[:280]
    expected = str(data.get("expected_reply", "")).strip()[:24]
    return {
        "move": move,
        "candidate_moves": candidates,
        "rationale": rationale,
        "expected_reply": expected,
    }


def get_inference_token():
    try:
        from alcf_tokens.auth import get_access_token
    except ImportError as exc:
        raise RuntimeError(
            "ALCF authentication requires `alcf-tokens`; run `uvx alcf-tokens login`."
        ) from exc
    try:
        return get_access_token("inference")
    except Exception as exc:
        raise RuntimeError(
            "No valid ALCF inference token. Run `uvx alcf-tokens login` and "
            "`uvx alcf-tokens test-token inference`."
        ) from exc


def request_decision(player, prompt, timeout):
    payload = json.dumps({
        "model": player["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "reasoning_effort": "low",
        "max_tokens": 8192,
    }).encode()
    request = urllib.request.Request(
        player["endpoint"],
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {get_inference_token()}"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.load(response)
    return decision_response(body)


def decision_response(body):
    usage = body.get("usage") or {}
    details = usage.get("completion_tokens_details") or {}
    message = body["choices"][0]["message"]
    raw = message.get("content") or message.get("reasoning") or ""
    return raw, {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "reasoning_tokens": details.get("reasoning_tokens"),
    }


def ask(player, board, moves, log, decision_log):
    legal = [board.san(move) for move in board.legal_moves]
    base_prompt = f"""You are {player['name']} in a chess match against another language model.
No chess engine, tools, code execution, web search, or outside assistance. Analyze the position yourself.
Moves so far (SAN): {' '.join(moves) if moves else '(none)'}
FEN: {board.fen()}
Legal SAN moves: {' '.join(legal)}
Return JSON only with these fields:
{{"move":"<legal SAN>","candidate_moves":["<up to 3 legal SAN moves>"],"rationale":"<one concise sentence explaining the choice>","expected_reply":"<one likely legal reply or empty string>"}}
This is a concise self-reported rationale, not hidden chain-of-thought."""
    for attempt in range(1, 4):
        prompt = base_prompt
        if attempt > 1:
            prompt += "\nYour previous response was invalid. Copy exactly one token from the legal SAN list."
        append(log, f"Ply {len(moves) + 1}: thinking (attempt {attempt})")
        try:
            raw, usage = request_decision(player, prompt, timeout=180)
        except (subprocess.TimeoutExpired, TimeoutError, urllib.error.URLError) as exc:
            append(log, f"timeout: {exc}")
            continue
        append(log, f"response: {raw or '(empty)'}")
        decision = parse_decision(raw, legal)
        if decision:
            row = {
                "ply": len(moves) + 1,
                "player": player["name"],
                "model": player["model"],
                "fen": board.fen(),
                **decision,
                **usage,
            }
            append(decision_log, json.dumps(row, ensure_ascii=False))
            return decision
    raise RuntimeError(f"{player['name']} did not return legal SAN")


def post(live, name, text):
    env = {**os.environ, "CHESS_NAME": name, "ARCADE_LIVE": str(live)}
    run(["bash", str(live / "game.sh"), "say", text], cwd=live, env=env)


def apply_move(live, player, san, log):
    env = {**os.environ, "CHESS_NAME": player["name"], "ARCADE_LIVE": str(live)}
    staged = run(["bash", str(live / "game.sh"), "submit", san], cwd=live, env=env)
    append(log, staged.stdout)
    pending = (live / "pending.txt").read_text().strip()
    applied = run(
        [sys.executable, str(live / "ref.py"), "move", pending],
        cwd=live,
        env={**os.environ, "ARCADE_LIVE": str(live)},
    )
    (live / "pending.txt").unlink(missing_ok=True)
    append(log, applied.stdout)
    return applied.stdout


def start_match(live, white, black):
    env = {
        **os.environ,
        "ARCADE_ROOT": str(ROOT),
        "ARCADE_LIVE": str(live),
    }
    return run(
        [
            sys.executable,
            "-m",
            "arcade_cli.main",
            "--live-dir",
            str(live),
            "start",
            "chess",
            "--white",
            white["name"].lower(),
            "--black",
            black["name"].lower(),
            "--host",
            "series-host",
        ],
        env=env,
    )


def archive_match(live, result):
    env = {
        **os.environ,
        "ARCADE_ROOT": str(ROOT),
        "ARCADE_LIVE": str(live),
    }
    return run(
        [
            sys.executable,
            "-m",
            "arcade_cli.main",
            "--live-dir",
            str(live),
            "archive",
            "--game",
            "chess",
            "--result",
            result,
        ],
        env=env,
    )


def play_one(live, game_index, games_requested, white, black, series_log, resume_live=False):
    if resume_live:
        match = current_live_match(white, black)
        if match is None:
            raise RuntimeError("--resume-live found no matching live match")
        match_number = match["match"]
        append(series_log, f"RESUMING match-{match_number:03d} at ply {len((live / 'moves.txt').read_text().split())}")
    else:
        started = start_match(live, white, black)
        append(series_log, started.stdout)
        match_number = next_match_number()
    match_path = ROOT / "games/chess" / f"match-{match_number:03d}" / "match.json"
    match = json.loads(match_path.read_text())
    if match["match"] != match_number:
        raise RuntimeError(f"match number mismatch in {match_path}")
    logs = {
        white["name"]: live / "white-model.log",
        black["name"]: live / "black-model.log",
    }
    for path in logs.values():
        if not resume_live:
            path.write_text("")
    decision_log = live / "decision_log.jsonl"
    if not resume_live:
        decision_log.write_text("")
    post(live, "HOST", f"Series game {game_index}/{games_requested}. {white['name']} has White; {black['name']} has Black.")
    append(series_log, f"GAME {game_index}/{games_requested} match-{match_number:03d}: {white['name']} vs {black['name']}")
    for _ in range(300):
        board, moves = board_from_log(live)
        terminal = terminal_result(board)
        if terminal:
            if not board.is_game_over():
                score, reason = terminal
                entry = f"{white['name']} {score} {black['name']}"
                with (live / "results.txt").open("a") as handle:
                    handle.write(entry + "\n")
                (live / "result.txt").write_text(f"draw ({reason})\n")
                (live / "banner.txt").write_text(f"{entry} — {reason}\n")
                post(live, "HOST", f"{entry} ({reason}).")
            break
        player = white if len(moves) % 2 == 0 else black
        decision = ask(player, board, moves, logs[player["name"]], decision_log)
        san = decision["move"]
        append(series_log, f"  ply {len(moves) + 1}: {player['name']} {san}")
        output = apply_move(live, player, san, logs[player["name"]])
        if "GAMEOVER" in output:
            break
        time.sleep(0.2)

    verified = run(
        [sys.executable, str(live / "ref.py"), "verify"],
        cwd=live,
        env={**os.environ, "ARCADE_LIVE": str(live)},
    )
    results_path = live / "results.txt"
    results = [line for line in results_path.read_text().splitlines() if line.strip()] if results_path.exists() else []
    if not results:
        raise RuntimeError(f"match-{match_number:03d} ended without a result")
    result = results[-1]
    archived = archive_match(live, result)
    append(series_log, f"  {result} | {verified.stdout.strip()} | {archived.stdout.strip()}")
    return match_number, result


def next_match_number():
    nums = []
    for path in (ROOT / "games/chess").glob("match-*/match.json"):
        nums.append(int(path.parent.name.split("-")[1]))
    return max(nums)


def current_live_match(white, black):
    wanted = (white["name"], black["name"])
    matches = []
    for path in (ROOT / "games/chess").glob("match-*/match.json"):
        data = json.loads(path.read_text())
        seats = data.get("seats") or {}
        names = (
            (seats.get("white") or {}).get("name"),
            (seats.get("black") or {}).get("name"),
        )
        if data.get("status") == "live" and names == wanted:
            matches.append(data)
    return max(matches, key=lambda item: item["match"]) if matches else None


def write_summary(path, rows, games_requested):
    wins = {PLAYERS["gpt-oss"]["name"]: 0, PLAYERS["inkling"]["name"]: 0}
    draws = 0
    for _, result in rows:
        first, score, second = result.split()[:3]
        if score == "1-0":
            wins[first] += 1
        elif score == "0-1":
            wins[second] += 1
        else:
            draws += 1
    payload = {
        "games_requested": games_requested,
        "games_complete": len(rows),
        "wins": wins,
        "draws": draws,
        "matches": [{"match": number, "result": result} for number, result in rows],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")


def existing_series_rows(before_match):
    rows = []
    for path in sorted((ROOT / "games/chess").glob("match-*/match.json")):
        data = json.loads(path.read_text())
        if data.get("match", 0) < before_match:
            continue
        result = data.get("result") or ""
        if data.get("status") == "complete" and len(result.split()) == 3:
            rows.append((data["match"], result))
    return rows


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=20)
    parser.add_argument("--live-dir", type=Path, default=DEFAULT_LIVE)
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--resume-live", action="store_true")
    return parser.parse_args()


def main():
    global live_dir, ROOT
    args = parse_args()
    live_dir = args.live_dir.resolve()
    ROOT = resolve_root(live_dir)
    live_dir.mkdir(parents=True, exist_ok=True)
    series_log = live_dir / "series-runner.log"
    summary = live_dir / "series-summary.json"
    if args.start_index < 1 or args.start_index > args.games:
        raise SystemExit("--start-index must be between 1 and --games")
    if args.start_index == 1:
        series_log.write_text("")
        completed = []
    else:
        completed = existing_series_rows(next_match_number() - args.start_index + 1)
        append(series_log, f"RESUME at game {args.start_index}/{args.games}")
    resume_live = args.resume_live
    for game_index in range(args.start_index, args.games + 1):
        if game_index % 2:
            white, black = PLAYERS["gpt-oss"], PLAYERS["inkling"]
        else:
            white, black = PLAYERS["inkling"], PLAYERS["gpt-oss"]
        completed.append(play_one(
            live_dir,
            game_index,
            args.games,
            white,
            black,
            series_log,
            resume_live=resume_live,
        ))
        resume_live = False
        write_summary(summary, completed, args.games)
    append(series_log, f"SERIES COMPLETE: {args.games} games")


if __name__ == "__main__":
    main()

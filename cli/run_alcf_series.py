#!/usr/bin/env python3
"""Run a referee-verified ALCF chess series through arcade's file bus."""

import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path

import chess

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIVE = Path(os.environ.get("ARCADE_LIVE", "/tmp/alcf-chess-series"))
PLAYERS = {
    "gpt-oss": {
        "name": "GPT-OSS-120B",
        "provider": "llm-rosetta",
        "model": "alcf-metis/gpt-oss-120b",
    },
    "inkling": {
        "name": "INKLING-BF16",
        "provider": "llm-rosetta",
        "model": "alcf-minerva/inkling-bf16",
    },
}
SAN_RE = re.compile(r"(?:O-O-O|O-O|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+#]?)")


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


def ask(player, board, moves, log):
    legal = [board.san(move) for move in board.legal_moves]
    base_prompt = f"""You are {player['name']} in a chess match against another language model.
No chess engine, tools, code execution, web search, or outside assistance. Analyze the position yourself.
Moves so far (SAN): {' '.join(moves) if moves else '(none)'}
FEN: {board.fen()}
Legal SAN moves: {' '.join(legal)}
Choose exactly one legal move. Reply with only its SAN token and nothing else."""
    for attempt in range(1, 4):
        prompt = base_prompt
        if attempt > 1:
            prompt += "\nYour previous response was invalid. Copy exactly one token from the legal SAN list."
        append(log, f"Ply {len(moves) + 1}: thinking (attempt {attempt})")
        proc = run(
            [
                "hermes",
                "-z",
                prompt,
                "--provider",
                player["provider"],
                "--model",
                player["model"],
                "--reasoning",
                "high",
                "--safe-mode",
            ],
            cwd=live_dir,
        )
        raw = proc.stdout.strip()
        append(log, f"response: {raw or '(empty)'}")
        candidates = [raw.strip("` \n\t.'\"")] + SAN_RE.findall(raw)
        for candidate in candidates:
            if candidate in legal:
                return candidate
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
        ["uv", "run", "--quiet", "--with", "chess", "python", str(live / "ref.py"), "move", pending],
        cwd=live,
        env={**os.environ, "ARCADE_LIVE": str(live)},
    )
    (live / "pending.txt").unlink(missing_ok=True)
    append(log, applied.stdout)
    return applied.stdout


def start_match(live, white, black):
    return run(
        [
            "uv",
            "run",
            "--project",
            "cli",
            "arcade",
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
        ]
    )


def archive_match(live, result):
    return run(
        [
            "uv",
            "run",
            "--project",
            "cli",
            "arcade",
            "--live-dir",
            str(live),
            "archive",
            "--game",
            "chess",
            "--result",
            result,
        ]
    )


def play_one(live, game_index, games_requested, white, black, series_log):
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
        path.write_text("")
    post(live, "HOST", f"Series game {game_index}/{games_requested}. {white['name']} has White; {black['name']} has Black.")
    append(series_log, f"GAME {game_index}/{games_requested} match-{match_number:03d}: {white['name']} vs {black['name']}")
    for _ in range(300):
        board, moves = board_from_log(live)
        if board.is_game_over(claim_draw=True):
            break
        player = white if len(moves) % 2 == 0 else black
        san = ask(player, board, moves, logs[player["name"]])
        append(series_log, f"  ply {len(moves) + 1}: {player['name']} {san}")
        output = apply_move(live, player, san, logs[player["name"]])
        if "GAMEOVER" in output:
            break
        time.sleep(0.2)

    verified = run(
        ["uv", "run", "--quiet", "--with", "chess", "python", str(live / "ref.py"), "verify"],
        cwd=live,
        env={**os.environ, "ARCADE_LIVE": str(live)},
    )
    results = [line for line in (live / "results.txt").read_text().splitlines() if line.strip()]
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


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=20)
    parser.add_argument("--live-dir", type=Path, default=DEFAULT_LIVE)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    live_dir = args.live_dir.resolve()
    live_dir.mkdir(parents=True, exist_ok=True)
    series_log = live_dir / "series-runner.log"
    summary = live_dir / "series-summary.json"
    series_log.write_text("")
    completed = []
    for game_index in range(1, args.games + 1):
        if game_index % 2:
            white, black = PLAYERS["gpt-oss"], PLAYERS["inkling"]
        else:
            white, black = PLAYERS["inkling"], PLAYERS["gpt-oss"]
        completed.append(play_one(live_dir, game_index, args.games, white, black, series_log))
        write_summary(summary, completed, args.games)
    append(series_log, f"SERIES COMPLETE: {args.games} games")

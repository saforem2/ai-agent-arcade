#!/bin/bash
# Referee v2: agents read the board and submit moves themselves via game.sh.
# The referee only approves staged moves and advances the game.
D="${ARCADE_LIVE:-/tmp/chess}"
cd "$D"
LOG="$D/relay2.log"
MAX_PLIES=300
touch "$LOG"

ref() { uv run --quiet --with chess python "$D/ref.py" "$@"; }

WHITE_AGENT="${CHESS_WHITE:-kimi-white}"
BLACK_AGENT="${CHESS_BLACK:-codex-black}"

moves=$(cat moves.txt 2>/dev/null || true)
ply=$(printf '%s' "$moves" | wc -w | tr -d ' ')
last_san="${moves##* }"
[ -z "$last_san" ] && last_san="(none — you have the first move)"
echo "START at ply $ply ($WHITE_AGENT vs $BLACK_AGENT)" >>"$LOG"
herdr notification show "CHESS v2" --body "self-service match starting" --sound done >>"$LOG" 2>&1

while [ "$ply" -lt "$MAX_PLIES" ]; do
  if [ $((ply % 2)) -eq 0 ]; then agent=$WHITE_AGENT; color=White; else agent=$BLACK_AGENT; color=Black; fi
  if [ -s pending.txt ]; then
    echo "[ply $ply] using pre-staged move" >>"$LOG"
    mv=$(cat pending.txt)
    res=$(ref move "$mv" 2>>"$LOG")
    rm -f pending.txt
    if [ -n "$res" ] && [ "$res" != "ILLEGAL" ]; then
      echo "[ply $ply] APPROVED $agent -> $res" >>"$LOG"
      last_san=$(printf '%s' "$res" | awk '{print $2}')
      if printf '%s' "$res" | grep -q GAMEOVER; then
        result=$(printf '%s' "$res" | grep -oE 'GAMEOVER.*')
        herdr notification show "CHESS OVER" --body "$result" --sound request >>"$LOG" 2>&1
        echo "DONE: $result" >>"$LOG"
        exit 0
      fi
      ply=$((ply + 1))
      continue
    fi
  fi
  rm -f pending.txt
  prompt="Chess match, you are $color. Opponent's last move: $last_san . Inspect the position by running: bash $D/game.sh show — then choose your move and stage it by running: bash $D/game.sh submit '<move>' (SAN). If it prints ILLEGAL, pick another from the legal list and submit again. Stop after STAGED is printed; the referee applies it. Do not edit any files."
  herdr agent prompt "$agent" "$prompt" --wait --timeout 300000 >>"$LOG" 2>&1 || { echo "PROMPT FAIL $agent" >>"$LOG"; break; }
  waited=0
  while [ ! -s pending.txt ] && [ "$waited" -lt 60 ]; do sleep 2; waited=$((waited + 2)); done
  if [ ! -s pending.txt ]; then
    herdr agent prompt "$agent" "No staged move detected. Run: bash $D/game.sh submit '<move>' now." --wait --timeout 180000 >>"$LOG" 2>&1
    waited=0
    while [ ! -s pending.txt ] && [ "$waited" -lt 40 ]; do sleep 2; waited=$((waited + 2)); done
  fi
  if [ ! -s pending.txt ]; then echo "STALL: $agent staged nothing" >>"$LOG"; break; fi
  mv=$(cat pending.txt)
  res=$(ref move "$mv" 2>>"$LOG")
  rm -f pending.txt
  if [ -z "$res" ] || [ "$res" = "ILLEGAL" ]; then echo "REJECTED: $agent -> $mv" >>"$LOG"; continue; fi
  echo "[ply $ply] APPROVED $agent -> $res" >>"$LOG"
  last_san=$(printf '%s' "$res" | awk '{print $2}')
  if printf '%s' "$res" | grep -q GAMEOVER; then
    result=$(printf '%s' "$res" | grep -oE 'GAMEOVER.*')
    herdr notification show "CHESS OVER" --body "$result" --sound request >>"$LOG" 2>&1
    echo "DONE: $result" >>"$LOG"
    exit 0
  fi
  ply=$((ply + 1))
done
echo "HALTED at ply $ply" >>"$LOG"
herdr notification show "CHESS" --body "match halted at ply $ply" --sound done >>"$LOG" 2>&1

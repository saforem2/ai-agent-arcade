#!/bin/bash
# Chess referee: relays moves between codex-white and kimi-black
D="${ARCADE_LIVE:-/tmp/chess}"
cd "$D"
LOG="$D/relay.log"
MAX_PLIES=300
touch "$LOG"

ref() { uv run --quiet --with chess python "$D/ref.py" "$@"; }

get_move() {  # $1=agent $2=prompt -> echoes SAN or empty
  local agent="$1" prompt="$2" out mv
  herdr agent prompt "$agent" "$prompt" --wait --timeout 300000 >>"$LOG" 2>&1 || return 1
  sleep 2
  out=$(herdr agent read "$agent" --source recent-unwrapped --lines 80 2>>"$LOG")
  mv=$(printf '%s\n' "$out" | grep -oE 'MOVE: *[a-hxRNBQKO0-8=+#-]+' | tail -1 | sed 's/MOVE: *//')
  printf '%s' "$mv"
}

herdr notification show "CHESS" --body "codex vs kimi — match starting" --sound done >>"$LOG" 2>&1

moves=$(cat moves.txt 2>/dev/null || true)
ply=$(printf '%s' "$moves" | wc -w | tr -d ' ')
last_san="${moves##* }"
[ -z "$last_san" ] && last_san="(none — you open)"
echo "RESUMING at ply $ply, last move: $last_san" >>"$LOG"
while [ "$ply" -lt "$MAX_PLIES" ]; do
  if [ $((ply % 2)) -eq 0 ]; then agent=codex-white; color=White; else agent=kimi-black; color=Black; fi
  fen=$(cat fen.txt)
  base="We are playing a live chess game. You are $color. Do NOT use tools, read files, or explain anything. Current position FEN: $fen . Opponent's last move: $last_san . Reply with exactly one line in this format and nothing else: MOVE: <your move in SAN>"
  mv=$(get_move "$agent" "$base")
  echo "[ply $ply] $agent -> '$mv'" >>"$LOG"
  if [ -z "$mv" ]; then echo "STALL: no move parsed from $agent" >>"$LOG"; break; fi
  res=$(ref move "$mv" 2>>"$LOG")
  if [ "$res" = "ILLEGAL" ] || [ -z "$res" ]; then
    legal=$(uv run --quiet --with chess python -c "import chess;b=chess.Board(open('fen.txt').read().strip());print(' '.join(b.san(m) for m in b.legal_moves))")
    mv=$(get_move "$agent" "Your move '$mv' is ILLEGAL in position $fen . Legal moves are: $legal . Reply with exactly one line: MOVE: <your move in SAN>")
    echo "[ply $ply retry] $agent -> '$mv'" >>"$LOG"
    res=$(ref move "$mv" 2>>"$LOG")
    if [ "$res" = "ILLEGAL" ] || [ -z "$res" ]; then echo "FORFEIT: $agent played illegal twice" >>"$LOG"; break; fi
  fi
  echo "[ply $ply] applied: $res" >>"$LOG"
  last_san=$(printf '%s' "$res" | awk '{print $2}')
  if printf '%s' "$res" | grep -q GAMEOVER; then
    result=$(printf '%s' "$res" | grep -oE 'GAMEOVER.*')
    herdr notification show "CHESS OVER" --body "$result" --sound request >>"$LOG" 2>&1
    echo "DONE: $result" >>"$LOG"
    exit 0
  fi
  ply=$((ply + 1))
done
herdr notification show "CHESS" --body "paused after $ply plies — board holds" --sound done >>"$LOG" 2>&1
echo "PAUSED after $ply plies" >>"$LOG"

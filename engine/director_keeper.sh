#!/bin/bash
# Nudges the idle host when it goes idle mid-match.
# Stops when the game ends (result posted to chat after this run's baseline) or after 60 nudge cycles.
D="${ARCADE_LIVE:-/tmp/chess}"
# HOST_AGENT is the preferred spelling (HOST rename, docs/design-history.md
# §14); DIRECTOR_AGENT still works as a fallback so a running keeper started
# under the old convention isn't broken by the rename.
HOST_AGENT="${HOST_AGENT:-${DIRECTOR_AGENT:-host}}"
cd "$D" || exit 1
BASE=$( [ -f chat.log ] && wc -l < chat.log || echo 0 )
[ -f names.txt ] && read -r WHITE_NAME BLACK_NAME < names.txt
WHITE_NAME="${WHITE_NAME:-White}"
BLACK_NAME="${BLACK_NAME:-Black}"
for i in $(seq 1 60); do
  sleep 90
  # game over? (only result patterns posted since this keeper started)
  if tail -n +$((BASE+1)) chat.log | grep -qiE "1-0|0-1|1/2-1/2|forfeit.*wins|game over|\b(check|stale)mate\b"; then
    echo "director_keeper: game over detected (post-baseline), exiting" >> keeper.log
    exit 0
  fi
  # board stale >180s?
  [ -f moves.txt ] || continue
  age=$(( $(date +%s) - $(stat -f %m moves.txt) ))
  [ "$age" -lt 180 ] && continue
  # never nudge after mate (game-5 retro fix): a chess SAN ending in '#' is
  # checkmate (python-chess's own board.san() convention), and result.txt
  # existing means a resignation/accepted-draw already ended the game --
  # either way the host going quiet here is correct, not stuck. This is
  # a second, more direct check than the chat.log scan above (which can lag
  # if the host hasn't posted the result yet).
  last_san=$(tail -c 64 moves.txt | awk '{print $NF}')
  case "$last_san" in *'#') echo "director_keeper: last move $last_san is mate, exiting" >> keeper.log; exit 0 ;; esac
  [ -f result.txt ] && { echo "director_keeper: result.txt exists, exiting" >> keeper.log; exit 0; }
  # host idle?
  status=$(herdr agent get "$HOST_AGENT" 2>/dev/null | grep -o '"agent_status":"[a-z]*"' | head -1)
  case "$status" in *idle*|*done*) ;; *) continue ;; esac
  side=$(( $(wc -w < moves.txt) % 2 ))
  [ "$side" -eq 0 ] && mover="$WHITE_NAME (White)" || mover="$BLACK_NAME (Black)"
  echo "director_keeper: nudge $i (stale ${age}s, $mover to move)" >> keeper.log
  herdr agent prompt "$HOST_AGENT" "You have gone quiet mid-match with the board stale. It is $mover to move. Resume the FACILITATOR.md turn loop now and continue until the game ends." >/dev/null 2>&1
done
echo "director_keeper: exhausted 60 cycles" >> keeper.log

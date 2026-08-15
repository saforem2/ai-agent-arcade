#!/bin/bash
# Xiangqi interface for playing agents:
#   game_xq.sh show            board, FEN, whose turn, full ICCS legal-move list
#   game_xq.sh status          ply, side to move, last move, pending, gameover,
#                               draw-offer flag -- one-shot recovery, zero args
#   game_xq.sh history         numbered ICCS move list
#   game_xq.sh await-turn      block until it's your seat's turn (or game over),
#                               then print `show`
#   game_xq.sh submit <move>   stage a move (ICCS, e.g. h2e2) for the referee
#   game_xq.sh resign          stage a resignation for the referee
#   game_xq.sh offer-draw      stage a draw offer for the referee
#   game_xq.sh accept-draw     stage acceptance of a pending draw offer
#   game_xq.sh say '<text>'    post to the room (name from $CHESS_NAME, else $USER)
#   game_xq.sh chat            just the room, no board
#
# Self-locating: game_xq.sh is deployed into the live match dir (next to
# game_xq_cli.py, moves.txt, ...), so its own path IS the live dir. Callers
# are player-agent shells that never have ARCADE_LIVE exported into them --
# deriving D from $ARCADE_LIVE here would silently fall back to /tmp/xiangqi.
# Resolve from BASH_SOURCE instead and export it so game_xq_cli.py/chat.py
# inherit the same dir.
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export ARCADE_LIVE="$D"

case "$1" in
  submit|resign|offer-draw|accept-draw)
    # Staging verbs only: run without exec so we can gate + fire the host's
    # auto-poke afterward instead of trusting the player to remember to
    # notify anyone. Game-6 retro fix: pokes must fire only for a
    # genuinely-staged move (exit 0, no result.txt, pending.txt non-empty --
    # a stale/empty pending is not "something is staged right now") and
    # carry a structured payload the host can act on without a status
    # round-trip. A receipt line always follows so a player can end its turn
    # with confidence either way. Strictly non-fatal throughout -- never
    # blocks or fails the submit itself.
    uv run --quiet python "$D/game_xq_cli.py" "$@"
    status=$?
    # host.txt is the 2e-renamed successor to director.txt (see
    # docs/design-history.md §14); fall back to a stale director.txt from an
    # older deploy so an already-live room isn't broken mid-match by the rename.
    HOST_FILE="$D/host.txt"
    [ -f "$HOST_FILE" ] || HOST_FILE="$D/director.txt"
    if [ "$status" -ne 0 ]; then
      echo "HOST NOT NOTIFIED (stage failed)"
    elif [ -f "$D/result.txt" ]; then
      echo "HOST NOT NOTIFIED (gameover)"
    elif [ ! -s "$D/pending.txt" ]; then
      echo "HOST NOT NOTIFIED (pending cleared before receipt)"
    elif [ ! -f "$HOST_FILE" ]; then
      echo "HOST NOT NOTIFIED (no host.txt)"
    elif ! command -v herdr >/dev/null 2>&1; then
      echo "HOST NOT NOTIFIED (herdr missing)"
    else
      pending="$(cat "$D/pending.txt")"
      name="${pending%%$'\t'*}"
      san="${pending#*$'\t'}"
      ply=$(( $(wc -w < "$D/moves.txt" 2>/dev/null || echo 0) + 1 ))
      if herdr agent prompt "$(cat "$HOST_FILE")" "STAGED $name $san ply=$ply" >/dev/null 2>&1; then
        echo "HOST NOTIFIED"
      else
        echo "HOST NOT NOTIFIED (stage failed)"
      fi
    fi
    exit "$status"
    ;;
  *)
    exec uv run --quiet python "$D/game_xq_cli.py" "$@"
    ;;
esac

#!/bin/bash
# Core War interface for playing agents:
#   game_cw.sh show                phase banner, hold, rounds so far, room tail
#   game_cw.sh status              phase, hold, pending, locked, rounds,
#                                   gameover -- one-shot recovery, zero args
#   game_cw.sh stage <file>        validate + stage a warrior for the referee
#   game_cw.sh spar <file> [imp|dwarf]
#                                  local exhibition vs a dummy (writes nothing)
#   game_cw.sh resign              stage a resignation for the referee
#   game_cw.sh await-battle        block until the battle result is posted,
#                                   then print `show`
#   game_cw.sh say '<text>'        post to the room (name from $CHESS_NAME, else $USER)
#   game_cw.sh chat                just the room
#
# Self-locating: game_cw.sh is deployed into the live match dir (next to
# game_cw_cli.py, moves.txt, ...), so its own path IS the live dir. Callers
# are player-agent shells that never have ARCADE_LIVE exported into them --
# deriving D from $ARCADE_LIVE here would silently fall back to /tmp/corewar.
# Resolve from BASH_SOURCE instead and export it so game_cw_cli.py/chat.py
# inherit the same dir.
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export ARCADE_LIVE="$D"

case "$1" in
  stage|resign)
    # Staging verbs only: run without exec so we can gate + fire the host's
    # auto-poke afterward instead of trusting the player to remember to
    # notify anyone. Game-6 retro fix: pokes must fire only for a
    # genuinely-staged token (exit 0, no result.txt, pending.txt non-empty --
    # a stale/empty pending is not "something is staged right now") and
    # carry a structured payload the host can act on without a status
    # round-trip: `STAGED <NAME> warrior` for a stage, `STAGED <NAME> resign`
    # for a resignation, and `BATTLE READY` when this stage means both seats
    # now hold a warrior (the host's lock -> battle cue, FACILITATOR_CW.md).
    # A receipt line always follows so a player can end its turn with
    # confidence either way. Strictly non-fatal throughout -- never blocks
    # or fails the stage itself.
    uv run --quiet python "$D/game_cw_cli.py" "$@"
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
      token="${pending#*$'\t'}"
      case "$token" in
        resign)
          payload="STAGED $name resign"
          ;;
        *)
          payload="STAGED $name warrior"
          # Both seats hold one once this stage lands if the OTHER seat's
          # referee-installed copy already exists. seats.txt labels the red
          # seat "white" (warriors/A.red) and the blue seat "black"
          # (warriors/B.red) -- the shared role machinery's internal labels.
          seat="$(awk -v n="$name" 'tolower($1)==tolower(n){print tolower($2); exit}' "$D/seats.txt" 2>/dev/null)"
          other=""
          [ "$seat" = "white" ] && other="B.red"
          [ "$seat" = "black" ] && other="A.red"
          if [ -n "$other" ] && [ -f "$D/warriors/$other" ]; then
            payload="BATTLE READY"
          fi
          ;;
      esac
      if herdr agent prompt "$(cat "$HOST_FILE")" "$payload" >/dev/null 2>&1; then
        echo "HOST NOTIFIED"
      else
        echo "HOST NOT NOTIFIED (stage failed)"
      fi
    fi
    exit "$status"
    ;;
  *)
    exec uv run --quiet python "$D/game_cw_cli.py" "$@"
    ;;
esac

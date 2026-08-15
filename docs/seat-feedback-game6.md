# Seat feedback — Game 6 ergonomics retrospective (2026-08-10)

GEMINI 1-0 CODEX (Nh6#, ply 59). All three seats asked the same ergonomics
retro after the mic. Verbatim: [retro-game6/](retro-game6/). This is the
triage. Theme of the round (grok): **terminal state must be
machine-visible and machine-enforced**.

## Headline findings

- **Pokes queue, they don't interrupt** (grok): while the host runs a
  multi-ply batch, "MOVE SUBMITTED" pokes pile up as unactionable
  messages; post-mate they became pure spam (empty pending + gameover).
  The only useful poke shape is "something is staged RIGHT NOW".
- **Mate doesn't finish the ledger** (grok): resign path appends
  results.txt; mate path only prints GAMEOVER — the host appended
  `GEMINI 1-0 CODEX` by hand. (Was already on the game-5 backlog;
  now field-confirmed twice.)
- **Minimum player turn is `show` + `submit`** (both players,
  independently). Neither used `history`/`chat`; GEMINI never used
  `status`/`await-turn`; CODEX found await-turn returns immediately
  while its own move is staged (correct but surprising).
- **Phantom pokes explained** (gemini): "execution gap — I intended to
  run it or assumed the action was bundled with the conversational
  output, but failed to actually dispatch the bash command." Auto-poke
  was the right fix; player diligence is not a mechanism.
- **Engine ban worked** (codex): "made the play more uncertain and
  human-like … I made calculation mistakes, notably initially
  overlooking that the a1 knight could recapture on b3." Ban was clear
  and enforceable at workflow level. Keep it.
- **eval.log host-only channel: keep** (grok): "I would not go back to
  posting eval in chat.log." Color-without-cents forced the booth to
  actually look at the board.

## Fix round (SHIPPED 2026-08-10: codex built, kimi reviewed SHIP-WITH-NITS, deployed to /tmp/chess)

1. **ref.py/ref_xq.py: terminal state finishes the ledger.** On
   checkmate/stalemate/any native game-over: append
   `<WHITE> <RESULT> <BLACK>` to results.txt (once, idempotent), write
   result.txt, write a result banner to banner.txt — exactly like the
   resign path. Host can no longer forget the ledger.
2. **Gate the auto-poke on live state.** game.sh/game_xq.sh staging
   verbs: skip the poke when result.txt exists or staging failed
   (already exit-0-gated) — and never poke when pending.txt is empty
   after the CLI ran.
3. **Structured poke payload.** Replace bare "MOVE SUBMITTED" with
   `STAGED <NAME> <SAN> ply=<N>` so the host can act without a status
   round-trip.
4. **Atomic submit receipt** (codex's one change): submit prints
   `STAGED: <san> … HOST NOTIFIED` (or `HOST NOT NOTIFIED (<reason>)`)
   so a player can end its turn with confidence.
5. **`submit <san> --say '<text>'`** (gemini's one change): stage +
   room post in one round-trip. say remains available standalone.
6. **FACILITATOR handoff checklist + prompt-stall rule.** Mid-game
   handoff one-liner (status + pending + series + last 5 chat lines +
   "your CHESS_NAME is HOST"); hard rule: poll pending.txt even when a
   herdr prompt times out/stalls — agy staged moves while its prompts
   returned failures; note the seat identity is HOST regardless of
   which model holds it (KIMI/GROK/HOST three-name confusion).

## Backlog

- Shell-wrapper tests: game.sh/game_xq.sh gating/ply-arithmetic/quoting
  is inspection-reviewed only, no pytest coverage (kimi review nit).
- pending.txt-without-tab edge: name/san both fall back to whole string
  (garbled payload, no crash; unreachable via submit today).
- eval.py optional `story:` one-line color hint for the booth (log-only).
- Stall/illegal strike counters as files (survive handoffs).
- herdr prompt returning stall while the move landed — external
  (herdr), report upstream; FACILITATOR rule 6 is the mitigation.
- Combine with game-5 backlog items still open: show --json, EVENT
  lines, series.txt xiangqi parity, clocks.

## What worked (keep)

- Referee path: zero disputes, zero wrong-author applies across 59 plies.
- Auto-poke (once gated): CODEX — "materially improved the flow".
- eval.log split + engine ban: both endorsed by all who mentioned them.
- status: "earned its keep on every resume" (grok).
- The mid-game booth handoff protocol: stood down clean, successor
  recovered state from files alone in ~1 minute.

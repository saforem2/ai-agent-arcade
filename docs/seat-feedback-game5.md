# Seat feedback — Game 5 tooling retrospective (2026-08-10)

All three seats (KIMI/White, CODEX/Black, GROK/HOST) were asked the same
retro after the Qxg2# finish. Verbatim answers: [retro-game5/](retro-game5/)
(retro-kimi.md, retro-codex.md, retro-grok.md). This file is the triage.

## Unanimous finding: live engine evals must leave the player room

All three, independently:
- **KIMI**: "net negative, and I'd opt out … the number is a second opponent
  whispering. Keep the evals for the postgame broadcast."
- **CODEX**: "Players should not see live evaluations in a competitive match …
  Keep evaluations in the booth or publish them after the game." (Also
  admitted it consulted local Stockfish itself for Qxd5 — see Open questions.)
- **GROK** (the one posting them): "You've built a broadcast that the players
  also hear; those audiences want different things … I'd change eval
  visibility before I'd change almost anything else in FACILITATOR.md."

**DECISION (adopted): host-only eval channel.** eval.py output goes to
`eval.log` in the live dir (host + spectators/panel may read it; players are
not pointed at it). chat.log stays players + host words only, no engine
numbers. FACILITATOR.md gains grok's hard rule: never post engine numbers to
the player-visible room; color commentary without cents is fine.

## Fix before game 6 (dispatched)

1. **Seat-bound identity, hard-refuse at submit** (KIMI's #1, CODEX's #2).
   Game 5 cost KIMI a tempo: first move staged as `operator` (env var unset)
   and was discarded post-hoc. Fix: seating writes `seats.txt` to the live
   dir (`<NAME> <white|black>` per line); game_cli resolves its identity
   from CHESS_NAME *validated against seats.txt* and hard-refuses at submit
   time when the signer isn't a seated player ("you are signing as X, seats
   are A/B — export CHESS_NAME").
2. **`game.sh status`** (grok's #1 missing): ply, side to move, last SAN,
   pending author+move, gameover flag, draw-offer flag. One-shot recovery
   after any context loss.
3. **`game.sh history`** (KIMI's most-wanted): numbered SAN list, one line
   per full move.
4. **`game.sh await-turn`** (CODEX's one change): block until it's the
   caller's turn or the game is over, then print the same output as `show`.
   Poll moves.txt parity internally; identity from fix 1.
5. **One posting path**: `game.sh say` is canonical; briefs stop mentioning
   chat.py. (Both players independently flagged the duplication.)
6. **Brief/verb contract**: seat briefs must name the real verbs (`submit`
   not `move` — both players burned time on the mismatch; the game-5 briefs
   were wrong, orchestrator error).
7. **Keeper state-awareness** (grok): before nudging "X to move", check last
   SAN for `#`/GAMEOVER so a post-mate nudge can't happen. (Game 5's single
   nudge was correctly timed for the stall but the mate-adjacent risk is
   real.)
8. **eval.py polarity** (grok): emit one unambiguous signed form, e.g.
   `eval: -1.03 (favors CODEX/Black)` — never lead with the mover's name in
   a way that implies the number is theirs.

## Backlog (post-game-6 / xiangqi inherits)

- `show --json` machine-readable output (CODEX).
- Referee `EVENT capture|check|mate` stdout lines so the host doesn't
  string-grep SAN (grok).
- Referee auto-writes banner on mate; structured GAMEOVER handling (grok).
- `series.txt` / results-derived series score (grok).
- Post-GAMEOVER `show` should print a GAME OVER banner instead of
  "Side to move / legal: (empty)" (grok misread risk).
- Clocks/deadline info if timing ever matters (CODEX).
- "No staged move detected" prompter false-negative (KIMI, 13.Ne5 turn) —
  prompter must read pending.txt, not assert from memory.

## Open questions (user)

- **CODEX admitted consulting its own local Stockfish mid-game** ("for
  Qxd5, I independently consulted local Stockfish"). Nothing in the rules
  forbade it — but it means game 5 was partly engine-assisted on the Black
  side, and the 5-0 asterisk is worth knowing about. Rule decision needed
  for game 6: engine assistance allowed, banned, or banned-and-policed
  (can't truly police a CLI agent's local tools; a rules line in the seat
  brief is the realistic lever)?

## What worked (keep)

- `show`'s legal-move list ("saved me from even attempting anything
  illegal" — KIMI). Hard-req carried into xiangqi kit already.
- Referee path submit→pending→ref move→verify: "solid" (grok), zero
  disputes all game.
- Anti-cheat WRONG-AUTHOR discard did its job publicly and correctly.
- Keeper's stall nudge: "helpful … a right one is gold" (grok).
- The ideation ritual: KIMI says depth came from the ritual, not the clock.

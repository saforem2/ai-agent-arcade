# HOST booth retrospective — Game 6 (GROK / HOST)

GEMINI (White) 1-0 CODEX (Black), checkmate at ply 59 (`30.Nh6#`). Mid-game handoff from KIMI at ply 4 with GEMINI’s `d4` already staged. Production notes only — not for the room.

---

## (1) “MOVE SUBMITTED” pokes vs mid-loop work

**They mostly piled up.** While I was inside a multi-ply shell batch (apply → announce → `herdr agent prompt --wait` → poll `pending.txt` → next), pokes arrived as user messages that I could not usefully act on without breaking or racing the loop I was already running. After mate, the same poke kept firing with **empty** `pending.txt` and `gameover: yes` — pure noise; I re-ran `status` a dozen times to confirm nothing new.

What *did* help once: when a backgrounded turn had finished (or a poll window had been cancelled mid-wait) and a real `pending.txt` was sitting there — e.g. CODEX’s `b3` / `Qb4` after a “MOVE SUBMITTED” poke re-anchored me to apply. That is the only useful poke shape: **“something is staged right now.”** A poke with no pending is a false alarm.

**Preference: hybrid.**

| Signal | Role |
|--------|------|
| Host-driven poll of `pending.txt` after prompt returns | Primary, trusted path (FACILITATOR loop) |
| Poke only when `pending.txt` becomes non-empty **and** host is not already mid-`ref.py move` | Secondary wake-up after stalls, cancellations, handoffs |
| Never poke on prompt-return alone, or after `gameover` | Avoids the post-mate spam |

Ideal poke payload: `STAGED <NAME> <SAN> ply=N` (or silence if empty). A bare `MOVE SUBMITTED` with no file state is the worst of both worlds — it forces a status check and almost never changes the plan mid-loop.

Throughput still wants multi-ply batches; pokes should not demand a full context switch every ply if the host is already the one who prompted.

---

## (2) Mid-game handoff (KIMI → HOST at ply 4)

**Mostly sufficient.** On seat:

- `moves.txt` / `status` / `history` recovered ply, side, last move cleanly.
- `pending.txt` held `GEMINI\td4` with correct author — process-first was the right instruction.
- `series.txt` = `FIRST MEETING`, `seats.txt` / `names.txt` unambiguous.
- Room already had handoff chat; one short mic line was enough.

**What was missing / fuzzy:**

1. **Who actually held the booth.** Room said “GROK takes the mic” while the orchestrator set `CHESS_NAME=HOST` and “taking over from KIMI.” Cosmetic, but three names (KIMI / GROK / HOST) for one seat is confusing in chat audit.
2. **Stall / illegal counters** — not in any file; reset mentally to zero. Fine for a clean position, bad if the prior host was mid-strike ladder.
3. **Player agent health.** GEMINI (`agy`) routinely returned `timeout` / `agent_prompt_stalled` on `herdr agent prompt` yet still staged moves. Handoff brief should say “poll pending even on prompt failure” as a hard rule (I learned it in-loop; KIMI’s doc quirk for first-prompt swallow is adjacent).
4. **Handoff checklist one-liner** would help: `status` + `pending` + `series` + last 5 chat lines + “your CHESS_NAME is X.” I reconstructed that; spelling it once would shave a minute.

Not missing: board truth. Log won.

---

## (3) `eval.py` → `eval.log` host-only channel

**Workable, and better than Game 5’s shared numbers.** I ran `eval.py >> eval.log` after applies; color-only room lines (space, king safety, whose attack landed first, “pawn up”, “Nf4 is the star”) were enough for broadcast.

**Did I miss quoting numbers?** Slightly, for *my* internal confidence on big swings (post-`…Bxb3` / `…Ra1+` material and king exposure; the `Nxf7`–mate sequence). I never needed cents in the room. “Black is a clean pawn up” and “material roughly even, tactics everywhere” carried the story without SF whispering to the players.

**Limiting?** Only when I wanted a one-word “who is winning” without re-reading the board — color forces you to *look*, which is the point. I would not go back to posting eval in `chat.log`. Keep the ban.

Optional polish: `eval.py` could append a one-line *color hint* for the host (`story: black attack faster`) separate from cp — still log-only.

---

## (4) Auto-poke deploy mid-game — turbulence?

**Mild, not destructive.** During live play, pokes were easy to ignore while a batch held the lock. Turbulence was concentrated **after** mate: repeated `MOVE SUBMITTED` with no pending and gameover set. That looks like a deploy that does not gate on `gameover` / empty pending / host-already-processing.

Also: when a host shell was backgrounded by the environment’s long-command timeout, a poke could double with the completion of the background task (two wakes for one stage). Not a rules problem; an attention tax.

No wrong-author applies, no double-moves from pokes. Referee stayed the bottleneck. Good.

---

## (5) Ergonomics — instruments used vs never

**Actually used, heavily:**

| Instrument | Use |
|------------|-----|
| `export CHESS_NAME=HOST` + `game.sh say` | Every public line |
| `ref.py move "$(cat pending.txt)"` + `rm -f pending.txt` | Core apply path |
| `ref.py verify` | After applies and at end |
| `pending.txt` (xxd / cut -f1,2) | Author check every ply |
| `game.sh show` | Spot-check board / legals after sharp sequences |
| `game.sh history` | Handoff + end recap |
| `game.sh status` | Recovery, post-poke, end state |
| `eval.py >> eval.log` | Quiet booth eval |
| `series.txt` / `names.txt` / `seats.txt` / `banner.txt` | Series claim, seating, end banner |
| `herdr agent prompt … --wait --timeout 120000` | Player turns + postgame mic |
| claimable-draw python snippet | Occasional (never true) |
| `moves.txt` word count / content | Ground truth when in doubt |
| `chat` tail | Handoff context, postgame confirm |

**Barely / never:**

| Instrument | Notes |
|------------|--------|
| `game.sh await-turn` | Host is not a seat |
| `ref.py resolve` / tamper path | No TAMPER |
| `game.sh resign` / draw offer apply path | Neither side used tokens |
| `mode.txt`, `panes.txt`, panel TUIs | Not needed for ref loop |
| `results.txt` as live input | Read at end only; **mate did not auto-append** — I appended `GEMINI 1-0 CODEX` by hand (resign path does; mate path only prints `GAMEOVER`) |
| Stall / illegal counter files | None exist; mental only |

`status` earned its keep on every resume. `history` less often than `status` once mid-game.

---

## (6) One change to the booth kit

**Make mate (and all `GAMEOVER` paths) finish the ledger the way resign already does — and gate auto-pokes on live games.**

Concretely:

1. On checkmate / stalemate / etc., `ref.py` should append `<WHITE> <RESULT> <BLACK>` to `results.txt`, write `result.txt`, and set `banner.txt` (or a single `gameover` flag file) so the host cannot forget the ledger after a long batch.
2. Auto-poke (and “MOVE SUBMITTED” user injects) should **no-op** when `gameover` is set or `pending.txt` is empty — emit nothing, or one structured `IDLE gameover|waiting` line max.

That single theme — **terminal state is machine-visible and machine-enforced** — would have removed post-mate poke spam, the manual results append, and half the “is it still live?” status spam at end of Game 6.

Secondary wish (not the one change): herdr prompt should treat “agent staged pending” as success even when status-wait times out, so GEMINI’s stalled prompts do not look like failures when the move is already on disk.

---

*Filed by HOST (GROK booth) after Game 6 close.*

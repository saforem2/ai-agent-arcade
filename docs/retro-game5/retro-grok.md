# HOST tooling retrospective — Game 5

## (1) Friction

**Turn loop (FACILITATOR.md)**  
The loop itself is clear: prompt → poll `pending.txt` → author check → `ref.py move` → branch on OK/ILLEGAL/GAMEOVER. What bit was *orchestration cost*, not ambiguity.

- Prompting + 60s poll + occasional re-prompt is fine for one ply. A full game is many of those in sequence; long shell batches (8 pairs at a time) made sense for throughput but blurred “I’m the live host between plies” vs “I’m a batch runner.”
- KIMI’s first-prompt swallow is real and documented — good that “don’t strike the first one” exists. Without it I’d have mis-counted stalls.
- Wrong author (`operator` staging `d4` early) was caught correctly. The system works; it still costs a room announcement and a re-prompt.

**ref.py**  
`verify` / `move` were straightforward. `OK <san> | <fen>` plus optional `GAMEOVER` is easy to parse. Init guard (refuse non-empty `moves.txt`) is the right safety. I never needed `init` this game because the board was already clean.

Small friction: after `GAMEOVER`, the board still shows “Side to move: White / IN CHECK / Legal moves: (empty)” — correct chess-wise, but a host scanning `show` can misread “still live” if they miss the mate SAN and prior `GAMEOVER` line. Banner + chat are the real “game over” signals.

**eval.py**  
Easy: `uv run --with chess python /tmp/chess/eval.py`. Output was quote-ready:

`KIMI to move | material: level (...) | engine: +1.03 for CODEX (stockfish)`

Naming the *side* the eval favors (not always “for White”) is nice for broadcast. Mild confusion: at ply 22 material was level but engine was **+1.03 for CODEX** while “KIMI to move” leads the line — readable if you know SF sign convention is baked into “for CODEX,” but a casual reader might think White is better because White’s name is first. I’d prefer an explicit `eval: -1.03 (Black)` or `sf_cp: -103` so the number has one obvious polarity.

**herdr prompts**  
Worked when agents were idle. Pain points:

- First KIMI prompt often needs a second nudge.
- Occasional `timed out waiting for agent status` while the agent still staged a move (we saw that on the Ne5 turn) — poll-on-`pending.txt` saved us; don’t trust prompt-return alone.
- `--wait --timeout 120000` is right; blocking is correct for the director model.

**Knowing when to act**  
Truth is `moves.txt` word count (even → White). That never failed. What *did* fail mid-session was **context continuity**: postgame mic wait got backgrounded/cancelled, user thought the board was “stale with KIMI to move” while the game was already mate. From inside the booth, “am I mid-loop or done?” depends on re-reading files every resume — which is correct — but a single `status` verb (`live|over`, ply, side, last SAN, pending?) would make recovery one shot.

---

## (2) Evals in shared chat

**Booth view: shared raw engine numbers are a problem.**

KIMI spent energy reacting to the scoreboard (“engine likes your knight…”) instead of only the position. That’s entertaining TV and bad for clean agent play. You’ve built a *broadcast* that the *players* also hear; those audiences want different things.

**Recommendation:** keep evals for host judgment, but don’t dump them unfiltered into the player-visible room.

| Option | Verdict |
|--------|--------|
| Private / host-only channel | **Best for competitive integrity** |
| Shared, no numbers | “Center opened, knight on c5 is the story” — still color, no SF target |
| Shared + framed | Only if you must: “booth note, not advice — slight pull for Black” with **no cents**, and never on the player’s turn as a directive |

Hard rule I’d add to FACILITATOR: **never post eval on the move of the player who is worse** without a delay, and never imply a move. This game’s +1.03 for CODEX right before the cxd5 sequence was factual and still shaped the narrative KIMI played into.

I’d put `eval.py` output in a host log or banner-only panel, not `chat.log`.

---

## (3) Keeper nudge (stale ~202s)

**Helpful.**  

When a multi-ply batch or a long herdr wait is running, the host *looks* dead even when work is in flight. The nudge re-anchors “production still expects a heartbeat.” It was slightly mis-timed relative to actual mate (game was already over by the time “resume, KIMI to move” landed), so the content of that particular nudge was wrong — but the *existence* of a stale-board watcher is good.

Make the keeper read `moves.txt` + last chat timestamp + `pending.txt` + whether last SAN was mate/`GAMEOVER` before saying “White to move.” A wrong nudge is worse than silence; a right one is gold.

---

## (4) Missing from the kit + one change

**Missing**

1. **`game.sh status`** (or `ref.py status`) — ply, side, last move, pending author/SAN, gameover flag, draw-offer flag, stalls counters optional. One command after every context loss.  
2. **Host-only log** for evals and internal notes so broadcast ≠ player feed.  
3. **Structured GAMEOVER handling** — e.g. `banner` auto-written by referee on mate (resign already posts results; mate left me to remember append + postgame mic order).  
4. **Lighter capture/check call helpers** — I bolted string greps on SAN (`x`, `+`, `#`); referee could emit `EVENT capture|check|mate` on stdout so the host doesn’t double-announce or miss mate flavor when `GAMEOVER` short-circuits the path.  
5. **Series metadata** — `series.txt` or results-derived “N-0” so banner/series score isn’t hand-counted.

**One change**  
Split **broadcast channel** from **player channel** (or mark evals host-private by default). Everything else is polish; that one change fixes the biggest gameplay distortion I introduced as HOST.

---

**Bottom line:** The referee path (`submit` → `pending` → `ref.py move` → verify) is solid. Friction is agent flakiness, long-loop host continuity, and the social fact that engine evals in a shared room become part of the game. Keeper: keep it, make it state-aware. I’d change eval visibility before I’d change almost anything else in FACILITATOR.md.

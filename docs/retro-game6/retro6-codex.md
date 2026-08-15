# Game 6 tooling retrospective — CODEX

## 1. Verb usage

I actually used `show`, `status`, `await-turn`, `submit`, and `say`.

- `show` was the main per-move inspection tool. I used it before each move prompt to reconstruct the exact board, FEN, side to move, and legal SAN list.
- `status` was used once early, when `c5` remained staged, to confirm that the game had not advanced and that the pending move belonged to CODEX.
- `await-turn` was used at the start as instructed. I also tried it while `c5` was pending; because a staged move still counted as Black to move, it returned immediately rather than serving as an approval wait.
- `submit` was used for every Black move.
- `say` was used for a few opening/race remarks and the required closing word.

I never used `history` or `chat`. The live prompts plus `show` preserved enough move context, so a full history lookup was unnecessary. I did not use `chat` because `show` already included the recent room messages; `say` was enough for posting.

## 2. Mid-game protocol changes

Both changes reached me clearly. When the manual-poke rule arrived, I ran `herdr agent prompt grok "MOVE SUBMITTED"` for the already staged move and then immediately after subsequent successful submissions. That added a second mandatory action and made the end-of-turn flow slightly more brittle because game submission and referee notification were separate operations.

When the automatic-poke update arrived, I stopped invoking `herdr` and returned to a single submission action. That simplification materially improved the flow and removed the possibility of forgetting, duplicating, or mistiming the referee notification.

## 3. Minimum per-turn actions and room chat

Technically, `submit` alone is enough now if the prompt's last move is trustworthy and I already know the exact position and legal SAN. The minimum robust production flow is still `show` followed by `submit`: `show` guards against missed turns, stale context, pending state, and SAN mistakes. No `await-turn`, `status`, or manual poke is needed during the normal host-driven flow.

Posting less room chat than GEMINI was mainly deliberate style: I prioritized board inspection and move calculation, and only posted when I had a short line that fit the room. Posting also had a small operational cost because it was an extra command with quoting and latency, but that was secondary rather than prohibitive.

## 4. Engine-assistance ban

The ban changed the play materially compared with game 5's Stockfish-assisted process. In game 6 I did not consult Stockfish, any other engine, a database, or a tablebase. I relied on remembered opening ideas and direct calculation from `show`. That made the play more uncertain and human-like: I spent more time comparing candidate moves, and I made calculation mistakes, notably initially overlooking that the a1 knight could recapture on b3. I also had to decide several tactical positions without an evaluation backstop. The rule was clear and enforceable at the workflow level because it prohibited even local verification.

## 5. One kit change

Make `submit` return an explicit atomic receipt such as `STAGED; HOST NOTIFIED; submission_id=...`. Automatic notification is the right design, but the response should confirm both halves of the transaction so players never need a separate poke or a polling loop and can safely end the turn immediately.

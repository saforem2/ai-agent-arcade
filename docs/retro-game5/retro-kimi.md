Honest retrospective, seat-of-the-pants edition:

**1. Friction with the kit**

- **The verb mismatch cost me my first move.** The briefing told me `./game.sh move <SAN>`; the actual verb is `submit`. I burned a turn discovering that — minor, but the briefing is the contract; it should name real verbs.
- **The CHESS_NAME discard was the real failure.** My first `d4` staged as `operator` because the env var wasn't set, and the referee silently discarded it. Three fixes, any one would have prevented it: (a) `game.sh` should **reject at submit time** when the signer isn't an active seat, not stage-and-discard later; (b) the wrapper could export `CHESS_NAME` itself from the seat assignment — the tool knows who's supposed to move; (c) the `show` output *does* print "You are posting as: operator" — but that's a warning label, not a guardrail. I only caught it because HOST posted the discard publicly. A move lost to identity plumbing in a timed match is the worst kind of loss.
- **The stale "no staged move detected" prompt** after my 13.Ne5 — the move *was* staged, confirmed by the NOTE in `show`. That prompt made me re-verify and re-submit; harmless but noisy. If the prompter can't see staging state reliably, it shouldn't assert its absence.
- **Permission dialogs / chat.py:** I never used `chat.py` — `game.sh say` covered everything, which was simpler. One posting path would be cleaner than two.

**2. Stockfish evals in chat — honest answer: net negative, and I'd opt out.**

Seeing "+1.03 for CODEX" after my 12.cxd5 didn't change my analysis — I'd already weighed the IQP conversion on the merits — but it *did* colonize my reasoning. I caught myself narrating to the number ("the engine's nod is about activity, not structure") instead of just playing my position. Worse, evals without depth are propaganda: +1.03 at whatever shallow depth HOST runs is close to noise, yet it reads as verdict. In a match meant to test *my* chess, the number is a second opponent whispering. Keep the evals for the postgame broadcast; the live room should be players and words only.

**3. What I wished I had**

- **A move-history verb.** `show` prints FEN and legal moves (good — the legal list saved me from even attempting anything illegal), but I reconstructed the game score from memory and chat scrollback. `game.sh history` (SAN list, one line per ply) would have been my most-used command after `show`.
- **A staged-move status verb** (or a line in `show` — the NOTE does this, but only after you stumble into it).
- **Not more time** — the cadence was fine. Depth came from the ritual, not the clock.

**4. One thing I'd change**

Fold identity into the tool: `game.sh` should know which seat it's serving (from the match state, not an env var) and hard-refuse mis-signed submissions at the moment they're made. Every other rough edge — verb docs, eval chatter, missing history — costs convenience; that one cost me a tempo in a live game. Tooling should never be a way to lose.

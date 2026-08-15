# DECISION — the v2 track system (2026-08-14)

Consulted: opus.md (CORE LOOP, 498 lines), kimi.md (133 lines). Both
independently converged on the same architecture, which LOCKS it:
fixed techno grid, one continuous track per match, phrase blocks joined
at bar lines, all events quantized, battle state → arrangement, forced
build into the elimination drop (offline lookahead), true-silence
hitstop, beatless merged-drone draw outro, and both reject vocal
chops/samples. v1's plumbing (Timeline, Mix, limiter, mux) untouched.

## Rulings where they differ

1. **Tempo: 135 BPM** (Opus). Derived, not chosen: ROUND_TARGET_S 50 +
   LOADIN_S 1.5 + VERDICT_S 1.4 = 52.9s = 29.8 bars — a tie round is a
   30-bar section for free. Kimi's 130 fits less exactly.
2. **Harmony: Opus's loop.** 8-bar Dm7|F6|Gsus|A(add4) — every chord a
   rotation of the D-minor-pentatonic set, real root motion with the
   nothing-can-land-wrong guarantee intact. And the Bb law: ONE note
   outside the scale in the whole piece, spent only on the elimination
   drop and the win finale. The outside note is the death note.
3. **Anti-noise law: Opus's, verbatim, as a test.** The battle never
   places an onset — it selects slots of existing patterns, velocity,
   timbre, filter. If moving an event 30ms changes the rhythm, it's
   sonification and it's a bug. (Kimi's sqrt-velocity slot-fusion is the
   right overflow rule within that law.)
4. **Macro-structure: Kimi's phrase-block table** (Intro/Groove/Build/
   Drop/Breakdown/Outro, state-triggered, bar-line joins) as the
   arranger's skeleton, with **Opus's intensity engine inside Groove**
   (0.42 energy + 0.28 momentum + 0.20 pressure + 0.10 contest, per-bar,
   4 tiers gating 8 layers, hysteresis 2-up/4-down; continuous automation
   on top: momentum→filter, quiet→reverb, contest→width+detune).
5. **Instrument library: Kimi's recipes** — they are the most
   production-ready numbers on the table: 808 kick (110→55Hz sweep +
   4kHz click), 3-voice supersaw bass (-7/+19 cents, resonant LPF
   250→900Hz), pentatonic pluck stabs, coal-crackle noise perc, cryo-sub
   thud, FM bell (ratio 3.14, index 4.0→0.5), beating-sine hats
   (8.0/8.234kHz), inharmonic bell pad (1, 2.01, 3.03, 4.21, 6.18) with
   0.37Hz tremolo, frost-steam sidechain-gated hiss, reverse-cymbal
   suck, Shepard riser. Implement with Opus's per-harmonic-gain-array
   filtering trick (no scipy, no per-sample IIR loops).
6. **Production identities: Opus's "two records" law** layered onto
   Kimi's timbres. Ember: saturated, light bitcrush, 56% swing, dragged
   +8ms, D1–A4, tresillo pattern gate. Ice: bone-dry synthesis into
   reverb, zero drive, machine-quantized, D5–D7, offbeat garage gate.
   The shared kick/sub inherits the DOMINANT faction's processing
   (drive, pitch floor, click brightness, reverb send scale with ground
   share) — territory audible in neutral passages.
7. **Drop timing: DO NOT quantize the silence** (against Kimi's ±200ms
   downbeat snap). The hitstop silence is synced to the picture's freeze
   — that law outranks the grid. The riser anticipates the exact t
   (offline lookahead), silence lands sample-exact with the frame,
   payoff (sub impact + Bb + winner motif) re-locks on the next 1/16
   (Opus). Loser's layers are CUT, not faded.
8. **Tie rounds still get a drop** (Opus): the arranger finds the
   round's peak-intensity bar and drops there — no silence, no Bb, so a
   kill can never be confused with a stalemate. match-002 is three ties;
   this path carries the whole current catalog.
9. **Draw outro, merged from both**: drums stop dead on the final
   downbeat, no fill (O); both faction pads glide in pitch toward each
   other into one shared D drone (O) blending ember saw warmth + ice
   sine purity + bell cluster (K); stereo collapses to center (K); slow
   breath, exponential fade to ~-60dB, never gated to zero (O — dissolve,
   don't cut). A win stops on a downbeat; a draw dissolves.
10. **Load-in: Kimi's anacrusis** — beat-1 silence, ember 808 pickup on
    the offbeats, ice reverse-cymbal suck, both locking the full groove
    on the bar-4 downbeat (compressed restatement at round cuts).
11. **Rejections locked** (both agree): no vocal collage, no sampled
    pathos, no brat-wall loudness, no whimsy layers, no Eno
    non-determinism — his patience only, in the outro. Both consultants'
    rejection sections were argued as taste; keep them in the record.

## Implementation shape

New sibling module `engine/score_cw.py` (Opus's module plan): Grid,
analyze() (the arranger: phrase blocks + intensity + stride detection +
lookahead), render_score() (instruments per rulings above).
`record_cw.py` keeps extract/Mix/limiter/frames/mux; its v1 musical
functions (punctuate, faction_beds, ambient_bed, bomb_hit, rumble,
motif) are replaced by calls into score_cw. v1 mix law stays: quiet
room, wide crest, real limiter. Tests: the 30ms anti-noise law, grid
alignment, tie-vs-kill drop distinction, determinism, duration
exactness; timeline tests untouched.

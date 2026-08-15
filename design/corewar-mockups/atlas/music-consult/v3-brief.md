# v3 consult — emergent material, conducted performance (2026-08-14)

You are one of two consultants (an Opus agent and a Kimi agent) asked to
design v3 of the Core War broadcast soundtrack. Write your proposal to
the file your dispatcher names, one to three pages. Do not edit any repo
files.

## History (read these, in order)

- `music-consult/brief.md` — the v2 brief (context on the recorder,
  timeline, constraints — ALL hard constraints there still apply:
  numpy-only synthesis, determinism, exact duration, mix law).
- `music-consult/DECISION.md` — the v2 rulings. v2 is implemented in
  `engine/score_cw.py` and shipped on two match masters.
- `engine/score_cw.py` — Grid / analyze() / render_score() as built.
- `engine/record_cw.py` — extract()/Mix/limiter/mux plumbing (stays).

## The verdict on v2 (user)

v2 works — "Love it" — but the user then heard match-001 and match-002
back to back: **they sound like siblings.** Same 135 BPM grid, same
8-bar Dm loop, same instrument bank; only the arrangement differs. The
user's original instinct was emergence: "attach the music elements to
the animation patterns and let things emerge." v1 tried literal
emergence and was rejected as borderline noise. So:

## The v3 direction: emergent MATERIAL, conducted PERFORMANCE

Keep everything that made v2 music — the fixed grid, quantization, the
30ms anti-noise law (battle selects slots, never places onsets), the
phrase-block arranger, the drop/hitstop laws, the mix law. But derive
the COMPOSITION from the match itself, deterministically:

1. **Harmony & motif from the warriors' code.** The warrior programs
   (Redcode: opcodes, modes, operands, lengths — parsed source is
   available at extract time) become the melodic/harmonic DNA: which
   scale/rotation, each faction's leitmotif contour, the bass figure.
   Two different warrior programs → two recognizably different songs.
   The same warrior in a rematch → recognizably ITS theme.
2. **Rhythm vocabulary from behaviour.** v2 already lets stride
   patterns select percussion slots; go further — the imp-train period,
   fork tempo, bombing cadence of THIS match generate the pattern
   vocabulary itself (within the anti-noise law: patterns are built
   offline from aggregate behaviour, then the battle conducts them).
3. **Structure from the battle** — v2's arranger already does this;
   keep it.

## Questions you must answer

- **The safety guarantee.** v2's nothing-can-land-wrong property came
  from one pentatonic set. If harmony is match-derived, what replaces
  that guarantee? (Constrained generation — e.g. code hashes choose
  among curated scale/mode/rotation families — is acceptable; free
  chromaticism is not.)
- **Ruling 2's fate.** The Bb death-note law (ONE outside note, spent
  only on kill drop + win finale) is the catalog's best idea. How does
  "the outside note" generalize when the scale is match-derived?
- **Catalog coherence.** Across many matches the broadcasts should
  still be one series — same sonic brand, different songs. What is
  fixed forever (tempo? production identities? drop grammar?) vs.
  derived per match? Be explicit: a FIXED/DERIVED table.
- **Faction identity vs. warrior identity.** ember/ice production
  identities are currently faction-fixed. Does a warrior's theme live
  in its faction's production dress, or does code-derived timbre creep
  in? (Careful: faction legibility — hearing who is winning — must
  survive.)
- **Degenerate inputs.** A 3-line imp vs. a 100-line p-space monster;
  two copies of the SAME warrior fighting each other; a warrior whose
  hash lands on an ugly rotation. Show your mapping is total and the
  worst case is still musical.
- **Implementation delta.** What changes in score_cw.py (be specific:
  new module? a `dna.py`? which functions of analyze()/render_score()
  take new parameters), what is untouched, and which existing tests
  break vs. carry over. New tests you'd pin (e.g. same-warriors →
  same theme; different-warriors → measurably different pitch-class
  distribution).

## Hard constraints (unchanged from v2)

Deterministic (same match → byte-identical WAV; sin-hash, no RNG);
numpy-only synthesis; exact broadcast duration; offline lookahead
allowed; quiet-room mix law; laptop-speaker sane. The two shipped
masters (match-001/002) will be re-rendered under v3 — your design is
judged against BOTH: the kill match and the three-tie stalemate.

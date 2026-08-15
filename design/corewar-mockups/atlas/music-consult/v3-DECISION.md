# v3 DECISION — CORE DNA (2026-08-14)

Consulted: v3-opus.md (CORE DNA, 279 lines) and v3-kimi.md (DNA System,
128 lines). As in v2, the consultants converged on the architecture,
which LOCKS it:

- One new pure module `engine/dna_cw.py` inserted BEFORE analyze();
  everything downstream of material selection is untouched.
- **Hash selects from a vetted space, never generates pitch.** The
  worst possible match is a plain song, never a wrong one.
- One anhemitonic pentatonic set per match — the safety guarantee was
  never "D minor", it was the semitone-free/tritone-free SHAPE, which
  is transposition/rotation-invariant.
- The death note generalizes as a rule (♭6 of the tonic); ruling 2
  (one outside note, kill drop + win finale only) carries verbatim.
- Faction production dresses stay 100% fixed — warrior identity lives
  in melody, faction identity in dress. Both explicitly reject (or
  concede deletable) code-derived timbre.
- Tempo stays 135 forever (both: the brand pulse; also derived from
  pacing, not chosen).
- **Null DNA reproduces v2 byte-for-byte** — the fallback for a
  warrior that fails to parse is the record already shipped, and the
  entire existing test suite becomes v3's first regression test.
- Deltas: dna_cw.py (~120–180 lines, no numpy) + a few lines in
  extract() + parameterization of score_cw's constant lookups.

## Rulings where they differ

1. **Key space: Opus's 60 keys** (12 tonics × 5 pentatonic rotations),
   not Kimi's 5 fifths-related tonics in one mode. Mode variety is the
   strongest anti-sibling lever we have, Opus swept all 60 for the
   safety property (zero violations), and Opus's octave-1 bass-root
   clamp ([32.70, 61.74) Hz) answers Kimi's register/laptop-safety
   concern exactly. Catalog "one family" cohesion is carried by shape,
   tempo, and dress — not by restricting tonics.
2. **Death note: Opus's total rule** — ♭6 of the tonic, ♭2 fallback
   when the rotation contains the ♭6 (man-gong only; +1 is absent from
   all five rotations, so the fallback always resolves). Required by
   ruling 1; degenerates to Bb at D minor. Kimi's ♭6-only rule is the
   same law restricted to one mode.
3. **Hashing machinery: Kimi's pure-integer DJB2 fold** (canonicalize →
   tokenize → fold; no floats). Opus's sin-hash fingerprint relies on
   libm's sin() being bit-identical across platforms — fine inside one
   render, a hazard for the public repo's "same match → byte-identical
   WAV" promise across machines. Integer hashing makes determinism a
   property of the arithmetic, not the C library. Kimi's canonicalizer
   (strip comments/headers, expand FOR/ROF, substitute equ) comes with
   it.
4. **Pair combination: symmetric (Opus's intent, Kimi's mechanism).**
   Seat swap of the same two warriors is the same match and must be the
   same song. Fold the two warrior hashes in sorted order —
   `match_hash = fold(sorted((hA, hB)))` — symmetric like Opus's
   `frac(fp(A)+fp(B))`, with no XOR-collapse on mirror matches (Kimi's
   worry), in pure integers (ruling 3).
5. **Motif: Opus's contour walk.** Opcodes are signed moves in degree
   space accumulated mod 5 (SPL +4 — a fork leaps; DAT −4 — a bomb
   falls), 8 degrees read from warrior.start, cycling if shorter;
   articulation from A-operand modes. The 3-line imp becoming a rising
   scale is the thesis of the whole feature in one example. Kimi's
   (opcode+operand)%5 is total but has no narrative semantics.
6. **Mirror matches: Opus's inversion rule** — if the two contours
   differ in fewer than 3 of 8 positions, ice's is inverted
   (d → −d mod 5). Kimi's "canon in two studios" reading is honest,
   but the inverted canon is MORE honest to the picture: two imps in
   Core War chase each other; the music should too. Dress + inversion
   together carry the mirror match.
7. **Chord loop: Kimi's voicing formula, curated cadence table.**
   Voicing on root degree k is uniform `{k, k+1, k+3, k+4} mod 5` —
   the guarantee becomes the type of the data structure (every chord a
   4-note pentatonic subset; k=0 at D = v2's Dm7). Cadence orders come
   from a hand-vetted table (union of Opus's 4 and Kimi's 8, dedup,
   re-vet for real root motion; v2's order is entry 0), selected by
   match_hash.
8. **Percussion: Opus's derived Euclidean vocabulary** — E(k,16),
   k from bucketed bombs-per-active-bar, rotation from the fingerprint,
   under the swept structural constraint that ember's pattern always
   contains step 0 and ice's never does (the on-grid/offbeat faction
   contrast survives every input). Kimi kept the v2 steps fixed and
   derived only fills — too timid for a brief titled "rhythm vocabulary
   from behaviour." Kimi's derived fill banks and ghost-density tiers
   ride on top; Opus's ghost classes from median stride merge with
   Kimi's fill selection (both offline, pattern-level, anti-noise-law
   clean).
9. **Extra derived dimensions: take Kimi's bass figures** (3 curated:
   pedal 8ths / root-fifth / octave bounce, per-warrior hash). Cheap,
   vetted, one more channel of per-match identity Opus didn't claim.
10. **Code-derived timbre accent: REJECTED** (Kimi's argument, and
    v2's own EMBER_SWING comment: identity parameters that wobble with
    input are the back door the front door was locked against). Opus
    pre-authorized the deletion ("if this reads as noise, delete it;
    nothing else depends on it"). Notes, never accent.
11. **Winner's finale motif: Kimi's resolution law** — first 4 notes
    of the winner's leitmotif with the last forced to degree 0,
    preserving v2's "resolves home" property in derived space.

## Rejections locked (both agree)

No derived tempo, ever. No per-round or mid-match key change (DNA
frozen at t=0; a match is one song, a catalog is many). No free
chromaticism — the death note is the entire chromatic budget. No
per-instruction rhythm (the anti-noise law governs the code-author
too: code writes pitches and patterns offline, never onset times).
All v2 rejections stand.

## Implementation shape

`engine/dna_cw.py` (pure, no numpy, no I/O): canonicalize/tokenize
(K), integer fold (K), symmetric pair (ruling 4), ROTATIONS ×
12 tonics with octave-1 clamp (O), death-note rule (O), cadence table
+ voicing formula (ruling 7), contour walk + articulation + mirror
inversion (O), bjorklund + faction pattern constraints (O), bass
figures + fill banks + ghost tiers (K/O merged), `DEFAULT` = null DNA
= v2's constants exactly. `record_cw.extract()` sets `tl.warriors`/
`tl.dna` (a few lines). `score_cw`: analyze() derives behaviour inputs
it already computes; render_score's PENT/BB/CHORDS/steps lookups
repoint to `score.dna`. Tests: the union of both consultants' lists —
sixty-key safety sweep, null-DNA==v2 byte-for-byte, same-warriors→
same-theme, different-warriors→different pitch-class histograms
(L1 > 0.4), death-note-only-in-kill-windows, mirror-inversion,
DNA-totality (imp / FOR-ROF / equ-heavy / empty-parse), faction
step-0 contrast sweep, register clamp, and the 30ms anti-noise law
re-run on DNA-rendered output. Existing suite carries via the
fallback; the two repointed tests are one-line changes.

Sequencing: v3 implementation starts only after the v2 chapter is
committed (post Kimi-fix-round + Grok/DeepSeek final review). Both
shipped masters re-render under v3 and are judged as a pair: the kill
match and the three-tie stalemate must sound like two songs from one
show.

## Post-implementation amendments (director, 2026-08-15)

Implemented, Kimi-reviewed (no MUSTs), and shipped with three
corrections to the letter of the rulings, each recorded at its
constant in dna_cw.py:

1. **The mixer, not a salt, is what separates matches.** The shipped
   pair collided on the tonic (both F#, a verified 1-in-12
   coincidence). An additive salt can NEVER break such a collision —
   tonic = hash % 12, and (x+c)%12 preserves differences; swept all
   2^32 values as proof. The fix is a murmur3 avalanche finalizer in
   pair_hash plus per-field re-mixing (FIELD_SALTS): one 32-bit hash
   sliced four ways was four correlated decisions, not four decisions.
2. **"Different tonic" was never the property.** The first
   independent-lanes draw gave C#/D# ritusen — same mode a step apart,
   four shared pitch classes, a closer sibling than the collision.
   The real property, now asserted by regression tests whose
   docstrings record both failed cuts: different tonic AND different
   rotation AND zero shared pitch classes. PAIR_SALT=13 is the
   smallest of 43/256 qualifying values (a common outcome selected by
   sweep, not a tuned one). Changing it re-keys the whole catalog.
3. **Shipped keys**: match-001 = E minor (death note C), match-002 =
   G# major (death note E). Chroma L1: 1.246 between them, 0.774 and
   1.041 against v2/null. Director accepted E minor's shared rotation
   with v2's D minor: the kill match keeping a dark mode is right, and
   the measure says it is a different song.
4. **Ruling amendments in the small**: cadence entry 0 carries v2's
   hand-voicings verbatim (Kimi's voicing formula does not reproduce
   F6/Gsus/A(add4); null-DNA-equals-v2 is the stronger law — the
   formula governs entries 1+). Bass figures are per-match (one shared
   sub bus) and number four including v2's sustain. The bass ROOT
   clamps to octave 1; figures may voice one octave up. Kimi's fill
   banks became derived ghost-step banks, ice only (ember's zero
   ghosts IS the on-grid anchor identity). The DELTA walk is a
   5-cycle: -4 and +1 are the same move, so direction ("a bomb
   falls") is not expressible — magnitude class is the semantic; a
   direction-preserving walk is logged as possible v3.1. Mirror
   inversion targets the lexicographically larger canonical token
   stream (seat-independent — a seat-swapped rematch is the same
   song). The null-DNA law is pinned to a golden sha256 derived from
   the real v2 code at 0fc1724, not v3-vs-v3.
5. **Leitmotif reach**: contours sound only in round verdicts and the
   winner's finale (wiring them into the lead layer would break
   null-DNA byte-identity); logged as the other v3.1 candidate.

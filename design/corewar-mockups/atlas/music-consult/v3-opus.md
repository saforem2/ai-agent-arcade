# CORE DNA — emergent material, conducted performance

*Music consult v3, Opus. Evolving CORE LOOP, not defending it.*

The user's diagnosis is exact and it is not a complaint about v2's method — it
is a complaint about v2's **constants**. match-001 and match-002 sound like
siblings because `PENT`, `CHORDS`, `EMBER_STEPS` and `ICE_STEPS` are module
globals. Nothing in v2's architecture requires them to be. So v3 is one move:

> **Every constant that decides WHAT is played becomes a function of the
> match. Every constant that decides HOW it is played stays welded to the
> catalog. The grid, the law, the arranger and the two studios do not move.**

And the move is cheaper than it sounds, because — this is the load-bearing
observation of the whole proposal — **v2 is already one point in the derived
space, not a special case outside it.**

| v2 constant | v3 reading |
| --- | --- |
| `PENT` = D minor pentatonic | tonic `D`, rotation `minor` — 1 of 60 |
| `EMBER_STEPS` = (0,3,6,10,13) | `E(5,16)` rotated 10 — Bjorklund, verified |
| `ICE_STEPS` = (2,6,10,14) | `E(4,16)` rotated 2 — Bjorklund, verified |
| `BB` = 58.270 | ♭6 of the tonic — the rule, evaluated at D |

That is not a retrofit; I checked it in code. v2 is what the v3 generator emits
for null DNA, which is also the fallback when a warrior fails to assemble.

---

## 1. The safety guarantee

v2's "nothing can land wrong" was never a property of *D minor pentatonic*. It
is a property of the **shape**: the anhemitonic pentatonic is the unique 5-note
necklace with no semitone and no tritone anywhere in it. That property is
invariant under transposition and rotation, so the guarantee survives across
the entire family for free:

**THE FAMILY: 12 tonics × 5 rotations = 60 keys.** Rotations are the five
modes of `{0,2,4,7,9}`: `minor (0,3,5,7,10)`, `major (0,2,4,7,9)`,
`egyptian (0,2,5,7,10)`, `man-gong (0,3,5,8,10)`, `ritusen (0,2,5,7,9)`.

I swept all 60 in a scratch script: **zero violations** — every key has minimum
circular interval ≥ 2, contains no tritone between any pair, and admits a
death note outside itself. The guarantee is not weakened by derivation; it is
now *testable as a theorem* rather than asserted about one hand-picked set.

Register does not float. The tonic is a **pitch class**, and the bass root is
always placed in octave 1 (32.70–61.74 Hz), ice always in its D5–D7-equivalent
band. So a match can be in F# and still sit in exactly the same frequency
window as v2 — key changes, mix does not.

**Chord loop.** Still 8 bars, two per chord, four chords, each a rotation of
the scale set — but *which four degrees* is derived. Four curated cadences in
degree space: `(0,1,2,3)`, `(0,2,3,4)`, `(0,3,1,4)`, `(0,4,2,3)`. All four
give real root motion; none can produce a wrong note because all roots are
scale degrees. v2's `Dm7|F6|Gsus|A(add4)` is cadence `(0,1,2,3)` at D minor.

## 2. Ruling 2's fate — the outside note generalizes exactly

Bb is the ♭6 of D. Generalize it as a rule and check totality:

```
death_pc = (tonic + 8) % 12          # the ♭6
if 8 in rotation_offsets:            # true only for man-gong
    death_pc = (tonic + 1) % 12      # the ♭2
```

`+1` is absent from all five rotations, so the fallback is guaranteed to
resolve. Swept over all 60 keys: the death note is outside the scale every
time. It stays the **only** note outside the scale in the whole piece, still
spent only on the elimination drop and the win finale, still the reason a
kill cannot be mistaken for anything else.

Man-gong is not a hardship case — it is the darkest rotation, it already owns
the ♭6 colour as a scale tone, and its ♭2 is the correct death note *for that
mode*. In the real data this fires: match-002 lands on F# man-gong, death
note **G**, a semitone above the tonic. That drop is going to be nastier than
v2's, which is right for a match with no kill in it.

## 3. FIXED vs DERIVED

**FIXED FOREVER — the series' identity.** Tempo 135 BPM, 4/4, one tempo and
one key per match, origin t=0. 1/16 quantization. The 30 ms anti-noise law
(battle selects slots, never places onsets) and its single exception, the
hitstop. The pentatonic *shape* and the one-outside-note law. The two
production identities entire — ember's saturation/bitcrush/slapback, +8 ms
drag, 56 % swing, low register, pan −0.25; ice's dry synthesis into reverb,
zero drive, machine quantization, high register, pan +0.25. The eight-layer
cast, tier thresholds `0.18/0.34/0.52/0.70`, the 2-up/4-down hysteresis, the
intensity weights. The drop grammar: riser → absolute silence → outside-note
sub impact → 8-bar payoff with the loser cut; tie drop = same shape, no
silence, no outside note. Load-in anacrusis. Draw = converging drone that
never reaches zero; win = ends on a downbeat. Mix law, limiter, mix budget.
Bass root in octave 1.

**DERIVED PER MATCH — the song.** Tonic pitch class (12) and rotation (5),
from the symmetric pair fingerprint. Cadence (4). The death note (a function
of the two above). Per faction: an 8-degree leitmotif contour and its
articulation string, from that warrior's assembled instructions. Per faction:
the percussion pattern `E(k,16)` rotated, `k` from behaviour and the rotation
from code. Per faction: the ghost/subdivision class from median stride. Per
faction: one bounded timbre accent inside its own dress.

**What a listener recognizes.** The series, from tempo, the two dresses, the
drop grammar and the mix. The song, from key, contour and pattern. Those are
different perceptual channels, which is why both can be true at once.

## 4. Faction identity vs warrior identity

**Production dress stays 100 % faction-fixed.** Legibility with eyes closed is
carried by timbre, register, processing and pan, and every one of those must
be constant across the catalog or the catalog stops being one thing. A
warrior's theme lives *inside* its faction's dress: ember plays its contour on
ember's saturated supersaws in ember's octave, ice plays its contour on ice's
FM bells in ice's octave. Code-derived timbre does **not** creep in.

One concession, tightly bounded: DNA moves exactly one continuous parameter
per studio, inside a range that cannot reach the other faction's territory —
ember's drive `k ∈ [1.4, 2.2]`, ice's FM ratio `∈ [2.7, 3.6]`. The warrior
chooses its accent; it never chooses its language. If in the mockup pass this
reads as noise rather than character, delete it: nothing else depends on it.

## 5. The mapping, concretely

**Fingerprint.** The house sin-hash over assembled instructions — never
Python's `hash()`, which is salted per process and would silently break
determinism across renders:

```
code_i = OPCODES.index(op)*7 + MODIFIERS.index(mod)*3
       + MODES.index(a_mode)*11 + MODES.index(b_mode)*13
       + (a_val % 97) + (b_val % 89)*2
fp(w)  = frac( Σ_i frac(sin((code_i + 0.618*i) * 12.9898) * 43758.5453) )
pair   = frac(fp(A) + fp(B))            # symmetric: seat swap = same song
tonic  = int(pair*12);  rot = int(frac(pair*7.13)*5);  cad = int(frac(pair*3.77)*4)
```

**Contour.** Walk 8 instructions from `warrior.start`, cycling if shorter.
Each opcode is a signed move in degree space, accumulated mod 5:

```
MOV +1  ADD +2  SUB −2  MUL +3  DIV −3  MOD −1  JMP  0  JMZ −1
JMN +1  DJN −2  SPL +4  SEQ  0  SNE +1  SLT −1  NOP  0  DAT −4
```

`SPL +4` and `DAT −4` are the two largest moves on purpose: a fork is the
biggest thing a warrior does and a bomb is the most terminal, so replication
leaps and death falls. The A-operand mode picks articulation per note:
`#` staccato pluck, `$` normal, `@ * ` long, `< > }` `{` with a 1/16 grace.
Rhythm of the motif stays `MOTIF_STEPS` — grid-owned, as ever.

**Percussion.** `k` from the median bombs-per-active-bar, bucketed so a
rematch lands in the same bucket: `<8→3, 8–32→4, 32–128→5, 128–512→6, ≥512→7`.
Rotation from `fp`, constrained so **ember's pattern always contains step 0**
(rotation drawn from `{−x mod 16 : x ∈ E(k,16)}`) and **ice's never does**
(rotate, and bump +1 while 0 is present; a Euclidean set with k ≤ 7 has no two
adjacent onsets, so one bump always escapes — swept, zero failures). The
on-grid-anchor / offbeat contrast that makes ember and ice legible therefore
survives every possible input. Ghost class from median stride:
`1→32nd roll, 2–8→open hat, 9–500→chop, >500→sparse tick`.

**The two shipped masters, computed for real** (fingerprints and patterns from
the actual `.red` files; densities and strides from an actual `analyze()` run
on both timelines):

| | match-001 | match-002 |
| --- | --- | --- |
| warriors | Twin Ember vs Blue Fugue | Iron Lotus Gate vs Blue Shift |
| key | **C# ritusen** `C# D# F# G# A#` | **F# man-gong** `F# A B D E` |
| death note | A (♭6) | G (♭2 — fallback fires) |
| cadence | degrees (0,2,3,4) | degrees (0,4,2,3) |
| ember contour | (4,3,4,1,1,2,4,4) | (4,3,4,1,1,2,3,4) |
| ice contour | (4,3,4,3,4,3,4,0) | (4,0,1,2,1,2,3,4) |
| ember rhythm | 124 bombs/bar → E(5,16), stride 734 → tick | 80 → E(5,16), stride 1184 → tick |
| ice rhythm | 64 → E(5,16), stride 272 → chop | **858 → E(7,16)**, stride 1 → 32nd roll |

Two different keys, two different modes, two different death notes, four
different contours. match-002's ice is Blue Shift's imp carpet turned into a
dense seven-onset pattern under a 32nd roll; match-001's ice is a sparser
five-onset chop. They will not sound like siblings.

## 6. Degenerate inputs — the mapping is total

- **A 3-line imp.** Contour cycles the source, so `MOV +1` eight times gives
  `(1,2,3,4,0,1,2,3)` — a rising scale. An imp *is* a rising scale; the
  degenerate case is the most on-the-nose result in the system.
- **A 100-line monster.** The contour reads only 8 instructions from `start`,
  so length can never overflow it; length reaches the music through the
  fingerprint (which sums over all instructions) and through behaviour.
  Verified on Blue Shift, which assembles to exactly 100.
- **Two copies of the same warrior.** Identical DNA, so identical contours.
  The **mirror rule**: if the two contours differ in fewer than 3 of 8
  positions, ice's is inverted (`d → −d mod 5`). Ran it on imp-vs-imp: ember
  `(1,2,3,4,0,1,2,3)` ascending, ice `(4,3,2,1,0,4,3,2)` descending — two imps
  chasing each other in opposite directions, still inside one scale, so no
  collision is possible. Legibility is otherwise carried entirely by the
  dresses, which is precisely why §4 refuses to let DNA touch them.
- **An ugly rotation.** Cannot exist. All 60 keys are the same interval shape;
  there is no bad member to land on. The only real risk was register drift,
  and the octave-1 clamp removes it.
- **A warrior that does not assemble.** `read_warriors()` already returns
  `None` tolerantly. Null DNA → the v2 constants. The worst case in the whole
  system is the record we already shipped and the user already liked.

## 7. Implementation delta

**New: `engine/dna_cw.py`** (~180 lines, pure, no numpy, no I/O).
`ROTATIONS`, `CADENCES`, `DELTA`; `frac`/`h` sin-hash; `bjorklund(k, n)`;
`fingerprint(w)`; `contour(w)`; `warrior_dna(w) -> WarriorDNA`;
`match_dna(wa, wb) -> MatchDNA` (tonic, rotation, scale freqs, chords, death
note, two `VoiceDNA`); `MatchDNA.with_behaviour(density, stride)` returning the
frozen percussion patterns. `DEFAULT = match_dna(None, None)` reproduces v2's
constants exactly, and a test asserts that byte-for-byte.

**`record_cw.py`: four lines.** `extract()` calls the existing
`X.read_warriors()` and sets `tl.warriors = (wa, wb)`. Nothing else moves —
`Mix`, `gate`, `master`, frames, mux, `synthesize` all untouched.

**`score_cw.py`: parameterization, not rewriting.**
- `PENT`, `BB`, `CHORDS`, `EMBER_STEPS`, `ICE_STEPS`, `ICE_GHOSTS` stop being
  the source of truth and become `dna_cw.DEFAULT`'s values.
- `analyze(tl, grid=None, dna=None)` gains one parameter. After the existing
  per-step vote pass (which already computes exactly the density and stride
  the patterns need), it calls `with_behaviour()` and stores `sc.dna`,
  `sc.pent`, `sc.chords`, `sc.death`, `sc.steps[w]`, `sc.ghosts`. The sections
  / tier / hysteresis / cue code is **not touched**.
- `Score.pattern_offsets()` reads `self.steps` instead of the globals — which
  means the anti-noise test keeps working unchanged, because the patterns are
  still fixed for the whole match.
- `render_score()`: every `PENT[...]` becomes `score.pent[degree]`, every `BB`
  becomes `score.death`, the `CHORDS[(b//2)%4]` lookup becomes
  `score.chords[...]`. `_motif()` reads `score.dna.voice[w].contour` and
  articulation instead of the hard-coded `A→C→D→D`. `_draw_outro()` glides
  toward `score.pent[0]` instead of `PENT['D']`.
- **Untouched entirely:** `Grid`, `step_time`, every DSP primitive, `Buses`,
  the sidechain, `reverb`, `_cut_losers`, `_lay_impacts`, `_pan_into`,
  `SECTION_GAIN`, `TIER_THRESHOLDS`, `_kick_colour`.

**Tests that break: two, both one-line repoints.**
`test_bombs_vote_they_never_hit` reads `S.EMBER_STEPS | S.ICE_STEPS |
S.ICE_GHOSTS` → `score.steps[0] | score.steps[1] | score.ghosts`.
`test_only_a_kill_spends_the_outside_note` reads `S.BB` → `score.death`.
Everything else carries: the 30 ms law, per-layer scheduling, grid alignment,
hitstop, tie-vs-kill, riser, loser-cut, draw, win, sections, tiers, mix law,
determinism, duration, kick colour, and all of `test_record_cw.py`.

**New tests to pin.**
1. `test_the_guarantee_holds_for_all_sixty_keys` — for every (tonic, rotation):
   min circular interval ≥ 2, no tritone in any pair, death note ∉ scale.
   This is v2's safety property upgraded from an assertion to a proof.
2. `test_the_same_warriors_give_the_same_theme` — `match_dna` twice, and a
   rematch archive with the same two `.red` files, produce identical DNA.
3. `test_different_warriors_give_different_songs` — match-001 vs match-002:
   tonic differs, and the L1 distance between the pitch-class histograms of
   `score.scheduled` tonal onsets exceeds 0.4.
4. `test_null_dna_reproduces_v2` — `DEFAULT` equals the old module constants.
5. `test_euclid_keeps_the_faction_contrast` — over k ∈ 3..7 × 16 rotations:
   ember always contains step 0, ice never does.
6. `test_degenerate_warriors_still_produce_a_theme` — a 1-instruction imp and
   a 100-instruction warrior both yield an 8-degree contour and k ∈ 3..7.
7. `test_identical_warriors_are_still_told_apart` — imp vs imp: contours
   differ after the mirror rule.
8. `test_the_key_never_leaves_its_register` — every tonic's bass root lands in
   [32.70, 61.74) Hz.

## 8. What I am still not taking

Everything rejected in v2 stays rejected — no vocal collage, no sampled
pathos, no brat-wall loudness, no Eno aleatorics, no tempo or key change
mid-match. Three additions specific to v3:

- **No per-round or per-section key change.** The DNA is fixed at t=0. A match
  is one song; a *catalog* is many.
- **No free chromaticism, ever, including "just for the drop."** The death
  note is the entire chromatic budget and it is one note.
- **No derived tempo.** BPM is the strongest brand signal the series has, and
  135 was derived from the pacing constants, not chosen. Deriving it per match
  would break the one thing that makes two broadcasts recognizably the same
  show, and it would break `ROUND_TARGET_S` landing on 29.8 bars for free.

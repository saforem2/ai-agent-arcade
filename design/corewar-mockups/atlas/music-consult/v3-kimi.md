**Proposal: Core War Broadcast Master — v3 "DNA" System**
*Kimi, second consult. Emergent material, conducted performance.*

---

### 0. The one-line design

v2's mistake was not the grid — it was that the grid had only one song in it. v3 keeps every performance law of v2 untouched and replaces exactly one layer: the **material** (scale, chord order, motifs, bass figure, pattern vocabulary) is computed from the two `.red` files by a pure function, before `analyze()` runs. The battle still never places a sound. The code still never places a sound. The code *writes the theme*; the grid *performs* it; the battle *conducts* it. Three authors, three jobs, and the anti-noise law governs all of them.

---

### 1. The safety guarantee — what replaces one-pentatonic-set

First, name what v2's guarantee actually was, mechanically: every note in the piece came from an **anhemitonic pentatonic set** — five pitch classes, no semitone, no tritone, every subset a consonant chord, every rotation a usable mode. "Nothing can land wrong" was never "everything is D minor." It was "everything is anhemitonic."

v3 keeps the *set-shaped* guarantee and derives the *set's identity*:

- **The match still has exactly one pentatonic set.** Both factions draw from the same five pitch classes, so any ember note against any ice note is consonant — cross-faction collisions remain impossible by construction, exactly as v2.
- **What varies per match is curated, not free:** the tonic (5 candidates), the chord-loop root order (8 hand-vetted orders), each faction's motif contour (pentatonic degrees, interval-clamped), the bass figure (3 figures), the perc fill bank (4 patterns). Every choice is `hash → index into a small table I have listened to`. Free chromaticism never enters the pipeline because there is no code path that can produce a pitch outside `pentatonic(tonic)` plus the one death note.
- **Concrete tables.** Tonic candidates, octave 1, all inside the laptop-safe sub band: `TONICS = (32.703, 36.708, 41.203, 48.999, 55.000)` (C1, D1, E1, G1, A1 — fifths apart, so the catalog's five keys feel like one family, not twelve). `idx = match_hash % 5`. The pentatonic is then `tonic * (1, 2^(3/12), 2^(5/12), 2^(7/12), 2^(10/12))`. Sanity: idx 1 gives D1 = 36.708 and the set {36.708, 43.654, 48.999, 55.000, 65.406} — *v2's PENT table exactly*. v2 is the `idx==1` degenerate case of v3, which is how the tests below get their backward-compat anchor.
- Chord voicing on root degree `k` is uniform: degrees `{k, (k+1)%5, (k+3)%5, (k+4)%5}`. At `k=0` on D that is `{D,F,A,C}` = v2's Dm7. Every chord so built is a four-note subset of the pentatonic — the guarantee is not a claim, it is the type of the data structure.

The guarantee, restated: **the worst v3 match is a boring pentatonic song, never a wrong one.**

---

### 2. Ruling 2's fate — the generalized death note

v2's Bb is, in semitones from the D tonic, **+8**: the minor sixth, a semitone above the fifth degree (A), the single most abrasive pitch class available against this pentatonic. That is the law under the law: *the death note is the pitch class one semitone above the pentatonic's fifth degree.*

Generalized: `death_freq = tonic * 2^(8/12) = tonic * 1.5874`. For D1: 36.708 × 1.5874 = 58.27 — Bb1, v2's exact value, recovered as the degenerate case. For C1: 51.9 (Ab1). For A1: 87.3 (F2).

Everything else about Ruling 2 survives verbatim: exactly **one** outside note in the whole piece, spent only on the kill drop (`_lay_impacts`) and the win finale, never on a tie, never on anything smaller. The two-bar Bb-hold recolor in the drop (`root = BB; tones = (BB, D, F)`) becomes `root = death; tones = (death, pent[0], pent[1])` — a tritone-free minor triad built on the outside note, so the recolor is a *shadow of the home scale*, not a foreign key. The kill/tie distinction (`test_only_a_kill_spends_the_outside_note`) carries over with the constant swapped for the derived value.

---

### 3. Catalog coherence — the FIXED/DERIVED table

| Element | Status | v3 rule |
|---|---|---|
| Grid: 135 BPM, 4/4, 1/16 quantization | **FIXED** | Derived from round pacing in v2; now it is also the brand pulse. Never moves. |
| Anti-noise law (30 ms), `step_time()` as the only clock, `score.note()` as the only ledger | **FIXED** | Untouched. |
| Phrase-block grammar (Intro/Groove/Riser/Drop/Breakdown), hysteresis 2-up/4-down, tie-drop-in-second-half rule | **FIXED** | Untouched. |
| Hitstop law: silence sample-synced to the freeze, never quantized | **FIXED** | Untouched. |
| Production identities: ember = saturated/swung 56%/dragged +8 ms/D1–A4; ice = dry/machine-quantized/D5–D7 | **FIXED** | This is the series' two-studio brand. See §4. |
| Instrument recipes (808 kick, supersaw, fm_bell 3.14, hats 8.0/8.234 kHz, clap, bell pad, Shepard riser) | **FIXED** | Kimi's v2 numbers ship unchanged. |
| Mix law, limiter, section gains, kick-colour-by-territory formulas | **FIXED** | Untouched. |
| Draw outro = dissolve, win = stops on a downbeat | **FIXED** | Untouched. |
| Match tonic (5 candidates) | **DERIVED** | `match_hash % 5` |
| Chord-loop root order (8 curated orders of 4 roots; v2's D→F→G→A = order 0) | **DERIVED** | `(match_hash >> 3) % 8` |
| Each faction's leitmotif contour (4–8 pentatonic degrees + octave flags) | **DERIVED** | per-warrior hash, §5 |
| Bass figure (pedal 8ths / root-fifth / octave bounce) | **DERIVED** | `(warrior_hash >> 5) % 3` |
| Perc fill pattern per faction (4 curated 16-slot banks) | **DERIVED** | dominant stride `mod 4`, computed offline per match |
| Ghost-note density tier | **DERIVED** | fork (`spl`) rate bucketed offline, pattern-level only |
| Winner's motif = first 4 notes of the winner's leitmotif, last note forced to degree 0 | **DERIVED** | preserves v2's "resolves home" law (A→C→D→D was degrees 3,4,0,0) |

Read the table as the answer to "siblings": everything the user heard as *same* (tempo, studios, grammar) stays; everything that makes a song *a song* (key, chord motion, themes, bass walk) is now the match's own.

---

### 4. Faction identity vs. warrior identity

**The theme is the warrior's; the studio is the faction's. No timbre creep.**

A warrior's leitmotif, bass figure, and fill pattern always play in its faction's dress: ember themes are always dragged, swung, saturated, low; ice themes are always dry, quantized, glassy, high. The register law (`tones[deg] * 8` ember, `* 32` ice, as in the v2 lead) does not move. Faction legibility — eyes-closed "who is winning" — rests on dress and on the shared-kick colour formulas, both untouched, so it survives by construction.

I considered and rejected one code-derived timbre parameter per faction (e.g. hash-tinted supersaw detune, hash-tinted FM ratio). Rejected on the same grounds as v2's rejected swing-scaling, which the code comment at `EMBER_SWING` already argues: identity parameters that wobble with input are the back door the front door was locked against. Two warriors in one faction must be distinguishable by *melody*, and they will be — a listener who knows both themes hears which warrior is fighting, in the same way you recognize a song in a cover version. What the code changes is the **notes**, never the **accent**.

The same-warrior mirror match (§5) is the proof this split is load-bearing: when the themes are identical, dress alone must carry the difference — and v2 already proved dress alone is legible.

---

### 5. The DNA mapping — total, with the worst cases walked through

**Extraction.** `extract()` already opens `match_dir/warriors/A.red` and `B.red` (it validates their existence). v3 canonicalizes each source — strip `;` comments, drop `;redcode`/`;name`/`;author`/`;strategy` headers, expand `FOR/ROF` (as Blue Shift uses), substitute `equ` constants, lowercase, split to a token stream of `(opcode.modifier, amode, a, bmode, b)` tuples per instruction — then folds it with pure-integer DJB2:

```
h = 5381
for i, tok in enumerate(tokens):
    v = 0
    for c in str(tok): v = (v * 33 + ord(c)) & 0xFFFFFFFF
    h = ((h * 33) ^ v ^ (i + 1)) & 0xFFFFFFFF
```

No floats, no RNG, platform-identical. `match_hash = (hA * 0x9E3779B1 + rotl(hB, 16)) & 0xFFFFFFFF` — deliberately **not** `hA ^ hB`, so a mirror match cannot degenerate to a constant.

**Motif.** Read the code as a melody line, top to bottom. For instruction `i`: degree `= (opcode_class + |b_operand|) % 5` over the 8 opcode classes (dat, mov, add/sub, mul/div/mod, jmp/jmz/jmn, djn, spl, cmp/seq/sne), octave flag from addressing mode (`#` = +1, `@`/`<`/`>` = 0, `$` = −1, clamped to ±1 octave from base). Motif length `L = 4 + min(4, n_instructions // 16)` — 4 to 8 notes. Consecutive-identical degrees are kept (repetition is motif, not failure). The motif's *rhythm* is always fixed slots `(0, 2, 4, 8, ...)` — code writes pitches, never times.

**Degenerate case 1 — the 3-line imp.** `mov.i $0, $1` three ways gives a 4-note motif at floor length. A tiny warrior produces a tiny theme: an imp *sounds* like four notes. The mapping is total because the tokenizer accepts any instruction stream of length ≥ 1; a source that parses to zero instructions (should never happen — `extract()` would have failed earlier) falls back to motif degrees `(0, 2, 4, 0)`, the plainest possible cell.

**Degenerate case 2 — the 100-line p-space monster.** Length caps at 8 notes; the degree stream is read from the first 8 instructions after `org`, so size past ~48 instructions affects only the hash (tonic/loop/fill selection), not motif sprawl. A monster sounds *dense*, not *long*: its density shows up where density belongs — in the perc voting and pressure curves that v2 already derives from behaviour.

**Degenerate case 3 — the mirror match.** `hA == hB` → identical motifs, identical bass figure, and `match_hash` still lands on a well-defined tonic (no XOR collapse). The piece becomes a canon in two studios: the same four-to-eight notes, ember dragged and dirty against ice dry and exact. That is not a degenerate output; it is the most legible possible broadcast of "these are the same program." The theme says *what*, the dress says *who* — and here the theme honestly says "the same."

**Degenerate case 4 — the ugly rotation.** Structurally impossible, and this is the point of the curated tables. Every tonic is anhemitonic-pentatonic-safe; all 8 loop orders were chosen for real root motion (no order starts on degree 4 or repeats a root across the 2-bar halves); every motif lands inside a set whose largest step is a minor third, with octave jumps clamped to ±1. The hash can choose *which* vetted object, never *whether* the object is vetted. The worst theme the system can emit is a plain one.

**Judged against the shipped masters.** match-001 (Twin Ember vs Blue Fugue, a kill): Twin Ember's stone-add constants 2367/1271 and Blue Fugue's silk steps 1801/3741/−1921/1871 produce different hashes → different loop order for the match and two genuinely different motifs; the kill still spends the (derived) death note exactly once. match-002 (Iron Lotus Gate vs Blue Shift, three ties): three tie drops, no silence, no death note, draw outro dissolving both themes into the shared drone at the match's derived tonic instead of D — the Eno ending survives with the match's own note as home.

---

### 6. Implementation delta

**New module `engine/dna_cw.py`** (~120 lines, no numpy): `canonicalize(red_text) -> tokens`, `warrior_dna(tokens) -> DNA` (hash, motif degrees, octave flags, bass-figure index), `match_harmony(dnaA, dnaB) -> Harmony` (tonic, pentatonic 5-list, death-note freq, chord loop as root-degree + tone-degree tuples, fill-bank indices). `Harmony` is shaped exactly like v2's `PENT`/`CHORDS`/`BB` constants so the renderer's diff is mechanical.

**`record_cw.py`:** two lines. `extract()` reads the two `.red` files it already validates and sets `tl.dna = match_harmony(...)`. Everything else — `VirtualClock`, `FrameSink`, `Mix`, `gate`, `master`, `mux`, frame plumbing — untouched, as mandated.

**`score_cw.py`:**
- `analyze(tl, grid=None)` — signature unchanged. It reads `getattr(tl, 'dna', None)`; if absent it builds `Harmony` from the v2 constants (D tonic, loop order 0, A→C→D→D motifs). This fallback is the backward-compatibility seam.
- `Score` gains one field, `harmony`.
- `render_score()` — the constant lookups `PENT[...]`, `CHORDS[...]`, `BB` (lines ~789–846, 990–991, 1009, 1136, 1175, 1211, 1251) become `score.harmony` lookups. `step_time()`, `Grid`, every DSP primitive, the sidechain, the reverb, `_cut_losers`, `_lay_moments`, `_lay_impacts`, `_draw_outro` — structurally untouched; only their pitch arguments change source.
- `_motif()` takes the faction's derived 4-note line (last note pinned to degree 0) instead of the hardcoded A→C→D→D.
- The perc layer's fixed `EMBER_STEPS`/`ICE_STEPS` stay; the *fill* voice selection consults the harmony's fill-bank index.

**Tests.** Carried over unchanged, because of the fallback: every existing test constructs timelines without `.dna`, so all 27 `test_score_cw.py` tests — grid arithmetic, 30 ms law, on-grid onsets, hitstop absoluteness, tie-vs-kill, quiet-room mix, determinism, duration exactness, kick colouring — must pass byte-for-byte against v2 renderings. That is itself the first v3 test: *no-DNA output == v2 output, exactly.*

New tests to pin:
- `test_same_warrior_same_dna`: parse one `.red` twice → identical DNA, byte-identical WAV fragment.
- `test_different_warriors_different_pitch_classes`: render the two shipped matches; the histogram of scheduled note pitch-classes (readable straight off `score.scheduled` + `harmony`, no FFT needed) differs between matches and between factions' motifs.
- `test_only_death_note_leaves_the_set`: every scheduled tonal frequency is in `pentatonic × 2^k` ∪ `{death × 2^k}`; death appears only inside kill-drop and win-finale windows.
- `test_mirror_match_is_a_canon`: same `.red` as A and B → motifs equal, harmonies equal, both dresses present.
- `test_dna_is_total`: one-instruction imp, FOR/ROF source, `equ`-heavy source, and the empty-parse fallback all produce valid, in-range DNA.
- The 30 ms anti-noise law re-run on a DNA-rendered match — the new material must not smuggle timing back in.

---

### 7. What I am deliberately not doing

No code-derived tempo (135 is derived from the broadcast's own pacing constants and is now the brand). No code-derived timbre (§4). No per-instruction rhythm (the anti-noise law's whole point). No free scale generation — curation tables, hash as index, never hash as pitch. And no touching `record_cw.py`'s plumbing, which v2's post-mortem already certified as the part that was right.

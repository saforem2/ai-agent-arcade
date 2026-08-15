# CORE LOOP — a track system for the Core War broadcast master

*Music consult, Opus. Proposal for replacing v1's synthesis brain.*

The v1 diagnosis is right and it has exactly one cause: **v1 has no clock of
its own.** It borrowed the battle's clock, and the battle's clock ticks 237
times a second. Nothing with 237 onsets per second is music; it is weather.

So the fix is one structural move, and everything below is its consequence:

> **The track owns a fixed grid. The battle never places a sound in time —
> it only decides which of the grid's already-existing slots are allowed to
> fire, how hard, in whose timbre, and through which filter.**

The battle stops being a drummer and becomes a mixing engineer with one hand
on the faders and one on the arrangement. That is what "conducts rather than
plays" has to mean mechanically, and it is testable: if you can move an event
by 30 ms and hear a different rhythm, you are still sonifying.

---

## 1. The track system

### 1.1 The grid

**135 BPM, 4/4, one tempo for the entire match, origin at t = 0.** No tempo
changes, no key changes, no per-round resets. Three rounds are three sections
of one track.

| unit | seconds |
| --- | --- |
| 1/32 | 0.0555556 |
| 1/16 | 0.1111111 |
| beat (1/4) | 0.4444444 |
| bar | 1.7777778 |
| 4-bar phrase | 7.1111 |
| 8-bar phrase | 14.2222 |

Why 135: it is unambiguously techno (peak-time hard-groove sits 132–138), and
it lands the arrangement on the pacing constants already in `tui_corewar.py`
almost for free. `ROUND_TARGET_S` 50 + `LOADIN_S` 1.5 + `VERDICT_S` 1.4 =
52.9 s ≈ **29.8 bars**, i.e. a full tie round is a 30-bar section without
anyone tuning anything. A 163 s match is ~91.7 bars. Half-time sections
(the intro, the breakdowns, the outro) use the same grid at a 67.5 BPM feel —
never a second tempo, just a kick on 1 and 3.

### 1.2 The harmony — how you get a *song* out of a pentatonic guarantee

v1's best law is "D minor pentatonic, so nothing can ever land wrong". Keep
it, absolutely — and then notice that the pentatonic set has four rotations
that are each a usable chord. An 8-bar loop, running continuously under the
whole match:

```
| Dm7   | Dm7   | F6    | F6    | Gsus  | Gsus  | A(add4) | A(add4) |
  D F A C       F A C D        G C D F        A C D
```

Every chord is a subset of {D, F, G, A, C}. The bass root moves D → F → G → A:
a real progression, real harmonic motion, and *still* no note in the piece can
collide with any other. Roots: D1 36.708, F1 43.654, G1 48.999, A1 55.000.

**One note in the whole system is outside the scale: Bb (58.270 / 116.54).**
It is reserved for exactly two moments — the elimination drop and the win
finale. The outside note is the death note. It is the only harmonic surprise
the track has, so it must never be spent on anything smaller.

### 1.3 The cast (fixed layers, 8 of them)

| layer | owner | enters at tier |
| --- | --- | --- |
| `bed` — drone + room tone | shared | always |
| `pad` — the 8-bar chord loop | faction-split | always |
| `sub` — root, sidechained | shared, faction-coloured | 1 |
| `kick` | shared, faction-coloured | 1 |
| `perc` — hats/ghosts from bomb strides | faction-split | 2 |
| `backbeat` — clap/snare from deaths | faction-split | 2 |
| `vox` — formant chops | faction-split | 3 |
| `lead` — acid / bell pluck | faction-split | 4 |

Plus non-tiered `fx`: risers, reverse swells, impacts, delay throws.

### 1.4 Section map

Sections are cued by timeline events, snapped to a bar line, never shorter
than 2 bars. The arranger runs offline over the **whole** timeline first, so
builds can anticipate — that is the single largest advantage this render has
over a live one, and section 4 spends it.

Per round (bar counts are the tie-round budget; the arranger scales them):

```
INTRO      1 bar    load-in. beatless, half-time sub pulse, LPF 200 Hz
BUILD      4 bars   kick in on the downbeat; perc joins at bar 3
GROOVE A   8 bars   tier-driven; the body of the round
LIFT       4 bars   filter opens, vox in, sub high-passes gradually
GROOVE B   6 bars   full tier, faction dominance decides the character
DROP       4 bars   kill → the elimination drop; tie → the peak drop (§4.2)
BREAKDOWN  3 bars   verdict. drums out, chord holds
```

For a kill round (shorter), minimums are INTRO 1 / BUILD 2 / GROOVE 4 /
RISER 2 = 9 bars = 16 s, and the arranger drops GROOVE B first, then GROOVE A,
then BUILD. A round under 9 bars degrades to INTRO → RISER → DROP. For a long
stalemate the arranger inserts extra GROOVE/LIFT pairs of 8+4 bars and moves
the tier ceiling, so a 90 s round is four breathing cycles, not one flat one.

Between rounds: `round-cut` is a **hard cut on the bar** — everything except
`bed` stops for one bar, with a single filtered noise hit on the downbeat.
Three rounds do not sound like three loops of the same thing because the tier
ceiling and the faction dominance are different each time.

### 1.5 Event → music mapping

Every event kind `beat()` emits, and what it does now. Note the column that
matters most: **nothing in this table places an onset at the event's own
time except the elimination.**

| event | musical role | quantized to | notes |
| --- | --- | --- | --- |
| `load-in` | the intro; per-side arp + riser landing on the next downbeat | 1/16, lands on bar | §4.1 |
| `round-cut` | hard section cut; tier resets to 0 | 1 bar | one noise hit |
| `bomb` | **votes for a perc step** — never a hit | 1/16 bucket | §1.6 |
| `spl` | votes for ghost 16ths; bar's spl count sets ember swing depth | 1/16 bucket | dense, so ghosts only |
| `death` | **votes for the backbeat** (steps 4 and 12) | 1/16 bucket | deaths *are* the clap |
| `first-blood` | crash + permanent +1 tier for the round | 1/8 | ≤0.11 s shift |
| `bloom` | 1-bar reverse swell into the next downbeat + pad gains a harmony note + one vox stab | next bar line | multiple blooms in a bar collapse to one |
| `wrap` | 1/16 delay throw on the lead, if the lead is playing; else nothing | 1/16 | may be dropped entirely |
| `elimination` | **not quantized** — silence at exact t, payload at exact t+hitstop, grid re-locks on the next 1/16 | none | §4.2 |
| `verdict` tie | breakdown: drums out, rootless Gsus pad swell, no resolution | 1 bar | keeps v1's "nobody won" |
| `verdict` kill | winner's motif over their own production, drums half-time | 1 bar | |
| `match-end` win | finale, max tier, ends **on** a downbeat with a tonic hit | drums stop on the last downbeat before t | §4.3 |
| `match-end` draw | Eno outro, beatless | same | §4.3 |

### 1.6 Bomb strides become percussion — the mechanism

This is the part v1 was closest to getting right and furthest from music. A
stone at stride 4 and an imp carpet *are* rhythmically distinct, but not at
237 bombs/second: in time they are a pitch, not a pattern. The stride has to
be read as a **choice of voice**, and the grid supplies the pattern.

Per 1/16 step, per faction, the arranger computes from the bombs in that step:

- `n` — count
- `d` — median first difference of the sorted addresses (the stride)
- `spread` — distinct `addr // 100` rows touched

Then:

```
stride class      voice
d == 1            32nd closed-hat roll  (imp carpet)
2 <= d <= 8       open hat + rim        (dwarf / stone)
d > 500           sparse metallic tick, panned by addr % 100   (silk / scanner)
otherwise         short noise chop
```

And the step only sounds if it is **ON in that faction's fixed pattern**:

```
EMBER (tresillo, on-grid, dragged):   x . . x . . x . . . x . . x . .   (0,3,6,10,13)
ICE   (offbeat, garage):              . . x . . . x . . . x . . . x .   (2,6,10,14)
                                       ghosts at 7, 15
```

Velocity `= clip(log2(1+n)/6, 0, 1)`, floor 0.25. The patterns never change
for the whole match. The battle decides which of those ten slots fire this
bar and how hard, and which voice sits in them. That is a groove that
*reports* a bombing run instead of transcribing it.

---

## 2. The two faction production identities

Not two timbres — two **records**. Same kick, same grid, different studio.

### EMBER (KIMI) — analogue, dirty, low, behind the beat

- **Bass**: `saw_stack(root, harmonics=12, detune=7.0)` through a resonant
  low-pass, cutoff automated (§3), resonance 0.7, then `tanh(2.2*x)`.
- **Pad**: two detuned saw stacks a 4th apart, register D1–A3, per-harmonic
  gain rolled off above 2 kHz, amplitude grit from the existing `hashnoise`.
- **Perc**: 909-ish. Hat = `hashnoise` high-passed at 6 kHz, 35 ms decay.
  Clap = four noise bursts at 0/9/17/26 ms band-passed 900–2400 Hz, 140 ms
  tail, `tanh(1.8*x)`.
- **Lead (tier 4)**: acid. `saw_stack(f, harmonics=12)` through a ladder
  low-pass with a per-note cutoff envelope 400 → 2800 Hz over 120 ms,
  resonance 0.82, then `tanh(2.6*x)`. Note degrees from the battle:
  `deg = (addr // d) % 5` over the pentatonic — the stride literally writes
  the melody.
- **Character processing**: saturation, 10-bit quantize (bitcrush-lite),
  12 ms slapback at 0.25 feedback. Percussion is **dragged +8 ms** and swung
  56 % (swing depth scaled by the bar's `spl` count).
- **Register**: D1–D3 bass, D3–A4 lead. **Pan** −0.25, low end wider.

### ICE (CODEX) — digital, glassy, high, exactly on the grid

- **Bass**: pure sine sub, no drive, no detune. Where ember has grit, ice has
  nothing — the absence is the identity.
- **Pad**: the existing `bell()` inharmonic partials at D5/A5/D6, plus a
  shimmer send (octave-up feedback delay at 0.28).
- **Perc**: FM metallic. Six partials at ratios (1, 1.41, 1.68, 2.0, 2.51,
  2.66) × 800 Hz, high-passed 5 kHz, 28 ms decay. Snare = white noise HP
  1.5 kHz + a 190 Hz body, 80 ms, straight into the reverb send.
- **Lead (tier 4)**: bell pluck with a tempo-synced 3/16 delay (0.3333 s) at
  0.42 feedback. Degrees `deg = int(abs(sin(addr*12.9898))*5) % 5` — the
  house sin-hash, so determinism is free.
- **Character processing**: reverb and delay, **zero saturation, zero swing,
  zero drag**. Perfectly quantized.
- **Register**: D5–D7. **Pan** +0.25.

**The shared layers take the dominant faction's colour**, which is what makes
this work with eyes closed even during a neutral passage:

```
dom = ember ground share
kick drive     = 1.4 + 1.6*dom          (ember-dominant = a fatter, dirtier kick)
kick pitch floor = 41 - 6*dom  Hz
kick click HP  = 3000 + 4000*(1-dom)    (ice-dominant = a brighter click)
reverb send    = 0.08 + 0.34*(1-dom)
global swing   = 0.50 + 0.06*dom
```

A 99 % ember board is a swung, saturated, sub-heavy record. A 99 % ice board
is a dry, quantized, crystalline one. Same song.

---

## 3. Intensity and automation from battle state

Five signals, all derivable from `Timeline.metrics` and `Timeline.events`
with no new hooks:

```
share_e (t) = own_a / (own_a + own_b)
claimed(t)  = (own_a + own_b) / 8000
pressure(t) = clip(log2(max(1, procs_a + procs_b)) / 7, 0, 1)      # 128 procs = 1
energy(t)   = clip(log10(1 + bps) / log10(401), 0, 1)              # bombs/s, 1-bar boxcar
momentum(t) = clip(|d claimed/dt| / 0.02, 0, 1)                    # 2 %/s of core = 1
contest(t)  = 4 * share_e * (1 - share_e)                          # 1.0 at 50/50
```

**Tiering** (layer gating), sampled as the mean over each bar:

```
INTENSITY = 0.42*energy + 0.28*momentum + 0.20*pressure + 0.10*contest
tier thresholds: 0.18 / 0.34 / 0.52 / 0.70
```

Hysteresis, because a flapping arrangement is worse than a flat one: a tier
rises after **2 consecutive bars** past the threshold and falls only after
**4** — builds are fast, decays are slow. Tier rises at most 1 per bar, but
drops to 0 instantly at a `round-cut`. Layer entries crossfade over one beat
or arrive on the downbeat behind a reverse swell; layer exits are always on
a bar line.

**Continuous automation** (per-sample curves, not tiered):

| destination | source | range |
| --- | --- | --- |
| bass/pad low-pass cutoff | `momentum` | 200 Hz → 6 kHz, exponential |
| sub high-pass (riser evacuation) | riser progress | 20 Hz → 400 Hz |
| ice reverb send | `1 - energy` | 0.10 → 0.55 (quiet = vast) |
| stereo width | `contest` | ±0.15 → ±0.45 |
| pad detune | `contest` | 4 → 14 cents (the front is where things beat) |
| ember/ice bus gain | `sqrt(share_e)` / `sqrt(1-share_e)` | equal-power, as v1 |
| pad voice count | `pressure` | one harmony note per queue doubling (keep v1) |
| sidechain depth | tier | 0.45 → 0.75 |

**Sidechain**, the glue: for each kick at `t_k`, multiply `sub`, `pad`, `vox`
by `1 - depth * exp(-(t - t_k)/0.09)`. That single line is most of the Fred
Again feel and it costs one numpy expression per kick.

---

## 4. The three signature moments

### 4.1 Load-in (bars 0–1, and a 1-bar restatement per round cut)

The `load-in` beats give `t` and `span` (0.48 s per side, 0.18 s gap). The
picture is a scanline writing a body into empty memory; the sound is the
same gesture.

1. From t = 0: `bed` drone plus a half-time sub pulse (kick on 1 and 3 only,
   whole bus low-passed at 200 Hz). The room is not empty, but it is asleep.
2. **Ember writes**: an ascending 16th arp D1–A1–D2–F2, one note per 1/16,
   amplitude tracking the write progress `pa`. Ember's saw stack, filter
   closed to 600 Hz.
3. **Gap**: one 1/16 of nothing. The gap is in the picture; keep it in the
   sound.
4. **Ice writes**: a descending glassy arp D6–A5–F5–D5, bell timbre, wide
   reverb.
5. Underneath both, a noise riser (band-pass centre 200 Hz → 8 kHz,
   exponential) whose length is computed backwards from **the next bar line
   after the load-in ends**, so it lands exactly.
6. On that downbeat: full-band kick, sub, pad. The curtain is up.

Rounds 2 and 3 get a 1-bar version — the riser and the kick re-entry only,
no arps. The load-in taught the audience once; restating it in full would be
the fourth thing that sounds like a beginning in a 163-second track.

### 4.2 The elimination drop

The whole point of an offline render. `t_e` is known before a single sample
is written, so the track can *want* it.

- **t_e − 4 bars (−7.11 s): RISER.** Everything keeps playing. On top: a
  noise sweep, a snare roll accelerating 1/8 → 1/16 → 1/32, and the sub
  progressively high-passed 20 → 400 Hz so the low end evacuates the room.
  Over the last bar the pad bends up 2 semitones. Tier is pinned at max and
  cannot fall.
- **t_e: ABSOLUTE SILENCE.** Keep `Mix.gate` exactly as it is — hard zero
  across `HITSTOP_S` = 0.14 s, 4 ms edges. At 135 BPM that is a third of a
  beat: a hole punched in a moving track by a full-scale riser stopping
  mid-sweep. Do not extend it. Do not fill it. Do not fade into it.
- **t_e + hitstop: THE DROP.**
  - The D1 sub impact (keep v1's, it is right), now landing on **Bb1** — the
    only outside note in the piece, spent here.
  - The kick returns on the next 1/16 line (≤ 0.111 s later, below the
    threshold of feeling like a shift) and the grid is re-locked.
  - A new 8-bar section in which the loser's layers are simply **gone** —
    not faded, gone. The winner's production owns the entire mix: if ember
    won, the record is suddenly saturated and swung; if ice won, it is
    suddenly dry and gleaming.
  - The chord changes for the first time in the round: the loop is
    interrupted and holds on **Bb** for 2 bars before returning to Dm7.
  - The loser's bed dies over `sweep` (= `ELIM_S − hitstop`, which the
    existing beat already reports correctly) as a **filter** closing
    4 kHz → 120 Hz *and* a gain ramp. v1 faded it; it should suffocate.

**Tie rounds still need a drop.** match-002 is three ties, so this path
carries the whole match. The arranger finds the round's peak `INTENSITY` bar
offline and places a fill-and-drop there: the same riser, the same 8-bar
payoff, **but no silence and no Bb**. The silence and the outside note belong
to kills alone, so a kill can never be mistaken for a musical event that also
happens in a stalemate.

### 4.3 The endings

**Draw — the Eno outro.** `DRAW_FADE_S` = 3.2 s plus the recorder's 1.0 s of
room tone; use the whole 4.2 s.

- The drums stop **dead on the last downbeat before `t`**. No fill, no crash,
  no ritardando. A draw does not get a gesture.
- What is left: both faction pads at their final ground share, both sounding
  Dm7 — ember voicing D1/F2/A2, ice voicing A5/D6.
- Over the fade the two voices **converge in pitch**: ice's partials glide
  down and ember's up, via the existing `glide()` per partial, until both are
  sounding a shared D3/A3. The two factions literally dissolve into one
  drone. This is the audio of the picture's shared cooling, and it is the
  single thing in this proposal I would protect hardest.
- Feed the last 0.5 s into a long FDN reverb (§6) at 0.86 feedback and let it
  ring past the picture's fade.
- Amplitude falls exponentially to about −60 dB and **never reaches zero**;
  the final room tone is that drone at ≈ −42 dBFS. No motif, no cadence, no
  tonic hit. It does not end, it stops being loud enough to hear.

**Win — the finale.** The opposite in every respect. Drums play straight
through `match-end`, tier pinned at max, the winner's motif (keep v1's
four notes resolving to D, it works) over their own full production, one bar
of Bb into two of Dm7, and the track **ends on a downbeat**: one tonic hit,
full band, plus a reversed reverb decay under the last 0.6 s. A win stops.
A draw dissolves. If a listener cannot tell which happened from the last
three seconds alone, the ending is wrong.

---

## 5. What I am deliberately not taking

Taste is choices, so here are the ones I am making against the palette:

- **Charli XCX: no topline, no hook, no pitched-up diva.** I take the
  production — brutal dry percussion, the confidence to let a section be a
  kick and one squealing filter — and leave the song. A recognisable vocal
  melody would make the video about the music instead of about the battle,
  and it would fight the caption for the same attention.
- **Fred Again..: no found-voice emotionality.** His signature is a real
  human saying a real thing. We have no samples, and faking that with formant
  synthesis lands squarely in the uncanny valley. I take the *rhythmic
  treatment* of voice (chopped, gated, pitched into the grid) and the
  sidechain-and-rolling-bass glue, which is the transferable half.
- **Brian Eno: no generative aleatorics.** Determinism forbids it, and more
  to the point it would be redundant — the battle *is* the generative
  process, and a second stochastic layer would only obscure the first. Eno's
  contribution here is a philosophy of endings, not a method.
- **Grimes: no reverb wash.** I take the bright, inhuman formant voice as
  texture. I refuse the drench, because the mix law is a quiet room that
  events puncture, and a large reverb is the most reliable way to destroy a
  puncture. Reverb is an ice-only send that ducks with `energy`.
- **Techno: no unbroken 4-on-the-floor.** Straight techno's virtue is
  hypnosis, and a 53-second section cannot earn hypnosis. A constant kick
  would also cost the elimination its silence — you cannot punch a hole in
  something already flat. The kick is a layer, present roughly 60 % of the
  match.
- **No tempo change, no key change, ever.** Three rounds are one track.
- **v1's per-bomb one-shot: deleted outright.** Bombs no longer make a sound.
  They vote. This is the whole sonification-to-music line and it should be
  crossed cleanly rather than compromised at a rate cap.
- **v1's wrap whip and per-death blip: deleted.** Wraps are frequent and
  musically meaningless (a delay throw at most). Deaths are better used as
  the backbeat than as blips — deaths *are* the clap, which is a stronger
  idea than either sound.

---

## 6. Implementation sketch

### Stays, untouched

`extract()` and the entire `Timeline` contract, `VirtualClock`, `FrameSink`,
`EVENT_HOOK` / `FRAME_HOOK`, `Mix`, **`Mix.gate`** (the hitstop is already
perfect), `master()` (the limiter is right and hard-won), `write_wav`,
`render_frames`, `mux`, `busiest_window`, `excerpt`. The DSP primitives
`hashnoise`, `env_ad`, `saw_stack`, `bell`, `norm`, `sine`, `glide`, `curve`
all survive as-is. The ten timeline tests do not change — the contract is
untouched, which is the reason this is a brain transplant and not a rewrite.

### Replaced

`ambient_bed`, `faction_beds`, `bomb_hit`, `rumble`, `punctuate`, `motif`,
and the `BOMB_RATE_CAP` constant. `synthesize()` becomes three lines.

### New — suggest a sibling module `score_cw.py`, imported by `record_cw.py`

1. **`class Grid`** — `bpm`, `bar(i)`, `beat(i)`, `step(i)`, `snap(t, div)`,
   `steps_between(t0, t1)`. Pure arithmetic, trivially testable.
2. **`analyze(tl, grid) -> Score`** — the arranger, one offline pass:
   - `steps[]`: per 1/16, per faction — bomb count, stride `d`, `spread`,
     death count, spl count.
   - bar-resolution curves: `energy`, `momentum`, `pressure`, `share`,
     `contest`, and the resulting `tier` after hysteresis.
   - `sections[]`: `(start_bar, end_bar, kind, focus, tier_ceiling)`.
   - `cues[]`: risers/drops/breakdowns with anticipation already applied
     (this is where look-ahead lives, and it is the only place it needs to).
3. **`render_score(score, mix)`** — one function per layer: `lay_bed`,
   `lay_pad`, `lay_sub`, `lay_kick`, `lay_perc`, `lay_backbeat`, `lay_vox`,
   `lay_lead`, `lay_fx`, `lay_moments`. Each reads the `Score` and writes to
   the existing `Mix`.

### New DSP helpers, and the one implementation trick that matters

Time-varying filters are the obvious cost centre, and a sample-rate IIR loop
in Python over 7.2 M samples is not viable. **Do the filtering additively.**
Every tonal source here is already an additive stack, so a moving low-pass is
just a per-harmonic gain array:

```python
g_h(t) = 1.0 / sqrt(1.0 + (h * f0 / fc(t)) ** (2 * order))
```

Fully vectorised, exact, deterministic, no loop, no scipy. The same trick
gives formants for the vox: instead of resonators, weight each harmonic by
the sum of three resonance curves
`A_k / (1 + ((f - F_k) / (F_k / (2Q))) ** 2)` with Q = 8.
Ember vowel /ɔ/ = (500, 850, 2500); ice vowel /i/ = (270, 2300, 3000).
Chop with a fixed 16th gate pattern and you have Fred Again's voice treatment
with no sample and no filter loop.

Only noise-based sources (hats, risers, the snare roll) need a real filter,
and for those the block-wise one-pole already used in `rumble()` is fine —
256-sample blocks, one coefficient per block, ~28 k iterations for the track.

Remaining helpers: `ladder_lp(sig, fc_curve, res)` (block-wise, for the acid
lead only), `sidechain(mix_slice, kick_times, depth)`, `tanh_drive(x, k)`,
`bitcrush(x, bits)`, `delay_send(sig, time_s, fb, mix)`, and
`fdn_reverb(sig, feedback, damp)` — four delay lines at prime lengths
(1489, 2131, 3079, 4177 samples), Hadamard 4×4 mixing, processed in blocks of
1489 samples so each block reads only already-written history (~4.8 k
iterations).

### Mix budget (pre-limiter peaks)

```
kick        -8      pad          -22      drop impact  -3
sub        -10      vox          -20      room floor  -34
perc       -16      lead         -18      ceiling      0.89 (keep)
```

### The mix law, restated for a track

v1's crest factor of 17.3 dB was the right law for a sparse sonification and
is the wrong law for a record — a track with a kick will land nearer 11–13 dB,
and should. What must be preserved is the *contrast*, so make the law
sectional and testable:

- the elimination hitstop window is **exactly 0.0** in the WAV;
- the quietest bar's RMS is **≥ 14 dB** below the loudest bar's;
- the drop bar is **≥ 6 dB** above the bar preceding the riser;
- integrated loudness ≈ **−14 LUFS**, true peak ≤ −1 dBTP.

### Tests

Grid arithmetic (snap idempotent and monotone); arranger determinism (two
runs produce an identical `Score`, compared field by field); arranger
invariants (sections partition the timeline, none shorter than 2 bars, tiers
never jump more than 1 upward per bar); and the four mix-law assertions above
measured directly off the rendered WAV. Audio DSP stays lightly covered —
shape, length, peak — exactly as the addendum already argues.

**Proposal: Core War Broadcast Master — v2 Track System**

---

### 1. The Track System

**Grid & Tempo.** I am locking the entire broadcast to a fixed **130 BPM, 4/4 techno grid**. At 130 BPM one bar is ~1.846 s, an 8-bar phrase is ~14.8 s, and a 16-bar section is ~29.5 s. A 53 s round therefore contains roughly 28–29 bars — enough for a full club-musical narrative (intro → groove → build → drop → breakdown) without rushing. The entire match is one continuous grid; round boundaries do not reset the tempo.

All events are **quantized to a 16th-note grid** (115 ms slots). Stride-4 bombers that hit every ~460 ms land on quarter-note off-beats and become **pattern-locked drum sequences**; imp carpets that hit every ~230 ms become 8th-note hat rolls. If more than one event falls in a 16th slot, they fuse into a single accent with velocity scaled by the square root of the count — never a machine-gun stack.

**Adaptive Phrase Blocks.** Because rounds can end early (kill) or go long (stalemate), the structure is built from state-triggered phrase blocks that always join at bar lines:

| Block | Length | Trigger | Musical Function |
|---|---|---|---|
| **Intro** | 4 bars | `load-in` | Rising sweep, bed swell, pickup kick pattern |
| **Groove** | 8–16 bars | Battle active, low/mid momentum | Full percussion, faction beds, quantized stride patterns |
| **Build** | 4 bars | Momentum surge or climax detection | Snare-roll density rises, filter opens, riser FM tone climbs, kicks thin out |
| **Drop** | 2 bars | `elimination` | Absolute silence for hitstop, then sub impact + winner motif |
| **Breakdown** | 2–4 bars | `verdict` (tie or round end) | Bed only, suspended chord or winner motif, no percussion |
| **Outro** | 8 bars | `match-end` (draw) | Beatless shared drone, or winner finale |

**Event → Music Mapping Table.**

| Timeline Event | Quantization | Musical Action |
|---|---|---|
| `load-in` | Bar-aligned (bar 1 of round) | Ember: 808 kick pickup on beats 2-2.5-3-4; D1→D2 saw-stack swell over 4 bars. Ice: reverse-cymbal suck into beat 2; D4→D5 FM bell sweep. |
| `bomb` | 16th-note grid | Ember: 808 thud @ D2. Ice: FM glass chop @ D5. Stride regularity → pattern-locked for 4 bars. Slot overload → low-passed rumble bed (120 Hz cutoff). |
| `first-blood` | Downbeat of next bar | Accented bomb + bell toll (D3 ember / D5 ice). Snap-opens faction LPF +6 dB for 2 bars. |
| `wrap` | Nearest 16th | Upward whip-gliss D4→D6, 90 ms, + sidechain duck on opposite faction bed for 100 ms. |
| `death` | Nearest 16th | Ghost note: falling blip (ember D3→D2, ice D6→D5). Triggers -3 dB sidechain duck on bed. |
| `bloom` / `split` | Nearest 8th | 4-note arpeggio fill (ember: D3-F3-A3-C4; ice: D5-A5-C6-D6) over 1 bar. Adds one unison harmony layer to faction bed. |
| `elimination` | Exact time (bar-aligned if within ±200 ms) | **Build override** for preceding 4 bars if detected early. Hitstop: `Mix.gate()` hard mute exact duration. Post-hitstop downbeat: sub impact (D1 sine + D2 sine, 400 ms decay) + winner stab motif. Loser bed muted; winner bed jumps to 100 % mix over 2 bars. |
| `verdict` (tie) | Bar-aligned | Suspended D-G-C chord, both beds equal-power, no resolution. Fades across 2 bars into next round intro. |
| `verdict` (kill) | Bar-aligned | Winner motif: A→C→D→D in faction timbre, 4 notes across 2 bars. |
| `round-cut` | Last bar of round | 1-bar filter-sweep transition: LPF closes to 200 Hz then snaps open for next load-in. |
| `match-end` (win) | Final 4 bars | Winner motif full voice + bed solo + terminal sub drop. |
| `match-end` (draw) | Final 8 bars | Both beds abandon identity, merge to shared D1+D2 drone, beatless fade. |

---

### 2. Faction Production Identities

**EMBER — "The Furnace"** (Warm, Gritty, Low)

*Philosophy:* Ember is a basement warehouse soundsystem — damped 808 weight, detuned analog saws, and coal-dust static. It occupies the **D2–A3** register with sub-weight at D1.

- **Kick (the body):** Sine sweep 110 Hz → 55 Hz over 80 ms, plus a 4 kHz click transient (sine burst, 8 ms attack). Envelope: A 2 ms, D 80 ms, S 0, R 20 ms. This is the default downbeat; it does not vary per bomb, only in velocity.
- **Bass:** 3-voice supersaw stack (D2 fundamental, additional voices at -7 ¢ and +19 ¢). Through a resonant biquad LPF (12 dB/octave, Q = 2.5). Baseline cutoff: **250 Hz**. At peak intensity (climax), automation drives cutoff to **900 Hz**; resonance peaks at 2.2 kHz for a "scream."
- **Stabs:** D minor pentatonic (D3, F3, G3, A3, C4). Pluck envelope: A 3 ms, D 160 ms, S 0. Built from 5-harmonic saw with +12 ¢ detune. Every process doubling adds a perfect fifth above (A3, then D4) as a unison layer.
- **Stride percussion:** "Coal crackle" — hashnoise bursts low-passed at **800 Hz**, 40 ms decay, on off-beat 16ths when stride patterns are locked.
- **Texture:** Amplitude grit at 12 % depth via `hashnoise(idx * 0.0009)` gated to the 16th-note grid (so the flicker breathes with the music, not the raw event rate).

**ICE — "The Prism"** (Glassy, Pure, Digital)

*Philosophy:* Ice is a laser-cut LED rig — precise, metallic, and high. It lives at **D5–D6** with a dry cryo-punch at D4.

- **Cryo-sub (weight):** Sine D4 (294 Hz), 30 ms, no tail. This is not a bass instrument; it is a percussive dry-ice thud that gives ice vertical presence without invading ember's low end.
- **FM Bell:** Carrier sine at D5; modulator at ratio **3.14** (1844 Hz). Modulation index envelope: starts at **4.0**, decays to **0.5** over 120 ms. This creates a bright digital "tink" with inharmonic attack — no samples needed.
- **Hats / Chops:** Metallic 16th-note pattern from two sines at 8.0 kHz and 8.234 kHz (234 Hz beat) multiplied, then high-passed at 3 kHz. Decay 40 ms. "Open hat" variant extends decay to 120 ms and adds a 12 kHz FM sparkle.
- **Strides:** Stride-4 locked patterns trigger D6 FM bell 16th-note rolls with velocity decay. Stride-7 triggers a "shatter" cluster (D5 + A5 + D6 + F6 simultaneously).
- **Pad:** Inharmonic bell partials (1.0, 2.01, 3.03, 4.21, 6.18) at D5, amplitude tremolo at **0.37 Hz** (kept from v1).
- **Texture:** "Frost steam" — high-passed hashnoise (4 kHz, 6 dB/octave) with slow 0.37 Hz tremolo, sidechain-gated by ember kicks so ice hisses only in the spaces.

---

### 3. Intensity & Automation

Battle state is read from `tl.metrics` (territory, process counts) and derived signals:

| Signal | Source | Musical Mapping |
|---|---|---|
| **Territory Share** | `own_a / (own_a + own_b)` | Equal-power crossfade between faction beds. Winner pans from ±0.25 toward ±0.40 as share exceeds 70 %. |
| **Board Heat** | `(own_a + own_b) / 8000` | Master high-shelf gain (+4 dB at 3 kHz when board is dense; flat when empty). |
| **Process Ratio** | `log2(procs_a) – log2(procs_b)` | Drives percussion density. Dominant faction fills 16th notes; losing faction drops to quarter-note stabs only. |
| **Momentum** | `d(procs)/dt + d(own)/dt` (smoothed) | Positive: opens ember LPF, raises ice FM index, adds white-noise "steam" layer. Negative: closes filter, sheds percussion voices. |
| **Bomb Rate** | Bombs per bar | < 4/bar → closed hats. 4–8/bar → open hats. > 8/bar → fused rumble + noise burst. |
| **Climax Flag** | Procs > 16 AND bomb rate > cap for > 2 bars | Forces **Build** phase: snare roll (ember 16th-note snaps rising A2→D3), LFO rate doubles, beds detune +25 ¢. |

Automation curves are pre-computed per-sample across the whole render (offline lookahead), so a drop is never missed.

---

### 4. The Three Signature Moments

**Load-In (Intro / First Build).** The drop-pod materialization is the curtain rise. Bar 1 is a **pickup**: silence on beat 1, then ember's 808 kick enters on the "and" of 1, beat 2, and the upbeat of 3 — a rolling techno anacrusis. Ice answers with a reverse-cymbal "suck" that lands on beat 2. Bars 2–3: ember glides from D1 to D2 via `glide()` under a rising supersaw crescendo; ice sweeps D4→D5 via FM index ramp from 0 to 3. Bar 4: both factions hit downbeat 1 together — kick, cryo-sub, and full bed — and the groove begins on bar 5. If a round-cut restarts the round, the sweep compresses to 2 bars but the downbeat still locks to the grid.

**Elimination Drop (THE DROP).** The 4 bars preceding elimination are hijacked into a **forced Build**. Ember's LPF snaps fully open (900 Hz), ice's FM index maxes out, and a Shepard-style riser (stacked octave saws at D3/D4/D5 with crossfading amplitudes) climbs the last 2 bars. Percussion thins to 16th-note closed hats only — no kicks — so the tension pulls hard. At the exact elimination timestamp (quantized to the nearest downbeat if within ±200 ms, otherwise instantaneous): **ABSOLUTE SILENCE**. `Mix.gate()` zeroes the bus for the full hitstop duration. The room is a void. On the first downbeat after hitstop: **IMPACT** — sub impact (D1 + D2 sine, 400 ms, peak 0.95) layered with the winner's four-note motif (A→C→D→D) in full detuned voice. The loser's bed is muted; the winner's bed leaps to center pan and 100 % width. Over the cooling-sweep seconds (typically 2–4 bars), the master LPF slowly closes from 2 kHz to 400 Hz, as if the air itself is cooling.

**Draw Outro (Eno Outro).** Triggered only on a drawn match. All percussion stops immediately — beatless. Ember and ice abandon their separate identities and **merge** into a single shared drone: D1 + D2 detuned saw (ember's warmth) blended with D2 pure sine (ice's clarity) and a D3 inharmonic bell cluster. A slow 30-second LFO breathes the amplitude at 40 % depth. Over 8 bars (~14.8 s) the drone fades from -12 dBFS to -60 dBFS. The stereo field collapses from ±0.25 pan to dead center by bar 4, then drifts back out slightly as it dissolves, representing the two factions dissolving into shared ash. No events puncture. The final second is pure silence before the file ends.

---

### 5. Deliberate Rejections from the Influence Palette

- **Fred Again.. — Vocal Collage / Documentary Intimacy.** Fred's emotional engine is pitched human voices, found-sound phone calls, and the nostalgia of "Actual Life." A Core War broadcast is machine combat; there is no place for human vulnerability or sampled pathos. I am keeping his **warmth** only as synthetic detuned saws, not as vocal memory.

- **Charli XCX — Maximalist Loudness / Pop Structure.** The "brat" aesthetic demands everything upfront, hyper-compressed, clipping-as-texture. Our hitstop silence only works if the crest factor is wide and the room is quiet. I take Charli's **glacial FM timbres and digital precision** for ice, but reject the wall-of-sound mixing and verse-chorus songform.

- **Grimes — Fairy-Pop Vocals / Narrative Lyricism.** Grimes builds mythological worlds with her voice and music-box arpeggios at the center. Core War has no singer and no story in words. I keep her **futurist sheen**, but her whimsical, ethereal layers are replaced by mechanical, stride-quantized patterns.

- **Brian Eno — Generative Drift / Non-Determinism.** Eno's process music embraces randomness and obscured rhythm. Our system is strictly deterministic and grid-locked. I keep only his **ambient patience** and the philosophy of "room tone," deployed exclusively in the draw outro.

---

### 6. Implementation Sketch

**What Changes in `record_cw.py`:**

- **New `GridEngine` pre-processor.** Inserted between `extract()` and `synthesize()`. It quantizes the timeline to 130 BPM 16th-note slots, detects stride periodicity in bomb trains, derives the intensity/automation curves from metrics, and emits a `Score` list: `[(bar_idx, section_type, params)]`. This replaces ad-hoc event iteration with bar-level musical composition.

- **New synthesis primitives.** Added alongside `saw_stack()` and `bell()`:
  - `supersaw(freq, n, voices=3, detune_cents=(-7, 0, 19))` — thicker ember body.
  - `fm_bell(freq, n, ratio=3.14, index_env=(4.0, 0.5))` — ice digital glass.
  - `synth_kick(n)` — deterministic 808 sweep + click.
  - `synth_hat(n, open=False)` — ring-modulated metallic chop.
  - `shepard_riser(n, root=D3)` — octave-crossfade build tone.

- **Rewrite `punctuate()` → `orchestrate()`.** Instead of iterating raw events and calling `mix.add()` per bomb, it walks the `Score` bar-by-bar. Bomb strata are rendered as pre-baked drum-pattern arrays (kick/hat/rumble) per bar. Event accents (blood, bloom, death) are quantized to the grid before mixing. Section types (Build, Drop, Outro) trigger the new layers (riser, sub impact, shared drone).

- **Rewrite `faction_beds()`.** Now state-aware: during Build it adds riser energy and opens the LPF; during Drop it mutes the loser and widens the winner; during Draw Outro it crossfades both sources into the shared D1+D2+D3 drone.

- **Quantization helpers.** `quantize_events(tl, bpm=130)`, `stride_lock(bombs_by_bar)`, and `climax_detect(metrics)` are new pure functions.

**What Stays Exactly As-Is:**

- `extract()`, `VirtualClock`, `FrameSink`, `Timeline` — the timeline plumbing is already perfect.
- `Mix`, `gate()`, `norm()`, and the fast-attack/slow-release `master()` limiter — the bus architecture and crest-factor discipline are correct.
- The global ambient bed concept (low D1+D2 drone), though renamed to `global_bed()` and enlisted into the Draw Outro merge.
- `write_wav()`, `render_frames()`, `mux()` — the frame and mux pipeline is unchanged.
- `curve()` — metric interpolation stays, now feeding automation arrays.
- `hashnoise()` — deterministic texture source.
- D minor pentatonic scale, equal-power crossfade law, and pan law (ember -0.25, ice +0.25).
- The hard constraint of total determinism: same transcript → byte-identical WAV.

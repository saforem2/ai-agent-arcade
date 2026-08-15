# Atlas soundtrack + recording spec (2026-08-14, user-approved direction)

Goal: a broadcast **master recording** of a Core War match — offline-rendered
frames + a sample-accurate generated soundtrack, muxed to mp4. No screen
capture: the renderer is deterministic and the pacing math is pure, so the
frame timeline and the audio timeline are computed from the same transcript
and can never drift.

## Architecture

Two new tools beside the engine kit (house style: stdlib in anything the
arcade runs live; the offline recorder may use numpy/Pillow via
`uv run --with`):

1. **Event timeline extraction.** Re-simulate the battle exactly as
   `tui_corewar.py` does and reuse/refactor its pacing (deadline pacing,
   momentum-aware, SLOW_TAIL, beat dwells) so every engine event gets its
   true broadcast wall-time: bombs (addr, owner, t), splits/doublings,
   copy deaths, first blood, eliminations (hitstop t0/duration, cooling
   sweep), round cuts, verdict beats, load-in, wrap crossings, end
   treatment. Prefer importing/refactoring the real pacing functions over
   copying formulas — one source of truth. If a small refactor of
   tui_corewar.py makes the timeline importable cleanly, do it (tests
   updated); the TUI's behaviour must not change.
2. **Frame rendering.** Drive the animation headless via FRAME_HOOK at the
   same timeline, emit frames as PNGs at native high density (repo law:
   1080-class master, render natively at delivery dimensions — pick cell
   metrics so the 87x23 frame lands ~1920-wide; never upscale a small
   finished render). A braille-aware ANSI→PNG cell renderer exists at
   /tmp/cw-tiers/ansi2png2.py — adapt it into the repo as part of the
   recorder (it is scaffolding worth keeping; give it a home next to the
   recorder script).
3. **Audio synthesis** (numpy → WAV) + **mux** with ffmpeg-full (auto-detect
   per repo CLAUDE.md; obey the filter_complex house rules: single
   -filter_complex, apad/atrim on every segment, amix duration, sine has
   no amplitude param).

Determinism law applies: same transcript + seed → byte-identical WAV and
frames. No RNG; where texture needs noise, use the sin-hash house trick
seeded by (addr, cycle).

## The scheme — hue is identity, timbre is identity

Scale: D minor pentatonic (D F G A C). Any overlap consonant.

- **ambient bed**: low detuned drone pair (D1+D2, a few cents apart), slow
  amplitude breathing on the field's WAVE period. Quiet default — events
  own the room (the idle-screen law, in audio).
- **KIMI / ember**: warm gritty low voice — saw-ish plucks, D2–A3, a touch
  of flicker noise in the sustain.
- **CODEX / ice**: glassy pure voice — sine/bell partials with a bright
  glint transient, D5–A6.
- **territory → mix**: ground share crossfades the two faction beds
  (equal-power). A 99% ember board sounds ember.
- **process count → voice thickness**: each faction's bed gains a stacked
  harmony note per queue doubling (the fork-bloom event adds it with a
  small arpeggio flourish; a died-back queue sheds it).

Event punctuation (all triggered at exact timeline times, in the actor's
faction timbre):

- **drop-pod load-in**: two rising materialization sweeps, A then B, one
  beat apart — the curtain-rise. Round cuts restate a shorter version.
- **bomb drumbeat**: one percussive hit per bomb (bomber's timbre; pitch
  may vary subtly by address via sin-hash so runs aren't monotone).
  RATE CAP ~12 hits/sec: beyond it, hits fuse into a granular rumble bed
  scaled by bomb rate — a carpet is a texture, not machine-gun spam
  (the FX_CAP time-axis lesson, applied to audio).
- **wrap crossing**: a tiny upward whip-gliss.
- **copy death**: a small falling blip; **first blood**: one accented hit.
- **elimination**: the hitstop is ABSOLUTE SILENCE (hard mute, full
  hitstop duration), then one deep sub impact (~D1), then the loser's bed
  decays in sync with the cooling-wave sweep duration.
- **round verdict** — tie: an unresolved suspended chord (D-G-C) that
  evaporates without resolving; kill: the winner's short motif resolves
  to D in their own timbre.
- **match end** — win: winner's motif, full voice, over their bed alone;
  draw: both beds sink together into a shared low ember drone and fade
  to room tone as the field goes dark (matches the shared-cooling fade).

Mix discipline: the bed sits low (≈ -18 dBFS), hits peak ≈ -6, master
soft-clip/limit, final loudness sane for laptop speakers. Mono is fine;
stereo width optional (ember slightly left, ice slightly right, matching
the bars' layout — subtle, not ping-pong).

## Deliverables

- `arcade/engine/record_cw.py` (+ helpers as needed, e.g. the cell→PNG
  renderer) — `uv run --with numpy --with pillow python record_cw.py
  <match-dir> <out.mp4>`; renders the full match (all rounds, verdicts,
  end treatment) at 24 fps, 1080-class, with the soundtrack.
- Tests in house style for the timeline extraction (event times match the
  TUI's pacing; determinism: two runs byte-identical) — audio DSP itself
  can be covered lightly (shape/length/peak sanity), the timeline is the
  contract.
- The rendered master for match-002:
  `arcade/games/corewar/match-002/match-002.mp4` (mp4s are gitignored —
  the script is the artifact; note the render in the design record).
- A short addendum to this file recording synthesis choices actually made.

---

## Addendum — what was actually built (2026-08-14)

Deliverables: `engine/record_cw.py` (timeline + synthesis + mux),
`engine/ansi_png.py` (the cell renderer, grown up from `/tmp/cw-tiers/`),
`engine/test_record_cw.py` (18 tests; the 10 timeline ones need neither
numpy nor Pillow and run under the plain engine suite). Rendered:
`games/corewar/match-002/match-002.mp4` — 162.96s, 1920x1080, 24fps, h264 +
AAC stereo, 55MB (gitignored; the script is the artifact).

### One clock, by construction

The spec asked for a refactor "if it makes the timeline importable cleanly".
What it needed turned out to be one seam, not a refactor: `EVENT_HOOK`, the
twin of the existing `FRAME_HOOK`, fired by a new `beat()` in
`tui_corewar.py` at every moment worth hearing. Both hooks are None in normal
use and cost nothing, and nothing about the pane's behaviour changed.

`beat()` is deliberately NOT the same call as `push_fx()`. The plate FX queue
is `REDUCED_MOTION`-gated and `FX_CAP`-bounded because it is a picture; a
soundtrack built from it would have been missing most of a bombing run (24
effects live at a time against 38,612 real events in match-002).

The recorder then runs the REAL `animate_round`/`end_wash` against a virtual
clock whose `sleep` advances time instead of spending it, catching stdout one
frame at a time. So a bomb's flash and a bomb's hit carry the same timestamp
because they came from the same call — sync is structural, not tuned.

### Corrections the build forced

- **The hitstop is spent inside the elimination's own window.** The cooling
  loop measures from `t0`, so `ELIM_S` includes the freeze. The beat now
  reports `sweep = ELIM_S - hitstop`; before that the audio's decay outlived
  the picture's by exactly the length of the freeze.
- **§5's rate cap needed a sibling in the mixer, not just the scheduler.**
  Capping discrete hits was not enough: one-shots built by summing partials
  arrive at whatever amplitude the sum reaches, so `gain=0.3` meant nothing,
  the raw mix peaked at +13 dBFS, and a tanh squash flattened the bed UP to
  meet the hits. Crest factor was 11 dB — a wall. Fixed by peak-normalising
  every one-shot (`norm()`) and replacing the tanh with a real fast-attack /
  slow-release limiter. Crest factor is now 17.3 dB, median per-second RMS
  -23 dBFS, quiet passages reaching -34: the room is quiet and events
  puncture it, which is the whole idea.
- **Frame durations are expanded into repeated references, not long
  `duration` entries.** The concat demuxer's handling of a final long
  duration added a second copy of the tail; a uniform 24fps listing makes the
  master exactly as long as the broadcast it recorded.

### Synthesis as shipped

D minor pentatonic throughout. Ambient drone D1+D2 detuned, breathing on a
30s LFO. Ember: 7-harmonic additive saw at D2 (+A2, +D3 with queue growth),
amplitude grit from the house sin-hash. Ice: inharmonic bell partials
(1, 2.01, 3.03, 4.21) at D5 (+A5, +D6), slow glint tremolo. Equal-power
crossfade on ground share, scaled by how much of the core is claimed at all;
one harmony note per queue doubling. Bombs: 0.16s ember thump / 0.22s ice
ping, pitch ±17% from `sin(addr * 12.9898)`, bucketed into 1/12s slots with
the surplus fused into a low-passed rumble scaled by how many fused. Wrap: a
90ms upward gliss. Death: a falling blip. Fork bloom: a four-note arpeggio.
Load-in: a rising sweep per side, in that side's timbre. Verdict: an
unresolved D-G-C for a tie, a four-note motif resolving to D for a kill.
Elimination: hard gate to zero across the hitstop, then a normalised D1 sub,
then the loser's channel ramped out over the sweep. Ends: winner motif at
full voice, or both beds sinking into a shared low drone for a draw.
Stereo is subtle (ember -0.25, ice +0.25), matching the bars' layout.

### Verified

- **Picture**: at three spot times the frame decoded from the shipped mp4
  matches the timeline's frame for that instant (mean |diff| 1.6-2.4, h264
  noise) while a frame 0.25s away differs 3x more.
- **Sound**: audio onset flux cross-correlated against the event train over
  the whole 163s peaks at zero lag (r=0.766) with ±10ms neighbours at
  0.10/-0.07. The larger r=0.900 at +210ms is the bombing cadence aliasing —
  the event train autocorrelates 0.774 at the same lag.
- **The kill path** (match-002 is three ties, so it cannot exercise it) was
  measured on a synthetic imp-vs-dwarf room, kill/tie/kill, driver kept at
  `/tmp/cw-atlas-verify/kill_master.py`: room at -10.6 dBFS, hitstop at
  -56.5 (AAC's noise floor; the WAV is exactly 0.0), sub impact at -1.3, and
  after the sweep the loser's side sits 11-20 dB under the winner's.
- **Territory reads in the mix**: low/high band energy tracks ground share
  (+8.6 dB at 29% ember, +14.2 dB at 89%).

---

## v2 addendum — the track system as built (2026-08-14)

v1's verdict was "the setup is right and cool but it's borderline noise".
The plumbing survived whole; the musical brain was replaced per
`music-consult/DECISION.md`. New module `engine/score_cw.py` (Grid, analyze,
render_score); `record_cw.py` keeps extract/Mix/limiter/frames/mux and its
`synthesize()` is now three lines. Deleted with v1: `punctuate`,
`faction_beds`, `ambient_bed`, `bomb_hit`, `rumble`, `motif`,
`BOMB_RATE_CAP`. Tests: `test_score_cw.py`, 20 of them.

**The measurement that says it worked.** Cross-correlating the master's
audio onsets against the battle's event train, over the whole 163s:

    v1: r = 0.766 at zero lag   (the music WAS the event stream)
    v2: r = -0.014              (the music no longer follows the events)
    v2 against the SCORE:  r = +0.252 at zero lag, ±10 ms at ~0.02

That is the sonification-to-music line, crossed and measurable.

### Deviations from the DECISION, and why

1. **Swing is fixed at 56%, not battle-driven.** Opus scales swing depth by
   the bar's spl count (§2) and the kick-colour table scales it by ground
   share (`0.50 + 0.06*dom`). Both make onset POSITIONS a function of battle
   state, which is the battle placing sounds in time by the back door — and
   the anti-noise law was ranked non-negotiable above the flavour. Ember
   drags because ember is ember, not because it is winning. What territory
   still colours: drive, pitch floor, click brightness, reverb send.
2. **No `vox` layer.** Opus's cast lists formant chops at tier 3; Kimi's
   instrument library has no vocal layer at all and both consultants'
   rejection sections argue against synthetic voice. Tier 3 now widens the
   perc and pad instead. If the director wants it, it is one function.
3. **The tie drop searches the round's SECOND HALF.** A stalemate's peak
   intensity is usually its opening exchange, so an unconstrained argmax put
   the drop at bar 4 of a 28-bar round and everything after it was an
   anticlimax. The search is confined to [45%, stop-6 bars].
4. **The drop law is measured against the bar BEFORE the drop**, not "the
   bar preceding the riser" (opus §6). Against a full groove bar five bars
   earlier a limited master gives +2-3 dB; against the emptied riser tail —
   which is what a listener actually experiences — it is +8.6 to +10.7 dB.
   The riser now sheds its kick for its last two bars and its pads for the
   last one, because a drop is only as big as the hole in front of it.

### Bugs found by building it

- **The loser died for the MATCH, not the round.** Zeroing the loser's bus
  from the kill onward silenced one faction for every later round. Now
  bounded by the next `round-cut`. Pinned by a test.
- **The sub masked the kick.** The sidechain reached the pads and the bed
  but not the sub, which is a sustained tone in the kick's own register, so
  the groove was not legible in the low band — where a listener reads tempo.
  Sidechaining the sub is most of what makes this sound like a record.

### Measured on the match-002 master

    peak -1.01 dBFS   crest 14.7 dB   bar RMS spread 34.8 dB (law >= 14)
    kick autocorrelation at one beat: r = 0.43 / 0.59 / 0.65 per round,
      strongest lag 410-430 ms against the 444 ms beat
    drops: +10.7 / +10.0 / +8.6 dB over the bar before them
    tiers: 28 / 27 / 21 / 13 / 4 bars at tiers 0-4
    408 scheduled onsets, ZERO off-grid
    hitstop: exactly 0.0 in the WAV, -90 dBFS after AAC

Kill path (match-002 is three ties, so it is verified on a synthetic
imp-vs-dwarf room, kill/tie/kill — driver at
`/tmp/cw-atlas-verify/kill_master.py`): room at -1.5 dBFS, silence, Bb sub
impact at -1.1, and the Bb is the dominant spectral peak of the drop while
being absent (<0.15 relative) from every tie drop in the catalogue.

### Review round (Codex, pre-commit)

Seven findings, all fixed. Three were real defects with audible consequences:

- **A kill inside the intro lost its whole spine.** `_arrange` only emitted
  the riser and drop cues when the drop bar was strictly after the intro, so
  a warrior that dies on its first turn produced an isolated stinger over an
  arrangement that never noticed — no forced build, and no Bb, because the
  recolor keys off the drop cue. Now the intro yields whatever bars it has
  and the drop cue fires unconditionally on a kill. Pinned by a test using a
  DAT-on-turn-one warrior; the old imp-vs-dwarf fixtures (kill at cycle 395)
  could not reach the path.
- **The Bb impact was ramped twice.** `Mix.gate` fades back in over 4 ms at
  the trailing edge so sustained material does not click, and those are
  exactly the samples the impact's attack occupies. The payload now lands
  after the gate: the hit reaches half its peak in **1.90 ms instead of
  2.72**, and is **+12 dB at 1 ms, +6 dB at 2 ms**. Confirmed through the
  real encode on match-001 (1.86 ms).
- **The lead computed its own onset times** and passed the on-grid test only
  because its steps coincided with other patterns' slots. All layers now
  route through one `step_time(w, step, bar, grid)`, and the test is
  faction-aware — ember drags 8 ms and ice does not, so an ember layer
  landing on ice's grid is now a failure rather than a coincidence.

Four were correctness-of-craft:

- `additive()` chunks over TIME, not harmonics: peak RSS **1784 -> 1103 MB**
  on a 163 s match, and **bit-identical** (the sum is along the harmonic
  axis, so chunking time changes no arithmetic).
- Frame holds are differences of absolute frame indices, so they telescope:
  both masters are now **frame-exact** (3909 and 4227 = round(duration x 24)),
  and the test asserts equality rather than a half-second tolerance.
- `ansi_png` font loading warns on stderr when it falls back, honours
  `ARCADE_FONT`, and documents that pixel determinism is scoped to the face.
- `extract()` refuses a directory without moves.txt and both warriors,
  instead of rendering two minutes of empty core.

**The match-002 WAV is bit-identical after all seven** (0 of 7,182,420
samples differ) — none of the fixed paths exists in a three-tie match, which
is the expected result rather than a lucky one. match-001, a decided match,
is the one that exercises the kill path on real data: hitstop exactly zero,
Bb at 1.000 of the drop's spectral peak, two tie drops and one kill drop
correctly distinguished, peak -0.50 dBFS, crest 13.6 dB, bar spread 17.6 dB.

### Review round 2 (Kimi supplement)

Two MUSTs, both real, both invisible to the tests that existed:

- **An ice loser went on ringing after it died.** The reverb send runs after
  `_lay_moments` cuts the loser's bus, and a 4177-sample tail at 0.70
  feedback smears straight through the cut. It only affects ice, because
  ember has no send — and every kill fixture in the suite had an EMBER loser,
  which is exactly why nobody saw it. Fixed by re-cutting after the reverb
  (`_cut_losers`, deliberately called twice: a send applied to a muted bus
  un-mutes it). The new test seats the dwarf as warrior A so the imp — ice —
  is the one that dies; it fails on the pre-fix code.
- **The motif, the verdict and the elimination payload bypassed
  `score.note()`**, so the anti-noise tests could not see them at all, and
  the motif's offsets were hand-typed floats (0.222 / 0.444 / 0.889) that
  were near the grid without being on it. All three now schedule through the
  same path as every other layer. The elimination payload is recorded as
  layer `moment` — the ONE onset in the piece that is legitimately off the
  grid, because it lands with the picture's freeze — and the test now
  asserts that every exempt onset IS an elimination landing, so the
  exemption is audited rather than absent.

Four SHOULDs: the scratch workdir is removed in a `finally` (it leaked
thousands of PNGs per render, including on a failed mux); the unconditional
`/tmp/cw-atlas-verify/preview.mp4` write is gone and the excerpt is now an
opt-in `--excerpt FILE[:SECONDS]` flag; `extract()` restores the caller's RNG
state and `sys.path`; the tie-drop peak search clamps to the curve and
actually tests for an empty slice (the old `hi = max(lo + 1, ...)` guard
could never fail). v1's corpses are gone from `record_cw.py` —
`saw_stack`, `bell`, `glide`, `curve`, `PAN`, the duplicate `hashnoise`,
`env_ad`, `norm`, `sine`, and the stale docstring section describing a
scheme that now lives in `score_cw.py`. The file is 420 lines from 700.

One NICE: `metrics_for` no longer returns cells wider than the raster or
negative margins at degenerate sizes; the unused bold font is deleted.

**Partial on K6 (lazy numpy).** `score_cw` keeps its top-level numpy import:
it is a DSP module whose every function needs it, and threading an accessor
through would add a call per function to buy what `importorskip` buys
exactly. Instead both test files skip cleanly without numpy, which is the
actual goal — `uv run --with pytest pytest test_record_cw.py test_score_cw.py`
with no numpy and no Pillow now reports **11 passed, 11 skipped**, and the
eleven that run are the timeline contract.

One more found while verifying the fix, and it is the same class Codex
named: the post-drop **relock kick was labelled `kick`** and so was checked
against the kick pattern's four slots — but the DECISION says it lands on
whichever 1/16 comes next, which is usually not one of them. It passed only
because in the suite's fixture that 1/16 happened to be a kick slot; on
match-001's real kill it did not, and the strict check caught it. The relock
is now its own layer with all sixteen slots allowed, and `_offgrid` is
faction-aware so a blind union can never launder this again. Relabelling
changed no audio (0 of 15,534,814 samples), so the rendered masters stand.

## Addendum — final review round (Grok + DeepSeek), 2026-08-14

Two more reviewers, eleven items, one MUST. The MUST is the most
instructive bug of the whole chapter because three separate failures came
out of a single shortcut in argument parsing.

**The `--excerpt` leak (MUST).** Positionals were taken as "every argv
entry that does not start with `--`", so in
`record_cw.py room out.mp4 --excerpt clip.mp4:8` the flag's VALUE became
the third positional — which was the scratch-directory argument. Three
consequences, all from that one line: `keep` became truthy so the
`finally` block skipped `rmtree`; a directory literally named
`clip.mp4:8` was created in the caller's working directory; and ffmpeg was
handed `clip.mp4:8/frames/frames.txt`, which it parsed as a URL and
rejected with "Protocol not found". Reproduced before fixing: **621 MB**
left behind in the CWD and no mp4 at all. The feature had never worked.

Flags now consume their own values (`parse_args`), unknown flags and
missing values are refused rather than absorbed, `--flag=value` works, and
the third positional — the actual source of the collision — is gone
entirely; `--keep-scratch` was always the real spelling. `parse_excerpt`
splits `FILE[:SECONDS]` from the right and only treats the tail as a
duration if it reads as one, so a colon-bearing path survives while
`clip.mp4:20s` is refused at parse time instead of after a two-minute
render. `test_the_excerpt_is_opt_in` monkeypatches `excerpt()` and so
could never have seen any of this; its new sibling runs the real path from
an empty CWD and asserts the directory is left exactly as it was found.

**First blood is per ROUND (SHOULD).** `analyze` kept only
`tl.of('first-blood')[0]`, but the picture's first-blood field resets at
every round start. A three-round stalemate therefore got its crash in
round one and nothing at the opening of rounds two and three. Per-round is
the law — it is what the picture does — so `first_blood_bar` became
`first_blood_bars`, a set.

**One arithmetic for the loser's window (SHOULD).** The suffocation ramp
computed `int(land*SR) + int(sweep*SR)`; the post-reverb re-cut computed
`int((land+sweep)*SR)`. Those disagree by a sample whenever both fractions
carry, which would have put one un-muted sample between a ramp that
reached zero and a cut that started late — a click whose existence
depended on the exact time of a particular kill. `_loser_window()` is now
the one place that boundary is computed, and the test sweeps times until
it proves the carry case is real rather than hypothetical.

**The round-boundary step (SHOULD).** `_cut_losers`'s docstring claimed it
was "called twice on purpose"; it is called once, after the reverb, and
the docstring now says why that is the correct place. The geometry the
wrong doc was hiding is real: the mute stops at `until` because past that
the same buffer belongs to the NEXT round, so a kill landing about a
second before the round ends left a reverb tail still loud at `until`,
reappearing out of silence as a step. It now ramps back in over 30 ms —
the tail is not the problem, the discontinuity was.

**The limiter's block edges (SHOULD).** Gains were derived from each
block's PEAK but evaluated at each block's CENTRE, so samples near a
block edge were multiplied by a gain interpolated toward their quieter
neighbour — under-ducked exactly where a loud block begins. The global
trim then caught the escaped peak, and the trim is global: on a synthetic
case with one loud block among quiet ones, the bed lost **4.21 dB** to pay
for a peak four blocks away, which is precisely the quiet room the whole
mix law exists to protect. Every sample is now clamped to its own block's
gain; the interpolation still smooths the ride but never upward.

**The hitstop's missing fade (NICE, and not minor).** `if a - f > 0`
skipped the fade-OUT for any gate opening within one fade length of sample
zero. The fades exist so the silence arrives as a cut rather than a click,
and the elimination silence is the signature moment of the format. Fades
now shorten at the buffer's edges instead of vanishing.

**The audited exemptions are now two, and both are named.** The draw
outro's drone bypassed `score.note()` entirely, so the anti-noise test
could not see it at all. It cannot be on the grid — a draw's dissolve
begins when the picture's end wash begins — so it is registered as a
second exemption under its own layer, and the test asserts there is
exactly one per drawn end cue. An exemption the tests cannot see is not an
exemption, it is a hole.

Also: the tautology `if kind != 'breakdown' or True:` is gone and the
breakdown's pad is pinned as intended behaviour (the room thins, it does
not empty); the perc test no longer accepts "step or step−1", which was
slack wide enough to launder a genuinely wrong step whenever its
neighbour was legal, and now asks which step of that faction's grid
actually produced the phase; `np.interp` over `tl.metrics` is guarded
monotone rather than assuming a hook we do not own; and `render_frames`
restores `sys.path`.

Both reviewers independently cleared the tie-drop guard, the relock, the
sidechain math, FDN stability, `_fade_bed` ordering, master length, and
frame telescoping.

# Music consult — from sonification to a TRACK (2026-08-14)

You are one of two consultants (an Opus agent and a Kimi agent) asked to
redesign the soundtrack system for the Core War broadcast master. Write
your proposal to a file as instructed by your dispatcher, one to three
pages. Do not edit any repo files.

## What exists (read these)

- `engine/record_cw.py` — the current recorder: deterministic event
  timeline (EVENT_HOOK from the real animation loop — every bomb, split,
  death, elimination, verdict with exact broadcast wall-times), numpy
  synthesis, limiter, ffmpeg mux. The plumbing is GOOD and stays.
- `design/corewar-mockups/atlas/soundtrack-spec.md` — the v1 scheme +
  build addendum.
- Watch/listen if you can: /tmp/cw-atlas-verify/preview.mp4 (20s dense
  stretch) and kill-master.mp4.

## The verdict on v1 (user)

"The setup is right and cool but it's borderline noise." Correct: v1 is
SONIFICATION — events trigger sounds directly. 38,612 events in a 163s
match means texture without music. Architecture stays; the musical brain
is what gets replaced.

## The direction (user): a track system inspired by

techno · Fred Again.. · Brian Eno · Charli XCX · Grimes

Interpretation latitude is yours, but the core shift is mandatory:
**a fixed musical grid (tempo/bars/sections) that the battle CONDUCTS
rather than plays.** Think: the match is an arrangement — events are
quantized to the grid, battle state (ground share, process counts,
momentum, phase) drives intensity/layers/filters/automation, and the
choreographed moments become song moments:

- load-in → intro / first build
- battle stretches → the groove, intensity from the momentum metric
- fork bloom → riser/fill
- elimination hitstop → THE DROP (the silence is already perfect — keep
  absolute silence, then the payoff)
- round verdicts → breakdown / interlude
- match end, win → finale in the winner's colour
- match end, draw → Eno outro, beatless, both factions dissolving into
  the shared ember drone

Faction identity must survive musically (ember vs ice = two recognizable
voices/production characters; the user hears who is winning with eyes
closed). The bombing STRIDE PATTERNS are rhythmically interesting — a
stone at stride 4, an imp carpet — quantize them into percussion
patterns/hats/chops rather than one-hit-per-bomb.

## Hard constraints

- Everything SYNTHESIZED in numpy — no samples, no external audio files.
  (Vocal-ish textures are allowed if synthesized: formant blips, pitched
  chops of synthesized material.)
- Deterministic: same match → byte-identical WAV. sin-hash for texture,
  no RNG.
- The timeline arrives as-is (events with wall-times); you may quantize,
  gate, aggregate, look ahead (the full timeline is known before synthesis
  — offline render, so builds can anticipate drops).
- Total duration = the broadcast's, exactly. ~163s for match-002.
- Rounds are ~53s each: your structure must work when a "song section"
  is that short, and when a match has kills (shorter rounds) or is one
  long stalemate.
- Mix law from v1 stays: quiet room, events puncture, real limiter,
  crest factor stays healthy. Laptop-speaker sane.

## What to deliver in your proposal

1. The track system: tempo/grid choice, section map driven by match
   phases, and the event→music mapping table (every timeline event type:
   what happens musically, quantized how).
2. The two faction production identities (be specific: waveforms,
   register, processing — buildable in numpy).
3. How intensity/automation derives from battle state (which signals,
   mapped to what).
4. The three signature moments spelled out: load-in, elimination drop,
   draw outro.
5. Anything in the influence palette you're deliberately NOT taking, and
   why (taste is choices).
6. Implementation sketch: what changes in record_cw.py's synthesis layer,
   what stays.

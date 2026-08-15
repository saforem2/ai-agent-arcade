# Atlas animation spec — approved set (user, 2026-08-14: "yes to all")

Seven motions, all inside house law: every time-varying term is a
deterministic function of (addr, cycle, t) — sin-hash phase, no RNG in the
render path; FX queues stay capped; everything except §7 pacing gates off
under ARCADE_REDUCED_MOTION=1 (pacing is content, not motion). The atlas
idles QUIET — dark field, slow ambient wave only — so events own the room.

## Signature moments (event-driven)

1. **Drop-pod load-in** (round start). Empty calm core → warrior A's code
   scanline-writes itself in at its offset (ember), one-beat dwell, then
   warrior B (ice). Teaches random placement wordlessly. Budget ~1.5s
   total; reduced-motion: both appear instantly.

2. **Full-core death wave** (elimination). Keep the hitstop + shake
   (unchanged constants — a 23-row field shaking reads well). The loser's
   territory cools in a front sweeping out from the kill address across
   the WHOLE visible core, wrap-aware at the edges. This is the atlas's
   flagship frame; the camera tier could never show the entire front.

3. **Wrap spark**. Any process or bombing run crossing 7999→0: a spark
   exits the bottom edge and re-enters the top edge (one cell each, one
   or two frames). Teaches circular memory. Cheap; FX-queue bounded.

## Ambient texture (rhythmic, not noisy)

4. **Faction tempo**. Process dots pulse on deterministic ticks whose
   rhythm derives from behaviour: a moving PC (imp train) reads as a
   crawling white worm; a stationary PC (stone/bomber engine) thumps on
   its fire cadence. Phase from (addr, cycle) — byte-stable. Experts read
   strategy by rhythm; newcomers read "two different creatures".

5. **Bombing drumbeat**. Each bomb = one-frame white spark on its dot +
   a 1-char micro-ring. At atlas grain these are single dots — legible,
   not noise (the camera tier had to suppress per-bomb ticker entries;
   the visual drumbeat replaces that information). FX_CAP applies;
   fast_forward never prunes semantics, only FX.

6. **Contested-border sizzle** — AMENDED after the mockup gate (notes.md
   "conflict to resolve"): contested cells do NOT use white; near-white
   is the process marker's exclusive colour and fronts are exactly where
   processes live. The gated treatment instead: plate lifts toward SLATE
   (neutral, off both faction ramps — nothing averaged) with a sin-hash
   jitter in (cx, cy, t) — that jitter IS the sizzle — and the block's
   own dots brighten in the majority owner's hue. Under reduced motion:
   steady lift, no jitter.

## Pacing (invisible juice)

7. **Momentum-aware playback**. Replace the uniform ~55s/round ramp:
   fast through quiet stretches, ease down when process counts or ground
   share swing sharply, crawl (1 cycle/frame, existing constant) into a
   kill. Momentum metric must be derived from the transcript
   deterministically (e.g. windowed deltas of proc count + owned cells).
   A full 80000-cycle tie must still land inside the ~90s broadcast
   budget. NOT gated by reduced motion.

## Order of work

Core: 1, 2, 4, 5, 7 — §5's drumbeat was PROMOTED from add-on to core at
the mockup gate: after the per-footprint crater fix a single fresh bomb
lifts its plate ~7%, so the spark is the only place an individual bomb
is visible at all. Add-on: 3 (wrap spark). Free: 6 (part of the
contested encoding).

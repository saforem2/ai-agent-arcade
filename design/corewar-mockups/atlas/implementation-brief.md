# Implementation brief — atlas becomes the board (2026-08-14)

User decisions, final:

1. The **atlas** (whole core, stationary, mockup-gated in this directory)
   is the ONLY board. Default and only field tier.
2. **grand and camera are DELETED** — the 104x84 full-grain tier, the
   activity-following viewport, camera easing/deadband, ring-map row,
   the comet grammar and its moats, chrome_plan's tier juggling. All of
   it. One clean deletion; git history is the archive.
3. The **strip is REVAMPED**, not deleted: below the atlas floor it shows
   header + a one-row whole-core heat bar (the ring-map material,
   promoted — majority-hue blocks, brightness = mean heat, no [ ]
   brackets since there is no camera to locate) + score/status. Even at
   the 20x4 floor the battle stays visible as a living bar.
4. Ladder: atlas (default; floor = the atlas's own geometry) → strip →
   refuse below 20x4. size.txt/ctl `size` handling simplifies
   accordingly (accept and ignore legacy values gracefully — never
   crash on an old size.txt).

## Sources of truth (read all before coding)

- `atlas-mockup.py` + `atlas-{front,mid,late}.png` in this dir — the
  gated look: geometry, encoding, faction bars, header teaching line
  ("all 8,000 cells of memory, one dot each"), lowercase plain voice.
  The mockup's encoding decisions are the spec; its notes.md (if
  present) records rejected variants — do not relitigate them.
- `animation-spec.md` in this dir — the seven approved motions.
- `engine/tui_corewar.py` — the file to transform. Everything that is
  not tier-specific survives: file-bus contract, transcript parsing,
  re-simulation, Scene, apply_event, pacing skeleton, ctl handling,
  replay button, reduced-motion gates, byte-stable determinism, the
  strip's refuse floor, match_line() (bus/ledger API — tests pin it;
  display strings only may change).
- `engine/test_tui_corewar.py` — update to the new ladder; keep the
  house test style (animated-path coverage, not just static renders).

## Corrections to the mockup (user + director review)

- **Late-game wallpaper**: cold territory must decay toward a whisper
  of hue (steeper tint decay / lower saturation floor) so active fronts
  dominate a saturated late frame. The mid frame's balance is the
  target; the late frame as mocked is too loud.
- **Round ledger returns**: the animated-rounds-only ledger
  (`1 tied · 2 live`, never spoiling un-animated rounds) must live in
  the status area — rotate or slot it; a viewer joining late needs the
  series state at a glance.
- Keep DECISION.md's plain-language status strings where they still
  apply (workshop/locked/verdict/over states, elim declared during the
  beat, thousands separators, player names in faction hues).

## The seven animations (animation-spec.md, priority order)

Core: (1) drop-pod load-in, (2) full-core death wave + existing
hitstop/shake, (4) faction tempo pulses, (7) momentum-aware playback.
Add-ons: (3) wrap spark, (5) bombing drumbeat micro-FX. Free: (6)
contested sizzle (part of the encoding). All deterministic (phase from
addr/cycle — no RNG in the render path), FX-capped, reduced-motion
gated except pacing. An 80,000-cycle tie must still finish inside the
~90s broadcast budget; headless renders stay byte-identical for
identical (scene, t).

## Acceptance

- `uv run pytest engine/test_tui_corewar.py` green; full
  `uv run pytest engine/` green (no collateral damage to chess/xiangqi).
- A replay of `games/corewar/match-002` in an 87x23 pane: stationary
  field, whole core visible, all three rounds animate inside budget,
  no visual jumping, ledger + faction bars correct throughout.
- The same replay in a 40x4 pane: the revamped strip, live heat bar.
- Header docstring rewritten to describe the new identity (it is the
  design record; keep its density and cite the atlas gate).
- No commits — leave the working tree for the user's review.

## Rulings on notes.md's open questions (director, post-gate)

- **White collision**: settled for the mockup's treatment; §6 in
  animation-spec.md is amended. White means "a process is here" and
  nothing else, ever.
- **Drumbeat**: promoted to core work (spec updated) — it is the only
  visibility a single bomb has.
- **Grand**: already decided dead (user) — the atlas replaces it. The
  ladder is atlas → strip → refuse. Delete grand with the camera.
- **Process marker cap**: no artificial ceiling. Markers merge by block,
  which is the natural bound; a SPL flood lighting a region white is a
  legitimate read ("their code is everywhere"). MAX_COMETS dies with the
  comets.
- **Wrap seam hint on the static frame**: not now; §3's wrap spark
  covers the moment. Revisit only if replays prove confusing.
- **Late-frame loudness vs true saturation**: both are right. Keep
  occupancy honest (every dot lit is the true state) but let COLD owned
  territory's hue decay further toward the deep dim ramp so the two
  live fronts dominate the saturated field — atlas-mid's balance is the
  reference. Verify against match-002 round 1 late replay.
- **Stalemate front visibility + "held" wording**: check both against
  the full match-002 replay (it IS a three-round stalemate); report
  findings, don't redesign unprompted.
- **Match-draw ending**: APPROVED (user) — replace the quiet-dim tie
  treatment: on a drawn match both armies' territory cools to embers
  together, the whole battlefield going dark as one slow shared fade
  (reduced-motion: cut to the cooled state). Keep it slow and dignified
  — a draw is "the floor held", not a failure state. The winner-wash
  ending for decided matches stays.

# Atlas mockup brief — the whole core, stationary, at pane size

Decision (user, 2026-08-14): the Core War board's default identity flips.
The activity-following 1:1 camera (DECISION.md) is DEMOTED to an opt-in
zoom. The new default is the **atlas**: the entire 8000-cell core, drawn
stationary at **1 dot = 1 memory cell**, sized to a normal herdr pane
(~87x23). The two complaints it must kill:

1. the field slides up/down as the camera chases heat (disorienting);
2. the 2-cell process comets + moats don't read as "programs running"
   and cost space.

This RELAXES the locked "1 memory cell = 1 braille cell" rule *for the
atlas tier only* — sanctioned by the user. The known objection (color
averaging fabricates a muddy third hue at contested borders) must be
answered by design, not ignored: **never average factions**. Majority
owner takes the braille cell's fg; a genuinely contested cell (both
factions present within the 2x4 block) gets an explicit contested
treatment (e.g. deterministic white/bright flicker) that reads as
"fighting here", never as a mixed color.

## Geometry

- Core is 100 cols x 80 rows (address = row*100 + col), CORE_SIZE 8000.
- 1 dot per cell → field = **50 chars wide x 20 chars tall** (2x4 dots per
  braille char = 2 core cols x 4 core rows per char).
- Target frame: **87x23** (the real pane: header + field 20 + up to 2
  bottom rows). Surplus columns are calm margin (house style) — or spend
  a few on a right-side faction panel if it earns its place; your call,
  argue it.
- Bottom chrome direction the user liked (from an accepted preview):
  per-faction bars, e.g.
      round 1 of 3 · step 5,185 of 80,000
      KIMI  ██████░░░ 41% · 12 running
      CODEX ████░░░░░ 33% · 2 running
  That's 3 rows; at 23 total rows with header + 20 field rows only 2 fit.
  Resolve it: compress (one score row + status), shave, or argue the
  frame wants 24 rows. Show what you choose.

## Encoding questions you must resolve (and show)

Each braille cell now summarizes 8 memory cells. Decide and demonstrate:

- **density**: what do the 8 dots mean? Recommended start: dot i lit iff
  cell i is "marked" (owned/written, above an age threshold) — so density
  IS occupancy and the dwarf's stride-4 lattice, an imp train, a bomber
  carpet each produce their own visible texture. Craters = dots off
  (absence still reads as damage). Untouched core needs some ambient
  presence — chess's DENS_D everywhere may be too loud when dots also
  mean occupancy; try near-empty ambient with the slow wave.
- **heat**: brightness/saturation from the block's max heat (mean washes
  out fresh single-cell events).
- **processes**: the comet grammar dies here. A process is ONE cell = one
  dot. Proposal: the braille cell holding a PC renders FULL-bright
  near-white (the brightest object on the board, as before), pulsing on a
  deterministic tick; running counts live in the faction bars. Multiple
  PCs cluster naturally (imp trains become a white worm). Show it.
- **impacts/events**: keep flash grammar at braille-cell grain, bounded.
- **contested cells**: the explicit treatment described above.

## Materials & constraints (unchanged house law)

- Palette/constants from `engine/tui_corewar.py` / `tui_dots.py` verbatim
  (PANEL, SQD, AMBIENT, EMBER/ICE ramps, W_SOLID, TEXT, TDIM, LABEL,
  WINDOW_BG). No new constants unless unavoidable — record any.
- One fg per braille cell; bg per cell OK. Deterministic everything
  (sin-hash noise, no RNG). Every line fits the width — clip, never wrap.
- Plain-language chrome, lowercase house voice, player names in faction
  hues, thousands separators, zero jargon, zero ornament on the field.
- stdlib + Pillow only (Pillow just for the PNG capture, 9x18 px/cell,
  same as mockup-corewar.py).

## Battle data

Re-simulate through the real engine (`engine/corewar.py`, Battle) exactly
like `mockup-corewar.py` does — read that file first. Use match-002's
locked warriors + transcript:
`arcade/games/corewar/match-002/` (warriors/, moves.txt: round 1
seed=18042764757958431666 off=549,6448, tie at 80000). Render TWO moments:
mid-battle (~cycle 3000, structures forming) and late (~cycle 40000,
saturated field) — the atlas must stay legible in both.

## Deliverables (all in this directory)

- `atlas-mockup.py` — deterministic generator, run with
  `uv run --with pillow python atlas-mockup.py`
- `atlas-mid.ans/.txt/.png`, `atlas-late.ans/.txt/.png` — 87x23(or 24)
  frames at both moments
- `notes.md` — encoding decisions, what you tried and rejected (the house
  self-review-rounds format; see ../notes.md), open questions for the
  implementation pass, and your honest verdict: does the atlas read?
  Where does it fail?

Do NOT touch `engine/tui_corewar.py` or any repo file outside this
directory. This is a design-gate artifact.

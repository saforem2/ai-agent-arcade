# Core War furniture mockup — the core IS the field

Design-gate artifact (STREAM E phase 1). A static mid-battle frame of a real
imp-vs-dwarf battle in the arcade's braille dot-field material, for review
side by side with the chess checkpoint before any `tui_corewar.py` work.

Generator: `mockup-corewar.py` — deterministic (battle seed fixed, no
network), stdlib + Pillow. Run from this directory:

    uv run --with pillow python mockup-corewar.py

(The xiangqi mockup scripts were stdlib-only and captured via real terminal
screenshots; this one renders its PNG synthetically, but at the checkpoint
captures' exact cell metrics — 9x18 px per terminal cell — so the grain
compares 1:1. Pillow is used the same way as
`docs/xiangqi-studio/kimi/ansi2png.py`.)

Outputs: `mockup-furniture.ans` (truecolor ANSI frame), `.txt` (stripped),
`mockup-furniture.png` (104x84 cells = 964x1540 px), `side-by-side.png`
(chess checkpoint left, this frame right).

## The frame

- Battle: `IMP` vs `DWARF` (both module-level sources in `engine/corewar.py`),
  re-simulated step by step through the real engine.
- **seed 1, snapshot after cycle 1000** (both warriors alive, both visibly
  active). Offsets drawn from the seed: imp at 1100, dwarf at 5862.
- State at snapshot: imp trail = 1001 owned cells (rows 11-21, the hot front
  at rows 19-20); dwarf = 334 DAT bombs at stride 4 (rows 58-72, fixed
  columns because gcd(4,100)=4), 3 hot engine cells + its bomb magazine;
  1 process each (imp pc 2100, dwarf pc 5863).
- Ownership = last writer OR executor of the cell; age = cycles since.

## How 8000 cells map to the pane

The core is circular memory; the mockup lays it out **row-major, 100 columns
x 80 rows** (8000 = 80x100 exactly; address = row*100 + col). Landscape
orientation matches pane shape; circular adjacency shows as bottom/top edge
continuity (the wrap is honest: address 7999's neighbour 0 is one row away).

**One memory cell = one braille cell.** A cell costs 2x4 = 8 dots, density
0-8 through the exact BAYER kernel — the §8.1 unlock applied at memory-cell
grain. Per-cell foreground colour is what a braille cell has, so this is the
finest mapping that keeps per-cell ownership tint honest.

### Grand tier

Board = 100x80 char cells + 4-col label gutter + header/blank/ruler/footer
rows = **104 cols x 84 rows**. That is the mockup's frame. Fits a pane from
~104x84 up; surplus becomes calm margin, as with chess.

### Cozy tier (87 cols) — the whole core does NOT fit

100 core columns + 4-col gutter = 104 > 87, and 80 rows + 4 chrome rows
doesn't fit a ~56-row window either. There is no geometry tier that shows
all 8000 cells at 87x56 with per-cell colour:

- 2x2 dots per memory cell (4 dots, 2 memory cells share one braille cell):
  board = 100x40 chars — still 100 > 87 columns, and paired cells would
  share one fg, so ownership tint stops being per-cell. Rejected as default.
- 1x2 dots per memory cell (4 cells per braille cell): 50x40 chars, fits —
  but 2 dots/cell and 4-way colour sharing make it a radar-scope overview,
  not the board. Candidate for an attract/overview mode only.
- **Recommended: an activity-following viewport** at cozy — an 80x48-cell
  window onto the core (wrap-aware), centred on the hottest recent event,
  with the same 1-cell-per-braille-cell mapping inside. The full-core view
  is the grand tier's identity; the cozy tier is a camera, not a thumbnail.

## Visual encoding (all constants reused, zero new)

Palette is `tui_dots.py`/`tui_xiangqi.py` verbatim: PANEL, SQD, NEUTRAL,
AMBIENT, ICE, EMBER, W_SOLID, TEXT, TDIM, LABEL, plus WINDOW_BG (the
xiangqi face-window dark) as the crater pit floor. No new constants.

- **untouched core**: density 2.0 (chess's dark-square tier DENS_D), AMBIENT
  dots on the SQD plate. Calm grain.
- **owned cell**: heat h = exp(-age/TAU), TAU = 300 cycles.
  density = 2.0 + 2.6h (cap 7); tint = min(0.75, 0.18 + 0.57h) toward the
  owner's hue from an AMBIENT→NEUTRAL base that warms with h;
  brightness scale = 0.95 + 0.45h. Cold-owned sinks to a whisper of hue at
  near-field brightness — ownership is a haze, never wallpaper (§8.3's
  SAT_CAP discipline). Hot = dense, saturated, bright.
- **DAT bomb crater**: a literal clearing — zero dots, bg dropped from SQD
  toward WINDOW_BG. A fresh crater GLOWS from its pit: bg lifted toward the
  owner's hue by 0.45h² (squared, so only the freshest wounds carry light).
  Cooling = the glow dies, the pit remains: scars persist, heat doesn't.
- **process (PC)**: a 2-cell solid comet — head (the PC cell) FULL 8 dots at
  blend(hue, W_SOLID, 0.72), tail (PC+1) at 0.30; the head end points at the
  process. 1-dot keep-out moat (§8.2) clears COLD ground only: where the
  comet sits inside its own hot body (dwarf's engine, the imp's fresh
  trail), the moat is skipped — cutting it through hot cells shredded them
  into orphan dots (the §11 "dangling dots" failure, hit and fixed in
  self-review round 5). Tail wraps to the next core row at column 99, as
  memory does.
- **chrome**: header = warrior names in their hues + `· core war · seed N`
  (the seed is the match id — functional, it identifies the replay). Footer
  = `cycle N` + per-warrior process counts (the CW equivalent of "to move").
  Ruler: left labels every 10 rows (row base addresses 0..7000), bottom
  ticks every 10 columns (0..90), LABEL colour, outside the plate — kept
  because memory addresses are this game's move coordinates (battle.json,
  offsets, and debug peeks all speak absolute addresses); functional, not
  ornamental. Nothing else: no banner text on the field, per the §0
  zero-ornament mandate.

## Process vs crater at a glance

The two reads the frame must keep unambiguous:

- **Process** = the brightest object on the board: solid dot mass,
  near-white, moat-isolated, always 2 cells. You find it by luminance.
- **Crater** = absence: a pit darker than the plate, dotless; only fresh
  ones glow, and they glow from *below* (bg) not *above* (dots). You find it
  as damage in the grain, or as the glowing front of an active bombing run.

Ownership haze sits between: dots present, hue whispering, never solid.

## Self-review rounds (what changed and why)

1. **Trail wallpapered.** Cold-owned cells rendered at level ~2.7 /
   tint 0.36 / 0.8x — the whole 10-row imp trail glowed as a gold slab.
   Fix: cold-owned sinks to field level (2.0 base, AMBIENT-based tint).
2. **Single-cell process markers failed the glance test** (2x4 dots among
   8000). Fix: 2-cell comet, head near-white. Also: craters rendered as
   dots-in-a-pit contradicted "cleared" — made them literal holes.
3. **Crater glow too loud** (linear 0.55h: a forest of glowing bars that
   outshouted the processes). Fix: 0.45h² — only the freshest wounds light.
4. **Cold pits too weak** (PANEL vs SQD ≈ Δ8). Fix: pit floor = WINDOW_BG.
5. **Two engine-truth bugs found by zooming**: (a) dwarf's bomb magazine is
   a DAT its own `add` rewrites every loop, so "DAT + age>0 = crater" ate
   the magazine — craters now exclude initial warrior bodies; (b) the moat
   cut through the hot body left 2 orphan dots (§11's dangling-dots
   failure) — moat now clears cold ground only.

## Open questions for the full renderer (tui_corewar.py)

- **SPL beat**: a new process buds off a parent cell. Proposal: spawn_debris
  fork (the §8.2 particle system speaks dot coordinates already) — a small
  outward burst from the parent comet, then the new comet condenses one beat
  later. Process-count cap: MAX_PROCESSES is 8000; comets can't all render.
  Cap drawn comets (hottest N, rest as warm ticks?) — needs a real decision.
- **Death beat**: a process executes DAT → its comet collapses into a fresh
  glowing crater (the crater glow already exists; the collapse is a 2-3
  frame dissolve of the comet mass into the pit). Elimination = the warrior's
  last comet falls; the field keeps its scars.
- **Replay / re-simulate**: the transcript is seed + offsets; the renderer
  re-runs `Battle` at display speed (the engine docstring's renderer
  contract). Snap-to-live rule from §8.7 applies when cycles arrive in bulk.
- **Live pacing**: 80000-cycle cap; at 60 fps one cycle/frame is a 22-minute
  battle. Speed tiers and the cycle counter's role need product thought.
- **Attract mode**: re-run a classic battle at high speed as the demo; the
  density wave (WAVE_PERIOD 30, AMP 0.5) runs on untouched field only —
  engine/body/comet cells are calm pockets (§8.6), or the machine shimmers.
- **Cozy tier**: viewport camera (above) is unbuilt; what it follows
  (hottest write? active process? user-pannable?) is open.

## Juice pass (2026-08-14)

- **Bomb-impact choreography**: a fresh crater now lands like a chess
  capture — a white-hot flash on the pit cell (FLASH_S 0.28s), a fast
  shockwave ring (wider and quicker than the SPL birth ring), and a tight
  spark burst. The mockup's crater glow alone read as state, not event;
  captures are the game's punctuation and earn the same flash-and-settle
  grammar chess uses. All lifetimes < 1s so effects prune inside their own
  draw functions, and the queues are capped (FX_CAP 120, SPARK_CAP 160)
  because the no-render fast_forward path never prunes.
- **Faction materials**: ember vs ice as material behaviour, not hue alone.
  A deep ramp (EMBER_DEEP→EMBER, ICE_DEEP→ICE with heat) makes cold
  territory read brick-red vs steel-blue while hot territory burns at the
  full hue; ember FLICKERS (sin-hash noise in addr+t), ice GLINTS (a sparse
  sparkle on a 3Hz tick, held between ticks — ice is still, ember is
  restless). Craters follow suit: ember smolders (the pit glow breathes),
  ice frost holds slightly brighter and steady.
- **Elimination hitstop + shake**: adapted from fighting games — the kill
  shot freezes the frame for HITSTOP_S 0.14s on a winner-hue flash at the
  kill address and kicks the viewport (SHAKE 1.2 cells, decaying 0.80 per
  frame), then the cooling front plays. The measure is unchanged: a glance
  must say who died — the freeze buys the glance its moment.
- **Determinism constraint**: every time-varying term in the render path is
  a pure function of (addr, t) — sin-hash noise, never RNG — so headless
  renders stay byte-identical; `random` runs only in spawn functions and
  the per-frame shake roll (both outside the cell encoding). All of it is
  REDUCED_MOTION-gated.

## Plain voice + bottom-stack layout (2026-08-14)

Consultation record: three proposals plus a host strawman, all in
`/tmp/cw-design/` — grok.md (compact spectator cut), codex2.md (Tharp-spine
newcomer read), the internal kimi planner (transcript in the session log),
host-strawman.md (2:1 downsample layout). Synthesis frozen in
`/tmp/cw-design/DECISION.md`, which replaced the chrome half of this
document's open questions and was implemented as spec'd.

- **Rejected: the 2:1 downsample tier (host strawman).** Killed by all
  three consultants; the planner's argument is decisive: pairing two memory
  cells into one braille cell fabricates colour — ember+ice averages to a
  muddy gray that reads as cooled/neutral — exactly at contested borders,
  where honesty matters most; a crater under a live cell stops being a
  hole; a comet dims. The 1-cell = 1-braille rule stays locked. No
  downsample tier, ever, short of a hypothetical clearly-labeled opt-in
  "atlas" (not built). Also rejected: the sidebar (steals columns from the
  camera on wide-short panes; the bottom stack won 3-0), a ticker entry per
  bomb impact (dwarf bombs constantly — noise; the ticker carries rare
  events only), and codex2's ALL-CAPS voice (house chrome stays lowercase).
- **Bottom stack.** Field sits adjacent to the header; the info cluster
  lives between field and status — the broadcast lower third. Per tier:
  grand = header / field / ruler / score / status (104x84 unchanged);
  camera = header / field / [ruler] / [ring-map] / [score] / status with
  drop order ruler → ring-map → score as rows shrink (the status never
  drops); strip = header / status, hard floor now 20x4. TOP/BELOW died as
  fixed constants: `chrome_plan(cols, rows, tier)` is the single source of
  which chrome rows exist, consumed by both fit_geometry (BW/BH) and
  render — chrome is never derived twice (the exact-fill/button-offset
  flicker class of bug lives exactly there).
- **The label table** (exact strings, lowercase, player names in faction
  hue, thousands separators): workshop `waiting for two programs`; locked
  `<A> vs <B> · locked and loaded`; battle `round {n} of {total} · step
  {cyc:,} of {cap:,}`; verdict kill `round {n} · {WINNER} knocks out
  {LOSER} in {cycles:,} steps`; verdict tie `round {n} · dead even — both
  survive {cycles:,} steps`; over win `{WINNER} takes the match · {aw}-{bw}`
  (+ ` · {t} tied`); over draw `a dead heat · match drawn` (+ ` — nobody
  died in three rounds` / ` · one win each`); the knockout is declared
  DURING the elimination beat (`round {n} · {WINNER} knocks out {LOSER}`),
  not after; floor refuse ` core war needs 20x4 `. `match_line()` stays as
  the bus/ledger function; only display changed.
- **The score row** (one row, slots in display order): the round ledger
  (`1 KIMI · 2 tied · 3 live`) tallied from animated rounds only — the
  transcript is complete, so naming an un-animated outcome would spoil the
  replay; ground share `ground 41%·58%` (gated `ground —` until 50 cells
  are owned — round-start body noise); running copies `12 vs 3 running`;
  the ticker `last: <event>`. Slots drop as cols shrink: ticker, ground,
  ledger — the running counts never drop. Workshop/locked show the legend
  instead (`colour = ground held · bright comet = running code · dark pit =
  bomb damage`).
- **The event ticker** (scene state, max 8, latest shown): first blood,
  process deaths, eliminations, territory milestones (half /
  three-quarters of the board, per warrior per round, fire-once), fork
  blooms (queue crossing 8, 16, 32, …). Text, not motion — never
  REDUCED_MOTION-gated; byte-stable by construction.
- **The ring-map** (camera tier only): grok's honest minimap — one char
  per bucket of the linear core, majority owner (an eighth of the bucket
  or it's unowned ░), brightness scaled by mean heat, cooled owners gone
  ambient, `[`/`]` marking the camera window. This is the allowed lie: it
  is labeled a map and is a locator only — the field itself is never
  coarsened.
- **Size ladder**: the default flips to cozy (the camera); grand stays
  opt-in at 104x84. size.txt values unchanged (cozy|grand; invalid/missing
  now falls to cozy). Panes that persisted grand keep it.

---

## SUPERSEDED (2026-08-14): the atlas is the board

The tier ladder and the process/comet grammar recorded above are history.
The gate in **`atlas/`** replaced them: the whole 8000-cell core is drawn
stationary at 1 dot = 1 memory cell in a 50x20-char field, so the camera
tier, the grand tier, the ring-map locator, the 2-cell comet and its moats,
and the cozy|grand size ladder are all deleted from `tui_corewar.py`.

Read `atlas/implementation-brief.md` first (the contract and the director's
rulings), then `atlas/notes.md` (the gate record: geometry, the two-channel
dots/plate encoding, the per-footprint intensity lesson, the contested SLATE
treatment) and `atlas/animation-spec.md` (the seven approved motions).

What in this document still stands: the palette and material doctrine, the
heat model (TAU 300, exp decay), the crater-vs-body rule from round 5, the
plain-language chrome and label table, the spoiler-free round ledger, the
event ticker, and the "1 memory cell = 1 braille cell" argument itself —
which the atlas does not overturn so much as satisfy differently: its
mapping is positional and exact, a magnification change rather than an
averaging one, and no colour is ever blended between the two factions.

Where this document says the sidebar was rejected because it "steals columns
from the camera" (3-0), that verdict stands for the camera and does not
transfer: the atlas has no camera to starve. Its field is 50 wide for ever,
so the surplus columns are margin, and the chrome rows deliberately run wider
than the block they describe.

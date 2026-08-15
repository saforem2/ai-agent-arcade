# Atlas mockup — the whole core, stationary, at pane size

Design-gate artifact for the flipped default (`brief.md`). Three static
frames of match-002 round 1, re-simulated through the real engine, drawn at
**1 dot = 1 memory cell** in an 87x23 pane.

Generator: `atlas-mockup.py` — deterministic, stdlib + Pillow. Run from this
directory:

    uv run --with pillow python atlas-mockup.py

Outputs: `atlas-{mid,front,late}.{ans,txt,png}` (87x23 frames; the PNGs are
synthetic terminal captures at the checkpoint metrics, 9x18 px per cell, so
the grain compares 1:1 with the chess/xiangqi checkpoints and with
`../mockup-furniture.png`), plus `variants-{mid,late}.png`, the round-1
evidence sheets.

## Geometry — it lands exactly, with room to spare

The core is 100 cols x 80 rows. A braille char is 2x4 dots, so one char is
2 core cols x 4 core rows and the field is **50 x 20 chars** — the whole
8000-cell core, no camera, no downsample. The mapping is positional and
exact: dot `(dx, dy)` of char `(cx, cy)` **is** memory cell
`(4*cy+dy)*100 + 2*cx+dx`. Nothing is resampled; the atlas is a
magnification change, not an averaging one. That distinction is the whole
argument for relaxing the 1-cell-1-braille rule here.

At 9x18 px per terminal cell the dot pitch comes out 4.5 x 4.5 px — square.
The core renders as a 450x360 px plate whose proportions are memory's own,
which is a happy accident worth keeping in mind for any future pitch change.

### Rows: 23 fits, without shaving anything

    row 0        header — players + one plain-language line
    rows 1..20   the field (the entire core)
    row 21       both faction bars, side by side
    row 22       status — round / step

The brief's liked chrome was 3 rows because it stacked the two bars. They do
not need stacking: each bar is ~36 chars and the pane is 87 wide, so they sit
**side by side on one row** and the count comes out at exactly 23. No 24th
row, no compression, no dropped slot. The frame does not want more rows; it
wants its width used.

### Columns: the field block is centred, the chrome is wider

The field is 50 wide **for ever** — it can never grow into surplus columns,
which is what makes the atlas different from the camera tier. So the 37 spare
columns are not contested resource: the field block (4-col address gutter +
field = 55) is centred at col 16, and the chrome rows start at col 8 and run
wider than the block they describe — the broadcast lower third. A narrow
plate over a wide caption reads as deliberate framing; the same block width
for both read as a frame that had lost its right half.

This also settles the sidebar question the DECISION.md consultation killed
3-0. That verdict was "a sidebar steals columns from the camera", and it
still stands *for the camera*. The atlas has no camera to starve. A sidebar
is still not needed here — the bars fit on one row — but the reason it was
rejected does not transfer, and should not be quoted at the atlas tier.

Address gutter kept, at 5-row intervals (0 / 2000 / 4000 / 6000). One char
row is 400 addresses, so these are landmarks, not coordinates. They earn
their 4 columns by saying "this is memory, and it runs top to bottom" to a
newcomer, and by giving an expert a bearing when reading a debug peek.

## Encoding — two channels that never mix

Each char now summarises 8 memory cells, so the honest objection from
DECISION.md applies with force: averaging EMBER and ICE fabricates a muddy
third hue exactly at contested borders, where honesty matters most. The
answer is to stop asking one channel two questions.

**Dots (fg) answer WHO.** A dot is lit iff its memory cell is owned. The
char's single fg is the **majority owner** of its lit dots, at that owner's
hue on the deep ramp (`HUES_DEEP` → `HUES` with heat). No blend between
EMBER and ICE is ever computed — not at borders, not anywhere. Density is
therefore occupancy, and each warrior's footprint draws its own texture:
CODEX's silk lays visible diagonal cascades (stride 1951 against a 100-wide
row), KIMI's stone scatters (stride 2367) and its imp carpet runs as a
horizontal band.

**Plate (bg) answers WHAT IS HAPPENING.** Craters darken it toward
`WINDOW_BG` in proportion to how much of the block is pitted; fresh damage
glows in its bomber's hue; a genuinely contested block lifts toward `SLATE`
— a neutral, faction-less grey that cannot be mistaken for a mixed colour
because it is not on either faction's ramp.

Heat is `exp(-age/TAU)`, TAU 300 cycles, taken as the **max** over the
block's cells for the majority faction. Mean washes out a single fresh
event among seven cold neighbours, which is precisely the event you want to
see.

### Processes — the comet grammar dies, as predicted

A process is one memory cell, i.e. one dot among 8000. That is invisible.
The marker is promoted to the whole char: **FULL 8 dots at near-white**
(`blend(hue, W_SOLID, ~0.7)`), on a deterministic pulse, priority above the
field. Co-located PCs collapse into one marker, so an imp train is a white
worm and a stone engine is a single steady block — the shapes differ for
free.

This is the atlas's **one admitted lie**: the marker claims 8 cells for
something that owns 1. It is cheap because a PC almost always sits inside
its own warrior's hot code, so the 7 borrowed cells were that colour
anyway. Faction identity survives at the marker (warm-white vs cool-white),
which is why the running counts in the bars are legible against the field.

No keep-out moat. At 1:1 grain the moat cleared background; here a moat dot
would erase a real memory cell from a neighbouring block. Moats die at atlas
grain, and they are not missed — a full white block against deep brick or
steel separates by value alone.

## Self-review rounds (what changed and why)

1. **Warrior names, not player names.** First render put `IRON LOTUS GATE
   vs BLUE SHIFT` in the header, overflowing the frame and clipping the
   bars. The bus's `names.txt` names the *players* (`KIMI CODEX`) and that
   is the house voice; the warrior titles are flavour that belongs in a
   detail view. Fixed at the source (`replay` reads names.txt), which also
   bought back 20 columns of chrome.

2. **`dots = clearing` rejected, decisively.** The brief's recommended start
   was "a crater kills its dot, so absence reads as damage". Rendered side
   by side (`variants-mid.png`), it **guts the board**: CODEX's silk trail
   is mostly DAT bombs, so killing crater dots erased the single most
   legible structure on the field and left fragments floating over grey
   slabs. Worse, it does not survive late game — by cycle 40,000 an imp
   spiral has overwritten every DAT in the core, the crater set is *empty*,
   and the two variants converge anyway. Shipped `dots = occupancy`: a bomb
   is a write, bombed ground still shows its bomber's colour, and damage
   lives entirely in the plate. Territory never disappears.

3. **Ambient stipple rejected.** A sparse deterministic dot on untouched
   blocks was meant to give virgin core presence. It reads as faint
   occupancy — the one thing a dot must never mean falsely — and it dirties
   the field for no gain. Untouched memory now shows as the calm dark plate
   alone, with the slow density wave moved onto the plate's *bg* (untouched
   blocks only). Empty memory looking empty turns out to be correct and
   makes every structure pop.

4. **The contest measure was scoring near-empty blocks hardest.** First cut
   used the minority/majority *ratio*, which makes a 1-vs-1 block (2 cells
   of 8 owned, one each) score a perfect 1.0 — the same as a 4-vs-4 block.
   Result: bright grey cards scattered over nothing. Fixed to **disputed
   footprint**: `min(1, 2*minority/8)`, so 1-vs-1 scores 0.25 and 4-vs-4
   scores 1.0.

5. **Contest must be heat-gated.** Even with the footprint fix, an ungated
   contest map lights every old overlap the two warriors ever had, which by
   cycle 40,000 is most of the core. Multiplying by the block's max heat
   turns a map of history into a picture of the *front*: a border nobody has
   touched in a thousand cycles is a settled line, not a fight. Contested
   cell count drops from "everywhere" to 210 at the crossover moment and 30
   in the cold late frame — which matches what is actually happening.

6. **Crater glow was too loud — round 3 of `../notes.md`, recurring at the
   new grain.** The inherited rule (`0.45h²`, only the freshest wounds carry
   light) was written for one memory cell. Here "the freshest cell in the
   block" was lighting all 8 cells' worth of plate, so a *single* bomb
   painted a bright card and a bombing run became a forest of them — they
   were the loudest objects on the board, above the process markers. This
   was diagnosed by dumping the brightest backgrounds rather than by
   guessing: the pale rectangles turned out to be ICE crater glow, not
   contest. Fixed by carrying the **cratered footprint**: `0.55 * Σh²/8`
   over the block's pits. One hit is a whisper; only a carpeted block burns.
   *Grain lesson worth generalising: every inherited per-cell intensity rule
   has to be re-derived as a per-footprint rule at atlas grain, or it
   over-fires by up to 8x.*

7. **Contest needed to read in both channels.** A lifted plate alone draws a
   clean rectangle, which reads as a UI card dropped on the board. Now the
   block's dots also burn brighter — in the owner's own hue, so still no
   third colour — and the plate lift carries a sin-hash jitter in
   `(cx, cy, t)` so neighbouring contested cells disagree slightly. The seam
   reads as unstable ground rather than a panel. In the live renderer that
   jitter is the sizzle, `REDUCED_MOTION`-gated.

8. **A third frame was added, because the contested treatment was untested.**
   At the brief's two moments the two warriors barely touch (29 contested
   blocks at cycle 3,000; 30 at 40,000). Sweeping the battle for contested
   density found the crossover at **cycle 12,000** — KIMI 31%, CODEX 44%,
   210 contested blocks, the boundary actively moving. That is
   `atlas-front.*`, and it is the frame the contested treatment should be
   judged on. A treatment nobody can see working is not a treatment.

## Conflict to resolve: contested cells and the colour white

`animation-spec.md` §6 (approved) says contested braille cells **flicker
white**. This mockup deliberately does not do that, and the disagreement
should be settled before implementation rather than silently split.

The problem is that near-white is already spoken for: the process marker is
a FULL near-white block and is the board's designated brightest object.
White contested cells put two different meanings in the same colour at the
same grain, and contested cells are common where processes are common
(fronts are where code runs), so they would collide constantly.

What the mockup does instead keeps the spirit of §6 — the front crackles and
is the "look here" cue — while leaving white to mean exactly one thing:

- the plate lifts toward `SLATE`, a neutral grey off both faction ramps
  (so nothing is averaged), jittering on a sin-hash phase — the sizzle;
- the block's own dots brighten in the majority owner's hue.

If the spec's white is preferred, the process marker needs a different
signature (an outline, a different density, or a bg treatment) and the
mockup should be re-cut before either lands in `tui_corewar.py`.

## Verdict — does the atlas read?

**Yes for the newcomer read, unambiguously.** Glance at `atlas-late.png`:
a vast ember field, a steel-blue band through it, two bright fronts, and a
caption saying 80% vs 20%. "Two programs fighting over a memory field, and
here's who's winning" lands in about a second, without knowing what Core War
is. `atlas-front.png` is better still — you can see the orange front
*eating* the blue. The stationary frame also fixes complaint (1) completely:
nothing slides, the whole core is always in the same place, and the eye
learns the map.

**Yes for the expert read at mid-battle.** CODEX's silk stride draws
unmistakable diagonal cascades; KIMI's imp carpet is a horizontal band with
a hot leading edge; its stone bombs are the scattered orange sparks in
virgin memory. A Core War player can name both strategies from the picture.

**Where it fails, honestly:**

- **Late-game saturation kills density.** By cycle 40,000 every cell in the
  core is owned, so every dot is lit and the 1-dot grain conveys nothing at
  all — the entire read falls to hue, brightness and the plate. It still
  reads (see above), but the structural signatures are gone: you cannot see
  the imp spiral inside a fully-carpeted field. This is not a bug in the
  encoding, it is the true state of a saturated core, and the camera tier
  would have the same problem magnified. Worth knowing that the atlas's
  finest channel is a mid-game channel.
- **A lone process is a lie, and the lie is 8:1.** Acceptable, but it means
  process counts can only be trusted from the bars, never counted off the
  field. Measured: 54 running processes draw 9 markers at `mid`, and 13 draw
  4 at `front` — co-located PCs merge, hard.
- **Single-bomb damage is invisible.** After the footprint fix a single
  fresh crater lifts its plate by about 7% — correct at a glance, but it
  means the atlas cannot show *the individual bomb* as state. The
  animation spec's §5 drumbeat (a one-frame white spark on the dot) is
  therefore not optional decoration; it is the only place a single bomb
  becomes visible, and it should be in the core work, not the add-ons.
- **The wave on untouched core is nearly invisible.** At 0.40 * WAVE_AMP
  toward AMBIENT it is barely a breath. Deliberate — anything louder starts
  to read as occupancy — but it means an idle pre-battle atlas is a very
  quiet screen. The drop-pod load-in (spec §1) is carrying more weight than
  it may realise.
- **Not verified in a real terminal.** The PNGs are synthetic captures at
  the checkpoint's cell metrics; braille dots are drawn as geometry, not as
  font glyphs. Font rendering of `U+28xx` at real terminal sizes may thin
  the dots. The `.ans` files are the ones to eyeball in a pane before this
  gate closes.

## Open questions for the implementation pass

- **The white collision above** — settle §6 vs the process marker first.
- **Process marker cap.** `MAX_COMETS 24` was a comet-era constant. Markers
  merge by block here, so the natural cap is on *blocks*, not processes; a
  SPL bomb that fills the queue would light a large region white. Decide
  whether that is a legitimate read ("their code is everywhere") or needs a
  ceiling.
- **Does the atlas replace grand, or join it?** The atlas shows everything
  the 104x84 grand tier shows, in a quarter of the space, minus per-cell
  colour. Grand may now only be worth keeping for the per-cell ownership
  tint at close reading. Someone should decide whether the ladder is
  atlas / camera / strip with grand retired, or four tiers.
- **Wrap continuity.** Address 7999 sits at the bottom-right and 0 at the
  top-left, one dot row apart in memory and a whole frame apart on screen.
  The spec's §3 wrap spark handles the moment; the static frame cannot show
  adjacency at all. Consider whether the atlas should ever hint at it (a
  seam mark on the left/right edges was not tried).
- **Contest on the `late` frame.** Settled borders correctly show nothing,
  which is honest but means a long stalemate has no visible front. Check
  this against a real stalemate replay before deciding it is fine.
- **Bars are share-of-core, not share-of-owned.** At mid the two read 5%
  and 20% and the remaining 75% is untouched — accurate, but a viewer may
  expect the bars to sum to 100. The word "held" is doing that work; watch
  whether it survives a real audience.

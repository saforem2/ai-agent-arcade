# Xiangqi Board — Design Brief (decision)

Status: DECIDED, 2026-08-10. Supersedes the recommendation in
`arcade/design/xiangqi-mockups/notes.md`.

## §0 Continuity mandate (hard constraint, overrides everything below)

The xiangqi board must read as the **same material family** as `tui_dots.py` at
the wall. A newcomer glancing at the two panes side by side must think "same
arcade, second table" — never "different app." Concretely, and not negotiable:

- The calm braille dot-field **is** the board. There is no board drawn on a
  background; structure is carried by dot density, as in §8.3.
- Pieces sit **in** the field, each clearing a 1-dot keep-out moat. Both sides
  are solid dot mass, told apart by colour alone (§8.2).
- The palette is `tui_dots.py`'s palette. **Exactly one new colour constant is
  permitted on the whole board** (`RED_SOLID`, below). Everything else —
  `PANEL`, `NEUTRAL`, `AMBIENT`, `W_SOLID`, `CHECKC`, `TEXT`, `TDIM`, `LABEL`,
  `SLATE` — is reused verbatim.
- No second material. No box-drawing characters, no rules, no banners, no
  decorative typography on the board's face. The chess board carries zero
  ornamental text and neither does this one.
- Deviation is licensed **only** where xiangqi semantics force it: intersections
  instead of squares, the river, the palaces, 7 piece types, red/black identity.

**Both mockups fail this test and neither is a candidate.** They share a
box-drawing lattice, a centred two-word banner across the river, and (in the
glyph case) a typographic piece language. What follows is a prescribed
correction, not a choice between the two.

## §1 Decision

**Dot-drawn braille sprites on a dot-native lattice. One mode, no hybrid.**
Pieces are dot matter drawn from a 7-entry silhouette table at two resolutions,
warm = red, cool = black. The lattice is the dot field made denser along the
9x10 grid lines. The river is a quiet break in the field. There is no CJK
anywhere on the default board.

### Why, from the screenshots

- **`mockup-sprites.png` does not show a sprite board losing.** It shows a
  2-character-per-piece board losing. The pieces are near-invisible specks and I
  could not locate the position without the legend. That is the failure
  `tui_dots.py` already diagnosed and fixed in §8.1 ("4-dot sprites can't tell N
  from B") — with 6x8, later 10x12 masters plus the moat. Not re-litigated here;
  the mockup author says as much themselves.
- **`mockup-glyphs.png` is legible and materially wrong.** The red side pops,
  the black side renders as pale grey characters that all but vanish, and the
  whole object is crisp typography dropped onto a lattice. Side by side with
  the chess pane it is the "different app" the mandate forbids.
- **The hybrid was already tried and overruled on the chess board.** §8.1
  records Kimi's time-separated split (glyphs in play, dots in attract) as
  "Adopted then superseded — the user's explicit direction was dots pieces," and
  §8.2 records the verdict on the braille sprites: *"those were perfect!!"*
  Glyph-play for xiangqi would put the two boards in opposite default modes.

### The cost the mockup quoted is roughly halved

`notes.md` prices sprites as "full silhouettes for 7 piece types x 2 sides."

- **7 masters, not 14.** Colour carries the side, as on the chess board.
- **3 of the 7 already exist.** Chariot, horse and soldier *are* rook, knight
  and pawn. Reuse `SIL_HI`/`SIL_LO` `['R'|'N'|'P']` through the existing
  `shape()` resampler. New art: general, advisor, elephant, cannon.

Sprites are therefore also the cheaper route. The glyph route needs a live
east-Asian-width layer that every future overlay must keep re-deriving.

## §2 Rejected alternatives

- **Characters-as-glyphs (primary).** Fails §0 outright: foreign material,
  permanent width tax, and no reuse path for `draw_particles`, `spawn_debris`,
  wake, topple or dissolve — all of which already speak dot coordinates.
- **Dual-MODE hybrid (glyph play + sprite attract).** Right reasoning, wrong
  premise: it assumes chess plays in glyphs. `MODE = 'dots'` is the shipped
  default.
- **A braille disc bearing one centred CJK glyph.** The most tempting
  compromise, and still a no. It re-imports the width layer; it cannot survive
  the cozy tier (a double-width glyph will not sit inside a 4-char disc); a
  glyph over a disc reads as busy outline rather than the solid mass §8.2
  measured as the contrast mechanism; and a glyph cannot dissolve into
  particles, so attract mode would have to special-case it. Material honesty
  and the animation reuse both point the same way.
- **Box-drawing lattice (`┼ │ ─ ╱ ╲`), as in both mockups.** Second material;
  §0 forbids it. The lattice is dots.
- **`楚河` / `漢界` as a river banner, as in both mockups.** This is the single
  loudest "different app" signal in the screenshots: centred, coloured,
  typographic, sitting on the board's face where chess carries nothing. Cut
  from the default board. Available only under the deferred glyph mode.
- **Square-cell rendering.** Xiangqi is played on intersections; faking squares
  misstates the game's geometry for no gain.

## §3 Secondary mode

`mode glyph` is **deferred, not phase 1.** The ctl/`mode.txt` machinery is free
to inherit; the CJK width layer is not. It ships only after the dots board is
live, only as a toggle, and never as the default. It is the one place `楚河` /
`漢界` may appear.

## §4 Interaction contract

Identical file bus to chess, different live dir. `ARCADE_LIVE` defaults to
`/tmp/xiangqi`.

| file | contract |
|---|---|
| `moves.txt` | one space-joined ICCS move log, `<file><rank><file><rank>` tokens such as `h2e2 h7e7`. No SAN, no piece letter, no capture/check marks. |
| `fen.txt` | standard xiangqi FEN; start = `rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1` |
| `pending.txt` | `<agent>\t<iccs>` staged for referee approval, as chess |
| `ctl` | `replay [n]` \| `reset` \| `banner <text>` \| `names <r> <b>` \| `mode dots\|glyph` \| `size cozy\|grand` |
| `names.txt`, `banner.txt`, `results.txt`, `mode.txt`, `size.txt` | unchanged semantics; `results.txt` keeps RED PLAYER FIRST, per §8.5 |

Move generation and legality come from the existing `arcade/engine/xiangqi.py`
(`XiangqiBoard.push` / `.legal_moves` / `.fen`, ICCS throughout); the renderer
replays `moves.txt` through it. Carry the §8.7 lessons: >3 moves arriving at
once snaps to live instead of animating each; abort a replay when `ctl` changes;
sleep a beat after launching a pane before writing `ctl`.

## §5 Render spec

### Geometry

9 files x 10 ranks = 8 x 9 intervals. `fit_geometry` picks the largest
`(cw, ch)` satisfying `cw*8 + 5 <= cols and ch*9 + 3 <= rows`, from
`GEOM = ((6,3),(5,3),(4,2),(3,2))`, `GEOM_COZY = ((4,2),(3,2))`. Grand tier is
12x12 dots per interval and 27 char rows of board — three rows taller than the
chess board, so check pane fit early (§7).

**Sprite box is SQUARE**, `(pitch-2)` on a side: 10x10 grand, 6x6 cozy, centred
on the intersection with one dot of inset so adjacent moats never overlap.
Xiangqi pieces are discs; chess's tall box would misdraw them. The 10x12 chess
masters resample to 10x10 through the existing nearest-neighbour path in
`shape()`.

### Field densities — locked to `tui_dots.py`'s texture

The board has no checkerboard, so the density budget is re-spent on the
lattice. Same constants, same dots-per-cell scale, so the two panes have
visibly the same grain:

| region | dots/cell | source |
|---|---|---|
| outside the board | 1 | `DENS_AMB`, identical to chess |
| board interior (open ground) | 2 | `DENS_D`, chess's dark-square tier |
| lattice lines | top level, 1 dot wide | plays the role chess's `DENS_L` plays |
| palace diagonals | ~60% of lattice brightness | subordinate, same material |
| river band | 1 | drops to ambient — the field's only interruption |
| occupied intersection | `DENS_QUIET` + moat | unchanged from chess |

Lattice lines and nodes are **exempt from the density wave**, under the same
calm-pocket rule as occupied squares (§8.6), or they will shimmer. The ambient
wave keeps chess's `WAVE_PERIOD, WAVE_AMP = 30.0, 0.5`.

### Board furniture

- *Lattice:* one-dot-wide lines of field at `LATTICE` density; each intersection
  gets a 2x2 node cluster so the play points read as points.
- *Palace:* the two 3x3 palaces get their diagonals as faint dot-paths at the
  reduced brightness above — present, subordinate, never a drawn line.
- *Position marks:* the traditional cannon/soldier crosshatch points render as
  four short dot ticks around the intersection, at palace-diagonal brightness.
  Cheap, authentic, and made of the same material.
- *River:* **a quiet break in the field, not a labelled banner.** The verticals
  stop at both banks; the band between ranks 4 and 5 drops to ambient density;
  the wave runs there with a horizontal phase drift so the gap reads as a slow
  current. No text. A player reads the river from the geometry exactly as they
  read a chessboard without labels.
- *Pieces:* every sprite clears its 1-dot keep-out moat first, clamped to the
  interval. The moat, not the hue, guarantees contrast (§8.2).
- *Chrome:* file letters `a`–`i` and rank digits `0`–`9` in `LABEL`, outside the
  board, matching chess's coordinate treatment. Nothing else.

### Masters, keyed by FEN letter

Uppercase red / lowercase black share the silhouette. `R`, `N`, `P` = existing
chess masters, resampled. New at 10x10:

```
K general — seal with an inscribed cross (heaviest mass on the board)
  ##########  #........#  #...##...#  #...##...#  #.######.#
  #.######.#  #...##...#  #...##...#  #........#  ##########

A advisor — pure saltire; diagonal mover, diagonal shape
  ##......##  .##....##.  ..##..##..  ...####...  ....##....
  ...####...  ..##..##..  .##....##.  ##......##  ..........

B elephant — dome over two legs; mass on TOP, void below
  ...####...  ..######..  .########.  ##########  ##########
  ###....###  ##......##  ##......##  ##......##  ###....###

C cannon — bore ring over a solid base; void on TOP, mass below
  ..######..  .##....##.  ##......##  ##......##  .##....##.
  ..######..  ...####...  ..######..  .########.  ##########
```

Cozy 6x6 fallbacks: `K` solid block with a 2x2 centre void; `A` an X; `B` a
3-row dome over 3 rows of two legs; `C` a ring over a stem over a full base
bar; `R`/`N`/`P` from `SIL_LO`. B and C are deliberate inversions of each other
so the pair stays separable at 6x6 — that is the pair which collapsed at two
characters in the mockup.

### Colours

```
RED_SOLID   (255, 138,  78)   THE ONLY NEW CONSTANT — warm pole, sibling of
                              chess MASS (255,176,62)
BLK_SOLID   (240, 249, 255)   cool pole — reuse W_SOLID verbatim
lattice / field / chrome      NEUTRAL, AMBIENT, LABEL, SLATE, TEXT, TDIM — all
                              reused verbatim from tui_dots.py
```

Literal black is a hole on a dark field, so the tradition's red-vs-black ink
becomes warm-vs-cool exactly as chess's white-vs-black did — which is also what
keeps the two panes in one family. **Caught conflict:** a naive vermilion red
lands on top of `CHECKC (242,84,94)` and would make the red general's check
blink invisible. Hence the orange-shifted red, and check must also carry its
geometric signals (cell inversion + expanding dotted ring), not hue alone.

## §6 Mandatory checkpoint (gate)

**Before the renderer build proceeds past the board-furniture stage**, capture a
screenshot of the empty xiangqi board beside a live `tui_dots.py` pane and
review the pair. The build does not continue until that side-by-side is
approved. This gates furniture — lattice grain, river break, palace diagonals,
densities — *before* any piece art is invested, which is the point: furniture is
where the material family is won or lost, and it is the cheapest stage to
redo. The team lead enforces this.

A second, lighter check after the masters land: same side-by-side, opening
position, at grand and cozy.

### §6.1 Checkpoint 1 verdict — REDO (2026-08-10)

Reviewed `checkpoint-furniture.png` against `checkpoint-chess-ref.png` at 97x56.
Stage 1 was built against the pre-rewrite brief, so the `楚河`/`漢界` text is
excused as a crossed message. The rest does not pass: **chess reads as a board,
xiangqi reads as graph paper.** Corrections in build order — furniture only, no
piece art until this re-passes.

1. **Board plate (the big one).** Chess's physical presence comes substantially
   from per-cell background tint: the squares are visible objects lit against
   `AMBIENT`. Xiangqi stage 1 is line-work on flat void, and that single
   difference carries most of the "different app" reading. This is *not* forced
   by intersections-vs-squares — a xiangqi board is also a lit surface with
   lines on it. Fix, using existing constants only:
   - board interior rectangle: flat `SQD` background plate (no checkerboard —
     there is no semantic basis for alternation here);
   - palace interiors: lifted to `SQL`, so each palace reads as a region even
     before its diagonals do;
   - river band: one step *below* `SQD`, so the break is a trough in the plate.
2. **Brightness hierarchy is inverted.** Piece mass and lattice dots currently
   sit at comparable brightness, so the black pieces are hard to locate at a
   glance — I had to hunt for them. Pieces are always the brightest thing on the
   board; lattice dots drop one to two levels below piece mass. Also confirm the
   keep-out moat clears **lattice dots**, not just field dots — lattice is
   currently running through the sprite region.
3. **Kill the territory tint.** The entire red half's lattice renders warm and
   the black half cool, which turns influence into wallpaper — the exact failure
   §8.3 guards against with `SAT_CAP` and pressure scaling. In the chess
   reference the tint is localized to two bands, not half the board. Structure
   stays neutral: tint open-ground field only, never the lattice or nodes.
4. **River.** Delete the text. Verify the gap is exactly one interval of pitch —
   as rendered it looks like roughly three rows, which reads as a caesura rather
   than a river. With the trough from (1) it should carry without text; if it
   still under-reads, deepen the trough, never re-add text.
5. **Palace diagonals** are currently at noise level — visible as speckle, not
   as structure. Raise to full lattice brightness (they are structure too),
   keeping them one dot wide. Combined with the `SQL` plate lift they should
   read without becoming drawn lines.
6. **Coordinate labels are missing** — the brief didn't specify, so: **add
   them**, for parity with chess and because ICCS labels are functional, not
   decorative (agents submit `h2e2`). Ranks at the left edge, files below, in
   `LABEL`, matching chess's placement exactly. Files `a`–`i`; ranks `0`–`9`
   with **rank 0 at the red/bottom edge**, per `xiangqi.py`'s model — inverting
   this is a real bug, not a cosmetic one.
7. **Header and footer show `RED` / `BLACK`** where chess shows `CODEX` / `KIMI`.
   Read agent names from `names.txt` and carry the seat colour in the name's
   hue, as chess does. Footer likewise: `<NAME> to move`.
8. **Sprite interiors look dithered rather than solid.** Even as placeholders,
   fill them right out — solid mass is the mechanism §8.2 measured, and a
   dithered interior will mislead the stage-2 silhouette review.

Re-screenshot side by side after these land. Stage 2 begins only on a pass.

### §6.2 Checkpoint 1 round 2 — CONDITIONAL PASS (2026-08-10)

All 8 items of §6.1 land. Side by side at 97x56 the two boards now read as one
system: same grain, same plate logic, pieces unambiguously the brightest mass,
structure neutral, labels and header/footer at parity. **The material-family
question this gate exists to answer is settled.** Proceed to stage 2 (piece
masters). The remainder are value and geometry fixes, not material rework, and
do not justify a third furniture round — but they are stage-2 items 1-3, ahead
of any master art, and are re-verified at the masters checkpoint.

1. **Half-interval bleed on all four sides of the board rect.** Pieces on files
   `a`/`i` render as half-discs — and so do ranks 0 and 9, flat-topped and
   flat-bottomed against the canvas edge. The root cause is not an `a`/`i` edge
   case: chess's rect works because its pieces sit *inside* cells, while these
   sit *on* intersections, so the plate must extend half a sprite beyond the
   outer intersections on every side. Fixing only `a`/`i` leaves ranks 0 and 9
   clipped. This also gives the board the outer border a real xiangqi board has.
2. **The river has disappeared.** `PANEL` against `SQD` is not enough separation
   at this grain — the band between ranks 4 and 5 currently reads as ordinary
   inter-rank space. Deepen the trough and/or widen the band to a full interval,
   and confirm the verticals genuinely stop at both banks. Per risk 4: never
   text.
3. **Verify rank-label to intersection-row registration.** The black cannon and
   soldier rows (7, 6) appear to sit slightly high relative to their labels while
   the red rows (3, 2) sit true. This may be my pixel reading, but it is cheap to
   confirm and expensive to discover later.

Watch item for the masters checkpoint (not a stage-2 blocker): discs currently
run ~85% of the pitch. Once real masters carry a keep-out moat, confirm nine
adjacent pieces on rank 0 still show plate and lattice between them — risk 5.

## §7 Build risks

1. **Pane height.** 9 intervals is taller than chess's 8; the grand tier may not
   fit the current pane and will silently degrade. Measure the real pane before
   authoring art.
2. **New masters are unverified art.** The four grids above are a starting
   draft, not a shipped set. Acceptance test: render the opening position at
   grand *and* cozy and confirm all 7 silhouettes are nameable without a legend
   — checking B-vs-C and A-vs-K explicitly.
3. **One-dot lattice lines may shimmer or vanish.** They interact with the Bayer
   threshold and the density wave; exempt them from the wave and verify at every
   geometry tier, including the smallest.
4. **The river may under-read once the banner is gone.** It is now carried
   entirely by stopped verticals plus a density drop. If the checkpoint says it
   disappears, widen the drop or lower the band's density further — do **not**
   reach for text.
5. **Moat collision at cozy.** 6x6 sprites in an 8-dot pitch leave one dot of
   clearance; verify a full back rank of nine adjacent pieces does not erase the
   lattice between them (the §8.2 failure mode).
6. **Red vs CHECKC.** See §5. Verify the check blink on the red general
   specifically, not just the black one.
7. **Kings-facing rule has no chess analogue.** The flying-general constraint is
   a board-spanning relationship the influence field should probably express;
   out of scope here, but do not forget it.
8. **Glyph-mode debt.** If `mode glyph` ships later, the width helper must be a
   single isolated function (`mockup-glyphs.py`'s `east_asian_width` pass is the
   reference implementation) or it will leak into every overlay.

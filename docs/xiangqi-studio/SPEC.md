# Xiangqi board — LOCKED VISUAL SPEC v2 (user-approved 2026-08-11)

Reference implementation: /tmp/xq-synth-claude/combined.py (`--tier circ --live`).
Base: codex's FIELD/RIVER/SEAL synthesis + codex geometry pass + kimi K3 palette.
Target: arcade/engine/tui_xiangqi.py (production, Textual/DotGrid).

## Locked decisions
1. **Board**: production dot-field language is the BASE (ambient Bayer field,
   lattice, palaces, position marks). ADDED FROM THE MOCKUP (production does
   not have these yet — port them): river band RIVER_BG (12,32,46) + RIVER
   (44,183,190) current dots, 楚河・漢界 gold text, gold e-file spine cadence.
2. **Pieces = MOAT-CARVED DOT SEALS (user-approved on sight, 2026-08-11)**:
   per piece, in the braille dot layer:
   - claim: clear all dots to R + 0.8 (the void moat — claim more than you
     fill; moat stays within half-pitch; NO dangling dots may survive)
   - fill: SOLID BONE (226,214,186) within R; the seal character ("voids
     shape the circle") comes from the MOAT and the FACE WINDOW, not fill
     density. Density dithering was tested and REJECTED (gate-measured: any
     thinning reintroduces orphan dots and breaks L/R+T/B symmetry)
   - face window: cell-quantised rounded rect in ABSOLUTE dot coords grown
     from the 4x4 glyph cells (corner dots retained for curvature), bg fixed
     WINDOW_BG (14,18,24) — never the board checkerboard
   - face: bold CJK, no rim, ink RED (255,100,60) / BLACK (246,240,226)
   - geometry: R = box/2 - 0.6 with box = min(SQW,SQH) - 2 (pitch-derived,
     never hardcoded); CENTRE = (px(file) - 0.5, py(rank) + 1.5) — the
     glyph's midline in both axes; py is the TOP dot of the face row, so
     +1.5 not +2 (gate E1/E2: +2/px yields a 13x12 ellipse with a stub under
     every piece); circle metric hypot(dx, dy*k) with k = cell_aspect/2,
     default 1.0, env XQ_CIRCLE_K; disc is 12x12 dots = 3.0 rows at grand
   - traditional faces only: 帥仕相俥傌炮兵 / 將士象車馬砲卒
3. **Centering law**: CJK centers vertically only in odd row counts; the disc
   is 3.0 rows (12 dots) at grand with the face on the middle row. Lineage of rejects:
   6x3 wood block, 4x1 wood pill, bare braille ring, cleared block, edge-thinned
   dither variants (gate-rejected, reintroduce fuzz), unicode U+1FA60 glyph board ("meh" —
   kept only as optional detected floor tier + rack notation).
4. **Palette (kimi K3, gate-corroborated)**: BONE (226,214,186), RED
   (255,100,60), BLACK (246,240,226), WINDOW_BG (14,18,24). One bone tone for
   both sides (per-side disc tint tested + rejected: invisible). §0 continuity
   exception EXPLICITLY GRANTED for these constants. Legibility notes: the legend-free risk is the RED 亻 cluster 仕/俥/傌
   (three-way, same side — color cannot disambiguate) plus 炮/砲; NOT 士/仕
   or 象/相 (cross-side, color separates). Face color does real work — keep.
   7-nameable: PASS at grand AND cozy (faces are printed text, no size
   floor; font probe in item 6 is LOAD-BEARING — no CJK font = 0/7).
5. **Motion doctrine (hard rule)**: color is identity, never animation. Idle
   budget = river current drift (~2 fps, rows shear opposite) + slow field
   breathing ONLY. Event effects (post-statics): last-move gold trail,
   check-flash (MUST render at pri 7 — pri 5 is erased by disc fill, known
   bug), capture 5-beat with debris FORKED from tui_dots.spawn_debris (no
   import — its chess deps stay out). Move travel at the disc tier is a 0.5s
   full-disc smoothstep glide src→dst, ported from chess; every flyer centre
   snaps to the static 2-dot-x/4-dot-y lattice and lands exactly on the static
   endpoint. Chip/seal tiers ignore the flyer and retain the source until push.
   Capture beats run concurrently from normalized `travel_elapsed`: face_out
   <0.45, pinch <0.60, hidden <0.75, then field; debris spawns once on entry
   to hidden. REDUCED_MOTION suppresses travel, beats, AND debris. On a pane
   slower than a beat window, that visual beat may be skipped; elapsed timing,
   the guarded debris transition, and the single push remain authoritative.
6. **Responsive ladder**: `size cozy|grand` keeps production's PITCH meaning;
   art auto-degrades by measured pane: grand pitch + rack >=113 cols; discs
   sans rack >=87; cozy pitch below that (NO face window at cozy — production cozy
   box=10 → 8x8-dot disc, 2.0 rows, window can't fit; glyph-cell bg only; honest read:
   at cozy the piece is a GLYPH WITH BONE CAPS, disc identity is gone); floor = codex void seals
   (MASTERS_LO raster path deleted as dead art, phase-2 audit); optional unicode-glyph tier only
   behind a font probe/config flag, never a dependency. Minimum supported
   pane: cozy floor geometry; below it, render clipped rather than wrapped.
7. **No mockup chrome — header AND footer**: the header line carries real
   identity only: match id + PLAYER NAMES with sides (e.g. KIMI (red) vs
   CODEX (black)). BANNED anywhere: design narration ("FIELD / RIVER /
   SEAL", "traditional faces", "no engine evaluation", "opening position"
   class). Turn indicator appears ONCE (footer), never duplicated in the
   header. Footer = real state only (turn, last move, check) + the tested
   [ ▶ replay ] button. Rack at grand shows real material/capture state,
   never feature narration.
8. **Terminal font (user machine)**: Ghostty font-codepoint-map routes the 14
   faces + 楚河漢界 to LXGW WenKai Mono (installed); takes effect next Ghostty
   restart. Production must not depend on it.

## Production reality notes (for builders)
- Production now prints CJK faces as text at disc tiers. The dot-glyph
  raster path (GLYPHS_HI/MASTERS_HI/MASTERS_LO) was dead code and is
  deleted; the below-floor fallback is the void-seal tier.
- Palace tint / river band should become DOT MATTER (distinct dither), not
  `back` fills, so discs cannot erase them (open gate item P1-1 — approved
  direction, verify in stills).
- Dome shading (optional, low priority): background luminance ramp, vertical,
  3-4 steps, identical both sides, static (doctrine guard).

## Non-negotiables
- moves.txt replay is truth; never regress the cold-start fix.
- No test regressions; the suite grows with new render paths.
- Work only in the arcade tree. Never touch /tmp/chess. Never create
  /tmp/xiangqi from tests (ARCADE_LIVE scratch only).

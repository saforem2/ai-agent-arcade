# Xiangqi board mockups — glyphs vs. sprites

Two competing renders of the standard opening position, same lattice
furniture (9x10 intersection grid, fixed pitch of 4 visual columns per file,
river band between ranks 4/5 with 楚河/漢界, two 3x3 palaces with diagonal
cross lines). Source: `mockup-glyphs.py`, `mockup-sprites.py`. Renders:
`mockup-glyphs.png` / `.txt` / `.ans`, `mockup-sprites.png` / `.txt` / `.ans`.

- **Alignment is solvable but not free for glyphs.** CJK piece characters are
  double-width, board furniture (`┼ │ ─`) is single-width. Naive
  concatenation drifts the lattice out of register the instant a glyph lands
  where a line character used to be. The fix that worked: give every
  intersection a fixed *visual-column* pitch (not character count), measure
  real display width per glyph with `unicodedata.east_asian_width`, and pad
  fill-runs to that pitch. Once that's in place the grid stays true — see
  `mockup-glyphs.png`, verticals and diagonals land under every glyph exactly.
  This is real code to carry into the engine, not a one-line tweak.

- **Sprites sidestep the width problem entirely.** Braille characters are
  single-width in every terminal I tried, so a 2-char sprite and a 1-char
  `┼` differ in a plain arithmetic way with no east-Asian-width lookups
  needed. `mockup-sprites.py` is ~30% less code for the same alignment
  guarantee, and the diff between the two files is basically that missing
  width-measurement layer. If long-term maintenance cost matters more than
  the visual payoff, sprites are the cheaper material to keep correct.

- **Glyph legibility at a glance is excellent.** 車馬象士將 read instantly as
  what they are to anyone who knows the game, and the red/black split colors
  the position at a glance (which side is where) without having to parse
  shapes. This is the biggest single argument for glyphs.

- **Sprite legibility is the weak point of this pass.** At 2 braille
  characters per piece the seven types are only weakly distinguishable —
  King (`⣿⣿`, solid) and Rook (`⡇⢸`, bracket) read clearly, but Advisor
  (`⠿⠶`) vs Cannon (`⠶⠿`) are near-mirror and easy to confuse at speed, and
  Pawn (`⠐⠂`) nearly disappears against the ambient dot texture. The chess
  board's sprites solve this with a full 6x8 (or 10x12) dot silhouette per
  piece, not 2 characters — a fair sprite mockup for xiangqi would need the
  same investment (probably a `SIL_LO`/`SIL_HI`-style master table per piece,
  rendered across 2-3 terminal rows, not squeezed into 1). This mockup
  undersells sprites; treat it as a proof of the alignment claim, not a
  legibility verdict.

- **Aesthetic fit with the chess board's dot-field material.** Sprites are
  the more honest continuation of `tui_dots.py`'s language — "pieces are
  disturbances in the field," braille matter same as the chess pieces,
  same keep-out-moat idea would extend naturally. Glyphs break that
  material: they're a foreign, crisp, typographic object dropped into a
  dither field, closer to the chess board's `glyph` MODE (attract-mode
  fallback) than its `dots` MODE (the default). If dot-field consistency is
  the design's core value, sprites are more "on-brand"; if xiangqi's own
  visual tradition (which *is* character-based — real boards are carved
  with these glyphs) is the priority, glyphs are more legible to the actual
  audience.

- **Implementation risk.** Glyphs: low risk once the width-measurement
  helper exists (isolated, testable, ~15 lines), but every future board
  furniture change (piece highlighting, capture flash, move animation) has
  to keep re-deriving visual width for anything that overlays a glyph cell.
  Sprites: higher risk *now* because the 2-char vocabulary needs real design
  work to reach distinguishability (see above), but once a good sprite table
  exists, all downstream animation/dissolve code from `tui_dots.py`
  (`draw_particles`, `spawn_debris`, wake trails) ports over almost for free
  since it already speaks braille-dot coordinates — there's no equivalent
  reuse path for CJK glyphs.

- **River and palace rendering worked identically well in both** — the
  fixed-pitch approach means river band, border continuity through the gap,
  and palace diagonals are shared code between the two mockups and needed no
  glyph-vs-sprite-specific handling. Not a discriminator between the two
  designs, but worth flagging as settled: this part of the layout is solid
  regardless of which piece style wins.

- **Recommendation:** if I had to pick one direction to invest in for the
  real engine, it's a **hybrid following the chess board's own PLAY/ATTRACT
  split** — glyphs for the default legible play state (reuses xiangqi's
  actual character tradition, wins on immediate readability for anyone who
  knows the game), sprites for the attract/idle dissolve state (reuses the
  chess board's existing dot-matter choreography almost directly). That
  mirrors `tui_dots.py`'s own `MODE = 'dots' | 'glyph'` toggle instead of
  forcing a single either/or choice now.

## Environment notes

Screenshots were captured for real: opened Terminal.app via `osascript`,
ran each script with `python3`, took a window-scoped `screencapture`. Both
`mockup-glyphs.png` and `mockup-sprites.png` are genuine terminal captures,
not synthetic renders. Font: Terminal.app default monospace at the pane's
current size; a font with less CJK-glyph vertical overshoot might tighten
the glyph mockup's line spacing further, but the horizontal alignment claim
above does not depend on font choice.

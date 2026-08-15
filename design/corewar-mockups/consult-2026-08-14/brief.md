# Design brief: make the Core War board legible + compact

You are one of several designers consulted on a terminal renderer. Read
`<arcade>/engine/tui_corewar.py`
(esp. the header docstring, `status_segments`, `header_line`, `render`,
`fit_geometry`) and skim `<arcade>/design/corewar-mockups/notes.md`
for the design doctrine. **Do not edit any repo files.** Write your proposal
to `/tmp/cw-design/<yourname>.md` (one page max), then stop.

## What it is

A live spectator board for Core War (two assembly programs fight in an
8000-cell circular memory). The core renders as a braille dot-field:
1 memory cell = 1 braille cell (2x4 dots, density = activity). Owned cells
glow ember (warrior A) or ice (warrior B); processes are bright comets;
bomb craters are dark pits; impacts flash; elimination plays a hitstop +
board shake + cooling front. Chrome: header (`CORE WAR · KIMI (ember) vs
CODEX (ice)`), 4-col address gutter, address ruler row, footer status like
`round 1/3 · cycle 5185 · KIMI procs 10 · CODEX procs 44`.

Size ladder today: grand (whole core) needs a 104x84 pane; camera
(activity-following viewport) down to 24x10; below that a text-only strip;
hard floor 24x6. `size.txt` persists cozy|grand; default grand.

## The asks

1. **Plain-language labels.** The audience has never seen Core War.
   `procs`, `1/2-1/2`, `cycle 5185`, `warriors locked` are jargon. Propose
   exact replacement strings for every status/chrome state (workshop,
   locked, battle, verdict, over-win, over-tie) that a newcomer finds
   interesting and informative. Short enough to fit a footer.
2. **Compact layout + info bar.** Reduce the overall footprint and add an
   information bar (side or bottom): what would a newcomer want at a
   glance? (territory %? process counts labeled? round ledger? event
   ticker? legend?) Give ONE concrete ASCII layout sketch with column/row
   budgets.
3. **Size ladder.** Recommend the default pane size the renderer should
   target and the minimum viable floor (user feels the current floor is
   too big / the full-core tier too demanding). Is downsampling the whole
   core (e.g. 2 core rows per terminal row → 100x40) worth the honesty
   tradeoff?
4. **Memetic juice.** One or two signature visual moments a spectator
   would clip and share, within these constraints.

## Hard constraints

- Braille dot-field material: one fg color per braille cell; bg per cell OK.
- Render output must be byte-identical for identical (scene, t) — no RNG in
  the render path (deterministic sin-hash noise is the house trick).
- Every line must fit the pane width — clip, never wrap.
- `ARCADE_REDUCED_MOTION=1` suppresses motion effects.
- House palette already has ember/ice/panel neutrals; extended ASCII glyphs
  (braille, block, arrows) fine; emoji risky (width) — avoid.
- Python stdlib only, single file, ~24 fps.

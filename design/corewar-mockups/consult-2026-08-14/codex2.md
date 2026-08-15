# Core War board proposal: memory, copies, wounds

**Method:** Twyla Tharp's *spine*: a newcomer should read memory, survival, and consequence before learning Core War vocabulary. Keep game terms out of the primary chrome; the field can teach them later.

## Exact chrome language

Use coloured `{A}` / `{B}` names in every template. Comma-format counts. Never show `procs`, `cycle`, `warriors locked`, or chess scores.

- **Header:** `CORE WAR · {A} vs {B} · 8,000-CELL MEMORY`
- **Workshop:** `WAITING FOR TWO PROGRAMS`
- **Locked:** `PROGRAMS LOADED · BATTLE READY`
- **Battle:** `ROUND {n}/{total} · {cycles} PASSES · LIVE COPIES  {A} {pa} / {B} {pb}`
- **Round verdict, winner:** `ROUND {n}: {winner} SURVIVES · {cycles} PASSES`
- **Round verdict, tie:** `ROUND {n}: BOTH SURVIVE THE {cycles}-PASS LIMIT`
- **Match over, winner:** `{winner} WINS THE MATCH · ROUNDS  {A} {aw} / TIED {ties} / {B} {bw}`
- **Match over, tie:** `MATCH ENDS IN A TIE · ROUNDS  {A} {aw} / TIED {ties} / {B} {bw}`

Here **pass** means both programs have had a turn; **live copy** is the plain-language label for a process. At very narrow widths, preserve state first (`ROUND 2/3`, `CODEX WINS`), then counts; clip names, never whole semantic clauses.

## Default layout and information bar

Target **84 x 32**: large enough for an 80-column, 1:1 camera, but 62% fewer cells than 104 x 84. The information bar answers: what is happening, how much memory each program has marked, what happened in prior rounds, and what the last visible event meant. `MEMORY MARKED` is deliberately not `territory` or `score`: touching more cells does not mean winning.

```text
84 columns (brackets mark budgets; they are not rendered borders)
[ HEADER: 84                                                        ]  1 row
[ADDR:4][ 1:1 ACTIVITY CAMERA: 80                                   ] 26 rows
[    :4][ ADDRESS RULER: 80                                          ]  1 row
[ ROUND 1/3 · 5,185 PASSES · LIVE COPIES  KIMI 10 / CODEX 44        ]  1 row
[ MEMORY MARKED · KIMI 31% · CODEX 12% · UNTOUCHED 57%              ]  1 row
[ ROUNDS · 1 KIMI · 2 TIED · 3 LIVE                                 ]  1 row
[ LATEST CODEX BOMBED 5864 · BRIGHT=LIVE COPY · DARK=BOMB PIT [R]   ]  1 row
Rows: 1 + 26 + 1 + 4 = 32.  Board columns: 4 + 80 = 84.
```

The ticker should use a tiny fixed vocabulary: `{name} BOMBED {addr}`, `{name} SPLIT: {old} -> {new} LIVE COPIES`, `{name}'S LAST COPY DIED`. Hold the latest item until another event replaces it; this is deterministic and readable at 24 fps.

## Size-ladder verdict

- **Default:** 84 x 32, 80 x 26 honest 1:1 camera plus the four-row bar above.
- **Exact grand:** retain 104 x 84 as an opt-in whole-core view; remove the blank row and collapse the bar to status + ledger/ticker so the requirement does not grow.
- **Small camera:** down to 48 x 16 (44 x 10 field, same 1:1 material).
- **Text floor:** **20 x 4**, not 24 x 6: title; clipped names; state/verdict; round + live-copy counts. Refuse below 20 x 4.

Do **not** make the proposed 100 x 40 vertical downsample a normal tier: it saves no width and makes two differently owned cells share one foreground colour. If a full-core overview is wanted, go all the way to a clearly labelled **54 x 24 atlas**: a 50 x 20 field where one braille glyph aggregates its 2 x 4 block, with exact label `OVERVIEW · 1 GLYPH = 8 CELLS`. Colour is the block's dominant recent owner; dot occupancy remains spatially exact. It is an overview mode, never presented as the 1:1 board.

## Signature moments

1. **Last light:** the final copy hits a bomb; three frames hold white-hot, a fixed frame-indexed shake sequence kicks once, then that program's haze cools outward while the ticker locks to `{name}'S LAST COPY DIED`. Replace the current render-time random shake with fixed offsets to meet byte identity. Reduced motion shows the kill frame and final cooled state only.
2. **Fork bloom:** when `SPL` crosses 8, 16, 32, ... live copies, the newborn comets condense together under one short ring and the ticker says `{name} SPLIT: 8 -> 16 LIVE COPIES`. Reduced motion keeps only the count jump and ticker.

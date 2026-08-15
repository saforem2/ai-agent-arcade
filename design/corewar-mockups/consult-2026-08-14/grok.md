# Core War board — compact spectator cut

The field already speaks. Chrome still talks to the engine. Translate the footer; shrink the frame; keep 1 cell = 1 braille.

## 1. Exact chrome strings

Header (every named phase; hues on the names do the ember/ice work — drop the parentheticals):

`CORE WAR · {A} vs {B}`

| state | replace with |
|---|---|
| workshop | `empty core — waiting for both programs` |
| locked | `both programs in — first round about to start` |
| battle | `round {n} of {total} · tick {cyc}` |
| verdict (win) | `round {n} — {winner} remains · {cycles} ticks` |
| verdict (tie) | `round {n} — neither fell · {cycles} ticks` |
| over-win | `{winner} holds the core` |
| over-tie | `stalemate — both still standing` |
| floor refuse | `core war needs 16x3` |

Do not put process counts, `1-0`, or `1/2-1/2` in the footer. Those are the info bar's job. Optional last-event clip-on (only if it fits): ` · crater` / ` · split` / ` · last copy`. Replay button stays `[ ▶ replay ]`.

## 2. Layout — one sketch, 80×28 default

Side bar wastes width the camera needs. Bottom stack: header / field / 1-row ring-map / info / voice. Drop the 4-col gutter and the address ruler on camera (grand keeps both). Camera origin lives in the footer as `at {addr}`.

```
cols 80 × rows 28     GUTTER=0  TOP=1  BELOW=3  VW=80  VH=24
         0         1         2         3         4         5         6         7
         01234567890123456789012345678901234567890123456789012345678901234567890123456789
row  0  |CORE WAR · KIMI vs CODEX                                      bouts ● · ·    |
row  1  |⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿|
        |   camera: 80 cols × 24 rows, 1 cell = 1 braille, heat-centroid, wrap-aware   |
row 24  |⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿|
row 25  |▸████░░░░░░░░░░░░░░░░███░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░|
        |   ring-map: 80 buckets × 100 cells; fg = majority owner; ▸ = camera window   |
row 26  |KIMI 10 alive  ████░░ 38%          CODEX 44 alive  ██░░░░ 12%                  |
row 27  |round 1 of 3 · tick 5185 · at 2100                              [ ▶ replay ]  |
```

Row 26 is the newcomer glance: copies still running (was `procs`) + territory % (count `owner[]` / 8000) + two 6-block sparks in ember/ice. Row 0 ledger `● · ·` is the match (filled = that name took the round; mid-dot = tie). Clip every line; never wrap. Narrower than 56 cols: drop names from row 26, keep `10  38%    44  12%`. Below camera floor, collapse to header + row 26 + row 27, no field.

## 3. Size ladder

Default `SIZE=cozy`, target pane **80×28** (common half-laptop / tmux). Grand 104×84 stays opt-in via `size.txt=grand` — the whole-core identity, not the daily board.

| tier | pane | field |
|---|---|---|
| grand (opt-in) | 104×84 | 100×80 + 4-col gutter + ruler |
| **default camera** | **80×28** | 80×24 + ring-map |
| tight camera | **32×12** | ≥28×8, no ring-map |
| strip | **20×4** | header + info + voice |
| refuse | **16×3** | one clipped line |

**Do not downsample the board** (2 core rows → 1 terminal row → 100×40 / 104×44). Two cells would share one fg; ownership tint is the only honest thing a braille cell can say. Notes.md already killed this as a default. The 1-row ring-map is the allowed lie: it is labeled a map, majority-hue, locator only. Drop it before you would ever coarsen the field.

## 4. Two clip moments

**First contact.** The first time both hues occupy neighbouring cells, a 0.4s white hairline runs that edge (`sin-hash` of the two addrs + `t`, no RNG). Two continents touch. `REDUCED_MOTION` skips it.

**The darkening.** Keep hitstop + shake + cooling front. Drive the ring-map with the same front: the loser's buckets go ambient in lockstep. One 3-second loop, two scales, glance says who died.

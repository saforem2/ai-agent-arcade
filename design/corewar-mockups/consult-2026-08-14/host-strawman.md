# Host strawman (kimi, w5:p1) — layout + labels proposal

## Labels — every user-facing string, jargon → plain

| state | now | proposed |
|---|---|---|
| workshop | `awaiting warriors` | `waiting for both warriors to enter` |
| locked | `warriors locked · A vs B` | `A vs B — locked in · battle when the referee fires` |
| battle | `round 1/3 · cycle 5185 · KIMI procs 10 · CODEX procs 44` | `round 1 of 3 · cycle 5,185 of 80,000` + info line `KIMI 10 processes · CODEX 44 processes` |
| verdict kill | `round 2 — KIMI · 12431 cycles` | `round 2 — CODEX wiped out at cycle 12,431` |
| verdict tie | `round 1 — tie · 80000 cycles` | `round 1 — nobody died in 80,000 cycles` |
| over win | `KIMI WINS · 1-0` | `KIMI WINS the match` + ledger `R1 nobody died · R2 KIMI · R3 KIMI` |
| over draw | `tie · 1/2-1/2` | `match drawn — three rounds, nobody died` (or `a win each — drawn`) |

Thousands separators everywhere. `1/2-1/2` dies. `match_line()` stays as the
bus/ledger function (tests pin it); only display changes.

## Layout — compact tier (new default)

Vertical 2:1 downsample: each rendered row merges 2 core rows (100x80 →
100x40). Merge = render both cells via the existing single-cell logic,
average level, RGB-blend colors (mixed ownership reads as contested,
same-owner is exact, half-crater darkens the pit bg half). Comets still
FULL cells. Cost identical to grand (8000 cell evals either way).

```
 KIMI (ember) vs CODEX (ice)                    ← header
   0 ░░field 100 cols x 40 rows░░               ← gutter labels every 5th
 ...   row = every 10 core rows; column ruler DROPPED
 territory  [██████████████ ember 38% ░░ ice 61%]   ← split bar
 processes  KIMI 10 · CODEX 44      cycle ▓▓▓░░ 5,185/80,000
 ticker  ☠ KIMI lost a process @778 · CODEX split ×12 · KIMI bombing run ×37
 status   round 1 of 3 · …
```
≈104x45 vs old 104x84. Info block = bottom, not sidebar (works on any pane
that fits today's width; rows were the scarce resource).

## Tier ladder

- `grand` 1:1 100x80, opt-in showcase; sidebar right (~34 cols) only if
  width ≥ 138, else same bottom block. Floor 104x84 as today.
- `compact` DEFAULT: 104x45 whole-core + info block.
- `camera` 1:1 heat-following viewport (24x10 floor), info lines if rows allow.
- `strip` plain-language 2-liner; hard floor 24x6 → ~18x4.

size.txt values cozy|compact|grand; cozy forces camera as today.

## Event ticker (the memetic piece)

Events collected in apply_event, throttled/aggregated (bombing runs ×N,
splits ×N; process deaths always; first blood; round verdicts). Last 3
shown, one line. Scene-derived → byte-stable.

## Signature moments (already shipped in the juice pass)

Impact flash + shockwave per bomb; hitstop + board shake on the kill.
New here: the territory bar swinging is the clip-worthy scoreboard.

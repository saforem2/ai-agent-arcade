# DECISION — Core War board: plain voice + score bar (2026-08-14)

Consulted: grok (herdr, /tmp/cw-design/grok.md), codex2 (herdr,
/tmp/cw-design/codex2.md), internal kimi planner (transcript in session
log), host strawman (/tmp/cw-design/host-strawman.md). This file is the
synthesis and the implementation spec. Repo file to change:
`<arcade>/engine/tui_corewar.py`
(post-juice-pass, 1559 lines) + `test_tui_corewar.py` +
`arcade/design/corewar-mockups/notes.md` addendum.

## Rejected

- **2:1 downsample tier (host strawman)** — REJECTED by all three
  consultants. Decisive argument (planner): pairing two memory cells into
  one braille cell fabricates color (ember+ice averages to a muddy gray
  that reads as cooled/neutral) exactly at contested borders; a crater
  under a live cell stops being a hole; a comet dims. The
  1-cell=1-braille honesty rule stays locked. No downsample tier, ever,
  except a hypothetical clearly-labeled opt-in "atlas" (NOT built now).
- Sidebar info bar — steals columns from the camera where panes are
  wide-short. Bottom stack won 3-0.
- Ticker entries for every bomb impact (grok) — dwarf bombs constantly;
  noise. Ticker carries rare events only.
- codex2's ALL-CAPS voice — house chrome is lowercase; keep it.

## Labels (exact strings; house voice = lowercase, terse)

`match_line()` is unchanged (bus/ledger API, tests pin it). Display only.

| state | new string |
|---|---|
| workshop | `waiting for two programs` |
| locked | `<A> vs <B> · locked and loaded` |
| battle | `round {n} of {total} · step {cyc:,} of {cap:,}` (cap = transcript cycles for the round; if unknown, `step {cyc:,}`) |
| verdict kill | `round {n} · {WINNER} knocks out {LOSER} in {cycles:,} steps` (winner name in faction hue, bold) |
| verdict tie | `round {n} · dead even — both survive {cycles:,} steps` |
| over win | `{WINNER} takes the match` (hue, bold) + ` · {aw}-{bw}` (+ ` · {t} tied` if any ties) |
| over draw | `a dead heat · match drawn` + (` — nobody died in three rounds` if no wins, else ` · one win each`) |
| elim beat (NEW: declare during the beat, not after) | when `sc.elim` is set and its t0 is live: `round {n} · {WINNER} knocks out {LOSER}` (winner hue, bold) |
| floor refuse | ` core war needs 20x4 ` |
| replay-no-op | keep ` · nothing to replay yet` |

Player names (names['r']/['b']) everywhere, not warrior names. Thousands
separators on all cycle counts. Strip-tier fallbacks: same strings,
existing clip mechanics (state words first, counts drop first).

## Layout — bottom stack

Field-adjacent-to-header; the info cluster sits between field and status
(“broadcast lower third”). Per tier (✓ = shown when it fits):

```
grand (opt-in, 1:1):   header / field 80 / ruler / score / status      = 84 rows, 104 cols (unchanged footprint)
camera (default):      header / field VH / [ruler] / [ring-map] / [score] / status
strip:                 header / status                                  floor 20x4 (was 24x6)
```

TOP/BELOW die as fixed constants in favor of a single **chrome plan**:
`chrome_plan(cols, rows, tier)` → which rows exist; called once per
render from fit_geometry (which render already calls), storing PLAN + BW/BH
globals. Both the row-emitter and `_btn_bounds` math read PLAN — never
derive chrome twice (this is the exact-fill flicker/button-offset risk
zone; see regression tests).

Drop order as rows shrink (camera): ruler first, then ring-map, then
score. Status NEVER drops. Banner keeps its current conditional (only if
a row is spare). Slot drop order within the score line as cols shrink:
ticker → ground → ledger → running counts.

## The score line (info bar)

One row, four slots, left-to-right keep-order:

1. **ledger** — `1 KIMI · 2 tied · 3 live` — tallied from
   `sc.rounds[:sc.animated]` + current round as `live`. NEVER leak
   un-animated outcomes (the transcript is complete; the replay must not
   spoil). Before round 1: `rounds —`.
2. **ground** — `ground 41%·58%` (each % in its faction hue; share of all
   8000 cells from sc.owner). Gate: `ground —` until ≥50 cells owned
   (round-start body noise).
3. **running** — `12 vs 3 running` (numbers hued; this replaces "procs").
4. **ticker** — `last: <event>` (see below).

Workshop/locked phases: the whole row is the legend instead —
`colour = ground held · bright comet = running code · dark pit = bomb damage`.

## Ring-map (camera tier only; grok's honest minimap)

One character row, VW buckets, bucket i = addresses
[i*8000//VW, (i+1)*8000//VW). Majority owner by count; if max count <
bucket_size/8 → unowned `░` AMBIENT. Owned: `█` with fg =
scale(HUES[maj], 0.55 + 0.45*mean_heat) (cooled owner → AMBIENT).
Camera window: buckets overlapping the linear span of the viewport rect
get `[` / `]` edge markers in LABEL. Not shown on grand (redundant).
Scene-derived → byte-stable.

## Event ticker (sc.events, max 8, display = latest)

Appended in apply_event / beats; pure scene state (byte-stable). Reset
per-round: milestone flags + first-blood flag (reset_field). Events:
- first crater of the round: `first blood — {name} lands the first bomb`
- process death: `{name}'s copy dies at {addr}` (no throttle; only latest shows)
- elimination: `{name}'s last copy died`
- territory milestones (per warrior per round, fire once each at first
  crossing): `{name} holds half the board` / `{name} holds three-quarters of the board`
- fork bloom (queue length crosses 8, 16, 32, …): `{name} splits: 8 → 16 running`

## Size ladder

- Default SIZE flips `grand` → `cozy` (camera). size.txt values stay
  cozy|grand; invalid/missing → cozy. (Panes that persisted grand keep it.)
- Grand threshold unchanged: 104x84 (1 header + 80 field + 1 ruler +
  1 score + 1 status = 84 ✓; 4 + 100 = 104 ✓).
- Camera viewport floor unchanged: 24x10 → strip.
- Hard floor: 20x4 (was 24x6): header + status, both clipped.

## Shake determinism note (codex2 review point)

The elim shake's per-frame `random.uniform` roll in render() only runs
while SHAKE[0] > 0 (beat is wall-clock-driven; same-(scene,t) headless
renders never have a live shake). Acceptable; the byte-stability test
covers the SHAKE=0 path. No change.

## Tests

Update: furniture test (`round 1 of 1 · step 1,000 of 80,000` + keep
ruler/comet/crater asserts), strip test (`waiting for two programs`),
floor test (20x4 message), exact-fill test (110x40 camera: recompute
chrome rows; assert per-line CONTENT — which row is score/ring-map/
status — not just the newline count; keep the no-trailing-newline
invariant). Unchanged: match_line, pacing, camera easing, juice block,
adversarial block.

New tests: label strings for every state (incl. knockout-during-elim);
ticker events (first blood, death, milestone crossing, split crossing);
ledger never spoils un-animated rounds; ground gate (<50 owned → `—`);
ring-map majority/unowned/camera-brackets/absent-on-grand; chrome-plan
drop order (ruler → ring-map → score); floor 20x4; score-line byte
stability (two renders, same t).

## Docs

Module docstring: visual-encoding + TIMELINE/tier sections updated to the
new chrome. notes.md addendum: consultation record (3 proposals + host),
the rejected downsample with the fabricated-color argument, the bottom-
stack decision, the label table.

## Amendment (2026-08-14, review round)

Header label change, adopting grok's polish: the header drops the
` (ember)`/` (ice)` parentheticals — fixed phrase is now `CORE WAR · {A} vs
{B}` (names keep faction hues) — and the workshop/locked legend line
carries the mapping instead, prefixed `{A} = ember · {B} = ice`. Everything
else in the label table stands.

# Review — Core War voice/layout pass vs DECISION.md

Scope: `chrome_plan`, `status_segments`, `score_slots`, `ringmap_segments`, `push_event`, `render`. No edits.

Labels, ledger (`sc.rounds[:sc.animated]` + current as `live`), ground gate (≥50), ticker strings, ring-map majority/`░`/`█`/cooled-AMBIENT, drop order ruler→ring-map→score, SIZE default cozy, and PLAN-as-single-source for row emission all match the spec. Shake RNG stays on the accepted SHAKE>0 path.

## BLOCKING

**1. Floor refuse wraps (new 20-col floor vs 21-char message).**
`render` writes ` core war needs 20x4 ` (21 cells, spec-exact) whenever `cols < 20` or `rows < 4`. That path is now *narrower than the string*: 19×5 (the floor test pane) and 20×3 both overflow. The old 24×6 floor hid this — the 21-char message always fit a 23-col refuse. Clip, never wrap.

**2. `status_extra` is outside the clip budget; strip drops it.**
Field/grand: after `status_segments` are clipped to `status_budget`, `render` does `status_colored += status_extra` with no second clip. Replay-no-op appends ` · nothing to replay yet` (23). On the camera floor (28×12, no button) that is `   ` + 25-char workshop line + 23 = 51 → wrap. Strip returns before this append, so the mandated replay-no-op is silent on strip. Same string, two failures.

**3. Strip does not clip; the 20×4 floor cannot show the mandated workshop line.**
Spec: floor is header + status, *both clipped*; same strings. Strip still drops whole segments (`used + w > cols - 1: break`). `waiting for two programs` is 25 wide; at 20 cols the entire status is omitted (empty lower row). The 26×12 strip test still passes only because 25 ≤ cols-1. Field-tier `clip_display` is the mechanic the 20-col floor needed and did not get.

## Polish (2)

1. Header is still `CORE WAR · {A} (ember) vs {B} (ice)`. Not in the label table, but it is leftover jargon: names are already faction-hued. Drop the parentheticals; reclaim ~16 cols for names.
2. Score drop order never removes `running` (comment: “never drop”; spec: ticker → ground → ledger → **running**). Clip-only can leave a stray `12` with the label gone. Drop the slot last, as specified.

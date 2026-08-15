# Verify — grok blockers + polish (voice/layout pass)

**SHIP**

1. Floor refuse clipped — SHIP. `clip_display(..., cols)` on the 21-cell message; 19-col and 20×3 panes no longer wrap.
2. `status_extra` budgeted + on strip — SHIP. Extra reserved from the status budget, then clipped, on both strip (`cols-1`) and field (`status_budget`); replay-no-op is visible on strip.
3. Strip clips segments — SHIP. `clip_display` on each segment; 20-col workshop shows a clipped `waiting for two programs`, not a blank row.
4. Header parentheticals → legend — SHIP. Header is `CORE WAR · {A} vs {B}` (hued names); legend is `{A} = ember · {B} = ice · colour = …`.
5. Running droppable-last — SHIP. `score_row_segments` drop order is ticker → ground → ledger → running; a leftover bare count is no longer forced.

# Core War redesign review — BLOCKING

**Verdict: NO-SHIP.** Five blocking issues against `DECISION.md` and the renderer's byte/geometry contracts.

1. **The default camera render is not byte-stable.** `render()` calls `camera_tick(sc)` (`tui_corewar.py:1173`), which mutates global `CAMX/CAMY` on every ordinary-motion render. Two renders of the same scene at the same `t` therefore move the camera and change both field and ring-map bytes. Direct probe at 60x30, cozy, `t=10.0`: first `CAMY=1.69875`, second `CAMY=3.295575`, outputs unequal. The new regression masks this by enabling `REDUCED_MOTION`; cozy/default motion remains broken. This is independent of the explicitly accepted live-shake exception.

2. **Single-round replay leaks completed-match outcomes.** `do_replay(sc, n)` saves the held scene but leaves `sc.animated` unchanged while animating the selected round (`1635-1646`). `score_slots()` then renders every outcome in `sc.rounds[:sc.animated]` (`1087-1094`). Replaying round 1 from a completed three-round match therefore shows all three final ledger results while round 1 is still `live`, directly violating “NEVER leak un-animated outcomes.” The ledger needs a replay-local reveal cursor/current-round identity, not the held scene's completion count.

3. **Three unbudgeted paths can wrap.** The hard rule is clip, never wrap.
   - At the valid 28x14 camera floor, `header_line()` has a 29-column fixed phrase and forces one column per name (`1006-1012`), producing **31 visible columns** in a 28-column pane.
   - The refusal path writes ` core war needs 20x4 ` without clipping (`1166-1170`): **21 columns** in the tested 19-column pane.
   - `status_extra` is appended after `status_budget` is spent (`1297-1312`). At 46x30, workshop plus ` · nothing to replay yet` produces a **51-column** line.

4. **The advertised 20x4 strip has no status in common states.** Strip rendering drops an entire segment when it exceeds `cols - 1` (`1211-1218`) instead of clipping it. At 20x4, `waiting for two programs` is 24 columns, so the status row is blank. Battle and draw strings fail similarly. This violates both `header / status` at the floor and the exact state-label requirement; the existing strip test only covers width 26.

5. **The one-plan invariant is not implemented as specified.** `fit_geometry()` calls `chrome_plan()` to size the core/camera (`1368-1374`), then calls it again to assign `PLAN` (`1379`). `DECISION.md` explicitly requires one call, stored once, because geometry, emitted rows, and button bounds share an exact-fill invariant. The function is pure today, but the implemented structure is still the rejected double-derivation shape.

No additional polish suggestions until these are resolved.

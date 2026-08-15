# NO-SHIP

1. **PASS — camera byte stability:** `camera_tick(sc, t)` is dt-scaled and returns on `dt <= 0`; two default-motion renders of the same camera scene at `t=10.0` were byte-identical.
2. **FAIL — replay spoiler cursor:** ordinary single-round replay now uses `sc.reveal`, but if that replay returns `action == 'replay'`, `do_replay()` switches to a full replay without restoring the snapshot or clearing `sc.reveal`; replaying round 3 then pressing replay starts round 1 while the ledger still exposes rounds 1–2 (`sc.animated=0`, `sc.reveal=2`).
3. **PASS — wrap clipping:** the 28-column camera header, 19-column refusal line, and 46-column `status_extra` paths all stayed within pane width in direct probes, including the replay button case.
4. **PASS — strip status:** 20x4 now renders a clipped, nonblank `waiting for two pro` status line.
5. **PASS — chrome plan:** the selected tier's local `plan` is stored directly in `PLAN` and reused for field height/BH; the only second call is a core-to-camera tier fallback, not a duplicate derivation of the chosen plan.

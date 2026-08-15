# `arcade` CLI — implementation brief (v1)

Roadmap item 2: productize the by-hand match setup. Orchestrator-authored spec;
implementation by external agent; review by a second external agent.

## Shape

- New uv project at `arcade/cli/` with `pyproject.toml` exposing a console
  script named `arcade` (entry `arcade_cli.main:main`). Python 3.11+,
  **stdlib only** (argparse) — no third-party deps in the CLI core.
- Runnable both ways: `uv run --project arcade/cli arcade ...` and
  `uv tool install --editable arcade/cli`.
- The CLI is a *match manager*, not a game engine. It never validates chess
  moves — `ref.py` in the live dir owns that.

## Ground truth it manages

- **Engine (durable)**: `arcade/engine/` — the canonical files.
- **Live dir (volatile)**: `/tmp/chess` by default; every engine file hardcodes
  it, so v1 keeps the convention. CLI accepts `--live-dir` / `ARCADE_LIVE` for
  its OWN reads/writes (status, archive) so tests can use a temp dir, but
  `start` must warn if live dir ≠ /tmp/chess (engine files won't follow).
- **Match dirs (durable)**: `arcade/games/<game>/match-NNN/` (3-digit, next =
  max existing + 1). Each contains `match.json` + archived artifacts.

`match.json` schema (replaces loose names.txt as source of truth):

```json
{
  "game": "chess",
  "match": 4,
  "started": "2026-08-10T15:04:00",
  "seats": {"white": {"agent": "kimi", "name": "KIMI"},
            "black": {"agent": "codex", "name": "CODEX"}},
  "host": {"agent": "grok", "name": "HOST"},
  "live_dir": "/tmp/chess",
  "status": "live",            // live | complete | abandoned
  "result": null,              // e.g. "CODEX 1-0 KIMI (checkmate ply 67)"
  "ended": null
}
```

(The `host` key was `director` before the 2e rename — see
docs/design-history.md §14; `--director` still works as a CLI alias for
`--host`, see below. Older archived `match.json` files still have the
`director` key.)

## Commands (v1)

### `arcade start chess --white kimi --black codex --host grok [--force]`
`--director` still works as an alias for `--host` (2e rename, back-compat).
1. Refuse if the live dir has a non-empty `moves.txt` belonging to a match
   still marked `live` (someone's game in progress) unless `--force`.
2. Allocate next `match-NNN/`, write `match.json`.
3. Deploy: copy the engine runtime set into the live dir —
   `tui_dots.py arcade_panel.py chat_tui.py chat.py game_cli.py game.sh ref.py
   FACILITATOR.md director_keeper.sh approver.sh` (list in one constant).
4. Init state: write `names.txt` (display names WHITE/BLACK lines matching the
   current engine format — READ the engine's expectations from `ref.py` /
   `tui_dots.py` before assuming), preserve `results.txt` (series is
   cumulative), run `uv run --quiet --with chess python <live>/ref.py init`
   (pass `--force` through only when the operator gave `--force`).
5. Print a **runbook**: herdr commands to seat white/black/host agents,
   the host seating prompt (point at `<live>/FACILITATOR.md`, include the
   `CHESS_NAME` export reminder), and the approver.sh note for kimi seats.
   Print, don't execute — the operator (or a wrapper) runs them.

### `arcade status`
Ply count + side to move (ply parity), last SAN, FEN (from `fen.txt`), pending
move if staged, current match number/seats from newest `live` match.json,
series line from `results.txt`. Degrade gracefully when files are missing.

### `arcade archive [--result "CODEX 1-0 KIMI (checkmate ply 67)"]`
Copy `moves.txt fen.txt chat.log results.txt names.txt` from live dir into the
newest `live` match dir; set status=complete, result (from flag, else last
`results.txt` line), ended timestamp. Idempotent: re-archive overwrites its own
copies, never touches the live dir.

### `arcade results`
Series table aggregated from all `match.json` files (+ per-line detail).

### `arcade prompt host`
Print just the host seating prompt (same text `start` prints). `arcade prompt
director` still works as an alias (2e rename, back-compat).

## Backfill

Create `match-001..003` stubs (status=complete) for the three historical games
using `arcade/README.md` "Match history" + `engine/results.seed.txt`. These
have `match.json` only — no artifacts survived. Games 1–3: codex 1-0 kimi,
kimi 0-1 codex, CODEX 1-0 KIMI (Rf5# ply 67).

## Tests

`arcade/cli/tests/test_cli.py`, runnable via
`uv run --project arcade/cli pytest` (pytest as dev-dep only). Cover: match-dir
numbering, start-refuses-over-live-match, deploy file set lands, archive
round-trip, results aggregation. Use tmp_path for live dir and a tmp games
root (games root overridable via `ARCADE_ROOT` env for tests; default =
the arcade checkout inferred from the installed package location, falling back
to the checkout containing the cwd — see `default_root()`).

## Files lifecycle (added post-v1, see match-state-spec.md)

`arcade start` opens a clean room for each new pairing. `chat.log`,
`banner.txt`, `eval.log`, `keeper.log` and `ctl` are per-match: snapshotted to
`<live>/backup/` and then cleared (truncated in place, not unlinked — running
TUIs tail them). `pending.txt`, `result.txt`, `draw_offer.txt`, `TAMPER.txt`
and `roles.txt` are ref-owned flag files, unlinked because their *existence*
is the signal. `results.txt` is the one file that persists across matches —
the cumulative ledger, append-only, never truncated, never filtered on disk.
`names.txt`, `seats.txt`, `roles.txt`, `series.txt` and `banner.txt` are
rewritten fresh every start from the current seats. Every series display
(`series.txt`, `cmd_status`, `cmd_results`) is read through a pairing filter
(`head_to_head`) — `results.txt` spans every pairing the arcade has ever run,
so an unfiltered read of it is, by construction, a different pairing's data
half the time.

## Out of scope (v1)

Human seat polling, xiangqi, herdr auto-seating (print commands only),
engine `/tmp/chess` env-var refactor, board size ctl verb.

## Style

Concise, direct, small functions; only non-obvious comments. Match the
engine's existing tone (see `ref.py`).

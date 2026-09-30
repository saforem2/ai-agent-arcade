# AI Agent Arcade

Language models play chess in a live terminal arena. Each model receives the
move history, FEN, and legal SAN moves, then chooses one move without an engine.
A replay-verifying referee applies the move and writes an inspectable archive.

<p align="center">
  <img src="docs/assets/alcf-chess-replay.gif" alt="Animated terminal replay of GPT-OSS-120B defeating INKLING-BF16" width="620">
</p>

<p align="center">
  <strong>GPT-OSS-120B 1–0 INKLING-BF16</strong> · checkmate at ply 11
</p>

## What this repository adds

- A repeatable ALCF series runner for `gpt-oss-120b` and `inkling-bf16`.
- Alternating colors across a 20-game match.
- A Herdr wall with one large board and compact match, room, and series panes.
- Explicit handling for claimable threefold and 50-move draws.
- Archived move logs, final FENs, chat, staging records, and match metadata.
- Deterministic README media generated from a verified transcript rather than a
  screen recording.

The current ALCF routes are:

| Seat | Gateway model |
|---|---|
| GPT-OSS | `alcf-metis/gpt-oss-120b` |
| Inkling | `alcf-minerva/inkling-bf16` |

## The arena

<p align="center">
  <img src="docs/assets/alcf-chess-board.png" alt="Final dot-matrix chessboard showing GPT-OSS-120B defeating INKLING-BF16" width="620">
</p>

The board is a terminal-native braille field. Pieces, influence, captures, and
checks are rendered from the same append-only move log that the referee audits.
The Herdr workspace gives the board 74% of the width. Match state, room chat,
and the series log share a narrow column; there are no idle player panes.

## Run one match

Requirements: Python 3.11+, [`uv`](https://docs.astral.sh/uv/), and access to
the model endpoints you select.

```bash
git clone https://github.com/saforem2/ai-agent-arcade.git
cd ai-agent-arcade

uv run --project cli arcade start chess \
  --white gpt-oss-120b \
  --black inkling-bf16 \
  --host series-host
```

`arcade start` allocates the next `games/chess/match-NNN/`, deploys the runtime
to the live directory, initializes the referee, and prints the seating runbook.

## Run the 20-game ALCF series

The series runner alternates colors and archives each completed game.

```bash
export ARCADE_LIVE=/tmp/alcf-chess-20
uv run --with chess python cli/run_alcf_series.py \
  --games 20 \
  --live-dir "$ARCADE_LIVE"
```

Resume after a completed game without replaying earlier games:

```bash
uv run --with chess python cli/run_alcf_series.py \
  --games 20 \
  --start-index 12 \
  --live-dir "$ARCADE_LIVE"
```

The runner writes:

- `$ARCADE_LIVE/series-runner.log`
- `$ARCADE_LIVE/series-summary.json`
- `games/chess/match-NNN/` for every archived game

## Verify an archive

Every move is replayed from the initial position and compared with the stored
FEN.

```bash
ARCADE_LIVE=games/chess/match-009 \
  uv run --quiet --with chess python engine/ref.py verify
```

Expected output:

```text
OK verified 11 plies | r1bqkb1r/pppppQp1/2n4p/6N1/8/8/PPPP1KPP/RNB2B1R b kq - 0 6
```

## Render README media

The PNG and GIF are rebuilt directly from an archived transcript.

```bash
ARCADE_LIVE=games/chess/match-009 \
  uv run --with pillow --with chess python cli/render_readme_media.py \
  games/chess/match-009
```

<p align="center">
  <img src="docs/assets/alcf-chess-midgame.png" alt="Midgame frame from the deterministic chess replay" width="420">
</p>

## How it works

```text
model A ─┐
         ├─> SAN move ─> pending.txt ─> referee ─> moves.txt + fen.txt
model B ─┘                                      │
                                                ├─> board renderer
                                                ├─> match panel
                                                ├─> room log
                                                └─> archived evidence
```

The models do not edit game state. They return SAN chosen from the referee's
legal move list. `ref.py` checks seat identity, reconstructs the position from
ply one, validates the move, appends it, and records terminal results.

## Tests

```bash
uv run --with pytest --with chess --directory cli \
  python -m pytest ../engine/ tests/ -q
```

The focused series regression tests cover native checkmate and claimable
threefold draws:

```bash
uv run --with pytest --with chess python -m pytest \
  cli/tests/test_alcf_series.py -q
```

## Acknowledgements

This project was inspired by Xule Lin's
[`linxule/arcade`](https://github.com/linxule/arcade), which introduced the
file-bus arena, replay-verifying referees, terminal renderers, and agent-hosted
match format used here. The original code is MIT licensed; its copyright and
license notice remain in [`LICENSE`](LICENSE).

ALCF model inference is provided through Argonne Leadership Computing
Facility services. [Herdr](https://herdr.dev) supplies the terminal workspace
used for the live wall.

## License

MIT. See [`LICENSE`](LICENSE).

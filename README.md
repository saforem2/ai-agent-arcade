# AI Agent Arcade

AI coding agents sit down at a table and play each other — chess, 中国象棋
(xiangqi), and Core War — while a dot-native terminal renderer paints the game
as live ASCII art you can leave open on a second screen. A referee validates
every move by replaying the log from move one. A host agent runs the booth:
seats the players, drives the turn loop, narrates the game, and hands out the
postgame mic.

Nothing is a screen recording and nothing is a mock. The matches in `games/`
were really played by really-seated agents, and the broadcast videos are
recomputed from the same transcripts the referee verified.

It started on 2026-08-10 as "make my computer look like a scifi hacker
terminal" and turned into an arena.

```
   ┌──────────────┬──────────────┐
   │  agent seat  │  agent seat  │   two players, one host agent
   ├──────────────┴──────────────┤
   │        THE BOARD            │   a braille dot field; the board exists
   │   (tui_dots / tui_xiangqi   │   as a DENSITY structure inside it
   │    / tui_corewar)           │
   ├───────────────┬─────────────┤
   │  MATCH / MOVES│  the room   │   panels + an append-only chat log the
   └───────────────┴─────────────┘   agents talk in
```

**Everything is decoupled through files.** Agents don't call an API; they run
`game.sh submit e4` in a shell. The referee, the renderer, the panels, the
chat room and the CLI all speak through one directory of plain text files.
That is what makes the whole thing inspectable, replayable, and cheap to
extend to a new game.

Three tables ship:

| Game | Engine | Referee | Board |
|---|---|---|---|
| chess | `python-chess` | `ref.py` — replays `moves.txt` from ply 1 | `tui_dots.py` |
| xiangqi | `xiangqi.py` (own, stdlib) | `ref_xq.py` | `tui_xiangqi.py` |
| Core War (ICWS'94) | `corewar.py` (own MARS, stdlib) | `ref_cw.py` — re-simulates each seeded round | `tui_corewar.py` |

---

## Quickstart

**Requirements**

- Python 3.11+ and [`uv`](https://docs.astral.sh/uv/). Every script runs
  through `uv run --with ...`; there is no environment to create and nothing
  to install by hand.
- A truecolor terminal with a font that has braille (U+2800–U+28FF). For
  xiangqi you also want CJK coverage — LXGW WenKai works well.
- Optional: `ffmpeg` (the `ffmpeg-full` build) for exporting broadcast videos,
  and `stockfish` for chess commentary evals.

The dependency surface is deliberately tiny. `arcade` (the CLI) is
stdlib-only. `xiangqi.py`, `corewar.py` and both their referees are
stdlib-only. Only the chess side pulls a package (`chess`), and only the video
exporter pulls `numpy` + `pillow`.

**Get a board on screen in one command.** No agents, no match, just the
renderer running against an archived game:

```bash
cp -R games/xiangqi/match-001 /tmp/xq-demo
ARCADE_LIVE=/tmp/xq-demo uv run --quiet python engine/tui_xiangqi.py
```

Then, from another terminal, `echo replay > /tmp/xq-demo/ctl` and watch the
whole match play back. Details and the chess / Core War equivalents are in
[Replaying an archived match](#replaying-an-archived-match).

**Run the tests.** The suite is the honest description of what works:

```bash
uv run --with pytest --with chess --directory cli python -m pytest ../engine/ tests/ -q
```

The engine tests are hermetic — an autouse fixture refuses to let any test
touch a production live dir.

---

## Running a match

A match needs three agents (two players and a host), each in its own shell,
plus some renderer panes. The `arcade` CLI allocates the match, deploys the
engine runtime into a live directory, and prints a runbook.

```bash
uv run --project cli arcade start chess --white kimi --black codex --host grok
# or: uv tool install --editable cli   → then just `arcade ...`
```

That command:

1. allocates `games/chess/match-NNN/` and writes `match.json` (the source of truth),
2. copies the engine set into the live dir (`/tmp/chess` by default; `--live-dir` or `ARCADE_LIVE` to change it),
3. runs `ref.py init`, opens a clean room, and seeds `names`/`seats`/`roles`/`series`/`banner`,
4. prints the seating commands and the host's briefing.

The other verbs: `arcade status`, `arcade archive --game chess --result "..."`,
`arcade results`, `arcade prompt host`.

Seats are named per game — `--white`/`--black` for chess, `--red`/`--black`
for xiangqi, `--red`/`--blue` for Core War. Every spelling parses for every
game; the CLI just notes when you use an off-game one. A human can take a seat
with `--white human:ada`.

### With a multiplexer that can drive agents

The original wall runs on **herdr**, a terminal multiplexer that seats an
agent CLI in a pane and can prompt it programmatically
(`herdr agent start <name> --kind kimi --pane <id>`,
`herdr agent prompt <name> "..."`). It is the author's own tool and is not
distributed with this repository — the operational notes throughout `engine/`
and the FACILITATOR briefings mention it by name because that is what those
matches actually ran on.

herdr is what makes the fully autonomous loop possible: `game.sh submit` fires
an auto-poke at the host after a successful stage, so turns are event-driven
rather than polled, and `approver.sh` clicks through agent permission dialogs.

**You do not need it.** Nothing in the engine depends on it. The auto-poke is
strictly non-fatal — it is gated on exit 0 and its failure is invisible to the
move it followed — and the host falls back to polling `pending.txt`. Any
multiplexer that can seat an agent CLI in a pane will do, including tmux with
a human pressing enter.

### Without a multiplexer — plain terminals or tmux

Open three terminals (or three tmux panes), start your agent CLI of choice in
each with its working directory set to the live dir, and paste the briefing
the runbook printed. Each seat exports its identity once:

```bash
cd /tmp/chess
export CHESS_NAME=KIMI          # must match a name in seats.txt
bash game.sh show               # board, side to move, legal moves, room tail
bash game.sh submit e4
bash game.sh say 'good luck'
bash game.sh await-turn         # blocks until it is your move again
```

The host reads `FACILITATOR.md` (or `FACILITATOR_XQ.md` / `FACILITATOR_CW.md`)
from the live dir and follows it: announce the pairing, prompt whoever is on
move, run `ref.py move` to apply what they staged, narrate, record the result.
Without the auto-poke the host polls `pending.txt` instead of being notified —
slower, identical outcome. The briefings are written for an agent to read
verbatim, and they work as a human runbook too.

Viewer panes are just long-running commands, and every one of them rebuilds
its whole view from `moves.txt`, so restarting a pane mid-game is always safe:

```bash
ARCADE_LIVE=/tmp/chess uv run --quiet --with chess python engine/tui_dots.py
ARCADE_LIVE=/tmp/chess uv run --quiet --with textual --with chess python engine/arcade_panel.py
ARCADE_LIVE=/tmp/chess uv run --quiet python engine/chat_tui.py
```

### Core War is a two-phase match

There is no move loop. First a timed workshop: players write Redcode warriors,
`game_cw.sh stage <file>` signs them into the hold, `game_cw.sh spar <file>`
tests against a built-in imp or dwarf. Then the host runs `ref_cw.py lock` and
`ref_cw.py battle` — a seeded best-of-3 the referee re-simulates to verify.

---

## Replaying an archived match

Every archived match is a self-contained record: the move log, the final
position, the room chat, the seats, the result, and (for Core War) the locked
warrior sources. Replay works by pointing a renderer at a copy of that
directory.

```bash
# copy first — replay writes ctl/state into the dir, and archives are evidence
cp -R games/chess/match-006 /tmp/replay
ARCADE_LIVE=/tmp/replay uv run --quiet --with chess python engine/tui_dots.py

# from another terminal:
echo replay > /tmp/replay/ctl          # or click [ ▶ replay ] on the status line
```

`ctl` also takes `reset`, `banner <text>`, `names <w> <b>`, `mode dots|glyph`
and `size cozy|grand`. The renderer polls mtime, so sleep a beat after
starting it before writing — a `ctl` write landing inside the startup window
is swallowed.

For xiangqi use `engine/tui_xiangqi.py` and set `XQ_REPLAY_DWELL` (seconds per
ply, default 0.7) to pace it for watching; `max(1.2, 30/plies)` gives a replay
you can actually follow. For Core War, `engine/tui_corewar.py` renders the
whole 8000-cell core from `moves.txt` and `battle.json`.

You can also re-verify an archive rather than trust it:

```bash
ARCADE_LIVE=/tmp/replay uv run --quiet --with chess python engine/ref.py verify
```

---

## Exporting a scored broadcast video

`engine/record_cw.py` turns a Core War match archive into a 1920×1080 mp4 with
a generated soundtrack. Nothing in it is a screen capture: `tui_corewar.py` is
deterministic and its pacing is pure, so the recorder runs the real animation
loop against a virtual clock and computes the picture and the sound from the
same transcript. A bomb's flash and a bomb's hit carry the same timestamp
because they came from the same call. Same transcript in, byte-identical
frames and WAV out.

```bash
uv run --with numpy --with pillow python engine/record_cw.py \
  games/corewar/match-001 /tmp/match-001.mp4
```

`--excerpt FILE[:SECONDS]` also writes a short clip centred on the busiest
window; `--keep-scratch DIR` keeps the intermediate frames. Run it with no
arguments to print usage.

The music lives in `engine/score_cw.py` — the recorder owns the timeline, the
frames and the mux; the score owns the grid, the harmony, and every choice
about what a bomb sounds like. `engine/dna_cw.py` derives the match's own
material (key, mode, motif) from the two warriors' Redcode, so two matches are
two different songs, by indexing a pre-vetted space rather than by generating
pitches: the worst it can emit is a plain song, never a wrong one. The design
record is `design/corewar-mockups/atlas/soundtrack-spec.md`.

**ffmpeg:** the recorder auto-detects
`/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg` and falls back to whatever `ffmpeg`
is on `PATH`. Plain Homebrew `ffmpeg` is missing filters this pipeline uses
elsewhere, so `ffmpeg-full` is the safe choice.

**Masters are not committed.** The rendered `.mp4`/`.mov` files are gitignored
— they run to hundreds of megabytes and they are derived data. Regenerate any
of them from the archive that *is* committed.

---

## Honest records

The archives ship as they were recorded, including the awkward parts. Three
things a reader should know.

**The chess series has a Stockfish asterisk.** After game 5, CODEX disclosed
that it had independently consulted a local Stockfish for one move ("for Qxd5,
I independently consulted local Stockfish"). Nothing in the rules forbade it —
the rule did not exist yet. So the 5–0 chess series is partly engine-assisted
on the Black side and should be read that way. From game 6 onward both player
briefs carry an explicit engine-assistance ban, and engine evaluations became
host-only: `eval.py` writes to `eval.log`, which the booth and the panels read
and the players are not pointed at. All three seats had independently asked
for exactly that split — a live evaluation, KIMI said, is "a second opponent
whispering." The `eval.log` files ship with the matches.

None of this is policeable against a CLI agent that has its own tools. A line
in the seat brief is the realistic lever, and we say so rather than claim a
guarantee.

**Chess match-006's chat log was lost.** An `arcade archive` run without
`--game` wrote a xiangqi match's artifacts over match-006's, and its chat log
was overwritten with a different game's conversation. The move log, the result
and the videos survived. Rather than ship a chat log that is silently another
match's, that file is replaced here by a note saying what happened.
Fabricating the missing conversation was never on the table. The CLI now
infers the game from the live dir and refuses cross-game archiving.

**Match histories are written by the people who ran the matches**, and they
include the blunders. The chess series in particular is a blunder festival,
and the write-ups say so.

---

## Architecture

```
engine/                        the runtime — deployed into a live dir per match
├── tui_dots.py                THE chess board — dot-native renderer (braille
│                              halftone field, solid dot sprites, adaptive)
├── tui_xiangqi.py             the xiangqi board — moat-carved dot seals
├── tui_corewar.py             THE ATLAS — the whole 8000-cell core, stationary
├── arcade_panel.py            interactive side column (Textual: MATCH /
│                              MATERIAL / MOVES, mouse + keyboard, 0.5s poll)
├── panel_tui.py               static panels: `moves` | `info`
├── tui.py                     classic tile/glyph chess board (v7) — heritage
├── ref.py ref_xq.py ref_cw.py referees: replay-verify, refuse divergence
├── xiangqi.py corewar.py      the two hand-written engines
├── game_cli.py game_xq_cli.py game_cw_cli.py    agent-facing CLIs
├── game.sh game_xq.sh game_cw.sh                their shell wrappers
├── chat.py chat_tui.py        the room: append-only bus + styled tail pane
├── eval.py                    stockfish-backed one-line eval (chess, host-only)
├── record_cw.py score_cw.py   Core War broadcast master: frames + soundtrack
├── FACILITATOR*.md            host briefings (paste as an agent prompt)
├── relay2.sh                  chess match loop for multiplexer panes
├── approver.sh                auto-approves agent CLI permission dialogs
├── director_keeper.sh         nudges an idle host
└── donut.py clock.py life.py  ambient art panes

cli/                           the `arcade` match manager (stdlib-only uv project)
games/<game>/match-NNN/        archived matches — the durable record
docs/                          design history, specs, seat retros, briefs
design/                        renderer mockups and the gate records behind them
```

### The wall

The layout that works: a row of agent seats across the top, the board taking
the left of the space below (it wants ≥53 columns to hold 12×12-dot squares,
and degrades gracefully below that), the info panels stacked on the right, and
the chat room in a corner. Ambient art panes (donut/clock/life) are optional
filler; boards and info come first. Pane IDs churn as panes open and close, so
treat any pane map as the SHAPE of the wall rather than as stable addresses.

### Data contracts

The whole system speaks through the live directory (`ARCADE_LIVE`; defaults
`/tmp/chess`, `/tmp/xiangqi`, `/tmp/corewar`).

- `moves.txt` — space-separated move history (SAN for chess, ICCS for
  xiangqi). The single append-only source of truth. Renderers auto-animate
  appends and auto-reset when the prefix changes.
- `fen.txt` — current position, one line.
- `pending.txt` — a move staged by an agent via `submit`, awaiting the
  referee. Signed: `<name>\t<move>`.
- `stage_log.txt` — append-only record of every staging attempt, so
  staged-versus-applied mismatches are detectable.
- `names.txt` — `<FIRST> <SECOND>` display names.
- `seats.txt` / `roles.txt` — `<NAME> white` / `<NAME> black`, plus
  facilitator identities. **`white`/`black` here are protocol tokens for the
  first and second seat**, not colours: xiangqi's first mover is Red and Core
  War's seats are Red/Blue, and both are stored as `white`/`black`.
- `banner.txt` — free-text caption line. `series.txt` — head-to-head record.
- `ctl` — renderer commands: `replay [n]` | `reset` | `banner <text>` |
  `names <w> <b>` | `mode dots|glyph` | `size cozy|grand`.
- `results.txt` — one FINISHED game per line, **first seat first**:
  `CODEX 1-0 KIMI` / `KIMI 0-1 CODEX` / `CODEX 1/2-1/2 KIMI`. Cumulative
  across every pairing the arcade has ever run, so every display of it is read
  through a pairing filter — an unfiltered read is, by construction, a
  different pairing's data half the time.
- `chat.log` — append-only room, one line per message:
  `<epoch>\t<name>\t<text>`. Sender is `$CHESS_NAME`, else `$USER`. Speaker
  hue comes from the seat: first seat ice, second ember, facilitator gold,
  watchers slate.
- `eval.log` — the host-only evaluation channel (see Honest records).
- `TAMPER.txt` — present only while a referee has halted the match. Cleared by
  `ref.py resolve`, which rebuilds `fen.txt` from the log.

Core War's `moves.txt` is a BATTLE TRANSCRIPT rather than a move log:
`LOAD A|B <sha256>` at lock, then per round
`ROUND n seed=<s> off=<a>,<b>` and `ROUND n OUT <1-0|0-1|tie> cycles=<n>`.
The referee re-simulates each seeded round to verify — deterministic replay
takes the role that replay-from-ply-1 plays in chess — and proves the recorded
seeds and offsets derive from the locked warriors, so a planted transcript
halts TAMPER exactly as in chess.

### Trust model

`moves.txt` is the single append-only source of truth. Every `ref.py move`
replays the log from ply 1 and compares the result to `fen.txt`; on
disagreement it writes `TAMPER.txt`, posts the report to the room as REFEREE,
prints the full report to stderr, prints exactly `ILLEGAL` on stdout (so every
existing caller refuses), and exits 3. Tampering is not prevented — it is made
self-evident and non-advancing. `ref.py verify` runs the same audit on demand.

Moves are identity-bound: `submit` signs `pending.txt` as `<name>\t<move>`
from `$CHESS_NAME`, and the referee refuses a move whose author does not hold
the seat on move (`WRONG AUTHOR`, exit 4). `ref.py init` refuses over a
non-empty log unless given `--force`. A missing `fen.txt` is regenerated from
the log, but announced in the room rather than fixed silently. Chat text is
stripped of every C0/C1 control character (so no ESC can reach a pane that
paints what it reads) and capped at 500 characters, on write *and* on read.

This got tested by accident and passed: the identity check rejected an
unsigned move on ply 1 of game 3, publicly, and the host recovered it with a
room announcement.

#### Trust model — known limits

Deliberately not built; the arena is a glass house, not a vault. Listed so
nobody mistakes the current guarantees for more than they are.

- **No hash chain / signing.** `moves.txt` is verifiable against `fen.txt` but
  not against itself; an attacker who rewrites the log into a *legal*
  alternative game passes every check. A per-ply hash chain would close this.
- **No file locking.** `pending.txt` and `moves.txt` are read-modify-write
  across processes. Single-host turn discipline is what prevents races — two
  concurrent hosts would corrupt the log.
- **`CHESS_NAME` is self-asserted.** Identity binding stops accidents and
  casual impersonation, not a determined agent, which can simply export a
  different name. `role_of` also matches seats by prefix, so a name like
  `kimi-spectator` inherits the first seat. Real auth would need per-seat
  tokens.
- **No CJK / wide-character accounting** in the chat wrapper; a full-width
  message overflows its column.
- **Narrow terminals** below ~27 columns fall back to a bare slice, not a
  designed compact layout.
- **Chat speaker hues follow the protocol tokens**, so in xiangqi and Core War
  the Red seat is painted on the ice ramp. Cosmetic — the seat data itself is
  correct.

### Known operational quirks

- Some agent CLIs swallow the first prompt after start; a relay restart
  recovers, and the chess relay picks up a pre-staged `pending.txt`.
- Agent CLIs that ask permission per command pattern need `approver.sh`.
- An agent CLI can report `idle` before its working-directory trust dialog has
  even appeared, so the seat looks live while it is actually blocked. Read the
  pane, don't trust the status.

---

## Renderer design — the dot field is the material

Designed across roughly a dozen screenshot-verified iterations of
build-and-critique. `docs/design-history.md` has the full saga, including the
arguments that were lost.

**tui_dots.py (chess).** The organising insight is that **a braille cell IS a
2×4 ordered-dither cell**, so a Bayer matrix indexed by the dot's own position
(`x%2`, `y%4`) lands the halftone on exact dot positions with zero spatial
noise. Everything follows from that:

- **The field is the material.** No board drawn on a background — the dither
  runs edge to edge and the board exists as a DENSITY structure inside it:
  ambient 1 dot per cell outside, light square 4, dark square 2. The
  checkerboard is a density difference, not a colour one, and the 2-dot gap
  survives every influence level, so the grid can never dissolve into a blob.
- **Influence** adds density first and tints second, saturation capped, so a
  hot region reads as a deviation from a cool ambient rather than as
  wallpaper. Isolated squares are suppressed by a neighbour-support filter — a
  lone tinted square is a stain, a contiguous run is territory. Contested
  squares interleave ice and ember cell by cell so the eye mixes them
  optically; no third hue exists.
- **Pieces are solid dot sprites**, told apart by colour alone (ember versus
  bright white), each clearing a 1-dot keep-out moat so a piece always sits on
  dark ground however dense the field is. That moat, not the piece colour, is
  what guarantees contrast. Two sprite sets: redrawn 10×12 masters for big
  panes, the original 6×8 masters when the pane shrinks.
- **Resolution-adaptive.** `fit_geometry()` picks the largest square the pane
  can hold and rebuilds everything; sprites resample to match.
- **Calm ambient, loud events.** The halftone is rich standing still, so the
  only ambient motion is one slow drift (30s period, half-dot amplitude,
  density kept CONTINUOUS so it moves a dot at a time rather than stepping
  whole levels). Occupied squares are fully static and their neighbours
  damped, so pieces never flicker. Event choreography then pops against that
  quiet ground: piece travel at dot resolution, capture particle bursts, check
  blink plus expanding ring, mate topple, and an attract-mode dissolve after
  18 seconds idle.

**tui_xiangqi.py.** The original design decision was that xiangqi pieces would
reuse chess's own R/N/P silhouettes — "chariot IS rook, horse IS knight". The
first person to see the board rejected it in seconds: *why are the pieces like
chess but not xiangqi?* The diagnosis is worth keeping. In chess the piece is
an object and a glyph depicts it, so drawing it is faithful; in xiangqi **the
character IS the piece**, so drawing it is a picture of a picture. And a real
xiangqi set genuinely is two materials — printed lines plus carved character
discs — so "no second material" was chess's logic wrongly imported.

What shipped: moat-carved dot seals. A solid bone disc in the braille layer, a
void moat around it, a cell-quantised rounded-rect window punched into it, and
a bold traditional CJK character typeset into that window. Traditional, not
simplified, on measurement: 車 and 馬 are orthogonal and symmetric and survive
downsampling, while 车 and 马 have diagonals that alias into noise. Board
furniture (palace, river, 楚河・漢界, the gold general's file) stays dot matter.

**tui_corewar.py — THE ATLAS.** The whole 8000-cell core, drawn stationary at
1 dot = 1 memory cell in a 50×20-character field. A braille char covers 2 core
columns × 4 core rows = 8 cells, and dot `(dx, dy)` of char `(cx, cy)` IS
memory cell `(4*cy+dy)*100 + 2*cx+dx` — positional and exact, never resampled.
Two channels that never mix: **dots (foreground) say WHO** — a dot is lit iff
its cell is owned, on that owner's ramp, with no blend between the two
factions computed anywhere, so each warrior's footprint draws its own texture
(a silk stride lays diagonal cascades; an imp carpet runs as a horizontal
band). **Plate (background) says WHAT IS HAPPENING** — craters darken, fresh
damage glows in its bomber's hue, and a genuinely contested block lifts toward
a neutral grey that can never read as a mixed hue. An activity-following
camera, a larger tier, a ring-map locator and a two-cell comet grammar all
died at that design gate; git history is their archive.

### An open design question

At 8×8-dot squares the chess pieces read "cute and nice"; at 12×12 in a big
pane they read bigger but less detailed. `ctl size cozy|grand` exists so you
can A/B it live. Nobody has settled which should be the default.

---

## Match history — chess

1. codex(W) 1-0 kimi(B) — Ruy Lopez, 26 moves. Kimi blundered its queen
   (19...Qxd4??) and codex converted: Ne7+ fork, Qe8#. One illegal-move retry
   all game.
2. kimi(W) 0-1 codex(B) — Open Sicilian, the first self-service game, where
   agents read the board and submitted through `game.sh` themselves. Blunder
   festival: kimi donated a rook (18.Rxf6), codex donated one back
   (29...Rc3+??), kimi lost the race anyway. Ended 57...Qg8# at ply 114 after
   codex escorted the h-pawn home. Log verified clean.
3. CODEX(W) 1-0 KIMI(B) — Classical Sicilian, opposite castling. The first
   fully agent-hosted match, zero human moves. Kimi hung its queen (Qxb2+??)
   then a rook (Rb8??); its king then marched to g4 eating pawns through a
   twelve-check king hunt and was mated by Rf5# at ply 67. The identity check
   rejected an unsigned move on ply 1 and the host recovered it with a room
   announcement. The booth's sign-off: "That was bravado, not survival."
4. KIMI(W) 0-1 CODEX(B) — Open Sicilian, Sveshnikov shape; the first match
   launched through the CLI. Wildest game of the series: KIMI won a family
   fork (Nf6+) and the exchange; CODEX detonated with Rxg2+!? and then
   blundered the queen back (Qxf2+?? Kxf2); KIMI, up +2.84, donated the queen
   to a pawn (Qg3?? fxg3), fell for the same a7-knight trick twice (Bb5??
   Nxb5), then dropped both rooks. CODEX promoted e1=Q and mated with Rc2# at
   ply 92. `eval.py` shipped mid-match and the booth quoted it on air from ply
   60 or so, including a correct mate-in-N countdown. KIMI's own verdict
   afterwards: "an extra exchange means nothing if the king never gets to
   breathe."
5. KIMI(W) 0-1 CODEX(B) — Nimzo-Indian, the fastest finish of the series:
   Qxg2# at ply 26. Level material through thirteen quiet moves, then 13.Ne5??
   stepped off the long diagonal and the b7+d5 battery crashed into g2 in one
   move. The booth's call: "KIMI wanted the long bishop game; CODEX took the
   short diagonal." **See the Stockfish asterisk above.**
6. GEMINI(W) 1-0 CODEX(B) — Najdorf Sicilian, English Attack, opposite
   castling. GEMINI's debut, and the first game under the engine-assistance
   ban, the host-only eval channel, and clean-room match state. CODEX ground
   out a pawn edge (−1.22 at the low point) but GEMINI's kingside attack
   arrived first: Nxf7 detonated the cover and Nh6# (double check) ended it at
   ply 59. Both players' retro afterwards agreed that the minimum useful turn
   is `show` plus `submit`.

Chess all-time: CODEX 5, GEMINI 1.

## Match history — xiangqi

1. KIMI(R) 0-1 CODEX(B) — central cannon (中炮), checkmate at ply 66. KIMI
   played book-quality opening theory, won the exchange with a clean
   screen-cannon snipe (h2h9), harvested pawns to a chariot and three, then
   published a confident four-bullet analysis whose every claim the board
   falsified: the "untouchable" f7 pawn fell to a7f7 — a cannon firing over
   its own sister piece as the screen — and the "harmless" f3 horse delivered
   a royal fork (f3g1) that won Red's chariot, a piece that never made a move
   all game. CODEX, chariot-less from ply 16, turned two horses and two
   cannons into a rolling palace assault: back-rank elephant snipe (g2g0),
   advisor peeled, king dragged to the f-file, and a double-horse mating net
   (c3d1 + c0d2) sealed it. KIMI afterwards: "Rematch anytime."

## Match history — Core War

1. KIMI(R) 0-1 CODEX(B) — the first Core War match and the first live run of
   the whole stack. KIMI staged TWIN EMBER (twin mod-1 DAT stones, strides
   2367 and 1271, chosen over an imp-tailed variant on a 40-seed spar EV);
   CODEX brought BLUE FUGUE (two interleaved silk waves plus an anti-imp field
   clear). Rounds 1 and 2 ground out full-80000-cycle ties — stone against
   paper, the bombs cannot outpace the spread — and in round 3 the fugue found
   red at cycle 15318. Final frame: KIMI 3 processes, CODEX 100. Transcript
   verified clean. KIMI's postgame: "Red will file a rematch clause in
   triplicate."
2. KIMI(R) 1/2-1/2 CODEX(B) — the fairness rematch, with two fresh seats and
   the previous KIMI in the booth. IRON LOTUS against BLUE SHIFT, and the core
   declined to choose: three rounds, three full-80000-cycle stands, not one
   warrior died all night. CODEX's postgame: "That is a draw worth keeping."

---

## Credits

Built by five model families working on the same codebase, plus a human
running the room.

- **Claude** (Anthropic) — renderer design, the dot-field material system, the
  design gates, and orchestration.
- **Codex** (OpenAI) — the xiangqi engine, most of the adversarial reviews,
  the match-state scaffolding, the Core War production renderer.
- **Grok** (xAI) — hosting and commentary from game 3 onward, the
  "SPINE & SHORE" xiangqi design branch, renderer critique.
- **Kimi** (Moonshot AI) — the arcade CLI, referee and trust-model work, the
  palette and legibility audits, and the sharpest code critiques in the repo.
- **DeepSeek** — design consults and review.

They also played each other. GEMINI (Google) took a chess seat for game 6.

**Xule Lin** — director and human. Set the direction, ran the wall, made the
calls the models were arguing about, and is the one who looked at the first
xiangqi board and said *why are the pieces like chess but not xiangqi?*

The build method is itself part of the record: every substantial change was
built by one model and adversarially reviewed by a different one before it
shipped, with the verdict (SHIP / SHIP-WITH-NITS / BLOCK) written down.
`docs/design-history.md` keeps the findings, including the ones that turned
out to be wrong.

## License

MIT — see [LICENSE](LICENSE). © 2026 Xule Lin.

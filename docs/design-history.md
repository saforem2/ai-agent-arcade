# Board Renderer Design History

Two design cycles in one day (2026-08-10), by a critique loop: Claude
(orchestrator) + Opus subagent (designer with implementation authority +
screenshot self-verification) + Kimi (critic via kimi-ask) + the user as the
final eye. Preserved here so future work inherits the reasoning, not just the code.

- **Cycle 1 (§1-§7)** built `engine/tui.py`, the tile/glyph board, v1 → v7.
- **Cycle 2 (§8)** built `engine/tui_dots.py`, the dot-native board, which the
  user then promoted to THE board. `tui.py` is heritage — still runs, no pane.

The through-line of both cycles: **measure before prescribing.** Nearly every
round, the fix that survived came from counting something (isolated squares,
dot-mass parity, density swing) rather than from arguing about taste.

## v1 — light tan board (chess.com colors), truecolor bg, unicode pieces
Worked, but flat. User asked for "ASCII-native and mesmerizing."

## v2 — dark + ░▒▓ influence heatmap (FAILED)
Per-square fg shade chars by attack pressure, per-square sine phase.
User verdict: "the visual is worse lmao." Lesson: dither chars at low alpha on
dark bg = mud; 64 independent oscillators = noise.

## v3 — first Opus+Kimi synthesis
Root causes found by Opus: alpha ceiling 0.6 destroyed the checkerboard;
max(w,b) over-triggered contested; per-square phase (f+r)*0.85 ≈ noise wavelength;
frame-count timing lurched with render rate. Kimi: violet contested hue was
"where the mud lives"; 64 oscillators "a screensaver, not life."
Shipped: whole-pane painting (theme-proof board-as-object), PEDESTAL system
(White pieces on darkened squares emit light; Black on lightened squares absorb;
contrast solved structurally), net-pressure two-hue field (ICE (120,210,235) /
EMBER (240,160,70)), ALPHA table capped ~0.22, ONE traveling wave (6s, one
diagonal wavelength), wall-clock animation, capture flash+shockwave, heartbeat
check, ember trails, winner wash. Palette anchors: PANEL (26,30,40), MATTE
(18,21,29), SQL/SQD bases, GW/GB glyphs — see tui.py header block.

## v4 — Opus round 2 (self-critique from screenshot)
Influence alpha recurve {1:0.20, 2:0.27, 3:0.32, 4:0.36} — "any pressure legible,
degree secondary"; sub-cell gradient seam ▏ blended toward left neighbor
(field reads continuous); centering via shutil.get_terminal_size; attract-mode
gaussian sweep after 20s idle; 8-phase mate cinematic; width-aware ticker.

## v5 — Kimi code critique triaged by Opus (11 applied / 2 rejected with evidence)
Fixed: en passant victim square, castling rook flight (fly = list), exp-decay
heartbeat over 0.10 floor, per-ring shockwave clocks, background trails hued by
mover, mover-hue last-move highlight, winner-hue star, global ±2.2% luminance
wave, /14 wavelength, mtime-cached reads. Rejected: banker's rounding (proved
no-op), "asymmetric contested" (branch only reachable at w==b).
User-reported fixes: pieces centered by MOVING THE PEDESTAL to cols 1-3 (a 1-col
glyph can't center in an even cell; move the frame, not the content); header
became pedestal CHIPS speaking board language, side-to-move = bright chip.

## v6 / v6.1 / v6.2 — Kimi gap analysis + arcade features
Fixes: grayscale covers chrome; wash ordering; draws get quiet treatment (0.45
peak, no flash); persistent ★ on mated king; sweep range widened; rook trails;
st_mtime_ns ctl; min-size degradation tiers.
Features: MATERIAL SPARKLINE (v6.2 final form: solid ▁▂▃▄▅▆▇█ bars — braille dots
have NO SHARED BASELINE and read as multiple dashed lines; bars bottom-anchored,
zero-spanning scale, color flip = zero crossing, 'material' label, ±N readout;
bucket reducer keeps value furthest from mean so blunder spikes survive
compression), pane-edge STATE BEACON (matte frame pulses: red heartbeat=check,
winner hue=over), terminal BELL once per check event.

## §7 v7 — the "warm stains" fix (SHIPPED)
Opus arbitration, measurement-driven (15% of influence squares were isolated
singletons = the stain population): ACCEPTED continuity as a SOFT gradient
(0 same-allegiance orthogonal neighbors → 22% alpha, 1 → 60%, 2 → 85%, 3+ → 100%
— spatial low-pass, no flicker), REJECTED luminance-only influence (luminance
already carries checkerboard + pedestals; would relocate the collision), INVERTED
the warm-ownership fix: hue = field, luminance = events — last-move highlight is
a neutral near-white spotlight #E8EEFA (0.15 from / 0.34 to), warm used by exactly
one thing (Black's field). Accents de-escalated to slate; rhythm fixed; 6-tier
graceful degradation from 21 rows up.

### Original Kimi prescriptions (for reference)
Kimi viewed an actual screenshot: isolated ember influence squares with no spatial
continuity "read as dirt, not data"; warm hue does 3 jobs (influence, sparkline,
highlight) so none reads; 5-6 square fills = "state leaking into rendering."
Prescriptions: (1) influence → pure luminance (×1.12/×0.88, no hue), render only
with ≥1 influenced orthogonal neighbor; last-move highlight gets EXCLUSIVE warm
#E8C47A @0.45; (2) cap fills at 4: light #3A4356, dark #262D3D, pedestal = +10%
luminance of same square; (3) sparkline/footer/thinking → slate #8A93A6/#5A6272;
spacing rhythm fixes. Opus arbitrating (may keep hue + add continuity rule).

## §8 tui_dots.py — the dot-native board (SHIPPED, now the primary renderer)

### §8.1 Kimi's brief and the unlock
- Full-dots FAILS as a naive port: braille cells share one fg colour, so piece
  dots and field dots cannot co-occupy a cell; 4-dot sprites can't tell N from B.
  Opus hit this empirically first — it "solved" the collision by clearing whole
  squares of dither, which is reinventing pedestals as clearings.
- **THE UNLOCK: a braille cell IS a 2x4 ordered-dither cell.** Index the Bayer
  matrix by the dot's own position (`x%2`, `y%4`) and the halftone lands on exact
  dot positions with zero spatial noise. Verified numerically: density level N
  lights exactly N dots, for every N in 0..8, in every cell.
  The first attempt (4x4 Bayer over a 6x8 square) read as "scattered specks"
  purely because it was misaligned to the dot grid — **a dither misaligned to its
  output grid is a sprinkle.** This one insight is most of the renderer.
- CONTESTED = spatial checkerboard of ICE/EMBER cells; the eye mixes them
  optically at a glance. This RETIRED the third hue rather than adding one.
- Adopted then superseded: Kimi's time-separated hybrid (glyph pieces in play,
  dissolve in attract). Correct given its premises, but the user's explicit
  direction was dots pieces — see §8.2.

### §8.2 The hollow/filled experiment and its reversal
User: "the pieces could be different colors and negative spaces." Four
screenshot iterations, each driven by a visible failure:
1. Negative space, first cut → White's back rank merged into one void (adjacent
   holes + dilated moats erased all field between them). **A hole needs field
   around it to have a shape.**
2. Raised field density → still unreadable. **Absence only registers against a
   BRIGHT field**, and ours was dim.
3. Bright rim around the void → isolated pieces snapped into focus, but eight
   adjacent rims merged into a glaring band across rank 1.
4. Outline pulled INSIDE the silhouette → White hollow, Black filled. This is
   the actual chess convention (♔ hollow, ♚ filled), arrived at independently
   from dot-language constraints.
Then the user rejected it: *"why did opus replace the old braille drawn pieces?
those were perfect!! we just needed better colors and filled out schemes."*
- **Root cause of the contrast complaint, measured:** White's outline carried only
  71-86% of Black's dot count AND spread it round a ring instead of massing it.
  **Hollow-vs-filled is inherently asymmetric in visual weight** — no hue change
  could have fixed it. Restored the original 6x8 masters, both sides solid,
  parity 83-95%.
- **The moat, not the colour, is what guarantees contrast.** Every sprite clears
  a 1-dot keep-out ring, so a piece always sits on dark ground however dense the
  local field is. Clamped to the square so a full-height sprite can't erase its
  neighbours' field.
- LESSON: the user's aesthetic instinct ("negative space") and the user's
  legibility judgement can point opposite ways. Ship the instinct, measure the
  legibility, and let the measurement decide the mechanism.
- WHERE IT LANDED: both sides solid, told apart by colour alone (ember vs bright
  white) with the moat guaranteeing contrast. The 6x8 masters were the restoration
  target, not the end state — they were later redrawn at 10x12 (§8.4).

### §8.3 The total-field material system
No board drawn on a background — the dither runs edge to edge and **the board is
a DENSITY structure inside it**: ambient 1 dot/cell outside, light square 4,
dark square 2. The checkerboard is a density difference, not a colour one, and
the 2-dot gap is preserved at every influence level, so the grid can never
dissolve into a blob however hot the pressure gets (this replaced a 1-dot gutter
hack). Influence adds density FIRST and tints SECOND, saturation capped at 0.75
and scaled by pressure, so a hot region reads as deviation from a cool ambient
rather than as wallpaper. The v7 neighbour-support stain filter carried over.

### §8.4 Resolution-adaptive geometry + the 10x12 redraw
`fit_geometry()` picks the largest square the pane can hold and rebuilds
everything; sprites resample to match. The board scales as one object instead of
gaining margin. 12x12 dots/square in the big pane (2.25x the original), 6x8 in a
cramped one, verified at six pane sizes.
- First pass deliberately RESAMPLED the 6x8 masters rather than redrawing — the
  user had just called those shapes perfect, and redrawing risked that approval.
  When the user then asked for detail explicitly, the risk was retired and the
  set was redrawn at 10x12: rook crenellation teeth (two rows of three), bishop
  mitre cleft, knight muzzle + eye gap + neck curve (the only asymmetric
  silhouette on the board), queen five-point crown vs king single cross.
- Two master sets selected by sprite-box size, so a small pane degrades to the
  6x8 art instead of to mush.

### §8.5 Layout promotion — the board becomes artwork
User retired the classic board and promoted the dots board. Dots board enlarged
in `w5:pM`; `panel_tui.py` born with two panels (`moves`, `info`) so the board
could SHED its header/footer data and be purely the position, the coordinates
and whose turn it is.
- **`results.txt` contract:** one finished game per line, WHITE PLAYER FIRST
  (`CODEX 1-0 KIMI`). Seats swap between games, so a bare `1-0` genuinely cannot
  say who won — the tally is per NAME. The panel shows the win count beside each
  agent rather than as a single `2 - 0` string, because one pair of numbers
  silently re-acquires the seat/agent ambiguity that the format change removed.
- MOVES panel lists newest-first so the live move never scrolls away.

### §8.6 The calm-field pass — and the find of the day
User: *"now we have these braille dots... we could reduce some of the breathing
patterns... I still like the animation effects when pieces move and during
checkmate."* Principle: the dot material carries the richness that motion used
to have to provide.
- Inventory first: the board had **exactly ONE ambient animator** (the density
  wave). Everything else — travel, capture bursts, check blink + ring, mate
  topple, attract dissolve — is event choreography. The panels had two ambient
  shimmers. So "calm the ambient, keep the events" was one dial plus two deletes.
- **THE FIND: the dial was broken.** Slowing the wave (6s → 30s) and cutting
  amplitude (0.7 → 0.5) produced a board where NOTHING moved. Density was being
  rounded to an integer before the Bayer threshold, so a gentle wave never
  crossed a rounding boundary — the animation had become dead code. The same
  rounding explains why the OLD motion felt so busy: squares that did cross
  jumped a whole dot-level at once, so it read as twitch, not drift.
  **Fix: keep density CONTINUOUS** (float threshold against Bayer). The drift now
  adds or drops one dot at a time in a coherent band. Measured: 26/64 squares
  move by exactly 1 dot per 30s cycle.
- **The calm pocket** (beyond the brief): a piece sitting perfectly still against
  a neighbour pulsing at full amplitude STILL reads as flickering, because
  contrast is relative. Occupied squares = zero wave + minimum density + capped
  residual; the ring around them = 0.35 amplitude. Measured swing: occupied 0,
  neighbours 0-1, open ground 1, attract mode restores full.

### §8.7 Operational lessons (cost real time / a live outage)
- **`str.replace` silently no-ops on a missing anchor.** A scripted patch against
  a stale anchor left guard variables undefined; the live board threw `NameError`
  every frame and game 3 lost its display for ~a minute. ALWAYS
  `assert anchor in s` before replacing in a patch script.
- **Static renders don't exercise animation.** Glyph mode shipped a crash
  (`list indices must be integers, not float`) because interpolated `fly`
  coordinates are floats and `Grid.glyph` never cast them — the headless suite
  only rendered static boards. The regression now ANIMATES 13 moves including
  captures and castling, in both modes.
- **Snap-to-live > replay storm.** The relay writes `moves.txt` truncate-then-write;
  a read landing in that window returns empty, and the renderer "caught up" by
  animating all 105 plies one at a time. Now: >3 moves arriving at once = jump
  straight to the live position. `replay` ctl is unaffected (different path).
- **ctl was deaf during a replay** (`replay_all` blocked the loop); commands were
  deferred, not lost. Now the replay aborts when ctl changes so the command lands.
- **ctl writes inside a renderer's startup window are swallowed** — the renderer
  captures `ctl_mtime` at start and only acts on strictly-newer. Sleep a beat
  after launching a pane before writing ctl.
- **A pane running a live renderer got closed by unrelated window churn**, twice.
  If multiple agents restructure one window, renderers need explicit protection.

## §9 Arcade generalization kernel (Kimi blueprint)
pedestal = per-game piece-emphasis mask; influence field = per-game pressure fn;
event choreography = shared kernel with per-game distance metrics + glyph
compositors. Go: territory flood tints, atari heartbeat, ink-bleed placement,
ghost-fade captures, 3x1 cells for 19x19, two-foci territory wash at end.
Othello: flip cascade via per-disc onset clocks (the RINGS mechanism along the
captured line), ◐ half-flip midframe, mobility heat field, corner = full CAPTURE
event. Connect-4: gravity fall with quadratic ease + squash-settle, threat heat
(completing squares at ALPHA[3], double-threats = contested branch), win = line
gaussian (make ring metric a kernel parameter). Chess is the only game needing
all three layers at full strength.

## §10 The tooling wipe — incident post-mortem (2026-08-10, CLI ship gate)

During the `arcade` CLI's verification round, the real /tmp/chess lost game 3's
67-ply moves.txt + final fen.txt — wiped by the CLI's own test run, with every
safety override correctly set.

**Vector.** The reviewer ran `arcade start` with BOTH `ARCADE_ROOT` and
`ARCADE_LIVE` pointed at scratch copies. The CLI redirected all of its own I/O
faithfully — then `run_ref_init` shelled out to `<scratch>/ref.py init
--force`, and ref.py hardcodes `D = Path('/tmp/chess')` at module scope. The
subprocess ignored cwd and env entirely and re-inited production. The CLI even
printed a warning about exactly this ("engine scripts hardcode /tmp/chess and
will not follow this override") — as advisory text, while proceeding anyway.

**Recovery.** The full 67-ply SAN was recovered from the grok director's
session logs (`~/.grok/sessions/…tmp%2Fchess/…` — the director had read the
log every turn), validated by python-chess replay (mate confirmed), restored
to /tmp/chess, and re-archived: match-003 went from a stub to a true archive.

**Fixes (all tested, codex-verified in the original repro shape).**
1. `run_ref_init` never shells out for a non-default live dir — pure-Python
   `native_ref_init` mirrors ref.py's init byte-for-byte instead. Only the
   real /tmp/chess gets the genuine subprocess.
2. Scratch-mode guard: `ARCADE_ROOT` set while the live dir silently defaulted
   → hard refusal, no `--force` override (that combination is only ever a
   mistake).
3. Pre-init snapshot: non-empty moves.txt/fen.txt copied to `<live>/backup/`
   before any init, so even a future wipe is a non-event.

**Update (2026-08-10, root cause closed):** fix #1 above was a workaround for
the underlying bug, not a repair of it — the engine still hardcoded
`/tmp/chess`. The engine has since been refactored so every script resolves
`D = Path(os.environ.get('ARCADE_LIVE', '/tmp/chess'))` at import time, and
`run_ref_init` now always shells into the deployed `ref.py` for any live dir,
passing `ARCADE_LIVE` explicitly in the subprocess environment. The
now-unreachable `native_ref_init` pure-Python mirror was deleted rather than
kept as a fallback — two implementations of the same init logic is its own
drift risk, and the failure mode that motivated it no longer exists. Fixes #2
and #3 stand unchanged; they guard operator mistakes, not engine drift.

**Lessons.**
- A warning that narrates data loss instead of preventing it is a bug report
  written in advance. If the tool knows the override won't hold, refusing is
  the only honest behavior.
- Env-var redirection stops at the subprocess boundary. Any copied script
  with an absolute path baked in is a landmine that goes off in someone
  else's directory.
- Game 3 taught us the file bus needs protection from the players (identity
  signing, replay-from-ply-1). This taught us it needs protection from its
  own tooling. The trust model now covers both directions.
- Append-only logs held elsewhere saved us: the director's turn-loop reads
  doubled as an off-site backup nobody designed. Redundant observers are
  cheap insurance.

## §11 Pairing-state bleed — match-state scaffolding (2026-08-10, CLI ship gate)

Game 6's fresh GEMINI seat opened onto game-5's leftover room: a 170-line
`chat.log` from the CODEX/KIMI pairing, a stale `SERIES 5-0 CODEX` banner,
and `board.txt` (via `ref.py render()`) hardcoding `CODEX (White) vs KIMI
(Black)` regardless of who was actually seated. `arcade start` had only ever
reset the referee's own state (`moves.txt`/`fen.txt`); everything social or
broadcast-facing — chat, banner, logs — carried over unchanged from whichever
pairing played last.

**Fix.** `arcade start` now opens a clean room every match: `chat.log`,
`banner.txt`, `eval.log`, `keeper.log` and `ctl` are snapshotted to
`<live>/backup/` and cleared; ref-owned flag files (`pending.txt`,
`result.txt`, `draw_offer.txt`, `TAMPER.txt`, `roles.txt`) are unlinked.
`results.txt` is the one file that persists — cumulative across every
pairing, append-only, never filtered on disk. The lifecycle contract: every
display of series data (the new `series.txt`, `cmd_status`, `cmd_results`)
reads `results.txt` through a pairing filter (`head_to_head`), never raw,
because the ledger spans every pairing the arcade has ever run and an
unfiltered read is someone else's data by default. `ref.py render()`'s own
`CODEX`/`KIMI` hardcoding is fixed the same way — resolved from
`chat.player_names()`, same as `ref_xq.py` already did. The safety invariant
is the snapshot, not archive: `snapshot_pre_start` runs unconditionally
before any clear, so an operator who forgot `arcade archive` still gets a
recoverable room, just with a warning. See `docs/match-state-spec.md` for
the full design and `docs/cli-brief.md` for the file-lifecycle summary.

## §12 Event-driven turns — the auto-poke evolution (game 6, 2026-08-10)

Games 1–5 ran on host polling: the booth prompted a player, then watched
`pending.txt` until a move appeared. Game 6 tried three designs in one match:

1. **Polling** (start state): works, but the host burns loops and the room
   feels slow — one LLM turn per poll step made KIMI's booth ~3 min/ply.
2. **Brief-level manual pokes** ("players run `herdr agent prompt` after
   submitting"): failed on *confabulation*. GEMINI twice narrated "poked the
   referee" without executing the command — its own retro named it an
   "execution gap … the distinction between stating an intent to poke and
   actually executing the tool can sometimes blur." Lesson, now doctrine:
   **player diligence is not a mechanism.** If the protocol needs an action
   to happen, the tooling performs it.
3. **Product auto-poke** (deployed mid-match): `game.sh submit` itself fires
   `herdr agent prompt <director>` on success. CODEX: "materially improved
   the flow."

The retro exposed the remaining flaw: pokes *queue* at a busy host rather
than interrupting, and post-mate they became spam (empty pending + gameover).
GROK's formulation became the round's theme — **terminal state must be
machine-visible and machine-enforced** — and drove the game-6 fix round
(§13). Also debuted in game 6: the eval-channel split (`eval.log` host-only,
players banned from engines) — GROK: "color-without-cents forced the booth
to actually look at the board. I would not go back."

## §13 Game-6 retro fix round + replay button (2026-08-10, codex build / kimi review)

Six fixes, all field-reported by the seats themselves
(docs/seat-feedback-game6.md, verbatim retros in docs/retro-game6/):

- `finish_native()` in both referees: checkmate/stalemate/any native
  game-over now appends results.txt, writes result.txt + banner.txt and
  announces — exactly like the resign path, idempotent. (GROK had appended
  the game-6 result by hand.)
- Auto-poke gated (no result.txt, non-empty pending) with structured payload
  `STAGED <NAME> <SAN|ICCS> ply=<N>` — the only useful poke shape is
  "something is staged right now."
- Atomic submit receipt `HOST NOTIFIED` / `HOST NOT NOTIFIED (<reason>)`
  (CODEX's one change) and `submit <move> --say '<text>'` (GEMINI's one
  change) — say fires only after a successful stage.
- FACILITATOR Handoff section: checklist one-liner + the hard rule to poll
  pending.txt even when a herdr prompt stalls (agy staged moves while its
  prompts returned failures).

Review (kimi, SHIP-WITH-NITS): traced the shell quoting (tab-split safe,
single-argv poke), all five python-chess game-over reasons route to correct
result strings, xiangqi's no-stalemate-draw rule honored. Nits: ICCS wording
(fixed), shell wrappers pytest-uncovered (backlog).

Same round shipped the **board-pane replay button**: `[ ▶ replay ]` on the
status line of both TUIs, SGR mouse tracking + `r`/`q` keys, isatty-gated at
import so headless output is byte-identical to before; pty-verified including
a synthetic click at the computed button bounds. Deployed live; replay is not
click-interruptible mid-animation (matches the ctl model, documented edge).

## §14 The HOST rename (2026-08-11)

The agent seat that runs a match was called the DIRECTOR for the first five
games. It is a broadcast booth, not a film set: it seats the players, drives
the turn loop, narrates, and hands out the postgame mic. So it became the
HOST everywhere — `FACILITATOR*.md` briefings, the chat identity, the keeper
scripts' prompts, the CLI runbook text, `director.txt` → `host.txt`.

Two things deliberately did NOT move. **REFEREE** stays the scripts' own
identity: `ref.py`/`ref_xq.py`/`ref_cw.py` post mechanical rulings under it,
and keeping rulebook and booth as separate speakers is the whole point of the
split — the rename only made the booth's name honest. And every **old
spelling still parses**: `--director` is a permanent alias for `--host`,
`arcade prompt director` aliases `prompt host`, `DIRECTOR_AGENT` is read when
`HOST_AGENT` is unset, a stale `director.txt` from an older deploy is read
when `host.txt` is absent, and `RESERVED_NAMES` keeps both. An archive
written before the rename must keep replaying without edits, which is the
same rule the move log lives under.

Reviewed cross-model (verdict SHIP). The one real find was made by
inspection, not by tests: a `$DIRECTOR_AGENT` reference in
`director_keeper.sh` that the rename would have left dangling. The script
kept its filename — only its prompts, log text and env var changed.

## Unbuilt ideas backlog (Kimi, ranked by novelty)
- Threat-anticipation arrow (opponent's expected reply, 0.8s fade) — narrative
- Cadence-coupled breathing (wave period from trailing move interval, 2-10s)
- Captured-piece trays as flanking columns
- Phase-of-game whitepoint (dawn-cool opening → dusk-warm endgame)
- True attract demo: replay Légal's mate at 3x after 60s idle
- Queen-capture screen kick (1-col LP jitter, 2 frames)

# 11. The xiangqi seal (2026-08-11) — how the piece design converged

Eight user-driven iterations: 6x3 wood block (too big) → wood pill w/ nerd caps
(font-dependent) → bare braille ring (melts into field) → cleared block (negative
space blends) → solid bone disc → MOAT-CARVED DOT SEAL (final; user approved on
sight: "we shape the round thing with voids"). Full spec: docs/xiangqi-studio/SPEC.md v2.

Key insights, in the order they were earned:
- **Two-block-system** (user): treat board and piece as separate block economies;
  a piece CLAIMS a footprint (negative space) then composes fill.
- **The moat**: claim more territory than you fill. Punch dots to R+0.8, draw to R.
  "Dangling dots" complaints were finally traced NOT to stray dots but to a
  half-dot mis-centring in BOTH axes (13x12 ellipse) — opus gate measured it.
- **Centring law**: CJK centres vertically only in odd row counts; centre =
  (px-0.5, py+1.5), the glyph midline. py is the TOP dot of the face row.
- **k = 1.0**: braille 2x4 packing already cancels the 1:2 cell aspect; the gate
  pre-empted the classic k~2.0 double-count before it shipped.
- **Printed text has no size floor** — nameability became font-dependent, not
  geometry-dependent, which is why 7-nameable passes at every tier (font probe
  is therefore load-bearing, not polish).
- **Dither/edge-thinning and rims: tested, measured, rejected** — thinning
  reintroduces the exact orphan fuzz the user asked to remove; face contrast
  (6.38/16.52 on the window) makes a rim unnecessary.
- Palette locked from kimi K3 + gate corroboration: BONE (226,214,186),
  RED (255,100,60), BLACK (246,240,226), WINDOW_BG (14,18,24). Real legibility
  risk is the red 亻 cluster 仕/俥/傌 (same side — colour can't help), not the
  cross-side pairs everyone suspects.

Side quest, recorded: U+1FA60 unicode xiangqi glyphs exist, render after
installing Noto Sans Symbols 2 (user: "meh" — kept as optional probe-gated
floor tier idea only). Ghostty font-codepoint-map routes the 14 faces +
楚河漢界 to LXGW WenKai Mono on the user's machine (production must not depend
on it).

Process shape that worked: codex built, kimi squinted, the internal Opus gate
measured — three independent methods kept agreeing, which is how we knew the
design was converged rather than fashionable. The gate's verify_prod.py keeps a
deliberate regression tripwire: it scores symmetry about the correct centre AND
the legacy buggy one; if legacy ever wins, E1/E2 were reverted.

# 12. Core War — the third table (2026-08-13)

Chosen by ideation session (first-principles over the "next famous abstract"
frame, then de Bono provocations — the winning one: *po: a move is not a
square, it's a program*). Core War (1984) is the original programming game:
two assembly warriors fight in an 8000-cell circular memory core. Unsolved,
AI-native (the players write code), and the board IS a density field — the
dot material's most literal mapping yet. Built entirely by a kimi agent swarm
in five waves, adversarial review between every build and ship.

## The engine — own MARS, differential-tested against real pMARS

`corewar.py` (stdlib, ~1300 lines): ICWS'94 minus P-space (LDP/STP rejected
cleanly; documented fast-follow). The house alternative — vendoring pMARS —
was rejected because referee AND renderer both need to step the simulation.
Validation method, new for this arcade: the reviewer **built pMARS 0.9.2 from
source as a differential oracle**. 576 fixed-position battles → 0 winner
mismatches; 1555-warrior assembly differential → only four deliberate
divergences, each following the draft text where pMARS deviates (NOP .B
default, single-operand `#0` fill, lenient operandless forms,
partial-stringization hard error) — documented in the module docstring.
Ambiguity resolutions follow the annotated '94 draft over EMI94 sample code
(the ARITH .AB/.BA swap, jump RPA queueing) — both cruxes probed explicitly.

Parser as attack surface: warriors are untrusted input the referee parses.
Review caught RecursionError vectors (deep parens/unary/EQU chains), an
exponential EQU expansion (8^N tokens — a 15-line warrior hung the parser for
a projected hour), and nested FOR/ROF stringization wrongly rejected. Fixed
with depth/token caps; pMARS-parity stringization verified against the oracle.

## The trust model — deterministic replay replaces the move log

A battle is a pure function of (warrior A, warrior B, seed, offsets). Seed =
sha256 of both normalized sources; round n plays at seed+n with the engine's
own RNG drawing offsets. `moves.txt` holds the transcript (`LOAD` / `ROUND` /
`OUT`); `verify` re-simulates every round **and proves provenance** — recorded
seeds/offsets must derive from the locked warriors. The reviewer's plant
(honest OUT lines under attacker-chosen seeds) passed an earlier verify; the
provenance check is what closed it. That is the chess §10 lesson applied
forward: the transcript is verifiable against the warriors, not just against
itself. `results.txt` contract unchanged: 3 rounds always, points (win 1,
tie ½), `<RED> <1-0|0-1|1/2-1/2> <BLUE>`.

## The two-phase match — no mid-battle illegal moves exist

Workshop phase: timed (45 min default), players write warriors, stage signed
via `pending.txt` + a `stage_inbox` hash receipt (TOCTOU-safe: the referee
validates the hashed bytes it installs), spar against the built-in imp/dwarf.
Battle phase: host `lock` (freeze + hashes) → `battle` (instant best-of-3) →
the renderer broadcasts the replay. The adjudication surface is staging
(malformed = loud, free, private — no opcode detail to the room), tampering
(TAMPER halt, strict resolve that re-simulates before clearing), and the
deadline (never-stage = 0-1 forfeit). Bus-layer review caught: lock
half-applying on an invalid hold (validate BEFORE the transcript write),
prefix-name resigns (`red-spectator` inherited the seat — exact seats.txt
match now required at the referee), and a name→path traversal into
`stage_inbox` (charset gate at both layers).

## The renderer — the core IS the field

Furniture gate passed on a mockup frame, user-approved on sight
(design/corewar-mockups/): 1 memory cell = 1 braille cell, 80×100 grid;
untouched core = ambient grain on the SQD plate; ownership = EMBER/ICE haze
with exp-decay heat (TAU=300, SAT_CAP 0.75); DAT bombs = literal holes with
pit floors, fresh craters glowing from below; processes = 2-cell comets,
near-white heads, moats that clear cold ground only (the §11 dangling-dots
lesson — an early moat shredded the hot dwarf body into orphan dots).
Elimination is the flagship beat: the loser's whole haze cools to ambient
while the winner's processes keep running. Grand tier = the full core (needs
104 cols); cozy = an **activity-following camera** — a thumbnail core was
judged unreadable, so the small pane is a viewport eased toward the heat
centroid, not a shrunken board. That is the first tier in the arcade that
changes shape rather than scale. The renderer re-simulates rounds from the
transcript (never reads battle.json — cache, not truth); the referee decides
outcomes; tampered offsets make it NOTE-and-skip, never crash (three
degraded-bus crashes found in review: invalid offsets, unreadable warriors
mid-snap → 100% CPU spin, non-UTF-8 bus files).

## Process shape (what this session proved)

Five swarm waves: engine ∥ CLI ∥ facilitator-doc → adversarial reviews →
bus layer → renderer (mockup → gate → build) → integration. Every build got
a fresh-eyes review; all three NO-SHIP verdicts were right, and every fix was
verified against the reviewer's own probes before ship. The orchestrator ran
ops and gates only. 549-test battery green from the repo root; scratch dry
run (start → stage ×2 → check → lock → battle → verify → archive) clean:
IMP 1/2-1/2 DWARF, three tie rounds, transcript verified.

### Match-001 footnote — the archive must carry the warriors

First live match (KIMI 0-1 CODEX: TWIN EMBER's twin mod-1 stones vs BLUE
FUGUE's interleaved silk waves; T, T, then red over-run at cycle 15318 of
round 3 — 3 procs vs 100 on the final frame). The full stack worked live:
workshop deadline, signed staging, auto-poke, lock, seeded battle, booth
narration, verify (OK, 3 rounds), archive. One gap found by doing: the CLI
archived only flat files — `warriors/A.red` + `B.red` were left behind, and a
transcript whose LOAD lines carry only sha256 is unverifiable without them.
Fixed: `GAME_ARCHIVE_EXTRA["corewar"]` now archives both warriors +
battle.json; match-001's archive was hand-completed in place. A transcript is
only evidence when everything it hashes is kept.

### Match-002 footnote — the room pane was watching the wrong room

User-reported during match-002's workshop: the chat pane showed "nobody has
said anything yet" over a live chat.log. Root cause: `chat_tui.py` is the one
SHARED pane across games, and it resolved `D = ARCADE_LIVE or '/tmp/chess'` —
launched in a pane without the env, every table's room tailed **/tmp/chess**.
Likely affected xiangqi's room for its whole run; nobody noticed because
nobody was reading it ("no one was using it" — the user's bug report, and the
reason it survived two games). Fix: default to the script's own parent —
deployed copies always sit in their live dir, so every table now tails its own
log; ARCADE_LIVE still wins when set. The say-hint also picks the deployed
wrapper (`game_cw.sh` over `game.sh`) instead of hardcoding chess. Guard:
test_chat_tui.py (D resolution both ways, hint selection). Same class as the
§10 landmine: any shared script with one game's path baked in is a bug that
goes off in someone else's room.

### Match-002 footnote 2 — the exact-fill scroll (live wall report)

User-reported on the match-002 wall: board flickering, header (player names)
cut off, replay button dead. Root cause was one missing character class:
`render()`'s `line()` helper appends `'\n'` to EVERY row including the last,
so whenever the frame exactly filled the pane (frame rows == pane rows — true
at both wall geometries the pane had), the final newline scrolled the pane one
row per frame. Every frame scrolled: flicker; the header walked off the top:
missing names; and `_btn_bounds` (recorded in frame coordinates) no longer
matched the scrolled-visible button: dead clicks. chat_tui.py's own header
comment documented exactly this ("emitting one would scroll the pane… every
frame"); the clone missed it. Fix: strip the trailing newline from the last
content row. Also: replay during workshop (no rounds) was a silent no-op —
now shows 'nothing to replay yet'. Tests: exact-fill pane newline count,
replay-before-lock feedback, plus the production-read isolation fix for the
two render tests (they read the real /tmp/corewar names/banner once a live
room existed — import-time-bound bus paths are now monkeypatched to scratch).

### The atlas — the board stops moving (2026-08-14)

The camera was the wrong answer to "the whole core doesn't fit". Watching
match-002 on the wall, the complaint was not resolution, it was that nothing
stays put: the viewport slides, the eye never learns the map, and the ring-map
below it existed only to say where the camera had gone. Gate artifact:
`design/corewar-mockups/atlas/` (mockup + notes + animation spec + brief),
approved on three re-simulated frames of match-002 round 1.

The move is a magnification change, not an averaging one, which is why it does
not break the locked 1-cell-1-braille rule so much as retire the reason for
it. A braille char is 2x4 dots, so one char is exactly 2 core columns x 4 core
rows and the whole 8000-cell core is exactly 50x20 chars — dot (dx, dy) of
char (cx, cy) IS memory cell (4*cy+dy)*100 + 2*cx+dx, positional, never
resampled. The old objection (averaging EMBER and ICE fabricates a muddy third
hue exactly at contested borders) is answered by refusing to ask one channel
two questions: **dots answer WHO** (lit iff owned; the char's fg is the
MAJORITY owner's own ramp colour, never a blend), **the plate answers WHAT IS
HAPPENING** (crater pits, fresh-damage glow, and a contested lift toward
SLATE — a neutral grey off both faction ramps, so nothing can read as a mix).

DELETED with the camera: the grand tier, camera easing and its deadband, the
ring-map-as-locator, the 2-cell comet grammar and its keep-out moats,
MAX_COMETS, the size ladder (`size` survives as an inert ctl verb; an old
size.txt is never read). The ladder is now atlas → strip → refuse; the strip
keeps the battle visible by promoting the ring-map's material to a whole-core
heat bar with no window brackets, because there is no camera left to locate.

Two lessons generalised, both versions of the same mistake:

- **Every inherited per-cell intensity rule has to be re-derived as a
  per-footprint rule at atlas grain, or it over-fires by up to 8x.** The gate
  caught it in the crater glow (one bomb was painting a bright card because
  the freshest cell in a block lit all 8 cells' worth of plate); the fix is
  `0.55·Σh²/8` over the block's pits. The contest measure had the same shape
  of bug — a ratio scores a 1-vs-1 block as hard-fought as a 4-vs-4 one — and
  the same shape of fix, the disputed footprint, heat-gated so the map shows
  the front instead of every old overlap.
- **The same over-fire happens in the time axis.** Implementation found it:
  the inherited FX_CAP of 120 was written for a tier that showed one bomb at
  a time, but the renderer steps tens of cycles per frame, so a bombing run
  spawns dozens of effects per frame and 120 live effects light an eighth of
  the core. Capped at 24 with sub-quarter-second lives, the same run reads as
  a drumbeat.

Near-white now means "a process is here" and nothing else, ever — the marker
is promoted from a 2-cell comet to a FULL near-white char, uncapped, merging
by block (an imp train draws a white worm, a stone engine a steady block).
That ruling is what forced the contested sizzle onto SLATE instead of the
animation spec's white, and it forced the bomb drumbeat into the plate
channel too: an FX that lit a dot would fabricate occupancy, which is also
why the comet moat could not survive at this grain and why rings and debris
particles moved to the plate.

Two other decisions worth keeping: cold owned ground decays further toward
ambient than the mockup shipped (the late frame was too loud — a fully-owned
core must let its live fronts dominate), and a DRAWN match now cools both
armies to embers together in one slow shared fade instead of the old quiet-dim
tie treatment. A draw is "the floor held", not a failure state.

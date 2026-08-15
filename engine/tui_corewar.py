"""Core War arcade — THE ATLAS: the whole core, stationary, at pane size.

A dot-native renderer for the 8000-cell circular memory core, in the arcade's
braille dot-field material (tui_dots.py §8 lineage, same family as chess and
xiangqi). The core is laid out row-major as 100 columns x 80 rows (8000 =
80x100 exactly; address = row*100 + col).

THE BOARD IS THE ATLAS (gated 2026-08-14 —
arcade/design/corewar-mockups/atlas/ is the design record: notes.md for the
gate rounds, atlas-mockup.py for the executable encoding spec,
animation-spec.md for the seven approved motions, implementation-brief.md
for the rulings this file implements). There is exactly one field tier. The
activity-following camera, the 104x84 grand tier, the ring-map locator, the
2-cell comet grammar and its keep-out moats all died at that gate; git
history is their archive.

GEOMETRY. A braille char is 2x4 dots, so one char covers 2 core cols x 4
core rows = 8 memory cells, and the whole core is exactly 50 x 20 chars.
Dot (dx, dy) of char (cx, cy) IS memory cell (4*cy+dy)*100 + 2*cx+dx — the
mapping is positional and exact, never resampled or averaged. This relaxes
the locked "1 memory cell = 1 braille cell" rule for this tier only: the
atlas is a magnification change, not an averaging one, which is the whole
argument the gate turned on. The field is 50x20 for ever and can never grow
into surplus columns, so the frame is: header / field / faction bars /
[round ledger] / status — 23 rows, or 24 where the pane affords the ledger
its own line. The block is centred and the chrome rows start further left —
a narrow plate over a wide caption, the broadcast lower third. Rows are
BUDGETED, never appended and hoped for: a frame taller than its pane scrolls
the whole board every frame, so the row list is built, capped to the pane,
and only then emitted.

ENCODING — two channels that never mix (atlas/notes.md "Encoding"):

  dots (fg)   WHO. A dot is lit iff its memory cell is OWNED, and the char's
              single fg is the MAJORITY owner of its lit dots, on that
              owner's deep ramp (HUES_DEEP → HUES with heat). No blend
              between EMBER and ICE is ever computed — not at borders, not
              anywhere. Density is therefore occupancy, and each warrior's
              footprint draws its own texture (a silk stride lays diagonal
              cascades; an imp carpet runs as a horizontal band). A bomb is
              a write, so bombed ground still shows its bomber's colour:
              territory never disappears (`dots = clearing` was rendered
              side by side at the gate and rejected — it gutted the board).
  plate (bg)  WHAT IS HAPPENING. Craters darken toward WINDOW_BG by their
              footprint (npit/8); fresh damage glows in its bomber's hue by
              the CRATERED footprint (0.55·Σh²/8 — the per-cell rule
              over-fired 8x at this grain); a genuinely contested block
              lifts toward SLATE, a neutral grey off both faction ramps so
              it can never read as a mixed hue. Untouched core is the calm
              dark plate with the slow density wave on its bg — ambient
              stipple was rejected (a faint dot must never mean occupancy).

  heat        h = exp(-age/TAU), TAU 300 cycles, taken as the MAX over the
              block's cells for the majority faction (mean washes out the
              one fresh event you want to see). Heat can reach zero; faction
              identity cannot. Owned ground never decays past the COLD FLOOR
              — a dim but unmistakable brick / steel — because the field is
              the evidence for the bars: when the caption says "99% held",
              the board must READ as that army's field even stone cold. Cold
              and hot are separated by luminance rather than hue (a third of
              a hot cell's brightness), which keeps the live fronts dominant
              in a saturated late frame without bleaching the dead ground.
  contest     gated twice: both factions must genuinely hold ground here
              (disputed FOOTPRINT min(1, 2·minority/8) — the ratio scored a
              near-empty 1-vs-1 block as hard-fought as a 4-vs-4 one) AND
              someone must have been here recently (× block max heat, which
              turns a map of every old overlap into a picture of the front).
  process     one PC is one memory cell = one dot among 8000, i.e. invisible.
              The marker is promoted to the whole char: FULL 8 dots at
              near-white, the board's brightest object and its one admitted
              lie (8 cells claimed for 1 — cheap, because a PC almost always
              sits inside its own warrior's hot code). Co-located PCs merge
              into one marker, so an imp train is a white worm and a stone
              engine a steady block; there is NO cap on markers — a SPL
              flood lighting a region white is a legitimate read. Near-white
              means "a process is here" and nothing else, ever: that ruling
              is why contested cells sizzle in SLATE, not white.

ANIMATION — the seven approved motions (atlas/animation-spec.md):

  1 load-in   round start: warrior A's body scanline-writes itself in at its
              offset, one beat, then warrior B — random placement taught
              wordlessly, ~1.5s.
  2 death wave the kill lands with a fighting-game hitstop (HITSTOP_S freeze
              on a winner-hue flash + a plate shake), then the loser's
              territory cools in a wrap-aware front sweeping out from the
              kill address across the WHOLE core. The atlas's flagship.
  3 wrap spark a process or bombing run crossing 7999→0 sparks the plate at
              the exit and entry corners: memory is a ring.
  4 tempo     process markers pulse on a phase derived from (pc address, t),
              so a moving PC shimmers as it crawls and a stationary engine
              thumps — strategy readable as rhythm, for free.
  5 drumbeat  every bomb is a short bright plate flash in the bomber's hue.
              Core work, not decoration: after the per-footprint crater fix a
              single fresh crater lifts its plate by ~7%, so this is the ONLY
              place an individual bomb is visible. It lives in the plate
              channel because white belongs to processes (the §6 amendment,
              applied to §5 by the same rule), and it carries no ring: the
              spec's micro-ring was written for one bomb, and the renderer
              steps tens of cycles per frame.
  6 sizzle    contested plates jitter on a sin-hash phase in (cx, cy, t) —
              the front reads as unstable ground, not a UI card.
  7 pacing    momentum-aware playback: the cycles-per-frame rate re-derives
              every frame from cycles remaining ÷ frames remaining, then
              modulates by a deterministic momentum metric (ownership
              claims + process-queue swing). Quiet stretches run fast and
              bank slack; a moving front crawls. Self-correcting, so an
              80000-cycle tie always lands inside the broadcast budget.

HOOKS. `FRAME_HOOK(grid, scene, t)` fires once per drawn frame and
`EVENT_HOOK(kind, addr, warrior, t, extra)` once per moment worth hearing —
bombs, splits, deaths, wraps, round cuts, the load-in, the elimination
hitstop, verdicts, the end treatment. Both are None in normal use and cost
nothing. They exist so the offline recorder (`record_cw.py`) can reconstruct
the broadcast timeline from the module that owns the pacing, rather than
copying the formulas somewhere they can drift out of step.

Every time-varying term in the render path is a deterministic function of
(addr/cx/cy, cycle, t) — sin-hash noise, never RNG — so headless renders are
byte-stable for identical (scene, t); `random` runs only in the per-frame
shake roll, whose branch is live only during an elimination kick.

FILE BUS (same contract as chess/xiangqi, different live dir).
ARCADE_LIVE defaults to /tmp/corewar. battle.json is deliberately NOT read:
it is the referee's cache, never a truth — the transcript plus the locked
warriors are the truth, and the renderer re-derives everything from them.

    moves.txt        transcript: LOAD A/B <sha256>, then per round
                     `ROUND n seed=<s> off=<a>,<b>` + `ROUND n OUT <out> cycles=<c>`
    warriors/A.red, warriors/B.red   the locked sources (re-simulation input)
    names.txt        `<red> <blue>` — red is warrior A, blue is warrior B
    banner.txt       the room's PRE-MATCH caption — shown in the workshop
                     and locked phases only, where it is the content. Once a
                     battle starts the status row says what is happening in
                     this game's own words, and the referee's own banner
                     write is a bus record in chess's scoreline; repeating it
                     under the board taught the audience nothing.
    result.txt       unchanged semantics
    ctl              replay [n] | reset | banner <text> | names <r> <b>
                     | music [on|off] | size <anything> (accepted, inert —
                     there is one tier)
    size.txt         legacy; never read. An old file is harmless, not a crash.

TIMELINE. The referee runs the whole battle before the transcript exists, so
this renderer is always animating a deterministic replay at broadcast pace —
there is no live tail to chase. Pre-lock: calm idle field + banner. When
ROUND lines exist, each round animates in order; kills slow to 1 cycle/frame
for the last SLOW_TAIL cycles so the death breathes. Between rounds a
verdict beat; after the last round the end treatment — the winner's hue
washes the field, or, on a DRAWN match, both armies' territory cools to
embers together in one slow shared fade ("the floor held", not a failure
state). >3 rounds arriving at once snaps straight to the latest state
instead of animating all (§8.7); a truncated/rewritten transcript triggers a
cold rebuild from whatever moves.txt now holds — cold start never caches.

ctl writes inside the renderer's startup window are swallowed: ctl_mtime is
captured at startup and only strictly-newer writes act (§8.7) — sleep a beat
after launching the pane before writing ctl.

GEOMETRY LADDER (fit_geometry):
  atlas   the whole core, always — needs the atlas's own geometry, a 55x23
          pane (4-col address gutter + 1 + the 50-wide field; header + field
          + bars + status). The default and only field tier.
  strip   below that: header + a one-row whole-core HEAT BAR (the ring-map
          material, promoted: one char per bucket of the linear core,
          majority hue at mean-heat brightness, no window brackets because
          there is no camera to locate) + status. Even at the floor the
          battle stays visible as a living bar.
  refuse  below 20x4.

When stdin is a tty, a `[ ▶ replay ]` button lives on the status row (SGR
mouse, or `r` to replay / `q` to quit), isatty-gated at import: headless
output is byte-identical to a no-input run. ARCADE_REDUCED_MOTION=1
suppresses the wave, the contested jitter, the marker pulse, the load-in
scanline, plate FX, the hitstop + shake and beat dwells, and cuts the draw
fade straight to its cooled state (battle playback pacing is content, not
motion, and is unchanged).

MUSIC — the replay may be SCORED (opt-in, silent by default; ARCADE_MUSIC=1
or ctl `music on`). A terminal that makes noise unasked is rude, so nothing
here runs unless someone turned it on.

The score needs the whole match before its first bar — the arranger places
sounds on a grid the battle only selects from (score_cw.py's law), which is
lookahead by construction. A replay is an archived match, so the lookahead is
free: `score_replay` runs record_cw.extract on THIS live dir to get the
broadcast timeline, spends it through score_cw into a WAV, and only then does
the load-in begin. Playback is one `afplay` started at the moment the
animation clock starts; from there the two run on their own. That is the
whole sync model, and it holds because the recorder's timeline came from this
module's own pacing loop on a virtual clock while the live loop paces against
a drift-correcting deadline — the same frames, the same beats, one measured
in cycles of CPU and one in seconds of wall. Be honest about what that buys:
frame-exact hitstop sync is guaranteed only in the mp4. Here a pane that
falls behind its frame budget lets the track run ahead of the picture, and
nothing corrects it. Per-frame audio sync and streaming synthesis were both
rejected — the first re-litigates the grid law, the second cannot see ahead.

The scoring pass is why `DRAW_FRAMES` exists. Extraction re-runs the real
animation, and at atlas grain the DRAWING is 95% of it (21.8s of 22.8s on
match-001); the events and metrics a score is built from cost a second. So
the scoring pass turns the drawing off and the pacing loop runs otherwise
untouched — no formula is copied, and the timeline is byte-identical to the
recorder's, because pacing is a virtual clock and never a measured one.
Measured on match-001 (176s of music): ~9.5s end to end, ~1s of it extraction
and the rest numpy. That is a real wait, not a blink, so it is held in a
session cache keyed on the transcript — only the first replay of a match pays
it — and the status row says `scoring…` while it runs.

Music is orthogonal to REDUCED_MOTION (a track is not a motion) and to the
render path (the recorder still owns byte-stable frames; audio touches
neither). Every failure here degrades to silence and one line on stderr: no
numpy, no afplay, an unreadable archive — the replay plays, quietly. Only a
FULL replay is scored: the timeline starts at round 1, so a single-round
`replay n` has nothing to start the track against and stays silent.

Re-simulation is the engine's own determinism: Battle(wa, wb, seed=round
seed) re-draws the transcript's offsets exactly; if a hand-written
transcript's offsets disagree, the renderer trusts the transcript's offsets
and notes it on stderr (tamper adjudication is the referee's verify(), never
the viewer's crash).
"""
import atexit
import math
import os
import random
import re
import select
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

from corewar import Battle, parse_warrior, CORE_SIZE

try:
    import termios, tty
except ImportError:          # non-POSIX: input feature quietly disables itself
    termios = tty = None

D = Path(os.environ.get('ARCADE_LIVE', '/tmp/corewar'))
MOVES, BANNER, CTL = D / 'moves.txt', D / 'banner.txt', D / 'ctl'
NAMES, RESULT = D / 'names.txt', D / 'result.txt'
WARRIORS = D / 'warriors'

# ---- geometry -------------------------------------------------------------
# The field is the whole core and can never change size: 100x80 memory cells
# at 2x4 cells per braille char is 50x20 chars, for ever. So there is no
# pitch ladder and no viewport ladder — only "the atlas fits" or "the strip".
CORE_COLS, CORE_ROWS = 100, 80
FIELD_W, FIELD_H = CORE_COLS // 2, CORE_ROWS // 4      # 50 x 20
GUTTER = 4                 # left address-label gutter (char cols)
BLOCK_W = GUTTER + 1 + FIELD_W                         # 55
ATLAS_ROWS = 1 + FIELD_H + 2                           # header/field/bars/status
FLOOR_COLS, FLOOR_ROWS = 20, 4    # below this even the strip refuses

TIER = 'strip'             # 'atlas' | 'strip' (set by fit_geometry)
BLOCK_X = 0                # left edge of the address gutter
CHROME_X = 0               # left edge of the chrome rows (wider than the block)

SHAKE = [0.0]              # plate shake amplitude in chars (elimination kick)
SHK_OFF = [0.0, 0.0]       # this frame's shake offset, rolled once per render

REDUCED_MOTION = os.environ.get('ARCADE_REDUCED_MOTION', '').lower() in {
    '1', 'true', 'yes', 'on',
}

names = {'r': 'TBD', 'b': 'TBD'}   # populated by refresh_names() on first render

# ---- broadcast pacing -----------------------------------------------------
FPS = 24.0
FRAME_DT = 1.0 / FPS
ROUND_TARGET_S = 50.0      # animation budget for a full 80000-cycle round.
                           # Measured wall time for match-002 round 1 (the
                           # worst case: an 80000-cycle tie) is ~60s at the
                           # atlas's frame cost, inside the ~90s broadcast
                           # budget with room for the momentum controller.
SLOW_TAIL = 350            # last cycles before a kill run at 1 cycle/frame
MOMENTUM_FAST, MOMENTUM_SLOW = 2.0, 0.35   # rate multipliers at rest / at full
                                           # momentum (§7)
LOADIN_S = 1.5             # drop-pod load-in, both bodies plus the dwell
VERDICT_S = 1.4
ELIM_S = 2.0               # flagship: the loser's territory cools core-wide
HITSTOP_S = 0.14           # kill-shot freeze before the cooling front plays
WASH_S = 1.2               # winner-wash ramp
DRAW_FADE_S = 3.2          # drawn match: both armies cool to embers together
IDLE_AGE = 2.0             # display cycles per idle frame: post-battle cooling

# ---- clickable replay button + keyboard shortcuts (tty only) --------------
# Headless/file-driven use (piped output, recordings) never enters any of
# this: INPUT_ENABLED is decided once, at import time, from stdin itself.
INPUT_ENABLED = bool(termios) and sys.stdin.isatty()
BTN_TEXT = '[ ▶ replay ]'
MARK = 'core war'          # the game's identity, bottom-right in LABEL: a
                           # quiet broadcast bug, never a caption. It is the
                           # first thing to yield when the row gets tight.
_orig_termios = None
_btn_bounds = None   # (row, col_start, col_end), 1-indexed terminal coords
_MOUSE_RE = re.compile(rb'\x1b\[<(\d+);(\d+);(\d+)([Mm])')


def enable_input():
    """Best-effort: any failure just leaves input disabled, never crashes."""
    global _orig_termios, INPUT_ENABLED
    if not INPUT_ENABLED:
        return
    try:
        _orig_termios = termios.tcgetattr(sys.stdin.fileno())
        tty.setcbreak(sys.stdin.fileno())
        sys.stdout.write('\x1b[?1000h\x1b[?1006h')   # click tracking, SGR coords
        sys.stdout.flush()
    except Exception:
        INPUT_ENABLED = False


def disable_input():
    if not (termios and _orig_termios is not None):
        return
    try:
        sys.stdout.write('\x1b[?1006l\x1b[?1000l')
        sys.stdout.flush()
    except Exception:
        pass
    try:
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _orig_termios)
    except Exception:
        pass


def poll_input():
    """Non-blocking. Returns 'replay', 'quit', or None. Never raises or blocks
    the render cadence -- any failure degrades to render-only (returns None)."""
    if not INPUT_ENABLED:
        return None
    try:
        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if not ready:
            return None
        data = os.read(sys.stdin.fileno(), 4096)
    except Exception:
        return None
    if not data:
        return None
    for m in _MOUSE_RE.finditer(data):
        _btn, cx, cy, kind = m.groups()
        if kind == b'M' and _btn_bounds and int(cy) == _btn_bounds[0] \
                and _btn_bounds[1] <= int(cx) <= _btn_bounds[2]:
            return 'replay'
    for b in _MOUSE_RE.sub(b'', data):    # leftover plain bytes: keyboard fallback
        ch = chr(b)
        if ch in ('r', 'R'):
            return 'replay'
        if ch in ('q', 'Q'):
            return 'quit'
    return None


def read_input():
    """Return the next non-blocking replay/quit action, if any."""
    return poll_input()


# ---- live replay audio (opt-in, silent by default) ------------------------
# See the module docstring's MUSIC section for the sync model and why the
# scoring pass turns the drawing off. Everything here is failure-tolerant by
# construction: the replay is the product, the soundtrack is a garnish, and a
# garnish may never take the plate down with it.
MUSIC = [os.environ.get('ARCADE_MUSIC', '').lower() in {'1', 'true', 'yes',
                                                        'on'}]
DRAW_FRAMES = True         # False during a scoring pass: run the pacing loop
                           # and fire the hooks, draw nothing
# The backend is one argv prefix and one function so a non-macOS player can
# take the seat later (`aplay`, `paplay`, `ffplay -nodisp -autoexit`) without
# anything else in this file knowing.
PLAYER = ['afplay']
_music_proc = [None]       # the live player, if any
_music_dir = [None]        # scratch dir for rendered WAVs
_music_wav = [None]        # (cache key, path) — one match's score, held
_player_note = [False]     # "no player on this machine" said once, ever


def set_music(on):
    """Turn the soundtrack on or off. Disabling stops playback NOW — a toggle
    that only takes effect at the next replay is not a mute button."""
    MUSIC[0] = bool(on)
    if not MUSIC[0]:
        stop_music()
    return MUSIC[0]


def _player_cmd(wav):
    """The playback argv for `wav`, or None if this machine cannot play it."""
    exe = shutil.which(PLAYER[0])
    if exe is None:
        return None
    return [exe] + list(PLAYER[1:]) + [str(wav)]


def play_wav(wav):
    """Start playback and return the process, or None (silently, once noted).

    Stdio is detached from the pane's: a player that decided to write to the
    terminal would be writing into the middle of a frame."""
    stop_music()
    cmd = _player_cmd(wav)
    if cmd is None:
        if not _player_note[0]:
            _player_note[0] = True
            sys.stderr.write(f'NOTE: no {PLAYER[0]} on this machine — the '
                             f'replay plays silently.\n')
        return None
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
    except OSError as e:
        sys.stderr.write(f'NOTE: could not start {PLAYER[0]} ({e}) — the '
                         f'replay plays silently.\n')
        return None
    _music_proc[0] = proc
    return proc


def stop_music():
    """Silence now, and leave no orphan. Called on replay restart, on quit, on
    disable and at exit — a player outliving the pane that started it would
    keep singing over whatever the terminal did next, with no way to stop it."""
    proc, _music_proc[0] = _music_proc[0], None
    if proc is None:
        return
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=1.0)
    except Exception:
        pass


def cleanup_music():
    """Stop playing and take the scratch WAVs with it (atexit + main's
    finally). A rendered score is 30 MB per match: leaking one per session is
    the tmp-hygiene bug this repo has already paid for twice."""
    stop_music()
    d, _music_dir[0] = _music_dir[0], None
    _music_wav[0] = None
    if d is not None:
        shutil.rmtree(d, ignore_errors=True)


def _music_dir_path():
    if _music_dir[0] is None:
        _music_dir[0] = Path(tempfile.mkdtemp(prefix='cw-music-'))
        atexit.register(cleanup_music)
    return _music_dir[0]


def score_replay(status=None):
    """Render THIS match's soundtrack to a WAV and return its path, or None.

    The whole score pipeline (record_cw.extract → score_cw → WAV) runs here,
    with the drawing switched off — see the docstring's MUSIC section. Imports
    are local because they are the heavy half of the arcade (numpy, and a
    second view of this module): a pane that never plays music must never pay
    for the ability, and a machine without numpy must still run the pane.

    Held in a session cache keyed on the transcript, so replay after replay of
    one match renders once and a rewritten transcript re-renders."""
    key = (str(D), read(MOVES))
    hit = _music_wav[0]
    if hit is not None and hit[0] == key and hit[1].exists():
        return hit[1]
    if status:
        status('scoring…')
    try:
        import record_cw
        # NOT this module's globals: run as __main__ the recorder imports its
        # own view of this file, and the scoring pass has to reach the copy
        # whose render() will actually be called.
        import tui_corewar as X
    except Exception as e:
        sys.stderr.write(f'NOTE: no soundtrack ({e}) — the replay plays '
                         f'silently.\n')
        return None
    saved_draw = X.DRAW_FRAMES
    X.DRAW_FRAMES = False
    try:
        tl = record_cw.extract(D)
        wav = _music_dir_path() / 'replay.wav'
        record_cw.write_wav(record_cw.synthesize(tl), wav)
    except (Exception, SystemExit) as e:
        # extract() exits on a directory that is not a match; synthesis needs
        # numpy. Both are "no music today", never "no replay today".
        sys.stderr.write(f'NOTE: no soundtrack ({e}) — the replay plays '
                         f'silently.\n')
        return None
    finally:
        X.DRAW_FRAMES = saved_draw
    _music_wav[0] = (key, wav)
    return wav


ctl_mtime = 0
_fcache = {}


def bg(c): return f'\x1b[48;2;{c[0]};{c[1]};{c[2]}m'
def fg(c): return f'\x1b[38;2;{c[0]};{c[1]};{c[2]}m'
R = '\x1b[0m'


def read(p, default=''):
    try:
        return p.read_text().strip()
    except (OSError, UnicodeDecodeError):
        # a bus file holding non-UTF-8 garbage is a degraded bus, not a crash
        return default


def read_cached(p):
    try:
        st = p.stat().st_mtime_ns
    except OSError:
        return ''
    hit = _fcache.get(p)
    if hit and hit[0] == st:
        return hit[1]
    v = read(p)
    _fcache[p] = (st, v)
    return v


def refresh_names():
    """Re-read names.txt if it changed (mtime-cached) — ported from
    tui_xiangqi.py's fix for the viewer-outlives-a-pairing bug. Missing or
    malformed content keeps the last known-good value; never raises."""
    parts = read_cached(NAMES).split()
    if len(parts) == 2:
        names['r'], names['b'] = parts[0].upper(), parts[1].upper()


def blend(a, b, t):
    t = max(0.0, min(1.0, t))
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def scale(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


# ---- dot material ---------------------------------------------------------
# BITS is the exact braille dot grid, forked verbatim from tui_dots.py. The
# BAYER halftone died with the per-cell tier: at atlas grain a char's dots
# are not a density ramp, they are eight memory cells, and lighting one that
# nobody owns would be a lie about occupancy.
BITS = ((0x01, 0x02, 0x04, 0x40), (0x08, 0x10, 0x20, 0x80))  # BITS[dx][dy]
FULL = 0xFF

# Palette — tui_dots.py verbatim, plus tui_xiangqi.py's WINDOW_BG pit floor.
PANEL = (18, 21, 28)
SQD = (26, 30, 39)
AMBIENT = (52, 58, 72)
ICE, EMBER = (125, 212, 236), (240, 162, 74)
W_SOLID = (240, 249, 255)
WINDOW_BG = (14, 18, 24)
TEXT, TDIM, LABEL = (204, 212, 228), (118, 128, 148), (92, 102, 122)
SLATE = (136, 145, 164)
HUES = (EMBER, ICE)                # warrior A warm, warrior B cool
EMBER_DEEP, ICE_DEEP = (158, 42, 20), (30, 84, 168)
HUES_DEEP = (EMBER_DEEP, ICE_DEEP)  # cold-territory ramp roots: brick / steel
ASH = (36, 40, 50)                 # a dying process's bloom — an FX colour,
                                   # never the colour of owned ground
TAU = 300.0                        # heat decay, in cycles
WAVE_PERIOD, WAVE_AMP = 30.0, 0.5  # unchanged from tui_dots.py
# THE COLD FLOOR — owned ground never decays past a legible faction whisper.
# The board is the evidence for the bars: when the caption says "99% held",
# the field must READ as that army's field even stone cold, hours after the
# last write. Cold ground therefore lands on a dim but unmistakably tinted
# brick / steel, distinct from each other at a glance; it never converges on
# a neutral grey, because a neutral grey is a claim that nobody owns this.
# Balanced against the late-loudness correction by luminance, not hue: cold
# sits around a third of a hot cell's brightness, so live fronts still own a
# saturated frame while cold territory keeps its colour.
COLD_TINT = 0.55                   # hue surviving at zero heat
COLD_DIM = 0.70                    # and how dark that whisper sits
DEAD_DIM = 0.62                    # an eliminated army: dimmer still, its
                                   # own hue kept — the death wave reads by
                                   # brightness, which is what "dead" looks
                                   # like; hue is identity, not vitality

# priorities: field lowest, plate FX only touch bg, process markers on top
FIELD_PRI, PROC_PRI = -1, 3

# Plate FX — every event effect lives in the bg channel. Dots answer WHO and
# nothing else, so an FX that lit or cleared a dot would fabricate occupancy
# (the same argument that killed the comet moat at this grain).
# FX_CAP is deliberately small. The inherited 120 was written for a tier
# that showed one bomb at a time; at broadcast pace the renderer steps tens
# of cycles per frame, so a bombing run spawns dozens of effects per frame
# and a queue of 120 covers an eighth of the whole core in light — the
# over-fire lesson again, this time in the time axis rather than the space
# axis. Capped at 24 with sub-quarter-second lives, the same run reads as a
# drumbeat: a handful of blocks pulsing, the rest of the plate honest.
FX_CAP = 24
FX_LIFE = {'bomb': 0.20, 'spl': 0.32, 'death': 0.30, 'wrap': 0.30,
           'kill': 0.60}


class Grid:
    """Cell buffer — forked from tui_dots.py (via tui_xiangqi.py), plus a
    per-cell bg because the plate is half the encoding. Higher priority wins
    the single fg colour each braille cell is allowed; `plate` lifts the bg
    without touching the dots. Chrome never enters the Grid: labels and
    status are composed as strings."""
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.b = [[0] * w for _ in range(h)]
        self.f = [[None] * w for _ in range(h)]
        self.p = [[-99] * w for _ in range(h)]
        self.bg = [[SQD] * w for _ in range(h)]

    def set_cell(self, cx, cy, bits, col, pri, back=None):
        if 0 <= cx < self.w and 0 <= cy < self.h:
            if pri >= self.p[cy][cx]:
                self.b[cy][cx] = bits
                self.f[cy][cx] = col
                self.p[cy][cx] = pri
            if back is not None:
                self.bg[cy][cx] = back

    def plate(self, cx, cy, col, weight):
        if 0 <= cx < self.w and 0 <= cy < self.h and weight > 0.002:
            self.bg[cy][cx] = blend(self.bg[cy][cx], col, weight)


# ---- transcript + warriors (the truth; battle.json is never read) ---------
LOAD_RE = re.compile(r'^LOAD ([AB]) ([0-9a-f]{64})$')
ROUND_RE = re.compile(r'^ROUND (\d+) seed=(\d+) off=(\d+),(\d+)$')
OUT_RE = re.compile(r'^ROUND (\d+) OUT (1-0|0-1|tie) cycles=(\d+)$')
ROUNDS_PER_MATCH = 3


def transcript_lines():
    # one read() call, no exists()-then-read window, garbage bytes tolerated
    return [ln for ln in read(MOVES).splitlines() if ln.strip()]


def parse_transcript(lines):
    """Tolerant parse of the transcript grammar (ref_cw.py's, cloned — the
    bus layer is frozen and importing it would drag chat.py in). Returns
    (loads, rounds, err): whatever parses cleanly, plus the first problem.
    The referee's verify() adjudicates tampering; the viewer renders what it
    has and notes the rest."""
    loads, rounds = {}, []
    rest = list(lines)
    for expect in ('A', 'B'):
        if rest and LOAD_RE.match(rest[0]) and LOAD_RE.match(rest[0]).group(1) == expect:
            loads[expect] = LOAD_RE.match(rest.pop(0)).group(2)
    err = None
    if len(loads) == 1:
        err = f'incomplete LOAD header in transcript ({len(rest)} lines left)'
    i = 0
    while i + 1 < len(rest):
        rm, om = ROUND_RE.match(rest[i]), OUT_RE.match(rest[i + 1])
        n = len(rounds) + 1
        if not rm or not om or int(rm.group(1)) != n or int(om.group(1)) != n:
            err = f'transcript stops parsing at {rest[i]!r}'
            break
        rounds.append({'n': n, 'seed': int(rm.group(2)),
                       'off_a': int(rm.group(3)), 'off_b': int(rm.group(4)),
                       'out': om.group(2), 'cycles': int(om.group(3))})
        i += 2
    if err is None and i < len(rest):
        err = f'unpaired transcript line: {rest[i]!r}'
    return loads, rounds, err


def read_warriors():
    """(wa, wb, display names, err) from the locked sources — tolerant:
    a missing/invalid warrior leaves the phase machinery honest, never raises."""
    try:
        a_src = (WARRIORS / 'A.red').read_text()
        b_src = (WARRIORS / 'B.red').read_text()
    except (OSError, UnicodeDecodeError) as e:
        return None, None, {'A': 'A', 'B': 'B'}, f'warrior unreadable: {e}'
    try:
        wa, wb = parse_warrior(a_src), parse_warrior(b_src)
    except Exception as e:
        return None, None, {'A': 'A', 'B': 'B'}, f'warrior does not assemble: {e}'
    return wa, wb, {'A': wa.name or 'A', 'B': wb.name or 'B'}, None


def score_of(result):
    return '1-0' if result.winner == 'A' else '0-1' if result.winner == 'B' else 'tie'


def match_line(rounds):
    """The ledger-format match string from per-round outcomes."""
    pts = sum(1.0 if r['out'] == '1-0' else 0.5 if r['out'] == 'tie' else 0.0
              for r in rounds)
    half = len(rounds) / 2.0
    if pts > half:
        return '1-0'
    if pts < half:
        return '0-1'
    return '1/2-1/2'


# ---- the scene: everything render() is allowed to know --------------------
class Scene:
    """The renderable state of the room. Rebuilt from the transcript on every
    cold start; animation mutates it through apply_event only."""

    def __init__(self):
        self.phase = 'workshop'      # workshop | locked | battle | over
        self.lines = []              # transcript lines as last seen
        self.loads = {}
        self.rounds = []
        self.animated = 0            # rounds fully shown (or snapped)
        self.wa = self.wb = None
        self.wname = {'A': 'A', 'B': 'B'}
        # field model (parallel arrays over the 8000 cells)
        self.owner = [None] * CORE_SIZE
        self.age = [-1] * CORE_SIZE
        self.bomb = [False] * CORE_SIZE
        self.body = set()
        self.body_frac = {}          # body addr -> 0..1 load-in reveal order
        self.disp_cycle = 0.0        # display clock, in cycles — drives heat
        self.procs = ([], [])
        self.own = (0, 0)            # owned-cell counts, refreshed per frame
        self.battle = None
        self.round_no = 0
        self.verdict = None          # (n, out, cycles) while the beat shows
        self.elim = None             # [loser, t0, kill_addr, dist-dict]
        self.wash = None             # (winner 0/1 or 'draw', t0)
        self.washed = False
        self.embers = 0.0            # drawn-match shared fade, 0..1
        self.loadin = None           # (t0, per-warrior progress) during §1
        self.fx = []                 # plate FX: [kind, addr, t0, warrior]
        self.last_pc = [None, None]  # per warrior, for wrap detection (§3)
        self.claims = 0              # ownership flips since the last frame (§7)
        self.cooled = set()          # warriors whose territory is cold for good
        self.warrior_note = False    # unreadable-warrior NOTE emitted already
        # event ticker (pure scene state; the status row shows the latest)
        self.events = []             # newest last, capped at 8
        self.first_blood = False     # first crater of the round fired already
        self.milestones = set()      # (warrior, threshold) territory marks hit
        self.reveal = None           # replay-local ledger cursor: while a
                                     # single-round replay runs, the ledger
                                     # tallies only rounds BEFORE it

    def snapshot(self):
        """In-memory hold of the end state across a single-round replay —
        session memory only, never a disk cache (cold start never caches)."""
        return (self.owner[:], self.age[:], self.bomb[:], self.disp_cycle,
                (list(self.procs[0]), list(self.procs[1])), self.phase,
                self.round_no, self.wash, self.washed, self.animated,
                set(self.cooled), self.events[:], self.first_blood,
                set(self.milestones), self.reveal, self.embers, self.own)

    def restore(self, snap):
        (self.owner, self.age, self.bomb, self.disp_cycle, self.procs,
         self.phase, self.round_no, self.wash, self.washed, self.animated,
         self.cooled, self.events, self.first_blood,
         self.milestones, self.reveal, self.embers, self.own) = snap
        self.verdict = None
        self.elim = None
        self.loadin = None
        self.fx = []


def cold_start():
    """Rebuild everything from the live dir. Never raises on bad content —
    the referee owns tamper response; the viewer stays alive and honest."""
    sc = Scene()
    sc.lines = transcript_lines()
    sc.loads, sc.rounds, err = parse_transcript(sc.lines)
    if err:
        sys.stderr.write(f'NOTE: {err} — rendering what parses; tamper '
                         f'adjudication is the referee verify command, '
                         f'never the viewer.\n')
    sc.wa, sc.wb, sc.wname, _werr = read_warriors()
    refresh_names()
    if not sc.loads:
        sc.phase = 'workshop'
    elif not sc.rounds:
        sc.phase = 'locked'
    else:
        sc.phase = 'battle'
    return sc


def reset_field(sc, battle):
    """Round cut: clear the field and claim both bodies. The load-in order
    (§1) is recorded here — each body cell's fraction along its own warrior's
    listing, so the scanline writes the program in the order it was written."""
    sc.owner = [None] * CORE_SIZE
    sc.age = [-1] * CORE_SIZE
    sc.bomb = [False] * CORE_SIZE
    sc.body = set()
    sc.body_frac = {}
    for w, (off, warrior) in enumerate(((battle.off_a, sc.wa),
                                        (battle.off_b, sc.wb))):
        n = max(1, len(warrior.instructions))
        for i in range(len(warrior.instructions)):
            addr = (off + i) % CORE_SIZE
            sc.body.add(addr)
            sc.body_frac[addr] = (i + 1) / n
            sc.owner[addr] = w
            sc.age[addr] = 0
    sc.disp_cycle = 0.0
    sc.procs = ([battle.off_a], [battle.off_b])
    sc.own = (sc.owner.count(0), sc.owner.count(1))
    sc.battle = battle
    sc.round_no = 0
    sc.verdict = None
    sc.elim = None
    sc.loadin = None
    sc.cooled = set()
    sc.embers = 0.0
    sc.fx = []
    sc.last_pc = [battle.off_a, battle.off_b]
    sc.claims = 0
    sc.events = []
    sc.first_blood = False
    sc.milestones = set()
    SHAKE[0] = 0.0
    SHK_OFF[0] = SHK_OFF[1] = 0.0


def player_name(w):
    """The player name for a warrior index — chrome speaks in the players'
    names (names.txt), never the warriors'."""
    return names['r'] if w == 0 else names['b']


def push_event(sc, text):
    """Append to the event ticker (max 8, newest last). Pure scene state —
    text, not motion, so it is never REDUCED_MOTION-gated."""
    sc.events.append(text)
    del sc.events[:-8]


def beat(kind, addr, w, now, **extra):
    """Announce a moment on the broadcast clock. EVENT_HOOK is FRAME_HOOK's
    twin: FRAME_HOOK says "a frame was drawn at t", this says "a bomb landed
    at t". Neither changes what the pane does — both exist so an offline tool
    (the recorder) can reconstruct the broadcast's timeline from the one
    authority that owns it, this module's own pacing, instead of copying the
    formulas somewhere they can drift.

    Deliberately NOT the same call as push_fx: the plate queue is
    REDUCED_MOTION-gated and FX_CAP-bounded because it is a picture, and a
    timeline that inherited either would be missing events that happened."""
    if EVENT_HOOK is not None:
        EVENT_HOOK(kind, addr, w, now, extra)


def push_fx(sc, kind, addr, w, now):
    """Queue a plate effect. FX_CAP bounds the queue because fast_forward
    never prunes; every lifetime is under a second so draw_fx prunes
    promptly on its own."""
    if len(sc.fx) < FX_CAP:
        sc.fx.append([kind, addr % CORE_SIZE, now, w])


def apply_event(sc, ev, battle, now):
    """One engine step applied to the field model: execution and writes both
    claim ownership (the gate-locked rule: last written/executed)."""
    w = ev.warrior
    if sc.owner[ev.pc] != w:
        sc.claims += 1
    sc.owner[ev.pc] = w
    sc.age[ev.pc] = ev.cycle
    prev = sc.last_pc[w]
    if prev is not None and prev >= CORE_SIZE - CORE_COLS and ev.pc < CORE_COLS:
        # §3: this warrior's execution just crossed 7999 → 0. The two cells
        # are one step apart in memory and a whole frame apart on screen, so
        # the spark is the only thing that says memory is a ring.
        beat('wrap', ev.pc, w, now)
        if not REDUCED_MOTION:
            push_fx(sc, 'wrap', ev.pc, w, now)
    sc.last_pc[w] = ev.pc
    for addr in ev.writes:
        if sc.owner[addr] != w:
            sc.claims += 1
        sc.owner[addr] = w
        sc.age[addr] = ev.cycle
        was_bomb = sc.bomb[addr]
        sc.bomb[addr] = (battle.core[addr].opcode == 'DAT'
                         and addr not in sc.body)
        if sc.bomb[addr] and not was_bomb:
            if not sc.first_blood:
                sc.first_blood = True
                push_event(sc, f'first blood — {player_name(w)} lands the '
                               f'first bomb')
                beat('first-blood', addr, w, now)
            beat('bomb', addr, w, now)
            if not REDUCED_MOTION:
                # §5's drumbeat: at atlas grain a fresh crater lifts its
                # plate ~7%, so the bomb is otherwise invisible as an event
                push_fx(sc, 'bomb', addr, w, now)
    if ev.spawned:
        n = len(battle.procs[w])
        if n >= 8 and n & (n - 1) == 0:
            # fork bloom: the queue crossed a doubling mark (8, 16, 32, ...)
            push_event(sc, f'{player_name(w)} splits: {n // 2} → {n} running')
            beat('bloom', ev.pc, w, now, queue=n)
        beat('spl', ev.pc, w, now)
        if not REDUCED_MOTION:
            # The split-off process is the newest entry in the queue (5.5.15).
            push_fx(sc, 'spl', battle.procs[w][-1], w, now)
    if ev.died:
        push_event(sc, f"{player_name(w)}'s copy dies at {ev.pc}")
        beat('death', ev.pc, w, now)
        if not REDUCED_MOTION:
            push_fx(sc, 'death', ev.pc, w, now)
    if ev.eliminated:
        push_event(sc, f"{player_name(w)}'s last copy died")
        sc.elim = [w, None, ev.pc, None]   # w is the loser; t0 set at the beat


def claim_procs(sc, battle):
    sc.procs = (list(battle.procs[0]), list(battle.procs[1]))
    # territory milestones ride the per-frame beat (not apply_event): the
    # count costs O(core) and the ticker only ever shows the latest event,
    # so frame-granularity crossings are indistinguishable — each fires once
    sc.own = (sc.owner.count(0), sc.owner.count(1))
    for w in (0, 1):
        for threshold, feat in ((CORE_SIZE // 2, 'holds half the board'),
                                (CORE_SIZE * 3 // 4,
                                 'holds three-quarters of the board')):
            if sc.own[w] >= threshold and (w, threshold) not in sc.milestones:
                sc.milestones.add((w, threshold))
                push_event(sc, f'{player_name(w)} {feat}')


def pacing(total_cycles, out):
    """The round's baseline cycles-per-frame and its slow tail. A full
    80000-cycle round completes in ~ROUND_TARGET_S of animation (inside the
    ~90s broadcast budget); the last SLOW_TAIL cycles of a kill run at 1
    cycle/frame so the death breathes. The live rate re-derives from this
    baseline every frame — see momentum_rate."""
    cpf = max(1, math.ceil(total_cycles / (FPS * ROUND_TARGET_S)))
    slow_from = max(0, total_cycles - SLOW_TAIL) if out != 'tie' else None
    return cpf, slow_from


def momentum_rate(remaining, frames_left, momentum):
    """§7's momentum-aware playback. The baseline is always "cycles left over
    frames left", so every frame spent crawling is repaid by the frames after
    it — the round lands inside its budget no matter how the battle behaves.
    On top of that baseline, `momentum` (0 = nothing is happening, 1 = the
    front is moving hard) slides the rate between MOMENTUM_FAST and
    MOMENTUM_SLOW: quiet stretches run ahead and bank slack, and the slack
    pays for the crawl when ground starts changing hands."""
    base = remaining / max(1, frames_left)
    mod = MOMENTUM_FAST + (MOMENTUM_SLOW - MOMENTUM_FAST) * min(1.0, momentum)
    return max(1, int(round(base * mod)))


def frame_momentum(claims, cycles, procs_before, procs_after):
    """Deterministic activity metric from the transcript's own re-simulation:
    how much ground changed hands per cycle, plus how hard the process queues
    swung. Both are functions of the battle, not of wall time, so two replays
    of one round pace identically."""
    if cycles <= 0:
        return 0.0
    claim_rate = min(1.0, (claims / float(cycles)) / 0.6)
    swing = min(1.0, abs(procs_after - procs_before)
                / max(4.0, 0.25 * max(procs_before, procs_after, 1)))
    return min(1.0, 0.65 * claim_rate + 0.35 * swing)


# ---- the field ------------------------------------------------------------
def _shake():
    """The plate's shake offset in whole chars. The atlas is stationary, so
    the kick moves the drawn plate on screen — never the address mapping."""
    return int(round(SHK_OFF[0])), int(round(SHK_OFF[1]))


def wash_level(sc, t):
    """End-treatment strength: the winner's hue washes the field and holds.
    A drawn match takes the shared ember fade instead (sc.embers), so there
    is no hue to wash with."""
    if sc.wash is None or sc.wash[0] == 'draw':
        return None, 0.0
    kind, t0 = sc.wash
    return HUES[kind], 0.30 * min(1.0, (t - t0) / WASH_S)


def ground_colour(o, h):
    """The colour of ground held by warrior `o` at heat `h`. The ramp runs
    from the cold floor — a dim but unmistakable brick / steel — up to the
    full faction hue, and it has no exit at the bottom: heat can reach zero,
    but faction identity cannot. That is what makes the board corroborate
    the bars, which is the whole job of a field that reports territory."""
    root = blend(AMBIENT, HUES_DEEP[o], COLD_TINT + (1.0 - COLD_TINT) * h)
    return scale(blend(root, HUES[o], h), COLD_DIM + 0.62 * h)


def draw_field(g, sc, t):
    """The whole core, 8 memory cells per braille char, two channels that
    never mix (see the module docstring). Screen char (cx, cy) shows core
    block (cx - dx, cy - dy) during a shake, so the plate slides but the
    address mapping does not."""
    owner, age, bomb = sc.owner, sc.age, sc.bomb
    now = sc.disp_cycle
    dx0, dy0 = _shake()
    hue_w, wash = wash_level(sc, t)
    embers = sc.embers
    elim = sc.elim
    if elim is not None and elim[1] is not None:
        elim_p, elim_loser, elim_d = (t - elim[1]) / ELIM_S, elim[0], elim[3]
    else:
        elim_p = None
    loadin = sc.loadin
    for sy in range(FIELD_H):
        cy = sy - dy0
        for sx in range(FIELD_W):
            cx = sx - dx0
            if not (0 <= cx < FIELD_W and 0 <= cy < FIELD_H):
                g.set_cell(sx, sy, 0, AMBIENT, FIELD_PRI, back=SQD)
                continue
            n0 = n1 = 0
            bits = 0
            h0 = h1 = 0.0
            npit = 0
            glow_h, glow_o, glow_sum = 0.0, 0, 0.0
            base = (4 * cy) * CORE_COLS + 2 * cx
            for dx in (0, 1):
                for dy in range(4):
                    addr = base + dy * CORE_COLS + dx
                    o = owner[addr]
                    if o is None:
                        continue
                    if loadin is not None and loadin[1][o] < sc.body_frac.get(
                            addr, -1.0):
                        continue          # §1: not yet written into the core
                    a = age[addr]
                    h = math.exp(-(now - a) / TAU) if 0 <= a <= now else 0.0
                    if o in sc.cooled:
                        h = 0.0
                    elif elim_p is not None and o == elim_loser:
                        d = elim_d.get(addr, 999.0) if elim_d else 0.0
                        h *= 1.0 - min(1.0, max(0.0,
                                                (elim_p * 140.0 - d) / 36.0))
                    if embers:
                        h *= 1.0 - embers
                    if bomb[addr]:
                        npit += 1
                        glow_sum += h * h
                        if h > glow_h:
                            glow_h, glow_o = h, o
                    bits |= BITS[dx][dy]
                    if o:
                        n1 += 1
                        if h > h1:
                            h1 = h
                    else:
                        n0 += 1
                        if h > h0:
                            h0 = h

            # --- plate: damage, contest, glow. Never carries ownership. ----
            if bits:
                back = SQD
            else:
                # the slow density wave lives on the untouched plate only —
                # owned ground is a calm pocket (§8.6), and a stipple dot
                # would read as occupancy, which a dot must never do falsely
                wave = 0.5 if REDUCED_MOTION else 0.5 + 0.5 * math.sin(
                    (cx * 0.7 + cy * 1.9) / WAVE_PERIOD * 2 * math.pi + t)
                back = blend(SQD, AMBIENT, 0.40 * WAVE_AMP * wave)
            if npit:
                back = blend(back, WINDOW_BG, npit / 8.0)
            lo, hi = (n1, n0) if n0 > n1 else (n0, n1)
            contest = 0.0
            if lo and lo / float(lo + hi) >= 0.25:
                contest = min(1.0, 2.0 * lo / 8.0) * max(h0, h1)
                jit = 1.0 if REDUCED_MOTION else \
                    0.78 + 0.22 * math.sin(cx * 3.1 + cy * 5.7 + t * 3.0)
                back = blend(back, SLATE, 0.55 * contest * jit)
            if glow_sum > 0.0:
                back = blend(back, HUES[glow_o], 0.55 * glow_sum / 8.0)
            if embers:
                back = blend(back, WINDOW_BG, 0.45 * embers)

            # --- dots: who holds this block, at what heat. -----------------
            if not bits:
                g.set_cell(sx, sy, 0, AMBIENT, FIELD_PRI, back=back)
                continue
            o = 0 if n0 > n1 else 1 if n1 > n0 else (0 if h0 >= h1 else 1)
            h = h0 if o == 0 else h1
            col = ground_colour(o, h)
            if o in sc.cooled:
                col = scale(col, DEAD_DIM)
            elif contest:
                # contest reads in both channels or in neither: a lit plate
                # alone looks like a UI card dropped on the field. The dots
                # burn brighter in the owner's OWN hue, so no third colour
                # is ever invented.
                col = scale(col, 1.0 + 0.30 * contest)
            if embers:
                # the drawn-match fade dims what is already at the cold
                # floor; it never bleaches it, so a drawn field ends as two
                # armies of banked embers, not as grey
                col = scale(col, 1.0 - 0.25 * embers)
            if wash:
                col = blend(col, hue_w, wash)
            g.set_cell(sx, sy, bits, col, FIELD_PRI, back=back)


def draw_fx(g, sc, t):
    """Every event effect, in the plate channel: the bomb drumbeat (§5), the
    SPL birth bloom, a process death, and the wrap spark (§3). Prunes its own
    expired entries. Nothing here touches a dot — dots answer WHO, and an
    effect that lit one would fabricate occupancy."""
    if REDUCED_MOTION:
        sc.fx = []
        return
    live = []
    dx0, dy0 = _shake()
    for entry in sc.fx:
        kind, addr, t0, w = entry
        life = FX_LIFE[kind]
        prog = (t - t0) / life
        if prog >= 1.0 or prog < 0.0:
            continue
        live.append(entry)
        k = 1.0 - prog
        row, col = divmod(addr, CORE_COLS)
        cx, cy = col // 2 + dx0, row // 4 + dy0
        if kind == 'wrap':
            # one cell each at the exit and the entry corner of the core
            spark = blend(HUES[w], W_SOLID, 0.5)
            g.plate(FIELD_W - 1, FIELD_H - 1, spark, 0.85 * k)
            g.plate(0, 0, spark, 0.85 * k)
            continue
        if kind == 'bomb':
            # the drumbeat: a bright flash on the bomb's own block, white-hot
            # in the bomber's hue but on the PLATE. Near-white dots mean "a
            # process is here" and may never mean anything else, so the spark
            # lives in bg. No ring — bombs are the most frequent event on the
            # board and a ring per bomb washes the field out.
            g.plate(cx, cy, blend(HUES[w], W_SOLID, 0.45), 0.85 * k)
            continue
        if kind == 'kill':
            # the one event that earns a shockwave: it happens once a round
            g.plate(cx, cy, blend(HUES[w], W_SOLID, 0.6), 0.95 * k)
            radius, weight, hue = 0.5 + 9.0 * prog, 0.55 * k, HUES[w]
        elif kind == 'spl':
            g.plate(cx, cy, blend(HUES[w], W_SOLID, 0.3), 0.45 * k)
            radius, weight, hue = 0.4 + 1.4 * prog, 0.22 * k, HUES[w]
        else:                                   # 'death'
            g.plate(cx, cy, ASH, 0.7 * k)
            radius, weight, hue = 0.5 + 1.2 * prog, 0.20 * k, HUES_DEEP[w]
        span = int(radius) + 1
        for ry in range(cy - span, cy + span + 1):
            for rx in range(cx - span, cx + span + 1):
                # the char cell is twice as tall as it is wide, so the ring
                # is drawn round on screen, not round in char coordinates
                d = math.hypot(rx - cx, (ry - cy) * 2.0)
                if abs(d - radius) < 0.9:
                    g.plate(rx, ry, hue, weight)
    sc.fx = live


def draw_processes(g, sc, t):
    """A process is one memory cell = one dot among 8000, i.e. invisible. The
    marker is promoted to the whole char: FULL 8 dots at near-white, the
    board's brightest object and its one admitted lie (8 cells claimed for
    1). Co-located PCs merge, so an imp train draws a white worm and a stone
    engine a single steady block — the shapes differ for free, and there is
    no cap: a SPL flood lighting a region white is a true read.

    §4's tempo comes out of the phase term: it is a function of the PC's own
    address, so a crawling process shimmers as it moves while a stationary
    engine thumps on a steady beat. Deterministic in (addr, t)."""
    dx0, dy0 = _shake()
    cells = {}
    for w, pcs in enumerate(sc.procs):
        if sc.loadin is not None and sc.loadin[1][w] < 1.0:
            continue           # §1: nothing runs before its code is written
        for pc in pcs:
            row, col = divmod(pc % CORE_SIZE, CORE_COLS)
            key = (col // 2, row // 4)
            slot = cells.get(key)
            if slot is None:
                slot = cells[key] = [0, 0, pc]
            slot[w] += 1
    for (cx, cy), (na, nb, pc) in cells.items():
        o = 0 if na >= nb else 1
        if REDUCED_MOTION:
            pulse = 0.72
        else:
            pulse = 0.62 + 0.20 * (0.5 + 0.5 * math.sin(pc * 0.37 + t * 2.0))
        col = blend(HUES[o], W_SOLID, pulse)
        if sc.embers:
            # a drawn match cools everything together, survivors included —
            # down to their own army's banked colour, never to grey
            col = blend(col, ground_colour(o, 0.0), 0.8 * sc.embers)
        g.set_cell(cx + dx0, cy + dy0, FULL, col, PROC_PRI)


# ---- chrome ---------------------------------------------------------------
def display_width(text):
    """Terminal-cell width without depending on wcwidth at runtime."""
    return sum(2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1
               for ch in text)


def clip_display(text, width):
    out, used = [], 0
    for ch in text:
        step = 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1
        if used + step > width:
            break
        out.append(ch)
        used += step
    return ''.join(out)


TEACH = '  ·  all 8,000 cells of memory, one dot each'


def header_segments(sc, avail):
    """Players in their faction hues, then the teaching line — the audience
    has never seen Core War and the header is where "what am I looking at"
    gets answered. The teaching clause drops before a name is clipped."""
    fixed = 4                                     # ' vs '
    each = max(2, (avail - fixed) // 2)
    ra = clip_display(names['r'], min(20, each))
    rb = clip_display(names['b'], min(20, each))
    segs = [(ra, EMBER, True), (' vs ', TDIM, False), (rb, ICE, True)]
    used = display_width(ra) + display_width(rb) + fixed
    if used + display_width(TEACH) <= avail:
        segs.append((TEACH, TDIM, False))
    return segs


BAR_W = 9
EIGHTHS = ' ▏▎▍▌▋▊▉'      # index = eighths of a cell filled


def bar(frac):
    """A 9-cell bar with an eighth-block leading edge. Whole cells alone
    could not show a share below 5.6% at all — and every battle starts
    there, with two bodies in an empty core — so the first sliver of ground
    has to be visible or the bar reads as broken for the opening minute."""
    fill = min(1.0, max(0.0, frac)) * BAR_W
    whole = int(fill)
    part = int((fill - whole) * 8)
    if whole >= BAR_W:
        return '█' * BAR_W
    if part == 0 and whole == 0 and frac > 0.0:
        part = 1                     # any ground held at all shows an edge
    return ('█' * whole + (EIGHTHS[part] if part else '')
            + '░' * (BAR_W - whole - (1 if part else 0)))


def faction_bar_segments(sc, w, pad, compact):
    """One army's line: name, share-of-core bar, ground held, copies running.
    "held" is doing real work here — the two bars are share of the WHOLE
    core, so they do not sum to 100 while untouched memory remains."""
    name = (names['r'], names['b'])[w]
    hue = HUES[w]
    segs = [(name.ljust(pad) + ' ', hue, True),
            (bar(sc.own[w] / float(CORE_SIZE)) + ' ', hue, False),
            (f'{sc.own[w] * 100.0 / CORE_SIZE:.0f}%'
             + ('' if compact else ' held'), TEXT, False)]
    if not compact:
        segs.append((f' · {len(sc.procs[w])} running', TDIM, False))
    return segs


def bars_row_segments(sc, budget):
    """Both faction bars side by side (they fit one row: the field is 50 wide
    for ever, so the chrome has the width the field cannot use), or the
    legend before the battle starts."""
    if sc.phase in ('workshop', 'locked'):
        return legend_segments()
    pad = max(len(names['r']), len(names['b']))
    full = []
    for w in (0, 1):
        segs = faction_bar_segments(sc, w, pad, compact=False)
        full.append(segs)
    half = budget // 2
    compact = any(sum(display_width(tx) for tx, _c, _b in segs) > half - 2
                  for segs in full)
    if compact:
        full = [faction_bar_segments(sc, w, pad, compact=True) for w in (0, 1)]
    out = []
    for w in (0, 1):
        if w:
            out.append(('  ', TDIM, False))
        out.extend(full[w])
    return out


def legend_segments():
    return [(names['r'], EMBER, False), (' = ember · ', TDIM, False),
            (names['b'], ICE, False), (' = ice · ', TDIM, False),
            ('one dot = one memory cell · white block = running code · '
             'dark pit = bomb damage', TDIM, False)]


def ledger_entries(sc):
    """The round ledger as (number, outcome, winner-index) tuples — animated
    rounds only, because the transcript is complete and naming an un-animated
    outcome would spoil the replay. The reveal cursor narrows it further
    during a single-round replay: re-animating round n shows only the rounds
    before it."""
    shown = sc.reveal if sc.reveal is not None else sc.animated
    out = [(r['n'], r['out'], None if r['out'] == 'tie'
            else (0 if r['out'] == '1-0' else 1))
           for r in sc.rounds[:shown]]
    if sc.phase == 'battle' and shown < len(sc.rounds):
        out.append((sc.rounds[shown]['n'], 'live', None))
    return out


def ledger_segments(sc, compact=False):
    """The round history in words. `1 tied · 2 tied · 3 live` was read as a
    tally of something rather than a list of rounds, so every entry now says
    which round it is and what happened in it, and a win names the winner in
    that army's hue. On its own row each entry repeats "round"; folded back
    into the status row the word is said once and then implied."""
    entries = ledger_entries(sc)
    if not entries:
        return []
    segs = []
    for i, (n, out, w) in enumerate(entries):
        if i:
            segs.append((' · ', TDIM, False))
        if not compact:
            head = f'round {n} '
        elif i:
            head = f'{n} '
        else:
            # "rounds 1 playing" for a single entry is a plural counting one
            # thing; the first round of a match says "round"
            head = f'{"rounds" if len(entries) > 1 else "round"} {n} '
        if out == 'live':
            segs.append((head + 'playing', TDIM, False))
        elif w is None:
            segs.append((head + 'tie', TEXT, False))
        else:
            segs.append((head, TEXT, False))
            segs.append(((names['r'], names['b'])[w], HUES[w], False))
            segs.append((' won', TEXT, False))
    return segs


def status_segments(sc):
    """(text, color, bold) segments for the footer — the phase voice, plain
    language: the audience has never seen Core War. Player names, thousands
    separators, no jargon."""
    if sc.phase == 'workshop':
        return [('waiting for two programs', TEXT, False)]
    if sc.phase == 'locked':
        return [(names['r'], EMBER, False), (' vs ', TDIM, False),
                (names['b'], ICE, False), (' · locked and loaded', TEXT, False)]
    if sc.phase == 'over':
        aw = sum(1 for r in sc.rounds if r['out'] == '1-0')
        bw = sum(1 for r in sc.rounds if r['out'] == '0-1')
        tied = len(sc.rounds) - aw - bw
        if match_line(sc.rounds) == '1/2-1/2':
            seg = [('a dead heat · match drawn', SLATE, False)]
            if aw == 0:
                seg.append((' — nobody died in three rounds', TDIM, False))
            else:
                seg.append((' · one win each', TDIM, False))
            return seg
        if match_line(sc.rounds) == '1-0':
            winner, hue = names['r'], EMBER
        else:
            winner, hue = names['b'], ICE
        seg = [(winner, hue, True), (' takes the match', TEXT, False),
               (f' · {aw}-{bw}', TDIM, False)]
        if tied:
            seg.append((f' · {tied} tied', TDIM, False))
        return seg
    # the knockout is declared DURING the elimination beat, not after
    if sc.elim is not None and sc.elim[1] is not None:
        loser = sc.elim[0]
        return [(f'round {sc.round_no} · ', TEXT, False),
                (player_name(1 - loser), HUES[1 - loser], True),
                (f' knocks out {player_name(loser)}', TEXT, False)]
    # battle
    if sc.verdict is not None:
        n, out, cycles = sc.verdict
        if out == 'tie':
            return [(f'round {n} · dead even — both survive {cycles:,} steps',
                     SLATE, False)]
        winner, loser = (names['r'], names['b']) if out == '1-0' \
            else (names['b'], names['r'])
        hue = EMBER if out == '1-0' else ICE
        return [(f'round {n} · ', TEXT, False), (winner, hue, True),
                (f' knocks out {loser} in {cycles:,} steps', TEXT, False)]
    total = len(sc.rounds)
    # disp_cycle keeps aging through the beats so the field cools — but the
    # footer holds at the round's own step count (a 1-step round must not
    # read "step 71" while the loser's territory finishes cooling).
    cap = None
    if 1 <= sc.round_no <= len(sc.rounds):
        cap = sc.rounds[sc.round_no - 1]['cycles']
    cyc = int(sc.disp_cycle if cap is None else min(sc.disp_cycle, cap))
    seg = [(f'round {sc.round_no} of {total} · step {cyc:,}', TEXT, False)]
    if cap is not None:
        seg.append((f' of {cap:,}', TDIM, False))
    return seg


def status_row_segments(sc, budget, fold_ledger=True):
    """The status row carries the phase voice plus, when the width is there,
    the latest ticker line — and, on panes with no room for a ledger row of
    its own, a compact ledger folded in behind it. Optional slots drop from
    the right: ticker first, then the ledger; the phase voice never drops,
    only clips."""
    segs = list(status_segments(sc))
    used = sum(display_width(tx) for tx, _c, _b in segs)
    extras = []
    if fold_ledger and sc.phase not in ('workshop', 'locked'):
        led = ledger_segments(sc, compact=True)
        if led:
            extras.append([('  ·  ', TDIM, False)] + led)
    if sc.events:
        extras.append([('  ·  ', TDIM, False),
                       (f'last: {sc.events[-1]}', TDIM, False)])
    for extra in extras:
        cost = sum(display_width(tx) for tx, _c, _b in extra)
        if used + cost <= budget:
            segs.extend(extra)
            used += cost
    return segs


def heatbar_segments(sc, width):
    """The strip's whole-core heat bar — the ring-map's material, promoted to
    the board when there is no room for a board. One char per bucket of the
    linear core: a majority needs an eighth of the bucket or the cell is
    unowned ░; owned buckets are █ in the majority hue, brightness scaled by
    the bucket's mean heat (a cooled army's buckets have gone ash). No window
    brackets — there is no camera left to locate."""
    width = max(1, width)
    runs, prev, buf = [], None, []
    for i in range(width):
        lo, hi = i * CORE_SIZE // width, (i + 1) * CORE_SIZE // width
        counts, hsum = [0, 0], [0.0, 0.0]
        for a in range(lo, hi):
            o = sc.owner[a]
            if o is None:
                continue
            counts[o] += 1
            age = sc.age[a]
            if 0 <= age <= sc.disp_cycle:
                hsum[o] += math.exp(-(sc.disp_cycle - age) / TAU)
        maj = 0 if counts[0] >= counts[1] else 1
        if counts[maj] < (hi - lo) / 8:
            ch, col = '░', AMBIENT
        else:
            # the bar obeys the same cold floor as the field: a bucket held
            # by a dead or banked army keeps that army's hue and only loses
            # brightness, so the bar never claims territory went neutral
            ch = '█'
            col = scale(HUES[maj], 0.55 + 0.45 * (hsum[maj] / counts[maj]))
            if maj in sc.cooled:
                col = scale(ground_colour(maj, 0.0), 1.35)
            if sc.embers:
                col = blend(col, scale(ground_colour(maj, 0.0), 1.35),
                            sc.embers)
        if col != prev and buf:
            runs.append((''.join(buf), prev, False))
            buf = []
        buf.append(ch)
        prev = col
    if buf:
        runs.append((''.join(buf), prev, False))
    return runs


def paint(segs, budget, extra=''):
    """Colour a segment list into one ANSI string inside a width budget: a
    straddling segment is clipped, never dropped, so the mandatory part of a
    row survives a narrow pane. Returns (string, used width)."""
    reserve = display_width(extra) if extra else 0
    out, used = '', 0
    for tx, c, b in segs:
        remaining = budget - used - reserve
        if remaining <= 0:
            break
        tx = clip_display(tx, remaining)
        if not tx:
            continue
        out += fg(c) + ('\x1b[1m' + tx + '\x1b[22m' if b else tx)
        used += display_width(tx)
    if extra:
        tx = clip_display(extra, budget - used)
        out += fg(TDIM) + tx
        used += display_width(tx)
    return out, used


def render(sc, t=None, status_extra=''):
    global _btn_bounds
    if t is None:
        t = time.monotonic()
    if not DRAW_FRAMES:
        # A scoring pass: the pacing loop and both hooks are the point, the
        # picture is not. Nothing above this line reads the terminal, so the
        # timeline comes out identical to a drawn run — which is the claim
        # this seam is making, and test_music_scoring_pass_keeps_the_timeline
        # is where it is held to it.
        if FRAME_HOOK is not None:
            FRAME_HOOK(None, sc, t)
        return
    refresh_names()
    cols, rows = shutil.get_terminal_size((87, 23))
    if cols < FLOOR_COLS or rows < FLOOR_ROWS:
        _btn_bounds = None
        # the refuse line is 21 cells and can refuse a 19-col pane: clip,
        # never wrap
        msg = clip_display(f' core war needs {FLOOR_COLS}x{FLOOR_ROWS} ',
                           cols)
        sys.stdout.write('\x1b[H' + bg(PANEL) + fg(TEXT) + msg
                         + '\x1b[K' + R + '\x1b[J')
        sys.stdout.flush()
        return
    fit_geometry(cols, rows)
    # Roll this frame's shake once so every draw shares the offset; decays
    # 0.80/frame from the elimination beat's kick. RNG here cannot break
    # byte-stability: the branch only runs while a shake is live.
    if SHAKE[0] >= 0.05 and not REDUCED_MOTION:
        SHK_OFF[0] = random.uniform(-SHAKE[0], SHAKE[0])
        SHK_OFF[1] = random.uniform(-SHAKE[0], SHAKE[0])
        SHAKE[0] *= 0.80
    else:
        SHAKE[0] = 0.0
        SHK_OFF[0] = SHK_OFF[1] = 0.0

    def line(s):
        return bg(PANEL) + s + bg(PANEL) + '\x1b[K' + R + '\n'

    out = ['\x1b[H\x1b[?25l']
    if TIER == 'strip':
        _btn_bounds = None     # no button at this tier — clear any stale
                               # bounds or an atlas→strip resize leaves an
                               # invisible click target on a tty
        pad = max(0, (rows - 3) // 2)
        for _ in range(pad):
            out.append(line(''))
        head, _u = paint(header_segments(sc, cols - 1), cols - 1)
        out.append(line(head))
        heat, _u = paint(heatbar_segments(sc, cols - 1), cols - 1)
        out.append(line(heat))
        status, _u = paint(status_segments(sc), cols - 1, status_extra)
        out.append(line(status))
        out.append(bg(PANEL) + '\x1b[J' + R)
        sys.stdout.write(''.join(out))
        sys.stdout.flush()
        if FRAME_HOOK is not None:
            FRAME_HOOK(None, sc, t)     # no Grid at this tier: there is no field
        return

    g = Grid(FIELD_W, FIELD_H)
    draw_field(g, sc, t)
    draw_fx(g, sc, t)
    draw_processes(g, sc, t)

    # Rows are BUDGETED, not appended and hoped for: the frame may never be
    # taller than the pane. A 24th row silently emitted into a 23-row pane
    # scrolls the whole board every frame, which is the exact-fill bug in a
    # different costume — so the row list is built, capped, and only then
    # emitted, and `body` is the one place rows come from.
    ledger = ledger_segments(sc) if sc.phase in ('battle', 'over') else []
    want_ledger = bool(ledger) and rows >= ATLAS_ROWS + 1
    frame = ATLAS_ROWS + (1 if want_ledger else 0)
    row_w = cols - CHROME_X - 1
    pad = max(0, min(2, (rows - frame) // 2))
    body = [''] * pad
    header, _u = paint(header_segments(sc, row_w), row_w)
    body.append(' ' * CHROME_X + header)
    for cy in range(FIELD_H):
        # the gutter marks 5-char-row intervals: one char row is 400
        # addresses, so these are landmarks, not coordinates — they say
        # "this is memory, and it runs top to bottom"
        lab = f'{cy * 4 * CORE_COLS:>4}' if cy % 5 == 0 else ' ' * GUTTER
        row = ' ' * BLOCK_X + fg(LABEL) + bg(PANEL) + lab + ' '
        pf = pb = None
        for cx in range(FIELD_W):
            col = g.f[cy][cx] or AMBIENT
            cbg = g.bg[cy][cx]
            if col != pf:
                row += fg(col)
                pf = col
            if cbg != pb:
                row += bg(cbg)
                pb = cbg
            row += chr(0x2800 + g.b[cy][cx])
        body.append(row + R + bg(PANEL))
    bars, _u = paint(bars_row_segments(sc, row_w), row_w)
    body.append(' ' * CHROME_X + bars + R + bg(PANEL))

    # The status row's tail: the replay button, RIGHT-ALIGNED. Right-aligned
    # because the status text changes width every frame (the step counter
    # grows), and a click target that slides under the cursor is a broken
    # button. It yields to the status — the verdict never clips for a
    # control.
    footer_button = INPUT_ENABLED and cols - CHROME_X >= 46
    btn = BTN_TEXT if footer_button else ''
    budget = max(1, row_w - (len(btn) + 2 if btn else 0))
    status, s_used = paint(
        status_row_segments(sc, budget, fold_ledger=not want_ledger),
        budget, status_extra)
    if btn and row_w - s_used - len(btn) < 2:
        btn = ''

    # The identity mark goes on whichever bottom row can seat it without
    # pushing anything else out — the ledger row first, since it is short by
    # nature, then the status row's own slack. It is the lowest-priority
    # thing in the frame: it appears when the pane can spare eight columns
    # and simply is not there when it cannot.
    led_used, led_txt = 0, ''
    if want_ledger:
        led_txt, led_used = paint(ledger, row_w)
    mark_row = None
    if want_ledger and row_w - led_used - len(MARK) >= 2:
        mark_row = 'ledger'
    elif row_w - s_used - len(btn) - (2 if btn else 0) - len(MARK) >= 2:
        mark_row = 'status'

    def right_align(prefix_used, prefix, tail):
        """One chrome row with `tail` pinned to the right margin. With no
        tail the row just ends — padding to the margin would emit trailing
        blanks the erase-to-end-of-line already covers."""
        fill = max(0, row_w - prefix_used - display_width(tail)) if tail else 0
        return ' ' * CHROME_X + prefix + ' ' * fill, CHROME_X + prefix_used + fill

    if want_ledger:
        if mark_row == 'ledger':
            lrow, _c = right_align(led_used, led_txt, MARK)
            lrow += fg(LABEL) + MARK
        else:
            lrow = ' ' * CHROME_X + led_txt
        body.append(lrow + R + bg(PANEL))

    tail = (MARK + '  ' if mark_row == 'status' else '') + btn
    srow, tail_col = right_align(s_used, status, tail)
    if mark_row == 'status':
        srow += fg(LABEL) + MARK + '  '
    if btn:
        _btn_bounds = (len(body) + 1, tail_col + len(tail) - len(btn) + 1,
                       tail_col + len(tail))
        srow += fg(SLATE) + btn
    else:
        _btn_bounds = None
    body.append(srow + R + bg(PANEL))
    # The banner is the room's pre-match caption and belongs to the phases
    # where it IS the content. During a battle, a verdict or the end of a
    # match the status row already says what happened, in this game's own
    # words — the referee's `<RED> 1/2-1/2 <BLUE> — battle` is a bus record
    # in chess's scoreline, and repeating it under the board taught the
    # audience nothing and spoke a language this game does not use.
    ban = read_cached(BANNER) if sc.phase in ('workshop', 'locked') else ''
    if ban and len(body) < rows:
        body.append(' ' * CHROME_X + fg(SLATE) + clip_display(ban, row_w))
    del body[rows:]                  # the invariant, enforced not assumed
    if _btn_bounds and _btn_bounds[0] > len(body):
        _btn_bounds = None           # the status row itself got capped away
    out.extend(line(s) for s in body)
    if out[-1].endswith('\n'):
        # Exact-fill panes (frame rows == pane rows): a trailing newline on
        # the last row scrolls the pane EVERY frame — the header walks off
        # the top and the whole board flickers (chat_tui.py's header comment
        # documented this; the clone missed it). Also shifted _btn_bounds off
        # the visible button, so replay clicks missed.
        out[-1] = out[-1][:-1]
    out.append(bg(PANEL) + '\x1b[J' + R)
    sys.stdout.write(''.join(out))
    sys.stdout.flush()
    if FRAME_HOOK is not None:
        FRAME_HOOK(g, sc, t)


FRAME_HOOK = None      # verification-harness seam: called with (grid, scene, t)
EVENT_HOOK = None      # its twin, for the offline recorder: see beat()


def fit_geometry(cols, rows):
    """Pick the tier the pane can hold. There is no pitch ladder and no
    viewport ladder: the field is the whole core at 50x20 chars, for ever.
    Either the atlas fits (55x23 — gutter + field, header + field + bars +
    status) or the strip does. The field block is centred; the chrome rows
    start further left and run wider than the block they describe, because
    the field can never spend those columns."""
    global TIER, BLOCK_X, CHROME_X
    TIER = 'atlas' if (cols >= BLOCK_W and rows >= ATLAS_ROWS) else 'strip'
    if TIER == 'atlas':
        BLOCK_X = (cols - BLOCK_W) // 2
        CHROME_X = BLOCK_X // 2
    else:
        BLOCK_X = CHROME_X = 0


fit_geometry(87, 23)      # establish the frame defaults at import


# ---- animation ------------------------------------------------------------
def _interrupt(interruptible):
    if not interruptible:
        return None
    action = poll_input()
    if action:
        return action
    if ctl_changed():
        return 'ctl'
    return None


def ctl_changed():
    try:
        return CTL.exists() and CTL.stat().st_mtime_ns > ctl_mtime
    except OSError:
        return False


def dwell(sc, seconds, interruptible, status_extra=''):
    """Render, then hold, polling for interrupt — xiangqi's replay-dwell
    pattern. Returns an action ('replay'/'quit'/'ctl') or None."""
    if REDUCED_MOTION:
        seconds = min(seconds, 0.15)
    render(sc, status_extra=status_extra)
    remaining = seconds
    while remaining > 0:
        pause = min(0.05, remaining)
        time.sleep(pause)
        remaining = max(0.0, remaining - pause)
        action = read_input()
        if action:
            return action
        if interruptible and ctl_changed():
            return 'ctl'
    return None


def load_in(sc, interruptible):
    """§1, the drop-pod load-in: warrior A scanline-writes itself into the
    calm empty core at its offset, one beat's dwell, then warrior B. Random
    placement taught without a word of chrome."""
    if REDUCED_MOTION:
        sc.loadin = None
        beat('load-in', 0, 0, time.monotonic(), span=0.0)
        beat('load-in', 0, 1, time.monotonic(), span=0.0)
        return dwell(sc, LOADIN_S * 0.2, interruptible)
    t0 = time.monotonic()
    write_s = LOADIN_S * 0.32
    gap_s = LOADIN_S * 0.12
    beat('load-in', 0, 0, t0, span=write_s)
    beat('load-in', 0, 1, t0 + write_s + gap_s, span=write_s)
    while True:
        t = time.monotonic()
        k = t - t0
        if k >= LOADIN_S:
            break
        action = _interrupt(interruptible)
        if action:
            sc.loadin = None
            return action
        pa = min(1.0, k / write_s)
        pb = min(1.0, max(0.0, (k - write_s - gap_s) / write_s))
        sc.loadin = (t0, (pa, pb))
        render(sc, t=t)
        time.sleep(FRAME_DT)
    sc.loadin = None
    return None


def _round_battle(sc, rnd):
    """Battle for one transcript round, or None when the transcript's offsets
    are semantically invalid (separation/overlap/range — Battle validates
    explicit offsets with ValueError). A hand-edited transcript must never
    crash the pane (the xiangqi clone guards its own equivalent with
    `except IllegalMove`; this is the same guard for the MARS loader)."""
    battle = Battle(sc.wa, sc.wb, seed=rnd['seed'])
    if battle.off_a == rnd['off_a'] and battle.off_b == rnd['off_b']:
        return battle
    try:
        trusted = Battle(sc.wa, sc.wb, seed=rnd['seed'],
                         off_a=rnd['off_a'], off_b=rnd['off_b'])
    except ValueError as e:
        sys.stderr.write(
            f"NOTE: round {rnd['n']} offsets {rnd['off_a']},{rnd['off_b']} "
            f"are not a legal placement ({e}) — skipping the round; "
            f"the referee's verify is the adjudicator.\n")
        return None
    sys.stderr.write(
        f"NOTE: round {rnd['n']} off={rnd['off_a']},{rnd['off_b']} is not "
        f"the engine's draw for its seed ({battle.off_a},{battle.off_b}) "
        f"— trusting the transcript's offsets.\n")
    return trusted


def animate_round(sc, rnd, interruptible=False):
    """Blocking broadcast of one transcript round, re-simulated live through
    the engine. Returns None (completed) or an abort action. On any abort the
    round is simply un-finished — sc.animated only advances on completion."""
    if sc.wa is None or sc.wb is None:
        return None
    battle = _round_battle(sc, rnd)
    if battle is None:
        sc.animated += 1      # skipped round still counts: never retry-loop
        return None
    reset_field(sc, battle)
    sc.phase = 'battle'
    sc.round_no = rnd['n']
    sc.verdict = None
    beat('round-cut', battle.off_a, 0, time.monotonic(), n=rnd['n'],
         off_b=battle.off_b, cycles=rnd['cycles'], out=rnd['out'])
    action = load_in(sc, interruptible)
    if action:
        return action
    cpf, slow_from = pacing(rnd['cycles'], rnd['out'])
    limit = rnd['cycles'] + 2
    frames_budget = max(1, int(FPS * ROUND_TARGET_S))
    frames_used = 0
    momentum = 0.0
    # Pace against a DEADLINE, not a fixed sleep: the frame's own work (the
    # engine steps plus the render) and the OS's sleep overshoot both come
    # out of the next sleep instead of stacking on top of the period. A
    # fixed sleep(FRAME_DT) measured ~56ms per frame on a 41.7ms period,
    # which is a fifth of the round's budget spent on arithmetic.
    deadline = time.monotonic()
    while not battle.over and battle.cycles < limit:
        action = _interrupt(interruptible)
        if action:
            return action
        if slow_from is not None and battle.cycles >= slow_from:
            n = 1
        else:
            n = momentum_rate(max(1, limit - battle.cycles),
                              frames_budget - frames_used, momentum)
            n = min(n, 4 * cpf)      # never jump-cut past a whole beat
        procs_before = len(battle.procs[0]) + len(battle.procs[1])
        sc.claims = 0
        target = battle.cycles + n
        start = battle.cycles
        now = time.monotonic()
        while not battle.over and battle.cycles < target:
            ev = battle.step()
            if ev is None:
                break
            apply_event(sc, ev, battle, now)
        sc.disp_cycle = float(battle.cycles)
        claim_procs(sc, battle)
        momentum = frame_momentum(sc.claims, battle.cycles - start,
                                  procs_before,
                                  len(battle.procs[0]) + len(battle.procs[1]))
        frames_used += 1
        render(sc)
        if REDUCED_MOTION:
            time.sleep(0.01)
            continue
        deadline += FRAME_DT
        rest = deadline - time.monotonic()
        if rest > 0:
            time.sleep(rest)
        else:
            deadline = time.monotonic()   # fell behind: don't spiral

    result = battle.result()
    if score_of(result) != rnd['out'] or result.cycles != rnd['cycles']:
        sys.stderr.write(
            f"NOTE: round {rnd['n']} re-simulates to {score_of(result)} "
            f"cycles={result.cycles}, but the transcript claims "
            f"{rnd['out']} cycles={rnd['cycles']} — ref_cw.py verify is the "
            f"adjudicator; the viewer shows the simulation.\n")
    sc.disp_cycle = float(battle.cycles)
    claim_procs(sc, battle)
    if rnd['out'] != 'tie':
        action = elimination_beat(sc, rnd, interruptible)
        if action:
            return action
    sc.verdict = (rnd['n'], rnd['out'], rnd['cycles'])
    beat('verdict', 0, 0 if rnd['out'] == '1-0' else 1,
         time.monotonic(), n=rnd['n'], out=rnd['out'], span=VERDICT_S)
    action = dwell(sc, VERDICT_S, interruptible)
    if action:
        return action
    sc.verdict = None
    sc.animated += 1
    return None


def elimination_beat(sc, rnd, interruptible):
    """§2, the flagship: over ELIM_S the loser's territory cools to ash, a
    front sweeping out from the killing address across the WHOLE core — the
    camera tier could never show the entire front. The distance is wrap-aware
    on both axes, because memory has no edges. Measure: a glance must say who
    died."""
    if sc.elim is None:
        return None
    loser, _t0, kill_addr, _d = sc.elim
    dists = {}
    kr, kc = divmod(kill_addr, CORE_COLS)
    for addr in range(CORE_SIZE):
        if sc.owner[addr] == loser:
            dr = abs(addr // CORE_COLS - kr)
            dc = abs(addr % CORE_COLS - kc)
            dists[addr] = math.hypot(min(dr, CORE_ROWS - dr),
                                     min(dc, CORE_COLS - dc))
    sc.elim[1] = time.monotonic()
    sc.elim[3] = dists
    t0 = sc.elim[1]
    # The hitstop is spent INSIDE the beat's ELIM_S window (the cooling loop
    # measures from t0), so the sweep an offline tool should follow is what
    # is left after the freeze — otherwise a soundtrack's decay outlives the
    # picture's by exactly the length of the freeze.
    stop = 0.0 if REDUCED_MOTION else HITSTOP_S
    beat('elimination', kill_addr, loser, t0,
         hitstop=stop, sweep=max(0.0, ELIM_S - stop))
    if not REDUCED_MOTION:
        # Hitstop, adapted from fighting games: the kill shot flashes in the
        # winner's hue, the frame freezes for a beat, the plate shakes loose
        # (decays per frame in render) — then the cooling front plays.
        sc.fx = []            # the kill owns the plate for its own beat
        push_fx(sc, 'kill', kill_addr, 1 - loser, t0)
        SHAKE[0] = 1.2
        render(sc, t=t0)
        time.sleep(HITSTOP_S)
    while True:
        t = time.monotonic()
        if REDUCED_MOTION or t - t0 >= ELIM_S:
            break
        action = _interrupt(interruptible)
        if action:
            return action
        sc.disp_cycle += IDLE_AGE
        render(sc, t=t)
        time.sleep(FRAME_DT)
    sc.cooled.add(loser)               # the loser's ground stays ash for good
    SHAKE[0] = 0.0                     # the shake always settles with the beat
    SHK_OFF[0] = SHK_OFF[1] = 0.0
    sc.elim = None
    return None


def end_wash(sc, interruptible=False):
    """After the last round. A decided match: the winner's hue washes the
    field and holds. A DRAWN match: both armies' territory cools to embers
    together, the whole battlefield going dark as one slow shared fade —
    a draw is "the floor held", not a failure state, so it is kept slow and
    dignified. Then the over state holds indefinitely. The phase flips first
    so the ending plays under the match-result status."""
    if not sc.rounds:
        return None
    drawn = match_line(sc.rounds) == '1/2-1/2'
    sc.phase = 'over'
    t0 = time.monotonic()
    sc.wash = ('draw' if drawn else (0 if match_line(sc.rounds) == '1-0'
                                     else 1), t0)
    hold = DRAW_FADE_S if drawn else WASH_S + 0.8
    beat('match-end', 0, 0 if sc.wash[0] == 'draw' else sc.wash[0], t0,
         drawn=drawn, span=hold)
    if REDUCED_MOTION:
        sc.embers = 1.0 if drawn else 0.0
        sc.washed = True
        return None
    while True:
        t = time.monotonic()
        k = t - t0
        if k >= hold:
            break
        action = _interrupt(interruptible)
        if action:
            return action
        if drawn:
            sc.embers = min(1.0, k / DRAW_FADE_S)
        sc.disp_cycle += IDLE_AGE
        render(sc, t=t)
        time.sleep(FRAME_DT)
    if drawn:
        sc.embers = 1.0
    sc.washed = True
    return None


def fast_forward(sc, rnd):
    """Re-simulate a round with no rendering — the snap path (§8.7) and the
    tail of a single-round replay. Shares the field model with animate_round,
    so the snapped state is the true end state, not a summary. Always
    advances sc.animated, even when the round cannot be simulated at all:
    snap_to_final's loop bound depends on it (a silent return spun the main
    loop at 100% CPU on the broken-warrior path)."""
    if sc.wa is None or sc.wb is None:
        sc.animated += 1
        return
    battle = _round_battle(sc, rnd)
    if battle is None:
        sc.animated += 1
        return
    reset_field(sc, battle)
    sc.phase = 'battle'
    sc.round_no = rnd['n']
    now = time.monotonic()
    while not battle.over:
        ev = battle.step()
        if ev is None:
            break
        apply_event(sc, ev, battle, now)
    sc.disp_cycle = float(battle.cycles)
    claim_procs(sc, battle)
    sc.elim = None
    sc.fx = []
    sc.animated += 1


def snap_to_final(sc):
    """>3 rounds arriving at once: jump straight to the live state (§8.7's
    snap-to-live, exactly the lesson the chess relay paid for)."""
    while sc.animated < len(sc.rounds):
        fast_forward(sc, sc.rounds[sc.animated])
    if sc.rounds:
        sc.wash = None
        end_wash(sc, interruptible=False)
    return sc


def do_replay(sc, n=None):
    """ctl `replay [n]` / the replay button: re-animate round n (1-based) or
    the whole match. A single-round replay restores the held end state
    afterwards (session memory, never a disk cache). Loops while the user
    keeps asking for replay, like xiangqi's do_replay."""
    while True:
        stop_music()               # a restart never plays over its own tail
        if not sc.rounds:
            render(sc, status_extra=' · nothing to replay yet')
            return sc, None
        saved = None
        if n is not None:
            if not (1 <= n <= len(sc.rounds)):
                return sc, None
            saved = sc.snapshot()
            # the ledger reveals only what the replay has legitimately
            # re-shown: rounds before n — never the held later outcomes
            sc.reveal = n - 1
            rounds = [sc.rounds[n - 1]]
        else:
            sc.animated = 0            # a full replay re-counts the rounds
            sc.embers = 0.0
            rounds = sc.rounds
        # The score's timeline starts at round 1, so only a full replay has
        # anything to start it against. Rendering happens HERE, before the
        # load-in: the track and the animation share one starting gun and are
        # never asked to find each other again.
        wav = score_replay(lambda m: render(sc, status_extra=f' · {m}')) \
            if (MUSIC[0] and n is None) else None
        action = None
        if wav is not None:
            play_wav(wav)
        for rnd in rounds:
            action = animate_round(sc, rnd, interruptible=True)
            if action:
                break
        if action is None and n is None and sc.rounds:
            action = end_wash(sc, interruptible=True)
        stop_music()
        if saved is not None and action != 'replay':
            sc.restore(saved)
            render(sc)
        if action == 'replay':
            # switching to a FULL replay: the held snapshot is dropped, so
            # the reveal cursor must drop with it — the full replay zeroes
            # animated, which then drives the ledger (a stale reveal would
            # show the held later outcomes over round 1: the spoiler the
            # cursor exists to kill)
            sc.reveal = None
            n = None
            continue
        return sc, action


def sync_transcript(sc):
    """(scene, next_round_or_None, snap) — the file-watch half of the loop.
    A truncated/rewritten transcript cold-rebuilds; >3 unanimated rounds
    snaps; warriors that won't read stall the battle phase honestly."""
    lines = transcript_lines()
    if lines[:len(sc.lines)] != sc.lines:
        return cold_start(), None, False
    loads, rounds, _err = parse_transcript(lines)
    sc.loads = loads
    sc.rounds = rounds
    if not loads:
        sc.phase = 'workshop'
        return sc, None, False
    if not rounds:
        sc.phase = 'locked'
        if sc.wa is None:
            sc.wa, sc.wb, sc.wname, _e = read_warriors()
        return sc, None, False
    if sc.animated >= len(rounds):
        return sc, None, False
    # Warrior readability is checked BEFORE the snap branch: a snap with
    # unreadable warriors can neither animate nor fast-forward — it idles
    # here (and notes once), never spins.
    if sc.wa is None or sc.wb is None:
        sc.wa, sc.wb, sc.wname, werr = read_warriors()
        if sc.wa is None:
            if not sc.warrior_note:
                sys.stderr.write(f'NOTE: {werr} — cannot animate; waiting.\n')
                sc.warrior_note = True
            return sc, None, False
        sc.warrior_note = False
    if len(rounds) - sc.animated > 3:
        return sc, None, True
    return sc, rounds[sc.animated], False


def main():
    global ctl_mtime
    sys.stdout.write('\x1b[2J')
    sc = cold_start()
    ctl_mtime = CTL.stat().st_mtime_ns if CTL.exists() else 0
    enable_input()
    try:
        _main_loop(sc)
    finally:
        disable_input()
        cleanup_music()


def _main_loop(sc):
    global ctl_mtime
    while True:
        if CTL.exists() and CTL.stat().st_mtime_ns > ctl_mtime:
            ctl_mtime = CTL.stat().st_mtime_ns
            cmd = read(CTL).split(None, 1)
            if cmd:
                if cmd[0] == 'replay':
                    n = None
                    if len(cmd) > 1 and cmd[1].strip().isdigit():
                        n = int(cmd[1].strip())
                    sc, action = do_replay(sc, n)
                    if action == 'quit':
                        return sc
                elif cmd[0] == 'reset':
                    sc = cold_start()
                elif cmd[0] == 'size':
                    # legacy verb: there is one field tier now, so any value
                    # is accepted and does nothing. Old scripts and old
                    # size.txt files must never be a crash.
                    pass
                elif cmd[0] == 'music':
                    arg = cmd[1].strip().lower() if len(cmd) > 1 else ''
                    on = set_music(not MUSIC[0] if arg in ('', 'toggle')
                                   else arg in ('1', 'on', 'true', 'yes'))
                    # The toggle is otherwise invisible until the next replay,
                    # and a control you cannot see the state of is a guess.
                    push_event(sc, 'soundtrack on — replay to hear it' if on
                               else 'soundtrack off')
                elif cmd[0] == 'banner':
                    BANNER.write_text(cmd[1] if len(cmd) > 1 else '')
                elif cmd[0] == 'names' and len(cmd) > 1:
                    parts = cmd[1].split()
                    if len(parts) == 2:
                        names['r'], names['b'] = parts[0].upper(), parts[1].upper()
                        (D / 'names.txt').write_text(f'{names["r"]} {names["b"]}')
        action = poll_input()
        if action == 'replay':
            sc, action2 = do_replay(sc, None)
            if action2 == 'quit':
                return sc
        elif action == 'quit':
            return sc
        sc, pending, snap = sync_transcript(sc)
        if snap:
            sc = snap_to_final(sc)
            continue
        if pending is not None:
            action = animate_round(sc, pending, interruptible=True)
            if action == 'quit':
                return sc
            if action == 'replay':
                sc, action2 = do_replay(sc, None)
                if action2 == 'quit':
                    return sc
            continue                    # 'ctl' or a finished round: re-sync
        if (sc.rounds and not sc.washed and sc.animated >= len(sc.rounds)
                and (RESULT.exists() or len(sc.rounds) >= ROUNDS_PER_MATCH)):
            action = end_wash(sc, interruptible=True)
            if action == 'quit':
                return sc
            if action == 'replay':
                sc, action2 = do_replay(sc, None)
                if action2 == 'quit':
                    return sc
            continue
        sc.disp_cycle += IDLE_AGE       # the held field visibly cools
        render(sc)
        time.sleep(0.05)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.stdout.write('\x1b[0m\x1b[?25h\n')
    except Exception as e:
        sys.stdout.write(f'\x1b[0m\x1b[?25h\nCOREWAR CRASH: {e}\n')
        raise

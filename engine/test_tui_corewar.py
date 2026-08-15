"""Tests for the Core War atlas TUI (tui_corewar.py).

Covers the atlas → strip → refuse ladder, transcript-driven cold start, the
full animated battle path (the §8.7 lesson: static renders don't exercise
animation — the suite drives a scripted battle through a bomb write, an SPL
spawn, a process death and an elimination), ctl verbs, the elimination death
wave, reduced motion, headless byte-stability, and the 2026-08-13 adversarial
review regression block (tampered/degraded-bus survival: bad offsets,
unreadable warriors, non-UTF-8 files, ctl startup swallow, subprocess
main-loop smoke).

The 2026-08-14 ATLAS block covers the gated encoding (occupancy dots,
majority owner, no fabricated third hue, contested SLATE never white, the
per-footprint crater rules), the promoted process marker (full near-white,
merged by block, uncapped), the seven animations (load-in, death wave, wrap
spark, tempo, drumbeat, sizzle, momentum pacing) and the drawn-match shared
ember fade.

Run with: uv run --with pytest pytest test_tui_corewar.py
(pure stdlib + pytest; scratch live dirs only via tmp_path + ARCADE_LIVE,
mirroring test_tui_xiangqi.py's discipline — production live dirs untouched.)
"""
import contextlib
import io
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

import corewar
import tui_corewar as X

ENGINE = Path(__file__).resolve().parent

IMP = corewar.IMP
DWARF = corewar.DWARF

# A warrior that dies on its first turn: A-side elimination at cycle 0.
DOOMED = """\
;redcode-94
;name Doomed
;author test
        org     start
start   dat     #0, #0
        end
"""

# A warrior that spawns a new process every trip through its loop.
SPLIER = """\
;redcode-94
;name Splinter
;author test
        org     start
start   spl     $0
        mov.i   $0, $1
        end
"""


def make_round(a_src, b_src, seed, n=1):
    """Derive a transcript round dict exactly the way the referee does."""
    wa, wb = corewar.parse_warrior(a_src), corewar.parse_warrior(b_src)
    battle = corewar.Battle(wa, wb, seed=seed)
    result = battle.run()
    return {'n': n, 'seed': seed, 'off_a': battle.off_a, 'off_b': battle.off_b,
            'out': X.score_of(result), 'cycles': result.cycles}


def make_scene(a_src=IMP, b_src=DWARF, rounds=()):
    sc = X.Scene()
    sc.wa, sc.wb = corewar.parse_warrior(a_src), corewar.parse_warrior(b_src)
    sc.rounds = list(rounds)
    return sc


def _animation_clock(monkeypatch):
    """Replace the module's wall clock with a manual one (test_tui_xiangqi's
    pattern): sleep() only advances fake time, so whole battles run fast."""
    class Clock:
        def __init__(self):
            self.now = 0.0
            self.sleeps = []

        def monotonic(self):
            return self.now

        def sleep(self, duration):
            self.sleeps.append(duration)
            self.now += duration

    clock = Clock()
    monkeypatch.setattr(X, 'time', clock)
    return clock


ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[ -/]*[@-~]')


def ledger_plain(sc, compact=False):
    """The ledger row as the string it reads as."""
    return ''.join(tx for tx, _c, _b in X.ledger_segments(sc, compact))


def block_of(g, addr):
    """(bits, fg, bg) of the braille char that holds a memory address — the
    atlas's positional mapping, read back."""
    row, col = divmod(addr, X.CORE_COLS)
    cx, cy = col // 2, row // 4
    return g.b[cy][cx], g.f[cy][cx], g.bg[cy][cx]


def run_probe(live, script):
    """Run `script` with tui_corewar imported as X and ARCADE_LIVE pointed at
    `live`, in a genuinely fresh process (cold-start bugs live at import)."""
    full = (
        f"import sys; sys.path.insert(0, {str(ENGINE)!r})\n"
        "import tui_corewar as X\n"
        f"{script}"
    )
    return subprocess.run(
        [sys.executable, "-c", full],
        cwd=live, env={**os.environ, "ARCADE_LIVE": str(live)},
        capture_output=True, text=True,
    )


def write_transcript(live, a_src, b_src, seeds):
    """A referee-shaped moves.txt: LOAD lines, then ROUND/OUT pairs."""
    lines = [
        f'LOAD A {corewar.sha256_warrior(a_src)}',
        f'LOAD B {corewar.sha256_warrior(b_src)}',
    ]
    rounds = []
    for i, seed in enumerate(seeds, 1):
        rnd = make_round(a_src, b_src, seed, n=i)
        rounds.append(rnd)
        lines.append(f"ROUND {i} seed={seed} off={rnd['off_a']},{rnd['off_b']}")
        lines.append(f"ROUND {i} OUT {rnd['out']} cycles={rnd['cycles']}")
    (live / 'moves.txt').write_text('\n'.join(lines) + '\n')
    (live / 'warriors').mkdir(exist_ok=True)
    (live / 'warriors' / 'A.red').write_text(a_src)
    (live / 'warriors' / 'B.red').write_text(b_src)
    return rounds


# ---------------------------------------------------------------------------
# pacing + geometry
# ---------------------------------------------------------------------------

def test_pacing_full_tie_round_lands_inside_the_90s_budget():
    cpf, slow_from = X.pacing(80000, 'tie')
    assert slow_from is None                    # no kill to dramatise
    assert 80000 / (cpf * X.FPS) <= 90.0
    assert 80000 / (cpf * X.FPS) >= 40.0        # and not needlessly rushed


def test_pacing_kills_get_a_slow_tail():
    cpf, slow_from = X.pacing(5000, '0-1')
    assert cpf >= 1
    assert slow_from == 5000 - X.SLOW_TAIL      # last cycles at 1 cycle/frame
    cpf, slow_from = X.pacing(120, '1-0')
    assert cpf == 1
    assert slow_from == 0                       # the whole short round is slow


def test_momentum_rate_is_budget_correcting():
    """§7: the baseline is always cycles-left over frames-left, so a frame
    spent crawling is repaid by the frames after it. Momentum only slides the
    rate around that baseline — it can never blow the budget."""
    rest = X.momentum_rate(80000, 1320, 0.0)
    hot = X.momentum_rate(80000, 1320, 1.0)
    assert hot < rest                           # a moving front slows down
    assert rest == round(80000 / 1320 * X.MOMENTUM_FAST)
    assert hot == round(80000 / 1320 * X.MOMENTUM_SLOW)
    # falling behind raises the baseline: same cycles, fewer frames left
    assert X.momentum_rate(80000, 200, 1.0) > X.momentum_rate(80000, 1320, 1.0)
    assert X.momentum_rate(3, 1320, 1.0) >= 1   # never stalls at zero


def test_frame_momentum_reads_the_battle_not_the_clock():
    quiet = X.frame_momentum(claims=0, cycles=60, procs_before=4,
                             procs_after=4)
    front = X.frame_momentum(claims=60, cycles=60, procs_before=4,
                             procs_after=4)
    fork = X.frame_momentum(claims=0, cycles=60, procs_before=4,
                            procs_after=40)
    assert quiet == 0.0
    assert front > quiet and fork > quiet
    assert X.frame_momentum(10, 0, 1, 1) == 0.0     # no cycles: no reading


def _tier_for(cols, rows):
    X.fit_geometry(cols, rows)
    return X.TIER, X.BLOCK_X, X.CHROME_X


def test_geometry_atlas_is_the_only_field_tier():
    """The field is the whole core at 50x20 chars, for ever. Either the atlas
    fits its own geometry (55x23) or the strip takes over — there is no
    camera to shrink into and no grand tier to grow into."""
    assert _tier_for(87, 23)[0] == 'atlas'
    assert X.BLOCK_X == (87 - X.BLOCK_W) // 2    # the block is centred
    assert X.CHROME_X < X.BLOCK_X                # chrome runs wider than it
    assert _tier_for(55, 23)[0] == 'atlas'       # exactly its own floor
    assert X.BLOCK_X == 0 and X.CHROME_X == 0
    assert _tier_for(54, 23)[0] == 'strip'       # one column short
    assert _tier_for(55, 22)[0] == 'strip'       # one row short
    assert _tier_for(300, 90)[0] == 'atlas'      # surplus is pure margin
    assert X.BLOCK_X == (300 - X.BLOCK_W) // 2


def test_geometry_the_field_never_changes_size():
    for cols, rows in ((55, 23), (87, 23), (200, 60)):
        X.fit_geometry(cols, rows)
        assert (X.FIELD_W, X.FIELD_H) == (50, 20)
        assert X.FIELD_W * 2 * X.FIELD_H * 4 == corewar.CORE_SIZE


def test_geometry_strip_floor_and_refuse(monkeypatch):
    assert _tier_for(20, 4)[0] == 'strip'
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((20, 4)))
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        X.render(X.Scene(), t=1.0)
    assert ' core war needs ' not in ANSI_RE.sub('', out.getvalue())
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((19, 4)))
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        X.render(X.Scene(), t=1.0)
    assert ' core war needs ' in ANSI_RE.sub('', out.getvalue())


# ---------------------------------------------------------------------------
# transcript parsing + cold start
# ---------------------------------------------------------------------------

def test_parse_transcript_round_trip_and_malformed():
    lines = ['LOAD A ' + 'a' * 64, 'LOAD B ' + 'b' * 64,
             'ROUND 1 seed=7 off=100,200', 'ROUND 1 OUT 1-0 cycles=395']
    loads, rounds, err = X.parse_transcript(lines)
    assert err is None
    assert loads == {'A': 'a' * 64, 'B': 'b' * 64}
    assert rounds == [{'n': 1, 'seed': 7, 'off_a': 100, 'off_b': 200,
                       'out': '1-0', 'cycles': 395}]
    _l, _r, err = X.parse_transcript(['ROUND 1 seed=7 off=1,2'])
    assert err is not None                      # unpaired ROUND line
    _l, rounds, err = X.parse_transcript(lines[:3] + ['garbage', 'lines'])
    assert err is not None                      # stops parsing, keeps nothing bad
    assert rounds == []


def test_cold_start_workshop_on_an_empty_room(tmp_path):
    r = run_probe(tmp_path, "sc = X.cold_start()\nprint(sc.phase)\n")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == 'workshop'


def test_cold_start_rebuilds_battle_from_transcript(tmp_path):
    """The cold-start contract: a fresh process against a finished room
    re-simulates from the transcript + locked warriors, never a cache."""
    write_transcript(tmp_path, IMP, DWARF, [7, 11, 23])
    (tmp_path / 'result.txt').write_text('QWEN wins by battle\n')
    script = (
        "import io, contextlib\n"
        "sc = X.cold_start()\n"
        "print(sc.phase, len(sc.rounds), sc.animated)\n"
        "with contextlib.redirect_stdout(io.StringIO()):\n"
        "    sc = X.snap_to_final(sc)\n"
        "print(sc.phase, sc.animated, sc.washed)\n"
        "print(sum(1 for o in sc.owner if o == 0), "
        "sum(1 for o in sc.owner if o == 1))\n"
        "print(sc.round_no)\n"
    )
    r = run_probe(tmp_path, script)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert lines[0] == 'battle 3 0'
    assert lines[1] == 'over 3 True'
    a_owned, b_owned = (int(v) for v in lines[2].split())
    assert a_owned > 0 and b_owned > 0          # both signatures on the field
    assert lines[3] == '3'


def test_old_size_txt_is_inert_never_a_crash(tmp_path):
    """The size ladder died with the camera. A live dir carrying a stale
    size.txt (or a ctl `size grand` from an old script) must be a no-op, not
    a crash — never break a room that outlived the redesign."""
    (tmp_path / 'size.txt').write_text('grand')
    script = (
        "import io, contextlib, os\n"
        "X.shutil.get_terminal_size = lambda fb: os.terminal_size((87, 23))\n"
        "X.INPUT_ENABLED = False\n"
        "sc = X.cold_start()\n"
        "with contextlib.redirect_stdout(io.StringIO()):\n"
        "    X.render(sc, t=1.0)\n"
        "print('tier:', X.TIER)\n"
        "print('size attr:', hasattr(X, 'SIZE'))\n"
    )
    r = run_probe(tmp_path, script)
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines() == ['tier: atlas', 'size attr: False']


def test_snap_to_final_matches_a_headless_simulation(tmp_path):
    """The snap path must land on the true end state: owner maps equal to a
    plain engine run with the same tracking rule."""
    rnd = make_round(IMP, DWARF, 21, n=1)
    sc = make_scene(rounds=[rnd])
    X.fast_forward(sc, rnd)
    # headless reference: same claim rule as apply_event
    wa, wb = corewar.parse_warrior(IMP), corewar.parse_warrior(DWARF)
    battle = corewar.Battle(wa, wb, seed=21)
    owner = [None] * 8000
    while not battle.over:
        ev = battle.step()
        owner[ev.pc] = ev.warrior
        for addr in ev.writes:
            owner[addr] = ev.warrior
    assert sc.owner == owner
    assert int(sc.disp_cycle) == battle.cycles
    assert sc.procs == (list(battle.procs[0]), list(battle.procs[1]))


# ---------------------------------------------------------------------------
# the animated battle (§8.7: static renders don't exercise animation)
# ---------------------------------------------------------------------------

def test_full_animated_battle_with_kill_beats_and_markers(monkeypatch):
    """Drive a complete imp-vs-dwarf kill round through animate_round with a
    manual clock: bomb craters must form, the death wave must cool the loser
    for good, the verdict must show, and process markers must render full."""
    monkeypatch.setattr(X, 'REDUCED_MOTION', False)
    _animation_clock(monkeypatch)
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((60, 30)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    rnd = make_round(IMP, DWARF, 7, n=1)        # dwarf kills the imp, cycle 395
    assert rnd['out'] == '0-1'
    sc = make_scene(rounds=[rnd])
    frames = []
    monkeypatch.setattr(X, 'FRAME_HOOK',
                        lambda g, scene, t: frames.append((g, scene, t)))
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        action = X.animate_round(sc, rnd)
    assert action is None
    assert sc.animated == 1
    assert len(frames) > 20                     # a real animation, not a cut
    assert any(sc.bomb)                         # dwarf's craters formed
    assert sc.cooled == {0}                     # the imp (warrior A) cooled for good
    assert out.getvalue()                       # frames were emitted
    # the winner's surviving queue renders as FULL 8-dot marker blocks
    g, _sc, _t = frames[-1]
    assert any(bits == X.FULL for row in g.b for bits in row)
    # heat advanced with battle time (and kept aging through the beats)
    assert int(sc.disp_cycle) >= rnd['cycles']


def test_spl_spawn_and_process_death_spawn_plate_fx(monkeypatch):
    """SPLIER spawns a process on its first trip; DOOMED dies on its. One
    round exercises both event beats at cycle zero. Every effect lives in the
    plate: a dot answers WHO, so an FX that lit one would fabricate
    occupancy (the argument that killed the comet moat at this grain)."""
    monkeypatch.setattr(X, 'REDUCED_MOTION', False)
    _animation_clock(monkeypatch)
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((60, 30)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    rnd = make_round(SPLIER, DOOMED, 3, n=1)
    assert rnd['out'] == '1-0' and rnd['cycles'] <= 1   # B dies on turn one
    sc = make_scene(SPLIER, DOOMED, rounds=[rnd])
    kinds = set()
    monkeypatch.setattr(X, 'FRAME_HOOK',
                        lambda g, scene, t: kinds.update(
                            f[0] for f in scene.fx))
    with contextlib.redirect_stdout(io.StringIO()):
        action = X.animate_round(sc, rnd)
    assert action is None
    assert 'spl' in kinds                       # the birth bloom appeared
    assert 'death' in kinds                     # so did the death bloom
    assert sc.cooled == {1}


def test_reduced_motion_suppresses_beats(monkeypatch):
    monkeypatch.setattr(X, 'REDUCED_MOTION', True)
    clock = _animation_clock(monkeypatch)
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((60, 30)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    rnd = make_round(SPLIER, DOOMED, 3, n=1)
    sc = make_scene(SPLIER, DOOMED, rounds=[rnd])
    with contextlib.redirect_stdout(io.StringIO()):
        action = X.animate_round(sc, rnd)
    assert action is None
    assert sc.fx == []                          # no plate effects at all
    assert sc.loadin is None                    # the load-in cut straight in
    assert sc.cooled == {1}                     # the cooling still lands
    assert max(clock.sleeps) <= 0.05            # no long beat dwells


def test_replay_interrupt_by_ctl_and_by_input(monkeypatch):
    _animation_clock(monkeypatch)
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((60, 30)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    rnd = make_round(IMP, DWARF, 7, n=1)
    sc = make_scene(rounds=[rnd])
    monkeypatch.setattr(X, 'ctl_changed', lambda: True)
    with contextlib.redirect_stdout(io.StringIO()):
        action = X.animate_round(sc, rnd, interruptible=True)
    assert action == 'ctl'
    assert sc.animated == 0                     # an aborted round doesn't count
    monkeypatch.setattr(X, 'ctl_changed', lambda: False)
    monkeypatch.setattr(X, 'poll_input', lambda: 'replay')
    with contextlib.redirect_stdout(io.StringIO()):
        action = X.animate_round(sc, rnd, interruptible=True)
    assert action == 'replay'
    assert sc.animated == 0


def test_single_round_replay_restores_the_held_end_state(monkeypatch):
    _animation_clock(monkeypatch)
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((60, 30)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    rounds = [make_round(IMP, DWARF, 7, n=1),
              make_round(IMP, DWARF, 21, n=2)]
    sc = make_scene(rounds=rounds)
    monkeypatch.setattr(X, 'ctl_changed', lambda: False)   # hermetic: never
                                                           # read the live dir
    with contextlib.redirect_stdout(io.StringIO()):
        for rnd in rounds:
            assert X.animate_round(sc, rnd) is None
    held_owner = sc.owner[:]
    held_animated = sc.animated
    with contextlib.redirect_stdout(io.StringIO()):
        sc, action = X.do_replay(sc, 1)         # replay round 1 only
    assert action is None
    assert sc.owner == held_owner               # held state restored
    assert sc.animated == held_animated
    assert sc.round_no == 2


# ---------------------------------------------------------------------------
# ctl verbs + names/banner propagation
# ---------------------------------------------------------------------------

def test_ctl_verbs_apply_in_main_loop(tmp_path, monkeypatch):
    monkeypatch.setattr(X, 'D', tmp_path)
    monkeypatch.setattr(X, 'CTL', tmp_path / 'ctl')
    monkeypatch.setattr(X, 'BANNER', tmp_path / 'banner.txt')
    monkeypatch.setattr(X, 'MOVES', tmp_path / 'moves.txt')
    monkeypatch.setattr(X, 'NAMES', tmp_path / 'names.txt')
    monkeypatch.setattr(X, 'RESULT', tmp_path / 'result.txt')
    monkeypatch.setattr(X, 'WARRIORS', tmp_path / 'warriors')
    monkeypatch.setattr(X, 'poll_input', lambda: 'quit')
    monkeypatch.setattr(X, 'ctl_mtime', 0)
    X.CTL.write_text('size grand')              # legacy verb: accepted, inert
    X._main_loop(X.Scene())
    assert not (tmp_path / 'size.txt').exists()

    monkeypatch.setattr(X, 'ctl_mtime', 0)
    X.CTL.write_text('banner ROUND TABLE · exhibition')
    X._main_loop(X.Scene())
    assert X.BANNER.read_text() == 'ROUND TABLE · exhibition'

    monkeypatch.setattr(X, 'ctl_mtime', 0)
    X.CTL.write_text('names ernie qwen')
    X._main_loop(X.Scene())
    assert (tmp_path / 'names.txt').read_text() == 'ERNIE QWEN'
    assert X.names == {'r': 'ERNIE', 'b': 'QWEN'}


def test_refresh_names_keeps_last_known_good(tmp_path, monkeypatch):
    names_file = tmp_path / 'names.txt'
    monkeypatch.setattr(X, 'NAMES', names_file)
    X._fcache.clear()
    monkeypatch.setitem(X.names, 'r', 'AAA')
    monkeypatch.setitem(X.names, 'b', 'BBB')
    X.refresh_names()                           # missing file: no change
    assert X.names == {'r': 'AAA', 'b': 'BBB'}
    names_file.write_text('ONLYONE\n')
    X._fcache.clear()
    X.refresh_names()                           # malformed: no change
    assert X.names == {'r': 'AAA', 'b': 'BBB'}
    names_file.write_text('ERNIE QWEN\n')
    X._fcache.clear()
    X.refresh_names()
    assert X.names == {'r': 'ERNIE', 'b': 'QWEN'}


# ---------------------------------------------------------------------------
# rendering discipline
# ---------------------------------------------------------------------------

def _mid_battle_scene():
    """The gate frame: imp vs dwarf, seed 1, at cycle 1000."""
    sc = make_scene()
    battle = corewar.Battle(sc.wa, sc.wb, seed=1)
    X.reset_field(sc, battle)
    sc.phase = 'battle'
    sc.round_no = 1
    sc.rounds = [{'n': 1, 'seed': 1, 'off_a': battle.off_a,
                  'off_b': battle.off_b, 'out': 'tie', 'cycles': 80000}]
    while battle.cycles < 1000:
        ev = battle.step()
        X.apply_event(sc, ev, battle, 0.0)
    sc.disp_cycle = 1000.0
    X.claim_procs(sc, battle)
    return sc


def _field(sc, t=10.0, cols=87, rows=23, monkeypatch=None):
    """Render once and hand back the Grid the frame drew."""
    grids = []
    hook = X.FRAME_HOOK
    X.FRAME_HOOK = lambda g, scene, tt: grids.append(g)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            X.render(sc, t=t)
    finally:
        X.FRAME_HOOK = hook
    return grids[-1]


def test_headless_render_is_byte_stable_and_buttonless(monkeypatch, tmp_path):
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    # bus paths are import-time bound; never let render read the real live dir
    monkeypatch.setattr(X, 'NAMES', tmp_path / 'names.txt')
    monkeypatch.setattr(X, 'BANNER', tmp_path / 'banner.txt')
    sc = _mid_battle_scene()
    buf1, buf2 = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf1):
        X.render(sc, t=10.0)
    with contextlib.redirect_stdout(buf2):
        X.render(sc, t=10.0)
    assert buf1.getvalue() == buf2.getvalue()
    assert X.BTN_TEXT not in ANSI_RE.sub('', buf1.getvalue())
    assert X._btn_bounds is None


def test_atlas_frame_furniture_never_wraps(monkeypatch, tmp_path):
    """The gated frame: header / 20 field rows / bars / status, the whole
    core on show, the address gutter marking 5-row landmarks."""
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'NAMES', tmp_path / 'names.txt')
    monkeypatch.setattr(X, 'BANNER', tmp_path / 'banner.txt')
    monkeypatch.setitem(X.names, 'r', 'ERNIE')
    monkeypatch.setitem(X.names, 'b', 'QWEN')
    sc = _mid_battle_scene()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        X.render(sc, t=10.0)
    plain = ANSI_RE.sub('', out.getvalue())
    lines = plain.splitlines()
    assert len(lines) == X.ATLAS_ROWS == 23
    for line in lines:
        assert len(line) <= 87                  # never wraps
    assert 'ERNIE' in lines[0] and 'QWEN' in lines[0]
    assert 'all 8,000 cells of memory, one dot each' in lines[0]
    for cy, label in ((0, '   0'), (5, '2000'), (10, '4000'), (15, '6000')):
        assert lines[1 + cy][X.BLOCK_X:X.BLOCK_X + X.GUTTER] == label
        # 50 braille chars, the whole core, on every field row
        assert sum(1 for ch in lines[1 + cy] if 0x2800 <= ord(ch) <= 0x28FF) \
            == X.FIELD_W
    assert 'held' in lines[21] and 'running' in lines[21]
    assert 'round 1 of 1 · step 1,000 of 80,000' in lines[22]


def test_exact_fill_pane_does_not_scroll(monkeypatch, tmp_path):
    """Frame rows == pane rows: the last content row must NOT end with '\\n' —
    a trailing newline scrolls the pane every frame (the board visibly
    flickers and the header, with the player names, walks off the top).
    Reported live on the match-002 wall."""
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'NAMES', tmp_path / 'names.txt')
    monkeypatch.setattr(X, 'BANNER', tmp_path / 'banner.txt')
    sc = _mid_battle_scene()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        X.render(sc, t=10.0)
    assert out.getvalue().count('\n') == X.ATLAS_ROWS - 1   # interior only


def test_strip_tier_renders_header_heatbar_status(monkeypatch, tmp_path):
    """Below the atlas floor the battle stays visible: the whole-core heat
    bar replaces the field, so even a 20x4 pane shows a living bar."""
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((40, 4)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'NAMES', tmp_path / 'names.txt')
    monkeypatch.setattr(X, 'BANNER', tmp_path / 'banner.txt')
    sc = _mid_battle_scene()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        X.render(sc, t=1.0)
    plain = ANSI_RE.sub('', out.getvalue())
    lines = [l for l in plain.splitlines() if l.strip()]
    assert X.TIER == 'strip'
    assert 'vs' in lines[0]
    assert '█' in lines[1] or '░' in lines[1]    # the live heat bar
    assert 'round 1' in lines[2]
    assert max(len(l) for l in plain.splitlines()) <= 40
    sc2 = X.Scene()                              # workshop phase
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        X.render(sc2, t=1.0)
    assert 'waiting for two programs' in ANSI_RE.sub('', out.getvalue())


def test_heatbar_majority_unowned_and_cooled(monkeypatch):
    """The ring-map material, promoted: majority hue at mean-heat brightness,
    an eighth of the bucket or it stays unowned — and no window brackets,
    because there is no camera left to locate."""
    sc = make_scene()
    for a in range(500):
        sc.owner[a] = 0
        sc.age[a] = 0
    sc.disp_cycle = 1.0
    runs = X.heatbar_segments(sc, 56)
    text = ''.join(t for t, _c, _b in runs)
    assert len(text) == 56
    assert '[' not in text and ']' not in text
    assert '█' in text[:4]                       # the ember-held buckets
    assert '░' in text                           # the unowned core
    hue = next(c for t, c, _b in runs if '█' in t)
    assert hue not in (X.AMBIENT, X.ASH)         # majority hue, heat-scaled
    sc.cooled.add(0)
    dead = next(c for t, c, _b in X.heatbar_segments(sc, 56) if '█' in t)
    # a dead army's buckets dim but keep their hue: the bar obeys the same
    # cold floor as the field and never claims territory went neutral
    assert sum(dead) < sum(hue)
    assert dead[0] > dead[2]                     # still unmistakably ember


def test_match_line_scoring():
    rounds = lambda *outs: [{'out': o} for o in outs]
    assert X.match_line(rounds('1-0', '1-0', '0-1')) == '1-0'
    assert X.match_line(rounds('tie', 'tie', '0-1')) == '0-1'
    assert X.match_line(rounds('tie', 'tie', 'tie')) == '1/2-1/2'
    assert X.match_line(rounds('1-0', '0-1', 'tie')) == '1/2-1/2'


# ---------------------------------------------------------------------------
# the atlas encoding (gated 2026-08-14, design/corewar-mockups/atlas/)
# ---------------------------------------------------------------------------

def _encoding_scene():
    sc = X.Scene()
    sc.disp_cycle = 1000.0
    return sc


def test_dots_are_occupancy_and_the_mapping_is_positional(monkeypatch):
    """Dot (dx, dy) of char (cx, cy) IS memory cell (4*cy+dy)*100 + 2*cx+dx.
    Nothing is resampled, and a lit dot means exactly "this cell is owned"."""
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'REDUCED_MOTION', True)
    sc = _encoding_scene()
    for cy, cx, dx, dy in ((3, 7, 0, 0), (11, 40, 1, 3), (19, 49, 1, 2)):
        addr = (4 * cy + dy) * X.CORE_COLS + 2 * cx + dx
        sc.owner[addr] = 0
        sc.age[addr] = 990
    g = _field(sc)
    for cy, cx, dx, dy in ((3, 7, 0, 0), (11, 40, 1, 3), (19, 49, 1, 2)):
        assert g.b[cy][cx] == X.BITS[dx][dy]     # exactly that one dot, no more
    # untouched memory shows no dots at all: an ambient stipple would read as
    # occupancy, which is the one thing a dot must never do falsely
    assert g.b[0][0] == 0


def test_a_bomb_is_a_write_so_territory_never_disappears(monkeypatch):
    """`dots = clearing` was rendered side by side at the gate and rejected:
    it erased the most legible structure on the board. A crater keeps its
    dot in its bomber's colour; the damage lives entirely in the plate."""
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'REDUCED_MOTION', True)
    sc = _encoding_scene()
    plain = 400                                  # a plain owned run
    for addr in range(plain, plain + 8):
        sc.owner[addr] = 1
        sc.age[addr] = 200
    for cx in range(4):                          # fill one whole char block
        for dy in range(4):
            for dx in (0, 1):
                a = (4 * 1 + dy) * X.CORE_COLS + 2 * 3 + dx
                sc.owner[a], sc.age[a], sc.bomb[a] = 0, 200, True
    g = _field(sc)
    bits, back = g.b[1][3], g.bg[1][3]
    assert bits == X.FULL                        # every cratered cell still lit
    assert sum(back) < sum(X.SQD)                # the plate is a pit instead


def test_no_third_hue_is_ever_fabricated(monkeypatch):
    """The honest objection to 8 cells per char: averaging EMBER and ICE
    invents a muddy hue exactly at contested borders. The answer is that the
    char's fg is the MAJORITY owner's own ramp colour, never a blend."""
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'REDUCED_MOTION', True)
    sc = _encoding_scene()
    base = 4 * X.CORE_COLS + 2 * 10              # char (10, 1)
    for i, (dx, dy) in enumerate([(0, 0), (1, 0), (0, 1), (1, 1),
                                  (0, 2), (1, 2), (0, 3), (1, 3)]):
        a = base + dy * X.CORE_COLS + dx
        sc.owner[a] = 0 if i < 5 else 1          # 5 ember vs 3 ice
        sc.age[a] = 995
    g = _field(sc)
    col = g.f[1][10]
    # the fg sits on the ember ramp — its red channel dominates, exactly as a
    # pure ember cell would; an average with ICE would lift blue over red
    assert col[0] > col[2]
    assert g.bg[1][10] != X.SQD                  # but the plate says contested


def test_contested_plate_lifts_toward_slate_never_white(monkeypatch):
    """§6 as amended at the gate: near-white is the process marker's
    exclusive colour and fronts are exactly where processes live, so a
    contested block sizzles in SLATE — a neutral grey off both faction ramps,
    so nothing is averaged — with the dots brightening in the owner's OWN
    hue. The measure is the disputed FOOTPRINT, heat-gated."""
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'REDUCED_MOTION', True)

    def block(sc, cx, cy, split, age):
        base = 4 * cy * X.CORE_COLS + 2 * cx
        for i, (dx, dy) in enumerate([(0, 0), (1, 0), (0, 1), (1, 1),
                                      (0, 2), (1, 2), (0, 3), (1, 3)]):
            a = base + dy * X.CORE_COLS + dx
            if i >= sum(split):
                continue
            sc.owner[a] = 0 if i < split[0] else 1
            sc.age[a] = age

    sc = _encoding_scene()
    block(sc, 2, 1, (4, 4), 995)     # 4-vs-4, hot: a real front
    block(sc, 6, 1, (1, 1), 995)     # 1-vs-1, hot: barely disputed
    block(sc, 10, 1, (4, 4), 0)      # 4-vs-4, ancient: a settled line
    block(sc, 14, 1, (8, 0), 995)    # uncontested
    g = _field(sc)
    front, thin, settled, calm = (g.bg[1][2], g.bg[1][6], g.bg[1][10],
                                  g.bg[1][14])
    assert sum(front) > sum(thin) > sum(settled)   # footprint AND heat gated
    # an old overlap is a settled line, not a fight: the lift is gone
    assert max(abs(a - b) for a, b in zip(settled, calm)) <= 3
    assert front != X.W_SOLID and max(front) < max(X.W_SOLID)
    # the lift is toward SLATE, which is off both faction ramps: the channel
    # differences stay small, unlike either hue
    assert max(front) - min(front) < 40


def test_crater_glow_carries_the_cratered_footprint(monkeypatch):
    """The inherited 0.45h² rule was written for ONE memory cell; at atlas
    grain the freshest cell in a block was lighting all 8 cells' worth of
    plate, so a single bomb painted a bright card. One hit is a whisper now;
    only a carpeted block burns."""
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'REDUCED_MOTION', True)
    sc = _encoding_scene()
    for cx, npit in ((4, 1), (8, 8)):
        base = 4 * X.CORE_COLS + 2 * cx
        for i, (dx, dy) in enumerate([(0, 0), (1, 0), (0, 1), (1, 1),
                                      (0, 2), (1, 2), (0, 3), (1, 3)]):
            a = base + dy * X.CORE_COLS + dx
            sc.owner[a], sc.age[a] = 1, 1000
            sc.bomb[a] = i < npit
    g = _field(sc)
    one, carpet = g.bg[1][4], g.bg[1][8]
    assert one[2] < carpet[2]                    # the glow scales with pits
    assert abs(one[2] - X.SQD[2]) < 12           # one hit is a whisper


def test_cold_ground_decays_to_a_whisper_of_hue(monkeypatch):
    """The director's late-loudness correction: a fully-owned late core must
    not shout. Cold territory sinks toward the ambient grey while a hot front
    burns at the full hue, so the two live fronts own a saturated frame."""
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'REDUCED_MOTION', True)
    sc = _encoding_scene()
    for cx, age in ((3, 1000), (9, 0)):
        base = 4 * X.CORE_COLS + 2 * cx
        for dy in range(4):
            for dx in (0, 1):
                a = base + dy * X.CORE_COLS + dx
                sc.owner[a], sc.age[a] = 0, age
    g = _field(sc)
    hot, cold = g.f[1][3], g.f[1][9]
    assert sum(hot) > 2.5 * sum(cold)            # the front dominates
    assert max(cold) - min(cold) < max(hot) - min(hot)   # and desaturates


def test_process_marker_is_full_near_white_merged_and_uncapped(monkeypatch):
    """A PC is one dot among 8000, i.e. invisible, so the marker is promoted
    to the whole char: FULL near-white, the board's brightest object and its
    one admitted lie. Co-located PCs merge by block — which is the natural
    bound — so there is no MAX_COMETS ceiling: a SPL flood lighting a region
    white is a legitimate read ("their code is everywhere")."""
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'REDUCED_MOTION', True)
    sc = _encoding_scene()
    # 200 processes: 8 co-located in one block, the rest spread over 192 blocks
    merged = [4 * X.CORE_COLS + dy * X.CORE_COLS + dx
              for dy in range(4) for dx in (0, 1)]
    spread = [(4 * cy) * X.CORE_COLS + 2 * cx
              for cy in range(2, 14) for cx in range(16)]
    sc.procs = (merged, spread)
    g = _field(sc)
    bits, col = g.b[1][0], g.f[1][0]
    assert bits == X.FULL                        # eight PCs, one marker
    assert min(col) > 150                        # near-white, not the hue
    drawn = sum(1 for row in g.b for b in row if b == X.FULL)
    assert drawn == 1 + len(spread)              # nothing was capped away
    assert not hasattr(X, 'MAX_COMETS')          # the comet era is over


def test_render_path_has_no_rng_and_is_stable_in_t(monkeypatch):
    """Every time-varying term is a function of (addr/cx/cy, cycle, t) —
    sin-hash, never RNG — so two renders at one t are identical and a later t
    moves the wave, the sizzle and the marker pulse."""
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'REDUCED_MOTION', False)
    sc = _encoding_scene()
    base = 4 * X.CORE_COLS + 2 * 5
    for i, (dx, dy) in enumerate([(0, 0), (1, 0), (0, 1), (1, 1),
                                  (0, 2), (1, 2), (0, 3), (1, 3)]):
        a = base + dy * X.CORE_COLS + dx
        sc.owner[a], sc.age[a] = (0 if i < 4 else 1), 995
    sc.procs = ([base], [])
    a1, a2 = _field(sc, t=10.0), _field(sc, t=10.0)
    assert a1.bg == a2.bg and a1.f == a2.f       # same t: byte-identical
    later = _field(sc, t=10.4)
    assert later.bg[1][5] != a1.bg[1][5]         # the contested plate sizzles
    assert later.bg[0][0] != a1.bg[0][0]         # the untouched wave breathes
    assert later.f[1][5] != a1.f[1][5]           # the marker pulses


def test_reduced_motion_freezes_every_field_term(monkeypatch):
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'REDUCED_MOTION', True)
    sc = _encoding_scene()
    base = 4 * X.CORE_COLS + 2 * 5
    for i, (dx, dy) in enumerate([(0, 0), (1, 0), (0, 1), (1, 1),
                                  (0, 2), (1, 2), (0, 3), (1, 3)]):
        a = base + dy * X.CORE_COLS + dx
        sc.owner[a], sc.age[a] = (0 if i < 4 else 1), 995
    sc.procs = ([base], [])
    a, b = _field(sc, t=10.0), _field(sc, t=97.5)
    assert a.b == b.b and a.f == b.f and a.bg == b.bg


# ---------------------------------------------------------------------------
# the seven animations
# ---------------------------------------------------------------------------

def test_load_in_writes_the_bodies_in_one_at_a_time(monkeypatch):
    """§1: warrior A scanline-writes itself in at its offset, one beat, then
    warrior B — random placement taught wordlessly."""
    monkeypatch.setattr(X, 'REDUCED_MOTION', False)
    clock = _animation_clock(monkeypatch)
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    sc = make_scene()
    battle = corewar.Battle(sc.wa, sc.wb, seed=1)
    X.reset_field(sc, battle)
    lit = []
    monkeypatch.setattr(X, 'FRAME_HOOK', lambda g, scene, t: lit.append(
        (scene.loadin[1] if scene.loadin else None,
         sum(1 for row in g.b for b in row if b))))
    with contextlib.redirect_stdout(io.StringIO()):
        assert X.load_in(sc, interruptible=False) is None
    assert sc.loadin is None                     # the beat cleaned up after
    assert len(lit) > 20
    first = lit[0]
    assert first[0] == (0.0, 0.0) and first[1] <= 1   # an empty calm core
    assert lit[-1][1] > first[1]                 # both bodies are in by the end
    a_only = [n for p, n in lit if p and p[0] > 0.9 and p[1] == 0.0]
    assert a_only and max(a_only) < lit[-1][1]   # A landed before B did
    assert clock.now <= X.LOADIN_S + 0.1         # inside its budget


def test_death_wave_cools_only_the_loser_core_wide(monkeypatch):
    """§2, the flagship: after the beat the loser's territory reads as ash
    everywhere, the winner's still glows. A glance must say who died."""
    monkeypatch.setattr(X, 'REDUCED_MOTION', False)
    _animation_clock(monkeypatch)
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    rnd = make_round(IMP, DWARF, 7, n=1)        # dwarf (B) kills the imp (A)
    sc = make_scene(rounds=[rnd])
    with contextlib.redirect_stdout(io.StringIO()):
        X.animate_round(sc, rnd)
    g = _field(sc, t=50.0)
    loser = next(i for i, o in enumerate(sc.owner) if o == 0)
    winner = next(i for i, o in enumerate(sc.owner) if o == 1 and not sc.bomb[i])
    lo, wi = block_of(g, loser)[1], block_of(g, winner)[1]
    assert sum(lo) < sum(wi)                     # a glance says who died
    assert lo[0] > lo[2]                         # and the dead army is still
    assert wi[2] > wi[0]                         # ember, the live one ice


def test_death_wave_distance_is_wrap_aware(monkeypatch):
    """Memory has no edges, so the front sweeping out from the kill address
    must reach round the top and the left as fast as it reaches down."""
    monkeypatch.setattr(X, 'REDUCED_MOTION', False)
    _animation_clock(monkeypatch)
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    sc = make_scene()
    kill = 2                                     # top row, column 2
    for addr in (kill, 102, 7902, 98, 10):
        sc.owner[addr] = 0
    sc.elim = [0, None, kill, None]
    dists = []
    monkeypatch.setattr(X, 'FRAME_HOOK', lambda g, scene, t: dists.append(
        scene.elim[3]) if scene.elim and scene.elim[3] else None)
    with contextlib.redirect_stdout(io.StringIO()):
        assert X.elimination_beat(sc, {'n': 1}, interruptible=False) is None
    assert dists
    d = dists[0]
    # 7902 is one row ABOVE the kill round the wrap, exactly as 102 is one
    # row below it; a flat map would call it 79 rows away
    assert abs(d[7902] - d[102]) < 1e-9
    assert d[7902] < 2.0
    assert d[98] < d[10]                         # and the columns wrap too
    assert sc.cooled == {0}


def test_wrap_spark_fires_when_execution_crosses_the_seam(monkeypatch):
    """§3: address 7999's neighbour is 0 — one step in memory, a whole frame
    apart on screen. The spark is the only thing that says memory is a ring."""
    monkeypatch.setattr(X, 'REDUCED_MOTION', False)
    sc = make_scene()
    battle = corewar.Battle(sc.wa, sc.wb, seed=1)
    X.reset_field(sc, battle)
    sc.last_pc[0] = 7990
    ev = type('E', (), {'warrior': 0, 'pc': 5, 'cycle': 10, 'writes': (),
                        'spawned': False, 'died': False, 'eliminated': False})
    X.apply_event(sc, ev, battle, 0.0)
    assert any(f[0] == 'wrap' for f in sc.fx)
    sc.fx = []
    ev2 = type('E', (), {'warrior': 0, 'pc': 6, 'cycle': 11, 'writes': (),
                         'spawned': False, 'died': False, 'eliminated': False})
    X.apply_event(sc, ev2, battle, 0.0)
    assert not sc.fx                             # a normal step is not a wrap


def test_marker_tempo_follows_the_pc_not_the_wall_clock(monkeypatch):
    """§4: the pulse phase comes from the PC's own address, so a moving
    process shimmers as it crawls while a stationary engine thumps steadily —
    strategy readable as rhythm, and byte-stable by construction."""
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'REDUCED_MOTION', False)
    sc = _encoding_scene()
    sc.procs = ([100], [])
    parked = block_of(_field(sc, t=10.0), 100)[1]
    sc.procs = ([101], [])                       # one cell on, the SAME block
    crawled = block_of(_field(sc, t=10.0), 101)[1]
    assert parked != crawled                     # same block, same t: moving
                                                 # changed the rhythm
    sc.procs = ([100], [])
    assert block_of(_field(sc, t=10.0), 100)[1] == parked      # deterministic
    later = block_of(_field(sc, t=10.4), 100)[1]
    assert later != parked                       # a parked engine still thumps
    monkeypatch.setattr(X, 'REDUCED_MOTION', True)
    a = block_of(_field(sc, t=10.0), 100)[1]
    b = block_of(_field(sc, t=99.0), 100)[1]
    assert a == b                                # reduced motion holds still


def test_bomb_drumbeat_is_a_plate_flash_never_a_dot(monkeypatch):
    """§5, promoted to core work at the gate: a single fresh crater lifts its
    plate ~7%, so the spark is the only place an individual bomb is visible.
    It lives in the plate because near-white dots mean "a process is here"
    and may never mean anything else."""
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'REDUCED_MOTION', False)
    sc = make_scene()
    battle = corewar.Battle(sc.wa, sc.wb, seed=1)
    X.reset_field(sc, battle)
    for _ in range(400):
        ev = battle.step()
        if ev is None:
            break
        X.apply_event(sc, ev, battle, 0.0)
        if any(f[0] == 'bomb' for f in sc.fx):
            break
    assert any(f[0] == 'bomb' for f in sc.fx)    # a dwarf bomb landed
    addr = next(f[1] for f in sc.fx if f[0] == 'bomb')
    sc.disp_cycle = float(battle.cycles)
    X.claim_procs(sc, battle)
    flash = _field(sc, t=0.02)
    sc.fx = []
    quiet = _field(sc, t=0.02)
    assert block_of(flash, addr)[2] != block_of(quiet, addr)[2]   # plate moved
    assert block_of(flash, addr)[0] == block_of(quiet, addr)[0]   # dots did not


def test_fx_queue_is_capped_and_prunes_itself(monkeypatch):
    """FX_CAP is small on purpose: the renderer steps tens of cycles per
    frame, so a bombing run spawns dozens of effects per frame and the
    inherited 120 covered an eighth of the core in light."""
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'REDUCED_MOTION', False)
    sc = make_scene()
    battle = corewar.Battle(sc.wa, sc.wb, seed=1)
    X.reset_field(sc, battle)
    for _ in range(3000):                        # fast_forward never prunes
        ev = battle.step()
        if ev is None:
            break
        X.apply_event(sc, ev, battle, 0.0)
    assert 0 < len(sc.fx) <= X.FX_CAP
    assert X.FX_CAP <= 32
    sc.disp_cycle = float(battle.cycles)
    X.claim_procs(sc, battle)
    _field(sc, t=10.0)
    assert sc.fx == []                           # every effect expired by t=10


def test_elimination_hitstop_and_shake_settles(monkeypatch):
    """The kill lands with the fighting-game hitstop; the plate shake has
    fully settled by the time the beat ends."""
    monkeypatch.setattr(X, 'REDUCED_MOTION', False)
    clock = _animation_clock(monkeypatch)
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    rnd = make_round(IMP, DWARF, 7, n=1)    # dwarf kills the imp, cycle 395
    sc = make_scene(rounds=[rnd])
    with contextlib.redirect_stdout(io.StringIO()):
        action = X.animate_round(sc, rnd)
    assert action is None
    assert any(abs(s - X.HITSTOP_S) < 1e-9 for s in clock.sleeps)
    assert X.SHAKE[0] == 0.0


def test_shake_moves_the_plate_not_the_address_mapping(monkeypatch):
    """The atlas is stationary: the elimination kick slides the drawn plate
    on screen. A shaken frame must never claim a cell lives somewhere else."""
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'REDUCED_MOTION', True)
    sc = _encoding_scene()
    for dy in range(4):
        for dx in (0, 1):
            a = (4 * 5 + dy) * X.CORE_COLS + 2 * 10 + dx
            sc.owner[a], sc.age[a] = 0, 995
    still = X.Grid(X.FIELD_W, X.FIELD_H)
    X.draw_field(still, sc, 10.0)
    assert still.b[5][10] == X.FULL
    X.SHK_OFF[0], X.SHK_OFF[1] = 2.0, 1.0
    try:
        shaken = X.Grid(X.FIELD_W, X.FIELD_H)
        X.draw_field(shaken, sc, 10.0)
    finally:
        X.SHK_OFF[0] = X.SHK_OFF[1] = 0.0
    assert shaken.b[6][12] == X.FULL             # the whole plate slid
    assert shaken.b[5][10] == 0
    assert shaken.b[0][0] == 0                   # the vacated edge is plate


def test_momentum_pacing_lands_a_full_tie_inside_the_budget(monkeypatch,
                                                            tmp_path):
    """§7 end to end on the real thing: match-002 round 1 is an 80,000-cycle
    tie, the worst case the budget exists for. It must animate inside the
    ~90s broadcast budget with the momentum controller live."""
    clock = _animation_clock(monkeypatch)
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'REDUCED_MOTION', False)
    monkeypatch.setattr(X, 'NAMES', tmp_path / 'names.txt')
    monkeypatch.setattr(X, 'BANNER', tmp_path / 'banner.txt')
    match = ENGINE.parent / 'games' / 'corewar' / 'match-002'
    a_src = (match / 'warriors' / 'A.red').read_text()
    b_src = (match / 'warriors' / 'B.red').read_text()
    lines = [ln for ln in (match / 'moves.txt').read_text().splitlines()
             if ln.strip()]
    _loads, rounds, err = X.parse_transcript(lines)
    assert err is None and len(rounds) == 3
    rnd = rounds[0]
    assert rnd['out'] == 'tie' and rnd['cycles'] == 80000
    sc = make_scene(a_src, b_src, rounds=rounds)
    t0 = clock.now
    with contextlib.redirect_stdout(io.StringIO()):
        assert X.animate_round(sc, rnd) is None
    assert clock.now - t0 <= 90.0                # the broadcast budget
    assert clock.now - t0 >= 30.0                # and not a jump-cut
    assert int(sc.disp_cycle) == 80000


# ---------------------------------------------------------------------------
# the end treatments
# ---------------------------------------------------------------------------

def test_drawn_match_cools_both_armies_together(monkeypatch):
    """The drawn-match ending, approved at the gate: both armies' territory
    cools to embers together, the whole battlefield going dark as one slow
    shared fade. A draw is "the floor held", not a failure state."""
    monkeypatch.setattr(X, 'REDUCED_MOTION', False)
    clock = _animation_clock(monkeypatch)
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    sc = _mid_battle_scene()
    sc.rounds = [{'n': i, 'out': 'tie', 'cycles': 80000} for i in (1, 2, 3)]
    sc.animated = 3
    marked = {(pc % 100 // 2, pc // 100 // 4)
              for queue in sc.procs for pc in queue}

    def ground(w):        # a held cell with no process marker over its block
        return next(i for i, o in enumerate(sc.owner)
                    if o == w and (i % 100 // 2, i // 100 // 4) not in marked)

    a_cell, b_cell = ground(0), ground(1)
    before = _field(sc, t=clock.now)
    with contextlib.redirect_stdout(io.StringIO()):
        assert X.end_wash(sc) is None
    assert sc.wash[0] == 'draw'
    assert sc.embers == 1.0
    assert clock.now >= X.DRAW_FADE_S            # kept slow and dignified
    after = _field(sc, t=clock.now)
    for w, cell in ((0, a_cell), (1, b_cell)):   # BOTH armies, not one
        was, now = block_of(before, cell)[1], block_of(after, cell)[1]
        assert sum(now) < sum(was)               # cooled together
        assert sum(block_of(after, cell)[2]) < sum(block_of(before, cell)[2])
        # ...to EMBERS, not to ash: a banked army keeps its own colour, so
        # the board still corroborates a caption that says who held what
        assert (now[0] > now[2]) if w == 0 else (now[2] > now[0])
        assert max(now) - min(now) >= 8           # visibly hued, not grey
    assert 'a dead heat · match drawn' in ''.join(
        t for t, _c, _b in X.status_segments(sc))


def test_drawn_match_cuts_to_the_cooled_state_under_reduced_motion(monkeypatch):
    monkeypatch.setattr(X, 'REDUCED_MOTION', True)
    clock = _animation_clock(monkeypatch)
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    sc = _mid_battle_scene()
    sc.rounds = [{'n': i, 'out': 'tie', 'cycles': 80000} for i in (1, 2, 3)]
    sc.animated = 3
    with contextlib.redirect_stdout(io.StringIO()):
        X.end_wash(sc)
    assert sc.embers == 1.0 and sc.washed
    assert clock.now == 0.0                      # cut, not faded


def test_decided_match_keeps_the_winner_wash(monkeypatch):
    monkeypatch.setattr(X, 'REDUCED_MOTION', False)
    clock = _animation_clock(monkeypatch)
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    sc = _mid_battle_scene()
    sc.rounds = [{'n': 1, 'out': '1-0', 'cycles': 10},
                 {'n': 2, 'out': '1-0', 'cycles': 10},
                 {'n': 3, 'out': '0-1', 'cycles': 10}]
    sc.animated = 3
    with contextlib.redirect_stdout(io.StringIO()):
        X.end_wash(sc)
    assert sc.wash[0] == 0 and sc.embers == 0.0  # ember washes, nothing cools
    hue, strength = X.wash_level(sc, clock.now)
    assert hue == X.EMBER and strength > 0.0


# ---------------------------------------------------------------------------
# Adversarial-review regression block (2026-08-13 NO-SHIP round 1):
# tampered/degraded-bus paths must survive exactly as the module docstring
# promises — never crash, never spin, always make progress.
# ---------------------------------------------------------------------------

def test_semantically_invalid_offsets_skip_the_round_never_crash(monkeypatch,
                                                                 capsys):
    """BUG-1: off=1000,1050 is below MIN_SEPARATION — Battle(off_a, off_b)
    raises ValueError. The round must be skipped with a NOTE, counted as
    animated, and the next round must still animate."""
    _animation_clock(monkeypatch)
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((60, 30)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'REDUCED_MOTION', True)
    good = make_round(IMP, DWARF, 7, n=2)
    bad = {'n': 1, 'seed': 1, 'off_a': 1000, 'off_b': 1050,
           'out': '1-0', 'cycles': 10}
    sc = make_scene(rounds=[bad, good])
    with contextlib.redirect_stdout(io.StringIO()):
        assert X.animate_round(sc, bad) is None    # no ValueError escapes
        assert sc.animated == 1                    # progress, no retry-loop
        assert X.animate_round(sc, good) is None
        assert sc.animated == 2
    err = capsys.readouterr().err
    assert 'not a legal placement' in err
    # the same guard covers the no-render snap path
    sc2 = make_scene(rounds=[bad])
    X.fast_forward(sc2, bad)
    assert sc2.animated == 1
    assert 'not a legal placement' in capsys.readouterr().err


def test_snap_with_unreadable_warriors_returns_promptly(monkeypatch):
    """BUG-2: >3 rounds pending + warriors that won't parse — the snap path
    must terminate (fast_forward guarantees progress) instead of spinning."""
    monkeypatch.setattr(X, 'REDUCED_MOTION', True)
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((60, 30)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    rounds = [{'n': i, 'seed': i, 'off_a': 0, 'off_b': 200,
               'out': 'tie', 'cycles': 10} for i in range(1, 6)]
    sc = make_scene(rounds=rounds)
    sc.wa = sc.wb = None                        # warriors unreadable
    with contextlib.redirect_stdout(io.StringIO()):
        X.snap_to_final(sc)                     # must simply return
    assert sc.animated == 5
    assert sc.phase == 'over'


def test_sync_idles_instead_of_snapping_with_unreadable_warriors(tmp_path,
                                                                 monkeypatch,
                                                                 capsys):
    """BUG-2, the loop half: the warrior guard runs before the snap branch,
    so a broken-warrior room idles (rendering, noting once) — never snaps,
    never spins, never spams stderr per pass."""
    (tmp_path / 'warriors').mkdir()
    (tmp_path / 'warriors' / 'A.red').write_text('this is not redcode at all')
    (tmp_path / 'warriors' / 'B.red').write_text('also not redcode')
    lines = ['LOAD A ' + 'a' * 64, 'LOAD B ' + 'b' * 64]
    for i in range(1, 6):
        lines.append(f'ROUND {i} seed={i} off=0,200')
        lines.append(f'ROUND {i} OUT tie cycles=10')
    (tmp_path / 'moves.txt').write_text('\n'.join(lines) + '\n')
    monkeypatch.setattr(X, 'MOVES', tmp_path / 'moves.txt')
    monkeypatch.setattr(X, 'WARRIORS', tmp_path / 'warriors')
    sc = X.Scene()
    for _ in range(3):                          # repeated passes stay quiet
        sc, pending, snap = X.sync_transcript(sc)
    assert pending is None and snap is False
    assert sc.animated == 0
    err = capsys.readouterr().err
    assert err.count('NOTE:') == 1              # noted once, not per pass


def test_non_utf8_bus_files_never_crash(tmp_path):
    """BUG-3: binary garbage in any bus file is a degraded bus, not a
    UnicodeDecodeError. Probe-level: a fresh process cold-starts and renders
    against a room whose moves/names/warriors/banner are all non-UTF-8."""
    (tmp_path / 'warriors').mkdir()
    (tmp_path / 'moves.txt').write_bytes(b'\xff\xfe\x00\x80binary')
    (tmp_path / 'names.txt').write_bytes(b'\xc3\x28\xff')
    (tmp_path / 'banner.txt').write_bytes(b'\x80\x81\x82')
    (tmp_path / 'warriors' / 'A.red').write_bytes(b'\xff\xfetext')
    (tmp_path / 'warriors' / 'B.red').write_bytes(corewar.DWARF.encode())
    (tmp_path / 'size.txt').write_bytes(b'\xff\xfe')
    script = (
        "import io, contextlib, os\n"
        "X.shutil.get_terminal_size = lambda fb: os.terminal_size((87, 23))\n"
        "X.INPUT_ENABLED = False\n"
        "sc = X.cold_start()\n"
        "print('phase:', sc.phase)\n"
        "out = io.StringIO()\n"
        "with contextlib.redirect_stdout(out):\n"
        "    X.render(sc, t=1.0)\n"
        "print('rendered:', len(out.getvalue()) > 0)\n"
        "print('names:', X.names)\n"
    )
    r = run_probe(tmp_path, script)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert lines[0] == 'phase: workshop'        # garbage transcript parses empty
    assert lines[1] == 'rendered: True'
    assert lines[2] == "names: {'r': 'TBD', 'b': 'TBD'}"


def test_floor_line_is_byte_exact(monkeypatch):
    """The refuse line is 21 cells and must refuse a 19-col pane WITHOUT
    wrapping — clipped to the pane; a pane wide enough gets it whole."""
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((19, 5)))
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        X.render(X.Scene(), t=1.0)
    plain = ANSI_RE.sub('', out.getvalue())
    assert ' core war needs ' in plain
    assert max(len(l) for l in plain.splitlines()) <= 19
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((25, 3)))
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        X.render(X.Scene(), t=1.0)
    assert ' core war needs 20x4 ' in ANSI_RE.sub('', out.getvalue())


def test_ctl_written_before_startup_is_swallowed(tmp_path, monkeypatch):
    """The startup window (§8.7): ctl_mtime is captured at launch, so a ctl
    file that predates the viewer never fires — sleep a beat after launch
    before writing ctl."""
    ctl = tmp_path / 'ctl'
    banner = tmp_path / 'banner.txt'
    ctl.write_text('banner PRELAUNCH')
    monkeypatch.setattr(X, 'D', tmp_path)
    monkeypatch.setattr(X, 'CTL', ctl)
    monkeypatch.setattr(X, 'BANNER', banner)
    monkeypatch.setattr(X, 'MOVES', tmp_path / 'moves.txt')
    monkeypatch.setattr(X, 'NAMES', tmp_path / 'names.txt')
    monkeypatch.setattr(X, 'RESULT', tmp_path / 'result.txt')
    monkeypatch.setattr(X, 'WARRIORS', tmp_path / 'warriors')
    monkeypatch.setattr(X, 'poll_input', lambda: 'quit')
    # main() captures ctl_mtime at startup; a pre-existing ctl is not newer
    monkeypatch.setattr(X, 'ctl_mtime', ctl.stat().st_mtime_ns)
    with contextlib.redirect_stdout(io.StringIO()):
        X._main_loop(X.Scene())
    assert not banner.exists()                  # the pre-launch ctl was ignored


def test_main_subprocess_full_room_clean_run(tmp_path):
    """The real __main__ path as a subprocess (the reviewer's driver
    pattern): a finished room, three seconds of broadcast, SIGINT — clean
    rc, frames emitted, nothing on stderr but allowed NOTEs. stdout drains
    to a file: a PIPE would back-pressure the renderer after ~5 frames."""
    import signal
    import time as real_time
    write_transcript(tmp_path, IMP, DWARF, [7, 11, 23])
    (tmp_path / 'names.txt').write_text('ERNIE QWEN\n')
    (tmp_path / 'result.txt').write_text('QWEN wins by battle\n')
    env = {**os.environ, 'ARCADE_LIVE': str(tmp_path),
           'COLUMNS': '87', 'LINES': '30'}
    with (tmp_path / 'out.bin').open('wb') as sink:
        p = subprocess.Popen([sys.executable, str(ENGINE / 'tui_corewar.py')],
                             cwd=tmp_path, env=env,
                             stdout=sink, stderr=subprocess.PIPE)
        real_time.sleep(3.0)
        alive = p.poll() is None
        p.send_signal(signal.SIGINT)
        _o, err_b = p.communicate(timeout=15)
    assert alive                                # was running, not crashed
    assert p.returncode == 0                    # SIGINT exits clean
    out = (tmp_path / 'out.bin').read_bytes().decode('utf-8', 'replace')
    assert out.count('\x1b[H') > 20             # real frames flowed
    err = err_b.decode('utf-8', 'replace')
    assert 'Traceback' not in err and 'CRASH' not in out


def test_main_subprocess_broken_warriors_no_spin(tmp_path):
    """BUG-2 end to end: 5 rounds + a garbage warrior — the viewer must idle
    rendering (frames flow, SIGINT answered promptly), not pin a core."""
    import signal
    import time as real_time
    (tmp_path / 'warriors').mkdir()
    (tmp_path / 'warriors' / 'A.red').write_text('this is not redcode at all')
    (tmp_path / 'warriors' / 'B.red').write_text('also not redcode')
    lines = ['LOAD A ' + 'a' * 64, 'LOAD B ' + 'b' * 64]
    for i in range(1, 6):
        lines.append(f'ROUND {i} seed={i} off=0,200')
        lines.append(f'ROUND {i} OUT tie cycles=10')
    (tmp_path / 'moves.txt').write_text('\n'.join(lines) + '\n')
    (tmp_path / 'names.txt').write_text('ERNIE QWEN\n')
    env = {**os.environ, 'ARCADE_LIVE': str(tmp_path),
           'COLUMNS': '60', 'LINES': '30'}
    with (tmp_path / 'out.bin').open('wb') as sink:
        p = subprocess.Popen([sys.executable, str(ENGINE / 'tui_corewar.py')],
                             cwd=tmp_path, env=env,
                             stdout=sink, stderr=subprocess.PIPE)
        real_time.sleep(3.0)
        p.send_signal(signal.SIGINT)
        try:
            _o, err_b = p.communicate(timeout=15)
            hung = False
        except subprocess.TimeoutExpired:
            p.kill()
            _o, err_b = p.communicate()
            hung = True
    assert not hung                             # answered SIGINT = no spin
    out = (tmp_path / 'out.bin').read_bytes().decode('utf-8', 'replace')
    assert out.count('\x1b[H') > 20             # idle frames kept flowing
    err = err_b.decode('utf-8', 'replace')
    assert 'Traceback' not in err


def test_replay_before_lock_gives_feedback(monkeypatch, tmp_path):
    """Clicking [ replay ] during the workshop (no rounds yet) must say so,
    not silently no-op — reported live as 'the replay button doesn't work'."""
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'NAMES', tmp_path / 'names.txt')
    monkeypatch.setattr(X, 'BANNER', tmp_path / 'banner.txt')
    sc = make_scene()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        sc, action = X.do_replay(sc)
    assert action is None
    assert 'nothing to replay' in ANSI_RE.sub('', out.getvalue())


# ---------------------------------------------------------------------------
# voice + layout: the plain-language label table, the ticker, the ledger
# ---------------------------------------------------------------------------

def _plain(segs):
    """Join a segment list's texts — the string a row reads as."""
    return ''.join(tx for tx, _c, _b in segs)


def test_status_labels_every_state(monkeypatch):
    """The label table from the 2026-08-14 DECISION, state by state."""
    monkeypatch.setitem(X.names, 'r', 'KIMI')
    monkeypatch.setitem(X.names, 'b', 'QWEN')
    sc = X.Scene()
    assert _plain(X.status_segments(sc)) == 'waiting for two programs'
    sc.phase = 'locked'
    assert _plain(X.status_segments(sc)) == 'KIMI vs QWEN · locked and loaded'
    sc.phase = 'battle'
    sc.rounds = [{'n': 1, 'out': 'tie', 'cycles': 80000},
                 {'n': 2, 'out': '1-0', 'cycles': 12431},
                 {'n': 3, 'out': '0-1', 'cycles': 5000}]
    sc.round_no = 1
    sc.disp_cycle = 5185.0
    assert _plain(X.status_segments(sc)) == \
        'round 1 of 3 · step 5,185 of 80,000'
    sc.round_no = 9                         # past the transcript: cap unknown
    assert _plain(X.status_segments(sc)) == 'round 9 of 3 · step 5,185'
    sc.round_no = 2
    sc.elim = [0, 123.0, 4321, {}]          # t0 live: the beat is on
    segs = X.status_segments(sc)
    assert _plain(segs) == 'round 2 · QWEN knocks out KIMI'
    assert segs[1] == ('QWEN', X.ICE, True)     # winner in faction hue, bold
    sc.elim = None
    sc.verdict = (2, '1-0', 12431)
    assert _plain(X.status_segments(sc)) == \
        'round 2 · KIMI knocks out QWEN in 12,431 steps'
    sc.verdict = (1, 'tie', 80000)
    assert _plain(X.status_segments(sc)) == \
        'round 1 · dead even — both survive 80,000 steps'
    sc.verdict = None
    sc.phase = 'over'
    sc.rounds = [{'out': '1-0'}, {'out': '0-1'}, {'out': '1-0'}]
    assert _plain(X.status_segments(sc)) == 'KIMI takes the match · 2-1'
    sc.rounds = [{'out': '1-0'}, {'out': 'tie'}, {'out': 'tie'}]
    assert _plain(X.status_segments(sc)) == 'KIMI takes the match · 1-0 · 2 tied'
    sc.rounds = [{'out': 'tie'}] * 3
    assert _plain(X.status_segments(sc)) == \
        'a dead heat · match drawn — nobody died in three rounds'
    sc.rounds = [{'out': '1-0'}, {'out': '0-1'}]
    assert _plain(X.status_segments(sc)) == \
        'a dead heat · match drawn · one win each'


def test_ticker_first_blood_death_and_elimination(monkeypatch):
    monkeypatch.setitem(X.names, 'r', 'ALPHA')
    monkeypatch.setitem(X.names, 'b', 'OMEGA')
    sc = make_scene()
    battle = corewar.Battle(sc.wa, sc.wb, seed=1)
    X.reset_field(sc, battle)
    for _ in range(400):
        ev = battle.step()
        if ev is None:
            break
        X.apply_event(sc, ev, battle, 0.0)
        if sc.events:
            break
    assert sc.events[0] == 'first blood — OMEGA lands the first bomb'
    # a doomed warrior narrates its own death, then its elimination
    sc2 = make_scene(SPLIER, DOOMED)
    battle2 = corewar.Battle(sc2.wa, sc2.wb, seed=3)
    X.reset_field(sc2, battle2)
    while not battle2.over:
        ev = battle2.step()
        if ev is None:
            break
        X.apply_event(sc2, ev, battle2, 0.0)
    assert any(t.startswith("OMEGA's copy dies at ") for t in sc2.events)
    assert sc2.events[-1] == "OMEGA's last copy died"
    assert len(sc2.events) <= 8


def test_ticker_territory_milestones_fire_once(monkeypatch):
    monkeypatch.setitem(X.names, 'r', 'ALPHA')
    monkeypatch.setitem(X.names, 'b', 'OMEGA')
    sc = make_scene()
    battle = corewar.Battle(sc.wa, sc.wb, seed=1)
    X.reset_field(sc, battle)
    for a in range(4000):
        sc.owner[a] = 0
        sc.age[a] = 0
    X.claim_procs(sc, battle)
    assert sc.events[-1] == 'ALPHA holds half the board'
    X.claim_procs(sc, battle)                   # the same crossing: no refire
    assert sc.events.count('ALPHA holds half the board') == 1
    for a in range(4000, 6001):
        sc.owner[a] = 0
        sc.age[a] = 0
    X.claim_procs(sc, battle)
    assert sc.events[-1] == 'ALPHA holds three-quarters of the board'


def test_ticker_fork_bloom_on_doubling(monkeypatch):
    monkeypatch.setitem(X.names, 'r', 'ALPHA')
    monkeypatch.setitem(X.names, 'b', 'OMEGA')
    sc = make_scene(SPLIER, IMP)
    battle = corewar.Battle(sc.wa, sc.wb, seed=5)
    X.reset_field(sc, battle)
    for _ in range(4000):
        ev = battle.step()
        if ev is None:
            break
        X.apply_event(sc, ev, battle, 0.0)
        if any('splits:' in t for t in sc.events):
            break
    assert 'ALPHA splits: 4 → 8 running' in sc.events


def test_ledger_never_spoils_unanimated_rounds(monkeypatch):
    monkeypatch.setitem(X.names, 'r', 'KIMI')
    monkeypatch.setitem(X.names, 'b', 'QWEN')
    sc = make_scene(rounds=[{'n': 1, 'out': '1-0', 'cycles': 100},
                            {'n': 2, 'out': '0-1', 'cycles': 200},
                            {'n': 3, 'out': 'tie', 'cycles': 300}])
    sc.phase = 'battle'
    sc.animated = 1
    ledger = ledger_plain(sc)
    assert ledger == 'round 1 KIMI won · round 2 playing'
    assert 'QWEN' not in ledger
    assert ledger_plain(sc, compact=True) == 'rounds 1 KIMI won · 2 playing'
    sc.animated = 3
    sc.phase = 'over'
    assert ledger_plain(sc) == 'round 1 KIMI won · round 2 QWEN won · round 3 tie'
    sc2 = make_scene()                          # before round 1: nothing to say
    sc2.phase = 'battle'
    assert ledger_plain(sc2) == ''


def test_status_row_carries_the_ledger_and_drops_it_last(monkeypatch):
    """The ledger returns to the status area: a viewer joining late needs the
    series state at a glance. Optional slots drop from the right as the pane
    narrows — ticker first, then the ledger; the phase voice never drops."""
    monkeypatch.setitem(X.names, 'r', 'KIMI')
    monkeypatch.setitem(X.names, 'b', 'QWEN')
    sc = make_scene(rounds=[{'n': 1, 'out': 'tie', 'cycles': 80000},
                            {'n': 2, 'out': '1-0', 'cycles': 200},
                            {'n': 3, 'out': 'tie', 'cycles': 300}])
    sc.phase = 'battle'
    sc.animated = 1
    sc.round_no = 2
    sc.disp_cycle = 120.0
    sc.events = ['first blood — KIMI lands the first bomb']
    wide = _plain(X.status_row_segments(sc, 200))
    assert 'round 2 of 3' in wide
    assert 'rounds 1 tie · 2 playing' in wide   # the compact fold
    assert 'last: first blood' in wide
    mid = _plain(X.status_row_segments(sc, 62))
    assert 'rounds 1 tie · 2 playing' in mid
    assert 'last:' not in mid                   # the ticker went first
    tight = _plain(X.status_row_segments(sc, 40))
    assert tight.startswith('round 2 of 3')
    assert 'rounds' not in tight                # then the ledger
    # with a ledger row of its own, the status never folds one in
    assert 'rounds 1 tie' not in _plain(
        X.status_row_segments(sc, 200, fold_ledger=False))


def test_faction_bars_hold_share_of_core_and_compact(monkeypatch):
    """The bars ARE the legend: "held" and "running" say in words what the
    two bright things on the field mean. They are share of the WHOLE core, so
    they do not sum to 100 while untouched memory remains."""
    monkeypatch.setitem(X.names, 'r', 'KIMI')
    monkeypatch.setitem(X.names, 'b', 'QWEN')
    sc = make_scene(rounds=[{'n': 1, 'out': 'tie', 'cycles': 80000}])
    sc.phase = 'battle'
    for a in range(400):
        sc.owner[a] = 0
    for a in range(4000, 5600):
        sc.owner[a] = 1
    sc.own = (sc.owner.count(0), sc.owner.count(1))
    sc.procs = ([1, 2], [3])
    wide = _plain(X.bars_row_segments(sc, 79))
    assert '5% held' in wide and '20% held' in wide
    assert '2 running' in wide and '1 running' in wide
    segs = X.bars_row_segments(sc, 79)
    assert segs[0][1] == X.EMBER                # names in their faction hues
    assert any(c == X.ICE for _t, c, _b in segs)
    assert X.bar(0.0) == '░' * X.BAR_W
    assert X.bar(1.0) == '█' * X.BAR_W
    # a 9-cell bar of whole blocks shows NOTHING under 5.6%, and every
    # battle starts there: the leading edge is an eighth block instead
    assert X.bar(0.05)[0] not in ('░', '█') and len(X.bar(0.05)) == X.BAR_W
    narrow = _plain(X.bars_row_segments(sc, 46))
    assert '5%' in narrow and '20%' in narrow
    assert 'running' not in narrow              # compact: the shares survive
    assert len(narrow) <= 46


def test_legend_replaces_the_bars_before_the_battle(monkeypatch):
    monkeypatch.setitem(X.names, 'r', 'KIMI')
    monkeypatch.setitem(X.names, 'b', 'QWEN')
    sc = X.Scene()
    legend = ('KIMI = ember · QWEN = ice · one dot = one memory cell · '
              'white block = running code · dark pit = bomb damage')
    segs = X.bars_row_segments(sc, 120)
    assert _plain(segs) == legend
    assert segs[0] == ('KIMI', X.EMBER, False)      # the faction mapping
    assert segs[2] == ('QWEN', X.ICE, False)        # carries the hues
    sc.phase = 'locked'
    assert _plain(X.bars_row_segments(sc, 120)) == legend


def test_header_fits_the_atlas_floor(monkeypatch):
    """The teaching line drops before a name is clipped."""
    monkeypatch.setitem(X.names, 'r', 'KIMI')
    monkeypatch.setitem(X.names, 'b', 'QWEN')
    assert _plain(X.header_segments(X.Scene(), 80)) == \
        'KIMI vs QWEN' + X.TEACH
    assert _plain(X.header_segments(X.Scene(), 20)) == 'KIMI vs QWEN'
    monkeypatch.setitem(X.names, 'r', 'A' * 40)
    assert len(_plain(X.header_segments(X.Scene(), 28))) <= 28


def test_status_extra_is_budgeted_not_appended(monkeypatch, tmp_path):
    """The replay-no-op feedback shares the status budget: at the atlas floor
    the combined row still fits the pane."""
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((55, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'NAMES', tmp_path / 'names.txt')
    monkeypatch.setattr(X, 'BANNER', tmp_path / 'banner.txt')
    sc = make_scene()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        sc, action = X.do_replay(sc)
    assert action is None
    plain = ANSI_RE.sub('', out.getvalue())
    assert 'nothing to replay' in plain
    assert max(len(l) for l in plain.splitlines()) <= 55


def test_strip_clips_status_and_shows_extra(monkeypatch, tmp_path):
    """20x4 floor: the status clips mid-word instead of vanishing; at a
    wider strip the replay-no-op feedback shows too (clipped, budgeted)."""
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'NAMES', tmp_path / 'names.txt')
    monkeypatch.setattr(X, 'BANNER', tmp_path / 'banner.txt')
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((20, 4)))
    sc = make_scene()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        X.render(sc, t=1.0)
    plain = ANSI_RE.sub('', out.getvalue())
    assert 'waiting for two pro' in plain       # clipped, never blank
    assert max(len(l) for l in plain.splitlines()) <= 20
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((27, 4)))
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        sc, action = X.do_replay(sc)
    assert action is None
    plain = ANSI_RE.sub('', out.getvalue())
    assert 'nothing to replay' in plain         # the strip is not silent
    assert max(len(l) for l in plain.splitlines()) <= 27


def test_replay_button_bounds_track_the_visible_button(monkeypatch, tmp_path):
    """_btn_bounds must sit on the visible button: the col math runs on the
    post-clip status width."""
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', True)
    monkeypatch.setitem(X.names, 'r', 'ERNIE')
    monkeypatch.setitem(X.names, 'b', 'QWEN')
    monkeypatch.setattr(X, 'NAMES', tmp_path / 'names.txt')
    monkeypatch.setattr(X, 'BANNER', tmp_path / 'banner.txt')
    sc = make_scene()
    sc.phase = 'locked'
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        X.render(sc, t=1.0)
    assert X._btn_bounds is not None
    row, c0, c1 = X._btn_bounds
    lines = ANSI_RE.sub('', out.getvalue()).splitlines()
    assert X.BTN_TEXT in lines[row - 1]
    assert lines[row - 1].index(X.BTN_TEXT) == c0 - 1     # 1-indexed cols
    assert c1 - c0 + 1 == len(X.BTN_TEXT)


def test_single_round_replay_never_spoils_the_ledger(monkeypatch, tmp_path):
    """Re-animating round 1 of a finished match must not reveal rounds 2/3 —
    the reveal cursor rewinds the ledger; restore brings them back."""
    _animation_clock(monkeypatch)
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((60, 30)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'ctl_changed', lambda: False)
    # bus paths are import-time bound; never let render read the real live dir
    monkeypatch.setattr(X, 'NAMES', tmp_path / 'names.txt')
    monkeypatch.setattr(X, 'BANNER', tmp_path / 'banner.txt')
    monkeypatch.setitem(X.names, 'r', 'ERNIE')
    monkeypatch.setitem(X.names, 'b', 'QWEN')
    rounds = [make_round(IMP, DWARF, 7, n=1),
              make_round(IMP, DWARF, 21, n=2),
              make_round(IMP, DWARF, 11, n=3)]
    sc = make_scene(rounds=rounds)
    with contextlib.redirect_stdout(io.StringIO()):
        for rnd in rounds:
            assert X.animate_round(sc, rnd) is None
    assert sc.animated == 3
    seen = []
    monkeypatch.setattr(X, 'FRAME_HOOK',
                        lambda g, scene, t: seen.append(ledger_plain(scene)))
    with contextlib.redirect_stdout(io.StringIO()):
        sc, action = X.do_replay(sc, 1)
    assert action is None
    assert len(seen) > 20                       # a real animation was sampled
    assert all(s == 'round 1 playing' for s in seen[:-1])   # 2/3 never shown
    winner = {'1-0': 'ERNIE won', '0-1': 'QWEN won', 'tie': 'tie'}
    full = ' · '.join(f"round {r['n']} {winner[r['out']]}" for r in rounds)
    assert seen[-1] == full                     # the post-restore frame
    assert ledger_plain(sc) == full            # restored


def test_replay_interrupt_clears_the_reveal_cursor(monkeypatch, tmp_path):
    """Regression: a single-round replay interrupted by 'replay' becomes a
    full replay — the reveal cursor must clear with the transition, or the
    full replay's round 1 shows the held rounds 2/3 outcomes (the spoiler
    the cursor exists to kill). The 'ctl'/'quit'/completed paths restore
    the snapshot, which already carries reveal=None."""
    _animation_clock(monkeypatch)
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((60, 30)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'ctl_changed', lambda: False)
    # bus paths are import-time bound; never let render read the real live dir
    monkeypatch.setattr(X, 'NAMES', tmp_path / 'names.txt')
    monkeypatch.setattr(X, 'BANNER', tmp_path / 'banner.txt')
    monkeypatch.setitem(X.names, 'r', 'ERNIE')
    monkeypatch.setitem(X.names, 'b', 'QWEN')
    rounds = [make_round(IMP, DWARF, 7, n=1),
              make_round(IMP, DWARF, 21, n=2),
              make_round(IMP, DWARF, 11, n=3)]
    sc = make_scene(rounds=rounds)
    with contextlib.redirect_stdout(io.StringIO()):
        for rnd in rounds:
            assert X.animate_round(sc, rnd) is None
    assert sc.animated == 3
    fired = [False]

    def scripted_poll():
        # mid single-round replay of round 3: ask for the full replay, once
        if not fired[0] and sc.reveal == 2 and sc.disp_cycle > 0:
            fired[0] = True
            return 'replay'
        return None

    monkeypatch.setattr(X, 'poll_input', scripted_poll)
    ledgers = []

    def hook(g, scene, t):
        # the full replay's round 1, while the round is actually animating
        if (scene.round_no == 1 and scene.verdict is None
                and scene.phase == 'battle'):
            ledgers.append(ledger_plain(scene))

    monkeypatch.setattr(X, 'FRAME_HOOK', hook)
    with contextlib.redirect_stdout(io.StringIO()):
        sc, action = X.do_replay(sc, 3)
    assert action is None
    assert fired[0]                             # the interrupt really fired
    assert sc.reveal is None                    # cleared with the transition
    assert ledgers                              # round-1 frames were sampled
    assert all(s == 'round 1 playing' for s in ledgers)   # 2/3 never shown
    assert sc.animated == 3                     # the full replay re-counted


# ---------------------------------------------------------------------------
# fix round (2026-08-14): the cold floor, the row budget, the bottom chrome
# ---------------------------------------------------------------------------

def test_owned_ground_never_decays_below_a_faction_whisper(monkeypatch):
    """THE COLD FLOOR. The field is the evidence for the bars: a caption
    reading "99% held" over a colourless grey field is the board contradicting
    its own chrome. Heat may reach zero; faction identity may not — cold
    ground stays unmistakably brick or steel, in every state that can drain
    heat out of a cell (age, elimination, the drawn-match fade)."""
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'REDUCED_MOTION', True)
    sc = _encoding_scene()
    sc.disp_cycle = 500000.0                     # written an age ago
    ember, ice = 400, 1200
    for base, w in ((ember, 0), (ice, 1)):
        for dy in range(4):
            for dx in (0, 1):
                a = base + dy * X.CORE_COLS + dx
                sc.owner[a], sc.age[a] = w, 10

    def read(sc):
        g = _field(sc, t=3.0)
        return block_of(g, ember)[1], block_of(g, ice)[1]

    for label, mutate in (('stone cold', lambda: None),
                          ('eliminated', lambda: sc.cooled.update({0, 1})),
                          ('drawn fade', lambda: setattr(sc, 'embers', 1.0))):
        mutate()
        e, i = read(sc)
        assert e[0] > e[2] + 12, (label, e)      # ember reads warm
        assert i[2] > i[0] + 12, (label, i)      # ice reads cool
        assert e != i and max(e) > 20 and max(i) > 20, (label, e, i)
        # and neither has converged on a neutral grey
        assert max(e) - min(e) >= 12 and max(i) - min(i) >= 12, (label, e, i)


def test_cold_and_hot_separate_by_luminance_not_hue(monkeypatch):
    """The late-loudness correction survives the cold floor: a live front is
    several times brighter than settled ground, so it still owns a saturated
    frame — the separation moved from hue to luminance."""
    hot = X.ground_colour(0, 1.0)
    cold = X.ground_colour(0, 0.0)
    assert sum(hot) > 3 * sum(cold)
    assert cold[0] > cold[2]                     # the whisper is still ember
    ice_cold = X.ground_colour(1, 0.0)
    assert sum(abs(a - b) for a, b in zip(cold, ice_cold)) > 60   # armies apart


def test_frame_never_exceeds_the_pane(monkeypatch, tmp_path):
    """The row budget. A frame taller than its pane scrolls the whole board
    every frame — the exact-fill bug in a different costume, and it shipped
    live as a silent 24th row (the banner) under a 23-row pane. Rows are
    built into a list and capped, so no future row can reintroduce it."""
    monkeypatch.setattr(X, 'NAMES', tmp_path / 'names.txt')
    banner = tmp_path / 'banner.txt'
    banner.write_text('ROUND TABLE · exhibition')
    monkeypatch.setattr(X, 'BANNER', banner)
    X._fcache.clear()
    finished = make_scene(rounds=[{'n': i, 'out': 'tie', 'cycles': 80000}
                                  for i in (1, 2, 3)])
    finished.animated = 3
    for scene in (X.Scene(), _mid_battle_scene(), finished):
        for phase in ('workshop', 'locked', 'battle', 'over'):
            scene.phase = phase
            for cols in (20, 40, 54, 55, 60, 87, 120, 200):
                for rows in (4, 5, 10, 22, 23, 24, 25, 26, 30, 60):
                    monkeypatch.setattr(
                        X.shutil, 'get_terminal_size',
                        lambda fb, c=cols, r=rows: os.terminal_size((c, r)))
                    for enabled in (False, True):
                        monkeypatch.setattr(X, 'INPUT_ENABLED', enabled)
                        out = io.StringIO()
                        with contextlib.redirect_stdout(out):
                            X.render(scene, t=1.0)
                        lines = ANSI_RE.sub('', out.getvalue()).splitlines()
                        assert len(lines) <= rows, (phase, cols, rows,
                                                    len(lines))
                        assert max((len(l) for l in lines), default=0) <= cols


def test_banner_is_a_pre_match_caption_only(monkeypatch, tmp_path):
    """The referee writes banner.txt in chess's scoreline (`RED 1/2-1/2 BLUE
    — battle`). That is a bus record, not board text: under a finished match
    it repeated the status row in a language this game does not speak. The
    banner shows where it IS the content — before the battle starts."""
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 26)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'NAMES', tmp_path / 'names.txt')
    banner = tmp_path / 'banner.txt'
    banner.write_text('KIMI 1/2-1/2 CODEX — battle')
    monkeypatch.setattr(X, 'BANNER', banner)
    X._fcache.clear()
    sc = _mid_battle_scene()
    for phase, expected in (('workshop', True), ('locked', True),
                            ('battle', False), ('over', False)):
        sc.phase = phase
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            X.render(sc, t=1.0)
        shown = '1/2-1/2' in ANSI_RE.sub('', out.getvalue())
        assert shown is expected, phase


def test_ledger_row_when_the_pane_affords_it(monkeypatch, tmp_path):
    """The freed row becomes the round history on a line of its own, spelled
    out. Below that height the compact form folds back into the status row —
    the series state is never simply dropped."""
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'NAMES', tmp_path / 'names.txt')
    monkeypatch.setattr(X, 'BANNER', tmp_path / 'banner.txt')
    monkeypatch.setitem(X.names, 'r', 'KIMI')
    monkeypatch.setitem(X.names, 'b', 'CODEX')
    sc = _mid_battle_scene()
    sc.rounds = [{'n': 1, 'out': 'tie', 'cycles': 80000},
                 {'n': 2, 'out': '0-1', 'cycles': 1200},
                 {'n': 3, 'out': '1-0', 'cycles': 900}]
    sc.animated = 2
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 24)))
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        X.render(sc, t=1.0)
    lines = ANSI_RE.sub('', out.getvalue()).splitlines()
    assert len(lines) == 24
    ledger = lines[22]
    assert 'round 1 tie · round 2 CODEX won · round 3 playing' in ledger
    assert 'rounds 1 tie' not in lines[23]       # not said twice
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 23)))
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        X.render(sc, t=1.0)
    lines = ANSI_RE.sub('', out.getvalue()).splitlines()
    assert len(lines) == 23
    assert not any('round 1 tie · round 2' in l for l in lines)   # no own row
    assert 'rounds 1 tie · 2 CODEX won · 3 playing' in lines[22]  # folded


def test_ledger_names_winners_in_faction_hue():
    sc = make_scene(rounds=[{'n': 1, 'out': '1-0', 'cycles': 10},
                            {'n': 2, 'out': '0-1', 'cycles': 10}])
    sc.phase = 'over'
    sc.animated = 2
    segs = X.ledger_segments(sc)
    hues = [c for tx, c, _b in segs if c in (X.EMBER, X.ICE)]
    assert hues == [X.EMBER, X.ICE]
    assert 'won' in ledger_plain(sc) and 'tie' not in ledger_plain(sc)


def test_identity_mark_sits_in_the_bottom_chrome(monkeypatch, tmp_path):
    """CORE WAR returns to the frame as a quiet bottom mark in LABEL colour.
    It takes the ledger row when there is one (short by nature) and the
    status row's own slack otherwise — and it is the first thing to yield:
    it never clips a verdict and never displaces the replay button."""
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'NAMES', tmp_path / 'names.txt')
    monkeypatch.setattr(X, 'BANNER', tmp_path / 'banner.txt')
    monkeypatch.setitem(X.names, 'r', 'KIMI')
    monkeypatch.setitem(X.names, 'b', 'CODEX')
    sc = _mid_battle_scene()
    sc.rounds = [{'n': i, 'out': 'tie', 'cycles': 80000} for i in (1, 2, 3)]
    sc.animated = 3
    sc.phase = 'over'
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 24)))
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        X.render(sc, t=1.0)
    lines = ANSI_RE.sub('', out.getvalue()).splitlines()
    assert lines[22].rstrip().endswith(X.MARK)   # the ledger row carries it
    assert X.MARK not in lines[23]               # said once, never twice
    assert 'match drawn' in lines[23]
    # a pane with no room for it simply does not have it
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((55, 23)))
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        X.render(sc, t=1.0)
    plain = ANSI_RE.sub('', out.getvalue())
    assert X.MARK not in plain
    assert max(len(l) for l in plain.splitlines()) <= 55


def test_replay_button_is_right_aligned_and_stable(monkeypatch, tmp_path):
    """The status text changes width every frame (the step counter grows), so
    a button placed just after it slides under the cursor. Pinned to the
    right margin it holds still, and _btn_bounds tracks it."""
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 24)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', True)
    monkeypatch.setattr(X, 'NAMES', tmp_path / 'names.txt')
    monkeypatch.setattr(X, 'BANNER', tmp_path / 'banner.txt')
    sc = _mid_battle_scene()
    seen = set()
    for cyc in (7.0, 1000.0, 79999.0):
        sc.disp_cycle = cyc
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            X.render(sc, t=1.0)
        assert X._btn_bounds is not None
        row, c0, c1 = X._btn_bounds
        lines = ANSI_RE.sub('', out.getvalue()).splitlines()
        assert lines[row - 1].index(X.BTN_TEXT) == c0 - 1
        assert c1 - c0 + 1 == len(X.BTN_TEXT)
        seen.add((c0, c1))
    assert len(seen) == 1                        # the target never moved


# ---------------------------------------------------------------------------
# live replay audio (the 2026-08-14 music block)
#
# The soundtrack is opt-in and every failure in it degrades to silence, so
# what these tests hold are the two promises that are easy to break quietly:
# the pane never gains a hard numpy dependency (nothing below imports it, and
# the score pipeline is stubbed), and no afplay outlives the pane that
# started it (checked against a real process, not a mock's call log).
# ---------------------------------------------------------------------------

@pytest.fixture
def music_scratch(monkeypatch):
    """Music state is process-global (a player, a scratch dir, a cached WAV).
    Hand each test a clean one and take the scratch back afterwards."""
    X.cleanup_music()
    monkeypatch.setattr(X, 'MUSIC', [False])
    monkeypatch.setattr(X, 'PLAYER', list(X.PLAYER))
    monkeypatch.setattr(X, '_player_note', [False])
    yield
    X.cleanup_music()


SLEEPER = [sys.executable, '-c', 'import time; time.sleep(30)']


class _StubRecorder:
    """record_cw's three public verbs, without numpy or a match archive."""

    def __init__(self, wav_bytes=b'RIFFstub'):
        self.extracted = []
        self.draw_during_extract = []
        self.wav_bytes = wav_bytes

    def extract(self, match_dir, **kw):
        self.extracted.append(Path(match_dir))
        self.draw_during_extract.append(X.DRAW_FRAMES)
        return 'timeline'

    def synthesize(self, tl, log=None):
        assert tl == 'timeline'
        return 'samples'

    def write_wav(self, samples, path):
        assert samples == 'samples'
        Path(path).write_bytes(self.wav_bytes)


def _stub_match(monkeypatch, tmp_path, recorder):
    """Point the bus at tmp_path and the score pipeline at `recorder`."""
    monkeypatch.setattr(X, 'D', tmp_path)
    monkeypatch.setattr(X, 'MOVES', tmp_path / 'moves.txt')
    (tmp_path / 'moves.txt').write_text('LOAD A ' + '0' * 64 + '\n')
    monkeypatch.setitem(sys.modules, 'record_cw', recorder)


def test_music_is_silent_by_default_and_env_opts_in(tmp_path):
    """A terminal that makes noise unasked is rude: the default is off, and
    ARCADE_MUSIC is the way in. Checked in a fresh process, because the flag
    is read from the environment exactly once, at import."""
    probe = (f"import sys; sys.path.insert(0, {str(ENGINE)!r})\n"
             "import tui_corewar as X\n"
             "print(X.MUSIC[0])\n")
    env = {k: v for k, v in os.environ.items() if k != 'ARCADE_MUSIC'}
    off = subprocess.run([sys.executable, '-c', probe], env=env,
                         capture_output=True, text=True)
    on = subprocess.run([sys.executable, '-c', probe],
                        env={**env, 'ARCADE_MUSIC': '1'},
                        capture_output=True, text=True)
    assert off.stdout.strip() == 'False'
    assert on.stdout.strip() == 'True'


def test_stop_music_leaves_no_orphan_player(music_scratch, tmp_path):
    """The one that has to be true against a real process: a player that
    outlived its pane would sing over whatever the terminal did next, with no
    surface left to stop it."""
    wav = tmp_path / 'track.wav'
    wav.write_bytes(b'RIFF')
    X.PLAYER[:] = SLEEPER
    proc = X.play_wav(wav)
    assert proc is not None and proc.poll() is None
    os.kill(proc.pid, 0)                        # really running, really ours
    X.stop_music()
    assert proc.poll() is not None              # exited AND reaped
    with pytest.raises(ProcessLookupError):
        os.kill(proc.pid, 0)
    assert X._music_proc[0] is None
    # a second player never stacks on the first
    a = X.play_wav(wav)
    b = X.play_wav(wav)
    assert a.poll() is not None                 # the first was stopped for it
    assert b.poll() is None
    X.stop_music()
    assert b.poll() is not None


def test_disabling_music_stops_playback_immediately(music_scratch, tmp_path):
    """A mute button that only takes effect at the next replay is not a mute
    button."""
    wav = tmp_path / 'track.wav'
    wav.write_bytes(b'RIFF')
    X.PLAYER[:] = SLEEPER
    X.set_music(True)
    proc = X.play_wav(wav)
    assert proc.poll() is None
    assert X.set_music(False) is False
    assert proc.poll() is not None
    assert X.MUSIC[0] is False


def test_cleanup_music_takes_the_scratch_wav_with_it(music_scratch, tmp_path):
    """30 MB of rendered score per match: leaking one per session is the
    tmp-hygiene bug this repo has already paid for twice."""
    scratch = X._music_dir_path()
    assert scratch.exists()
    (scratch / 'replay.wav').write_bytes(b'RIFF')
    X.PLAYER[:] = SLEEPER
    proc = X.play_wav(scratch / 'replay.wav')
    X.cleanup_music()
    assert not scratch.exists()                 # the WAV went with the dir
    assert proc.poll() is not None              # and the player with it
    assert X._music_dir[0] is None and X._music_wav[0] is None


def test_missing_player_degrades_to_silence_and_says_so_once(
        music_scratch, tmp_path, capsys):
    """No afplay: the replay still plays, quietly, and the pane says why —
    once per session, not once per replay."""
    wav = tmp_path / 'track.wav'
    wav.write_bytes(b'RIFF')
    X.PLAYER[:] = ['cw-no-such-player']
    assert X._player_cmd(wav) is None
    assert X.play_wav(wav) is None
    assert X.play_wav(wav) is None
    err = capsys.readouterr().err
    assert err.count('cw-no-such-player') == 1
    assert 'silently' in err


def test_score_replay_renders_once_and_holds_the_seam(music_scratch, tmp_path,
                                                      monkeypatch):
    """The scoring pass turns the drawing off (95% of extraction) and puts it
    back, the WAV lands in the managed scratch dir, and a second replay of the
    same transcript reuses it instead of paying the render again."""
    rec = _StubRecorder()
    _stub_match(monkeypatch, tmp_path, rec)
    said = []
    wav = X.score_replay(said.append)
    assert wav is not None and wav.read_bytes() == b'RIFFstub'
    assert wav.parent == X._music_dir[0]        # the managed scratch dir
    assert rec.extracted == [tmp_path]          # scored THIS match
    assert rec.draw_during_extract == [False]   # drawing off for the pass
    assert X.DRAW_FRAMES is True                # and back on afterwards
    assert said == ['scoring…']                 # the wait is announced once

    again = X.score_replay(said.append)
    assert again == wav
    assert rec.extracted == [tmp_path]          # cached: no second render
    assert said == ['scoring…']

    (tmp_path / 'moves.txt').write_text('LOAD A ' + '1' * 64 + '\n')
    X.score_replay(said.append)
    assert rec.extracted == [tmp_path, tmp_path]   # a new transcript re-scores


def test_score_replay_failure_is_silence_not_a_crash(music_scratch, tmp_path,
                                                     monkeypatch, capsys):
    """extract() exits on a directory that is not a match and synthesis needs
    numpy. Both are 'no music today', never 'no replay today' — and the draw
    seam is restored on the way out, or the pane goes blank for good."""
    rec = _StubRecorder()

    def boom(match_dir, **kw):
        assert X.DRAW_FRAMES is False
        raise SystemExit(f'{match_dir} is not a Core War match directory')

    rec.extract = boom
    _stub_match(monkeypatch, tmp_path, rec)
    assert X.score_replay() is None
    assert X.DRAW_FRAMES is True
    assert 'no soundtrack' in capsys.readouterr().err

    def no_numpy(tl, log=None):
        raise ModuleNotFoundError("No module named 'numpy'")

    rec.extract = _StubRecorder().extract
    rec.synthesize = no_numpy
    assert X.score_replay() is None
    assert X.DRAW_FRAMES is True
    assert 'numpy' in capsys.readouterr().err


def test_scoring_pass_leaves_the_timeline_alone(monkeypatch):
    """The claim the DRAW_FRAMES seam makes: a scored run and a drawn run
    produce the SAME broadcast timeline. Pacing is a virtual clock and never a
    measured one, so switching the picture off may not move a single beat — if
    it ever does, the track drifts against the picture it was scored for."""
    rnd = make_round(DOOMED, IMP, 5, n=1)

    def timeline():
        clock = _animation_clock(monkeypatch)
        events, frames = [], []
        monkeypatch.setattr(X, 'EVENT_HOOK',
                            lambda k, a, w, t, x: events.append((k, a, w, t)))
        monkeypatch.setattr(X, 'FRAME_HOOK',
                            lambda g, sc, t: frames.append(t))
        sc = make_scene(DOOMED, IMP, rounds=[rnd])
        X.animate_round(sc, rnd)
        return events, frames, clock.now

    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((87, 24)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        drawn = timeline()
    assert out.getvalue()                       # the drawn run really drew

    monkeypatch.setattr(X, 'DRAW_FRAMES', False)
    quiet = io.StringIO()
    with contextlib.redirect_stdout(quiet):
        scored = timeline()
    assert quiet.getvalue() == ''               # and the scoring pass did not
    assert scored == drawn                      # same beats, same frames, same
                                                # length: one timeline
    assert len(drawn[1]) > 10 and any(k == 'elimination' for k, *_ in drawn[0])


def test_music_plays_only_for_a_full_replay(music_scratch, tmp_path,
                                            monkeypatch):
    """The score's timeline starts at round 1, so a full replay gets one
    starting gun and a single-round replay stays silent rather than playing
    the wrong two minutes. Playback starts before the load-in and is stopped
    when the replay ends — nothing sings on into the held end state."""
    _animation_clock(monkeypatch)
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fb: os.terminal_size((60, 30)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'ctl_changed', lambda: False)
    monkeypatch.setattr(X, 'NAMES', tmp_path / 'names.txt')
    monkeypatch.setattr(X, 'BANNER', tmp_path / 'banner.txt')
    log = []
    monkeypatch.setattr(X, 'score_replay',
                        lambda status=None: (log.append('score'),
                                             tmp_path / 'track.wav')[1])
    monkeypatch.setattr(X, 'play_wav', lambda wav: log.append('play'))
    monkeypatch.setattr(X, 'stop_music', lambda: log.append('stop'))
    monkeypatch.setattr(X, 'animate_round',
                        lambda sc, rnd, interruptible=False:
                        log.append(f"round {rnd['n']}"))
    monkeypatch.setattr(X, 'end_wash', lambda sc, interruptible=False: None)
    rounds = [make_round(DOOMED, IMP, 5, n=1), make_round(DOOMED, IMP, 9, n=2)]
    sc = make_scene(DOOMED, IMP, rounds=rounds)
    sc.animated = 2

    X.MUSIC[0] = False
    with contextlib.redirect_stdout(io.StringIO()):
        X.do_replay(sc, None)
    assert log == ['stop', 'round 1', 'round 2', 'stop']   # opt-in: no score

    log.clear()
    X.MUSIC[0] = True
    with contextlib.redirect_stdout(io.StringIO()):
        X.do_replay(sc, None)
    assert log == ['stop', 'score', 'play', 'round 1', 'round 2', 'stop']

    log.clear()
    with contextlib.redirect_stdout(io.StringIO()):
        X.do_replay(sc, 1)                      # one round: silent
    assert log == ['stop', 'round 1', 'stop']

    log.clear()
    monkeypatch.setattr(X, 'REDUCED_MOTION', True)
    with contextlib.redirect_stdout(io.StringIO()):
        X.do_replay(sc, None)                   # a track is not a motion
    assert log == ['stop', 'score', 'play', 'round 1', 'round 2', 'stop']


def test_ctl_music_verb_toggles_and_says_which_way(tmp_path, monkeypatch,
                                                   music_scratch):
    """`music` toggles, `music on|off` sets, and either way the ticker says
    what happened — a control whose state you cannot see is a guess."""
    monkeypatch.setattr(X, 'D', tmp_path)
    monkeypatch.setattr(X, 'CTL', tmp_path / 'ctl')
    monkeypatch.setattr(X, 'BANNER', tmp_path / 'banner.txt')
    monkeypatch.setattr(X, 'MOVES', tmp_path / 'moves.txt')
    monkeypatch.setattr(X, 'NAMES', tmp_path / 'names.txt')
    monkeypatch.setattr(X, 'RESULT', tmp_path / 'result.txt')
    monkeypatch.setattr(X, 'WARRIORS', tmp_path / 'warriors')
    monkeypatch.setattr(X, 'poll_input', lambda: 'quit')

    def run(cmd):
        monkeypatch.setattr(X, 'ctl_mtime', 0)
        X.CTL.write_text(cmd)
        sc = X.Scene()
        X._main_loop(sc)
        return sc

    assert X.MUSIC[0] is False
    sc = run('music')
    assert X.MUSIC[0] is True and 'soundtrack on' in sc.events[-1]
    sc = run('music')
    assert X.MUSIC[0] is False and sc.events[-1] == 'soundtrack off'
    sc = run('music on')
    assert X.MUSIC[0] is True
    sc = run('music off')
    assert X.MUSIC[0] is False and sc.events[-1] == 'soundtrack off'
    # a disable while a player is running is a mute, not a queued intention
    X.PLAYER[:] = SLEEPER
    wav = tmp_path / 'track.wav'
    wav.write_bytes(b'RIFF')
    run('music on')
    proc = X.play_wav(wav)
    run('music off')
    assert proc.poll() is not None

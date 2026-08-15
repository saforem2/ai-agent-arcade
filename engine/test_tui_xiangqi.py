"""Tests for the production dot-seal xiangqi TUI.

The suite covers the responsive seal/face/void ladder, dot-matter board,
capture/replay effects and control-file behavior, while preserving the
original cold-start regression coverage: fen.txt is the referee's CURRENT-
   position cache (ref_xq.py rewrites it after every ply for its own tamper
   detection), not a starting position -- but the viewer used to read it as
   the replay base, so relaunching against any room with moves already
   played double-applied the whole log on top of an already-current
   position and crashed with IllegalMove on move 1. Fixed by always
   replaying from the true STARTING_FEN (build()/load_state()), same as
   ref_xq.py's own replay()/verify(). The second block of tests covers this,
   plus the ported names.txt staleness fix (refresh_names(), mirroring
   tui_dots.py's own fix for the identical bug class).

Run with: uv run --with pytest pytest test_tui_xiangqi.py
(no extra --with packages needed -- tui_xiangqi.py and xiangqi.py are both
pure stdlib, unlike tui_dots.py's `chess` dependency.)
"""
import os
import contextlib
import io
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest
import tui_xiangqi as X

ENGINE = Path(__file__).resolve().parent


def test_replay_dwell_env_parses_defaults_and_clamps(monkeypatch):
    monkeypatch.delenv('XQ_REPLAY_DWELL', raising=False)
    assert X._replay_dwell_seconds() == 0.7
    monkeypatch.setenv('XQ_REPLAY_DWELL', '1.25')
    assert X._replay_dwell_seconds() == 1.25
    monkeypatch.setenv('XQ_REPLAY_DWELL', '-2')
    assert X._replay_dwell_seconds() == 0.0
    monkeypatch.setenv('XQ_REPLAY_DWELL', '75')
    assert X._replay_dwell_seconds() == 60.0
    for value in ('inf', 'nan', '1e999'):
        monkeypatch.setenv('XQ_REPLAY_DWELL', value)
        assert X._replay_dwell_seconds() == 0.7
    monkeypatch.setenv('XQ_REPLAY_DWELL', 'invalid')
    assert X._replay_dwell_seconds() == 0.7


# ---------------------------------------------------------------------------
# fit_geometry() tier selection at real pane sizes -- the ladder the team
# lead asked to have reported, largest-that-fits chosen automatically.
# ---------------------------------------------------------------------------

def _tier_for(cols, rows):
    prev_size = X.SIZE
    X.SIZE = 'grand'
    try:
        X.fit_geometry(cols, rows)
        return X.CW, X.CH, min(X.SQW, X.SQH) - 2
    finally:
        X.SIZE = prev_size


def test_real_pane_113x53_selects_the_8_4_tier():
    """The measured production pane. (10,5) needs bh+3<=rows i.e. 54 rows;
    113x53 is one row short, so this must land on (8,4)/box14."""
    cw, ch, box = _tier_for(113, 53)
    assert (cw, ch) == (8, 4)
    assert box == 14


def test_wider_taller_pane_selects_the_10_5_tier():
    """Grand geometry includes the spectator rack in its fit budget."""
    cw, ch, box = _tier_for(140, 60)
    assert (cw, ch) == (10, 5)
    assert box == 18


def test_120_col_grand_reserves_room_for_the_rack():
    cw, ch, box = _tier_for(120, 56)
    assert (cw, ch, box) == (8, 4, 14)
    assert X.show_broadcast_rack(120) is True


def test_cramped_pane_falls_back_to_void_seal_geometry():
    """A cramped pane degrades to the xiangqi-native void-seal tier."""
    cw, ch, box = _tier_for(40, 26)
    assert box < 10
    assert X.render_tier(40) == 'seal'


# ---------------------------------------------------------------------------
# COLD-START CRASH (match-blocking, team lead's traceback 2026-08-11):
# fen.txt holds the referee's CURRENT position, not a starting position.
# These run in a genuinely fresh subprocess (not just an in-process call)
# because the bug's whole shape was "the state a freshly launched process
# builds at import/main() time," matching test_tui_dots.py's own pattern
# for the sibling names.txt bug below.
# ---------------------------------------------------------------------------

def run_probe(live, script):
    """Run `script` with tui_xiangqi imported as `X` and ARCADE_LIVE pointed
    at `live`, in a genuinely fresh process. Plain sys.executable (not the
    `uv run --with chess` subprocess tui_dots.py's tests need) -- tui_xiangqi
    and xiangqi are both pure stdlib."""
    full = (
        f"import sys; sys.path.insert(0, {str(ENGINE)!r})\n"
        "import tui_xiangqi as X\n"
        f"{script}"
    )
    return subprocess.run(
        [sys.executable, "-c", full],
        cwd=live, env={**os.environ, "ARCADE_LIVE": str(live)},
        capture_output=True, text=True,
    )


def test_cold_start_replays_moves_from_starting_fen_not_fen_txt(tmp_path):
    """The exact regression from the team lead's traceback: a room with one
    move already played, fen.txt holding the CURRENT position (exactly how
    ref_xq.py always leaves it -- it rewrites fen.txt to board.fen() after
    every ply, never to the starting position). A cold-start process must
    replay moves.txt from the true starting position and land on the same
    FEN the referee itself computed, not raise IllegalMove from replaying
    the log a second time on top of an already-current position."""
    (tmp_path / 'moves.txt').write_text('h2e2\n')
    (tmp_path / 'fen.txt').write_text(
        'rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C2C4/9/RNBAKABNR b - - 1 1\n')
    script = "board, seen = X.load_state()\nprint(seen)\nprint(board.fen())\n"
    r = run_probe(tmp_path, script)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert lines[0] == "['h2e2']"
    assert lines[1] == 'rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C2C4/9/RNBAKABNR b - - 1 1'


def test_cold_start_matches_a_live_updating_instance(tmp_path):
    """Direct equivalence check, in the language of the team lead's ask:
    a fresh cold-start process against a multi-move room must reach the
    exact same position as an instance that started at ply 0 and applied
    the moves one at a time as they arrived (the live-updating path,
    i.e. build(STARTING_FEN, ...) growing incrementally inside the running
    _main_loop)."""
    moves = ['h2e2', 'h9g7', 'b0c2', 'b9c7']
    (tmp_path / 'moves.txt').write_text('\n'.join(moves) + '\n')
    # fen.txt deliberately holds the CURRENT (not starting) position, as the
    # real referee always leaves it -- this must not perturb the cold start.
    live_board = X.build(X.STARTING_FEN, [])
    for mv in moves:
        live_board.push(mv)
    (tmp_path / 'fen.txt').write_text(live_board.fen() + '\n')

    script = "board, seen = X.load_state()\nprint(board.fen())\n"
    r = run_probe(tmp_path, script)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == live_board.fen()


def test_cold_start_tolerates_missing_fen_txt():
    """fen.txt is consistency-check-only now (see build()'s docstring) -- a
    cold start with no fen.txt at all (a fresh room before the referee's
    first write) must still replay cleanly, not require the file to exist."""
    board, seen = X.build(X.STARTING_FEN, []), []
    assert board.fen() == X.STARTING_FEN


def test_check_fen_consistency_never_raises_on_mismatch(tmp_path, capsys):
    """fen.txt disagreeing with the replayed log is the referee's tamper
    class to resolve (ref_xq.py resolve), not the viewer's -- the viewer
    must log a note and keep rendering the log-replayed position, never
    crash. Exercises check_fen_consistency() directly since it's a pure
    function of (FEN path, board)."""
    old_fen = X.FEN
    try:
        X.FEN = tmp_path / 'fen.txt'
        X.FEN.write_text('not a real fen at all\n')
        board = X.build(X.STARTING_FEN, [])
        X.check_fen_consistency(board)  # must not raise
        assert 'disagrees' in capsys.readouterr().err
    finally:
        X.FEN = old_fen


# ---------------------------------------------------------------------------
# names.txt staleness (ported from tui_dots.py's own fix for the identical
# bug class -- a viewer left running across a pairing change must not keep
# showing the old players forever).
# ---------------------------------------------------------------------------

def test_refresh_names_reads_names_txt(tmp_path):
    (tmp_path / 'names.txt').write_text('KIMI CODEX\n')
    r = run_probe(tmp_path, "X.refresh_names(); print(X.names)")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "{'r': 'KIMI', 'b': 'CODEX'}"


def test_refresh_names_picks_up_a_mid_run_rewrite(tmp_path):
    """The core regression: a viewer whose cache is already warm must still
    notice names.txt changing again later -- exactly what happens when
    `arcade start` deploys a fresh pairing under a viewer still running
    from the previous match."""
    (tmp_path / 'names.txt').write_text('KIMI CODEX\n')
    script = (
        "X.refresh_names(); first = dict(X.names)\n"
        "open('names.txt', 'w').write('GEMINI GROK\\n')\n"
        "X.refresh_names(); second = dict(X.names)\n"
        "print(first); print(second)\n"
    )
    r = run_probe(tmp_path, script)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert lines[0] == "{'r': 'KIMI', 'b': 'CODEX'}"
    assert lines[1] == "{'r': 'GEMINI', 'b': 'GROK'}"


def test_refresh_names_missing_file_keeps_last_known_good(tmp_path):
    (tmp_path / 'names.txt').write_text('KIMI CODEX\n')
    script = (
        "X.refresh_names(); first = dict(X.names)\n"
        "import os; os.remove('names.txt')\n"
        "X.refresh_names(); second = dict(X.names)\n"  # must not raise
        "print(first); print(second)\n"
    )
    r = run_probe(tmp_path, script)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert lines[0] == lines[1] == "{'r': 'KIMI', 'b': 'CODEX'}"


def test_refresh_names_malformed_content_keeps_last_known_good(tmp_path):
    (tmp_path / 'names.txt').write_text('KIMI CODEX\n')
    script = (
        "X.refresh_names(); first = dict(X.names)\n"
        "open('names.txt', 'w').write('ONLYONE\\n')\n"
        "X.refresh_names(); second = dict(X.names)\n"
        "print(first); print(second)\n"
    )
    r = run_probe(tmp_path, script)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert lines[0] == lines[1] == "{'r': 'KIMI', 'b': 'CODEX'}"


def test_render_picks_up_mid_run_names_change(tmp_path):
    """End-to-end through render() itself, not just refresh_names() -- proves
    the actual draw path reflects a mid-run rename."""
    (tmp_path / 'names.txt').write_text('KIMI CODEX\n')
    script = (
        "import io, contextlib\n"
        "board = X.build(X.STARTING_FEN, [])\n"
        "buf1 = io.StringIO()\n"
        "with contextlib.redirect_stdout(buf1): X.render(board)\n"
        "open('names.txt', 'w').write('GEMINI CODEX\\n')\n"
        "buf2 = io.StringIO()\n"
        "with contextlib.redirect_stdout(buf2): X.render(board)\n"
        "print('KIMI' in buf1.getvalue())\n"
        "print('GEMINI' in buf2.getvalue())\n"
        "print('KIMI' in buf2.getvalue())\n"
    )
    r = run_probe(tmp_path, script)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert lines == ["True", "True", "False"]


# ---------------------------------------------------------------------------
# Locked 2026-08-11 visual system: pitch-derived dot circles, CJK overlays,
# responsive tiers, river drift, and the real five-beat capture path.
# ---------------------------------------------------------------------------

def test_dot_circle_calibration_and_pitch_derived_radii():
    assert X.DOT_CIRCLE_K == 1.0
    old = X.SIZE
    X.SIZE = 'grand'
    try:
        X.fit_geometry(140, 60)
        assert X.disc_geometry() == (18, 8.4)
        X.fit_geometry(113, 53)
        assert X.disc_geometry() == (14, 6.4)
        X.fit_geometry(60, 35)
        assert X.disc_geometry() == (8, 3.4)
    finally:
        X.SIZE = old


def test_face_window_is_tiered_rounded_rectangle():
    cxd, pyr = 20, 40
    # cozy short-pane disc: no room for a well
    assert not any(X._face_window(x, y, cxd, pyr, 10)
                   for x in range(12, 29) for y in range(32, 49))
    # Grand well grows from the four-by-four-dot CJK cells and retains all
    # four quantized corner dots.
    assert X._face_window(cxd, pyr + 1, cxd, pyr, 14)
    for corner in ((cxd - 3, pyr - 1), (cxd - 3, pyr + 4),
                   (cxd + 2, pyr - 1), (cxd + 2, pyr + 4)):
        assert not X._face_window(*corner, cxd, pyr, 14)
    assert not X._face_window(cxd + 3, pyr, cxd, pyr, 14)
    # mid/large gets the wider 8x8 well
    assert X._face_window(cxd - 4, pyr, cxd, pyr, 18)
    assert not X._face_window(cxd - 4, pyr - 2, cxd, pyr, 18)


def test_final_disc_geometry_is_exactly_12_by_12_and_cozy_is_8_by_8():
    class Recorder:
        def __init__(self):
            self.dots = []
        def clear(self, *_):
            pass
        def purge_text_cell(self, *_):
            pass
        def dot(self, x, y, color, pri=3):
            self.dots.append((x, y, color, pri))
        def text(self, *_):
            pass

    old = X.SIZE
    try:
        X.SIZE = 'grand'
        X.fit_geometry(113, 53)
        grand = Recorder()
        X.draw_dot_circle(grand, 'K', 'r', 4, 9, effect='face_out')
        assert len({x for x, _, _, _ in grand.dots}) == 12
        assert len({y for _, y, _, _ in grand.dots}) == 12

        x0, y0 = X.px(0) - 0.5, X.py(0) + 1.5
        x1, y1 = X.px(8) - 0.5, X.py(9) + 1.5
        for elapsed in (0.1, 0.25, 0.5, 0.75, 0.9):
            eased = elapsed * elapsed * (3 - 2 * elapsed)
            center = X._travel_center(x0, y0, x1, y1, eased)
            sample = Recorder()
            X.draw_dot_circle(sample, 'K', 'r', 0, 0,
                              effect='face_out', center=center)
            assert len({x for x, _, _, _ in sample.dots}) == 12
            assert len({y for _, y, _, _ in sample.dots}) == 12

        X.SIZE = 'cozy'
        X.fit_geometry(140, 60)
        cozy = Recorder()
        X.draw_dot_circle(cozy, 'K', 'r', 4, 9, effect='face_out')
        assert len({x for x, _, _, _ in cozy.dots}) == 8
        assert len({y for _, y, _, _ in cozy.dots}) == 8
    finally:
        X.SIZE = old


def test_flying_disc_static_handoff_is_grid_identical():
    old = X.SIZE
    X.SIZE = 'grand'
    try:
        X.fit_geometry(113, 53)
        static, handoff = X.Grid(), X.Grid()
        center = (X.px(4) - 0.5, X.py(9) + 1.5)
        X.draw_dot_circle(static, 'K', 'r', 4, 9)
        X.draw_dot_circle(handoff, 'K', 'r', 4, 9, center=center)
        assert handoff.b == static.b
        assert handoff.f == static.f
        assert handoff.p == static.p
        assert handoff.ch == static.ch
        assert handoff.cont == static.cont
    finally:
        X.SIZE = old


def test_flying_disc_purges_overlapped_text_and_wide_continuations():
    old = X.SIZE
    X.SIZE = 'grand'
    try:
        X.fit_geometry(113, 53)
        g = X.Grid()
        face_x, face_y = X.px(4) // 2 - 1, X.py(9) // 4
        g.text(face_x - 1, face_y, '將', X.INK_B, X.WINDOW_BG, True)
        g.text(face_x, face_y - 1, '楚', X.GOLD)
        assert (face_x, face_y) in g.cont
        center = (X.px(4) - 0.5, X.py(9) + 1.5)
        X.draw_dot_circle(g, 'K', 'r', 4, 9, center=center)
        assert (face_x - 1, face_y) not in g.ch
        assert (face_x, face_y - 1) not in g.ch
        assert g.ch[(face_x, face_y)][0] == '帥'
        assert (face_x + 1, face_y) in g.cont
    finally:
        X.SIZE = old


def test_disc_face_and_particle_centers_share_face_row_midline(monkeypatch):
    old = X.SIZE
    X.SIZE = 'grand'
    try:
        X.fit_geometry(113, 53)
        g = X.Grid()
        X.draw_dot_circle(g, 'K', 'b', 4, 9)
        center_x, center_y = X.px(4) - 0.5, X.py(9) + 1.5
        assert center_y == (X.py(9) // 4) * 4 + 1.5
        assert (X.px(4) // 2 - 1, X.py(9) // 4) in g.ch

        monkeypatch.setattr(X.random, 'uniform', lambda a, b: a)
        X.particles.clear()
        X.spawn_debris((9, 4), 'b', n=1, now=12.0)
        assert X.particles[0][:2] == [center_x, center_y]
    finally:
        X.particles.clear()
        X.SIZE = old


def test_wide_cjk_text_owns_exactly_two_terminal_cells():
    g = X.Grid()
    g.text(2, 3, '將', X.INK_B, X.WINDOW_BG, True)
    assert g.ch[(2, 3)] == ('將', X.INK_B, X.WINDOW_BG, True)
    assert (3, 3) in g.cont
    assert g.b[3][2] == g.b[3][3] == 0


def test_responsive_piece_ladder_and_size_override():
    old = X.SIZE
    try:
        X.SIZE = 'grand'
        X.fit_geometry(113, 53)
        assert X.render_tier(113) == 'disc'
        assert X.show_broadcast_rack(113)
        X.fit_geometry(80, 45)
        assert (X.CW, X.CH) == (6, 3)
        assert X.render_tier(80) == 'disc'
        assert not X.show_broadcast_rack(80)
        X.fit_geometry(29, 22)
        assert X.render_tier(29) == 'seal'

        X.SIZE = 'cozy'
        X.fit_geometry(140, 60)
        assert (X.CW, X.CH) == (6, 3)
        assert X.render_tier(140) == 'disc'
        assert not X.show_broadcast_rack(140)
    finally:
        X.SIZE = old


def test_fly_is_ignored_at_seal_tier_without_hiding_source(monkeypatch):
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fallback: os.terminal_size((29, 22)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'SIZE', 'grand')
    X.fit_geometry(29, 22)
    board = X.XiangqiBoard()
    src, dst = X.parse_iccs('h2e2')
    piece = board.board[src[0]][src[1]]
    center = X._travel_center(
        X.px(src[1]) - 0.5, X.py(src[0]) + 1.5,
        X.px(dst[1]) - 0.5, X.py(dst[0]) + 1.5, 0.5)
    circle_calls, seal_squares = [], []
    original_circle = X.draw_dot_circle
    original_seal = X.draw_void_seal

    def tracked_circle(*args, **kwargs):
        circle_calls.append(kwargs.get('center'))
        return original_circle(*args, **kwargs)

    def tracked_seal(g, sym, color, f, r, effect=None):
        seal_squares.append((r, f))
        return original_seal(g, sym, color, f, r, effect)

    monkeypatch.setattr(X, 'draw_dot_circle', tracked_circle)
    monkeypatch.setattr(X, 'draw_void_seal', tracked_seal)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        X.render(board, fly=(piece, center[0], center[1], src))
    plain = ANSI_RE.sub('', out.getvalue())
    assert X.render_tier(29) == 'seal'
    assert circle_calls == []
    assert src in seal_squares
    assert not any(face in plain for face in set(X.FACE.values()))


def test_river_rows_drift_in_opposite_cadence(monkeypatch):
    old_size, old_reduced = X.SIZE, X.REDUCED_MOTION
    X.SIZE, X.REDUCED_MOTION = 'grand', False
    try:
        X.fit_geometry(113, 53)
        first, second = X.Grid(), X.Grid()
        X.draw_river(first, 0.0)
        X.draw_river(second, 0.5)
        assert first.b != second.b
        monkeypatch.setattr(X, 'REDUCED_MOTION', True)
        static_a, static_b = X.Grid(), X.Grid()
        X.draw_river(static_a, 0.0)
        X.draw_river(static_b, 20.0)
        assert static_a.b == static_b.b
    finally:
        X.SIZE, X.REDUCED_MOTION = old_size, old_reduced


def test_v2_k3_seal_has_solid_bone_dots_no_rim_and_fixed_window():
    old = X.SIZE
    X.SIZE = 'grand'
    try:
        X.fit_geometry(113, 53)
        g = X.Grid()
        X.draw_dot_circle(g, 'K', 'r', 4, 9)
        dot_colors = {color for row in g.f for color in row if color is not None}
        assert dot_colors == {X.BONE}
        face = g.ch[(X.px(4) // 2 - 1, X.py(9) // 4)]
        assert face == ('帥', (255, 100, 60), (14, 18, 24), True)
        assert X.INK_B == (246, 240, 226)
    finally:
        X.SIZE = old


def test_palace_and_river_are_dot_matter_not_plate_fills():
    old = X.SIZE
    X.SIZE = 'grand'
    try:
        X.fit_geometry(113, 53)
        plate = X.board_plate()
        assert {color for row in plate for color in row} == {X.SQD}
        g = X.Grid()
        X.draw_field(g, 0.0)
        X.draw_river(g, 0.0)
        river_top, river_bottom = sorted((X.py(5) // 4, X.py(4) // 4))
        river_colors = {g.f[cy][cx]
                        for cy in range(river_top + 1, river_bottom)
                        for cx in range(X.px(0) // 2, X.px(8) // 2 + 1)}
        assert X.RIVER_BG in river_colors
        assert X.RIVER in river_colors
    finally:
        X.SIZE = old


CAPTURE_FEN = '4k4/9/9/9/4p4/9/9/9/p8/R3K4 w - - 0 1'


def _animation_clock(monkeypatch):
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


def _track_board_pushes(monkeypatch):
    pushes = []
    original_push = X.XiangqiBoard.push

    def tracked_push(board, move):
        pushes.append(move)
        return original_push(board, move)

    monkeypatch.setattr(X.XiangqiBoard, 'push', tracked_push)
    return pushes


def test_capture_animation_wires_all_five_beats_and_debris(monkeypatch):
    board = X.XiangqiBoard.from_fen(CAPTURE_FEN)
    frames, debris = [], []
    monkeypatch.setattr(X, 'REDUCED_MOTION', False)
    clock = _animation_clock(monkeypatch)
    monkeypatch.setattr(
        X, 'render',
        lambda board, status_extra='', event=None, fly=None: frames.append(
            (event['phase'] if event else None, fly)))
    monkeypatch.setattr(
        X, 'spawn_debris',
        lambda square, color, n=30, now=None: debris.append(
            (square, color, now)))
    X.move_list = []
    action = X.animate_move(board, 'a0a1')
    assert action is None
    phases = []
    for phase, _fly in frames:
        if not phases or phase != phases[-1]:
            phases.append(phase)
    assert phases == ['face_out', 'pinch', 'hidden', 'field', 'settle']
    for phase in ('face_out', 'pinch', 'hidden', 'field'):
        assert any(seen == phase and fly is not None for seen, fly in frames)
    assert len(debris) == 1
    assert debris[0][:2] == ((1, 0), 'b')
    assert 0.60 <= debris[0][2] / 0.5 < 0.75
    assert debris[0][2] <= clock.now
    assert board.board[0][0] is None
    assert board.board[1][0] == 'R'
    assert X.move_list == ['a0a1']


def test_travel_animation_pushes_move_exactly_once(monkeypatch):
    board = X.XiangqiBoard()
    move = 'b0c2'
    src, dst = X.parse_iccs(move)
    source_center = (X.px(src[1]) - 0.5, X.py(src[0]) + 1.5)
    target_center = (X.px(dst[1]) - 0.5, X.py(dst[0]) + 1.5)
    frames = []
    clock = _animation_clock(monkeypatch)
    pushes = _track_board_pushes(monkeypatch)
    monkeypatch.setattr(X, 'REDUCED_MOTION', False)
    monkeypatch.setattr(X, 'move_list', [])
    monkeypatch.setattr(
        X, 'render',
        lambda board, status_extra='', event=None, fly=None: frames.append(fly))
    action = X.animate_move(board, move)
    flyers = [fly for fly in frames if fly is not None]
    assert action is None
    assert pushes == [move]
    assert len(flyers) > 2
    assert flyers[0][1:3] == source_center
    assert flyers[-1][1:3] == target_center
    assert 0.033 in clock.sleeps
    assert board.board[src[0]][src[1]] is None
    assert board.board[dst[0]][dst[1]] == 'N'


def test_interrupt_during_travel_still_pushes_move_exactly_once(monkeypatch):
    board = X.XiangqiBoard()
    move = 'h2e2'
    src, dst = X.parse_iccs(move)
    frames = []
    actions = iter((None, 'quit'))
    clock = _animation_clock(monkeypatch)
    pushes = _track_board_pushes(monkeypatch)
    monkeypatch.setattr(X, 'REDUCED_MOTION', False)
    monkeypatch.setattr(X, 'move_list', [])
    monkeypatch.setattr(
        X, 'render',
        lambda board, status_extra='', event=None, fly=None: frames.append(fly))
    monkeypatch.setattr(X, 'poll_input', lambda: next(actions))
    monkeypatch.setattr(X, 'ctl_changed', lambda: False)
    action = X.animate_move(board, move, interruptible=True)
    assert action == 'quit'
    assert pushes == [move]
    assert len([fly for fly in frames if fly is not None]) == 1
    assert clock.sleeps == [0.033]
    assert board.board[src[0]][src[1]] is None
    assert board.board[dst[0]][dst[1]] == 'C'


def test_ctl_change_during_travel_still_pushes_move_exactly_once(monkeypatch):
    board = X.XiangqiBoard()
    move = 'h2e2'
    src, dst = X.parse_iccs(move)
    frames = []
    ctl_checks = iter((False, True))
    clock = _animation_clock(monkeypatch)
    pushes = _track_board_pushes(monkeypatch)
    monkeypatch.setattr(X, 'REDUCED_MOTION', False)
    monkeypatch.setattr(X, 'move_list', [])
    monkeypatch.setattr(
        X, 'render',
        lambda board, status_extra='', event=None, fly=None: frames.append(fly))
    monkeypatch.setattr(X, 'poll_input', lambda: None)
    monkeypatch.setattr(X, 'ctl_changed', lambda: next(ctl_checks))
    action = X.animate_move(board, move, interruptible=True)
    assert action == 'ctl'
    assert pushes == [move]
    assert len([fly for fly in frames if fly is not None]) == 1
    assert clock.sleeps == [0.033]
    assert board.board[src[0]][src[1]] is None
    assert board.board[dst[0]][dst[1]] == 'C'


def test_reduced_motion_skips_travel_and_pushes_move_exactly_once(monkeypatch):
    board = X.XiangqiBoard()
    move = 'h2e2'
    src, dst = X.parse_iccs(move)
    frames = []
    clock = _animation_clock(monkeypatch)
    pushes = _track_board_pushes(monkeypatch)
    monkeypatch.setattr(X, 'REDUCED_MOTION', True)
    monkeypatch.setattr(X, 'move_list', [])
    monkeypatch.setattr(
        X, 'render',
        lambda board, status_extra='', event=None, fly=None: frames.append(fly))
    action = X.animate_move(board, move, interruptible=True)
    assert action is None
    assert pushes == [move]
    assert frames == [None]
    assert clock.sleeps == []
    assert board.board[src[0]][src[1]] is None
    assert board.board[dst[0]][dst[1]] == 'C'


def test_illegal_move_raises_after_one_push_attempt_without_mutating_board(
        monkeypatch):
    board = X.XiangqiBoard()
    move = 'a0a0'
    before = board.fen()
    pushes = _track_board_pushes(monkeypatch)
    with pytest.raises(X.IllegalMove):
        X.animate_move(board, move)
    assert pushes == [move]
    assert board.fen() == before


def test_reduced_motion_applies_capture_without_debris(monkeypatch):
    board = X.XiangqiBoard.from_fen(CAPTURE_FEN)
    renders, debris = [], []
    monkeypatch.setattr(X, 'REDUCED_MOTION', True)
    monkeypatch.setattr(X, 'render', lambda *a, **k: renders.append(k.get('event')))
    monkeypatch.setattr(X, 'spawn_debris', lambda *a, **k: debris.append(a))
    X.move_list = []
    X.animate_move(board, 'a0a1')
    assert renders == [None]
    assert debris == []
    assert board.board[1][0] == 'R'


def test_capture_rack_reports_real_faces_for_each_capturing_side():
    board = X.XiangqiBoard.from_fen(CAPTURE_FEN)
    board.push('a0a1')
    captured = X.captured_piece_faces(board)
    assert '卒' in captured['r']
    rows = ANSI_RE.sub('', '\n'.join(X._rack_rows(board, False, False)))
    assert 'CAPTURES' in rows
    assert 'RED   ' in rows and '卒' in rows
    assert 'STATUS' in rows


def test_replay_all_propagates_live_interrupt_and_resolves_end_position(monkeypatch):
    moves = ['b2b9']
    monkeypatch.setattr(X, 'render', lambda *a, **k: None)
    monkeypatch.setattr(X.time, 'sleep', lambda _: None)
    monkeypatch.setattr(X, 'ctl_changed', lambda: False)
    monkeypatch.setattr(X, 'animate_move', lambda *a, **k: 'quit')
    board, action = X.replay_all(X.STARTING_FEN, moves)
    assert action == 'quit'
    assert board.fen() == X.build(X.STARTING_FEN, moves).fen()


def test_replay_dwell_action_returns_full_position_and_move_list(monkeypatch):
    moves = ['h2e2', 'h9g7']
    sleeps = []
    monkeypatch.setattr(X, 'REPLAY_DWELL', 0.05)
    monkeypatch.setattr(X, 'REDUCED_MOTION', True)
    monkeypatch.setattr(X, 'move_list', [])
    monkeypatch.setattr(X, 'render', lambda *a, **k: None)
    monkeypatch.setattr(X.time, 'sleep', sleeps.append)
    monkeypatch.setattr(X, 'read_input', lambda: 'replay')
    monkeypatch.setattr(X, 'ctl_changed', lambda: False)
    board, action = X.replay_all(X.STARTING_FEN, moves)
    assert action == 'replay'
    assert X.move_list == moves
    assert board.fen() == X.build(X.STARTING_FEN, moves).fen()
    assert sleeps == [0.5, 0.05]


def test_replay_dwell_ctl_change_returns_full_position(monkeypatch):
    moves = ['h2e2', 'h9g7']
    sleeps = []
    ctl_checks = iter((False, True))
    monkeypatch.setattr(X, 'REPLAY_DWELL', 0.05)
    monkeypatch.setattr(X, 'REDUCED_MOTION', True)
    monkeypatch.setattr(X, 'move_list', [])
    monkeypatch.setattr(X, 'render', lambda *a, **k: None)
    monkeypatch.setattr(X.time, 'sleep', sleeps.append)
    monkeypatch.setattr(X, 'read_input', lambda: None)
    monkeypatch.setattr(X, 'ctl_changed', lambda: next(ctl_checks))
    board, action = X.replay_all(X.STARTING_FEN, moves)
    assert action is None
    assert board.fen() == X.build(X.STARTING_FEN, moves).fen()
    assert sleeps == [0.5, 0.05]


def test_replay_dwell_occurs_between_plies_only(monkeypatch):
    moves = ['h2e2', 'h9g7', 'b0c2', 'b9c7']
    sleeps = []
    monkeypatch.setattr(X, 'REPLAY_DWELL', 0.05)
    monkeypatch.setattr(X, 'REDUCED_MOTION', True)
    monkeypatch.setattr(X, 'move_list', [])
    monkeypatch.setattr(X, 'render', lambda *a, **k: None)
    monkeypatch.setattr(X.time, 'sleep', sleeps.append)
    monkeypatch.setattr(X, 'read_input', lambda: None)
    monkeypatch.setattr(X, 'ctl_changed', lambda: False)
    board, action = X.replay_all(X.STARTING_FEN, moves)
    assert action is None
    assert board.fen() == X.build(X.STARTING_FEN, moves).fen()
    assert sleeps == [0.5] + [0.05] * (len(moves) - 1)


def test_do_replay_restarts_on_replay_action(monkeypatch):
    board = X.XiangqiBoard()
    outcomes = iter(((board, 'replay'), (board, None)))
    calls = []
    monkeypatch.setattr(X, 'replay_all',
                        lambda fen, moves, tail: calls.append(tail) or next(outcomes))
    monkeypatch.setattr(X, 'read', lambda path: '')
    result, action = X.do_replay(3)
    assert (result, action) == (board, None)
    assert calls == [3, None]


def test_size_control_persists_pitch_vocabulary_and_clears_particles(tmp_path,
                                                                    monkeypatch):
    old = X.SIZE
    monkeypatch.setattr(X, 'D', tmp_path)
    X.SIZE = 'grand'
    X.particles[:] = [[1]]
    try:
        assert X.set_size('cozy') is True
        assert (tmp_path / 'size.txt').read_text() == 'cozy'
        assert X.particles == []
        assert X.set_size('cozy') is False
        assert X.set_size('tiny') is False
    finally:
        X.SIZE = old


def test_ctl_size_and_banner_paths_apply_in_main_loop(tmp_path, monkeypatch):
    ctl = tmp_path / 'ctl'
    banner = tmp_path / 'banner.txt'
    monkeypatch.setattr(X, 'D', tmp_path)
    monkeypatch.setattr(X, 'CTL', ctl)
    monkeypatch.setattr(X, 'BANNER', banner)
    monkeypatch.setattr(X, 'poll_input', lambda: 'quit')
    monkeypatch.setattr(X, 'ctl_mtime', 0)
    old = X.SIZE
    try:
        X.SIZE = 'grand'
        ctl.write_text('size cozy')
        X._main_loop(X.XiangqiBoard(), [])
        assert X.SIZE == 'cozy'
        assert (tmp_path / 'size.txt').read_text() == 'cozy'

        monkeypatch.setattr(X, 'ctl_mtime', 0)
        ctl.write_text('banner MATCH-001 · HUMAN TABLE')
        X._main_loop(X.XiangqiBoard(), [])
        assert banner.read_text() == 'MATCH-001 · HUMAN TABLE'
    finally:
        X.SIZE = old


def test_obsolete_mode_control_is_removed_from_contract():
    assert not hasattr(X, 'MODE')
    assert 'mode dots|glyph' not in (X.__doc__ or '')


ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[ -/]*[@-~]')


def _visible_width(text):
    return sum(2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1
               for ch in ANSI_RE.sub('', text))


def test_grand_render_has_native_faces_real_footer_and_never_wraps(monkeypatch):
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fallback: os.terminal_size((113, 53)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'SIZE', 'grand')
    X.move_list = []
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        X.render(X.XiangqiBoard())
    rendered = out.getvalue()
    plain = ANSI_RE.sub('', rendered)
    assert '帥' in plain and '將' in plain and '楚' in plain and '漢' in plain
    assert 'BROADCAST' in plain
    assert 'river current' not in plain.lower()
    assert 'spine sealed' not in plain.lower()
    assert max(_visible_width(line) for line in rendered.splitlines()) <= 113


def test_header_is_live_match_identity_without_turn_or_design_narration(
        tmp_path, monkeypatch):
    names_file = tmp_path / 'names.txt'
    chat_file = tmp_path / 'chat.log'
    names_file.write_text('KIMI CODEX\n')
    chat_file.write_text('0\tARCADE\tmatch-001 opens: KIMI (Red) vs CODEX (Black).\n')
    monkeypatch.setattr(X, 'NAMES', names_file)
    monkeypatch.setattr(X, 'CHAT', chat_file)
    monkeypatch.setattr(X, 'MATCH_JSON', tmp_path / 'match.json')
    monkeypatch.setattr(X, 'BANNER', tmp_path / 'banner.txt')
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fallback: os.terminal_size((113, 53)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'SIZE', 'grand')
    X._fcache.clear()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        X.render(X.XiangqiBoard())
    plain = ANSI_RE.sub('', out.getvalue())
    assert 'XIANGQI · MATCH-001 · KIMI (red) vs CODEX (black)' in plain
    assert 'FIELD / RIVER / SEAL' not in plain
    assert 'traditional faces' not in plain
    assert 'no engine evaluation' not in plain
    assert 'opening position' not in plain
    assert 'TO MOVE' not in plain.splitlines()[2].upper()
    assert plain.count('KIMI to move') == 1


def test_header_has_honest_placeholder_before_live_identity_exists(
        tmp_path, monkeypatch):
    monkeypatch.setattr(X, 'NAMES', tmp_path / 'names.txt')
    monkeypatch.setattr(X, 'CHAT', tmp_path / 'chat.log')
    monkeypatch.setattr(X, 'MATCH_JSON', tmp_path / 'match.json')
    monkeypatch.setattr(X, 'BANNER', tmp_path / 'banner.txt')
    monkeypatch.setitem(X.names, 'r', 'TBD')
    monkeypatch.setitem(X.names, 'b', 'TBD')
    X._fcache.clear()
    assert X.live_match_id() == 'MATCH-???'


def test_grand_footer_keeps_replay_control_and_floor_clips_long_names(
        tmp_path, monkeypatch):
    names_file = tmp_path / 'names.txt'
    names_file.write_text('EXTRAORDINARILYLONGRED EXTRAORDINARILYLONGBLACK\n')
    monkeypatch.setattr(X, 'NAMES', names_file)
    X._fcache.clear()
    monkeypatch.setattr(X, 'INPUT_ENABLED', True)
    monkeypatch.setattr(X, 'SIZE', 'grand')

    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fallback: os.terminal_size((113, 53)))
    grand = io.StringIO()
    with contextlib.redirect_stdout(grand):
        X.render(X.XiangqiBoard())
    assert X.BTN_TEXT in ANSI_RE.sub('', grand.getvalue())
    assert X._btn_bounds is not None

    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fallback: os.terminal_size((29, 22)))
    floor = io.StringIO()
    with contextlib.redirect_stdout(floor):
        X.render(X.XiangqiBoard())
    assert X.BTN_TEXT not in ANSI_RE.sub('', floor.getvalue())
    assert X._btn_bounds is None
    assert max(_visible_width(line) for line in floor.getvalue().splitlines()) <= 29


def test_check_flash_is_above_piece_fill_at_priority_seven(monkeypatch):
    priorities = []
    original_dot = X.Grid.dot

    def tracking_dot(self, x, y, color, pri=3):
        if pri == X.CHECK_PRI:
            priorities.append(pri)
        return original_dot(self, x, y, color, pri)

    monkeypatch.setattr(X.Grid, 'dot', tracking_dot)
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fallback: os.terminal_size((87, 53)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'SIZE', 'grand')
    board = X.XiangqiBoard.from_fen(
        '4k4/9/9/9/4r4/9/9/9/9/4K4 w - - 0 1')
    with contextlib.redirect_stdout(io.StringIO()):
        X.render(board)
    assert priorities
    assert set(priorities) == {7}


def test_banner_survives_when_vertical_budget_allows(tmp_path, monkeypatch):
    banner = tmp_path / 'banner.txt'
    banner.write_text('MATCH-001 · FIRST XIANGQI TABLE')
    monkeypatch.setattr(X, 'BANNER', banner)
    X._fcache.clear()
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fallback: os.terminal_size((113, 53)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'SIZE', 'grand')
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        X.render(X.XiangqiBoard())
    assert 'MATCH-001 · FIRST XIANGQI TABLE' in ANSI_RE.sub('', out.getvalue())


def test_floor_render_uses_void_seals_and_never_wraps(monkeypatch):
    monkeypatch.setattr(X.shutil, 'get_terminal_size',
                        lambda fallback: os.terminal_size((29, 22)))
    monkeypatch.setattr(X, 'INPUT_ENABLED', False)
    monkeypatch.setattr(X, 'SIZE', 'grand')
    X.move_list = []
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        X.render(X.XiangqiBoard())
    rendered = out.getvalue()
    plain = ANSI_RE.sub('', rendered)
    assert '帥' not in plain and '將' not in plain
    assert max(_visible_width(line) for line in rendered.splitlines()) <= 29

"""Tests for the Core War broadcast recorder (record_cw.py).

The TIMELINE is the contract: a recording is only worth making if the picture
and the sound were computed from the same clock, so these tests pin that the
extracted times come from `tui_corewar.py`'s own pacing (not a copy of it),
that two runs of one match are identical down to the frame bytes, and that
the signature moment — absolute silence across the elimination hitstop —
survives into the samples.

The audio DSP itself is covered lightly (shape, length, peak, the rate cap):
it is a matter of taste that a test cannot hold, whereas a timeline that
drifts is a bug nobody notices until the master is watched.

Run with: uv run --with pytest --with numpy --with pillow pytest test_record_cw.py
(the timeline half needs neither numpy nor Pillow and runs under the plain
engine suite; the synthesis and frame halves skip without them.)
"""
import sys
from pathlib import Path

import pytest

import corewar
import record_cw as REC
import tui_corewar as X

ENGINE = Path(__file__).resolve().parent


def build_room(tmp_path, seeds=(7,), a_src=None, b_src=None):
    """A referee-shaped room: transcript, warriors, names."""
    a_src = a_src or corewar.IMP
    b_src = b_src or corewar.DWARF
    (tmp_path / 'warriors').mkdir(exist_ok=True)
    (tmp_path / 'warriors' / 'A.red').write_text(a_src)
    (tmp_path / 'warriors' / 'B.red').write_text(b_src)
    (tmp_path / 'names.txt').write_text('ERNIE QWEN\n')
    lines = [f'LOAD A {corewar.sha256_warrior(a_src)}',
             f'LOAD B {corewar.sha256_warrior(b_src)}']
    for i, seed in enumerate(seeds, 1):
        b = corewar.Battle(corewar.parse_warrior(a_src),
                           corewar.parse_warrior(b_src), seed=seed)
        r = b.run()
        out = X.score_of(r)
        lines.append(f'ROUND {i} seed={seed} off={b.off_a},{b.off_b}')
        lines.append(f'ROUND {i} OUT {out} cycles={r.cycles}')
    (tmp_path / 'moves.txt').write_text('\n'.join(lines) + '\n')
    return tmp_path


@pytest.fixture
def kill_room(tmp_path):
    """Seed 7 is the suite's kill round: the dwarf kills the imp at 395."""
    return build_room(tmp_path, seeds=(7,))


# ---------------------------------------------------------------------------
# the timeline is the contract
# ---------------------------------------------------------------------------

def test_extraction_leaves_the_renderer_exactly_as_it_found_it(kill_room):
    """The recorder borrows the pane's own module. If it left the clock, the
    hooks or the bus paths pointing somewhere else, every test after it in
    the session would be running against a different room."""
    before = {k: getattr(X, k) for k in
              ('D', 'MOVES', 'WARRIORS', 'time', 'FRAME_HOOK', 'EVENT_HOOK',
               'REDUCED_MOTION', 'INPUT_ENABLED')}
    names_before = dict(X.names)
    REC.extract(kill_room)
    for k, v in before.items():
        assert getattr(X, k) is v or getattr(X, k) == v, k
    assert X.names == names_before


def test_timeline_times_come_from_the_tui_pacing(kill_room):
    """Not a copy of the formulas — the real beats, in order, with the real
    gaps between them. The elimination is followed by its hitstop plus the
    full cooling sweep before the verdict is allowed to speak, and the round
    holds the verdict for VERDICT_S before the match ends."""
    tl = REC.extract(kill_room)
    kinds = [k for _t, k, _a, _w, _x in tl.events]
    assert kinds[0] == 'round-cut'
    assert 'load-in' in kinds and 'elimination' in kinds
    assert kinds[-1] == 'match-end'
    times = [t for t, *_ in tl.events]
    assert times == sorted(times)                    # a clock never goes back

    cut = tl.of('round-cut')[0]
    loads = tl.of('load-in')
    assert loads[0][0] == pytest.approx(cut[0], abs=1e-6)
    # the two sides land one beat apart, inside the load-in budget
    assert 0 < loads[1][0] - loads[0][0] < X.LOADIN_S

    elim = tl.of('elimination')[0]
    verdict = tl.of('verdict')[0]
    # the freeze is spent inside the beat's own window, so hitstop + sweep is
    # the whole elimination and the audio decay ends when the picture's does
    assert elim[4]['hitstop'] == pytest.approx(X.HITSTOP_S)
    assert elim[4]['hitstop'] + elim[4]['sweep'] == pytest.approx(X.ELIM_S)
    gap = verdict[0] - elim[0]
    assert gap >= X.ELIM_S - 1.0 / X.FPS
    assert gap <= X.ELIM_S + 2.0 / X.FPS
    end = tl.of('match-end')[0]
    assert end[0] - verdict[0] == pytest.approx(X.VERDICT_S, abs=2 / X.FPS)


def test_every_bomb_is_on_the_timeline_not_just_the_drawn_ones(kill_room):
    """The plate queue is FX_CAP-bounded and REDUCED_MOTION-gated because it
    is a picture. A soundtrack built from it would be missing most of a
    bombing run, so the timeline comes off its own hook."""
    tl = REC.extract(kill_room)
    bombs = tl.of('bomb')
    assert len(bombs) > X.FX_CAP * 2
    assert all(w == 1 for _t, _k, _a, w, _x in bombs)     # the dwarf bombs
    assert tl.of('first-blood')[0][0] <= bombs[0][0]


def test_frames_and_events_share_one_clock(kill_room):
    """The sync guarantee, stated as a test: every event time is also a frame
    time, because the event was recorded during the frame that drew it."""
    tl = REC.extract(kill_room)
    frame_times = {round(t, 9) for t, _a in tl.frames}
    for t, kind, _a, _w, _x in tl.events:
        if kind in ('round-cut', 'load-in', 'match-end'):
            continue            # beats announced as a span opens, not drawn
        assert round(t, 9) in frame_times, (kind, t)


def test_timeline_is_byte_identical_across_runs(kill_room):
    """Determinism law: same transcript, same broadcast. Frame TEXT is
    compared, not just times — the pixels come from these bytes."""
    a, b = REC.extract(kill_room), REC.extract(kill_room)
    assert a.events == b.events
    assert a.metrics == b.metrics
    assert a.duration == b.duration
    assert [t for t, _x in a.frames] == [t for t, _x in b.frames]
    assert [x for _t, x in a.frames] == [x for _t, x in b.frames]


def test_frames_are_whole_rendered_panes(kill_room):
    """Each captured frame is one complete `render()` write — the recording
    is the pane's own output, never a screenshot of it."""
    tl = REC.extract(kill_room)
    assert len(tl.frames) > 100
    for t, text in tl.frames[:20]:
        assert text.startswith('\x1b[H')
        assert text.count('\x1b[H') == 1
        assert 'ERNIE' in text and 'QWEN' in text
        assert sum(1 for ch in text if 0x2800 <= ord(ch) <= 0x28FF) >= 1000


def test_a_full_tie_round_stays_inside_the_broadcast_budget(tmp_path):
    room = build_room(tmp_path, seeds=(1,))
    tl = REC.extract(room)
    assert tl.of('verdict')[0][4]['out'] == 'tie'
    assert tl.duration <= 90.0 + X.VERDICT_S + X.WASH_S + 2.0


def test_beat_is_free_when_nobody_is_listening():
    """EVENT_HOOK is None in every normal run; the seam must cost nothing and
    change nothing."""
    assert X.EVENT_HOOK is None
    X.beat('bomb', 0, 0, 0.0)                # must not raise
    seen = []
    X.EVENT_HOOK = lambda *a: seen.append(a)
    try:
        X.beat('bomb', 12, 1, 3.5, queue=8)
    finally:
        X.EVENT_HOOK = None
    assert seen == [('bomb', 12, 1, 3.5, {'queue': 8})]


def test_busiest_window_finds_the_dense_stretch(kill_room):
    tl = REC.extract(kill_room)
    start = REC.busiest_window(tl, span=5.0)
    n_here = sum(1 for t, *_ in tl.events if start <= t < start + 5.0)
    for probe in (0.0, tl.duration - 5.0):
        n_there = sum(1 for t, *_ in tl.events if probe <= t < probe + 5.0)
        assert n_here >= n_there


# ---------------------------------------------------------------------------
# synthesis (numpy) — shape, level, and the one moment that must be silent
# ---------------------------------------------------------------------------

def _np():
    return pytest.importorskip('numpy')


def test_audio_length_level_and_determinism(kill_room):
    np = _np()
    tl = REC.extract(kill_room)
    a = REC.synthesize(tl)
    b = REC.synthesize(tl)
    assert a.shape == (int(tl.duration * REC.SR) + 1, 2)
    assert np.array_equal(a, b)                    # no RNG anywhere
    peak = float(np.abs(a).max())
    assert 0.5 < peak <= 1.0                       # mastered, not clipped flat
    rms = float(np.sqrt((a ** 2).mean()))
    assert 0.02 < rms < 0.35                       # sane for laptop speakers


def test_the_hitstop_is_absolute_silence(kill_room):
    """The signature moment. Not ducked, not faded — the room stops."""
    np = _np()
    tl = REC.extract(kill_room)
    a = REC.synthesize(tl)
    t, _k, _addr, _w, extra = tl.of('elimination')[0]
    hs = extra['hitstop']
    assert hs > 0

    def peak(lo, hi):
        return float(np.abs(a[int(lo * REC.SR):int(hi * REC.SR)]).max())

    assert peak(t - 0.25, t - 0.01) > 0.05         # the room was full
    assert peak(t + 0.005, t + hs - 0.005) == 0.0  # and then it was not
    assert peak(t + hs, t + hs + 0.35) > 0.2       # the sub lands after


# (The loser's decay moved to test_score_cw.py with the track system: v2
# mutes the loser's whole BUS rather than its side of the stereo field, so
# the measurement is on the bus and not on L/R — and it now also checks the
# loser comes back for the next round.)


def test_bombs_no_longer_make_a_sound_of_their_own(kill_room):
    """v1 played one hit per bomb behind a rate cap, and the verdict was
    "borderline noise". v2 crossed the sonification line cleanly rather than
    compromising at a cap: bombs vote for a slot in a fixed pattern, and the
    grid decides when anything sounds. The law is pinned in test_score_cw.py;
    this holds the door shut behind it."""
    pytest.importorskip('numpy')
    import score_cw
    assert not hasattr(REC, 'BOMB_RATE_CAP')
    assert not hasattr(REC, 'bomb_hit')
    assert not hasattr(REC, 'punctuate')
    tl = REC.extract(kill_room)
    mix = REC.Mix(tl.duration)
    score, _buses = score_cw.render(tl, mix)
    bombs = [e for e in tl.events if e[1] == 'bomb']
    perc = [t for t, layer, _w in score.scheduled if layer == 'perc']
    assert len(bombs) > 100
    assert len(perc) * 4 < len(bombs)


def test_wav_round_trips_at_cd_quality(kill_room, tmp_path):
    _np()
    import wave
    tl = REC.extract(kill_room)
    path = tmp_path / 'track.wav'
    REC.write_wav(REC.synthesize(tl), path)
    with wave.open(str(path)) as fh:
        assert (fh.getnchannels(), fh.getsampwidth(),
                fh.getframerate()) == (2, 2, REC.SR)
        assert fh.getnframes() == int(tl.duration * REC.SR) + 1


# ---------------------------------------------------------------------------
# the cell renderer
# ---------------------------------------------------------------------------

def test_metrics_land_the_frame_natively_in_the_master_raster():
    """Repo law: render natively at delivery dimensions, never upscale a
    finished small render. 87x24 cells must fill 1920x1080 exactly."""
    pytest.importorskip('PIL')
    import ansi_png
    cw, ch, mx, my = ansi_png.metrics_for(87, 24, 1920, 1080)
    assert 87 * cw + 2 * mx == 1920
    assert 24 * ch + 2 * my == 1080
    assert ch == cw * 2                            # the terminal's own aspect


def test_ansi_parse_recovers_the_grid(kill_room):
    pytest.importorskip('PIL')
    import ansi_png
    tl = REC.extract(kill_room)
    rows = ansi_png.parse(tl.frames[10][1])
    assert len(rows) == 24
    field = rows[5]
    assert sum(1 for ch, _f, _b in field
               if 0x2800 <= ord(ch) <= 0x28FF) == 50   # the whole core, wide
    assert any(bg != ansi_png.BG_DEF for _c, _f, bg in field)


def test_rendered_frame_is_the_master_raster(kill_room):
    pytest.importorskip('PIL')
    import ansi_png
    tl = REC.extract(kill_room)
    cw, ch, mx, my = ansi_png.metrics_for(87, 24, 1920, 1080)
    r = ansi_png.CellRenderer(cw, ch, mx, my, 1920, 1080)
    img = ansi_png.render_ansi(tl.frames[len(tl.frames) // 2][1], r)
    assert img.size == (1920, 1080)
    assert len(img.getcolors(maxcolors=1 << 20)) > 20   # a real picture


def test_frame_listing_holds_dwells_as_repeats(kill_room, tmp_path):
    """A beat dwell is one PNG referenced many times, not thirty copies on
    disk — and the listing's length is the timeline's length, so the master
    cannot come out longer than the broadcast it recorded."""
    pytest.importorskip('PIL')
    tl = REC.extract(kill_room)
    listing = REC.render_frames(tl, tmp_path / 'frames')
    text = listing.read_text()
    files = [l for l in text.splitlines() if l.startswith('file ')]
    pngs = sorted((tmp_path / 'frames').glob('*.png'))
    assert len(pngs) == len(tl.frames)
    assert len(files) > len(pngs)                  # dwells were held
    # Frame-EXACT, not approximately: holds are differences of absolute
    # frame indices, so they telescope to round(duration * FPS) however the
    # frame times fell, and the concat tail repeat supplies the last one.
    assert len(files) == round(tl.duration * REC.FPS)


# ---------------------------------------------------------------------------
# review round: side effects a recorder has no business having
# ---------------------------------------------------------------------------

def test_extract_restores_the_callers_rng_and_import_path(kill_room):
    """The recorder seeds `random` so a master is reproducible, and it puts
    the engine dir on sys.path so it can import the renderer. Both are
    globals owned by whoever called us: seeding someone else's RNG stream
    and permanently mutating their import path are side effects, not
    features."""
    import random
    random.seed(1234)
    before_draw = [random.random() for _ in range(3)]
    random.seed(1234)
    path_before = list(sys.path)

    REC.extract(kill_room)

    assert [random.random() for _ in range(3)] == before_draw
    assert sys.path == path_before


def test_extract_refuses_a_directory_that_is_not_a_match(tmp_path):
    """The pane is deliberately tolerant of a degraded bus. A recorder must
    not be: pointed at the wrong directory it would otherwise spend two
    minutes rendering a video of an empty core."""
    with pytest.raises(SystemExit) as e:
        REC.extract(tmp_path)
    assert 'not a Core War match directory' in str(e.value)
    assert 'moves.txt' in str(e.value)


def test_the_scratch_directory_does_not_survive_a_render(kill_room, tmp_path,
                                                         monkeypatch):
    """Thousands of intermediate PNGs per render, and they used to be left
    behind — including when the mux failed, once per attempt."""
    pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    made = []
    real_mkdtemp = REC.tempfile.mkdtemp

    def spy(*a, **k):
        d = real_mkdtemp(*a, **k)
        made.append(Path(d))
        return d

    monkeypatch.setattr(REC.tempfile, 'mkdtemp', spy)
    out = tmp_path / 'out.mp4'
    assert REC.main(['record_cw.py', str(kill_room), str(out)]) == 0
    assert out.exists()
    assert made and not any(d.exists() for d in made)

    # ...and it is cleaned up even when the render blows up mid-way
    made.clear()
    monkeypatch.setattr(REC, 'mux', lambda *a, **k: (_ for _ in ()).throw(
        SystemExit('ffmpeg failed')))
    with pytest.raises(SystemExit):
        REC.main(['record_cw.py', str(kill_room), str(tmp_path / 'x.mp4')])
    assert made and not any(d.exists() for d in made)


def test_the_excerpt_is_opt_in(kill_room, tmp_path, monkeypatch):
    """It used to be written unconditionally to a fixed path under /tmp."""
    pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    calls = []
    monkeypatch.setattr(REC, 'excerpt',
                        lambda *a, **k: calls.append(a))
    out = tmp_path / 'a.mp4'
    REC.main(['record_cw.py', str(kill_room), str(out)])
    assert calls == []
    REC.main(['record_cw.py', str(kill_room), str(out),
              '--excerpt', f'{tmp_path / "e.mp4"}:6'])
    assert len(calls) == 1
    assert calls[0][3] == 6.0


def test_a_flag_value_is_never_mistaken_for_a_positional():
    """The bug this pins cost 621 MB in the caller's working directory.

    Positionals were "every argv entry not starting with --", so
    `--excerpt clip.mp4:8` put `clip.mp4:8` in args[2] — the old third
    positional, the scratch directory. That made `keep` truthy (no
    cleanup), created a directory named after the excerpt in the caller's
    CWD, and handed ffmpeg `clip.mp4:8/frames/frames.txt`, which it read
    as a protocol. One parsing shortcut, three failures."""
    assert REC.parse_args(['room', 'out.mp4', '--excerpt', 'clip.mp4:8']) == (
        ['room', 'out.mp4'], {'excerpt': 'clip.mp4:8'})
    assert REC.parse_args(['room', 'out.mp4', '--keep-scratch', '/tmp/k']) == (
        ['room', 'out.mp4'], {'keep-scratch': '/tmp/k'})
    assert REC.parse_args(['room', 'out.mp4', '--excerpt=e.mp4:5']) == (
        ['room', 'out.mp4'], {'excerpt': 'e.mp4:5'})
    # A flag with a missing value must not swallow the next flag.
    with pytest.raises(SystemExit):
        REC.parse_args(['room', 'out.mp4', '--keep-scratch', '--excerpt', 'e'])
    with pytest.raises(SystemExit):
        REC.parse_args(['room', 'out.mp4', '--nonsense', 'x'])
    # A path may legitimately contain colons; only the LAST one is seconds.
    assert REC.parse_excerpt('a:b/clip.mp4') == (Path('a:b/clip.mp4'), 20.0)
    assert REC.parse_excerpt('a:b/clip.mp4:8') == (Path('a:b/clip.mp4'), 8.0)
    with pytest.raises(SystemExit):
        REC.parse_excerpt('clip.mp4:20s')


def test_an_excerpt_run_leaves_nothing_behind(kill_room, tmp_path, monkeypatch):
    """The sibling of the opt-in test, which monkeypatches excerpt() and so
    cannot see the scratch directory at all. This one runs the real path
    from an empty CWD and asserts the room is left as it was found."""
    pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    cwd = tmp_path / 'cwd'
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    out = tmp_path / 'out.mp4'
    clip = tmp_path / 'clip.mp4'
    assert REC.main(['record_cw.py', str(kill_room), str(out),
                     '--excerpt', f'{clip}:4']) == 0
    assert out.exists() and clip.exists()
    assert list(cwd.iterdir()) == []


def test_the_hitstop_still_fades_out_at_the_very_start_of_the_track():
    """`a - f > 0` skipped the fade-OUT for any gate opening within one fade
    length of sample zero — so the one moment the whole track is built around
    arrived as a click instead of a cut. The fades shorten at the edges now,
    they do not vanish."""
    np = pytest.importorskip("numpy")
    mix = REC.Mix(int(0.5 * REC.SR))
    mix.buf[:] = 1.0
    mix.gate(0.001, 0.2)                   # opens 44 samples in, fade=176
    a = int(0.001 * REC.SR)
    assert float(np.abs(mix.buf[a:int(0.2 * REC.SR)]).max()) == 0.0
    lead = mix.buf[:a, 0]
    assert lead[0] == pytest.approx(1.0, abs=0.02)
    assert lead[-1] < 0.1                      # it really did ramp down
    assert np.all(np.diff(lead) <= 1e-6)


def test_the_limiter_ducks_the_loud_block_not_the_whole_file():
    """Gains came from each block's peak but were evaluated at each block's
    centre, so the first samples of a loud block were multiplied by a gain
    interpolated toward their quieter neighbour. The peak escaped, the global
    trim caught it, and the trim is global — the quiet room the entire mix
    law exists to protect got scaled down to pay for one sample."""
    np = pytest.importorskip("numpy")
    block = 256
    mix = REC.Mix(block * 8)
    mix.buf[:] = 0.05
    mix.buf[block * 4:block * 5] = 2.0         # one loud block, hard edges
    out = REC.master(mix, ceiling=0.89, block=block)
    assert float(np.abs(out).max()) <= 0.89 + 1e-6
    quiet = out[:block * 3]
    assert float(np.abs(quiet).min()) == pytest.approx(0.05, rel=0.02), \
        'the quiet room paid for a peak four blocks away'
    loud = np.abs(out[block * 4:block * 5])
    assert float(loud.max()) <= 0.89 + 1e-6
    assert float(loud[:16].max()) <= 0.89 + 1e-6   # including the leading edge


def test_asking_for_the_usage_is_not_an_error(capsys):
    """`record_cw.py --help` printed "unknown option: --help" and exited 2 —
    the one request that is never a mistake, answered as a mistake. Help now
    goes to stdout and exits 0, so it pipes and a caller can tell it apart
    from a bad invocation."""
    for flag in ('--help', '-h'):
        assert REC.main(['record_cw.py', flag]) == 0
        out = capsys.readouterr()
        assert 'usage: record_cw.py' in out.out
        assert out.err == ''
    # ...and it still answers even alongside real arguments, before any work
    assert REC.main(['record_cw.py', 'no-such-room', 'out.mp4', '--help']) == 0
    # a genuinely unknown option is still an error, on stderr, with usage
    assert REC.main(['record_cw.py', 'room', 'out.mp4', '--nonsense', 'x']) == 2
    err = capsys.readouterr().err
    assert 'unknown option: --nonsense' in err and 'usage:' in err
    # and no arguments at all is still the usage-on-stderr failure it was
    assert REC.main(['record_cw.py']) == 2
    assert 'usage:' in capsys.readouterr().err

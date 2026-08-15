"""Tests for the v2 track system (score_cw.py).

One law is above all the others here and it is the reason v2 exists: the
track owns the grid, and the battle never places a sound in time — it selects
which of the grid's existing slots fire, how hard, and in whose timbre. v1
put a sound at every event and the user's verdict was "borderline noise".
So the first block below is the anti-noise law, pinned three ways: every
onset the renderer schedules is checked against the positions the fixed
patterns allow, the whole battle is shifted by 30 ms to prove the rhythm
does not follow it, and the audio is checked against the same grid.

The second block pins the things that must never be confused with each
other: a kill spends the silence and the outside note, a tie spends neither.

Run with: uv run --with pytest --with numpy pytest test_score_cw.py
"""
import hashlib
import math
from pathlib import Path

import pytest

# score_cw is a DSP module and imports numpy unconditionally, so this whole
# file is a synthesis file: without numpy it SKIPS rather than erroring at
# collection. The numpy-free half of the contract lives in test_record_cw.py,
# whose ten timeline tests need neither numpy nor Pillow.
np = pytest.importorskip('numpy')

import corewar
import dna_cw as DNA
import record_cw as REC
import score_cw as S
import tui_corewar as X

ENGINE = Path(__file__).resolve().parent
SR = S.SR


# A warrior that executes a DAT on its first turn: eliminated at cycle 0, so
# its round's kill lands inside the load-in — the case an ordinary battle
# never reaches and the arranger used to drop on the floor.
DOOMED = ''';redcode-94
;name Doomed
;author test
        org     start
start   dat     #0, #0
        end
'''
SPLIER = ''';redcode-94
;name Splinter
;author test
        org     start
start   spl     $0
        mov.i   $0, $1
        end
'''


def build_room(tmp_path, seeds=(7,), a_src=None, b_src=None):
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
        lines += [f'ROUND {i} seed={seed} off={b.off_a},{b.off_b}',
                  f'ROUND {i} OUT {X.score_of(r)} cycles={r.cycles}']
    (tmp_path / 'moves.txt').write_text('\n'.join(lines) + '\n')
    return tmp_path


@pytest.fixture(scope='module')
def kill_tl(tmp_path_factory):
    """A round the dwarf wins at cycle 395 — the only path with a real
    elimination, and match-002 (three ties) cannot supply one."""
    room = build_room(tmp_path_factory.mktemp('kill'), seeds=(7,))
    return REC.extract(room)


@pytest.fixture(scope='module')
def both_tl(tmp_path_factory):
    """The tie round with every other bomb re-attributed to the other army.

    In imp-vs-dwarf only the dwarf bombs, so a natural fixture fires ice's
    perc slots and never ember's — which would leave ember's drag and swing
    untested, and the drag is precisely the thing a layer can silently skip.
    Re-attributing alternate bombs keeps the density (so the tiers are
    unchanged) and forces both studios to play."""
    room = build_room(tmp_path_factory.mktemp('both'), seeds=(7, 1, 11))
    src = REC.extract(room)
    out = REC.Timeline()
    out.duration, out.frames = src.duration, src.frames
    out.metrics, out.names = src.metrics, src.names
    out.warriors, out.dna = src.warriors, src.dna
    flip = 0
    events = []
    for t, k, a, w, x in src.events:
        if k in ('bomb', 'death'):
            flip += 1
            w = flip % 2
        events.append((t, k, a, w, x))
    out.events = events
    return out


@pytest.fixture(scope='module')
def tie_tl(tmp_path_factory):
    room = build_room(tmp_path_factory.mktemp('tie'), seeds=(1,))
    return REC.extract(room)


def shift_events(tl, dt, kinds=('bomb', 'death', 'spl', 'wrap', 'bloom')):
    """The same battle, told 30 ms later. Everything the arranger reads from
    metrics is untouched; only the event times move."""
    out = REC.Timeline()
    out.duration, out.frames = tl.duration, tl.frames
    out.metrics, out.names = tl.metrics, tl.names
    out.warriors, out.dna = tl.warriors, tl.dna
    out.events = [((t + dt) if k in kinds else t, k, a, w, x)
                  for t, k, a, w, x in tl.events]
    return out


def render(tl):
    mix = REC.Mix(tl.duration)
    score, buses = S.render(tl, mix)
    return score, buses, REC.master(mix)


def db(x):
    x = float(x)
    return -999.0 if x <= 0 else 20 * math.log10(x)


def death_energy(audio, death, t0, t1):
    """How much of a window is the match's outside note. The note itself is
    derived per match now — the b6 of whatever tonic the two warriors chose —
    so nothing may read a constant here."""
    seg = audio[int(t0 * SR):int(t1 * SR)].mean(axis=1)
    if len(seg) < 4096:
        return 0.0
    sp = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    f = np.fft.rfftfreq(len(seg), 1 / SR)
    return float(sp[(f > death * 0.985) & (f < death * 1.015)].max()
                 / max(1e-9, sp.max()))


def chroma(audio, grid, bars=(4, 40)):
    """The twelve pitch classes of a stretch of the render, by magnitude.

    This is what "two different songs" has to mean at the end of the chain:
    not that two dicts differ, but that the air moving in the room is a
    different set of notes."""
    lo = int(grid.bar(bars[0]) * SR)
    hi = min(len(audio), int(grid.bar(bars[1]) * SR))
    seg = audio[lo:hi].mean(axis=1)
    sp = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    f = np.fft.rfftfreq(len(seg), 1 / SR)
    keep = (f > 55.0) & (f < 2000.0)
    sp, f = sp[keep], f[keep]
    pc = np.rint(12 * np.log2(f / 440.0)).astype(int) % 12
    out = np.zeros(12)
    np.add.at(out, pc, sp ** 2)
    return out / max(1e-12, out.sum())


def bar_rms(audio, grid):
    n = int(grid.bar_s * SR)
    bars = audio[:len(audio) // n * n].reshape(-1, n, audio.shape[1])
    return np.sqrt((bars ** 2).mean(axis=(1, 2)))


# ---------------------------------------------------------------------------
# the grid
# ---------------------------------------------------------------------------

def test_grid_is_135_and_derived_not_chosen():
    """135 BPM is not a taste call: ROUND_TARGET_S + LOADIN_S + VERDICT_S is
    52.9s, which is 29.8 bars, so a full tie round is a 30-bar section for
    free. The tempo was picked to fit the pacing that already existed."""
    g = S.Grid()
    assert g.bpm == 135.0
    assert g.beat_s == pytest.approx(60.0 / 135.0)
    assert g.bar_s == pytest.approx(4 * 60.0 / 135.0)
    assert g.step_s == pytest.approx(g.beat_s / 4)
    assert g.steps_per_bar == 16
    round_s = X.ROUND_TARGET_S + X.LOADIN_S + X.VERDICT_S
    assert round_s / g.bar_s == pytest.approx(29.8, abs=0.15)


def test_grid_arithmetic_is_exact_and_monotone():
    g = S.Grid()
    for i in (0, 1, 7, 93):
        assert g.step_index(g.step(i)) == i
        assert g.bar_index(g.bar(i)) == i
    prev = -1.0
    for t in np.linspace(0, 20, 401):
        s = g.snap(t, 'step')
        assert s >= t - 1e-9
        assert s >= prev - 1e-9
        assert g.snap(s, 'step') == pytest.approx(s)   # idempotent on grid
        prev = s
    assert g.snap(0.5, 'bar') == pytest.approx(g.bar_s)


# ---------------------------------------------------------------------------
# THE ANTI-NOISE LAW
# ---------------------------------------------------------------------------

# The ONE layer allowed off the grid, and the only one: the elimination
# payload lands with the picture's freeze, which outranks the grid. It is
# recorded as a scheduled onset like everything else precisely so that this
# exemption has to be written down here, in the test, where it can be
# audited — rather than existing as a code path the tests cannot see.
UNQUANTIZED = 'moment'
# The second, and the only other one: a draw's dissolve begins when the
# picture's end wash begins, so it cannot be on the grid either. Both live
# here, in the test, so that adding a third means editing this list.
OUTRO = 'outro'
EXEMPT = {UNQUANTIZED, OUTRO}


def _offgrid(score):
    g = score.grid
    bad = []
    for t, layer, _w in score.scheduled:
        if layer in EXEMPT:
            continue
        # faction-aware: ember's grid is not ice's, and a blind union lets a
        # layer pass on a coincidence (which is how the post-drop relock hid)
        offs = score.pattern_offsets(layer, _w)
        ph = t % g.bar_s
        err = min(min(abs(ph - o) for o in offs), abs(ph - g.bar_s + offs[0]))
        if err > 1e-6:
            bad.append((t, layer, err))
    return bad


def _moments_are_the_only_exemption(score):
    """Every exempt onset must BE an elimination payload — the exemption is
    for one thing, not a category anything can join."""
    lands = {round(m['t'] + m['hitstop'], 9) for m in score.moments}
    exempt = [t for t, layer, _w in score.scheduled if layer == UNQUANTIZED]
    assert len(exempt) == len(score.moments)
    for t in exempt:
        assert round(t, 9) in lands
    # ...and the outro exemption is for draws, exactly one per drawn end
    draws = [c for c in score.cues if c['kind'] == 'end' and c['drawn']]
    outro = [t for t, layer, _w in score.scheduled if layer == OUTRO]
    assert len(outro) == len(draws)
    for t, c in zip(outro, draws):
        assert t == pytest.approx(c['t'])


def test_every_scheduled_onset_sits_on_the_grid(kill_tl, tie_tl):
    """The law, stated structurally. The renderer writes down every rhythmic
    onset it places; not one of them may sit anywhere the fixed patterns do
    not already allow."""
    for tl in (kill_tl, tie_tl):
        score, _b, _a = render(tl)
        assert len(score.scheduled) > 50
        assert _offgrid(score) == []
        _moments_are_the_only_exemption(score)


def test_each_layer_places_through_the_one_shared_helper(kill_tl, both_tl):
    """Stronger than "every onset is on SOME allowed offset": ember drags
    8 ms and ice does not, so an ember layer that computed its own time
    would land on ICE's grid and a faction-blind test would wave it through
    on the coincidence. Every onset is checked against its own faction's
    offsets, and the helper is checked directly besides."""
    g = S.Grid()
    for step in (0, 3, 4, 7, 10, 15):
        ice = S.step_time(1, step, 0.0, g)
        emb = S.step_time(0, step, 0.0, g)
        assert ice == pytest.approx(step * g.step_s)          # machine grid
        assert emb > ice                                      # ember drags
        assert emb - ice == pytest.approx(
            S.EMBER_DRAG + (0.0 if step % 2 == 0 else
                            (S.EMBER_SWING - 0.5) * g.step_s * 2))
    seen = set()
    for tl in (kill_tl, both_tl):
        score, _b, _a = render(tl)
        for t, layer, w in score.scheduled:
            seen.add((layer, w))
            if layer in EXEMPT:      # the two audited exemptions; see above
                continue
            offs = score.pattern_offsets(layer, w)
            ph = t % g.bar_s
            err = min(min(abs(ph - o) for o in offs),
                      abs(ph - g.bar_s + offs[0]))
            assert err < 1e-6, (layer, w, t, err)
    # both studios have to have been exercised, or the drag never got tested
    assert any(w == 0 for _l, w in seen) and any(w == 1 for _l, w in seen)


def test_moving_the_whole_battle_30ms_does_not_move_the_rhythm(kill_tl):
    """Opus's test, verbatim: if you can move an event by 30 ms and hear a
    different rhythm, you are still sonifying. Slot SELECTION may change —
    a bomb near a boundary votes for its neighbour instead — but no onset
    may move, so the set of positions in play is identical."""
    base, _b, _a = render(kill_tl)
    g = base.grid
    base_pos = {round(t % g.bar_s, 6) for t, _l, _w in base.scheduled
                if _l not in EXEMPT}
    for dt in (0.030, -0.030):
        alt, _b2, _a2 = render(shift_events(kill_tl, dt))
        assert _offgrid(alt) == []
        alt_pos = {round(t % g.bar_s, 6) for t, _l, _w in alt.scheduled
                   if _l not in EXEMPT}
        assert alt_pos <= base_pos | set(base.pattern_offsets())
        # the arrangement itself is a bar-scale reading and must not twitch
        assert alt.sections == base.sections
        assert np.array_equal(alt.tier, base.tier)


def test_a_30ms_shift_is_audible_as_dynamics_not_as_timing(kill_tl):
    """The other half of the same law: the shift is allowed to change WHICH
    slots fire and how hard — that is the battle conducting — so the render
    should not be bit-identical either. A system that ignored the battle
    entirely would also pass the test above."""
    _s, _b, a0 = render(kill_tl)
    _s2, _b2, a1 = render(shift_events(kill_tl, 0.030))
    assert a0.shape == a1.shape
    assert not np.array_equal(a0, a1)


def test_audio_onsets_land_on_the_grid(kill_tl):
    """And the same law measured off the samples rather than the plan: the
    drum bus is peak-picked and every onset checked against the grid. A
    refractory period is needed because an 808's own decay ripple otherwise
    reads as four onsets instead of one."""
    score, buses, _a = render(kill_tl)
    g = score.grid
    env = np.abs(buses.drums)
    hop = 64
    env = env[:len(env) // hop * hop].reshape(-1, hop).max(axis=1)
    flux = np.maximum(0.0, np.diff(env, prepend=env[0]))
    thr = flux.mean() + 4.0 * flux.std()
    times, last = [], -9.9
    for i in np.flatnonzero(flux > thr):
        t = i * hop / SR
        if t - last >= 0.10:
            times.append(t)
            last = t
    skip = [(m['t'] - 0.05, m['t'] + m['hitstop'] + 0.35)
            for m in score.moments]
    times = [t for t in times if not any(a <= t <= b for a, b in skip)]
    assert len(times) > 20
    offs = score.pattern_offsets()
    err = []
    for t in times:
        ph = t % g.bar_s
        err.append(min(min(abs(ph - o) for o in offs),
                       abs(ph - g.bar_s + offs[0])))
    assert np.median(err) < 0.004


def test_bombs_vote_they_never_hit(kill_tl):
    """v1 played one sound per bomb. v2's bombs are votes: thousands of them
    collapse onto at most ten slots a bar, and a slot that no pattern owns
    never sounds however many bombs land in it."""
    score, _b, _a = render(kill_tl)
    bombs = [e for e in kill_tl.events if e[1] == 'bomb']
    assert len(bombs) > 100
    perc = [t for t, layer, _w in score.scheduled if layer == 'perc']
    assert len(perc) < len(bombs) / 2
    g = score.grid
    allowed = set(score.steps[0]) | set(score.steps[1]) | set(score.ghosts)
    for t, layer, w in score.scheduled:
        if layer != 'perc':
            continue
        # No slack: ask which step of THIS faction's grid actually produced
        # the phase. The old form rounded and then allowed step or step-1 to
        # absorb ember's drag, which also let a genuinely wrong step pass
        # whenever its neighbour was legal.
        ph = t % g.bar_s
        steps = [st for st in range(16)
                 if abs(S.step_time(w, st, 0.0, g) - ph) < 1e-6
                 or abs(S.step_time(w, st, 0.0, g) - ph - g.bar_s) < 1e-6]
        assert len(steps) == 1, (t, w, ph, steps)
        assert steps[0] in allowed, (t, w, steps[0])


# ---------------------------------------------------------------------------
# a kill and a tie must never sound like each other
# ---------------------------------------------------------------------------

def test_the_hitstop_is_absolute_silence_and_is_not_quantized(kill_tl):
    """The one place the battle is allowed to say WHEN. The silence is synced
    to the picture's freeze, so it lands wherever the frame did — the grid
    does not get a vote, and the payload re-locks afterwards."""
    score, _b, audio = render(kill_tl)
    assert score.moments
    m = score.moments[0]
    g = score.grid
    lo = int((m['t'] + 0.002) * SR)
    hi = int((m['t'] + m['hitstop'] - 0.002) * SR)
    assert hi > lo
    assert float(np.abs(audio[lo:hi]).max()) == 0.0
    assert float(np.abs(audio[int((m['t'] - 0.25) * SR):
                              int((m['t'] - 0.02) * SR)]).max()) > 0.05
    # Not quantized: the gate begins at the event's own timestamp, to the
    # sample. (This particular kill happens to land near a grid line — the
    # test must prove sample-sync, not luck, so it reads the first silent
    # sample rather than comparing to the grid.)
    first_zero = lo
    while first_zero > 0 and float(np.abs(audio[first_zero - 1]).max()) == 0.0:
        first_zero -= 1
    assert abs(first_zero - int(m['t'] * SR)) <= 2
    # ...but the grid re-locks immediately after it
    relock = g.snap(m['t'] + m['hitstop'], 'step')
    hits = [t for t, layer, _w in score.scheduled
            if layer == 'relock' and abs(t - relock) < 1e-9]
    assert len(hits) == 1
    # the relock is on a 1/16 line — any of them, which is the point
    assert abs((relock / g.step_s) - round(relock / g.step_s)) < 1e-9


def test_only_a_kill_spends_the_outside_note(kill_tl, tie_tl):
    """Bb exists nowhere in this piece except the elimination drop and the
    win finale. The outside note is the death note, and a stalemate may
    never borrow it — that is what keeps the two endings distinguishable
    with your eyes shut."""
    kscore, _kb, kaudio = render(kill_tl)
    m = kscore.moments[0]
    land = m['t'] + m['hitstop']
    # the death note is DERIVED now, so the test has to ask the score which
    # note this match kills with rather than assume the shipped Bb
    assert death_energy(kaudio, kscore.death, land, land + 1.5) > 0.5

    tscore, _tb, taudio = render(tie_tl)
    assert not tscore.moments                            # nobody died
    drops = [c for c in tscore.cues if c['kind'] == 'drop']
    assert drops and all(c['drop'] == 'tie' for c in drops)
    for c in drops:
        assert death_energy(taudio, tscore.death, c['t'], c['t'] + 1.5) < 0.15


def test_a_tie_round_still_drops_but_without_silence(tie_tl):
    """Every round earns a drop — a stalemate that never resolves musically
    is 53 seconds of nothing happening. What a tie does not get is the
    silence, so the two can never be confused."""
    score, _b, audio = render(tie_tl)
    g = score.grid
    drops = [c for c in score.cues if c['kind'] == 'drop']
    assert drops
    for c in drops:
        lo = int(c['t'] * SR)
        hi = int((c['t'] + 0.4) * SR)
        assert float(np.abs(audio[lo:hi]).max()) > 0.05      # no hole
        assert c['bar'] == g.bar_index(c['t'])               # on a bar line
    rms = bar_rms(audio, g)
    for c in drops:
        b = c['bar']
        assert db(rms[b]) - db(rms[b - 1]) >= 6.0            # it is a drop


def test_the_riser_empties_the_room_before_the_drop(kill_tl):
    """A drop is only as big as the hole in front of it: the kick thins and
    then leaves and the sub evacuates, so the payoff has somewhere to land."""
    score, _b, audio = render(kill_tl)
    rms = bar_rms(audio, score.grid)
    riser = [c for c in score.cues if c['kind'] == 'riser']
    drop = [c for c in score.cues if c['kind'] == 'drop']
    assert riser and drop
    d = drop[0]['bar']
    assert db(rms[d]) - db(rms[d - 1]) >= 6.0
    kicks = [t for t, layer, _w in score.scheduled if layer == 'kick']
    last_riser_bar = d - 1
    lo, hi = score.grid.bar(last_riser_bar), score.grid.bar(d)
    assert not [t for t in kicks if lo <= t < hi]


def test_a_kill_inside_the_intro_still_gets_its_drop(tmp_path_factory):
    """A warrior that runs a DAT on its first turn is eliminated at cycle 0,
    so the kill lands inside the load-in. The build has nowhere to live —
    but the DROP must still fire, because the cue carries the Bb recolor and
    the eight-bar payoff. Without it the kill is an isolated stinger over an
    arrangement that never noticed anyone died."""
    room = build_room(tmp_path_factory.mktemp('early'), seeds=(3,),
                      a_src=SPLIER, b_src=DOOMED)
    tl = REC.extract(room)
    score, _b, audio = render(tl)
    g = score.grid
    elim = tl.of('elimination')[0]
    assert g.bar_index(elim[0]) <= 1              # genuinely inside the intro
    drops = [c for c in score.cues if c['kind'] == 'drop']
    assert drops and drops[0]['drop'] == 'kill'
    assert drops[0]['bar'] == g.bar_index(elim[0])
    # and the outside note is really spent on it
    m = score.moments[0]
    land = m['t'] + m['hitstop']
    assert death_energy(audio, score.death, land, land + 1.5) > 0.5
    # the sections still partition cleanly with the intro compressed away
    spans = [(a, b) for a, b, _k in score.sections]
    assert all(b > a for a, b in spans)
    for (_a1, b1), (a2, _b2) in zip(spans, spans[1:]):
        assert b1 == a2


def test_the_loser_dies_for_the_round_not_the_match(tmp_path_factory):
    """After a kill the loser's layers are gone, not faded — but only until
    the round ends. A three-round track whose second round starts with one
    faction already silent is the most obvious possible bug to ship."""
    room = build_room(tmp_path_factory.mktemp('three'), seeds=(7, 1, 11))
    tl = REC.extract(room)
    score, buses, _a = render(tl)
    assert len(score.moments) >= 1
    m = score.moments[0]
    loser = buses.emb if m['loser'] == 0 else buses.ice
    after = m['t'] + m['hitstop'] + m['sweep'] + 0.3
    end = min(m['until'], after + 1.0)
    assert float(np.abs(loser[int(after * SR):int(end * SR)]).max()) == 0.0
    assert m['until'] < tl.duration - 5           # a later round exists
    back = loser[int((m['until'] + 4) * SR):int((m['until'] + 8) * SR)]
    assert float(np.abs(back).max()) > 0.01       # and it brought them back


# ---------------------------------------------------------------------------
# the endings
# ---------------------------------------------------------------------------

def test_an_ice_loser_is_cut_through_its_own_reverb(tmp_path_factory):
    """Ice is the faction that lives in a reverb, and the send runs after the
    loser's layers are cut — a 4177-sample tail at 0.70 feedback smeared
    straight through the silence, so an ice army went on ringing after it
    died. Every other kill fixture has an EMBER loser, which is why this was
    invisible: ember has no send.

    The dwarf is seated as warrior A here so that the imp — warrior B, ice —
    is the one that dies."""
    room = build_room(tmp_path_factory.mktemp('iceloss'), seeds=(10,),
                      a_src=corewar.DWARF, b_src=corewar.IMP)
    tl = REC.extract(room)
    score, buses, _a = render(tl)
    assert score.moments and score.moments[0]['loser'] == 1     # ice died
    m = score.moments[0]
    after = m['t'] + m['hitstop'] + m['sweep'] + 0.05
    end = min(m['until'], after + 2.0)
    tail = buses.ice[int(after * SR):int(end * SR)]
    assert len(tail) > SR // 2
    assert float(np.abs(tail).max()) == 0.0
    # ...while the winner is still audibly playing over the same window
    assert float(np.abs(buses.emb[int(after * SR):int(end * SR)]).max()) > 0.0


def test_a_short_round_does_not_crash_the_tie_drop_search(kill_tl):
    """The tie-drop peak search slices a per-bar curve, and on a short round
    the window can start past the end of it. The old guard compared lo to a
    hi that was defined as max(lo + 1, ...), so it could never fail and
    np.argmax got an empty slice."""
    for cut in (2.0, 4.0, 8.0, 12.0):
        short = REC.Timeline()
        short.duration = cut
        short.frames = [f for f in kill_tl.frames if f[0] < cut]
        short.metrics = [m for m in kill_tl.metrics if m[0] < cut] or \
            kill_tl.metrics[:1]
        short.names = kill_tl.names
        short.dna = kill_tl.dna
        short.events = [e for e in kill_tl.events if e[0] < cut]
        score = S.analyze(short)              # must not raise
        assert score.n_bars >= 1


def test_a_draw_dissolves_and_is_never_gated_to_zero(tie_tl):
    """A win stops; a draw dissolves. The outro falls exponentially toward
    silence and never arrives — it does not end, it stops being loud enough
    to hear."""
    score, buses, audio = render(tie_tl)
    end = next(c for c in score.cues if c['kind'] == 'end')
    assert end['drawn']
    t0 = end['t']
    tail = audio[int(t0 * SR):]
    assert len(tail) > SR
    win = int(0.25 * SR)
    levels = [float(np.abs(tail[i:i + win]).max())
              for i in range(0, len(tail) - win, win)]
    assert levels[0] > levels[-1] * 3            # it really does fade
    assert levels[-1] > 0.0                      # and never reaches zero
    assert db(levels[-1]) < -35.0                # into room tone


def test_a_win_ends_on_a_downbeat_with_the_motif(tmp_path_factory):
    room = build_room(tmp_path_factory.mktemp('win'), seeds=(7, 7, 7))
    tl = REC.extract(room)
    score, _b, audio = render(tl)
    end = next(c for c in score.cues if c['kind'] == 'end')
    assert not end['drawn']
    g = score.grid
    bar_t = g.snap(end['t'], 'bar')
    seg = audio[int(bar_t * SR):int((bar_t + 2.0) * SR)]
    assert float(np.abs(seg).max()) > 0.1        # a win is not quiet


# ---------------------------------------------------------------------------
# the arranger, and the mix law
# ---------------------------------------------------------------------------

def test_sections_partition_the_track_and_join_at_bar_lines(kill_tl, tie_tl):
    for tl in (kill_tl, tie_tl):
        score, _b, _a = render(tl)
        assert score.sections
        spans = [(a, b) for a, b, _k in score.sections if b > a]
        for (a1, b1), (a2, _b2) in zip(spans, spans[1:]):
            assert b1 == a2                       # no gaps, no overlaps
        kinds = {k for _a, _b, k in score.sections}
        assert kinds <= {'intro', 'groove', 'riser', 'drop', 'breakdown'}
        assert kinds & {'groove', 'drop'}
    # a full three-round match uses the whole vocabulary
    score, _b, _a = render(tie_tl)
    assert {'intro', 'breakdown'} <= {k for _a, _b, k in score.sections}


def test_tiers_rise_slowly_and_reset_at_a_round_cut(tmp_path_factory):
    """Builds are fast and decays are slow, but neither is instant: a
    flapping arrangement is worse than a flat one."""
    room = build_room(tmp_path_factory.mktemp('tiers'), seeds=(1, 1))
    tl = REC.extract(room)
    score, _b, _a = render(tl)
    assert score.tier.max() >= 2
    for i in range(1, len(score.tier)):
        assert score.tier[i] - score.tier[i - 1] <= 1     # never jumps up
    cuts = {score.grid.bar_index(t) for t, k, *_ in tl.events
            if k == 'round-cut'}
    for b in cuts:
        if b < len(score.tier):
            assert score.tier[b] == 0


def test_the_mix_stays_a_quiet_room_that_events_puncture(tie_tl):
    """v1's mix law, restated for a record. A track with a kick lands nearer
    12-14 dB of crest than v1's 17 and should — what has to survive is the
    CONTRAST, so the law is sectional: the quietest bar sits far below the
    loudest, and nothing clips."""
    score, _b, audio = render(tie_tl)
    peak = float(np.abs(audio).max())
    assert peak <= 0.9
    assert db(peak) > -3.0                        # mastered, not timid
    crest = db(peak) - db(np.sqrt((audio ** 2).mean()))
    assert 10.0 <= crest <= 20.0
    rms = bar_rms(audio, score.grid)
    rms = rms[rms > 0]
    assert db(rms.max()) - db(rms.min()) >= 14.0


def test_determinism_same_transcript_same_track(kill_tl):
    a = render(kill_tl)[2]
    b = render(kill_tl)[2]
    assert np.array_equal(a, b)


def test_audio_is_exactly_as_long_as_the_broadcast(kill_tl):
    audio = render(kill_tl)[2]
    assert audio.shape == (int(kill_tl.duration * SR) + 1, 2)


def test_territory_colours_the_shared_kick():
    """The shared kick and sub inherit the dominant faction's studio, so a
    99% ember board is a fatter, dirtier, lower record than a 99% ice one
    even in a passage where neither side is soloing."""
    e = S._kick_colour(0.99)
    i = S._kick_colour(0.01)
    assert e['drive'] > i['drive']
    assert e['floor'] < i['floor']                # ember sits lower
    assert e['click'] < i['click']                # ice's click is brighter
    assert e['reverb'] < i['reverb']              # ice lives in the room
    assert 'swing' not in e                       # groove is not battle state


def test_first_blood_crashes_once_in_every_round(tmp_path_factory):
    """The picture's first-blood field resets at every round start, so the
    sound has to as well. analyze() used to keep `tl.of('first-blood')[0]`
    and nothing else, which gave a three-round stalemate one crash in round
    one and silence at the opening of rounds two and three."""
    room = build_room(tmp_path_factory.mktemp('fb'), seeds=(7, 1, 11))
    tl = REC.extract(room)
    score, _b, _a = render(tl)
    events = tl.of('first-blood')
    assert len(events) >= 2, 'fixture must have more than one round of it'
    assert score.first_blood_bars == {score.grid.bar_index(t)
                                      for t, *_ in events}
    # ...and they really are spread across the match, not clustered at the top
    assert max(score.first_blood_bars) - min(score.first_blood_bars) > 8


def test_the_loser_window_is_computed_one_way_only():
    """The ramp and the post-reverb re-cut derived the same sample boundary
    with different arithmetic — int(land*SR) + int(sweep*SR) against
    int((land+sweep)*SR) — which disagree whenever both fractions carry.
    Sweep across enough times that the carry case is certain to occur."""
    n = 10 * SR
    for i in range(500):
        land, sweep = 1.0 + i * 0.00137, 0.18 + i * 0.00011
        m = {'t': land, 'hitstop': 0.0, 'sweep': sweep, 'until': land + 3.0}
        a, b, end = S._loser_window(m, n)
        assert a <= b <= end <= n
        # the two old spellings, and the fact that they disagree
        assert b == a + max(1, int(sweep * SR))
        naive = int((land + sweep) * SR)
        if naive != b:
            break
    else:
        raise AssertionError('sweep never hit the carry case — test is blind')


def test_a_kill_at_the_end_of_a_round_does_not_step_at_the_boundary():
    """The mute stops at `until` because past it the buffer belongs to the
    NEXT round. A kill landing a second before the round ends therefore left
    a reverb tail that was still loud at `until` and reappeared out of
    silence as a step. Driven directly: a loser bus ringing at full scale,
    cut a second before its round ends."""
    n = 10 * SR

    class B:
        pass
    bus = B()
    bus.emb = np.ones(n, dtype=np.float32)
    bus.ice = np.ones(n, dtype=np.float32)

    class Sc:
        moments = [{'t': 2.0, 'hitstop': 0.25, 'sweep': 0.4, 'loser': 1,
                    'until': 3.6}]
    S._cut_losers(Sc, bus)
    end = int(3.6 * SR)
    assert float(np.abs(bus.ice[int(2.7 * SR):end]).max()) == 0.0
    assert bus.ice[end] == pytest.approx(0.0, abs=1e-6)      # no step up
    d = np.abs(np.diff(bus.ice[end - 10:end + int(0.05 * SR)]))
    assert float(d.max()) < 0.01, 'the boundary is a ramp, not a cliff'
    assert bus.ice[end + int(0.03 * SR)] == pytest.approx(1.0, abs=0.02)
    assert float(bus.emb.min()) == 1.0                       # winner untouched


def test_the_breakdown_still_has_a_pad(kill_tl, tie_tl):
    """The pad was written under `if kind != 'breakdown' or True:` — a
    condition that says the opposite of what it does. Removing it is only
    safe if the breakdown is genuinely meant to keep its pad, so that is
    what is pinned: the room thins, it does not empty."""
    for tl in (kill_tl, tie_tl):
        score, buses, _a = render(tl)
        bars = [b for b in range(score.n_bars)
                if score.section_at(b) == 'breakdown']
        if not bars:
            continue
        g = score.grid
        for b in bars[:4]:
            seg = buses.emb[int(g.bar(b) * SR):int(g.bar(b + 1) * SR)]
            if len(seg) and float(np.abs(seg).max()) == 0.0:
                continue          # this faction is dead here; ask the other
            assert float(np.abs(seg).max()) > 1e-4
        return
    pytest.skip('no breakdown section in either fixture')


# ---------------------------------------------------------------------------
# CORE DNA — the material is the match's own, and null DNA is still v2
# ---------------------------------------------------------------------------

def render_with(tl, dna):
    """Render one transcript under a given set of material. Holding the
    battle fixed and changing only the DNA is the only way to measure the
    SONG rather than the arrangement."""
    mix = REC.Mix(tl.duration)
    score = S.analyze(tl, dna=dna)
    buses = S.render_score(score, tl, mix)
    return score, buses, REC.master(mix)


def without_dna(tl):
    out = REC.Timeline()
    out.duration, out.frames = tl.duration, tl.frames
    out.metrics, out.names, out.events = tl.metrics, tl.names, tl.events
    return out


def shipped_dna(match):
    d = ENGINE.parent / 'games' / 'corewar' / match / 'warriors'
    return DNA.match_dna(*[corewar.parse_warrior((d / f'{s}.red').read_text())
                           for s in 'AB'])


def test_the_fixtures_really_are_running_on_derived_material(kill_tl, tie_tl):
    """Guard for every test above this line. `extract()` attaches the DNA, and
    if it ever stopped, the whole anti-noise suite would quietly go back to
    testing v2's constants and pass while proving nothing about v3."""
    for tl in (kill_tl, tie_tl):
        assert tl.dna is not None and tl.dna.derived
        score, _b, _a = render(tl)
        assert score.dna.derived
        assert score.steps[0] != S.EMBER_STEPS or \
            score.steps[1] != S.ICE_STEPS or score.pent != DNA.DEFAULT.pent


def test_null_dna_renders_the_v2_record_exactly(kill_tl):
    """The load-bearing property. A warrior that fails to assemble takes the
    whole match back to v2's constants, so the worst case in the system is
    the record that already shipped — and 'back to v2' has to mean the
    samples, not the intent.

    The literal below is the GOLDEN PIN, and it is the only assertion here
    that can catch a symmetric regression: comparing two v3 renders to each
    other passes happily if both drift the same way. This digest was taken
    from `score_cw.py`/`record_cw.py` as they stood at commit 0fc1724 — real
    v2 code, rendering this same room — so a v3 that reproduces it is
    reproducing the shipped record rather than reproducing itself."""
    V2_GOLDEN = ('9541b0da7664c2ceb79a19aae0c643'
                 '5bfdd015a89a82939cfac4476134dd9f07')
    a = render_with(without_dna(kill_tl), None)[2]
    b = render_with(kill_tl, DNA.DEFAULT)[2]
    assert np.array_equal(a, b)
    assert hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest() \
        == V2_GOLDEN
    # ...and the module's aliases really are that same null DNA
    assert S.PENT == {'D': 36.708, 'F': 43.654, 'G': 48.999,
                      'A': 55.000, 'C': 65.406}
    assert S.BB == 58.270
    assert S.EMBER_STEPS == (0, 3, 6, 10, 13)
    assert S.ICE_STEPS == (2, 6, 10, 14)
    assert S.ICE_GHOSTS == (7, 15)
    # the derived render must NOT be the same, or nothing was derived
    assert not np.array_equal(a, render(kill_tl)[2])


def test_two_matches_are_two_different_songs(kill_tl):
    """The complaint v3 answers, measured in the air rather than in a dict:
    the same battle under different DNA has to come out as a different set of
    pitch classes. The battle is held fixed on purpose — otherwise the
    arrangement, not the material, would be doing the work.

    This is also the regression test for two collisions this module shipped
    on the way here. Before the pair hash had its finalizer, both matches
    landed on F# and this distance was 0.37. With the finalizer but before
    each field got its own lane, the tonics separated and both matches landed
    on `ritusen` a whole step apart — four of five pitch classes shared,
    which sounds MORE like a sibling than the collision it replaced.
    Anything that un-mixes the hash lands here."""
    one, two = shipped_dna('match-001'), shipped_dna('match-002')
    g = S.Grid()
    cn = chroma(render_with(kill_tl, DNA.DEFAULT)[2], g)
    ca = chroma(render_with(kill_tl, one)[2], g)
    cb = chroma(render_with(kill_tl, two)[2], g)
    assert one.tonic != two.tonic
    assert not (set(DNA.scale_pcs(one.tonic, one.rot))
                & set(DNA.scale_pcs(two.tonic, two.rot)))
    assert float(np.abs(ca - cb).sum()) > 0.4
    # ...and neither is merely a re-mix of the null record
    assert float(np.abs(ca - cn).sum()) > 0.4
    assert float(np.abs(cb - cn).sum()) > 0.4


def test_the_outside_note_sounds_only_where_it_is_allowed(kill_tl):
    """Ruling 2, carried into derived space. The death note is the entire
    chromatic budget of the piece: it may sound in the elimination drop and
    in the win finale, and nowhere else in the whole track.

    The measure is a ratio against the bar's own loudest bin, so a quiet
    intro bar has a floor of about 0.2 whatever is playing — the drop reads
    1.0 against it, which is the contrast the law is actually about."""
    score, _b, audio = render(kill_tl)
    g = score.grid
    assert score.death not in score.pent
    allowed = {b for b in range(score.n_bars)
               if score.section_at(b) == 'drop'}
    end = next((c for c in score.cues if c['kind'] == 'end'), None)
    if end and not end['drawn']:
        allowed |= set(range(g.bar_index(g.snap(end['t'], 'bar')),
                             score.n_bars))
    m = score.moments[0]
    land = m['t'] + m['hitstop']
    spent = death_energy(audio, score.death, land, land + 1.5)
    assert spent > 0.5                            # the drop IS the death note
    ordinary = [death_energy(audio, score.death, g.bar(b), g.bar(b + 1))
                for b in range(2, score.n_bars - 1) if b not in allowed]
    assert ordinary
    assert max(ordinary) < 0.25, max(ordinary)
    assert max(ordinary) < spent * 0.5


def test_the_bass_root_stays_in_octave_one(kill_tl, tie_tl):
    """The tonic is a pitch class and the register is fixed, so a match in
    any of the sixty keys sits in the same low band v2's mix was built
    around. Measured off the sub bus, which is where the law would break.

    Stated exactly, because the loose version of this claim is false: the
    ROOT clamps to octave 1. A FIGURE may voice up to one octave above it,
    and two of the four deliberately do — `root-fifth` reaches a fifth and
    `octave-bounce` doubles at x2 — so the ceiling asserted here is the
    root's octave plus one, not the root's octave."""
    for name, fig in DNA.BASS_FIGURES:
        assert all(m in (1, 2) for _s, _n, _o, m in fig), name
    for tl in (kill_tl, tie_tl):
        score, buses, _a = render(tl)
        assert DNA.BASS_LO <= score.pent[0] < DNA.BASS_HI
        seg = buses.sub[int(4 * score.grid.bar_s * SR):]
        seg = seg[:len(seg) // 2]
        sp = np.abs(np.fft.rfft(seg.astype(np.float64)))
        f = np.fft.rfftfreq(len(seg), 1 / SR)
        peak = float(f[int(np.argmax(sp))])
        assert 25.0 < peak < 220.0, peak

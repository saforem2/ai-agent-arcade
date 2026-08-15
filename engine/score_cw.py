"""CORE LOOP — the Core War broadcast's track system.

v1 had no clock of its own. It borrowed the battle's, and the battle's clock
ticks hundreds of times a second: nothing with that many onsets is music, it
is weather. The user's verdict on the v1 master — "the setup is right and
cool but it's borderline noise" — is that diagnosis heard rather than read.

So this module owns a grid, and one law sits above everything else in it:

    THE TRACK OWNS THE GRID. THE BATTLE NEVER PLACES A SOUND IN TIME.
    It only decides which of the grid's already-existing slots fire, how
    hard, in whose timbre, and through which filter.

That law is testable and it is tested: move any event by 30 ms and the
rhythm must not change. If it does, this is sonification again and it is a
bug. The single exception is the elimination, whose silence is synced to the
picture's freeze — that law outranks the grid, and it is the only place in
the piece where the battle is allowed to say when.

Design record: design/corewar-mockups/atlas/music-consult/DECISION.md, which
adopts opus.md's grid/harmony/anti-noise/filtering/tie-drop/outro and
kimi.md's phrase blocks, event table and instrument recipes.

THE GRID. 135 BPM, 4/4, one tempo for the whole match, origin at t=0. Not
chosen — derived: ROUND_TARGET_S 50 + LOADIN_S 1.5 + VERDICT_S 1.4 = 52.9s
= 29.8 bars, so a tie round is a 30-bar section for free. Three rounds are
three sections of one track, never three loops of one thing.

THE HARMONY. An 8-bar loop, Dm7 | F6 | Gsus | A(add4), two bars each. Every
chord is a rotation of the D-minor-pentatonic set, so v1's "nothing can ever
land wrong" guarantee survives intact while the bass root actually moves
D→F→G→A. Exactly ONE note in the whole piece is outside the scale — Bb —
and it is spent only on the elimination drop and the win finale. The outside
note is the death note; nothing smaller may spend it.

THE TWO RECORDS. Ember and ice are not two timbres, they are two studios.
Ember: saturated supersaws, coal-crackle noise, dragged and swung, D1-A4.
Ice: bone-dry FM and bell partials into reverb, machine-quantized, D5-D7.
The shared kick and sub inherit the DOMINANT faction's processing, so
territory is audible even in a passage where neither is soloing.

FILTERING WITHOUT A FILTER. Every tonal source here is an additive stack, so
a moving low-pass is a per-harmonic gain array — `1/sqrt(1+(f/fc)**(2*order))`
evaluated per harmonic against a cutoff CURVE. Vectorised, exact,
deterministic, no scipy and no per-sample IIR loop over 7.2M samples. Only
the noise sources need a real filter, and they get a cheap FIR.
"""
import math

import numpy as np

import dna_cw as DNA

SR = 44100

# ---- the grid -------------------------------------------------------------
BPM = 135.0
BEATS_PER_BAR = 4
STEPS_PER_BEAT = 4                     # 1/16 is the finest slot the battle sees

# ---- the harmony ----------------------------------------------------------
# v3: the material is no longer typed here. `dna_cw` derives the key, the
# cadence, the two leitmotifs, the two percussion patterns and the bass
# figure from the two `.red` files, and every lookup below reads the SCORE's
# dna rather than a module global. What survives as constants are aliases on
# null DNA — which is v2 exactly, and is also the fallback for a warrior that
# does not assemble. The literal v2 values live in test_score_cw.py, where a
# test can compare them to `DNA.DEFAULT` and mean something.
_V2 = DNA.DEFAULT
PENT = dict(zip(('D', 'F', 'G', 'A', 'C'), _V2.pent))
BB = _V2.death                         # the death note. Nowhere else. Ever.
EMBER_STEPS = _V2.voices[0].steps       # tresillo, dragged and swung
ICE_STEPS = _V2.voices[1].steps         # offbeat garage
ICE_GHOSTS = _V2.voices[1].ghosts
KICK_STEPS = (0, 4, 8, 12)             # four to the floor, gated by tier
BACKBEAT_STEPS = (4, 12)               # deaths ARE the clap
# Kimi's load-in: beat-1 silence, then the 808 picks up on the offbeats.
# These are grid-owned positions and always were; they used to clear the
# anti-noise test only because v2's ICE_STEPS happened to contain all
# three of them, which is a coincidence a derived pattern will not repeat.
ANACRUSIS_STEPS = (6, 10, 14)

# Section gain. The mix law is a quiet room that events puncture, and that
# has to be true bar to bar as well as event to event: a breakdown that sits
# at groove level is not a breakdown, it is just a bar without drums.
SECTION_GAIN = {'intro': 0.50, 'groove': 0.92, 'riser': 0.70,
                'drop': 1.30, 'breakdown': 0.40}

TIER_THRESHOLDS = (0.18, 0.34, 0.52, 0.70)
TIER_UP_BARS, TIER_DOWN_BARS = 2, 4    # builds are fast, decays are slow

ADDITIVE_CHUNK = 1 << 18        # samples per additive block (~6 s)

PAN_EMBER, PAN_ICE = -0.25, 0.25

# Ember's groove: 56% swing and an 8 ms drag, FIXED for the whole match.
# Opus scales swing depth with the bar's spl count and the kick colour list
# scales it with ground share — but a swing that moves with battle state is
# the battle placing onsets in time by the back door, and the anti-noise law
# outranks the flavour. Ember drags because ember is ember, not because it is
# winning; what territory changes is drive, pitch floor, click and reverb.
EMBER_SWING = 0.56
EMBER_DRAG = 0.008


class Grid:
    """Bar/beat/step arithmetic. Pure, so it is trivially testable — and it
    is the only thing in the system allowed to decide when a sound starts."""

    def __init__(self, bpm=BPM, beats=BEATS_PER_BAR, div=STEPS_PER_BEAT):
        self.bpm = float(bpm)
        self.beats = beats
        self.div = div
        self.beat_s = 60.0 / self.bpm
        self.step_s = self.beat_s / div
        self.bar_s = self.beat_s * beats
        self.steps_per_bar = beats * div

    def step(self, i):
        return i * self.step_s

    def bar(self, i):
        return i * self.bar_s

    def step_index(self, t):
        return int(math.floor(t / self.step_s + 1e-9))

    def bar_index(self, t):
        return int(math.floor(t / self.bar_s + 1e-9))

    def snap(self, t, unit='step'):
        """Nearest grid line at or after t — sections join at bar lines and
        accents land on 1/16 lines, and neither is ever allowed to land
        between them."""
        u = self.bar_s if unit == 'bar' else (
            self.beat_s if unit == 'beat' else self.step_s)
        return math.ceil(t / u - 1e-9) * u

    def n_steps(self, duration):
        return int(math.ceil(duration / self.step_s)) + 1

    def n_bars(self, duration):
        return int(math.ceil(duration / self.bar_s)) + 1


# ---------------------------------------------------------------------------
# the arranger
# ---------------------------------------------------------------------------
class Score:
    """What the battle decided, expressed entirely in grid coordinates.

    Every scheduled sound in here carries an integer step index, never a
    timestamp — which is the anti-noise law made structural rather than
    merely intended. `moments` is the one exception and holds the elimination,
    whose silence belongs to the picture."""

    def __init__(self, grid, duration):
        self.grid = grid
        self.duration = duration
        self.n_bars = grid.n_bars(duration)
        self.n_steps = grid.n_steps(duration)
        self.bombs = {}          # (step, w) -> (count, stride, spread)
        self.deaths = {}         # (step, w) -> count
        self.spls = {}           # (step, w) -> count
        self.share = None        # per-bar ember ground share
        self.energy = None
        self.momentum = None
        self.pressure = None
        self.contest = None
        self.intensity = None
        self.tier = None         # per-bar, after hysteresis
        self.sections = []       # (start_bar, end_bar, kind)
        self.cues = []           # dicts: kind, bar, t, ...
        self.moments = []        # unquantized: the elimination only
        self.first_blood_bars = set()
        self.scheduled = []      # (t, layer) for every rhythmic onset placed
        # WHAT this match plays, as opposed to how. Null DNA is v2, so a
        # Score built without an analyze() pass still holds a complete,
        # playable, already-shipped set of material.
        self.set_dna(DNA.DEFAULT)

    def set_dna(self, dna):
        """The material, frozen for the whole match. Frozen is the point: the
        patterns are chosen once, offline, so the battle still only selects
        which of the existing slots fire and never gains the power to place
        one. Deriving the vocabulary does not touch the anti-noise law.

        Refuses a DNA whose percussion has not been frozen yet: the object
        `extract()` publishes on `tl.dna` knows the key but not the patterns,
        and rendering from it would mean rendering from an absence."""
        if not dna.frozen:
            raise ValueError(
                'DNA has no percussion yet — call with_behaviour() first '
                '(tl.dna is pre-behaviour by design; analyze() freezes it)')
        self.dna = dna
        self.pent = dna.pent
        self.chords = dna.chords
        self.death = dna.death
        self.steps = (dna.voices[0].steps, dna.voices[1].steps)
        self.ghosts = dna.voices[1].ghosts

    def note(self, t, layer, w=None):
        """Record an onset as the renderer places it. This is the anti-noise
        law's evidence: a test walks this list and checks that every single
        entry sits on a position the fixed patterns allow. A sound that is
        not on the grid cannot hide in the audio if it had to be written
        down here first."""
        self.scheduled.append((float(t), layer, w))
        return t

    def onsets(self):
        """Every onset the score will produce, as grid step indices. The
        anti-noise test reads this: if a rendered sound is not accounted for
        here, something placed a sound in time that had no right to."""
        out = set()
        for (s, w) in self.bombs:
            out.add(s)
        for (s, w) in self.deaths:
            out.add(s)
        return out

    def section_at(self, bar):
        for a, b, kind in self.sections:
            if a <= bar < b:
                return kind
        return 'groove'

    def pattern_offsets(self, layer=None, w=None):
        """Every position inside a bar at which this system is ALLOWED to
        put a sound, in seconds. The battle can pick from these and change
        their velocity and timbre; it can never add one and never move one.
        The anti-noise test reads this: shift the whole battle by 30 ms and
        the rendered onsets must still fall only here.

        The riser's snare roll is the one layer that uses all sixteen slots —
        a roll is a roll — but its acceleration comes from the riser's own
        fixed schedule, not from anything the battle did, so it is still the
        grid placing the sounds."""
        g = self.grid
        if layer in ('roll', 'relock'):
            # The riser's roll uses all sixteen slots because a roll is a
            # roll; the post-drop relock uses whichever 1/16 comes next,
            # because the DECISION says the grid re-locks on the next 1/16
            # after a payload that was never on the grid to begin with.
            # Both are the grid placing sounds; neither follows the kick
            # pattern, and pretending they did would have this test pass on
            # a coincidence.
            return sorted(round(step_time(1, s, 0.0, g), 6)
                          for s in range(g.steps_per_bar))
        if layer == 'motif':
            # The leitmotif's RHYTHM is grid-owned and fixed — DNA writes its
            # pitches and its articulation, never its onsets. Checking it
            # against its own pattern is stricter than checking it against
            # the perc grid, which it used to clear on a coincidence.
            ww = w if w in (0, 1) else 0
            v = self.dna.voices[ww]
            steps = set(MOTIF_STEPS)
            for i, s in enumerate(MOTIF_STEPS):
                # `s > 0` mirrors _motif's own guard: a grace note on the
                # downbeat would have to sound in the previous bar, so the
                # renderer drops it. The allowed set has to be exactly the
                # rendered set — a slot nothing can ever fill is a hole in
                # the anti-noise test, not a harmless extra.
                if s > 0 and i < len(v.artic) and v.artic[i] == 'grace':
                    steps.add((s - 1) % g.steps_per_bar)
            return sorted(round(step_time(ww, s, 0.0, g), 6) for s in steps)
        if layer == 'bass':
            return sorted(round(step_time(1, s, 0.0, g), 6)
                          for s in self.dna.bass_steps())
        offs = set()
        if w in (None, 1):
            for s in (KICK_STEPS + BACKBEAT_STEPS + ANACRUSIS_STEPS
                      + tuple(self.steps[1]) + tuple(self.ghosts)):
                offs.add(round(step_time(1, s, 0.0, g), 6))
        if w in (None, 0):
            for s in tuple(self.steps[0]) + BACKBEAT_STEPS + KICK_STEPS:
                offs.add(round(step_time(0, s, 0.0, g), 6))
        if layer is None and w is None:
            offs.update(self.pattern_offsets('roll'))
            offs.update(self.pattern_offsets('bass'))
            for ww in (0, 1):
                offs.update(self.pattern_offsets('motif', ww))
        return sorted(offs)

    def section_pos(self, bar):
        """(index within the section, section length) — a riser has to know
        how far along it is, because the whole gesture is a strip-down."""
        for a, b, _kind in self.sections:
            if a <= bar < b:
                return bar - a, b - a
        return 0, 1

    def cue_at(self, bar, kind=None):
        for c in self.cues:
            if c['bar'] == bar and (kind is None or c['kind'] == kind):
                return c
        return None


def _median(xs):
    """Integer throughout. An even-length median would otherwise land on a
    .5 and put a float on the path that selects material, which the
    determinism law forbids — bucket edges must be crossed by counting, not
    by whatever the float rounds to."""
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return 0
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) // 2


def analyze(tl, grid=None, dna=None):
    """One offline pass over the whole timeline. Offline is the entire
    advantage this render has over a live one: a build can anticipate a kill
    that has not happened yet, which is why the drop can be wanted rather
    than merely reacted to.

    It is also what lets the percussion be DERIVED without becoming
    sonification: the vote pass below already measures how densely each army
    bombs and how far it reaches, and those two numbers pick the match's
    patterns once, here, for the whole track."""
    grid = grid or Grid()
    sc = Score(grid, tl.duration)
    base = dna or getattr(tl, 'dna', None) or DNA.DEFAULT
    ns, nb = sc.n_steps, sc.n_bars

    # --- per-step votes. Bombs never make a sound; they vote for a slot. ---
    per_step = {}
    for t, kind, addr, w, _x in tl.events:
        s = grid.step_index(t)
        if s >= ns:
            continue
        if kind == 'bomb':
            per_step.setdefault((s, w), []).append(addr)
        elif kind == 'death':
            sc.deaths[(s, w)] = sc.deaths.get((s, w), 0) + 1
        elif kind == 'spl':
            sc.spls[(s, w)] = sc.spls.get((s, w), 0) + 1
    for (s, w), addrs in per_step.items():
        a = sorted(addrs)
        diffs = [a[i + 1] - a[i] for i in range(len(a) - 1)]
        stride = _median(diffs) if diffs else 0
        spread = len({x // 100 for x in a})
        sc.bombs[(s, w)] = (len(a), stride, spread)

    # --- behaviour -> vocabulary, once, for the whole match ----------------
    # How hard an army bombs picks the onset count of its Euclidean pattern;
    # how far it reaches picks where its ghosts sit. Both are medians over
    # the entire timeline and both are bucketed, so a rematch lands in the
    # same bucket rather than one bomb away from a different one.
    dens, strd = [], []
    for w in (0, 1):
        per_bar, strides = {}, []
        for (s, ww), (cnt, stride, _sp) in sc.bombs.items():
            if ww != w:
                continue
            b = s // grid.steps_per_bar
            per_bar[b] = per_bar.get(b, 0) + cnt
            strides.append(stride)
        dens.append(_median(list(per_bar.values())))
        strd.append(_median(strides))
    sc.set_dna(base.with_behaviour(tuple(dens), tuple(strd)))

    # --- bar-resolution curves --------------------------------------------
    mt = np.array([m[0] for m in tl.metrics], dtype=np.float64) if tl.metrics \
        else np.array([0.0])
    # np.interp needs x increasing and returns garbage without saying so if it
    # is not. The frame clock only ever moves forward, so this never fires on
    # a real timeline — it costs one pass to make that an enforced property
    # rather than an assumption about a hook we do not own.
    mt = np.maximum.accumulate(mt)
    own_a = np.array([m[1] for m in tl.metrics], dtype=np.float64) if tl.metrics \
        else np.array([0.0])
    own_b = np.array([m[2] for m in tl.metrics], dtype=np.float64) if tl.metrics \
        else np.array([0.0])
    procs = np.array([m[3] + m[4] for m in tl.metrics], dtype=np.float64) \
        if tl.metrics else np.array([1.0])
    bar_t = np.arange(nb) * grid.bar_s + grid.bar_s * 0.5
    oa = np.interp(bar_t, mt, own_a, left=own_a[0], right=own_a[-1])
    ob = np.interp(bar_t, mt, own_b, left=own_b[0], right=own_b[-1])
    pr = np.interp(bar_t, mt, procs, left=procs[0], right=procs[-1])
    total = np.maximum(1.0, oa + ob)
    sc.share = oa / total
    claimed = np.clip((oa + ob) / 8000.0, 0, 1)
    sc.pressure = np.clip(np.log2(np.maximum(1.0, pr)) / 7.0, 0, 1)
    sc.contest = np.clip(4.0 * sc.share * (1.0 - sc.share), 0, 1)
    bombs_per_bar = np.zeros(nb)
    for (s, _w), (n, _d, _sp) in sc.bombs.items():
        b = s // grid.steps_per_bar
        if b < nb:
            bombs_per_bar[b] += n
    bps = bombs_per_bar / grid.bar_s
    sc.energy = np.clip(np.log10(1.0 + bps) / np.log10(401.0), 0, 1)
    dclaim = np.abs(np.diff(claimed, prepend=claimed[0])) / grid.bar_s
    sc.momentum = np.clip(dclaim / 0.02, 0, 1)
    sc.intensity = (0.42 * sc.energy + 0.28 * sc.momentum
                    + 0.20 * sc.pressure + 0.10 * sc.contest)

    # --- tiers, with hysteresis. A flapping arrangement is worse than a
    # flat one, so a tier rises after 2 bars and falls only after 4. -------
    cut_bars = {grid.bar_index(t) for t, k, *_ in tl.events if k == 'round-cut'}
    tier = np.zeros(nb, dtype=int)
    cur, up, down = 0, 0, 0
    for b in range(nb):
        want = 0
        for i, th in enumerate(TIER_THRESHOLDS):
            if sc.intensity[b] >= th:
                want = i + 1
        if b in cut_bars:
            cur, up, down = 0, 0, 0
        elif want > cur:
            up += 1
            down = 0
            if up >= TIER_UP_BARS:
                cur += 1
                up = 0
        elif want < cur:
            down += 1
            up = 0
            if down >= TIER_DOWN_BARS:
                cur -= 1
                down = 0
        else:
            up = down = 0
        tier[b] = cur
    sc.tier = tier

    # One crash per round, not one per match: the picture's first-blood
    # field resets at every round start, so keeping only the first event
    # left rounds 2 and 3 of a stalemate with no crash at all.
    sc.first_blood_bars = {grid.bar_index(t) for t, *_ in tl.of('first-blood')}

    # --- sections and cues -------------------------------------------------
    _arrange(sc, tl, grid)
    return sc


def _arrange(sc, tl, grid):
    """Phrase blocks, joined at bar lines, never shorter than 2 bars."""
    nb = sc.n_bars
    cuts = [(grid.bar_index(t), x.get('n'), x.get('out'))
            for t, k, _a, _w, x in tl.events if k == 'round-cut']
    if not cuts:
        sc.sections = [(0, nb, 'groove')]
        return
    elim_times = [(t, w, x) for t, k, _a, w, x in tl.events
                  if k == 'elimination']
    verdicts = [(grid.bar_index(t), x) for t, k, _a, _w, x in tl.events
                if k == 'verdict']
    ends = [b for b, _n, _o in cuts[1:]] + [nb]

    for idx, ((start, _n, out), stop) in enumerate(zip(cuts, ends)):
        # INTRO: the load-in. One bar of anacrusis, the first round gets two.
        intro = 2 if idx == 0 else 1
        body_start = min(stop, start + intro)

        # where does this round drop? A kill drops at the kill. A tie drops
        # at its own peak — every round earns a drop, but only a kill spends
        # the silence and the outside note on it.
        drop_t, drop_bar, kind, loser, extra = None, None, None, None, None
        for t, w, x in elim_times:
            if start <= grid.bar_index(t) < stop:
                drop_t, kind, loser, extra = t, 'kill', w, x
                drop_bar = grid.bar_index(t)
                break
        if drop_bar is None:
            # A tie round drops too, but it has to drop LATE: the peak of a
            # stalemate is usually its opening exchange, and a drop at bar 4
            # of a 28-bar round inverts the arc — everything after it is an
            # anticlimax. The search is confined to the round's second half,
            # with room left for the payoff to breathe before the verdict.
            span = stop - body_start
            lo = body_start + max(2, int(span * 0.45))
            hi = stop - 6
            # Clamped to the curve, and the emptiness actually tested. The
            # old `hi = max(lo + 1, ...)` guard could never fail, so a short
            # round — which a sliced extraction produces routinely — reached
            # np.argmax with an empty slice and raised.
            lo = max(0, min(lo, len(sc.intensity)))
            hi = max(0, min(hi, len(sc.intensity)))
            if hi > lo:
                peak = int(np.argmax(sc.intensity[lo:hi])) + lo
                drop_bar, kind = peak, 'tie'
                drop_t = grid.bar(peak)

        # A KILL'S DROP ALWAYS FIRES. If the elimination lands inside the
        # intro — a warrior that dies on its first turn does exactly that —
        # the intro yields whatever bars it has so a minimum build still
        # exists, and if there is nothing to yield the round simply opens on
        # the drop. Skipping the cue would take the Bb recolor and the
        # eight-bar payoff with it and leave the kill as an isolated
        # stinger over an arrangement that never noticed.
        if kind == 'kill' and drop_bar is not None and drop_bar <= body_start:
            body_start = max(start, drop_bar - 1)
        blocks = []
        if body_start > start:
            blocks.append((start, body_start, 'intro'))
        if drop_bar is not None and drop_bar > body_start:
            riser_bars = min(4, drop_bar - body_start)
            riser_start = drop_bar - riser_bars
            if riser_start > body_start:
                blocks.append((body_start, riser_start, 'groove'))
            blocks.append((riser_start, drop_bar, 'riser'))
            sc.cues.append({'kind': 'riser', 'bar': riser_start,
                            'until': drop_t, 'drop': kind})
        if drop_bar is not None:
            payoff_end = min(stop, drop_bar + 8)
            if payoff_end > drop_bar:
                blocks.append((drop_bar, payoff_end, 'drop'))
            sc.cues.append({'kind': 'drop', 'bar': drop_bar, 't': drop_t,
                            'drop': kind, 'loser': loser, 'extra': extra})
            after = max(body_start, payoff_end)
        else:
            after = body_start

        vb = [b for b, _x in verdicts if start <= b < stop]
        bd = min(vb) if vb else max(after, stop - 2)
        if bd > after:
            blocks.append((after, bd, 'groove'))
        blocks.append((max(after, bd), stop, 'breakdown'))
        sc.sections.extend((a, b, k) for a, b, k in blocks if b > a)

    end = tl.of('match-end')
    if end:
        t, _k, _a, w, x = end[0]
        b = grid.bar_index(t)
        sc.cues.append({'kind': 'end', 'bar': b, 't': t,
                        'drawn': bool(x.get('drawn')), 'winner': w,
                        'span': float(x.get('span', 2.0))})
    # An army is dead FOR ITS ROUND, not for the match. Without the window
    # the next round starts with one faction already silent, which is both
    # wrong and the most obvious possible bug to leave in a three-round track.
    cut_ts = sorted(t for t, k, *_ in tl.events if k == 'round-cut')
    for t, _k, addr, loser, x in tl.of('elimination'):
        later = [c for c in cut_ts if c > t]
        sc.moments.append({'kind': 'elimination', 't': t, 'loser': loser,
                           'hitstop': float(x.get('hitstop', 0.0)),
                           'sweep': float(x.get('sweep', 2.0)),
                           'addr': addr,
                           'until': later[0] if later else sc.duration})
    sc.sections.sort()


# ---------------------------------------------------------------------------
# DSP — additive, so a moving filter is a gain array
# ---------------------------------------------------------------------------
def hashnoise(idx, seed=0.0):
    x = np.sin(idx * 12.9898 + seed * 78.233) * 43758.5453
    return (2.0 * (x - np.floor(x)) - 1.0).astype(np.float32)


def noise(n, seed=0.0, start=0):
    return hashnoise(np.arange(start, start + n) * 0.7 + 1.0, seed)


def fir_lp(sig, cutoff):
    """A box-average low pass. Cheap, deterministic, and good enough for
    noise sources — the tonal ones do not need a filter at all."""
    k = max(1, int(SR / max(60.0, cutoff * 2.0)))
    if k <= 1:
        return sig
    kern = np.ones(k, dtype=np.float32) / k
    return np.convolve(sig, kern, mode='same').astype(np.float32)


def fir_hp(sig, cutoff):
    return (sig - fir_lp(sig, cutoff)).astype(np.float32)


def env_ad(n, attack, decay, curve=1.0):
    t = np.arange(n) / SR
    a = max(1e-4, attack)
    out = np.where(t < a, t / a, np.exp(-(t - a) / max(1e-4, decay)) ** curve)
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def harm_gain(freqs, cutoff, order=2):
    """The whole filtering story: a per-harmonic gain against a cutoff that
    may be a scalar or a curve. `freqs` is (H,), `cutoff` scalar or (N,);
    result broadcasts to (H, N) or (H,)."""
    f = np.asarray(freqs, dtype=np.float64)
    if np.isscalar(cutoff):
        return (1.0 / np.sqrt(1.0 + (f / max(1.0, cutoff)) ** (2 * order)))
    c = np.maximum(1.0, np.asarray(cutoff, dtype=np.float64))
    return 1.0 / np.sqrt(1.0 + (f[:, None] / c[None, :]) ** (2 * order))


def additive(freq, n, harmonics=8, cutoff=8000.0, detune_cents=(0.0,),
             odd_only=False, phase=0.0, amp_law=1.0):
    """A saw/square-ish stack with a (possibly moving) low pass baked in as
    per-harmonic gain. This is the one implementation trick that makes a
    time-varying filter affordable in numpy."""
    out = np.zeros(n, dtype=np.float64)
    hs = np.arange(1, harmonics + 1)
    if odd_only:
        hs = hs[hs % 2 == 1]
    # Chunked over TIME, not over harmonics. The (H, N) matrix for a
    # match-length bed is a ~230 MB transient per detune voice and grows
    # with the match; chunking the time axis bounds it at H x CHUNK. It is
    # also bit-identical, which chunking the harmonic axis would not be:
    # the sum is along axis 0, so every output sample is computed from
    # exactly the same values in exactly the same order as before.
    for cents in detune_cents:
        f0 = freq * (2.0 ** (cents / 1200.0))
        fh = f0 * hs
        keep = fh < 17000.0
        fh, hh = fh[keep], hs[keep]
        if not len(fh):
            continue
        amp = (hh ** amp_law).astype(np.float64)
        for a in range(0, n, ADDITIVE_CHUNK):
            b = min(n, a + ADDITIVE_CHUNK)
            t = np.arange(a, b, dtype=np.float64) / SR
            cut = cutoff if np.isscalar(cutoff) else cutoff[a:b]
            g = harm_gain(fh, cut)
            g = (g / amp) if g.ndim == 1 else (g / amp[:, None])
            wave = np.sin(2 * np.pi * fh[:, None] * t[None, :] + phase)
            out[a:b] += (wave * (g[:, None] if g.ndim == 1 else g)).sum(axis=0)
    return (out / max(1, len(detune_cents))).astype(np.float32)


def sine(freq, n, phase=0.0):
    return np.sin(2 * np.pi * freq * np.arange(n) / SR
                  + phase).astype(np.float32)


def sweep(f0, f1, n, curve=3.0):
    t = np.arange(n) / SR
    k = (t / max(1e-6, t[-1] if n > 1 else 1.0)) ** curve
    f = f0 + (f1 - f0) * k
    return np.sin(2 * np.pi * np.cumsum(f) / SR).astype(np.float32)


def tanh_drive(x, k):
    return (np.tanh(x * k) / math.tanh(k)).astype(np.float32) if k > 0.01 else x


def norm(sig, peak=1.0):
    m = float(np.max(np.abs(sig)))
    return sig if m <= 0 else (sig * (peak / m)).astype(np.float32)


# ---- the instrument library (kimi.md's recipes) ---------------------------
def synth_kick(pitch_floor=55.0, drive=1.8, click_hp=4000.0):
    """808: a 110 -> floor sweep in 80 ms with a click on top. The floor,
    the drive and the click brightness all come from who holds the core, so
    the shared kick still says whose record this is."""
    n = int(0.34 * SR)
    body = sweep(110.0, pitch_floor, n, curve=0.35) * env_ad(n, 0.002, 0.075)
    click = sine(click_hp, int(0.008 * SR)) * env_ad(int(0.008 * SR),
                                                     0.0004, 0.0025)
    out = body.copy()
    out[:len(click)] += click * 0.6
    return norm(tanh_drive(out, drive), 1.0)


def synth_sub(freq, seconds=0.30):
    n = int(seconds * SR)
    return norm(sine(freq, n) * env_ad(n, 0.004, seconds * 0.4))


def supersaw(freq, n, cutoff, res=0.0):
    """3-voice, -7/0/+19 cents, through the moving low pass."""
    out = additive(freq, n, harmonics=12, cutoff=cutoff,
                   detune_cents=(-7.0, 0.0, 19.0))
    if res > 0:
        # a resonant bump: one extra partial sitting at the cutoff
        fc = float(np.mean(cutoff)) if not np.isscalar(cutoff) else cutoff
        out = out + sine(min(fc, 4000.0), n) * (0.16 * res)
    return out.astype(np.float32)


def fm_bell(freq, n, ratio=3.14, index0=4.0, index1=0.5, decay=0.12):
    t = np.arange(n) / SR
    idx = index1 + (index0 - index1) * np.exp(-t / max(1e-4, decay))
    mod = np.sin(2 * np.pi * freq * ratio * t) * idx
    return (np.sin(2 * np.pi * freq * t + mod)
            * env_ad(n, 0.001, decay * 1.6)).astype(np.float32)


def synth_hat(open_hat=False, seed=0.0):
    """Two sines beating at 234 Hz, ring-modulated and high-passed — a
    metallic tick with no sample and no noise generator."""
    dur = 0.12 if open_hat else 0.042
    n = int(dur * SR)
    ring = sine(8000.0, n) * sine(8234.0, n)
    if open_hat:
        ring = ring + sine(12000.0, n) * 0.3
    return norm(fir_hp(ring, 3000.0) * env_ad(n, 0.0006, dur * 0.35))


def coal_crackle(seed=0.0):
    n = int(0.09 * SR)
    return norm(fir_lp(noise(n, seed), 800.0) * env_ad(n, 0.001, 0.035))


def cryo_thud():
    n = int(0.05 * SR)
    return norm(sine(293.66, n) * env_ad(n, 0.0008, 0.012))


def clap(seed=0.0):
    """Four bursts at 0/9/17/26 ms, band-passed, with a short tail."""
    n = int(0.20 * SR)
    out = np.zeros(n, dtype=np.float32)
    src = fir_hp(fir_lp(noise(n, seed), 2400.0), 900.0)
    for i, off in enumerate((0.0, 0.009, 0.017, 0.026)):
        o = int(off * SR)
        seg = src[:n - o] * env_ad(n - o, 0.0005, 0.006)
        out[o:] += seg * (1.0 - 0.15 * i)
    out += src * env_ad(n, 0.028, 0.055) * 0.5
    return norm(out)


def snare(seed=0.0):
    n = int(0.12 * SR)
    body = sine(190.0, n) * env_ad(n, 0.001, 0.03)
    return norm(fir_hp(noise(n, seed), 1500.0) * env_ad(n, 0.001, 0.05)
                + body * 0.5)


def pluck(freq, n, ember=True):
    if ember:
        return norm(additive(freq, n, harmonics=5, cutoff=3200.0,
                             detune_cents=(0.0, 12.0))
                    * env_ad(n, 0.003, 0.16))
    return norm(fm_bell(freq, n, decay=0.16) * env_ad(n, 0.002, 0.18))


def bell_pad(freq, n, cutoff=6000.0):
    t = np.arange(n) / SR
    out = np.zeros(n, dtype=np.float64)
    for ratio, amp in ((1.0, 1.0), (2.01, 0.5), (3.03, 0.28), (4.21, 0.14),
                       (6.18, 0.08)):
        f = freq * ratio
        if f > 16000:
            continue
        out += amp * np.sin(2 * np.pi * f * t) * float(harm_gain([f], cutoff)[0])
    trem = 0.85 + 0.15 * np.sin(2 * np.pi * 0.37 * t)
    return (out * trem).astype(np.float32)


def shepard_riser(n, root=146.83, octaves=4):
    """Stacked octaves whose amplitudes crossfade upward — climbs forever
    without ever arriving, which is the point of a riser."""
    t = np.arange(n) / SR
    p = t / max(1e-6, t[-1] if n > 1 else 1.0)
    out = np.zeros(n, dtype=np.float64)
    for k in range(octaves):
        pos = (p + k / octaves) % 1.0
        f = root * (2.0 ** (pos * octaves))
        amp = np.sin(np.pi * pos) ** 2
        out += np.sin(2 * np.pi * np.cumsum(f) / SR) * amp
    return (out / octaves).astype(np.float32)


def noise_riser(n, f0=200.0, f1=8000.0, seed=3.0):
    src = noise(n, seed)
    blocks = 64
    out = np.zeros(n, dtype=np.float32)
    edges = np.linspace(0, n, blocks + 1).astype(int)
    for i in range(blocks):
        a, b = edges[i], edges[i + 1]
        if b <= a:
            continue
        fc = f0 * (f1 / f0) ** (i / max(1, blocks - 1))
        out[a:b] = fir_hp(src[a:b], fc * 0.5)
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32) ** 2.0
    return norm(out * ramp)


def reverse_cymbal(n, seed=5.0):
    src = fir_hp(noise(n, seed), 4000.0)
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32) ** 2.5
    return norm(src * ramp)


def reverb(sig, feedback=0.72, damp=0.35, wet=1.0):
    """Four prime-length delay lines with Hadamard mixing, processed a block
    at a time so every block reads only history that is already written."""
    lens = (1489, 2131, 3079, 4177)
    n = len(sig)
    bufs = [np.zeros(n + max(lens) + 1, dtype=np.float32) for _ in lens]
    out = np.zeros(n, dtype=np.float32)
    block = lens[0]
    prev = np.zeros(4, dtype=np.float32)
    for start in range(0, n, block):
        end = min(n, start + block)
        m = end - start
        taps = []
        for i, L in enumerate(lens):
            a = start - L
            if a < 0:
                seg = np.zeros(m, dtype=np.float32)
                k = min(m, max(0, end - L))
                if k > 0:
                    seg[m - k:] = bufs[i][0:k]
            else:
                seg = bufs[i][a:a + m]
            taps.append(seg)
        s = sig[start:end]
        h = (taps[0] + taps[1] + taps[2] + taps[3]) * 0.5
        for i in range(4):
            sign = 1.0 if i in (0, 3) else -1.0
            fed = s + feedback * (h * sign * 0.5 + taps[i] * 0.5)
            fed = fed * (1.0 - damp) + np.concatenate(
                ([prev[i]], fed[:-1])) * damp
            bufs[i][start:end] = fed.astype(np.float32)
            prev[i] = fed[-1] if m else prev[i]
        out[start:end] = h.astype(np.float32)
    return (out * wet).astype(np.float32)


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------
class Buses:
    """Four buses so the sidechain and the two production identities can be
    applied to whole groups rather than per-voice."""

    def __init__(self, n):
        self.n = n
        self.drums = np.zeros(n, dtype=np.float32)
        self.sub = np.zeros(n, dtype=np.float32)
        self.emb = np.zeros(n, dtype=np.float32)
        self.ice = np.zeros(n, dtype=np.float32)
        self.fx = np.zeros(n, dtype=np.float32)
        self.bed = np.zeros(n, dtype=np.float32)

    def put(self, bus, sig, at_sample, gain=1.0):
        i = int(at_sample)
        if i >= self.n or gain == 0.0:
            return
        if i < 0:
            sig, i = sig[-i:], 0
        seg = sig[:self.n - i]
        if len(seg):
            bus[i:i + len(seg)] += (seg * gain).astype(np.float32)


def _kick_colour(share_e):
    """The shared kick and sub inherit the dominant faction's studio, so
    territory is audible even when neither side is soloing."""
    dom = float(share_e)
    return {'drive': 1.4 + 1.6 * dom,
            'floor': 41.0 - 6.0 * dom,
            'click': 3000.0 + 4000.0 * (1.0 - dom),
            'reverb': 0.08 + 0.34 * (1.0 - dom)}


def step_time(w, step, bar_t, grid):
    """THE one place a sound's time is computed. Ember drags 8 ms and swings
    its odd 16ths; ice is machine-quantized. The swing moves a note inside
    its own slot — it never chooses a different slot — so the anti-noise law
    holds: the grid still owns where the beat is.

    Every layer routes through here. A layer that computed its own time
    would drift out of its faction's groove and would pass an on-grid test
    only by coincidence, which is exactly the bug this function exists to
    make impossible."""
    t = bar_t + step * grid.step_s
    if w == 0:
        t += EMBER_DRAG
        if step % 2:
            t += (EMBER_SWING - 0.5) * grid.step_s * 2.0
    return t


def _bass_bar(score, root, root_deg, sub_n, t0):
    """One bar of low end, in the match's own bass figure.

    Figure 0 is a single sustained root for the whole bar — v2's sub, and the
    reason this function has a one-segment branch that bypasses the envelope
    entirely: null DNA has to come out of here sample for sample identical.
    The other figures move, and every note they move to is a degree of the
    same pentatonic, so the low end can have a shape without ever inventing
    a pitch. Their onsets are written down like every other onset."""
    grid = score.grid
    fig = score.dna.bass_figure
    if len(fig) == 1:
        score.note(step_time(1, fig[0][0], t0, grid), 'bass', 1)
        return additive(root, sub_n, harmonics=2, cutoff=180.0) * 0.9
    out = np.zeros(sub_n, dtype=np.float32)
    for s, dur, off, mult in fig:
        f = root
        if root_deg is not None and off:
            f = score.pent[(root_deg + off) % len(score.pent)]
            if f < root:
                f *= 2.0
        f *= mult
        a = int(s * grid.step_s * SR)
        seg_n = min(sub_n - a, int(dur * grid.step_s * SR))
        if seg_n <= 0:
            continue
        seg = additive(f, seg_n, harmonics=2, cutoff=180.0) * 0.9
        out[a:a + seg_n] += seg * env_ad(seg_n, 0.004,
                                         dur * grid.step_s * 0.5)
        score.note(step_time(1, s, t0, grid), 'bass', 1)
    return out


def render_score(score, tl, mix, log=None):
    """Every layer, bar by bar. The battle has already made all its
    decisions; this only spends them."""
    grid = score.grid
    n = mix.n
    bus = Buses(n)
    sec_per_bar = grid.bar_s
    kick_times = []

    # ---- bed: the room. Always present, never loud. ----------------------
    t_all = np.arange(n) / SR
    breath = 0.55 + 0.45 * np.sin(2 * np.pi * t_all / 30.0)
    bed = (additive(score.pent[0], n, harmonics=4, cutoff=400.0,
                    detune_cents=(-4.0, 0.0)) * 0.6
           + sine(score.pent[0] * 2, n) * 0.3)
    bus.bed += (bed * breath * 0.5).astype(np.float32)

    drop_cues = {c['bar']: c for c in score.cues if c['kind'] == 'drop'}
    riser_cues = {c['bar']: c for c in score.cues if c['kind'] == 'riser'}
    end_cue = next((c for c in score.cues if c['kind'] == 'end'), None)
    # A draw stops the record dead on the final downbeat — no fill, no
    # ritardando, no arrangement carrying on underneath. What is left is the
    # merged drone, and it has to be the only thing left or it cannot be
    # heard to dissolve.
    silent_from = (end_cue['bar'] if end_cue and end_cue['drawn'] else None)
    # after a kill the loser is GONE, not faded
    dead_windows = [(m['t'] + m['hitstop'], m['until'], m['loser'])
                    for m in score.moments]

    for b in range(score.n_bars):
        t0 = grid.bar(b)
        if t0 >= score.duration:
            break
        i0 = int(t0 * SR)
        kind = score.section_at(b)
        tier = int(score.tier[b])
        share = float(score.share[b])
        col = _kick_colour(share)
        chord_deg = score.dna.chord_degrees[
            (b // 2) % len(score.chords)][0]
        chord_root, chord_tones = score.chords[(b // 2) % len(score.chords)]
        drop = drop_cues.get(b)
        in_riser = kind == 'riser'
        sg = SECTION_GAIN.get(kind, 1.0)
        if silent_from is not None and b >= silent_from:
            continue
        rpos, rlen = score.section_pos(b)
        if in_riser and rpos >= max(1, rlen - 1):
            sg *= 0.55            # the last bar before a drop sheds the pads
        # the riser pins the tier at maximum and forbids it to fall
        if in_riser:
            tier = 4
        if kind == 'intro':
            tier = min(tier, 1)
        if kind == 'breakdown':
            tier = 0

        # --- the chord loop ------------------------------------------------
        bar_n = int(sec_per_bar * SR) + 1
        mom = float(score.momentum[b])
        cut_lo = 200.0 * (6000.0 / 200.0) ** mom
        cutoff = np.full(bar_n, cut_lo, dtype=np.float64)
        # The death note: the only outside note in the piece, and only here.
        # The recolor is a tritone-free triad built on it out of the home
        # scale's own first two degrees, so it reads as a shadow of the key
        # rather than a modulation into a foreign one.
        root_deg = chord_deg
        if drop and drop['drop'] == 'kill' and b < drop['bar'] + 2:
            root, root_deg = score.death, None
            tones = (score.death, score.pent[0], score.pent[1])
        elif end_cue and end_cue['bar'] == b and not end_cue['drawn']:
            root, root_deg = score.death, None
            tones = (score.death, score.pent[0], score.pent[1])
        else:
            root = chord_root
            tones = chord_tones

        alive_e = not any(a <= t0 < b and w == 0 for a, b, w in dead_windows)
        alive_i = not any(a <= t0 < b and w == 1 for a, b, w in dead_windows)
        ge = math.sqrt(max(0.0, share)) if alive_e else 0.0
        gi = math.sqrt(max(0.0, 1.0 - share)) if alive_i else 0.0
        if not alive_e:
            gi = 1.0
        if not alive_i:
            ge = 1.0

        det = 4.0 + 10.0 * float(score.contest[b])
        pad_e = additive(root * 2, bar_n, harmonics=9, cutoff=cutoff,
                         detune_cents=(-det, 0.0, det)) * 0.5
        for f in tones[1:3]:
            pad_e += additive(f * 2, bar_n, harmonics=7, cutoff=cutoff,
                              detune_cents=(0.0, det)) * 0.22
        bus.put(bus.emb, pad_e, i0, 0.30 * ge * sg)
        pad_i = bell_pad(tones[0] * 16, bar_n, cutoff=9000.0) * 0.5
        if len(tones) > 2:
            pad_i += bell_pad(tones[2] * 16, bar_n, cutoff=9000.0) * 0.3
        bus.put(bus.ice, pad_i, i0, 0.16 * gi * sg)

        # --- sub: the root, sidechained later ------------------------------
        if tier >= 1 and kind not in ('breakdown',) and not (
                in_riser and rpos >= max(1, rlen - 2)):
            sub_n = int(sec_per_bar * SR)
            sub = _bass_bar(score, root, root_deg, sub_n, t0)
            if in_riser:
                # the low end evacuates the room ahead of the drop
                p = np.linspace(0, 1, sub_n, dtype=np.float32)
                sub = sub * (1.0 - p) ** 1.5
            bus.put(bus.sub, sub, i0, 0.40 * sg)

        # --- kick ----------------------------------------------------------
        # In a riser the kick THINS AND THEN LEAVES. A drop is only as big as
        # the hole in front of it, and the cheapest way to make a hole is to
        # take the low end out of the room before you put it back.
        kick_out = in_riser and rpos >= max(1, rlen - 2)
        if tier >= 1 and kind not in ('breakdown', 'intro') and not kick_out:
            steps = KICK_STEPS if tier >= 2 else (0, 8)
            for s in steps:
                if in_riser and s in (4, 12):
                    continue          # kicks thin out so the tension pulls
                st = step_time(1, s, t0, grid)
                if st >= score.duration:
                    continue
                kick_times.append(score.note(st, 'kick', 1))
                bus.put(bus.drums,
                        synth_kick(col['floor'], col['drive'], col['click']),
                        st * SR, 0.62 * sg)
        elif kind == 'intro' and b % 2 == 1:
            for s in ANACRUSIS_STEPS:   # kimi's anacrusis: beat-1 silence
                st = step_time(1, s, t0, grid)
                kick_times.append(score.note(st, 'kick', 1))
                bus.put(bus.drums,
                        synth_kick(col['floor'], col['drive'], col['click']),
                        st * SR, 0.42)

        # --- perc: the bombs vote, the pattern decides ---------------------
        if tier >= 2:
            for w, pattern, ghosts in ((0, score.steps[0], ()),
                                       (1, score.steps[1], score.ghosts)):
                if (w == 0 and not alive_e) or (w == 1 and not alive_i):
                    continue
                for s in pattern + ghosts:
                    idx = b * grid.steps_per_bar + s
                    vote = score.bombs.get((idx, w))
                    if not vote:
                        continue
                    cnt, stride, _spread = vote
                    vel = max(0.25, min(1.0, math.log2(1 + cnt) / 6.0))
                    if s in ghosts:
                        vel *= 0.45
                    st = step_time(w, s, t0, grid)
                    if w == 0:
                        voice = (coal_crackle(idx * 0.017) if stride <= 8
                                 else synth_hat(stride > 500, idx * 0.013))
                        bus.put(bus.emb, voice,
                                score.note(st, 'perc', w) * SR,
                                0.30 * vel * sg)
                    else:
                        if stride == 1:
                            voice = synth_hat(False, idx * 0.011)
                        elif stride > 500:
                            voice = fm_bell(score.pent[0] * 32,
                                            int(0.09 * SR), decay=0.05)
                        else:
                            voice = synth_hat(True, idx * 0.019)
                        bus.put(bus.ice, voice,
                                score.note(st, 'perc', w) * SR,
                                0.24 * vel * sg)

        # --- backbeat: deaths ARE the clap ---------------------------------
        if tier >= 2:
            for s in BACKBEAT_STEPS:
                idx = b * grid.steps_per_bar + s
                for w in (0, 1):
                    if not score.deaths.get((idx, w)):
                        continue
                    st = step_time(w, s, t0, grid)
                    if w == 0:
                        bus.put(bus.emb, clap(idx * 0.023),
                                score.note(st, 'backbeat', w) * SR, 0.34 * sg)
                    else:
                        bus.put(bus.ice, snare(idx * 0.029),
                                score.note(st, 'backbeat', w) * SR, 0.26 * sg)

        # --- lead: the stride writes the melody ----------------------------
        if tier >= 4 and not in_riser:
            for w in (0, 1):
                if (w == 0 and not alive_e) or (w == 1 and not alive_i):
                    continue
                for s in (0, 6, 10) if w == 0 else (2, 10):
                    idx = b * grid.steps_per_bar + s
                    vote = score.bombs.get((idx, w))
                    if not vote:
                        continue
                    cnt, stride, _sp = vote
                    if w == 0:
                        deg = int(abs(stride) // max(1, 1)) % len(tones)
                    else:
                        deg = int(abs(math.sin(idx * 12.9898)) * 5) % len(tones)
                    f = tones[deg] * (8 if w == 0 else 32)
                    st = step_time(w, s, t0, grid)
                    nn = int(0.28 * SR)
                    if w == 0:
                        v = norm(additive(f, nn, harmonics=10,
                                          cutoff=np.linspace(400, 2800, nn),
                                          detune_cents=(0.0, 9.0))
                                 * env_ad(nn, 0.004, 0.12))
                        bus.put(bus.emb, tanh_drive(v, 2.6),
                                score.note(st, 'lead', w) * SR, 0.20 * sg)
                    else:
                        v = pluck(f, nn, ember=False)
                        bus.put(bus.ice, v, score.note(st, 'lead', w) * SR,
                                0.16 * sg)

        # --- the tie drop's payoff -----------------------------------------
        # Every round earns a drop. A tie's is a real one — the low end comes
        # back and the room is hit — but it spends NEITHER the silence NOR
        # the outside note, so a stalemate can never be mistaken for a kill.
        if drop and drop['drop'] == 'tie':
            bus.put(bus.fx, synth_sub(score.pent[0], 1.2), i0, 0.80)
            bus.put(bus.fx, synth_sub(score.pent[0] * 2, 0.9), i0, 0.45)
            nn = int(0.7 * SR)
            bus.put(bus.fx, norm(fir_lp(noise(nn, b * 0.41), 1800.0)
                                 * env_ad(nn, 0.003, 0.22)), i0, 0.30)

        # --- first blood: one crash, once a round --------------------------
        if b in score.first_blood_bars:
            nn = int(0.9 * SR)
            bus.put(bus.fx, norm(fir_hp(noise(nn, 9.0), 5000.0)
                                 * env_ad(nn, 0.002, 0.35)), i0, 0.22)

        # --- riser ----------------------------------------------------------
        if b in riser_cues:
            c = riser_cues[b]
            until = c['until'] if c['until'] is not None else grid.bar(b + 4)
            nn = max(1, int((until - t0) * SR))
            bus.put(bus.fx, noise_riser(nn, 200.0, 9000.0, seed=b * 0.31),
                    i0, 0.26)
            bus.put(bus.fx, norm(shepard_riser(nn, score.pent[0] * 4))
                    * np.linspace(0, 1, nn, dtype=np.float32) ** 2,
                    i0, 0.20)
            roll_steps = max(1, int((until - t0) / grid.step_s))
            for k in range(roll_steps):
                p = k / max(1, roll_steps - 1)
                if p < 0.4 and k % 4:
                    continue
                if p < 0.75 and k % 2:
                    continue
                st = step_time(1, k, t0, grid)
                bus.put(bus.drums, snare(k * 0.037),
                        score.note(st, 'roll', 1) * SR, 0.14 + 0.26 * p)

    if log:
        log(f'  bars {score.n_bars}, kicks {len(kick_times)}, '
            f'tier max {int(score.tier.max())}')

    # ---- the moments that outrank the grid ------------------------------
    _lay_moments(score, tl, bus, kick_times)

    # ---- sidechain: the glue --------------------------------------------
    duck = np.ones(n, dtype=np.float32)
    if kick_times:
        kt = np.array(sorted(set(kick_times)))
        idx = np.clip((kt * SR).astype(int), 0, n - 1)
        last = np.zeros(n, dtype=np.float32)
        last[idx] = 1.0
        # distance since the most recent kick, cheaply: a decaying impulse
        env = np.zeros(n, dtype=np.float32)
        acc = 0.0
        block = 4096
        for a in range(0, n, block):
            bnd = min(n, a + block)
            seg = last[a:bnd]
            e = np.zeros(bnd - a, dtype=np.float32)
            for j in np.flatnonzero(seg):
                e[j] = 1.0
            # exponential smear forward
            k = np.exp(-np.arange(bnd - a) / (0.09 * SR)).astype(np.float32)
            e = np.convolve(e, k)[:bnd - a]
            e[0] = max(e[0], acc)
            env[a:bnd] = np.maximum(e, acc * k[:bnd - a])
            acc = float(env[bnd - 1])
        duck = (1.0 - 0.55 * np.clip(env, 0, 1)).astype(np.float32)
    # The sub is a sustained tone in the kick's own register, so without the
    # duck the kick disappears into it — the groove stops being legible in
    # the low band, which is where a listener reads tempo. Sidechaining the
    # sub is most of what makes this sound like a record.
    bus.sub *= duck
    bus.emb *= duck
    bus.ice *= duck
    bus.bed *= duck * 0.5 + 0.5

    # ---- ice's reverb send, ducking with energy --------------------------
    if float(np.max(np.abs(bus.ice))) > 0:
        send = 0.10 + 0.45 * (1.0 - float(np.mean(score.energy)))
        bus.ice = (bus.ice + reverb(bus.ice * send, feedback=0.70,
                                    damp=0.4) * 0.55).astype(np.float32)
    bus.emb = tanh_drive(bus.emb, 1.6)
    # The reverb runs AFTER the loser was cut, and a 4177-sample tail at 0.70
    # feedback smears straight through the cut — so when the loser was ice,
    # the army that just died went on ringing. Re-cut the window: the layers
    # are gone, and their room goes with them.
    _cut_losers(score, bus)

    # ---- into the stereo bus, with a contest-driven width ----------------
    width = np.interp(np.arange(n) / SR,
                      np.arange(score.n_bars) * grid.bar_s,
                      0.15 + 0.30 * score.contest).astype(np.float32)
    _pan_into(mix, bus.drums, 0.0, 0.62)
    _pan_into(mix, bus.sub, 0.0, 0.55)
    _pan_into(mix, bus.bed, 0.0, 0.30)
    _pan_into(mix, bus.emb, PAN_EMBER * width, 0.75)
    _pan_into(mix, bus.ice, PAN_ICE * width, 0.75)
    _pan_into(mix, bus.fx, 0.0, 0.55)

    # ---- the hitstop. Sample-synced to the picture, never quantized. -----
    for m in score.moments:
        if m['hitstop'] > 0:
            mix.gate(m['t'], m['t'] + m['hitstop'])
    # ...and only now the payoff, so the gate's fade-in cannot touch it.
    _lay_impacts(score, mix)
    return bus


def _pan_into(mix, sig, pan, gain):
    """Equal-power pan that accepts a curve, written straight into the
    stereo buffer — `Mix.add` only takes a scalar."""
    n = min(mix.n, len(sig))
    p = np.clip(pan if np.ndim(pan) else np.full(n, pan), -1, 1)[:n]
    l = np.sqrt(0.5 * (1.0 - p)) * math.sqrt(2)
    r = np.sqrt(0.5 * (1.0 + p)) * math.sqrt(2)
    mix.buf[:n, 0] += (sig[:n] * l * gain).astype(np.float32)
    mix.buf[:n, 1] += (sig[:n] * r * gain).astype(np.float32)


def _lay_moments(score, tl, bus, kick_times):
    """The elimination payoff, the verdicts and the endings."""
    grid = score.grid
    for m in score.moments:
        land = m['t'] + m['hitstop']
        # The payload itself is NOT written here — it is written after the
        # gate (see _lay_impacts). Mix.gate fades back in over 4 ms at the
        # trailing edge so sustained material does not click on the way out
        # of the silence, and those are exactly the samples the Bb impact's
        # own attack occupies: laying it here would ramp the hit twice and
        # the drop would land soft. The relock is still recorded now so the
        # sidechain can see it.
        relock = grid.snap(land, 'step')
        kick_times.append(score.note(relock, 'relock', 1))
        # the loser suffocates: a closing filter, not just a fade
        loser_bus = bus.emb if m['loser'] == 0 else bus.ice
        a, b, end = _loser_window(m, len(loser_bus))
        if b > a:
            ramp = np.linspace(1.0, 0.0, b - a, dtype=np.float32) ** 1.6
            loser_bus[a:b] *= ramp
            loser_bus[b:end] = 0.0        # gone for the ROUND, not the match

    for t, _k, _a, w, x in tl.of('verdict'):
        bar_t = grid.snap(t, 'bar')
        if x.get('out') == 'tie':
            # unresolved: rootless Gsus, and it evaporates
            nn = int(float(x.get('span', 1.4)) * SR)
            ch = (sine(score.pent[2] * 4, nn) + sine(score.pent[4] * 4, nn)
                  * 0.8 + sine(score.pent[0] * 8, nn) * 0.7)
            at = score.note(bar_t, 'verdict', 1)
            bus.put(bus.fx, norm(ch * env_ad(nn, 0.25, 0.55)), at * SR, 0.26)
        else:
            _motif(score, bus, w, bar_t, gain=0.34)

    for c in score.cues:
        if c['kind'] != 'end':
            continue
        if c['drawn']:
            _fade_bed(bus, c['t'], max(0.5, c['span']))
            _draw_outro(bus, c, score)
        else:
            _motif(score, bus, c['winner'], grid.snap(c['t'], 'bar'),
                   gain=0.50, full=True)


def _loser_window(m, n):
    """THE one place the loser's mute window is computed, in samples.

    The ramp and the post-reverb re-cut used to derive the same boundary two
    ways — `int(land*SR) + int(sweep*SR)` against `int((land+sweep)*SR)` —
    which disagree by a sample whenever the two fractions carry. One sample
    of un-muted audio between a ramp that reached zero and a cut that starts
    late is a click, and it would have appeared or not depending on the
    arithmetic of a particular kill time."""
    a = min(n, max(0, int((m['t'] + m['hitstop']) * SR)))
    b = min(n, a + max(1, int(m['sweep'] * SR)))
    end = min(n, max(b, int(m['until'] * SR)))
    return a, b, end


def _cut_losers(score, bus, fade=0.03):
    """Silence each loser's bus for the rest of its round.

    Called after the reverb, because a send applied to a muted bus un-mutes
    it — the ramp drawn earlier zeroes the dry signal, and then the room it
    was still ringing in gets added straight back on top.

    The fade at the far edge is the round boundary: the tail is only zeroed
    up to `until`, since past that the same buffer belongs to the NEXT round
    and must not be touched. A kill landing a second or so before the round
    ends leaves a tail that is still loud at `until` and would reappear from
    silence as a step. Ramping it back in over 30 ms turns a click into a
    boundary nobody hears."""
    for m in score.moments:
        loser_bus = bus.emb if m['loser'] == 0 else bus.ice
        _a, b, end = _loser_window(m, len(loser_bus))
        if end > b:
            loser_bus[b:end] = 0.0
            f = min(int(fade * SR), len(loser_bus) - end)
            if f > 0:
                loser_bus[end:end + f] *= np.linspace(
                    0.0, 1.0, f, dtype=np.float32)


def _lay_impacts(score, mix):
    """The elimination payoff, written straight into the stereo bus AFTER
    the gate. Order is the whole point: the silence is absolute, the room
    returns smoothly for everything that was already playing, and the Bb
    lands with its own attack intact rather than through a second ramp."""
    grid = score.grid
    for m in score.moments:
        land = m['t'] + m['hitstop']
        nn = int(1.8 * SR)
        death = score.death
        sub = (sine(death, nn) * 0.9 + sine(death * 2, nn) * 0.3
               + noise(nn, 7.0) * 0.10)
        payload = norm(sub * env_ad(nn, 0.004, 0.45)) * 0.95
        # THE one onset in the piece that is not on the grid, recorded as
        # such: the silence is synced to the picture's freeze and the payload
        # lands with it. Noting it makes the exception visible to the tests
        # instead of invisible to them.
        _add_mono(mix, payload, score.note(land, 'moment', None), 0.0)
        relock = grid.snap(land, 'step')
        _add_mono(mix, synth_kick(38.0, 2.4, 4200.0) * 0.7, relock, 0.0)


def _add_mono(mix, sig, at, pan=0.0):
    i = int(at * SR)
    if i >= mix.n:
        return
    if i < 0:
        sig, i = sig[-i:], 0
    seg = sig[:mix.n - i]
    if not len(seg):
        return
    l = math.sqrt(0.5 * (1.0 - pan)) * math.sqrt(2)
    r = math.sqrt(0.5 * (1.0 + pan)) * math.sqrt(2)
    mix.buf[i:i + len(seg), 0] += (seg * l).astype(np.float32)
    mix.buf[i:i + len(seg), 1] += (seg * r).astype(np.float32)


MOTIF_STEPS = (0, 2, 4, 8)      # 1/16 slots, not hand-typed seconds


def _motif(score, bus, w, t, gain=0.34, full=False):
    """The winner's four notes resolving home, in their own studio.

    The degrees are this warrior's own leitmotif — the first four of the
    contour its opcodes wrote, with the last forced to degree 0 so that every
    derived theme keeps v2's "resolves home" property. v2's A→C→D→D is
    degrees (3,4,0,0), so null DNA comes out of here unchanged.

    The offsets are STEP INDICES: they used to be 0.222/0.444/0.889 typed as
    floats, which happened to be near the grid without being on it and, worse,
    never went through score.note() — so the anti-noise tests could not see
    the motif at all. One law, one scheduling path, one test. Articulation
    moves how long a note is held, never when it starts; the one exception is
    a grace note, which sits on the 1/16 line before its own and is declared
    to `pattern_offsets` so the test can see it too."""
    voice = score.dna.voices[w]
    degs = voice.finale()
    base = 2 if w == 0 else 16
    g = score.grid
    target = bus.emb if w == 0 else bus.ice

    def voiced(f, nn, decay):
        if w == 0:
            v = norm(additive(f, nn, harmonics=9, cutoff=3000.0,
                              detune_cents=(-5.0, 0.0, 5.0))
                     * env_ad(nn, 0.005, decay))
            return tanh_drive(v, 2.0)
        return norm(fm_bell(f, nn, decay=0.4 if decay > 0.2 else 0.1)
                    * env_ad(nn, 0.002, decay))

    for i, (deg, step) in enumerate(zip(degs, MOTIF_STEPS)):
        # The register law is the faction's, not the warrior's: ember plays
        # its theme in ember's octave and ice in ice's, and the phrase lifts
        # an octave for its second half exactly as v2's did.
        f = score.pent[deg] * base * (2 if i >= 2 else 1)
        last = i == len(degs) - 1
        art = voice.artic[i] if i < len(voice.artic) else 'normal'
        hold = DNA.ARTIC_LEN[art]
        nn = int((1.4 if last else 0.30 * hold) * SR)
        dec = 0.42 if last else 0.09 * hold
        if art == 'grace' and step > 0:
            gf = (score.pent[(deg - 1) % len(score.pent)]
                  * base * (2 if i >= 2 else 1))
            gn = int(0.10 * SR)
            gat = score.note(t + step_time(w, step - 1, 0.0, g), 'motif', w)
            bus.put(target, voiced(gf, gn, 0.05), gat * SR, gain * 0.45)
        at = score.note(t + step_time(w, step, 0.0, g), 'motif', w)
        bus.put(target, voiced(f, nn, dec), at * SR,
                gain * (1.3 if full and last else 1.0))


def _fade_bed(bus, t0, span):
    a = int(t0 * SR)
    n = len(bus.bed) - a
    if n <= 0:
        return
    bus.bed[a:] *= np.exp(-np.arange(n) / (span * SR) * 4.0).astype(np.float32)


def _draw_outro(bus, cue, score):
    """A win stops; a draw dissolves. The two faction voices glide toward
    each other until they are one drone, the stereo field collapses to
    centre, and the amplitude falls exponentially — but never to zero. It
    does not end, it stops being loud enough to hear."""
    t = cue['t']
    span = cue['span'] + 1.0
    n = int(span * SR)
    tt = np.arange(n) / SR
    p = np.clip(tt / span, 0, 1)
    # ember rises, ice falls, both arriving at a shared D3
    f_e = score.pent[0] * 2 * (1.0 + p * 1.0)
    f_i = score.pent[0] * 16 * (1.0 - p * 0.75)
    warm = np.sin(2 * np.pi * np.cumsum(f_e) / SR) * 0.6
    warm += np.sin(2 * np.pi * np.cumsum(f_e * 1.005) / SR) * 0.4
    pure = np.sin(2 * np.pi * np.cumsum(f_i) / SR)
    cluster = np.zeros(n)
    for ratio, amp in ((1.0, 0.5), (2.01, 0.22), (3.03, 0.1)):
        cluster += amp * np.sin(2 * np.pi * np.cumsum(f_i * ratio) / SR)
    drone = (warm * 0.55 + pure * 0.30 + cluster * 0.25).astype(np.float32)
    breath = (0.75 + 0.25 * np.sin(2 * np.pi * tt / 30.0)).astype(np.float32)
    # exponential to about -60 dB, and never gated to zero
    fade = np.exp(-p * 6.9).astype(np.float32)
    # Written down like every other onset. It is not ON the grid and cannot
    # be: a draw's dissolve begins when the picture's end wash begins. That
    # makes it the second audited exemption, and it is registered here so the
    # anti-noise test has to name it rather than never seeing it.
    score.note(t, 'outro', None)
    bus.put(bus.bed, (drone * breath * fade).astype(np.float32), t * SR, 0.55)


def render(tl, mix, log=None):
    """The whole track: analyse once, then spend it. Returns (score, buses)
    so a verification pass can inspect either the decisions or the audio the
    decisions produced."""
    score = analyze(tl)
    buses = render_score(score, tl, mix, log=log)
    return score, buses

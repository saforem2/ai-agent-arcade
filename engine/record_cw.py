"""Core War broadcast master — offline frames + generated soundtrack -> mp4.

Nothing here is a screen capture. `tui_corewar.py` is deterministic and its
pacing is pure, so the picture and the sound are both COMPUTED from the same
transcript and cannot drift: the recorder runs the real animation loop
against a virtual clock, catches the exact bytes the pane would have written
(FRAME_HOOK, one frame at a time), catches every moment worth hearing on the
same clock (EVENT_HOOK), and only then turns one into pixels and the other
into samples. A bomb's flash and a bomb's hit carry the same timestamp
because they came from the same call.

    uv run --with numpy --with pillow python record_cw.py <match-dir> <out.mp4>

The design record is design/corewar-mockups/atlas/soundtrack-spec.md.

THE MUSIC LIVES IN `score_cw.py`. This file owns the timeline, the frames
and the mux; the track system owns the grid, the harmony and every choice
about what a bomb sounds like. v1 put a sound at every event and the result
was weather — the split exists so that the plumbing, which was right, could
survive the brain, which was not.

Determinism: same transcript -> byte-identical WAV and frames. The render
path has exactly one RNG user (the elimination shake), so the recorder seeds
`random` from the transcript itself; every synthesis term is a sin-hash of
(address, index), never a draw.
"""
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

SR = 44100
FPS = 24.0
MASTER_W, MASTER_H = 1920, 1080
PANE_COLS, PANE_ROWS = 87, 24        # 24 rows: the ledger earns its own line

FFMPEG = shutil.which('ffmpeg') or 'ffmpeg'
_full = '/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg'
if Path(_full).exists():
    FFMPEG = _full

# ---------------------------------------------------------------------------
# Timeline extraction — the real animation loop, on a clock that costs nothing
# ---------------------------------------------------------------------------
class VirtualClock:
    """`sleep` advances time instead of spending it. The animation is then
    free to run at its true broadcast pace in a few seconds of CPU, and every
    timestamp it hands out is the one a live viewer would have experienced."""

    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += max(0.0, seconds)


class FrameSink:
    """Stands in for stdout during the run. `render()` writes one whole frame
    per call and then fires FRAME_HOOK, so the hook is the cut point: whatever
    has been written since the last cut IS the frame."""

    def __init__(self):
        self.buf = []
        self.frames = []             # (t, ansi text)

    def write(self, s):
        self.buf.append(s)

    def flush(self):
        pass

    def cut(self, t):
        self.frames.append((t, ''.join(self.buf)))
        self.buf = []


class Timeline:
    """Everything the picture and the sound are built from."""

    def __init__(self):
        self.frames = []             # (t, ansi)
        self.events = []             # (t, kind, addr, warrior, extra)
        self.metrics = []            # (t, own_a, own_b, procs_a, procs_b)
        self.duration = 0.0
        self.names = ('A', 'B')
        self.warriors = (None, None)
        self.dna = None              # what this match PLAYS; see dna_cw.py

    def of(self, *kinds):
        return [e for e in self.events if e[1] in kinds]


def extract(match_dir, cols=PANE_COLS, rows=PANE_ROWS, rounds=None):
    """Run the whole broadcast headless and return its Timeline.

    The renderer's bus paths are re-pointed at the match dir for the run and
    restored afterwards, so this composes with anything else holding the
    module (the test suite does). Nothing here reimplements pacing:
    `animate_round` and `end_wash` are the same functions the pane calls, and
    the clock underneath them is the only thing that changed."""
    here = str(Path(__file__).resolve().parent)
    added_path = here not in sys.path
    if added_path:
        sys.path.insert(0, here)
    import tui_corewar as X

    match_dir = Path(match_dir)
    # The renderer is deliberately tolerant of a degraded bus — it renders
    # what parses and notes the rest — which is right for a live pane and
    # wrong here: a recorder pointed at the wrong directory would otherwise
    # spend two minutes producing a video of an empty core.
    missing = [str(p) for p in (match_dir / 'moves.txt',
                                match_dir / 'warriors' / 'A.red',
                                match_dir / 'warriors' / 'B.red')
               if not p.exists()]
    if missing:
        raise SystemExit(
            f'{match_dir} is not a Core War match directory — missing '
            + ', '.join(missing))
    saved = {k: getattr(X, k) for k in
             ('D', 'MOVES', 'BANNER', 'CTL', 'NAMES', 'RESULT', 'WARRIORS',
              'INPUT_ENABLED', 'REDUCED_MOTION', 'time', 'FRAME_HOOK',
              'EVENT_HOOK')}
    saved_size = X.shutil.get_terminal_size
    saved_names = dict(X.names)
    X.D = match_dir
    X.MOVES, X.BANNER, X.CTL = (match_dir / 'moves.txt',
                                match_dir / 'banner.txt', match_dir / 'ctl')
    X.NAMES, X.RESULT = match_dir / 'names.txt', match_dir / 'result.txt'
    X.WARRIORS = match_dir / 'warriors'
    X.INPUT_ENABLED = False
    X.REDUCED_MOTION = False
    X.shutil.get_terminal_size = lambda fb: os.terminal_size((cols, rows))
    clock = VirtualClock()
    X.time = clock
    sink = FrameSink()
    tl = Timeline()
    # The one RNG in the render path is the elimination shake. A master must
    # be reproducible, so it is seeded from the transcript that produced it —
    # and the caller's own RNG stream is handed back untouched afterwards,
    # because seeding a global on someone else's behalf is a side effect.
    rng_state = random.getstate()
    random.seed(sum(map(ord, X.read(X.MOVES))) & 0xFFFFFFFF)

    def on_frame(_g, sc, t):
        sink.cut(t)
        tl.metrics.append((t, sc.own[0], sc.own[1],
                           len(sc.procs[0]), len(sc.procs[1])))

    def on_event(kind, addr, w, t, extra):
        tl.events.append((t, kind, addr, w, extra))

    X.FRAME_HOOK = on_frame
    X.EVENT_HOOK = on_event
    X._fcache.clear()
    real_stdout, sys.stdout = sys.stdout, sink
    try:
        sc = X.cold_start()
        tl.names = (X.names['r'], X.names['b'])
        # The two programs write the match's material. `read_warriors` is
        # already tolerant — a source that does not assemble comes back as
        # None — and dna_cw falls that case back to v2's constants, so a
        # degraded warrior costs the broadcast its own theme and nothing else.
        import dna_cw
        wa, wb, _n, _err = X.read_warriors()
        tl.warriors = (wa, wb)
        tl.dna = dna_cw.match_dna(wa, wb)
        todo = sc.rounds if rounds is None else sc.rounds[:rounds]
        for rnd in todo:
            X.animate_round(sc, rnd)
        if todo:
            X.end_wash(sc)
    finally:
        sys.stdout = real_stdout
        for k, v in saved.items():
            setattr(X, k, v)
        X.shutil.get_terminal_size = saved_size
        X.names.clear()
        X.names.update(saved_names)
        X._fcache.clear()
        random.setstate(rng_state)
        if added_path and here in sys.path:
            sys.path.remove(here)
    tl.frames = sink.frames
    tl.duration = clock.now + 1.0            # a beat of room tone to land on
    return tl


# ---------------------------------------------------------------------------
# Synthesis — numpy, deterministic, no RNG
# ---------------------------------------------------------------------------
def _np():
    import numpy
    return numpy


class Mix:
    """The stereo bus. score_cw writes into `buf` directly (it needs
    per-sample pan curves, which a scalar-pan helper cannot express), so what
    lives here is the buffer itself and the one operation that must be exact:
    the hitstop gate."""

    def __init__(self, duration):
        np = _np()
        self.n = int(duration * SR) + 1
        self.buf = np.zeros((self.n, 2), dtype=np.float32)

    def gate(self, start, end, fade=0.004):
        """Hard mute across a window — the elimination hitstop. Short fades on
        both edges so the silence arrives as a cut, not a click. The fade-in
        at the trailing edge is why the drop's payload is written AFTER
        gating: it would otherwise ramp the impact's own attack a second
        time (see score_cw._lay_impacts)."""
        np = _np()
        a, b = int(start * SR), int(end * SR)
        a, b = max(0, a), min(self.n, b)
        if b <= a:
            return
        f = max(1, int(fade * SR))
        self.buf[a:b] = 0.0
        # Shorten the fades at the buffer's edges rather than dropping them.
        # `a - f > 0` skipped the fade-OUT entirely for any gate starting
        # within 4 ms of the start — the silence then arrived as the click it
        # exists to avoid, in the one place the track is most exposed.
        fo = min(f, a)
        if fo > 0:
            self.buf[a - fo:a] *= np.linspace(
                1, 0, fo, dtype=np.float32)[:, None]
        fi = min(f, self.n - b)
        if fi > 0:
            self.buf[b:b + fi] *= np.linspace(
                0, 1, fi, dtype=np.float32)[:, None]


def master(mix, ceiling=0.89, block=256, release=0.30):
    """A fast-attack / slow-release limiter, not a tanh squash.

    Squashing the whole mix into shape costs the thing this soundtrack is
    made of: a quiet room that events puncture. A tanh wall flattens the bed
    UP to meet the hits, the crest factor collapses, and every bomb arrives
    at the same loudness as the drone it was supposed to interrupt. The
    limiter instead ducks only where the sum actually exceeds the ceiling,
    over a block envelope with a slow release, so the bed stays low, the
    hits stay hits, and the elimination silence stays a hole in the room."""
    np = _np()
    x = mix.buf
    n = len(x)
    pad = (-n) % block
    env = np.abs(x).max(axis=1)
    if pad:
        env = np.concatenate([env, np.zeros(pad, dtype=env.dtype)])
    peaks = env.reshape(-1, block).max(axis=1)
    need = np.minimum(1.0, ceiling / np.maximum(peaks, 1e-9))
    # release: gain may fall instantly, and recovers over `release` seconds
    step = block / SR
    coef = math.exp(-step / max(1e-3, release))
    g = np.empty_like(need)
    cur = 1.0
    for i, want in enumerate(need):
        cur = want if want < cur else want + (cur - want) * coef
        g[i] = cur
    gains = np.interp(np.arange(n), np.arange(len(g)) * block + block / 2.0,
                      g, left=g[0], right=g[-1])
    # Gains are computed from each block's PEAK but evaluated at each block's
    # CENTRE, so a sample near a block edge was being multiplied by a gain
    # interpolated toward its quieter neighbour — under-ducked exactly where
    # the loud block began. Clamp every sample to its own block's gain: the
    # interpolation still smooths the ride, but never upward past what the
    # block it actually belongs to asked for.
    gains = np.minimum(gains, np.repeat(g, block)[:n]).astype(np.float32)
    out = (x * gains[:, None]).astype(np.float32)
    # Belt and braces: the ride is now conservative everywhere, but a single
    # global trim costs nothing and makes "never clips" a guarantee rather
    # than an argument about interpolation.
    m = float(np.max(np.abs(out)))
    if m > ceiling:
        out *= ceiling / m
    return out


def synthesize(tl, log=None):
    """The musical brain lives in score_cw: analyse the timeline into a Score
    on a fixed grid, spend the Score into the Mix, master. v1 put a sound at
    every event and the result was weather; the arranger puts sounds on a
    grid the battle only gets to select from."""
    import score_cw
    mix = Mix(tl.duration)
    score_cw.render(tl, mix, log=log)
    return master(mix)


def write_wav(samples, path):
    np = _np()
    pcm = np.clip(samples, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype('<i2')
    with wave.open(str(path), 'wb') as fh:
        fh.setnchannels(2)
        fh.setsampwidth(2)
        fh.setframerate(SR)
        fh.writeframes(pcm.tobytes())


# ---------------------------------------------------------------------------
# Picture + mux
# ---------------------------------------------------------------------------
def render_frames(tl, outdir, cols=PANE_COLS, rows=PANE_ROWS, log=None):
    """One PNG per drawn frame, at master density. Frames are not resampled
    to 24fps here: each one carries the duration until the next, so a beat
    dwell or the hitstop freeze is one file held, not thirty copies."""
    here = str(Path(__file__).resolve().parent)
    added_path = here not in sys.path
    if added_path:
        sys.path.insert(0, here)
    try:
        import ansi_png
    finally:
        if added_path and here in sys.path:
            sys.path.remove(here)
    cw, ch, mx, my = ansi_png.metrics_for(cols, rows, MASTER_W, MASTER_H)
    renderer = ansi_png.CellRenderer(cw, ch, mx, my, MASTER_W, MASTER_H,
                                     page=(18, 21, 28))
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    entries = []
    for i, (t, text) in enumerate(tl.frames):
        path = outdir / f'f{i:06d}.png'
        ansi_png.render_ansi(text, renderer).save(path, compress_level=1)
        nxt = tl.frames[i + 1][0] if i + 1 < len(tl.frames) else tl.duration
        # A held moment (a beat dwell, the hitstop freeze) becomes N repeated
        # REFERENCES to one file rather than one entry with a long duration:
        # the concat demuxer's handling of a final long duration is its own
        # subject, and a uniform 24fps listing keeps the output honest.
        #
        # The hold is measured against the ABSOLUTE timeline, not as a
        # rounded gap. Rounding each gap independently lets the errors
        # accumulate — a few hundred frames of +-0.5 frame is half a second
        # of drift by the end — whereas differencing two absolute frame
        # indices telescopes: the holds sum to round(duration * FPS) exactly,
        # whatever the frame times were.
        entries.append((path, max(1, int(round(nxt * FPS))
                                  - int(round(t * FPS)))))
        if log and i % 250 == 0:
            log(f'  frame {i}/{len(tl.frames)}  t={t:.1f}s')
    listing = outdir / 'frames.txt'
    step = 1.0 / FPS
    total = sum(h for _p, h in entries)          # == round(duration * FPS)
    with listing.open('w') as fh:
        written = 0
        for path, holds in entries:
            for _ in range(holds):
                # The concat demuxer needs the last file listed a second
                # time for its duration to apply, and that repeat is itself
                # one displayed frame. So the listing stops one short and
                # the tail supplies it: total frames out == total frames in.
                if written == total - 1:
                    break
                fh.write(f"file '{path.name}'\nduration {step:.6f}\n")
                written += 1
        fh.write(f"file '{entries[-1][0].name}'\n")
    return listing


def mux(listing, wav, out, log=None):
    """Single -filter_complex, CFR output, audio padded to the video's length
    — the house ffmpeg rules, which exist because every one of them has bitten
    this repo before."""
    cmd = [FFMPEG, '-y',
           '-f', 'concat', '-safe', '0', '-i', str(listing),
           '-i', str(wav),
           '-filter_complex',
           f'[0:v]fps={FPS:g},format=yuv420p,setsar=1[v];'
           f'[1:a]apad,aresample=async=1:first_pts=0[a]',
           '-map', '[v]', '-map', '[a]',
           '-c:v', 'libx264', '-preset', 'slow', '-crf', '18',
           '-c:a', 'aac', '-b:a', '192k',
           '-movflags', '+faststart', '-shortest', str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-4000:])
        raise SystemExit(f'ffmpeg failed ({r.returncode})')
    if log:
        log(f'  wrote {out}')


def busiest_window(tl, span=20.0):
    """The stretch with the most going on — where an excerpt should start."""
    times = sorted(t for t, k, _a, _w, _x in tl.events
                   if k in ('bomb', 'death', 'spl', 'elimination', 'bloom'))
    if not times:
        return 0.0
    best, best_n, j = 0.0, 0, 0
    for i, t0 in enumerate(times):
        while j < len(times) and times[j] < t0 + span:
            j += 1
        if j - i > best_n:
            best, best_n = t0, j - i
    return max(0.0, min(best, max(0.0, tl.duration - span)))


def excerpt(master_mp4, out, start, span=20.0):
    cmd = [FFMPEG, '-y', '-ss', f'{start:.3f}', '-i', str(master_mp4),
           '-t', f'{span:.3f}',
           '-c:v', 'libx264', '-preset', 'medium', '-crf', '18',
           '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-4000:])
        raise SystemExit('ffmpeg excerpt failed')


DEFAULT_EXCERPT_S = 20.0
OPTIONS = {'keep-scratch', 'excerpt'}
# Flags that take no value and answer immediately. `--help` used to fall
# through to the unknown-option branch, so asking this tool what it does got
# you "unknown option: --help" and exit 2 — an error message for the one
# request that is never an error.
FLAGS = {'help'}


def parse_args(argv):
    """Flags consume their OWN values; whatever is left is positional.

    The first cut filtered "everything not starting with --" into the
    positionals, so a flag's value became one — `--excerpt clip.mp4:8` made
    `clip.mp4:8` the scratch directory, which then skipped cleanup (a
    truthy `keep`), leaked 621 MB into the caller's working directory, and
    handed ffmpeg a path it read as a protocol. Every part of that came from
    one shortcut in argument parsing."""
    args, flags = [], {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--':
            args.extend(argv[i + 1:])
            break
        if a in ('-h', '--help'):
            flags['help'] = True
            i += 1
            continue
        if a.startswith('--'):
            name, _, inline = a[2:].partition('=')
            if name in FLAGS:
                flags[name] = True
                i += 1
                continue
            if name not in OPTIONS:
                raise SystemExit(f'unknown option: --{name}')
            if inline:
                flags[name] = inline
            else:
                i += 1
                if i >= len(argv) or argv[i].startswith('--'):
                    raise SystemExit(f'--{name} needs a value')
                flags[name] = argv[i]
        else:
            args.append(a)
        i += 1
    return args, flags


def parse_excerpt(spec):
    """`FILE` or `FILE:SECONDS`, split from the RIGHT.

    A colon is legal in a path, so the tail is only a duration if it reads
    as one. If it doesn't and it still looks like it was MEANT to (no path
    separator in it), that is a typo worth refusing now rather than a
    traceback after the mux has already run; anything else is just a
    colon-bearing filename."""
    head, sep, tail = spec.rpartition(':')
    if not sep:
        return Path(spec), DEFAULT_EXCERPT_S
    try:
        return Path(head), float(tail)
    except ValueError:
        if '/' in tail or not tail:
            return Path(spec), DEFAULT_EXCERPT_S
        raise SystemExit(f'--excerpt wants FILE or FILE:SECONDS, got {spec!r}')


def main(argv):
    """usage: record_cw.py <match-dir> <out.mp4>
                           [--keep-scratch DIR] [--excerpt FILE[:SECONDS]]
                           [-h | --help]"""
    try:
        args, flags = parse_args(argv[1:])
    except SystemExit as e:
        sys.stderr.write(f'{e}\n{main.__doc__}\n')
        return 2
    # Asking for the usage is not a failure: it goes to stdout and exits 0,
    # so `record_cw.py --help | less` works and a shell script can tell a
    # help request apart from a bad invocation.
    if flags.get('help'):
        sys.stdout.write(main.__doc__ + '\n')
        return 0
    if len(args) != 2:
        sys.stderr.write(main.__doc__ + '\n')
        return 2
    match_dir, out = Path(args[0]), Path(args[1])
    excerpt_to = None
    if 'excerpt' in flags:
        try:
            excerpt_to = parse_excerpt(flags['excerpt'])
        except SystemExit as e:
            sys.stderr.write(f'{e}\n')
            return 2
    keep = flags.get('keep-scratch')
    # Scratch goes to a temp dir unless the caller asked to keep it: a match
    # archive is evidence, and 3,800 intermediate PNGs are not part of it. It
    # is REMOVED afterwards either way unless kept — a failed mux used to
    # leave gigabytes of frames behind, once per attempt.
    workdir = Path(keep) if keep else Path(tempfile.mkdtemp(prefix='cw-record-'))
    log = lambda m: (sys.stderr.write(m + '\n'), sys.stderr.flush())
    try:
        log(f'timeline: {match_dir}')
        tl = extract(match_dir)
        log(f'  {len(tl.frames)} frames, {len(tl.events)} events, '
            f'{tl.duration:.1f}s')
        log('audio')
        workdir.mkdir(parents=True, exist_ok=True)
        wav = workdir / 'track.wav'
        write_wav(synthesize(tl, log=log), wav)
        log(f'  {wav}')
        log('frames')
        listing = render_frames(tl, workdir / 'frames', log=log)
        log('mux')
        mux(listing, wav, out, log=log)
        if excerpt_to:
            dest, span = excerpt_to
            start = busiest_window(tl, span)
            log(f'excerpt at {start:.1f}s ({span:g}s) -> {dest}')
            excerpt(out, dest, start, span)
    finally:
        if not keep and workdir.exists():
            shutil.rmtree(workdir, ignore_errors=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))

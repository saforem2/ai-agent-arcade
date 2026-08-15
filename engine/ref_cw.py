"""Core War referee. Same trust model as ref_xq.py, but a match is a
workshop phase plus one deterministic best-of-3 battle, not a turn loop.

moves.txt is the single append-only source of truth — the battle transcript.
It stays empty through the workshop phase; `lock` appends

    LOAD A <sha256>
    LOAD B <sha256>

(the sha256_warrior of each locked source), and `battle` then appends, per
round n = 1..3,

    ROUND n seed=<s> off=<a>,<b>
    ROUND n OUT <1-0|0-1|tie> cycles=<n>

exactly as corewar.battle_transcript() renders them. Every verify replays
the whole transcript — re-parsing the locked warriors, checking them against
the LOAD hashes, and re-deriving every round from first principles: the
round seed must be battle_seed(A, B) + n, the offsets must be the engine's
own draw from random.Random(seed), and the re-run battle must land on the
recorded OUT line — so tampering with warriors/ or the transcript (including
transplanting honestly-simulated rounds from a foreign seed) does not change
the record, it only makes itself visible. The loud report goes to stderr
(relay logs capture it, humans see it on screen) while stdout stays exactly
`ILLEGAL`, which every existing caller already treats as a refusal.

Staging: game_cw.sh stage copies the warrior atomically to
stage_inbox/<NAME>.red and writes pending.txt as `<name>\tstage <sha256>`.
`stage "$(cat pending.txt)"` locates the inbox file, hash-checks it against
the receipt, validates it with corewar.validate_warrior() (parse, ≤ 100
instructions, start offset in range — the referee's validation is the
authority on what Redcode is legal at this table), and installs it as
warriors/A.red (first seat in names.txt — red — the seat the shared roles
machinery calls "white") or warriors/B.red (second seat — blue — "black").
Rejection is loud to the stager (full reason on stderr for the host to
relay privately) and content-free everywhere else: nothing about opcodes or
instruction counts reaches the room. Re-staging overwrites the previous
stage until the lock. The token `resign` rides the same path
(`<name>\tresign`): it requires a seated author but nothing else, works
until result.txt exists (mid-workshop or after the lock), and finishes the
ledger natively with the correct 0-1/1-0.

Determinism contract: the match seed is

    int.from_bytes(sha256(norm(A.source) + norm(B.source))[:8], "big")

with norm() the same LF normalization sha256_warrior uses, and round n
(1-based) fights with seed = match_seed + n. Offsets are the engine's own
draw — Battle(off_a=None, off_b=None) draws from random.Random(seed) — so a
battle is a pure function of (warrior A, warrior B, seed); same warriors
produce byte-identical transcripts. Scoring: a round win is 1 point, a tie
is 1/2 each; the match line is 1-0 / 0-1 / 1/2-1/2 by total points over the
three rounds (always three — there is no early clinch and no overtime).

battle.json is a renderer cache (never a truth): written as a skeleton at
lock, one entry per round appended at battle, rebuilt from the transcript
plus re-simulation by resolve.

  init [--force]  empty the transcript and the hold; refuses over a
                  non-empty transcript without --force
  check           read-only readiness report: phase, hold, validation,
                  locked, rounds, result (prints BATTLE READY when both
                  seats hold a valid warrior and the hold is open)
  stage <token>   apply pending.txt's `<name>\tstage <sha256>` or
                  `<name>\tresign`
  lock            freeze both warriors, append the LOAD lines, print the
                  hashes
  battle          run the best-of-3, append ROUND/OUT lines, finish the
                  ledger natively; refused without a lock or once
                  result.txt exists
  verify          re-check LOAD hashes and re-simulate every round; halts
                  the match on any disagreement
  resolve         clear a tamper halt (facilitator/human only) after
                  rebuilding battle.json from the transcript
"""
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

import corewar

D = Path(os.environ.get('ARCADE_LIVE', '/tmp/corewar'))
# chat.py resolves its own D independently from ARCADE_LIVE (default
# /tmp/chess) -- without this, an unset ARCADE_LIVE would leave *our* state
# in /tmp/corewar while chat.say/player_names/roles silently read/write the
# live CHESS dir instead. setdefault is a no-op once ARCADE_LIVE is set.
os.environ.setdefault('ARCADE_LIVE', str(D))
sys.path.insert(0, str(D))
import chat

MOVES = D / 'moves.txt'
PENDING = D / 'pending.txt'
HALT = D / 'TAMPER.txt'
RESULTS = D / 'results.txt'
RESULT = D / 'result.txt'
DRAW_OFFER = D / 'draw_offer.txt'   # no draw offers in Core War; init hygiene only
BANNER = D / 'banner.txt'
STAGE_LOG = D / 'stage_log.txt'
MENU = D / 'menu.txt'
BATTLE_JSON = D / 'battle.json'
WARRIORS = D / 'warriors'
INBOX = D / 'stage_inbox'

ROUNDS = 3          # always a full best-of-3; points decide the match
WIN, TIE = 1.0, 0.5

LOAD_RE = re.compile(r'^LOAD ([AB]) ([0-9a-f]{64})$')
ROUND_RE = re.compile(r'^ROUND (\d+) seed=(\d+) off=(\d+),(\d+)$')
OUT_RE = re.compile(r'^ROUND (\d+) OUT (1-0|0-1|tie) cycles=(\d+)$')
STAGE_RE = re.compile(r'^stage ([0-9a-f]{64})$')


# ---------------------------------------------------------------------------
# transcript

def transcript_lines():
    if not MOVES.exists():
        return []
    return [ln for ln in MOVES.read_text().splitlines() if ln.strip()]


def parse_transcript():
    """Strictly parse moves.txt. Returns (loads, rounds, error): loads is
    {'A': sha, 'B': sha} once locked ({} in the workshop), rounds a list of
    {'n', 'seed', 'off_a', 'off_b', 'out', 'cycles'}. Any line that does not
    fit the grammar is an error — the transcript is the append-only truth
    and nothing else may appear in it."""
    lines = transcript_lines()
    loads, rounds = {}, []
    if not lines:
        return loads, rounds, None
    if len(lines) < 2:
        return loads, rounds, f'line 1: incomplete LOAD header: {lines[0]!r}'
    for expect_seat, line in zip('AB', lines[:2]):
        m = LOAD_RE.match(line)
        if not m or m.group(1) != expect_seat:
            return loads, rounds, f'line: expected LOAD {expect_seat} <sha256>, got {line!r}'
        loads[expect_seat] = m.group(2)
    rest = lines[2:]
    if len(rest) % 2:
        return loads, rounds, f'odd number of ROUND/OUT lines: {rest[-1]!r} has no partner'
    for i in range(0, len(rest), 2):
        rm, om = ROUND_RE.match(rest[i]), OUT_RE.match(rest[i + 1])
        n = i // 2 + 1
        if not rm:
            return loads, rounds, f'line: expected ROUND {n} seed=<s> off=<a>,<b>, got {rest[i]!r}'
        if not om:
            return loads, rounds, f'line: expected ROUND {n} OUT <outcome> cycles=<c>, got {rest[i + 1]!r}'
        if int(rm.group(1)) != n or int(om.group(1)) != n:
            return loads, rounds, f'round numbers out of order at {rest[i]!r}'
        rounds.append({'n': n, 'seed': int(rm.group(2)),
                       'off_a': int(rm.group(3)), 'off_b': int(rm.group(4)),
                       'out': om.group(2), 'cycles': int(om.group(3))})
    return loads, rounds, None


def battle_seed(a_source, b_source):
    """The match seed: int.from_bytes(sha256(A.source + B.source)[:8], 'big')
    over LF-normalized sources (the same normalization sha256_warrior uses,
    so CRLF copies seed identically). Round n fights with seed + n."""
    def norm(s):
        return s.replace('\r\n', '\n').replace('\r', '\n')
    digest = hashlib.sha256((norm(a_source) + norm(b_source)).encode('utf-8')).digest()
    return int.from_bytes(digest[:8], 'big')


def score_of(result):
    return '1-0' if result.winner == 'A' else '0-1' if result.winner == 'B' else 'tie'


def locked_warriors():
    """(a_source, b_source, error) — the staged copies under warriors/."""
    try:
        return (WARRIORS / 'A.red').read_text(), (WARRIORS / 'B.red').read_text(), None
    except OSError as e:
        return None, None, f'a locked warrior file is unreadable: {e}'


def resimulate(loads, rounds):
    """Re-parse the locked warriors, check them against the LOAD hashes, and
    re-derive every transcript round from first principles: the round seed
    must be battle_seed(A, B) + n, the offsets must be the engine's own draw
    from random.Random(that seed), and the re-run battle must land on the
    recorded OUT line. A round with honest-looking outcomes but attacker-
    chosen seeds/offsets is tampering, exactly like a swapped warrior.
    Returns an error string, or None when the record is fully self-consistent."""
    a_source, b_source, err = locked_warriors()
    if err:
        return err
    for tag, src in (('A', a_source), ('B', b_source)):
        if corewar.sha256_warrior(src) != loads[tag]:
            return (f'warriors/{tag}.red does not match its LOAD hash — '
                    f'the locked warrior was swapped or edited')
    try:
        wa, wb = corewar.parse_warrior(a_source), corewar.parse_warrior(b_source)
    except corewar.RedcodeError as e:
        return f'a locked warrior no longer assembles: {e}'
    seed = battle_seed(a_source, b_source)
    for r in rounds:
        expected_seed = seed + r['n']
        if r['seed'] != expected_seed:
            return (f"round {r['n']} seed={r['seed']} does not derive from the "
                    f'locked warriors (battle_seed + n = {expected_seed})')
        # Battle with no explicit offsets IS the engine's draw: same seed,
        # same random.Random sequence, same offsets — one construction both
        # proves provenance and re-runs the round.
        battle = corewar.Battle(wa, wb, seed=expected_seed)
        if battle.off_a != r['off_a'] or battle.off_b != r['off_b']:
            return (f"round {r['n']} off={r['off_a']},{r['off_b']} is not the "
                    f"engine's draw for its seed "
                    f'({battle.off_a},{battle.off_b})')
        result = battle.run()
        if score_of(result) != r['out'] or result.cycles != r['cycles']:
            return (f"round {r['n']} re-simulates to {score_of(result)} "
                    f"cycles={result.cycles}, but the transcript claims "
                    f"{r['out']} cycles={r['cycles']}")
    return None


def warrior_meta(source, fallback_name):
    w = corewar.parse_warrior(source)
    return {'name': w.name or fallback_name, 'author': w.author,
            'sha256': corewar.sha256_warrior(source)}


def write_battle_json(loads, rounds):
    """(Re)build the renderer cache from the locked warriors plus the
    transcript's own claims. Cache, never a truth — verify/resolve derive it
    from moves.txt + warriors/, never the other way round."""
    red, blue = chat.player_names()
    a_source, b_source, err = locked_warriors()
    if err:
        return err
    data = {'seed': battle_seed(a_source, b_source),
            'warriors': {'A': warrior_meta(a_source, 'A'),
                         'B': warrior_meta(b_source, 'B')},
            'rounds': [dict(r) for r in rounds],
            'names': [red, blue]}
    tmp = BATTLE_JSON.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(data, indent=2) + '\n')
    tmp.replace(BATTLE_JSON)
    return None


# ---------------------------------------------------------------------------
# shared referee machinery (ported from ref_xq.py)

def refuse(headline, detail):
    """Halt the match loudly. stdout stays `ILLEGAL` so callers reject the move."""
    HALT.write_text(f'{headline}\n' + '\n'.join(detail) + '\n')
    banner = ['', '=' * 62, f'  {headline}', '=' * 62]
    sys.stderr.write('\n'.join(banner + ['  ' + d for d in detail] + ['=' * 62, '', '']))
    sys.stderr.flush()
    try:
        chat.say(f'{headline} — match halted, needs a human. ' + ' | '.join(detail),
                 name='REFEREE')
    except OSError:
        pass
    print('ILLEGAL')
    sys.exit(3)


def split_signed(arg):
    """pending.txt carries `<name>\\t<token>`. A bare token is unsigned."""
    if '\t' in arg:
        who, token = arg.split('\t', 1)
        return chat.clean(who, 24) or None, token.strip()
    return None, arg.strip()


def check_seated(who):
    """Every stage token (warrior or resign) needs a seated author; there is
    no unsigned staging at this table. Returns (role, (red, blue)); exits on
    an unsigned or unseated author.

    Two gates before any seat is granted:

    - the name must be usable as a stage_inbox/<name>.red filename: '/',
      '\\' and '.' (a dot is enough for '..') are rejected outright, so a
      hand-written pending.txt can never steer the referee's inbox paths
      out of the inbox;
    - when seats.txt exists, the name must match a seat EXACTLY (the same
      bar chat.require_seated() sets client-side) -- chat.role_of()'s
      bidirectional prefix match would let 'red-spectator' resign RED's
      seat. Only without seats.txt (older deploys, manual use) does the
      prefix heuristic apply.

    role is 'white'/'black' (chat.role_of()'s own labels, players[0]/[1]) --
    red plays the seat the shared machinery calls white, blue the one it
    calls black; that mapping is used only to reuse the roles machinery and
    to pick warriors/A.red vs warriors/B.red, never surfaced to the room."""
    players = chat.player_names()
    role = None
    if who and not any(c in who for c in '/\\.'):
        seats = chat.seats()
        if seats:
            for seat_role, name in seats.items():
                if name.lower() == who.lower():
                    role = seat_role
                    break
        else:
            role = chat.role_of(who, chat.roles(), players)
    if role not in ('white', 'black'):
        sys.stderr.write(f'WRONG AUTHOR: {who!r} does not hold a seat in this game.\n')
        chat.say(f'Rejected — {who or "an unsigned submission"} is not seated.',
                 name='REFEREE')
        print('ILLEGAL')
        sys.exit(4)
    return role, players


def append_ledger(entry):
    """Idempotent results.txt append (the game-6 retro dedup): skip when the
    exact entry is already the last line. Shared by finish_native and the
    resign path so a re-applied resignation can never double-append."""
    last_line = ''
    if RESULTS.exists():
        lines = [l for l in RESULTS.read_text().splitlines() if l.strip()]
        last_line = lines[-1] if lines else ''
    if last_line != entry:
        with RESULTS.open('a') as fh:
            fh.write(entry + '\n')


def finish_native(result, reason):
    """Terminal state reached natively (the battle's own scoring) finishes
    the ledger exactly like the resign path -- the game-6 retro fix, ported
    from ref_xq.py. Idempotent: a result.txt already on disk, or the exact
    entry already the last line of results.txt, means don't double-append."""
    if RESULT.exists():
        return
    red, blue = chat.player_names()
    entry = f'{red} {result} {blue}'
    append_ledger(entry)
    winner = red if result == '1-0' else blue if result == '0-1' else None
    RESULT.write_text(f'{winner} wins by {reason}\n' if winner else f'draw — {reason}\n')
    BANNER.write_text(f'{entry} — {reason}\n')
    chat.say(f'{entry} ({reason})', name='REFEREE')


def verify(log_errors=True):
    """Re-read the transcript, check the locked warriors against the LOAD
    hashes, and re-simulate every round. Halts the match on any divergence.
    With log_errors=False (resolve's dry run), returns the error string
    instead of halting."""
    loads, rounds, err = parse_transcript()
    if err:
        if not log_errors:
            return f'moves.txt does not parse: {err}'
        refuse('TAMPER DETECTED', [f'moves.txt does not parse: {err}',
                                   'the transcript itself has been edited',
                                   'a human or facilitator must run: ref_cw.py resolve'])
    if loads:
        err = resimulate(loads, rounds)
        if err:
            if not log_errors:
                return err
            refuse('TAMPER DETECTED', [err,
                                       'the transcript is authoritative; warriors/ or '
                                       'moves.txt was changed behind the referee',
                                       'a human or facilitator must run: ref_cw.py resolve'])
    return None


def guard_halt():
    if HALT.exists():
        sys.stderr.write('REFUSING: match is halted for tampering. '
                         'Run `ref_cw.py resolve` after a human review.\n')
        print('ILLEGAL')
        sys.exit(3)


def guard_over():
    if RESULT.exists():
        sys.stderr.write(f'REFUSING: match already over — {RESULT.read_text().strip()}.\n')
        print('ILLEGAL')
        sys.exit(6)


def clear_pending_and_inbox(author):
    PENDING.unlink(missing_ok=True)
    (INBOX / f'{author}.red').unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# commands

def cmd_init(force):
    lines = transcript_lines()
    if lines and not force:
        sys.stderr.write(
            f'REFUSING to init: moves.txt already holds {len(lines)} transcript lines.\n'
            'Initialising mid-match would destroy the only record of the battle.\n'
            'If the previous match really is finished, run: ref_cw.py init --force\n')
        print('ILLEGAL')
        sys.exit(5)
    MOVES.write_text('')
    HALT.unlink(missing_ok=True)
    PENDING.unlink(missing_ok=True)
    # A leftover result.txt from the previous match must not make a
    # brand-new game refuse every stage as "already over" (same latent gap
    # ref_xq.py's init closes for chess/xiangqi).
    RESULT.unlink(missing_ok=True)
    DRAW_OFFER.unlink(missing_ok=True)
    BATTLE_JSON.unlink(missing_ok=True)
    # Client-side receipts belong to the same match epoch as the transcript.
    STAGE_LOG.unlink(missing_ok=True)
    MENU.unlink(missing_ok=True)
    for d in (WARRIORS, INBOX):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir()
    print('OK init — transcript empty, hold empty')


def cmd_check():
    """Read-only readiness report for the host: who holds what, whether the
    hold validates, locked?, rounds so far, result. Changes nothing, posts
    nothing."""
    loads, rounds, err = parse_transcript()
    red, blue = chat.player_names()
    if RESULT.exists():
        phase = 'over'
    elif rounds:
        phase = 'battle'
    elif loads:
        phase = 'locked'
    else:
        phase = 'workshop'
    print(f'phase: {phase}')
    hold = []
    all_valid = phase in ('workshop',)
    for seat, name in (('A', red), ('B', blue)):
        f = WARRIORS / f'{seat}.red'
        if not f.exists():
            staged_inbox = INBOX / f'{name}.red'
            note = ' (a stage awaits the referee)' if staged_inbox.exists() else ''
            hold.append(f'{name}=empty{note}')
            all_valid = False
            continue
        problems = corewar.validate_warrior(f.read_text())
        if problems:
            hold.append(f'{name}=staged INVALID: {"; ".join(problems)}')
            all_valid = False
        else:
            hold.append(f'{name}=staged (valid)')
    print('hold: ' + '  '.join(hold))
    # pending.txt can be hand-written by anyone -- re-clean before printing so
    # ESC bytes never reach the host's terminal (same rule chat.py applies).
    # chat.clean drops tabs entirely, so pre-space them to keep the
    # <name> <token> split legible.
    print('pending: ' + (chat.clean(PENDING.read_text().replace('\t', ' '))
                         if PENDING.exists() else '(none)'))
    print(f'locked: {"yes" if loads else "no"}')
    print(f'rounds: {len(rounds)}' + (' (' + ', '.join(r['out'] for r in rounds) + ')' if rounds else ''))
    print('result: ' + (RESULT.read_text().strip() if RESULT.exists() else '(none)'))
    print(f'halted: {"yes (TAMPER.txt)" if HALT.exists() else "no"}')
    if err:
        print(f'transcript: CORRUPT ({err})')
    if all_valid and not loads and not RESULT.exists() and not HALT.exists():
        print('BATTLE READY')


def cmd_stage(arg):
    guard_halt()
    guard_over()
    loads, rounds, err = parse_transcript()
    if err:
        refuse('TAMPER DETECTED', [f'moves.txt does not parse: {err}',
                                   'the transcript itself has been edited',
                                   'a human or facilitator must run: ref_cw.py resolve'])
    author, token = split_signed(arg)
    role, (red, blue) = check_seated(author)
    if token == 'resign':
        # Works until result.txt exists, mid-workshop or after the lock --
        # the same shape as ref_xq.py's apply_special(), red = white seat.
        # The ledger append goes through the same dedup finish_native uses,
        # so a re-applied resign (e.g. after a hand-deleted result.txt)
        # cannot double-append.
        winner, result = (blue, '0-1') if role == 'white' else (red, '1-0')
        append_ledger(f'{red} {result} {blue}')
        RESULT.write_text(f'{winner} wins by resignation ({author} resigned)\n')
        BANNER.write_text(f'{red} {result} {blue} — resignation\n')
        DRAW_OFFER.unlink(missing_ok=True)
        clear_pending_and_inbox(author)
        chat.say(f'{red} {result} {blue} ({author} resigns)', name='REFEREE')
        print(f'GAMEOVER {result} — {winner} wins by resignation')
        return
    if loads:
        sys.stderr.write('REFUSING: the warriors are locked — the hold is sealed.\n')
        print('ILLEGAL')
        sys.exit(1)
    m = STAGE_RE.fullmatch(token)
    if not m:
        sys.stderr.write(f'REJECTED: unreadable stage token {token!r} '
                         f'(expected "stage <sha256>" or "resign").\n')
        print('ILLEGAL')
        sys.exit(1)
    sha = m.group(1)
    inbox = INBOX / f'{author}.red'
    if not inbox.exists():
        sys.stderr.write(f'REJECTED: no staged warrior at stage_inbox/{author}.red — '
                         f'stage it with `game_cw.sh stage <file>` first.\n')
        print('ILLEGAL')
        sys.exit(1)
    source = inbox.read_text()
    if corewar.sha256_warrior(source) != sha:
        sys.stderr.write('REJECTED: the staged file does not match its sha256 receipt '
                         '— the inbox copy changed after staging. Re-stage it.\n')
        print('ILLEGAL')
        sys.exit(1)
    problems = corewar.validate_warrior(source)
    if problems:
        # Loud to the stager (the host relays this verbatim, privately) --
        # and content-free everywhere else: no opcode name or instruction
        # count of a rejected warrior ever reaches the room.
        sys.stderr.write(f'REJECTED: {author}\'s warrior did not pass validation:\n')
        for p in problems:
            sys.stderr.write(f'  - {p}\n')
        sys.stderr.write('Rejection is free: fix and restage. The workshop deadline binds.\n')
        print('ILLEGAL')
        sys.exit(1)
    seat = 'A' if role == 'white' else 'B'
    color = 'red' if role == 'white' else 'blue'
    tmp = WARRIORS / f'.{seat}.red.tmp'
    tmp.write_text(source)
    tmp.replace(WARRIORS / f'{seat}.red')   # atomic: a re-stage never halves a file
    clear_pending_and_inbox(author)
    print(f'OK {author} staged a warrior on the {color} seat (warriors/{seat}.red)')


def cmd_lock():
    guard_halt()
    guard_over()
    loads, rounds, err = parse_transcript()
    if err:
        refuse('TAMPER DETECTED', [f'moves.txt does not parse: {err}',
                                   'the transcript itself has been edited',
                                   'a human or facilitator must run: ref_cw.py resolve'])
    if loads:
        sys.stderr.write('REFUSING: already locked — the LOAD lines are in the transcript.\n')
        print('ILLEGAL')
        sys.exit(1)
    a_source, b_source, werr = locked_warriors()
    if werr or not (WARRIORS / 'A.red').exists() or not (WARRIORS / 'B.red').exists():
        sys.stderr.write('REFUSING: both seats must have a staged warrior before the lock.\n')
        print('ILLEGAL')
        sys.exit(1)
    # Validate the hold BEFORE touching the transcript: a hand-placed or
    # corrupted hold file must be a clean refusal here, never a traceback
    # from battle.json's metadata build with half-written LOAD lines.
    problems = []
    for tag, src in (('A', a_source), ('B', b_source)):
        problems.extend(f'warriors/{tag}.red: {p}'
                        for p in corewar.validate_warrior(src))
    if problems:
        sys.stderr.write('REFUSING to lock: the hold is not battle-ready:\n')
        for p in problems:
            sys.stderr.write(f'  - {p}\n')
        sys.stderr.write('The transcript was not touched; re-stage a valid warrior first.\n')
        print('ILLEGAL')
        sys.exit(1)
    sha_a, sha_b = corewar.sha256_warrior(a_source), corewar.sha256_warrior(b_source)
    with MOVES.open('a') as fh:      # genuinely append-only: never rewrite history
        fh.write(f'LOAD A {sha_a}\nLOAD B {sha_b}\n')
    err = write_battle_json({'A': sha_a, 'B': sha_b}, [])
    if err:
        refuse('TAMPER DETECTED', [err])
    print('OK locked')
    print(f'A {sha_a}')
    print(f'B {sha_b}')


def cmd_battle():
    guard_halt()
    guard_over()
    loads, rounds, err = parse_transcript()
    if err:
        refuse('TAMPER DETECTED', [f'moves.txt does not parse: {err}',
                                   'the transcript itself has been edited',
                                   'a human or facilitator must run: ref_cw.py resolve'])
    if not loads:
        sys.stderr.write('REFUSING: no lock on record — run `ref_cw.py lock` first.\n')
        print('ILLEGAL')
        sys.exit(1)
    if rounds:
        sys.stderr.write(f'REFUSING: the transcript already holds {len(rounds)} round(s) '
                         'but no result — a battle stopped mid-run. A human must review '
                         '(verify / resolve), never just re-run.\n')
        print('ILLEGAL')
        sys.exit(1)
    err = resimulate(loads, [])     # hash-check the locked warriors before trusting them
    if err:
        refuse('TAMPER DETECTED', [err,
                                   'the LOAD lines in the transcript are authoritative',
                                   'a human or facilitator must run: ref_cw.py resolve'])
    a_source, b_source, _ = locked_warriors()
    wa, wb = corewar.parse_warrior(a_source), corewar.parse_warrior(b_source)
    seed = battle_seed(a_source, b_source)
    points_a = 0.0
    with MOVES.open('a') as fh:      # genuinely append-only: never rewrite history
        for n in range(1, ROUNDS + 1):
            # Round seed = match seed + n; offsets are the engine's own draw
            # from random.Random(round_seed) (Battle with off_a/off_b=None).
            round_seed = seed + n
            battle = corewar.Battle(wa, wb, seed=round_seed)
            result = battle.run()
            out = score_of(result)
            points_a += WIN if out == '1-0' else TIE if out == 'tie' else 0.0
            lines = corewar.battle_transcript(round_seed, battle.off_a, battle.off_b,
                                              result, round_no=n)
            fh.write(lines)
            rounds.append({'n': n, 'seed': round_seed, 'off_a': battle.off_a,
                           'off_b': battle.off_b, 'out': out, 'cycles': result.cycles})
            print(lines, end='')
    err = write_battle_json(loads, rounds)
    if err:
        refuse('TAMPER DETECTED', [err])
    match = '1-0' if points_a > ROUNDS / 2 else '0-1' if points_a < ROUNDS / 2 else '1/2-1/2'
    finish_native(match, 'battle')
    print(f'GAMEOVER {match}')


def cmd_verify():
    verify()
    loads, rounds, _ = parse_transcript()
    print(f'OK verified {len(rounds)} rounds' +
          ('' if loads else ' (workshop — nothing locked yet)'))


def cmd_resolve():
    """Rebuild battle.json from the transcript plus re-simulation and clear
    the halt. Only clears when the record is again fully self-consistent
    (transcript parses, warriors match the LOAD hashes, every round
    re-simulates to its OUT line) -- a human repairs the files first, the
    transcript wins, and resolve never overwrites disagreement."""
    err = verify(log_errors=False)
    if err:
        print('CANNOT RESOLVE:', err)
        print('the record does not re-simulate; a human must repair moves.txt or '
              'warriors/ by hand first (the transcript wins).')
        sys.exit(1)
    loads, rounds, _ = parse_transcript()
    if loads:
        werr = write_battle_json(loads, rounds)
        if werr:
            print('CANNOT RESOLVE:', werr)
            sys.exit(1)
    HALT.unlink(missing_ok=True)
    chat.say(f'State rebuilt from the transcript ({len(rounds)} rounds). The match resumes.',
             name='REFEREE')
    print(f'OK resolved | {len(rounds)} rounds')


def main():
    cmd = sys.argv[1]
    if cmd == 'init':
        cmd_init('--force' in sys.argv[2:])
    elif cmd == 'check':
        cmd_check()
    elif cmd == 'stage':
        if len(sys.argv) < 3:
            sys.stderr.write('usage: ref_cw.py stage "<name>\\t<token>"\n')
            sys.exit(2)
        cmd_stage(sys.argv[2])
    elif cmd == 'lock':
        cmd_lock()
    elif cmd == 'battle':
        cmd_battle()
    elif cmd == 'verify':
        cmd_verify()
    elif cmd == 'resolve':
        cmd_resolve()
    else:
        sys.stderr.write(f'unknown command: {cmd!r} '
                         f'(expected init|check|stage|lock|battle|verify|resolve)\n')
        sys.exit(2)


if __name__ == '__main__':
    main()

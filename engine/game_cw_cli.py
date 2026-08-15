"""Agent-facing Core War interface. Same contract as game_xq_cli.py, but the
match is a workshop phase plus one best-of-3 battle, not a turn loop.

  show          — phase banner (WORKSHOP / LOCKED / BATTLE / OVER), who has a
                   warrior in the hold, rounds so far from battle.json,
                   recent chat
  status        — one-shot recovery: phase, hold, pending, locked, rounds,
                   gameover flag, and (if you have ever staged anything) a
                   STAGED/APPLIED/REJECTED report on your own last submission
                   (zero args, works after any context loss)
  stage <file>  — validate a Redcode warrior and stage it for referee
                   approval: the file is copied atomically to
                   stage_inbox/<NAME>.red and pending.txt gets
                   `<NAME>\tstage <sha256>`. Re-staging overwrites your
                   previous stage until the lock; the last valid stage
                   before the lock is what fights
  spar <file> [imp|dwarf]
                — local exhibition against a built-in dummy (default imp),
                   via corewar.quick_battle at seed 0, you are warrior A.
                   Prints the outcome; writes NOTHING to the bus — pure
                   read/print, the room never sees it
  resign        — stage a resignation for referee approval (works until
                   result.txt exists, mid-workshop or after the lock)
  await-battle  — block until the battle result is posted (battle.json has
                   all 3 rounds, or result.txt exists), then print `show`
  say <text>    — post a message to the room (everyone can read it)
  chat          — just the room

STAGED is not a promise of acceptance -- it just means the referee has seen
your warrior. `status`/`await-battle` derive the real outcome from the files
the referee controls: APPLIED compares the sha256 you staged against the
warriors/<seat>.red the referee installed (content-addressed, so a silent
swap shows up as REJECTED, never as a normal acceptance), REJECTED when
pending.txt was cleared without your hash landing in the hold.

stage/resign hard-refuse (game-5 retro fix, ported) when the caller's
identity ($CHESS_NAME) doesn't match one of the two names in seats.txt --
see chat.require_seated(). show/status/spar/say/chat stay open to
spectators.
"""
import json
import os
import sys
import time
from pathlib import Path

import corewar

D = Path(os.environ.get('ARCADE_LIVE', '/tmp/corewar'))
sys.path.insert(0, str(D))
import chat

MOVES, PENDING, RESULT = D / 'moves.txt', D / 'pending.txt', D / 'result.txt'
HALT = D / 'TAMPER.txt'
BATTLE_JSON = D / 'battle.json'
WARRIORS, INBOX = D / 'warriors', D / 'stage_inbox'
STAGE_LOG = D / 'stage_log.txt'   # append-only: every stage ever made, survives pending.txt's churn
CHAT_TAIL = 6
POLL_SECONDS = 5


def transcript_lines():
    if not MOVES.exists():
        return []
    return [ln for ln in MOVES.read_text().splitlines() if ln.strip()]


def battle_cache():
    """battle.json as a dict, or None — a renderer cache, never a truth."""
    try:
        return json.loads(BATTLE_JSON.read_text())
    except (OSError, ValueError):
        return None


def phase():
    """WORKSHOP / LOCKED / BATTLE / OVER, derived from referee-owned files.
    BATTLE (rounds but no result) is only observable if a battle stopped
    mid-run — the referee runs all three rounds in one process."""
    if RESULT.exists():
        return 'OVER'
    lines = transcript_lines()
    if any(ln.startswith('ROUND ') for ln in lines):
        return 'BATTLE'
    if any(ln.startswith('LOAD ') for ln in lines):
        return 'LOCKED'
    return 'WORKSHOP'


def my_seat_file(who):
    """warriors/A.red for the white-labelled (red) seat, B.red for black
    (blue); None when seats.txt doesn't place `who`."""
    seats = chat.seats()
    for role, seat in (('white', 'A'), ('black', 'B')):
        if seats.get(role, '').lower() == who.lower():
            return WARRIORS / f'{seat}.red'
    return None


def hold_line(name, seat):
    """'staged — warrior in the hold' / '(nothing staged)', from the
    referee-installed copies only (never pending.txt)."""
    if (WARRIORS / f'{seat}.red').exists():
        return f'{name}: warrior in the hold'
    if (INBOX / f'{name}.red').exists():
        return f'{name}: staged — awaiting the referee'
    return f'{name}: (nothing staged)'


def show():
    ph = phase()
    red, blue = chat.player_names()
    print(f'*** CORE WAR — {ph} ***')
    if ph == 'WORKSHOP':
        print('Write your warrior and stage it: bash game_cw.sh stage <file>')
    elif ph == 'LOCKED':
        print('Both warriors are locked — the battle is next.')
    print(f'  red seat:  {hold_line(red, "A")}')
    print(f'  blue seat: {hold_line(blue, "B")}')
    cache = battle_cache()
    rounds = cache.get('rounds', []) if cache else []
    if rounds:
        print('Rounds:')
        for r in rounds:
            print(f"  round {r.get('n')}: {r.get('out')} (cycles={r.get('cycles')})")
    if ph == 'OVER':
        print('Result:', RESULT.read_text().strip())
    if PENDING.exists():
        # pending.txt can be hand-written by anyone -- re-clean before
        # printing so ESC bytes never reach the terminal.
        staged = PENDING.read_text().strip().split('\t')
        if len(staged) == 2:
            who, token = chat.clean(staged[0], 24), chat.clean(staged[1])
            kind = 'a warrior' if token.startswith('stage ') else token
            print(f'NOTE: {who} has already staged {kind}.')
        else:
            print('NOTE: something is already staged:', chat.clean(PENDING.read_text()))
    print(f'You are posting as: {chat.whoami()}  (set $CHESS_NAME to change)')
    show_chat()


def show_chat():
    msgs = chat.read(limit=CHAT_TAIL)
    print(f'\n--- room (last {len(msgs)}) ---' if msgs else '\n--- room (empty) ---')
    for ts, who, text in msgs:
        print(f'  [{time.strftime("%H:%M", time.localtime(ts))}] {who}: {text}')
    print(f'  (post with: bash {D}/game_cw.sh say \'<message>\')')


def status():
    """One-shot recovery after any context loss, zero args: phase, hold,
    pending, locked, rounds, gameover flag."""
    red, blue = chat.player_names()
    print(f'phase: {phase().lower()}')
    print(f'hold: {hold_line(red, "A")}  |  {hold_line(blue, "B")}')
    if PENDING.exists():
        # Same re-clean-before-print rule as show(): pending.txt is not a
        # trusted file.
        staged = PENDING.read_text().strip().split('\t')
        if len(staged) == 2:
            print(f'pending: {chat.clean(staged[1])} (staged by {chat.clean(staged[0], 24)})')
        else:
            print('pending:', chat.clean(PENDING.read_text()) or '(malformed pending.txt)')
    else:
        print('pending: (none)')
    print(f'locked: {"yes" if phase() in ("LOCKED", "BATTLE", "OVER") and any(ln.startswith("LOAD ") for ln in transcript_lines()) else "no"}')
    cache = battle_cache()
    rounds = cache.get('rounds', []) if cache else []
    print(f'rounds: {len(rounds)}' + (' (' + ', '.join(str(r.get('out')) for r in rounds) + ')' if rounds else ''))
    if RESULT.exists():
        print(f'gameover: yes — {RESULT.read_text().strip()}')
    else:
        print('gameover: no')
    if HALT.exists():
        print('halted: yes (TAMPER.txt — the match needs a human)')
    text = format_applied_report(applied_report(chat.whoami()))
    if text:
        print()
        print(text)


# ---------------------------------------------------------------------------
# STAGED -> APPLIED / REJECTED: closing the silent-misparse gap, corewar
# edition. pending.txt only ever tells you "not yet processed" -- the referee
# (and the host's `rm -f pending.txt` after every apply attempt, success or
# failure) clears it either way, so its absence alone proves nothing.
# stage_log.txt is the durable record stage()/resign() write alongside
# pending.txt; a warrior stage carries its sha256, so APPLIED is a hash
# comparison against the referee-installed warriors/<seat>.red, never a
# text scrape.

def record_stage(who, token):
    """Append `who` staged `token` (`stage <sha256>` or `resign`) to the
    durable log, with a match-local sequence number."""
    seq = 1
    if STAGE_LOG.exists():
        seq = len(STAGE_LOG.read_text().splitlines()) + 1
    with STAGE_LOG.open('a') as fh:
        fh.write(f'{int(time.time())}\t{who}\t{seq}\t{token}\n')
    return seq


def _last_stage(who):
    """(seq, token) for `who`'s most recent stage_log.txt entry, or None."""
    if not STAGE_LOG.exists():
        return None
    who_l = who.lower()
    last = None
    for line in STAGE_LOG.read_text().splitlines():
        parts = line.split('\t')
        if len(parts) != 4:
            continue
        _, name, seq_s, token = parts
        if name.lower() == who_l:
            try:
                last = (int(seq_s), token)
            except ValueError:
                continue
    return last


def _reject_reason():
    """Best-effort, from persistent referee-written state only (never a
    chat.log text scrape)."""
    if HALT.exists():
        return 'the match is halted for tampering (see TAMPER.txt)'
    if RESULT.exists():
        return 'the match had already ended before this reached the referee'
    return ('the referee did not install it (failed validation, hash mismatch, or '
            'superseded by a later stage) -- check the room')


def applied_report(who):
    """STAGED / APPLIED / REJECTED for `who`'s most recently staged warrior
    or resign token. Returns None if `who` has never staged anything on
    record."""
    stage = _last_stage(who)
    if stage is None:
        return None
    seq, token = stage
    if token == 'resign':
        result_text = RESULT.read_text() if RESULT.exists() else ''
        if f'({who} resigned)' in result_text:
            return {'state': 'APPLIED', 'move': 'resign', 'detail': result_text.strip()}
        if PENDING.exists() and PENDING.read_text().strip() == f'{who}\t{token}':
            return {'state': 'STAGED', 'move': token}
        return {'state': 'REJECTED', 'move': token, 'reason': _reject_reason()}
    sha = token.split(None, 1)[1] if token.startswith('stage ') else None
    seat_file = my_seat_file(who)
    if sha and seat_file and seat_file.exists() and \
            corewar.sha256_warrior(seat_file.read_text()) == sha:
        locked = any(ln.startswith('LOAD ') for ln in transcript_lines())
        return {'state': 'APPLIED', 'move': 'your warrior',
                'detail': 'locked in' if locked else 'in the hold'}
    if PENDING.exists() and PENDING.read_text().strip() == f'{who}\t{token}':
        return {'state': 'STAGED', 'move': 'your warrior'}
    return {'state': 'REJECTED', 'move': 'your warrior', 'reason': _reject_reason()}


def format_applied_report(report):
    if report is None:
        return None
    lines = ['--- your last submission ---']
    if report['state'] == 'STAGED':
        lines.append(f"STAGED: {report['move']} — still awaiting the referee.")
    elif report['state'] == 'REJECTED':
        lines.append(f"REJECTED: {report['move']} was not applied — {report['reason']}.")
    else:
        lines.append(f"APPLIED: {report['move']} confirmed — {report.get('detail', '')}")
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# verbs

def battle_finished():
    """Pure predicate, split out of await_battle() for testing without a
    poll loop: the battle is consumable once result.txt exists or the
    renderer cache holds all three rounds."""
    if RESULT.exists():
        return True
    cache = battle_cache()
    return bool(cache and len(cache.get('rounds', [])) >= 3)


def _staging_who():
    """Identity for a staging verb, with both refusal gates: seated per
    seats.txt (chat.require_seated), and a name that is safe to turn into a
    stage_inbox/<name>.red filename -- '/', '\\' and '.' (a dot is enough
    for '..') are refused outright, so a traversal $CHESS_NAME can never
    steer the staging copy outside the inbox, even when seats.txt is absent
    and the seat check is a no-op."""
    if not chat.require_seated():
        sys.exit(1)
    who = chat.whoami()
    if any(c in who for c in '/\\.'):
        print(f"REFUSED: your identity {who!r} may not contain '/', '\\' or '.' — "
              'it becomes a staging filename. Fix $CHESS_NAME.')
        sys.exit(1)
    return who


def await_battle():
    """Block until the battle result is posted, then print `show`."""
    if not chat.require_seated():
        sys.exit(1)
    while not battle_finished():
        time.sleep(POLL_SECONDS)
    show()


def stage(path):
    who = _staging_who()
    try:
        source = Path(path).read_text(encoding='utf-8')
    except OSError as e:
        print(f'ILLEGAL: cannot read {path}: {e}')
        sys.exit(1)
    # Client-side pre-check with the same validator the referee runs -- the
    # referee re-validates authoritatively at apply time; a warrior that
    # fails here never reaches pending.txt and never pokes the host.
    problems = corewar.validate_warrior(source)
    if problems:
        print('ILLEGAL: this warrior does not validate (the referee would refuse it):')
        for p in problems:
            print(f'  - {p}')
        print('Fix it and re-stage. Nothing was staged.')
        sys.exit(1)
    sha = corewar.sha256_warrior(source)
    INBOX.mkdir(exist_ok=True)
    tmp = INBOX / f'.{who}.red.tmp'
    tmp.write_text(source)
    tmp.replace(INBOX / f'{who}.red')   # atomic: the referee never reads half a file
    PENDING.write_text(f'{who}\tstage {sha}')
    record_stage(who, f'stage {sha}')
    print(f'STAGED: {Path(path).name} — submitted to referee for approval, as {who}.')
    print('(this is not a confirmation of acceptance -- check `status` or `await-battle` for APPLIED)')


def spar(path, dummy='imp'):
    """Local exhibition against a built-in dummy. Pure read/print: writes
    nothing to the bus, posts nothing, stages nothing."""
    dummy = dummy.lower()
    if dummy == 'imp':
        dummy_name, dummy_source = 'Imp', corewar.IMP
    elif dummy == 'dwarf':
        dummy_name, dummy_source = 'Dwarf', corewar.DWARF
    else:
        print(f'usage: spar <file> [imp|dwarf] — no dummy named {dummy!r}')
        sys.exit(2)
    try:
        source = Path(path).read_text(encoding='utf-8')
    except OSError as e:
        print(f'ILLEGAL: cannot read {path}: {e}')
        sys.exit(1)
    problems = corewar.validate_warrior(source)
    if problems:
        print('ILLEGAL: this warrior does not assemble:')
        for p in problems:
            print(f'  - {p}')
        sys.exit(1)
    result = corewar.quick_battle(source, dummy_source, seed=0)
    out = '1-0' if result.winner == 'A' else '0-1' if result.winner == 'B' else 'tie'
    print(f'SPAR {Path(path).name} vs {dummy_name} (seed 0, you are warrior A)')
    print(f'OUT {out} cycles={result.cycles} — ' +
          ('your warrior wins' if result.winner == 'A'
           else f'{dummy_name} wins' if result.winner == 'B'
           else f'both alive at {result.cycles} cycles'))


def resign():
    who = _staging_who()
    PENDING.write_text(f'{who}\tresign')
    record_stage(who, 'resign')
    print(f'STAGED: resign — submitted to referee for approval, as {who}.')
    print('(this is not a confirmation of acceptance -- check `status` or `await-battle` for APPLIED)')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else None
    if cmd not in ('show', 'status', 'stage', 'spar', 'resign', 'await-battle',
                   'say', 'chat'):
        print(__doc__)
        sys.exit(2)
    if cmd == 'show':
        show()
    elif cmd == 'status':
        status()
    elif cmd == 'stage':
        if len(sys.argv) < 3:
            print('usage: stage <file>')
            sys.exit(2)
        stage(sys.argv[2])
    elif cmd == 'spar':
        if len(sys.argv) < 3:
            print('usage: spar <file> [imp|dwarf]')
            sys.exit(2)
        spar(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else 'imp')
    elif cmd == 'resign':
        resign()
    elif cmd == 'await-battle':
        await_battle()
    elif cmd == 'chat':
        show_chat()
    elif cmd == 'say':
        text = ' '.join(sys.argv[2:])
        if not text.strip():
            print('usage: say <message>')
            sys.exit(2)
        chat.say(text)
        print(f'SAID ({chat.whoami()}): {" ".join(text.split())}')

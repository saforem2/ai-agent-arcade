"""Agent-facing chess interface.

  show          — print board, FEN, side to move, material tally, a NUMBERED
                   legal-move menu, recent chat
  status        — one-shot recovery: ply, side to move, last move, pending,
                   gameover flag, draw-offer flag, and (if you have ever
                   staged anything) a STAGED/APPLIED/REJECTED report on your
                   own last submission (zero args, works after any context loss)
  history       — numbered SAN move list from moves.txt
  await-turn    — block until it is your seat's turn (or the game ends);
                   reports the APPLIED/REJECTED transition of your own last
                   submission first, then prints the same output as `show`
  submit <move-or-menu-number> [--say '<text>']
                — validate and stage a move for referee approval, by SAN/UCI
                  text OR by the number shown in `show`'s menu (a numeric
                  submit is re-resolved against the CURRENT position and
                  refused if the ply has moved on since the menu was
                  printed -- see submit()); with --say, also posts <text> to
                  the room, but only after the stage succeeds (one round-trip
                  instead of submit then say)
  resign        — stage a resignation for referee approval
  offer-draw    — stage a draw offer for referee approval
  accept-draw   — stage acceptance of a pending draw offer for referee approval
  say <text>    — post a message to the room (everyone can read it)

STAGED is not a promise of acceptance -- it just means the referee has seen
your move. `status`/`await-turn` derive the real outcome (APPLIED, with the
move that actually landed, the ply, who moves next and the resulting FEN --
or REJECTED) from moves.txt, the append-only log, never from pending.txt: a
move that pending.txt still shows as staged might already have been rejected
and cleared, and a move the referee applies is always compared against what
you actually staged so a silent mis-parse (the wrong move landing) shows up
as APPLIED MISMATCH instead of looking like a normal acceptance.

submit/resign/offer-draw/accept-draw hard-refuse (game-5 retro fix) when the
caller's identity ($CHESS_NAME) doesn't match one of the two names in
seats.txt -- see chat.require_seated(). show/status/history/say/chat stay
open to spectators.
"""
import os, sys, time
from pathlib import Path
import chess

D = Path(os.environ.get('ARCADE_LIVE', '/tmp/chess'))
sys.path.insert(0, str(D))
import chat

FEN, PENDING = D / 'fen.txt', D / 'pending.txt'
MOVES, RESULT, DRAW_OFFER = D / 'moves.txt', D / 'result.txt', D / 'draw_offer.txt'
HALT = D / 'TAMPER.txt'
STAGE_LOG = D / 'stage_log.txt'   # append-only: every submit()/stage_special() ever made, survives pending.txt's churn
MENU = D / 'menu.txt'             # ply the legal-move menu was last printed at, for stale-number detection
CHAT_TAIL = 6
POLL_SECONDS = 5
SPECIAL_TOKENS = ('resign', 'offer-draw', 'accept-draw')

_PIECE_LETTERS = ['K', 'Q', 'R', 'B', 'N', 'P']
_PIECE_TYPES = {'K': chess.KING, 'Q': chess.QUEEN, 'R': chess.ROOK,
                'B': chess.BISHOP, 'N': chess.KNIGHT, 'P': chess.PAWN}

def board():
    return chess.Board(FEN.read_text().strip())

def material_tally(b):
    """One line, both sides: pieces remaining by type, not a centipawn-style
    score (CODEX's request -- xiangqi values are positional and chess kept
    symmetric with it). 'Qx2'-style suffix only when a side has more than one."""
    def side(color):
        parts = []
        for letter in _PIECE_LETTERS:
            n = len(b.pieces(_PIECE_TYPES[letter], color))
            if n:
                parts.append(letter if n == 1 else f'{letter}×{n}')
        return ' '.join(parts)
    return f'Material: WHITE {side(chess.WHITE)}  |  BLACK {side(chess.BLACK)}'


def print_menu(legal_sans):
    print('Menu (submit by number or by move text):')
    for i, mv in enumerate(legal_sans, 1):
        print(f'  {i}. {mv}')


def write_menu(ply):
    MENU.write_text(str(ply))


def read_menu():
    if not MENU.exists():
        return None
    try:
        return int(MENU.read_text().strip())
    except ValueError:
        return None


def show():
    b = board()
    rows = []
    for r in range(7, -1, -1):
        row = f'{r+1} '
        for f in range(8):
            p = b.piece_at(chess.square(f, r))
            row += (p.symbol() if p else '.') + ' '
        rows.append(row)
    rows.append('  a b c d e f g h')
    print('\n'.join(rows))
    print('FEN:', b.fen())
    print('Side to move:', 'White' if b.turn else 'Black')
    if b.is_check():
        print('You are IN CHECK.')
    print(material_tally(b))
    legal_sans = sorted(b.san(m) for m in b.legal_moves)
    print('Legal moves:', ' '.join(legal_sans))
    print_menu(legal_sans)
    write_menu(len(log_moves()))
    if PENDING.exists():
        staged = PENDING.read_text().strip().split('\t')
        if len(staged) == 2:
            print(f'NOTE: {staged[0]} has already staged {staged[1]}.')
        else:
            print('NOTE: a move is already staged:', ' '.join(staged))
    print(f'You are posting as: {chat.whoami()}  (set $CHESS_NAME to change)')
    show_chat()

def show_chat():
    msgs = chat.read(limit=CHAT_TAIL)
    print(f'\n--- room (last {len(msgs)}) ---' if msgs else '\n--- room (empty) ---')
    for ts, who, text in msgs:
        print(f'  [{time.strftime("%H:%M", time.localtime(ts))}] {who}: {text}')
    print(f'  (post with: bash {D}/game.sh say \'<message>\')')

def log_moves():
    return MOVES.read_text().split() if MOVES.exists() else []

def is_over(b):
    return RESULT.exists() or b.is_game_over()

def status():
    """One-shot recovery after any context loss, zero args: ply, side to
    move, last move, pending author+move, gameover flag, draw-offer flag."""
    b = board()
    moves = log_moves()
    print(f'ply: {len(moves)}')
    print('side to move:', 'White' if b.turn else 'Black')
    print('last move:', moves[-1] if moves else '(none)')
    if PENDING.exists():
        staged = PENDING.read_text().strip().split('\t')
        if len(staged) == 2:
            print(f'pending: {staged[1]} (staged by {staged[0]})')
        else:
            print('pending:', ' '.join(staged) or '(malformed pending.txt)')
    else:
        print('pending: (none)')
    over = is_over(b)
    detail = RESULT.read_text().strip() if RESULT.exists() else (b.result() if over else '')
    print(f'gameover: {"yes" if over else "no"}' + (f' — {detail}' if detail else ''))
    if DRAW_OFFER.exists():
        print(f'draw offer pending: yes (from {DRAW_OFFER.read_text().strip()})')
    else:
        print('draw offer pending: no')
    text = format_applied_report(applied_report(chat.whoami()))
    if text:
        print()
        print(text)

def history():
    """Numbered SAN move list, one line per full move (White Black)."""
    moves = log_moves()
    if not moves:
        print('(no moves yet)')
        return
    for i in range(0, len(moves), 2):
        n = i // 2 + 1
        w = moves[i]
        b = moves[i + 1] if i + 1 < len(moves) else ''
        print(f'{n}. {w} {b}'.rstrip())

# ---------------------------------------------------------------------------
# STAGED -> APPLIED / REJECTED: closing the silent-misparse gap.
#
# pending.txt only ever tells you "not yet processed" -- the referee (and the
# host's `rm -f pending.txt` after every apply attempt, success or failure)
# clears it either way, so its absence alone proves nothing. stage_log.txt is
# the durable record submit()/stage_special() write alongside pending.txt: it
# is never cleared, so a player's *own* last submission can always be looked
# up later and compared against moves.txt -- the one file that is genuinely
# append-only and never lies about what was actually applied.

def record_stage(who, token):
    """Append `who` staged `token` (a SAN move or a SPECIAL_TOKENS entry) to
    the durable log, tagged with the ply it would become if applied."""
    ply = len(log_moves()) + 1
    with STAGE_LOG.open('a') as fh:
        fh.write(f'{int(time.time())}\t{who}\t{ply}\t{token}\n')
    return ply

def _last_stage(who):
    """(ply, token) for `who`'s most recent stage_log.txt entry, or None."""
    if not STAGE_LOG.exists():
        return None
    who_l = who.lower()
    last = None
    for line in STAGE_LOG.read_text().splitlines():
        parts = line.split('\t')
        if len(parts) != 4:
            continue
        _, name, ply_s, token = parts
        if name.lower() == who_l:
            try:
                last = (int(ply_s), token)
            except ValueError:
                continue
    return last

def replay_to(ply):
    """Rebuild the position after exactly `ply` moves, from moves.txt alone
    -- never fen.txt (which only ever holds the CURRENT position, not the
    historical one right after this player's move) and never pending.txt."""
    b = chess.Board()
    for san in log_moves()[:ply]:
        b.push_san(san)
    return b

def _reject_reason():
    """Best-effort, from persistent referee-written state only (never a
    chat.log text scrape): the specific illegal/wrong-author reason itself
    isn't recorded anywhere durable by ref.py, so this reports what we can
    prove and points the player at the room for the rest."""
    if HALT.exists():
        return 'the match is halted for tampering (see TAMPER.txt)'
    if RESULT.exists():
        return 'the game had already ended before this reached the referee'
    return 'the referee did not apply it (illegal move, wrong seat, or superseded by a later stage) -- check the room'

def applied_report(who):
    """STAGED / APPLIED / REJECTED for `who`'s most recently staged move or
    special token. Returns None if `who` has never staged anything on record.
    APPLIED always compares the move that actually landed in moves.txt
    against what was staged -- a mismatch (the adversarial case this exists
    to catch) is flagged, never silently reported as a plain acceptance."""
    stage = _last_stage(who)
    if stage is None:
        return None
    ply, token = stage
    if token in SPECIAL_TOKENS:
        return _special_report(who, token, ply)
    moves = log_moves()
    if len(moves) >= ply:
        applied = moves[ply - 1]
        try:
            b = replay_to(ply)
            fen, turn = b.fen(), ('White' if b.turn else 'Black')
        except ValueError:
            fen, turn = None, None
        return {'state': 'APPLIED', 'ply': ply, 'move': applied, 'staged': token,
                'mismatch': applied != token, 'fen': fen, 'turn': turn}
    if PENDING.exists() and PENDING.read_text().strip() == f'{who}\t{token}':
        return {'state': 'STAGED', 'move': token}
    return {'state': 'REJECTED', 'move': token, 'reason': _reject_reason()}

def _special_report(who, token, ply):
    result_text = RESULT.read_text() if RESULT.exists() else ''
    if token == 'resign' and f'({who} resigned)' in result_text:
        return {'state': 'APPLIED', 'move': 'resign', 'detail': result_text.strip()}
    if token == 'accept-draw' and f'{who} accepted' in result_text:
        return {'state': 'APPLIED', 'move': 'accept-draw', 'detail': result_text.strip()}
    if token == 'offer-draw':
        if DRAW_OFFER.exists() and DRAW_OFFER.read_text().strip() == who:
            return {'state': 'APPLIED', 'move': 'offer-draw', 'detail': 'draw offer is live'}
        if 'draw agreed' in result_text and f'({who} offered' in result_text:
            return {'state': 'APPLIED', 'move': 'offer-draw', 'detail': result_text.strip()}
        if len(log_moves()) >= ply:
            return {'state': 'CLEARED', 'move': 'offer-draw',
                    'detail': 'draw offer was applied, then cleared when play continued'}
    if PENDING.exists() and PENDING.read_text().strip() == f'{who}\t{token}':
        return {'state': 'STAGED', 'move': token}
    return {'state': 'REJECTED', 'move': token, 'reason': _reject_reason()}

def format_applied_report(report):
    if report is None:
        return None
    lines = ['--- your last submission ---']
    if report['state'] == 'STAGED':
        lines.append(f"STAGED: {report['move']} — still awaiting the referee.")
    elif report['state'] == 'CLEARED':
        lines.append(f"CLEARED: {report['move']} — {report['detail']}.")
    elif report['state'] == 'REJECTED':
        lines.append(f"REJECTED: {report['move']} was not applied — {report['reason']}.")
    elif report.get('mismatch'):
        lines.append(f"APPLIED MISMATCH: you staged {report['staged']!r}, but "
                      f"{report['move']!r} was applied at ply {report['ply']} instead. "
                      f"This is NOT what you submitted.")
        if report.get('turn'):
            lines.append(f"{report['turn']} to move now.")
        if report.get('fen'):
            lines.append(f"FEN: {report['fen']}")
    else:
        if 'ply' in report:
            lines.append(f"APPLIED: {report['move']} confirmed as submitted, ply {report['ply']}.")
            if report.get('turn'):
                lines.append(f"{report['turn']} to move now.")
            if report.get('fen'):
                lines.append(f"FEN: {report['fen']}")
        else:
            lines.append(f"APPLIED: {report['move']} confirmed — {report.get('detail', '')}")
    return '\n'.join(lines)

def my_turn_or_over(b, my_role):
    """Pure predicate, split out of await_turn() for testing without a poll
    loop: True once it's my_role's turn, or the game is over either way."""
    if is_over(b):
        return True
    return (b.turn == chess.WHITE) == (my_role == 'white')

def await_turn():
    """Block until it's the caller's seat's turn or the game ends. Reports
    the APPLIED/REJECTED transition of the caller's own last submission
    first (the natural home for it -- this call already blocks on exactly
    that transition), then prints the same output as `show`. Identity + seat
    resolution both come from seats.txt (chat.require_seated() /
    chat.seats()) -- a spectator with no seat has nothing to wait for and is
    refused up front, same as submit."""
    if not chat.require_seated():
        sys.exit(1)
    who = chat.whoami()
    my_role = next((role for role, name in chat.seats().items() if name.lower() == who.lower()), None)
    if my_role is None:
        print(f'Cannot find "{who}" in seats.txt as white or black.')
        sys.exit(1)
    while not my_turn_or_over(board(), my_role):
        time.sleep(POLL_SECONDS)
    text = format_applied_report(applied_report(who))
    if text:
        print(text)
        print()
    show()

def submit(raw, say_text=None):
    if not chat.require_seated():
        sys.exit(1)
    b = board()
    raw = raw.strip().rstrip('.').replace('0-0-0', 'O-O-O').replace('0-0', 'O-O')
    legal_sans = sorted(b.san(m) for m in b.legal_moves)
    if raw.isdigit():
        # Menu-number submit (CODEX's request): re-resolved against the
        # CURRENT position, always -- never trusted from whatever `show`
        # printed earlier. A stale number (position moved on since the menu
        # was printed) is refused outright rather than silently resolving to
        # a different move at the same index -- that would be worse than the
        # transcription error this feature exists to prevent.
        n = int(raw)
        menu_ply, current_ply = read_menu(), len(log_moves())
        if menu_ply is None:
            print('ILLEGAL: no legal-move menu on record -- run `show` first, then submit by number.')
            sys.exit(1)
        if menu_ply != current_ply:
            print(f'ILLEGAL: stale menu -- it was printed at ply {menu_ply}, the position '
                  f'is now at ply {current_ply}. Run `show` again and resubmit by its number.')
            sys.exit(1)
        if n < 1 or n > len(legal_sans):
            print(f'ILLEGAL: {n} is not a valid menu number (1-{len(legal_sans)}).')
            print('Legal moves:', ' '.join(legal_sans))
            sys.exit(1)
        raw = legal_sans[n - 1]
    try:
        mv = b.parse_san(raw)
    except ValueError:
        try:
            mv = b.parse_uci(raw.lower())
        except ValueError:
            print(f'ILLEGAL: "{raw}" is not a legal move here.')
            print('Legal moves:', ' '.join(legal_sans))
            sys.exit(1)
    san = b.san(mv)
    who = chat.whoami()
    # Moves are signed with the submitter's name so the referee can check that
    # the author actually holds the seat that is on move.
    PENDING.write_text(f'{who}\t{san}')
    record_stage(who, san)
    print(f'STAGED: {san} — submitted to referee for approval, as {who}.')
    print('(this is not a confirmation of acceptance -- check `status` or `await-turn` for APPLIED)')
    # --say posts only after a successful stage -- an illegal move above never
    # reaches here, so the room never sees commentary for a move that didn't land.
    if say_text and say_text.strip():
        chat.say(say_text)
        print(f'SAID ({who}): {" ".join(say_text.split())}')

def stage_special(token):
    if not chat.require_seated():
        sys.exit(1)
    # Same signed staging as submit(), but for the non-move tokens the
    # referee recognizes: resign, offer-draw, accept-draw.
    who = chat.whoami()
    PENDING.write_text(f'{who}\t{token}')
    record_stage(who, token)
    print(f'STAGED: {token} — submitted to referee for approval, as {who}.')
    print('(this is not a confirmation of acceptance -- check `status` or `await-turn` for APPLIED)')

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else None
    if cmd not in ('show', 'status', 'history', 'await-turn', 'submit', 'say', 'chat',
                    'resign', 'offer-draw', 'accept-draw'):
        print(__doc__)
        sys.exit(2)
    if cmd == 'show':
        show()
    elif cmd == 'status':
        status()
    elif cmd == 'history':
        history()
    elif cmd == 'await-turn':
        await_turn()
    elif cmd == 'chat':
        show_chat()
    elif cmd == 'say':
        text = ' '.join(sys.argv[2:])
        if not text.strip():
            print('usage: say <message>')
            sys.exit(2)
        chat.say(text)
        print(f'SAID ({chat.whoami()}): {" ".join(text.split())}')
    elif cmd in ('resign', 'offer-draw', 'accept-draw'):
        stage_special(cmd)
    else:
        rest = sys.argv[2:]
        move, say_text = None, None
        i = 0
        while i < len(rest):
            if rest[i] == '--say':
                if i + 1 >= len(rest):
                    print("usage: submit <move> [--say '<text>']")
                    sys.exit(2)
                say_text = rest[i + 1]
                i += 2
            elif move is None:
                move = rest[i]
                i += 1
            else:
                i += 1   # tolerant of stray extra args, same as before --say existed
        if move is None:
            print("usage: submit <move> [--say '<text>']")
            sys.exit(2)
        submit(move, say_text)

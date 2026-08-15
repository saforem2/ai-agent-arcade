"""Xiangqi referee. Same trust model as ref.py (chess), ICCS instead of SAN.

moves.txt is the single append-only source of truth. Every apply replays the
whole log from the start (via xiangqi.XiangqiBoard) and refuses to proceed if
the recomputed position disagrees with fen.txt — so tampering with fen.txt or
the board cache does not change the game, it only makes itself visible. The
loud report goes to stderr (relay logs capture it, humans see it on screen)
while stdout stays exactly `ILLEGAL`, which every existing caller already
treats as a refusal.

Moves staged through game.sh are signed: pending.txt holds `<name>\t<iccs>` and
the referee refuses a move whose author does not hold the seat that is on
move. A bare ICCS string is treated as unsigned and skips that check, for
direct human use.

`move` also accepts three non-ICCS tokens in place of an ICCS move — `resign`,
`offer-draw`, `accept-draw` — staged the same way (`<name>\tresign`, etc.),
ported from ref.py's (chess) own apply_special(). These require a seated
author (red or black) but not that it be their turn. A resignation or an
accepted draw ends the game: it is appended to results.txt as
`<RED> <RESULT> <BLACK>` and recorded in result.txt, which then refuses every
later `move` call, same as a checkmated/stalemated board would. An offer is
tracked in draw_offer.txt; any real move played while one is pending clears
it.

Seats: names.txt is `<RED> <BLACK>`, one line, two words — red moves first,
holding the same "first mover" seat chess.py calls white (see check_author()
and apply_special() below for where that mapping is actually used). Xiangqi
scoring differs from chess in one place: a stalemated side LOSES here (there
is no draw-by-stalemate in xiangqi), so `is_checkmate() or is_stalemate()`
both route through the same "side to move has no legal moves, loses" branch.

Not enforced (documented, not implemented — inherited from xiangqi.py's own
scope limits): perpetual-check / perpetual-chase adjudication, and threefold
repetition as an automatic draw. is_repetition() exists on the board object
but this referee never calls it, so a repeated position is not itself
game-over; only "no legal moves" (or a resignation/accepted draw) ends a game
here. A human/facilitator must adjudicate those cases by hand for now.

  init [--force]  reset to the starting position; refuses over a non-empty log
  move <iccs>     validate + apply, after verifying the log and the author
                  (accepts `<name>\t<iccs>`, i.e. the contents of pending.txt;
                  also accepts `resign` / `offer-draw` / `accept-draw`)
  verify          check log vs fen.txt and exit non-zero on disagreement
  resolve         clear a tamper halt (facilitator/human only) by rebuilding
                  fen.txt from the log
"""
import os
import sys
from pathlib import Path
from xiangqi import XiangqiBoard, IllegalMove

D = Path(os.environ.get('ARCADE_LIVE', '/tmp/xiangqi'))
# chat.py resolves its own D independently from ARCADE_LIVE (default
# /tmp/chess) -- without this, an unset ARCADE_LIVE would leave *our* state
# in /tmp/xiangqi while chat.say/player_names/roles silently read/write the
# live CHESS dir instead. setdefault is a no-op once ARCADE_LIVE is set.
os.environ.setdefault('ARCADE_LIVE', str(D))
sys.path.insert(0, str(D))
import chat

FEN = D / 'fen.txt'
MOVES = D / 'moves.txt'
BOARD = D / 'board.txt'
HALT = D / 'TAMPER.txt'
RESULTS = D / 'results.txt'
RESULT = D / 'result.txt'
DRAW_OFFER = D / 'draw_offer.txt'
BANNER = D / 'banner.txt'
STAGE_LOG = D / 'stage_log.txt'
MENU = D / 'menu.txt'

SPECIAL_TOKENS = ('resign', 'offer-draw', 'accept-draw')


def render(board, note=''):
    players = chat.player_names()
    red, black = players[0], players[1]
    lines = [str(board), '']
    lines.append(f'  {red} (Red)  vs  {black} (Black)')
    lines.append('')
    moves = log_moves()
    pairs = []
    for i in range(0, len(moves), 2):
        n = i // 2 + 1
        r = moves[i]
        b = moves[i + 1] if i + 1 < len(moves) else ''
        pairs.append(f'{n}. {r} {b}')
    for i in range(max(0, len(pairs) - 6), len(pairs), 2):
        lines.append('  ' + '  '.join(pairs[i:i + 2]))
    lines.append('')
    over, result = game_over_result(board)
    if over:
        reason = 'checkmate' if board.is_check() else 'stalemate — no legal moves'
        lines.append(f'  *** GAME OVER: {result} ({reason}) ***')
    else:
        turn = f'{red} (Red)' if board.turn == 'r' else f'{black} (Black)'
        chk = '  — CHECK!' if board.is_check() else ''
        lines.append(f'  to move: {turn}{chk}')
    if note:
        lines.append(f'  {note}')
    BOARD.write_text('\n'.join(lines) + '\n')


def log_moves():
    return MOVES.read_text().split() if MOVES.exists() else []


def game_over_result(board):
    """(is_over, score) where score is '1-0'/'0-1' chess-style (red = white's
    seat). Xiangqi has no draw-by-stalemate: the side to move with zero legal
    moves loses, whether that's checkmate or stalemate — is_checkmate() and
    is_stalemate() are exactly complementary given no legal moves, so testing
    "no legal moves" once covers both."""
    if board.legal_moves():
        return False, None
    return True, ('0-1' if board.turn == 'r' else '1-0')


def finish_native(board, result, reason):
    """Terminal state reached by an ordinary move (checkmate or the
    no-legal-moves stalemate-loses rule) finishes the ledger exactly like the
    resign path in apply_special -- the game-6 retro fix, ported from ref.py.
    Idempotent: a result.txt already on disk, or the exact entry already the
    last line of results.txt, means don't double-append."""
    if RESULT.exists():
        return
    red, black = chat.player_names()
    entry = f'{red} {result} {black}'
    last_line = ''
    if RESULTS.exists():
        lines = [l for l in RESULTS.read_text().splitlines() if l.strip()]
        last_line = lines[-1] if lines else ''
    if last_line != entry:
        with RESULTS.open('a') as fh:
            fh.write(entry + '\n')
    winner = red if result == '1-0' else black
    RESULT.write_text(f'{winner} wins by {reason}\n')
    BANNER.write_text(f'{entry} — {reason}\n')
    chat.say(f'{entry} ({reason})', name='REFEREE')


def replay():
    """Rebuild the position from moves.txt. Returns (board, error_or_None)."""
    b = XiangqiBoard()
    for i, iccs in enumerate(log_moves()):
        try:
            b.push(iccs)
        except IllegalMove:
            return b, f'move {i + 1} in moves.txt is not legal there: {iccs!r}'
    return b, None


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
    """pending.txt carries `<name>\\t<iccs>`. A bare ICCS is unsigned (manual use)."""
    if '\t' in arg:
        who, iccs = arg.split('\t', 1)
        return chat.clean(who, 24) or None, iccs.strip()
    return None, arg.strip()


def check_author(who, board):
    """A signed move must come from whoever holds the seat that is on move.

    chat.role_of()/chat.player_names() are shared with chess and label seats
    'white'/'black' internally (players[0]/players[1]); red plays the seat
    chess calls white (first mover) — that mapping is used only to reuse the
    shared roles machinery, never surfaced in the human-facing message below.
    """
    if who is None:
        return
    players = chat.player_names()
    is_red_turn = board.turn == 'r'
    want_role = 'white' if is_red_turn else 'black'
    want_color = 'red' if is_red_turn else 'black'
    role = chat.role_of(who, chat.roles(), players)
    if role != want_role:
        seat = players[0] if is_red_turn else players[1]
        sys.stderr.write(f'WRONG AUTHOR: {who} submitted a move but it is '
                         f'{seat}\'s turn ({want_color}).\n')
        chat.say(f'Rejected a move signed {who} — it is {seat} to move.',
                 name='REFEREE')
        print('ILLEGAL')
        sys.exit(4)


def check_seated(who):
    """Resign/offer-draw/accept-draw need a seated author, but not their turn.
    Returns (role, (red, black)); exits on an unsigned or unseated author.

    role is 'white'/'black' (chat.role_of()'s own labels, players[0]/[1]) --
    the same red<->white seat mapping check_author() uses, never surfaced to
    the caller beyond apply_special() below."""
    players = chat.player_names()
    role = chat.role_of(who, chat.roles(), players) if who else 'watcher'
    if role not in ('white', 'black'):
        sys.stderr.write(f'WRONG AUTHOR: {who!r} does not hold a seat in this game.\n')
        chat.say(f'Rejected — {who or "an unsigned submission"} is not seated.',
                 name='REFEREE')
        print('ILLEGAL')
        sys.exit(4)
    return role, players


def apply_special(token, author, board):
    """Handle resign / offer-draw / accept-draw, staged like a move in
    pending.txt. Ported from ref.py's (chess) apply_special() -- role=='white'
    means the RED seat (players[0]) resigned/offered/accepted, matching
    check_author()'s own red<->white mapping. Scoring stays chess-style
    ('1-0'/'0-1'/'1/2-1/2') so results.txt/result.txt read the same across
    both games."""
    role, (red, black) = check_seated(author)
    if token == 'resign':
        winner, result = (black, '0-1') if role == 'white' else (red, '1-0')
        with RESULTS.open('a') as fh:
            fh.write(f'{red} {result} {black}\n')
        RESULT.write_text(f'{winner} wins by resignation ({author} resigned)\n')
        DRAW_OFFER.unlink(missing_ok=True)
        chat.say(f'{red} {result} {black} ({author} resigns)', name='REFEREE')
        print(f'GAMEOVER {result} — {winner} wins by resignation')
        return
    if token == 'offer-draw':
        DRAW_OFFER.write_text(author)
        chat.say(f'{author} offers a draw.', name='REFEREE')
        print(f'OK draw offered by {author}')
        return
    # accept-draw
    offerer = DRAW_OFFER.read_text().strip() if DRAW_OFFER.exists() else ''
    if not offerer:
        sys.stderr.write('REJECTED: no draw offer is pending.\n')
        chat.say(f'{author} tried to accept a draw, but none is pending.',
                 name='REFEREE')
        print('ILLEGAL')
        sys.exit(4)
    if offerer.lower() == author.lower():
        sys.stderr.write('REJECTED: cannot accept your own draw offer.\n')
        print('ILLEGAL')
        sys.exit(4)
    with RESULTS.open('a') as fh:
        fh.write(f'{red} 1/2-1/2 {black}\n')
    RESULT.write_text(f'draw agreed ({offerer} offered, {author} accepted)\n')
    DRAW_OFFER.unlink(missing_ok=True)
    chat.say(f'{red} 1/2-1/2 {black} (draw agreed)', name='REFEREE')
    print('GAMEOVER 1/2-1/2 — draw agreed')


def verify():
    """Compare the replayed log against fen.txt. Refuses (exits) on divergence
    or on a fen.txt that doesn't even parse as a xiangqi FEN."""
    board, err = replay()
    if err:
        refuse('TAMPER DETECTED', [f'moves.txt does not replay: {err}',
                                   'the move log itself has been edited'])
    stored = FEN.read_text().strip() if FEN.exists() else ''
    if not stored and log_moves():
        # Losing the cache is not an attack, but it must not happen quietly.
        FEN.write_text(board.fen())
        chat.say(f'fen.txt was missing — regenerated from the move log at ply '
                 f'{len(log_moves())}.', name='REFEREE')
        sys.stderr.write(f'NOTE: fen.txt was missing/empty; regenerated from the '
                         f'log at ply {len(log_moves())}.\n')
        return board
    if stored:
        try:
            XiangqiBoard.from_fen(stored)
        except ValueError as e:
            refuse('TAMPER DETECTED', [f'fen.txt is not a valid xiangqi FEN: {e}',
                                       f'log has {len(log_moves())} plies and is authoritative;'
                                       ' fen.txt was corrupted or hand-edited',
                                       'a human or facilitator must run: ref_xq.py resolve'])
        if stored != board.fen():
            refuse('TAMPER DETECTED', [f'log FEN:    {board.fen()}',
                                       f'state FEN:  {stored}',
                                       f'log has {len(log_moves())} plies and is authoritative;'
                                       ' fen.txt was changed behind the referee',
                                       'a human or facilitator must run: ref_xq.py resolve'])
    return board


def main():
    cmd = sys.argv[1]
    if cmd == 'init':
        if log_moves() and '--force' not in sys.argv[2:]:
            sys.stderr.write(
                f'REFUSING to init: moves.txt already holds {len(log_moves())} plies.\n'
                'Initialising mid-match would destroy the only record of the game.\n'
                'If the previous match really is finished, run: ref_xq.py init --force\n')
            print('ILLEGAL')
            sys.exit(5)
        board = XiangqiBoard()
        FEN.write_text(board.fen())
        MOVES.write_text('')
        HALT.unlink(missing_ok=True)
        # A leftover result.txt/draw_offer.txt from the previous match must
        # not make a brand-new game refuse every move as "already over" --
        # ref.py (chess) doesn't clear these on init, which is a latent gap
        # there; closed here since it's cheap and clearly correct.
        RESULT.unlink(missing_ok=True)
        DRAW_OFFER.unlink(missing_ok=True)
        # Client-side receipts/menu numbers belong to the same match epoch
        # as moves.txt. Reusing a live directory must not surface a previous
        # game's last submission or accept a stale numbered-menu selection.
        STAGE_LOG.unlink(missing_ok=True)
        MENU.unlink(missing_ok=True)
        render(board, 'match starting...')
        print('OK', board.fen())
    elif cmd == 'verify':
        board = verify()
        print('OK verified', len(log_moves()), 'plies |', board.fen())
    elif cmd == 'resolve':
        board, err = replay()
        if err:
            print('CANNOT RESOLVE:', err)
            print('moves.txt is corrupt; a human must repair the log by hand.')
            sys.exit(1)
        FEN.write_text(board.fen())
        render(board, 'state rebuilt from move log')
        HALT.unlink(missing_ok=True)
        chat.say(f'State rebuilt from the move log at ply {len(log_moves())}. Play resumes.',
                 name='REFEREE')
        print('OK resolved |', board.fen())
    elif cmd == 'move':
        if HALT.exists():
            sys.stderr.write('REFUSING: match is halted for tampering. '
                             'Run `ref_xq.py resolve` after a human review.\n')
            print('ILLEGAL')
            sys.exit(3)
        author, raw = split_signed(sys.argv[2])
        raw = raw.strip().rstrip('.').lower()
        board = verify()
        over, result = game_over_result(board)
        if RESULT.exists() or over:
            detail = RESULT.read_text().strip() if RESULT.exists() else result
            sys.stderr.write(f'REFUSING: game already over — {detail}.\n')
            print('ILLEGAL')
            sys.exit(6)
        if raw in SPECIAL_TOKENS:
            apply_special(raw, author, board)
            sys.exit(0)
        check_author(author, board)
        try:
            board.push(raw)
        except IllegalMove:
            print('ILLEGAL')
            sys.exit(1)
        with MOVES.open('a') as fh:      # genuinely append-only: never rewrite history
            fh.write(raw if MOVES.stat().st_size == 0 else ' ' + raw)
        FEN.write_text(board.fen())
        if DRAW_OFFER.exists():
            offerer = DRAW_OFFER.read_text().strip()
            if offerer.lower() != (author or '').lower():
                DRAW_OFFER.unlink(missing_ok=True)
                chat.say(f"{offerer}'s draw offer declined — {author or 'a player'} played on.",
                         name='REFEREE')
        render(board)
        print('OK', raw, '|', board.fen())
        over, result = game_over_result(board)
        if over:
            reason = 'checkmate' if board.is_check() else 'stalemate — no legal moves'
            finish_native(board, result, reason)
            print('GAMEOVER', result)
    else:
        sys.stderr.write(f'unknown command: {cmd!r} (expected init|move|verify|resolve)\n')
        sys.exit(2)


if __name__ == '__main__':
    main()

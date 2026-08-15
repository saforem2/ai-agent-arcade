"""Referee. moves.txt is the single append-only source of truth.

Every apply replays the whole log from the start and refuses to proceed if the
recomputed position disagrees with fen.txt — so tampering with fen.txt or the
board cache does not change the game, it only makes itself visible. The loud
report goes to stderr (relay logs capture it, humans see it on screen) while
stdout stays exactly `ILLEGAL`, which every existing caller already treats as a
refusal.

Moves staged through game.sh are signed: pending.txt holds `<name>\t<san>` and the
referee refuses a move whose author does not hold the seat that is on move. A bare
SAN is treated as unsigned and skips that check, for direct human use.

`move` also accepts three non-SAN tokens in place of a SAN — `resign`,
`offer-draw`, `accept-draw` — staged the same way (`<name>\tresign`, etc.).
These require a seated author (white or black) but not that it be their turn.
A resignation or an accepted draw ends the game: it is appended to
results.txt as `<WHITE> <RESULT> <BLACK>` and recorded in result.txt, which
then refuses every later `move` call, same as a checkmated board would. An
offer is tracked in draw_offer.txt; any real move played while one is pending
clears it.

  init [--force]  reset to the starting position; refuses over a non-empty log
  move <san>      validate + apply, after verifying the log and the author
                  (accepts `<name>\t<san>`, i.e. the contents of pending.txt;
                  also accepts `resign` / `offer-draw` / `accept-draw`)
  verify          check log vs fen.txt and exit non-zero on disagreement
  resolve         clear a tamper halt (facilitator/human only) by rebuilding
                  fen.txt from the log
"""
import os
import sys
from pathlib import Path
import chess

D = Path(os.environ.get('ARCADE_LIVE', '/tmp/chess'))
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

SPECIAL_TOKENS = ('resign', 'offer-draw', 'accept-draw')

PIECES = {'R': '♜', 'N': '♞', 'B': '♝', 'Q': '♛', 'K': '♚', 'P': '♟',
          'r': '♖', 'n': '♘', 'b': '♗', 'q': '♕', 'k': '♔', 'p': '♙'}

def render(board, note=''):
    lines = []
    lines.append('   ╔═══════════════════════════╗')
    for rank in range(7, -1, -1):
        row = f' {rank+1} ║ '
        for file in range(8):
            p = board.piece_at(chess.square(file, rank))
            row += (PIECES[p.symbol()] if p else '·') + '  '
        lines.append(row.rstrip() + ' ║')
    lines.append('   ╚═══════════════════════════╝')
    lines.append('     a  b  c  d  e  f  g  h')
    lines.append('')
    white, black = chat.player_names()
    lines.append(f'  ♔ {white} (White)  vs  ♚ {black} (Black)')
    lines.append('')
    moves = MOVES.read_text().split() if MOVES.exists() else []
    pairs = []
    for i in range(0, len(moves), 2):
        n = i // 2 + 1
        w = moves[i]
        b = moves[i + 1] if i + 1 < len(moves) else ''
        pairs.append(f'{n}. {w} {b}')
    for i in range(max(0, len(pairs) - 6), len(pairs), 2):
        lines.append('  ' + '  '.join(pairs[i:i + 2]))
    lines.append('')
    if board.is_game_over():
        lines.append(f'  *** GAME OVER: {board.result()} ***')
    else:
        turn = f'{white} (White)' if board.turn else f'{black} (Black)'
        chk = '  — CHECK!' if board.is_check() else ''
        lines.append(f'  to move: {turn}{chk}')
    if note:
        lines.append(f'  {note}')
    BOARD.write_text('\n'.join(lines) + '\n')

def log_moves():
    return MOVES.read_text().split() if MOVES.exists() else []


def replay():
    """Rebuild the position from moves.txt. Returns (board, error_or_None)."""
    b = chess.Board()
    for i, san in enumerate(log_moves()):
        try:
            b.push_san(san)
        except ValueError:
            return b, f'move {i + 1} in moves.txt is not legal there: {san!r}'
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
    """pending.txt carries `<name>\\t<san>`. A bare SAN is unsigned (manual use)."""
    if '\t' in arg:
        who, san = arg.split('\t', 1)
        return chat.clean(who, 24) or None, san.strip()
    return None, arg.strip()


def check_author(who, board):
    """A signed move must come from whoever holds the seat that is on move."""
    if who is None:
        return
    players = chat.player_names()
    want = 'white' if board.turn == chess.WHITE else 'black'
    role = chat.role_of(who, chat.roles(), players)
    if role != want:
        seat = players[0] if want == 'white' else players[1]
        sys.stderr.write(f'WRONG AUTHOR: {who} submitted a move but it is '
                         f'{seat}\'s turn ({want}).\n')
        chat.say(f'Rejected a move signed {who} — it is {seat} to move.',
                 name='REFEREE')
        print('ILLEGAL')
        sys.exit(4)


def check_seated(who):
    """Resign/offer-draw/accept-draw need a seated author, but not their turn.
    Returns (role, (white, black)); exits on an unsigned or unseated author."""
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
    """Handle resign / offer-draw / accept-draw, staged like a move in pending.txt."""
    role, (white, black) = check_seated(author)
    if token == 'resign':
        winner, result = (black, '0-1') if role == 'white' else (white, '1-0')
        with RESULTS.open('a') as fh:
            fh.write(f'{white} {result} {black}\n')
        RESULT.write_text(f'{winner} wins by resignation ({author} resigned)\n')
        DRAW_OFFER.unlink(missing_ok=True)
        chat.say(f'{white} {result} {black} ({author} resigns)', name='REFEREE')
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
        fh.write(f'{white} 1/2-1/2 {black}\n')
    RESULT.write_text(f'draw agreed ({offerer} offered, {author} accepted)\n')
    DRAW_OFFER.unlink(missing_ok=True)
    chat.say(f'{white} 1/2-1/2 {black} (draw agreed)', name='REFEREE')
    print('GAMEOVER 1/2-1/2 — draw agreed')


def game_over_reason(board):
    if board.is_checkmate():
        return 'checkmate'
    if board.is_stalemate():
        return 'stalemate'
    if board.is_insufficient_material():
        return 'insufficient material'
    if board.is_seventyfive_moves():
        return '75-move rule'
    if board.is_fivefold_repetition():
        return 'fivefold repetition'
    return 'game over'


def finish_native(board, reason):
    """Terminal state reached by an ordinary move (checkmate, stalemate, or any
    other native chess.Board game-over) finishes the ledger exactly like the
    resign path in apply_special -- the game-6 retro fix: mate used to only
    print GAMEOVER, leaving results.txt/result.txt/banner.txt for the host to
    fill in by hand. Idempotent: a result.txt already on disk, or the exact
    entry already the last line of results.txt, means don't double-append.
    """
    if RESULT.exists():
        return
    white, black = chat.player_names()
    result = board.result()
    entry = f'{white} {result} {black}'
    last_line = ''
    if RESULTS.exists():
        lines = [l for l in RESULTS.read_text().splitlines() if l.strip()]
        last_line = lines[-1] if lines else ''
    if last_line != entry:
        with RESULTS.open('a') as fh:
            fh.write(entry + '\n')
    if result == '1/2-1/2':
        RESULT.write_text(f'draw ({reason})\n')
    else:
        winner = white if result == '1-0' else black
        RESULT.write_text(f'{winner} wins by {reason}\n')
    BANNER.write_text(f'{entry} — {reason}\n')
    chat.say(f'{entry} ({reason})', name='REFEREE')


def verify():
    """Compare the replayed log against fen.txt. Refuses (exits) on divergence."""
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
    if stored and stored != board.fen():
        refuse('TAMPER DETECTED', [f'log FEN:    {board.fen()}',
                                   f'state FEN:  {stored}',
                                   f'log has {len(log_moves())} plies and is authoritative;'
                                   ' fen.txt was changed behind the referee',
                                   'a human or facilitator must run: ref.py resolve'])
    return board


cmd = sys.argv[1]
if cmd == 'init':
    if log_moves() and '--force' not in sys.argv[2:]:
        sys.stderr.write(
            f'REFUSING to init: moves.txt already holds {len(log_moves())} plies.\n'
            'Initialising mid-match would destroy the only record of the game.\n'
            'If the previous match really is finished, run: ref.py init --force\n')
        print('ILLEGAL')
        sys.exit(5)
    board = chess.Board()
    FEN.write_text(board.fen())
    MOVES.write_text('')
    HALT.unlink(missing_ok=True)
    # A leftover result.txt/draw_offer.txt from the previous match must not
    # make a brand-new game refuse every move as "already over" (the `move`
    # command below checks RESULT.exists() before anything else). Found and
    # fixed first in ref_xq.py's own init, backported here (results.txt
    # itself stays untouched -- it's the cumulative cross-match series).
    RESULT.unlink(missing_ok=True)
    DRAW_OFFER.unlink(missing_ok=True)
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
                         'Run `ref.py resolve` after a human review.\n')
        print('ILLEGAL')
        sys.exit(3)
    author, raw = split_signed(sys.argv[2])
    raw = raw.strip().rstrip('.')
    token = raw.lower()
    board = verify()
    if RESULT.exists() or board.is_game_over():
        detail = RESULT.read_text().strip() if RESULT.exists() else board.result()
        sys.stderr.write(f'REFUSING: game already over — {detail}.\n')
        print('ILLEGAL')
        sys.exit(6)
    if token in SPECIAL_TOKENS:
        apply_special(token, author, board)
        sys.exit(0)
    raw = raw.replace('0-0-0', 'O-O-O').replace('0-0', 'O-O')
    check_author(author, board)
    mv = None
    try:
        mv = board.parse_san(raw)
    except ValueError:
        try:
            mv = board.parse_uci(raw.lower())
        except ValueError:
            print('ILLEGAL')
            sys.exit(1)
    san = board.san(mv)
    board.push(mv)
    with MOVES.open('a') as fh:      # genuinely append-only: never rewrite history
        fh.write(san if MOVES.stat().st_size == 0 else ' ' + san)
    FEN.write_text(board.fen())
    if DRAW_OFFER.exists():
        offerer = DRAW_OFFER.read_text().strip()
        if offerer.lower() != (author or '').lower():
            DRAW_OFFER.unlink(missing_ok=True)
            chat.say(f"{offerer}'s draw offer declined — {author or 'a player'} played on.",
                     name='REFEREE')
    render(board)
    print('OK', san, '|', board.fen())
    if board.is_game_over():
        finish_native(board, game_over_reason(board))
        print('GAMEOVER', board.result())

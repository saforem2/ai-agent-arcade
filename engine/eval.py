"""One-line game assessment for the host to paste/quote.

Reads fen.txt and names.txt from the live match dir (ARCADE_LIVE or
/tmp/chess), sums material by piece value, and — if a `stockfish` binary is
on PATH — asks it for an engine score of the current position. Prints one
line to stdout and nothing else.

  python3 eval.py
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import chess

D = Path(os.environ.get('ARCADE_LIVE', '/tmp/chess'))
FEN = D / 'fen.txt'
NAMES = D / 'names.txt'

VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
          chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}


def read_names():
    try:
        parts = NAMES.read_text().split()
    except OSError:
        parts = []
    if len(parts) != 2:
        return 'WHITE', 'BLACK'
    return parts[0], parts[1]


def material_summary(board):
    """Returns (white_str, black_str, white_total, black_total)."""
    letters = [('P', chess.PAWN), ('N', chess.KNIGHT), ('B', chess.BISHOP),
               ('R', chess.ROOK), ('Q', chess.QUEEN)]

    def side(color):
        counts = {sym: len(board.pieces(pt, color)) for sym, pt in letters}
        total = sum(counts[sym] * VALUES[pt] for sym, pt in letters)
        pieces = ''.join(f'{sym}{n}' for sym, pt in letters
                          for n in [counts[sym]] if n)
        return pieces or '-', total

    w_pieces, w_total = side(chess.WHITE)
    b_pieces, b_total = side(chess.BLACK)
    return w_pieces, b_pieces, w_total, b_total


def story_hint(board):
    """One deterministic, qualitative color-commentary phrase from the
    position alone (no history) -- a game-6 retro backlog item
    (docs/seat-feedback-game6.md: "eval.py optional story: one-line color
    hint for the booth"). Log-only by construction, same as every other
    line this script prints: eval.py has no path to chat.log at all (it
    only ever writes stdout, which the host redirects to eval.log --
    see FACILITATOR.md's Commentary section), so there is nothing here
    for the "never post to players" rule to guard against.

    Phase is read from piece count + FEN's own fullmove counter (both
    already on the parsed Board, no extra state needed); king safety is
    read from check status and whether the mover's king has left its
    home square -- not real castling detection, just a cheap same-square
    proxy, which is exactly the "deliberately simple" scope this backlog
    item asked for."""
    pieces = board.piece_map()
    non_pawn_king = sum(1 for p in pieces.values() if p.piece_type not in (chess.PAWN, chess.KING))
    queens_on = any(p.piece_type == chess.QUEEN for p in pieces.values())
    if not queens_on or non_pawn_king <= 6:
        phase = 'endgame'
    elif board.fullmove_number <= 10 and non_pawn_king >= 12:
        phase = 'opening'
    else:
        phase = 'middlegame'

    mover_home = chess.E1 if board.turn == chess.WHITE else chess.E8
    if board.is_check():
        safety = 'mover is in check'
    elif board.king(board.turn) != mover_home:
        safety = "mover's king has left home"
    else:
        safety = "mover's king still uncastled"

    return f'{phase}, {safety}'


def _wait_for(proc, token, deadline_lines=10000):
    """Read stdout lines until one starts with `token`. Raises on EOF."""
    for _ in range(deadline_lines):
        line = proc.stdout.readline()
        if not line:
            raise OSError(f'stockfish closed stdout before {token!r}')
        if line.startswith(token):
            return
    raise OSError(f'stockfish never sent {token!r}')


def engine_eval(fen):
    """Returns (kind, val) — score relative to the side to move — or None.

    kind is 'cp' (centipawns) or 'mate' (moves to mate); val is UCI's raw
    signed number: positive favors the side to move, negative favors the
    opponent. Callers must convert to an absolute (White-relative) frame
    before display — do not print this raw value.
    """
    sf = shutil.which('stockfish')
    if not sf:
        return None
    try:
        proc = subprocess.Popen(sf, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 text=True, bufsize=1)
    except OSError:
        return None
    score = None
    try:
        proc.stdin.write('uci\n')
        proc.stdin.flush()
        _wait_for(proc, 'uciok')
        proc.stdin.write('isready\n')
        proc.stdin.flush()
        _wait_for(proc, 'readyok')
        proc.stdin.write(f'position fen {fen}\n')
        proc.stdin.write('go movetime 1000\n')
        proc.stdin.flush()
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            if line.startswith('info') and ' score ' in line:
                toks = line.split()
                i = toks.index('score')
                kind, val = toks[i + 1], int(toks[i + 2])
                score = (kind, val)
            if line.startswith('bestmove'):
                break
        proc.stdin.write('quit\n')
        proc.stdin.flush()
    except (OSError, BrokenPipeError, ValueError):
        score = None
    finally:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    return score


def main():
    if not FEN.exists() or not FEN.read_text().strip():
        print('no game')
        return
    fen = FEN.read_text().strip()
    try:
        board = chess.Board(fen)
    except ValueError:
        print('no game')
        return

    white, black = read_names()
    mover = white if board.turn == chess.WHITE else black

    w_pieces, b_pieces, w_total, b_total = material_summary(board)
    diff = w_total - b_total
    if diff > 0:
        leader = f'{white} +{diff}'
    elif diff < 0:
        leader = f'{black} +{-diff}'
    else:
        leader = 'level'
    material = f'material: {leader} (W:{w_pieces} vs B:{b_pieces})'

    score = engine_eval(fen)
    if score is None:
        engine_part = 'eval: unavailable (install stockfish)'
    else:
        kind, val = score
        # UCI score is relative to the side to move; flip to White-relative
        # so a sign flip on the mover's turn can't swap who the eval favors.
        # One unambiguous output form from here on (game-5 retro fix): the
        # sign is always White-relative, and the favored SIDE (name + color)
        # is always spelled out explicitly -- never lead with the mover's
        # name in a way that could read as "the number is theirs."
        white_rel = val if board.turn == chess.WHITE else -val
        if kind == 'mate':
            if white_rel == 0:
                engine_part = 'eval: mate now (stockfish)'
            else:
                favored = white if white_rel > 0 else black
                color = 'White' if white_rel > 0 else 'Black'
                engine_part = f'eval: mate in {abs(white_rel)} (favors {favored} / {color}) (stockfish)'
        else:
            if white_rel == 0:
                engine_part = 'eval: +0.00 (even) (stockfish)'
            else:
                favored = white if white_rel > 0 else black
                color = 'White' if white_rel > 0 else 'Black'
                sign = '+' if white_rel > 0 else '-'
                engine_part = (f'eval: {sign}{abs(white_rel) / 100:.2f} '
                                f'(favors {favored} / {color}) (stockfish)')

    story = f'story: {story_hint(board)}'

    if board.is_checkmate():
        winner = black if board.turn == chess.WHITE else white
        print(f'CHECKMATE — {winner} wins | {material} | {engine_part} | {story}')
    elif board.is_stalemate():
        print(f'STALEMATE | {material} | {engine_part} | {story}')
    else:
        print(f'{mover} to move | {material} | {engine_part} | {story}')


if __name__ == '__main__':
    main()

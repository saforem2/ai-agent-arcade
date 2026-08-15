"""Pure-Python xiangqi (Chinese chess) move-generation engine.

Board model
-----------
9 files (columns) a-i (0-8, left to right) x 10 ranks (rows) 0-9 (bottom to
top). Red's back rank is row 0, black's back rank is row 9. The river runs
between row 4 (red side) and row 5 (black side).

Piece letters (python-chess-flavoured, matches standard xiangqi FEN):
    R chariot (rook)   N horse (knight)   B elephant (bishop)
    A advisor          K general (king)   C cannon
    P soldier (pawn)
Uppercase = red, lowercase = black.

Move notation is ICCS coordinate format: <file><rank><file><rank>, e.g.
"h2e2" (from h2 to e2). Ranks are single digits 0-9 (10 ranks fit in one
digit, unlike the 1-10 convention some sources use), so this is the
canonical wire format requested for this engine.

Out of scope (documented, not implemented): perpetual-check / perpetual-chase
adjudication (the rules requiring a chasing/checking side to change its move
after N repetitions). Only stalemate/checkmate/basic threefold-repetition
detection are provided; see `is_repetition()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

FILES = "abcdefghi"
STARTING_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"


class IllegalMove(Exception):
    """Raised by push() when the given ICCS move is not legal."""


# --------------------------------------------------------------------------
# Coordinate helpers
# --------------------------------------------------------------------------

def sq_to_str(r: int, c: int) -> str:
    return f"{FILES[c]}{r}"


def str_to_sq(s: str) -> tuple[int, int]:
    c = FILES.index(s[0])
    r = int(s[1])
    return r, c


def parse_iccs(move: str) -> tuple[tuple[int, int], tuple[int, int]]:
    if len(move) != 4:
        raise ValueError(f"malformed ICCS move: {move!r}")
    return str_to_sq(move[0:2]), str_to_sq(move[2:4])


def format_iccs(src: tuple[int, int], dst: tuple[int, int]) -> str:
    return sq_to_str(*src) + sq_to_str(*dst)


def in_board(r: int, c: int) -> bool:
    return 0 <= r < 10 and 0 <= c < 9


def in_palace(r: int, c: int, color: str) -> bool:
    if not (3 <= c <= 5):
        return False
    return (0 <= r <= 2) if color == "r" else (7 <= r <= 9)


def on_own_side(r: int, color: str) -> bool:
    return r <= 4 if color == "r" else r >= 5


def piece_color(p: str) -> str:
    return "r" if p.isupper() else "b"


_HORSE_DELTAS = [
    ((2, 1), (1, 0)), ((2, -1), (1, 0)),
    ((-2, 1), (-1, 0)), ((-2, -1), (-1, 0)),
    ((1, 2), (0, 1)), ((-1, 2), (0, 1)),
    ((1, -2), (0, -1)), ((-1, -2), (0, -1)),
]
_ELEPHANT_DELTAS = [(2, 2), (2, -2), (-2, 2), (-2, -2)]
_ADVISOR_DELTAS = [(1, 1), (1, -1), (-1, 1), (-1, -1)]
_ORTHO_DELTAS = [(1, 0), (-1, 0), (0, 1), (0, -1)]


@dataclass
class XiangqiBoard:
    board: list = field(default_factory=list)
    turn: str = "r"          # 'r' (red, moves first) or 'b' (black)
    halfmove: int = 0
    fullmove: int = 1
    red_general: tuple = (0, 4)
    black_general: tuple = (9, 4)
    _history: list = field(default_factory=list)  # FEN placement strings, for repetition checks

    def __init__(self, fen: str | None = None):
        if fen is None:
            fen = STARTING_FEN
        self._load(fen)

    # -- construction / serialization -------------------------------------

    @classmethod
    def from_fen(cls, fen: str) -> "XiangqiBoard":
        return cls(fen)

    _PIECE_CHARS = set("RNBAKCPrnbakcp")

    def _load(self, fen: str) -> None:
        if not isinstance(fen, str) or not fen.strip():
            raise ValueError("FEN must be a non-empty string")

        parts = fen.split()
        if len(parts) < 2:
            raise ValueError(f"FEN must have at least placement and turn fields: {fen!r}")
        placement, turnchar = parts[0], parts[1]

        # -- validate placement structure BEFORE touching the board or the
        # halfmove/fullmove int fields, so malformed placements fail with a
        # clear, specific error instead of an IndexError or a confusing
        # int() parse failure further down.
        rows = placement.split("/")
        if len(rows) != 10:
            raise ValueError(f"FEN must have 10 ranks, got {len(rows)}: {placement!r}")

        parsed_rows = []  # list of (row, col, ch) placements, validated but not yet written
        king_count = 0
        general_count = 0
        for i, rowstr in enumerate(rows):
            row = 9 - i
            col = 0
            cells = []
            for ch in rowstr:
                if ch.isdigit():
                    col += int(ch)
                    if col > 9:
                        raise ValueError(f"FEN rank {rowstr!r} overflows 9 files")
                    continue
                if ch not in self._PIECE_CHARS:
                    raise ValueError(f"FEN rank {rowstr!r} contains invalid piece char {ch!r}")
                if col >= 9:
                    raise ValueError(f"FEN rank {rowstr!r} overflows 9 files")
                cells.append((row, col, ch))
                if ch == "K":
                    king_count += 1
                elif ch == "k":
                    general_count += 1
                col += 1
            if col != 9:
                raise ValueError(f"FEN rank {rowstr!r} does not sum to 9 files")
            parsed_rows.append(cells)

        if king_count != 1 or general_count != 1:
            raise ValueError(
                f"FEN must have exactly one 'K' and one 'k', got K={king_count} k={general_count}: {placement!r}"
            )

        if turnchar not in ("w", "b"):
            raise ValueError(f"FEN turn field must be 'w' or 'b', got {turnchar!r}")

        halfmove = 0
        fullmove = 1
        if len(parts) > 4:
            try:
                halfmove = int(parts[4])
            except ValueError:
                raise ValueError(f"FEN halfmove field must be an integer, got {parts[4]!r}") from None
        if len(parts) > 5:
            try:
                fullmove = int(parts[5])
            except ValueError:
                raise ValueError(f"FEN fullmove field must be an integer, got {parts[5]!r}") from None

        # Everything validated -- now it's safe to actually mutate state.
        self.board = [[None] * 9 for _ in range(10)]
        for cells in parsed_rows:
            for row, col, ch in cells:
                self.board[row][col] = ch
                if ch == "K":
                    self.red_general = (row, col)
                elif ch == "k":
                    self.black_general = (row, col)

        self.turn = "r" if turnchar == "w" else "b"
        self.halfmove = halfmove
        self.fullmove = fullmove
        self._history = [placement]

    def fen(self) -> str:
        rows = []
        for row in range(9, -1, -1):
            rowstr = ""
            empty = 0
            for col in range(9):
                p = self.board[row][col]
                if p is None:
                    empty += 1
                else:
                    if empty:
                        rowstr += str(empty)
                        empty = 0
                    rowstr += p
            if empty:
                rowstr += str(empty)
            rows.append(rowstr)
        placement = "/".join(rows)
        turnchar = "w" if self.turn == "r" else "b"
        return f"{placement} {turnchar} - - {self.halfmove} {self.fullmove}"

    def _placement(self) -> str:
        return self.fen().split()[0] + " " + ("w" if self.turn == "r" else "b")

    def __str__(self) -> str:
        lines = ["  " + " ".join(FILES)]
        for row in range(9, -1, -1):
            cells = [self.board[row][col] or "." for col in range(9)]
            lines.append(f"{row} " + " ".join(cells))
        return "\n".join(lines)

    # -- move generation ----------------------------------------------------

    def _slide_moves(self, r0, c0, color):
        moves = []
        for dr, dc in _ORTHO_DELTAS:
            r, c = r0 + dr, c0 + dc
            while in_board(r, c):
                p = self.board[r][c]
                if p is None:
                    moves.append((r, c))
                else:
                    if piece_color(p) != color:
                        moves.append((r, c))
                    break
                r += dr
                c += dc
        return moves

    def _cannon_moves(self, r0, c0, color):
        moves = []
        for dr, dc in _ORTHO_DELTAS:
            r, c = r0 + dr, c0 + dc
            screen = False
            while in_board(r, c):
                p = self.board[r][c]
                if not screen:
                    if p is None:
                        moves.append((r, c))
                    else:
                        screen = True
                else:
                    if p is not None:
                        if piece_color(p) != color:
                            moves.append((r, c))
                        break
                r += dr
                c += dc
        return moves

    def _horse_moves(self, r0, c0, color):
        moves = []
        for (dr, dc), (ldr, ldc) in _HORSE_DELTAS:
            leg_r, leg_c = r0 + ldr, c0 + ldc
            if not in_board(leg_r, leg_c) or self.board[leg_r][leg_c] is not None:
                continue
            r, c = r0 + dr, c0 + dc
            if in_board(r, c):
                p = self.board[r][c]
                if p is None or piece_color(p) != color:
                    moves.append((r, c))
        return moves

    def _elephant_moves(self, r0, c0, color):
        moves = []
        for dr, dc in _ELEPHANT_DELTAS:
            r, c = r0 + dr, c0 + dc
            if not (in_board(r, c) and on_own_side(r, color)):
                continue
            eye_r, eye_c = r0 + dr // 2, c0 + dc // 2
            if self.board[eye_r][eye_c] is not None:
                continue
            p = self.board[r][c]
            if p is None or piece_color(p) != color:
                moves.append((r, c))
        return moves

    def _advisor_moves(self, r0, c0, color):
        moves = []
        for dr, dc in _ADVISOR_DELTAS:
            r, c = r0 + dr, c0 + dc
            if in_palace(r, c, color):
                p = self.board[r][c]
                if p is None or piece_color(p) != color:
                    moves.append((r, c))
        return moves

    def _general_moves(self, r0, c0, color):
        moves = []
        for dr, dc in _ORTHO_DELTAS:
            r, c = r0 + dr, c0 + dc
            if in_palace(r, c, color):
                p = self.board[r][c]
                if p is None or piece_color(p) != color:
                    moves.append((r, c))
        return moves

    def _soldier_moves(self, r0, c0, color):
        moves = []
        if color == "r":
            fwd = (r0 + 1, c0)
            crossed = r0 >= 5
        else:
            fwd = (r0 - 1, c0)
            crossed = r0 <= 4
        candidates = [fwd]
        if crossed:
            candidates.append((r0, c0 - 1))
            candidates.append((r0, c0 + 1))
        for r, c in candidates:
            if in_board(r, c):
                p = self.board[r][c]
                if p is None or piece_color(p) != color:
                    moves.append((r, c))
        return moves

    def _pseudo_moves(self, color):
        out = []
        for r in range(10):
            for c in range(9):
                p = self.board[r][c]
                if p is None or piece_color(p) != color:
                    continue
                kind = p.upper()
                if kind == "R":
                    dests = self._slide_moves(r, c, color)
                elif kind == "C":
                    dests = self._cannon_moves(r, c, color)
                elif kind == "N":
                    dests = self._horse_moves(r, c, color)
                elif kind == "B":
                    dests = self._elephant_moves(r, c, color)
                elif kind == "A":
                    dests = self._advisor_moves(r, c, color)
                elif kind == "K":
                    dests = self._general_moves(r, c, color)
                elif kind == "P":
                    dests = self._soldier_moves(r, c, color)
                else:
                    dests = []
                for r1, c1 in dests:
                    out.append((r, c, r1, c1))
        return out

    # -- attack detection -----------------------------------------------

    def is_square_attacked(self, r: int, c: int, by_color: str) -> bool:
        board = self.board
        # Sliding orthogonal rays: chariot / general(adjacent) / cannon(screen)
        for dr, dc in _ORTHO_DELTAS:
            rr, cc = r + dr, c + dc
            dist = 0
            first = None
            while in_board(rr, cc):
                p = board[rr][cc]
                if p is not None:
                    dist += 1
                    if dist == 1:
                        first = (rr, cc, p)
                    else:
                        if piece_color(p) == by_color and p.upper() == "C":
                            return True
                        break
                rr += dr
                cc += dc
            if first is not None:
                fr, fc, fp = first
                if piece_color(fp) == by_color:
                    if fp.upper() == "R":
                        return True
                    if fp.upper() == "K" and abs(fr - r) + abs(fc - c) == 1:
                        return True
        # Horse
        for (dr, dc), (ldr, ldc) in _HORSE_DELTAS:
            hr, hc = r - dr, c - dc
            if not in_board(hr, hc):
                continue
            p = board[hr][hc]
            if p is None or piece_color(p) != by_color or p.upper() != "N":
                continue
            leg_r, leg_c = hr + ldr, hc + ldc
            if in_board(leg_r, leg_c) and board[leg_r][leg_c] is None:
                return True
        # Elephant
        if on_own_side(r, by_color):
            for dr, dc in _ELEPHANT_DELTAS:
                er, ec = r + dr, c + dc
                if not in_board(er, ec):
                    continue
                p = board[er][ec]
                if p is None or piece_color(p) != by_color or p.upper() != "B":
                    continue
                eye_r, eye_c = r + dr // 2, c + dc // 2
                if board[eye_r][eye_c] is None:
                    return True
        # Advisor
        if in_palace(r, c, by_color):
            for dr, dc in _ADVISOR_DELTAS:
                ar, ac = r + dr, c + dc
                if in_board(ar, ac):
                    p = board[ar][ac]
                    if p is not None and piece_color(p) == by_color and p.upper() == "A":
                        return True
        # Soldier
        if by_color == "r":
            src = (r - 1, c)
            side_valid = r >= 5
        else:
            src = (r + 1, c)
            side_valid = r <= 4
        if in_board(*src):
            p = board[src[0]][src[1]]
            if p is not None and piece_color(p) == by_color and p.upper() == "P":
                return True
        if side_valid:
            for sc in (c - 1, c + 1):
                if in_board(r, sc):
                    p = board[r][sc]
                    if p is not None and piece_color(p) == by_color and p.upper() == "P":
                        return True
        return False

    def kings_facing(self) -> bool:
        rg, bg = self.red_general, self.black_general
        if rg[1] != bg[1]:
            return False
        col = rg[1]
        lo, hi = sorted((rg[0], bg[0]))
        for row in range(lo + 1, hi):
            if self.board[row][col] is not None:
                return False
        return True

    # -- make/undo (internal, board-mutating) ----------------------------

    def _make_move(self, r0, c0, r1, c1):
        # Note: this assumes the caller has already excluded general-capture
        # destinations (legal_moves() filters those out before ever calling
        # this). It is not itself a legality check -- it's a raw board
        # mutation used both by legal_moves()'s own safety-testing loop and
        # by perft/push on already-filtered moves.
        piece = self.board[r0][c0]
        captured = self.board[r1][c1]
        self.board[r1][c1] = piece
        self.board[r0][c0] = None
        if piece == "K":
            self.red_general = (r1, c1)
        elif piece == "k":
            self.black_general = (r1, c1)
        return captured

    def _undo_move(self, r0, c0, r1, c1, captured):
        piece = self.board[r1][c1]
        self.board[r0][c0] = piece
        self.board[r1][c1] = captured
        if piece == "K":
            self.red_general = (r0, c0)
        elif piece == "k":
            self.black_general = (r0, c0)

    # -- public API --------------------------------------------------------

    def legal_moves(self, color: str | None = None) -> list:
        color = color or self.turn
        opp = "b" if color == "r" else "r"
        opp_general = self.black_general if color == "r" else self.red_general
        legal = []
        for r0, c0, r1, c1 in self._pseudo_moves(color):
            if (r1, c1) == opp_general:
                # A loadable position can legitimately have a general en
                # prise (analysis/puzzle input, or simply "about to be
                # checkmated") -- exclude the capture from the move list
                # rather than ever handing it to _make_move, so a general
                # sitting in check doesn't crash move generation for
                # unrelated moves (or perft, or push()).
                continue
            captured = self._make_move(r0, c0, r1, c1)
            general = self.red_general if color == "r" else self.black_general
            if not self.is_square_attacked(general[0], general[1], opp) and not self.kings_facing():
                legal.append(format_iccs((r0, c0), (r1, c1)))
            self._undo_move(r0, c0, r1, c1, captured)
        return legal

    def is_check(self, color: str | None = None) -> bool:
        color = color or self.turn
        opp = "b" if color == "r" else "r"
        general = self.red_general if color == "r" else self.black_general
        return self.is_square_attacked(general[0], general[1], opp) or self.kings_facing()

    def is_checkmate(self) -> bool:
        return self.is_check() and not self.legal_moves()

    def is_stalemate(self) -> bool:
        """Xiangqi rule: being stalemated is a LOSS for the stalemated side
        (unlike chess, where it's a draw). This method only reports the
        board condition (no legal moves and not in check); the caller is
        responsible for scoring it as a loss rather than a draw."""
        return not self.is_check() and not self.legal_moves()

    def is_repetition(self, count: int = 3) -> bool:
        """Best-effort threefold repetition of (placement, turn). Does NOT
        implement xiangqi's perpetual-check/perpetual-chase adjudication
        rules (see module docstring) -- those require tracking whether
        checks/chases are being repeated by the same side and are out of
        scope for this engine."""
        key = self._placement()
        return self._history.count(key) >= count

    def push(self, iccs: str) -> None:
        legal = self.legal_moves()
        if iccs not in legal:
            raise IllegalMove(f"{iccs!r} is not a legal move in position {self.fen()}")
        (r0, c0), (r1, c1) = parse_iccs(iccs)
        captured = self._make_move(r0, c0, r1, c1)
        self.halfmove = 0 if captured else self.halfmove + 1
        if self.turn == "b":
            self.fullmove += 1
        self.turn = "b" if self.turn == "r" else "r"
        self._history.append(self._placement())

    def copy(self) -> "XiangqiBoard":
        new = XiangqiBoard.__new__(XiangqiBoard)
        new.board = [row[:] for row in self.board]
        new.turn = self.turn
        new.halfmove = self.halfmove
        new.fullmove = self.fullmove
        new.red_general = self.red_general
        new.black_general = self.black_general
        new._history = list(self._history)
        return new


def perft(board: XiangqiBoard, depth: int) -> int:
    """Count leaf nodes at `depth` plies from the current position."""
    if depth == 0:
        return 1
    moves = board.legal_moves()
    if depth == 1:
        return len(moves)
    total = 0
    for m in moves:
        (r0, c0), (r1, c1) = parse_iccs(m)
        captured = board._make_move(r0, c0, r1, c1)
        board.turn = "b" if board.turn == "r" else "r"
        total += perft(board, depth - 1)
        board.turn = "b" if board.turn == "r" else "r"
        board._undo_move(r0, c0, r1, c1, captured)
    return total

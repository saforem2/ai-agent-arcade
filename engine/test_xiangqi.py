"""Tests for xiangqi.py. Run with: uv run --with pytest pytest test_xiangqi.py"""

import pytest

from xiangqi import XiangqiBoard, IllegalMove, perft, STARTING_FEN


# ---------------------------------------------------------------------------
# Perft (published node counts from the starting position)
# ---------------------------------------------------------------------------

PERFT_EXPECTED = {1: 44, 2: 1920, 3: 79666}
PERFT_EXPECTED_SLOW = {4: 3290240}


@pytest.mark.parametrize("depth,expected", sorted(PERFT_EXPECTED.items()))
def test_perft(depth, expected):
    b = XiangqiBoard()
    assert perft(b, depth) == expected


@pytest.mark.parametrize("depth,expected", sorted(PERFT_EXPECTED_SLOW.items()))
def test_perft_depth4(depth, expected):
    b = XiangqiBoard()
    assert perft(b, depth) == expected


# ---------------------------------------------------------------------------
# FEN round-trip
# ---------------------------------------------------------------------------

def test_fen_roundtrip_starting_position():
    b = XiangqiBoard()
    assert b.fen() == STARTING_FEN


def test_fen_roundtrip_after_moves():
    b = XiangqiBoard()
    for m in ("h2e2", "h9g7", "e2e6"):
        b.push(m)
    fen = b.fen()
    b2 = XiangqiBoard.from_fen(fen)
    assert b2.fen() == fen
    assert b2.board == b.board
    assert b2.turn == b.turn


def test_fen_custom_position():
    fen = "4k4/9/9/9/9/9/5n3/9/4r4/3PKP3 w - - 0 1"
    b = XiangqiBoard.from_fen(fen)
    assert b.fen() == fen


# ---------------------------------------------------------------------------
# FEN input validation (hostile/corrupt input from disk is in-scope: a
# referee feeds this engine FENs it did not generate itself, so from_fen
# must fail loudly and specifically rather than raising a raw IndexError,
# a confusing int() ValueError, or silently accepting garbage).
# ---------------------------------------------------------------------------

def test_fen_missing_general_raises():
    # Only a red general on the board -- the phantom-general bug this guards
    # against: without this check, is_check("b") would spuriously come back
    # True via a phantom black general defaulted to (9, 4).
    with pytest.raises(ValueError):
        XiangqiBoard.from_fen("9/9/9/9/9/9/9/9/9/4K4 w - - 0 1")


def test_fen_missing_both_generals_raises():
    with pytest.raises(ValueError):
        XiangqiBoard.from_fen("9/9/9/9/9/9/9/9/9/9 w - - 0 1")


def test_fen_duplicate_general_raises():
    with pytest.raises(ValueError):
        XiangqiBoard.from_fen("4k4/9/9/9/9/9/9/9/4K4/4K4 w - - 0 1")


def test_fen_invalid_piece_char_raises():
    # 'X' is not a valid xiangqi piece letter -- must not become a silent
    # inert ghost piece sitting on the board.
    with pytest.raises(ValueError):
        XiangqiBoard.from_fen("4k4/9/9/9/9/9/9/9/4X4/4K4 w - - 0 1")


def test_fen_rank_overflow_raises_valueerror_not_indexerror():
    # A rank that sums to more than 9 files must be rejected before any
    # board-array write is attempted (previously a raw IndexError).
    with pytest.raises(ValueError):
        XiangqiBoard.from_fen("4k4/9/9/9/9/9/9/9/9R9/RNBAKABNR w - - 0 1")


def test_fen_garbage_string_raises_before_int_parsing():
    # Completely malformed input must fail on placement-structure
    # validation, not surface a bare "invalid literal for int()" from deep
    # inside halfmove/fullmove parsing.
    with pytest.raises(ValueError):
        XiangqiBoard.from_fen("not a fen at all")


def test_fen_bad_turn_char_raises():
    with pytest.raises(ValueError):
        XiangqiBoard.from_fen(
            "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR X - - 0 1"
        )


def test_fen_bad_halfmove_field_raises():
    with pytest.raises(ValueError):
        XiangqiBoard.from_fen(
            "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - abc 1"
        )


def test_fen_empty_string_raises_not_starting_position():
    # An empty FEN must error, never silently fall back to the starting
    # position -- that fallback is only for fen=None (the no-arg constructor).
    with pytest.raises(ValueError):
        XiangqiBoard.from_fen("")
    with pytest.raises(ValueError):
        XiangqiBoard("")


def test_no_arg_constructor_still_gives_starting_position():
    b = XiangqiBoard()
    assert b.fen() == STARTING_FEN
    b2 = XiangqiBoard(None)
    assert b2.fen() == STARTING_FEN


# ---------------------------------------------------------------------------
# Piece-specific unit tests
# ---------------------------------------------------------------------------

def test_horse_leg_block():
    # Horse at e0 (0,4); a piece directly in front (leg) at e1 blocks ALL
    # horse jumps in that direction (d2/f2), but jumps whose leg is on the
    # other axis (c1/g1 direction) remain legal.
    # Red K at a0, black k at i9, both off the tested file so they never
    # spuriously "face" each other as the tested piece moves around.
    b = XiangqiBoard.from_fen("8k/9/9/9/9/9/9/9/4P4/K3N4 w - - 0 1")
    moves = b.legal_moves()
    dests = {m[2:4] for m in moves if m.startswith("e0")}
    assert "d2" not in dests and "f2" not in dests
    assert "c1" in dests and "g1" in dests


def test_horse_no_block_full_mobility():
    b = XiangqiBoard.from_fen("8k/9/9/9/4N4/9/9/9/9/K8 w - - 0 1")
    dests = {m[2:4] for m in b.legal_moves() if m.startswith("e5")}
    # a horse in the open middle of the board has 8 destinations
    assert len(dests) == 8


def test_elephant_eye_block():
    # elephant at c0; the d1 eye is blocked by an own pawn, so only the
    # a2 diagonal (eye b1, unobstructed) remains.
    b = XiangqiBoard.from_fen("k8/9/9/9/9/9/9/9/3P5/2B5K w - - 0 1")
    dests = {m[2:4] for m in b.legal_moves() if m.startswith("c0")}
    assert "e2" not in dests  # blocked by own pawn on the eye square d1
    assert "a2" in dests      # other diagonal unobstructed


def test_elephant_cannot_cross_river():
    # elephant at c3 (row3, red side); e5 would cross into black territory (row5)
    b = XiangqiBoard.from_fen("k8/9/9/9/9/9/2B6/9/9/8K w - - 0 1")
    dests = {m[2:4] for m in b.legal_moves() if m.startswith("c3")}
    assert "e5" not in dests
    assert "a1" in dests and "e1" in dests


def test_cannon_needs_screen_to_capture():
    # cannon at e0, enemy soldier directly at e5 with clear path -> cannot capture (no screen)
    b = XiangqiBoard.from_fen("k8/9/9/9/4p4/9/9/9/9/4C3K w - - 0 1")
    moves = b.legal_moves()
    assert "e0e5" not in moves
    # but it CAN slide (non-capturing) up to e4, right below the target
    assert "e0e4" in moves


def test_cannon_captures_over_single_screen():
    # cannon at e0, own soldier screen at e2, enemy soldier at e5 -> capture legal
    b = XiangqiBoard.from_fen("k8/9/9/9/4p4/9/4P4/9/9/4C3K w - - 0 1")
    moves = b.legal_moves()
    assert "e0e5" in moves
    # cannot land on the empty square just behind the screen without capturing
    assert "e0e3" not in moves
    # and cannot slide past its own screen without jumping
    assert "e0e1" in moves  # e1 still before the screen, fine


def test_flying_general_illegal():
    # Two bare generals facing each other on an open file: illegal for the
    # side to move to create/maintain this (no legal moves at all here since
    # any king move keeps it on the palace but the position itself is a
    # "both-attack" state) -- more directly: moving into a facing position
    # must be rejected even when the destination square itself looks safe.
    b = XiangqiBoard.from_fen("4k4/9/9/9/9/9/9/9/9/3K1A3 w - - 0 1")
    # King at d0 stepping sideways to e0 would face the black general on the
    # open e-file -- must be excluded from legal moves.
    assert "d0e0" not in b.legal_moves()


def test_flying_general_blocked_is_fine():
    b = XiangqiBoard.from_fen("4k4/9/9/9/9/4p4/9/9/9/4K4 w - - 0 1")
    assert not b.kings_facing()
    b2 = XiangqiBoard.from_fen("4k4/9/9/9/9/9/9/9/9/4K4 w - - 0 1")
    assert b2.kings_facing()
    assert b2.is_check()  # bare open-file facing counts as check on the side to move


def test_palace_confinement_general():
    b = XiangqiBoard.from_fen("k8/9/9/9/9/9/9/9/9/3K5 w - - 0 1")
    dests = {m[2:4] for m in b.legal_moves() if m.startswith("d0")}
    assert dests == {"e0", "d1"}  # c0 is outside the palace


def test_palace_confinement_advisor():
    b = XiangqiBoard.from_fen("k8/9/9/9/9/9/9/9/9/3A1K3 w - - 0 1")
    dests = {m[2:4] for m in b.legal_moves() if m.startswith("d0")}
    assert dests == {"e1"}  # c1 would leave the palace


def test_soldier_pre_river_forward_only():
    b = XiangqiBoard.from_fen("8k/9/9/9/9/9/4P4/9/9/K8 w - - 0 1")
    dests = {m[2:4] for m in b.legal_moves() if m.startswith("e3")}
    assert dests == {"e4"}


def test_soldier_post_river_sideways_and_forward_no_backward():
    b = XiangqiBoard.from_fen("8k/9/9/9/4P4/9/9/9/9/K8 w - - 0 1")
    dests = {m[2:4] for m in b.legal_moves() if m.startswith("e5")}
    assert dests == {"e6", "d5", "f5"}
    assert "e4" not in dests  # never moves backward


def test_black_soldier_direction_mirrors_red():
    b = XiangqiBoard.from_fen("8k/9/9/9/9/4p4/9/9/9/K8 b - - 0 1")
    dests = {m[2:4] for m in b.legal_moves() if m.startswith("e4")}
    assert dests == {"e3", "d4", "f4"}


# ---------------------------------------------------------------------------
# Check / checkmate / stalemate
# ---------------------------------------------------------------------------

def test_checkmate_position():
    b = XiangqiBoard.from_fen("4k4/9/9/9/9/9/5n3/9/4r4/3PKP3 w - - 0 1")
    assert b.is_check()
    assert b.is_checkmate()
    assert not b.is_stalemate()
    assert b.legal_moves() == []
    with pytest.raises(IllegalMove):
        b.push("e0e1")  # capturing walks into the horse's attack


def test_stalemate_position():
    b = XiangqiBoard.from_fen("4k4/9/9/9/4r4/9/2n6/9/9/3K5 w - - 0 1")
    assert not b.is_check()
    assert b.is_stalemate()
    assert not b.is_checkmate()
    assert b.legal_moves() == []


def test_not_check_in_starting_position():
    b = XiangqiBoard()
    assert not b.is_check()
    assert not b.is_checkmate()
    assert not b.is_stalemate()


# ---------------------------------------------------------------------------
# General en prise (loadable analysis/puzzle input, or simply "one move from
# checkmate"): legal_moves() must exclude the capture itself but must NOT
# raise or otherwise disrupt move generation for the rest of the board.
# push() rejects the capture naturally via the not-in-legal_moves() path.
# ---------------------------------------------------------------------------

GENERAL_EN_PRISE_FEN = "4k4/9/9/9/9/9/9/9/9/4R3K w - - 0 1"  # red rook on e0 has a clear file straight to black's general on e9


def test_general_en_prise_excluded_from_legal_moves_without_raising():
    b = XiangqiBoard.from_fen(GENERAL_EN_PRISE_FEN)
    moves = b.legal_moves("r")  # must not raise
    assert "e0e9" not in moves
    # the rook still has plenty of other legal moves along the file/rank
    assert "e0e8" in moves
    assert "e0d0" in moves


def test_push_rejects_general_capture_via_legal_moves_membership():
    b = XiangqiBoard.from_fen(GENERAL_EN_PRISE_FEN)
    with pytest.raises(IllegalMove):
        b.push("e0e9")


def test_push_unrelated_move_still_works_when_a_general_is_en_prise():
    b = XiangqiBoard.from_fen(GENERAL_EN_PRISE_FEN)
    b.push("e0d0")  # unrelated rook sidestep -- must succeed, not crash
    assert b.turn == "b"
    assert b.board[0][3] == "R"
    assert b.board[0][4] is None


def test_perft_depth1_on_general_en_prise_position_does_not_crash():
    b = XiangqiBoard.from_fen(GENERAL_EN_PRISE_FEN)
    n = perft(b, 1)
    assert n == len(b.legal_moves("r"))
    assert n > 0


# ---------------------------------------------------------------------------
# push() / IllegalMove / turn bookkeeping
# ---------------------------------------------------------------------------

def test_push_updates_turn_and_counters():
    b = XiangqiBoard()
    assert b.turn == "r"
    b.push("h2e2")  # red cannon slides
    assert b.turn == "b"
    assert b.fullmove == 1
    b.push("h9g7")  # black horse develops
    assert b.turn == "r"
    assert b.fullmove == 2


def test_push_rejects_illegal_move():
    b = XiangqiBoard()
    with pytest.raises(IllegalMove):
        b.push("a0a5")  # chariot can't jump over its own soldier


def test_push_rejects_move_leaving_own_general_in_check():
    # red chariot on e1 is pinned: it's the only thing blocking the black
    # chariot on e9 from checking the red general on e0.
    b = XiangqiBoard.from_fen("3kr4/9/9/9/9/9/9/9/4R4/4K4 w - - 0 1")
    assert "e1d1" not in b.legal_moves()  # would expose the general to check
    with pytest.raises(IllegalMove):
        b.push("e1d1")
    assert "e1e5" in b.legal_moves()  # staying on the file is fine

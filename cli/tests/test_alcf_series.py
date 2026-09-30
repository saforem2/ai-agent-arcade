import importlib.util
from pathlib import Path

import chess

MODULE_PATH = Path(__file__).resolve().parents[1] / "run_alcf_series.py"
spec = importlib.util.spec_from_file_location("run_alcf_series", MODULE_PATH)
series = importlib.util.module_from_spec(spec)
spec.loader.exec_module(series)


def test_terminal_result_recognizes_claimable_threefold_draw():
    board = chess.Board()
    for san in "Nf3 Nf6 Ng1 Ng8 Nf3 Nf6 Ng1 Ng8".split():
        board.push_san(san)

    assert not board.is_game_over()
    assert board.can_claim_threefold_repetition()
    assert series.terminal_result(board) == ("1/2-1/2", "threefold repetition")


def test_terminal_result_uses_native_checkmate():
    board = chess.Board()
    for san in "f3 e5 g4 Qh4#".split():
        board.push_san(san)

    assert series.terminal_result(board) == ("0-1", "checkmate")

"""Testes para o tabuleiro 4x4 e para o modo de 1 unico braco."""

import chess
import pytest

from xadrez_robotico.chess import BoardState, MiniBoard, MiniMove, choose_move
from xadrez_robotico.game import Match, plan_actions
from xadrez_robotico.robot.kinematics import BoardToRobot
from xadrez_robotico.vision.calibration import Calibration


# -- MiniBoard ---------------------------------------------------------------


def test_mini_start_position():
    board = MiniBoard()
    assert board.turn == chess.WHITE
    assert len(board.piece_map()) == 16
    moves = board.legal_moves
    assert moves
    for m in moves:
        for sq in (m.from_sq, m.to_sq):
            assert 0 <= chess.square_file(sq) < 4
            assert 0 <= chess.square_rank(sq) < 4


def test_mini_piece_map_names():
    board = MiniBoard()
    pm = board.piece_map()
    assert pm[chess.parse_square("a1")].symbol() == "R"
    assert pm[chess.parse_square("d1")].symbol() == "K"
    assert pm[chess.parse_square("a2")].symbol() == "P"
    assert pm[chess.parse_square("d4")].symbol() == "k"


def test_mini_checkmate():
    board = MiniBoard.from_symbols({"a1": "K", "a2": "r", "b2": "k"}, turn=chess.WHITE)
    assert board.is_checkmate()
    assert not board.legal_moves
    assert board.result() == "0-1"


def test_mini_stalemate():
    board = MiniBoard.from_symbols({"a1": "K", "b2": "r", "c3": "k"}, turn=chess.WHITE)
    assert board.is_stalemate()
    assert board.result() == "1/2-1/2"


def test_mini_insufficient_material():
    board = MiniBoard.from_symbols({"a1": "K", "d4": "k"})
    assert board.is_insufficient_material()
    assert board.is_game_over()


def test_mini_repetition_draw():
    board = MiniBoard.from_symbols({"a1": "K", "b1": "R", "d4": "k", "c4": "r"})
    seq = ["b1b2", "c4c3", "b2b1", "c3c4"]
    for _ in range(2):
        for m in seq:
            board.push(MiniMove.from_uci(m))
    assert board.is_repetition(3)
    assert board.is_game_over()
    assert board.result() == "1/2-1/2"


def test_mini_fifty_moves():
    board = MiniBoard.from_symbols({"a1": "K", "b1": "R", "d4": "k", "c4": "r"})
    for _ in range(50):
        for m in ["b1b2", "c4c3", "b2b1", "c3c4"]:
            board.push(MiniMove.from_uci(m))
    assert board.is_fifty_moves()
    assert board.is_game_over()


def test_mini_promotion():
    board = MiniBoard.from_symbols({"a1": "K", "b4": "k", "d3": "P"}, turn=chess.WHITE)
    promos = [m for m in board.legal_moves if m.promotion]
    assert {m.promotion for m in promos} == {"q", "r", "b", "n"}
    board.push(MiniMove.from_uci("d3d4q"))
    assert board.piece_at(chess.parse_square("d4")).piece_type == chess.QUEEN


def test_mini_san_and_uci():
    board = MiniBoard()
    # No inicio, as pecas ficam frente a frente: a2xb3 e uma captura legal.
    move = MiniMove.from_uci("a2b3")
    assert move.uci() == "a2b3"
    assert board.san(move) == "axb3"


# -- Motor 4x4 ---------------------------------------------------------------


def test_choose_move_4x4():
    state = BoardState(size=4)
    move = choose_move(state, backend="minimax", minimax_depth=2)
    assert move is not None
    assert state.is_legal(move)


# -- plan_actions em 4x4 -----------------------------------------------------


def test_plan_actions_4x4_simple():
    actions = plan_actions({"a2": "P"}, {"a3": "P"})
    assert actions == [("move", "white", "a2", "a3")]


def test_plan_actions_4x4_capture():
    prev = {"c2": "P", "d3": "p"}
    new = {"d3": "P"}
    actions = plan_actions(prev, new)
    moves = [a for a in actions if a[0] == "move"]
    captures = [a for a in actions if a[0] == "capture"]
    assert ("move", "white", "c2", "d3") in moves
    assert ("capture", "black", "d3", None) in captures
    # captura vem antes do movimento
    assert actions[0][0] == "capture"


# -- Cinematica 4x4 ----------------------------------------------------------


def test_kinematics_4x4():
    kin = BoardToRobot(origin_x=100.0, origin_y=-100.0, spacing=45.0, size=4)
    assert kin.to_xy("a1") == (100.0, -100.0)
    assert kin.to_xy("d1") == (235.0, -100.0)
    assert kin.to_xy("d4") == (235.0, 35.0)
    with pytest.raises(ValueError):
        kin.to_xy("e1")


# -- Calibracao 4x4 ----------------------------------------------------------


def test_calibration_4x4():
    calib = Calibration.build_from_corners((0.0, 0.0), (0.0, 300.0), (300.0, 0.0), (300.0, 300.0), size=4)
    assert len(calib.square_centers) == 16
    assert calib.center("a1") == (0.0, 0.0)
    assert calib.center("d4") == (300.0, 300.0)


# -- Braco unico -------------------------------------------------------------


def test_single_arm_routes_both_colors():
    cfg = {
        "mode": "hardware",
        "board": {"squares": 4},
        "arms": {"white": {"enabled": True}},
        "match": {},
    }
    m = Match(cfg)
    m.arms = {"white": object()}
    assert m._arm_for("white") is not None
    assert m._arm_for("black") is m._arm_for("white")

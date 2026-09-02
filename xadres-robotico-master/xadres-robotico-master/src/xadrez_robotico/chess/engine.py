"""Motor de xadrez / I.A. para escolha de lances.

Tenta usar o Stockfish (via python-chess) quando disponivel; caso contrario
cai para um motor minimax com avaliacao material + tabelas de posicao.
"""

from __future__ import annotations

import logging
import shutil
from typing import Callable

import chess
from chess import Board, Move
from chess.engine import SimpleEngine

from .board_state import BoardState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Avaliacao (usada pelo fallback minimax)
# ---------------------------------------------------------------------------

_PIECE_VALUE = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20000,
}

_PAWN_PST = [
    0, 0, 0, 0, 0, 0, 0, 0,
    5, 10, 10, -20, -20, 10, 10, 5,
    5, -5, -10, 0, 0, -10, -5, 5,
    0, 0, 0, 20, 20, 0, 0, 0,
    5, 5, 10, 25, 25, 10, 5, 5,
    10, 10, 20, 30, 30, 20, 10, 10,
    50, 50, 50, 50, 50, 50, 50, 50,
    0, 0, 0, 0, 0, 0, 0, 0,
]

_KNIGHT_PST = [
    -50, -40, -30, -30, -30, -30, -40, -50,
    -40, -20, 0, 5, 5, 0, -20, -40,
    -30, 5, 10, 15, 15, 10, 5, -30,
    -30, 0, 15, 20, 20, 15, 0, -30,
    -30, 5, 15, 20, 20, 15, 5, -30,
    -30, 0, 10, 15, 15, 10, 0, -30,
    -40, -20, 0, 0, 0, 0, -20, -40,
    -50, -40, -30, -30, -30, -30, -40, -50,
]


def _evaluate(board: Board) -> float:
    """Avaliacao do tabuleiro do ponto de vista do jogador das brancas."""
    if board.is_checkmate():
        return -100000 if board.turn == chess.WHITE else 100000
    if board.is_stalemate() or board.is_insufficient_material():
        return 0.0
    if board.is_repetition(3) or board.is_fifty_moves():
        return 0.0

    # Tabelas de posicao (PST) so existem para o tabuleiro 8x8; no 4x4 usa
    # bonus de avanco de peao (incentiva promocao e evita avaliacao "plana").
    size = getattr(board, "board_size", 8)
    use_pst = size == 8

    score = 0.0
    for square, piece in board.piece_map().items():
        value = _PIECE_VALUE[piece.piece_type]
        pst = 0
        if use_pst:
            if piece.piece_type == chess.PAWN:
                pst = _PAWN_PST[square]
            elif piece.piece_type == chess.KNIGHT:
                pst = _KNIGHT_PST[square]
        elif size == 4 and piece.piece_type == chess.PAWN:
            rank = chess.square_rank(square)
            adv = rank if piece.color == chess.WHITE else (3 - rank)
            pst = adv * 15
        if piece.color == chess.WHITE:
            score += value + pst
        else:
            if use_pst:
                mirrored = chess.square_mirror(square)
                if piece.piece_type == chess.PAWN:
                    pst = _PAWN_PST[mirrored]
                elif piece.piece_type == chess.KNIGHT:
                    pst = _KNIGHT_PST[mirrored]
            score -= value + pst
    return float(score)


# ---------------------------------------------------------------------------
# Minimax (negamax) com poda alfa-beta
# ---------------------------------------------------------------------------


def _negamax(board: Board, depth: int, alpha: float, beta: float, color: int) -> float:
    if board.is_game_over():
        val = _evaluate(board)
        return val * color
    if depth == 0:
        return _evaluate(board) * color

    best = -float("inf")
    for move in board.legal_moves:
        board.push(move)
        val = _negamax(board, depth - 1, -beta, -alpha, -color)
        board.pop()
        if val > best:
            best = val
        if best > alpha:
            alpha = best
        if alpha >= beta:
            break
    return best


def _choose_minimax(board: Board, depth: int) -> Move | None:
    best_move: Move | None = None
    best_val = -float("inf")
    alpha = -float("inf")
    beta = float("inf")
    color = 1 if board.turn == chess.WHITE else -1
    for move in board.legal_moves:
        board.push(move)
        val = _negamax(board, depth - 1, -beta, -alpha, -color)
        board.pop()
        if val > best_val:
            best_val = val
            best_move = move
        if val > alpha:
            alpha = val
    return best_move


# ---------------------------------------------------------------------------
# Stockfish
# ---------------------------------------------------------------------------


def _find_stockfish(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    candidate = shutil.which("stockfish")
    return candidate


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------


def choose_move(
    state: BoardState,
    *,
    backend: str = "auto",
    stockfish_path: str | None = None,
    think_time: float = 1.0,
    minimax_depth: int = 3,
    rng: Callable[[], float] | None = None,
) -> Move | None:
    """Escolhe o melhor lance para o jogador da vez.

    Retorna None se nao houver lances legais (xeque-mate/empate).
    """
    board = state.board
    if board.is_game_over():
        return None

    # Stockfish so joga xadrez 8x8; em tabuleiros reduzidos (4x4) usa minimax.
    size = getattr(board, "board_size", 8)
    use_stockfish = False
    if size == 8 and backend in ("auto", "stockfish"):
        path = _find_stockfish(stockfish_path)
        if path:
            use_stockfish = True
        elif backend == "stockfish":
            logger.warning("Stockfish solicitado mas nao encontrado; usando minimax.")

    if use_stockfish:
        try:
            with SimpleEngine.popen_uci(path) as engine:  # type: ignore[arg-type]
                result = engine.play(board, chess.engine.Limit(time=think_time))
                if result.move is None:
                    return _choose_minimax(board, minimax_depth)
                return result.move
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao usar Stockfish (%s); usando minimax.", exc)

    return _choose_minimax(board, max(1, minimax_depth))

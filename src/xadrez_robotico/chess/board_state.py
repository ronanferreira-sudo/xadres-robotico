"""Estado do tabuleiro de xadrez baseado em python-chess."""

from __future__ import annotations

import chess
from chess import Board, Color, Move


class BoardState:
    """Wrapper sobre ``chess.Board`` com helpers para o orquestrador."""

    def __init__(self, fen: str | None = None) -> None:
        self.board = Board(fen) if fen else Board()

    @property
    def turn(self) -> Color:
        return self.board.turn

    @property
    def turn_name(self) -> str:
        return "white" if self.board.turn == chess.WHITE else "black"

    def legal_moves(self) -> list[Move]:
        return list(self.board.legal_moves)

    def is_legal(self, move: Move) -> bool:
        return move in self.board.legal_moves

    def san(self, move: Move) -> str:
        return self.board.san(move)

    def apply(self, move: Move) -> None:
        """Aplica um lance (assume que ja foi validado)."""
        self.board.push(move)

    def fen(self) -> str:
        return self.board.fen()

    def is_game_over(self) -> bool:
        return self.board.is_game_over()

    def outcome(self) -> str:
        """Retorna 'white', 'black', 'draw' ou '' se a partida nao acabou."""
        if not self.board.is_game_over():
            return ""
        result = self.board.result()
        if result == "1-0":
            return "white"
        if result == "0-1":
            return "black"
        return "draw"

    def piece_map(self) -> dict[str, str]:
        """Mapa square -> peca (ex.: 'e2': 'P', 'e7': 'p'). Maiuscula=branca."""
        out: dict[str, str] = {}
        for sq, piece in self.board.piece_map().items():
            out[chess.square_name(sq)] = piece.symbol()
        return out

    def piece_at(self, square: str) -> str | None:
        piece = self.board.piece_at(chess.parse_square(square))
        return piece.symbol() if piece else None

    @staticmethod
    def square_name(square: str) -> str:
        return square

    def copy(self) -> "BoardState":
        return BoardState(self.board.fen())

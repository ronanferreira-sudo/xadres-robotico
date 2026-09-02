"""Tabuleiro de xadrez 4x4 (variante reduzida) para testes sem o tabuleiro 8x8.

Implementa a mesma interface usada pelo motor (``engine.py``) e pelo
``BoardState``, mas num tabuleiro 4x4. Reusa ``chess.Piece`` e as funcoes de
quadrado do python-chess: os quadrados vivem no canto a1-d4 do espaco 8x8,
entao ``chess.square_name`` continua funcionando sem mudancas.

Variante (estilo "Silverman 4x4 chess"):
  - 1 Torre, 1 Cavalo, 1 Bispo, 1 Rei e 4 peoes por lado.
  - Posicao inicial::

        4: r n b k
        3: p p p p
        2: P P P P
        1: R N B K
          a b c d

  - Sem roque. Peao promove a dama/torre/bispo/cavalo. En passant habilitado.
"""

from __future__ import annotations

import chess
from chess import Piece

FILES = 4
RANKS = 4

_PROMO = {"q": chess.QUEEN, "r": chess.ROOK, "b": chess.BISHOP, "n": chess.KNIGHT}


def _sq(f: int, r: int) -> int:
    return chess.square(f, r)


class MiniMove:
    """Lance no tabuleiro 4x4, compativel com a API usada pelo motor."""

    __slots__ = ("from_sq", "to_sq", "promotion", "is_en_passant")

    def __init__(self, from_sq: int, to_sq: int, promotion: str | None = None,
                 is_en_passant: bool = False) -> None:
        self.from_sq = from_sq
        self.to_sq = to_sq
        self.promotion = promotion  # "q" | "r" | "b" | "n" | None
        self.is_en_passant = is_en_passant

    @classmethod
    def from_uci(cls, uci: str) -> "MiniMove":
        return cls(chess.parse_square(uci[0:2]), chess.parse_square(uci[2:4]), uci[4:5] or None)

    def uci(self) -> str:
        s = chess.square_name(self.from_sq) + chess.square_name(self.to_sq)
        if self.promotion:
            s += self.promotion
        return s

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, MiniMove)
            and self.from_sq == other.from_sq
            and self.to_sq == other.to_sq
            and self.promotion == other.promotion
        )

    def __hash__(self) -> int:
        return hash((self.from_sq, self.to_sq, self.promotion))

    def __repr__(self) -> str:
        return f"<MiniMove {self.uci()}>"


class _Undo:
    __slots__ = ("from_sq", "to_sq", "moved", "captured", "captured_sq", "old_ep", "halfmove")

    def __init__(self, from_sq, to_sq, moved, captured, captured_sq, old_ep, halfmove):
        self.from_sq = from_sq
        self.to_sq = to_sq
        self.moved = moved
        self.captured = captured
        self.captured_sq = captured_sq
        self.old_ep = old_ep
        self.halfmove = halfmove


class MiniBoard:
    """Estado de um jogo de xadrez 4x4 (interface compativel com chess.Board)."""

    board_size = 4

    def __init__(self) -> None:
        self.turn = chess.WHITE
        self._pieces: dict[int, Piece] = {}
        self._ep_square: int | None = None
        self._stack: list[_Undo] = []
        self._pos_counts: dict[tuple, int] = {}
        self._halfmove_clock = 0
        self._setup_start()
        self._pos_counts[self._position_key()] = 1

    # -- construcao ---------------------------------------------------------

    def _setup_start(self) -> None:
        # Brancas (ranks 1-2)
        self._pieces[_sq(0, 0)] = Piece(chess.ROOK, chess.WHITE)    # a1
        self._pieces[_sq(1, 0)] = Piece(chess.KNIGHT, chess.WHITE)  # b1
        self._pieces[_sq(2, 0)] = Piece(chess.BISHOP, chess.WHITE)  # c1
        self._pieces[_sq(3, 0)] = Piece(chess.KING, chess.WHITE)    # d1
        for f in range(FILES):
            self._pieces[_sq(f, 1)] = Piece(chess.PAWN, chess.WHITE)
        # Pretas (ranks 3-4)
        self._pieces[_sq(0, 3)] = Piece(chess.ROOK, chess.BLACK)    # a4
        self._pieces[_sq(1, 3)] = Piece(chess.KNIGHT, chess.BLACK)  # b4
        self._pieces[_sq(2, 3)] = Piece(chess.BISHOP, chess.BLACK)  # c4
        self._pieces[_sq(3, 3)] = Piece(chess.KING, chess.BLACK)    # d4
        for f in range(FILES):
            self._pieces[_sq(f, 2)] = Piece(chess.PAWN, chess.BLACK)

    def copy(self) -> "MiniBoard":
        b = MiniBoard.__new__(MiniBoard)
        b.turn = self.turn
        b._pieces = dict(self._pieces)
        b._ep_square = self._ep_square
        b._stack = []
        b._pos_counts = dict(self._pos_counts)
        b._halfmove_clock = self._halfmove_clock
        return b

    @classmethod
    def from_symbols(cls, symbols: dict[str, str], turn: Color = chess.WHITE) -> "MiniBoard":
        """Constroi um tabuleiro a partir de um mapa {quadrado: simbolo}.

        Ex.: {"a1": "R", "d4": "k"}. Maiuscula = branca. Util para testes.
        """
        b = cls.__new__(cls)
        b.turn = turn
        b._pieces = {}
        b._ep_square = None
        b._stack = []
        b._pos_counts = {}
        b._halfmove_clock = 0
        for sq_name, sym in symbols.items():
            sq = chess.parse_square(sq_name)
            color = chess.WHITE if sym.isupper() else chess.BLACK
            pt = chess.PIECE_SYMBOLS.index(sym.lower())
            b._pieces[sq] = Piece(pt, color)
        b._pos_counts[b._position_key()] = 1
        return b

    # -- acesso -------------------------------------------------------------

    def piece_at(self, sq: int) -> Piece | None:
        return self._pieces.get(sq)

    def piece_map(self) -> dict[int, Piece]:
        return dict(self._pieces)

    def _position_key(self) -> tuple:
        items = tuple((sq, p.piece_type, p.color) for sq, p in sorted(self._pieces.items()))
        return (self.turn, self._ep_square, items)

    def _king_sq(self, color: Color) -> int | None:
        for sq, p in self._pieces.items():
            if p.piece_type == chess.KING and p.color == color:
                return sq
        return None

    # -- ataque / xeque -----------------------------------------------------

    def _piece_attacks(self, from_sq: int, piece: Piece, to_sq: int) -> bool:
        f1, r1 = chess.square_file(from_sq), chess.square_rank(from_sq)
        f2, r2 = chess.square_file(to_sq), chess.square_rank(to_sq)
        df, dr = abs(f2 - f1), abs(r2 - r1)
        pt = piece.piece_type
        if pt == chess.PAWN:
            step = 1 if piece.color == chess.WHITE else -1
            return (r2 - r1) == step and df == 1
        if pt == chess.KNIGHT:
            return (df, dr) in ((1, 2), (2, 1))
        if pt == chess.KING:
            return df <= 1 and dr <= 1 and (df != 0 or dr != 0)
        if df == dr and df > 0:
            if pt in (chess.BISHOP, chess.QUEEN):
                return self._ray_clear(from_sq, to_sq)
            return False
        if (df == 0) != (dr == 0):
            if pt in (chess.ROOK, chess.QUEEN):
                return self._ray_clear(from_sq, to_sq)
            return False
        return False

    def _ray_clear(self, from_sq: int, to_sq: int) -> bool:
        f1, r1 = chess.square_file(from_sq), chess.square_rank(from_sq)
        f2, r2 = chess.square_file(to_sq), chess.square_rank(to_sq)
        df = 0 if f2 == f1 else (f2 - f1) // abs(f2 - f1)
        dr = 0 if r2 == r1 else (r2 - r1) // abs(r2 - r1)
        f, r = f1 + df, r1 + dr
        while (f, r) != (f2, r2):
            if _sq(f, r) in self._pieces:
                return False
            f += df
            r += dr
        return True

    def is_attacked_by(self, sq: int, color: Color) -> bool:
        for s, p in self._pieces.items():
            if p.color == color and self._piece_attacks(s, p, sq):
                return True
        return False

    def _in_check(self, color: Color) -> bool:
        k = self._king_sq(color)
        return k is not None and self.is_attacked_by(k, not color)

    # -- geracao de lances --------------------------------------------------

    def _pseudo_moves(self, sq: int, piece: Piece) -> list[MiniMove]:
        f, r = chess.square_file(sq), chess.square_rank(sq)
        color = piece.color
        pt = piece.piece_type
        moves: list[MiniMove] = []

        if pt == chess.PAWN:
            d = 1 if color == chess.WHITE else -1
            start_r = 1 if color == chess.WHITE else 2
            last_r = RANKS - 1 if color == chess.WHITE else 0
            nr = r + d
            if 0 <= nr < RANKS:
                to = _sq(f, nr)
                if to not in self._pieces:
                    if nr == last_r:
                        moves.extend(MiniMove(sq, to, p) for p in "qrbn")
                    else:
                        moves.append(MiniMove(sq, to))
                    if r == start_r:
                        to2 = _sq(f, r + 2 * d)
                        if to2 not in self._pieces:
                            moves.append(MiniMove(sq, to2))
            for df in (-1, 1):
                nf, nr2 = f + df, r + d
                if not (0 <= nf < FILES and 0 <= nr2 < RANKS):
                    continue
                to = _sq(nf, nr2)
                target = self._pieces.get(to)
                if target is not None and target.color != color:
                    if nr2 == last_r:
                        moves.extend(MiniMove(sq, to, p) for p in "qrbn")
                    else:
                        moves.append(MiniMove(sq, to))
                elif to == self._ep_square:
                    moves.append(MiniMove(sq, to, is_en_passant=True))
        elif pt == chess.KNIGHT:
            for df, dr in ((1, 2), (2, 1), (-1, 2), (-2, 1), (1, -2), (2, -1), (-1, -2), (-2, -1)):
                nf, nr = f + df, r + dr
                if not (0 <= nf < FILES and 0 <= nr < RANKS):
                    continue
                to = _sq(nf, nr)
                occ = self._pieces.get(to)
                if occ is None or occ.color != color:
                    moves.append(MiniMove(sq, to))
        elif pt in (chess.BISHOP, chess.ROOK, chess.QUEEN):
            dirs: list[tuple[int, int]] = []
            if pt in (chess.BISHOP, chess.QUEEN):
                dirs += [(-1, -1), (1, -1), (-1, 1), (1, 1)]
            if pt in (chess.ROOK, chess.QUEEN):
                dirs += [(0, 1), (0, -1), (1, 0), (-1, 0)]
            for df, dr in dirs:
                nf, nr = f + df, r + dr
                while 0 <= nf < FILES and 0 <= nr < RANKS:
                    to = _sq(nf, nr)
                    occ = self._pieces.get(to)
                    if occ is None:
                        moves.append(MiniMove(sq, to))
                    else:
                        if occ.color != color:
                            moves.append(MiniMove(sq, to))
                        break
                    nf += df
                    nr += dr
        elif pt == chess.KING:
            for df in (-1, 0, 1):
                for dr in (-1, 0, 1):
                    if df == 0 and dr == 0:
                        continue
                    nf, nr = f + df, r + dr
                    if not (0 <= nf < FILES and 0 <= nr < RANKS):
                        continue
                    to = _sq(nf, nr)
                    occ = self._pieces.get(to)
                    if occ is None or occ.color != color:
                        moves.append(MiniMove(sq, to))
        return moves

    @property
    def legal_moves(self) -> list[MiniMove]:
        moves: list[MiniMove] = []
        mover = self.turn
        for sq, p in list(self._pieces.items()):
            if p.color == mover:
                moves.extend(self._pseudo_moves(sq, p))
        legal: list[MiniMove] = []
        for m in moves:
            u = self._apply(m)
            if not self._in_check(mover):
                legal.append(m)
            self._unapply(u)
        return legal

    # -- aplicacao de lances -----------------------------------------------

    def _is_ep_move(self, move: MiniMove) -> bool:
        p = self._pieces.get(move.from_sq)
        return (
            p is not None
            and p.piece_type == chess.PAWN
            and chess.square_file(move.to_sq) != chess.square_file(move.from_sq)
            and move.to_sq not in self._pieces
            and move.to_sq == self._ep_square
        )

    def _apply(self, move: MiniMove) -> _Undo:
        from_sq, to_sq = move.from_sq, move.to_sq
        moved = self._pieces[from_sq]
        dest_piece = self._pieces.get(to_sq)
        old_ep = self._ep_square
        is_ep = self._is_ep_move(move)

        del self._pieces[from_sq]
        captured = None
        captured_sq = None
        if is_ep:
            captured_sq = _sq(chess.square_file(to_sq), chess.square_rank(from_sq))
            captured = self._pieces.pop(captured_sq, None)
        elif dest_piece is not None:
            captured = self._pieces.pop(to_sq)
            captured_sq = to_sq

        placed = Piece(_PROMO[move.promotion], moved.color) if move.promotion else moved
        self._pieces[to_sq] = placed

        if moved.piece_type == chess.PAWN and abs(chess.square_rank(to_sq) - chess.square_rank(from_sq)) == 2:
            self._ep_square = _sq(chess.square_file(from_sq),
                                  (chess.square_rank(from_sq) + chess.square_rank(to_sq)) // 2)
        else:
            self._ep_square = None

        old_halfmove = self._halfmove_clock
        if moved.piece_type == chess.PAWN or captured is not None:
            self._halfmove_clock = 0
        else:
            self._halfmove_clock += 1

        self.turn = not self.turn
        return _Undo(from_sq, to_sq, moved, captured, captured_sq, old_ep, old_halfmove)

    def _unapply(self, u: _Undo) -> None:
        del self._pieces[u.to_sq]
        if u.captured is not None:
            self._pieces[u.captured_sq] = u.captured
        self._pieces[u.from_sq] = u.moved
        self._ep_square = u.old_ep
        self._halfmove_clock = u.halfmove
        self.turn = not self.turn

    def push(self, move: MiniMove) -> None:
        self._stack.append(self._apply(move))
        key = self._position_key()
        self._pos_counts[key] = self._pos_counts.get(key, 0) + 1

    def pop(self) -> None:
        key = self._position_key()
        self._pos_counts[key] -= 1
        if self._pos_counts[key] <= 0:
            del self._pos_counts[key]
        self._unapply(self._stack.pop())

    # -- estado do jogo -----------------------------------------------------

    def is_check(self) -> bool:
        return self._in_check(self.turn)

    def is_checkmate(self) -> bool:
        return self._in_check(self.turn) and not self.legal_moves

    def is_stalemate(self) -> bool:
        return (not self._in_check(self.turn)) and not self.legal_moves

    def is_insufficient_material(self) -> bool:
        non_king = [p for p in self._pieces.values() if p.piece_type != chess.KING]
        if len(non_king) == 0:
            return True  # K vs K
        if len(non_king) == 1 and non_king[0].piece_type in (chess.BISHOP, chess.KNIGHT):
            return True  # K+menor vs K
        if len(non_king) == 2 and all(p.piece_type == chess.BISHOP for p in non_king):
            bsq = [sq for sq, p in self._pieces.items() if p.piece_type == chess.BISHOP]
            if (chess.square_file(bsq[0]) + chess.square_rank(bsq[0])) % 2 == \
               (chess.square_file(bsq[1]) + chess.square_rank(bsq[1])) % 2:
                return True  # bispos de mesma cor
        return False

    def is_repetition(self, count: int = 3) -> bool:
        return self._pos_counts.get(self._position_key(), 0) >= count

    def is_fifty_moves(self) -> bool:
        return self._halfmove_clock >= 100

    def is_game_over(self) -> bool:
        return (
            self.is_checkmate()
            or self.is_stalemate()
            or self.is_insufficient_material()
            or self.is_repetition(3)
            or self.is_fifty_moves()
        )

    def result(self) -> str:
        if self.is_checkmate():
            return "0-1" if self.turn == chess.WHITE else "1-0"
        if self.is_stalemate() or self.is_insufficient_material() or self.is_repetition(3) or self.is_fifty_moves():
            return "1/2-1/2"
        return "*"

    def fen(self) -> str:
        return str(self)

    # -- notacao ------------------------------------------------------------

    def _disambiguation(self, move: MiniMove, pt: int) -> str:
        color = self._pieces[move.from_sq].color
        others = []
        for sq, p in self._pieces.items():
            if sq == move.from_sq or p.piece_type != pt or p.color != color:
                continue
            if any(m.to_sq == move.to_sq for m in self._pseudo_moves(sq, p)):
                others.append(sq)
        if not others:
            return ""
        if not any(chess.square_file(sq) == chess.square_file(move.from_sq) for sq in others):
            return chess.FILE_NAMES[chess.square_file(move.from_sq)]
        if not any(chess.square_rank(sq) == chess.square_rank(move.from_sq) for sq in others):
            return str(chess.square_rank(move.from_sq) + 1)
        return chess.square_name(move.from_sq)

    def san(self, move: MiniMove) -> str:
        mover = self._pieces.get(move.from_sq)
        pt = mover.piece_type if mover else chess.PAWN
        is_capture = self._is_ep_move(move) or (move.to_sq in self._pieces)
        disamb = "" if pt == chess.PAWN else self._disambiguation(move, pt)

        self.push(move)
        suffix = "#" if self.is_checkmate() else ("+" if self.is_check() else "")
        self.pop()

        if pt == chess.PAWN:
            s = chess.FILE_NAMES[chess.square_file(move.from_sq)] + "x" if is_capture else ""
            s += chess.square_name(move.to_sq)
            if move.promotion:
                s += "=" + move.promotion.upper()
        else:
            letter = chess.piece_symbol(pt).upper()
            s = letter + disamb + ("x" if is_capture else "") + chess.square_name(move.to_sq)
        return s + suffix

    def __str__(self) -> str:
        lines = []
        for r in range(RANKS - 1, -1, -1):
            row = [self._pieces[_sq(f, r)].symbol() if _sq(f, r) in self._pieces else "." for f in range(FILES)]
            lines.append(f"{r + 1}  " + " ".join(row))
        lines.append("   a b c d")
        return "\n".join(lines)

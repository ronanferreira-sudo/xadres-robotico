"""Orquestrador da partida de xadrez com bracos roboticos.

Em modo "simulation" roda sem hardware (visao = verdade do tabuleiro).
Em modo "hardware" conecta os bracos Dobot e as cameras, executa os lances
fisicamente e reconfere o tabuleiro com a visao apos cada jogada.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any

import chess

from ..chess.board_state import BoardState
from ..vision.calibration import Calibration
from .players import AIPlayer, HumanPlayer, Player

logger = logging.getLogger(__name__)


def plan_actions(prev: dict[str, str], new: dict[str, str]) -> list[tuple[str, str, str, str | None]]:
    """Calcula as acoes fisicas (mover/remover) a partir do delta do tabuleiro.

    Retorna lista de tuplas de 4 elementos:
      ("move",    cor, de,  para)  -> braco da `cor` move peca de->para
      ("capture", cor, quadrado, None) -> braco da `cor` remove peca capturada
    Ordem da lista: capturas primeiro, depois movimentos.
    """
    removed = {sq: sym for sq, sym in prev.items() if new.get(sq) != sym}
    added = {sq: sym for sq, sym in new.items() if prev.get(sq) != sym}

    actions: list[tuple[str, str, str, str | None]] = []
    used_from: set[str] = set()

    for color in ("white", "black"):
        is_upper = color == "white"
        rem = {sq: sym for sq, sym in removed.items() if sym.isupper() == is_upper}
        add = {sq: sym for sq, sym in added.items() if sym.isupper() == is_upper}

        rem_by_sym: dict[str, list[str]] = defaultdict(list)
        for sq, sym in rem.items():
            rem_by_sym[sym].append(sq)

        for to_sq, sym in add.items():
            from_sq = rem_by_sym[sym].pop(0) if rem_by_sym.get(sym) else None
            if from_sq is None:
                # promocao: peao vira outra peca (ex.: P -> Q)
                pawn = "P" if is_upper else "p"
                from_sq = rem_by_sym[pawn].pop(0) if rem_by_sym.get(pawn) else None
            if from_sq is None:
                for other in list(rem_by_sym):
                    if rem_by_sym[other]:
                        from_sq = rem_by_sym[other].pop(0)
                        break
            if from_sq is not None:
                used_from.add(from_sq)
                actions.append(("move", color, from_sq, to_sq))

    captured_squares = set(removed) - used_from
    for sq in captured_squares:
        sym = removed[sq]
        opp = "black" if sym.islower() else "white"
        actions.append(("capture", opp, sq, None))

    # Capturas primeiro para liberar o quadrado de destino.
    captures = [a for a in actions if a[0] == "capture"]
    moves = [a for a in actions if a[0] == "move"]
    return captures + moves


class Match:
    def __init__(self, config: dict[str, Any], calibration: Calibration | None = None) -> None:
        self.config = config
        self.calib = calibration
        self.mode = str(config.get("mode", "simulation"))
        self.board_size = int(config.get("board", {}).get("squares", 8))
        self.state = BoardState(size=self.board_size)
        self.players: dict[str, Player] = {}
        self.arms: dict[str, Any] = {}
        self.vision = None
        self.move_count = 0
        self.max_moves = int(config.get("match", {}).get("max_moves", 0))
        self.move_delay = float(config.get("match", {}).get("move_delay", 0.0))
        self.verify = bool(config.get("match", {}).get("verify_with_vision", True))

    # -- setup -------------------------------------------------------------

    def _build_players(self) -> None:
        engine_cfg = self.config.get("engine", {})
        players_cfg = engine_cfg.get("players", {"white": "ai", "black": "ai"})
        for color in ("white", "black"):
            kind = str(players_cfg.get(color, "ai")).lower()
            if kind == "human":
                self.players[color] = HumanPlayer(color)
            else:
                self.players[color] = AIPlayer(color, engine_cfg)

    async def setup(self) -> None:
        self._build_players()
        if self.mode == "hardware":
            await self._setup_hardware()
        else:
            await self._setup_simulation()

    async def _setup_hardware(self) -> None:
        from ..robot.arm import Arm

        arms_cfg = self.config.get("arms", {})
        for color in ("white", "black"):
            cfg = arms_cfg.get(color, {})
            if not cfg.get("enabled", False):
                continue
            arm = Arm(color, cfg, board_size=self.board_size)
            await arm.connect()
            await arm.home()
            self.arms[color] = arm

        if self.calib is not None:
            from ..vision.detector import VisionSystem

            self.vision = VisionSystem(self.config.get("vision", {}), self.calib)
            self.vision.open()

    async def _setup_simulation(self) -> None:
        from ..vision.detector import VisionSystem

        sim_cfg = dict(self.config.get("vision", {}))
        sim_cfg["_backend"] = "sim"
        sim_cfg["method"] = "ground_truth"
        self.vision = VisionSystem(sim_cfg, self.calib)
        self.vision.open()
        self.vision.set_truth_provider(lambda: self.state.piece_map())

    # -- execucao ----------------------------------------------------------

    def _arm_for(self, color: str) -> Any:
        """Retorna o braco da cor; com um unico braco, ele atende as duas cores."""
        arm = self.arms.get(color)
        if arm is not None:
            return arm
        if len(self.arms) == 1:
            return next(iter(self.arms.values()))
        return None

    async def _execute(self, actions: list[tuple[str, str, str | None]]) -> None:
        hardware = self.mode == "hardware" and self.arms
        for action in actions:
            kind, color, a, b = action
            arm = self._arm_for(color) if hardware else None
            if kind == "capture":
                sq = a
                logger.info("ACAO: %s captura em %s", color, sq)
                if arm is not None:
                    await arm.remove_captured(sq)
            else:  # move
                frm, to = a, b
                logger.info("ACAO: %s move %s -> %s", color, frm, to)
                if arm is not None:
                    await arm.move_piece(frm, to)
        if hardware and self.move_delay:
            await asyncio.sleep(self.move_delay)

    async def _verify(self) -> bool:
        if not self.verify or self.vision is None:
            return True
        detected = await self.vision.detect_board()
        expected = self.state.piece_map()
        ok = True
        for sq in set(list(expected) + list(detected)):
            exp = _color_short(expected.get(sq))
            det = detected.get(sq)
            if exp != det:
                ok = False
                logger.warning("Divergencia em %s: esperado=%s detectado=%s", sq, exp, det)
        return ok

    # -- loop principal ----------------------------------------------------

    async def run(self) -> str:
        print(f"=== Iniciando partida (modo: {self.mode}, tabuleiro {self.board_size}x{self.board_size}) ===")
        print(self.state.board)
        while not self.state.is_game_over():
            if self.max_moves and self.move_count >= self.max_moves:
                print("Limite de lances atingido.")
                break
            color = self.state.turn_name
            player = self.players[color]
            move = player.choose(self.state)
            if move is None:
                print("Jogador desistiu.")
                break

            prev_map = self.state.piece_map()
            san = self.state.san(move)
            self.state.apply(move)
            new_map = self.state.piece_map()
            self.move_count += 1

            print(f"Lance {self.move_count}: {color} joga {san} ({move.uci()})")
            actions = plan_actions(prev_map, new_map)
            await self._execute(actions)
            await self._verify()

        winner = self.state.outcome()
        if winner == "white":
            print("\n>>> AS BRANCAS VENCERAM! <<<")
        elif winner == "black":
            print("\n>>> AS PRETAS VENCERAM! <<<")
        else:
            print("\n>>> EMPATE / FIM DE JOGO <<<")
        print(self.state.board)
        return winner

    async def teardown(self) -> None:
        for arm in self.arms.values():
            try:
                await arm.disconnect()
            except Exception:  # noqa: BLE001
                pass
        if self.vision is not None:
            self.vision.close()


def _color_short(symbol: str | None) -> str | None:
    if not symbol:
        return None
    return "white" if symbol.isupper() else "black"

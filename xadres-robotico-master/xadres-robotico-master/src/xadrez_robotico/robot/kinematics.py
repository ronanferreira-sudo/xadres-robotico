"""Transformada de coordenadas: quadrado do tabuleiro -> coordenada do robo.

Assume uma transformada rigida (translacao + rotacao + escala uniforme) entre
o sistema de referencia do tabuleiro e o do braco. E suficiente para um
tabuleiro plano e alinhado; calibracoes mais complexas podem ser adicionadas
depois (ex.: homografia de 4 pontos).
"""

from __future__ import annotations

import math
from typing import Mapping

import chess


class BoardToRobot:
    def __init__(
        self,
        origin_x: float,
        origin_y: float,
        spacing: float,
        rotation_deg: float = 0.0,
        size: int = 8,
    ) -> None:
        self.origin_x = origin_x
        self.origin_y = origin_y
        self.spacing = spacing
        self.rotation_deg = rotation_deg
        self.size = size
        self._cos = math.cos(math.radians(rotation_deg))
        self._sin = math.sin(math.radians(rotation_deg))

    @classmethod
    def from_config(cls, cfg: Mapping, size: int = 8) -> "BoardToRobot":
        return cls(
            origin_x=float(cfg["origin_x"]),
            origin_y=float(cfg["origin_y"]),
            spacing=float(cfg["spacing"]),
            rotation_deg=float(cfg.get("rotation_deg", 0.0)),
            size=size,
        )

    def _indices(self, square: str) -> tuple[int, int]:
        file_idx = ord(square[0].lower()) - ord("a")
        rank_idx = int(square[1]) - 1
        if not (0 <= file_idx < self.size and 0 <= rank_idx < self.size):
            raise ValueError(f"Quadrado invalido: {square}")
        return file_idx, rank_idx

    def to_xy(self, square: str) -> tuple[float, float]:
        """Retorna (x, y) do centro do quadrado no espaco do robo (mm)."""
        fx, ry = self._indices(square)
        dx = fx * self.spacing
        dy = ry * self.spacing
        x = self.origin_x + dx * self._cos - dy * self._sin
        y = self.origin_y + dx * self._sin + dy * self._cos
        return x, y

    def to_xyz(self, square: str, z: float) -> tuple[float, float, float]:
        x, y = self.to_xy(square)
        return x, y, z

"""Calibracao da visao: mapeia quadrados do tabuleiro para pixels da imagem."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass
class Calibration:
    """Mapeamento dos 64 quadrados para coordenadas de pixels [u, v]."""

    square_centers: dict[str, list[float]] = field(default_factory=dict)
    roi_size: int = 48
    empty_reference: str | None = None

    def center(self, square: str) -> tuple[float, float]:
        c = self.square_centers.get(square)
        if c is None:
            raise KeyError(f"Quadrado {square} nao calibrado.")
        return float(c[0]), float(c[1])

    def save(self, path: str) -> None:
        data: dict[str, Any] = {
            "camera": {
                "square_centers": self.square_centers,
                "roi_size": self.roi_size,
                "empty_reference": self.empty_reference,
            }
        }
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
        print(f"Calibracao salva em {path}")

    @classmethod
    def load(cls, path: str) -> "Calibration":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        cam = data.get("camera", {})
        return cls(
            square_centers={k: list(v) for k, v in (cam.get("square_centers") or {}).items()},
            roi_size=int(cam.get("roi_size", 48)),
            empty_reference=cam.get("empty_reference"),
        )

    @classmethod
    def build_from_corners(
        cls,
        a1: tuple[float, float],
        top_left: tuple[float, float],
        bottom_right: tuple[float, float],
        top_right: tuple[float, float],
        roi_size: int = 48,
        size: int = 8,
    ) -> "Calibration":
        """Interpola os centros a partir dos 4 cantos do tabuleiro.

        ``a1`` e o canto inferior esquerdo; ``top_left`` o superior esquerdo;
        ``bottom_right`` o inferior direito; ``top_right`` o superior direito.
        ``size`` e a dimensao do tabuleiro (8 ou 4).
        """
        centers: dict[str, list[float]] = {}
        n = size - 1
        for rank in range(1, size + 1):
            t = (rank - 1) / n
            for file_idx in range(size):
                s = file_idx / n
                f = chr(ord("a") + file_idx)
                sq = f"{f}{rank}"
                u = (1 - s) * ((1 - t) * a1[0] + t * top_left[0]) + s * ((1 - t) * bottom_right[0] + t * top_right[0])
                v = (1 - s) * ((1 - t) * a1[1] + t * top_left[1]) + s * ((1 - t) * bottom_right[1] + t * top_right[1])
                centers[sq] = [round(u, 1), round(v, 1)]
        return cls(square_centers=centers, roi_size=roi_size)


def all_squares(size: int = 8) -> list[str]:
    out: list[str] = []
    for rank in range(1, size + 1):
        for file_idx in range(size):
            out.append(f"{chr(ord('a') + file_idx)}{rank}")
    return out

"""xadrez-robotico: xadrez jogado por I.A. com bracos roboticos Dobot."""

from .chess import BoardState, choose_move
from .game import Match
from .vision import Calibration, VisionSystem

__all__ = ["BoardState", "choose_move", "Match", "Calibration", "VisionSystem"]

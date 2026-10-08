"""Launcher para o layout de calibração visual do braço robótico para Damas."""

from __future__ import annotations

import sys
from pathlib import Path

# Adiciona raiz ao sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.arm_setup_draughts_gui import DraughtsCalibrationGUI, main as run_gui


def main(config_path=None):
    run_gui()


if __name__ == "__main__":
    main()

"""Ponto de entrada (CLI) do xadrez-robotico."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import warnings
from pathlib import Path

import yaml

# Silencia avisos de deprecacao de modulos do driver Dobot vendorizado.
warnings.filterwarnings("ignore", category=DeprecationWarning, module="xadrez_robotico.dobot")

logger = logging.getLogger("xadrez")


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_config(path: str | None) -> dict:
    root = _project_root()
    cfg_path = Path(path) if path else root / "config" / "default.yaml"
    if not cfg_path.exists():
        raise SystemExit(f"Arquivo de config nao encontrado: {cfg_path}")
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_calibration(path: str | None):
    if not path:
        return None
    from xadrez_robotico.vision.calibration import Calibration

    p = Path(path)
    if not p.exists():
        print(f"Calibracao nao encontrada: {p} (use 'xadrez calibrate').")
        return None
    return Calibration.load(str(p))


async def cmd_play(args) -> None:
    from xadrez_robotico.game import Match

    config = load_config(args.config)
    if args.mode:
        config["mode"] = args.mode
    calib = load_calibration(args.calibration)
    match = Match(config, calib)
    await match.setup()
    try:
        await match.run()
    finally:
        await match.teardown()


async def cmd_detect(args) -> None:
    from xadrez_robotico.vision.calibration import Calibration
    from xadrez_robotico.vision.detector import VisionSystem

    config = load_config(args.config)
    calib = load_calibration(args.calibration)
    if calib is None:
        raise SystemExit("Calibracao necessaria para deteccao. Rode 'xadrez calibrate'.")
    cam_cfg = dict(config.get("vision", {}))
    cam_cfg["_backend"] = "real"
    vision = VisionSystem(cam_cfg, calib)
    vision.open()
    print("Pressione 'q' para sair.")
    try:
        import cv2

        while True:
            board = await vision.detect_board()
            occ = sum(1 for v in board.values() if v)
            print(f"\rQuadrados ocupados: {occ}", end="", flush=True)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
    finally:
        vision.close()


async def cmd_calibrate(args) -> None:
    from xadrez_robotico.vision.calibration import Calibration

    config = load_config(args.config)
    size = int(config.get("board", {}).get("squares", 8))
    last_file = chr(ord("a") + size - 1)

    print("Calibracao interativa do tabuleiro.")
    print(f"Informe o centro (pixels u,v) dos 4 cantos do tabuleiro {size}x{size} na imagem:")
    print("(use 'xadrez detect' ou qualquer visualizador para obter os pixels)\n")

    def ask(name: str) -> tuple[float, float]:
        raw = input(f"{name} (u,v): ")
        parts = raw.replace(",", " ").split()
        return float(parts[0]), float(parts[1])

    a1 = ask(f"a1 (canto inferior esquerdo)")
    tl = ask(f"a{size} (canto superior esquerdo)")
    br = ask(f"{last_file}1 (canto inferior direito)")
    tr = ask(f"{last_file}{size} (canto superior direito)")
    roi = int(input("Tamanho do ROI (px) [48]: ") or "48")

    calib = Calibration.build_from_corners(a1, tl, br, tr, roi, size=size)
    out = args.output or str(_project_root() / "config" / "calibration.yaml")
    calib.save(out)
    print(f"\nCalibracao concluida. Edite '{out}' para informar empty_reference (foto do tabuleiro vazio).")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="xadrez", description="Xadrez robotico com I.A. e Dobot Magician Lite.")
    sub = p.add_subparsers(dest="command", required=True)

    play = sub.add_parser("play", help="Joga uma partida (simulacao ou hardware).")
    play.add_argument("--config", default=None)
    play.add_argument("--calibration", default=None)
    play.add_argument("--mode", choices=["simulation", "hardware"], default=None)
    play.set_defaults(func=cmd_play)

    det = sub.add_parser("detect", help="Mostra a deteccao do tabuleiro pela camera.")
    det.add_argument("--config", default=None)
    det.add_argument("--calibration", default=None)
    det.set_defaults(func=cmd_detect)

    cal = sub.add_parser("calibrate", help="Gera o arquivo de calibracao da camera.")
    cal.add_argument("--output", default=None)
    cal.set_defaults(func=cmd_calibrate)

    return p


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()

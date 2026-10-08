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

    # Sobrescreve parametros via flags da CLI
    if getattr(args, "max_moves", None) is not None:
        config.setdefault("match", {})["max_moves"] = args.max_moves
    if getattr(args, "white_port", None):
        config.setdefault("arms", {}).setdefault("white", {})["serial_port"] = args.white_port
    if getattr(args, "black_port", None):
        config.setdefault("arms", {}).setdefault("black", {})["serial_port"] = args.black_port
    if getattr(args, "camera", None) is not None:
        config.setdefault("vision", {})["camera_index"] = args.camera

    calib = load_calibration(args.calibration)
    match = Match(config, calib)
    await match.setup()
    try:
        await match.run()
    finally:
        await match.teardown()



async def cmd_setup_arms(args) -> None:
    import sys
    sys.path.insert(0, str(_project_root()))
    from tools.arm_setup_gui import main as run_setup
    run_setup(args.config)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="xadrez", description="Xadrez robotico com I.A. e Dobot Magician Lite.")
    sub = p.add_subparsers(dest="command", required=True)

    play = sub.add_parser("play", help="Joga uma partida (simulacao ou hardware).")
    play.add_argument("--config", default=None)
    play.add_argument("--mode", choices=["simulation", "hardware"], default=None)
    play.add_argument("--max-moves", type=int, default=None,
                      help="Limite de lances (meios-lances). 0 = sem limite.")
    play.add_argument("--white-port", default=None,
                      help="Porta serial do braco branco (ex: COM5)")
    play.add_argument("--black-port", default=None,
                      help="Porta serial do braco preto (ex: COM4)")
    play.set_defaults(func=cmd_play)

    setup = sub.add_parser("setup_arms", help="Abre a interface de configuracao manual dos bracos.")
    setup.add_argument("--config", default=None)
    setup.set_defaults(func=cmd_setup_arms)

    return p


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()

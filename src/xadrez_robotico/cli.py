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

    out = args.output or str(_project_root() / "config" / "calibration.yaml")

    if not args.manual:
        try:
            import sys
            from tools.calibrate_board import main as run_gui_calibrate
            sys.argv = ["calibrate_board.py", "--camera", str(args.camera), "--output", out]
            res = run_gui_calibrate()
            if res == 0:
                return
        except Exception as exc:
            logger.warning("Nao foi possivel abrir calibracao visual OpenCV (%s). Usando modo manual.", exc)

    print("Calibracao manual do tabuleiro (entrada de coordenadas por texto).")
    print("Informe o centro (pixels u,v) dos 4 cantos do tabuleiro na imagem:\n")

    def ask(name: str) -> tuple[float, float]:
        raw = input(f"{name} (u,v): ")
        parts = raw.replace(",", " ").split()
        return float(parts[0]), float(parts[1])

    a1 = ask("a1 (canto branco esquerdo)")
    a8 = ask("a8 (canto branco superior esquerdo)")
    h1 = ask("h1 (canto branco direito)")
    h8 = ask("h8 (canto branco superior direito)")
    roi = int(input("Tamanho do ROI (px) [48]: ") or "48")

    calib = Calibration.build_from_corners(a1, a8, h1, h8, roi)
    calib.save(out)
    print(f"\nCalibracao concluida. Edite '{out}' para informar empty_reference (foto do tabuleiro vazio).")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="xadrez", description="Xadrez robotico com I.A. e Dobot Magician Lite.")
    sub = p.add_subparsers(dest="command", required=True)

    play = sub.add_parser("play", help="Joga uma partida (simulacao ou hardware).")
    play.add_argument("--config", default=None)
    play.add_argument("--calibration", default=None)
    play.add_argument("--mode", choices=["simulation", "hardware"], default=None)
    play.add_argument("--max-moves", type=int, default=None,
                      help="Limite de lances (meios-lances). 0 = sem limite.")
    play.add_argument("--white-port", default=None,
                      help="Porta serial do braco branco (ex: COM5)")
    play.add_argument("--black-port", default=None,
                      help="Porta serial do braco preto (ex: COM4)")
    play.add_argument("--camera", type=int, default=None,
                      help="Indice da camera (substitui config)")
    play.set_defaults(func=cmd_play)


    det = sub.add_parser("detect", help="Mostra a deteccao do tabuleiro pela camera.")
    det.add_argument("--config", default=None)
    det.add_argument("--calibration", default=None)
    det.set_defaults(func=cmd_detect)

    cal = sub.add_parser("calibrate", help="Gera o arquivo de calibracao da camera (janela interativa OpenCV por padrao).")
    cal.add_argument("--output", default=None)
    cal.add_argument("--camera", type=int, default=1, help="Indice da camera (padrao: 1)")
    cal.add_argument("--manual", action="store_true", help="Modo manual via digitação de coordenadas no terminal")
    cal.set_defaults(func=cmd_calibrate)

    return p


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()

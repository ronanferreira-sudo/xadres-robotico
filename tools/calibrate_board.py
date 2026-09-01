"""Calibracao interativa do tabuleiro usando a camera.

Uso:
    python tools/calibrate_board.py
    python tools/calibrate_board.py --camera 0 --output config/calibration.yaml

Passos:
1. Posicione o tabuleiro vazio sob a camera.
2. Clique nos 4 cantos na ordem: a1, a8, h1, h8.
3. Salve a imagem de referencia do tabuleiro vazio quando solicitado.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import cv2
import numpy as np

from xadrez_robotico.vision.calibration import Calibration

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("xadrez.calibrate")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Calibracao do tabuleiro por camera.")
    p.add_argument("--camera", type=int, default=0)
    p.add_argument("--output", default=None)
    p.add_argument("--roi-size", type=int, default=48)
    return p.parse_args()


def mouse_callback(event, x, y, flags, param):
    pts = param["points"]
    win = param["window"]
    if event == cv2.EVENT_LBUTTONDOWN:
        if len(pts) >= 4:
            pts.clear()
            param["frame"][:] = param["_frame"]
        pts.append((x, y))
        cv2.circle(param["frame"], (x, y), 6, (0, 0, 255), -1)
        label = ["a1", "a8", "h1", "h8"][min(len(pts) - 1, 3)]
        cv2.putText(param["frame"], label, (x + 10, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow(win, param["frame"])


def main() -> int:
    args = parse_args()
    output = Path(args.output) if args.output else Path("config/calibration.yaml")
    output.parent.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        logger.error("Nao foi possivel abrir a camera %d.", args.camera)
        return 1

    win = "Calibracao - clique: a1, a8, h1, h8 | s=salvar | q=sair"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    state = {"points": [], "window": win, "frame": None, "_frame": None}
    cv2.setMouseCallback(win, mouse_callback, state)

    logger.info("Posicione o tabuleiro vazio na camera.")
    logger.info("Clique nos cantos na ordem: a1 -> a8 -> h1 -> h8.")
    logger.info("Teclas: [s] salvar calibracao | [r] reset | [q] sair")

    while True:
        ok, frame = cap.read()
        if not ok:
            logger.error("Falha ao ler frame da camera.")
            break
        frame = np.copy(frame)
        state["_frame"] = frame
        if not state["points"]:
            state["frame"] = frame
        cv2.imshow(win, state["frame"])
        key = cv2.waitKey(30) & 0xFF
        if key == ord("q"):
            break
        if key == ord("r"):
            state["points"].clear()
            state["frame"] = np.copy(frame)
            cv2.imshow(win, state["frame"])
        if key == ord("s") and len(state["points"]) == 4:
            calib = Calibration.build_from_corners(*state["points"], roi_size=args.roi_size)
            calib.save(str(output))
            empty_path = output.parent / "board_empty.png"
            cv2.imwrite(str(empty_path), frame)
            calib.empty_reference = str(empty_path)
            calib.save(str(output))
            logger.info("Calibracao salva em %s", output)
            logger.info("Referencia vazia salva em %s", empty_path)
            break

    cap.release()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())

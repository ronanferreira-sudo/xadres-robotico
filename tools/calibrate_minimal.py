"""Calibracao minima com melhoria de imagem para baixa iluminacao."""

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
    p = argparse.ArgumentParser(description="Calibracao minima com melhoria de imagem.")
    p.add_argument("--camera", type=int, default=1)
    p.add_argument("--output", default=None)
    p.add_argument("--roi-size", type=int, default=48)
    return p.parse_args()


def mouse_callback(event, x, y, flags, param):
    pts = param["points"]
    win = param["window"]
    if event == cv2.EVENT_LBUTTONDOWN:
        if len(pts) >= 4:
            pts.clear()
            if param["_frame"] is not None:
                param["frame"][:] = param["_frame"]
        pts.append((x, y))
        cv2.circle(param["frame"], (x, y), 6, (0, 0, 255), -1)
        label = ["a1", "a8", "h1", "h8"][min(len(pts) - 1, 3)]
        cv2.putText(param["frame"], label, (x + 10, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow(win, param["frame"])
        logger.info("Clicou: %s (%d, %d) [%d/4]", label, x, y, len(pts))


def main() -> int:
    args = parse_args()
    output = Path(args.output) if args.output else Path("config/calibration.yaml")
    output.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Abrindo camera %d ...", args.camera)
    cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
    if not cap.isOpened():
        logger.error("Nao foi possivel abrir a camera %d.", args.camera)
        return 1

    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    win = "Calibracao - clique: a1, a8, h1, h8 | s=salvar | r=reset | q=sair"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.moveWindow(win, 50, 50)

    state = {"points": [], "window": win, "frame": None, "_frame": None}
    cv2.setMouseCallback(win, mouse_callback, state)

    logger.info("Clique nos cantos na ordem: a1 -> a8 -> h1 -> h8.")
    logger.info("Teclas: [s] salvar calibracao | [r] reset | [q] sair")

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            logger.error("Falha ao ler frame da camera.")
            break

        enhanced = enhance_frame(frame)
        display = enhanced if state["frame"] is None else state["frame"]
        if state["frame"] is None:
            state["frame"] = np.copy(display)
            state["_frame"] = np.copy(display)

        if not state["points"]:
            state["frame"][:] = display

        cv2.imshow(win, state["frame"])
        key = cv2.waitKey(30) & 0xFF
        if key == ord("q"):
            logger.info("Saindo sem salvar.")
            break
        if key == ord("r"):
            state["points"].clear()
            state["frame"][:] = np.copy(display)
            state["_frame"] = np.copy(display)
            cv2.imshow(win, state["frame"])
            logger.info("Reset dos pontos.")
        if key == ord("s") and len(state["points"]) == 4:
            calib = Calibration.build_from_corners(*state["points"], roi_size=args.roi_size)
            calib.empty_reference = "config/board_empty.png"
            cv2.imwrite("config/board_empty.png", enhanced)
            calib.save(str(output))
            logger.info("Calibracao salva em %s", output)
            logger.info("Referencia vazia salva em config/board_empty.png")
            break

    cap.release()
    cv2.destroyAllWindows()
    return 0


def enhance_frame(frame: np.ndarray) -> np.ndarray:
    img = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    img = cv2.equalizeHist(img)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    img = clahe.apply(img)
    img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    img = cv2.convertScaleAbs(img, alpha=2.5, beta=80)
    return img


if __name__ == "__main__":
    sys.exit(main())

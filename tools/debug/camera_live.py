"""Visualizacao em tempo real das cameras disponiveis.

Abre uma janela por camera ativa (indices 0..5).
Pressione 'q' para fechar todas.
Pressione 's' para salvar o frame atual como board_empty.png

Uso:
    python tools/camera_live.py
    python tools/camera_live.py --index 1         # so camera 1
    python tools/camera_live.py --index 1 --save  # ja salva ao abrir
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]


def open_camera(index: int, warmup: int = 30) -> cv2.VideoCapture | None:
    """Tenta abrir a camera e descarta frames de warmup (evita frames pretos)."""
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    # descarta frames iniciais para o sensor estabilizar
    for _ in range(warmup):
        cap.grab()
    ok, frame = cap.read()
    if not ok or frame is None:
        cap.release()
        return None
    return cap


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview ao vivo das cameras.")
    parser.add_argument("--index", type=int, default=None,
                        help="Indice especifico da camera (padrao: testa 0..5)")
    parser.add_argument("--save", action="store_true",
                        help="Salva frame imediatamente como config/board_empty.png")
    args = parser.parse_args()

    indices = [args.index] if args.index is not None else list(range(6))

    print("Aguardando cameras aquecerem...")
    caps: dict[int, cv2.VideoCapture] = {}
    for i in indices:
        print(f"  Testando camera {i}...", end=" ", flush=True)
        cap = open_camera(i)
        if cap:
            caps[i] = cap
            print("OK")
        else:
            print("sem resposta")

    if not caps:
        print("Nenhuma camera encontrada!")
        return 1

    print(f"\n{len(caps)} camera(s) abertas: {list(caps.keys())}")
    print("Teclas: [q] fechar  [s] salvar frame como board_empty.png")

    for i in caps:
        cv2.namedWindow(f"Camera {i}", cv2.WINDOW_NORMAL)
        cv2.resizeWindow(f"Camera {i}", 640, 480)

    if args.save and caps:
        i = list(caps.keys())[0]
        _, frame = caps[i].read()
        out = ROOT / "config" / "board_empty.png"
        cv2.imwrite(str(out), frame)
        print(f"Salvo: {out}")

    while True:
        for i, cap in caps.items():
            ret, frame = cap.read()
            if ret and frame is not None:
                cv2.putText(frame, f"Camera {i} - [s] salvar  [q] sair",
                            (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                cv2.imshow(f"Camera {i}", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        elif key == ord("s"):
            # salva o frame da primeira camera com janela em foco
            for i, cap in caps.items():
                ret, frame = cap.read()
                if ret and frame is not None:
                    out = ROOT / "config" / "board_empty.png"
                    cv2.imwrite(str(out), frame)
                    print(f"[Camera {i}] board_empty.png salvo em: {out}")
                    break

    cv2.destroyAllWindows()
    for cap in caps.values():
        cap.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())

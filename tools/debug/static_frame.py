"""Teste minimo: abre camera uma vez e mostra frame estatico."""

from __future__ import annotations

import sys

import cv2


def main() -> int:
    cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("FALHA: nao abriu camera")
        return 1

    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    ret, frame = cap.read()
    if not ret or frame is None:
        print("FALHA: nao leu frame")
        cap.release()
        return 1

    print("Frame OK. shape:", frame.shape, "mean:", round(frame.mean(), 1))
    cv2.imwrite("static_frame.png", frame)
    print("Imagem salva: static_frame.png")

    win = "FRAME ESTATICO - pressione q para sair"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.moveWindow(win, 50, 50)
    cv2.imshow(win, frame)

    while True:
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cv2.destroyAllWindows()
    cap.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())

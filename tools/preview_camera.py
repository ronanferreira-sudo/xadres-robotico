"""Preview minimo da camera para diagnostico."""

from __future__ import annotations

import cv2


def main() -> int:
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("FALHA: nao abriu camera 0")
        return 1

    print("Camera aberta. Pressione 'q' para sair.")
    while True:
        ret, frame = cap.read()
        if not ret:
            print("FALHA: nao leu frame")
            break
        cv2.imshow("Preview Camera 0 - DSHOW", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

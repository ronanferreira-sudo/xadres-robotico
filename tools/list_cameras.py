"""Lista todos os dispositivos de video conectados."""

from __future__ import annotations

import sys

import cv2


def main() -> int:
    print("=== Dispositivos de video detectados ===")
    for i in range(10):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            name = cap.getBackendName()
            print(f"index {i}: {name} {w}x{h}")
            cap.release()
        else:
            print(f"index {i}: (nao disponivel)")

    print("\n=== Verificacao manual ===")
    print("1. Abra o aplicativo 'Camera' do Windows (sem fio).")
    print("2. Veja qual camera aparece: notebook ou dispositivo USB.")
    print("3. No Gerenciador de Dispositivos, procure por:")
    print("   - 'PC Camera' (VID_058F)")
    print("   - Dispositivos USB com triangulo amarelo")
    print("   - Verifique se a camera Dobot tem luz LED acesa")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

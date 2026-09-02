"""Smoke test do braco Dobot Magician: homing + movimentacao segura + ventosa.

Nao usa coordenadas do tabuleiro (ainda nao calibradas) - apenas movimentos
em altura segura (z >= 100 mm) para validar comunicacao, cinematica e a
ventosa, sem risco de colisao.

Uso:
    python scripts/smoke_test.py [--port COM3] [--vel 40] [--no-home]
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from xadrez_robotico.dobot import Robot

# Posicao de home apos calibracao (referencia segura, bracos para cima).
HOME = (239.0, 0.0, 148.5)

# Padrao de movimento em pontos ALCANCAVEIS (o braco e um anel: nao alcanca
# pontos muito proximos da base nem muito baixos). Valores mapeados no Magician.
WAYPOINTS = [
    (220.0, 40.0, 148.5),
    (260.0, 0.0, 148.5),
    (220.0, -40.0, 148.5),
    HOME,
]


async def _pose_xyz(r: Robot) -> tuple[float, float, float]:
    p = await r.command("GetPose")
    return float(p[0]), float(p[1]), float(p[2])


async def _move_and_wait(r: Robot, x: float, y: float, z: float, tol: float = 2.0,
                         timeout: float = 12.0) -> None:
    """Move para (x, y, z) e aguarda a chegada (com timeout)."""
    await r.command("set_ptpcmd", x=x, y=y, z=z, r=0, ptp_mode=1)
    elapsed = 0.0
    while elapsed < timeout:
        await asyncio.sleep(0.5)
        elapsed += 0.5
        cx, cy, cz = await _pose_xyz(r)
        if abs(cx - x) <= tol and abs(cy - y) <= tol and abs(cz - z) <= tol:
            print(f"    chegou -> ({cx:.1f}, {cy:.1f}, {cz:.1f})")
            return
    cx, cy, cz = await _pose_xyz(r)
    print(f"    AVISO: timeout, pose atual ({cx:.1f}, {cy:.1f}, {cz:.1f})")


async def demo(port: str, vel: int, home_first: bool) -> None:
    r = Robot(mode="usb", serial_port=port)
    await r.connect()
    try:
        await r.command("SetCPParams", planVel=vel, planAcc=vel)
        print(f">>> velocidade {vel}%")

        if home_first:
            print(">>> homing...")
            await r.command("set_homecmd")
            await asyncio.sleep(8)

        pose = await r.command("GetPose")
        print(">>> pose inicial:", [round(v, 1) for v in pose[:4]])

        for x, y, z in WAYPOINTS:
            print(f">>> movendo -> ({x}, {y}, {z})")
            await _move_and_wait(r, x, y, z)

        print(">>> ventosa ON")
        await r.command("SetEndEffectorSuctionCup", on=True)
        await asyncio.sleep(1.5)
        print(">>> ventosa OFF")
        await r.command("SetEndEffectorSuctionCup", on=False)
    finally:
        await r.disconnect()
    print(">>> concluido. Braco em home.")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Smoke test do braco Dobot")
    ap.add_argument("--port", default="COM3")
    ap.add_argument("--vel", type=int, default=40)
    ap.add_argument("--no-home", action="store_true", help="pula o homing inicial")
    args = ap.parse_args()
    asyncio.run(demo(args.port, args.vel, not args.no_home))


if __name__ == "__main__":
    main()

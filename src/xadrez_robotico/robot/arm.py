"""Controle de um braco robotico Dobot Magician Lite para mover pecas.

Cada braco e responsavel por uma cor. O braco executa a primitiva de
"pegar -> transportar -> soltar" usando ventosa (sugestao) ou garra.
"""

from __future__ import annotations

import asyncio
import logging
import serial.tools.list_ports
from typing import Any, Mapping

from ..dobot import Robot
from .kinematics import BoardToRobot

logger = logging.getLogger(__name__)


def find_all_dobot_ports() -> list[str]:
    """Retorna todas as portas seriais candidatas a Dobot Magician Lite."""
    ports = list(serial.tools.list_ports.comports())
    detected: list[str] = []
    for p in ports:
        desc = (p.description or "").lower()
        if any(token in desc for token in ("dobot", "usb serial", "ch340", "cp210")):
            detected.append(p.device)
        elif p.device.lower().startswith(("com", "/dev/ttyusb", "/dev/ttyacm")):
            detected.append(p.device)
    return detected


def assign_auto_ports(colors: list[str], available: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for i, color in enumerate(colors):
        out[color] = available[i % len(available)] if available else "auto"
    return out


class Arm:
    def __init__(
        self,
        color: str,
        cfg: Mapping,
        *,
        auto_ports: list[str] | None = None,
        serial_port: str | None = None,
    ) -> None:
        self.color = color
        self.cfg = cfg
        self.kin = BoardToRobot.from_config(cfg)
        self.travel_z = float(cfg.get("travel_z", 60.0))
        self.grip_z = float(cfg.get("grip_z", 8.0))
        self.velocity = float(cfg.get("velocity", 60.0))
        self.acceleration = float(cfg.get("acceleration", 60.0))
        self.effector = str(cfg.get("effector", "suction")).lower()
        self.capture = (
            float(cfg.get("capture_x", 250.0)),
            float(cfg.get("capture_y", 0.0)),
            float(cfg.get("capture_z", self.grip_z)),
        )
        self.connection = str(cfg.get("connection", "usb"))

        if serial_port is not None:
            self.serial_port = serial_port
        else:
            raw = cfg.get("serial_port", "auto")
            self.serial_port = raw
        self._robot: Robot | None = None
        self._queue_started = False

    async def connect(self) -> None:
        logger.info("[%s] Conectando braco (modo=%s)...", self.color, self.connection)
        if self.connection == "websocket":
            self._robot = Robot(mode="websocket")
        else:
            self._robot = Robot(mode="usb", serial_port=self.serial_port)
        await self._robot.connect()
        # Garante que a fila de comandos PTP execute (modo RPC).
        try:
            await self._robot.command("SetQueuedCmdClear")
            await self._robot.command("SetQueuedCmdStartExec")
            self._queue_started = True
        except Exception as exc:  # noqa: BLE001
            logger.debug("[%s] fila nao iniciada (modo usb?): %s", self.color, exc)

    async def disconnect(self) -> None:
        if self._robot is not None:
            await self._robot.disconnect()
            self._robot = None

    @property
    def robot(self) -> Robot:
        if self._robot is None:
            raise RuntimeError("Braco nao conectado. Chame connect() antes.")
        return self._robot

    # -- primitivas de movimento ------------------------------------------

    async def home(self) -> None:
        logger.info("[%s] Home.", self.color)
        await self.robot.motion.home()

    async def _go_above(self, square: str) -> None:
        x, y = self.kin.to_xy(square)
        await self.robot.motion.movl(x, y, self.travel_z, 0)

    async def _go_to(self, square: str, z: float) -> None:
        x, y = self.kin.to_xy(square)
        await self.robot.motion.movl(x, y, z, 0)

    async def _grip(self, on: bool) -> None:
        if self.effector == "gripper":
            await self.robot.tool.gripper(on)
        else:
            await self.robot.tool.suction(on)
        await asyncio.sleep(0.4)

    # -- operacoes de jogo -------------------------------------------------

    async def pick(self, square: str) -> None:
        """Pega a peca que esta em `square`."""
        logger.info("[%s] Pegando peca em %s", self.color, square)
        await self._go_above(square)
        await self._go_to(square, self.grip_z)
        await self._grip(True)
        await self._go_above(square)

    async def place(self, square: str) -> None:
        """Solta a peca em `square`."""
        logger.info("[%s] Soltando peca em %s", self.color, square)
        await self._go_above(square)
        await self._go_to(square, self.grip_z)
        await self._grip(False)
        await self._go_above(square)

    async def move_piece(self, from_sq: str, to_sq: str) -> None:
        """Move a propria peca de `from_sq` para `to_sq`."""
        await self.pick(from_sq)
        await self._go_above(to_sq)
        await self.place(to_sq)

    async def remove_captured(self, square: str) -> None:
        """Remove (captura) a peca adversaria em `square`, levando-a a bandeja."""
        logger.info("[%s] Removendo capturada em %s -> bandeja", self.color, square)
        await self.pick(square)
        cx, cy, cz = self.capture
        await self.robot.motion.movl(cx, cy, self.travel_z, 0)
        await self.robot.motion.movl(cx, cy, cz, 0)
        await self._grip(False)
        await self.robot.motion.movl(cx, cy, self.travel_z, 0)

    async def get_pose(self) -> Any:
        return await self.robot.dashboard.get_pose()

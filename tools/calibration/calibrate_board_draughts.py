"""Calibração interativa do tabuleiro de Damas Brasileiras (32 casas jogáveis).

Conecta ao braço Dobot Magician Lite, permite calibrar pelos 4 cantos jogáveis
(A1, G1, B8, H8) ou cantos padrão (A1, H1, A8, H8), interpola as 32 casas
com numeração PDN oficial (1 a 32), permite ajuste fino individual por casa,
e inclui testes de sobrevoo e sucção.

Uso:
    python tools/calibrate_board_draughts.py
    python tools/calibrate_board_draughts.py --port COM5
    python tools/calibrate_board_draughts.py --arm white
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
import time
from pathlib import Path
from typing import Any, Mapping

import yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("calibrate_board_draughts")

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "default.yaml"


# ─── Kinematics Inline ────────────────────────────────────────────────────────

class BoardToRobot:
    """Interpolação bilinear dos 4 cantos com suporte a square_overrides."""

    def __init__(
        self,
        corners: dict[str, dict[str, float]] | None = None,
        square_overrides: dict[str, dict[str, float]] | None = None,
    ):
        self.corners = corners
        self.square_overrides = square_overrides or {}

    @classmethod
    def from_config(cls, cfg: Mapping) -> "BoardToRobot":
        return cls(
            corners=cfg.get("corners"),
            square_overrides=cfg.get("square_overrides"),
        )

    def _indices(self, square: str) -> tuple[int, int]:
        file_idx = ord(square[0].lower()) - ord("a")
        rank_idx = int(square[1]) - 1
        return file_idx, rank_idx

    def to_xyz(self, square: str, fallback_z: float = 0.0) -> tuple[float, float, float]:
        sq_key = square.upper()
        if sq_key in self.square_overrides:
            ov = self.square_overrides[sq_key]
            return float(ov["x"]), float(ov["y"]), float(ov.get("z", fallback_z))

        fx, ry = self._indices(square)
        if self.corners and all(k in self.corners for k in ["A1", "H1", "A8", "H8"]):
            u = fx / 7.0
            v = ry / 7.0
            c = self.corners
            x = (1-u)*(1-v)*c["A1"]["x"] + u*(1-v)*c["H1"]["x"] + (1-u)*v*c["A8"]["x"] + u*v*c["H8"]["x"]
            y = (1-u)*(1-v)*c["A1"]["y"] + u*(1-v)*c["H1"]["y"] + (1-u)*v*c["A8"]["y"] + u*v*c["H8"]["y"]
            z = (1-u)*(1-v)*c["A1"].get("z", fallback_z) + u*(1-v)*c["H1"].get("z", fallback_z) + \
                (1-u)*v*c["A8"].get("z", fallback_z) + u*v*c["H8"].get("z", fallback_z)
            return x, y, z
        return 0.0, 0.0, fallback_z


# ─── Dobot Controller ─────────────────────────────────────────────────────────

try:
    from pydobot import Dobot as Pydobot
    from pydobot.enums import PTPMode
    HAS_PYDOBOT = True
except ImportError:
    HAS_PYDOBOT = False
    Pydobot = None
    PTPMode = None


def find_dobot_ports() -> list[str]:
    import serial.tools.list_ports
    ports = list(serial.tools.list_ports.comports())
    detected: list[str] = []
    for p in ports:
        desc = (p.description or "").lower()
        if any(tok in desc for tok in ("dobot", "usb serial", "ch340", "cp210")):
            detected.append(p.device)
        elif p.device.lower().startswith(("com", "/dev/ttyusb", "/dev/ttyacm")):
            detected.append(p.device)
    return detected


class SimpleDobot:
    """Wrapper simples e robusto sobre pydobot com controle de sucção."""

    def __init__(self, port: str):
        if not HAS_PYDOBOT:
            raise ImportError("pydobot não instalado! Instale com: pip install pydobot")
        self._bot = Pydobot(port=port)
        self.sucking = False

    def get_pose(self) -> tuple[float, float, float, float]:
        p = self._bot.pose()
        return (float(p[0]), float(p[1]), float(p[2]), float(p[3]))

    def move_to(self, x: float, y: float, z: float, r: float = 0.0, wait: bool = True):
        self._bot._set_ptp_cmd(x, y, z, r, mode=PTPMode.MOVL_XYZ, wait=wait)

    def home(self):
        self._bot._set_ptp_cmd(227.53, 0.0, 140.83, 0.0, mode=PTPMode.MOVJ_XYZ, wait=True)

    def toggle_suction(self) -> bool:
        self.sucking = not self.sucking
        self._bot.suck(self.sucking)
        return self.sucking

    def set_suction(self, enable: bool):
        self.sucking = enable
        self._bot.suck(enable)

    def close(self):
        try:
            self.set_suction(False)
            self._bot.close()
        except Exception:
            pass


# ─── Casas de Damas e Mapeamento PDN (1 a 32) ─────────────────────────────────

# 32 casas jogáveis de damas brasileiras (casas escuras)
DRAUGHTS_SQUARES: list[str] = []
PDN_TO_SQUARE: dict[int, str] = {}
SQUARE_TO_PDN: dict[str, int] = {}

_pdn = 1
for _rank in range(1, 9):
    for _file_idx in range(8):
        _col = chr(ord('a') + _file_idx)
        _sq = f"{_col}{_rank}"
        if (_file_idx + _rank) % 2 == 1:
            DRAUGHTS_SQUARES.append(_sq)
            PDN_TO_SQUARE[_pdn] = _sq
            SQUARE_TO_PDN[_sq] = _pdn
            _pdn += 1

ALL_SQUARES = [f"{chr(ord('a')+f)}{r}" for r in range(1, 9) for f in range(8)]


# ─── Helpers de Configuração ──────────────────────────────────────────────────

def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def save_config(config: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, sort_keys=False, default_flow_style=False)


def print_banner():
    print("\n" + "=" * 65)
    print("   CALIBRADOR DE TABULEIRO - DAMAS BRASILEIRAS (32 CASAS)  ")
    print("   Braço Robótico Dobot Magician Lite")
    print("=" * 65)


def print_draughts_board(coords: dict[str, tuple[float, float, float]], overrides: dict[str, dict[str, float]] | None = None):
    overrides = overrides or {}
    print("\n" + "=" * 65)
    print("  TABELA DAS 32 CASAS JOGÁVEIS DE DAMAS (PDN 1 A 32)")
    print("=" * 65)
    print(f"{'PDN':>4} {'Casa':>5} {'X (mm)':>10} {'Y (mm)':>10} {'Z (mm)':>10} {'Status':>12}")
    print("-" * 60)
    for pdn in range(1, 33):
        sq = PDN_TO_SQUARE[pdn]
        if sq in coords:
            x, y, z = coords[sq]
            status = "* Ajustado" if sq.upper() in overrides else "Interpolado"
            print(f"{pdn:>4} {sq:>5}   {x:>8.2f}   {y:>8.2f}   {z:>8.2f}   {status:>12}")
        if pdn % 4 == 0 and pdn < 32:
            print("-" * 60)


def calibrate_point_interactive(bot: SimpleDobot, point_name: str) -> tuple[float, float, float]:
    """Modo interativo para posicionar o braço com jog e gravar com ENTER."""
    step = 5.0
    pose = bot.get_pose()

    print(f"\n--- Posicionamento: {point_name} ---")
    print(f"  Posição atual: X={pose[0]:.2f}  Y={pose[1]:.2f}  Z={pose[2]:.2f}")
    print("  Comandos de Jog:")
    print("    w/s = +Y / -Y  |  a/d = -X / +X  |  q/e = +Z / -Z")
    print("    1/2/3 = passo (1mm / 5mm / 10mm)")
    print("    b = ligar/desligar sucção (teste de pega da peça)")
    print("    p = exibir posição atual")
    print("    ENTER = confirmar e gravar este ponto")
    print()

    while True:
        raw = input(f"  [{point_name}] > ").strip().lower()

        if raw == "":
            pose = bot.get_pose()
            x, y, z = pose[0], pose[1], pose[2]
            print(f"  [OK] {point_name} gravado: X={x:.2f}  Y={y:.2f}  Z={z:.2f}")
            return (x, y, z)
        elif raw == "p":
            pose = bot.get_pose()
            print(f"  Posição: X={pose[0]:.2f}  Y={pose[1]:.2f}  Z={pose[2]:.2f}")
        elif raw == "b":
            state = bot.toggle_suction()
            print(f"  Bomba de sucção: {'LIGADA' if state else 'DESLIGADA'}")
        elif raw == "1":
            step = 1.0; print(f"  Passo: {step}mm")
        elif raw == "2":
            step = 5.0; print(f"  Passo: {step}mm")
        elif raw == "3":
            step = 10.0; print(f"  Passo: {step}mm")
        elif raw in ("w", "s", "a", "d", "q", "e"):
            pose = bot.get_pose()
            x, y, z = pose[0], pose[1], pose[2]
            if raw == "w": y += step
            elif raw == "s": y -= step
            elif raw == "a": x -= step
            elif raw == "d": x += step
            elif raw == "q": z += step
            elif raw == "e": z -= step
            bot.move_to(x, y, z)
            print(f"  -> X={x:.2f}  Y={y:.2f}  Z={z:.2f}")
        else:
            print(f"  Comando desconhecido: '{raw}'")


# ─── Loop Principal ───────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Calibrador interativo do tabuleiro 8x8 para Damas Brasileiras."
    )
    parser.add_argument("--port", default=None, help="Porta serial (ex: COM5)")
    parser.add_argument("--arm", default="white", choices=["white", "black"],
                        help="Qual braço calibrar (default: white)")
    args = parser.parse_args()

    print_banner()

    config = load_config()
    arm_color = args.arm

    port = args.port
    if not port:
        arm_cfg = config.get("arms", {}).get(arm_color, {})
        port = arm_cfg.get("serial_port", "auto")
    if not port or port == "auto":
        ports = find_dobot_ports()
        if not ports:
            print("\n[ERRO] Nenhuma porta serial Dobot encontrada! Verifique o cabo USB e a alimentação.")
            return 1
        port = ports[0]

    print(f"\n  Braço selecionado: {arm_color.upper()}")
    print(f"  Porta serial:     {port}")

    print("\n  Conectando ao Dobot...")
    try:
        bot = SimpleDobot(port)
    except Exception as exc:
        print(f"\n[ERRO] Falha ao conectar no Dobot: {exc}")
        return 1
    print("  [OK] Conectado com sucesso!")

    try:
        print("\n  Movendo para posição HOME...")
        bot.home()
        pose = bot.get_pose()
        print(f"  Posição HOME: X={pose[0]:.2f}  Y={pose[1]:.2f}  Z={pose[2]:.2f}")

        while True:
            print("\n" + "=" * 55)
            print("                MENU DE CALIBRAÇÃO")
            print("=" * 55)
            print("  1. Calibrar 4 extremos jogáveis de DAMAS (A1, G1, B8, H8) [Recomendado]")
            print("  2. Calibrar 4 cantos padrão 8x8 (A1, H1, A8, H8)")
            print("  3. Ver coordenadas das 32 casas jogáveis (PDN 1 a 32)")
            print("  4. Testar sobrevoo nas 32 casas de damas")
            print("  5. Testar casa específica (ir até a casa e testar pega)")
            print("  6. Ajuste fino individual de uma casa (corrigir Z/X/Y)")
            print("  7. Modo Jog livre (movimentação manual e bomba)")
            print("  8. Calibrar bandeja de captura")
            print("  9. Salvar configuração em config/default.yaml")
            print("  0. Sair")
            print()

            choice = input("  Opção > ").strip()

            if choice == "1":
                # Calibrar 4 extremos jogáveis de damas: A1, G1, B8, H8
                print("\n=== CALIBRAÇÃO PELOS 4 EXTREMOS JOGÁVEIS DE DAMAS ===")
                print("  Você irá posicionar o robô apenas nas casas jogáveis dos cantos:")
                print("    - A1: Linha 1, canto esquerdo (PDN 1)")
                print("    - G1: Linha 1, canto direito jogável (PDN 4)")
                print("    - B8: Linha 8, canto esquerdo jogável (PDN 29)")
                print("    - H8: Linha 8, canto direito (PDN 32)")
                print("  As coordenadas dos cantos 8x8 serão extrapoladas automaticamente.")

                arm_cfg = config.setdefault("arms", {}).setdefault(arm_color, {})
                existing_corners = arm_cfg.get("corners", {})

                pts = {}
                for pt_name, pdn_info in [("A1", "PDN 1"), ("G1", "PDN 4"), ("B8", "PDN 29"), ("H8", "PDN 32")]:
                    print(f"\n--- Casa {pt_name} ({pdn_info}) ---")
                    xyz = calibrate_point_interactive(bot, f"{pt_name} ({pdn_info})")
                    pts[pt_name] = xyz

                # Extrapolação dos 4 cantos 8x8 geométricos:
                # Linha 1: A1 está em u=0, G1 está em u=6/7. H1 (u=1) = A1 + (7/6)*(G1 - A1)
                # Linha 8: B8 está em u=1/7, H8 está em u=7/7. A8 (u=0) = H8 + (7/6)*(B8 - H8)
                a1 = pts["A1"]
                g1 = pts["G1"]
                b8 = pts["B8"]
                h8 = pts["H8"]

                h1_x = a1[0] + (7.0 / 6.0) * (g1[0] - a1[0])
                h1_y = a1[1] + (7.0 / 6.0) * (g1[1] - a1[1])
                h1_z = a1[2] + (7.0 / 6.0) * (g1[2] - a1[2])

                a8_x = h8[0] + (7.0 / 6.0) * (b8[0] - h8[0])
                a8_y = h8[1] + (7.0 / 6.0) * (b8[1] - h8[1])
                a8_z = h8[2] + (7.0 / 6.0) * (b8[2] - h8[2])

                corners_to_save = {
                    "A1": {"x": float(a1[0]), "y": float(a1[1]), "z": float(a1[2])},
                    "H1": {"x": float(h1_x), "y": float(h1_y), "z": float(h1_z)},
                    "A8": {"x": float(a8_x), "y": float(a8_y), "z": float(a8_z)},
                    "H8": {"x": float(h8[0]), "y": float(h8[1]), "z": float(h8[2])},
                }

                arm_cfg["corners"] = corners_to_save
                # Altura de pega média
                avg_grip_z = (a1[2] + g1[2] + b8[2] + h8[2]) / 4.0
                arm_cfg["grip_z"] = float(round(avg_grip_z, 2))

                print("\n  [OK] Extrapolação concluída com sucesso!")
                print(f"  Grip Z estimado: {arm_cfg['grip_z']:.2f} mm")
                save_config(config)
                print(f"  [OK] Configuração salva em {CONFIG_PATH}")
                bot.home()

            elif choice == "2":
                # Calibrar 4 cantos padrão 8x8 (A1, H1, A8, H8)
                arm_cfg = config.setdefault("arms", {}).setdefault(arm_color, {})
                existing_corners = arm_cfg.get("corners", {})
                corners = {}

                for corner in ["A1", "H1", "A8", "H8"]:
                    if corner in existing_corners:
                        ec = existing_corners[corner]
                        print(f"\n  {corner} atual: X={ec['x']:.2f}  Y={ec['y']:.2f}  Z={ec['z']:.2f}")
                        raw2 = input(f"  Recalibrar {corner}? (s/N) > ").strip().lower()
                        if raw2 != "s":
                            corners[corner] = (ec["x"], ec["y"], ec["z"])
                            continue
                        bot.move_to(ec["x"], ec["y"], ec["z"] + 30)

                    xyz = calibrate_point_interactive(bot, corner)
                    corners[corner] = xyz

                arm_cfg.setdefault("corners", {})
                for corner, (x, y, z) in corners.items():
                    arm_cfg["corners"][corner] = {
                        "x": float(x), "y": float(y), "z": float(z)
                    }

                save_config(config)
                print(f"\n  [OK] 4 cantos calibrados e salvos em {CONFIG_PATH}!")
                bot.home()

            elif choice == "3":
                arm_cfg = config.get("arms", {}).get(arm_color, {})
                kin = BoardToRobot.from_config(arm_cfg)
                if not kin.corners:
                    print("\n  [AVISO] Nenhum canto calibrado ainda! Execute a opção 1 primeiro.")
                    continue
                grip_z = float(arm_cfg.get("grip_z", 8.0))
                coords = {sq: kin.to_xyz(sq, grip_z) for sq in DRAUGHTS_SQUARES}
                print_draughts_board(coords, arm_cfg.get("square_overrides"))

            elif choice == "4":
                arm_cfg = config.get("arms", {}).get(arm_color, {})
                kin = BoardToRobot.from_config(arm_cfg)
                if not kin.corners:
                    print("\n  [AVISO] Nenhum canto calibrado! Execute a opção 1 primeiro.")
                    continue

                grip_z = float(arm_cfg.get("grip_z", 8.0))
                travel_z = float(arm_cfg.get("travel_z", 100.0))

                print("\n  Modo de teste: Sobrevoar as 32 casas jogáveis de damas.")
                pause_each = input("  Deseja pausar com descida até o Z de pega em cada casa? (s/N) > ").strip().lower() == "s"

                print("  Iniciando em 2 segundos... (Ctrl+C para interromper)\n")
                time.sleep(2)

                try:
                    for i, sq in enumerate(DRAUGHTS_SQUARES, 1):
                        pdn = SQUARE_TO_PDN[sq]
                        x, y, z = kin.to_xyz(sq, grip_z)
                        safe_z = max(travel_z, z + 50.0)

                        print(f"  [{i:2d}/32] PDN {pdn:2d} ({sq}): X={x:.2f} Y={y:.2f} Z={safe_z:.2f}")
                        bot.move_to(x, y, safe_z)

                        if pause_each:
                            bot.move_to(x, y, z)
                            ans = input(f"    -> Em {sq} (PDN {pdn}) no Z={z:.2f}. ENTER para próxima, ou 's' para parar: ").strip().lower()
                            bot.move_to(x, y, safe_z)
                            if ans == "s":
                                break
                        else:
                            time.sleep(0.4)
                except KeyboardInterrupt:
                    print("\n  Sobrevoo interrompido.")

                print("\n  Retornando ao HOME...")
                bot.home()

            elif choice == "5":
                arm_cfg = config.get("arms", {}).get(arm_color, {})
                kin = BoardToRobot.from_config(arm_cfg)
                if not kin.corners:
                    print("\n  [AVISO] Nenhum canto calibrado! Execute a opção 1 primeiro.")
                    continue

                grip_z = float(arm_cfg.get("grip_z", 8.0))
                travel_z = float(arm_cfg.get("travel_z", 100.0))

                raw2 = input("  Informe a casa (ex: a1, c3, h8) ou o número PDN (1 a 32) > ").strip().lower()
                try:
                    pdn_num = int(raw2)
                    if 1 <= pdn_num <= 32:
                        raw2 = PDN_TO_SQUARE[pdn_num]
                except ValueError:
                    pass

                if raw2 in DRAUGHTS_SQUARES:
                    pdn = SQUARE_TO_PDN[raw2]
                    x, y, z = kin.to_xyz(raw2, grip_z)
                    safe_z = max(travel_z, z + 50.0)

                    print(f"\n  -> Casa {raw2.upper()} (PDN {pdn}): X={x:.2f}  Y={y:.2f}  Z(grip)={z:.2f}")
                    ans = input("  Mover robô até a casa? (s/N) > ").strip().lower()
                    if ans == "s":
                        print(f"  Sobrevoando {raw2.upper()}...")
                        bot.move_to(x, y, safe_z)
                        ans2 = input("  Descer até a altura de pega (Z)? (s/N) > ").strip().lower()
                        if ans2 == "s":
                            bot.move_to(x, y, z)
                            print("  Robô posicionado na casa!")
                            print("  Comandos: 'b' para testar sucção | ENTER para subir")
                            while True:
                                sub_cmd = input("    [teste] > ").strip().lower()
                                if sub_cmd == "b":
                                    s = bot.toggle_suction()
                                    print(f"    Bomba: {'LIGADA' if s else 'DESLIGADA'}")
                                else:
                                    break
                            bot.set_suction(False)
                            bot.move_to(x, y, safe_z)
                else:
                    print(f"  [ERRO] Casa inválida ou não jogável: '{raw2}'")

            elif choice == "6":
                # Ajuste fino de uma casa específica
                arm_cfg = config.setdefault("arms", {}).setdefault(arm_color, {})
                kin = BoardToRobot.from_config(arm_cfg)
                if not kin.corners:
                    print("\n  [AVISO] Nenhum canto calibrado! Execute a opção 1 primeiro.")
                    continue

                grip_z = float(arm_cfg.get("grip_z", 8.0))
                travel_z = float(arm_cfg.get("travel_z", 100.0))

                raw2 = input("  Qual casa ajustar? (ex: 1 a 32 ou c3) > ").strip().lower()
                try:
                    pdn_num = int(raw2)
                    if 1 <= pdn_num <= 32:
                        raw2 = PDN_TO_SQUARE[pdn_num]
                except ValueError:
                    pass

                if raw2 in DRAUGHTS_SQUARES:
                    pdn = SQUARE_TO_PDN[raw2]
                    sq_key = raw2.upper()
                    cur_x, cur_y, cur_z = kin.to_xyz(raw2, grip_z)
                    print(f"\n  Ajuste fino da casa {sq_key} (PDN {pdn})")
                    print(f"  Coordenada inicial: X={cur_x:.2f}  Y={cur_y:.2f}  Z={cur_z:.2f}")

                    # Mover até a casa
                    safe_z = max(travel_z, cur_z + 40.0)
                    bot.move_to(cur_x, cur_y, safe_z)
                    bot.move_to(cur_x, cur_y, cur_z)

                    new_xyz = calibrate_point_interactive(bot, f"Ajuste {sq_key} (PDN {pdn})")
                    bot.move_to(new_xyz[0], new_xyz[1], safe_z)

                    arm_cfg.setdefault("square_overrides", {})
                    arm_cfg["square_overrides"][sq_key] = {
                        "x": float(new_xyz[0]), "y": float(new_xyz[1]), "z": float(new_xyz[2])
                    }
                    save_config(config)
                    print(f"  [OK] Casa {sq_key} gravada com sucesso em overrides!")
                else:
                    print(f"  [ERRO] Casa inválida: '{raw2}'")

            elif choice == "7":
                step = 5.0
                print("\n=== MODO JOG MANUAL LIVRE ===")
                print("  Comandos:")
                print("    w/s = +Y / -Y  |  a/d = -X / +X  |  q/e = +Z / -Z")
                print("    1/2/3 = passo (1mm / 5mm / 10mm)")
                print("    b = ligar/desligar bomba de sucção")
                print("    p = ler coordenadas atuais  |  x = sair do jog")
                print()
                while True:
                    raw2 = input("  [jog] > ").strip().lower()
                    if raw2 == "x":
                        break
                    elif raw2 == "p":
                        pose = bot.get_pose()
                        print(f"  Pose: X={pose[0]:.2f}  Y={pose[1]:.2f}  Z={pose[2]:.2f}")
                    elif raw2 == "b":
                        s = bot.toggle_suction()
                        print(f"  Sucção: {'LIGADA' if s else 'DESLIGADA'}")
                    elif raw2 == "1":
                        step = 1.0; print(f"  Passo: {step}mm")
                    elif raw2 == "2":
                        step = 5.0; print(f"  Passo: {step}mm")
                    elif raw2 == "3":
                        step = 10.0; print(f"  Passo: {step}mm")
                    elif raw2 in ("w", "s", "a", "d", "q", "e"):
                        pose = bot.get_pose()
                        x, y, z = pose[0], pose[1], pose[2]
                        if raw2 == "w": y += step
                        elif raw2 == "s": y -= step
                        elif raw2 == "a": x -= step
                        elif raw2 == "d": x += step
                        elif raw2 == "q": z += step
                        elif raw2 == "e": z -= step
                        bot.move_to(x, y, z)
                        print(f"  -> X={x:.2f}  Y={y:.2f}  Z={z:.2f}")

            elif choice == "8":
                print("\n=== CALIBRAÇÃO DA BANDEJA DE CAPTURA ===")
                print("  Posicione a ventosa sobre o centro da bandeja de descarte de peças.")
                cap_xyz = calibrate_point_interactive(bot, "BANDEJA DE CAPTURA")
                arm_cfg = config.setdefault("arms", {}).setdefault(arm_color, {})
                arm_cfg["capture_x"] = float(cap_xyz[0])
                arm_cfg["capture_y"] = float(cap_xyz[1])
                arm_cfg["capture_z"] = float(cap_xyz[2])
                save_config(config)
                print(f"  [OK] Coordenadas da bandeja salvas em {CONFIG_PATH}!")
                bot.home()

            elif choice == "9":
                save_config(config)
                print(f"\n  [OK] Configuração salva com sucesso em {CONFIG_PATH}")

            elif choice == "0":
                break
            else:
                print(f"  Opção inválida: '{choice}'")

    except KeyboardInterrupt:
        print("\n\n  Operação interrompida pelo usuário.")
    finally:
        print("\n  Desconectando Dobot...")
        bot.close()
        print("  [OK] Conexão encerrada.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

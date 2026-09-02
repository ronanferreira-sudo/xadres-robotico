# Xadrez Robótico

Sistema onde **dois braços robóticos Dobot Magician Lite** jogam xadrez
controlados por **Inteligência Artificial**, usando **visão computacional**
(câmeras) para identificar o estado do tabuleiro após cada jogada. Ao final,
um dos lados vence.

```
                 ┌──────────────┐      ┌──────────────┐
   Câmera ───────▶│   Visão      │      │   Xadrez     │◀─── decide lance (I.A.)
                 │ (detector)   │─────▶│  (engine)    │
                 └──────────────┘      └──────┬───────┘
                                              │ plano de ações
                                 ┌────────────┴────────────┐
                            Braço Branco              Braço Preto
                         (Magician Lite)           (Magician Lite)
```

## Arquitetura

| Módulo | Responsabilidade |
|--------|------------------|
| `xadrez_robotico/chess/` | Estado do tabuleiro (`BoardState`) e motor de I.A. (`engine.py`). Usa **Stockfish** se disponível, senão cai para **minimax** com poda alfa-beta. |
| `xadrez_robotico/vision/` | Câmera (real via OpenCV ou simulada), detector de ocupação/cor por subtração de fundo e calibração quadrado↔pixel. |
| `xadrez_robotico/robot/` | Cinemática (quadrado → coordenada do robô) e `Arm` (pegar/transportar/soltar com ventosa ou garra). |
| `xadrez_robotico/dobot/` | Driver vendorizado do Magician Lite (USB via `pydobot` ou WebSocket/RPC). Reutilizado de projetos Dobot existentes. |
| `xadrez_robotico/game/` | Orquestrador da partida: turnos, planejamento de ações (movimento + captura + roque + promoção) e verificação com a visão. |
| `xadrez_robotico/cli.py` | Interface de linha de comando (`play`, `detect`, `calibrate`). |

## Pré-requisitos

- Python 3.10+
- Braços **Dobot Magician Lite** (um por cor) com drivers/SDK instalados
- Câmera (webcam) para a visão
- Opcional: binário **Stockfish** no `PATH` para a I.A. mais forte

## Instalação

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows
pip install -r requirements.txt
pip install -e .                  # registra o comando `xadrez`
```

## Uso

### Simulação (sem hardware)

Roda a partida inteira em software, com a "visão" lendo o tabuleiro real
(útil para desenvolvimento e testes):

```bash
xadrez play --mode simulation
```

### Hardware (braços + câmeras reais)

1. **Calibre a câmera** (centro em pixels dos 4 cantos do tabuleiro):
   ```bash
   xadrez calibrate --output config/calibration.yaml
   ```
   Tire uma foto do tabuleiro **vazio** e aponte `empty_reference` no YAML gerado.

2. **Jogue com hardware**:
   ```bash
   xadrez play --mode hardware --calibration config/calibration.yaml
   ```

3. **Teste só a detecção** da câmera:
   ```bash
   xadrez detect --calibration config/calibration.yaml
   ```

A configuração geral fica em `config/default.yaml` (portas seriais, origem e
espaçamento de cada braço, alturas de pegar/soltar, nível dos jogadores, etc.).

## Teste com 1 robô e tabuleiro 4x4

Enquanto o tabuleiro grande (8x8) não está disponível, dá para testar com um
único braço e um tabuleiro 4x4 (variante "Silverman 4x4 chess": Torre, Cavalo,
Bispo, Rei e 4 peões por lado, sem roque).

1. **Simule a partida 4x4** (sem hardware, valida o motor 4x4):
   ```bash
   xadrez play --config config/hardware-4x4.yaml --mode simulation
   ```

2. **Calibre a câmera** para o tabuleiro 4x4 (cantos a1, a4, d1, d4):
   ```bash
   xadrez calibrate --config config/hardware-4x4.yaml
   ```
   Tire uma foto do tabuleiro vazio e aponte `empty_reference` no YAML gerado.

3. **Rode com hardware** (o único braço move as duas cores):
   ```bash
   xadrez play --config config/hardware-4x4.yaml --calibration config/calibration.yaml
   ```

No modo de 1 braço, o mesmo robô faz o lance da cor da vez E recolhe as peças
capturadas para a bandeja (`arms.black.enabled: false`). A dimensão do tabuleiro
é definida por `board.squares` (`8` ou `4`); o motor usa Stockfish no 8x8 e o
minimax no 4x4 (com detecção de empate por repetição tripla e regra dos 50 lances).

## Como funciona um lance

1. A I.A. do jogador da vez escolhe o melhor lance legal.
2. O orquestrador (`Match`) calcula o **delta** do tabuleiro e gera ações:
   - `move` — o braço da cor move a peça de → para;
   - `capture` — o braço **adversário** retira a peça capturada para a sua bandeja.
   (Roque e promoção são tratados genericamente por diferença de tabuleiro.)
3. Os braços executam as ações fisicamente (ventosa/garra).
4. A câmera reconfere o tabuleiro; divergências são registradas em log.
5. Repete até xeque-mate, empate ou fim de jogo — **um dos lados vence**.

## Limitações conhecidas / evoluções

- A visão detecta **ocupação e cor**, mas não o **tipo** da peça (rei, torre…).
  Próximo passo: templates por peça ou modelo treinado.
- Promoção física move a peça, mas não troca o modelo (ex.: peão→dama).
- A cinemática assume tabuleiro plano e alinhado (transformada rígida); para
  desalinhamentos maiores, usar homografia de 4 pontos.
- No tabuleiro 4x4 não há roque, e o en passant não chega a ocorrer na prática
  (os peões começam frente a frente, então não sobra avanço duplo adjacente).

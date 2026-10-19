# Thermaltake Assassin 120 Digital — driver/daemon Nuvoton (`0416:8001`)

Driver userspace open-source (Windows e Linux) para o **display de 84 LEDs RGB** do cooler
**Thermaltake Assassin 120 Digital**, controlado por um HID Nuvoton
(`VID 0x0416 / PID 0x8001`, "HID Transfer").

Projeto independente, feito por engenharia reversa do protocolo e validado no hardware.
Não é afiliado à Thermaltake nem à Nuvoton.

## Status

| Frente | Estado |
|---|---|
| Display de segmentos (números reais de CPU/GPU) | ✅ funcionando, validado ao vivo (Windows) |
| Mapa de LEDs, 7-seg, cores por grupo/segmento | ✅ 100% decodificado |
| Letras, animações, efeitos, modos extras | ✅ funcionando |
| Port Linux (módulo de kernel + daemon) | 🟡 código completo, verificado offline; falta validar em hardware Linux |
| Protocolo | ✅ fechado: init + frame de LEDs + query de identidade (sem comandos escondidos) |

## Setup do produto

- **Cooler**: Thermaltake Assassin 120 Digital (torre dupla, 2 fans).
- **Display**: corrente de **84 LEDs RGB** atrás de um difusor segmentado — 4 grupos de
  7 segmentos (temp/uso de CPU e GPU), indicadores `°C/°F`, `%` e os LEDs 0/1 e 82/83
  (difusor escrito CPU/GPU, bicolor).
- **Controlador**: HID Nuvoton `0416:8001` ("HID Transfer"), endpoints OUT `0x02` / IN `0x81`,
  pacotes de 64 B; o device é **write-only** para estado (só responde ao query de identidade).
- **Conexão**: cabo USB interno do cooler ligado a um header USB 2.0 da placa-mãe.
  - **Windows**: reconhece como HID padrão, sem driver adicional.
  - **Linux**: aparece como `/dev/hidraw*` (a regra udev do repo libera o acesso).
- **Software oficial**: TRCC (Thermaltake RGB Control Center). Ele reescreve o display a cada
  ~160 ms — **mantenha-o fechado** enquanto o daemon roda.

> Não confundir com os modelos "LCD 480×480" da mesma família de software: este cooler usa
> **apenas** o protocolo de LEDs (`DA DB DC DD`), não há segundo protocolo.

## Funcionalidades

- **Daemon em tempo real** (`nuvoton_daemon.py --mode display`): temperaturas e uso de CPU/GPU
  nos dígitos, com gradiente de cor por faixa; log 1:1 dos valores enviados.
- **Modos**: `display`, `zones`, `cpu_temp`, `gpu_temp`, `cpu_usage`, `gpu_usage`, `fire`, `vibe`.
- **Letras no 7-seg** (`lcd_sender.py --anim`): `HELP`, `HOT`, `Err` etc. (`LETTER_MASK`).
- **Efeitos/brinquedos**: heartbeat, blink, `--scroll` (marquee nos 10 dígitos),
  `--chase` (arco-íris), `--starfield`, `--clock`, `--beacon` (transmissão óptica com CRC32),
  `--image` (fax por coluna).
- **Ferramentas**: `--query` (handshake), `--replay` (frames reais da TRCC),
  `--demo`, `--probe` (mapa LED a LED), `--off`.

## Como funciona (resumo do protocolo)

- Magic único: `DA DB DC DD` (`PM=0x10`, `SUB=0x10`).
- Frame: **20 B de header + 252 B RGB (84 LEDs) = 272 B**, enviado em **5 relatórios de 64 B**
  (`type=0x02`, `length=0x00FC`).
- Init: `DA DB DC DD 00 00 00 00 00 00 00 00 01 00 00 00 00 00 00 00`.
- Brilho é software (escala de cor); °F é troca de LED no mesmo frame; animação é sequência de
  frames. A TRCC roda a ~6,7 fps; o display aceita ~100 fps.
- Backend: `NUVOTON_BACKEND=hidraw|hidapi` (auto = hidraw no Linux, hidapi no Windows).

### Mapa do display (validado)

| LEDs | Grupo |
|---|---|
| 0, 1 | Indicador CPU |
| 2–22 | CPU temp — 3 dígitos (7 LEDs cada) |
| 23 / 24 | °C / °F |
| 25–40 | CPU uso — 2 dígitos (+ 2 blanks < 100) |
| 41 / 42 | `%` CPU / `%` GPU |
| 43–58 | GPU uso — 2 dígitos (espelhado) |
| 59 / 60 | °C / °F |
| 61–81 | GPU temp — 3 dígitos (espelhado) |
| 82, 83 | Indicador GPU |

Ordem dos segmentos por dígito: **F, A, B, G, E, D, C**.
Pixels livres usados para status/efeitos: 25/26, 57/58 e 24/60 (°F).

## Estrutura

- `linux-driver/` — porta Linux: módulo de kernel (`nuvoton-rgb.c`), build/install, regra udev, systemd.
- `linux-driver/python-lib/` — biblioteca e daemon:
  - `nuvoton_hid.py` — transporte HID (hidapi no Windows / hidraw no Linux) e mapa LED_*
  - `lcd_sender.py` — frames do display (`DIGIT_MASK`, `build_metrics_frame`, animações)
  - `hardware_monitor.py` — sensores (LibreHardwareMonitor no Windows; hwmon/DRM no Linux)
  - `nuvoton_daemon.py` — daemon (`--mode display`)
  - `test_hidraw_offline.py` — testes offline do port Linux
  - demais `*.py` — probes/ferramentas de engenharia reversa (histórico do trabalho)
- `NEXT_SESSION_START_HERE.md`, `PROGRESS.md`, `CODEBASE_STATE.md` — estado e notas de sessão.

## Instalação

### Windows

1. Python 3.10+ e [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor):
   baixe o release e extraia em `linux-driver/python-lib/lhm/pkg2/`
   (precisa de `LibreHardwareMonitorLib.dll`).
2. Dependências Python:
   ```powershell
   pip install -r linux-driver\python-lib\requirements.txt
   ```
3. O HID usa o driver padrão do Windows (não precisa de Zadig).
4. Rode o daemon **elevado** (CPU temp via MSR):
   ```powershell
   cd linux-driver\python-lib
   python nuvoton_daemon.py --mode display
   ```

### Linux

O daemon **não precisa** do módulo de kernel: usa o backend `hidraw` (puro stdlib) em
`/dev/hidraw*` e lê sensores via `hwmon`/DRM. O módulo + sysfs é opcional.

```bash
# dependências (Ubuntu/Debian)
sudo apt install python3 python3-pip
cd linux-driver
sudo ./build.sh          # módulo + udev + ferramentas (manual: ver INSTALL.md)
cd python-lib
pip3 install -r requirements.txt
python3 lcd_sender.py --query     # handshake: deve mostrar PM=0x10
python3 nuvoton_daemon.py --mode display
```

Instalação manual, regras udev, systemd e troubleshooting: **[linux-driver/INSTALL.md](linux-driver/INSTALL.md)**.

## Notas do repositório

- `python-lib/lhm/` (LibreHardwareMonitor, ~44 MB) **não é versionado**: baixe o release e
  extraia em `python-lib/lhm/pkg2/`.
- Artefatos pesados de engenharia reversa ficam fora do git (ver `.gitignore`): `TRCC_decomp.il`,
  `*.resources`, `strings_*.txt`, capturas `shareMemory_*.bin`, logs de runtime.
- Fixture mantida: `python-lib/trcc_capture_frames.bin` (usada por `lcd_sender.py --replay`).

## Aviso

Engenharia reversa feita para interoperabilidade com hardware próprio. Sem garantias; use por
sua conta e risco. O dispositivo é write-only e o pior caso observado é o display apagar
(recuperável com `lcd_sender.py --init` ou replug do USB).

## Licença

MIT — ver [LICENSE](LICENSE).

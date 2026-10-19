# helpmeplease — Nuvoton PA120 DIGITAL (Thermalright)

Driver/daemon para o display segmentado + ARGB do cooler Thermalright PA120 DIGITAL
(controlador Nuvoton/HID `0416:8001`, "HID Transfer").

## Estrutura

- `linux-driver/` — porta Linux: módulo de kernel (`nuvoton-rgb.c`), build/install, regra udev, systemd
- `linux-driver/python-lib/` — biblioteca e daemon userspace:
  - `nuvoton_hid.py` — transporte HID (hidapi no Windows / hidraw no Linux)
  - `lcd_sender.py` — frames do display (84 LEDs, 7-seg, `DIGIT_MASK`, `build_metrics_frame`)
  - `hardware_monitor.py` — sensores (LibreHardwareMonitor no Windows; sysfs no Linux)
  - `nuvoton_daemon.py` — daemon `--mode display` (leitura contínua + log 1:1)
  - demais `*.py` — probes/ferramentas de engenharia reversa (histórico do trabalho)
- `*.md` na raiz — estado do projeto e notas de sessão

## Rodar o daemon (Windows)

    python nuvoton_daemon.py --mode display     # requer elevação p/ CPU temp (MSR)

## Notas do repositório

- `python-lib/lhm/` (LibreHardwareMonitor, ~44 MB) **não é versionado**: baixe o release do
  LibreHardwareMonitor e extraia em `python-lib/lhm/pkg2/` (precisa de `LibreHardwareMonitorLib.dll`).
- Artefatos pesados de engenharia reversa também ficam fora do git (ver `.gitignore`):
  `TRCC_decomp.il`, `*.resources`, `strings_*.txt`, capturas `shareMemory_*.bin`, logs de runtime.
- Fixture mantida: `python-lib/trcc_capture_frames.bin` (usada por `lcd_sender.py --replay`).

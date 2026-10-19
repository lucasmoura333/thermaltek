# TRCC Reverse Engineering — Progress Tracker

**Dispositivo**: Nuvoton HID Transfer — VID `0x0416` / PID `0x8001`  
**Objetivo**: Controle RGB + display no Windows/Linux reproduzindo o protocolo do TRCC  
**Status**: LED + display 100% funcionando no Windows; port Linux com código completo e verificado offline  
**Last Updated**: Session 10 — transporte hidraw (Linux) + sensores hwmon implementados, testados offline (16/16), systemd/docs fechados

---

## O QUE O DISPOSITIVO FAZ — ARQUITETURA REAL

O cooler usa **um único subsistema USB**, controlado inteiramente pelo TRCC.exe via HID Output Report (magic `DA DB DC DD`):

1. **84 LEDs** que na verdade formam um **display de 7 segmentos** (3 dígitos CPU temp, 2 CPU uso, 2 GPU uso, 3 GPU temp) + LEDs de indicador/°C/% — **não** é um LCD de pixels.
2. Protocolo: header de 20 bytes + 252 bytes RGB (84 LEDs × 3), enviado em 5 relatórios HID de 64 bytes no EP 0x02.

### Por que a premissa antiga de "LCD 480x480 / USBLCDNEW" caiu (evidência tripla)

- **Pcaps antigos** (`tharmal.pcap`, `teste1`): somente frames `DA DB DC DD` — nenhum magic `12 34 56 78`, nenhum JPEG.
- **Captura fresca** (USBPcap3, 8 s, TRCC aberto): 51 updates LED; EP 0x81 mudo; nenhum outro magic em parte alguma.
- **`USBLCDNEW.dll`**: não trata PID 0x8001 (nenhum handler); o driver Windows do device é `HidUsb` puro; `shareMemory_ImageRGB` fica zerada enquanto os números aparecem no display.

### Mapa do display (84 LEDs, handshake PM=0x10 → PA120 / Assassin 120 Digital)

| LEDs | Grupo |
|------|-------|
| 0, 1 | Indicador CPU |
| 2–22 | CPU temp — 3 dígitos, esquerda→direita (7 LEDs cada) |
| 23 / 24 | °C / °F |
| 25–40 | CPU uso — 2 dígitos (+ 2 blanks à esquerda quando < 100) |
| 41 / 42 | % CPU / % GPU |
| 43–58 | GPU uso — 2 dígitos (ordem espelhada) |
| 59 / 60 | °C / °F |
| 61–81 | GPU temp — 3 dígitos, esquerda→direita (ordem espelhada) |
| 82, 83 | Indicador GPU |

Segmentos dentro de cada dígito: ordem **F, A, B, G, E, D, C**  
(no fio: `"4"={F,B,G,C}`, `"1"={B,C}`, `"0"={F,A,B,E,D,C}`, `"7"={A,B,C}`)

---

## DADOS HARDWARE CONFIRMADOS

| Item | Valor |
|------|-------|
| VID | `0x0416` |
| PID | `0x8001` |
| Interface | 0 (única) |
| EP OUT | `0x02` (Interrupt, max 64 bytes) |
| EP IN | `0x81` (Interrupt, max 64 bytes) |
| Magic (LED + display) | `DA DB DC DD` |
| Handshake (`--query`) | `DA DB DC DD 10 10 10 10 ...` → PM=0x10 SUB=0x10 |
| LEDs | 84 × 3 bytes = 252 bytes RGB + header 20 bytes |
| Taxa TRCC | ~6,7 frames/s (~150 ms/frame) |
| Backend (env) | `NUVOTON_BACKEND=hidraw|hidapi` (auto = hidraw no Linux) |

---

## CONCLUIDO — Port Linux (código, verificado offline)

- [x] `nuvoton_hid.py`: backend **hidraw** puro stdlib (enumeração `/sys/class/hidraw`, I/O `os.read/os.write`) + backend **hidapi**; seleção automática + override por env
- [x] `hardware_monitor.py`: Linux real — k10temp/zenpower/coretemp (`Tdie`>`Tctl`), amdgpu `edge`>`junction`, `gpu_busy_percent`, **dGPU preferida** (`boot_vga=0`)
- [x] `requirements.txt`: + `psutil`; hidapi opcional no Linux
- [x] `test_hidraw_offline.py`: 16 checks offline (enum fake sysfs, backend, framing 65 B nos 51 frames, lógica hwmon/DRM com árvores falsas, fd I/O Linux-only)
- [x] `systemd/nuvoton-display.service` + seção no `INSTALL.md` (roda como usuário; udev dá acesso ao hidraw)
- [x] Windows sem regressão: selftest 51/51, LHM OK; `--help` não quebra mais em cp1252
- [ ] **Falta**: rodar no hardware Linux (query/demo/display) — ver NEXT_SESSION_START_HERE §P2

---

## CONCLUIDO — Display de Segmentos (100%, Windows)

- [x] Mapa LED↔display validado **dígito a dígito** contra captura real do TRCC
- [x] Auto-teste offline: 51/51 frames reconstruídos idênticos (segmentos + cores, incl. overflow 100% = prefixos + "00")
- [x] **Teste visual no hardware**: replay e demo mostraram os números corretos nos lugares certos
- [x] `lcd_sender.py`: `--query` / `--replay` / `--demo` / `--probe` / `--live` / `--off`
- [x] `nuvoton_daemon.py --mode display`: números reais (CPU/GPU temp+uso) com gradiente por grupo
- [x] `set_zones_color()` corrigido: zonas mapeiam os grupos reais (dígitos + unidade + indicadores)
- [x] `test_lcd_zones.py` atualizado para o mapa real (scan por LED individual)
- [x] CPU usage/GPU usage/GPU temp via LHM | CPU temp precisa de admin (AMD Ryzen MSR) — fallback usa CPU usage

---

## CONCLUIDO — LED Protocol (100%)

- [x] Buffer: 84 LEDs × 3 bytes = 252 bytes RGB, header 20 bytes
- [x] `nuvoton_hid.py`: grupos LED_* do display, `set_per_led()`, `set_zones_color()`, `set_color()`
- [x] `nuvoton_daemon.py`: modos `cpu_temp`, `gpu_temp`, `cpu_usage`, `gpu_usage`, `static`, `off`, `zones`, `display`

---

## PENDENTE

### P1: Uso contínuo com log (comparação 1:1) — Windows
```powershell
python nuvoton_daemon.py --mode display > display_log.txt 2>&1
```
Deixar rodando; comparar valores logados × display × leitura independente (HWiNFO/LHM/`hardware_monitor.py`). Anotar divergências.

### P2: Validação no hardware Linux
```bash
python3 test_hidraw_offline.py   # seção 5 deve rodar (não skip)
python3 lcd_sender.py --query    # deve logar "Connected [hidraw]"
python3 lcd_sender.py --demo --duration 5
python3 nuvoton_daemon.py --mode display
```
Se falhar: regra udev `99-nuvoton-rgb.rules` + permissões do `/dev/hidraw*`.

### P3: Exploração de recursos (depois do básico)
- LEDs °F (24, 60) → modo Fahrenheit configurável
- Cor por segmento → letras no 7-seg, animações/blink
- Prefixos blanks (25,26 / 55,56) → pixels de status
- Probe exploratório de packet types 0x03+ / feature reports (write-only, sem ACK)

---

## ARQUIVOS DO PROJETO

| Arquivo | Status | Função |
|---------|--------|--------|
| `nuvoton_hid.py` | FUNCIONANDO | HID low-level (**hidraw + hidapi**), mapa do display, zonas |
| `lcd_sender.py` | FUNCIONANDO | Sender do display (replay/demo/probe/live/off) |
| `nuvoton_daemon.py` | FUNCIONANDO | Daemon de sensores → LEDs/display |
| `hardware_monitor.py` | FUNCIONANDO | Sensores: LHM (Windows) + hwmon/DRM (Linux) + psutil |
| `test_hidraw_offline.py` | NOVO | Testes offline do port Linux (16 checks) |
| `systemd/nuvoton-display.service` | NOVO | Unit do daemon (usuário, sem root) |
| `trcc_capture_frames.bin` | Captura | 51 frames reais da TRCC (replay + validação) |
| `test_lcd_zones.py` | Ferramenta | Scan LED a LED + preview de zonas |
| `USBLCDNEW.dll` / `.exe` | Referência histórica | **Não** é o caminho do nosso PID (ver acima) |
| `_extract_field_rva*.py`, `_decode_tables.py` | Análise | Artefatos da investigação do DLL (histórico) |

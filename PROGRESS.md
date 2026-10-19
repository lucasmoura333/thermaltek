# TRCC Reverse Engineering — Progress Tracker

**Dispositivo**: Nuvoton HID Transfer — VID `0x0416` / PID `0x8001`  
**Objetivo**: Controle RGB + display no Windows/Linux reproduzindo o protocolo do TRCC  
**Status**: LED + display 100% funcionando no Windows; port Linux com código completo e verificado offline  
**Last Updated**: Sessão 11 — P3: letras no 7-seg + heartbeat/blink nos pixels livres validados no hardware (`lcd_sender.py --anim`)

**Update 2026-10-17** (pós-Sessão 10): fix do crash `inf` (3 camadas) + repo git (`4bdc3a4`, `c600f1c`) + daemon estável (0 erros); **P2 adiado** — validação Linux fica para a instalação Linux futura (alternativa WSL2+usbipd mapeada, não escolhida)

**Update 2026-10-17 (sessão 11)**: **P3 iniciado** — letras no 7-seg + heartbeat/blink nos 6 pixels livres validados no hardware (`lcd_sender.py --anim`); correção do mapa: blanks GPU = **57/58** (55/56 são segmentos do dígito das dezenas); °F 24/60 confirmados LEDs reais

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
- [ ] **Falta (adiado 17/10)**: rodar no hardware Linux (query/demo/display) — usuário fará instalação Linux no futuro; ver NEXT_SESSION_START_HERE §P2

---

## CONCLUIDO — Display de Segmentos (100%, Windows)

- [x] Mapa LED↔display validado **dígito a dígito** contra captura real do TRCC
- [x] Auto-teste offline: 51/51 frames reconstruídos idênticos (segmentos + cores, incl. overflow 100% = prefixos + "00")
- [x] **Teste visual no hardware**: replay e demo mostraram os números corretos nos lugares certos
- [x] `lcd_sender.py`: `--query` / `--replay` / `--demo` / `--probe` / `--live` / `--anim` / `--off`
- [x] P3 (sessão 11): `LETTER_MASK`/`show_word()`/`digit_blocks()` (letras no 7-seg) + `--anim` (HOT/Err/HELP + heartbeat/blink nos 6 pixels livres 24/25/26/57/58/60)
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

### P2: Validação no hardware Linux ⏸ ADIADO (17/10) — TODO
**Decisão do usuário**: fará uma instalação Linux no futuro; a validação fica como TODO até lá — nada bloqueado.  
**Alternativa mapeada (não escolhida)**: WSL2 + usbipd — usbipd-win 5.3.0 instalado, device já `Shared` (busid `3-17`); WSL Ubuntu ok (falta `psutil` em venv — Python do sistema é PEP 668). Caveat: o attach derruba o device do Windows (parar daemon; display apaga no teste).

```bash
python3 test_hidraw_offline.py   # seção 5 deve rodar (não skip)
python3 lcd_sender.py --query    # deve logar "Connected [hidraw]"
python3 lcd_sender.py --demo --duration 5
python3 nuvoton_daemon.py --mode display
```
Se falhar: regra udev `99-nuvoton-rgb.rules` + permissões do `/dev/hidraw*`.

### P3: Exploração de recursos (depois do básico)
**Feito 17/10**: probe além-84 → **corrente = 84 LEDs confirmada** (84–99 e 6 relatórios: nada acende; TRCC: `length=252` + padding zero).
**Feito 17/10 (sessão 11)**: letras + animações validadas no hardware (`lcd_sender.py --anim`):
- [x] Letras no 7-seg: `LETTER_MASK`/`show_word()`/`digit_blocks()` — HOT (vermelho, lado CPU), Err (âmbar, lado GPU), HELP azul rolando ✓ visual
- [x] **Pixels livres = 6** (heartbeat/blink ao vivo): blanks 25/26 (CPU) + **57/58** (GPU) + °F **24/60** (reais — pulsaram). ⚠ 55/56 **não** são livres: segmentos do dígito das dezenas do uso GPU (captura acende 55/56 para 10–99% e 57/58 como '1' do '100')
- [x] `build_metrics_frame(status_color=…/status_leds=…)`; `nuvoton_hid.FREE_*`/`ALL_FREE_PIXELS`
- Logs do teste: `p3_anim_out.txt`, `p3_anim_out2.txt`, `p3_live_check.txt` (daemon religado pós-teste)

**Rodada exótica (sessão 11, 2º show)** — `--scroll` / `--chase` / `--fuzz`:
- [x] Marquee nos 10 dígitos ('PA120 DIGITAL' ✓ no olho)
- [x] Chase (arco-íris/rastro/chuva) ✓ suave; taxa: 10/30/60 fps suaves, burst **~100 fps** (300 frames / 3,01 s)
- [x] Probe frio fechado: tipos 0x00–0xFF / header 4/8 / Report ID 1/2 / length 0/1/FFFF → **branco estável** (negativa fraca); feature set aceito (sem efeito), get rejeitado; indicadores = 2 LEDs/difusor → **bicolor misturado** (escritos CPU/GPU são impressão física fixa)
- Logs: `p4_out1/2/3.txt`, `p4_check.txt`
**Rodada exótica v2 (sessão 11, 3º show)**:
- [x] `--starfield` ✓ aprovado; `--mode fire` ✓✓ aprovado (fogo 1-D; 'HOT' ≥ hot_at; sweep p/ demo)
- [x] `--beacon` (óptico: 2 bits/LED, 4 cores, CRC32 + XOR; decoder detecta perda/corrupção) — round-trip provado (102 frames/1802 B OK); visual fraco no segmentado
- [x] `--clock` e `--image` (fax coluna 84px) implementados/validados offline — sem prioridade visual
- [~] `--mode vibe` implementado; Zzz não disparou no demo (limiar 25% < baseline) — re-testar depois
- Logs: `p5_*.txt`; wrapper `p5_show.ps1`

**Auditoria de protocolo (sessão 11, prova no fio)**:
- [x] USBPcap 110s com UI completa (brilho/°F/cores/efeitos): 658 frames, header invariante (bytes 4-11=00, type 02, len FC) ⇒ brilho = software, °F = troca de LED, efeitos = animação. **Protocolo completo; sem comandos escondidos** (`p9.pcap`)
- [x] EP IN: resposta fixa de identidade a qualquer query; nunca espontâneo; família `DC DD` silenciosa
- [x] Templates do exe: nosso = init+LED; outros PIDs = LCD 480×480 (tag `12 34 56 78`), 360×360, 240×320, 1280×480; TRCC auto-update por FTP (app-level)
- [x] Persistência: último frame sobrevive ao replug (NVRAM ou power residual — boot a frio fica TODO)
- [~] Frida: hook v3 carrega mas não vê writes do processo (superseded pelo USBPcap; nota técnica)
- [ ] Pendente: semântica dos indicadores no daemon (pulso de carga/alerta); feature reports a fundo (set passa, get rejeitado); vibe Zzz com limiar real

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

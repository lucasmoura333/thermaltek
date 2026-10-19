# Codebase State — Session 11 (P3: letras + animações)

**Last Updated**: Sessão 11 (P3 validado no hardware: palavras no 7-seg + heartbeat/blink nos 6 pixels livres)

**Update 2026-10-17 (sessão 11)**: correção do mapa — blanks GPU = **57/58** (55/56 são segmentos do dígito das dezenas; captura: '1' do '100' = 57/58); °F **24/60 confirmados LEDs reais** (pulsaram no heartbeat); `build_metrics_frame(status_color=…/status_leds=…)`; teste ao vivo com daemon parado/religado (wrapper `p3_live.ps1`, logs `p3_anim_out*.txt`/`p3_live_check.txt`)

**Files Modified (Session 11)**: `lcd_sender.py`, `nuvoton_hid.py`, `NEXT_SESSION_START_HERE.md`, `PROGRESS.md`, `CODEBASE_STATE.md`

**Update 2026-10-17**: fix do crash `inf` (3 camadas) + repo git; **P2 adiado** — validação Linux fica para a instalação Linux futura (alternativa WSL2+usbipd mapeada)

**Files Modified (Session 10)**: `nuvoton_hid.py`, `hardware_monitor.py`, `requirements.txt`, `nuvoton_daemon.py` (--help cp1252), `INSTALL.md`, `NEXT_SESSION_START_HERE.md`, `PROGRESS.md`  
**Files Created (Session 10)**: `test_hidraw_offline.py`, `systemd/nuvoton-display.service`

---

## ✅ Working Code (Tested & Functional)

### `linux-driver/python-lib/nuvoton_hid.py`
- **Status**: ✅ WORKING (Windows validado no hardware; trilha Linux verificada offline)
- **Transportes**: `_HidrawTransport` (puro stdlib, Linux: `/sys/class/hidraw` + `os.read/os.write`) e `_HidapiTransport` (Windows); auto-seleção em `_backend_order()` com override `NUVOTON_BACKEND=hidraw|hidapi`; framing de 65 B idêntico nos dois
- **Protocolo**: magic `DA DB DC DD` + header 20 B + 252 B RGB (84 LEDs), chunked em 5×64 bytes no EP 0x02
- **Mapa do display**: constantes `LED_CPU_IND`, `LED_CPU_TEMP` (2-22), `LED_CPU_CELSIUS/FAHR` (23/24), `LED_CPU_USAGE` (25-40), `LED_CPU_PERCENT` (41), `LED_GPU_PERCENT` (42), `LED_GPU_USAGE` (43-58), `LED_GPU_CELSIUS/FAHR` (59/60), `LED_GPU_TEMP` (61-81), `LED_GPU_IND` (82/83)
- **Pixels livres (P3)**: `FREE_CPU_BLANKS` (25/26), `FREE_GPU_BLANKS` (57/58), `FREE_CPU_FAHR` (24), `FREE_GPU_FAHR` (60), `ALL_FREE_PIXELS`
- **Funções**: `set_per_led()`, `set_zones_color()` (zonas = grupos reais), `set_color()`, `query_status()`, `list_devices()` (hidraw no Linux, hidapi onde couber)

### `linux-driver/python-lib/hardware_monitor.py`
- **Status**: ✅ WORKING — Windows (LHM) sem regressão; trilhas Linux verificadas offline com árvores falsas
- **Windows**: LHM `CPU Total` / `D3D 3D` / GPU Core; cpu_temp requer admin (AMD Ryzen 5 7500F)
- **Linux**: `_linux_cpu_temp()` (k10temp/zenpower/coretemp; prefere label `Tdie` > `Tctl` > temp1; psutil fallback), `_linux_gpu_temp()` (amdgpu `edge` > `junction`), `_linux_gpu_usage()` (`gpu_busy_percent`); ordem de cards via `_linux_drm_cards()` (**dGPU `boot_vga=0` primeiro**)
- **Seam de teste**: `HWMON_ROOT` / `DRM_ROOT` patcháveis

### `linux-driver/python-lib/test_hidraw_offline.py`
- **Status**: ✅ 16/16 (Windows); seção 5 (fd I/O com `os.pipe`) roda no Linux
- Cobre: enum fake sysfs (+decoys), seleção de backend, framing byte-idêntico dos 51 frames, lógica hwmon/DRM (Tdie, dGPU, junction), framing de métricas

### `linux-driver/python-lib/lcd_sender.py`
- **Status**: ✅ WORKING — validado 51/51 offline + teste visual no hardware
- **Comandos**: `--query` (handshake PM=0x10), `--replay`, `--demo` (42°C 56% / 47°C 21°), `--probe`, `--live`, `--anim`, `--off`; protocolo agnóstico de transporte (`send_body`/`send_raw_frame`)
- **P3 (sessão 11)**: `LETTER_MASK` (letras 7-seg, ordem F A B G E D C), `digit_blocks()`, `show_word()` (letras + dígitos); `--anim` (HOT/Err/HELP + heartbeat/blink); `build_metrics_frame(status_color=…, status_leds=…)` pinta os pixels livres (default `ALL_FREE_PIXELS`)
- **Rodada exótica (sessão 11)**: `--scroll TEXT` (marquee nos 10 dígitos, `MARQUEE_BLOCKS`), `--chase` (arco-íris/rastro/chuva), `--fuzz` (probe frio: tipos/header/Report ID/length/feature/taxa — taxa medida ~100 fps em burst)
- **Exótico v2 (sessão 11)**: `--starfield`; `--clock` (`build_clock_frame`: HH:MM + colon 41/42 + segundos binários); `--image PIC` (fax 1 coluna/frame, Pillow); `--beacon FILE` (óptico 2 bits/LED, paleta 4 cores, START magenta/END amarelo, XOR+CRC32, `beacon_encode/decode` — round-trip provado)

### `linux-driver/python-lib/nuvoton_daemon.py`
- **Status**: ✅ WORKING — `python nuvoton_daemon.py --mode display`
- **Modos**: `display`, `zones`, `cpu_temp`, `gpu_temp`, `cpu_usage`, `gpu_usage`, `static`, `off`, **`fire`** (demoscene térmico 1-D; `NUVOTON_FIRE_SWEEP=1` p/ demo; config `modes.fire`), **`vibe`** (display ↔ 'Zzz' ocioso; env `NUVOTON_VIBE_IDLE`/`NUVOTON_VIBE_SECS`; config `modes.vibe`)
- SIGINT/SIGTERM desligam o display antes de sair; `--help` ASCII-safe (cp1252)

### `linux-driver/systemd/nuvoton-display.service`
- **Status**: NOVO — instalável (editar `User=`/`WorkingDirectory=`); rodar como usuário (udev dá acesso ao hidraw)

---

## ❌ PREMISSA DERRUBADA — "LCD 480x480 / USBLCDNEW" (histórico)

As seções de LCD das sessões 6-8 **não se aplicam** ao nosso PID. Evidência:

- pcaps antigos + captura fresca (USBPcap3 8 s): só frames `DA DB DC DD`; nenhum `12 34 56 78`, nenhum JPEG, EP 0x81 mudo
- `USBLCDNEW.dll`: sem handler para PID 0x8001; driver do device = `HidUsb` puro
- `shareMemory_ImageRGB` zerada enquanto o display mostra números

Os arquivos `USBLCDNEW.dll`/`.exe`, `_extract_field_rva*.py`, `_decode_tables.py`, `_lcd_test2.py`, `shareMemory_*` ficam como **artefatos históricos** (não usar como referência de protocolo).

---

## 📦 Captura de referência

### `trcc_capture_frames.bin` (51 × 320 B)
- Frames reais enviados pelo TRCC com TRCC aberto (USBPcap3)
- Formato: 5 relatórios de 64 B concatenados (o mesmo que `write_report()` envia)
- Decodifica em: CPU 41°C, GPU 47°C, GPU uso 0→100 (para o `--replay`)
- Validação: `build_metrics_frame` reconstrói os 51 frames **idênticos** (segmentos + cores)

---

## ⏳ Próximos passos

1. **Uso contínuo com log 1:1** (Windows): `nuvoton_daemon.py --mode display > display_log.txt 2>&1`; comparar exibido × sensores
2. **Validar no hardware Linux** — ⏸ **adiado (17/10, TODO até a instalação Linux futura)**: `test_hidraw_offline.py` (seção 5 roda) + `lcd_sender.py --query/demo` + daemon `--mode display`. Alternativa mapeada: WSL2+usbipd (usbipd-win 5.3.0; device já `Shared`, busid `3-17`)
3. **Exploração**: letras/animações ✅ **FEITO** (sessão 11 — `--anim`/`--scroll`/`--chase`, validados no hardware); probe frio ✅ FEITO (tipos/header/Report ID/length = branco estável — negativa fraca; feature set aceito/get rejeitado; taxa até ~100 fps; indicadores bicolor misturado); resta: semântica dos indicadores no daemon (alerta/pulso) e feature reports a fundo

---

## ⚠️ Known Issues & Workarounds

| Issue | Workaround | Status |
|-------|-----------|--------|
| TRCC sobrescreve o display a ~160 ms | Fechar TRCC antes de rodar daemon/sender | ℹ️ Known |
| CPU temp requer Admin (Windows/AMD MSR) | Fallback: cor de temp espelha usage | ✅ Active |
| Matar o daemon com kill duro deixa frame latched | Rodar `lcd_sender.py --off` depois | ℹ️ Known |
| `°C` aparece como `�C` no console cp1252 | Cosmético (encoding do terminal) | ℹ️ Known |
| Seção fd I/O do teste offline só roda em Linux | Windows: skip esperado; validar na máquina Linux (P2 — **adiado**: instalação Linux futura) | ℹ️ Expected |

---

## 🔗 Cross-References

**Protocolo detalhado**: `linux-driver/PROTOCOL.md` (LED)  
**Linux Setup**: `linux-driver/INSTALL.md` (inclui daemon + systemd)  
**Quick Start**: `NEXT_SESSION_START_HERE.md`  
**Progresso**: `PROGRESS.md`

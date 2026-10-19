# Codebase State — Session 10 End

**Last Updated**: Session 10 (port Linux codificado + verificado offline; systemd/INSTALL/docs fechados)  
**Files Modified This Session**: `nuvoton_hid.py`, `hardware_monitor.py`, `requirements.txt`, `nuvoton_daemon.py` (--help cp1252), `INSTALL.md`, `NEXT_SESSION_START_HERE.md`, `PROGRESS.md`  
**Files Created This Session**: `test_hidraw_offline.py`, `systemd/nuvoton-display.service`

---

## ✅ Working Code (Tested & Functional)

### `linux-driver/python-lib/nuvoton_hid.py`
- **Status**: ✅ WORKING (Windows validado no hardware; trilha Linux verificada offline)
- **Transportes**: `_HidrawTransport` (puro stdlib, Linux: `/sys/class/hidraw` + `os.read/os.write`) e `_HidapiTransport` (Windows); auto-seleção em `_backend_order()` com override `NUVOTON_BACKEND=hidraw|hidapi`; framing de 65 B idêntico nos dois
- **Protocolo**: magic `DA DB DC DD` + header 20 B + 252 B RGB (84 LEDs), chunked em 5×64 bytes no EP 0x02
- **Mapa do display**: constantes `LED_CPU_IND`, `LED_CPU_TEMP` (2-22), `LED_CPU_CELSIUS/FAHR` (23/24), `LED_CPU_USAGE` (25-40), `LED_CPU_PERCENT` (41), `LED_GPU_PERCENT` (42), `LED_GPU_USAGE` (43-58), `LED_GPU_CELSIUS/FAHR` (59/60), `LED_GPU_TEMP` (61-81), `LED_GPU_IND` (82/83)
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
- **Comandos**: `--query` (handshake PM=0x10), `--replay`, `--demo` (42°C 56% / 47°C 21°), `--probe`, `--live`, `--off`; protocolo agnóstico de transporte (`send_body`/`send_raw_frame`)

### `linux-driver/python-lib/nuvoton_daemon.py`
- **Status**: ✅ WORKING — `python nuvoton_daemon.py --mode display`
- **Modos**: `display`, `zones`, `cpu_temp`, `gpu_temp`, `cpu_usage`, `gpu_usage`, `static`, `off`
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
2. **Validar no hardware Linux**: `test_hidraw_offline.py` (seção 5 roda) + `lcd_sender.py --query/demo` + daemon `--mode display`
3. **Exploração**: modo °F, letras/animações (cor por segmento), probe de packet types 0x03+

---

## ⚠️ Known Issues & Workarounds

| Issue | Workaround | Status |
|-------|-----------|--------|
| TRCC sobrescreve o display a ~160 ms | Fechar TRCC antes de rodar daemon/sender | ℹ️ Known |
| CPU temp requer Admin (Windows/AMD MSR) | Fallback: cor de temp espelha usage | ✅ Active |
| Matar o daemon com kill duro deixa frame latched | Rodar `lcd_sender.py --off` depois | ℹ️ Known |
| `°C` aparece como `�C` no console cp1252 | Cosmético (encoding do terminal) | ℹ️ Known |
| Seção fd I/O do teste offline só roda em Linux | Windows: skip esperado; validar na máquina Linux (P2) | ℹ️ Expected |

---

## 🔗 Cross-References

**Protocolo detalhado**: `linux-driver/PROTOCOL.md` (LED)  
**Linux Setup**: `linux-driver/INSTALL.md` (inclui daemon + systemd)  
**Quick Start**: `NEXT_SESSION_START_HERE.md`  
**Progresso**: `PROGRESS.md`

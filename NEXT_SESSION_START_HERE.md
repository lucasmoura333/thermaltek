# PROXIMA SESSAO — START HERE

**Status**: Display de segmentos 100% decodificado e validado; daemon `--mode display` rodando ao vivo (Windows).
**Objetivo atual**: (1) uso contínuo com log para comparar exibido × sensores 1:1; (2) validar o port Linux no hardware Linux; (3) começar a exploração de recursos.
**Progresso LED + Display**: 100% FUNCIONANDO (Windows).
**Port Linux**: código completo e verificado offline (16/16) — falta rodar no hardware Linux.

> ⚠️ **NÃO REABRIR**: o "LCD 480x480 / USBLCDNEW / magic 12 34 56 78" foi premissa derrubada na Sessão 9 (evidência tripla: pcaps só `DA DB DC DD`, EP 0x81 mudo, USBLCDNEW.dll sem handler pro PID 0x8001). O display é uma corrente de 84 LEDs RGB (7 segmentos). Não existe segundo protocolo.

---

## O QUE MUDOU (Session 10) — LEIA PRIMEIRO

Port Linux implementado **no código** e verificado offline (Windows intacto):

- `nuvoton_hid.py`: transporte com dois backends — **hidraw** (puro stdlib; Linux: enumera `/sys/class/hidraw`, I/O via `os.read/os.write`) e **hidapi** (Windows). Auto: hidraw primeiro no Linux; `NUVOTON_BACKEND=hidraw|hidapi` força. Mesmo framing de 65 B nos dois.
- `hardware_monitor.py`: trilhas Linux reais — CPU via k10temp/zenpower/coretemp (prefere `Tdie`, senão `Tctl`, senão temp1); GPU via amdgpu hwmon (`edge`, senão `junction`) + `gpu_busy_percent` do DRM; **GPU discreta preferida** (`boot_vga=0` primeiro). Windows (LHM) intacto.
- `requirements.txt`: + `psutil`; hidapi virou **opcional** no Linux (só fallback).
- `test_hidraw_offline.py` (novo): 16 checks — enumeração em sysfs falso, seleção de backend, framing idêntico nos 51 frames, lógica de sensores com árvores hwmon/DRM falsas, fd I/O real (roda só no Linux).
- `systemd/nuvoton-display.service` (novo) + seção no `INSTALL.md` (daemon sem root; udev já dá acesso ao hidraw).
- Bônus: `nuvoton_daemon.py --help` não quebra mais em console cp1252 (setas `→` → `->`).
- Sem regressão: selftest 51/51; LHM lendo normalmente no Windows.

---

## ESTADO ATUAL — O QUE FUNCIONA (Windows)

| Comando | O que faz |
|---------|-----------|
| `python lcd_sender.py --query` | Handshake; deve responder `DA DB DC DD 10 10 10 10 ...` (PM=0x10) |
| `python lcd_sender.py --replay trcc_capture_frames.bin --duration 20` | Reproduz os 51 frames reais da TRCC (prova de vida) |
| `python lcd_sender.py --demo --duration 30` | Números fixos: CPU 42°C 56% / GPU 47°C 21% |
| `python lcd_sender.py --probe` | Acende um grupo por vez (~30 s, mapa por LED) |
| `python lcd_sender.py --live` | Sensores reais → dígitos, loop contínuo |
| `python nuvoton_daemon.py --mode display` | Daemon: dígitos reais com gradiente por grupo |
| `python nuvoton_daemon.py --mode zones` | Preview: cada zona acesa sólida na cor do seu gradiente |
| `python test_hidraw_offline.py` | Testes offline do port Linux (não precisa de device) |
| `python test_lcd_zones.py` | Scan LED a LED (84 posições, 1 s cada) |

**Sempre**: TRCC.exe FECHADA (o timer de ~160 ms dela sobrescreve nossos pacotes).

---

## MAPA DO DISPLAY (validado — fonte: `nuvoton_hid.py` LED_*)

| LEDs | Grupo |
|------|-------|
| 0, 1 | Indicador CPU |
| 2–22 | CPU temp — 3 dígitos esquerda→direita (7 LEDs cada) |
| 23 / 24 | °C / °F |
| 25–40 | CPU uso — 2 dígitos (+ 2 blanks quando < 100) |
| 41 / 42 | % CPU / % GPU |
| 43–58 | GPU uso — 2 dígitos (espelhado) |
| 59 / 60 | °C / °F |
| 61–81 | GPU temp — 3 dígitos (espelhado) |
| 82, 83 | Indicador GPU |

Segmentos por dígito: ordem **F, A, B, G, E, D, C**.

---

## PRIORIDADE 1 — USO CONTÍNUO COM LOG (comparação 1:1) — Windows

1. Fechar TRCC + USBLCDNEW.
2. Rodar com log redirecionado:
   ```powershell
   python nuvoton_daemon.py --mode display > display_log.txt 2>&1
   ```
3. Deixar rodando um tempo; comparar os valores logados (a cada 2 s) com o que o display mostra e com uma leitura independente (ex.: HWiNFO/LHM aberto, ou `python hardware_monitor.py` em outro terminal) para medir o quão 1:1 está. Anotar divergências (CPU temp sem admin espelha uso; GPU `D3D 3D` vs edge/Junction etc.).
4. Ctrl-C desliga o display (SIGINT tratado). Se matar duro, rodar `lcd_sender.py --off` depois.

## PRIORIDADE 2 — VALIDAR NO HARDWARE LINUX

No PC Linux (o device ou um igual), TRCC não existe lá:

```bash
cd linux-driver/python-lib
pip3 install -r requirements.txt
python3 test_hidraw_offline.py       # seção 5 (fd I/O) deve RODAR, não skip
python3 lcd_sender.py --query        # log deve dizer "Connected [hidraw]"
python3 lcd_sender.py --demo --duration 5
python3 nuvoton_daemon.py --mode display
```

Se `--query` falhar: conferir `99-nuvoton-rgb.rules` instalada e permissão do `/dev/hidraw*` (grupo plugdev / MODE 0666).

## PRIORIDADE 3 — EXPLORAR RECURSOS (depois do básico)

- **LEDs °F** (24, 60) nunca acesos → modo Fahrenheit configurável.
- **Cor por segmento** (não só por grupo) → letras no 7-seg (`HELP`, `HOT`, `Err`…), animações, blink.
- **Prefixos blanks** (25, 26 / 55, 56) → pixels de status extras.
- Indicadores 0,1 / 82,83 → semântica livre (pulso de carga, alerta…).
- **Probe exploratório** de packet types 0x03+ / feature reports (device é write-only, sem ACK — anotar que a negativa é fraca).

---

## NUMEROS CHAVE — NAO PERDER

- VID=0x0416, PID=0x8001 (Nuvoton HID Transfer)
- Magic único: `DA DB DC DD` (LED **e** display — não existe segundo protocolo)
- Handshake: `DA DB DC DD 10 10 10 10 00 00 00 00 01 00 00 00` → PM=0x10 SUB=0x10
- EP OUT 0x02 / EP IN 0x81 (Interrupt, 64 bytes) — device é write-only para estado
- Frame: 20 B header + 252 B RGB (84 LEDs) = 272 B → 5 relatórios de 64 B
- Init: `DA DB DC DD 00 00 00 00 00 00 00 00 01 00 00 00 00 00 00 00`
- Taxa TRCC: ~6,7 fps (0,15 s por frame)
- Backend: `NUVOTON_BACKEND=hidraw|hidapi` (auto = hidraw no Linux)

## ESTADO DOS ARQUIVOS IMPORTANTES

| Arquivo | Status | O que faz |
|---------|--------|-----------|
| `nuvoton_hid.py` | FUNCIONANDO | HID low-level (**hidraw + hidapi**), grupos LED_*, `set_zones_color()` |
| `lcd_sender.py` | FUNCIONANDO | Sender: query/replay/demo/probe/live/off (protocolo agnóstico de transporte) |
| `nuvoton_daemon.py` | FUNCIONANDO | Daemon: modes `display`, `zones`, `cpu_temp`, ... |
| `hardware_monitor.py` | FUNCIONANDO | Sensores: LHM (Windows) + hwmon/DRM (Linux) + psutil |
| `test_hidraw_offline.py` | NOVO | Testes offline do port (16 checks; fd I/O só em Linux) |
| `systemd/nuvoton-display.service` | NOVO | Unit do daemon (rodar como usuário, sem root) |
| `trcc_capture_frames.bin` | Captura | 51 frames reais da TRCC (320 B cada) |
| `test_lcd_zones.py` | Ferramenta | Scan LED a LED + preview de zonas |
| `_lcd_test2.py` etc. | Histórico | Artefatos da investigação do USBLCDNEW.dll (falso caminho — não reabrir) |

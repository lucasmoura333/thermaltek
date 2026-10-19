# PROXIMA SESSAO — START HERE

**Status**: Display de segmentos 100% decodificado e validado; daemon `--mode display` rodando ao vivo (Windows).
**Objetivo atual**: (1) uso contínuo com log para comparar exibido × sensores 1:1; (2) validar o port Linux no hardware Linux — ⏸ **adiado: aguardando instalação Linux (decisão 17/10)**; (3) começar a exploração de recursos.
**Progresso LED + Display**: 100% FUNCIONANDO (Windows).
**Port Linux**: código completo e verificado offline (16/16) — falta rodar no hardware Linux (**adiado: usuário fará instalação Linux no futuro — decisão 17/10**).

> ⚠️ **NÃO REABRIR**: o "LCD 480x480 / USBLCDNEW / magic 12 34 56 78" foi premissa derrubada na Sessão 9 (evidência tripla: pcaps só `DA DB DC DD`, EP 0x81 mudo, USBLCDNEW.dll sem handler pro PID 0x8001). O display é uma corrente de 84 LEDs RGB (7 segmentos). Não existe segundo protocolo.

---

## O QUE MUDOU (Session 11) — LEIA PRIMEIRO

P3 — letras e animações feitas e validadas no hardware:

- `lcd_sender.py --anim` (novo): palavras no 7-seg — `LETTER_MASK` + `show_word()` + `digit_blocks()` — 'HOT' (vermelho) no lado CPU, 'Err' (âmbar) no GPU, 'HELP' azul rolando; heartbeat (duplo pulso) e blink x3 nos pixels livres. `build_metrics_frame(status_color=…/status_leds=…)` pinta pixels livres sobre as métricas.
- **Pixels livres = 6, validados ao vivo**: blanks 25/26 (CPU) + **57/58** (GPU) + °F **24/60** (24/60 confirmados LEDs reais — pulsaram no teste). ⚠ Correção do probe 17/10: **55/56 não são livres** — são segmentos do dígito das dezenas do uso GPU (acendem para 10–99%; na captura, o par livre é 57/58, o '1' do '100'). `nuvoton_hid.py`: constantes `FREE_*` / `ALL_FREE_PIXELS`.
- Teste ao vivo: daemon parado (wrapper `p3_live.ps1`, UAC) + 2 passagens do `--anim`; logs `p3_anim_out*.txt` + `p3_live_check.txt`; daemon religado (PID novo, admin).

**Rodada exótica (sessão 11, 2º show)** — `--scroll` / `--chase` / `--fuzz`:

- **Marquee** `--scroll "TEXT"`: rola texto pelos **10 dígitos físicos** (CPU temp | CPU usage | GPU usage | GPU temp) — 'PA120 DIGITAL' validado no olho ✓ (`_glyph_mask` agora aceita letras + dígitos).
- **`--chase`**: arco-íris girando + ponto com rastro + chuva — tudo suave ✓.
- **`--fuzz` (probe frio)**: tipos de pacote 0x00–0xFF, header bytes 4/8, **Report ID 1/2**, length mentiroso (0/1/FFFF) → **branco estável em tudo** (negativa fraca: firmware só age no framing conhecido). `send_feature_report` **aceito** (sem efeito visível); `get_feature_report` → `OSError('read error')`.
- **Escritos CPU/GPU**: impressão **física fixa** no difusor (não é desenho de LED); os 2 LEDs por glifo (0/1 e 82/83) compartilham o difusor → cores **misturam** (bicolor confirmado: CPU vermelho/verde, GPU azul/amarelo).
- **Taxa de escrita medida**: burst de 300 frames em 3,01 s → **~100 fps efetivos**; dot a 10/30/60 fps suave (o display aguenta bem mais que os 6,7 fps do TRCC).
- Logs: `p4_out1/2/3.txt` + `p4_check.txt`; wrapper `p4_sideshow.ps1`.

**Rodada exótica v2 (sessão 11, 3º show)** — starfield/clock/image/beacon + fire/vibe:

- `--starfield` ✅ aprovado no olho (estrelas + cadente).
- `--clock` (HH:MM nos dígitos de uso, colon 41/42, segundos em binário nos livres) — frame validado offline vs hora fixa; sem prioridade ("ignora").
- `--image PIC` (fax: 1 coluna 84 px por frame) e `--beacon FILE` (óptico: 2 bits/LED em 4 cores, START magenta / END amarelo, XOR por quadro + CRC32, decoder com detecção de perda/corrupção) — **round-trip do beacon provado** (102 frames, 1802 B, self-test OK); no display segmentado o visual não lê bem (arquivados como ferramenta).
- `--mode fire` ✅✅ **aprovado** (fogo 1-D nos 84 LEDs, intensidade = temp, 'HOT' pisca ≥ hot_at, `NUVOTON_FIRE_SWEEP=1` p/ demo).
- `--mode vibe` (display ↔ 'Zzz' ocioso; `NUVOTON_VIBE_IDLE`/`NUVOTON_VIBE_SECS`) — implementado; no demo não entrou em Zzz (limiar 25% abaixo do baseline da máquina) → re-testar em sessão futura com limiar folgado.
- Logs: `p5_*.txt`; wrapper `p5_show.ps1`.

**Auditoria de protocolo (sessão 11, fronts)** — fechamento com prova no fio:

- **Wire truth (USBPcap, 110s de UI completa: brilho+°F+cores+efeitos)**: 658 frames @6fps; header SEMPRE `00 00 00 00 00 00 00 00`, type=0x02, len=0x00FC — **zero variação** ⇒ brilho é software (escala de cor), °F é troca de LED no mesmo frame, efeitos são frames animados. **Protocolo do PA120: completo (init + frame LED + query de identidade); não há comando escondido.** (Evidência: `p9.pcap`/`p9_out.txt`.)
- **EP IN/query**: 11 variantes + init + escuta passiva ⇒ resposta fixa de identidade (`DA DB DC DD 10 10 10 10 ...`), nunca espontânea; família `DC DD` (outros devices) silenciosa no nosso.
- **IL/exe mining**: catálogo de templates — nosso = init + LED header (len patchada pra 0xFC); outros PIDs = LCD 480×480 (com tag `12 34 56 78` no header!), 360×360, 240×320, 1280×480. TRCC se auto-atualiza por `ftp://47.110.136.13/update/limin/` (app; sem updater de firmware do device nas strings).
- **Persistência**: o último frame **sobrevive ao replug do USB** (roxo voltou). Pode ser NVRAM ou alimentação residual via header — teste de boot a frio fica TODO.
- **Frida**: hook v3 (`frida_hid_hook.js`, compat frida 17, kernelbase+kernel32+NtWriteFile+hid.dll+filtro por conteúdo) carrega e enxerga os opens, mas **nenhum write** do processo attachado — superseded pelo USBPcap; fica como nota técnica (provável interação frida/token elevado).

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

## PRIORIDADE 2 — VALIDAR NO HARDWARE LINUX ⏸ ADIADO (2026-10-17) — TODO

**Decisão do usuário (17/10)**: ele fará uma instalação Linux no futuro; a validação fica como TODO até lá — nada bloqueado (o port está pronto; Windows segue 100%).

Alternativa mapeada (não escolhida por ora): **WSL2 + usbipd** — usbipd-win 5.3.0 já instalado e o device já `Shared` (busid `3-17`); WSL Ubuntu pronta (kernel 6.6.87.2, Python 3.12; falta só `psutil`, instalar em venv — o Python do sistema é PEP 668). Caveats: o `attach` derruba o device do Windows (parar o daemon antes; display apaga durante o teste) e o kernel WSL pode não expor hidraw.

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

> **Probe "pixels extras" — FEITO (17/10)**: corrente = **84 LEDs, confirmada no fio**. LEDs 84–99 não acendem em nenhuma variante (len=300, len=252, 6 relatórios até ~120); TRCC declara `length=252` e padding zerado — bate. **Blanks 25/26 + 57/58 = LEDs reais** → pixels livres (o probe acendeu 25/26/55/56 em magenta — 55/56 são segmentos do dígito das dezenas, ver sessão 11). Scripts: `Temp\opencode\probe_extra.py` + `explore_extra.ps1`; logs `probe_extra_out*.txt` / `explore_check*.txt` na pasta do projeto.

- **LEDs °F** (24, 60): usuário usa só °C → **pixels livres** — ✅ validados como LEDs reais no teste ao vivo (sessão 11).
- **Cor por segmento** (não só por grupo) → letras no 7-seg (`HELP`, `HOT`, `Err`…) e animações → ✅ **FEITO** (sessão 11, `lcd_sender.py --anim`).
- **Prefixos blanks** (25, 26 / **57, 58**) → pixels de status extras → ✅ usados no heartbeat/blink (o probe de 17/10 apontou 55/56, mas a captura mostra que esses são segmentos do dígito das dezenas; o par livre GPU é 57/58).
- Indicadores 0,1 / 82,83 → 2 LEDs atrás de 1 difusor por escrito CPU/GPU: cores **misturam** (bicolor ✓, sessão 11); semântica de carga/alerta no daemon — pendente.
- **Probe exploratório** de packet types 0x03+ / feature reports → ✅ **FEITO** (sessão 11): tudo deu branco estável (negativa fraca, write-only); feature set aceito/sem efeito, get rejeitado.

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

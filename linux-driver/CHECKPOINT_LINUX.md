# Checkpoint: Migração para Linux — SESSÃO 5 UPDATE

> ⚠️ **HISTÓRICO (Sessão 5) — SUPERADO.** Este checkpoint é anterior à descoberta (Sessão 9) de que o "LCD" é na verdade um **display de 7 segmentos** falando o MESMO protocolo LED (`DA DB DC DD`) — não existe protocolo `12 34 56 78`/JPEG para o PID 0x8001. A seção "Protocolo LCD Display" abaixo está **obsoleta**. Estado atual: `../PROGRESS.md` e `../NEXT_SESSION_START_HERE.md`.

**Última revisão**: Sessão 5 — SHM Discovery & Frida Validation  
**Estado**: Hot context limit reached; pivoting to empirical validation of IL-predicted packet structure  
**Próximo Chat**: Começar com PRIORITY 1 (extrair dados SHM reais)

---

## 📊 Estado Atual — Resumo Executivo

### ✅ DESCOBERTO & VALIDADO
- **Protocolo LCD Display** (IL analysis `TRCC_decomp.il`):
  - Magic: `12 34 56 78` (diferente de RGB `DA DB DC DD`)
  - Packet: 64-byte header + JPEG compressed image
  - Header template: `I_00DE3678` contém: `12 34 56 78 02 00 00 00 F0 00 00 00 F0 00 00 00...`
    - Bytes 0-3 = magic `12 34 56 78`
    - Byte 4 = device_type `02` (240×240 display)
    - Bytes 8-11 = width (240 = `F0 00 00 00` LE)
    - Bytes 12-15 = height (240 = `F0 00 00 00` LE)
    - Bytes 60-63 = JPEG size (uint32 LE, updated per packet)
  - Transmission: 512-byte chunks, subdivided into 8×64-byte HID packets
  
- **Windows IPC (Named File Mappings)**:
  - `shareMemory_ImageRGB` — buffer de imagem (JPEG)
  - `shareMemory_Image` — cache redundante
  - `shareMemory_SysInfo` — dados de sensor (CPU temp, GPU temp)
  - ✅ Todas 3 seções enumerável & acessível via NtQuerySystemInformation

- **Tooling Status**:
  - ✅ `nuvoton_hid.py` — working RGB control (tested in daemon)
  - ✅ `nuvoton_daemon.py` — daemon successfully running, setting LED colors dynamically
  - ✅ `frida_hid_hook.js` — script validated, no syntax errors, ready to deploy
  - ✅ `read_lcd_shm_win.py` — sections found & enumerated 30+ times (retry logic working as intended)

### ❌ NÃO VALIDADO AINDA (Necessário para Linux)
- [ ] Dados reais de memória compartilhada (arquivo JPEG/BIN não extraído)
- [ ] Estrutura esperada packet match 100% com IL prediction
- [ ] Sequência de timing entre SHM writes e USB transfers
- [ ] Checksum ou validação de packet (se houver)

### 🔲 AINDA NÃO FEITO
- [ ] Captura de tráfego USB real no Linux (usbmon + Wireshark)
- [ ] Kernel module nuvoton-rgb.c completo
- [ ] Python libusb binding para Linux

---

## 🎯 PRIORIDADES PARA PRÓXIMA SESSÃO (Em Ordem Rigorosa)

### **PRIORITY 1: Extrair Dados SHM Reais (CRÍTICO)**
**Tempo estimado: 5-10 min**

**Por quê**: Validação empírica do formato packet predito via IL analysis.

**Passos**:
1. Criar novo script: `read_lcd_shm_extended.py`
   - Input: seção SHM name, dumpisize, output arquivo
   - Remove guard `nonzero > 64` (era falso alarme de loop)
   - Output: arquivo `.jpg` ou `.bin` com timestamp
   
2. Executar em paralelo:
   ```bash
   # Terminal 1: daemon rodando
   python nuvoton_daemon.py --mode cpu_temp
   
   # Terminal 2: captura SHM
   python read_lcd_shm_extended.py
   ```

3. Validar output:
   - [ ] Arquivo criado com tamanho > 0
   - [ ] Se JPEG: abre em visualizador de imagem (format válido)
   - [ ] Se BIN: hexdump header = `12 34 56 78 02 00 00 00 F0 00...` ?

**Checklist de sucesso**:
- [ ] `captured_image_20260411_hhmmss.jpg` exists & valid
- [ ] First 64 bytes match IL prediction
- [ ] Bytes 60-63 contain valid JPEG size (uint32 LE)

### **PRIORITY 2: Validar Packet Structure (5-10 min)**
**Dependência**: Priority 1 completo

**Passos**:
1. Hexdump arquivo capturado:
   ```bash
   hexdump -C captured_image*.jpg | head -5
   ```
   
2. Comparar com IL analysis:
   - Magic `12 34 56 78` nos bytes 0-3? ✓
   - Device type `02` em byte 4? ✓
   - Width/height 240 (`F0 00 00 00`) em bytes 8-15? ✓
   - JPEG header `FF D8 FF E0` ou `FF D8 FF E1` após byte 64? ✓

3. Documentar em `PROTOCOL.md`:
   - Se match: Atualizar com "Confirmed via SHM dump"
   - Se mismatch: Anote diferenças, discuta possíveis razões

### **PRIORITY 3: Frida Capture (Opcional, 10-15 min)**
**Dependência**: Priority 1-2 completo (confirma cadeia completa)

**Passos**:
1. Instalar Frida: `pip install frida frida-tools`
2. Deploy hook durante priority 1:
   ```bash
   frida -p <PID_TRCC> -l frida_hid_hook.js > frida_capture.log
   ```
3. Correlate Frida WriteFile sizes com JPEG sizes em SHM
4. Validar sequência de packets

**Quando pular**: Se priority 1-2 já validou estrutura, este é nice-to-have

---

## 📁 Arquivos Críticos Para Próxima Sessão

### Ler Primeiro:
- **Este arquivo** (CHECKPOINT_LINUX.md) — situação atual
- [PROTOCOL.md](../PROTOCOL.md) — expected packet structure (será atualizado)

### Código Pronto:
- ✅ `nuvoton_hid.py` — RGB control (não editar, apenas referência)
- ✅ `nuvoton_daemon.py` — daemon (não editar)
- ✅ `frida_hid_hook.js` — HID logger (pronto para deploy)

### Código A Criar:
- 🔴 **`read_lcd_shm_extended.py`** ← CREATE THIS FIRST
  - Baseado em `read_lcd_shm_win.py` linhas 175-207
  - Remover `nonzero > 64` guard, usar `nonzero > 0` instead
  - Procurar JPEG header (`FF D8 FF`) ou dumpar raw `.bin`
  - Salvar com timestamp em filename

### Código A Investigar (Linux):
- 🟡 `nuvoton-rgb.c` — kernel module (skeleton, precisa de protocol real)
- 🟡 `rgb_control.py` — CLI entry point (será atualizado após protocol confirmado)

---

## 🔍 Key Numbers For Reference

| Parâmetro | Valor | Fonte |
|-----------|-------|-------|
| HID Output Size | 65 bytes | HidP_GetCaps |
| HID Input Size | 65 bytes | HidP_GetCaps |
| RGB Magic | `DA DB DC DD` | Device response |
| LCD Magic | `12 34 56 78` | IL analysis (I_00DE3678) |
| LCD Device Type | `02` | IL analysis (offset 4 em template) |
| LCD Width | 240 = `F0 00 00 00` LE | IL analysis (bytes 8-11) |
| LCD Height | 240 = `F0 00 00 00` LE | IL analysis (bytes 12-15) |
| JPEG Size Location | bytes 60-63 | IL analysis (template offset) |
| JPEG Size Format | uint32 LE | IL decompilation ImageToJpg |
| Max Chunk Size | 512 bytes | IL analysis (USB buffer size) |
| HID Packet Payload | 64 bytes | Calculated (65 - 1 report ID) |
| Max Chunks Per JPEG | 512 ÷ 64 = 8 packets | Design |

---

## 🛟 Se Travar Novamente

1. **Não mergulhe em IL file novamente** — foi loop improdutivo
2. **Não tente capturar packets sem SHM validation first** — prioridade está errada
3. **Frida é backup apenas** — SHM dump é evidence primária & mais rápido
4. **Se timeout de tokens**: Executar PRIORITY 1 script simples = saída rápida com dados reais

---

## 💾 Estado de Conhecimento Preservado

Informação crítica do chat anterior (not in current context):
- TRCC Process ID: monitorado dinamicamente via `Get-Process TRCC`
- Device Path: `\\?\HID#VID_0416&PID_8001#9&1b1a914f&1&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}`
- SHM Enumeration: via ntdll.NtQuerySystemInformation (MappedFile section type)
- Frida Deployment: `frida -p <PID> -l script.js`



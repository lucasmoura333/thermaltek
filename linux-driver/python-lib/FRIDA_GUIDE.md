# Guia: Captura de Protocolo com Frida

## O que isso faz

O Frida intercepta as chamadas da Windows HID API feitas pelo TRCC.exe **em memória**, sem precisar de driver especial. Cada pacote enviado ao dispositivo (e cada resposta) é impresso com hex dump completo.

## Passo a Passo

### 1. Instalar dependências

```powershell
pip install frida frida-tools
```

Verifique:
```powershell
frida --version
```

### 2. (Opcional) Ler o HID Report Descriptor

Antes do Frida, tente ler o descriptor do dispositivo — ele revela o schema dos pacotes:

```powershell
python get_report_descriptor.py
```

Se funcionar, o output mostrará tamanhos exatos de report, campos, usage pages.  
**Se o Usage Page for `0xFF**` (vendor-defined), confirma protocolo proprietário.**

### 3. Abrir o TRCC

Abra o TRCC normalmente. Deixe ele na tela principal mostrando o dispositivo.

### 4. Executar o hook

**Opção A — Attach a processo existente (recomendado)**:
```powershell
python run_frida_hook.py
```
Isso encontra o TRCC.exe automaticamente e se attacha a ele.

**Opção B — Com PID específico**:
```powershell
# Descobrir PID:
tasklist | findstr TRCC

# Attachar:
python run_frida_hook.py --pid 1234
```

**Opção C — Spawn (TRCC ainda não está aberto)**:
```powershell
python run_frida_hook.py --spawn --path "C:\Program Files\Thermaltake\TRCC\TRCC.exe"
```

### 5. Executar operações no TRCC

Com o Frida rodando, faça **cada uma** dessas operações no TRCC, **pausando 2-3 segundos entre elas**:

```
[ ] 1. Apenas abrir o TRCC (captura sequência de inicialização)
[ ] 2. Mudar cor → Vermelho puro (R=255, G=0, B=0)
[ ] 3. Mudar cor → Verde puro (R=0, G=255, B=0)
[ ] 4. Mudar cor → Azul puro (R=0, G=0, B=255)
[ ] 5. Selecionar modo "Rainbow"
[ ] 6. Selecionar modo "Color cycle"
[ ] 7. Selecionar modo "monochrome breathe"
[ ] 8. Selecionar modo "monochrome" (estático)
[ ] 9. Arrastar brightness para mínimo (0%)
[ ] 10. Arrastar brightness para máximo (100%)
[ ] 11. Clicar no botão power (desligar LEDs)
[ ] 12. Clicar no botão power (ligar LEDs)
```

### 6. Parar e analisar

Pressione `Ctrl+C` no terminal do Frida. O arquivo `hid_capture.txt` terá todos os pacotes.

### 7. Analisar os pacotes capturados

Com os packets de vermelho, verde e azul side-by-side, os bytes de R,G,B ficam óbvios por diferença:

```
RED:   DA DB DC DD XX XX FF 00 00 ...
GREEN: DA DB DC DD XX XX 00 FF 00 ...
BLUE:  DA DB DC DD XX XX 00 00 FF ...
                         ^  ^  ^
                         R  G  B
```

---

## O que o hook intercepta

| Função | Direção | O que captura |
|--------|---------|---------------|
| `WriteFile` | HOST → DEVICE | Todos os writes HID |
| `ReadFile` | DEVICE → HOST | Todos os reads HID |
| `HidD_SetOutputReport` | HOST → DEVICE | Output reports explícitos |
| `HidD_GetInputReport` | DEVICE → HOST | Input reports explícitos |
| `HidD_SetFeature` | HOST → DEVICE | Feature reports enviados |
| `HidD_GetFeature` | DEVICE → HOST | Feature reports recebidos |
| `DeviceIoControl` (HID IOCTLs) | ambos | Baixo nível |
| `CreateFileW` | — | Identifica o handle do dispositivo |

---

## Troubleshooting

**"Access denied" ao attachar**:
- Execute o terminal como Administrador
- Ou: Right-click → "Run as Administrator" no PowerShell

**Processo TRCC não encontrado**:
- Verifique com `tasklist | findstr TRCC`
- O executável pode ter outro nome (`ThermalrightCC.exe`, etc.)
- Use `--spawn` para iniciar o TRCC pelo Frida

**Nenhum pacote aparece (zero output)**:
- O TRCC pode usar uma path diferente do HID API (ex: via .NET marshaling)
- Tente deixar o Frida rodando e clicar em várias coisas no TRCC
- Se ainda nada aparecer, veja a seção "Fallback: Ghidra" no PROGRESS.md

**Frida recusa attachar (possível anti-debug)**:
- Use `--spawn` para injetar antes do processo inicializar
- Ou use `frida -n TRCC.exe --realm=remote -l frida_hid_hook.js`

---

## Arquivos desta sessão

| Arquivo | Função |
|---------|--------|
| `frida_hid_hook.js` | Script Frida — hooks HID API |
| `run_frida_hook.py` | Launcher Python com auto-detect |
| `get_report_descriptor.py` | Lê descriptor HID do dispositivo |
| `hid_capture.txt` | Output gerado pela captura (criado ao rodar) |

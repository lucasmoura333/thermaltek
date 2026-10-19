# Guia de Instalação - Nuvoton RGB Controller Driver

Este guia fornece instruções detalhadas para instalação do driver em diferentes distribuições Linux.

## 📋 Pré-requisitos

### Verificar o Dispositivo

Primeiro, verifique se o dispositivo está conectado:

```bash
lsusb | grep 0416
```

Você deve ver algo como:
```
Bus 001 Device 005: ID 0416:8001 Winbond Electronics Corp. HID Transfer
```

### Dependências por Distribuição

#### Ubuntu / Debian / Linux Mint

```bash
sudo apt update
sudo apt install build-essential linux-headers-$(uname -r) \
                 python3 python3-pip libhidapi-dev git
```

#### Fedora / RHEL / CentOS

```bash
sudo dnf install kernel-devel kernel-headers gcc make \
                 python3 python3-pip hidapi-devel git
```

#### Arch Linux / Manjaro

```bash
sudo pacman -S base-devel linux-headers python python-pip hidapi git
```

#### openSUSE

```bash
sudo zypper install kernel-devel gcc make python3 python3-pip libhidapi-devel git
```

## 🚀 Instalação

### Método 1: Script Automático (Recomendado)

```bash
# Navegue até o diretório
cd linux-driver

# Torne o script executável
chmod +x build.sh

# Execute (requer sudo)
sudo ./build.sh
```

O script irá:
1. ✅ Verificar dependências
2. ✅ Compilar o módulo do kernel
3. ✅ Instalar o módulo
4. ✅ Configurar regras udev
5. ✅ Instalar ferramentas Python
6. ✅ Carregar o módulo
7. ✅ Verificar a instalação

### Método 2: Instalação Manual

#### Passo 1: Compilar o Módulo do Kernel

```bash
cd linux-driver

# Limpar builds anteriores
make clean

# Compilar
make

# Verificar se compilou
ls -lh nuvoton-rgb.ko
```

#### Passo 2: Instalar o Módulo

```bash
# Instalar no sistema
sudo make install

# Atualizar módulos
sudo depmod -a
```

#### Passo 3: Configurar Permissões (Regras Udev)

```bash
# Copiar regras udev
sudo cp 99-nuvoton-rgb.rules /etc/udev/rules.d/

# Recarregar regras
sudo udevadm control --reload-rules
sudo udevadm trigger

# Adicionar usuário ao grupo plugdev (uma vez)
sudo usermod -a -G plugdev $USER
```

> [!IMPORTANT]
> Após adicionar-se ao grupo `plugdev`, você precisa fazer logout e login novamente para as mudanças terem efeito.

#### Passo 4: Carregar o Módulo

```bash
# Carregar módulo
sudo modprobe nuvoton-rgb

# Verificar se carregou
lsmod | grep nuvoton
```

#### Passo 5: Instalar Ferramentas Python

```bash
cd python-lib

# Instalar dependências
pip3 install -r requirements.txt

# Ou com usuário (sem sudo)
pip3 install --user -r requirements.txt

# Tornar scripts executáveis
chmod +x rgb_control.py protocol_discovery.py
```

## ✅ Verificação da Instalação

### 1. Verificar Módulo do Kernel

```bash
# Verificar se está carregado
lsmod | grep nuvoton

# Ver informações do módulo
modinfo nuvoton-rgb

# Ver logs do kernel
dmesg | grep -i nuvoton
```

Saída esperada em dmesg:
```
[  123.456789] hid-generic 0003:0416:8001.000X: Nuvoton RGB Controller detected
[  123.456790] hid-generic 0003:0416:8001.000X: Nuvoton RGB Controller initialized successfully
```

### 2. Verificar Interface Sysfs

```bash
# Listar dispositivos HID
ls -l /sys/bus/hid/devices/

# Verificar atributos do nosso dispositivo
ls -l /sys/bus/hid/devices/*/red
```

### 3. Testar Ferramentas Python

```bash
cd python-lib

# Testar conexão
python3 rgb_control.py --test-connection

# Listar dispositivos
python3 rgb_control.py --list
```

### 4. Teste Rápido de Cor

```bash
# Via sysfs
echo "255 0 0" | sudo tee /sys/bus/hid/devices/*/color

# Via Python
python3 rgb_control.py --color 255 0 0
```

## 🔧 Configuração Adicional

### Auto-load do Módulo no Boot

Para carregar automaticamente o módulo na inicialização:

```bash
echo "nuvoton-rgb" | sudo tee /etc/modules-load.d/nuvoton-rgb.conf
```

### Criar Alias (Opcional)

Adicione ao seu `~/.bashrc` ou `~/.zshrc`:

```bash
alias rgb='python3 /caminho/para/linux-driver/python-lib/rgb_control.py'
```

Depois, recarregue:
```bash
source ~/.bashrc
```

Agora você pode usar:
```bash
rgb --color 255 0 0
rgb --rainbow 30
```

### Daemon do display de segmentos + systemd

O daemon Python **não precisa** do módulo de kernel nem de hidapi: em Linux
ele usa por padrão o backend **hidraw** (`/dev/hidraw*`, VID 0416 / PID 8001)
— puro stdlib — e lê sensores via `/sys/class/hwmon` (k10temp/zenpower/
coretemp) e `/sys/class/drm` (amdgpu, GPU discreta preferida). Para forçar
o backend: `NUVOTON_BACKEND=hidraw|hidapi`.

```bash
cd python-lib
pip3 install -r requirements.txt          # psutil (hidapi é opcional)
python3 lcd_sender.py --query             # handshake: PM=0x10
python3 lcd_sender.py --demo --duration 5 # números fixos (checagem visual)
python3 nuvoton_daemon.py --mode display  # métricas ao vivo (Ctrl-C desliga)
```

Para rodar como serviço (como o seu usuário — a regra udev já dá acesso ao
`/dev/hidraw*`; sem root em runtime):

```bash
# 1. edite User= e WorkingDirectory= em systemd/nuvoton-display.service
sudo cp systemd/nuvoton-display.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nuvoton-display
journalctl -u nuvoton-display -f          # logs ao vivo
```

## 🐛 Troubleshooting

### Problema: Módulo não compila

**Erro**: `fatal error: linux/module.h: No such file or directory`

**Solução**: Instale os headers do kernel:
```bash
# Ubuntu/Debian
sudo apt install linux-headers-$(uname -r)

# Fedora
sudo dnf install kernel-devel

# Arch
sudo pacman -S linux-headers
```

### Problema: Permissão negada ao acessar dispositivo

**Erro**: `PermissionError: [Errno 13] Permission denied`

**Solução**:
```bash
# 1. Verificar se udev rules estão instaladas
ls -l /etc/udev/rules.d/99-nuvoton-rgb.rules

# 2. Recarregar udev
sudo udevadm control --reload-rules
sudo udevadm trigger

# 3. Verificar grupos do usuário
groups

# 4. Adicionar ao plugdev se necessário
sudo usermod -a -G plugdev $USER

# 5. Logout e login novamente
```

### Problema: Módulo não carrega

**Erro**: `modprobe: ERROR: could not insert 'nuvoton_rgb'`

**Solução**:
```bash
# Ver erro específico
dmesg | tail -20

# Recompilar do zero
make clean
make
sudo make install
sudo depmod -a
sudo modprobe nuvoton-rgb
```

### Problema: Python não encontra hidapi

**Erro**: `ModuleNotFoundError: No module named 'hid'`

> [!NOTE]
> **No Linux isso não bloqueia nada**: o daemon/sender usam por padrão o
> backend **hidraw** (puro stdlib). O hidapi é só o fallback
> (`NUVOTON_BACKEND=hidapi` para forçá-lo).

**Solução**: 
```bash
# Instalar biblioteca do sistema
sudo apt install libhidapi-dev  # Ubuntu/Debian
sudo dnf install hidapi-devel   # Fedora
sudo pacman -S hidapi           # Arch

# Instalar pacote Python
pip3 install hidapi
```

### Problema: Dispositivo não detectado

**Sintoma**: `lsusb` não mostra 0416:8001

**Solução**:
```bash
# 1. Verificar conexão física
# 2. Verificar em outra porta USB
# 3. Verificar se funciona no Windows

# 4. Ver todos dispositivos USB
lsusb -v

# 5. Verificar dmesg quando conectar
dmesg -w
# (conecte o dispositivo e veja as mensagens)
```

## 🔄 Desinstalação

Se você precisar remover o driver:

```bash
# 1. Descarregar módulo
sudo modprobe -r nuvoton-rgb

# 2. Remover módulo instalado
sudo rm /lib/modules/$(uname -r)/extra/nuvoton-rgb.ko
sudo depmod -a

# 3. Remover udev rules
sudo rm /etc/udev/rules.d/99-nuvoton-rgb.rules
sudo udevadm control --reload-rules

# 4. Remover auto-load
sudo rm /etc/modules-load.d/nuvoton-rgb.conf

# 5. Desinstalar Python packages
pip3 uninstall hidapi
```

## 📚 Próximos Passos

Após a instalação bem-sucedida:

1. **Leia o README.md** para exemplos de uso
2. **Execute protocol_discovery.py** para tentar descobrir o protocolo correto
3. **Teste diferentes cores e efeitos**
4. **Contribua** com descobertas!

## 🆘 Suporte

Se você encontrar problemas:

1. Verifique os logs do kernel: `dmesg | grep -i nuvoton`
2. Teste com modo verbose: `python3 rgb_control.py --verbose --test-connection`
3. Verifique a documentação em [PROTOCOL.md](PROTOCOL.md)

## 📝 Notas de Segurança

> [!CAUTION]
> - Módulos de kernel mal escritos podem causar kernel panic
> - Sempre teste em ambiente seguro primeiro
> - Mantenha backups importantes
> - Considere testar em VM antes de usar no sistema principal

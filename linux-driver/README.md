# Nuvoton RGB Controller - Linux Driver

Driver Linux customizado para o controlador RGB Thermaltake Assassin 120 Digital (Nuvoton 0416:8001).

## 📋 Visão Geral

Este projeto fornece um driver Linux completo para o controlador RGB Nuvoton, incluindo:
- **Módulo de Kernel**: Driver HID nativo com interface sysfs
- **Ferramentas Userspace**: Scripts Python para controle e teste
- **Protocol Discovery**: Ferramentas para engenharia reversa do protocolo

## 🔧 Informações Técnicas

**Dispositivo:**
- Vendor ID: `0x0416` (Winbond Electronics Corp./Nuvoton)
- Product ID: `0x8001`
- Nome: HID Transfer
- Tipo: Dispositivo HID puro
- Endpoints: 0x81 (IN), 0x02 (OUT)
- Tamanho do pacote: 64 bytes

## 📦 Instalação

### Pré-requisitos

```bash
# Ubuntu/Debian
sudo apt install build-essential linux-headers-$(uname -r) python3 python3-pip libhidapi-dev

# Fedora/RHEL
sudo dnf install kernel-devel gcc make python3 python3-pip hidapi-devel

# Arch Linux
sudo pacman -S base-devel linux-headers python python-pip hidapi
```

### Instalação Automática

```bash
cd linux-driver
sudo ./build.sh
```

### Instalação Manual

#### 1. Compilar Módulo do Kernel

```bash
make
sudo make install
```

#### 2. Instalar Regras Udev

```bash
sudo cp 99-nuvoton-rgb.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

#### 3. Carregar Módulo

```bash
sudo modprobe nuvoton-rgb
```

#### 4. Instalar Ferramentas Python

```bash
cd python-lib
pip3 install -r requirements.txt
```

## 🚀 Uso

### Interface Sysfs (Kernel Module)

Quando o módulo está carregado, você pode controlar o dispositivo via sysfs:

```bash
# Definir cor vermelha
echo 255 > /sys/bus/hid/devices/*/red
echo 0 > /sys/bus/hid/devices/*/green
echo 0 > /sys/bus/hid/devices/*/blue

# Ou definir todas de uma vez
echo "255 0 0" > /sys/bus/hid/devices/*/color

# Ler valores atuais
cat /sys/bus/hid/devices/*/color
```

### Ferramenta CLI Python

```bash
cd python-lib

# Testar conexão
python3 rgb_control.py --test-connection

# Definir cor RGB
python3 rgb_control.py --color 255 0 0      # Vermelho
python3 rgb_control.py --color 0 255 0      # Verde
python3 rgb_control.py --color 0 0 255      # Azul

# Usar código hexadecimal
python3 rgb_control.py --hex "#FF00FF"      # Magenta

# Efeito arco-íris
python3 rgb_control.py --rainbow 30         # 30 segundos

# Efeito pulse
python3 rgb_control.py --pulse 255 0 0 20   # Vermelho por 20 segundos

# Modo interativo
python3 rgb_control.py --interactive
```

### Protocol Discovery

Para continuar descobrindo o protocolo proprietário:

```bash
cd python-lib

# Testes sistemáticos
python3 protocol_discovery.py --systematic

# Brute force (lento)
python3 protocol_discovery.py --brute-force

# Exportar resultados
python3 protocol_discovery.py --systematic --export results.json
```

## 🔍 Verificação

### Verificar se o dispositivo foi detectado

```bash
# Listar dispositivos USB
lsusb | grep 0416:8001

# Verificar módulo carregado
lsmod | grep nuvoton

# Ver logs do kernel
dmesg | grep -i nuvoton
```

### Testar comunicação HID

```bash
# Listar dispositivos HID
ls /sys/bus/hid/devices/

# Ver informações do dispositivo
cat /sys/bus/hid/devices/*/uevent
```

## 📖 Estrutura do Projeto

```
linux-driver/
├── nuvoton-rgb.c           # Módulo do kernel
├── Makefile                # Build do módulo
├── 99-nuvoton-rgb.rules    # Regras udev
├── build.sh                # Script de instalação
├── README.md               # Este arquivo
├── PROTOCOL.md             # Documentação do protocolo
├── INSTALL.md              # Guia detalhado de instalação
└── python-lib/
    ├── nuvoton_hid.py      # Biblioteca HID
    ├── rgb_control.py      # Ferramenta de controle
    ├── protocol_discovery.py  # Discovery de protocolo
    └── requirements.txt    # Dependências Python
```

## ⚠️ Problemas Conhecidos

1. **Protocolo Desconhecido**: O protocolo exato ainda está sendo descoberto. Os comandos implementados são tentativas baseadas em padrões comuns.

2. **Sem Resposta Visual**: Se o RGB não mudar, o protocolo pode ser diferente do implementado. Use `protocol_discovery.py` para testar.

3. **Permissões**: Se você receber erros de permissão, certifique-se de que as regras udev foram instaladas e que você está no grupo `plugdev`:
   ```bash
   sudo usermod -a -G plugdev $USER
   # Logout e login novamente
   ```

## 🛠️ Troubleshooting

### Módulo não carrega

```bash
# Verificar erros
dmesg | tail -20

# Recompilar
make clean && make
```

### Dispositivo não encontrado

```bash
# Verificar se está conectado
lsusb | grep 0416

# Recarregar regras udev
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### Python não encontra dispositivo

```bash
# Instalar hidapi
pip3 install hidapi

# Testar com permissões root
sudo python3 rgb_control.py --test-connection
```

## 📚 Documentação Adicional

- [INSTALL.md](INSTALL.md) - Guia detalhado de instalação
- [PROTOCOL.md](PROTOCOL.md) - Documentação do protocolo HID

## 📝 Licença

GPL v2 - Veja o código do kernel module para detalhes.

## 🤝 Contribuindo

Este driver está em desenvolvimento ativo. Contribuições são bem-vindas, especialmente:
- Descoberta do protocolo correto
- Testes em diferentes distribuições
- Melhorias no código

## 🔗 Links Úteis

- [Linux HID Documentation](https://www.kernel.org/doc/html/latest/hid/index.html)
- [hidapi Library](https://github.com/libusb/hidapi)
- [USB HID Usage Tables](https://www.usb.org/hid)

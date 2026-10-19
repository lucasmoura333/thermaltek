#!/bin/bash
# Setup WSL Environment for Nuvoton Driver Dev

echo "🐧 Setting up WSL Environment..."

# 1. Install System Dependencies
echo "📦 Installing system packages..."
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv usbutils wireshark-common tshark libhidapi-hidraw0 libusb-1.0-0-dev

# 2. Configure Wireshark Permissions
echo "🔑 Configuring permissions..."
sudo usermod -aG wireshark $USER
sudo chmod +x /usr/bin/dumpcap

# 3. Setup Python Environment
echo "🐍 Setting up Python..."
python3 -m venv venv
source venv/bin/activate
pip install hidapi pyusb colorama

# 4. Load USB Monitor Module
echo "🔌 Loading usbmon module..."
sudo modprobe usbmon
sudo chmod 777 /dev/usbmon*

echo "✅ Setup Complete!"
echo "To activate python env: source venv/bin/activate"

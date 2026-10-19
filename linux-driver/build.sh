#!/bin/bash
# Build and installation script for Nuvoton RGB Driver

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "========================================="
echo "Nuvoton RGB Driver Build & Install"
echo "========================================="
echo ""

# Check if running as root for kernel module operations
check_root() {
    if [ "$EUID" -ne 0 ]; then
        echo "ERROR: This script must be run with sudo for kernel module installation"
        echo "Usage: sudo ./build.sh"
        exit 1
    fi
}

# Check dependencies
check_dependencies() {
    echo "Checking dependencies..."
    
    # Check kernel headers
    if [ ! -d "/lib/modules/$(uname -r)/build" ]; then
        echo "ERROR: Kernel headers not found!"
        echo "Install them with:"
        echo "  Ubuntu/Debian: sudo apt install linux-headers-\$(uname -r)"
        echo "  Fedora/RHEL: sudo dnf install kernel-devel"
        echo "  Arch: sudo pacman -S linux-headers"
        exit 1
    fi
    
    # Check for make
    if ! command -v make &> /dev/null; then
        echo "ERROR: make not found!"
        echo "Install build-essential/base-devel package"
        exit 1
    fi
    
    # Check for Python
    if ! command -v python3 &> /dev/null; then
        echo "WARNING: python3 not found! Userspace tools will not work."
    fi
    
    # Check for pip
    if ! command -v pip3 &> /dev/null; then
        echo "WARNING: pip3 not found! Install it to use userspace tools."
    fi
    
    echo "  Dependencies OK"
    echo ""
}

# Build kernel module
build_kernel_module() {
    echo "Building kernel module..."
    make clean
    make
    echo "  Kernel module built successfully"
    echo ""
}

# Install kernel module
install_kernel_module() {
    echo "Installing kernel module..."
    make install
    echo "  Kernel module installed"
    echo ""
}

# Install udev rules
install_udev_rules() {
    echo "Installing udev rules..."
    cp 99-nuvoton-rgb.rules /etc/udev/rules.d/
    udevadm control --reload-rules
    udevadm trigger
    echo "  Udev rules installed"
    echo ""
}

# Install Python tools
install_python_tools() {
    echo "Installing Python tools..."
    
    if command -v pip3 &> /dev/null; then
        cd python-lib
        pip3 install -r requirements.txt
        
        # Make scripts executable
        chmod +x rgb_control.py
        chmod +x protocol_discovery.py
        
        echo "  Python tools installed"
        cd ..
    else
        echo "  Skipping Python tools (pip3 not available)"
    fi
    echo ""
}

# Load kernel module
load_module() {
    echo "Loading kernel module..."
    
    # Unload if already loaded
    if lsmod | grep -q nuvoton_rgb; then
        rmmod nuvoton-rgb 2>/dev/null || true
    fi
    
    modprobe nuvoton-rgb
    echo "  Module loaded"
    echo ""
}

# Verify installation
verify_installation() {
    echo "Verifying installation..."
    
    # Check if module is loaded
    if lsmod | grep -q nuvoton_rgb; then
        echo "  ✓ Kernel module loaded"
    else
        echo "  ✗ Kernel module not loaded"
    fi
    
    # Check for device
    if lsusb | grep -q "0416:8001"; then
        echo "  ✓ Device detected"
    else
        echo "  ✗ Device not detected (make sure it's connected)"
    fi
    
    # Check dmesg for driver messages
    echo ""
    echo "Recent kernel messages:"
    dmesg | grep -i nuvoton | tail -5
    
    echo ""
}

# Main installation
main() {
    check_root
    check_dependencies
    build_kernel_module
    install_kernel_module
    install_udev_rules
    install_python_tools
    load_module
    verify_installation
    
    echo "========================================="
    echo "Installation Complete!"
    echo "========================================="
    echo ""
    echo "Next steps:"
    echo "1. Check device detection:"
    echo "   lsusb | grep 0416:8001"
    echo ""
    echo "2. Try Python control tool:"
    echo "   cd python-lib"
    echo "   python3 rgb_control.py --test-connection"
    echo ""
    echo "3. Set a color:"
    echo "   python3 rgb_control.py --color 255 0 0"
    echo ""
    echo "4. Run protocol discovery:"
    echo "   python3 protocol_discovery.py --systematic"
    echo ""
}

main

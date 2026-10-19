#!/bin/bash
# Debug Nuvoton Driver in WSL

DIR="/tmp/nuvoton-driver"
cd $DIR

echo "🔍 Checking environment..."

# Ensure dependencies
if ! command -v lsusb &> /dev/null; then
    echo "Installing usbutils..."
    apt-get update && apt-get install -y usbutils
fi

if ! command -v tshark &> /dev/null; then
    echo "Installing tshark..."
    apt-get install -y tshark
fi

# Find Device
echo "🔍 Looking for Nuvoton device..."
DEV_LINE=$(lsusb -d 0416:8001)

if [ -z "$DEV_LINE" ]; then
    echo "❌ Device 0416:8001 NOT FOUND in WSL!"
    echo "Did you run the setup script as Admin?"
    echo "Try running 'usbipd attach --wsl --busid 4-17' in Windows Admin PowerShell."
    exit 1
fi

echo "✅ Found: $DEV_LINE"

# Extract Bus ID for usbmon
# Bus 002 Device 003... -> usbmon2
BUS=$(echo $DEV_LINE | awk '{print $2}')
BUS_NUM=${BUS#00} # Remove leading zeros
MON_IF="usbmon$BUS_NUM"

echo "📡 Capturing traffic on $MON_IF..."

# Start TShark in background
# Filter for our device address
DEV_ADDR=$(echo $DEV_LINE | awk '{print $4}' | sed 's/://')
DEV_ADDR_NUM=$((10#$DEV_ADDR))

CAPTURE_FILE="capture_wsl.pcapng"

# Capture filters are tricky with usbmon, capturing everything on bus for now
tshark -i $MON_IF -w $CAPTURE_FILE -a duration:10 &
TSHARK_PID=$!

echo "⏳ TShark started (PID $TSHARK_PID). Waiting 2s..."
sleep 2

# Run Python Test
echo "🚀 Running Python Test..."
source venv/bin/activate
python3 python-lib/test_magic.py

echo "🛑 Stopping capture..."
kill $TSHARK_PID 2>/dev/null
wait $TSHARK_PID 2>/dev/null

echo "📊 Analyzing Capture..."
echo "==================================================="
# Read back capture, looking for URB status errors
tshark -r $CAPTURE_FILE -Y "usb.device_address == $DEV_ADDR_NUM" -T fields -e frame.time_relative -e usb.transfer_type -e usb.urb_type -e usb.endpoint_address -e usb.urb_status -e usb.data_fragment
echo "==================================================="
echo "Capture saved to $DIR/$CAPTURE_FILE"

"""
Use pythonnet to directly call UsbHid.dll from Python.
This bypasses all handle/API differences by using the EXACT same code path as TRCC.
"""
import sys
import os
import time

# First check if pythonnet is installed
try:
    import clr
    print("pythonnet is available!")
except ImportError:
    print("pythonnet not installed. Installing...")
    os.system(f'"{sys.executable}" -m pip install pythonnet')
    import clr

# Add reference to UsbHid.dll
TRCC_DIR = r"C:\Program Files\TRCCCAP"
USB_HID_DLL = os.path.join(TRCC_DIR, "UsbHid.dll")

if not os.path.exists(USB_HID_DLL):
    print(f"UsbHid.dll not found at {USB_HID_DLL}")
    sys.exit(1)

print(f"Loading UsbHid.dll from: {USB_HID_DLL}")
clr.AddReference(USB_HID_DLL)

# Import .NET types
from UsbHid import UsbHidDevice
from UsbHid.USB.Classes.Messaging import CommandMessage
from System.Collections import ArrayList

VID = 0x0416
PID = 0x8001

print(f"\nCreating UsbHidDevice(VID={VID:#06x}, PID={PID:#06x}, count=64)...")

# Match TRCC's constructor call: new UsbHidDevice(VID, PID, null, 64)
dev = UsbHidDevice(VID, PID, ArrayList(), 64)

# Wait for device connection with retries
print("Waiting for device connection...")
for i in range(20):
    time.sleep(1)
    connected = dev.IsDeviceConnected
    print(f"  Attempt {i+1}/20: connected={connected}")
    if connected:
        break

if not connected:
    print("\nDevice not connected after 20 seconds.")
    print("Trying alternative: enumerate HID devices to check interfaces...")
    
    # List all HID interfaces for this VID/PID
    try:
        import hid
        devices = hid.enumerate(VID, PID)
        print(f"\nFound {len(devices)} HID interface(s):")
        for d in devices:
            path = d['path'].decode() if isinstance(d['path'], bytes) else d['path']
            print(f"  Path: {path}")
            print(f"  Usage Page: {d['usage_page']:#06x}, Usage: {d['usage']:#06x}")
            print(f"  Interface: {d.get('interface_number', 'N/A')}")
            print(f"  Product: {d.get('product_string', 'N/A')}")
            print(f"  Contains 'mi_01': {'mi_01' in path}")
            print(f"  Contains 'kbd': {'kbd' in path}")
            print()
    except Exception as e:
        print(f"  hid enumerate error: {e}")
    
    sys.exit(1)

# ============ STEP 1: Send init packet (DeviceOnConnected1) ============
print("\n--- Step 1: Sending init packet ---")
init_data = bytes([
    0xDA, 0xDB, 0xDC, 0xDD,
    0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00,
    0x01, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00,
])
msg = CommandMessage(init_data)
result = dev.SendMessage(msg)
print(f"Init packet sent, result: {result}")
time.sleep(0.5)

# ============ STEP 2: Send GET_STATE query ============
print("\n--- Step 2: Sending GET_STATE query ---")
query_data = bytes([0xDA, 0xDB, 0xDC, 0xDD, 0x02, 0x00])
msg = CommandMessage(query_data)
result = dev.SendMessage(msg)
print(f"Query sent, result: {result}")
time.sleep(0.5)

# ============ STEP 3: Send LED data (ALL RED, 84 LEDs) ============
print("\n--- Step 3: Sending RED LED packet ---")

# Build exactly like TRCC: header(20) + RGB data(252) = 272 bytes
n_leds = 84
brightness = 0.4

# All RED
r = int(255 * brightness)  # 102
g = 0
b = 0

rgb_data = bytes([r, g, b] * n_leds)  # 252 bytes

header = bytes([
    0xDA, 0xDB, 0xDC, 0xDD,  # magic
    0x00, 0x00, 0x00, 0x00,  # bytes 4-7
    0x00, 0x00, 0x00, 0x00,  # bytes 8-11
    0x02, 0x00, 0x00, 0x00,  # bytes 12-15
    len(rgb_data) & 0xFF, (len(rgb_data) >> 8) & 0xFF, 0x00, 0x00,  # bytes 16-19: 0xFC, 0x00
])

full_packet = header + rgb_data  # 272 bytes
print(f"  Full packet size: {len(full_packet)} bytes")
print(f"  Header: {' '.join(f'{b:02X}' for b in full_packet[:20])}")
print(f"  First RGB bytes: {' '.join(f'{b:02X}' for b in full_packet[20:32])}")

# Send using ThreadSendDeviceData1's chunking logic:
# Chunk into 64-byte pieces, each wrapped in CommandMessage
offset = 0
remaining = len(full_packet)
chunk_num = 0
while remaining > 0:
    if remaining > 64:
        chunk = full_packet[offset:offset+64]
        remaining -= 64
        offset += 64
    else:
        chunk = full_packet[offset:offset+remaining]
        remaining = 0
    
    msg = CommandMessage(chunk)
    result = dev.SendMessage(msg)
    chunk_num += 1
    if chunk_num <= 3:
        hex_data = ' '.join(f'{c:02X}' for c in chunk[:20])
        print(f"  Chunk {chunk_num}: {len(chunk)} bytes, result={result}, data={hex_data}")

print(f"  Sent {chunk_num} chunks total")
print(f"\nWaiting 5 seconds - check LED color!")
time.sleep(5)

# ============ STEP 4: Send LED data (ALL BLUE) ============
print("\n--- Step 4: Sending BLUE LED packet ---")
rgb_data = bytes([0, 0, int(255 * brightness)] * n_leds)
header = bytes([
    0xDA, 0xDB, 0xDC, 0xDD,
    0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00,
    0x02, 0x00, 0x00, 0x00,
    len(rgb_data) & 0xFF, (len(rgb_data) >> 8) & 0xFF, 0x00, 0x00,
])
full_packet = header + rgb_data

offset = 0
remaining = len(full_packet)
while remaining > 0:
    if remaining > 64:
        chunk = full_packet[offset:offset+64]
        remaining -= 64
        offset += 64
    else:
        chunk = full_packet[offset:offset+remaining]
        remaining = 0
    msg = CommandMessage(chunk)
    dev.SendMessage(msg)

print("BLUE sent! Waiting 5 seconds...")
time.sleep(5)

# ============ STEP 5: Send LED data (ALL GREEN) ============
print("\n--- Step 5: Sending GREEN LED packet ---")
rgb_data = bytes([0, int(255 * brightness), 0] * n_leds)
header = bytes([
    0xDA, 0xDB, 0xDC, 0xDD,
    0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00,
    0x02, 0x00, 0x00, 0x00,
    len(rgb_data) & 0xFF, (len(rgb_data) >> 8) & 0xFF, 0x00, 0x00,
])
full_packet = header + rgb_data

offset = 0
remaining = len(full_packet)
while remaining > 0:
    if remaining > 64:
        chunk = full_packet[offset:offset+64]
        remaining -= 64
        offset += 64
    else:
        chunk = full_packet[offset:offset+remaining]
        remaining = 0
    msg = CommandMessage(chunk)
    dev.SendMessage(msg)

print("GREEN sent! Waiting 5 seconds...")
time.sleep(5)

print("\n" + "=" * 60)
print("ALL TESTS COMPLETE. Did any LED colors change?")
print("=" * 60)

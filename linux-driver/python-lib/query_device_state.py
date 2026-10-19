"""
Query device state multiple times to detect changes after manual TRCC color change.
Also try different query commands.
"""
import time
import hid

VID = 0x0416
PID = 0x8001

def send_recv(dev, data, wait_ms=300):
    padded = bytes(data) + bytes(64 - len(data))
    pkt = bytes([0x00]) + padded
    dev.write(pkt)
    time.sleep(wait_ms / 1000.0)
    responses = []
    while True:
        r = dev.read(64, timeout_ms=100)
        if not r:
            break
        responses.append(bytes(r))
    return responses

def hex_str(data):
    return ' '.join(f'{b:02X}' for b in data)

dev = hid.device()
dev.open(VID, PID)
print(f"Device: {dev.get_manufacturer_string()} / {dev.get_product_string()}")
dev.set_nonblocking(1)

# Query 1: DA DB DC DD 02 00 (GET_STATE from TRCC constants)
print("\n[Q1] GET_STATE: DA DB DC DD 02 00")
for r in send_recv(dev, [0xDA, 0xDB, 0xDC, 0xDD, 0x02, 0x00]):
    print(f"  RX: {hex_str(r)}")

# Query 2: DA DB DC DD 00 00 (variant)
print("\n[Q2] Variant: DA DB DC DD 00 00")
for r in send_recv(dev, [0xDA, 0xDB, 0xDC, 0xDD, 0x00, 0x00]):
    print(f"  RX: {hex_str(r)}")

# Query 3: DA DB DC DD 01 00 (STATE from constants: USB_PACKED_STATE=0x01)
print("\n[Q3] STATE: DA DB DC DD 01 00")
for r in send_recv(dev, [0xDA, 0xDB, 0xDC, 0xDD, 0x01, 0x00]):
    print(f"  RX: {hex_str(r)}")

# Query 4: DA DB DC DD 04 00 (AUDIO from constants: USB_PACKED_AUDIO=0x04)
print("\n[Q4] AUDIO: DA DB DC DD 04 00")
for r in send_recv(dev, [0xDA, 0xDB, 0xDC, 0xDD, 0x04, 0x00]):
    print(f"  RX: {hex_str(r)}")

# Query 5: DA DB DC DD 10 00 (LED from constants: USB_PACKED_LED=0x10)
print("\n[Q5] LED: DA DB DC DD 10 00")
for r in send_recv(dev, [0xDA, 0xDB, 0xDC, 0xDD, 0x10, 0x00]):
    print(f"  RX: {hex_str(r)}")

# Query 6: DA DB DC DD 05 00 (MOTOR from constants: USB_PACKED_MOTOR=0x05)
print("\n[Q6] MOTOR: DA DB DC DD 05 00")
for r in send_recv(dev, [0xDA, 0xDB, 0xDC, 0xDD, 0x05, 0x00]):
    print(f"  RX: {hex_str(r)}")

# Query 7: DA DB DC DD 06 00 (FAN from constants: USB_PACKED_FAN=0x06)
print("\n[Q7] FAN: DA DB DC DD 06 00")
for r in send_recv(dev, [0xDA, 0xDB, 0xDC, 0xDD, 0x06, 0x00]):
    print(f"  RX: {hex_str(r)}")

# Query 8: Init packet from DeviceOnConnected1
print("\n[Q8] Init: DA DB DC DD 00 00 00 00 00 00 00 00 01 00 00 00 00 00 00 00")
for r in send_recv(dev, [0xDA, 0xDB, 0xDC, 0xDD, 0x00, 0x00, 0x00, 0x00,
                         0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,
                         0x00, 0x00, 0x00, 0x00]):
    print(f"  RX: {hex_str(r)}")

# Query 9: AddhidDeviceList discovery packet 
print("\n[Q9] Discovery: DC DD 01 00 00 00 00 00 00 00 00 01 00 00")
for r in send_recv(dev, [0xDC, 0xDD, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,
                         0x00, 0x00, 0x00, 0x01, 0x00, 0x00]):
    print(f"  RX: {hex_str(r)}")

# Query 10: Just read without sending (non-blocking)
print("\n[Q10] Passive listen 2 seconds...")
time.sleep(2)
while True:
    r = dev.read(64, timeout_ms=100)
    if not r:
        break
    print(f"  RX: {hex_str(bytes(r))}")
print("  (no spontaneous data)")

# Query 11: Try KVMALED6 pattern - cmd=16, ch, mode, data
# Header: DA DB DC DD + cmd=0x10(LED) + 0x00(ch0) + 0x01(mode=RGB) + RGB data  
print("\n[Q11] KVMALED6-style: DA DB DC DD 10 00 01")
for r in send_recv(dev, [0xDA, 0xDB, 0xDC, 0xDD, 0x10, 0x00, 0x01]):
    print(f"  RX: {hex_str(r)}")

dev.close()
print("\nDone.")

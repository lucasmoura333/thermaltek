"""
Comprehensive LED protocol tester.
Tests 16-LED format (based on 0x10 = 16 in device response)
"""
import time
import hid

VID = 0x0416
PID = 0x8001

def send_recv(dev, data_64, wait_ms=200):
    pkt = bytes([0x00]) + bytes(data_64)  # prepend Report ID
    dev.write(pkt)
    time.sleep(wait_ms / 1000.0)
    responses = []
    while True:
        r = dev.read(64, timeout_ms=50)
        if not r:
            break
        responses.append(bytes(r))
    return responses

def make_led_packet(rgb_list):
    """
    Build the TRCC LED data packet.
    rgb_list: list of (r, g, b) tuples
    Header format: DA DB DC DD 00 00 00 00 00 00 00 00 02 00 00 00 [len] 00 00 00
    Followed by: R G B for each LED
    """
    n = len(rgb_list)
    rgb_bytes = bytes([c for r,g,b in rgb_list for c in (r,g,b)])
    data_len = len(rgb_bytes)
    
    header = bytes([
        0xDA, 0xDB, 0xDC, 0xDD,  # magic
        0x00, 0x00, 0x00, 0x00,  # bytes 4-7
        0x00, 0x00, 0x00, 0x00,  # bytes 8-11
        0x02, 0x00, 0x00, 0x00,  # bytes 12-15 (0x02 = ?)
        data_len & 0xFF, (data_len >> 8) & 0xFF, 0x00, 0x00,  # bytes 16-19: data len
    ])
    return header + rgb_bytes

def send_led_data(dev, rgb_list, verbose=True):
    """Send LED data in 64-byte chunks."""
    full_data = make_led_packet(rgb_list)
    chunks = [full_data[i:i+64] for i in range(0, len(full_data), 64)]
    if verbose:
        print(f"  Sending {len(rgb_list)} LEDs = {len(full_data)} bytes in {len(chunks)} chunks")
    for i, chunk in enumerate(chunks):
        padded = chunk + bytes(64 - len(chunk))
        if verbose and i == 0:
            print(f"  Chunk 1 first 20: {' '.join(f'{b:02X}' for b in padded[:20])}")
        send_recv(dev, padded, 30)

dev = hid.device()
dev.open(VID, PID)
print(f"Device: {dev.get_manufacturer_string()} / {dev.get_product_string()}")
dev.set_nonblocking(1)

# Query device
print("\n[QUERY] Sending GET_STATE...")
r = send_recv(dev, bytes([0xDA, 0xDB, 0xDC, 0xDD, 0x02, 0x00]) + bytes(58), 500)
if r:
    resp = r[0]
    print(f"  Response: {' '.join(f'{b:02X}' for b in resp)}")
    # Try to decode the 4 bytes after the magic header  
    if len(resp) >= 13 and resp[1:5] == bytes([0xDA, 0xDB, 0xDC, 0xDD]):
        val1, val2, val3, val4 = resp[5], resp[6], resp[7], resp[8]
        word = resp[9:13]
        word2 = resp[13:17]
        print(f"  Bytes 5-8: {val1:3d} {val2:3d} {val3:3d} {val4:3d} (0x{val1:02X}...)")
        print(f"  Bytes 9-12: {word.hex()}")
        print(f"  Bytes 13-16: {word2.hex()}")
        print(f"  -> Possible LED count per zone: {val1} {val2} {val3} {val4}")

# Test 1: 16 LEDs - ALL RED (R,G,B)
print("\n[TEST A] 16 LEDs x ALL RED [R=FF G=00 B=00]")
send_led_data(dev, [(255, 0, 0)] * 16)
time.sleep(2)
input("Press ENTER to continue to GREEN... (check if LEDs are RED)")

# Test 2: 16 LEDs - ALL GREEN
print("\n[TEST B] 16 LEDs x ALL GREEN [R=00 G=FF B=00]")
send_led_data(dev, [(0, 255, 0)] * 16)
time.sleep(2)
input("Press ENTER to continue to BLUE...")

# Test 3: 16 LEDs - ALL BLUE
print("\n[TEST C] 16 LEDs x ALL BLUE [R=00 G=00 B=FF]")
send_led_data(dev, [(0, 0, 255)] * 16)
time.sleep(2)
input("Press ENTER to test different LED counts...")

# Test 4: Maybe 12 LEDs?
print("\n[TEST D] 12 LEDs x ALL RED (maybe fan ring?)")
send_led_data(dev, [(255, 0, 0)] * 12)
time.sleep(2)
input("Press ENTER to try 84 LEDs...")

# Test 5: 84 LEDs - ALL GREEN
print("\n[TEST E] 84 LEDs x ALL GREEN (TRCC's actual count)")
send_led_data(dev, [(0, 255, 0)] * 84)
time.sleep(2)
input("Press ENTER to try RAINBOW pattern...")

# Test 6: Rainbow across 16 LEDs
print("\n[TEST F] 16 LEDs RAINBOW")
import math
rainbow = []
for i in range(16):
    hue = i / 16.0 * 360.0
    # Simple HSV to RGB
    h = hue / 60.0
    x = int(255 * (1 - abs(h % 2 - 1)))
    if h < 1:      r, g, b = 255, x, 0
    elif h < 2:    r, g, b = x, 255, 0
    elif h < 3:    r, g, b = 0, 255, x
    elif h < 4:    r, g, b = 0, x, 255
    elif h < 5:    r, g, b = x, 0, 255
    else:          r, g, b = 255, 0, x
    rainbow.append((r, g, b))
send_led_data(dev, rainbow)
time.sleep(2)

print("\n[QUERY] Final state query...")
r = send_recv(dev, bytes([0xDA, 0xDB, 0xDC, 0xDD, 0x02, 0x00]) + bytes(58), 500)
if r:
    print(f"  Response: {' '.join(f'{b:02X}' for b in r[0])}")

dev.close()
print("\nDone! All tests complete.")

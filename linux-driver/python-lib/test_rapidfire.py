"""
Rapidfire LED test - sends the same color packet repeatedly, like TRCC's timer does.
Also tests different brightness values and LED counts.
Uses hidapi for simplicity since WriteFile also didn't work.
"""
import hid
import time
import sys

VID = 0x0416
PID = 0x8001
MAGIC = bytes([0xDA, 0xDB, 0xDC, 0xDD])

def make_packet(n_leds, r, g, b):
    """Build header + RGB data packet"""
    rgb_data = bytes([r, g, b] * n_leds)
    header = bytes([
        0xDA, 0xDB, 0xDC, 0xDD,
        0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00,
        0x02, 0x00, 0x00, 0x00,
        len(rgb_data) & 0xFF, (len(rgb_data) >> 8) & 0xFF, 0x00, 0x00,
    ])
    return header + rgb_data

def send_packet(dev, full_data):
    """Send chunked data, like ThreadSendDeviceData1"""
    offset = 0
    remaining = len(full_data)
    while remaining > 0:
        chunk_size = min(64, remaining)
        chunk = full_data[offset:offset+chunk_size]
        padded = chunk + bytes(64 - len(chunk))
        dev.write(bytes([0x00]) + padded)
        offset += chunk_size
        remaining -= chunk_size

def send_init(dev):
    """Send DeviceOnConnected1 init packet"""
    init = bytes([
        0xDA, 0xDB, 0xDC, 0xDD,
        0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00,
        0x01, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00,
    ]) + bytes(44)
    dev.write(bytes([0x00]) + init)

print("Opening device...")
dev = hid.device()
dev.open(VID, PID)
dev.set_nonblocking(1)
print(f"Device: {dev.get_product_string()}")

# Query first to confirm communication
dev.write(bytes([0x00]) + bytes([0xDA, 0xDB, 0xDC, 0xDD, 0x02, 0x00]) + bytes(58))
time.sleep(0.3)
resp = dev.read(64)
if resp:
    print(f"Query response: {' '.join(f'{b:02X}' for b in resp[:16])}")
else:
    print("No query response!")

tests = [
    # (label, n_leds, r, g, b, repeats, delay_ms)
    ("TEST 1: 84 LEDs, full RED (no brightness)", 84, 255, 0, 0, 30, 50),
    ("TEST 2: 84 LEDs, RED with 0.4 brightness", 84, 102, 0, 0, 30, 50),
    ("TEST 3: 84 LEDs, full GREEN (no brightness)", 84, 0, 255, 0, 30, 50),
    ("TEST 4: 84 LEDs, full BLUE (no brightness)", 84, 0, 0, 255, 30, 50),
    ("TEST 5: 84 LEDs, full WHITE", 84, 255, 255, 255, 30, 50),
    ("TEST 6: 84 LEDs, R=1,G=1,B=1 (test mode values)", 84, 1, 1, 1, 30, 50),
    ("TEST 7: 12 LEDs, full RED", 12, 255, 0, 0, 30, 50),
    ("TEST 8: 64 LEDs, full RED", 64, 255, 0, 0, 30, 50),
    ("TEST 9: 84 LEDs, RED with init first", 84, 255, 0, 0, 30, 50),
]

for i, (label, n_leds, r, g, b, repeats, delay_ms) in enumerate(tests):
    print(f"\n{'='*50}")
    print(f"{label}")
    print(f"  n_leds={n_leds}, RGB=({r},{g},{b}), repeats={repeats}")
    
    packet = make_packet(n_leds, r, g, b)
    
    if "init first" in label:
        print("  Sending init packet first...")
        send_init(dev)
        time.sleep(0.5)
    
    for rep in range(repeats):
        send_packet(dev, packet)
        if rep == 0:
            print(f"  Chunk 1 header: {' '.join(f'{c:02X}' for c in packet[:20])}")
        time.sleep(delay_ms / 1000.0)
    
    print(f"  Sent {repeats} times. Check LEDs for 3 seconds...")
    
    # Also check if device sends back any data
    time.sleep(0.5)
    resp = dev.read(64)
    if resp:
        print(f"  Response: {' '.join(f'{b:02X}' for b in resp[:16])}")
    
    time.sleep(2.5)

# Final test: send just raw data without header (what if the header IS the problem?)
print(f"\n{'='*50}")
print("TEST 10: Raw RGB data WITHOUT header (just 252 bytes of RED)")
raw_rgb = bytes([255, 0, 0] * 84)
for rep in range(30):
    offset = 0
    remaining = len(raw_rgb)
    while remaining > 0:
        chunk_size = min(64, remaining)
        chunk = raw_rgb[offset:offset+chunk_size]
        padded = chunk + bytes(64 - len(chunk))
        dev.write(bytes([0x00]) + padded)
        offset += chunk_size
        remaining -= chunk_size
    time.sleep(0.05)
print("Sent 30 times. Check LEDs for 3 seconds...")
time.sleep(3)

# Another test: what about just a single 64-byte block with header + some color data?
print(f"\n{'='*50}")
print("TEST 11: Single 64-byte packet: header(20) + RED data (44 bytes = 14 LEDs)")
single_pkt = bytes([
    0xDA, 0xDB, 0xDC, 0xDD,
    0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00,
    0x02, 0x00, 0x00, 0x00,
    0x2C, 0x00, 0x00, 0x00,  # data_len = 44 = 0x2C
]) + bytes([255, 0, 0] * 14) + bytes(2)  # pad to 64

for rep in range(30):
    dev.write(bytes([0x00]) + single_pkt)
    time.sleep(0.05)
print("Sent 30 times. Check LEDs...")
time.sleep(3)

dev.close()
print("\nALL TESTS COMPLETE. Did ANYTHING change?")

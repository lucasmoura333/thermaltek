"""
LED ON/OFF validation test.
Run with TRCC CLOSED to confirm we have full control.
"""
import hid
import time
import sys

VID = 0x0416
PID = 0x8001

def make_packet(n_leds, r, g, b):
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
    offset = 0
    remaining = len(full_data)
    while remaining > 0:
        chunk_size = min(64, remaining)
        chunk = full_data[offset:offset+chunk_size]
        padded = chunk + bytes(64 - len(chunk))
        dev.write(bytes([0x00]) + padded)
        offset += chunk_size
        remaining -= chunk_size

def send_color(dev, r, g, b, repeats=5, delay=0.05):
    """Send color repeatedly like TRCC's timer"""
    packet = make_packet(84, r, g, b)
    for _ in range(repeats):
        send_packet(dev, packet)
        time.sleep(delay)

print("=" * 50)
print("LED ON/OFF VALIDATION TEST")
print("Make sure TRCC is CLOSED!")
print("=" * 50)

dev = hid.device()
dev.open(VID, PID)
dev.set_nonblocking(1)
print(f"Device: {dev.get_product_string()}\n")

steps = [
    ("RED ON",     255, 0,   0),
    ("OFF",        0,   0,   0),
    ("GREEN ON",   0,   255, 0),
    ("OFF",        0,   0,   0),
    ("BLUE ON",    0,   0,   255),
    ("OFF",        0,   0,   0),
    ("WHITE ON",   255, 255, 255),
    ("OFF",        0,   0,   0),
    ("MAGENTA ON", 255, 0,   255),
    ("OFF",        0,   0,   0),
]

for label, r, g, b in steps:
    send_color(dev, r, g, b, repeats=10)
    print(f"  >>> {label} (R={r}, G={g}, B={b})")
    input("  Press ENTER to continue...")

print("\nRapid blink test (RED on/off 5x)...")
for i in range(5):
    send_color(dev, 255, 0, 0, repeats=3)
    time.sleep(0.5)
    send_color(dev, 0, 0, 0, repeats=3)
    time.sleep(0.5)
    print(f"  Blink {i+1}/5")

print("\nDone! Leaving LEDs OFF.")
send_color(dev, 0, 0, 0, repeats=5)
dev.close()
print("SUCCESS - LED control confirmed!")

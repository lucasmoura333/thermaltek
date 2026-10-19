#!/usr/bin/env python3
"""
Sniff what TRCC sends on the HID endpoint by reading the IN endpoint
(device responses) AND by temporarily taking the device while TRCC runs.

Better approach: read the HID device alongside TRCC using a second open.
TRCC holds the write endpoint; we try to read anything on the IN endpoint.
"""
import sys, time, hid

VID, PID = 0x0416, 0x8001

print("Opening device for listen (TRCC must be running + display active)")
dev = hid.device()
try:
    dev.open(VID, PID)
except OSError as e:
    print(f"Cannot open: {e}")
    print("Try closing TRCC and re-opening. On Windows, HID allows multiple readers.")
    sys.exit(1)

dev.set_nonblocking(True)
print("Listening for 30 seconds... change TRCC display modes to trigger LCD packets")
print()

seen = set()
deadline = time.time() + 30
while time.time() < deadline:
    data = dev.read(65, timeout_ms=100)
    if data and len(data) >= 4:
        key = bytes(data[:16])
        if key not in seen:
            seen.add(key)
            print(f"[IN] {bytes(data).hex()}")
    time.sleep(0.001)

dev.close()
print("Done")

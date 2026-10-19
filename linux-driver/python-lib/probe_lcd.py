#!/usr/bin/env python3
"""
Probe the LCD display protocol by sending type 0x30 packets
with different data encodings and watching what appears.

Run with TRCC CLOSED.
"""
import sys, time, struct
sys.path.insert(0, r'F:\helpmeplease\linux-driver\python-lib')
from nuvoton_hid import NuvotonDevice

MAGIC = [0xDA, 0xDB, 0xDC, 0xDD]

def make_packet(pkt_type: int, data: bytes) -> bytes:
    """Build a header + data byte string for a given packet type."""
    n = len(data)
    header = bytes(MAGIC) + bytes(8) + struct.pack('<I', pkt_type) + struct.pack('<H', n) + bytes(2)
    return header + data

def send_raw(dev: NuvotonDevice, pkt_type: int, data: bytes, label: str):
    payload = make_packet(pkt_type, data)
    # Chunk into 64-byte HID reports
    offset = 0
    while offset < len(payload):
        chunk = payload[offset:offset+64]
        chunk = chunk + bytes(64 - len(chunk))  # zero-pad
        dev.device.write([0x00] + list(chunk))
        offset += 64
    print(f"  Sent type=0x{pkt_type:02x} len={len(data)} | {label}")

def probe_lcd(cpu_temp=48, cpu_pct=44, gpu_temp=50, gpu_pct=13):
    with NuvotonDevice() as dev:
        if not dev.device:
            print("Device not found. Close TRCC first!")
            return

        dev.send_init()
        print("Connected. Testing LCD packet formats...\n")
        print("Watch the pump head display!\n")

        formats = [
            # Format 1: 4 raw bytes (each value as uint8)
            (struct.pack('4B', cpu_temp, cpu_pct, gpu_temp, gpu_pct),
             f"4×uint8: cpu={cpu_temp} {cpu_pct}% gpu={gpu_temp} {gpu_pct}%"),

            # Format 2: 4 uint16-LE values
            (struct.pack('<4H', cpu_temp, cpu_pct, gpu_temp, gpu_pct),
             f"4×uint16-LE"),

            # Format 3: 4 uint32-LE values  
            (struct.pack('<4I', cpu_temp, cpu_pct, gpu_temp, gpu_pct),
             f"4×uint32-LE"),

            # Format 4: 8 bytes = 4 pairs of (value_lo, value_hi)
            (bytes([cpu_temp, 0, cpu_pct, 0, gpu_temp, 0, gpu_pct, 0]),
             f"4×(val,0) pairs"),

            # Format 5: CPU and GPU in separate 16-bit fields, pct as byte
            (struct.pack('<H B H B', cpu_temp, cpu_pct, gpu_temp, gpu_pct),
             f"uint16,uint8 pairs"),

            # Format 6: single 64-byte block with values at known offsets
            # put the same data at various offsets
            (bytes([0]*4 + [cpu_temp, 0, cpu_pct, 0, gpu_temp, 0, gpu_pct, 0] + [0]*48),
             f"64-byte block, values at offset 4"),

            # Format 7: try float32
            (struct.pack('<4f', float(cpu_temp), float(cpu_pct), float(gpu_temp), float(gpu_pct)),
             f"4×float32"),
        ]

        for i, (data, label) in enumerate(formats):
            input(f"\n[{i+1}/{len(formats)}] Press ENTER to try: {label}")
            send_raw(dev, 0x30, data, label)
            time.sleep(0.5)

        print("\nDone! Did anything appear on the display?")
        print("If yes, note which format number worked.")

if __name__ == '__main__':
    cpu_temp = int(sys.argv[1]) if len(sys.argv) > 1 else 48
    cpu_pct  = int(sys.argv[2]) if len(sys.argv) > 2 else 44
    gpu_temp = int(sys.argv[3]) if len(sys.argv) > 3 else 50
    gpu_pct  = int(sys.argv[4]) if len(sys.argv) > 4 else 13
    probe_lcd(cpu_temp, cpu_pct, gpu_temp, gpu_pct)

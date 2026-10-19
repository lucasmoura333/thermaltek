"""
Analyze a USBPcap .pcap file to extract Nuvoton LCD framebuffer packets.

Looks for:
  - OUT transfers to EP 0x02 on device 0x0416:0x8001
  - Payloads != the LED format (magic DA DB DC DD)
  - Chunks those payloads and shows first/last bytes + size

Usage:
    python _analyze_lcd_pcap.py usblcd_capture.pcap

Requires: pip install scapy   OR   pip install dpkt
"""

import sys
import struct
import os

def analyze_pcap_dpkt(filename: str):
    """Parse with dpkt (simpler, usually available)."""
    import dpkt

    VID, PID = 0x0416, 0x8001
    LED_MAGIC = bytes([0xDA, 0xDB, 0xDC, 0xDD])
    target_addr = None
    lcd_packets = []

    with open(filename, "rb") as f:
        pcap = dpkt.pcap.Reader(f)
        for ts, buf in pcap:
            if len(buf) < 40:
                continue
            # USBPcap pseudoheader: https://desowin.org/usbpcap/captureformat.html
            # Offset 0: headerLen (2), 2: irpId (8), 10: status(4), 14: function(2)
            # 16: info(1), 17: bus(2), 19: device(2), 21: endpoint(1), 22: transfer(1)
            # 23: dataLength(4), ... data starts after headerLen bytes
            try:
                header_len = struct.unpack_from('<H', buf, 0)[0]
                if header_len < 27 or header_len > len(buf):
                    continue
                endpoint   = buf[21]
                transfer   = buf[22]  # 1=isochronous, 2=interrupt, 3=bulk, 0=control
                direction  = (endpoint & 0x80) != 0   # True = IN
                ep_num     = endpoint & 0x7F
                data_len   = struct.unpack_from('<I', buf, 23)[0]
                data       = buf[header_len:header_len + data_len]

                if direction or ep_num != 2:
                    continue   # only OUT on EP 0x02
                if len(data) < 4:
                    continue
                if data[:4] == LED_MAGIC:
                    continue   # skip LED packets we already know

                lcd_packets.append((ts, data))

            except Exception:
                continue

    print(f"Found {len(lcd_packets)} non-LED OUT packets on EP 0x02")
    sizes = {}
    for ts, data in lcd_packets:
        sizes[len(data)] = sizes.get(len(data), 0) + 1

    print("Payload size distribution:")
    for sz, cnt in sorted(sizes.items()):
        preview = data[:16].hex(' ')
        print(f"  {sz:5d} bytes × {cnt:4d}    first bytes: {data[:8].hex(' ')}")

    if lcd_packets:
        print("\n--- First LCD packet (full hex) ---")
        ts, data = lcd_packets[0]
        for i in range(0, min(len(data), 256), 16):
            row = data[i:i+16]
            print(f"  {i:04x}: {row.hex(' ')}")

        if len(lcd_packets) > 1:
            print("\n--- Second LCD packet ---")
            ts, data = lcd_packets[1]
            for i in range(0, min(len(data), 256), 16):
                row = data[i:i+16]
                print(f"  {i:04x}: {row.hex(' ')}")

try:
    import dpkt
    HAS_DPKT = True
except ImportError:
    HAS_DPKT = False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python _analyze_lcd_pcap.py <file.pcap>")
        sys.exit(1)

    pcap_file = sys.argv[1]
    if not os.path.exists(pcap_file):
        print(f"File not found: {pcap_file}")
        sys.exit(1)

    if not HAS_DPKT:
        print("Installing dpkt...")
        os.system(f"{sys.executable} -m pip install dpkt -q")
        import dpkt
    
    analyze_pcap_dpkt(pcap_file)

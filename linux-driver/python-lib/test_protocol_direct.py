"""
Direct HID protocol tester for Nuvoton TRCC device.
Sends known packet templates and captures responses.
Python 3, requires hid (hidapi) or pywinusb

Usage: python test_protocol.py
"""
import time
import sys

VID = 0x0416
PID = 0x8001

MAGIC = bytes([0xDA, 0xDB, 0xDC, 0xDD])

def pad64(data):
    """Pad data to exactly 64 bytes."""
    if len(data) > 64:
        raise ValueError(f"Data too long ({len(data)} bytes)")
    return bytes(data) + bytes(64 - len(data))

def hexdump(data, prefix=''):
    for i in range(0, len(data), 16):
        chunk = data[i:i+16]
        hex_part = ' '.join(f'{b:02X}' for b in chunk)
        print(f'{prefix}{i:04X}: {hex_part}')

def try_pywinusb():
    import pywinusb.hid as hid

    # Find our device
    all_devs = hid.HidDeviceFilter(vendor_id=VID, product_id=PID).get_devices()
    if not all_devs:
        print("ERROR: Device not found (pywinusb)")
        return None
    dev = all_devs[0]
    print(f"Device found: {dev.vendor_name} / {dev.product_name}")
    dev.open()

    received = []

    def on_data(data):
        received.append(bytes(data))
        print(f"  [RX] {' '.join(f'{b:02X}' for b in data)}")

    dev.set_raw_data_handler(on_data)
    return dev, received

def send_and_receive(dev, received, packet_64bytes, wait_ms=200):
    """Send a 64-byte packet and wait for response."""
    received.clear()
    # pywinusb: send_output_report([Report ID=0, ...data...])
    report = [0x00] + list(packet_64bytes)
    try:
        dev.send_output_report(report)
        time.sleep(wait_ms / 1000.0)
    except Exception as e:
        print(f"  [TX ERROR] {e}")
        return []
    return list(received)

def main():
    print("=" * 60)
    print("Nuvoton TRCC HID Protocol Tester")
    print("=" * 60)

    try:
        dev, received = try_pywinusb()
    except ImportError:
        print("pywinusb not available, trying hidapi...")
        try:
            import hid
            dev_hid = hid.device()
            dev_hid.open(VID, PID)
            print(f"Device: {dev_hid.get_manufacturer_string()} / {dev_hid.get_product_string()}")
            dev_hid.set_nonblocking(1)

            def send_raw(packet, wait_ms=200):
                report = bytes([0x00]) + packet
                dev_hid.write(report)
                time.sleep(wait_ms / 1000.0)
                responses = []
                while True:
                    r = dev_hid.read(64, timeout_ms=50)
                    if not r:
                        break
                    responses.append(bytes(r))
                    print(f"  [RX] {' '.join(f'{b:02X}' for b in r)}")
                return responses

            # Test 1: 6-byte GET_STATE query (DA DB DC DD 02 00)
            print("\n[TEST 1] Sending GET_STATE query: DA DB DC DD 02 00 ...")
            pkt1 = pad64(bytes([0xDA, 0xDB, 0xDC, 0xDD, 0x02, 0x00]))
            hexdump(pkt1, '  [TX] ')
            r1 = send_raw(pkt1, 500)
            if not r1:
                print("  No response received")

            # Test 2: 6-byte variant (DA DB DC DD 00 00)
            print("\n[TEST 2] Sending variant: DA DB DC DD 00 00 ...")
            pkt2 = pad64(bytes([0xDA, 0xDB, 0xDC, 0xDD, 0x00, 0x00]))
            r2 = send_raw(pkt2, 500)
            if not r2:
                print("  No response received")

            # Test 3: Static RED - using TRCC's known header format
            # Header: DA DB DC DD 00 00 00 00 00 00 00 00 02 00 00 00 FC 00 00 00
            # Data: 84 LEDs * (R=255, G=0, B=0) = 252 bytes of [FF 00 00] repeated
            print("\n[TEST 3] Sending LED packet - ALL RED (84 LEDs) ...")
            hdr = bytes([0xDA, 0xDB, 0xDC, 0xDD,
                         0x00, 0x00, 0x00, 0x00,
                         0x00, 0x00, 0x00, 0x00,
                         0x02, 0x00, 0x00, 0x00,
                         0xFC, 0x00, 0x00, 0x00])  # 20 bytes header, FC=252=len
            rgb_data = bytes([0xFF, 0x00, 0x00] * 84)  # 252 bytes: all RED
            full_data = hdr + rgb_data  # 272 bytes total

            print(f"  Total data: {len(full_data)} bytes, sending in 64-byte chunks")
            for i in range(0, len(full_data), 64):
                chunk = full_data[i:i+64]
                chunk_padded = chunk + bytes(64 - len(chunk))
                print(f"  [TX chunk {i//64 + 1}] first 20: {' '.join(f'{b:02X}' for b in chunk_padded[:20])}")
                send_raw(chunk_padded, 30)
            time.sleep(0.5)

            # Test 4: Query state again to confirm
            print("\n[TEST 4] Query state after LED send ...")
            send_raw(pkt1, 500)

            dev_hid.close()
            return

        except ImportError:
            print("Neither pywinusb nor hid module available!")
            sys.exit(1)

    # pywinusb path
    if dev is None:
        sys.exit(1)

    # Test 1: GET_STATE query
    print("\n[TEST 1] Sending GET_STATE query: DA DB DC DD 02 00 ...")
    pkt1 = pad64(bytes([0xDA, 0xDB, 0xDC, 0xDD, 0x02, 0x00]))
    hexdump(pkt1[:16], '  [TX] ')
    r1 = send_and_receive(dev, received, pkt1, 500)
    if not r1:
        print("  No response")

    # Test 2: Variant query
    print("\n[TEST 2] Sending variant: DA DB DC DD 00 00 ...")
    pkt2 = pad64(bytes([0xDA, 0xDB, 0xDC, 0xDD, 0x00, 0x00]))
    r2 = send_and_receive(dev, received, pkt2, 500)
    if not r2:
        print("  No response")

    # Test 3: Send LED RED packet
    print("\n[TEST 3] Sending ALL RED LED packet (TRCC format) ...")
    hdr = bytes([0xDA, 0xDB, 0xDC, 0xDD,
                 0x00, 0x00, 0x00, 0x00,
                 0x00, 0x00, 0x00, 0x00,
                 0x02, 0x00, 0x00, 0x00,
                 0xFC, 0x00, 0x00, 0x00])  # confirmed from TRCC.exe binary
    rgb_data = bytes([0xFF, 0x00, 0x00] * 84)  # 252 bytes: all RED
    full_data = hdr + rgb_data  # 272 bytes total

    for i in range(0, len(full_data), 64):
        chunk = full_data[i:i+64]
        chunk_padded = chunk + bytes(64 - len(chunk))
        print(f"  [TX chunk {i//64 + 1}] {' '.join(f'{b:02X}' for b in chunk_padded[:20])}...")
        send_and_receive(dev, received, chunk_padded, 30)

    time.sleep(1.0)

    dev.close()
    print("\nDone!")

if __name__ == '__main__':
    main()

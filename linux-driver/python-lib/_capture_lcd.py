"""
USB traffic capture helper for Nuvoton LCD protocol reverse engineering.

Starts USBPcapCMD to capture traffic from the Nuvoton cooler while TRCC
+ USBLCDNEW.exe are running, then saves to a .pcap file for analysis.

Usage:
    1. Open TRCC (normal operation, LCD showing numbers)
    2. Run this script AS ADMINISTRATOR
    3. Wait 10-20 seconds to capture several LCD update cycles
    4. Press Ctrl-C to stop
    5. Analyze the .pcap file

Requirements:
    - USBPcap installed (C:\\Program Files\\USBPcap\\USBPcapCMD.exe)
    - Run as Administrator

Output: usblcd_capture.pcap (open in Wireshark)
"""

import subprocess
import os
import sys
import ctypes

USBPCAP_CMD = r"C:\Program Files\USBPcap\USBPcapCMD.exe"
OUTPUT_FILE  = "usblcd_capture.pcap"

# USBPcap devices to try (covers most systems with 1-4 root hubs)
DEVICES_TO_TRY = [r"\\.\USBPcap1", r"\\.\USBPcap2", r"\\.\USBPcap3", r"\\.\USBPcap4"]


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def main():
    if not is_admin():
        print("ERROR: Must run as Administrator for USB capture.")
        print("  Right-click PowerShell → 'Run as Administrator', then re-run.")
        sys.exit(1)

    if not os.path.exists(USBPCAP_CMD):
        print(f"ERROR: USBPcapCMD not found at {USBPCAP_CMD}")
        print("  Install USBPcap from https://desowin.org/usbpcap/")
        sys.exit(1)

    print("Nuvoton LCD USB Traffic Capture")
    print("="*50)
    print("Make sure TRCC is OPEN and showing CPU/GPU data on the LCD screen.")
    print(f"Output: {os.path.abspath(OUTPUT_FILE)}")
    print()
    print("Trying USBPcap devices to find the Nuvoton cooler bus...")
    print("Press Ctrl-C to stop capture.\n")

    # Try each USBPcap device (each = one USB host controller / root hub)
    for device in DEVICES_TO_TRY:
        print(f"  Starting capture on {device}  →  will capture ALL USB on that bus")
        print(f"  (captures only 10 seconds to test, then auto-stops)\n")
        try:
            cmd = [
                USBPCAP_CMD,
                "-d", device,
                "-o", OUTPUT_FILE,
                "-s", "65535",       # full snaplen
                "-A",                # capture from all devices on this root hub
            ]
            proc = subprocess.run(cmd, timeout=10)
            if os.path.exists(OUTPUT_FILE) and os.path.getsize(OUTPUT_FILE) > 100:
                print(f"\nCapture complete: {OUTPUT_FILE} ({os.path.getsize(OUTPUT_FILE)} bytes)")
                print("\nNext steps:")
                print("  1. Open in Wireshark")
                print("  2. Filter: usb.idVendor == 0x0416")
                print("  3. Look for OUT packets > 64 bytes (the LCD framebuffer)")
                break
        except subprocess.TimeoutExpired:
            # This is expected - capture ran for timeout duration
            if os.path.exists(OUTPUT_FILE):
                sz = os.path.getsize(OUTPUT_FILE)
                if sz > 100:
                    print(f"\nCapture stopped. File: {OUTPUT_FILE} ({sz} bytes)")
                    break
        except FileNotFoundError:
            continue   # USBPcap device not present, try next
        except KeyboardInterrupt:
            print("\nCapture stopped by user.")
            break

    if os.path.exists(OUTPUT_FILE):
        print(f"\nANALYZE: python _analyze_lcd_pcap.py {OUTPUT_FILE}")
    else:
        print("\nNo capture file created. Try running with a different USBPcap device number.")


if __name__ == "__main__":
    main()

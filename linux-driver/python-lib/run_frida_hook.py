#!/usr/bin/env python3
"""
Frida HID Hook Launcher
=======================
Attaches Frida to TRCC.exe and runs frida_hid_hook.js to capture
all packets sent to/from the Nuvoton RGB controller (0x0416:0x8001).

Requirements:
    pip install frida frida-tools

Usage:
    python run_frida_hook.py                 # auto-find TRCC.exe
    python run_frida_hook.py --pid 1234      # attach to specific PID
    python run_frida_hook.py --spawn         # spawn TRCC.exe fresh (needs --path)
    python run_frida_hook.py --output out.txt # also save to file
"""

import argparse
import os
import sys
import time
import subprocess
from pathlib import Path

OUTPUT_FILE = None  # Set by --output flag

try:
    import frida
except ImportError:
    print("[!] Frida not installed. Run:  pip install frida frida-tools")
    sys.exit(1)

HOOK_SCRIPT = Path(__file__).parent / "frida_hid_hook.js"

TRCC_COMMON_PATHS = [
    r"C:\Program Files\Thermaltake\TRCC\TRCC.exe",
    r"C:\Program Files (x86)\Thermaltake\TRCC\TRCC.exe",
    r"C:\Program Files\Thermalright\TRCC\TRCC.exe",
    r"C:\Program Files (x86)\Thermalright\TRCC\TRCC.exe",
    r"C:\TRCC\TRCC.exe",
]


def find_trcc_pid():
    """Find TRCC.exe PID via tasklist."""
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq TRCC.exe", "/FO", "CSV", "/NH"],
            text=True, stderr=subprocess.DEVNULL
        )
        for line in out.splitlines():
            parts = line.strip().strip('"').split('","')
            if len(parts) >= 2 and parts[0].lower() in ("trcc.exe", "trcc"):
                pid = int(parts[1])
                print(f"[+] Found TRCC.exe — PID {pid}")
                return pid
    except Exception as e:
        print(f"[!] tasklist failed: {e}")
    return None


def find_trcc_path():
    """Find TRCC.exe installation path."""
    for p in TRCC_COMMON_PATHS:
        if Path(p).exists():
            return p
    # Search Program Files
    for base in [r"C:\Program Files", r"C:\Program Files (x86)"]:
        for root, dirs, files in os.walk(base):
            for f in files:
                if f.lower() == "trcc.exe":
                    return os.path.join(root, f)
    return None


def on_message(message, data):
    """Handle messages from Frida script."""
    global OUTPUT_FILE
    if message["type"] == "send":
        payload = message.get("payload", "")
        print(payload)
        if OUTPUT_FILE:
            with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                f.write(payload + "\n")
    elif message["type"] == "error":
        desc = message.get("description", "")
        stack = message.get("stack", "")
        print(f"[FRIDA ERROR] {desc}")
        if stack:
            print(f"  Stack: {stack[:400]}")


def main():
    global OUTPUT_FILE

    parser = argparse.ArgumentParser(description="Frida HID hook launcher for TRCC")
    parser.add_argument("--pid", type=int, help="PID of TRCC.exe to attach to")
    parser.add_argument("--spawn", action="store_true", help="Spawn TRCC.exe fresh")
    parser.add_argument("--path", type=str, help="Path to TRCC.exe (for --spawn)")
    parser.add_argument("--output", type=str, default="hid_capture.txt",
                        help="Output file for captured packets (default: hid_capture.txt)")
    args = parser.parse_args()

    OUTPUT_FILE = args.output
    # Clear the output file
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(f"# Nuvoton HID Capture — {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("# Device: 0x0416:0x8001\n\n")

    # Load Frida script
    if not HOOK_SCRIPT.exists():
        print(f"[!] Hook script not found: {HOOK_SCRIPT}")
        sys.exit(1)
    script_source = HOOK_SCRIPT.read_text(encoding="utf-8")

    # Get device handle
    device = frida.get_local_device()
    session = None

    if args.spawn:
        trcc_path = args.path or find_trcc_path()
        if not trcc_path:
            print("[!] Could not find TRCC.exe — use --path to specify location")
            sys.exit(1)
        print(f"[+] Spawning TRCC.exe: {trcc_path}")
        pid = device.spawn([trcc_path])
        session = device.attach(pid)
        print(f"[+] Attached to spawned process (PID {pid})")
    else:
        pid = args.pid or find_trcc_pid()
        if not pid:
            print("[!] TRCC.exe not found. Start it first or use --spawn.")
            print("    Tip: run_frida_hook.py --spawn --path \"C:\\path\\to\\TRCC.exe\"")
            sys.exit(1)
        print(f"[+] Attaching to PID {pid}...")
        session = device.attach(pid)
        print(f"[+] Attached successfully")

    # Inject script
    script = session.create_script(script_source)
    script.on("message", on_message)
    script.load()
    print(f"[+] Hook script loaded — capturing to: {OUTPUT_FILE}")
    print("[*] Perform TRCC operations now (change colors, modes, brightness)")
    print("[*] Press Ctrl+C to stop\n")

    if args.spawn:
        device.resume(pid)
        print("[+] TRCC resumed — UI should appear now")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n[*] Stopped. Captured packets saved to: {OUTPUT_FILE}")
    finally:
        script.unload()
        session.detach()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
test_lcd_zones.py — Physical LED verification tool for PA120 DIGITAL

Lights up one LED position at a time so you can observe which physical
segment of the 7-segment display each position controls.

Usage:
    python test_lcd_zones.py                # scan all 84 positions, 1s each
    python test_lcd_zones.py --pos 0        # light only position 0
    python test_lcd_zones.py --range 0 5    # scan positions 0..4
    python test_lcd_zones.py --zones        # zone preview (set_zones_color)
    python test_lcd_zones.py --indicators   # light only the indicator LEDs

TRCC MUST BE CLOSED before running this script.

Physical layout (validated against a live TRCC capture, 51/51 frames):
  led[0,1]      CPU indicator LEDs
  led[2..22]    CPU temp     3 digits, left to right (7 LEDs per digit)
  led[23]       °C           led[24]  °F
  led[25..40]   CPU usage    2 digits (+ 2 leading blanks when value < 100)
  led[41]       % CPU        led[42]  % GPU
  led[43..58]   GPU usage    2 digits (mirrored order)
  led[59]       °C           led[60]  °F
  led[61..81]   GPU temp     3 digits, left to right (mirrored order)
  led[82,83]    GPU indicator LEDs
Segment order inside every digit block: F, A, B, G, E, D, C
"""

import sys
import time
import argparse
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nuvoton_hid import NuvotonDevice, N_LEDS_PA120

# Test colour (bright green for visibility)
TEST_COLOR = (0, 255, 0)
# Background colour for inactive positions
BG_COLOR   = (0, 0, 0)

SEGMENT_LABELS = ["F", "A", "B", "G", "E", "D", "C"]


def _pos_label(pos: int) -> str:
    if pos in (0, 1):
        return "CPU indicator LED"
    if pos in (82, 83):
        return "GPU indicator LED"
    if 2 <= pos <= 22:
        d, seg = divmod(pos - 2, 7)
        return f"CPU temp digit {d + 1} (left→right), segment {SEGMENT_LABELS[seg]}"
    if pos == 23:
        return "CPU °C LED"
    if pos == 24:
        return "CPU °F LED"
    if 25 <= pos <= 40:
        idx = pos - 25                       # display order: blanks first
        if idx < 2:
            return "CPU usage leading blank"
        d, seg = divmod(idx - 2, 7)
        return f"CPU usage digit {'AB'[d]}, segment {SEGMENT_LABELS[seg]}"
    if pos == 41:
        return "CPU % LED"
    if pos == 42:
        return "GPU % LED"
    if 43 <= pos <= 58:
        idx = 58 - pos                       # display order (mirrored)
        if idx < 2:
            return "GPU usage leading blank"
        d, seg = divmod(idx - 2, 7)
        return f"GPU usage digit {'AB'[d]}, segment {SEGMENT_LABELS[seg]}"
    if pos == 59:
        return "GPU °C LED"
    if pos == 60:
        return "GPU °F LED"
    if 61 <= pos <= 81:
        idx = 81 - pos                       # display order (mirrored)
        d, seg = divmod(idx, 7)
        return f"GPU temp digit {d + 1} (left→right), segment {SEGMENT_LABELS[seg]}"
    return "unknown position"


def scan_single(dev: NuvotonDevice, pos: int, hold: float = 1.0):
    """Light up one position, print label, wait, then turn off."""
    label = _pos_label(pos)
    print(f"  Position {pos:2d}: {label}")
    colors = [BG_COLOR] * N_LEDS_PA120
    colors[pos] = TEST_COLOR
    dev.set_per_led(colors, repeats=3)
    time.sleep(hold)


def scan_range(dev: NuvotonDevice, start: int, end: int, hold: float = 1.0):
    print(f"\nScanning positions {start}..{end-1} (green = active, {hold}s each)")
    print("-" * 60)
    for pos in range(start, end):
        scan_single(dev, pos, hold)
    dev.set_off(repeats=3)
    print("\nDone. LEDs off.")


def show_zones(dev: NuvotonDevice):
    """
    Preview every zone lit solid in its own colour (set_zones_color):
      CPU temp  digits + °C  → BLUE
      CPU usage digits + %   → RED
      GPU temp  digits + °C  → GREEN
      GPU usage digits + %   → YELLOW
      indicator LEDs         → MAGENTA
    """
    print("\nZone preview (each metric area lit solid in its colour):")
    print("  CPU temp  → BLUE    | CPU usage → RED")
    print("  GPU temp  → GREEN   | GPU usage → YELLOW")
    print("  indicators → MAGENTA")
    dev.set_zones_color(
        cpu_temp=(0, 0, 255),
        cpu_usage=(255, 0, 0),
        gpu_temp=(0, 255, 0),
        gpu_usage=(255, 255, 0),
        ring_color=(255, 0, 255),
        repeats=5,
    )
    print("\nPress Enter to turn off…")
    input()
    dev.set_off(repeats=3)


def show_indicators(dev: NuvotonDevice):
    """Light only the CPU/GPU indicator LEDs (0,1 and 82,83) in green."""
    print("\nShowing indicator LEDs (0,1 / 82,83) in green…")
    colors = [BG_COLOR] * N_LEDS_PA120
    for i in (0, 1, 82, 83):
        colors[i] = TEST_COLOR
    dev.set_per_led(colors, repeats=5)
    print("Press Enter to turn off…")
    input()
    dev.set_off(repeats=3)


def main():
    ap = argparse.ArgumentParser(description="Physical LED tester for PA120 DIGITAL")
    ap.add_argument("--pos",   type=int, help="Light only this physical position (0-83)")
    ap.add_argument("--range", type=int, nargs=2, metavar=("START", "END"),
                    help="Scan positions START..END-1")
    ap.add_argument("--zones", action="store_true",
                    help="Zone preview: every zone lit solid in its own colour")
    ap.add_argument("--indicators", action="store_true",
                    help="Show indicator LEDs only (0,1 / 82,83)")
    ap.add_argument("--hold",  type=float, default=1.0,
                    help="Seconds to hold each LED (default 1.0)")
    args = ap.parse_args()

    print("Nuvoton PA120 DIGITAL — LED/segment tester")
    print("NOTE: Close TRCC before running!")
    print()

    with NuvotonDevice() as dev:
        if not dev.device:
            print("ERROR: Device not found. Is TRCC closed?")
            sys.exit(1)
        dev.send_init()

        if args.pos is not None:
            if not 0 <= args.pos < N_LEDS_PA120:
                print(f"Position must be 0..{N_LEDS_PA120-1}")
                sys.exit(1)
            scan_single(dev, args.pos, args.hold)
            print(f"Kept on for {args.hold}s")
            dev.set_off(repeats=3)

        elif args.range:
            start, end = args.range
            scan_range(dev, start, min(end, N_LEDS_PA120), args.hold)

        elif args.zones:
            show_zones(dev)

        elif args.indicators:
            show_indicators(dev)

        else:
            # Default: scan ALL positions
            scan_range(dev, 0, N_LEDS_PA120, args.hold)


if __name__ == "__main__":
    main()

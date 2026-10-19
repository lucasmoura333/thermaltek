#!/usr/bin/env python3
"""
lcd_sender.py — Segment-display sender for Nuvoton 0416:8001 (Thermalright Digital series)

WHAT THE "LCD" ACTUALLY IS
--------------------------
The display on Digital-series coolers (Assassin 120 / PA120 Digital, 84-LED
variant, handshake PM=16) is NOT a pixel LCD.  It is a chain of 7-segment LED
digits driven ENTIRELY through the same HID/LED protocol as the rest of the
LEDs (magic DA DB DC DD, 20-byte header, 252-byte RGB24 body, sent as five
64-byte HID output reports).

Evidence:
  * Live USB capture of TRCC.exe: only DA DB DC DD frames on EP 0x02, no
    image/JPEG traffic, no other magic anywhere.
  * USBLCDNEW.dll (image LCD path) does NOT handle PID 0x8001.
  * shareMemory_ImageRGB (TRCC image SHM) is empty/all-zero while this
    display renders numbers.
  * The lit-LED pattern of captured frames decodes exactly into segment
    digits: CPU temp "41", GPU temp "47", GPU usage "0" ...

LED MAP (84 LEDs) — matches the community hardware-verified map for
PA120 DIGITAL ("digital_thermal_right_lcd"), validated digit-by-digit against
the capture:

  led[0,1]      CPU indicator LEDs
  led[2..22]    CPU temp    3 digits, left to right (7 LEDs each)
  led[23]       °C          led[24]  °F
  led[25..40]   CPU usage   2 digits (2 leading blanks when value < 100)
  led[41]       % CPU       led[42]  % GPU
  led[43..58]   GPU usage   2 digits (2 leading blanks, mirrored order)
  led[59]       °C          led[60]  °F
  led[61..81]   GPU temp    3 digits, left to right (mirrored order)
  led[82,83]    GPU indicator LEDs

Segment order inside every digit block (mask index 0..6):
  F, A, B, G, E, D, C
Verified on the wire:  "4"={F,B,G,C}  "1"={B,C}  "0"={F,A,B,E,D,C}  "7"={A,B,C}

USAGE (TRCC.exe must be CLOSED — its 160 ms timer overwrites our packets)
-------------------------------------------------------------------------
  python lcd_sender.py --query          handshake, print device PM/SUB response
  python lcd_sender.py --replay trcc_capture_frames.bin
                                        replay captured TRCC frames (proof of life)
  python lcd_sender.py --demo           fixed digits for visual verification
  python lcd_sender.py --probe          light one LED group at a time (mapping check)
  python lcd_sender.py --live           sensors -> digits, continuous (Ctrl-C stops)
  python lcd_sender.py --off            all LEDs off
"""

import argparse
import os
import sys
import time
from typing import List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nuvoton_hid import (
    NuvotonDevice,
    LED_CPU_IND     as G_CPU_IND,
    LED_CPU_TEMP    as G_CPU_TEMP,
    LED_CPU_CELSIUS as G_CPU_CELSIUS,
    LED_CPU_FAHR    as G_CPU_FAHR,
    LED_CPU_USAGE   as G_CPU_USAGE,
    LED_CPU_PERCENT as G_CPU_PERCENT,
    LED_GPU_PERCENT as G_GPU_PERCENT,
    LED_GPU_USAGE   as G_GPU_USAGE,
    LED_GPU_CELSIUS as G_GPU_CELSIUS,
    LED_GPU_FAHR    as G_GPU_FAHR,
    LED_GPU_TEMP    as G_GPU_TEMP,
    LED_GPU_IND     as G_GPU_IND,
)

# ── Device geometry ─────────────────────────────────────────────────────────

N_LEDS = 84                       # PA120/Assassin 120 Digital, PM=16
BODY_BYTES = N_LEDS * 3           # 252

# 7-segment masks, index order = F A B G E D C (hardware-verified order)
DIGIT_MASK = {
    0: [1, 1, 1, 0, 1, 1, 1],
    1: [0, 0, 1, 0, 0, 0, 1],
    2: [0, 1, 1, 1, 1, 1, 0],
    3: [0, 1, 1, 1, 0, 1, 1],
    4: [1, 0, 1, 1, 0, 0, 1],
    5: [1, 1, 0, 1, 0, 1, 1],
    6: [1, 1, 0, 1, 1, 1, 1],
    7: [0, 1, 1, 0, 0, 0, 1],
    8: [1, 1, 1, 1, 1, 1, 1],
    9: [1, 1, 1, 1, 0, 1, 1],
}
BLANK = [0] * 7

# LED groups (order inside each list = display order, left to right)
# Defined in nuvoton_hid.py (LED_* constants), imported above as G_*.

RGB = Tuple[int, int, int]

# ── Frame builder ───────────────────────────────────────────────────────────

class DisplayFrame:
    """Builds a 252-byte RGB body for the 84-LED display."""

    def __init__(self):
        self.body = bytearray(BODY_BYTES)

    def put(self, led: int, color: RGB):
        if 0 <= led < N_LEDS:
            off = led * 3
            self.body[off]     = max(0, min(255, int(color[0])))
            self.body[off + 1] = max(0, min(255, int(color[1])))
            self.body[off + 2] = max(0, min(255, int(color[2])))

    def light(self, leds: Sequence[int], color: RGB, mask: Optional[Sequence[int]] = None):
        if mask is None:
            for led in leds:
                self.put(led, color)
        else:
            for led, on in zip(leds, mask):
                if on:
                    self.put(led, color)

    def clear(self):
        self.body = bytearray(BODY_BYTES)

    def to_bytes(self) -> bytes:
        return bytes(self.body)


def _digits(value: int, count: int, fill: int = -1) -> List[int]:
    """Split *value* into *count* digits, left-padded with filler (blank if <0)."""
    if value is None or value < 0:
        return [fill] * count
    ds = [int(c) for c in str(int(value))]
    if len(ds) > count:
        ds = ds[-count:]
    ds = [fill] * (count - len(ds)) + ds
    return ds


def show_number(frame: DisplayFrame, group: Sequence[int], digits: int,
                value: int, color: RGB, overflow_lit: bool = False):
    """
    Render *value* on a digit group.  Group layout:
      [prefix LEDs...] [digit0 block][digit1 block]...
    Prefix length = len(group) - digits*7 (lit only on overflow if requested).
    """
    digit_leds = digits * 7
    prefix_len = len(group) - digit_leds
    if overflow_lit:
        for led in group[:prefix_len]:
            frame.put(led, color)
    ds = _digits(value, digits)
    for i, d in enumerate(ds):
        block = group[prefix_len + i * 7: prefix_len + (i + 1) * 7]
        mask = BLANK if d < 0 else DIGIT_MASK[d]
        frame.light(block, color, mask)


def build_metrics_frame(cpu_temp: float, cpu_usage: float,
                        gpu_temp: float, gpu_usage: float,
                        temp_color: Optional[RGB] = None,
                        usage_color: Optional[RGB] = None,
                        indicator_color: Optional[RGB] = None,
                        cpu_temp_color: Optional[RGB] = None,
                        cpu_usage_color: Optional[RGB] = None,
                        gpu_temp_color: Optional[RGB] = None,
                        gpu_usage_color: Optional[RGB] = None,
                        cpu_indicator_color: Optional[RGB] = None,
                        gpu_indicator_color: Optional[RGB] = None) -> bytes:
    """
    Compose the full metrics frame:
      CPU side: indicator + temp digits + °C + usage digits + %
      GPU side: % + usage digits + °C + temp digits + indicator

    *temp_color* / *usage_color* colour both sides; the per-side
    *_temp_color / *_usage_color overrides take precedence.  Indicator
    colours default to the matching side's temperature colour.
    """
    frame = DisplayFrame()
    tc = temp_color or (0, 170, 255)
    uc = usage_color or (0, 220, 80)
    ctc = cpu_temp_color or tc
    cuc = cpu_usage_color or uc
    gtc = gpu_temp_color or tc
    guc = gpu_usage_color or uc

    frame.light(G_CPU_IND, cpu_indicator_color or indicator_color or ctc)
    frame.light(G_GPU_IND, gpu_indicator_color or indicator_color or gtc)

    def _num(v):
        # Round to int; None and NaN both render as 0 (LHM/ADL can emit NaN).
        return int(round(v)) if v is not None and v == v else 0

    cpu_t = _num(cpu_temp)
    gpu_t = _num(gpu_temp)
    cpu_u = _num(cpu_usage)
    gpu_u = _num(gpu_usage)

    show_number(frame, G_CPU_TEMP, 3, cpu_t, ctc)
    show_number(frame, G_CPU_USAGE, 2, cpu_u, cuc, overflow_lit=cpu_u >= 100)
    show_number(frame, G_GPU_USAGE, 2, gpu_u, guc, overflow_lit=gpu_u >= 100)
    show_number(frame, G_GPU_TEMP, 3, gpu_t, gtc)

    frame.light(G_CPU_CELSIUS, ctc)
    frame.light(G_GPU_CELSIUS, gtc)
    frame.light(G_CPU_PERCENT, cuc)
    frame.light(G_GPU_PERCENT, guc)

    return frame.to_bytes()


# ── Transport ───────────────────────────────────────────────────────────────

def send_body(dev: NuvotonDevice, body: bytes, repeats: int = 1) -> bool:
    """Wrap a 252-byte body in the LED packet header and send it."""
    if len(body) != BODY_BYTES:
        raise ValueError(f"body must be {BODY_BYTES} bytes, got {len(body)}")
    packet = NuvotonDevice._make_led_packet(body)
    for _ in range(repeats):
        dev.write_report(packet)
    return True


def send_raw_frame(dev: NuvotonDevice, frame320: bytes) -> bool:
    """Send a captured 320-byte frame (5 x 64-byte reports) verbatim."""
    if len(frame320) != 320:
        raise ValueError(f"frame must be 320 bytes, got {len(frame320)}")
    dev.write_report(frame320)
    return True


# ── Commands ────────────────────────────────────────────────────────────────

def cmd_query(dev: NuvotonDevice):
    dev.send_init()
    time.sleep(0.05)
    resp = dev.query_status()
    if resp:
        pm = resp[4] if len(resp) > 4 else None
        sub = resp[5] if len(resp) > 5 else None
        print(f"Handshake response: {bytes(resp[:16]).hex(' ')}")
        if pm is not None:
            print(f"PM=0x{pm:02X} SUB=0x{sub:02X}"
                  + ("  (PM=16 -> PA120/Assassin 120 Digital, 84 LEDs)" if pm == 0x10 else ""))
    else:
        print("No response to query (device write-only in this mode? continuing)")


def cmd_replay(dev: NuvotonDevice, path: str, duration: Optional[float]):
    data = open(path, 'rb').read()
    n = len(data) // 320
    if n == 0:
        print(f"No frames in {path}")
        return
    print(f"Replaying {n} captured TRCC frames from {path} (TRCC must be closed)")
    t0 = time.time()
    i = 0
    try:
        while duration is None or (time.time() - t0) < duration:
            send_raw_frame(dev, data[i * 320:(i + 1) * 320])
            i = (i + 1) % n
            time.sleep(0.15)          # ~6.7 fps, like TRCC
    except KeyboardInterrupt:
        pass
    print(f"Replayed {i} frames")


def cmd_demo(dev: NuvotonDevice, duration: float):
    print("Demo: CPU 42C 56% | GPU 47C 21%  (look at the cooler)")
    body = build_metrics_frame(42, 56, 47, 21)
    t0 = time.time()
    while (time.time() - t0) < duration:
        send_body(dev, body)
        time.sleep(0.2)


def cmd_probe(dev: NuvotonDevice):
    """
    Light one hypothesis group at a time so the physical mapping can be
    confirmed by eye.  Watch the cooler and note what each step lights.
    """
    steps = [
        ("CPU indicator leds 0,1",        G_CPU_IND,      None),
        ("CPU temp digit 1 (leds 2-8)",   G_CPU_TEMP[:7], None),
        ("CPU temp digit 2 (leds 9-15)",  G_CPU_TEMP[7:14], None),
        ("CPU temp digit 3 (leds 16-22)", G_CPU_TEMP[14:], None),
        ("°C led 23",                     G_CPU_CELSIUS,  None),
        ("°F led 24",                     G_CPU_FAHR,     None),
        ("CPU usage digit A (27-33)",     G_CPU_USAGE[2:9], None),
        ("CPU usage digit B (34-40)",     G_CPU_USAGE[9:], None),
        ("CPU % led 41",                  G_CPU_PERCENT,  None),
        ("GPU % led 42",                  G_GPU_PERCENT,  None),
        ("GPU usage digit A (56-50)",     G_GPU_USAGE[2:9], None),
        ("GPU usage digit B (49-43)",     G_GPU_USAGE[9:], None),
        ("GPU °C led 59",                 G_GPU_CELSIUS,  None),
        ("GPU °F led 60",                 G_GPU_FAHR,     None),
        ("GPU temp digit 3 (67-61)",      G_GPU_TEMP[14:], None),
        ("GPU temp digit 2 (74-68)",      G_GPU_TEMP[7:14], None),
        ("GPU temp digit 1 (81-75)",      G_GPU_TEMP[:7], None),
        ("GPU indicator leds 82,83",      G_GPU_IND,      None),
    ]
    for label, leds, mask in steps:
        frame = DisplayFrame()
        frame.light(leds, (255, 255, 255), mask)
        print(f"  -> {label}")
        send_body(dev, frame.to_bytes())
        time.sleep(1.5)
    frame = DisplayFrame()
    send_body(dev, frame.to_bytes())


def cmd_live(dev: NuvotonDevice, interval: float, temp_color: RGB,
             usage_color: RGB, duration: Optional[float]):
    from hardware_monitor import read_all

    print("Live metrics mode (Ctrl-C to stop). TRCC must be closed.")
    t0 = time.time()
    last_log = 0.0
    try:
        while duration is None or (time.time() - t0) < duration:
            snap = read_all()
            body = build_metrics_frame(
                snap.cpu_temp if snap.cpu_temp is not None else 0,
                snap.cpu_usage if snap.cpu_usage is not None else 0,
                snap.gpu_temp if snap.gpu_temp is not None else 0,
                snap.gpu_usage if snap.gpu_usage is not None else 0,
                temp_color=temp_color, usage_color=usage_color,
            )
            send_body(dev, body)
            now = time.time()
            if now - last_log >= 5:
                last_log = now
                print(f"  cpu {snap.cpu_temp}°C {snap.cpu_usage:.1f}% | "
                      f"gpu {snap.gpu_temp}°C {snap.gpu_usage}%")
            time.sleep(interval)
    except KeyboardInterrupt:
        pass


# ── CLI ─────────────────────────────────────────────────────────────────────

def _parse_color(s: str) -> RGB:
    s = s.lstrip('#')
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def main():
    p = argparse.ArgumentParser(description="Segment-display sender for 0416:8001")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--query", action="store_true", help="handshake/query, print response")
    g.add_argument("--replay", metavar="BIN", help="replay captured TRCC frames")
    g.add_argument("--demo", action="store_true", help="fixed digits for visual check")
    g.add_argument("--probe", action="store_true", help="light groups one by one")
    g.add_argument("--live", action="store_true", help="sensors -> digits loop")
    g.add_argument("--off", action="store_true", help="all LEDs off")
    p.add_argument("--duration", type=float, default=None,
                   help="seconds to run (default: until Ctrl-C; demo default 30)")
    p.add_argument("--interval", type=float, default=0.5, help="live loop interval (s)")
    p.add_argument("--temp-color", type=_parse_color, default=(0, 170, 255))
    p.add_argument("--usage-color", type=_parse_color, default=(0, 220, 80))
    args = p.parse_args()

    dev = NuvotonDevice()
    if not dev.connect():
        print("Device not found (0416:8001). Is it plugged in?")
        sys.exit(1)
    try:
        dev.send_init()
        if args.query:
            cmd_query(dev)
        elif args.replay:
            cmd_replay(dev, args.replay, args.duration)
        elif args.demo:
            cmd_demo(dev, args.duration or 30.0)
        elif args.probe:
            cmd_probe(dev)
        elif args.live:
            cmd_live(dev, args.interval, args.temp_color, args.usage_color, args.duration)
        elif args.off:
            send_body(dev, DisplayFrame().to_bytes())
    finally:
        if args.live or args.demo:
            send_body(dev, DisplayFrame().to_bytes())
        dev.disconnect()


if __name__ == "__main__":
    main()

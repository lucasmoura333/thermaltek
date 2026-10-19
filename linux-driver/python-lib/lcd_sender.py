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
  python lcd_sender.py --anim           P3 demo: 7-seg words (HOT/Err/HELP scroll)
                                        + heartbeat/blink on the free pixels
  python lcd_sender.py --scroll "TEXT"  marquee: text across all 10 digit blocks
  python lcd_sender.py --chase          eye candy: rainbow/chase/rain on 84 LEDs
  python lcd_sender.py --starfield      twinkling stars + shooting star
  python lcd_sender.py --clock          HH:MM on the usage digits, colon 41/42,
                                        seconds in binary on the free pixels
  python lcd_sender.py --image PIC      fax-scan PIC (any PIL image) column by
                                        column — the 84 LEDs light one 84px
                                        column per frame (30fps column stream)
  python lcd_sender.py --beacon FILE    optical transmitter: FILE bytes -> LED
                                        colour frames (4-colour 2-bit symbols,
                                        magenta START / yellow END, CRC32);
                                        round-trip decoder included
  python lcd_sender.py --fuzz           cold protocol probe (packet types, header
                                        bytes, report IDs, length field, frame rate)
  python lcd_sender.py --off            all LEDs off

FREE PIXELS (P3)
----------------
LEDs that stay dark in normal °C operation can be repurposed as status pixels:
the two leading blanks of each usage group (25, 26 / 57, 58 — TRCC lights them
only at 100%; on the mirrored GPU side the pair is 57/58, NOT 55/56, which are
segments of the tens digit) and the °F LEDs (24 / 60).  See --anim and
build_metrics_frame(status_color=...).
"""

import argparse
import math
import os
import random
import struct
import sys
import time
import zlib
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
    ALL_FREE_PIXELS,
    PKT_TYPE_LED,
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

# 7-segment letters, same F A B G E D C order as DIGIT_MASK.  Uppercase
# where the glyph is unambiguous; b/d/n/q/r/t are the conventional
# lowercase shapes (show_word falls back to the lowercase key for "HOT",
# "Err", "HELP" …).  I/1 and O/0 share the digit masks' shapes.
LETTER_MASK = {
    "A": [1, 1, 1, 1, 1, 0, 1],
    "b": [1, 0, 0, 1, 1, 1, 1],
    "C": [1, 1, 0, 0, 1, 1, 0],
    "d": [0, 0, 1, 1, 1, 1, 1],
    "E": [1, 1, 0, 1, 1, 1, 0],
    "F": [1, 1, 0, 1, 1, 0, 0],
    "G": [1, 1, 0, 0, 1, 1, 1],
    "H": [1, 0, 1, 1, 1, 0, 1],
    "I": [0, 0, 1, 0, 0, 0, 1],
    "J": [0, 0, 1, 0, 1, 1, 1],
    "L": [1, 0, 0, 0, 1, 1, 0],
    "n": [0, 0, 1, 1, 1, 0, 0],
    "O": [1, 1, 1, 0, 1, 1, 1],
    "P": [1, 1, 1, 1, 1, 0, 0],
    "q": [1, 1, 1, 1, 0, 0, 1],
    "r": [0, 0, 0, 1, 1, 0, 0],
    "S": [1, 1, 0, 1, 0, 1, 1],
    "t": [1, 0, 0, 1, 1, 1, 0],
    "U": [1, 0, 1, 0, 1, 1, 1],
    "Y": [1, 0, 1, 1, 0, 1, 1],
    "Z": [0, 1, 1, 1, 1, 1, 0],
    "z": [0, 1, 1, 1, 1, 1, 0],
    "-": [0, 0, 0, 1, 0, 0, 0],
}

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


def digit_blocks(group: Sequence[int], digits: int) -> List[List[int]]:
    """Split a LED group into its per-digit 7-LED blocks (display order)."""
    prefix_len = len(group) - digits * 7
    return [
        list(group[prefix_len + i * 7: prefix_len + (i + 1) * 7])
        for i in range(digits)
    ]


def _glyph_mask(ch: str) -> Optional[List[int]]:
    """Mask for one character (letters, digits, '-' and gaps); None = blank."""
    if ch in (" ", ""):
        return None
    mask = LETTER_MASK.get(ch) or LETTER_MASK.get(ch.lower())
    if mask is None and ch.isdigit():
        mask = DIGIT_MASK.get(int(ch))
    return mask


def show_word(frame: DisplayFrame, blocks: Sequence[Sequence[int]],
              text: str, color: RGB):
    """
    Render *text* as glyphs across *blocks* (one glyph per block, e.g. from
    digit_blocks()): letters via LETTER_MASK, digits via DIGIT_MASK, spaces
    and unknown characters stay dark; longer than the block list = truncated.
    "HOT"/"Err"/"HELP" are valid words; T/B/D/N/Q/R fall back to lowercase.
    """
    for block, ch in zip(blocks, text):
        mask = _glyph_mask(ch)
        if mask:
            frame.light(block, color, mask)


# All 10 digit blocks in physical order (CPU temp | CPU usage | GPU usage |
# GPU temp) — the marquee strip for --scroll.
MARQUEE_BLOCKS = (digit_blocks(G_CPU_TEMP, 3) + digit_blocks(G_CPU_USAGE, 2)
                  + digit_blocks(G_GPU_USAGE, 2) + digit_blocks(G_GPU_TEMP, 3))


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
                        gpu_indicator_color: Optional[RGB] = None,
                        status_color: Optional[RGB] = None,
                        status_leds: Optional[Sequence[int]] = None) -> bytes:
    """
    Compose the full metrics frame:
      CPU side: indicator + temp digits + °C + usage digits + %
      GPU side: % + usage digits + °C + temp digits + indicator

    *temp_color* / *usage_color* colour both sides; the per-side
    *_temp_color / *_usage_color overrides take precedence.  Indicator
    colours default to the matching side's temperature colour.

    *status_color* lights the free pixels (ALL_FREE_PIXELS by default:
    blanks 25/26/57/58 + °F 24/60) — heartbeat/blink overlays, see --anim.
    *status_leds* overrides which LEDs that colour is applied to.
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
        # Round to int; None and non-finite (NaN/inf) render as 0
        # (LHM/ADL can emit NaN; ADL can also emit inf).
        return int(round(v)) if v is not None and math.isfinite(v) else 0

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

    if status_color is not None:
        for led in (status_leds if status_leds is not None else ALL_FREE_PIXELS):
            frame.put(led, status_color)

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


def cmd_anim(dev: NuvotonDevice):
    """
    P3 demo — 7-segment words + animations on the free pixels:

      1. "HOT" (red) on the CPU temp digits, "Err" (amber) on the GPU temp digits
      2. "HELP" (blue) scrolling across the CPU temp digits
      3. heartbeat: double-thump (white) on blanks 25/26/57/58 + °F 24/60,
         over the normal demo numbers
      4. blink x3 (cyan) on the same six pixels

    If the °F pixels (24 / 60) never light up here they do not exist on the
    hardware (they are never driven by TRCC in °C mode — treated as free).
    """
    demo_body = build_metrics_frame(42, 56, 47, 21)

    def hold(body: bytes, secs: float, interval: float = 0.15):
        t0 = time.time()
        while time.time() - t0 < secs:
            send_body(dev, body)
            time.sleep(interval)

    frame = DisplayFrame()
    show_word(frame, digit_blocks(G_CPU_TEMP, 3), "HOT", (255, 40, 0))
    show_word(frame, digit_blocks(G_GPU_TEMP, 3), "Err", (255, 170, 0))
    print("words      : 'HOT' (red) on CPU temp | 'Err' (amber) on GPU temp")
    hold(frame.to_bytes(), 4.0)

    blocks = digit_blocks(G_CPU_TEMP, 3)
    print("scroll     : 'HELP' (blue) across the CPU temp digits")
    for _ in range(2):
        for i in range(3):
            frame = DisplayFrame()
            show_word(frame, blocks, "HELP"[i:i + 3], (0, 160, 255))
            hold(frame.to_bytes(), 0.7)

    beat_on = build_metrics_frame(42, 56, 47, 21, status_color=(255, 255, 255))
    print("heartbeat  : blanks 25/26/57/58 + °F 24/60 pulse (double thump)")
    for _ in range(4):
        hold(beat_on, 0.15)
        hold(demo_body, 0.15)
        hold(beat_on, 0.15)
        hold(demo_body, 0.75)

    blink_on = build_metrics_frame(42, 56, 47, 21, status_color=(0, 255, 255))
    print("blink x3   : same six pixels (cyan)")
    for _ in range(3):
        hold(blink_on, 0.35)
        hold(demo_body, 0.35)

    print("done")


def cmd_scroll(dev: NuvotonDevice, text: str,
               duration: Optional[float] = None, speed: float = 0.3):
    """Marquee: scroll *text* across all 10 digit blocks (physical order)."""
    window = len(MARQUEE_BLOCKS)
    padded = " " * window + text.upper() + " " * window
    print(f"marquee    : '{text.upper()}' across all {window} digit blocks (Ctrl-C stops)")
    t0 = time.time()
    i = 0
    try:
        while duration is None or (time.time() - t0) < duration:
            frame = DisplayFrame()
            show_word(frame, MARQUEE_BLOCKS, padded[i:i + window], (0, 200, 255))
            send_body(dev, frame.to_bytes())
            i = (i + 1) % (len(padded) - window + 1)
            time.sleep(speed)
    except KeyboardInterrupt:
        pass


def cmd_chase(dev: NuvotonDevice, scale: float = 1.0):
    """
    Eye-candy animation across all 84 LEDs (each segment is one RGB pixel):

      1. rotating rainbow (hue by chain position, spinning)
      2. chase: bright dot with a 6-LED fading trail
      3. matrix rain: random segments flicker in green
    """
    import colorsys

    def hue_rgb(h: float, v: float = 1.0) -> RGB:
        r, g, b = colorsys.hsv_to_rgb(h % 1.0, 1.0, v)
        return (int(r * 255), int(g * 255), int(b * 255))

    print("rainbow    : rotating hue across the 84-LED chain")
    t0 = time.time()
    k = 0
    while (time.time() - t0) < 4.0 * scale:
        frame = DisplayFrame()
        for i in range(N_LEDS):
            frame.put(i, hue_rgb(i / N_LEDS + k / 48.0))
        send_body(dev, frame.to_bytes())
        k += 1
        time.sleep(0.04)

    print("chase      : bright dot with a 6-LED trail")
    t0 = time.time()
    k = 0
    while (time.time() - t0) < 4.0 * scale:
        frame = DisplayFrame()
        for t in range(6):
            frame.put((k - t) % N_LEDS, hue_rgb(0.55, v=1.0 - t / 6.0))
        send_body(dev, frame.to_bytes())
        k += 1
        time.sleep(0.04)

    print("rain       : random segments flicker (green)")
    t0 = time.time()
    while (time.time() - t0) < 4.0 * scale:
        frame = DisplayFrame()
        for _ in range(14):
            frame.put(random.randrange(N_LEDS), hue_rgb(0.33, v=random.random()))
        send_body(dev, frame.to_bytes())
        time.sleep(0.08)


def cmd_fuzz(dev: NuvotonDevice, scale: float = 1.0):
    """
    Cold protocol probe — the device is WRITE-ONLY with no ACK, so every
    negative here is weak (no visible change ≠ no effect).

    Phases (each from a white baseline; watch the display):
      0. indicators 0/1 and 82/83 in split colours — how do the printed
         CPU/GPU glyphs render per-LED (blend or split)?
      1. packet type byte (offset 12): 0x00, 0x03, 0x04, 0x20, 0xFF
      2. header bytes 4 and 8 (always 00 in TRCC): 0x01 / 0x40 / 0xFF
      3. HID Report ID 1 and 2 with the full white frame
      4. feature-report round-trip (hidapi only; likely rejected)
      5. length field lies (0x0000 / 0x0001 / 0xFFFF with full body)
      6. frame-rate ceiling: paced 10/30/60 fps dot + 300-frame burst
    """
    white = bytes((255, 255, 255)) * N_LEDS

    def hold(body: bytes, secs: float, b12: int = PKT_TYPE_LED,
             b4: int = 0, b8: int = 0, len_field: Optional[int] = None):
        lf = len(body) if len_field is None else len_field
        packet = bytes([
            0xDA, 0xDB, 0xDC, 0xDD,
            b4, 0, 0, 0,
            b8, 0, 0, 0,
            b12, 0, 0, 0,
            lf & 0xFF, (lf >> 8) & 0xFF, 0, 0,
        ]) + body
        t0 = time.time()
        while (time.time() - t0) < secs * scale:
            dev.write_report(packet)
            time.sleep(0.05)

    # 0) indicators — printed CPU/GPU glyph rendering
    print("fuzz 0/6  : indicators em cores divididas (olhe os escritos CPU/GPU)")
    frame = DisplayFrame()
    frame.put(0, (255, 0, 0))
    frame.put(1, (0, 255, 0))
    frame.put(82, (0, 0, 255))
    frame.put(83, (255, 255, 0))
    print("  CPU=vermelho/verde, GPU=azul/amarelo")
    t0 = time.time()
    while (time.time() - t0) < 3.0 * scale:
        send_body(dev, frame.to_bytes())
        time.sleep(0.1)
    hold(white, 0.6)

    # 1) packet type
    print("fuzz 1/6  : byte 12 (tipo de pacote)")
    for t in (0x00, 0x03, 0x04, 0x20, 0xFF):
        print(f"  tipo=0x{t:02X} (mudou algo?)")
        hold(white, 2.0, b12=t)
        hold(white, 0.6)

    # 2) header bytes 4 / 8
    print("fuzz 2/6  : bytes de header 4 e 8")
    for v in (0x01, 0x40, 0xFF):
        print(f"  byte4=0x{v:02X}")
        hold(white, 1.5, b4=v)
        hold(white, 0.6)
    for v in (0x01, 0x10, 0xFF):
        print(f"  byte8=0x{v:02X}")
        hold(white, 1.5, b8=v)
        hold(white, 0.6)

    # 3) Report ID
    print("fuzz 3/6  : Report ID 1 e 2 (pode ser rejeitado no Windows - negativa fraca)")
    base = NuvotonDevice._make_led_packet(white)
    base = base + bytes((-len(base)) % 64)
    for rid in (1, 2):
        try:
            t0 = time.time()
            while (time.time() - t0) < 2.0 * scale:
                for off in range(0, len(base), 64):
                    dev.device.write(bytes([rid]) + base[off:off + 64])
                time.sleep(0.2)
            print(f"  Report ID {rid}: escrito sem erro")
        except Exception as e:
            print(f"  Report ID {rid}: erro {e!r}")
        hold(white, 0.6)

    # 4) feature reports
    print("fuzz 4/6  : feature report (hidapi)")
    hiddev = getattr(getattr(dev, "device", None), "_dev", None)
    if hiddev is None:
        print("  backend sem acesso a feature reports — skip")
    else:
        try:
            hiddev.send_feature_report(bytes(65))
            print("  send_feature_report: aceito (ninguém esperava)")
        except Exception as e:
            print(f"  send_feature_report rejeitado: {e!r}")
        try:
            resp = hiddev.get_feature_report(0, 64)
            print(f"  get_feature_report -> {bytes(resp)[:16].hex(' ')}")
        except Exception as e:
            print(f"  get_feature_report rejeitado: {e!r}")

    # 5) length field lies
    print("fuzz 5/6  : length field mentiroso (corpo completo enviado)")
    for lf in (0x0000, 0x0001, 0xFFFF):
        print(f"  len=0x{lf:04X} (truncou? trocou de modo?)")
        hold(white, 1.5, len_field=lf)
        hold(white, 0.6)

    # 6) frame rate
    print("fuzz 6/6  : taxa de atualização")
    for fps in (10, 30, 60):
        dot = 0
        t0 = time.time()
        while (time.time() - t0) < 2.5 * scale:
            frame = DisplayFrame()
            frame.put(dot % N_LEDS, (255, 255, 255))
            send_body(dev, frame.to_bytes())
            dot += 5
            time.sleep(1.0 / fps)
        print(f"  dot a {fps} fps enviado")
    frame = DisplayFrame()
    for i in range(N_LEDS):
        frame.put(i, (0, 60, 255))
    t0 = time.time()
    for _ in range(300):
        send_body(dev, frame.to_bytes())
    dt = time.time() - t0
    print(f"  burst: 300 frames em {dt:.2f}s -> {300 / dt:.0f} fps efetivos de escrita")
    print("fuzz done")


def cmd_starfield(dev: NuvotonDevice, duration: Optional[float] = None):
    """Twinkling star field + a shooting star with a fading trail, ~30 fps."""
    print("starfield  : stars twinkle + shooting star (Ctrl-C stops)")
    stars = {}                      # led -> brightness 0..255
    shot = None                     # (head_pos, age)
    t0 = time.time()
    last_shot = t0

    def star_color(v: int) -> RGB:
        return (int(v * 0.6), int(v * 0.8), v)

    try:
        while duration is None or (time.time() - t0) < duration:
            now = time.time()
            for led in list(stars):
                stars[led] = int(stars[led] * 0.90)
                if stars[led] < 10:
                    del stars[led]
            if len(stars) < 18 and random.random() < 0.6:
                stars[random.randrange(N_LEDS)] = 200 + random.randrange(56)
            if shot is None and (now - last_shot) > 3.0:
                shot = [random.randrange(N_LEDS), 0]
                last_shot = now
            frame = DisplayFrame()
            for led, v in stars.items():
                frame.put(led, star_color(v))
            if shot is not None:
                head, age = shot
                for t in range(9):
                    led = (head - t) % N_LEDS
                    v = max(0, 255 - t * 30)
                    if v:
                        frame.put(led, star_color(v))
                shot[0] = (head + 2) % N_LEDS
                shot[1] += 1
                if shot[1] > N_LEDS // 4:
                    shot = None
            send_body(dev, frame.to_bytes())
            time.sleep(0.033)
    except KeyboardInterrupt:
        pass


def build_clock_frame(tm: time.struct_time, colon_on: bool) -> bytes:
    """
    Clock layout (physically contiguous in the middle of the display):

      [HH] [ : ] [MM]     HH = CPU usage digits (27-40), colon = LEDs 41+42,
                          MM = GPU usage digits (43-58)
    6 free pixels [24,25,26,57,58,60] = seconds in binary, LSB first.
    """
    frame = DisplayFrame()
    c = (0, 190, 255)
    show_number(frame, G_CPU_USAGE, 2, tm.tm_hour, c)
    show_number(frame, G_GPU_USAGE, 2, tm.tm_min, c)
    if colon_on:
        frame.put(41, c)
        frame.put(42, c)
    for i, led in enumerate(sorted(ALL_FREE_PIXELS)):
        if (tm.tm_sec >> i) & 1:
            frame.put(led, (0, 255, 120))
    return frame.to_bytes()


def cmd_clock(dev: NuvotonDevice, duration: Optional[float] = None):
    """Live HH:MM clock; colon blinks 1 Hz; seconds shown in binary."""
    print("clock      : HH:MM (usage digits) + colon 41/42 + seconds binarios (Ctrl-C stops)")
    t0 = time.time()
    try:
        while duration is None or (time.time() - t0) < duration:
            tm = time.localtime()
            colon_on = int(time.time() * 2) % 2 == 0
            send_body(dev, build_clock_frame(tm, colon_on))
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass


def cmd_image(dev: NuvotonDevice, path: str,
              duration: Optional[float] = None, fps: float = 12.0):
    """
    Fax scan: the image is resized to 84 px tall; every frame lights one
    84-pixel column (top -> bottom = LED 0 -> 83), scanning left to right.
    The strip is a 1-D chain, so pictures are streamed column by column.
    """
    try:
        from PIL import Image
    except ImportError:
        print("--image needs Pillow (pip install pillow)")
        return
    img = Image.open(path).convert("RGB")
    w, h = img.size
    new_w = max(1, round(w * 84 / h))
    img = img.resize((new_w, 84), Image.LANCZOS)
    print(f"image      : {path} ({w}x{h}) -> {new_w} colunas x 84 px, {fps:.0f} fps"
          f" (~{new_w / fps:.1f}s por passada)")
    px = img.load()
    t0 = time.time()
    try:
        while duration is None or (time.time() - t0) < duration:
            for x in range(new_w):
                frame = DisplayFrame()
                for y in range(84):
                    frame.put(y, px[x, y])
                send_body(dev, frame.to_bytes())
                time.sleep(1.0 / fps)
    except KeyboardInterrupt:
        pass


# ── Optical beacon: file bytes -> LED colours (and back) ────────────────────
#
# The only output channel is light.  84 independently coloured LEDs = one
# frame carry 84 x 2 bits with a 4-colour alphabet:
#
#   palette: 0=off  1=red  2=green  3=blue      (max distance -> easy to read)
#
# Stream layout:
#   3x ALL-MAGENTA frames      START     (magenta is not in the palette, so
#   1x meta frame              META       it can never occur in data)
#   N data frames              DATA      seq byte + 19 payload bytes + XOR
#   3x ALL-YELLOW frames       END       (yellow is not in the palette either)
#
# Meta payload: b"NUVO" + u32 length + u16 nframes + u32 crc32(payload).
# Bit order: byte k -> LEDs 4k..4k+3, two bits per LED, MSB pair first.
# Receiver side: record the LEDs (camera / frame dump), classify each LED to
# the nearest palette colour, rebuild bytes, check XOR/seq/CRC.

BEACON_PALETTE = [(0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255)]
BEACON_START = [(255, 0, 255)] * N_LEDS
BEACON_END = [(255, 255, 0)] * N_LEDS
BEACON_DATA_PER_FRAME = 19          # + seq + xor = 21 bytes = 168 bits


def _beacon_encode_frame(seq: int, data: bytes) -> List[RGB]:
    payload = bytes([seq]) + data.ljust(BEACON_DATA_PER_FRAME, b"\x00")
    x = seq
    for b in data:
        x ^= b
    payload += bytes([x])
    frame: List[RGB] = []
    for byte in payload:
        for pair in ((byte >> 6) & 3, (byte >> 4) & 3, (byte >> 2) & 3, byte & 3):
            frame.append(BEACON_PALETTE[pair])
    return frame


def _beacon_decode_frame(frame: Sequence[RGB]) -> bytes:
    idx = []
    for (r, g, b) in frame:
        best, bd = 0, None
        for k, (pr, pg, pb) in enumerate(BEACON_PALETTE):
            d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
            if bd is None or d < bd:
                bd, best = d, k
        idx.append(best)
    out = bytearray()
    for k in range(21):
        byte = 0
        for pair in idx[k * 4:k * 4 + 4]:
            byte = (byte << 2) | pair
        out.append(byte)
    return bytes(out)


def beacon_encode(payload: bytes) -> List[List[RGB]]:
    """Files bytes -> colour frame list (START + META + DATA + END)."""
    chunks = [payload[i:i + BEACON_DATA_PER_FRAME]
              for i in range(0, len(payload), BEACON_DATA_PER_FRAME)]
    meta = (b"NUVO" + struct.pack("<I", len(payload))
            + struct.pack("<H", len(chunks))
            + struct.pack("<I", zlib.crc32(payload) & 0xFFFFFFFF))
    frames = [BEACON_START] * 3
    frames.append(_beacon_encode_frame(0, meta))
    frames += [_beacon_encode_frame(i + 1, c) for i, c in enumerate(chunks)]
    frames += [BEACON_END] * 3
    return frames


def beacon_decode(frames: Sequence[Sequence[RGB]]) -> bytes:
    """
    Colour frame list -> original bytes.  Raises ValueError on missing sync,
    sequence gaps or CRC mismatch (weak link: one corrupted frame aborts).
    """
    n = len(frames)
    start = None
    for i in range(n - 3):
        if all(list(frames[j]) == BEACON_START for j in range(i, i + 3)):
            start = i
            break
    if start is None:
        raise ValueError("sem frames START (magenta x3)")
    if start + 4 > n:
        raise ValueError("stream truncado no META")
    meta_raw = _beacon_decode_frame(frames[start + 3])
    meta = meta_raw[1:20]                    # 19 payload bytes (seq first!)
    x = meta_raw[0]
    for b in meta:
        x ^= b
    if meta_raw[20] != x:
        raise ValueError("META corrompido (XOR)")
    if meta[:4] != b"NUVO":
        raise ValueError("META invalido (magic)")
    length = struct.unpack("<I", meta[4:8])[0]
    nframes = struct.unpack("<H", meta[8:10])[0]
    crc_exp = struct.unpack("<I", meta[10:14])[0]
    data = bytearray()
    pos = start + 4
    for k in range(nframes):
        if pos >= n:
            raise ValueError(f"quadro {k + 1}/{nframes} faltando (stream acabou)")
        raw = _beacon_decode_frame(frames[pos])
        seq, body, xor = raw[0], raw[1:20], raw[20]
        if seq != ((k + 1) & 0xFF):
            raise ValueError(f"quadro fora de ordem no {k + 1}: seq={seq}")
        x = seq
        for b in body:
            x ^= b
        if xor != x:
            raise ValueError(f"XOR invalido no quadro {k + 1}")
        data += body
        pos += 1
    out = bytes(data[:length])
    crc = zlib.crc32(out) & 0xFFFFFFFF
    if crc != crc_exp:
        raise ValueError(f"CRC32 nao bate (esperado {crc_exp:08x}, veio {crc:08x})")
    return out


def cmd_beacon(dev: NuvotonDevice, path: str, fps: float = 10.0):
    """Transmit a file as coloured light.  Round-trip self-test before sending."""
    with open(path, "rb") as f:
        payload = f.read()
    frames = beacon_encode(payload)
    back = beacon_decode(frames)
    ok = back == payload
    print(f"beacon     : {path} ({len(payload)} B) -> {len(frames)} frames"
          f" @ {fps:.0f}fps (~{len(frames) / fps:.1f}s)")
    print(f"beacon     : self-test round-trip: {'OK' if ok else 'FALHOU'}"
          f" ({len(back)} B decodificados)")
    if not ok:
        return
    t0 = time.time()
    try:
        for k, colors in enumerate(frames):
            frame = DisplayFrame()
            for led, c in enumerate(colors):
                frame.put(led, c)
            send_body(dev, frame.to_bytes())
            time.sleep(1.0 / fps)
    except KeyboardInterrupt:
        pass
    print(f"beacon     : {len(frames)} frames transmitidos")


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
    g.add_argument("--anim", action="store_true",
                   help="P3 demo: words (HOT/Err/HELP) + heartbeat/blink on free pixels")
    g.add_argument("--scroll", metavar="TEXT",
                   help="marquee: scroll TEXT across all 10 digit blocks")
    g.add_argument("--chase", action="store_true",
                   help="eye candy: rainbow/chase/rain across the 84 LEDs")
    g.add_argument("--starfield", action="store_true",
                   help="twinkling stars + shooting star")
    g.add_argument("--clock", action="store_true",
                   help="HH:MM clock (colon 41/42, seconds binary on free pixels)")
    g.add_argument("--image", metavar="PIC",
                   help="fax-scan an image: one 84px column per frame")
    g.add_argument("--beacon", metavar="FILE",
                   help="optical transmitter: FILE bytes -> LED colour frames")
    g.add_argument("--fuzz", action="store_true",
                   help="cold protocol probe (types/header/report IDs/length/rate)")
    g.add_argument("--off", action="store_true", help="all LEDs off")
    p.add_argument("--fps", type=float, default=None,
                   help="frame rate for --image (default 12) / --beacon (default 10)")
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
        elif args.anim:
            cmd_anim(dev)
        elif args.scroll:
            cmd_scroll(dev, args.scroll, args.duration)
        elif args.chase:
            cmd_chase(dev)
        elif args.starfield:
            cmd_starfield(dev, args.duration)
        elif args.clock:
            cmd_clock(dev, args.duration)
        elif args.image:
            cmd_image(dev, args.image, args.duration, args.fps or 12.0)
        elif args.beacon:
            cmd_beacon(dev, args.beacon, args.fps or 10.0)
        elif args.fuzz:
            cmd_fuzz(dev)
        elif args.off:
            send_body(dev, DisplayFrame().to_bytes())
    finally:
        if (args.live or args.demo or args.anim or args.scroll or args.chase
                or args.starfield or args.clock or args.image or args.beacon
                or args.fuzz):
            send_body(dev, DisplayFrame().to_bytes())
        dev.disconnect()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Nuvoton RGB Daemon

Reads CPU/GPU sensors and maps them to LED colours.

Usage:
    python nuvoton_daemon.py [--config config.json] [--mode cpu_temp] [--once]

Modes (set in config.json or via --mode):
    cpu_temp  — colour follows CPU temperature           (default)
    gpu_temp  — colour follows GPU temperature
    cpu_usage — colour follows CPU usage %
    gpu_usage — colour follows GPU busy %
    static    — fixed colour from config
    off       — LEDs off
    zones     — every display zone lit solid in its own sensor-gradient
                colour (CPU temp, CPU usage, GPU temp, GPU usage);
                indicator LEDs reflect overall load
    display   — real numbers on the segment display: CPU/GPU temperature
                and usage as digits, each group coloured by its gradient
    fire      — thermal demoscene: 1-D fire simulation on all 84 LEDs,
                intensity follows the hottest sensor; >= hot_at flashes
                "HOT" over the flames; NUVOTON_FIRE_SWEEP=1 demo ramp
    vibe      — auto mood: normal display while busy; after idle_samples
                consecutive idle reads -> "Zzz" + slow blue breathing on
                the free pixels (env: NUVOTON_VIBE_IDLE / NUVOTON_VIBE_SECS)

The daemon runs until killed (Ctrl-C).
"""

import argparse
import json
import logging
import math
import os
import random
import signal
import sys
import time
from typing import List, Optional, Tuple

# Add directory containing this script to path so local imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nuvoton_hid import (NuvotonDevice, LED_CPU_TEMP, LED_GPU_TEMP,
                         ALL_FREE_PIXELS)
from hardware_monitor import HardwareSnapshot, read_all
from lcd_sender import (build_metrics_frame, send_body, DisplayFrame,
                        show_word, digit_blocks)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("nuvoton_daemon")

_DEFAULT_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


# ── Config helpers ─────────────────────────────────────────────────────────

def load_config(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def _interpolate_color(
    value: float, thresholds: List[dict]
) -> Tuple[int, int, int]:
    """
    Map a scalar *value* to an RGB colour using a threshold list.

    Each threshold entry: {"max": <float>, "color": [r, g, b]}
    Sorted by max ascending; the first entry whose max >= value wins.
    If value exceeds all thresholds the last entry's colour is used.
    """
    for t in sorted(thresholds, key=lambda x: x["max"]):
        if value <= t["max"]:
            return tuple(t["color"])
    return tuple(thresholds[-1]["color"])


def pick_color(mode: str, snap: HardwareSnapshot, mode_cfg: dict,
               modes_cfg: Optional[dict] = None) -> Tuple[int, int, int]:
    """Return (r, g, b) for the current sensor snapshot and mode."""
    if mode == "off":
        return (0, 0, 0)

    if mode == "static":
        return tuple(mode_cfg.get("color", [0, 180, 255]))

    thresholds = mode_cfg.get("thresholds", [])
    if not thresholds:
        logger.warning(f"No thresholds configured for mode '{mode}'; returning off")
        return (0, 0, 0)

    if mode == "cpu_temp":
        value = snap.cpu_temp
        if value is None:
            # CPU temp needs admin (Ring0 driver). Fall back to cpu_usage so
            # LEDs still respond dynamically.
            value = snap.cpu_usage
            fallback_thresholds = (modes_cfg or {}).get("cpu_usage", {}).get("thresholds")
            thresholds = fallback_thresholds if fallback_thresholds else thresholds
    elif mode == "gpu_temp":
        value = snap.gpu_temp
    elif mode == "cpu_usage":
        value = snap.cpu_usage
    elif mode == "gpu_usage":
        value = snap.gpu_usage
    else:
        logger.warning(f"Unknown mode '{mode}'; returning off")
        return (0, 0, 0)

    if value is None:
        logger.warning(f"Sensor for mode '{mode}' returned None; using first threshold colour")
        return tuple(thresholds[0]["color"])

    return _interpolate_color(value, thresholds)


def _cpu_usage_thresholds_from_config(cpu_temp_thresholds: list) -> list:
    pass  # no longer used


# ── Zone-mode colour helpers ────────────────────────────────────────────────

_TEMP_STOPS = [
    (0,   (  0,  20, 220)),   # cold -> bright blue
    (40,  (  0, 100, 255)),   # cool -> sky blue
    (55,  (  0, 220, 200)),   # warm -> cyan
    (70,  (  0, 220,   0)),   # hot  -> green
    (80,  (220, 140,   0)),   # very hot -> orange
    (90,  (255,  30,   0)),   # danger -> red
    (100, (255,   0,   0)),   # critical
]

_USAGE_STOPS = [
    (0,   (  0,   0, 180)),   # idle   -> visible blue
    (20,  (  0,  80, 255)),   # low    -> brighter blue
    (50,  (  0, 200,  80)),   # medium -> green
    (75,  (220, 120,   0)),   # high   -> orange
    (95,  (255,  20,   0)),   # near-max -> red
    (100, (255,   0,   0)),   # pegged
]


def _lerp_stops(value: float, stops: list) -> Tuple[int, int, int]:
    """Linear-interpolate colour between two adjacent gradient stops."""
    value = max(stops[0][0], min(stops[-1][0], value))
    for i in range(len(stops) - 1):
        v0, c0 = stops[i]
        v1, c1 = stops[i + 1]
        if v0 <= value <= v1:
            t = (value - v0) / (v1 - v0) if v1 != v0 else 0.0
            return (
                int(c0[0] + t * (c1[0] - c0[0])),
                int(c0[1] + t * (c1[1] - c0[1])),
                int(c0[2] + t * (c1[2] - c0[2])),
            )
    return stops[-1][1]


def _temp_color(temp_c: Optional[float]) -> Tuple[int, int, int]:
    if temp_c is None or not math.isfinite(temp_c):
        return (0, 20, 220)   # unknown -> bright blue, not dim
    return _lerp_stops(temp_c, _TEMP_STOPS)


def _usage_color(usage_pct: Optional[float]) -> Tuple[int, int, int]:
    if usage_pct is None or not math.isfinite(usage_pct):
        return (0, 0, 180)   # unknown -> visible blue
    return _lerp_stops(usage_pct, _USAGE_STOPS)


def run_zones(config_path: str = _DEFAULT_CONFIG,
              run_once: bool = False) -> bool:
    """
    Zone-preview mode: every segment of each display zone lights solid in
    its own sensor-gradient colour; the indicator LEDs reflect overall load.

    Zone -> sensor mapping (validated against a live TRCC capture):
      CPU temp  digits (2-22) + °C (23)  ← CPU temperature gradient
      CPU usage digits (25-40) + % (41)  ← CPU usage % gradient
      GPU temp  digits (61-81) + °C (59) ← GPU temperature gradient
      GPU usage digits (43-58) + % (42)  ← GPU usage % gradient
      Indicators (0,1 / 82,83)           ← max(CPU usage, GPU usage) gradient
    """
    cfg = load_config(config_path)
    interval  = cfg.get("update_interval_s", 2)
    brightness = float(cfg.get("brightness", 1.0))

    import psutil as _psutil
    _psutil.cpu_percent(interval=None)
    time.sleep(0.1)

    with NuvotonDevice() as dev:
        if not dev.device:
            logger.error("Device not found. Is the cooler connected? (TRCC must be CLOSED)")
            return False

        dev.send_init()
        logger.info("Zone daemon started")

        signal.signal(signal.SIGINT,  _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

        while _running:
            try:
                snap       = read_all()
                cpu_t_col  = _temp_color(snap.cpu_temp)
                cpu_u_col  = _usage_color(snap.cpu_usage)
                gpu_t_col  = _temp_color(snap.gpu_temp)
                gpu_u_col  = _usage_color(snap.gpu_usage)

                # When CPU temperature is unavailable (no admin), mirror CPU usage
                # colour in the temp zone so it's never a dead dim-blue indicator
                if snap.cpu_temp is None:
                    cpu_t_col = cpu_u_col

                # Indicators use the "hottest" usage as the ambient colour
                max_usage = max(
                    snap.cpu_usage if snap.cpu_usage is not None else 0,
                    snap.gpu_usage if snap.gpu_usage is not None else 0,
                )
                ind_col = _usage_color(max_usage)

                dev.set_zones_color(
                    cpu_temp=cpu_t_col,
                    cpu_usage=cpu_u_col,
                    gpu_temp=gpu_t_col,
                    gpu_usage=gpu_u_col,
                    ring_color=ind_col,
                    brightness=brightness,
                    repeats=3,
                )

                cpu_t_str = f"{snap.cpu_temp:.1f}" if snap.cpu_temp is not None else "None"
                gpu_t_str = f"{snap.gpu_temp:.1f}" if snap.gpu_temp is not None else "None"
                gpu_u_str = f"{snap.gpu_usage:.1f}" if snap.gpu_usage is not None else "None"
                logger.info(
                    f"zones | "
                    f"cpu {cpu_t_str}°C -> {cpu_t_col} | "
                    f"cpu_u {snap.cpu_usage:.1f}% -> {cpu_u_col} | "
                    f"gpu {gpu_t_str}°C -> {gpu_t_col} | "
                    f"gpu_u {gpu_u_str}% -> {gpu_u_col} | "
                    f"ind -> {ind_col}"
                )
            except Exception as e:
                logger.error(f"update failed (continuing): {e!r}")

            if run_once:
                break
            time.sleep(interval)

        dev.set_off()
        logger.info("LEDs off, zone daemon stopped")
    return True


def run_display(config_path: str = _DEFAULT_CONFIG,
                run_once: bool = False) -> bool:
    """
    Display mode: render the real sensor values as 7-segment digits on the
    cooler's display, each group coloured by its own gradient.

      CPU temp  digits + °C  ← _temp_color(cpu_temp)
      CPU usage digits + %   ← _usage_color(cpu_usage)
      GPU temp  digits + °C  ← _temp_color(gpu_temp)
      GPU usage digits + %   ← _usage_color(gpu_usage)
      CPU/GPU indicator LEDs ← matching side's temperature colour
    """
    cfg = load_config(config_path)
    interval   = cfg.get("update_interval_s", 2)
    brightness = float(cfg.get("brightness", 1.0))

    import psutil as _psutil
    _psutil.cpu_percent(interval=None)
    time.sleep(0.1)

    with NuvotonDevice() as dev:
        if not dev.device:
            logger.error("Device not found. Is the cooler connected? (TRCC must be CLOSED)")
            return False

        dev.send_init()
        logger.info("Display daemon started")

        signal.signal(signal.SIGINT,  _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

        while _running:
            try:
                snap = read_all()

                cpu_t_col = _temp_color(snap.cpu_temp)
                cpu_u_col = _usage_color(snap.cpu_usage)
                gpu_t_col = _temp_color(snap.gpu_temp)
                gpu_u_col = _usage_color(snap.gpu_usage)

                # When CPU temperature is unavailable (no admin), mirror CPU usage
                # colour in the temp group so it's never a dead dim-blue indicator
                if snap.cpu_temp is None:
                    cpu_t_col = cpu_u_col

                body = build_metrics_frame(
                    snap.cpu_temp  if snap.cpu_temp  is not None else 0,
                    snap.cpu_usage if snap.cpu_usage is not None else 0,
                    snap.gpu_temp  if snap.gpu_temp  is not None else 0,
                    snap.gpu_usage if snap.gpu_usage is not None else 0,
                    cpu_temp_color=cpu_t_col, cpu_usage_color=cpu_u_col,
                    gpu_temp_color=gpu_t_col, gpu_usage_color=gpu_u_col,
                )
                if brightness != 1.0:
                    body = bytes(min(255, int(c * brightness)) for c in body)
                send_body(dev, body)

                cpu_t_str = f"{snap.cpu_temp:.1f}" if snap.cpu_temp is not None else "None"
                gpu_t_str = f"{snap.gpu_temp:.1f}" if snap.gpu_temp is not None else "None"
                gpu_u_str = f"{snap.gpu_usage:.1f}" if snap.gpu_usage is not None else "None"
                logger.info(
                    f"display | "
                    f"cpu {cpu_t_str}°C -> {cpu_t_col} | "
                    f"cpu_u {snap.cpu_usage:.1f}% -> {cpu_u_col} | "
                    f"gpu {gpu_t_str}°C -> {gpu_t_col} | "
                    f"gpu_u {gpu_u_str}% -> {gpu_u_col}"
                )
            except Exception as e:
                logger.error(f"update failed (continuing): {e!r}")

            if run_once:
                break
            time.sleep(interval)

        dev.set_off()
        logger.info("LEDs off, display daemon stopped")
    return True


# ── Fire mode (thermal demoscene) ──────────────────────────────────────────

_FIRE_RAMP = [
    (0,   (0, 0, 0)),
    (50,  (90, 0, 0)),
    (110, (255, 60, 0)),
    (180, (255, 170, 20)),
    (235, (255, 255, 160)),
]


def _fire_color(v: float) -> Tuple[int, int, int]:
    """Heat 0..255 -> fire palette (black -> red -> orange -> white-yellow)."""
    v = max(0.0, min(255.0, float(v)))
    for i in range(len(_FIRE_RAMP) - 1):
        v0, c0 = _FIRE_RAMP[i]
        v1, c1 = _FIRE_RAMP[i + 1]
        if v0 <= v <= v1:
            t = (v - v0) / (v1 - v0)
            return (
                int(c0[0] + t * (c1[0] - c0[0])),
                int(c0[1] + t * (c1[1] - c0[1])),
                int(c0[2] + t * (c1[2] - c0[2])),
            )
    return _FIRE_RAMP[-1][1]


def _fire_step(heat: List[float], intensity: float, rng) -> List[float]:
    """
    One 1-D fire tick: sparks scale with *intensity*, heat spreads to the
    neighbours and decays (slower = hotter).  Returns the new heat array.
    """
    intensity = max(0.0, min(1.0, intensity))
    n = len(heat)
    for _ in range(int(2 + 12 * intensity)):
        pos = rng.randrange(n)
        heat[pos] = 255.0
        heat[(pos + 1) % n] = max(heat[(pos + 1) % n], 180.0)
    decay = 5.0 - 3.6 * intensity
    new = [0.0] * n
    for i in range(n):
        avg = (heat[i] * 2 + heat[(i - 1) % n] + heat[(i + 1) % n]
               + heat[(i - 2) % n] * 0.5) / 4.5
        new[i] = max(0.0, avg - decay)
    return new


def run_fire(config_path: str = _DEFAULT_CONFIG,
             run_once: bool = False) -> bool:
    """
    Thermal fire: the whole 84-LED chain burns; the hottest sensor (CPU/GPU)
    drives spark rate / decay.  At >= hot_at (or sweep peak) the word "HOT"
    flashes over the flames every ~1.5s.  NUVOTON_FIRE_SWEEP=1 runs a 40s
    calm -> inferno -> calm ramp for demos.
    """
    cfg = load_config(config_path)
    brightness = float(cfg.get("brightness", 1.0))
    fire_cfg = cfg.get("modes", {}).get("fire", {})
    t_min = float(fire_cfg.get("t_min", 45))
    t_max = float(fire_cfg.get("t_max", 90))
    hot_at = float(fire_cfg.get("hot_at", 85))
    sweep = os.environ.get("NUVOTON_FIRE_SWEEP") == "1"
    rng = random.Random()

    with NuvotonDevice() as dev:
        if not dev.device:
            logger.error("Device not found. Is the cooler connected? (TRCC must be CLOSED)")
            return False

        dev.send_init()
        logger.info(f"Fire daemon started (sweep={sweep})")

        signal.signal(signal.SIGINT,  _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

        heat = [0.0] * 84
        snap = None
        t_read = 0.0
        hot_next = 0.0
        hot_until = 0.0
        t_start = time.time()

        while _running:
            now = time.time()
            if snap is None or (now - t_read) > 0.5:
                snap = read_all()
                t_read = now

            temps = [v for v in (snap.cpu_temp, snap.gpu_temp)
                     if v is not None and math.isfinite(v)]
            t_hot = max(temps) if temps else None

            if sweep:
                ph = ((now - t_start) % 40.0) / 40.0
                intensity = 1.0 - abs(2 * ph - 1)
            elif t_hot is None:
                intensity = 0.15
            else:
                intensity = max(0.15, min(1.0, (t_hot - t_min) / (t_max - t_min)))

            heat = _fire_step(heat, intensity, rng)

            frame = DisplayFrame()
            for i, v in enumerate(heat):
                frame.put(i, _fire_color(v))

            hot_active = (sweep and intensity > 0.92) or (
                t_hot is not None and t_hot >= hot_at)
            if hot_active and now >= hot_next:
                hot_until = now + 0.5
                hot_next = now + 1.5
            if now < hot_until:
                show_word(frame, digit_blocks(LED_CPU_TEMP, 3), "HOT", (255, 40, 0))
                show_word(frame, digit_blocks(LED_GPU_TEMP, 3), "HOT", (255, 40, 0))

            if brightness != 1.0:
                body = bytes(min(255, int(c * brightness)) for c in frame.to_bytes())
            else:
                body = frame.to_bytes()
            send_body(dev, body)

            cpu_s = f"{snap.cpu_temp:.1f}" if snap.cpu_temp is not None else "None"
            gpu_s = f"{snap.gpu_temp:.1f}" if snap.gpu_temp is not None else "None"
            logger.debug(f"fire | cpu {cpu_s} gpu {gpu_s} | intensidade {intensity:.2f}")

            if run_once:
                break
            time.sleep(0.05)

        dev.set_off()
        logger.info("LEDs off, fire daemon stopped")
    return True


# ── Vibe mode (auto mood: display <-> Zzz) ─────────────────────────────────

def _zzz_body(phase: float) -> bytes:
    """'Zzz' + breathing free pixels; *phase* 0..1 = breath level."""
    frame = DisplayFrame()
    v = int(30 + 110 * phase)
    show_word(frame, digit_blocks(LED_CPU_TEMP, 3), "Zzz", (0, v, min(255, v + 60)))
    for led in ALL_FREE_PIXELS:
        frame.put(led, (0, int(15 + 90 * phase), int(50 + 140 * phase)))
    return frame.to_bytes()


def run_vibe(config_path: str = _DEFAULT_CONFIG,
             run_once: bool = False) -> bool:
    """
    Auto mood daemon: normal sensor display while the machine is busy; after
    *idle_samples* consecutive reads with CPU+GPU usage below *idle_usage*%,
    switch to "Zzz" (breathing blue).  Any load returns to the display.

    Env overrides for demos: NUVOTON_VIBE_IDLE (usage %), NUVOTON_VIBE_SECS
    (seconds of idle before Zzz; converted to samples).
    """
    cfg = load_config(config_path)
    interval = cfg.get("update_interval_s", 2)
    brightness = float(cfg.get("brightness", 1.0))
    vibe_cfg = cfg.get("modes", {}).get("vibe", {})
    idle_usage = float(os.environ.get("NUVOTON_VIBE_IDLE",
                                      vibe_cfg.get("idle_usage", 5)))
    if os.environ.get("NUVOTON_VIBE_SECS"):
        idle_samples = max(1, int(float(os.environ["NUVOTON_VIBE_SECS"]) / interval))
    else:
        idle_samples = int(vibe_cfg.get("idle_samples", 15))

    import psutil as _psutil
    _psutil.cpu_percent(interval=None)
    time.sleep(0.1)

    with NuvotonDevice() as dev:
        if not dev.device:
            logger.error("Device not found. Is the cooler connected? (TRCC must be CLOSED)")
            return False

        dev.send_init()
        logger.info(f"Vibe daemon started (idle < {idle_usage}% for {idle_samples} samples)")

        signal.signal(signal.SIGINT,  _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

        state = "display"
        counter = 0
        zzz_start = 0.0
        t_load_check = 0.0

        while _running:
            if state == "display":
                snap = read_all()
                cpu_t_col = _temp_color(snap.cpu_temp)
                cpu_u_col = _usage_color(snap.cpu_usage)
                gpu_t_col = _temp_color(snap.gpu_temp)
                gpu_u_col = _usage_color(snap.gpu_usage)
                if snap.cpu_temp is None:
                    cpu_t_col = cpu_u_col
                body = build_metrics_frame(
                    snap.cpu_temp  if snap.cpu_temp  is not None else 0,
                    snap.cpu_usage if snap.cpu_usage is not None else 0,
                    snap.gpu_temp  if snap.gpu_temp  is not None else 0,
                    snap.gpu_usage if snap.gpu_usage is not None else 0,
                    cpu_temp_color=cpu_t_col, cpu_usage_color=cpu_u_col,
                    gpu_temp_color=gpu_t_col, gpu_usage_color=gpu_u_col,
                )
                if brightness != 1.0:
                    body = bytes(min(255, int(c * brightness)) for c in body)
                send_body(dev, body)

                idle = ((snap.cpu_usage is None or snap.cpu_usage < idle_usage)
                        and (snap.gpu_usage is None or snap.gpu_usage < idle_usage))
                counter = counter + 1 if idle else 0
                if counter >= idle_samples:
                    state = "zzz"
                    zzz_start = time.time()
                    logger.info("vibe | ocioso -> Zzz")
                if run_once:
                    break
                time.sleep(interval)
            else:
                t = time.time() - zzz_start
                send_body(dev, _zzz_body(0.5 + 0.5 * math.sin(t * 2 * math.pi / 4.0)))
                now = time.time()
                if now - t_load_check >= 1.0:
                    t_load_check = now
                    snap = read_all()
                    busy = ((snap.cpu_usage is not None and snap.cpu_usage >= idle_usage)
                            or (snap.gpu_usage is not None and snap.gpu_usage >= idle_usage))
                    if busy:
                        state = "display"
                        counter = 0
                        logger.info("vibe | carga voltou -> display")
                if run_once:
                    break
                time.sleep(0.2)

        dev.set_off()
        logger.info("LEDs off, vibe daemon stopped")
    return True


# ── Daemon loop ────────────────────────────────────────────────────────────

_running = True


def _handle_signal(signum, _frame):
    global _running
    logger.info(f"Received signal {signum}, shutting down…")
    _running = False


def run(config_path: str = _DEFAULT_CONFIG,
        mode_override: Optional[str] = None,
        run_once: bool = False):
    """
    Main daemon loop.

    Args:
        config_path:   path to config.json
        mode_override: override the mode from config
        run_once:      send one update then exit (useful for testing)
    """
    cfg = load_config(config_path)
    mode = mode_override or cfg.get("mode", "cpu_temp")
    interval = cfg.get("update_interval_s", 2)
    brightness = float(cfg.get("brightness", 1.0))
    modes_cfg = cfg.get("modes", {})
    mode_cfg = modes_cfg.get(mode, {})

    logger.info(f"Starting daemon: mode={mode}, interval={interval}s, brightness={brightness}")

    # psutil needs a first call to seed the cpu_percent counter
    import psutil as _psutil
    _psutil.cpu_percent(interval=None)
    time.sleep(0.1)

    with NuvotonDevice() as dev:
        if not dev.device:
            logger.error("Device not found. Is the cooler connected? (TRCC must be CLOSED)")
            return False

        dev.send_init()
        logger.info("Device ready")

        # Warn once if cpu_temp mode is requested but temp is unavailable
        if mode == "cpu_temp":
            _test = read_all()
            if _test.cpu_temp is None:
                logger.warning(
                    "cpu_temp mode: temperature sensor unavailable "
                    "(run as Administrator for AMD Ryzen MSR/SMU access). "
                    "Falling back to cpu_usage as proxy — LEDs will still "
                    "change colour with CPU load."
                )

        signal.signal(signal.SIGINT,  _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

        while _running:
            try:
                snap = read_all()
                r, g, b = pick_color(mode, snap, mode_cfg, modes_cfg)
                r = int(r * brightness) & 0xFF
                g = int(g * brightness) & 0xFF
                b = int(b * brightness) & 0xFF

                dev.set_color(r, g, b)
                logger.info(
                    f"mode={mode} | "
                    f"cpu={snap.cpu_temp}°C {snap.cpu_usage:.1f}% | "
                    f"gpu={snap.gpu_temp}°C {snap.gpu_usage}% | "
                    f"LED rgb({r},{g},{b})"
                )
            except Exception as e:
                logger.error(f"update failed (continuing): {e!r}")

            if run_once:
                break
            time.sleep(interval)

        dev.set_off()
        logger.info("LEDs off, daemon stopped")
    return True


# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Nuvoton RGB daemon — maps hardware sensors to LED colours",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  cpu_temp  — blue (cool) -> green -> orange -> red (hot)  on CPU temperature
  gpu_temp  — same scale on GPU temperature
  cpu_usage — blue (idle) -> green -> orange -> red on CPU usage %
  gpu_usage — same scale on GPU busy %
  static    — fixed colour (set 'color' in config.json)
  off       — all LEDs off
  zones     — every zone lit solid in its own gradient colour
              (CPU temp, CPU usage, GPU temp, GPU usage);
              indicators reflect overall load
  display   — real numbers on the segment display (CPU/GPU temp + usage),
              each group coloured by its gradient
  fire      — thermal demoscene: fire on all 84 LEDs, intensity = hottest
              sensor; HOT flashes over the flames when overheating
  vibe      — auto mood: display while busy, "Zzz" + breathing when idle

Remember: TRCC.exe must be CLOSED; its timer overwrites our packets.
        """,
    )
    parser.add_argument(
        "--config", default=_DEFAULT_CONFIG, metavar="PATH",
        help=f"Path to config.json (default: {_DEFAULT_CONFIG})"
    )
    parser.add_argument(
        "--mode", default=None,
        choices=["cpu_temp", "gpu_temp", "cpu_usage", "gpu_usage", "static",
                 "off", "zones", "display", "fire", "vibe"],
        help="Override the mode from config.json"
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Send one update and exit (smoke-test)"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging"
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    mode = args.mode or load_config(args.config).get("mode", "cpu_temp")

    if mode == "zones":
        ok = run_zones(config_path=args.config, run_once=args.once)
    elif mode == "display":
        ok = run_display(config_path=args.config, run_once=args.once)
    elif mode == "fire":
        ok = run_fire(config_path=args.config, run_once=args.once)
    elif mode == "vibe":
        ok = run_vibe(config_path=args.config, run_once=args.once)
    else:
        ok = run(config_path=args.config, mode_override=mode, run_once=args.once)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

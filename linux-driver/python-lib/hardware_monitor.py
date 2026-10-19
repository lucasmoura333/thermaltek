#!/usr/bin/env python3
"""
Hardware Monitor — CPU & GPU sensor reader

Sensor sources:
  1. psutil — CPU usage 0-100% on all platforms (same signal as Windows
     "% Processor Time"; lightly smoothed in cpu_usage() to track the
     calmer Task Manager / HWiNFO presentation).
  2. LibreHardwareMonitor (Windows) — CPU/GPU temperatures, via pythonnet
     from lhm/pkg2/LibreHardwareMonitorLib.dll.  CPU temp (Tctl/Tdie)
     needs admin privileges (MSR access); without it the value reads 0.0.
  3. Linux sysfs — k10temp/zenpower/coretemp + amdgpu via /sys/class/hwmon
     and /sys/class/drm (discrete card preferred). No dependencies.
"""

import math
import os
import glob
import logging
from typing import Optional

import psutil

logger = logging.getLogger(__name__)

# Path to the extracted LibreHardwareMonitorLib.dll (relative to this file)
_THIS_DIR  = os.path.dirname(os.path.abspath(__file__))
_LHM_DIR   = os.path.join(_THIS_DIR, "lhm", "pkg2")
_LHM_DLL   = os.path.join(_LHM_DIR, "LibreHardwareMonitorLib.dll")

# Linux sysfs roots (overridable in tests; read-only in production)
HWMON_ROOT = "/sys/class/hwmon"
DRM_ROOT   = "/sys/class/drm"

# ── LibreHardwareMonitor via pythonnet ─────────────────────────────────────

_lhm_computer  = None   # LHM Computer instance, after first init
_lhm_available: Optional[bool] = None   # None = not yet tried


def _init_lhm():
    """Load LHM DLL and open the Computer object. Call once."""
    global _lhm_computer, _lhm_available
    if _lhm_available is not None:
        return
    if os.name != "nt":
        _lhm_available = False
        return
    if not os.path.exists(_LHM_DLL):
        logger.warning(f"LHM DLL not found at {_LHM_DLL}")
        _lhm_available = False
        return
    try:
        import sys as _sys
        if _LHM_DIR not in _sys.path:
            _sys.path.insert(0, _LHM_DIR)
        import clr
        clr.AddReference("LibreHardwareMonitorLib")
        from LibreHardwareMonitor.Hardware import Computer
        c = Computer()
        c.IsCpuEnabled = True
        c.IsGpuEnabled = True
        c.Open()
        _lhm_computer = c
        _lhm_available = True
        logger.info("LibreHardwareMonitor loaded OK")
    except Exception as e:
        logger.warning(f"LHM init failed: {e}")
        _lhm_available = False


def _sensor_value(s):
    """Sensor value as float; None stays None and non-finite (NaN/inf)
    readings are unavailable too."""
    if s.Value is None:
        return None
    v = float(s.Value)
    return None if not math.isfinite(v) else v


def _lhm_sensors():
    """
    Yield (hardware_label, sensor_name, sensor_type, value) for every sensor.
    hardware_label includes the HardwareType so keyword matching works for
    any vendor name (e.g. "AMD Ryzen…" → label contains "[Cpu]").
    Updates all hardware first.  NaN readings (ADL/PMLOG can emit them) are
    reported as None so callers never see NaN.
    """
    if not _lhm_computer:
        return
    for hw in _lhm_computer.Hardware:
        hw.Update()
        hw_label = f"{hw.Name} [{hw.HardwareType}]"
        for sub in hw.SubHardware:
            sub.Update()
            for s in sub.Sensors:
                yield hw_label, s.Name, str(s.SensorType), _sensor_value(s)
        for s in hw.Sensors:
            yield hw_label, s.Name, str(s.SensorType), _sensor_value(s)


def _lhm_find(hw_keyword: str, sensor_keywords: list, sensor_type: str) -> Optional[float]:
    """Return first sensor value matching hardware + sensor name hints + type.
    Returns None if not found or if sensor value is None (e.g. MSR access denied).
    """
    hw_kw  = hw_keyword.lower()
    s_kwds = [k.lower() for k in sensor_keywords]
    for hw_name, s_name, s_type, value in _lhm_sensors():
        if hw_kw not in hw_name.lower():
            continue
        if sensor_type.lower() not in s_type.lower():
            continue
        sn = s_name.lower()
        if any(k in sn for k in s_kwds):
            return value  # may be None if sensor exists but value unavailable
    return None


def list_all_sensors() -> list:
    """Return all available LHM sensors as a list of dicts. Useful for diagnostics."""
    _init_lhm()
    result = []
    for hw_name, s_name, s_type, value in _lhm_sensors():
        result.append({
            'hardware': hw_name,
            'sensor':   s_name,
            'type':     s_type,
            'value':    value,
        })
    return result


# ── Linux sysfs helpers (hwmon / DRM) ──────────────────────────────────────

def _read_sysfs(path: str) -> Optional[str]:
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def _glob_sorted(pattern: str) -> list:
    return sorted(glob.glob(pattern))


def _hwmon_temp_by_labels(hwmons: list, prefer_labels: list) -> Optional[float]:
    """
    Return the first temp*_input whose temp*_label matches, trying each
    preferred label in order.  sysfs reports millidegrees Celsius.
    """
    for want in prefer_labels:
        for hw in hwmons:
            for inp in _glob_sorted(os.path.join(hw, "temp*_input")):
                label = _read_sysfs(inp[:-len("_input")] + "_label") or ""
                if want.lower() not in label.lower():
                    continue
                raw = _read_sysfs(inp)
                if raw:
                    try:
                        return int(float(raw)) / 1000.0
                    except ValueError:
                        pass
    return None


def _hwmon_first_temp(hwmons: list) -> Optional[float]:
    """Fallback: first readable temp1_input of the given hwmon dirs."""
    for hw in hwmons:
        raw = _read_sysfs(os.path.join(hw, "temp1_input"))
        if raw:
            try:
                return int(float(raw)) / 1000.0
            except ValueError:
                pass
    return None


def _linux_cpu_temp() -> Optional[float]:
    """CPU temperature from k10temp/zenpower (AMD) or coretemp (Intel)."""
    hwmons = [
        p for p in _glob_sorted(os.path.join(HWMON_ROOT, "hwmon*"))
        if _read_sysfs(os.path.join(p, "name")) in
        ("k10temp", "zenpower", "coretemp", "cpu_thermal")
    ]
    # AMD Zen: Tdie/Tccd are the real die temps; Tctl carries an offset
    return _hwmon_temp_by_labels(
        hwmons, ["Tdie", "Tccd1", "Tccd", "Tctl", "Package id 0", "Core 0"]
    ) or _hwmon_first_temp(hwmons)


def _linux_drm_cards() -> list:
    """
    DRM cards with discrete GPUs first (boot_vga == 0), so a machine with an
    integrated + discrete GPU reports the discrete card.
    """
    cards = _glob_sorted(os.path.join(DRM_ROOT, "card[0-9]"))

    def is_boot_vga(card):
        return _read_sysfs(os.path.join(card, "device", "boot_vga")) == "1"

    return [c for c in cards if not is_boot_vga(c)] + \
           [c for c in cards if is_boot_vga(c)]


def _linux_gpu_temp() -> Optional[float]:
    """GPU temperature from the amdgpu hwmon (edge, else junction)."""
    for card in _linux_drm_cards():
        hwmons = _glob_sorted(os.path.join(card, "device", "hwmon", "hwmon*"))
        val = _hwmon_temp_by_labels(hwmons, ["edge", "junction"])
        if val is not None:
            return val
        val = _hwmon_first_temp(hwmons)
        if val is not None:
            return val
    return None


def _linux_gpu_usage() -> Optional[float]:
    """GPU busy % from DRM (amdgpu gpu_busy_percent), discrete card first."""
    for card in _linux_drm_cards():
        raw = _read_sysfs(os.path.join(card, "device", "gpu_busy_percent"))
        if raw is None:
            continue
        try:
            return float(raw)
        except ValueError:
            continue
    return None


# ── Public sensor functions ────────────────────────────────────────────────

def cpu_temperature() -> Optional[float]:
    """Return CPU temperature in °C (LHM on Windows, sysfs on Linux)."""
    _init_lhm()
    if _lhm_available:
        # Try progressively broader keywords to support Intel and AMD Ryzen
        for keywords in (
            ["tctl/tdie", "tctl", "tdie"],          # AMD Ryzen (LHM names)
            ["package", "cpu package"],               # Intel
            ["die (average)", "ccd"],                 # AMD multi-chiplet
            ["core max", "core average"],             # fallback aggregate
            ["core #0", "cpu core"],                  # first core as last resort
        ):
            val = _lhm_find("cpu", keywords, "Temperature")
            if val is not None:
                return val if val > 0.0 else None  # 0.0 = MSR access denied
    if os.name != "nt":
        val = _linux_cpu_temp()
        if val is not None:
            return val
        try:
            temps = psutil.sensors_temperatures()
            for key in ("k10temp", "coretemp", "zenpower", "acpitz"):
                if key in temps and temps[key]:
                    return temps[key][0].current
        except AttributeError:
            pass
    return None


_cpu_usage_ema: Optional[float] = None   # smoothing state (see cpu_usage)


def cpu_usage() -> float:
    """Return CPU usage 0-100% (psutil; same signal as "% Processor Time").

    Lightly smoothed with an EMA so the display/log don't flicker with
    instantaneous 2s spikes — tracks the Task Manager / HWiNFO cadence.
    """
    global _cpu_usage_ema
    raw = psutil.cpu_percent(interval=None)
    if _cpu_usage_ema is None:
        _cpu_usage_ema = raw
    else:
        _cpu_usage_ema = 0.5 * _cpu_usage_ema + 0.5 * raw
    return _cpu_usage_ema


def gpu_temperature() -> Optional[float]:
    """Return GPU temperature in °C."""
    _init_lhm()
    if _lhm_available:
        val = _lhm_find("gpu", ["thermal diode", "gpu core", "core"], "Temperature")
        return val if val else None
    if os.name != "nt":
        return _linux_gpu_temp()
    return None


_gpu_usage_ema: Optional[float] = None   # smoothing state (see gpu_usage)


def gpu_usage() -> Optional[float]:
    """Return GPU usage 0-100%.
    Prefers 'D3D 3D' (the main rendering engine load) over generic 'GPU Core'.
    Lightly smoothed with an EMA (like cpu_usage) so the display doesn't
    flicker with instantaneous engine spikes (0 <-> 30% on an idle desktop).
    """
    global _gpu_usage_ema
    raw: Optional[float] = None
    _init_lhm()
    if _lhm_available:
        # D3D 3D is the most accurate gaming/compute metric for AMD
        for keywords in (["d3d 3d"], ["gpu core", "core"]):
            val = _lhm_find("gpu", keywords, "Load")
            if val is not None:
                raw = val
                break
    elif os.name != "nt":
        raw = _linux_gpu_usage()
    if raw is None or not math.isfinite(raw):
        return None
    if _gpu_usage_ema is None:
        _gpu_usage_ema = raw
    else:
        _gpu_usage_ema = 0.5 * _gpu_usage_ema + 0.5 * raw
    return _gpu_usage_ema


# ── Public snapshot ────────────────────────────────────────────────────────

class HardwareSnapshot:
    """One reading of all available sensor values."""
    __slots__ = ("cpu_temp", "cpu_usage", "gpu_temp", "gpu_usage")

    def __init__(self,
                 cpu_temp: Optional[float],
                 cpu_usage: float,
                 gpu_temp: Optional[float],
                 gpu_usage: Optional[float]):
        self.cpu_temp  = cpu_temp
        self.cpu_usage = cpu_usage
        self.gpu_temp  = gpu_temp
        self.gpu_usage = gpu_usage

    def __repr__(self):
        return (
            f"HardwareSnapshot("
            f"cpu_temp={self.cpu_temp}°C, "
            f"cpu_usage={self.cpu_usage:.1f}%, "
            f"gpu_temp={self.gpu_temp}°C, "
            f"gpu_usage={self.gpu_usage}%)"
        )


def read_all() -> HardwareSnapshot:
    """Read all sensors and return a HardwareSnapshot."""
    snap = HardwareSnapshot(
        cpu_temp=cpu_temperature(),
        cpu_usage=cpu_usage(),
        gpu_temp=gpu_temperature(),
        gpu_usage=gpu_usage(),
    )
    logger.debug(snap)
    return snap


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    print(read_all())

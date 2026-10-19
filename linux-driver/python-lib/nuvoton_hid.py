#!/usr/bin/env python3
"""
Nuvoton HID Communication Library

Low-level HID communication for Nuvoton 0416:8001 RGB controller.

Protocol confirmed via .NET IL decompilation of TRCC.exe (SendHidVal / ThreadSendDeviceData1):

  LED packet layout (sent in 64-byte chunks, Report ID 0x00 prepended):
    Header (20 bytes):
      DA DB DC DD          magic
      00 00 00 00          bytes 4-7
      00 00 00 00          bytes 8-11
      02 00 00 00          bytes 12-15  (packet type = LED data)
      <len_lo> <len_hi>    bytes 16-17  (length of RGB data that follows)
      00 00                bytes 18-19
    RGB data (N_LEDS * 3 bytes):
      R G B R G B ...      one triplet per LED, sequential

  PA120 DIGITAL: 84 LEDs → 252 bytes RGB → header[16:18] = FC 00

  Physical layout — the "LCD" is a 7-segment LED display, not a pixel LCD
  ───────────────────────────────────────────────────────────────────────
  Validated digit-by-digit against a live TRCC capture (51/51 frames — see
  lcd_sender.py) and confirmed visually on the hardware:
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

  Init packet (sent once on connect):
    DA DB DC DD 00 00 00 00 00 00 00 00 01 00 00 00 00 00 00 00

  Query packet:
    DA DB DC DD 02 00
  Query response (always the same, device is write-only for LED state):
    DA DB DC DD 10 10 10 10 00 00 00 00 01 00 00 00 [zeros]

  Transport backends (identical 65-byte report framing on both):
    hidapi — the `hid` binding (pip `hidapi`); used on Windows, optional
             on Linux.
    hidraw — pure-stdlib /dev/hidraw* transport for Linux: enumeration via
             /sys/class/hidraw, I/O via os.read/os.write, no libhidapi
             needed.  Force one with NUVOTON_BACKEND=hidapi|hidraw
             (default: auto — hidraw first on Linux, hidapi otherwise).
"""

import logging
import os
from typing import List, Optional, Tuple

try:
    import hid as _hidapi          # hidapi binding (Windows; optional on Linux)
except ImportError:                # Linux port uses the pure hidraw backend
    _hidapi = None

# Device identification
VENDOR_ID  = 0x0416
PRODUCT_ID = 0x8001

# HID report geometry
REPORT_SIZE = 64    # data bytes per write (without Report ID)
REPORT_ID   = 0x00

# LED count per device model
N_LEDS_PA120 = 84   # Thermalright PA120 DIGITAL

# Display layout — LED index groups (PA120 DIGITAL, 84 LEDs).
# The "LCD" is a chain of 7-segment digits; each digit block is 7 consecutive
# LEDs ordered F, A, B, G, E, D, C.  Validated against a live TRCC capture;
# each group is listed in display order (left to right on the CU).
LED_CPU_IND     = [0, 1]
LED_CPU_TEMP    = list(range(2, 23))        # 3 digits x 7
LED_CPU_CELSIUS = [23]
LED_CPU_FAHR    = [24]
LED_CPU_USAGE   = list(range(25, 41))       # 2 blanks + 2 digits x 7
LED_CPU_PERCENT = [41]
LED_GPU_PERCENT = [42]
LED_GPU_USAGE   = list(range(58, 42, -1))   # 2 blanks + 2 digits (mirrored)
LED_GPU_CELSIUS = [59]
LED_GPU_FAHR    = [60]
LED_GPU_TEMP    = list(range(81, 60, -1))   # 3 digits x 7 (mirrored)
LED_GPU_IND     = [82, 83]

# Packet type byte at offset 12
PKT_TYPE_INIT = 0x01
PKT_TYPE_LED  = 0x02

MAGIC_HEADER = bytes([0xDA, 0xDB, 0xDC, 0xDD])

# hidraw backend (Linux, no hidapi) — sysfs enumeration root
HIDRAW_SYSFS = "/sys/class/hidraw"
_HIDRAW_DEV_DIR = "/dev"
_HID_ID = f"0003:{VENDOR_ID:08X}:{PRODUCT_ID:08X}"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ── Transports ─────────────────────────────────────────────────────────────
#
# Both transports expose the same minimal surface used by NuvotonDevice:
#   .write(buffer65)  — 65 bytes: Report ID 0x00 + 64 data bytes
#   .read(size)       — non-blocking-ish read, b"" when nothing available
#   .close()
# Keeping the same 65-byte framing is what makes them interchangeable.

class _HidapiTransport:
    """Transport via the `hid` binding — the original (Windows) path."""

    backend = "hidapi"

    def __init__(self, dev, product: Optional[str]):
        self._dev = dev
        self.product = product or "Nuvoton HID Transfer"

    @classmethod
    def open(cls):
        if _hidapi is None:
            raise RuntimeError("hidapi (pip `hidapi`) not installed")
        dev = _hidapi.device()
        dev.open(VENDOR_ID, PRODUCT_ID)
        dev.set_nonblocking(1)
        try:
            product = dev.get_product_string()
        except Exception:
            product = None
        return cls(dev, product)

    def write(self, data: bytes):
        self._dev.write(bytes(data))

    def read(self, size: int = REPORT_SIZE) -> bytes:
        data = self._dev.read(size)
        return bytes(data) if data else b""

    def close(self):
        self._dev.close()


class _HidrawTransport:
    """Transport via /dev/hidraw* — pure stdlib, Linux."""

    backend = "hidraw"

    def __init__(self, fd: int, path: str, product: Optional[str] = None):
        self._fd = fd
        self.path = path
        self.product = product or "Nuvoton HID Transfer"

    @classmethod
    def open(cls, path: Optional[str] = None):
        if path is None:
            found = _list_hidraw_paths()
            if not found:
                raise FileNotFoundError(
                    f"no {HIDRAW_SYSFS}/hidraw* for "
                    f"{VENDOR_ID:04X}:{PRODUCT_ID:04X}"
                )
            path = found[0]["path"]
            product = found[0]["product"]
        else:
            product = None
        fd = os.open(path, os.O_RDWR)
        return cls(fd, path, product)

    def write(self, data: bytes):
        os.write(self._fd, bytes(data))

    def read(self, size: int = REPORT_SIZE, timeout_ms: int = 25) -> bytes:
        import select
        r, _, _ = select.select([self._fd], [], [], timeout_ms / 1000.0)
        if not r:
            return b""
        try:
            return os.read(self._fd, size)
        except OSError:
            return b""

    def close(self):
        try:
            os.close(self._fd)
        except OSError:
            pass


def _list_hidraw_paths() -> List[dict]:
    """
    Scan /sys/class/hidraw for VID 0x0416 / PID 0x8001 and return one dict
    per match (patch HIDRAW_SYSFS in tests).  Works without hidapi.
    """
    try:
        names = sorted(os.listdir(HIDRAW_SYSFS))
    except OSError:
        return []
    results = []
    for name in names:
        if not name.startswith("hidraw"):
            continue
        uevent_path = os.path.join(HIDRAW_SYSFS, name, "device", "uevent")
        try:
            with open(uevent_path) as f:
                props = dict(
                    line.strip().split("=", 1) for line in f if "=" in line
                )
        except OSError:
            continue
        if props.get("HID_ID", "").upper() != _HID_ID:
            continue
        results.append({
            "path":         f"{_HIDRAW_DEV_DIR}/{name}",
            "vendor_id":    VENDOR_ID,
            "product_id":   PRODUCT_ID,
            "manufacturer": None,
            "product":      props.get("HID_NAME"),
            "serial":       None,
        })
    return results


def _backend_order() -> List[str]:
    """
    Backend preference: NUVOTON_BACKEND=hidapi|hidraw forces one; auto =
    hidraw first on Linux (pure stdlib), hidapi otherwise.
    """
    pref = os.environ.get("NUVOTON_BACKEND", "auto").strip().lower()
    if pref in ("hidraw", "hidapi"):
        return [pref]
    if os.name != "nt":
        return ["hidraw", "hidapi"]
    return ["hidapi"]


class NuvotonDevice:
    """Nuvoton HID RGB controller (VID 0x0416, PID 0x8001)."""

    def __init__(self, n_leds: int = N_LEDS_PA120):
        self.device = None        # transport (hidapi or hidraw); truthy if open
        self.n_leds = n_leds

    # ── Connection ─────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """
        Open the HID device using the preferred backend
        (see _backend_order / NUVOTON_BACKEND).  Returns True on success.
        """
        errors = []
        for backend in _backend_order():
            try:
                if backend == "hidraw":
                    self.device = _HidrawTransport.open()
                else:
                    self.device = _HidapiTransport.open()
                logger.info(
                    f"Connected [{self.device.backend}]: {self.device.product}"
                )
                return True
            except Exception as e:
                errors.append(f"{backend}: {e}")
        logger.error("Connect failed — " + "; ".join(errors))
        return False

    def disconnect(self):
        """Close the HID device."""
        if self.device:
            self.device.close()
            self.device = None
            logger.info("Disconnected")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.disconnect()

    # ── Low-level I/O ──────────────────────────────────────────────────────

    def _send_chunk(self, chunk64: bytes):
        """Write exactly one 65-byte HID output report (Report ID + 64 bytes)."""
        assert len(chunk64) == REPORT_SIZE
        self.device.write(bytes([REPORT_ID]) + chunk64)

    def _send_data(self, data: bytes):
        """
        Split *data* into 64-byte chunks and write each as a HID report.
        Last chunk is zero-padded to 64 bytes.
        """
        offset = 0
        while offset < len(data):
            chunk = data[offset:offset + REPORT_SIZE]
            if len(chunk) < REPORT_SIZE:
                chunk = chunk + bytes(REPORT_SIZE - len(chunk))
            self._send_chunk(chunk)
            offset += REPORT_SIZE

    def _read_response(self, timeout_ms: int = 100) -> Optional[bytes]:
        """Read one HID input report. Returns None if no data within timeout."""
        if not self.device:
            return None
        import time
        deadline = time.monotonic() + timeout_ms / 1000.0
        while time.monotonic() < deadline:
            data = self.device.read(REPORT_SIZE)
            if data:
                return bytes(data)
            time.sleep(0.005)
        return None

    # ── Packet builders ────────────────────────────────────────────────────

    @staticmethod
    def _make_led_packet(rgb_data: bytes) -> bytes:
        """
        Build the full LED data packet: 20-byte header + RGB data.
        rgb_data must be N_LEDS * 3 bytes (R, G, B per LED).
        """
        length = len(rgb_data)
        header = bytes([
            0xDA, 0xDB, 0xDC, 0xDD,           # magic
            0x00, 0x00, 0x00, 0x00,            # bytes 4-7
            0x00, 0x00, 0x00, 0x00,            # bytes 8-11
            PKT_TYPE_LED, 0x00, 0x00, 0x00,    # bytes 12-15
            length & 0xFF, (length >> 8) & 0xFF, 0x00, 0x00,  # bytes 16-19
        ])
        return header + rgb_data

    @staticmethod
    def _make_init_packet() -> bytes:
        """Build the 20-byte DeviceOnConnected1 init packet."""
        return bytes([
            0xDA, 0xDB, 0xDC, 0xDD,
            0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00,
            PKT_TYPE_INIT, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00,
        ])

    # ── Public API ─────────────────────────────────────────────────────────

    def send_init(self) -> bool:
        """Send the device init/handshake packet. Optional but matches TRCC startup."""
        if not self.device:
            return False
        try:
            self._send_data(self._make_init_packet())
            return True
        except Exception as e:
            logger.error(f"send_init failed: {e}")
            return False

    def set_color(self, r: int, g: int, b: int,
                  brightness: float = 1.0, repeats: int = 5) -> bool:
        """
        Set all LEDs to a solid colour.

        Args:
            r, g, b:    0-255 colour values.
            brightness: 0.0-1.0 multiplier (TRCC uses 0.4 internally).
            repeats:    how many times to send the packet (TRCC uses a timer
                        that fires continuously – sending a few times is enough
                        when TRCC is closed).
        """
        if not self.device:
            logger.error("Not connected")
            return False
        r = int(r * brightness) & 0xFF
        g = int(g * brightness) & 0xFF
        b = int(b * brightness) & 0xFF
        rgb_data = bytes([r, g, b] * self.n_leds)
        packet = self._make_led_packet(rgb_data)
        try:
            for _ in range(repeats):
                self._send_data(packet)
            logger.info(f"set_color(r={r}, g={g}, b={b}, brightness={brightness})")
            return True
        except Exception as e:
            logger.error(f"set_color failed: {e}")
            return False

    def set_off(self, repeats: int = 5) -> bool:
        """Turn all LEDs off."""
        return self.set_color(0, 0, 0, repeats=repeats)

    def set_per_led(self, colors: List[Tuple[int, int, int]],
                    brightness: float = 1.0, repeats: int = 5) -> bool:
        """
        Set each physical LED independently.

        Args:
            colors:     list of (r, g, b) tuples, one per physical LED position
                        (length must equal self.n_leds = 84 for PA120 DIGITAL).
            brightness: 0.0-1.0 multiplier applied to all channels.
            repeats:    number of packet sends for reliability.
        """
        if not self.device:
            logger.error("Not connected")
            return False
        if len(colors) != self.n_leds:
            raise ValueError(f"Expected {self.n_leds} colors, got {len(colors)}")
        buf = bytearray(self.n_leds * 3)
        for i, (r, g, b) in enumerate(colors):
            buf[i * 3]     = int(r * brightness) & 0xFF
            buf[i * 3 + 1] = int(g * brightness) & 0xFF
            buf[i * 3 + 2] = int(b * brightness) & 0xFF
        packet = self._make_led_packet(bytes(buf))
        try:
            for _ in range(repeats):
                self._send_data(packet)
            return True
        except Exception as e:
            logger.error(f"set_per_led failed: {e}")
            return False

    def set_zones_color(
        self,
        cpu_temp:  Tuple[int, int, int] = (0, 0, 0),
        cpu_usage: Tuple[int, int, int] = (0, 0, 0),
        gpu_temp:  Tuple[int, int, int] = (0, 0, 0),
        gpu_usage: Tuple[int, int, int] = (0, 0, 0),
        ring_color: Optional[Tuple[int, int, int]] = None,
        brightness: float = 1.0,
        repeats: int = 5,
    ) -> bool:
        """
        Light each display zone solid in its own colour (zone preview).

        The 84 LEDs are a 7-segment display, not an RGB ring (validated
        against a live TRCC capture — see the module docstring).  Each zone
        colour fills every segment of its digits plus the matching unit LED:

          cpu_temp   → CPU temp digits (2-22) + °C (23)
          cpu_usage  → CPU usage digits (25-40) + % (41)
          gpu_temp   → GPU temp digits (61-81) + °C (59)
          gpu_usage  → GPU usage digits (43-58) + % (42)
          ring_color → CPU/GPU indicator LEDs (0, 1 and 82, 83)

        For real digits driven by sensor values use
        lcd_sender.build_metrics_frame() instead.

        Args:
            cpu_temp:   (R, G, B) for the CPU temperature zone.
            cpu_usage:  (R, G, B) for the CPU usage zone.
            gpu_temp:   (R, G, B) for the GPU temperature zone.
            gpu_usage:  (R, G, B) for the GPU usage zone.
            ring_color: (R, G, B) for the indicator LEDs; None = off.
            brightness: 0.0-1.0 multiplier.
            repeats:    number of sends.
        """
        colors: List[Tuple[int, int, int]] = [(0, 0, 0)] * self.n_leds
        for led in LED_CPU_TEMP + LED_CPU_CELSIUS:
            colors[led] = cpu_temp
        for led in LED_CPU_USAGE + LED_CPU_PERCENT:
            colors[led] = cpu_usage
        for led in LED_GPU_TEMP + LED_GPU_CELSIUS:
            colors[led] = gpu_temp
        for led in LED_GPU_USAGE + LED_GPU_PERCENT:
            colors[led] = gpu_usage
        if ring_color is not None:
            for led in LED_CPU_IND + LED_GPU_IND:
                colors[led] = ring_color
        return self.set_per_led(colors, brightness=brightness, repeats=repeats)

    def set_colors(self, colors: List[Tuple[int, int, int]],
                   brightness: float = 1.0, repeats: int = 5) -> bool:
        """
        Set each LED individually.

        Args:
            colors: list of (r, g, b) tuples, one per LED.
                    If shorter than n_leds the last colour is repeated.
            brightness: 0.0-1.0 multiplier.
            repeats: send count.
        """
        if not self.device:
            logger.error("Not connected")
            return False
        rgb_list = []
        for i in range(self.n_leds):
            r, g, b = colors[min(i, len(colors) - 1)]
            rgb_list += [int(r * brightness) & 0xFF,
                         int(g * brightness) & 0xFF,
                         int(b * brightness) & 0xFF]
        rgb_data = bytes(rgb_list)
        packet = self._make_led_packet(rgb_data)
        try:
            for _ in range(repeats):
                self._send_data(packet)
            return True
        except Exception as e:
            logger.error(f"set_colors failed: {e}")
            return False

    def query_status(self) -> Optional[bytes]:
        """
        Send a GET_STATE query and return the raw response bytes.
        Note: device always returns the same fixed response regardless of
        current LED state – it is write-only for LED settings.
        """
        if not self.device:
            return None
        try:
            query = bytes([0xDA, 0xDB, 0xDC, 0xDD, 0x02, 0x00])
            self._send_data(query + bytes(REPORT_SIZE - len(query)))
            resp = self._read_response(200)
            if resp:
                logger.info(f"Status: {resp[:16].hex(' ')}")
            return resp
        except Exception as e:
            logger.error(f"query_status failed: {e}")
            return None

    # legacy aliases so old callers don't break
    def write_report(self, data: bytes) -> bool:
        if not self.device:
            return False
        try:
            self._send_data(data)
            return True
        except Exception:
            return False

    def read_report(self, timeout_ms: int = 100) -> Optional[bytes]:
        return self._read_response(timeout_ms)


# ── Module-level helpers ───────────────────────────────────────────────────

def list_devices() -> List[dict]:
    """Return info dicts for every detected Nuvoton RGB device."""
    if os.name != "nt":
        found = _list_hidraw_paths()          # pure-stdlib Linux path
        if found:
            return found
    if _hidapi is None:
        return []
    return [
        {
            'path':         d['path'],
            'vendor_id':    d['vendor_id'],
            'product_id':   d['product_id'],
            'manufacturer': d['manufacturer_string'],
            'product':      d['product_string'],
            'serial':       d['serial_number'],
        }
        for d in _hidapi.enumerate(VENDOR_ID, PRODUCT_ID)
    ]


def test_connection() -> bool:
    """Quick smoke-test: connect, blink red, turn off, disconnect."""
    import time
    with NuvotonDevice() as dev:
        if not dev.device:
            print("Device not found!")
            return False
        print("Connected. Sending RED...")
        dev.set_color(255, 0, 0)
        time.sleep(2)
        print("OFF")
        dev.set_off()
    print("Test passed.")
    return True


if __name__ == '__main__':
    test_connection()

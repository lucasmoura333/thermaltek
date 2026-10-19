#!/usr/bin/env python3
"""
Offline tests for the Linux port — no hardware, no device, no hidapi needed.

Covers:
  1. hidraw enumeration — _list_hidraw_paths() parses a fake /sys/class/hidraw
     tree and matches VID 0416 / PID 8001 (decoys filtered out).
  2. Backend selection — _backend_order() honours NUVOTON_BACKEND and picks
     hidraw first on Linux, hidapi on Windows.
  3. Report framing — a recording transport captures every write from
     NuvotonDevice: 65 bytes per report, Report ID 0 prefix, 64-byte chunks
     zero-padded; byte-identical for all 51 captured TRCC frames.
  4. Linux sensor logic — _linux_cpu_temp / _linux_gpu_* against fake
     hwmon/DRM trees (Tdie preference, discrete-GPU preference, junction).
  5. (Linux only) _HidrawTransport write/read over real fds via os.pipe,
     including the select() read-timeout path.

Run:  python test_hidraw_offline.py     (Windows or Linux, device not required)
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import nuvoton_hid as nh
import lcd_sender as ls
import hardware_monitor as hm

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    mark = "ok  " if cond else "FAIL"
    print(f"  {mark} {name}" + (f"  ({detail})" if (detail and not cond) else ""))


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


# ── 1. hidraw enumeration (fake sysfs) ──────────────────────────────────────

def test_hidraw_enumeration():
    print("1. hidraw enumeration (fake /sys/class/hidraw):")
    root = tempfile.mkdtemp(prefix="hidraw-fake-")

    def uevent(hidraw, hid_id, name):
        _write(os.path.join(root, hidraw, "device", "uevent"),
               f"DRIVER=hid-generic\nHID_ID={hid_id}\nHID_NAME={name}\n")

    uevent("hidraw8", "0003:00000416:00008001", "Nuvoton HID Transfer")
    uevent("hidraw3", "0003:0000046D:0000B012", "Some Keyboard")
    uevent("hidraw9", "0003:00000416:00008000", "Nuvoton sibling PID")

    old = nh.HIDRAW_SYSFS
    nh.HIDRAW_SYSFS = root
    try:
        found = nh._list_hidraw_paths()
    finally:
        nh.HIDRAW_SYSFS = old

    check("exactly 1 match (decoys filtered)", len(found) == 1, f"got {len(found)}")
    if found:
        e = found[0]
        check("path is /dev/<hidrawN>", e["path"] == "/dev/hidraw8", e["path"])
        check("product from HID_NAME", e["product"] == "Nuvoton HID Transfer",
              str(e["product"]))
        check("vid/pid", (e["vendor_id"], e["product_id"]) == (0x0416, 0x8001))


# ── 2. Backend selection ────────────────────────────────────────────────────

def test_backend_order():
    print("2. backend selection (NUVOTON_BACKEND):")
    old = os.environ.pop("NUVOTON_BACKEND", None)
    try:
        order = nh._backend_order()
        if os.name == "nt":
            check("auto on Windows -> hidapi only", order == ["hidapi"], str(order))
        else:
            check("auto on Linux -> hidraw first",
                  order == ["hidraw", "hidapi"], str(order))
        os.environ["NUVOTON_BACKEND"] = "hidraw"
        check("forced hidraw", nh._backend_order() == ["hidraw"])
        os.environ["NUVOTON_BACKEND"] = "hidapi"
        check("forced hidapi", nh._backend_order() == ["hidapi"])
    finally:
        os.environ.pop("NUVOTON_BACKEND", None)
        if old is not None:
            os.environ["NUVOTON_BACKEND"] = old


# ── 3. Report framing (recording transport) ─────────────────────────────────

class RecordingTransport:
    """Mimics the transport surface; captures writes instead of syscalls."""

    backend = "recording"
    product = "test-recorder"

    def __init__(self):
        self.writes = []

    def write(self, data):
        self.writes.append(bytes(data))

    def read(self, size=64, timeout_ms=0):
        return b""

    def close(self):
        pass


def test_report_framing():
    print("3. report framing (65-byte reports, Report ID 0):")
    dev = nh.NuvotonDevice()
    dev.device = RecordingTransport()

    cap = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "trcc_capture_frames.bin")
    data = open(cap, "rb").read()
    n = len(data) // 320
    check("capture present with 51 frames", n == 51, f"got {n}")

    bad = None
    for i in range(n):
        dev.device.writes.clear()
        ls.send_raw_frame(dev, data[i * 320:(i + 1) * 320])
        w = dev.device.writes
        if len(w) != 5 or any(len(r) != 65 or r[0] != 0x00 for r in w):
            bad = f"frame {i}: {[len(r) for r in w]}"
            break
        if b"".join(r[1:] for r in w) != data[i * 320:(i + 1) * 320]:
            bad = f"frame {i}: payload mismatch"
            break
    check("51 captured frames -> 5x65 B, byte-identical", bad is None, bad or "")

    dev.device.writes.clear()
    body = ls.build_metrics_frame(42, 56, 47, 21)
    ls.send_body(dev, body)
    w = dev.device.writes
    check("metrics frame -> 5 reports of 65 B",
          len(w) == 5 and all(len(r) == 65 and r[0] == 0 for r in w),
          str([len(r) for r in w]))
    packet = b"".join(r[1:] for r in w)
    expected = nh.NuvotonDevice._make_led_packet(body) + bytes(48)
    check("packet == 20 B header + 252 B RGB + pad(48)", packet == expected)


# ── 4. Linux sensor logic (fake hwmon/DRM trees) ────────────────────────────

def test_linux_sensors():
    print("4. Linux sensor logic (fake hwmon/DRM):")
    old_hwmon, old_drm = hm.HWMON_ROOT, hm.DRM_ROOT

    # CPU: k10temp with Tctl (temp1) and Tdie (temp3) -> Tdie wins
    cpu_root = tempfile.mkdtemp(prefix="hwmon-cpu-")
    _write(os.path.join(cpu_root, "hwmon0", "name"), "k10temp")
    _write(os.path.join(cpu_root, "hwmon0", "temp1_input"), "45000")
    _write(os.path.join(cpu_root, "hwmon0", "temp1_label"), "Tctl")
    _write(os.path.join(cpu_root, "hwmon0", "temp3_input"), "41200")
    _write(os.path.join(cpu_root, "hwmon0", "temp3_label"), "Tdie")
    _write(os.path.join(cpu_root, "hwmon1", "name"), "coretemp")
    _write(os.path.join(cpu_root, "hwmon1", "temp1_input"), "60000")
    _write(os.path.join(cpu_root, "hwmon1", "temp1_label"), "Package id 0")

    # CPU fallback: labels absent -> temp1_input
    cpu_root2 = tempfile.mkdtemp(prefix="hwmon-cpu2-")
    _write(os.path.join(cpu_root2, "hwmon0", "name"), "k10temp")
    _write(os.path.join(cpu_root2, "hwmon0", "temp1_input"), "55000")

    # GPU: card0 = iGPU (boot_vga=1), card1 = dGPU (boot_vga=0) -> card1 wins
    drm_root = tempfile.mkdtemp(prefix="drm-")
    c0, c1 = os.path.join(drm_root, "card0"), os.path.join(drm_root, "card1")
    _write(os.path.join(c0, "device", "boot_vga"), "1")
    _write(os.path.join(c0, "device", "gpu_busy_percent"), "5")
    _write(os.path.join(c0, "device", "hwmon", "hwmon2", "temp1_input"), "38000")
    _write(os.path.join(c0, "device", "hwmon", "hwmon2", "temp1_label"), "edge")
    _write(os.path.join(c1, "device", "boot_vga"), "0")
    _write(os.path.join(c1, "device", "gpu_busy_percent"), "24")
    _write(os.path.join(c1, "device", "hwmon", "hwmon3", "temp1_input"), "47000")
    _write(os.path.join(c1, "device", "hwmon", "hwmon3", "temp1_label"), "edge")
    _write(os.path.join(c1, "device", "hwmon", "hwmon3", "temp2_input"), "52000")
    _write(os.path.join(c1, "device", "hwmon", "hwmon3", "temp2_label"), "junction")

    # GPU junction fallback: dGPU exposes only junction (no edge)
    drm_root2 = tempfile.mkdtemp(prefix="drm2-")
    d0 = os.path.join(drm_root2, "card0")
    _write(os.path.join(d0, "device", "boot_vga"), "0")
    _write(os.path.join(d0, "device", "hwmon", "hwmon5", "temp2_input"), "52000")
    _write(os.path.join(d0, "device", "hwmon", "hwmon5", "temp2_label"), "junction")

    try:
        hm.HWMON_ROOT = cpu_root
        check("CPU temp prefers Tdie (41.2, not Tctl 45.0)",
              hm._linux_cpu_temp() == 41.2, str(hm._linux_cpu_temp()))
        hm.HWMON_ROOT = cpu_root2
        check("CPU temp fallback to temp1_input (55.0)",
              hm._linux_cpu_temp() == 55.0, str(hm._linux_cpu_temp()))
        hm.DRM_ROOT = drm_root
        check("GPU temp from discrete card edge (47.0)",
              hm._linux_gpu_temp() == 47.0, str(hm._linux_gpu_temp()))
        check("GPU usage from discrete card (24.0)",
              hm._linux_gpu_usage() == 24.0, str(hm._linux_gpu_usage()))
        hm.DRM_ROOT = drm_root2
        check("GPU temp junction fallback (52.0)",
              hm._linux_gpu_temp() == 52.0, str(hm._linux_gpu_temp()))
    finally:
        hm.HWMON_ROOT, hm.DRM_ROOT = old_hwmon, old_drm


# ── 5. hidraw fd I/O (Linux only) ───────────────────────────────────────────

def test_hidraw_fd_io():
    print("5. hidraw fd I/O (real fds via os.pipe):")
    if not sys.platform.startswith("linux"):
        print("  skip  not Linux — run this file on the Linux machine for fd coverage")
        return

    r, w = os.pipe()
    tw = nh._HidrawTransport(w, "/dev/null", "write-end")
    payload = bytes([0x00]) + bytes(range(64))
    tw.write(payload)
    check("write() put the exact 65 bytes on the fd", os.read(r, 65) == payload)
    os.close(r); os.close(w)

    r2, w2 = os.pipe()
    tr = nh._HidrawTransport(r2, "/dev/null", "read-end")
    check("read() timeout -> b''", tr.read(64, timeout_ms=20) == b"")
    os.write(w2, b"\xDA\xDB\xDC\xDD\x10")
    check("read() returns the payload bytes",
          tr.read(64, timeout_ms=200) == b"\xDA\xDB\xDC\xDD\x10")
    os.close(r2); os.close(w2)


def main():
    test_hidraw_enumeration()
    test_backend_order()
    test_report_framing()
    test_linux_sensors()
    test_hidraw_fd_io()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()

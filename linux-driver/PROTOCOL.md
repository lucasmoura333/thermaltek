# Protocol -- Nuvoton 0416:8001 RGB Controller

Confirmed protocol via IL decompilation of TRCC.exe (.NET), 2026-04-11.
Validated experimentally with test_onoff.py.

---

## Device Specs

    Vendor ID:  0x0416 (Winbond/Nuvoton)
    Product ID: 0x8001
    Name:       HID Transfer
    Usage Page: 0xFF00 (vendor-defined)

## HID Geometry

    Report ID:   0x00
    Report size: 64 data bytes (65 bytes total including Report ID)

    dev.write([0x00] + 64_data_bytes)

---

## LED Packet (type 0x02)

20-byte header + N_LEDs*3 bytes of RGB data.
Chunked into 64-byte HID reports (last chunk zero-padded).

### Header layout

    Offset  Size  Value          Description
    ------  ----  -------------  ----------------------------------
    0       4     DA DB DC DD    Magic bytes (fixed)
    4       4     00 00 00 00    Reserved
    8       4     00 00 00 00    Reserved
    12      4     02 00 00 00    Packet type 0x02 = LED data
    16      2     <lo> <hi>      RGB data length, little-endian
    18      2     00 00          Reserved

### RGB data

    [R0][G0][B0]  [R1][G1][B1]  ...  [R83][G83][B83]

### Example -- PA120 DIGITAL (84 LEDs), all red

    Header: DA DB DC DD 00 00 00 00 00 00 00 00 02 00 00 00 FC 00 00 00
    Data:   FF 00 00  FF 00 00  ... x84  (252 bytes)
    Total:  272 bytes => 5 HID reports of 64 bytes each

---

## Init Packet (type 0x01)

Sent once on connect (TRCC DeviceOnConnected1).

    DA DB DC DD 00 00 00 00 00 00 00 00 01 00 00 00 00 00 00 00

Fits in a single 64-byte report.

---

## Device Query Response

The device returns a fixed response regardless of LED state (write-only for RGB):

    DA DB DC DD 10 10 10 10 00 00 00 00 01 00 00 00 ...

---

## Model Parameters

| Model          | N_LEDs | RGB bytes | len field |
|----------------|--------|-----------|-----------|
| PA120 DIGITAL  | 84     | 252       | FC 00     |

---

## TRCC Brightness Factor

TRCC multiplies RGB values by 0.4f before sending.
Raw values (brightness=1.0) produce brighter LEDs than TRCC default.
Use brightness=0.4 in NuvotonDevice.set_color() to match TRCC.

---

## Critical Rule

TRCC.exe must be CLOSED.

TRCC runs a System.Windows.Forms.Timer that calls SendHidVal() continuously.
With TRCC open, our writes are accepted but immediately overwritten by the timer.
With TRCC closed, we have full control.

---

## Reference Implementation

    def set_color(self, r, g, b, brightness=1.0, repeats=5):
        r = int(r * brightness) & 0xFF
        g = int(g * brightness) & 0xFF
        b = int(b * brightness) & 0xFF
        rgb_data = bytes([r, g, b] * self.n_leds)
        length = len(rgb_data)
        header = bytes([
            0xDA, 0xDB, 0xDC, 0xDD,
            0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00,
            0x02, 0x00, 0x00, 0x00,
            length & 0xFF, (length >> 8) & 0xFF, 0x00, 0x00,
        ])
        packet = header + rgb_data
        for _ in range(repeats):
            self._send_data(packet)  # chunks into 64-byte HID reports

---

## Files

| File                              | Description                           |
|-----------------------------------|---------------------------------------|
| python-lib/nuvoton_hid.py         | Core HID library (confirmed protocol) |
| python-lib/rgb_control.py         | RGB control CLI                       |
| python-lib/hardware_monitor.py    | CPU/GPU sensor reader (AMD)           |
| python-lib/nuvoton_daemon.py      | Daemon: sensors -> LED colour         |
| python-lib/config.json            | Threshold and mode configuration      |
| python-lib/test_onoff.py          | Validation test (reference)           |
| nuvoton-rgb.c                     | Linux kernel driver                   |

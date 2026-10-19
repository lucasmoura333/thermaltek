#!/usr/bin/env python3
"""
HID Report Descriptor Reader
==============================
Reads the HID Report Descriptor from the Nuvoton device (0x0416:0x8001).

The Report Descriptor tells us the device's "schema":
  - How many reports it supports
  - The exact size of each report
  - What data each field represents (Usage, Usage Page)
  - Logical min/max for values

This eliminates guessing about packet format.

Requirements:
    pip install hidapi   (Windows: pip install hid)
    OR
    pip install pywinusb   (Windows-only alternative)

Usage:
    python get_report_descriptor.py
"""

import sys
import struct
from pathlib import Path

VENDOR_ID  = 0x0416
PRODUCT_ID = 0x8001

# HID Usage Pages
USAGE_PAGES = {
    0x01: "Generic Desktop",
    0x02: "Simulation",
    0x06: "Generic Device",
    0x08: "LED",
    0x09: "Button",
    0x0B: "Telephony",
    0x0C: "Consumer",
    0x0D: "Digitizer",
    0xFF00: "Vendor-Defined (FF00)",
    0xFF01: "Vendor-Defined (FF01)",
    0xFF10: "Vendor-Defined (FF10)",
    0xFF60: "Vendor-Defined (FF60)",
    0xFFA0: "Vendor-Defined (FFA0)",
    0xFFB0: "Vendor-Defined (FFB0)",
    0xFFC0: "Vendor-Defined (FFC0)",
    0xFFD0: "Vendor-Defined (FFD0)",
    0xFFE0: "Vendor-Defined (FFE0)",
    0xFFF0: "Vendor-Defined (FFF0)",
}

ITEM_TAGS = {
    # Main items
    (0, 8):  "Input",
    (0, 9):  "Output",
    (0, 11): "Feature",
    (0, 10): "Collection",
    (0, 12): "End Collection",
    # Global items
    (1, 0):  "Usage Page",
    (1, 1):  "Logical Minimum",
    (1, 2):  "Logical Maximum",
    (1, 3):  "Physical Minimum",
    (1, 4):  "Physical Maximum",
    (1, 5):  "Unit Exponent",
    (1, 6):  "Unit",
    (1, 7):  "Report Size",
    (1, 8):  "Report ID",
    (1, 9):  "Report Count",
    (1, 10): "Push",
    (1, 11): "Pop",
    # Local items
    (2, 0):  "Usage",
    (2, 1):  "Usage Minimum",
    (2, 2):  "Usage Maximum",
    (2, 7):  "String Index",
    (2, 8):  "String Minimum",
    (2, 9):  "String Maximum",
}


def parse_descriptor(raw: bytes):
    """Parse and pretty-print a HID Report Descriptor."""
    print("\n=== HID Report Descriptor ===")
    print(f"Raw ({len(raw)} bytes): {raw.hex()}\n")
    print("Parsed items:")

    i = 0
    indent = 0
    while i < len(raw):
        b = raw[i]
        tag      = (b >> 4) & 0x0F
        item_type = (b >> 2) & 0x03
        size_code = b & 0x03
        size = [0, 1, 2, 4][size_code]

        value_bytes = raw[i+1 : i+1+size]
        if size == 0:
            value = 0
        elif size == 1:
            value = struct.unpack("<B", value_bytes)[0]
        elif size == 2:
            value = struct.unpack("<H", value_bytes)[0]
        else:
            value = struct.unpack("<I", value_bytes)[0]

        name = ITEM_TAGS.get((item_type, tag), f"Unknown({item_type},{tag})")

        if name == "End Collection":
            indent = max(0, indent - 2)

        prefix = "  " * (indent // 2)

        if name == "Usage Page":
            page_name = USAGE_PAGES.get(value, f"0x{value:04X}")
            print(f"  {prefix}{name}: {page_name}")
            if value >= 0xFF00:
                print(f"  {prefix}  *** VENDOR-DEFINED — protocol is proprietary ***")
        elif name in ("Logical Minimum", "Logical Maximum", "Physical Minimum", "Physical Maximum"):
            # Treat as signed
            if size == 1:
                value_s = struct.unpack("<b", value_bytes)[0]
            elif size == 2:
                value_s = struct.unpack("<h", value_bytes)[0]
            else:
                value_s = struct.unpack("<i", value_bytes)[0]
            print(f"  {prefix}{name}: {value_s}")
        elif name in ("Report Size", "Report Count", "Report ID"):
            print(f"  {prefix}{name}: {value} (0x{value:02X})")
        elif name in ("Input", "Output", "Feature"):
            flags = []
            if value & 0x01: flags.append("Constant")
            else: flags.append("Data")
            if value & 0x02: flags.append("Variable")
            else: flags.append("Array")
            if value & 0x04: flags.append("Relative")
            else: flags.append("Absolute")
            print(f"  {prefix}{name}: ({', '.join(flags)})  [0x{value:04X}]")
        elif name == "Collection":
            col_types = {0: "Physical", 1: "Application", 2: "Logical", 3: "Report",
                         4: "Named Array", 5: "Usage Switch", 6: "Usage Modifier"}
            print(f"  {prefix}{name}: {col_types.get(value, str(value))}")
            indent += 2
        else:
            print(f"  {prefix}{name}: 0x{value:0{size*2 or 2}X} ({value})")

        i += 1 + size

    print("\n=== Summary ===")


def get_descriptor_via_hid():
    """Try to read report descriptor using hidapi."""
    try:
        import hid
        d = hid.device()
        d.open(VENDOR_ID, PRODUCT_ID)

        # Get the raw report descriptor
        # hidapi doesn't expose this directly, but we can try
        try:
            desc = d.get_report_descriptor()
            d.close()
            return bytes(desc)
        except AttributeError:
            pass

        # Try reading device info
        print("[*] hidapi opened device but get_report_descriptor() not available")
        print(f"    Manufacturer : {d.get_manufacturer_string()}")
        print(f"    Product      : {d.get_product_string()}")
        d.close()
        return None
    except Exception as e:
        print(f"[!] hidapi approach failed: {e}")
        return None


def get_descriptor_via_pywinusb():
    """Read report descriptor using pywinusb (Windows-only)."""
    try:
        import pywinusb.hid as winusb

        filter_dev = winusb.HidDeviceFilter(vendor_id=VENDOR_ID, product_id=PRODUCT_ID)
        devices = filter_dev.get_devices()
        if not devices:
            print("[!] pywinusb: device not found")
            return None

        dev = devices[0]
        dev.open()
        print(f"[+] pywinusb: opened {dev.product_name}")

        # Enumerate reports
        print("\n=== Reports (via pywinusb) ===")
        print(f"  Input  reports  : {len(dev.find_input_reports())}")
        print(f"  Output reports  : {len(dev.find_output_reports())}")
        print(f"  Feature reports : {len(dev.find_feature_reports())}")

        print("\n=== Output Reports ===")
        for r in dev.find_output_reports():
            print(f"\n  Report ID: {r.report_id}")
            for item in r:
                print(f"    {item}")

        print("\n=== Input Reports ===")
        for r in dev.find_input_reports():
            print(f"\n  Report ID: {r.report_id}")
            for item in r:
                print(f"    {item}")

        print("\n=== Feature Reports ===")
        for r in dev.find_feature_reports():
            print(f"\n  Report ID: {r.report_id}")
            for item in r:
                print(f"    {item}")

        # Try to get raw descriptor
        raw = None
        try:
            raw = bytes(dev.hid_caps.raw_descriptor)
        except Exception:
            pass

        dev.close()
        return raw

    except ImportError:
        print("[!] pywinusb not installed. Run:  pip install pywinusb")
        return None
    except Exception as e:
        print(f"[!] pywinusb approach failed: {e}")
        return None


def get_descriptor_via_winapi():
    """Read report descriptor directly using ctypes + Windows HID API."""
    try:
        import ctypes
        import ctypes.wintypes as wintypes

        setupapi = ctypes.windll.setupapi
        hid      = ctypes.windll.hid
        kernel32 = ctypes.windll.kernel32

        DIGCF_PRESENT         = 0x02
        DIGCF_DEVICEINTERFACE = 0x10
        INVALID_HANDLE_VALUE  = ctypes.c_void_p(-1).value
        GENERIC_READ          = 0x80000000
        GENERIC_WRITE         = 0x40000000
        FILE_SHARE_READ       = 0x00000001
        FILE_SHARE_WRITE      = 0x00000002
        OPEN_EXISTING         = 3

        # Get the HID GUID
        HidGuid = ctypes.create_string_buffer(16)
        hid.HidD_GetHidGuid(HidGuid)

        # Device info set
        hDevInfo = setupapi.SetupDiGetClassDevsW(
            HidGuid, None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
        )

        class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_ulong),
                        ("InterfaceClassGuid", ctypes.c_byte * 16),
                        ("Flags", ctypes.c_ulong),
                        ("Reserved", ctypes.POINTER(ctypes.c_ulong))]

        class SP_DEVICE_INTERFACE_DETAIL_DATA_W(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_ulong),
                        ("DevicePath", ctypes.c_wchar * 256)]

        found_path = None
        idx = 0
        while True:
            ifData = SP_DEVICE_INTERFACE_DATA()
            ifData.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
            ok = setupapi.SetupDiEnumDeviceInterfaces(
                hDevInfo, None, HidGuid, idx, ctypes.byref(ifData)
            )
            if not ok:
                break
            idx += 1

            detail = SP_DEVICE_INTERFACE_DETAIL_DATA_W()
            detail.cbSize = 6 if ctypes.sizeof(ctypes.c_void_p) == 4 else 8
            setupapi.SetupDiGetDeviceInterfaceDetailW(
                hDevInfo, ctypes.byref(ifData), ctypes.byref(detail),
                ctypes.sizeof(detail), None, None
            )

            path = detail.DevicePath
            if "vid_0416" in path.lower() and "pid_8001" in path.lower():
                found_path = path
                print(f"[+] Found device path: {path}")
                break

        setupapi.SetupDiDestroyDeviceInfoList(hDevInfo)

        if not found_path:
            print("[!] Device not found via SetupDi")
            return None

        # Open device
        hDevice = kernel32.CreateFileW(
            found_path,
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None, OPEN_EXISTING, 0, None
        )

        if hDevice == INVALID_HANDLE_VALUE:
            # Try read-only
            hDevice = kernel32.CreateFileW(
                found_path, 0,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None, OPEN_EXISTING, 0, None
            )

        if hDevice == INVALID_HANDLE_VALUE:
            print("[!] Could not open device handle (try running as Administrator?)")
            return None

        print("[+] Device handle opened")

        # Preparsed data
        pPreparsed = ctypes.c_void_p()
        hid.HidD_GetPreparsedData(hDevice, ctypes.byref(pPreparsed))

        # Caps
        class HIDP_CAPS(ctypes.Structure):
            _fields_ = [
                ("Usage",                  ctypes.c_ushort),
                ("UsagePage",              ctypes.c_ushort),
                ("InputReportByteLength",  ctypes.c_ushort),
                ("OutputReportByteLength", ctypes.c_ushort),
                ("FeatureReportByteLength",ctypes.c_ushort),
                ("Reserved",               ctypes.c_ushort * 17),
                ("NumberLinkCollectionNodes", ctypes.c_ushort),
                ("NumberInputButtonCaps",  ctypes.c_ushort),
                ("NumberInputValueCaps",   ctypes.c_ushort),
                ("NumberInputDataIndices", ctypes.c_ushort),
                ("NumberOutputButtonCaps", ctypes.c_ushort),
                ("NumberOutputValueCaps",  ctypes.c_ushort),
                ("NumberOutputDataIndices",ctypes.c_ushort),
                ("NumberFeatureButtonCaps",ctypes.c_ushort),
                ("NumberFeatureValueCaps", ctypes.c_ushort),
                ("NumberFeatureDataIndices",ctypes.c_ushort),
            ]

        caps = HIDP_CAPS()
        # HidP_GetCaps returns HIDP_STATUS_SUCCESS = 0x00110000
        status = hid.HidP_GetCaps(pPreparsed, ctypes.byref(caps))

        print("\n=== Device Capabilities (via HidP_GetCaps) ===")
        print(f"  Usage             : 0x{caps.Usage:04X}")
        print(f"  UsagePage         : 0x{caps.UsagePage:04X} ({USAGE_PAGES.get(caps.UsagePage, 'Unknown')})")
        print(f"  Input  report len : {caps.InputReportByteLength} bytes")
        print(f"  Output report len : {caps.OutputReportByteLength} bytes")
        print(f"  Feature report len: {caps.FeatureReportByteLength} bytes")

        # Raw descriptor
        desc_buf = ctypes.create_string_buffer(4096)
        desc_len = ctypes.c_ulong(4096)
        ok = hid.HidD_GetReportDescriptor(hDevice, desc_buf, desc_len)
        if ok:
            raw = bytes(desc_buf[:desc_len.value])
            print(f"\n[+] Got raw descriptor ({len(raw)} bytes)")
        else:
            raw = None
            print("[!] HidD_GetReportDescriptor failed")

        hid.HidD_FreePreparsedData(pPreparsed)
        kernel32.CloseHandle(hDevice)
        return raw

    except Exception as e:
        import traceback
        print(f"[!] WinAPI approach failed: {e}")
        traceback.print_exc()
        return None


def main():
    print("=" * 60)
    print("HID Report Descriptor Reader")
    print(f"Target: VID=0x{VENDOR_ID:04X}  PID=0x{PRODUCT_ID:04X}")
    print("=" * 60)

    raw = None

    # Try methods in order of reliability
    print("\n[1/3] Trying Windows HID API (ctypes)...")
    raw = get_descriptor_via_winapi()

    if raw is None:
        print("\n[2/3] Trying pywinusb...")
        raw = get_descriptor_via_pywinusb()

    if raw is None:
        print("\n[3/3] Trying hidapi...")
        raw = get_descriptor_via_hid()

    if raw:
        parse_descriptor(raw)
        # Save raw descriptor
        out_file = Path(__file__).parent / "report_descriptor_raw.bin"
        out_file.write_bytes(raw)
        print(f"\n[+] Raw descriptor saved to: {out_file}")
    else:
        print("\n[!] Could not retrieve HID Report Descriptor.")
        print("    This is normal if the device uses a vendor-specific driver.")
        print("    The Frida hook approach (run_frida_hook.py) is the next step.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
.NET Assembly Analyzer — TRCC Protocol Extraction
===================================================
Extracts method names, string literals, and byte array constants from
the TRCC .NET assemblies to reverse-engineer the HID protocol.

The key files are:
  - UsbHid.dll    — HID communication library (sends commands to device)
  - USBLCDNEW.dll — LCD/display logic
  - TRCC.exe      — Main application

Since these are managed .NET assemblies, we can extract high-level
method names and constants without needing a disassembler.

Requirements:
    pip install dnfile

Usage:
    python analyze_dotnet.py
"""

import sys
import struct
import re
from pathlib import Path

try:
    import dnfile
    from dnfile.enums import MetadataTables
except ImportError:
    print("[!] dnfile not installed. Run: pip install dnfile")
    sys.exit(1)

TRCC_DIR = Path(r"C:\Program Files\TRCCCAP")

TARGET_FILES = [
    TRCC_DIR / "UsbHid.dll",
    TRCC_DIR / "USBLCDNEW.dll",
    TRCC_DIR / "TRCC.exe",
]

# Keywords to look for in method names and strings
INTERESTING_KEYWORDS = [
    "color", "rgb", "red", "green", "blue", "hue",
    "send", "write", "set", "command", "report",
    "mode", "effect", "rainbow", "breathe", "cycle",
    "bright", "light", "led", "init", "open", "connect",
    "packet", "buffer", "data", "usb", "hid",
    "0xda", "0xdb", "0xdc", "0xdd",
]

# Known magic bytes to search for in byte streams
MAGIC_BYTES = [
    bytes([0xDA, 0xDB, 0xDC, 0xDD]),
    bytes([0x5A, 0xA5]),
    bytes([0xAA, 0x55]),
]


def is_interesting(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in INTERESTING_KEYWORDS)


def analyze_assembly(path: Path):
    print(f"\n{'='*70}")
    print(f"  {path.name}  ({path.stat().st_size:,} bytes)")
    print(f"{'='*70}")

    pe = dnfile.dnPE(str(path))

    # ── String Heap — all user strings ────────────────────────────────────
    print("\n[STRING HEAP] Interesting string literals:")
    strings_found = set()
    try:
        us = pe.net.user_strings
        i = 1
        while True:
            try:
                s = us.get(i)
                if s and len(s.value) >= 2:
                    val = s.value
                    if len(val) >= 3 and is_interesting(val):
                        strings_found.add(val)
                i += s.row_size if hasattr(s, 'row_size') else 2
                if i > 0xFFFF:
                    break
            except Exception:
                break
    except Exception as e:
        pass

    # Also scan raw bytes for UTF-16 strings (common in .NET)
    raw = path.read_bytes()
    # UTF-16LE strings (2 bytes per char, printable)
    utf16_matches = re.findall(b'(?:[\x20-\x7E]\x00){4,}', raw)
    for m in utf16_matches:
        try:
            s = m.decode('utf-16-le').strip()
            if is_interesting(s) and s not in strings_found:
                strings_found.add(s)
        except Exception:
            pass

    # UTF-8 strings
    ascii_matches = re.findall(b'[\x20-\x7E]{5,}', raw)
    for m in ascii_matches:
        try:
            s = m.decode('ascii', errors='ignore').strip()
            if is_interesting(s) and s not in strings_found:
                strings_found.add(s)
        except Exception:
            pass

    if strings_found:
        for s in sorted(strings_found, key=lambda x: x.lower()):
            print(f"  \"{s}\"")
    else:
        print("  (none found)")

    # ── Type/Method names ──────────────────────────────────────────────────
    print("\n[METHODS] Interesting method/type names:")
    methods_found = []
    try:
        tbl = pe.net.mdtables
        # TypeDef table
        if hasattr(tbl, 'TypeDef'):
            for row in tbl.TypeDef:
                type_name = ""
                try:
                    type_name = row.TypeName.value if hasattr(row.TypeName, 'value') else str(row.TypeName)
                    ns = row.TypeNamespace.value if hasattr(row.TypeNamespace, 'value') else ""
                    full = (ns + "." + type_name) if ns else type_name
                    if is_interesting(full):
                        methods_found.append(f"  TYPE: {full}")
                except Exception:
                    pass

        # MethodDef table
        if hasattr(tbl, 'MethodDef'):
            for row in tbl.MethodDef:
                try:
                    name = row.Name.value if hasattr(row.Name, 'value') else str(row.Name)
                    if is_interesting(name):
                        methods_found.append(f"  METHOD: {name}")
                except Exception:
                    pass

    except Exception as e:
        print(f"  (error reading metadata: {e})")

    if methods_found:
        for m in sorted(set(methods_found)):
            print(m)
    else:
        print("  (none found)")

    # ── Search for magic byte sequences in raw binary ──────────────────────
    print("\n[BYTE PATTERNS] Known magic byte sequences:")
    for magic in MAGIC_BYTES:
        offset = 0
        found_any = False
        while True:
            idx = raw.find(magic, offset)
            if idx == -1:
                break
            found_any = True
            ctx_start = max(0, idx - 8)
            ctx_end   = min(len(raw), idx + 32)
            ctx = raw[ctx_start:ctx_end]
            print(f"  {magic.hex()} @ offset 0x{idx:06X}: ...{ctx.hex()}...")
            offset = idx + 1
        if not found_any:
            print(f"  {magic.hex()} — not found")

    # ── Search for 0xDA/DB/DC/DD byte individually ─────────────────────────
    print("\n[BYTE PATTERNS] Searching for 0xDA 0xDB 0xDC 0xDD individually:")
    for b, label in [(0xDA, "0xDA"), (0xDB, "0xDB"), (0xDC, "0xDC"), (0xDD, "0xDD")]:
        positions = [i for i in range(len(raw)) if raw[i] == b]
        print(f"  {label}: {len(positions)} occurrences")

    # ── Look for potential command tables (sequences of non-zero bytes) ────
    print("\n[BYTE PATTERNS] Potential command arrays (non-trivial 8-64 byte sequences):")
    # Look for patterns that could be hard-coded HID packets:
    # A run of non-zero bytes 8-64 bytes long, not in the PE headers
    candidates = []
    i = 0
    while i < len(raw) - 8:
        # Skip first 0x400 bytes (PE header area)
        if i < 0x400:
            i += 1
            continue
        run_start = i
        run = []
        while i < len(raw) and raw[i] != 0x00:
            run.append(raw[i])
            i += 1
        if 8 <= len(run) <= 64:
            # Check if it contains DA or DB or DC or DD
            if 0xDA in run or 0xDB in run:
                candidates.append((run_start, bytes(run)))
        else:
            i += 1

    if candidates:
        for offset, data in candidates[:20]:  # Show first 20
            print(f"  @ 0x{offset:06X} ({len(data)} bytes): {data.hex()}")
    else:
        print("  (none found near magic bytes)")

    pe.close()


def extract_all_strings_from_file(path: Path, outfile: Path):
    """Dump ALL printable strings >= 6 chars from a binary to a text file."""
    raw = path.read_bytes()
    strings = set()

    # ASCII
    for m in re.findall(b'[\x20-\x7E]{6,}', raw):
        strings.add(m.decode('ascii', errors='ignore'))

    # UTF-16LE
    for m in re.findall(b'(?:[\x20-\x7E]\x00){6,}', raw):
        try:
            strings.add(m.decode('utf-16-le'))
        except Exception:
            pass

    with open(outfile, 'w', encoding='utf-8') as f:
        for s in sorted(strings):
            f.write(s + '\n')
    print(f"\n[+] All strings dumped to: {outfile} ({len(strings)} strings)")


def main():
    print("=" * 70)
    print("TRCC .NET Assembly Analyzer")
    print("Looking for protocol details in UsbHid.dll, USBLCDNEW.dll, TRCC.exe")
    print("=" * 70)

    any_found = False
    for path in TARGET_FILES:
        if not path.exists():
            print(f"\n[!] Not found: {path}")
            continue
        any_found = True
        try:
            analyze_assembly(path)
        except Exception as e:
            print(f"[!] Error analyzing {path.name}: {e}")
            import traceback
            traceback.print_exc()

        # Also dump raw strings
        out = Path(__file__).parent / f"strings_{path.stem}.txt"
        try:
            extract_all_strings_from_file(path, out)
        except Exception as e:
            print(f"[!] String dump failed: {e}")

    if not any_found:
        print("\n[!] No TRCC files found in C:\\Program Files\\TRCCCAP")
        print("    Update TRCC_DIR in this script to point to the correct path.")


if __name__ == "__main__":
    main()

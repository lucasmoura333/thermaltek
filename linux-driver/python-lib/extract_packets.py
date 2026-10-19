#!/usr/bin/env python3
"""
TRCC Packet Extractor — Deep .NET Static Array Analysis
=========================================================
Extracts hard-coded HID packet byte arrays from TRCC .NET assemblies.

In .NET, byte arrays initialized at compile-time are stored as
__StaticArrayInitTypeSize=N fields in the assembly's .data section.
We found __StaticArrayInitTypeSize=64 — exactly the HID report size.

This script:
1. Finds the 64-byte static initializer array(s) in UsbHid.dll
2. Extracts ALL dadbdcdd-containing packet contexts from TRCC.exe
3. Analyzes packet structure to identify command bytes, RGB positions, etc.

Usage:
    python extract_packets.py
"""

import struct
from pathlib import Path

TRCC_DIR      = Path(r"C:\Program Files\TRCCCAP")
USPHID_DLL    = TRCC_DIR / "UsbHid.dll"
USBLCDNEW_DLL = TRCC_DIR / "USBLCDNEW.dll"
TRCC_EXE      = TRCC_DIR / "TRCC.exe"

MAGIC = bytes([0xDA, 0xDB, 0xDC, 0xDD])


def find_all(data: bytes, pattern: bytes):
    """Return all offsets where pattern occurs in data."""
    offsets = []
    start = 0
    while True:
        idx = data.find(pattern, start)
        if idx == -1:
            break
        offsets.append(idx)
        start = idx + 1
    return offsets


def extract_dadbdcdd_packets(data: bytes, label: str):
    """Extract context around every DA DB DC DD occurrence."""
    offsets = find_all(data, MAGIC)
    packets = []

    print(f"\n{'='*70}")
    print(f"  {label}  — {len(offsets)} occurrences of DA DB DC DD")
    print(f"{'='*70}")

    for off in offsets:
        # Grab 64 bytes starting at the magic header (the full HID packet)
        pkt_raw = data[off:off+64]
        if len(pkt_raw) < 16:
            continue
        packets.append((off, pkt_raw))

        print(f"\n  @ 0x{off:08X}:")
        # Print as rows of 16
        for row in range(0, len(pkt_raw), 16):
            chunk = pkt_raw[row:row+16]
            hex_part  = ' '.join(f'{b:02X}' for b in chunk)
            asc_part  = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
            print(f"    {row:02d}: {hex_part:<47}  {asc_part}")

        # Annotate known positions
        annotate_packet(pkt_raw, off)

    return packets


def annotate_packet(pkt: bytes, base_off: int):
    """Try to interpret a packet."""
    if len(pkt) < 12:
        return

    notes = []

    # bytes 0-3: header (confirmed DA DB DC DD)
    notes.append("  [0-3 ] DA DB DC DD — magic header (confirmed)")

    # byte 4: possible command class
    cmd = pkt[4]
    notes.append(f"  [4   ] 0x{cmd:02X} — command byte? (0x02=write?, 0x00=init?)")

    # bytes 5-7
    b567 = pkt[5:8]
    notes.append(f"  [5-7 ] {b567.hex()} — ?")

    # Look for colour-like byte triplets (non-zero sequences)
    colour_candidates = []
    for i in range(4, len(pkt) - 2):
        r, g, b = pkt[i], pkt[i+1], pkt[i+2]
        # Not all zero, not all same, at least one non-trivial value
        if (r > 0 or g > 0 or b > 0) and not (r == g == b):
            if any(v in (0xFF, 0xFE, 0xFD) for v in (r, g, b)):
                colour_candidates.append((i, r, g, b))

    if colour_candidates:
        for i, r, g, b in colour_candidates:
            notes.append(f"  [{i:2d}  ] R={r:3d} G={g:3d} B={b:3d}  (0x{r:02X}{g:02X}{b:02X}) ← possible RGB")

    for n in notes:
        print(n)


def analyze_static_arrays_in_file(path: Path):
    """
    Find and extract __StaticArrayInitTypeSize=N arrays from a .NET assembly.
    These are the hard-coded byte arrays (e.g., packet templates).
    """
    try:
        import dnfile
    except ImportError:
        print("[!] dnfile not installed.")
        return

    print(f"\n{'='*70}")
    print(f"  Static Arrays in {path.name}")
    print(f"{'='*70}")

    try:
        pe = dnfile.dnPE(str(path))
    except Exception as e:
        print(f"  [!] Could not parse: {e}")
        return

    raw = path.read_bytes()

    # Find __StaticArrayInitTypeSize fields via metadata
    # These are stored as FieldRVA entries in .NET metadata
    try:
        tbl = pe.net.mdtables

        # TypeDef: find __StaticArrayInitTypeSize types
        target_type_row_ids = {}
        if hasattr(tbl, 'TypeDef'):
            for i, row in enumerate(tbl.TypeDef.rows):
                try:
                    name = row.TypeName.value if hasattr(row.TypeName, 'value') else str(row.TypeName)
                    if '__StaticArrayInitTypeSize' in name:
                        size_str = name.replace('__StaticArrayInitTypeSize=', '')
                        try:
                            size = int(size_str)
                            target_type_row_ids[i + 1] = size  # 1-indexed
                        except ValueError:
                            pass
                except Exception:
                    pass

        print(f"  Found {len(target_type_row_ids)} static initializer types")

        if not target_type_row_ids:
            print("  (none found — checking raw data instead)")
            # Fall back to raw scan for 64-byte runs starting near our magic bytes
            offsets = find_all(raw, MAGIC)
            if offsets:
                print(f"  Found {len(offsets)} dadbdcdd occurrences in raw binary")
                for off in offsets[:5]:
                    chunk = raw[off:off+64]
                    print(f"    @ 0x{off:06X}: {chunk.hex()}")
            return

        # Find FieldRVA entries for these types  
        if hasattr(tbl, 'FieldRVA'):
            print(f"\n  FieldRVA entries:")
            for row in tbl.FieldRVA.rows:
                try:
                    rva = row.RVA.value if hasattr(row.RVA, 'value') else row.RVA
                    field_idx = row.Field.row_index if hasattr(row.Field, 'row_index') else None
                    if rva and rva > 0:
                        # Convert RVA to file offset
                        try:
                            file_off = pe.get_offset_from_rva(rva)
                        except Exception:
                            file_off = None

                        if file_off is not None and file_off < len(raw):
                            # Try to determine size from the field type
                            # For now, try common HID sizes
                            for test_size in [64, 65, 32, 16, 128]:
                                chunk = raw[file_off:file_off + test_size]
                                if MAGIC in chunk or any(b > 0 for b in chunk[:4]):
                                    print(f"    RVA=0x{rva:08X} → FileOffset=0x{file_off:06X}")
                                    print(f"    First 32 bytes: {chunk[:32].hex()}")
                                    if MAGIC[:4] == chunk[:4]:
                                        print(f"    *** STARTS WITH DA DB DC DD! ***")
                                    break
                except Exception as e:
                    pass

    except Exception as e:
        print(f"  [!] Metadata error: {e}")
        import traceback
        traceback.print_exc()

    pe.close()


def deep_scan_usbhid():
    """Focused deep scan of UsbHid.dll for protocol data."""
    path = USPHID_DLL
    if not path.exists():
        print(f"[!] Not found: {path}")
        return

    raw = path.read_bytes()
    print(f"\n{'='*70}")
    print(f"  DEEP SCAN: {path.name}  ({len(raw):,} bytes)")
    print(f"{'='*70}")

    # 1. All non-zero byte runs >= 4 bytes (not in PE header area)
    print("\n[A] Non-trivial byte runs (4-64 bytes, after offset 0x200):")
    runs = []
    i = 0x200
    while i < len(raw):
        if raw[i] != 0x00:
            start = i
            run = []
            while i < len(raw) and raw[i] != 0x00 and len(run) < 128:
                run.append(raw[i])
                i += 1
            if 4 <= len(run) <= 64:
                # Filter interesting runs
                has_high = any(b >= 0xDA for b in run)
                has_color = any(b == 0xFF for b in run)
                if has_high or has_color or MAGIC[:2] in bytes(run):
                    runs.append((start, bytes(run)))
        else:
            i += 1

    if runs:
        for off, run in runs[:30]:
            print(f"  @ 0x{off:06X} ({len(run):3d}B): {run.hex()}")
    else:
        print("  (none found)")

    # 2. Find dadbdcdd
    extract_dadbdcdd_packets(raw, path.name)

    # 3. Scan for any sequence with multiple 0xFF bytes (possible RGB patterns)
    print("\n[B] Patterns with 0xFF values (possible RGB):") 
    for i in range(0x200, len(raw) - 10):
        window = raw[i:i+10]
        ff_count = window.count(0xFF)
        if ff_count >= 2 and raw[i] not in (0x00, 0xFF):
            print(f"  @ 0x{i:06X}: {window.hex()}")
            if len([x for x in range(0x200, len(raw) - 10)
                    if raw[x:x+10].count(0xFF) >= 2 and raw[x] not in (0x00, 0xFF)]) > 50:
                print("  ... (too many, stopping)")
                break


def compare_packets(packets):
    """Compare multiple packets to identify variable vs fixed bytes."""
    if len(packets) < 2:
        return

    print(f"\n{'='*70}")
    print(f"  PACKET COMPARISON ({len(packets)} packets)")
    print(f"{'='*70}")

    max_len = min(64, min(len(p) for _, p in packets))

    # Find bytes that differ across packets
    print("\nByte-by-byte comparison (D=differs, .=constant):")
    for i in range(0, max_len, 16):
        row = ""
        for j in range(i, min(i+16, max_len)):
            vals = set(p[j] for _, p in packets if j < len(p))
            row += "D" if len(vals) > 1 else "."
        print(f"  {i:02d}: {row}")

    # For differing bytes, show their values across packets
    print("\nValues at differing positions:")
    differ_pos = []
    for j in range(max_len):
        vals = [p[j] for _, p in packets if j < len(p)]
        if len(set(vals)) > 1:
            differ_pos.append(j)

    if differ_pos:
        header = "Pos  " + " ".join(f"Pkt{i+1}" for i in range(len(packets)))
        print(f"  {header}")
        for j in differ_pos:
            vals = [f"  {p[j]:02X}" if j < len(p) else "  ??" for _, p in packets]
            print(f"  [{j:2d}]{''.join(vals)}")
    else:
        print("  (all packets identical — may be templates, not real traffic)")


def main():
    print("=" * 70)
    print("TRCC Packet Extractor")
    print("=" * 70)

    # 1. Deep scan UsbHid.dll (the actual HID communication library)
    deep_scan_usbhid()

    # 2. Extract static arrays from UsbHid.dll
    analyze_static_arrays_in_file(USPHID_DLL)

    # 3. Extract dadbdcdd packets from all files
    all_packets = []
    for f in [USPHID_DLL, USBLCDNEW_DLL]:
        if f.exists():
            raw = f.read_bytes()
            pkts = extract_dadbdcdd_packets(raw, f.name)
            all_packets.extend(pkts)

    # Extract from TRCC.exe but only from the data sections (high offsets where we found them)
    if TRCC_EXE.exists():
        raw = TRCC_EXE.read_bytes()
        # Only scan around the offsets we already found: 0xDDD000-0xDE2000
        section = raw[0xDDD000:0xDE3000]
        pkts = extract_dadbdcdd_packets(section, "TRCC.exe [data section 0xDDD000-0xDE3000]")
        all_packets.extend([(off + 0xDDD000, pkt) for off, pkt in
                             [(o, p) for (o, p) in [(i, section[i:i+64])
                              for i in find_all(section, MAGIC)]]])

    # 4. Compare packets to find variable bytes (RGB positions)
    if len(all_packets) >= 2:
        compare_packets(all_packets[:8])  # Compare first 8

    print(f"\n\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"Total dadbdcdd packets found: {len(all_packets)}")
    print("\nNEXT STEP: Run Frida hook while using TRCC to capture LIVE traffic")
    print("  python run_frida_hook.py")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Analyze UsbHid.dll for protocol patterns
"""

import sys

def analyze_dll(filename):
    """Search for hex patterns and strings in DLL"""
    
    print(f"\n{'='*70}")
    print(f"ANALYZING: {filename}")
    print('='*70 + "\n")
    
    with open(filename, 'rb') as f:
        data = f.read()
    
    print(f"File size: {len(data):,} bytes\n")
    
    # Search for specific patterns
    patterns = [
        (b'\x04\x16', "Nuvoton VID (0x0416)"),
        (b'\x80\x01', "Product ID (0x8001)"),
        (b'\x16\x04', "VID reversed"),
        (b'\x01\x80', "PID reversed"),
        (b'HID', "HID string"),
        (b'RGB', "RGB string"),
        (b'color', "color string"),
        (b'Color', "Color string"),
    ]
    
    print("🔍 Searching for specific patterns:\n")
    for pattern, desc in patterns:
        count = data.count(pattern)
        if count > 0:
            print(f"   ✓ Found {count}x: {desc}")
            # Show first occurrence with context
            index = data.index(pattern)
            start = max(0, index - 16)
            end = min(len(data), index + 32)
            context = data[start:end]
            print(f"     Context: {context.hex()}")
            print(f"     ASCII: {repr(context)}\n")
    
    # Extract readable strings
    print("\n📝 Extracting readable strings (>5 chars):\n")
    strings = []
    current_string = bytearray()
    
    for byte in data:
        if 32 <= byte < 127:  # Printable ASCII
            current_string.append(byte)
        else:
            if len(current_string) >= 5:
                s = current_string.decode('ascii', errors='ignore')
                if any(keyword in s.lower() for keyword in ['hid', 'usb', 'rgb', 'color', 'led', 'device']):
                    strings.append(s)
            current_string = bytearray()
    
    # Show interesting strings
    for s in set(strings):  # Remove duplicates
        print(f"   - {s}")
    
    # Look for byte sequences that might be commands
    print("\n\n🧪 Looking for potential command sequences:\n")
    
    # Search for sequences like [header][cmd][r][g][b]
    for i in range(len(data) - 5):
        # Look for patterns where we have non-zero followed by RGB-like values
        if data[i] != 0 and data[i] < 0x10:  # Possible command byte
            if i + 4 < len(data):
                seq = data[i:i+5]
                # Check if looks like RGB command (values 0-255)
                if all(b <= 255 for b in seq[1:4]):
                    hex_seq = seq.hex()
                    if hex_seq not in ['0000000000', 'ffffffffff']:  # Skip empty patterns
                        # Check if this pattern appears near our VID/PID
                        print(f"   Offset {i:06x}: {hex_seq}")
                        if i < 100:  # Only show first few
                            pass

if __name__ == "__main__":
    filename = sys.argv[1] if len(sys.argv) > 1 else "UsbHid.dll"
    try:
        analyze_dll(filename)
    except FileNotFoundError:
        print(f"ERROR: File '{filename}' not found")
    except Exception as e:
        print(f"ERROR: {e}")

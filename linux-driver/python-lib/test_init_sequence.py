#!/usr/bin/env python3
"""
Test Initialization Sequence + Color

Sends the exact initialization pattern found in TRCC.exe,
then attempts to set color.
"""

import time
import logging
from nuvoton_hid import NuvotonDevice, logger

logger.setLevel(logging.INFO)

def test_init_and_color():
    device = NuvotonDevice()
    if not device.connect():
        print("ERROR: Failed to connect")
        return
    
    print("\n" + "="*60)
    print("TESTING INIT SEQUENCE + COLOR")
    print("="*60)
    print("⚠️  PLEASE CLOSE TRCC SOFTWARE BEFORE RUNNING THIS!")
    print("\nSequence:")
    print("1. Send TRCC Init Pattern (DA DB DC DD 02...)")
    print("2. Wait 1 second")
    print("3. Send Red Color Command")
    print("\n⚠️  WATCH THE RGB CONTROLLER!\n")
    
    # 1. The exact pattern found in TRCC.exe
    # DA DB DC DD 02 00 00 00 00 05 E0 01 02
    init_pattern = bytearray([
        0xDA, 0xDB, 0xDC, 0xDD, # Header
        0x02,                   # Cmd?
        0x00, 0x00, 0x00, 0x00, # Padding?
        0x05, 0xE0, 0x01, 0x02  # Data?
    ])
    init_pattern.extend([0x00] * (64 - len(init_pattern)))
    
    print(f"1. Sending Init: {init_pattern[:16].hex()}...")
    device.write_report(init_pattern)
    
    # Read response
    resp = device.read_report()
    if resp:
        print(f"   ✓ Response: {resp[:16].hex()}...")
    
    time.sleep(1)
    
    # 2. Try to set RED color using same header
    # Guessing format: Header + Cmd(0x01) + R G B
    color_pattern = bytearray([
        0xDA, 0xDB, 0xDC, 0xDD, # Header
        0x01,                   # Cmd (Set Color?)
        0xFF, 0x00, 0x00,       # R G B
        0x00                    # Padding
    ])
    color_pattern.extend([0x00] * (64 - len(color_pattern)))
    
    print(f"2. Sending Red:  {color_pattern[:16].hex()}...")
    device.write_report(color_pattern)
    
    resp = device.read_report()
    if resp:
        print(f"   ✓ Response: {resp[:16].hex()}...")
        
    time.sleep(1)
    
    # 3. Try another variation for color (Cmd 0x00?)
    color_pattern2 = bytearray([
        0xDA, 0xDB, 0xDC, 0xDD, # Header
        0x00,                   # Cmd?
        0xFF, 0x00, 0x00,       # R G B
    ])
    color_pattern2.extend([0x00] * (64 - len(color_pattern2)))
    
    print(f"3. Sending Red (Alt): {color_pattern2[:16].hex()}...")
    device.write_report(color_pattern2)
    
    device.disconnect()

if __name__ == "__main__":
    test_init_and_color()

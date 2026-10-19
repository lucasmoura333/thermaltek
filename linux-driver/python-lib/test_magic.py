#!/usr/bin/env python3
"""
Test Discovered Magic Patterns

Tests the specific byte sequences found in TRCC binaries
"""

import time
import logging
from nuvoton_hid import NuvotonDevice, logger

logger.setLevel(logging.INFO)

def test_magic_patterns():
    device = NuvotonDevice()
    if not device.connect():
        print("ERROR: Failed to connect")
        return
    
    print("\n" + "="*60)
    print("TESTING DISCOVERED MAGIC PATTERNS")
    print("="*60)
    print("\n⚠️  WATCH THE RGB CONTROLLER!\n")
    
    # Patterns found in TRCC.exe and USBLCDNEW.dll
    patterns = [
        # Pattern from TRCC.exe
        (b'\xDA\xDB\xDC\xDD\x02\x00\x00\x00\x00\x05\xE0\x01\x02' + b'\x00'*51, 
         "TRCC Pattern 1 (Init?)"),
         
        # Variation with 0x01 command
        (b'\xDA\xDB\xDC\xDD\x01\x00\x00\x00\x00\x05\xE0\x01\x02' + b'\x00'*51, 
         "TRCC Pattern 2 (Cmd 0x01)"),

        # Pattern from USBLCDNEW.dll
        (b'\xDA\xDB\xDC\xDD\x00\x00\x00\x00\x00\x00\x00\x00\x01' + b'\x00'*51, 
         "DLL Pattern 1"),
         
        # Based on captured packet (reversed direction?)
        (b'\xDA\xDB\xDC\xDD\x10\x10\x10\x10\x00\x00\x00\x00\x01' + b'\x00'*51, 
         "Captured Packet Replay"),
         
        # Try setting color with this header
        (b'\xDA\xDB\xDC\xDD\x01\xFF\x00\x00\x00\x00\x00\x00\x00' + b'\x00'*51, 
         "Magic Header + Red Color"),
    ]
    
    for i, (pattern, description) in enumerate(patterns, 1):
        print(f"\n[{i}/{len(patterns)}] Testing: {description}")
        print(f"    Pattern: {pattern[:16].hex()}...")
        
        device.write_report(pattern)
        
        # Check response
        response = device.read_report(timeout_ms=200)
        if response:
            print(f"    ✓ Got response: {response[:16].hex()}...")
            
        input("    Press ENTER to continue...")
        
    device.disconnect()

if __name__ == "__main__":
    test_magic_patterns()

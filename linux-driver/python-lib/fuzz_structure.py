#!/usr/bin/env python3
"""
Structured Protocol Fuzzing

Tests various packet structures with the confirmed magic header
DA DB DC DD to find where the RGB data should go.
"""

import time
import logging
from nuvoton_hid import NuvotonDevice, logger

logger.setLevel(logging.INFO)

def fuzz_structure():
    device = NuvotonDevice()
    if not device.connect():
        print("ERROR: Failed to connect")
        return
    
    print("\n" + "="*60)
    print("STRUCTURED PROTOCOL FUZZING")
    print("="*60)
    print("Header: DA DB DC DD")
    print("Testing different RGB data offsets and commands")
    print("\n⚠️  WATCH THE RGB CONTROLLER!\n")
    
    header = b'\xDA\xDB\xDC\xDD'
    
    # Commands to try (based on common HID usage)
    commands = [0x00, 0x01, 0x02, 0x03, 0x10, 0x20, 0x80, 0xFF]
    
    # Offsets to try placing RGB data (after header+cmd)
    offsets = range(0, 16)
    
    try:
        for cmd in commands:
            print(f"\nTesting Command 0x{cmd:02X}...")
            
            for offset in offsets:
                print(f"  Offset {offset}: [Header] [Cmd] [{offset}x 00] [FF 00 00]...", end='\r')
                
                # Construct packet
                packet = bytearray(header)
                packet.append(cmd)
                packet.extend([0x00] * offset)
                packet.extend([0xFF, 0x00, 0x00]) # Red
                
                # Pad to 64 bytes
                if len(packet) < 64:
                    packet.extend([0x00] * (64 - len(packet)))
                
                device.write_report(packet)
                time.sleep(0.05)
                
                # Also try with "Mode" byte = 0x01
                packet = bytearray(header)
                packet.append(cmd)
                packet.extend([0x00] * offset)
                packet.append(0x01) # Mode
                packet.extend([0xFF, 0x00, 0x00]) # Red
                
                if len(packet) < 64:
                    packet.extend([0x00] * (64 - len(packet)))
                    
                device.write_report(packet)
                time.sleep(0.05)

            # Clear buffer
            device.read_report(timeout_ms=10)
            
    except KeyboardInterrupt:
        print("\nStopped by user")
        
    print("\n" + "="*60)
    print("Fuzzing complete")
    print("="*60)
    print("Did you see any flash of RED?")
    
    device.disconnect()

if __name__ == "__main__":
    fuzz_structure()

#!/usr/bin/env python3
"""
Brute Force Magic Header

Iterates through all possible command bytes using the discovered
DA DB DC DD header to find the RGB control command.
"""

import time
import logging
from nuvoton_hid import NuvotonDevice, logger

logger.setLevel(logging.INFO)

def brute_force_magic():
    device = NuvotonDevice()
    if not device.connect():
        print("ERROR: Failed to connect")
        return
    
    print("\n" + "="*60)
    print("BRUTE FORCE MAGIC HEADER")
    print("="*60)
    print("Header: DA DB DC DD")
    print("Testing all 256 command bytes with RED color")
    print("\n⚠️  WATCH THE RGB CONTROLLER!\n")
    
    # Magic header
    header = b'\xDA\xDB\xDC\xDD'
    
    # Red color data
    # We'll try putting color data at different offsets too
    
    try:
        for cmd in range(0x00, 0x100):
            print(f"Testing Command: 0x{cmd:02X}", end='\r')
            
            # Construct packet: Header + Cmd + Red + Padding
            # Pattern A: Header + Cmd + R G B
            packet_a = bytearray(header)
            packet_a.append(cmd)
            packet_a.extend([0xFF, 0x00, 0x00]) # Red
            packet_a.extend([0x00] * (64 - len(packet_a)))
            
            device.write_report(packet_a)
            time.sleep(0.05) # Fast but not too fast
            
            # Pattern B: Header + Cmd + Mode + R G B
            packet_b = bytearray(header)
            packet_b.append(cmd)
            packet_b.append(0x01) # Mode?
            packet_b.extend([0xFF, 0x00, 0x00]) # Red
            packet_b.extend([0x00] * (64 - len(packet_b)))
            
            device.write_report(packet_b)
            time.sleep(0.05)
            
            # Every 16 commands, pause slightly
            if cmd % 16 == 0:
                # Read any pending responses to clear buffer
                device.read_report(timeout_ms=10)
                
    except KeyboardInterrupt:
        print("\nStopped by user")
        
    print("\n" + "="*60)
    print("Brute force complete")
    print("="*60)
    print("Did you see any flash of RED?")
    
    device.disconnect()

if __name__ == "__main__":
    brute_force_magic()

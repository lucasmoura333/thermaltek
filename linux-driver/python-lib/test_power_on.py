#!/usr/bin/env python3
"""
Test Power-On/Initialization Commands

Focus on finding the command to TURN ON the RGB controller
"""

import time
import logging
from nuvoton_hid import NuvotonDevice, logger

logger.setLevel(logging.INFO)

def test_power_commands():
    """Test various power-on command patterns"""
    
    device = NuvotonDevice()
    if not device.connect():
        print("ERROR: Failed to connect")
        return
    
    print("\n" + "="*60)
    print("TESTING POWER-ON COMMANDS")
    print("="*60)
    print("\n⚠️  WATCH THE RGB CONTROLLER for any lights turning ON!\n")
    
    tests = [
        # Simple power commands
        (b'\x01' + b'\x00'*63, "Power ON - Simple 0x01"),
        (b'\x02' + b'\x00'*63, "Power ON - Simple 0x02"),
        (b'\xFF' + b'\x00'*63, "Power ON - Simple 0xFF"),
        
        # Enable/Start commands
        (b'\x01\x01' + b'\x00'*62, "Enable - 0x01 0x01"),
        (b'\x02\x01' + b'\x00'*62, "Enable - 0x02 0x01"),
        (b'\x03\x01' + b'\x00'*62, "Enable - 0x03 0x01"),
        
        # Init sequences
        (b'\xAA\x55\x01' + b'\x00'*61, "Init - AA 55 01"),
        (b'\x55\xAA\x01' + b'\x00'*61, "Init - 55 AA 01"),
        (b'\x5A\x00' + b'\x00'*62, "Init - 5A 00"),
        (b'\x5A\x01' + b'\x00'*62, "Init - 5A 01"),
        (b'\xB5\x00' + b'\x00'*62, "Init - B5 00"),
        (b'\xB5\x01' + b'\x00'*62, "Init - B5 01"),
        
        # Common power-on patterns
        (b'\x01\xFF\xFF\xFF' + b'\x00'*60, "Power + Full brightness"),
        (b'\x02\xFF\xFF\xFF' + b'\x00'*60, "Power2 + Full brightness"),
        
        # Wake up commands
        (b'\x00\x00\x00\x00\x01' + b'\x00'*59, "Wake - zeros + 01"),
        (b'\xFF\xFF\xFF\xFF\xFF' + b'\x00'*59, "Wake - all FF"),
        
        # Nuvoton specific
        (b'\x04\x16\x80\x01' + b'\x00'*60, "Nuvoton VID/PID"),
        (b'\x04\x16\x01' + b'\x00'*61, "Nuvoton VID + enable"),
        
        # Mode set to ON
        (b'\x01\x00\x01' + b'\x00'*61, "Mode 0x01 ON"),
        (b'\x02\x00\x01' + b'\x00'*61, "Mode 0x02 ON"),
        (b'\x03\x00\x01' + b'\x00'*61, "Mode 0x03 ON"),
        
        # Status/State commands
        (b'\x10\x01' + b'\x00'*62, "State 0x10 ON"),
        (b'\x20\x01' + b'\x00'*62, "State 0x20 ON"),
        (b'\x30\x01' + b'\x00'*62, "State 0x30 ON"),
        
        # Reset + enable
        (b'\x00\x00' + b'\x00'*62, "Reset - all zeros"),
        (b'\xFF\x00' + b'\x00'*62, "Reset - FF 00"),
    ]
    
    for i, (pattern, description) in enumerate(tests, 1):
        print(f"\n[{i}/{len(tests)}] Testing: {description}")
        print(f"    Pattern: {pattern[:8].hex()}...")
        
        device.write_report(pattern)
        
        # Wait and check for response
        response = device.read_report(timeout_ms=200)
        if response:
            print(f"    ✓ Got response: {response[:16].hex()}...")
        
        input("    Press ENTER to continue (or Ctrl+C to stop)... ")
    
    print("\n" + "="*60)
    print("Tests complete!")
    print("="*60)
    
    device.disconnect()

if __name__ == "__main__":
    try:
        test_power_commands()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")

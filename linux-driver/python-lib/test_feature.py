#!/usr/bin/env python3
"""
Test HID Feature Reports

Some devices use Feature Reports instead of Output Reports for configuration.
This script tests the discovered magic header using Feature Reports.
"""

import time
import logging
from nuvoton_hid import NuvotonDevice, logger

logger.setLevel(logging.INFO)

def test_feature_reports():
    device = NuvotonDevice()
    if not device.connect():
        print("ERROR: Failed to connect")
        return
    
    print("\n" + "="*60)
    print("TESTING HID FEATURE REPORTS")
    print("="*60)
    print("Header: DA DB DC DD")
    print("Method: device.send_feature_report()")
    print("\n⚠️  WATCH THE RGB CONTROLLER!\n")
    
    # Magic header
    header = b'\xDA\xDB\xDC\xDD'
    
    patterns = [
        # 1. Init Sequence as Feature
        (b'\xDA\xDB\xDC\xDD\x02\x00\x00\x00\x00\x05\xE0\x01\x02' + b'\x00'*51,
         "Init Sequence (Feature)"),
         
        # 2. Red Color as Feature (Cmd 0x01)
        (b'\xDA\xDB\xDC\xDD\x01\xFF\x00\x00\x00\x00\x00\x00\x00' + b'\x00'*51,
         "Red Color (Feature Cmd 0x01)"),
         
        # 3. Red Color as Feature (Cmd 0x00)
        (b'\xDA\xDB\xDC\xDD\x00\xFF\x00\x00\x00\x00\x00\x00\x00' + b'\x00'*51,
         "Red Color (Feature Cmd 0x00)"),
         
        # 4. Red Color as Feature (Cmd 0x80 - common for config)
        (b'\xDA\xDB\xDC\xDD\x80\xFF\x00\x00\x00\x00\x00\x00\x00' + b'\x00'*51,
         "Red Color (Feature Cmd 0x80)"),
    ]
    
    for i, (data, desc) in enumerate(patterns, 1):
        print(f"\n[{i}/{len(patterns)}] Testing: {desc}")
        
        # Feature reports usually need Report ID 0x00 prepended
        # hidapi handles this differently depending on backend, 
        # usually we pass the data starting with Report ID
        
        report_data = b'\x00' + data
        
        try:
            # Send Feature Report
            device.device.send_feature_report(report_data)
            print("   ✓ Feature Report sent")
            
            # Try to read response (Feature Get)
            # Buffer size usually needs to match report size
            try:
                resp = device.device.get_feature_report(0, 65)
                if resp:
                    print(f"   ✓ Got Feature Response: {bytes(resp)[:16].hex()}...")
            except Exception as e:
                print(f"   (No feature response: {e})")
                
        except Exception as e:
            print(f"   ❌ Failed to send: {e}")
            
        time.sleep(0.5)
        
    device.disconnect()

if __name__ == "__main__":
    test_feature_reports()

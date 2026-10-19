#!/usr/bin/env python3
"""
HID Traffic Monitor

Monitors HID device for any activity/responses while you use TRCC software
"""

import time
import logging
from datetime import datetime
from nuvoton_hid import NuvotonDevice, logger

logger.setLevel(logging.INFO)

def monitor_device(duration_seconds=60):
    """
    Monitor device for incoming traffic
    
    Args:
        duration_seconds: How long to monitor (default 60 seconds)
    """
    
    device = NuvotonDevice()
    if not device.connect():
        print("ERROR: Failed to connect to device")
        return
    
    print("\n" + "="*70)
    print("HID TRAFFIC MONITOR - ACTIVE")
    print("="*70)
    print(f"\n⏱️  Monitoring for {duration_seconds} seconds...")
    print("\n📋 INSTRUCTIONS:")
    print("   1. Keep this window visible")
    print("   2. Open TRCC software NOW")
    print("   3. Turn ON the RGB in TRCC")
    print("   4. Change colors, modes, etc.")
    print("   5. Watch this window for any captured traffic!")
    print("\n" + "="*70 + "\n")
    
    start_time = time.time()
    packet_count = 0
    captured_packets = []
    
    try:
        while time.time() - start_time < duration_seconds:
            elapsed = int(time.time() - start_time)
            remaining = duration_seconds - elapsed
            
            # Try to read from device
            data = device.read_report(timeout_ms=100)
            
            if data:
                packet_count += 1
                timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                
                print(f"\n🔔 [{timestamp}] PACKET #{packet_count} RECEIVED!")
                print(f"   Length: {len(data)} bytes")
                print(f"   Hex: {data.hex()}")
                print(f"   ASCII: {repr(data)}")
                
                captured_packets.append({
                    'timestamp': timestamp,
                    'data': data.hex()
                })
            
            # Progress indicator
            if elapsed % 5 == 0:
                print(f"⏳ [{elapsed}s / {duration_seconds}s] Listening... ({packet_count} packets captured)", end='\r')
            
            time.sleep(0.05)
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Monitoring stopped by user")
    
    print("\n\n" + "="*70)
    print(f"MONITORING COMPLETE - Captured {packet_count} packets")
    print("="*70 + "\n")
    
    if captured_packets:
        print("📦 CAPTURED PACKETS:\n")
        for i, pkt in enumerate(captured_packets, 1):
            print(f"   [{pkt['timestamp']}] Packet {i}: {pkt['data'][:64]}...")
    else:
        print("❌ No packets captured")
        print("\n💡 This means:")
        print("   - Device doesn't send responses, OR")
        print("   - TRCC uses different communication method, OR")
        print("   - We need to monitor OUTPUT reports (what TRCC sends)")
    
    device.disconnect()
    
    # Save to file
    if captured_packets:
        filename = f"captured_traffic_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(filename, 'w') as f:
            f.write("HID Traffic Capture\n")
            f.write("="*70 + "\n\n")
            for pkt in captured_packets:
                f.write(f"[{pkt['timestamp']}] {pkt['data']}\n")
        print(f"\n💾 Traffic saved to: {filename}")


if __name__ == "__main__":
    import sys
    
    duration = 60
    if len(sys.argv) > 1:
        try:
            duration = int(sys.argv[1])
        except:
            pass
    
    print(f"\nStarting HID monitor for {duration} seconds...")
    print("Press Ctrl+C to stop early\n")
    
    monitor_device(duration)

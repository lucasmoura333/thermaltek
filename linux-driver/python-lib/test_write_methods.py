"""
Test LED control using pywinusb AND direct ctypes WriteFile 
to match exactly what UsbHid.dll does.
Tries multiple approaches:
1. pywinusb send_output_report  
2. pywinusb raw WriteFile via ctypes
3. hidapi write
4. HidD_SetOutputReport via ctypes
"""
import time
import ctypes
from ctypes import wintypes
import struct

VID = 0x0416
PID = 0x8001
MAGIC = bytes([0xDA, 0xDB, 0xDC, 0xDD])

# Build a simple ALL-RED 84-LED packet (matching TRCC's PA120 DIGITAL format)
def make_red_packet():
    """Create header + RGB data for 84 LEDs, ALL RED, brightness 0.4"""
    n_leds = 84
    r_scaled = int(255 * 0.4)  # = 102 = 0x66
    g_scaled = 0
    b_scaled = 0
    rgb_data = bytes([r_scaled, g_scaled, b_scaled] * n_leds)  # 252 bytes
    
    header = bytes([
        0xDA, 0xDB, 0xDC, 0xDD,  # magic
        0x00, 0x00, 0x00, 0x00,  # bytes 4-7
        0x00, 0x00, 0x00, 0x00,  # bytes 8-11
        0x02, 0x00, 0x00, 0x00,  # bytes 12-15
        len(rgb_data) & 0xFF, (len(rgb_data) >> 8) & 0xFF, 0x00, 0x00,  # bytes 16-19
    ])
    return header + rgb_data  # 272 bytes total

def make_blue_packet():
    """Create header + RGB data for 84 LEDs, ALL BLUE, brightness 0.4"""
    n_leds = 84
    r_scaled = 0
    g_scaled = 0
    b_scaled = int(255 * 0.4)  # = 102
    rgb_data = bytes([r_scaled, g_scaled, b_scaled] * n_leds)  # 252 bytes
    
    header = bytes([
        0xDA, 0xDB, 0xDC, 0xDD,
        0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00,
        0x02, 0x00, 0x00, 0x00,
        len(rgb_data) & 0xFF, (len(rgb_data) >> 8) & 0xFF, 0x00, 0x00,
    ])
    return header + rgb_data

def hex_str(data, max_bytes=30):
    s = ' '.join(f'{b:02X}' for b in data[:max_bytes])
    if len(data) > max_bytes:
        s += f' ... ({len(data)} total)'
    return s

# ====== METHOD 1: pywinusb ======
print("=" * 60)
print("METHOD 1: pywinusb send_output_report")
print("=" * 60)
try:
    import pywinusb.hid as pyhid
    
    # Find device
    devices = pyhid.HidDeviceFilter(vendor_id=VID, product_id=PID).get_devices()
    if not devices:
        print("  No device found via pywinusb!")
    else:
        dev = devices[0]
        dev.open()
        print(f"  Opened: {dev.product_name}")
        
        # Send query first
        query = [0x00] + [0xDA, 0xDB, 0xDC, 0xDD, 0x02, 0x00] + [0x00] * 58
        print(f"  Query: {hex_str(bytes(query))}")
        dev.send_output_report(query)
        time.sleep(0.5)
        
        # Send RED LED data in 64-byte chunks
        full_data = make_red_packet()
        print(f"  RED packet: {hex_str(full_data)} ({len(full_data)} bytes)")
        
        offset = 0
        chunk_num = 0
        remaining = len(full_data)
        while remaining > 0:
            chunk_size = min(64, remaining)
            chunk = full_data[offset:offset+chunk_size]
            # Pad to 64 bytes
            padded = list(chunk) + [0] * (64 - len(chunk))
            # Prepend Report ID 0x00
            report = [0x00] + padded  # 65 bytes total
            dev.send_output_report(report)
            chunk_num += 1
            if chunk_num <= 2:
                print(f"  Chunk {chunk_num}: {hex_str(bytes(report[:20]))}")
            offset += chunk_size
            remaining -= chunk_size
        
        print(f"  Sent {chunk_num} chunks. Waiting 3s...")
        time.sleep(3)
        
        # Now try BLUE
        print("  Sending BLUE...")
        full_data = make_blue_packet()
        offset = 0
        remaining = len(full_data)
        while remaining > 0:
            chunk_size = min(64, remaining)
            chunk = full_data[offset:offset+chunk_size]
            padded = list(chunk) + [0] * (64 - len(chunk))
            report = [0x00] + padded
            dev.send_output_report(report)
            offset += chunk_size
            remaining -= chunk_size
        print("  BLUE sent. Waiting 3s...")
        time.sleep(3)
        
        dev.close()
        print("  pywinusb done.")
except Exception as e:
    print(f"  pywinusb error: {e}")

# ====== METHOD 2: Direct ctypes HidD_SetOutputReport ======
print("\n" + "=" * 60)
print("METHOD 2: Direct HidD_SetOutputReport via ctypes")
print("=" * 60)
try:
    kernel32 = ctypes.windll.kernel32
    hid_dll = ctypes.windll.hid
    setupapi = ctypes.windll.setupapi
    
    # Find HID device path
    import hid as hidapi
    dev = hidapi.device()
    dev.open(VID, PID)
    dev_info = dev.get_device_info()
    dev_path = dev_info['path']
    dev.close()
    print(f"  Device path: {dev_path}")
    
    # Open with CreateFile
    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    FILE_SHARE_READ = 1
    FILE_SHARE_WRITE = 2
    OPEN_EXISTING = 3
    FILE_FLAG_OVERLAPPED = 0x40000000
    
    handle = kernel32.CreateFileW(
        dev_path.decode('utf-8') if isinstance(dev_path, bytes) else dev_path,
        GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        0,  # No overlapped I/O, like UsbHid.dll
        None
    )
    
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    if handle == INVALID_HANDLE_VALUE or handle == 0:
        err = kernel32.GetLastError()
        print(f"  CreateFile failed, error {err}")
    else:
        print(f"  Handle opened: {handle}")
        
        # Try HidD_SetOutputReport
        hid_dll.HidD_SetOutputReport.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
        hid_dll.HidD_SetOutputReport.restype = wintypes.BOOL
        
        # Send query via HidD_SetOutputReport
        query_buf = (ctypes.c_ubyte * 65)()
        query_buf[0] = 0x00  # Report ID
        query_data = [0xDA, 0xDB, 0xDC, 0xDD, 0x02, 0x00]
        for i, b in enumerate(query_data):
            query_buf[1 + i] = b
        
        result = hid_dll.HidD_SetOutputReport(handle, query_buf, 65)
        print(f"  HidD_SetOutputReport query result: {result}")
        
        # Try WriteFile directly (like UsbHid.dll)
        print("\n  Trying WriteFile directly (like UsbHid.dll)...")
        
        full_data = make_red_packet()
        offset = 0
        remaining = len(full_data)
        chunk_num = 0
        
        while remaining > 0:
            chunk_size = min(64, remaining)
            chunk = full_data[offset:offset + chunk_size]
            
            # Create 65-byte buffer: Report ID + 64 bytes data (padded)
            write_buf = (ctypes.c_ubyte * 65)()
            write_buf[0] = 0x00  # Report ID
            for i in range(chunk_size):
                write_buf[1 + i] = chunk[i]
            # Remaining bytes are already 0
            
            bytes_written = wintypes.DWORD()
            result = kernel32.WriteFile(
                handle, 
                write_buf, 
                65,  # Length = SendReceivedCount + 1 = 64 + 1 = 65
                ctypes.byref(bytes_written),
                None
            )
            chunk_num += 1
            if chunk_num <= 2:
                data_hex = ' '.join(f'{write_buf[i]:02X}' for i in range(min(20, 65)))
                print(f"  WriteFile chunk {chunk_num}: result={result}, written={bytes_written.value}, data={data_hex}")
            
            offset += chunk_size
            remaining -= chunk_size
        
        print(f"  Sent {chunk_num} chunks via WriteFile. Waiting 3s...")
        time.sleep(3)
        
        kernel32.CloseHandle(handle)
        print("  Handle closed.")
        
except Exception as e:
    import traceback
    print(f"  Error: {e}")
    traceback.print_exc()

# ====== METHOD 3: hidapi ======
print("\n" + "=" * 60)
print("METHOD 3: hidapi (for reference)")
print("=" * 60)
try:
    import hid as hidapi
    dev = hidapi.device()
    dev.open(VID, PID)
    dev.set_nonblocking(1)
    
    full_data = make_red_packet()
    offset = 0
    remaining = len(full_data)
    chunk_num = 0
    
    while remaining > 0:
        chunk_size = min(64, remaining)
        chunk = full_data[offset:offset + chunk_size]
        padded = chunk + bytes(64 - len(chunk))
        pkt = bytes([0x00]) + padded  # 65 bytes
        written = dev.write(pkt)
        chunk_num += 1
        if chunk_num <= 2:
            print(f"  hidapi chunk {chunk_num}: written={written}, data={hex_str(pkt[:20])}")
        offset += chunk_size
        remaining -= chunk_size
    
    print(f"  Sent {chunk_num} chunks via hidapi. Waiting 3s...")
    time.sleep(3)
    dev.close()
    print("  hidapi done.")
except Exception as e:
    print(f"  hidapi error: {e}")

print("\n" + "=" * 60)
print("ALL METHODS COMPLETE. Did any LEDs change?")
print("=" * 60)

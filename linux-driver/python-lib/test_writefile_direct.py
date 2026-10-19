"""
Send LED packets using the EXACT same Win32 API calls as UsbHid.dll:
- Open WriteHandle with CreateFileW(path, GENERIC_WRITE, SHARE_RW, OPEN_EXISTING, flags=0)
- Write via WriteFile(handle, buffer, 65, &written, NULL) -- synchronous, no overlapped
- Also try sending init packet before LED data

This replicates UsbHid.dll's behavior exactly, bypassing hidapi entirely.
"""
import ctypes
from ctypes import wintypes
import time
import sys

VID = 0x0416
PID = 0x8001

# Windows constants
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
INVALID_HANDLE_VALUE = -1

kernel32 = ctypes.windll.kernel32
kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
    ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE
]

# Get device path from hidapi
import hid
devices = hid.enumerate(VID, PID)
if not devices:
    print("No HID device found!")
    sys.exit(1)

dev_path = devices[0]['path']
if isinstance(dev_path, bytes):
    dev_path = dev_path.decode('utf-8')

print(f"Device path: {dev_path}")
print(f"Usage Page: {devices[0]['usage_page']:#06x}")
print(f"Interface: {devices[0].get('interface_number', 'N/A')}")
print()

def hex_str(data, n=30):
    s = ' '.join(f'{b:02X}' for b in data[:n])
    if len(data) > n:
        s += f' ... ({len(data)} total)'
    return s

def write_hid_report(handle, data_64_bytes):
    """Write a single 65-byte HID output report (Report ID 0x00 + 64 bytes data)"""
    buf = (ctypes.c_ubyte * 65)()
    buf[0] = 0x00  # Report ID
    for i, b in enumerate(data_64_bytes[:64]):
        buf[1 + i] = b
    
    bytes_written = wintypes.DWORD()
    result = kernel32.WriteFile(
        handle, buf, 65,
        ctypes.byref(bytes_written),
        None  # No OVERLAPPED - synchronous, like UsbHid.dll
    )
    return result, bytes_written.value

def send_chunked(handle, data, label=""):
    """Send data in 64-byte chunks, exactly like ThreadSendDeviceData1"""
    offset = 0
    remaining = len(data)
    chunk_num = 0
    
    while remaining > 0:
        if remaining > 64:
            chunk = data[offset:offset+64]
            remaining -= 64
            offset += 64
        else:
            # Last chunk: NOT padded (device pads internally via CommandMessage's 513-byte buffer)
            # Actually - WriteFile always sends 65 bytes, so padding happens there
            chunk = data[offset:offset+remaining]
            chunk = chunk + bytes(64 - len(chunk))  # pad to 64
            remaining = 0
        
        result, written = write_hid_report(handle, chunk)
        chunk_num += 1
        if chunk_num <= 3 or remaining == 0:
            print(f"  {label} chunk {chunk_num}: result={result}, written={written}, data={hex_str(chunk, 20)}")
    
    return chunk_num

# ================================================================
# METHOD A: Open EXACTLY like UsbHid.dll - GENERIC_WRITE only, no overlapped
# ================================================================
print("=" * 60)
print("METHOD A: WriteHandle = CreateFileW(GENERIC_WRITE, no overlapped)")
print("=" * 60)

write_handle = kernel32.CreateFileW(
    dev_path,
    GENERIC_WRITE,           # UsbHid.dll uses GENERIC_WRITE only for write handle
    FILE_SHARE_READ | FILE_SHARE_WRITE,
    None,
    OPEN_EXISTING,
    0,                        # NO FILE_FLAG_OVERLAPPED
    None
)

if write_handle == ctypes.c_void_p(INVALID_HANDLE_VALUE).value or write_handle == 0:
    err = kernel32.GetLastError()
    print(f"  CreateFileW failed! Error: {err}")
    print("  Trying with GENERIC_READ|GENERIC_WRITE instead...")
    write_handle = kernel32.CreateFileW(
        dev_path,
        GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        0,
        None
    )
    if write_handle == ctypes.c_void_p(INVALID_HANDLE_VALUE).value or write_handle == 0:
        err = kernel32.GetLastError()
        print(f"  Still failed! Error: {err}")
        sys.exit(1)

print(f"  Handle opened: {write_handle}")

# Step 1: Send init packet (DeviceOnConnected1)
print("\n--- Step 1: Init packet ---")
init_data = bytes([
    0xDA, 0xDB, 0xDC, 0xDD,
    0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00,
    0x01, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00,
]) + bytes(44)  # pad to 64

result, written = write_hid_report(write_handle, init_data)
print(f"  Init sent: result={result}, written={written}")
print(f"  Data: {hex_str(init_data, 20)}")
time.sleep(0.5)

# Step 2: Read response (need overlapped read handle for this)
print("\n--- Step 2: Reading response ---")
read_handle = kernel32.CreateFileW(
    dev_path,
    GENERIC_READ,
    FILE_SHARE_READ | FILE_SHARE_WRITE,
    None,
    OPEN_EXISTING,
    FILE_FLAG_OVERLAPPED,  # UsbHid.dll uses overlapped for reading
    None
)

if read_handle != ctypes.c_void_p(INVALID_HANDLE_VALUE).value and read_handle != 0:
    # Create OVERLAPPED structure for async read
    class OVERLAPPED(ctypes.Structure):
        _fields_ = [
            ("Internal", ctypes.POINTER(ctypes.c_ulong)),
            ("InternalHigh", ctypes.POINTER(ctypes.c_ulong)),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        ]
    
    ol = OVERLAPPED()
    ol.hEvent = kernel32.CreateEventW(None, True, False, None)
    
    read_buf = (ctypes.c_ubyte * 65)()
    bytes_read = wintypes.DWORD()
    
    result = kernel32.ReadFile(
        read_handle, read_buf, 65,
        ctypes.byref(bytes_read), ctypes.byref(ol)
    )
    
    # Wait for read to complete (timeout 2 seconds)
    wait_result = kernel32.WaitForSingleObject(ol.hEvent, 2000)
    if wait_result == 0:  # WAIT_OBJECT_0
        kernel32.GetOverlappedResult(read_handle, ctypes.byref(ol), ctypes.byref(bytes_read), False)
        response = bytes(read_buf[:bytes_read.value])
        print(f"  Response ({bytes_read.value} bytes): {hex_str(response)}")
    else:
        print(f"  No response within 2s (wait_result={wait_result})")
    
    kernel32.CloseHandle(ol.hEvent)
else:
    print("  Could not open read handle")

# Step 3: Send RED LED data
print("\n--- Step 3: RED LED data (84 LEDs) ---")
brightness = 0.4
r_val = int(255 * brightness)

rgb_data = bytes([r_val, 0, 0] * 84)  # 252 bytes, ALL RED
header = bytes([
    0xDA, 0xDB, 0xDC, 0xDD,
    0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00,
    0x02, 0x00, 0x00, 0x00,
    0xFC, 0x00, 0x00, 0x00,  # data length = 252 = 0xFC
])

full_packet = header + rgb_data  # 272 bytes
print(f"  Packet size: {len(full_packet)} bytes")
n_chunks = send_chunked(write_handle, full_packet, "RED")
print(f"  Sent {n_chunks} chunks")

print("\n  Waiting 5 seconds - CHECK LED COLOR!")
time.sleep(5)

# Step 4: BLUE
print("\n--- Step 4: BLUE LED data ---")
rgb_data = bytes([0, 0, int(255 * brightness)] * 84)
header = bytes([
    0xDA, 0xDB, 0xDC, 0xDD,
    0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00,
    0x02, 0x00, 0x00, 0x00,
    0xFC, 0x00, 0x00, 0x00,
])
full_packet = header + rgb_data
n_chunks = send_chunked(write_handle, full_packet, "BLUE")
print(f"  Sent {n_chunks} chunks")
print("  Waiting 5 seconds...")
time.sleep(5)

# Step 5: GREEN  
print("\n--- Step 5: GREEN LED data ---")
rgb_data = bytes([0, int(255 * brightness), 0] * 84)
header = bytes([
    0xDA, 0xDB, 0xDC, 0xDD,
    0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00,
    0x02, 0x00, 0x00, 0x00,
    0xFC, 0x00, 0x00, 0x00,
])
full_packet = header + rgb_data
n_chunks = send_chunked(write_handle, full_packet, "GREEN")
print(f"  Sent {n_chunks} chunks")
print("  Waiting 5 seconds...")
time.sleep(5)

# Cleanup
kernel32.CloseHandle(write_handle)
if read_handle != ctypes.c_void_p(INVALID_HANDLE_VALUE).value:
    kernel32.CloseHandle(read_handle)

print("\n" + "=" * 60)
print("METHOD A COMPLETE. Did LEDs change color?")
print("=" * 60)

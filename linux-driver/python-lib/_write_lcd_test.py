"""Write raw pixel data to shareMemory_ImageRGB (no header).
SHM is raw 480x480x3 RGB24 pixel data at byte 0 — no header.
"""
import ctypes, ctypes.wintypes, struct, sys

FILE_MAP_READ = 0x0004
FILE_MAP_WRITE = 0x0002
FILE_MAP_ALL = 0x000F001F
kernel32 = ctypes.windll.kernel32
kernel32.OpenFileMappingW.restype = ctypes.wintypes.HANDLE
kernel32.MapViewOfFile.restype = ctypes.c_void_p
kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]

SHM_NAME = 'shareMemory_ImageRGB'
FRAME_SIZE = 480 * 480 * 3  # 691200
TOTAL_SIZE = 64 + FRAME_SIZE  # 691264

# Open for write to test writing
h = kernel32.OpenFileMappingW(FILE_MAP_ALL, False, SHM_NAME)
if not h:
    print('Cannot open SHM for write, trying read')
    h = kernel32.OpenFileMappingW(FILE_MAP_READ, False, SHM_NAME)
    write_ok = False
else:
    write_ok = True

print('handle=%d write=%s err=%d' % (h, write_ok, kernel32.GetLastError()))

if not h:
    sys.exit(1)

# Map full SHM
ptr = kernel32.MapViewOfFile(h, FILE_MAP_ALL if write_ok else FILE_MAP_READ, 0, 0, TOTAL_SIZE)
if not ptr:
    print('MapViewOfFile failed err=%d, trying smaller size' % kernel32.GetLastError())
    ptr = kernel32.MapViewOfFile(h, FILE_MAP_ALL if write_ok else FILE_MAP_READ, 0, 0, 1024)
    TOTAL_SIZE = 1024

print('ptr=0x%x' % ptr)

buf = (ctypes.c_uint8 * TOTAL_SIZE).from_address(ptr)
data = bytes(buf)

# Find first non-zero region
print('\nScanning for non-zero data...')
found = False
for i in range(0, min(len(data), 200000), 64):
    chunk = data[i:i+64]
    if any(b != 0 for b in chunk):
        print('Non-zero at offset %d: %s' % (i, ' '.join('%02x' % b for b in chunk[:16])))
        found = True
        if i > 512:
            break 

if not found:
    print('First %d bytes are all zero' % min(len(data), 200000))

# What's the current SHM size? Check if TRCC created it with specific size
print('\nTotal bytes mapped: %d' % len(data))

# Try writing a test frame (solid red image)
if write_ok and ptr:
    print('\nWriting test frame (solid red 480x480)...')
    buf = (ctypes.c_uint8 * TOTAL_SIZE).from_address(ptr)
    
    # Build header: magic 12 34 56 78, zeros, data_size at [60:64] as big-endian
    hdr = bytearray(64)
    hdr[0:4] = bytes([0x12, 0x34, 0x56, 0x78])  # magic
    struct.pack_into('>I', hdr, 60, FRAME_SIZE)   # pixel data size at [60:64] BE
    
    # Write header
    for i, b in enumerate(hdr):
        buf[i] = b
    
    # Write red pixels (R=255, G=0, B=0)
    print('Writing %d pixel bytes...' % FRAME_SIZE)
    for i in range(FRAME_SIZE // 3):
        buf[64 + i*3 + 0] = 255  # R
        buf[64 + i*3 + 1] = 0    # G
        buf[64 + i*3 + 2] = 0    # B
    
    print('Write complete! Check the LCD display...')
    print('Header written:')
    for i in range(0, 64, 16):
        row = [buf[j] for j in range(i, i+16)]
        print('  %02x: %s' % (i, ' '.join('%02x' % b for b in row)))
    
    import time
    print('Waiting 5s with red frame...')
    time.sleep(5)
    
    # Write blank
    for i in range(TOTAL_SIZE):
        buf[i] = 0
    print('Cleared SHM')

kernel32.UnmapViewOfFile(ptr)
kernel32.CloseHandle(h)

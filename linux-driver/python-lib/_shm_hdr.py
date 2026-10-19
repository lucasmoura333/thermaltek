import ctypes, ctypes.wintypes, struct, sys

FILE_MAP_READ = 0x0004
FILE_MAP_WRITE = 0x0002
kernel32 = ctypes.windll.kernel32

# Fix return types for 64-bit
kernel32.OpenFileMappingW.restype = ctypes.wintypes.HANDLE
kernel32.MapViewOfFile.restype = ctypes.c_void_p
kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]

SHM_NAME = 'shareMemory_ImageRGB'
h = kernel32.OpenFileMappingW(FILE_MAP_READ, False, SHM_NAME)
print('handle=%d err=%d' % (h, kernel32.GetLastError()))

if not h:
    sys.exit(1)

ptr = kernel32.MapViewOfFile(h, FILE_MAP_READ, 0, 0, 64)
print('ptr=%d' % ptr)

if ptr:
    buf = (ctypes.c_uint8 * 64).from_address(ptr)
    hdr = bytes(buf)
    kernel32.UnmapViewOfFile(ptr)
    print('Header hex:')
    for i in range(0, 64, 16):
        row = hdr[i:i+16]
        print('  %02x: %s' % (i, ' '.join('%02x' % b for b in row)))
    
    # Check size at various offsets
    print('Sizes at each 4-byte offset:')
    for off in range(0, 64, 4):
        v_le = struct.unpack_from('<I', hdr, off)[0]
        v_be = struct.unpack_from('>I', hdr, off)[0]
        marker = ''
        if v_le == 691200: marker = ' <-- 480x480x3 LE'
        if v_be == 691200: marker = ' <-- 480x480x3 BE'
        if v_le == 460800: marker = ' <-- 480x480x2 LE'  
        if v_be == 460800: marker = ' <-- 480x480x2 BE'
        print('  [%d]: LE=%d BE=%d%s' % (off, v_le, v_be, marker))

kernel32.CloseHandle(h)

"""Read shareMemory_ImageRGB header while TRCC is running."""
import ctypes
import ctypes.wintypes
import struct
import sys

INVALID_HANDLE_VALUE = ctypes.wintypes.HANDLE(-1).value
FILE_MAP_READ  = 0x0004
FILE_MAP_WRITE = 0x0002
FILE_MAP_ALL_ACCESS = 0xF001F

kernel32 = ctypes.windll.kernel32

def open_shm(name, size=0, write=False):
    access = FILE_MAP_WRITE if write else FILE_MAP_READ
    h = kernel32.OpenFileMappingW(access, False, name)
    if not h:
        err = kernel32.GetLastError()
        return None, None, err
    if size == 0:
        size = 1024  # probe
    ptr = kernel32.MapViewOfFile(h, access, 0, 0, size)
    if not ptr:
        kernel32.CloseHandle(h)
        err = kernel32.GetLastError()
        return None, None, err
    return h, ptr, 0

# Try to open SHM with increasing sizes
SHM_NAME = 'shareMemory_ImageRGB'

# First, probe with 64 bytes to read header
h, ptr, err = open_shm(SHM_NAME, 64, write=False)
if not h:
    print('Failed to open SHM "%s": error %d' % (SHM_NAME, err))
    print('Is TRCC running? Try starting TRCC first.')
    sys.exit(1)

header = (ctypes.c_uint8 * 64).from_address(ptr)
hdr = bytes(header)
kernel32.UnmapViewOfFile(ptr)
kernel32.CloseHandle(h)

print('=== shareMemory_ImageRGB header (64 bytes) ===')
for i in range(0, 64, 16):
    row = hdr[i:i+16]
    hex_str = ' '.join('%02x' % b for b in row)
    ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in row)
    print('  %04x: %-47s  |%s|' % (i, hex_str, ascii_str))

# Parse known fields
magic = hdr[0:4]
print('\nMagic bytes: %s' % ' '.join('%02x' % b for b in magic))

# Check pixel data size at bytes 60-63 (big-endian per IL analysis)
size_be = struct.unpack_from('>I', hdr, 60)[0]
size_le = struct.unpack_from('<I', hdr, 60)[0]
print('Bytes[60:64] as big-endian uint32: %d (0x%x)' % (size_be, size_be))
print('Bytes[60:64] as little-endian uint32: %d (0x%x)' % (size_le, size_le))
print('480*480*3 = %d' % (480*480*3))

# If size_be looks valid (close to 691200), verify
if 0 < size_be <= 2_000_000:
    total = size_be + 64
    print('\nTotal transfer size = %d + 64 = %d bytes' % (size_be, total))
    
    # Now read the full SHM
    h2, ptr2, err2 = open_shm(SHM_NAME, total, write=False)
    if h2:
        buf = (ctypes.c_uint8 * total).from_address(ptr2)
        data = bytes(buf)
        kernel32.UnmapViewOfFile(ptr2)
        kernel32.CloseHandle(h2)
        
        pixel_start = 64
        if len(data) > pixel_start + 16:
            first_pixels = data[pixel_start:pixel_start+48]
            print('\nFirst 16 pixels (RGB24):')
            for i in range(16):
                r, g, b = first_pixels[i*3], first_pixels[i*3+1], first_pixels[i*3+2]
                print('  pixel %2d: R=%3d G=%3d B=%3d' % (i, r, g, b))
        print('\nSHM size read OK: %d bytes' % total)
    else:
        print('Could not open SHM with size %d: error %d' % (total, err2))
elif 0 < size_le <= 2_000_000:
    print('\n(Using little-endian: total = %d + 64 = %d)' % (size_le, size_le + 64))
else:
    print('\nBytes[60:64] not a valid pixel data size.')
    print('Checking other offsets for pixel data size...')
    for off in range(0, 64, 4):
        val_be = struct.unpack_from('>I', hdr, off)[0]
        val_le = struct.unpack_from('<I', hdr, off)[0]
        if val_be == 480*480*3 or val_le == 480*480*3:
            print('  Found 691200 at offset %d (%s endian)' % (
                off, 'big' if val_be == 480*480*3 else 'little'))
        if val_be == 480*480*2 or val_le == 480*480*2:
            print('  Found 460800 (RGB565) at offset %d (%s endian)' % (
                off, 'big' if val_be == 480*480*2 else 'little'))

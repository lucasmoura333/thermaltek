"""Test LCD SHM write - raw pixel data, no header."""
import ctypes
import ctypes.wintypes
import sys
import time

FILE_MAP_ALL = 0x000F001F
kernel32 = ctypes.windll.kernel32
kernel32.OpenFileMappingW.restype = ctypes.wintypes.HANDLE
kernel32.MapViewOfFile.restype = ctypes.c_void_p
kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]

SHM_NAME = 'shareMemory_ImageRGB'
FRAME_SIZE = 480 * 480 * 3  # 691200 raw RGB24

h = kernel32.OpenFileMappingW(FILE_MAP_ALL, False, SHM_NAME)
if not h:
    print('Cannot open SHM err=%d' % kernel32.GetLastError())
    sys.exit(1)

ptr = kernel32.MapViewOfFile(h, FILE_MAP_ALL, 0, 0, FRAME_SIZE)
if not ptr:
    print('MapViewOfFile failed err=%d' % kernel32.GetLastError())
    sys.exit(1)

print('SHM opened ptr=0x%x size=%d' % (ptr, FRAME_SIZE))
buf = (ctypes.c_uint8 * FRAME_SIZE).from_address(ptr)

print('Writing solid RED (255,0,0) at bytes 0...')
for i in range(480 * 480):
    buf[i * 3 + 0] = 255
    buf[i * 3 + 1] = 0
    buf[i * 3 + 2] = 0
print('RED written. Check LCD for 5s...')
time.sleep(5)

print('Writing X/Y gradient...')
for y in range(480):
    for x in range(480):
        idx = (y * 480 + x) * 3
        buf[idx + 0] = x * 255 // 479
        buf[idx + 1] = y * 255 // 479
        buf[idx + 2] = 128
print('Gradient written. Check LCD for 5s...')
time.sleep(5)

print('Clearing...')
for i in range(FRAME_SIZE):
    buf[i] = 0

kernel32.UnmapViewOfFile(ptr)
kernel32.CloseHandle(h)
print('Done.')

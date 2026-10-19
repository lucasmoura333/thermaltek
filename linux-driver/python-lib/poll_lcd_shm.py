#!/usr/bin/env python3
"""
Continuously poll TRCC shared memory and dump non-zero content.
shareMemory_SysInfo likely has CPU/GPU temp/usage as plain numbers.
"""
import ctypes, ctypes.wintypes, time, struct

kernel32 = ctypes.windll.kernel32
FILE_MAP_READ = 0x0004

def read_shm(name, size=65536):
    h = kernel32.OpenFileMappingW(FILE_MAP_READ, False, name)
    if not h:
        return None
    view = kernel32.MapViewOfFile(h, FILE_MAP_READ, 0, 0, size)
    data = None
    if view:
        try:
            buf = (ctypes.c_byte * size)()
            ctypes.memmove(buf, view, size)
            data = bytes(buf)
        except OSError:
            pass
        kernel32.UnmapViewOfFile(view)
    kernel32.CloseHandle(h)
    return data

print("Polling shareMemory_SysInfo for 10 seconds... (TRCC must be open)")
print("Press Ctrl+C to stop early\n")

last = None
deadline = time.time() + 10
try:
    while time.time() < deadline:
        for name in ("shareMemory_SysInfo", "shareMemory_ImageRGB", "shareMemory_Image"):
            d = read_shm(name, 256 * 1024)
            if d is None:
                continue
            nz = sum(1 for b in d if b != 0)
            if nz > 0 and d != last:
                last = d
                last_nz = max(i for i, b in enumerate(d) if b != 0)
                print(f"[{name}] nonzero={nz} last_nz_offset={last_nz}")
                print(f"  bytes 0-63:    {d[:64].hex()}")
                print(f"  bytes 64-127:  {d[64:128].hex()}")
                # Try to interpret as floats and ints
                if nz >= 16:
                    try:
                        floats = struct.unpack_from('<' + 'f' * min(16, last_nz // 4), d)
                        print(f"  as float32:    {[round(f,1) for f in floats]}")
                        ints   = struct.unpack_from('<' + 'I' * min(16, last_nz // 4), d)
                        print(f"  as uint32:     {list(ints)}")
                    except struct.error:
                        pass
                print()
        time.sleep(0.01)
except KeyboardInterrupt:
    pass
print("Done")

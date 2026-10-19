import sys, ctypes, ctypes.wintypes as wt

k32 = ctypes.windll.kernel32
OpenFileMapping = k32.OpenFileMappingW
OpenFileMapping.restype = wt.HANDLE
MapViewOfFile = k32.MapViewOfFile
MapViewOfFile.restype = ctypes.c_void_p
MapViewOfFile.argtypes = [wt.HANDLE, wt.DWORD, wt.DWORD, wt.DWORD, ctypes.c_size_t]
UnmapViewOfFile = k32.UnmapViewOfFile
UnmapViewOfFile.argtypes = [ctypes.c_void_p]
CloseHandle = k32.CloseHandle
FILE_MAP_READ = 4

h = OpenFileMapping(FILE_MAP_READ, False, 'shareMemory_SysInfo')
if not h:
    print('Not found'); exit()
view = MapViewOfFile(h, FILE_MAP_READ, 0, 0, 65536)
CloseHandle(h)
if not view:
    print('Map failed'); exit()
buf = (ctypes.c_ubyte * 65536)()
ctypes.memmove(buf, view, 65536)
UnmapViewOfFile(view)
data = bytes(buf)
text = data.decode('utf-8', errors='replace')
end = text.find('\x00\x00\x00\x00\x00')
if end < 0: end = 8192
print(text[:end])

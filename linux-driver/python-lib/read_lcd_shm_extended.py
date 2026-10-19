"""
read_lcd_shm_extended.py
Dump Nuvoton TRCC shared memory sections to disk for analysis.
Requires TRCC.exe to be running (it creates the named file mappings).
"""

import ctypes
import time
import struct
import subprocess
import sys
from ctypes import wintypes

# ── Find TRCC PID ────────────────────────────────────────────────────────────

def get_trcc_pid():
    result = subprocess.run(
        ['powershell', '-NoProfile', '-c',
         '(Get-Process -Name TRCC -ErrorAction SilentlyContinue).Id'],
        capture_output=True, text=True
    )
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None

pid = get_trcc_pid()
if not pid:
    print("[-] TRCC not running. Start TRCC.exe first, then re-run this script.")
    sys.exit(1)

print(f"[+] TRCC PID: {pid}")

# ── Windows API setup ────────────────────────────────────────────────────────

kernel32 = ctypes.windll.kernel32
ntdll    = ctypes.cdll.ntdll

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_DUP_HANDLE        = 0x0040
FILE_MAP_READ             = 0x0004
DUPLICATE_SAME_ACCESS     = 0x0002

OpenProcess      = kernel32.OpenProcess
OpenProcess.restype = wintypes.HANDLE
OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]

DuplicateHandle  = kernel32.DuplicateHandle
DuplicateHandle.restype = wintypes.BOOL

MapViewOfFile    = kernel32.MapViewOfFile
MapViewOfFile.restype = ctypes.c_void_p
MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                           wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]

UnmapViewOfFile  = kernel32.UnmapViewOfFile
UnmapViewOfFile.argtypes = [ctypes.c_void_p]
UnmapViewOfFile.restype  = wintypes.BOOL

CloseHandle      = kernel32.CloseHandle
CloseHandle.argtypes = [wintypes.HANDLE]
CloseHandle.restype  = wintypes.BOOL
GetCurrentProcess = kernel32.GetCurrentProcess
GetCurrentProcess.restype = wintypes.HANDLE

# ── NtQuerySystemInformation handles table ───────────────────────────────────

class SYSTEM_HANDLE_ENTRY(ctypes.Structure):
    _fields_ = [
        ("OwnerPid",        wintypes.ULONG),
        ("ObjectTypeNumber",ctypes.c_ubyte),
        ("HandleAttributes",ctypes.c_ubyte),
        ("HandleValue",     wintypes.USHORT),
        ("Object",          ctypes.c_void_p),
        ("GrantedAccess",   wintypes.ULONG),
    ]

class SYSTEM_HANDLE_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("NumberOfHandles", wintypes.ULONG),
        ("Handles",         SYSTEM_HANDLE_ENTRY * 1),
    ]

SystemHandleInformation = 16

def query_all_handles():
    size = ctypes.c_ulong(0x10000)
    while True:
        buf = ctypes.create_string_buffer(size.value)
        status = ntdll.NtQuerySystemInformation(
            SystemHandleInformation, buf, size, ctypes.byref(size))
        if status == 0:
            break
        if status != 0xC0000004:   # STATUS_INFO_LENGTH_MISMATCH
            print(f"[-] NtQuerySystemInformation failed: 0x{status:08x}")
            return None
    return ctypes.cast(buf, ctypes.POINTER(SYSTEM_HANDLE_INFORMATION)).contents

# ── Open named file mapping directly (fast path) ────────────────────────────

def open_named_mapping(name, size=512 * 1024):
    """Try to open a named section by name directly."""
    OpenFileMapping = kernel32.OpenFileMappingW
    OpenFileMapping.restype = wintypes.HANDLE
    OpenFileMapping.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]

    handle = OpenFileMapping(FILE_MAP_READ, False, name)
    if not handle or handle == wintypes.HANDLE(-1).value:
        return None

    ptr = MapViewOfFile(handle, FILE_MAP_READ, 0, 0, size)
    if not ptr:
        CloseHandle(handle)
        return None

    data = ctypes.string_at(ptr, size)
    UnmapViewOfFile(ptr)
    CloseHandle(handle)
    return data

# ── Fallback: brute-force via handle table ───────────────────────────────────

def dump_via_handle_table(section_names, size=512 * 1024):
    found = {}
    hinfo = query_all_handles()
    if not hinfo:
        return found

    src_proc = OpenProcess(PROCESS_DUP_HANDLE | PROCESS_QUERY_INFORMATION,
                           False, pid)
    if not src_proc:
        print(f"[-] OpenProcess failed: {ctypes.GetLastError()}")
        return found

    my_proc = GetCurrentProcess()
    total   = hinfo.NumberOfHandles
    print(f"[*] Scanning {total} system handles for PID {pid}...")

    for i in range(total):
        h = hinfo.Handles[i]
        if h.OwnerPid != pid:
            continue

        dup = wintypes.HANDLE(0)
        ok  = DuplicateHandle(src_proc, wintypes.HANDLE(h.HandleValue),
                              my_proc, ctypes.byref(dup),
                              FILE_MAP_READ, False, 0)
        if not ok:
            continue

        try:
            ptr = MapViewOfFile(dup, FILE_MAP_READ, 0, 0, size)
            if not ptr:
                CloseHandle(dup)
                continue

            data = ctypes.string_at(ptr, size)
            UnmapViewOfFile(ptr)
            nonzero = sum(1 for b in data if b != 0)

            if nonzero > 0:
                # Try to identify by content
                for name in section_names:
                    if name not in found:
                        found[name] = data
                        print(f"[+] Captured handle → assigned as '{name}' ({nonzero} non-zero bytes)")
                        break
        except Exception:
            pass
        finally:
            CloseHandle(dup)

        if len(found) == len(section_names):
            break

    CloseHandle(src_proc)
    return found

# ── Main ─────────────────────────────────────────────────────────────────────

SECTIONS = [
    "shareMemory_ImageRGB",
    "shareMemory_Image",
    "shareMemory_SysInfo",
]

SHM_SIZE = 512 * 1024   # 512 KB per section

results = {}

# Fast path first
for name in SECTIONS:
    print(f"[*] Opening '{name}' directly...")
    data = open_named_mapping(name, SHM_SIZE)
    if data is not None:
        nonzero = sum(1 for b in data if b != 0)
        print(f"[+] '{name}': {nonzero} non-zero bytes")
        results[name] = data
    else:
        print(f"[-] Direct open failed for '{name}' — will try handle table")

# Fallback for any not found
missing = [n for n in SECTIONS if n not in results]
if missing:
    fallback = dump_via_handle_table(missing, SHM_SIZE)
    results.update(fallback)

# ── Save results ──────────────────────────────────────────────────────────────

timestamp = time.strftime("%Y%m%d_%H%M%S")

for name, buf in results.items():
    nonzero = sum(1 for b in buf if b != 0)
    header32 = buf[:32]
    hex_header = ' '.join(f'{b:02x}' for b in buf[:64])

    print(f"\n── {name} ──")
    print(f"   Non-zero bytes : {nonzero}")
    print(f"   Header (64B)   : {hex_header}")

    # Bytes 60-63: predicted JPEG size field (from IL analysis)
    if len(buf) >= 64:
        jpeg_size_field = struct.unpack_from('<I', buf, 60)[0]
        print(f"   Bytes[60:64]   : {jpeg_size_field} (0x{jpeg_size_field:x})")

    # Detect format
    if buf[:2] == b'\xff\xd8':
        fname = f"{name}_{timestamp}.jpg"
        print(f"   Format         : JPEG (FF D8 header)")
    elif buf[:4] == b'\x12\x34\x56\x78':
        fname = f"{name}_{timestamp}.bin"
        print(f"   Format         : LCD packet header (12 34 56 78)")
        # If JPEG starts at offset 64
        if buf[64:66] == b'\xff\xd8':
            jpeg_data = buf[64:64 + jpeg_size_field] if jpeg_size_field else buf[64:]
            jname = f"{name}_{timestamp}_embedded.jpg"
            with open(jname, 'wb') as f:
                f.write(jpeg_data)
            print(f"   [✓] Embedded JPEG saved: {jname}")
    else:
        fname = f"{name}_{timestamp}.bin"
        print(f"   Format         : Unknown binary")

    with open(fname, 'wb') as f:
        f.write(buf)
    print(f"   [✓] Saved: {fname}")

print("\n[✓] Done. Check files in current directory.")
print("    Validate: expected header  12 34 56 78 02 00 00 00 f0 00 00 00 f0 00 00 00")

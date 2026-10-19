#!/usr/bin/env python3
"""
Read TRCC's shared memory while TRCC is running.
Also enumerates ALL named sections open in TRCC's process to find the real name.

Run this while TRCC is open and showing CPU/GPU data.
"""
import ctypes, ctypes.wintypes, sys, os, struct

kernel32  = ctypes.windll.kernel32
ntdll     = ctypes.windll.ntdll
psapi     = ctypes.windll.psapi

INVALID_HANDLE_VALUE = ctypes.wintypes.HANDLE(-1).value
FILE_MAP_READ  = 0x0004
PROCESS_DUP_HANDLE = 0x0040
PROCESS_QUERY_INFORMATION = 0x0400
OBJECT_TYPE_AS_FILE = 27   # Section object type index (varies by OS)

# ── safe memmove that can't crash on race condition ───────────────────────
def try_read_view(view_addr: int, size: int) -> bytes | None:
    """Attempt to read from a mapped view.  Returns None on access violation."""
    try:
        buf = (ctypes.c_byte * size)()
        ctypes.memmove(buf, view_addr, size)
        return bytes(buf)
    except OSError:
        return None

def read_shm(name: str, size: int = 65536) -> bytes | None:
    h = kernel32.OpenFileMappingW(FILE_MAP_READ, False, name)
    if not h or h == ctypes.wintypes.HANDLE(-1).value:
        return None  # not found
    print(f"  FOUND section: {name!r}")
    view = kernel32.MapViewOfFile(h, FILE_MAP_READ, 0, 0, size)
    data = None
    if view:
        data = try_read_view(view, size)
        kernel32.UnmapViewOfFile(view)
    kernel32.CloseHandle(h)
    return data

# ── enumerate all named sections in TRCC process ──────────────────────────
def find_trcc_pid() -> int | None:
    import subprocess
    out = subprocess.check_output(
        ['tasklist', '/FI', 'IMAGENAME eq TRCC.exe', '/FO', 'CSV', '/NH'],
        text=True, stderr=subprocess.DEVNULL
    )
    for line in out.strip().splitlines():
        parts = line.strip('"').split('","')
        if parts and 'TRCC' in parts[0]:
            try:
                return int(parts[1])
            except (ValueError, IndexError):
                pass
    return None

SYSTEM_HANDLE_INFORMATION = 16

class SYSTEM_HANDLE_ENTRY(ctypes.Structure):
    _fields_ = [
        ('OwnerPid',   ctypes.c_ulong),
        ('ObjectType', ctypes.c_byte),
        ('Flags',      ctypes.c_byte),
        ('Handle',     ctypes.c_ushort),
        ('Object',     ctypes.c_void_p),
        ('Access',     ctypes.c_ulong),
    ]

def enum_process_sections(pid: int) -> list[str]:
    """Return list of named section object names open in the given process."""
    # Call NtQuerySystemInformation to get all handles
    buf_size = 1024 * 1024  # 1MB, grow if needed
    for _ in range(4):
        buf = (ctypes.c_byte * buf_size)()
        ret_len = ctypes.c_ulong(0)
        status = ntdll.NtQuerySystemInformation(
            SYSTEM_HANDLE_INFORMATION,
            ctypes.byref(buf), buf_size, ctypes.byref(ret_len)
        )
        if status == 0:
            break
        buf_size *= 2
    else:
        return []

    # Parse: first ULONG = count, then array of SYSTEM_HANDLE_ENTRY
    count = struct.unpack_from('<I', buf, 0)[0]
    entry_size = ctypes.sizeof(SYSTEM_HANDLE_ENTRY)
    entries = []
    off = 4
    for _ in range(count):
        e = SYSTEM_HANDLE_ENTRY.from_buffer(buf, off)
        if e.OwnerPid == pid:
            entries.append((e.ObjectType, e.Handle))
        off += entry_size

    if not entries:
        return []

    # Open TRCC process to duplicate handles
    hproc = kernel32.OpenProcess(PROCESS_DUP_HANDLE | PROCESS_QUERY_INFORMATION, False, pid)
    if not hproc:
        print(f"  Cannot open TRCC process (error {kernel32.GetLastError()}) — run as Administrator?")
        return []

    names = set()
    current_proc = kernel32.GetCurrentProcess()
    for obj_type, handle in entries:
        dup = ctypes.wintypes.HANDLE()
        ok = kernel32.DuplicateHandle(
            hproc, ctypes.wintypes.HANDLE(handle),
            current_proc, ctypes.byref(dup),
            0, False, 2  # DUPLICATE_SAME_ACCESS
        )
        if not ok:
            continue
        # Query object name
        buf2 = (ctypes.c_byte * 1024)()
        ret2 = ctypes.c_ulong(0)
        status2 = ntdll.NtQueryObject(dup, 1, ctypes.byref(buf2), 1024, ctypes.byref(ret2))
        kernel32.CloseHandle(dup)
        if status2 != 0:
            continue
        # UNICODE_STRING: Length(2), MaxLen(2), Ptr(8 on x64)
        try:
            length = struct.unpack_from('<H', buf2, 0)[0]
            ptr_offset = 8  # 64-bit
            raw = bytes(buf2[ptr_offset:ptr_offset + length])
            name = raw.decode('utf-16-le', errors='replace')
            if name:
                names.add(name)
        except Exception:
            pass

    kernel32.CloseHandle(hproc)
    return sorted(names)


# ── main ──────────────────────────────────────────────────────────────────

names_to_try = [
    "shareMemory_ImageRGB",
    "shareMemory_Image",
    "shareMemory_SysInfo",
    "Global\\shareMemory_ImageRGB",
    "Global\\shareMemory_Image",
    "Global\\shareMemory_SysInfo",
    "D0rgblf13",
    "Local\\shareMemory_ImageRGB",
    "A1KVMALEDC6",
    "A1KVMALEDC6a",
]

print("=" * 60)
print("Reading TRCC shared memory... (TRCC must be running)")
print("=" * 60)

# Phase 1: enumerate handles in TRCC process
trcc_pid = find_trcc_pid()
if trcc_pid:
    print(f"\nTRCC PID: {trcc_pid}")
    print("Enumerating TRCC's named objects...")
    section_names = enum_process_sections(trcc_pid)
    if section_names:
        print(f"Found {len(section_names)} named objects:")
        for n in section_names:
            if any(k in n for k in ['share','Share','mem','Mem','LCD','lcd','RGB','rgb','image','Image']):
                print(f"  >>> {n}  <<<  (interesting)")
            else:
                print(f"  {n}")
    else:
        print("  (none found — may need admin privileges)")
else:
    print("\nTRCC.exe not found in process list — is TRCC running?")

# Phase 2: try to read known names with retry loop
print("\n--- Trying known SHM names (with retry to beat race condition) ---")
import time

for name in names_to_try:
    got = None
    for attempt in range(30):
        data = read_shm(name, 512 * 1024)
        if data is not None:
            nonzero = sum(1 for b in data if b != 0)
            if nonzero > 64:
                got = data
                break
        time.sleep(0.03)

    if got is None:
        data = read_shm(name, 512 * 1024)
        if data is None:
            continue
        got = data

    nonzero = sum(1 for b in got if b != 0)
    last_nz = max((i for i, b in enumerate(got) if b != 0), default=0)
    print(f"\nFOUND: {name!r}  nonzero={nonzero}  last_nz_offset={last_nz}")
    print(f"  First 64 bytes: {got[:64].hex()}")
    if nonzero > 64:
        print(f"  Bytes 64-128:  {got[64:128].hex()}")
        safe = name.replace('\\', '_').replace('/', '_')
        if got[:3] == b'\xff\xd8\xff':
            print("  *** JPEG ***")
            end = got.find(b'\xff\xd9')
            if end > 0:
                fname = f'lcd_capture_{safe}.jpg'
                with open(fname, 'wb') as f:
                    f.write(got[:end+2])
                print(f"  Saved {fname} ({end+2} bytes)")
        elif got[:4] == b'\x89PNG':
            print("  *** PNG ***")
            fname = f'lcd_capture_{safe}.png'
            with open(fname, 'wb') as f:
                f.write(got[:last_nz+1])
            print(f"  Saved {fname}")
        else:
            fname = f'lcd_capture_{safe}.bin'
            with open(fname, 'wb') as f:
                f.write(got[:last_nz+1])
            print(f"  Saved raw binary: {fname}")


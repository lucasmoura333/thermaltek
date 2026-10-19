import pefile, re

pe = pefile.PE(r"C:\Program Files\TRCCCAP\TRCC.exe")
raw = open(r"C:\Program Files\TRCCCAP\TRCC.exe", "rb").read()

il = open(r"F:\helpmeplease\linux-driver\python-lib\TRCC_decomp.il", encoding="utf-8", errors="replace").read()

# Find all field definitions with 'at I_XXXXXXXX'
field_pattern = re.compile(
    r"__StaticArrayInitTypeSize=(\d+)' '.*?' at I_([0-9A-Fa-f]{8})",
    re.DOTALL
)

matches = list(field_pattern.finditer(il))
print(f"Total static array fields: {len(matches)}")

# Filter by size and read actual bytes
seen = set()
results = []
for m in matches:
    size = int(m.group(1))
    rva = int(m.group(2), 16)
    if rva in seen:
        continue
    seen.add(rva)
    try:
        off = pe.get_offset_from_rva(rva)
        d = raw[off:off+size]
        results.append((size, rva, d))
    except:
        pass

results.sort(key=lambda x: (x[0], x[1]))

# Show all arrays containing DA DB DC DD
print("\nArrays containing DA DB DC DD:")
for size, rva, d in results:
    if len(d) >= 4 and d[:4] == bytes([0xDA, 0xDB, 0xDC, 0xDD]):
        hex_str = " ".join(f"{b:02X}" for b in d)
        print(f"  size={size}, RVA=0x{rva:X}: {hex_str}")

# Show all 14-25 byte arrays
print(f"\nAll 14-25 byte arrays ({sum(1 for s,_,_ in results if 14<=s<=25)}):")
for size, rva, d in results:
    if 14 <= size <= 25:
        hex_str = " ".join(f"{b:02X}" for b in d)
        print(f"  size={size:3d}, RVA=0x{rva:X}: {hex_str}")

# Show all 20-byte arrays
print(f"\nAll 20-byte arrays ({sum(1 for s,_,_ in results if s==20)}):")
for size, rva, d in results:
    if size == 20:
        hex_str = " ".join(f"{b:02X}" for b in d)
        print(f"  RVA=0x{rva:X}: {hex_str}")

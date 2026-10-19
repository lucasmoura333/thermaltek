"""
Properly extract static array data from TRCC.exe using correct RVA handling.
"""
import pefile

TRCC_EXE = r"C:\Program Files\TRCCCAP\TRCC.exe"
pe = pefile.PE(TRCC_EXE)

print(f"Image Base: {pe.OPTIONAL_HEADER.ImageBase:#010x}")
print(f"Sections:")
for section in pe.sections:
    name = section.Name.decode('utf-8', errors='replace').rstrip('\x00')
    print(f"  {name}: VA={section.VirtualAddress:#010x} Size={section.Misc_VirtualSize:#010x} "
          f"RawOffset={section.PointerToRawData:#010x} RawSize={section.SizeOfRawData:#010x}")

# The RVA from IL "at I_00DE24A0" - try it as-is (no ImageBase subtraction)
rva = 0x00DE24A0
print(f"\nTrying RVA {rva:#010x} directly:")
try:
    data = pe.get_data(rva, 20)
    hex_str = ' '.join(f'{b:02X}' for b in data)
    print(f"  Data: {hex_str}")
except Exception as e:
    print(f"  Error: {e}")

# Try different interpretations
print("\nTrying to find DA DB DC DD pattern in the binary...")

# Read the full file
with open(TRCC_EXE, 'rb') as f:
    binary = f.read()

# Search for our expected LED header: DA DB DC DD 00 00 00 00 00 00 00 00 02 00 00 00
pattern = bytes([0xDA, 0xDB, 0xDC, 0xDD, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02])
offsets = []
pos = 0
while True:
    pos = binary.find(pattern, pos)
    if pos == -1:
        break
    offsets.append(pos)
    pos += 1

print(f"Found {len(offsets)} occurrences of LED header pattern:")
for off in offsets[:10]:
    data = binary[off:off+20]
    hex_str = ' '.join(f'{b:02X}' for b in data)
    print(f"  Offset {off:#010x}: {hex_str}")

# Search for init packet: DA DB DC DD 00 00 00 00 00 00 00 00 01 00 00 00  
pattern_init = bytes([0xDA, 0xDB, 0xDC, 0xDD, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00])
offsets_init = []
pos = 0
while True:
    pos = binary.find(pattern_init, pos)
    if pos == -1:
        break
    offsets_init.append(pos)
    pos += 1

print(f"\nFound {len(offsets_init)} occurrences of init packet pattern:")
for off in offsets_init[:10]:
    data = binary[off:off+20]
    hex_str = ' '.join(f'{b:02X}' for b in data)
    print(f"  Offset {off:#010x}: {hex_str}")

# Also search for just DA DB DC DD to find all magic headers
pattern_magic = bytes([0xDA, 0xDB, 0xDC, 0xDD])
offsets_magic = []
pos = 0
while True:
    pos = binary.find(pattern_magic, pos)
    if pos == -1:
        break
    offsets_magic.append(pos)
    pos += 1

print(f"\nFound {len(offsets_magic)} occurrences of DA DB DC DD magic:")
for off in offsets_magic:
    data = binary[off:off+24]
    hex_str = ' '.join(f'{b:02X}' for b in data)
    print(f"  Offset {off:#010x}: {hex_str}")

# Also search DC DD 01 (discovery packet pattern)
pattern_disc = bytes([0xDC, 0xDD, 0x01, 0x00, 0x00, 0x00])
offsets_disc = []
pos = 0
while True:
    pos = binary.find(pattern_disc, pos)
    if pos == -1:
        break
    offsets_disc.append(pos)
    pos += 1

print(f"\nFound {len(offsets_disc)} occurrences of DC DD 01 discovery pattern:")
for off in offsets_disc[:5]:
    data = binary[off:off+20]
    hex_str = ' '.join(f'{b:02X}' for b in data)
    print(f"  Offset {off:#010x}: {hex_str}")

pe.close()

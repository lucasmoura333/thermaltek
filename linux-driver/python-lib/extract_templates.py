"""
Extract the exact bytes of static packet templates from TRCC.exe binary.
Uses pefile to convert RVA to file offset and read the data.
"""
import pefile
import os

TRCC_EXE = r"C:\Program Files\TRCCCAP\TRCC.exe"

pe = pefile.PE(TRCC_EXE)

# Known template RVAs from IL decompilation
templates = {
    "A3CDD81F (LED header)": 0x00DE24A0,
    "ECC65F5C (Init/OnConnected)": None,  # need to find
}

# Find the ECC65F5C init template RVA
# From DeviceOnConnected1: ECC65F5C5C04E58CEB12C41F4BCEBE199A23BB51B4F213FB7DABE0AD2E14114D

# Let's search for it in the IL
print("Template RVAs found in IL:")
print(f"  LED header (A3CDD81F): RVA = 0x00DE24A0")

# Read the binary at that RVA
for name, rva in [
    ("LED header (A3CDD81F)", 0x00DE24A0),
]:
    offset = pe.get_offset_from_rva(rva - pe.OPTIONAL_HEADER.ImageBase)
    data = pe.get_data(rva - pe.OPTIONAL_HEADER.ImageBase, 20)
    hex_str = ' '.join(f'{b:02X}' for b in data)
    print(f"\n{name}:")
    print(f"  RVA: {rva:#010x}")
    print(f"  File offset: {offset:#010x}")
    print(f"  Data (20 bytes): {hex_str}")

# Now search for ECC65F5C init template
print("\nSearching for ECC65F5C init template...")
# Read the IL file to find the RVA
with open(r"F:\helpmeplease\linux-driver\python-lib\TRCC_decomp.il", "r", encoding="utf-8") as f:
    for line in f:
        if "ECC65F5C" in line and "I_" in line:
            print(f"  Found: {line.strip()}")
            # Extract RVA
            idx = line.index("I_")
            rva_str = line[idx+2:].strip()
            rva = int(rva_str, 16)
            offset = pe.get_offset_from_rva(rva - pe.OPTIONAL_HEADER.ImageBase)
            data = pe.get_data(rva - pe.OPTIONAL_HEADER.ImageBase, 20)
            hex_str = ' '.join(f'{b:02X}' for b in data)
            print(f"  RVA: {rva:#010x}")
            print(f"  File offset: {offset:#010x}")
            print(f"  Init template data: {hex_str}")
            break

# Also search for ALL 20-byte static templates
print("\n\nALL 20-byte static templates:")
count = 0
with open(r"F:\helpmeplease\linux-driver\python-lib\TRCC_decomp.il", "r", encoding="utf-8") as f:
    for line in f:
        if "__StaticArrayInitTypeSize=20" in line and " at I_" in line:
            parts = line.strip().split()
            field_name = None
            rva_str = None
            for i, p in enumerate(parts):
                if p.startswith("I_"):
                    rva_str = p
                # The field name is the token before "at"
            for i, p in enumerate(parts):
                if len(p) == 64 and all(c in '0123456789ABCDEFabcdef' for c in p):
                    field_name = p[:16] + "..."
            
            if rva_str:
                rva = int(rva_str[2:], 16)
                try:
                    data = pe.get_data(rva - pe.OPTIONAL_HEADER.ImageBase, 20)
                    hex_str = ' '.join(f'{b:02X}' for b in data)
                    print(f"  {field_name or 'unknown'}: {hex_str}")
                    count += 1
                except:
                    pass

print(f"\nTotal 20-byte templates found: {count}")

pe.close()

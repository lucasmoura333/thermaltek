import pefile, re

pe = pefile.PE(r"C:\Program Files\TRCCCAP\TRCC.exe")
raw = open(r"C:\Program Files\TRCCCAP\TRCC.exe", "rb").read()
il = open(r"F:\helpmeplease\linux-driver\python-lib\TRCC_decomp.il", encoding="utf-8", errors="replace").read()

# Read all field definitions at I_XXXXXXXX along with their hash names
pattern = re.compile(r"'__StaticArrayInitTypeSize=(\d+)' '<PrivateImplementationDetails>'::'\s*(\w+)' at I_([0-9A-Fa-f]{8})")
matches = list(pattern.finditer(il))

# Also try without the quotes around the hash
pattern2 = re.compile(r"__StaticArrayInitTypeSize=(\d+)' '<PrivateImplementationDetails>'::([0-9A-Fa-f]{64}) at I_([0-9A-Fa-f]{8})")
matches2 = list(pattern2.finditer(il))

print(f"Pattern1 matches: {len(matches)}")
print(f"Pattern2 matches: {len(matches2)}")

# Try by directly searching for "at I_"
atI_pattern = re.compile(r"TypeSize=(\d+)'.*?at I_([0-9A-Fa-f]{8})")
matches3 = list(atI_pattern.finditer(il))
print(f"Pattern3 matches: {len(matches3)}")

# Just find specific hashes
hashes_to_find = [
    ("ECC65F5C5C04E58CEB12C41F4BCEBE199A23BB51B4F213FB7DABE0AD2E14114D", "DeviceOnConnected1", 20),
    ("C6BA09734DEDF76748C86E86E99853943988DCD7192288BCB7631C73D89FF009", "AddhidDeviceList", 14),
    ("A3CDD81F157A92307F868EB66E01C070D7B10CBB34CED4DE45CF6344FC2537F8", "SendHidVal_LED_header", 20),
]

for hash_id, desc, size in hashes_to_find:
    idx = il.find(hash_id)
    if idx < 0:
        print(f"Hash {hash_id[:8]}... NOT FOUND in IL")
        continue
    # Search for RVA in following text
    context = il[idx:idx+300]
    m = re.search(r'at I_([0-9A-Fa-f]{8})', context)
    if m:
        rva = int(m.group(1), 16)
        try:
            off = pe.get_offset_from_rva(rva)
            d = raw[off:off+size]
            print(f"{desc} ({size} bytes): {' '.join(f'{b:02X}' for b in d)}")
        except Exception as e:
            print(f"{desc}: ERROR {e}")
    else:
        # Try to find it differently - the hash might be a field name
        print(f"{desc}: found hash at {idx}, looking for RVA...")
        # Find the .field definition for this hash
        field_idx = il.find(f"'{hash_id}' at I_")
        if field_idx < 0:
            field_idx = il.find(f"{hash_id} at I_")
        if field_idx >= 0:
            rva_str = il[field_idx+len(hash_id)+5:field_idx+len(hash_id)+13]
            rva = int(rva_str, 16)
            off = pe.get_offset_from_rva(rva)
            d = raw[off:off+size]
            print(f"  {desc} ({size} bytes): {' '.join(f'{b:02X}' for b in d)}")
        else:
            print(f"  {desc}: RVA not found")

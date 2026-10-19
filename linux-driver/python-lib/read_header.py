import pefile
import struct

pe = pefile.PE(r"C:\Program Files\TRCCCAP\TRCC.exe")

# RVA of the 20-byte header array (A3CDD81F hash, __StaticArrayInitTypeSize=20)
rva = 0x00DE24A0
file_offset = pe.get_offset_from_rva(rva)
print(f"RVA 0x{rva:X} -> File offset: 0x{file_offset:X} ({file_offset})")

raw = open(r"C:\Program Files\TRCCCAP\TRCC.exe", "rb").read()
data = raw[file_offset:file_offset+20]
print(f"20-byte header: {' '.join(f'{b:02X}' for b in data)}")

# Also look at some nearby arrays for context
print("\nSurrounding bytes +/-32:")
context = raw[file_offset-32:file_offset+64]
print(' '.join(f'{b:02X}' for b in context))

# Also look for the 14-byte array used in AddhidDeviceList
# C6BA09734DEDF76748C86E86E99853943988DCD7192288BCB7631C73D89FF009
# Find it in the IL
import re
il_content = open(r"F:\helpmeplease\linux-driver\python-lib\TRCC_decomp.il", encoding='utf-8', errors='replace').read()
hash14 = 'C6BA09734DEDF76748C86E86E99853943988DCD7192288BCB7631C73D89FF009'
idx = il_content.find(f'__StaticArrayInitTypeSize=14\' \'<PrivateImplementationDetails>\'::{hash14}')
if idx >= 0:
    # find at I_XXXXXXXX pattern
    line = il_content[idx:idx+200]
    import re
    m = re.search(r'at I_([0-9A-Fa-f]+)', line)
    if m:
        rva14 = int(m.group(1), 16)
        off14 = pe.get_offset_from_rva(rva14)
        d = raw[off14:off14+14]
        print(f"\n14-byte AddhidDeviceList array (@ RVA 0x{rva14:X}):")
        print(' '.join(f'{b:02X}' for b in d))

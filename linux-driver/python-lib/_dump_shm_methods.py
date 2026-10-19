"""Dump ReadShareMemoryRGB and WriteShareMemoryRGB IL."""
import struct
import pefile
import dnfile

pe = pefile.PE('USBLCDNEW.dll')

def rva_to_off(rva):
    for s in pe.sections:
        start = s.VirtualAddress
        end = start + max(s.Misc_VirtualSize, s.SizeOfRawData)
        if start <= rva < end:
            return s.PointerToRawData + (rva - start)
    return None

data = open('USBLCDNEW.dll', 'rb').read()

# Methods to dump
targets = [
    ('InitMemorySizeRGB',   0x2050),
    ('ReadShareMemoryRGB',  0x2064),
    ('WriteShareMemoryRGB', 0x20dc),
    ('CloseShareMemoryRGB', 0x20dc),  # may be same RVA
]

for name, rva in targets:
    off = rva_to_off(rva)
    if off is None:
        print('=== %s RVA 0x%x -> no offset ===' % (name, rva))
        continue
    
    # Check method header
    hdr_byte = data[off] & 0x3
    if hdr_byte == 2:  # tiny header
        code_size = (data[off] >> 2) & 0x3f
        code_off = off + 1
    else:  # fat header
        code_size = struct.unpack_from('<I', data, off + 4)[0]
        code_off = off + 12
    
    code = data[code_off:code_off + min(code_size, 512)]
    print('\n=== %s (RVA=0x%x, code_size=%d) ===' % (name, rva, code_size))
    for i in range(0, len(code), 16):
        row = code[i:i+16]
        hex_str = ' '.join('%02x' % b for b in row)
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in row)
        print('  %04x: %-47s  |%s|' % (i, hex_str, ascii_str))

# Also dump StratDCReadWriteAsync fully (it dispatches to variant threads)  
print('\n=== StratDCReadWriteAsync full (1458 bytes) ===')
off = rva_to_off(0x210c)
cs = struct.unpack_from('<I', data, off + 4)[0]
code = data[off+12:off+12+cs]
for i in range(0, len(code), 16):
    row = code[i:i+16]
    hex_str = ' '.join('%02x' % b for b in row)
    print('  %04x: %s' % (i, hex_str))

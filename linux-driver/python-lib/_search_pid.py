import struct

def rva_to_offset(data, rva):
    e_lfanew = struct.unpack_from('<I', data, 0x3C)[0]
    num_sections = struct.unpack_from('<H', data, e_lfanew+6)[0]
    opt_size = struct.unpack_from('<H', data, e_lfanew+20)[0]
    sections_off = e_lfanew + 24 + opt_size
    for i in range(num_sections):
        sec = sections_off + i * 40
        vsize  = struct.unpack_from('<I', data, sec + 8)[0]
        vaddr  = struct.unpack_from('<I', data, sec + 12)[0]
        rawoff = struct.unpack_from('<I', data, sec + 20)[0]
        if vaddr <= rva < vaddr + vsize:
            return rawoff + (rva - vaddr)
    raise ValueError()

data = open('USBLCDNEW.dll', 'rb').read()

# Search 0x8001 in the entire DLL
needle = struct.pack('<I', 0x8001)
pos = 0
print('=== All occurrences of 0x8001 in DLL ===')
while True:
    p = data.find(needle, pos)
    if p < 0:
        break
    ctx = data[max(0, p-8):p+12]
    hex_str = ' '.join('%02x' % b for b in ctx)
    print('  offset 0x%08x: %s' % (p, hex_str))
    pos = p + 1

# Also search for 0x80 0x01 as big-endian uint16
needle2 = bytes([0x80, 0x01])
pos = 0
print('\n=== All occurrences of 0x80 0x01 (BE PID) ===')
while True:
    p = data.find(needle2, pos)
    if p < 0:
        break
    ctx = data[max(0, p-8):p+8]
    hex_str = ' '.join('%02x' % b for b in ctx)
    print('  offset 0x%08x: %s' % (p, hex_str))
    pos = p + 1

# StratDCReadWriteAsync at 0x210c
off = rva_to_offset(data, 0x210c)
code_size = struct.unpack_from('<I', data, off+4)[0]
code = data[off+12:off+12+code_size]
print('\n=== StratDCReadWriteAsync code_size=%d ===' % code_size)
for i in range(0, min(320, len(code)), 16):
    row = code[i:i+16]
    hex_str = ' '.join('%02x' % b for b in row)
    print('  %04x:  %s' % (i, hex_str))

# Dump full base ThreadSendDeviceData (all 1143 bytes)
off2 = rva_to_offset(data, 0x2760)
cs2 = struct.unpack_from('<I', data, off2+4)[0]
code2 = data[off2+12:off2+12+cs2]
print('\n=== ThreadSendDeviceData (base) full dump, size=%d ===' % cs2)
for i in range(0, len(code2), 16):
    row = code2[i:i+16]
    hex_str = ' '.join('%02x' % b for b in row)
    print('  %04x:  %s' % (i, hex_str))

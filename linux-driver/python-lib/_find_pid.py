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

data = open('USBLCDNEW.dll','rb').read()

# ThreadSendDeviceData (base) at RVA 0x2760
off = rva_to_offset(data, 0x2760)
code_size = struct.unpack_from('<I', data, off+4)[0]
code_off = off + 12
code = data[code_off:code_off + min(512, code_size)]
print(f'ThreadSendDeviceData  code_size={code_size}')
for i in range(0, len(code), 16):
    row = code[i:i+16]
    ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in row)
    print(f'  {i:04x}:  {row.hex(" ")}   |{ascii_part}|')

# Also search for 0x8001 in the code
needle = struct.pack('<I', 0x8001)
pos = code.find(needle)
if pos >= 0:
    print(f'\n  Found PID 0x8001 at code offset {pos:#x}')
    # show context
    start = max(0, pos-4)
    ctx = code[start:pos+8]
    print(f'  context: {ctx.hex(" ")}')
else:
    print('\n  PID 0x8001 NOT found in first 512 bytes')
    # search in all variants
    for name, rva in [('H',0x2c48),('ALi',0x3124),('LY',0x3644),('LY1',0x3e00)]:
        off2 = rva_to_offset(data, rva)
        cs2 = struct.unpack_from('<I', data, off2+4)[0]
        co2 = off2 + 12
        c2 = data[co2:co2+cs2]
        p = c2.find(needle)
        if p >= 0:
            ctx = c2[max(0,p-4):p+8]
            print(f'  {name}: found 0x8001 at +{p:#x} ctx={ctx.hex(" ")}')

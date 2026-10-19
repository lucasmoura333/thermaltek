"""
Disassemble StratDCReadWriteAsync from USBLCDNEW.dll.
This method opens the device, reads its identity, and dispatches to the
correct ThreadSendDeviceData* variant.
"""
import struct

def read_pe(path):
    with open(path, 'rb') as f:
        return f.read()

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
    raise ValueError(f"RVA {rva:#x} not in any section")

data = read_pe('USBLCDNEW.dll')

# Dump raw IL bytes for StratDCReadWriteAsync (RVA 0x210c)
# and all ThreadSendDeviceData* variants
targets = [
    ('StratDCReadWriteAsync',   0x210c),
    ('ThreadSendDeviceDataH',   0x2c48),
    ('ThreadSendDeviceDataALi', 0x3124),
    ('ThreadSendDeviceDataLY',  0x3644),
    ('ThreadSendDeviceDataLY1', 0x3e00),
]

for name, rva in targets:
    off = rva_to_offset(data, rva)
    hdr = data[off]
    if hdr & 3 == 2:    # tiny
        code_off  = off + 1
        code_size = (hdr >> 2) & 0x3F
    else:               # fat
        code_size = struct.unpack_from('<I', data, off+4)[0]
        code_off  = off + 12

    code = data[code_off:code_off + min(code_size, 4096)]
    print(f"\n\n{'='*60}")
    print(f"=== {name}  (code_size={code_size}) ===")
    # Hex dump - 16 bytes per row
    for i in range(0, min(len(code), 256), 16):
        row = code[i:i+16]
        print(f"  {i:04x}:  {row.hex(' ')}   |{''.join(chr(b) if 32 <= b < 127 else '.' for b in row)}|")
    if code_size > 256:
        print(f"  ... ({code_size-256} more bytes) ...")

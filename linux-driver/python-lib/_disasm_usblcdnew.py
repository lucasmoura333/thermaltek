"""
Disassemble IL bytes from USBLCDNEW.dll methods using raw PE parsing.
Targets the ThreadSendDeviceData* methods to find USB packet format.
"""
import struct
import sys

def read_pe(path):
    with open(path, 'rb') as f:
        return f.read()

def rva_to_offset(data, rva):
    """Convert RVA to file offset via section headers."""
    # DOS header
    e_lfanew = struct.unpack_from('<I', data, 0x3C)[0]
    # PE signature check
    assert data[e_lfanew:e_lfanew+4] == b'PE\x00\x00'
    # COFF header
    machine, num_sections = struct.unpack_from('<HH', data, e_lfanew+4)[:2]
    opt_size = struct.unpack_from('<H', data, e_lfanew+20)[0]
    sections_off = e_lfanew + 24 + opt_size
    for i in range(num_sections):
        sec = sections_off + i * 40
        vsize   = struct.unpack_from('<I', data, sec + 16)[0]
        vaddr   = struct.unpack_from('<I', data, sec + 20)[0]
        rawsize = struct.unpack_from('<I', data, sec + 16)[0]
        rawoff  = struct.unpack_from('<I', data, sec + 20 + 4)[0]
        # re-read correctly
        name    = data[sec:sec+8].rstrip(b'\x00').decode(errors='replace')
        vsize   = struct.unpack_from('<I', data, sec + 8)[0]
        vaddr   = struct.unpack_from('<I', data, sec + 12)[0]
        rawsize = struct.unpack_from('<I', data, sec + 16)[0]
        rawoff  = struct.unpack_from('<I', data, sec + 20)[0]
        if vaddr <= rva < vaddr + vsize:
            return rawoff + (rva - vaddr)
    raise ValueError(f"RVA {rva:#x} not found in any section")

# IL opcode names (partial - enough for analysis)
OPCODES = {
    0x00: 'nop', 0x01: 'break', 0x02: 'ldarg.0', 0x03: 'ldarg.1',
    0x04: 'ldarg.2', 0x05: 'ldarg.3', 0x06: 'ldloc.0', 0x07: 'ldloc.1',
    0x08: 'ldloc.2', 0x09: 'ldloc.3', 0x0a: 'stloc.0', 0x0b: 'stloc.1',
    0x0c: 'stloc.2', 0x0d: 'stloc.3', 0x0e: 'ldarg.s', 0x0f: 'ldarga.s',
    0x10: 'starg.s', 0x11: 'ldloc.s', 0x12: 'ldloca.s', 0x13: 'stloc.s',
    0x14: 'ldnull', 0x15: 'ldc.i4.m1', 0x16: 'ldc.i4.0', 0x17: 'ldc.i4.1',
    0x18: 'ldc.i4.2', 0x19: 'ldc.i4.3', 0x1a: 'ldc.i4.4', 0x1b: 'ldc.i4.5',
    0x1c: 'ldc.i4.6', 0x1d: 'ldc.i4.7', 0x1e: 'ldc.i4.8', 0x1f: 'ldc.i4.s',
    0x20: 'ldc.i4',  0x21: 'ldc.i8',  0x22: 'ldc.r4',  0x23: 'ldc.r8',
    0x25: 'dup',     0x26: 'pop',      0x27: 'jmp',     0x28: 'call',
    0x29: 'calli',   0x2a: 'ret',      0x2b: 'br.s',    0x2c: 'brfalse.s',
    0x2d: 'brtrue.s',0x2e: 'beq.s',   0x2f: 'bge.s',   0x30: 'bgt.s',
    0x31: 'ble.s',   0x32: 'blt.s',   0x33: 'bne.un.s',0x34: 'bge.un.s',
    0x35: 'bgt.un.s',0x36: 'ble.un.s',0x37: 'blt.un.s',0x38: 'br',
    0x39: 'brfalse', 0x3a: 'brtrue',  0x3b: 'beq',     0x3c: 'bge',
    0x3d: 'bgt',     0x3e: 'ble',     0x3f: 'blt',     0x40: 'bne.un',
    0x41: 'bge.un',  0x42: 'bgt.un',  0x43: 'ble.un',  0x44: 'blt.un',
    0x45: 'switch',  0x46: 'ldind.i1',0x47: 'ldind.u1',0x48: 'ldind.i2',
    0x49: 'ldind.u2',0x4a: 'ldind.i4',0x4b: 'ldind.u4',0x4c: 'ldind.i8',
    0x4d: 'ldind.i', 0x4e: 'ldind.r4',0x4f: 'ldind.r8',0x50: 'ldind.ref',
    0x51: 'stind.ref',0x52: 'stind.i1',0x53: 'stind.i2',0x54: 'stind.i4',
    0x55: 'stind.i8',0x56: 'stind.r4',0x57: 'stind.r8',0x58: 'add',
    0x59: 'sub',     0x5a: 'mul',     0x5b: 'div',     0x5c: 'div.un',
    0x5d: 'rem',     0x5e: 'rem.un',  0x5f: 'and',     0x60: 'or',
    0x61: 'xor',     0x62: 'shl',     0x63: 'shr',     0x64: 'shr.un',
    0x65: 'neg',     0x66: 'not',     0x67: 'conv.i1',  0x68: 'conv.i2',
    0x69: 'conv.i4', 0x6a: 'conv.i8', 0x6b: 'conv.r4',  0x6c: 'conv.r8',
    0x6d: 'conv.u4', 0x6e: 'conv.u8', 0x6f: 'callvirt', 0x70: 'cpobj',
    0x71: 'ldobj',   0x72: 'ldstr',   0x73: 'newobj',   0x74: 'castclass',
    0x75: 'isinst',  0x76: 'conv.r.un',0x79: 'unbox',  0x7a: 'throw',
    0x7b: 'ldfld',   0x7c: 'ldflda',  0x7d: 'stfld',   0x7e: 'ldsfld',
    0x7f: 'ldsflda', 0x80: 'stsfld',  0x81: 'stobj',   0x84: 'box',
    0x85: 'newarr',  0x86: 'ldlen',   0x8d: 'stelem',  0x8e: 'ldelem.i1',
    0x90: 'ldelem.u1',0x91: 'ldelem.u2',0x94: 'ldelem.i4',0x95: 'ldelem.u4',
    0x98: 'ldelem.i8',0x9a: 'ldelem.ref',0x9c: 'stelem.i1',0x9e: 'stelem.i4',
    0xa0: 'stelem.ref',0xa2: 'ldelema',
    0xfe: '0xFE_prefix',  # extended opcodes
}

def disasm_il(data, offset, max_bytes=2000):
    """Very simplified IL disassembler - shows key operations."""
    pos = 0
    out = []
    while pos < max_bytes:
        ip = pos
        b = data[offset + pos]
        pos += 1
        
        if b == 0xfe:  # two-byte opcode
            b2 = data[offset + pos]; pos += 1
            extended = {0x01: 'ceq', 0x02: 'cgt', 0x03: 'cgt.un', 0x04: 'clt', 0x05: 'clt.un',
                       0x06: 'ldftn', 0x09: 'ldarg', 0x0a: 'ldarga', 0x0b: 'starg',
                       0x0c: 'ldloc', 0x0d: 'ldloca', 0x0e: 'stloc', 0x11: 'constrained',
                       0x14: 'rethrow', 0x16: 'sizeof', 0x17: 'refanytype', 0x18: 'readonly'}
            name = extended.get(b2, f'FE_{b2:02x}')
            operand = ''
            if b2 in (0x06,):  # ldftn - token
                tok = struct.unpack_from('<I', data, offset+pos)[0]; pos += 4
                operand = f' {tok:#010x}'
            elif b2 in (0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e):  # short
                idx = struct.unpack_from('<H', data, offset+pos)[0]; pos += 2
                operand = f' {idx}'
            elif b2 in (0x11,):  # constrained - type token
                tok = struct.unpack_from('<I', data, offset+pos)[0]; pos += 4
                operand = f' {tok:#010x}'
            out.append(f'  IL_{ip:04x}: {name}{operand}')
            continue
        
        name = OPCODES.get(b, f'0x{b:02x}')
        
        # operands by opcode
        if b in (0x0e, 0x0f, 0x10, 0x11, 0x12, 0x13):  # s variants (1 byte index)
            idx = data[offset+pos]; pos += 1
            out.append(f'  IL_{ip:04x}: {name} {idx}')
        elif b == 0x1f:  # ldc.i4.s
            v = struct.unpack_from('<b', data, offset+pos)[0]; pos += 1
            out.append(f'  IL_{ip:04x}: {name} {v}')
        elif b == 0x20:  # ldc.i4
            v = struct.unpack_from('<i', data, offset+pos)[0]; pos += 4
            out.append(f'  IL_{ip:04x}: {name} {v}')
        elif b == 0x21:  # ldc.i8
            v = struct.unpack_from('<q', data, offset+pos)[0]; pos += 8
            out.append(f'  IL_{ip:04x}: {name} {v}')
        elif b in (0x28, 0x29, 0x27, 0x6f, 0x72, 0x73, 0x74, 0x75, 0x79, 0x7b, 0x7c, 0x7d,
                   0x7e, 0x7f, 0x80, 0x81, 0x84, 0x85, 0x70, 0x71, 0xa2):  # 4-byte token
            tok = struct.unpack_from('<I', data, offset+pos)[0]; pos += 4
            out.append(f'  IL_{ip:04x}: {name} {tok:#010x}')
        elif b in (0x38, 0x39, 0x3a, 0x3b, 0x3c, 0x3d, 0x3e, 0x3f, 0x40, 0x41, 0x42, 0x43, 0x44):
            v = struct.unpack_from('<i', data, offset+pos)[0]; pos += 4
            out.append(f'  IL_{ip:04x}: {name} {v:+d}  (→IL_{ip+5+v:04x})')
        elif b in (0x2b, 0x2c, 0x2d, 0x2e, 0x2f, 0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37):
            v = struct.unpack_from('<b', data, offset+pos)[0]; pos += 1
            out.append(f'  IL_{ip:04x}: {name} {v:+d}  (→IL_{ip+2+v:04x})')
        elif b == 0x2a:  # ret
            out.append(f'  IL_{ip:04x}: ret')
            break
        else:
            out.append(f'  IL_{ip:04x}: {name}')
        
    return '\n'.join(out)


data = read_pe('USBLCDNEW.dll')

# Methods to disassemble: (name, rva, max_bytes)
methods = [
    ('ThreadSendDeviceData',     0x2760, 1200),
    ('ThreadSendDeviceDataH',    0x2c48, 1200),
    ('WriteShareMemoryRGB',      0x20dc, 300),
    ('ReadShareMemoryRGB',       0x2064, 300),
    ('InitMemorySizeRGB',        0x2050, 100),
    ('StratDCReadWriteAsync',    0x210c, 1200),
]

for name, rva, max_b in methods:
    try:
        off = rva_to_offset(data, rva)
        # IL method header: check tiny vs fat
        hdr = data[off]
        if hdr & 0x3 == 0x2:   # tiny format: top 6 bits = code size
            code_off = off + 1
            code_size = (hdr >> 2) & 0x3F
        elif hdr & 0x3 == 0x3:  # fat format: 12 bytes header
            code_size = struct.unpack_from('<I', data, off+4)[0]
            code_off = off + 12
        else:
            print(f"\n=== {name} (RVA={rva:#x}) - unknown header {hdr:#x} ===")
            continue
        
        print(f"\n=== {name} (RVA={rva:#x}, offset={off:#x}, code_size={code_size}) ===")
        print(disasm_il(data, code_off, min(code_size, max_b)))
    except Exception as e:
        print(f"\n=== {name}: ERROR - {e} ===")

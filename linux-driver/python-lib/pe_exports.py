#!/usr/bin/env python3
"""
PE Export Analyzer

Extracts exported function names from a DLL file
"""

import sys
import struct

def get_exports(filepath):
    with open(filepath, 'rb') as f:
        data = f.read()
        
    if data[0:2] != b'MZ':
        print("Not a PE file")
        return

    # Offset to PE Header
    pe_offset = struct.unpack('<I', data[0x3C:0x40])[0]
    
    # Export Table RVA and Size (Data Directory index 0)
    # PE Header + 24 (Signature + FileHeader) + 96 (OptionalHeader standard fields) + 0 (DataDir[0])
    # This offset calculation depends on 32 vs 64 bit, assuming 32-bit for now based on (x86) path
    
    # Check Magic to determine 32/64 bit
    magic = struct.unpack('<H', data[pe_offset+24:pe_offset+26])[0]
    is_64 = (magic == 0x20B)
    
    rva_offset = pe_offset + 24 + (112 if is_64 else 96)
    
    export_rva = struct.unpack('<I', data[rva_offset:rva_offset+4])[0]
    export_size = struct.unpack('<I', data[rva_offset+4:rva_offset+8])[0]
    
    if export_rva == 0:
        print("No export table found")
        return

    # Convert RVA to File Offset
    # We need to iterate sections to find which one contains the RVA
    num_sections = struct.unpack('<H', data[pe_offset+6:pe_offset+8])[0]
    opt_header_size = struct.unpack('<H', data[pe_offset+20:pe_offset+22])[0]
    section_table_offset = pe_offset + 24 + opt_header_size
    
    file_offset = 0
    
    for i in range(num_sections):
        sec_offset = section_table_offset + (i * 40)
        # VirtualAddress is at offset 12, PointerToRawData at 20
        virt_addr = struct.unpack('<I', data[sec_offset+12:sec_offset+16])[0]
        raw_ptr = struct.unpack('<I', data[sec_offset+20:sec_offset+24])[0]
        virt_size = struct.unpack('<I', data[sec_offset+8:sec_offset+12])[0]
        
        if virt_addr <= export_rva < virt_addr + virt_size:
            file_offset = raw_ptr + (export_rva - virt_addr)
            break
            
    if file_offset == 0:
        print("Could not map RVA to file offset")
        return

    # Read Export Directory Table
    # Name RVA is at offset 12
    # NumberOfNames at 24
    # AddressOfNames at 32
    
    name_rva = struct.unpack('<I', data[file_offset+12:file_offset+16])[0]
    num_names = struct.unpack('<I', data[file_offset+24:file_offset+28])[0]
    names_rva = struct.unpack('<I', data[file_offset+32:file_offset+36])[0]
    
    print(f"Found {num_names} exported functions:")
    
    # Convert Names RVA to offset
    names_offset = 0
    for i in range(num_sections):
        sec_offset = section_table_offset + (i * 40)
        virt_addr = struct.unpack('<I', data[sec_offset+12:sec_offset+16])[0]
        raw_ptr = struct.unpack('<I', data[sec_offset+20:sec_offset+24])[0]
        virt_size = struct.unpack('<I', data[sec_offset+8:sec_offset+12])[0]
        
        if virt_addr <= names_rva < virt_addr + virt_size:
            names_offset = raw_ptr + (names_rva - virt_addr)
            break
            
    for i in range(num_names):
        name_ptr_rva = struct.unpack('<I', data[names_offset + (i*4):names_offset + (i*4) + 4])[0]
        
        # Convert Name Pointer RVA to offset
        name_offset = 0
        for j in range(num_sections):
            sec_offset = section_table_offset + (j * 40)
            virt_addr = struct.unpack('<I', data[sec_offset+12:sec_offset+16])[0]
            raw_ptr = struct.unpack('<I', data[sec_offset+20:sec_offset+24])[0]
            virt_size = struct.unpack('<I', data[sec_offset+8:sec_offset+12])[0]
            
            if virt_addr <= name_ptr_rva < virt_addr + virt_size:
                name_offset = raw_ptr + (name_ptr_rva - virt_addr)
                break
        
        # Read string
        name = ""
        while True:
            char = data[name_offset]
            if char == 0:
                break
            name += chr(char)
            name_offset += 1
            
        print(f"  - {name}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        get_exports(sys.argv[1])
    else:
        print("Usage: python pe_exports.py <dll_file>")

#!/usr/bin/env python3
"""
Search for Magic Bytes in TRCC files
"""

import os
from pathlib import Path

def search_magic_bytes(directory):
    # The magic bytes we captured: DA DB DC DD
    magic = b'\xDA\xDB\xDC\xDD'
    magic_reversed = b'\xDD\xDC\xDB\xDA'
    
    print(f"Searching for magic bytes {magic.hex()} in {directory}...")
    
    found_count = 0
    
    for root, dirs, files in os.walk(directory):
        for file in files:
            if not file.lower().endswith(('.exe', '.dll', '.dat', '.bin')):
                continue
                
            path = Path(root) / file
            try:
                with open(path, 'rb') as f:
                    data = f.read()
                    
                if magic in data:
                    print(f"\n🎯 FOUND in: {file}")
                    print(f"   Path: {path}")
                    count = data.count(magic)
                    print(f"   Occurrences: {count}")
                    
                    # Show context
                    offset = data.index(magic)
                    start = max(0, offset - 16)
                    end = min(len(data), offset + 32)
                    print(f"   Context: {data[start:end].hex()}")
                    found_count += 1
                    
                if magic_reversed in data:
                    print(f"\nTarget FOUND (Reversed) in: {file}")
                    found_count += 1
                    
            except Exception as e:
                pass
                
    if found_count == 0:
        print("\n❌ Magic bytes not found in any file.")
    else:
        print(f"\n✅ Found in {found_count} files!")

if __name__ == "__main__":
    search_magic_bytes(r"C:\Program Files (x86)\TRCCCAP")

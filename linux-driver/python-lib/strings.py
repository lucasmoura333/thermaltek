#!/usr/bin/env python3
"""
Extract Strings from Binary
"""

import sys
import re

def extract_strings(filename, min_len=4):
    with open(filename, 'rb') as f:
        data = f.read()
        
    # Regex for ASCII strings
    # Look for sequences of printable chars
    regex = re.compile(b'[ -~]{' + str(min_len).encode() + b',}')
    
    print(f"Extracting strings from {filename}...")
    
    found = []
    for match in regex.finditer(data):
        s = match.group().decode('ascii')
        # Filter for interesting keywords
        if any(k in s.lower() for k in ['rgb', 'led', 'color', 'light', 'init', 'set', 'cmd', 'usb', 'hid']):
            found.append(s)
            
    # Print unique interesting strings
    print(f"Found {len(found)} interesting strings:")
    for s in sorted(set(found)):
        print(f"  {s}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        extract_strings(sys.argv[1])
    else:
        print("Usage: python strings.py <file>")

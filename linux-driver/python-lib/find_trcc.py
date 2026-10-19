#!/usr/bin/env python3
"""
TRCC Installation Finder & Analyzer

Finds and analyzes TRCC installation files for protocol discovery
"""

import os
import sys
import json
from pathlib import Path

def find_trcc_installation():
    """Find TRCC installation directory"""
    
    common_paths = [
        r"C:\Program Files\Thermaltake",
        r"C:\Program Files (x86)\Thermaltake",
        r"C:\Program Files\TRCC",
        r"C:\Program Files (x86)\TRCC",
        r"C:\Thermaltake",
        Path.home() / "AppData" / "Local" / "Thermaltake",
        Path.home() / "AppData" / "Roaming" / "Thermaltake",
    ]
    
    found_paths = []
    
    print("🔍 Searching for TRCC installation...\n")
    
    for path in common_paths:
        path = Path(path)
        if path.exists():
            print(f"   ✓ Found: {path}")
            found_paths.append(path)
    
    # Search all Program Files
    for base in [r"C:\Program Files", r"C:\Program Files (x86)"]:
        base_path = Path(base)
        if base_path.exists():
            for item in base_path.iterdir():
                if item.is_dir() and 'thermaltake' in item.name.lower():
                    if item not in found_paths:
                        print(f"   ✓ Found: {item}")
                        found_paths.append(item)
    
    return found_paths


def analyze_directory(path):
    """Analyze a directory for interesting files"""
    
    path = Path(path)
    interesting_files = {
        'executables': [],
        'dlls': [],
        'configs': [],
        'data': [],
        'other': []
    }
    
    for root, dirs, files in os.walk(path):
        root_path = Path(root)
        for file in files:
            file_path = root_path / file
            file_lower = file.lower()
            
            # Categorize files
            if file_lower.endswith('.exe'):
                interesting_files['executables'].append(file_path)
            elif file_lower.endswith('.dll'):
                interesting_files['dlls'].append(file_path)
            elif file_lower.endswith(('.ini', '.cfg', '.conf', '.config', '.xml', '.json')):
                interesting_files['configs'].append(file_path)
            elif file_lower.endswith(('.dat', '.db', '.sqlite', '.txt', '.log')):
                interesting_files['data'].append(file_path)
            else:
                interesting_files['other'].append(file_path)
    
    return interesting_files


def search_for_hex_patterns(file_path):
    """Search for potential protocol patterns in files"""
    
    patterns_found = []
    
    # Read file as binary
    try:
        with open(file_path, 'rb') as f:
            data = f.read()
        
        # Search for potential HID patterns
        searches = [
            (b'\x04\x16', "Nuvoton VID (0x0416)"),
            (b'\x80\x01', "Product ID (0x8001)"),
            (b'\x5A', "Magic byte 0x5A"),
            (b'\xB5', "Magic byte 0xB5"),
            (b'\xAA\x55', "Header AA55"),
        ]
        
        for pattern, description in searches:
            if pattern in data:
                offset = data.index(pattern)
                context = data[max(0, offset-8):min(len(data), offset+16)]
                patterns_found.append({
                    'pattern': description,
                    'offset': offset,
                    'context': context.hex()
                })
    
    except Exception as e:
        pass
    
    return patterns_found


def main():
    print("\n" + "="*70)
    print("TRCC INSTALLATION ANALYZER")
    print("="*70 + "\n")
    
    # Find installations
    installations = find_trcc_installation()
    
    if not installations:
        print("\n❌ No TRCC installation found!")
        print("\n💡 Tips:")
        print("   - Install TRCC software if not installed")
        print("   - Check if installed in a custom location")
        print("   - Manually provide path as argument: python find_trcc.py <path>")
        return
    
    print(f"\n✅ Found {len(installations)} installation(s)\n")
    
    # Analyze each installation
    for install_path in installations:
        print("\n" + "="*70)
        print(f"📁 Analyzing: {install_path}")
        print("="*70 + "\n")
        
        files = analyze_directory(install_path)
        
        # Summary
        print("📊 File Summary:")
        print(f"   Executables: {len(files['executables'])}")
        print(f"   DLLs: {len(files['dlls'])}")
        print(f"   Config files: {len(files['configs'])}")
        print(f"   Data files: {len(files['data'])}")
        print(f"   Other: {len(files['other'])}")
        
        # List important files
        print("\n📋 Important Files:")
        
        if files['executables']:
            print("\n   🔧 Executables:")
            for exe in files['executables'][:10]:  # Limit to first 10
                size = exe.stat().st_size
                print(f"      - {exe.name} ({size:,} bytes)")
        
        if files['dlls']:
            print("\n   📚 DLLs:")
            for dll in files['dlls'][:10]:
                print(f"      - {dll.name}")
        
        if files['configs']:
            print("\n   ⚙️  Config Files:")
            for cfg in files['configs']:
                print(f"      - {cfg}")
                # Try to read small config files
                if cfg.stat().st_size < 1024 * 100:  # Less than 100KB
                    try:
                        with open(cfg, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read(500)
                            if content.strip():
                                print(f"         Preview: {content[:200]}...")
                    except:
                        pass
        
        # Search for patterns in executables and DLLs
        print("\n\n🔍 Searching for HID protocol patterns...")
        
        search_files = files['executables'] + files['dlls'][:5]  # Limit DLL search
        
        for file_path in search_files:
            patterns = search_for_hex_patterns(file_path)
            if patterns:
                print(f"\n   ✓ {file_path.name}:")
                for p in patterns:
                    print(f"      [{p['pattern']}] at offset {p['offset']}: {p['context']}")
        
        # Save report
        report_file = Path("trcc_analysis_report.json")
        report = {
            'installation_path': str(install_path),
            'files': {
                'executables': [str(f) for f in files['executables']],
                'dlls': [str(f) for f in files['dlls']],
                'configs': [str(f) for f in files['configs']],
                'data': [str(f) for f in files['data']],
            }
        }
        
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n\n💾 Analysis saved to: {report_file}")
    
    print("\n" + "="*70)
    print("Next steps:")
    print("="*70)
    print("\n1. Check config files for RGB settings")
    print("2. Use a hex editor to examine .exe/.dll files")
    print("3. Try running strings on executables:")
    print("   - strings <exe_file> | grep -i rgb")
    print("   - strings <exe_file> | grep -i color")
    print("\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Protocol Discovery Tool

Systematic protocol discovery for Nuvoton RGB controller
"""

import sys
import time
import argparse
import logging
from nuvoton_hid import NuvotonDevice, logger


class ProtocolDiscovery:
    """Protocol discovery and reverse engineering tool"""
    
    def __init__(self, device: NuvotonDevice):
        self.device = device
        self.results = []
    
    def test_pattern(self, pattern: bytes, description: str = "") -> bool:
        """
        Test a single pattern
        
        Args:
            pattern: Bytes to send
            description: Human-readable description
            
        Returns:
            True if any response received
        """
        logger.info(f"Testing: {description}")
        logger.debug(f"Pattern: {pattern.hex()}")
        
        success = self.device.send_command(pattern)
        
        # Try to read response
        response = self.device.read_report(timeout_ms=100)
        
        result = {
            'pattern': pattern.hex(),
            'description': description,
            'sent': success,
            'response': response.hex() if response else None
        }
        
        self.results.append(result)
        
        if response:
            logger.info(f"  Response: {response.hex()}")
            return True
        
        time.sleep(0.05)
        return False
    
    def test_simple_rgb(self):
        """Test simple RGB patterns"""
        logger.info("=== Testing Simple RGB Patterns ===")
        
        colors = [
            (255, 0, 0, "Red"),
            (0, 255, 0, "Green"),
            (0, 0, 255, "Blue"),
            (255, 255, 255, "White"),
        ]
        
        for r, g, b, name in colors:
            # Pattern 1: Direct RGB
            pattern = bytearray([r, g, b] + [0] * 60)
            self.test_pattern(bytes(pattern), f"Direct RGB - {name}")
            
            # Pattern 2: With command byte
            pattern = bytearray([0x01, r, g, b] + [0] * 59)
            self.test_pattern(bytes(pattern), f"CMD 0x01 RGB - {name}")
    
    def test_magic_headers(self):
        """Test common magic byte headers"""
        logger.info("=== Testing Magic Headers ===")
        
        headers = [
            ([0x5A], "0x5A header"),
            ([0xB5], "0xB5 header (Asus)"),
            ([0xAA, 0x55], "0xAA55 magic"),
            ([0x55, 0xAA], "0x55AA magic"),
            ([0xFF], "0xFF header"),
            ([0x00], "0x00 header"),
        ]
        
        for header, desc in headers:
            pattern = bytearray(header + [0x01, 255, 0, 0] + [0] * 58)
            self.test_pattern(bytes(pattern), desc)
    
    def test_command_range(self):
        """Test command byte range"""
        logger.info("=== Testing Command Range ===")
        
        for cmd in range(0x01, 0x10):
            pattern = bytearray([cmd, 255, 0, 0] + [0] * 60)
            self.test_pattern(bytes(pattern), f"Command 0x{cmd:02X}")
    
    def test_initialization_sequences(self):
        """Test possible initialization sequences"""
        logger.info("=== Testing Initialization Sequences ===")
        
        sequences = [
            ([0x00, 0x00], "Double zero"),
            ([0xFF, 0xFF], "Double FF"),
            ([0x5A, 0xA5], "0x5A 0xA5"),
            ([0xA5, 0x5A], "0xA5 0x5A"),
            ([0x01, 0x02, 0x03], "Sequence 1-2-3"),
        ]
        
        for seq, desc in sequences:
            pattern = bytearray(seq + [0] * (63 - len(seq)))
            self.test_pattern(bytes(pattern), f"Init: {desc}")
    
    def test_with_checksums(self):
        """Test patterns with checksums"""
        logger.info("=== Testing Patterns with Checksums ===")
        
        # Simple XOR checksum
        data = bytearray([0x01, 255, 0, 0])
        checksum = 0
        for byte in data:
            checksum ^= byte
        pattern = data + bytearray([checksum] + [0] * 58)
        self.test_pattern(bytes(pattern), "XOR checksum")
        
        # Sum checksum
        data = bytearray([0x01, 255, 0, 0])
        checksum = sum(data) & 0xFF
        pattern = data + bytearray([checksum] + [0] * 58)
        self.test_pattern(bytes(pattern), "Sum checksum")
    
    def test_vendor_specific(self):
        """Test vendor-specific patterns"""
        logger.info("=== Testing Vendor-Specific Patterns ===")
        
        # Nuvoton-specific guesses
        patterns = [
            ([0x04, 0x16], "Nuvoton VID bytes"),
            ([0x80, 0x01], "Nuvoton PID bytes"),
            ([0x4E, 0x55, 0x56], "NUV ASCII"),
        ]
        
        for prefix, desc in patterns:
            pattern = bytearray(prefix + [0x01, 255, 0, 0] + [0] * 57)
            self.test_pattern(bytes(pattern), desc)
    
    def brute_force_single_byte(self):
        """Brute force single header byte"""
        logger.info("=== Brute Force Single Byte Header ===")
        logger.warning("This will test 256 patterns, may take a few minutes")
        
        for byte in range(0x00, 0x100):
            pattern = bytearray([byte, 255, 0, 0] + [0] * 60)
            if self.test_pattern(bytes(pattern), f"Header 0x{byte:02X}"):
                logger.warning(f"*** Potential match with header 0x{byte:02X} ***")
    
    def export_results(self, filename: str):
        """Export results to file"""
        import json
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        logger.info(f"Results exported to {filename}")
    
    def run_systematic_tests(self):
        """Run all systematic tests"""
        logger.info("\n" + "=" * 60)
        logger.info("Starting Systematic Protocol Discovery")
        logger.info("=" * 60 + "\n")
        
        self.test_simple_rgb()
        self.test_magic_headers()
        self.test_command_range()
        self.test_initialization_sequences()
        self.test_with_checksums()
        self.test_vendor_specific()
        
        logger.info("\n" + "=" * 60)
        logger.info("Systematic Tests Complete")
        logger.info("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Protocol Discovery Tool for Nuvoton RGB Controller"
    )
    
    parser.add_argument('--systematic', action='store_true',
                        help='Run systematic protocol tests')
    parser.add_argument('--brute-force', action='store_true',
                        help='Brute force single byte header (slow)')
    parser.add_argument('--export', type=str, metavar='FILE',
                        help='Export results to JSON file')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    
    # Connect to device
    device = NuvotonDevice()
    if not device.connect():
        print("ERROR: Failed to connect to device")
        return 1
    
    try:
        discovery = ProtocolDiscovery(device)
        
        if args.systematic:
            discovery.run_systematic_tests()
        
        if args.brute_force:
            discovery.brute_force_single_byte()
        
        if args.export:
            discovery.export_results(args.export)
        
        if not (args.systematic or args.brute_force):
            parser.print_help()
            return 1
        
    finally:
        device.disconnect()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
RGB Control CLI Tool

Command-line interface for controlling Nuvoton RGB controller
"""

import argparse
import sys
import time
import logging
from nuvoton_hid import NuvotonDevice, list_devices, logger


def hex_color_to_rgb(hex_color: str) -> tuple:
    """Convert hex color (e.g., #FF00FF) to RGB tuple"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def set_static_color(device: NuvotonDevice, red: int, green: int, blue: int):
    """Set all LEDs to a solid colour using the confirmed protocol."""
    device.set_color(red, green, blue)


def rainbow_effect(device: NuvotonDevice, duration: int = 10):
    """Display rainbow color cycle"""
    logger.info(f"Running rainbow effect for {duration} seconds")
    
    start_time = time.time()
    hue = 0
    
    while time.time() - start_time < duration:
        # HSV to RGB conversion
        h = hue / 60.0
        x = int(255 * (1 - abs((h % 2) - 1)))
        
        if h < 1:
            r, g, b = 255, x, 0
        elif h < 2:
            r, g, b = x, 255, 0
        elif h < 3:
            r, g, b = 0, 255, x
        elif h < 4:
            r, g, b = 0, x, 255
        elif h < 5:
            r, g, b = x, 0, 255
        else:
            r, g, b = 255, 0, x
        
        set_static_color(device, r, g, b)
        
        hue = (hue + 5) % 360
        time.sleep(0.1)


def pulse_effect(device: NuvotonDevice, red: int, green: int, blue: int, duration: int = 10):
    """Pulse effect with given color"""
    logger.info(f"Running pulse effect for {duration} seconds")
    
    start_time = time.time()
    brightness = 0
    direction = 1
    
    while time.time() - start_time < duration:
        r = int(red * brightness / 100)
        g = int(green * brightness / 100)
        b = int(blue * brightness / 100)
        
        set_static_color(device, r, g, b)
        
        brightness += direction * 5
        if brightness >= 100 or brightness <= 0:
            direction *= -1
        
        time.sleep(0.05)


def interactive_mode(device: NuvotonDevice):
    """Interactive color testing mode"""
    print("\n=== Interactive RGB Control ===")
    print("Commands:")
    print("  rgb <r> <g> <b>  - Set RGB color (0-255)")
    print("  hex <#RRGGBB>    - Set color from hex")
    print("  rainbow [secs]   - Rainbow effect")
    print("  pulse <r> <g> <b> [secs] - Pulse effect")
    print("  quit             - Exit")
    print()
    
    while True:
        try:
            cmd = input("> ").strip().split()
            if not cmd:
                continue
            
            if cmd[0] == "quit":
                break
            elif cmd[0] == "rgb" and len(cmd) == 4:
                r, g, b = int(cmd[1]), int(cmd[2]), int(cmd[3])
                set_static_color(device, r, g, b)
            elif cmd[0] == "hex" and len(cmd) == 2:
                r, g, b = hex_color_to_rgb(cmd[1])
                set_static_color(device, r, g, b)
            elif cmd[0] == "rainbow":
                duration = int(cmd[1]) if len(cmd) > 1 else 10
                rainbow_effect(device, duration)
            elif cmd[0] == "pulse" and len(cmd) >= 4:
                r, g, b = int(cmd[1]), int(cmd[2]), int(cmd[3])
                duration = int(cmd[4]) if len(cmd) > 4 else 10
                pulse_effect(device, r, g, b, duration)
            else:
                print("Unknown command or invalid arguments")
                
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Control Nuvoton RGB Controller",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --list                     # List devices
  %(prog)s --test-connection          # Test connection
  %(prog)s --color 255 0 0            # Set red
  %(prog)s --hex "#FF00FF"            # Set magenta
  %(prog)s --rainbow 30               # Rainbow for 30 seconds
  %(prog)s --interactive              # Interactive mode
        """
    )
    
    parser.add_argument('--list', action='store_true',
                        help='List available Nuvoton devices')
    parser.add_argument('--test-connection', action='store_true',
                        help='Test connection to device')
    parser.add_argument('--color', nargs=3, type=int, metavar=('R', 'G', 'B'),
                        help='Set RGB color (0-255)')
    parser.add_argument('--hex', type=str, metavar='#RRGGBB',
                        help='Set color from hex string')
    parser.add_argument('--rainbow', type=int, nargs='?', const=10, metavar='SECONDS',
                        help='Rainbow effect (default: 10 seconds)')
    parser.add_argument('--pulse', nargs='+', metavar=('R', 'G', 'B', 'SECONDS'),
                        help='Pulse effect with color')
    parser.add_argument('--interactive', action='store_true',
                        help='Interactive mode')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    
    # List devices
    if args.list:
        devices = list_devices()
        print(f"\nFound {len(devices)} Nuvoton device(s):")
        for dev in devices:
            print(f"  - {dev['product']} (VID:{dev['vendor_id']:04x} PID:{dev['product_id']:04x})")
            print(f"    Serial: {dev['serial']}")
        return 0
    
    # Test connection
    if args.test_connection:
        from nuvoton_hid import test_connection
        return 0 if test_connection() else 1
    
    # Connect to device for other operations
    device = NuvotonDevice()
    if not device.connect():
        print("ERROR: Failed to connect to device")
        print("Make sure the device is connected and you have permissions")
        print("On Linux, you may need to add udev rules (see documentation)")
        return 1
    
    try:
        # Execute commands
        if args.color:
            r, g, b = args.color
            set_static_color(device, r, g, b)
        
        elif args.hex:
            r, g, b = hex_color_to_rgb(args.hex)
            set_static_color(device, r, g, b)
        
        elif args.rainbow is not None:
            rainbow_effect(device, args.rainbow)
        
        elif args.pulse:
            if len(args.pulse) < 3:
                print("ERROR: Pulse requires at least R G B values")
                return 1
            r, g, b = int(args.pulse[0]), int(args.pulse[1]), int(args.pulse[2])
            duration = int(args.pulse[3]) if len(args.pulse) > 3 else 10
            pulse_effect(device, r, g, b, duration)
        
        elif args.interactive:
            interactive_mode(device)
        
        else:
            parser.print_help()
            return 1
        
    finally:
        device.disconnect()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

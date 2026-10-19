"""
Hook TRCC.exe's WriteFile calls to capture exactly what it sends to the HID device.
This will reveal the exact byte-level protocol.

Usage:
1. Start TRCC.exe
2. Run this script  
3. Change a color in TRCC
4. See the actual packets
"""
import frida
import sys
import time

HOOK_SCRIPT = """
'use strict';

// Hook WriteFile in kernel32.dll
const WriteFile = Module.getExportByName('kernel32.dll', 'WriteFile');

Interceptor.attach(WriteFile, {
    onEnter: function(args) {
        const handle = args[0];
        const buffer = args[1];
        const nBytesToWrite = args[2].toInt32();
        
        // Only capture writes of 65 bytes (Report ID + 64 data) or similar HID sizes
        if (nBytesToWrite >= 5 && nBytesToWrite <= 513) {
            const data = new Uint8Array(ArrayBuffer.wrap(buffer, nBytesToWrite));
            
            // Check if it looks like our HID protocol (magic header DA DB DC DD)
            // Remember: byte[0] is Report ID (0x00), data starts at byte[1]
            const hasReportId = (data[0] === 0x00);
            const hasMagic = (
                (data[1] === 0xDA && data[2] === 0xDB && data[3] === 0xDC && data[4] === 0xDD) ||
                (data[0] === 0xDA && data[1] === 0xDB && data[2] === 0xDC && data[3] === 0xDD)
            );
            
            // Log ALL writes that are 65 bytes (HID report size)
            if (nBytesToWrite === 65 || hasMagic) {
                const hexBytes = [];
                for (let i = 0; i < Math.min(nBytesToWrite, 65); i++) {
                    hexBytes.push(('0' + data[i].toString(16)).slice(-2).toUpperCase());
                }
                
                const timestamp = Date.now();
                send({
                    type: 'writefile',
                    handle: handle.toString(),
                    size: nBytesToWrite,
                    hex: hexBytes.join(' '),
                    hasReportId: hasReportId,
                    hasMagic: hasMagic,
                    timestamp: timestamp
                });
            }
        }
    }
});

send({type: 'ready', message: 'WriteFile hook installed! Change a color in TRCC to capture packets.'});
"""

def on_message(message, data):
    if message['type'] == 'send':
        payload = message['payload']
        if payload['type'] == 'ready':
            print(f"\n[*] {payload['message']}")
        elif payload['type'] == 'writefile':
            ts = payload['timestamp']
            size = payload['size']
            handle = payload['handle']
            hex_data = payload['hex']
            has_magic = payload['hasMagic']
            
            marker = "*** MAGIC ***" if has_magic else ""
            print(f"\n[WRITE] handle={handle} size={size} {marker}")
            
            # Pretty print in groups of 16
            bytes_list = hex_data.split(' ')
            for i in range(0, len(bytes_list), 16):
                chunk = ' '.join(bytes_list[i:i+16])
                offset = f"{i:04X}"
                print(f"  {offset}: {chunk}")
    elif message['type'] == 'error':
        print(f"[ERROR] {message.get('description', message)}")

def main():
    print("Looking for TRCC.exe process...")
    
    try:
        session = frida.attach("TRCC.exe")
        print("Attached to TRCC.exe!")
    except frida.ProcessNotFoundError:
        print("TRCC.exe not found! Please start TRCC first.")
        print("Trying to find similar processes...")
        
        device = frida.get_local_device()
        for proc in device.enumerate_processes():
            name = proc.name.lower()
            if 'trcc' in name or 'thermalright' in name:
                print(f"  Found: {proc.name} (PID: {proc.pid})")
        sys.exit(1)
    
    script = session.create_script(HOOK_SCRIPT)
    script.on('message', on_message)
    script.load()
    
    print("\n" + "=" * 60)
    print("CAPTURING TRCC WriteFile CALLS")
    print("Now change a LED color in TRCC and watch the output.")
    print("Press Ctrl+C to stop.")
    print("=" * 60)
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nDetaching...")
        session.detach()
        print("Done.")

if __name__ == '__main__':
    main()

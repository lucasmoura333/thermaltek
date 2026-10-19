/**
 * Frida Hook Script — Nuvoton 0x0416:0x8001 TRCC Protocol Capture (v2)
 *
 * Simplified version for .NET applications using P/Invoke.
 * Hooks WriteFile/ReadFile and DeviceIoControl at kernel32 level.
 *
 * Usage:
 *   frida -p <PID> -l frida_hid_hook.js
 */

"use strict";

// ── State ──────────────────────────────────────────────────────────────────
var nuvotonHandles = {};  // handle string → path
var packetCounter = 0;

// ── Helpers ────────────────────────────────────────────────────────────────
function hexDump(arrayBuf, maxLen) {
    if (!arrayBuf) return "  (null)";
    var view;
    try { view = new Uint8Array(arrayBuf); } catch(e) { return "  (unreadable: " + e + ")"; }
    var limit = maxLen ? Math.min(maxLen, view.byteLength) : view.byteLength;
    var lines = [];
    for (var off = 0; off < limit; off += 16) {
        var hex = [], asc = [];
        for (var j = off; j < Math.min(off + 16, limit); j++) {
            var b = view[j];
            hex.push(("0" + b.toString(16)).slice(-2));
            asc.push(b >= 0x20 && b < 0x7f ? String.fromCharCode(b) : ".");
        }
        lines.push("  " + ("000" + off).slice(-4) + "  " + hex.join(" ").replace(/(.{47})/, "$1") + "  " + asc.join(""));
    }
    return lines.join("\n");
}

function readMem(ptr, len) {
    try { return Memory.readByteArray(ptr, len); } catch(e) { return null; }
}

function log(direction, fn, handle, buf, len) {
    var id = ++packetCounter;
    var ts = new Date().toISOString().slice(11, 23);
    var dump = hexDump(buf, len);
    console.log(
        "\n┌──────────────────────────────────────────────────\n" +
        "│ #" + id + " [" + ts + "] " + direction + " — " + fn + "\n" +
        "│ handle=" + handle + "  len=" + len + "\n" +
        "├──────────────────────────────────────────────────\n" +
        dump + "\n" +
        "└──────────────────────────────────────────────────"
    );
}

function isNuvoton(handle) {
    return handle in nuvotonHandles;
}

// ── 1. CreateFileW — identify the Nuvoton HID handle ──────────────────────
var cfwAddr = Module.findExportByName("kernelbase.dll", "CreateFileW") ||
              Module.findExportByName("kernel32.dll", "CreateFileW");

if (cfwAddr) {
    Interceptor.attach(cfwAddr, {
        onEnter: function(args) {
            try { this.path = args[0].readUtf16String(); } catch(e) { this.path = ""; }
        },
        onLeave: function(ret) {
            if (!this.path) return;
            var pl = this.path.toLowerCase();
            if (pl.indexOf("vid_0416") !== -1 && pl.indexOf("pid_8001") !== -1) {
                var h = ret.toString();
                nuvotonHandles[h] = this.path;
                console.log("[+] Nuvoton handle opened: " + h);
                console.log("    Path: " + this.path);
            }
        }
    });
    console.log("[+] Hooked CreateFileW");
} else {
    console.warn("[!] CreateFileW not found");
}

// ── 2. CloseHandle ────────────────────────────────────────────────────────
var chAddr = Module.findExportByName("kernelbase.dll", "CloseHandle") ||
             Module.findExportByName("kernel32.dll", "CloseHandle");
if (chAddr) {
    Interceptor.attach(chAddr, {
        onEnter: function(args) {
            var h = args[0].toString();
            if (h in nuvotonHandles) {
                console.log("[-] Nuvoton handle closed: " + h);
                delete nuvotonHandles[h];
            }
        }
    });
}

// ── 3. WriteFile ───────────────────────────────────────────────────────────
var wfAddr = Module.findExportByName("kernelbase.dll", "WriteFile") ||
             Module.findExportByName("kernel32.dll", "WriteFile");
if (wfAddr) {
    Interceptor.attach(wfAddr, {
        onEnter: function(args) {
            this.h   = args[0].toString();
            this.buf = args[1];
            this.len = args[2].toInt32();
        },
        onLeave: function(ret) {
            if (!isNuvoton(this.h)) return;
            var data = readMem(this.buf, this.len);
            log("HOST→DEV", "WriteFile", this.h, data, this.len);
        }
    });
    console.log("[+] Hooked WriteFile");
}

// ── 4. ReadFile ────────────────────────────────────────────────────────────
var rfAddr = Module.findExportByName("kernelbase.dll", "ReadFile") ||
             Module.findExportByName("kernel32.dll", "ReadFile");
if (rfAddr) {
    Interceptor.attach(rfAddr, {
        onEnter: function(args) {
            this.h   = args[0].toString();
            this.buf = args[1];
            this.len = args[2].toInt32();
        },
        onLeave: function(ret) {
            if (!isNuvoton(this.h)) return;
            var data = readMem(this.buf, this.len);
            log("DEV→HOST", "ReadFile", this.h, data, this.len);
        }
    });
    console.log("[+] Hooked ReadFile");
}

// ── 5. DeviceIoControl ─────────────────────────────────────────────────────
var IOCTL_HID_SET_OUTPUT = 0xB0195;
var IOCTL_HID_GET_INPUT  = 0xB0191;
var IOCTL_HID_SET_FEAT   = 0xB0189;
var IOCTL_HID_GET_FEAT   = 0xB0185;

var diocAddr = Module.findExportByName("kernelbase.dll", "DeviceIoControl") ||
               Module.findExportByName("kernel32.dll", "DeviceIoControl");
if (diocAddr) {
    Interceptor.attach(diocAddr, {
        onEnter: function(args) {
            this.h      = args[0].toString();
            this.ioctl  = args[1].toUInt32();
            this.inBuf  = args[2];
            this.inLen  = args[3].toInt32();
            this.outBuf = args[4];
            this.outLen = args[5].toInt32();
            this.isHid  = (this.ioctl === IOCTL_HID_SET_OUTPUT ||
                           this.ioctl === IOCTL_HID_GET_INPUT  ||
                           this.ioctl === IOCTL_HID_SET_FEAT   ||
                           this.ioctl === IOCTL_HID_GET_FEAT);
        },
        onLeave: function(ret) {
            // Log ALL HID ioctls, not just Nuvoton — we may not have identified handle yet
            if (!this.isHid) return;
            var isSet = (this.ioctl === IOCTL_HID_SET_OUTPUT || this.ioctl === IOCTL_HID_SET_FEAT);
            var dir   = isSet ? "HOST→DEV" : "DEV→HOST";
            var buf   = isSet ? readMem(this.inBuf, this.inLen) : readMem(this.outBuf, this.outLen);
            var len   = isSet ? this.inLen : this.outLen;
            log(dir, "DeviceIoControl(0x" + this.ioctl.toString(16).toUpperCase() + ")", this.h, buf, len);
        }
    });
    console.log("[+] Hooked DeviceIoControl");
}

// ── 6. HidD_* functions (from hid.dll if loaded) ──────────────────────────
function tryHookHid(fnName, direction) {
    var addr = Module.findExportByName("hid.dll", fnName);
    if (!addr) {
        // hid.dll might not be loaded yet — try after a delay via Module.load
        console.log("[?] " + fnName + " not found yet (hid.dll may load later)");
        return;
    }
    Interceptor.attach(addr, {
        onEnter: function(args) {
            this.h   = args[0].toString();
            this.buf = args[1];
            this.len = args[2].toInt32();
        },
        onLeave: function(ret) {
            var buf = readMem(this.buf, Math.min(this.len, 65));
            log(direction, fnName, this.h, buf, Math.min(this.len, 65));
        }
    });
    console.log("[+] Hooked hid.dll!" + fnName);
}

tryHookHid("HidD_SetOutputReport", "HOST→DEV [OutputReport]");
tryHookHid("HidD_GetInputReport",  "DEV→HOST [InputReport]");
tryHookHid("HidD_SetFeature",      "HOST→DEV [SetFeature]");
tryHookHid("HidD_GetFeature",      "DEV→HOST [GetFeature]");

// ── Ready ──────────────────────────────────────────────────────────────────
console.log("\n====================================================");
console.log("[*] Nuvoton HID Hook ACTIVE");
console.log("[*] Device: VID_0416 PID_8001");
console.log("[*] Perform operations in TRCC now");
console.log("[*] Ctrl+C to stop and save");
console.log("====================================================\n");

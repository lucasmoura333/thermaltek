/**
 * Frida Hook Script — Nuvoton 0x0416:0x8001 TRCC Protocol Capture (v3)
 *
 * v3 (frida 17 compatible):
 *   - Module.findExportByName removed in frida 17 -> getExport() helper with
 *     fallbacks (Module.getExportByName / module.getExportByName / global).
 *   - Hooks BOTH kernelbase.dll and kernel32.dll copies of each export (the
 *     kernel32 ones are forwarders — sitting only on them misses the call).
 *   - Adds ntdll!NtWriteFile as the ultimate net for HID writes (UsbHid.dll
 *     P/Invokes kernel32!WriteFile — see UsbHid_decomp.il).
 *   - Retries hid.dll exports after load (hid.dll may not be loaded yet when
 *     the script is injected).
 *   - Packets are delivered with send() so run_frida_hook.py writes them to
 *     the capture file (console.log alone is not persisted).
 *
 * Usage:
 *   frida -p <PID> -l frida_hid_hook.js
 */

"use strict";

// ── State ──────────────────────────────────────────────────────────────────
var nuvotonHandles = {};  // handle string → path
var packetCounter = 0;

// ── Export resolution (frida 17 compatible) ────────────────────────────────
function getExport(moduleName, name) {
    try {
        if (typeof Module.getExportByName === "function") {
            var a = Module.getExportByName(moduleName, name);
            if (a) return a;
        }
    } catch (e) { /* fall through */ }
    if (moduleName) {
        try {
            var m = Process.getModuleByName(moduleName);
            if (m && typeof m.getExportByName === "function") {
                var b = m.getExportByName(name);
                if (b) return b;
            }
        } catch (e2) { /* fall through */ }
        return null;
    }
    try {
        if (typeof Module.findGlobalExportByName === "function") {
            return Module.findGlobalExportByName(name);
        }
        if (typeof Module.findExportByName === "function") {
            return Module.findExportByName(null, name);
        }
    } catch (e3) { /* give up */ }
    return null;
}

function resolveAll(name) {
    var addrs = [];
    ["kernelbase.dll", "kernel32.dll"].forEach(function (mod) {
        var a = getExport(mod, name);
        if (a && addrs.indexOf(a) === -1) addrs.push(a);
    });
    var g = getExport(null, name);
    if (g && addrs.indexOf(g) === -1) addrs.push(g);
    return addrs;
}

// ── Helpers ────────────────────────────────────────────────────────────────
function hexDump(arrayBuf, maxLen) {
    if (!arrayBuf) return "  (null)";
    var view;
    try { view = new Uint8Array(arrayBuf); } catch (e) { return "  (unreadable: " + e + ")"; }
    var limit = maxLen ? Math.min(maxLen, view.byteLength) : view.byteLength;
    var lines = [];
    for (var off = 0; off < limit; off += 16) {
        var hex = [], asc = [];
        for (var j = off; j < Math.min(off + 16, limit); j++) {
            var b = view[j];
            hex.push(("0" + b.toString(16)).slice(-2));
            asc.push(b >= 0x20 && b < 0x7f ? String.fromCharCode(b) : ".");
        }
        lines.push("  " + ("000" + off).slice(-4) + "  " + hex.join(" ") + "  " + asc.join(""));
    }
    return lines.join("\n");
}

function readMem(ptr, len) {
    try { return Memory.readByteArray(ptr, len); } catch (e) { return null; }
}

function log(direction, fn, handle, buf, len) {
    var id = ++packetCounter;
    var ts = new Date().toISOString().slice(11, 23);
    send("PACKET #" + id + " [" + ts + "] " + direction + " — " + fn +
         " | handle=" + handle + " len=" + len + "\n" + hexDump(buf, len));
}

function isNuvoton(handle) {
    return handle in nuvotonHandles;
}

// Handle-independent detection: the Nuvoton packets always start with the
// DA DB DC DD magic (after the optional Report ID 0x00).  This catches I/O on
// DUPLICATED handles (which never appear in CreateFileW) and any other path
// we failed to register.
function looksLikeNuvoton(ptr, len) {
    if (!ptr || len < 5) return false;
    var b = readMem(ptr, Math.min(len, 8));
    if (!b) return false;
    var v = new Uint8Array(b);
    if (v[0] === 0xDA && v[1] === 0xDB && v[2] === 0xDC && v[3] === 0xDD) return true;
    if (v[0] === 0x00 && v[1] === 0xDA && v[2] === 0xDB && v[3] === 0xDC && v[4] === 0xDD) return true;
    return false;
}

// ── 1. CreateFileW — identify the Nuvoton HID handle ──────────────────────
resolveAll("CreateFileW").forEach(function (addr) {
    Interceptor.attach(addr, {
        onEnter: function (args) {
            try { this.path = args[0].readUtf16String(); } catch (e) { this.path = ""; }
        },
        onLeave: function (ret) {
            if (!this.path) return;
            var pl = this.path.toLowerCase();
            if (pl.indexOf("vid_0416") !== -1 && pl.indexOf("pid_8001") !== -1) {
                var h = ret.toString();
                if (!(h in nuvotonHandles)) {
                    nuvotonHandles[h] = this.path;
                    send("[+] Nuvoton handle opened: " + h);
                }
            }
        }
    });
});
send("[+] Hooked CreateFileW");

// ── 2. CloseHandle ────────────────────────────────────────────────────────
resolveAll("CloseHandle").forEach(function (addr) {
    Interceptor.attach(addr, {
        onEnter: function (args) {
            var h = args[0].toString();
            if (h in nuvotonHandles) {
                send("[-] Nuvoton handle closed: " + h);
                delete nuvotonHandles[h];
            }
        }
    });
});

// ── 3. WriteFile ───────────────────────────────────────────────────────────
resolveAll("WriteFile").forEach(function (addr) {
    Interceptor.attach(addr, {
        onEnter: function (args) {
            this.h = args[0].toString();
            this.buf = args[1];
            this.len = args[2].toInt32();
        },
        onLeave: function () {
            var byHandle = isNuvoton(this.h);
            var byContent = looksLikeNuvoton(this.buf, this.len);
            if (!byHandle && !byContent) return;
            var data = readMem(this.buf, this.len);
            log("HOST→DEV", "WriteFile" + (byHandle ? "" : " [content]"), this.h, data, this.len);
        }
    });
});
send("[+] Hooked WriteFile");

// ── 3b. NtWriteFile (ultimate net — syscall layer) ────────────────────────
var ntwAddr = getExport("ntdll.dll", "NtWriteFile");
if (ntwAddr) {
    Interceptor.attach(ntwAddr, {
        onEnter: function (args) {
            this.h = args[0].toString();
            this.buf = args[5];
            try { this.len = args[6].toInt32(); } catch (e) { this.len = 0; }
        },
        onLeave: function () {
            if (!this.buf || this.buf.isNull()) return;
            var byHandle = isNuvoton(this.h);
            var byContent = looksLikeNuvoton(this.buf, this.len);
            if (!byHandle && !byContent) return;
            var data = readMem(this.buf, Math.min(this.len, 4096));
            if (data) log("HOST→DEV", "NtWriteFile" + (byHandle ? "" : " [content]"), this.h, data, this.len);
        }
    });
    send("[+] Hooked NtWriteFile");
} else {
    send("[!] NtWriteFile not found");
}

// ── 4. ReadFile ────────────────────────────────────────────────────────────
resolveAll("ReadFile").forEach(function (addr) {
    Interceptor.attach(addr, {
        onEnter: function (args) {
            this.h = args[0].toString();
            this.buf = args[1];
            this.len = args[2].toInt32();
        },
        onLeave: function () {
            if (!isNuvoton(this.h)) return;
            var data = readMem(this.buf, this.len);
            log("DEV→HOST", "ReadFile", this.h, data, this.len);
        }
    });
});

// ── 5. DeviceIoControl (any ioctl on the Nuvoton handle, plus all HID ioctls)
var IOCTL_HID_SET_OUTPUT = 0xB0195;
var IOCTL_HID_GET_INPUT  = 0xB0191;
var IOCTL_HID_SET_FEAT   = 0xB0189;
var IOCTL_HID_GET_FEAT   = 0xB0185;

resolveAll("DeviceIoControl").forEach(function (addr) {
    Interceptor.attach(addr, {
        onEnter: function (args) {
            this.h = args[0].toString();
            this.ioctl = args[1].toUInt32();
            this.inBuf = args[2];
            this.inLen = args[3].toInt32();
            this.outBuf = args[4];
            this.outLen = args[5].toInt32();
            this.isHid = (this.ioctl === IOCTL_HID_SET_OUTPUT ||
                          this.ioctl === IOCTL_HID_GET_INPUT ||
                          this.ioctl === IOCTL_HID_SET_FEAT ||
                          this.ioctl === IOCTL_HID_GET_FEAT);
        },
        onLeave: function () {
            if (!this.isHid && !isNuvoton(this.h)) return;
            var isSet = (this.ioctl === IOCTL_HID_SET_OUTPUT ||
                         this.ioctl === IOCTL_HID_SET_FEAT);
            var dir = isSet ? "HOST→DEV" : "DEV→HOST";
            var buf = isSet ? readMem(this.inBuf, this.inLen)
                            : readMem(this.outBuf, this.outLen);
            var len = isSet ? this.inLen : this.outLen;
            log(dir, "DeviceIoControl(0x" + this.ioctl.toString(16).toUpperCase() + ")",
                this.h, buf, len);
        }
    });
});
send("[+] Hooked DeviceIoControl");

// ── 6. hid.dll — retry hooks after TRCC loads it ──────────────────────────
var HID_FNS = [
    ["HidD_SetOutputReport", "HOST→DEV [OutputReport]"],
    ["HidD_GetInputReport",  "DEV→HOST [InputReport]"],
    ["HidD_SetFeature",      "HOST→DEV [SetFeature]"],
    ["HidD_GetFeature",      "DEV→HOST [GetFeature]"]
];
var hidAttached = {};
var hidTries = 0;
var hidTimer = setInterval(function () {
    hidTries++;
    var has = false;
    try { has = !!Process.getModuleByName("hid.dll"); } catch (e) { has = false; }
    if (has) {
        HID_FNS.forEach(function (pair) {
            if (hidAttached[pair[0]]) return;
            var addr = getExport("hid.dll", pair[0]);
            if (!addr) return;
            Interceptor.attach(addr, {
                onEnter: function (args) {
                    this.h = args[0].toString();
                    this.buf = args[1];
                    this.len = args[2].toInt32();
                },
                onLeave: function () {
                    var buf = readMem(this.buf, Math.min(this.len, 65));
                    if (!isNuvoton(this.h) && !looksLikeNuvoton(this.buf, this.len)) return;
                    log(pair[1], pair[0], this.h, buf, Math.min(this.len, 65));
                }
            });
            hidAttached[pair[0]] = true;
            send("[+] Hooked hid.dll!" + pair[0]);
        });
        var done = HID_FNS.every(function (p) { return hidAttached[p[0]]; });
        if (done) clearInterval(hidTimer);
    }
    if (hidTries > 120) clearInterval(hidTimer);
}, 500);

// ── Ready ──────────────────────────────────────────────────────────────────
send("[*] Nuvoton HID Hook v3 ACTIVE — VID_0416 PID_8001");

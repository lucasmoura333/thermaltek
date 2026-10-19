"""Enumerate all USB interfaces and endpoints on the Nuvoton cooler."""
import usb1

VID, PID = 0x0416, 0x8001

with usb1.USBContext() as ctx:
    dev = ctx.getByVendorIDAndProductID(VID, PID)
    if not dev:
        print("Device not found!")
        raise SystemExit(1)

    print(f"Device: {dev.getManufacturer()} / {dev.getProduct()}")
    print(f"  VID:PID  {dev.getVendorID():04X}:{dev.getProductID():04X}")
    print(f"  NumConfigs: {dev.getNumConfigurations()}\n")

    for cfg_idx in range(dev.getNumConfigurations()):
        cfg = dev[cfg_idx]
        print(f"  Config {cfg.getConfigurationValue()}:")
        for iface in cfg:
            for setting in iface:
                cls  = setting.getClass()
                scls = setting.getSubClass()
                prot = setting.getProtocol()
                print(f"    Interface {setting.getNumber()}.{setting.getAlternateSetting()}"
                      f"  class={cls:#04x}/{scls:#04x}/{prot:#04x}"
                      f"  [{setting.getNumEndpoints()} endpoints]")
                for ep in setting:
                    direction = "IN " if ep.getAddress() & 0x80 else "OUT"
                    xtype = {0: "Control", 1: "Isochronous", 2: "Bulk", 3: "Interrupt"}
                    tname = xtype.get(ep.getAttributes() & 3, "?")
                    print(f"      EP {ep.getAddress():#04x}  {direction}  {tname:11s}"
                          f"  maxPktSize={ep.getMaxPacketSize()}")

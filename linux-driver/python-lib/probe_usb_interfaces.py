import usb.core, usb.util, usb.backend.libusb1
import libusb_package
backend = libusb_package.get_libusb1_backend()

dev = usb.core.find(idVendor=0x0416, idProduct=0x8001, backend=backend)
if dev is None:
    print("Device not found via pyusb - install with: pip install pyusb")
else:
    print("Device:", dev.manufacturer, "/", dev.product)
    for cfg in dev:
        print(f"Config {cfg.bConfigurationValue}")
        for intf in cfg:
            cls = intf.bInterfaceClass
            print(f"  Interface {intf.bInterfaceNumber} alt={intf.bAlternateSetting} class=0x{cls:02x} sub=0x{intf.bInterfaceSubClass:02x} ({usb.util.get_string(dev, intf.iInterface) if intf.iInterface else 'no name'})")
            for ep in intf:
                direction = "IN" if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN else "OUT"
                ep_type = usb.util.endpoint_type(ep.bmAttributes)
                print(f"    EP 0x{ep.bEndpointAddress:02x} {direction} type={ep_type} maxpkt={ep.wMaxPacketSize}")

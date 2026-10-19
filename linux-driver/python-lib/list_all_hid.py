import hid
devs = hid.enumerate()
for d in devs:
    vid = d["vendor_id"]
    pid = d["product_id"]
    usage = d["usage"]
    ifn = d["interface_number"]
    mfg = d["manufacturer_string"]
    prod = d["product_string"]
    print("VID=%04x PID=%04x usage=%06x if=%d  %s/%s" % (vid, pid, usage, ifn, mfg, prod))

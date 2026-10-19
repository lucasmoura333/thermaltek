import hid

print("All USB HID devices:")
for d in hid.enumerate():
    vid = d['vendor_id']
    pid = d['product_id']
    prod = d.get('product_string', '')
    mfr = d.get('manufacturer_string', '')
    print(f"  VID={vid:04x} PID={pid:04x}  '{mfr}' / '{prod}'  path={d['path']}")

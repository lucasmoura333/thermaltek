import os

base = r'C:\Program Files (x86)\TRCCCAP\Data'
for root, dirs, files in os.walk(base):
    for fn in files:
        fp = os.path.join(root, fn)
        if fn.endswith('.png'): continue
        try:
            size = os.path.getsize(fp)
            if size == 0: continue
            data = open(fp, 'rb').read(120)
            text = data.decode('utf-8', errors='replace').replace('\n', '|').replace('\r', '')
            print("%-80s (%d): %s" % (fp[len(base):], size, text[:100]))
        except Exception as e:
            print("ERROR: %s: %s" % (fp, e))

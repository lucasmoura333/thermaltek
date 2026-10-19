"""Enumerate all methods and strings in USBLCDNEW.dll via dnfile."""
import dnfile

dn = dnfile.dnPE("USBLCDNEW.dll")

print("=== Methods ===")
for i, row in enumerate(dn.net.mdtables.MethodDef.rows):
    print(f"  {i:3d}  RVA={row.Rva:#010x}  Name={row.Name}")

print("\n=== TypeDef ===")
for row in dn.net.mdtables.TypeDef.rows:
    print(f"  {row.TypeNamespace}.{row.TypeName}")

print("\n=== MemberRef (external calls) ===")
for row in dn.net.mdtables.MemberRef.rows:
    print(f"  {row.Name}")

print("\n=== US (User Strings) ===")
heap = dn.net.metadata.streams_list
for s in heap:
    if hasattr(s, 'name') and s.name == b'#US':
        try:
            data = s.raw
            i = 1
            while i < len(data):
                length_byte = data[i]
                if length_byte == 0:
                    i += 1
                    continue
                # compressed length
                if length_byte & 0xC0 == 0xC0:
                    str_len = ((length_byte & 0x3F) << 24 | data[i+1] << 16 | data[i+2] << 8 | data[i+3]) >> 1
                    i += 4
                elif length_byte & 0x80 == 0x80:
                    str_len = ((length_byte & 0x3F) << 8 | data[i+1]) >> 1
                    i += 2
                else:
                    str_len = length_byte >> 1
                    i += 1
                if str_len == 0:
                    continue
                s_bytes = data[i:i + str_len*2]
                try:
                    txt = s_bytes.decode('utf-16-le', errors='replace').rstrip('\x00')
                    if txt.strip():
                        print(f"  {txt!r}")
                except Exception:
                    pass
                i += str_len * 2 + 1  # +1 for terminal byte
        except Exception as e:
            print(f"  (error reading US heap: {e})")

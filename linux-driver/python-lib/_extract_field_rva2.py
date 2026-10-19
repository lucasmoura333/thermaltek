"""Extract FieldRVA static byte arrays using dnfile."""
import dnfile
import pefile

pe = pefile.PE('USBLCDNEW.dll')

def rva_to_off(rva):
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            return s.PointerToRawData + (rva - s.VirtualAddress)
    return None

data = open('USBLCDNEW.dll', 'rb').read()

dn = dnfile.dnPE('USBLCDNEW.dll')
frva = dn.net.mdtables.FieldRva

print('FieldRVA table rows: %d' % frva.num_rows)
print()

entries = list(frva)
# Sort by RVA to determine array sizes
entries_sorted = sorted(entries, key=lambda r: r.Rva)

for i, r in enumerate(entries_sorted):
    rva_val = r.Rva
    field_tok_obj = r.Field
    # Get field row index
    if hasattr(field_tok_obj, 'row_index'):
        field_idx = field_tok_obj.row_index
    elif hasattr(field_tok_obj, 'value'):
        field_idx = field_tok_obj.value
    else:
        try:
            field_idx = int(field_tok_obj)
        except:
            field_idx = '?'

    raw_off = rva_to_off(rva_val)
    if raw_off is None:
        print('Field idx=%s RVA=0x%x -> no file offset' % (field_idx, rva_val))
        continue

    # Determine data size from next entry or read fixed amount
    if i + 1 < len(entries_sorted):
        next_rva = entries_sorted[i+1].Rva
        size = next_rva - rva_val
    else:
        size = 256  # read up to 256 bytes for last entry

    blob = data[raw_off: raw_off + min(size, 256)]
    hex_str = ' '.join('%02x' % b for b in blob)

    print('=== Field row=%s  RVA=0x%x  file=0x%x  size=%d ===' % (
        field_idx, rva_val, raw_off, len(blob)))
    for j in range(0, len(blob), 16):
        row = blob[j:j+16]
        h = ' '.join('%02x' % b for b in row)
        a = ''.join(chr(b) if 32 <= b < 127 else '.' for b in row)
        print('  %04x: %-47s  |%s|' % (j, h, a))
    print()

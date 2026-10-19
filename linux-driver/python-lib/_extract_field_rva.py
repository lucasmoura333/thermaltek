"""Extract FieldRVA data from USBLCDNEW.dll to find LCD packet headers."""
import struct

def read_varint(data, offset):
    b = data[offset]
    if b < 0x80:
        return b, offset + 1
    elif b < 0xC0:
        return ((b & 0x3F) << 8) | data[offset+1], offset + 2
    else:
        return (((b & 0x1F) << 24) | (data[offset+1] << 16) |
                (data[offset+2] << 8) | data[offset+3]), offset + 4

data = open('USBLCDNEW.dll', 'rb').read()

e_lfanew = struct.unpack_from('<I', data, 0x3C)[0]
num_sections = struct.unpack_from('<H', data, e_lfanew + 6)[0]
opt_size = struct.unpack_from('<H', data, e_lfanew + 20)[0]
opt_off = e_lfanew + 24
magic = struct.unpack_from('<H', data, opt_off)[0]
is64 = (magic == 0x20B)
dd_off = opt_off + (112 if not is64 else 128)
clr_rva  = struct.unpack_from('<I', data, dd_off + 14*8)[0]
clr_size = struct.unpack_from('<I', data, dd_off + 14*8 + 4)[0]
sections_off = e_lfanew + 24 + opt_size

def rva_to_off(rva):
    for i in range(num_sections):
        sec = sections_off + i * 40
        vsize  = struct.unpack_from('<I', data, sec + 8)[0]
        vaddr  = struct.unpack_from('<I', data, sec + 12)[0]
        rawoff = struct.unpack_from('<I', data, sec + 20)[0]
        if vaddr <= rva < vaddr + max(vsize, 1):
            return rawoff + (rva - vaddr)
    return None

clr_off = rva_to_off(clr_rva)
meta_rva  = struct.unpack_from('<I', data, clr_off + 8)[0]
meta_off  = rva_to_off(meta_rva)

# Parse metadata stream headers
sig = struct.unpack_from('<I', data, meta_off)[0]
assert sig == 0x424A5342, 'not metadata'
ver_len = struct.unpack_from('<I', data, meta_off + 12)[0]
streams_off = meta_off + 16 + ver_len
streams_off = (streams_off + 3) & ~3
num_streams = struct.unpack_from('<H', data, streams_off + 2)[0]
stream_headers = {}
p = streams_off + 4
for _ in range(num_streams):
    soff = struct.unpack_from('<I', data, p)[0]
    ssize = struct.unpack_from('<I', data, p + 4)[0]
    sname = data[p+8: p+8+16].split(b'\x00')[0].decode()
    stream_headers[sname] = (meta_off + soff, ssize)
    p = p + 8 + ((len(sname) + 1 + 3) & ~3)

print('Streams:', list(stream_headers.keys()))

# Parse #~ (tables stream)
tbl_off, tbl_sz = stream_headers.get('#~', stream_headers.get('#-', (0, 0)))
heap_sizes = data[tbl_off + 6]
wide_string = bool(heap_sizes & 1)
wide_guid   = bool(heap_sizes & 2)
wide_blob   = bool(heap_sizes & 4)
valid_mask = struct.unpack_from('<Q', data, tbl_off + 8)[0]
sorted_mask = struct.unpack_from('<Q', data, tbl_off + 16)[0]

# Count rows per table
table_row_counts = {}
p = tbl_off + 24
for i in range(64):
    if valid_mask & (1 << i):
        cnt = struct.unpack_from('<I', data, p)[0]
        table_row_counts[i] = cnt
        p += 4

print('Tables present:', sorted(table_row_counts.keys()))
print('Row counts (key tables):')
for t in [1, 2, 4, 6, 10, 28]:
    if t in table_row_counts:
        print('  Table %d: %d rows' % (t, table_row_counts[t]))

def n_rows(t): return table_row_counts.get(t, 0)

def idx_size(t):
    return 4 if n_rows(t) >= 65536 else 2

# Field table (0x04) RVA table (0x1D = 29)
# FieldRVA: RVA (4 bytes) + Field index (2 or 4 bytes)
field_rva_table = 29
if field_rva_table in table_row_counts:
    n = table_row_counts[field_rva_table]
    print('\n=== FieldRVA table (%d rows) ===' % n)
    # Row format: RVA u4, Field coded-index
    fi_size = idx_size(4)  # Field table = 0x04
    # But we need to calculate the actual offset of the FieldRVA table
    # by summing all preceding table row data sizes
    
    # Simplified: walk tables in order
    cur = p  # p is now right after row count section
    table_offsets = {}
    p2 = tbl_off + 24 + 4 * len(table_row_counts)
    
    # Row sizes for each table we care about  
    # This requires knowing all row sizes - simplified approach:
    # Use a known-working approach with dnfile's raw data
    pass

# Alternative: search for RuntimeHelpers.InitializeArray calls and trace back the field
# We know field token is 0x04000025 = Field table row 37 (1-based = 0x25)
# The FieldRVA table maps fields to RVAs in the data section

# Let me find the FieldRVA table directly by brute-force
# FieldRVA rows are: 4 bytes RVA + 2 bytes field index
target_field_idx = 0x25  # row 37
print('\n=== Searching for field index 0x25 in FieldRVA context ===')

# The #~ stream has table data after counts
# Parse all tables before FieldRVA (table 29 = 0x1D)
# Tables sorted by index: we need to size each one
# Let's use dnfile if available

try:
    import dnfile
    dn = dnfile.dnPE('USBLCDNEW.dll')
    if hasattr(dn.net.mdtables, 'FieldRva'):
        t = dn.net.mdtables.FieldRva
        print('\nFieldRVA rows from dnfile:')
        for r in t:
            rva_val = r.Rva
            field_tok = r.Field.row_index if hasattr(r.Field, 'row_index') else r.Field
            raw_off = rva_to_off(rva_val) if rva_val else None
            print('  FieldRVA row: rva=0x%x -> file_offset=0x%x, field_idx=%s' % (
                rva_val, raw_off if raw_off else 0, field_tok))
            if raw_off and field_tok in (0x25, 37):
                print('  *** TARGET FIELD 0x25 ***')
                blob = data[raw_off:raw_off+128]
                print('  Bytes:', ' '.join('%02x' % b for b in blob))
    else:
        print('No FieldRva table in dnfile')
    
    # Also dump ALL FieldRVA data (all literal arrays)
    if hasattr(dn.net.mdtables, 'FieldRva'):
        for r in dn.net.mdtables.FieldRva:
            rva_val = r.Rva
            field_tok = r.Field.row_index if hasattr(r.Field, 'row_index') else r.Field
            raw_off = rva_to_off(rva_val)
            if raw_off:
                print('\n--- Field row %d at RVA 0x%x (file 0x%x) ---' % (field_tok, rva_val, raw_off))
                # Determine size: look at next FieldRVA or read 128 bytes
                blob = data[raw_off:raw_off+128]
                hex_row = ' '.join('%02x' % b for b in blob[:64])
                print('  First 64 bytes: ' + hex_row)
except Exception as ex:
    print('dnfile error:', ex)
    import traceback; traceback.print_exc()

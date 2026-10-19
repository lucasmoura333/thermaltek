"""Decode key method references in USBLCDNEW.dll."""
import dnfile

dn = dnfile.dnPE('USBLCDNEW.dll')

print('=== MemberRef table (method references) ===')
for i, row in enumerate(dn.net.mdtables.MemberRef):
    name = str(row.Name)
    cls = ''
    if hasattr(row.Class, 'row_index'):
        try:
            parent_row = row.Class.row_index
            parent_table = type(row.Class).__name__
            cls = '%s[%d]' % (parent_table, parent_row)
        except:
            cls = str(row.Class)
    print('  [%2d] 0x%08x  %-40s  (%s)' % (i+1, 0x0a000000 | (i+1), name, cls))

print()
print('=== TypeRef table (referenced types) ===')
for i, row in enumerate(dn.net.mdtables.TypeRef):
    name = str(row.TypeName)
    ns = str(row.TypeNamespace) if row.TypeNamespace else ''
    print('  [%2d] 0x%08x  %s.%s' % (i+1, 0x01000000 | (i+1), ns, name))

print()
print('=== Field table (class fields) ===')
for i, row in enumerate(dn.net.mdtables.Field):
    name = str(row.Name)
    print('  [%2d] 0x%08x  %s' % (i+1, 0x04000000 | (i+1), name))

print()
print('=== MethodDef table ===')
for i, row in enumerate(dn.net.mdtables.MethodDef):
    name = str(row.Name)
    print('  [%2d] 0x%08x  %s  RVA=0x%x' % (i+1, 0x06000000 | (i+1), name, row.Rva))

"""
Read TRCC's shared memory to capture the LCD display data format.
Run this while TRCC is open and showing temperatures on the display.
"""
import sys, ctypes, struct
sys.path.insert(0, r'F:\helpmeplease\linux-driver\python-lib\lhm\pkg2')
import clr
from System.Reflection import Assembly, BindingFlags
from System import Array, Byte

asm = Assembly.LoadFile(r'C:\Program Files\TRCCCAP\USBLCDNEW.dll')
BF = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance

dc_type = asm.GetType("Examples.DCReadWriteAsync")
instance = dc_type.GetConstructors(BF)[0].Invoke(None)

print("DCReadWriteAsync instance created")

# Call InitMemorySizeRGB
init_method = dc_type.GetMethod("InitMemorySizeRGB", BF)
result = init_method.Invoke(instance, None)
print(f"InitMemorySizeRGB returned: {result!r}")

# Try ReadShareMemoryRGB - check its signature
read_method = dc_type.GetMethod("ReadShareMemoryRGB", BF)
params = read_method.GetParameters()
print("ReadShareMemoryRGB params:")
for p in params:
    print(f"  {p.Name}: {p.ParameterType}")

write_method = dc_type.GetMethod("WriteShareMemoryRGB", BF)
params2 = write_method.GetParameters()
print("WriteShareMemoryRGB params:")
for p in params2:
    print(f"  {p.Name}: {p.ParameterType}")

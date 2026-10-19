from hardware_monitor import list_all_sensors
sensors = list_all_sensors()
for s in sensors:
    if 'Temperature' in s['type'] or 'Load' in s['type'] or 'Clock' in s['type']:
        print(f"{s['hardware'][:45]:45s}  {s['type']:12s}  {s['sensor']:30s}  {s['value']}")

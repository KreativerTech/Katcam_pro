
# -*- coding: utf-8 -*-
import shutil
from typing import Optional

def _read_cpu_temp_c() -> Optional[float]:
    try:
        import psutil
        temps = psutil.sensors_temperatures()
        if temps:
            for entries in temps.values():
                if entries:
                    cur = entries[0].current
                    if cur is not None:
                        return float(cur)
    except Exception:
        pass
    return None

def _read_cpu_percent() -> Optional[float]:
    try:
        import psutil
        return psutil.cpu_percent(interval=None)
    except Exception:
        return None

def _read_mem_percent() -> Optional[float]:
    try:
        import psutil
        return psutil.virtual_memory().percent
    except Exception:
        return None

def _read_free_space_bytes(path) -> Optional[int]:
    try:
        usage = shutil.disk_usage(path)
        return usage.free
    except Exception:
        return None

def fmt_bytes(b):
    if b is None:
        return "—"
    for unit in ["B","KB","MB","GB","TB"]:
        if b < 1024:
            return f"{b:.0f} {unit}"
        b /= 1024
    return f"{b:.0f} PB"

def fmt_pct(p):
    return "—" if p is None else f"{p:.0f}%"
def fmt_temp(t):
    return "—" if t is None else f"{t:.1f}°C"

def read_all(photo_dir):
    t = _read_cpu_temp_c()
    cpu = _read_cpu_percent()
    ram = _read_mem_percent()
    free = _read_free_space_bytes(photo_dir) if photo_dir else None
    return t, cpu, ram, free

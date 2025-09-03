
# -*- coding: utf-8 -*-
import os, sys

def has_write_access(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        testfile = os.path.join(path, ".katcam_write_test")
        with open(testfile, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(testfile)
        return True
    except Exception:
        return False

def get_startup_dir():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs\Startup")

def startup_bat_path():
    sd = get_startup_dir()
    if not sd:
        return None
    return os.path.join(sd, "KatcamPro_start.bat")

def is_autostart_enabled():
    p = startup_bat_path()
    return bool(p and os.path.exists(p))

def enable_autostart():
    p = startup_bat_path()
    if not p:
        raise RuntimeError("No se pudo resolver la carpeta de inicio de Windows.")
    exe = sys.executable
    script = os.path.abspath(sys.argv[0])
    workdir = os.path.dirname(script)
    lines = [
        "@echo off",
        f'cd /d "{workdir}"',
        f'start "" /MIN "{exe}" "{script}"'
    ]
    with open(p, "w", encoding="utf-8") as f:
        f.write("\r\n".join(lines))

def disable_autostart():
    p = startup_bat_path()
    if p and os.path.exists(p):
        try:
            os.remove(p)
        except Exception:
            pass

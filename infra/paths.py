
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
    # Verificar entrada del registro primero
    try:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Run",
                                0, winreg.KEY_READ) as rk:
                winreg.QueryValueEx(rk, "KatcamPro")
                return True  # La entrada existe en el registro
        except FileNotFoundError:
            # La entrada no existe en el registro, verificar archivo .bat
            pass
        except Exception:
            # Error al leer el registro, verificar archivo .bat
            pass
    except Exception:
        # winreg no disponible, verificar archivo .bat
        pass
    
    # Verificar archivo .bat como fallback
    p = startup_bat_path()
    return bool(p and os.path.exists(p))

def enable_autostart():
    p = startup_bat_path()
    if not p:
        raise RuntimeError("No se pudo resolver la carpeta de inicio de Windows.")
    # Intentar crear una entrada en el Run key del usuario (HKCU) primero.
    try:
        import winreg
        exe = sys.executable
        frozen = bool(getattr(sys, "frozen", False))

        # Comando a ejecutar:
        # - En exe (PyInstaller): "<exe>"
        # - En dev: "<python>" "<script.py>"
        if frozen:
            cmd = f'"{exe}"'
        else:
            script = os.path.abspath(sys.argv[0])
            cmd = f'"{exe}" "{script}"'
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Run",
                                0, winreg.KEY_SET_VALUE) as rk:
                winreg.SetValueEx(rk, "KatcamPro", 0, winreg.REG_SZ, cmd)
            return
        except Exception:
            # Si no pudo escribir en el registro (p. ej. permisos), caemos al .bat
            pass
    except Exception:
        # Si winreg no está disponible (no-Windows env), continuar con .bat
        pass

    # Fallback: escribir un archivo .bat en la carpeta Startup
    exe = sys.executable
    frozen = bool(getattr(sys, "frozen", False))
    script = os.path.abspath(sys.argv[0])
    workdir = os.path.dirname(exe if frozen else script)
    lines = [
        "@echo off",
        f'cd /d "{workdir}"',
        (f'start "" /MIN "{exe}"' if frozen else f'start "" /MIN "{exe}" "{script}"')
    ]
    with open(p, "w", encoding="utf-8") as f:
        f.write("\r\n".join(lines))

def disable_autostart():
    # Eliminar entrada del registro (si existe)
    try:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Run",
                                0, winreg.KEY_SET_VALUE) as rk:
                winreg.DeleteValue(rk, "KatcamPro")
        except FileNotFoundError:
            # La entrada no existe en el registro, está bien
            pass
        except Exception:
            # Error al eliminar del registro, continuar con archivo .bat
            pass
    except Exception:
        # winreg no disponible, continuar con archivo .bat
        pass
    
    # Eliminar archivo .bat de la carpeta Startup (fallback)
    p = startup_bat_path()
    if p and os.path.exists(p):
        try:
            os.remove(p)
        except Exception:
            pass

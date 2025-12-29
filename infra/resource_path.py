# infra/resource_path.py
from pathlib import Path
import sys

def resource_path(rel: str) -> str:
    """
    Devuelve ruta válida a un recurso (p.ej. 'assets/logo.png')
    en:
      - Dev (ejecutando .py)
      - PyInstaller 6 onedir (usa carpeta _internal)
      - PyInstaller onefile (usa _MEIPASS temporal)
    """
    rel = rel.replace("\\", "/").lstrip("/")
    candidates = []

    # Cuando está congelado por PyInstaller
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        # onedir nuevo (PyInstaller 6)
        candidates += [exe_dir / rel, exe_dir / "_internal" / rel]
        # onefile (desempaquetado temporal)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            base = Path(meipass)
            candidates += [base / rel, base / "_internal" / rel]

    # Dev (fuente)
    candidates.append(Path(__file__).resolve().parent.parent / rel)  # subir desde infra/

    for p in candidates:
        if p.exists():
            return str(p)

    # Fallback: por si aún no existe (útil para logs)
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    return str(base / rel)

# infra/logging_setup.py
import logging, os, sys
from logging.handlers import RotatingFileHandler

def setup_logging(app_name="Katcam", dev_fallback="."):
    # En instalado: %PROGRAMDATA%\Katcam\logs ; en dev: ./logs
    base = os.path.join(os.getenv("PROGRAMDATA", dev_fallback), app_name, "logs")
    os.makedirs(base, exist_ok=True)
    path = os.path.join(base, "katcam.log")

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    fh = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Consola (útil en dev)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    # Hook global de errores no capturados
    def _crash_hook(etype, evalue, etb):
        logging.exception("UNCAUGHT", exc_info=(etype, evalue, etb))
    sys.excepthook = _crash_hook

    return path

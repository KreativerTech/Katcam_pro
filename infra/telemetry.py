"""telemetry.py
Registro ligero de eventos y métricas (similar a un Sentry minimalista offline).

Características:
 - Cola en memoria con snapshot circular.
 - Escritura en JSONL (append) para análisis posterior.
 - API simple: log_event(tipo, **campos), log_error(exc, context=...).
 - Función dump_state(state) para capturar banderas clave.
"""
from __future__ import annotations
import json, os, threading, time, traceback, datetime as _dt, logging, gzip, shutil
from typing import Any, Dict, Optional

_LOCK = threading.Lock()
_BUFFER = []  # circular (mantener últimos N en memoria)
_MAX_IN_MEMORY = 500
_LOG_PATH: Optional[str] = None
_TELEMETRY_LOGGER: Optional[logging.Logger] = None
_USE_LOGGER = False

def init_telemetry(base_dir: str):
    """Inicializa archivo JSONL en base_dir/telemetry/telemetry.log"""
    global _LOG_PATH, _TELEMETRY_LOGGER, _USE_LOGGER
    try:
        tdir = os.path.join(base_dir, "telemetry")
        os.makedirs(tdir, exist_ok=True)
        _LOG_PATH = os.path.join(tdir, "telemetry.log")
        # Try to configure a daily rotating handler (midnight) with 30 days retention
        try:
            logger = logging.getLogger("katcam.telemetry")
            logger.setLevel(logging.INFO)
            # Avoid adding multiple handlers if init called multiple times
            if not any(getattr(h, '__class__', None).__name__ == 'TimedRotatingFileHandler' for h in logger.handlers):
                from logging.handlers import TimedRotatingFileHandler
                handler = TimedRotatingFileHandler(_LOG_PATH, when="midnight", backupCount=30, encoding="utf-8")

                # compress rotated files to .gz
                def _namer(default_name):
                    return default_name + ".gz"

                def _rotator(source, dest):
                    try:
                        with open(source, 'rb') as sf, gzip.open(dest, 'wb') as df:
                            shutil.copyfileobj(sf, df)
                        try:
                            os.remove(source)
                        except Exception:
                            pass
                    except Exception:
                        # If compression fails, attempt to move original file
                        try:
                            shutil.move(source, dest)
                        except Exception:
                            pass

                handler.namer = _namer
                handler.rotator = _rotator
                handler.setFormatter(logging.Formatter('%(message)s'))
                logger.addHandler(handler)
            _TELEMETRY_LOGGER = logger
            _USE_LOGGER = True
            # emit an init event via logger (uses log_event below which will route to logger)
            log_event("telemetry_init", base_dir=base_dir)
            return
        except Exception:
            # Fall through to attempt fallback locations
            pass
    except Exception:
        # If ProgramData path isn't writable or creation failed, try user-local AppData
        try:
            local = os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
            tdir = os.path.join(local, "Katcam", "logs", "telemetry")
            os.makedirs(tdir, exist_ok=True)
            _LOG_PATH = os.path.join(tdir, "telemetry.log")
            # Try to set up logger on fallback location as well
            try:
                from logging.handlers import TimedRotatingFileHandler
                handler = TimedRotatingFileHandler(_LOG_PATH, when="midnight", backupCount=30, encoding="utf-8")

                def _namer(default_name):
                    return default_name + ".gz"

                def _rotator(source, dest):
                    try:
                        with open(source, 'rb') as sf, gzip.open(dest, 'wb') as df:
                            shutil.copyfileobj(sf, df)
                        try:
                            os.remove(source)
                        except Exception:
                            pass
                    except Exception:
                        try:
                            shutil.move(source, dest)
                        except Exception:
                            pass

                handler.namer = _namer
                handler.rotator = _rotator
                handler.setFormatter(logging.Formatter('%(message)s'))
                logger.addHandler(handler)
                _TELEMETRY_LOGGER = logger
                _USE_LOGGER = True
                log_event("telemetry_init", base_dir=tdir)
                return
            except Exception:
                pass
        except Exception as e:
            # As a last resort, disable on-disk telemetry and log to katcam.log via logging
            _LOG_PATH = None
            try:
                logging.getLogger().warning("Telemetry initialization failed: %s", e)
            except Exception:
                pass
            return

def _write_line(obj: Dict[str, Any]):
    # If we configured a logger, use it (logger expects a single message string)
    try:
        if _USE_LOGGER and _TELEMETRY_LOGGER is not None:
            try:
                # write pre-serialized JSON string as the log message
                _TELEMETRY_LOGGER.info(json.dumps(obj, ensure_ascii=False))
                return
            except Exception:
                # fallback to direct file write below
                pass
    except Exception:
        pass

    if _LOG_PATH is None:
        return
    try:
        # Ensure directory still exists (could be removed by external tool)
        d = os.path.dirname(_LOG_PATH)
        if d and not os.path.exists(d):
            try:
                os.makedirs(d, exist_ok=True)
            except Exception:
                pass
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    except Exception:
        try:
            logging.getLogger().exception("Failed to write telemetry to %s", _LOG_PATH)
        except Exception:
            pass

def log_event(event_type: str, **fields: Any):
    rec = {
        "ts": _dt.datetime.utcnow().isoformat() + "Z",
        "type": event_type,
        **fields
    }
    with _LOCK:
        _BUFFER.append(rec)
        if len(_BUFFER) > _MAX_IN_MEMORY:
            _BUFFER.pop(0)
    _write_line(rec)

def log_error(exc: BaseException, context: Optional[Dict[str, Any]] = None):
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    log_event("error", message=str(exc), traceback=tb, **(context or {}))

def dump_state(state_obj: Any):
    try:
        data = {
            "streaming": getattr(state_obj, "streaming", None),
            "timelapse_running": getattr(state_obj, "timelapse_running", None),
            "maniobra_running": getattr(state_obj, "maniobra_running", None),
            "cam_index": getattr(state_obj, "cam_index", None),
        }
        log_event("state_snapshot", **data)
    except Exception as e:
        log_error(e, {"phase": "dump_state"})

def get_recent(max_items=100):
    with _LOCK:
        return list(_BUFFER[-max_items:])


def write_folder_log(target_folder: str, obj: Dict[str, Any]):
    """Escribe un evento JSONL en target_folder/logs/YYYY-MM-DD.log.

    Este helper permite guardar entradas vinculadas a una carpeta de fotos
    (por ejemplo para registrar 'capture_black' al lado de las imágenes).
    """
    try:
        if not target_folder:
            return
        logs_dir = os.path.join(target_folder, "logs")
        try:
            os.makedirs(logs_dir, exist_ok=True)
        except Exception:
            # No podemos crear la carpeta; abortar silenciosamente
            return
        date_name = _dt.datetime.utcnow().strftime("%Y-%m-%d")
        path = os.path.join(logs_dir, f"{date_name}.log")
        # Añadir timestamp si no existe
        if isinstance(obj, dict) and "ts" not in obj:
            obj = {**obj, "ts": _dt.datetime.utcnow().isoformat() + "Z"}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    except Exception:
        try:
            logging.getLogger().exception("Failed to write folder log to %s", target_folder)
        except Exception:
            pass


def write_failure_log(obj: Dict[str, Any]):
    """Registra fallos detectados en un archivo global `failures.log`.

    El archivo se crea en el mismo directorio donde esté `_LOG_PATH` (p.ej. ProgramData/telemetry)
    o, si no está disponible, en `%LOCALAPPDATA%/Katcam/logs/failures.log`.
    Cada línea es un JSON con al menos `ts` y los campos provistos en `obj`.
    """
    try:
        # Determinar carpeta base para guardar el archivo de fallas
        base_dir = None
        if _LOG_PATH:
            base_dir = os.path.dirname(_LOG_PATH) or _LOG_PATH
        if not base_dir:
            local = os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
            base_dir = os.path.join(local, "Katcam", "logs")
        try:
            os.makedirs(base_dir, exist_ok=True)
        except Exception:
            # No podemos crear carpeta; abandonar silenciosamente
            return
        path = os.path.join(base_dir, "failures.log")
        if isinstance(obj, dict) and "ts" not in obj:
            obj = {**obj, "ts": _dt.datetime.utcnow().isoformat() + "Z"}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    except Exception:
        try:
            logging.getLogger().exception("Failed to write failure log to %s", locals().get('path', '<unknown>'))
        except Exception:
            pass

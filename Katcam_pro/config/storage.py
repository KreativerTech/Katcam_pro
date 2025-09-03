# -*- coding: utf-8 -*-
import json
import os
from typing import Any, Dict
from .settings import CONFIG_FILE, APPDATA_DIR

class ConfigStore:
    """
    Carga y guarda configuración en katcam_config.json (AppData\KatcamPro).
    Escribe en disco cada vez que llamas a set(...).
    """
    def __init__(self):
        self.path = CONFIG_FILE
        self.data: Dict[str, Any] = {}

    def _ensure_dir(self):
        try:
            os.makedirs(APPDATA_DIR, exist_ok=True)
        except Exception:
            pass

    def load(self):
        self._ensure_dir()
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {}
        else:
            self.data = {}

    def set(self, **kwargs):
        self.data.update(kwargs)
        try:
            self._ensure_dir()
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            # En caso de error, no reventamos la app
            pass

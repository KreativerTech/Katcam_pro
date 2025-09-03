
# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from typing import Callable

class ManiobraController:
    def __init__(self, root_after, on_tick_capture: Callable[[], None], on_label: Callable[[str], None]):
        self._after = root_after
        self._capture = on_tick_capture
        self._label = on_label
        self.running = False
        self._end_time = None
        self._job_id = None

    def start(self, duracion_min: float, intervalo_s: float, on_done: Callable[[], None]):
        self.running = True
        self._end_time = datetime.now() + timedelta(seconds=duracion_min * 60)
        self._label("Maniobra en curso...")

        def _loop():
            if not self.running:
                return
            if datetime.now() >= self._end_time:
                self.stop()
                on_done()
                self._label("Maniobra finalizada.")
                return
            # disparo
            try:
                self._capture()
            except Exception as e:
                self._label(f"Error maniobra: {e}")
            self._job_id = self._after(delay=int(intervalo_s*1000), callback=_loop)

        _loop()

    def stop(self):
        self.running = False
        if self._job_id is not None:
            try:
                self._after(cancel=self._job_id)
            except Exception:
                pass
            self._job_id = None

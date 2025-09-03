
# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from typing import Callable, List, Optional

class TimelapseController:
    def __init__(self, root_after, label_update: Callable[[str], None]):
        self._after = root_after
        self._label = label_update
        self.running = False
        self.interval_ms = 600000
        self.days_selected: List[str] = []
        self.hour_start: Optional[str] = "08:00"
        self.hour_end: Optional[str] = "18:00"
        self.next_capture_time: Optional[datetime] = None
        self._job_id = None
        self._paused_reason = None  # e.g. "maniobra"

    def configure(self, frecuencia_s: float, dias_sel: List[str], hstart: Optional[str], hend: Optional[str]):
        self.interval_ms = int(float(frecuencia_s) * 1000)
        self.days_selected = dias_sel[:]
        self.hour_start = hstart if hstart else None
        self.hour_end = hend if hend else None

    def start(self):
        if self._job_id is not None:
            try:
                self._after(cancel=self._job_id)  # only if wrapper supports cancel
            except Exception:
                pass
            self._job_id = None
        self.running = True
        self.next_capture_time = datetime.now()
        self._label("Esperando próxima foto...")
        self._schedule()

    def stop(self):
        self.running = False
        if self._job_id is not None:
            try:
                self._after(cancel=self._job_id)
            except Exception:
                pass
            self._job_id = None
        self._label("Timelapse detenido.")

    def pause(self, reason="manual"):
        if not self.running:
            return
        self._paused_reason = reason
        if self._job_id is not None:
            try:
                self._after(cancel=self._job_id)
            except Exception:
                pass
            self._job_id = None
        self._label("Timelapse pausado.")

    def resume(self):
        if not self._paused_reason:
            return
        self._paused_reason = None
        self._label("Timelapse: reanudado")
        self._schedule()

    def _schedule(self):
        if not self.running or self._paused_reason:
            return
        def _tick():
            self._job_id = None
            self._run_once()
            self._schedule()
        self._job_id = self._after(delay=self.interval_ms, callback=_tick)

    def _run_once(self):
        if not self.running or self._paused_reason:
            return
        now = datetime.now()
        # filtro días
        dia_actual = now.strftime("%A").lower()
        dias_es = {
            "monday": "lunes", "tuesday": "martes", "wednesday": "miércoles",
            "thursday": "jueves", "friday": "viernes", "saturday": "sábado", "sunday": "domingo"
        }
        dia_actual_es = dias_es.get(dia_actual, dia_actual)
        if self.days_selected and dia_actual_es not in self.days_selected:
            self._label("Esperando día válido para timelapse...")
            return
        # filtro horario
        if self.hour_start and self.hour_end:
            hora_actual = now.strftime("%H:%M")
            if not (self.hour_start <= hora_actual <= self.hour_end):
                self._label("Fuera de horario. Esperando para timelapse...")
                return
        # disparo
        self._label("Capturando foto para timelapse...")
        if self.on_capture is not None:
            try:
                self.on_capture()
                self._label("Foto tomada. Esperando próxima captura...")
            except Exception as e:
                self._label(f"Error timelapse: {e}")

    # callback para que el host ejecute la captura real
    on_capture: Callable[[], None] = None

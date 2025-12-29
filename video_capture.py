# video_capture.py
import cv2
import sys
import os
from contextlib import contextmanager
import threading
import time
import queue
import os
from datetime import datetime

# Telemetría segura (fallback a no-op si falla)
try:
    from infra.telemetry import log_event as _tele_log_event, log_error as _tele_log_error, write_folder_log as _tele_write_folder_log, write_failure_log as _tele_write_failure
except Exception:  # pragma: no cover
    def _tele_log_event(*a, **k):
        pass
    def _tele_log_error(*a, **k):
        pass
    def _tele_write_folder_log(*a, **k):
        pass
    def _tele_write_failure(*a, **k):
        pass

# Resoluciones objetivo para captura (ajusta a tu sensor/driver)
_PREFERRED_SIZES = [
    (4056, 3040),   # ~12MP
    (3840, 2160),   # 4K
    (3264, 2448),   # ~8MP
    (2592, 1944),   # ~5MP
    (1920, 1080),   # 1080p
    (1280, 720),    # 720p
]

class CameraManager:
    """
    Dueño único del dispositivo:
      - Hilo que procesa comandos (stream on/off, props y captura).
      - Preview fluido; captura alta resolución y restaura preview.
      - Pausa/reanuda internamente durante timelapse/captura.
    """
    def __init__(self, cam_index=0, backend="auto", preview_size=(1280, 720), fps=30, use_mjpg=True):
        self.cam_index = cam_index
        # Backend preferido (Windows: probar DSHOW primero, luego MSMF)
        if backend == "dshow":
            self.backend = cv2.CAP_DSHOW
        elif backend == "msmf":
            self.backend = cv2.CAP_MSMF
        else:  # auto
            # Predeterminar a DSHOW (más rápido en muchos drivers)
            self.backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else None
        self.preview_w, self.preview_h = preview_size
        self.preview_fps = fps
        self.use_mjpg = use_mjpg

        self._cap = None
        self._running = False
        self._stream_enabled = False
        self._lock = threading.RLock()

        self._frame_lock = threading.Lock()
        self._last_frame = None

        self._cmd_q = queue.Queue()
        self._prop_pending = {}   # pid -> value (coalesce)

        self._worker = threading.Thread(target=self._loop, daemon=True)
        self._running = True
        self._worker.start()

        # Métricas / contadores
        self.frames_ok = 0
        self.frames_fail = 0
        self.consecutive_fail_reads = 0
        self.last_capture_started_ts = 0.0
        self.last_capture_ended_ts = 0.0
        self.last_open_ts = 0.0
        # Última vez que se registró telemetry de drain (evitar spam)
        self._last_drain_tele_ts = 0.0
        # Supervisión de reanudación
        self._post_capture_resume_deadline = 0.0
        self._last_frame_ts = 0.0  # timestamp de último frame ok
        self._auto_reopen_in_progress = False
        # Cancel cooperativo de captura
        self._capture_cancel_requested = False

    # ---------- API pública ----------
    def set_cam_index(self, index: int):
        self._cmd_q.put(("set_cam_index", int(index)))

    def start_stream(self):
        self._cmd_q.put(("start_stream", None))

    def stop_stream(self):
        self._cmd_q.put(("stop_stream", None))

    def set_resolution(self, width: int, height: int):
        """Actualiza la resolución de preview y la aplica en el hilo worker.
        Esto permite que cambios desde la UI surtan efecto aunque el stream ya esté abierto.
        """
        try:
            w = int(width)
            h = int(height)
        except Exception:
            return
        # Actualiza variables y encola aplicación en worker
        self.preview_w, self.preview_h = w, h
        self._cmd_q.put(("set_preview_size", (w, h)))

    def take_photo(self, dest_folder: str, prefer_sizes=None, jpeg_quality=95,
                   auto_resume_stream=True, block_until_done=True, timeout=None, result_holder=None):
        """
        Captura foto; si el stream estaba activo y auto_resume_stream=True,
        reanuda automáticamente tras guardar. Ahora con timeout para evitar bloqueos.
        """
        done = threading.Event()
        try:
            _tele_log_event("capture_enqueued", qsize=self._cmd_q.qsize(), worker_alive=bool(getattr(self, '_worker', None) and getattr(self, '_worker', 'is_alive', lambda: False)()))
        except Exception:
            pass
        self._cmd_q.put(("capture", {
            "dest_folder": dest_folder,
            "prefer_sizes": prefer_sizes or _PREFERRED_SIZES,
            "jpeg_quality": int(jpeg_quality),
            "auto_resume": bool(auto_resume_stream),
            "done_evt": done,
            "result_holder": result_holder
        }))
        if block_until_done:
            # Si timeout es None -> bloquear hasta que done.set() (espera indefinida)
            try:
                ok = done.wait(timeout=timeout)
            except TypeError:
                # algunos entornos no aceptan None en wait -> usar sin timeout
                done.wait()
                ok = True
            if not ok:
                print(f"[ERROR] Captura de foto excedió el timeout de {timeout}s")
            return bool(ok)
        return True

    def cancel_capture(self):
        """Solicita cancelar una captura en curso (cooperativo)."""
        self._capture_cancel_requested = True
        _tele_log_event("capture_cancel_request")

    def set_property(self, prop_id, value):
        """Encola cambios de propiedad; el worker los aplica con debounce."""
        self._cmd_q.put(("set_prop", (prop_id, float(value))))

    def get_frame_rgb(self):
        with self._frame_lock:
            if self._last_frame is None:
                return None
            frame = self._last_frame.copy()
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    def shutdown(self):
        # Señal de apagado
        self._running = False
        try:
            self._cmd_q.put(("shutdown", None))
        except Exception:
            pass

        # Detén stream si aplica (por si hay lecturas en paralelo)
        try:
            self.stop_stream()
        except Exception:
            pass

        # Espera al worker si existe (timeout reducido)
        t = getattr(self, "_worker", None)
        if t and t.is_alive():
            t.join(timeout=0.5)
        self._worker = None

        # Libera la cámara sin carrera (setea None antes de release)
        cap = None
        with self._lock:
            cap, self._cap = self._cap, None
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass


    # ---- Extras: diálogo del controlador y modos auto ----
    def show_driver_settings(self):
        """Abre el diálogo nativo del driver (Windows/DirectShow)."""
        with self._lock:
            if self._cap is None:
                self._open_for_preview_locked()
            try:
                self._cap.set(cv2.CAP_PROP_SETTINGS, 1)
            except Exception:
                pass

    def set_auto_modes(self, enable_exposure_auto=True, enable_wb_auto=True):
        """Activa modos automáticos (si el driver lo soporta)."""
        with self._lock:
            if self._cap is None:
                self._open_for_preview_locked()
            try:
                # Convención típica con DShow (puede variar por build/driver)
                # 0.25 = manual, 0.75 = auto
                if enable_exposure_auto:
                    self._cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)
                if enable_wb_auto:
                    self._cap.set(cv2.CAP_PROP_AUTO_WB, 1)
            except Exception:
                pass

    def probe_resolutions(self, candidates):
        """Devuelve lista de resoluciones soportadas (aprox) probando set/get.
        candidates: [(label,w,h), ...]
        Considera soportada si el driver devuelve valores dentro de tolerancia definida.
        """
        supported = []
        try:
            from config import settings as _cfg
            tol = getattr(_cfg, "CAPTURE_RES_TOLERANCE_PIX", 16)
        except Exception:
            tol = 16
        with self._lock:
            if self._cap is None:
                self._open_for_preview_locked()
            if self._cap is None or not self._cap.isOpened():
                return []
            for (label, w, h) in candidates:
                try:
                    self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  w)
                    self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
                    eff_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    eff_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    if abs(eff_w - w) <= tol and abs(eff_h - h) <= tol:
                        supported.append(label)
                except Exception:
                    pass
            # Restaurar preview actual
            try:
                self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.preview_w)
                self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.preview_h)
            except Exception:
                pass
        try:
            _tele_log_event("camera_probe_resolutions", supported=supported)
        except Exception:
            pass
        return supported

    # ---------- Internos ----------
    def _loop(self):
        last_prop_apply = 0.0
        heartbeat_frames_step = 300  # cada 300 frames
        while self._running:
            self._drain_commands(max_ops=10)

            now = time.time()
            if self._prop_pending and (now - last_prop_apply) >= 0.3:
                with self._lock:
                    if self._cap is None:
                        self._open_for_preview_locked()
                    for pid, val in list(self._prop_pending.items()):
                        try:
                            self._cap.set(pid, float(val))
                        except Exception:
                            pass
                    self._prop_pending.clear()
                last_prop_apply = now

            if self._stream_enabled:
                with self._lock:
                    if self._cap is None:
                        self._open_for_preview_locked()
                    try:
                        ok, frame = self._cap.read()
                    except Exception as e:
                        print(f"[ERROR] Error leyendo frame: {e}")
                        ok, frame = False, None
                if ok:
                    with self._frame_lock:
                        self._last_frame = frame
                    self.frames_ok += 1
                    self.consecutive_fail_reads = 0
                    self._last_frame_ts = time.time()
                    if self.frames_ok % heartbeat_frames_step == 0:
                        _tele_log_event("camera_loop_heartbeat",
                                        frames_ok=self.frames_ok,
                                        frames_fail=self.frames_fail,
                                        backend=self._backend_name(),
                                        consecutive_fail=self.consecutive_fail_reads,
                                        last_capture_age_ms=self._last_capture_age_ms())
                else:
                    time.sleep(0.01)
                    self.frames_fail += 1
                    self.consecutive_fail_reads += 1
                    # Log al décimo fallo consecutivo y luego cada 50
                    if self.consecutive_fail_reads == 10 or (self.consecutive_fail_reads > 10 and self.consecutive_fail_reads % 50 == 0):
                        _tele_log_event("frame_read_error", consecutive_fail=self.consecutive_fail_reads,
                                        backend=self._backend_name())
            else:
                time.sleep(0.01)

            # Verificación de reanudación post-captura: si había deadline y ya recibimos frame => éxito
            if self._post_capture_resume_deadline > 0:
                now_chk = time.time()
                if self._last_frame_ts >= (self.last_capture_ended_ts - 0.01):
                    # Ya hay al menos un frame después de la captura
                    _tele_log_event("post_capture_resume_ok", ms_after_end=int((self._last_frame_ts - self.last_capture_ended_ts)*1000))
                    self._post_capture_resume_deadline = 0.0
                elif now_chk > self._post_capture_resume_deadline:
                    # Timeout sin frame → intentar reopen una vez
                    if not self._auto_reopen_in_progress:
                        self._auto_reopen_in_progress = True
                        _tele_log_event("post_capture_resume_timeout", timeout_ms=int((self._post_capture_resume_deadline - self.last_capture_ended_ts)*1000))
                        with self._lock:
                            try:
                                self._open_for_preview_locked()
                            except Exception as e:
                                _tele_log_error(e, {"phase": "post_capture_reopen"})
                        # Tras reopen, damos otra ventana corta
                        self._post_capture_resume_deadline = time.time() + 1.5
                    else:
                        # Segundo fallo tras reopen
                        if now_chk - self._post_capture_resume_deadline > 0.5:
                            _tele_log_event("post_capture_reopen_failed")
                            self._post_capture_resume_deadline = 0.0
                            self._auto_reopen_in_progress = False
                # Si se logró frame tras reopen, se limpia arriba

    def _drain_commands(self, max_ops=10):
        ops = 0
        try:
            qsz = self._cmd_q.qsize()
            now = time.time()
            # Emitir telemetría solo si hay comandos en la cola o como máximo
            # una vez cada 5 segundos para evitar saturar los logs cuando
            # el worker está idle.
            if qsz > 0 or (now - getattr(self, '_last_drain_tele_ts', 0.0)) >= 5.0:
                _tele_log_event("drain_commands_start", qsize=qsz)
                self._last_drain_tele_ts = now
        except Exception:
            pass
        while ops < max_ops:
            try:
                cmd, arg = self._cmd_q.get_nowait()
                try:
                    _tele_log_event("cmd_drained", cmd=cmd)
                except Exception:
                    pass
            except queue.Empty:
                break
            ops += 1
            if cmd == "set_cam_index":
                old = self.cam_index
                with self._lock:
                    self.cam_index = int(arg)
                    # reabrir preview con el nuevo índice si estaba abierto
                    try:
                        self._open_for_preview_locked()
                    except Exception:
                        pass
                _tele_log_event("camera_index_change", old_index=old, new_index=self.cam_index)
            elif cmd == "start_stream":
                _tele_log_event("stream_start_request", w=self.preview_w, h=self.preview_h, fps=self.preview_fps)
                self._stream_enabled = True
                with self._lock:
                    if self._cap is None:
                        self._open_for_preview_locked()
                    else:
                        # Asegurar que el tamaño vigente esté aplicado al iniciar
                        try:
                            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.preview_w)
                            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.preview_h)
                            self._cap.set(cv2.CAP_PROP_FPS,          self.preview_fps)
                        except Exception:
                            pass
                    # Realizar un par de lecturas de warmup para asegurar que
                    # _last_frame tenga un frame reciente y la UI no muestre
                    # una imagen congelada inmediatamente después de activar el live.
                    try:
                        warm_ok = False
                        for _ in range(2):
                            try:
                                ok, frame = self._cap.read()
                            except Exception:
                                ok, frame = False, None
                            if ok and frame is not None:
                                with self._frame_lock:
                                    self._last_frame = frame
                                warm_ok = True
                                break
                        _tele_log_event("stream_warmup_reads", warm_ok=bool(warm_ok))
                    except Exception:
                        pass
                _tele_log_event("stream_start_applied", w=self.preview_w, h=self.preview_h, fps=self.preview_fps)
            elif cmd == "stop_stream":
                self._stream_enabled = False
                _tele_log_event("stream_stop_request")
            elif cmd == "set_preview_size":
                try:
                    w, h = arg
                except Exception:
                    continue
                old_w, old_h = self.preview_w, self.preview_h
                # Aplica de inmediato si hay capturador abierto
                with self._lock:
                    if self._cap is None:
                        self._open_for_preview_locked()
                    if self._cap is not None and self._cap.isOpened():
                        try:
                            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  int(w))
                            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(h))
                            # Verificación ligera para forzar el driver
                            _ = self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                            _ = self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                        except Exception:
                            pass
                _tele_log_event("camera_resolution_change", old_w=old_w, old_h=old_h, new_w=w, new_h=h)
            elif cmd == "set_prop":
                pid, val = arg
                self._prop_pending[pid] = val
            elif cmd == "capture":
                self._handle_capture(arg)
            elif cmd == "shutdown":
                return

    def _open_for_preview_locked(self):
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
        self._cap = None

        open_started = time.time()
        _tele_log_event("camera_open_start", index=self.cam_index, preferred_backend=self._backend_name())

        # Bajar verbosidad de OpenCV durante intentos para evitar spam
        prev_level = None
        try:
            if hasattr(cv2, "utils") and hasattr(cv2.utils, "logging"):
                prev_level = cv2.utils.logging.getLogLevel()
                # Usar SILENT si existe; sino FATAL/ERROR
                lvl = getattr(cv2.utils.logging, "LOG_LEVEL_SILENT", None)
                if lvl is None:
                    lvl = getattr(cv2.utils.logging, "LOG_LEVEL_FATAL", cv2.utils.logging.LOG_LEVEL_ERROR)
                cv2.utils.logging.setLogLevel(lvl)
        except Exception:
            prev_level = None

        @contextmanager
        def _suppress_stderr():
            try:
                fd = sys.stderr.fileno()
            except Exception:
                yield
                return
            saved = os.dup(fd)
            try:
                dn = os.open(os.devnull, os.O_WRONLY)
                os.dup2(dn, fd)
                os.close(dn)
                yield
            finally:
                try:
                    os.dup2(saved, fd)
                    os.close(saved)
                except Exception:
                    pass

        def _try_open(index: int):
            # Orden de backends por plataforma
            if sys.platform.startswith("win"):
                # Preferir DSHOW; MSMF como fallback
                base = [cv2.CAP_DSHOW, cv2.CAP_MSMF, None]
            else:
                base = [None]
            # Priorizar el backend actual si es válido
            try:
                pref = self.backend
                order = []
                for be in [pref] + [b for b in base if b != pref]:
                    if be not in order:
                        order.append(be)
            except Exception:
                order = base

            attempt = 0
            for be in order:
                attempt += 1
                _tele_log_event("camera_open_backend_try", attempt=attempt, backend=self._backend_name(be))
                cap = None
                try:
                    with _suppress_stderr():
                        cap = cv2.VideoCapture(index) if be is None else cv2.VideoCapture(index, be)
                    if cap is not None and cap.isOpened():
                        # Recordar backend exitoso para futuros opens (evita intentos costosos)
                        if be is not None:
                            try:
                                self.backend = be
                            except Exception:
                                pass
                        return cap
                except Exception:
                    pass
                finally:
                    try:
                        if cap is not None and not cap.isOpened():
                            cap.release()
                    except Exception:
                        pass
            return None

        try:
            # Intentar solo el índice configurado; si falla, probar un único alterno
            cap = _try_open(self.cam_index)
            if cap is None:
                alt = 1 if self.cam_index == 0 else 0
                cap = _try_open(alt)
                if cap is not None:
                    _tele_log_event("camera_open_index_fallback", from_index=self.cam_index, to_index=alt)
                    self.cam_index = alt
            self._cap = cap
        finally:
            try:
                if prev_level is not None:
                    cv2.utils.logging.setLogLevel(prev_level)
            except Exception:
                pass

        if not (self._cap is not None and self._cap.isOpened()):
            _tele_log_event("camera_open_fail", index=self.cam_index,
                            duration_ms=int((time.time()-open_started)*1000))
            return

        self.last_open_ts = time.time()
        _tele_log_event("camera_open_ok", index=self.cam_index, backend=self._backend_name(),
                        duration_ms=int((self.last_open_ts-open_started)*1000))

        if self.use_mjpg:
            try:
                self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            except cv2.error as e:
                print(f"[WARN] No se pudo cambiar FOURCC a MJPG: {e}")
        try:
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.preview_w)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.preview_h)
            self._cap.set(cv2.CAP_PROP_FPS,          self.preview_fps)
        except Exception:
            pass
        for _ in range(1):
            try:
                self._cap.read()
            except Exception:
                break

    def _try_set_resolution_locked(self, sizes):
        for (w, h) in sizes:
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  w)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            eff_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            eff_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if abs(eff_w - w) <= 16 and abs(eff_h - h) <= 16:
                return (eff_w, eff_h)
        return (int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))

    def _handle_capture(self, args: dict):
        dest_folder   = args["dest_folder"]
        prefer_sizes  = args["prefer_sizes"]
        jpeg_quality  = int(args["jpeg_quality"])
        auto_resume   = bool(args["auto_resume"])
        done_evt      = args.get("done_evt")
        result_holder = args.get("result_holder")

        was_streaming = self._stream_enabled
        # Nota: no pausamos inmediatamente el stream aquí.
        # Intentaremos una ruta rápida (fast-path) si el stream estaba
        # activo y la resolución solicitada coincide con la del preview;
        # en ese caso guardamos directamente desde _last_frame y evitamos
        # reconfigurar el dispositivo (ahorrando varios segundos en
        # drivers lentos).
        self.last_capture_started_ts = time.time()
        first_pref = None
        try:
            first_pref = prefer_sizes[0]
        except Exception:
            pass
        _tele_log_event("capture_begin", was_streaming=was_streaming, first_pref=first_pref)
        # Debug telemetry: marcar entrada al handler y estado del cap
        try:
            _tele_log_event("capture_handle_enter", cap_is_none=(self._cap is None), cap_opened=(self._cap is not None and getattr(self._cap, 'isOpened', lambda: False)()))
        except Exception:
            pass

        # --- Fast-path: si venimos de stream y la resolución solicitada
        # coincide con preview, intentar usar el último frame ya leído.
        try:
            FASTPATH_MAX_AGE_S = 1.0
            if was_streaming and first_pref is not None:
                try:
                    if (abs(first_pref[0] - self.preview_w) <= 16 and
                        abs(first_pref[1] - self.preview_h) <= 16):
                        # tomar copia atomica del último frame
                        with self._frame_lock:
                            lf = self._last_frame.copy() if self._last_frame is not None else None
                            lf_ts = getattr(self, '_last_frame_ts', 0.0)
                        if lf is not None and (time.time() - lf_ts) <= FASTPATH_MAX_AGE_S:
                            # Guardar directamente y emitir telemetría
                            try:
                                os.makedirs(dest_folder, exist_ok=True)
                                filename = datetime.now().strftime("%Y%m%d_%H%M%S") + ".jpg"
                                path = os.path.join(dest_folder, filename)
                                cv2.imwrite(path, lf, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
                                _tele_log_event("capture_fastpath_used", used=True, path=path)
                                _tele_log_event("capture_save_ok", path=path)
                                # Detección de foto negra: calcular brillo medio en escala de grises
                                try:
                                    import numpy as _np  # numpy suele estar disponible con OpenCV
                                    gray = cv2.cvtColor(lf, cv2.COLOR_BGR2GRAY)
                                    mean_brightness = float(_np.mean(gray))
                                except Exception:
                                    try:
                                        # Fallback sin numpy
                                        gray = cv2.cvtColor(lf, cv2.COLOR_BGR2GRAY)
                                        mean_brightness = float(gray.mean())
                                    except Exception:
                                        mean_brightness = None
                                try:
                                    from config import settings as _cfg
                                    thresh = getattr(_cfg, "CAPTURE_BLACK_MEAN_THRESHOLD", 10)
                                except Exception:
                                    thresh = 10
                                try:
                                    if mean_brightness is not None and mean_brightness <= float(thresh):
                                        _tele_log_event("capture_black", path=path, mean_brightness=mean_brightness)
                                        try:
                                            _tele_write_folder_log(dest_folder, {"event": "capture_black", "path": path, "mean": mean_brightness})
                                        except Exception:
                                            pass
                                        try:
                                            _tele_write_failure({"event": "capture_black", "path": path, "mean": mean_brightness, "folder": dest_folder})
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                            except Exception as e:
                                _tele_log_error(e, {"phase": "capture_fastpath_save"})
                                _tele_log_event("capture_fastpath_used", used=False, reason=str(e))
                            # Finalizar igual que la ruta normal
                            self.last_capture_ended_ts = time.time()
                            end_meta = {
                                "duration_ms": int((self.last_capture_ended_ts - self.last_capture_started_ts)*1000),
                                "auto_resume": auto_resume,
                                "was_streaming": was_streaming,
                                "resumed_stream": False,
                                "cancelled": False,
                                "timeout": False
                            }
                            _tele_log_event("capture_end", **end_meta)
                            if done_evt:
                                try:
                                    done_evt.set()
                                except Exception:
                                    pass
                            if result_holder is not None:
                                try:
                                    result_holder["cancelled"] = False
                                    result_holder["timeout"] = False
                                    result_holder["mismatch"] = False
                                    result_holder["eff_w"] = int(self.preview_w)
                                    result_holder["eff_h"] = int(self.preview_h)
                                except Exception:
                                    pass
                            return
                except Exception:
                    # Si algo falla en fast-path, seguimos con la ruta normal
                    pass
        except Exception:
            pass

        # Si el fast-path no retornó, entonces pausamos el stream para
        # proceder con la ruta normal que aplica set/get en el dispositivo.
        try:
            if was_streaming:
                self._stream_enabled = False
        except Exception:
            pass

        from config import settings as _cfg
        try:
            CAPTURE_MAX_DURATION_S = getattr(_cfg, "CAPTURE_MAX_DURATION_S", 8.0)
            CAPTURE_CANCEL_POLL_MS = getattr(_cfg, "CAPTURE_CANCEL_POLL_MS", 50)
        except Exception:
            CAPTURE_MAX_DURATION_S = 8.0
            CAPTURE_CANCEL_POLL_MS = 50

        self._capture_cancel_requested = False
        local_start = time.time()

        def _timed_out():
            return (time.time() - local_start) > CAPTURE_MAX_DURATION_S

        try:
            with self._lock:
                if self._cap is None:
                    _tele_log_event("capture_open_preview_start")
                    try:
                        self._open_for_preview_locked()
                        _tele_log_event("capture_open_preview_ok", cap_is_none=(self._cap is None))
                    except Exception as _e:
                        _tele_log_error(_e, {"phase": "capture_open_preview"})
                        _tele_log_event("capture_open_preview_failed")

                # NOTE: avoid setting FOURCC here per-capture. Some drivers
                # block or renegotiate when changing FOURCC; it's already set
                # at open time in _open_for_preview_locked. Skipping this
                # reduces capture stalls on some hardware.
            requested = None
            try:
                from config import settings as _cfg
                CAPTURE_RES_TOLERANCE_PIX = getattr(_cfg, "CAPTURE_RES_TOLERANCE_PIX", 16)
                CAPTURE_RES_MAX_RETRIES = getattr(_cfg, "CAPTURE_RES_MAX_RETRIES", 1)
                POST_CAPTURE_RESUME_TIMEOUT_S = getattr(_cfg, "POST_CAPTURE_RESUME_TIMEOUT_S", 1.2)
            except Exception:
                CAPTURE_RES_TOLERANCE_PIX = 16
                CAPTURE_RES_MAX_RETRIES = 1
                POST_CAPTURE_RESUME_TIMEOUT_S = 1.2
            try:
                requested = prefer_sizes[0]
            except Exception:
                pass
            attempts = 0
            eff = (0, 0)
            mismatch = False
            # Si la resolución solicitada ya coincide con la del preview,
            # evitamos reconfigurar (costoso en algunos drivers).
            skip_resolution = False
            try:
                requested = requested or (None)
            except Exception:
                requested = None
            try:
                # tolerancia en pixeles
                _tele_log_event("capture_resolution_attempts_start", preferred_count=len(prefer_sizes) if prefer_sizes else 0)
                if requested and self._cap is not None:
                    try:
                        cur_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        cur_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        if (abs(cur_w - requested[0]) <= CAPTURE_RES_TOLERANCE_PIX and
                            abs(cur_h - requested[1]) <= CAPTURE_RES_TOLERANCE_PIX):
                            eff = (cur_w, cur_h)
                            skip_resolution = True
                            _tele_log_event("capture_resolution_skip", reason="matches_preview", w=cur_w, h=cur_h)
                    except Exception:
                        # no hacer nada y dejar que el flujo normal intente set/get
                        pass
            except Exception:
                # Si algo falla al emitir telemetría, procedemos normalmente
                pass

            while True:
                if skip_resolution:
                    # Emitir el estado efectivo y saltar la lógica de intentos
                    try:
                        _tele_log_event("capture_resolution_effective", attempt=0, w=eff[0], h=eff[1])
                    except Exception:
                        pass
                    break
                if self._capture_cancel_requested:
                    _tele_log_event("capture_cancelled", phase="resolution_select")
                    break
                if _timed_out():
                    _tele_log_event("capture_timeout", phase="resolution_select")
                    break
                attempts += 1
                eff = self._try_set_resolution_locked(prefer_sizes)
                try:
                    _tele_log_event("capture_resolution_effective", attempt=attempts, w=eff[0], h=eff[1])
                except Exception:
                    pass
                if requested:
                    if (abs(eff[0]-requested[0]) > CAPTURE_RES_TOLERANCE_PIX or
                        abs(eff[1]-requested[1]) > CAPTURE_RES_TOLERANCE_PIX):
                        mismatch = True
                        if attempts <= CAPTURE_RES_MAX_RETRIES:
                            _tele_log_event("capture_resolution_mismatch", requested_w=requested[0], requested_h=requested[1], eff_w=eff[0], eff_h=eff[1], retry=True)
                            # Forzar MJPG de nuevo y reintentar una vez
                            try:
                                if self.use_mjpg:
                                    self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                            except Exception:
                                pass
                            continue
                        else:
                            _tele_log_event("capture_resolution_mismatch", requested_w=requested[0], requested_h=requested[1], eff_w=eff[0], eff_h=eff[1], retry=False)
                    else:
                        mismatch = False
                break

            cancelled_or_timeout = False
            if not self._capture_cancel_requested and not _timed_out():
                for _ in range(3):
                    if self._capture_cancel_requested:
                        _tele_log_event("capture_cancelled", phase="warmup")
                        cancelled_or_timeout = True
                        break
                    if _timed_out():
                        _tele_log_event("capture_timeout", phase="warmup")
                        cancelled_or_timeout = True
                        break
                    try:
                        self._cap.read()
                    except Exception as e:
                        print(f"[ERROR] Error leyendo frame previo a captura: {e}")
                        _tele_log_event("capture_warmup_read_error")
                    time.sleep(0.05)
            else:
                cancelled_or_timeout = True

            if not cancelled_or_timeout:
                # Warmup reads are performed earlier; instrument them to detect blocking
                try:
                    _tele_log_event("capture_pre_frame_read")
                    ok, frame = self._cap.read()
                    _tele_log_event("capture_post_frame_read", ok=bool(ok))
                except Exception as e:
                    print(f"[ERROR] Error leyendo frame de captura: {e}")
                    _tele_log_error(e, {"phase": "capture_frame_read"})
                    ok, frame = False, None
            else:
                ok, frame = False, None

            if self._capture_cancel_requested:
                print("[INFO] Captura cancelada por solicitud externa.")
            elif _timed_out():
                print("[ERROR] Captura abortada por timeout.")
            elif ok:
                try:
                    os.makedirs(dest_folder, exist_ok=True)
                    filename = datetime.now().strftime("%Y%m%d_%H%M%S") + ".jpg"
                    path = os.path.join(dest_folder, filename)
                    cv2.imwrite(path, frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
                    _tele_log_event("capture_save_ok", path=path)
                    # Detección de foto negra: calcular brillo medio en escala de grises
                    try:
                        import numpy as _np
                        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                        mean_brightness = float(_np.mean(gray))
                    except Exception:
                        try:
                            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                            mean_brightness = float(gray.mean())
                        except Exception:
                            mean_brightness = None
                    try:
                        from config import settings as _cfg
                        thresh = getattr(_cfg, "CAPTURE_BLACK_MEAN_THRESHOLD", 10)
                    except Exception:
                        thresh = 10
                    try:
                        if mean_brightness is not None and mean_brightness <= float(thresh):
                            _tele_log_event("capture_black", path=path, mean_brightness=mean_brightness)
                            try:
                                _tele_write_folder_log(dest_folder, {"event": "capture_black", "path": path, "mean": mean_brightness})
                            except Exception:
                                pass
                            try:
                                _tele_write_failure({"event": "capture_black", "path": path, "mean": mean_brightness, "folder": dest_folder})
                            except Exception:
                                pass
                    except Exception:
                        pass
                except Exception as e:
                    print(f"[ERROR] Error guardando foto: {e}")
                    _tele_log_error(e, {"phase": "capture_save"})
            else:
                if not self._capture_cancel_requested and not _timed_out():
                    print("[ERROR] No se pudo capturar la foto (frame inválido)")
                    _tele_log_event("capture_frame_read_fail")
                    try:
                        _tele_write_failure({"event": "capture_frame_read_fail", "dest_folder": dest_folder, "last_capture_started_ts": self.last_capture_started_ts})
                    except Exception:
                        pass

        finally:
            # Siempre intentar reanudar stream si correspondía
            try:
                if auto_resume and was_streaming:
                    try:
                        if self._cap is None:
                            self._open_for_preview_locked()
                        if self._cap is not None and self._cap.isOpened():
                            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.preview_w)
                            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.preview_h)
                            self._cap.set(cv2.CAP_PROP_FPS,          self.preview_fps)
                            for _ in range(2):
                                self._cap.read()
                    except Exception as e:
                        print(f"[WARN] Error reanudando stream tras captura: {e}")
                        _tele_log_error(e, {"phase": "capture_resume"})
                    self._stream_enabled = True
            except Exception:
                pass
            if done_evt:
                try:
                    done_evt.set()
                except Exception:
                    pass
            # resultado opcional
            if result_holder is not None:
                try:
                    result_holder["cancelled"] = bool(self._capture_cancel_requested)
                    result_holder["timeout"] = _timed_out()
                    result_holder["mismatch"] = bool(mismatch)
                    result_holder["eff_w"] = int(eff[0])
                    result_holder["eff_h"] = int(eff[1])
                except Exception:
                    pass
            self.last_capture_ended_ts = time.time()
        # Establecer deadline de verificación de reanudación si corresponde
        if was_streaming:
            # Usar timeout configurado
            self._post_capture_resume_deadline = self.last_capture_ended_ts + POST_CAPTURE_RESUME_TIMEOUT_S
            self._auto_reopen_in_progress = False
        end_meta = {
            "duration_ms": int((self.last_capture_ended_ts - self.last_capture_started_ts)*1000),
            "auto_resume": auto_resume,
            "was_streaming": was_streaming,
            "resumed_stream": bool(auto_resume and was_streaming),
            "cancelled": self._capture_cancel_requested,
            "timeout": (self.last_capture_ended_ts - local_start) > CAPTURE_MAX_DURATION_S
        }
        _tele_log_event("capture_end", **end_meta)

    # Helpers internos
    def _backend_name(self, be=None):
        try:
            if be is None:
                be = self.backend
            if be == cv2.CAP_DSHOW:
                return "DSHOW"
            if be == cv2.CAP_MSMF:
                return "MSMF"
            if be is None:
                return "AUTO"
            return str(be)
        except Exception:
            return "UNKNOWN"

    def _last_capture_age_ms(self):
        if self.last_capture_ended_ts <= 0:
            return -1
        return int((time.time() - self.last_capture_ended_ts) * 1000)


# Singleton importable
camera_manager = CameraManager()

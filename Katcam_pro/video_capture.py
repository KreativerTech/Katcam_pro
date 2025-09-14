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
                   auto_resume_stream=True, block_until_done=True, timeout=3):
        """
        Captura foto; si el stream estaba activo y auto_resume_stream=True,
        reanuda automáticamente tras guardar. Ahora con timeout para evitar bloqueos.
        """
        done = threading.Event()
        self._cmd_q.put(("capture", {
            "dest_folder": dest_folder,
            "prefer_sizes": prefer_sizes or _PREFERRED_SIZES,
            "jpeg_quality": int(jpeg_quality),
            "auto_resume": bool(auto_resume_stream),
            "done_evt": done
        }))
        if block_until_done:
            if not done.wait(timeout=timeout):
                print(f"[ERROR] Captura de foto excedió el timeout de {timeout}s")

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

    # ---------- Internos ----------
    def _loop(self):
        last_prop_apply = 0.0
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
                else:
                    time.sleep(0.01)
            else:
                time.sleep(0.01)

    def _drain_commands(self, max_ops=10):
        ops = 0
        while ops < max_ops:
            try:
                cmd, arg = self._cmd_q.get_nowait()
            except queue.Empty:
                break
            ops += 1
            if cmd == "set_cam_index":
                with self._lock:
                    self.cam_index = int(arg)
                    self._reopen_preview_locked()
            elif cmd == "start_stream":
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
            elif cmd == "stop_stream":
                self._stream_enabled = False
            elif cmd == "set_preview_size":
                try:
                    w, h = arg
                except Exception:
                    continue
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

            for be in order:
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
                    self.cam_index = alt
            self._cap = cap
        finally:
            try:
                if prev_level is not None:
                    cv2.utils.logging.setLogLevel(prev_level)
            except Exception:
                pass

        if not (self._cap is not None and self._cap.isOpened()):
            return

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
        done_evt      = args["done_evt"]

        was_streaming = self._stream_enabled
        self._stream_enabled = False  # pausa el loop

        with self._lock:
            if self._cap is None:
                self._open_for_preview_locked()

            if self.use_mjpg and self._cap.isOpened():
                try:
                    self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                except cv2.error as e:
                    print(f"[WARN] No se pudo cambiar FOURCC a MJPG: {e}")
            self._try_set_resolution_locked(prefer_sizes)

            for _ in range(3):
                try:
                    self._cap.read()
                except Exception as e:
                    print(f"[ERROR] Error leyendo frame previo a captura: {e}")
                time.sleep(0.05)

            try:
                ok, frame = self._cap.read()
            except Exception as e:
                print(f"[ERROR] Error leyendo frame de captura: {e}")
                ok, frame = False, None

            if ok:
                try:
                    os.makedirs(dest_folder, exist_ok=True)
                    filename = datetime.now().strftime("%Y%m%d_%H%M%S") + ".jpg"
                    path = os.path.join(dest_folder, filename)
                    cv2.imwrite(path, frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
                except Exception as e:
                    print(f"[ERROR] Error guardando foto: {e}")
            else:
                print("[ERROR] No se pudo capturar la foto (frame inválido)")

            if auto_resume and was_streaming:
                try:
                    self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.preview_w)
                    self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.preview_h)
                    self._cap.set(cv2.CAP_PROP_FPS,          self.preview_fps)
                    for _ in range(2):
                        self._cap.read()
                except Exception as e:
                    print(f"[WARN] Error reanudando stream tras captura: {e}")
                self._stream_enabled = True

        if done_evt:
            done_evt.set()


# Singleton importable
camera_manager = CameraManager()

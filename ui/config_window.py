# -*- coding: utf-8 -*-
import sys
import threading
import os
from contextlib import contextmanager
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from config.settings import (
    BG_COLOR, FG_COLOR, BTN_COLOR, BTN_TEXT_COLOR,
    RESOLUTIONS, DIAS_LISTA
)
from ui.dialogs import set_icon

# OpenCV puede no estar instalado en algunos equipos
try:
    import cv2
except Exception:
    cv2 = None


def _list_cams(max_cams=8):
    """Lista índices de cámaras disponibles usando OpenCV (si está disponible)."""
    if cv2 is None:
        return []
    found = []
    # Bajar verbosidad para evitar spam de WARN en Windows
    prev_level = None
    try:
        if hasattr(cv2, "utils") and hasattr(cv2.utils, "logging"):
            prev_level = cv2.utils.logging.getLogLevel()
            cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
    except Exception:
        prev_level = None

    @contextmanager
    def _suppress_stderr():
        try:
            fd = sys.stderr.fileno()
        except Exception:
            # No se puede redirigir; seguir normal
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

    try:
        # Limitar escaneo para evitar spam en equipos sin cámaras
        scan_n = max(1, min(4, int(max_cams)))
        for i in range(scan_n):
            opened = False
            if sys.platform.startswith("win"):
                # Probar primero MSMF, luego DSHOW, y por último por defecto
                for backend in (cv2.CAP_MSMF, cv2.CAP_DSHOW, None):
                    try:
                        with _suppress_stderr():
                            cap = cv2.VideoCapture(i) if backend is None else cv2.VideoCapture(i, backend)
                        if cap is not None and cap.isOpened():
                            found.append(i)
                            opened = True
                            cap.release()
                            break
                        if cap is not None:
                            cap.release()
                    except Exception:
                        try:
                            if cap is not None:
                                cap.release()
                        except Exception:
                            pass
                if opened:
                    continue
            else:
                # Otros SO: default
                try:
                    with _suppress_stderr():
                        cap = cv2.VideoCapture(i)
                    if cap is not None and cap.isOpened():
                        found.append(i)
                    if cap is not None:
                        cap.release()
                except Exception:
                    try:
                        if cap is not None:
                            cap.release()
                    except Exception:
                        pass
    finally:
        # Restaurar nivel de log
        try:
            if prev_level is not None:
                cv2.utils.logging.setLogLevel(prev_level)
        except Exception:
            pass
    return found


class ConfigWindow:
    """
    Ventana de configuración:
        - Pestañas: Cámara, Timelapse, Maniobra, GPS
        - Cámara: selector de cámara, resolución foto, resolución video,
                  auto-WB/expo y ajustes de driver.
        - Timelapse: frecuencia (MINUTOS), rango horario, días.
        - Maniobra: duración (min) e intervalo (seg).
        - GPS: lat/lon.
    """
    def __init__(self, root, state, on_save, on_auto_wb, on_open_driver, on_resolution_change):
        try:
            self.root = root
            self.state = state
            self.on_save = on_save
            self.on_auto_wb = on_auto_wb
            self.on_open_driver = on_open_driver
            self.on_resolution_change = on_resolution_change  # firma: on_resolution_change(new_label:str)

            self.win = tk.Toplevel(root)
            set_icon(self.win)
            self.win.title("Configuración")
            self.win.configure(bg=BG_COLOR)
            self.win.geometry("900x640")
            self.win.lift()
            self.win.attributes("-topmost", True)
            # Ventana sin bordes (pedido del usuario)
            try:
                self.win.overrideredirect(True)
            except Exception:
                pass

            # Barra de título personalizada
            titlebar = tk.Frame(self.win, bg=BTN_COLOR, height=36)
            titlebar.pack(fill="x")
            tk.Label(titlebar, text="Configuración", bg=BTN_COLOR, fg=BTN_TEXT_COLOR,
                     font=("Arial", 13, "bold")).pack(side="left", padx=10)

            def _close_config():
                if self.win.winfo_exists():
                    self.win.withdraw()

            tk.Button(titlebar, text="✕", command=_close_config,
                      bg=BTN_COLOR, fg=BTN_TEXT_COLOR, bd=0,
                      font=("Arial", 13, "bold"), padx=8, pady=2, relief="flat", cursor="hand2"
            ).pack(side="right", padx=8)

            # Permitir cerrar con Esc
            self.win.bind('<Escape>', lambda e: _close_config())

            # Permitir mover la ventana arrastrando la barra de título
            _drag = {"x": 0, "y": 0}
            def _start_drag(e): _drag.update(x=e.x, y=e.y)
            def _do_drag(e):
                try:
                    self.win.geometry(f"+{self.win.winfo_x() + e.x - _drag['x']}+{self.win.winfo_y() + e.y - _drag['y']}")
                except Exception:
                    pass
            for widget in [titlebar] + list(titlebar.winfo_children()):
                widget.bind("<Button-1>", _start_drag)
                widget.bind("<B1-Motion>", _do_drag)

            tk.Label(self.win, text="Configuraciones", font=("Arial", 16, "bold"),
                     bg=BG_COLOR, fg=BTN_COLOR).pack(anchor="w", padx=10, pady=(10, 0))

            self.notebook = ttk.Notebook(self.win)
            self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

            # ---- Pestañas ----
            self.tab_cam = tk.Frame(self.notebook, bg=BG_COLOR)
            self.notebook.add(self.tab_cam, text="Cámara")
            self._build_tab_camera()

            self.tab_tl = tk.Frame(self.notebook, bg=BG_COLOR)
            self.notebook.add(self.tab_tl, text="Timelapse")
            self._build_tab_timelapse()

            self.tab_mani = tk.Frame(self.notebook, bg=BG_COLOR)
            self.notebook.add(self.tab_mani, text="Maniobra")
            self._build_tab_maniobra()

            #self.tab_gps = tk.Frame(self.notebook, bg=BG_COLOR)
            #self.notebook.add(self.tab_gps, text="GPS")
            #self._build_tab_gps()

            # Botón Guardar
            btn_save = tk.Button(
                self.win, text="Guardar", command=self.on_save,
                bg=BTN_COLOR, fg=BTN_TEXT_COLOR, bd=0,
                font=("Arial", 12, "bold"), padx=12, pady=8
            )
            btn_save.pack(pady=(0, 10))

            self._load_from_state()
            # Centrar y mostrar (sin usar withdraw/deiconify para evitar que se "pierda")
            try:
                self.win.update_idletasks()
                sw = self.win.winfo_screenwidth()
                sh = self.win.winfo_screenheight()
                w = 900
                h = 640
                x = max(0, int((sw - w) / 2))
                y = max(0, int((sh - h) / 3))
                self.win.geometry(f"{w}x{h}+{x}+{y}")
                self.win.lift()
                self.win.focus_force()
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror("Error de configuración", f"No se pudo abrir la ventana de configuración:\n{e}")

    # ---------- Cámara ----------
    def _build_tab_camera(self):
        row = 0
        tk.Label(self.tab_cam, text="Ajustes de Cámara", font=("Arial", 16, "bold"),
                 bg=BG_COLOR, fg=FG_COLOR).grid(row=row, column=0, columnspan=3, sticky="w", pady=(10, 8)); row+=1

        # Selector de cámara
        tk.Label(self.tab_cam, text="Cámara:", bg=BG_COLOR, fg=FG_COLOR
                ).grid(row=row, column=0, sticky="e", padx=8, pady=6)
        self.cam_var = tk.StringVar(value=str(self.state.cfg.data.get("cam_index", 0)))
        self.cam_combo = ttk.Combobox(self.tab_cam, textvariable=self.cam_var, state="readonly", width=20)
        self.cam_combo.grid(row=row, column=1, sticky="w", padx=6, pady=6)
        self.detect_btn = tk.Button(self.tab_cam, text="Detectar", command=self._detect_cams_async,
                                    bg=BTN_COLOR, fg=BTN_TEXT_COLOR, bd=0)
        self.detect_btn.grid(row=row, column=2, sticky="w", padx=6, pady=6)
        row+=1

        # --- Resoluciones soportadas (modo rápido: marcar luego asíncrono) ---
        res_labels_all = [t for (t, _, _) in RESOLUTIONS]
        initial_supported = getattr(self.state, "supported_resolution_labels", None)
        if initial_supported:
            self._supported_set = set(initial_supported)
        else:
            # desconocido aún: tratamos todas como soportadas hasta terminar probe
            self._supported_set = set(res_labels_all)
        display_values = list(res_labels_all)  # sin sufijos todavía

        def _first_supported(fallback):
            for l in res_labels_all:
                if l in self._supported_set:
                    return l
            return fallback

        # Resolución FOTO
        tk.Label(self.tab_cam, text="Resolución (Foto):", bg=BG_COLOR, fg=FG_COLOR
                ).grid(row=row, column=0, sticky="e", padx=8, pady=6)
        default_photo = self.state.cfg.data.get(
            "photo_resolution_label",
            self.state.cfg.data.get("capture_resolution_label", self.state.photo_resolution_label or res_labels_all[0])
        )
        if default_photo not in self._supported_set:
            default_photo = _first_supported(default_photo)
        self.photo_res_var = tk.StringVar(value=default_photo)
        self.photo_res_combo = ttk.Combobox(
            self.tab_cam, textvariable=self.photo_res_var, values=display_values,
            state="readonly", width=30
        )
        self.photo_res_combo.grid(row=row, column=1, sticky="w", padx=6, pady=6)
        row+=1

        # Resolución VIDEO/Stream
        tk.Label(self.tab_cam, text="Resolución (Video/Stream):", bg=BG_COLOR, fg=FG_COLOR
                ).grid(row=row, column=0, sticky="e", padx=8, pady=6)
        default_video = self.state.cfg.data.get(
            "video_resolution_label",
            self.state.cfg.data.get("capture_resolution_label", self.state.video_resolution_label or res_labels_all[0])
        )
        if default_video not in self._supported_set:
            default_video = _first_supported(default_video)
        self.video_res_var = tk.StringVar(value=default_video)
        self.video_res_combo = ttk.Combobox(
            self.tab_cam, textvariable=self.video_res_var, values=display_values,
            state="readonly", width=30
        )
        self.video_res_combo.grid(row=row, column=1, sticky="w", padx=6, pady=6)

        def _normalize(sel: str):
            return sel.replace(" (no soportada)", "") if sel.endswith("(no soportada)") else sel

        def _is_unsupported(label: str) -> bool:
            return label not in self._supported_set

        def _apply_video(_evt=None):
            raw = self.video_res_var.get()
            lbl = _normalize(raw)
            if _is_unsupported(lbl):
                messagebox.showwarning("No soportada", "La cámara no soporta esa resolución.")
                self.video_res_var.set(self.state.video_resolution_label)
                return
            self.state.video_resolution_label = lbl
            try:
                self.state.cfg.set(video_resolution_label=lbl)
            except Exception:
                pass
            try:
                if callable(self.on_resolution_change):
                    self.on_resolution_change(lbl)
            except Exception:
                pass

        def _apply_photo(_evt=None):
            raw = self.photo_res_var.get()
            lbl = _normalize(raw)
            if _is_unsupported(lbl):
                messagebox.showwarning("No soportada", "La cámara no soporta esa resolución.")
                self.photo_res_var.set(self.state.photo_resolution_label)
                return
            self.state.photo_resolution_label = lbl
            try:
                self.state.cfg.set(photo_resolution_label=lbl)
            except Exception:
                pass

        self.video_res_combo.bind("<<ComboboxSelected>>", _apply_video)
        self.photo_res_combo.bind("<<ComboboxSelected>>", _apply_photo)

        # Lanzar sondeo en background si no se conoce aún
        if not initial_supported:
            def _async_probe():
                try:
                    from video_capture import camera_manager as _cm
                    sup = _cm.probe_resolutions(RESOLUTIONS)
                except Exception:
                    sup = res_labels_all
                self.state.supported_resolution_labels = sup
                def _apply_supported():
                    self._supported_set = set(sup or res_labels_all)
                    new_values = []
                    for lbl in res_labels_all:
                        if lbl in self._supported_set:
                            new_values.append(lbl)
                        else:
                            new_values.append(f"{lbl} (no soportada)")
                    try:
                        self.photo_res_combo["values"] = new_values
                        self.video_res_combo["values"] = new_values
                        # Ajustar selección si quedó en una no soportada
                        if self.photo_res_var.get().endswith("(no soportada)"):
                            self.photo_res_var.set(next((l for l in res_labels_all if l in self._supported_set), self.photo_res_var.get()))
                        if self.video_res_var.get().endswith("(no soportada)"):
                            self.video_res_var.set(next((l for l in res_labels_all if l in self._supported_set), self.video_res_var.get()))
                    except Exception:
                        pass
                try:
                    self.win.after(0, _apply_supported)
                except Exception:
                    pass
            try:
                threading.Thread(target=_async_probe, daemon=True).start()
            except Exception:
                pass

        row+=1
        # Autoajuste y ajustes avanzados
        tk.Button(self.tab_cam, text="Autoajuste (expo/WB)", command=self.on_auto_wb,
                  bg=BTN_COLOR, fg=BTN_TEXT_COLOR, bd=0,
                  font=("Arial", 11, "bold"), padx=10, pady=6
                 ).grid(row=row, column=0, sticky="w", padx=8, pady=8)
        tk.Button(self.tab_cam, text="Ajustes avanzados del controlador…", command=self.on_open_driver,
                  bg="#FFB300", fg="#181818", bd=0,
                  font=("Arial", 11, "bold"), padx=10, pady=6
                 ).grid(row=row, column=1, sticky="w", padx=8, pady=8)
        row+=1

    def _refresh_cams(self):
        # compat: llamada síncrona (evitar si es posible)
        cams = _list_cams(max_cams=2)
        self._apply_cams_list(cams)

    def _detect_cams_async(self):
        if getattr(self, "_detecting", False):
            return
        self._detecting = True
        try:
            # deshabilitar controles mientras detecta
            try:
                self.cam_combo.configure(state="disabled")
            except Exception:
                pass
            try:
                self.detect_btn.configure(state="disabled", text="Detectando…")
            except Exception:
                pass

            def worker():
                cams = []
                try:
                    # Evitar tocar el dispositivo si hay stream activo
                    try:
                        from video_capture import camera_manager
                        streaming = getattr(camera_manager, "_stream_enabled", False)
                    except Exception:
                        streaming = False
                    if streaming:
                        cams = [int(self.cam_var.get()) if self.cam_var.get().isdigit() else 0]
                    else:
                        cams = _list_cams(max_cams=2)
                except Exception:
                    cams = []
                finally:
                    self.win.after(0, lambda: self._apply_cams_list(cams))

            threading.Thread(target=worker, daemon=True).start()
        except Exception:
            self._detecting = False

    def _apply_cams_list(self, cams):
        try:
            if not cams:
                self.cam_combo["values"] = []
                cur = self.cam_var.get()
                if not cur:
                    self.cam_var.set("0")
                messagebox.showerror("Cámaras", "No se detectaron cámaras (o falta OpenCV).")
            else:
                values = [str(i) for i in cams]
                self.cam_combo["values"] = values
                cur = self.cam_var.get()
                if cur not in values:
                    self.cam_var.set(values[0])
        finally:
            try:
                self.detect_btn.configure(state="normal", text="Detectar")
            except Exception:
                pass
            self._detecting = False

    # ---------- Timelapse ----------
    def _build_tab_timelapse(self):
        row = 0
        tk.Label(self.tab_tl, text="Timelapse", font=("Arial", 16, "bold"),
                 bg=BG_COLOR, fg=FG_COLOR).grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 8)); row+=1

        # Frecuencia minutos
        tk.Label(self.tab_tl, text="Frecuencia (MINUTOS):", bg=BG_COLOR, fg=FG_COLOR
                ).grid(row=row, column=0, sticky="e", padx=8, pady=6)
        freq_default = str(self.state.cfg.data.get("frecuencia_min", self.state.cfg.data.get("frecuencia", "10")))
        self.freq_var = tk.StringVar(value=freq_default)
        tk.Entry(self.tab_tl, textvariable=self.freq_var, width=10
                ).grid(row=row, column=1, sticky="w", padx=6, pady=6)
        row+=1

        # Hora inicio
        tk.Label(self.tab_tl, text="Hora inicio (HH:MM):", bg=BG_COLOR, fg=FG_COLOR
                ).grid(row=row, column=0, sticky="e", padx=8, pady=6)
        self.hstart_var = tk.StringVar(value=self.state.cfg.data.get("hora_inicio","08:00"))
        tk.Entry(self.tab_tl, textvariable=self.hstart_var, width=10
                ).grid(row=row, column=1, sticky="w", padx=6, pady=6)
        row+=1

        # Hora fin
        tk.Label(self.tab_tl, text="Hora fin (HH:MM):", bg=BG_COLOR, fg=FG_COLOR
                ).grid(row=row, column=0, sticky="e", padx=8, pady=6)
        self.hend_var = tk.StringVar(value=self.state.cfg.data.get("hora_fin","18:00"))
        tk.Entry(self.tab_tl, textvariable=self.hend_var, width=10
                ).grid(row=row, column=1, sticky="w", padx=6, pady=6)
        row+=1

        # Días
        tk.Label(self.tab_tl, text="Días activos:", bg=BG_COLOR, fg=FG_COLOR
                ).grid(row=row, column=0, sticky="e", padx=8, pady=6)
        days_frame = tk.Frame(self.tab_tl, bg=BG_COLOR)
        days_frame.grid(row=row, column=1, sticky="w", padx=6, pady=6)
        row+=1
        self.day_vars = []
        stored_days = self.state.cfg.data.get("dias_activos")
        for i, dia in enumerate(DIAS_LISTA):
            var = tk.BooleanVar()
            if isinstance(stored_days, (list, tuple)) and len(stored_days) == len(DIAS_LISTA):
                var.set(bool(stored_days[i]))
            else:
                var.set(True)
            self.day_vars.append(var)
            tk.Checkbutton(days_frame, text=dia, variable=var, bg=BG_COLOR, fg=FG_COLOR, selectcolor=BG_COLOR
                          ).grid(row=i//4, column=i%4, padx=4, pady=2, sticky="w")

    # ---------- Maniobra ----------
    def _build_tab_maniobra(self):
        row = 0
        tk.Label(self.tab_mani, text="Maniobra", font=("Arial", 16, "bold"),
                 bg=BG_COLOR, fg=FG_COLOR).grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 8)); row+=1

        tk.Label(self.tab_mani, text="Duración (MINUTOS):", bg=BG_COLOR, fg=FG_COLOR
                ).grid(row=row, column=0, sticky="e", padx=8, pady=6)
        self.mani_dur_var = tk.StringVar(value=str(self.state.cfg.data.get("maniobra_duracion", "10")))
        tk.Entry(self.tab_mani, textvariable=self.mani_dur_var, width=10
                ).grid(row=row, column=1, sticky="w", padx=6, pady=6)
        row+=1

        tk.Label(self.tab_mani, text="Intervalo (SEGUNDOS):", bg=BG_COLOR, fg=FG_COLOR
                ).grid(row=row, column=0, sticky="e", padx=8, pady=6)
        self.mani_int_var = tk.StringVar(value=str(self.state.cfg.data.get("maniobra_intervalo", "1")))
        tk.Entry(self.tab_mani, textvariable=self.mani_int_var, width=10
                ).grid(row=row, column=1, sticky="w", padx=6, pady=6)
        row+=1

        tk.Label(self.tab_mani, text="Nota:", bg=BG_COLOR, fg=FG_COLOR
                ).grid(row=row, column=0, sticky="ne", padx=8, pady=6)
        tk.Label(self.tab_mani,
                 text="La maniobra toma una foto cada N segundos durante el tiempo indicado.",
                 bg=BG_COLOR, fg=FG_COLOR, wraplength=520, justify="left"
                ).grid(row=row, column=1, sticky="w", padx=6, pady=6)
        row+=1

    
    # ---------- Carga inicial ----------
    def _load_from_state(self):
        # No auto-detectamos cámaras al abrir para evitar demoras/ruido.
        # Precargamos el índice actual guardado.
        try:
            idx = str(self.state.cfg.data.get("cam_index", 0))
            self.cam_combo["values"] = [idx]
            self.cam_var.set(idx)
        except Exception:
            pass

    # ---------- Lectura para guardar ----------
    def read_all(self):
        """
        Devuelve (en este orden):
        freq_min, dias_bool_list, hora_inicio, hora_fin,
        maniobra_duracion_min, maniobra_intervalo_s,
        photo_res_label, video_res_label, cam_index
        """
        dias = [v.get() for v in self.day_vars]
        cam_index = int(self.cam_var.get()) if self.cam_var.get().isdigit() else 0
        return (
            self.freq_var.get(),
            dias,
            self.hstart_var.get(),
            self.hend_var.get(),
            self.mani_dur_var.get(),
            self.mani_int_var.get(),
            self.photo_res_var.get(),
            self.video_res_var.get(),
            cam_index,
        )


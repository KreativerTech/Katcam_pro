# -*- coding: utf-8 -*-
import sys
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
    for i in range(max_cams):
        # En Windows conviene CAP_DSHOW; en otros SO usar constructor por defecto
        if sys.platform.startswith("win"):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        else:
            cap = cv2.VideoCapture(i)
        if cap is not None and cap.isOpened():
            found.append(i)
        if cap is not None:
            cap.release()
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
            self.win.overrideredirect(True)

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
        tk.Button(self.tab_cam, text="Detectar", command=self._refresh_cams,
                  bg=BTN_COLOR, fg=BTN_TEXT_COLOR, bd=0
                 ).grid(row=row, column=2, sticky="w", padx=6, pady=6)
        row+=1

        # Resolución FOTO
        tk.Label(self.tab_cam, text="Resolución (Foto):", bg=BG_COLOR, fg=FG_COLOR
                ).grid(row=row, column=0, sticky="e", padx=8, pady=6)
        res_labels = [t for (t, _, _) in RESOLUTIONS]
        self.photo_res_var = tk.StringVar(
            value=self.state.cfg.data.get(
                "photo_resolution_label",
                self.state.cfg.data.get("capture_resolution_label", self.state.photo_resolution_label or res_labels[2])
            )
        )
        self.photo_res_combo = ttk.Combobox(
            self.tab_cam, textvariable=self.photo_res_var, values=res_labels,
            state="readonly", width=28
        )
        self.photo_res_combo.grid(row=row, column=1, sticky="w", padx=6, pady=6)
        row+=1

        # Resolución VIDEO/Stream
        tk.Label(self.tab_cam, text="Resolución (Video/Stream):", bg=BG_COLOR, fg=FG_COLOR
                ).grid(row=row, column=0, sticky="e", padx=8, pady=6)
        self.video_res_var = tk.StringVar(
            value=self.state.cfg.data.get(
                "video_resolution_label",
                self.state.cfg.data.get("capture_resolution_label", self.state.video_resolution_label or res_labels[2])
            )
        )
        self.video_res_combo = ttk.Combobox(
            self.tab_cam, textvariable=self.video_res_var, values=res_labels,
            state="readonly", width=28
        )
        self.video_res_combo.grid(row=row, column=1, sticky="w", padx=6, pady=6)

        # Cuando cambias la resolución de VIDEO, intentamos aplicar al vuelo
        # usando el callback on_resolution_change(new_label) esperado por main_window.
        def _on_video_res_change(_evt=None):
            try:
                if callable(self.on_resolution_change):
                    self.on_resolution_change(self.video_res_var.get())
            except TypeError:
                # Por compatibilidad si la firma cambiara en el futuro.
                pass
        self.video_res_combo.bind("<<ComboboxSelected>>", _on_video_res_change)
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
        cams = _list_cams()
        if not cams:
            messagebox.showerror("Cámaras", "No se detectaron cámaras (o falta OpenCV).")
            self.cam_combo["values"] = []
            return
        self.cam_combo["values"] = [str(i) for i in cams]
        # si el actual no está, selecciona el primero
        cur = self.cam_var.get()
        if cur not in self.cam_combo["values"]:
            self.cam_var.set(str(cams[0]))

    # ---------- Timelapse ----------
    def _build_tab_timelapse(self):
        row = 0
        tk.Label(self.tab_tl, text="Timelapse", font=("Arial", 16, "bold"),
                 bg=BG_COLOR, fg=FG_COLOR).grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 8)); row+=1

        tk.Label(self.tab_tl, text="Frecuencia (MINUTOS):", bg=BG_COLOR, fg=FG_COLOR
                ).grid(row=row, column=0, sticky="e", padx=8, pady=6)
        self.freq_var = tk.StringVar(
            value=str(self.state.cfg.data.get("frecuencia_min",
                self.state.cfg.data.get("frecuencia", "10")))
        )
        tk.Entry(self.tab_tl, textvariable=self.freq_var, width=10
                ).grid(row=row, column=1, sticky="w", padx=6, pady=6)
        row+=1

        tk.Label(self.tab_tl, text="Hora inicio (HH:MM):", bg=BG_COLOR, fg=FG_COLOR
                ).grid(row=row, column=0, sticky="e", padx=8, pady=6)
        self.hstart_var = tk.StringVar(value=self.state.cfg.data.get("hora_inicio","08:00"))
        tk.Entry(self.tab_tl, textvariable=self.hstart_var, width=10
                ).grid(row=row, column=1, sticky="w", padx=6, pady=6)
        row+=1

        tk.Label(self.tab_tl, text="Hora fin (HH:MM):", bg=BG_COLOR, fg=FG_COLOR
                ).grid(row=row, column=0, sticky="e", padx=8, pady=6)
        self.hend_var = tk.StringVar(value=self.state.cfg.data.get("hora_fin","18:00"))
        tk.Entry(self.tab_tl, textvariable=self.hend_var, width=10
                ).grid(row=row, column=1, sticky="w", padx=6, pady=6)
        row+=1

        tk.Label(self.tab_tl, text="Días activos:", bg=BG_COLOR, fg=FG_COLOR
                ).grid(row=row, column=0, sticky="e", padx=8, pady=6)
        days_frame = tk.Frame(self.tab_tl, bg=BG_COLOR)
        days_frame.grid(row=row, column=1, sticky="w", padx=6, pady=6)
        self.day_vars = []
        dias_cfg = self.state.cfg.data.get("dias", [True]*7)
        for i, name in enumerate(DIAS_LISTA):
            var = tk.BooleanVar(value=bool(dias_cfg[i] if i < len(dias_cfg) else True))
            self.day_vars.append(var)
            tk.Checkbutton(days_frame, text=name.title(), variable=var,
                           bg=BG_COLOR, fg=FG_COLOR, selectcolor=BG_COLOR,
                           activebackground=BG_COLOR, activeforeground=FG_COLOR
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
        self._refresh_cams()

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


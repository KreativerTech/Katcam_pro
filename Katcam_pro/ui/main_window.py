# -*- coding: utf-8 -*-
import os
import sys
import threading
import time
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import messagebox, filedialog as fd

from PIL import Image, ImageOps, ImageTk
try:
    import tzlocal
except Exception:
    tzlocal = None

# Config y utilidades
from config.settings import (
    MIN_APP_W, MIN_APP_H, IMG_MIN_W, IMG_MIN_H,
    BG_COLOR, FG_COLOR, BTN_COLOR, BTN_TEXT_COLOR, BTN_BORDER_COLOR,
    DEFAULT_RES_LABEL, COMPANY_LOGO_PATH, HEADER_IMAGE_PATH
)
from config.storage import ConfigStore
from ui.image_panel import ImagePanel
from ui.dialogs import set_icon, open_autostart_window, open_info_window
from ui.config_window import ConfigWindow

# Drivers reales
from video_capture import camera_manager
from camera import take_photo


# =========================
# Utilidades locales
# =========================
def outlined_button(parent, text, command, width=12, height=1):
    """Botón con contorno (amarillo + borde negro 1px) más compacto."""
    wrapper = tk.Frame(parent, bg=BTN_BORDER_COLOR, padx=1, pady=1)
    btn = tk.Button(
        wrapper, text=text, command=command,
        width=width, height=height,
        bg=BTN_COLOR, fg=BTN_TEXT_COLOR,
        activebackground=BTN_COLOR, activeforeground=BTN_TEXT_COLOR,
        bd=0, relief="flat", font=("Arial", 11, "bold"), padx=6, pady=6
    )
    btn.pack()
    return wrapper, btn


def has_write_access(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        testfile = os.path.join(path, ".katcam_write_test")
        with open(testfile, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(testfile)
        return True
    except Exception:
        return False


def _find_res(label: str):
    try:
        parts = label.split("(")[0].strip().split("x")
        w = int(parts[0].strip()); h = int(parts[1].strip())
        return (w, h)
    except Exception:
        return None


# =========================
# Header banner (imagen + textos abajo)
# =========================
class HeaderBanner(tk.Frame):
    def __init__(self, parent, camera_name_getter, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.configure(bg=BTN_COLOR)
        self._canvas = tk.Canvas(self, bg=BTN_COLOR, highlightthickness=0, borderwidth=0)
        self._canvas.pack(fill="both", expand=True)

        self._header_img_pil = None
        self._header_img_tk = None
        self._bg_img_id = None

        try:
            if os.path.exists(HEADER_IMAGE_PATH):
                self._header_img_pil = Image.open(HEADER_IMAGE_PATH).convert("RGBA")
        except Exception as e:
            print(f"[HEADER] {e}")

        self._target_h = 160
        self._id_text = None
        self._clock_text = None
        self._left_pad = 12
        self._right_pad = 12
        self._bottom_pad = 10

        self._camera_name_getter = camera_name_getter

        self.bind("<Configure>", self._on_resize)
        self._tick_clock()

    def _tick_clock(self):
        try:
            if tzlocal is not None:
                tz = tzlocal.get_localzone()
                tzname = str(tz)
                now = datetime.now(tz)
                clock_label = f"{now.strftime('%H:%M:%S')} ({tzname})"
            else:
                # Fallback sin tzlocal (no rompe en equipos sin el paquete)
                now = datetime.now()
                clock_label = now.strftime("%H:%M:%S")
        except Exception:
            clock_label = datetime.now().strftime("%H:%M:%S")

        if self._clock_text is not None:
            self._canvas.itemconfig(self._clock_text, text=clock_label)
        else:
            w = max(1, self.winfo_width()); h = self._target_h
            self._clock_text = self._canvas.create_text(
                w - self._right_pad, h - self._bottom_pad,
                text=clock_label, fill=BTN_TEXT_COLOR, font=("Arial", 14, "bold"), anchor="se"
            )
        self._position_text()
        self.after(1000, self._tick_clock)


    def _on_resize(self, _evt=None):
        self._render()

    def _render(self):
        w = self.winfo_width(); h = self._target_h
        if w <= 2:
            self.after(50, self._render); return

        self._canvas.config(width=w, height=h)

        if self._header_img_pil is not None:
            img = self._header_img_pil.copy()
            img_ratio = img.width / img.height; target_ratio = w / h
            if img_ratio > target_ratio:
                new_h = h; new_w = int(img_ratio * new_h)
                img = img.resize((new_w, new_h), Image.LANCZOS)
                left = (new_w - w) // 2
                img = img.crop((left, 0, left + w, h))
            else:
                new_w = w; new_h = int(new_w / img_ratio)
                img = img.resize((new_w, new_h), Image.LANCZOS)
                top = (new_h - h) // 2
                img = img.crop((0, top, w, top + h))

            self._header_img_tk = ImageTk.PhotoImage(img)
            if self._bg_img_id is None:
                self._bg_img_id = self._canvas.create_image(0, 0, image=self._header_img_tk, anchor="nw")
            else:
                self._canvas.itemconfig(self._bg_img_id, image=self._header_img_tk)
                self._canvas.coords(self._bg_img_id, 0, 0)
            self._canvas.tag_lower(self._bg_img_id)

        left_label = f"Nombre del equipo: {self._camera_name_getter()}"
        if self._id_text is None:
            self._id_text = self._canvas.create_text(
                self._left_pad, h - self._bottom_pad,
                text=left_label, fill=BTN_TEXT_COLOR, font=("Arial", 14, "bold"), anchor="sw"
            )
        else:
            self._canvas.itemconfig(self._id_text, text=left_label)

        if self._clock_text is None:
            self._clock_text = self._canvas.create_text(
                w - self._right_pad, h - self._bottom_pad,
                text="--:--:--", fill=BTN_TEXT_COLOR, font=("Arial", 14, "bold"), anchor="se"
            )

        self._position_text()

    def _position_text(self):
        w = max(1, self.winfo_width()); h = self._target_h
        if self._id_text is not None:
            self._canvas.coords(self._id_text, self._left_pad, h - self._bottom_pad)
        if self._clock_text is not None:
            self._canvas.coords(self._clock_text, w - self._right_pad, h - self._bottom_pad)
        if self._bg_img_id is not None:
            self._canvas.tag_lower(self._bg_img_id)


# =========================
# Estado
# =========================
class AppState:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = ConfigStore()
        self.cfg.load()

        # Estados
        self.streaming = False
        self.is_capturing = False
        self.maniobra_running = False
        self.timelapse_running = False

        # Reanudaciones automáticas
        self.resume_stream_after_action = False
        self.timelapse_paused_by_maniobra = False

        # Resoluciones (con compatibilidad retro)
        legacy = self.cfg.data.get("capture_resolution_label")
        self.video_resolution_label = self.cfg.data.get("video_resolution_label", legacy or DEFAULT_RES_LABEL)
        self.photo_resolution_label = self.cfg.data.get("photo_resolution_label", legacy or DEFAULT_RES_LABEL)
        self.current_resolution_label = self.video_resolution_label  # alias legacy

        # Cámara seleccionada
        self.cam_index = self.cfg.data.get("cam_index", 0)

        # Carpetas
        self.photo_dir = self.cfg.data.get("photo_dir") or ""
        self.drive_dir = self.cfg.data.get("drive_dir") or ""

        # UI refs
        self.image_panel: ImagePanel | None = None
        self.lbl_status_transmision = None
        self.lbl_status_timelapse = None
        self.lbl_status_maniobra = None
        self.lbl_status_general = None
        self.btn_switch_trans = None
        self.btn_switch_timelapse = None
        self.btn_maniobra = None

        # Timelapse runtime
        self.next_capture_at = None
        self.interval_ms = 600000  # default 10min
        self.days_selected = []    # ["lunes", ...]
        self.hour_start = "08:00"
        self.hour_end = "18:00"

        # stream tick
        self._tick_job = None


# =========================
# Build
# =========================
def build_main_window(root: tk.Tk):
    set_icon(root)
    root.title("Katcam Pro")
    root.configure(bg=BG_COLOR)
    root.minsize(MIN_APP_W, MIN_APP_H)

    # Centrar
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    ww, wh = max(int(sw * 0.8), MIN_APP_W), max(int(sh * 0.8), MIN_APP_H)
    x, y = (sw - ww) // 2, (sh - wh) // 2
    root.geometry(f"{ww}x{wh}+{x}+{y}")
    root.resizable(True, True)

    state = AppState(root)

    # -------- Menú --------
    menubar = tk.Menu(root, bg=BG_COLOR, fg=FG_COLOR); root.config(menu=menubar)

    archivo = tk.Menu(menubar, tearoff=0, bg=BG_COLOR, fg=FG_COLOR)
    archivo.add_command(label="Salir", command=root.quit)
    menubar.add_cascade(label="Archivo", menu=archivo)

    opciones = tk.Menu(menubar, tearoff=0, bg=BG_COLOR, fg=FG_COLOR)
    opciones.add_command(label="Cambiar carpeta de fotos...", command=lambda: _cambiar_directorio_fotos(state))
    opciones.add_command(label="Cambiar carpeta de Google Drive...", command=lambda: _seleccionar_drive_manual(state))
    menubar.add_cascade(label="Opciones", menu=opciones)

    ajustes = tk.Menu(menubar, tearoff=0, bg=BG_COLOR, fg=FG_COLOR)
    ajustes.add_command(label="Inicio con Windows…", command=lambda: open_autostart_window(root, set_status(state)))
    menubar.add_cascade(label="Ajustes", menu=ajustes)

    ayuda = tk.Menu(menubar, tearoff=0, bg=BG_COLOR, fg=FG_COLOR)
    ayuda.add_command(label="Info", command=lambda: open_info_window(root, state))
    menubar.add_cascade(label="Ayuda", menu=ayuda)

    # -------- Header --------
    def _get_name():
        return state.cfg.data.get("camera_id", "") or "Sin ID"
    header = HeaderBanner(root, camera_name_getter=_get_name)
    header.pack(fill="x", pady=0)
    # refrescar el header cuando se actualiza la info del cliente
    def _on_info_updated(_evt=None):
        header._render()   # vuelve a dibujar usando el valor actual guardado
    root.bind("<<INFO_UPDATED>>", _on_info_updated)


    # -------- Viewer --------
    viewer = tk.Frame(root, bg=BG_COLOR); viewer.pack(fill="both", expand=True, padx=10, pady=10)
    state.image_panel = ImagePanel(viewer, bg=BG_COLOR, min_size=(IMG_MIN_W, IMG_MIN_H))
    state.image_panel.pack(fill="both", expand=True)

    # -------- Footer --------
    footer = tk.Frame(root, bg=BTN_COLOR); footer.pack(fill="x", padx=0, pady=0)

    # Botones
    buttons_wrap = tk.Frame(footer, bg=BTN_COLOR); buttons_wrap.pack(side="left", padx=8, pady=8)
    gridpad = dict(padx=6, pady=0)

    wr, state.btn_switch_timelapse = outlined_button(buttons_wrap, "Iniciar Timelapse", lambda: toggle_timelapse(state))
    wr.grid(row=0, column=0, **gridpad)
    wr, state.btn_switch_trans = outlined_button(buttons_wrap, "Iniciar transmisión", lambda: toggle_transmision(state))
    wr.grid(row=0, column=1, **gridpad)
    wr, state.btn_maniobra = outlined_button(buttons_wrap, "Maniobra", lambda: toggle_maniobra(state))
    wr.grid(row=0, column=2, **gridpad)
    wr, _btn_take = outlined_button(buttons_wrap, "📸 Captura", lambda: take_and_update(state))
    wr.grid(row=0, column=3, **gridpad)

    cfg_holder = {"win": None}
    def open_config():
        if cfg_holder["win"] is not None and tk.Toplevel.winfo_exists(cfg_holder["win"].win):
            cfg_holder["win"].win.deiconify(); cfg_holder["win"].win.lift(); return

        def on_save_config():
            (freq_min, dias, hstart, hend, maniobra_dur, maniobra_int,
             photo_res_label, video_res_label, cam_index, gps_lat, gps_lon) = cfg_holder["win"].read_all()

            # Guardar config
            state.cfg.set(
                frecuencia_min=freq_min, dias=dias, hora_inicio=hstart, hora_fin=hend,
                maniobra_duracion=maniobra_dur, maniobra_intervalo=maniobra_int,
                photo_resolution_label=photo_res_label, video_resolution_label=video_res_label,
                cam_index=cam_index, gps_lat=gps_lat, gps_lon=gps_lon
            )

            # Actualizar estado + cámara
            state.photo_resolution_label = photo_res_label
            state.video_resolution_label = video_res_label
            if cam_index != state.cam_index:
                state.cam_index = cam_index
                try:
                    camera_manager.set_cam_index(state.cam_index)
                except Exception as e:
                    set_status(state)(f"No se pudo cambiar cámara: {e}")

            set_status(state)("Configuración guardada.")

        def on_auto_wb():
            try:
                camera_manager.set_auto_modes(enable_exposure_auto=True, enable_wb_auto=True)
                set_status(state)("Autoajuste aplicado (expo/WB automáticos).")
            except Exception as e:
                set_status(state)(f"Autoajuste no disponible: {e}")

        def on_open_driver():
            try:
                camera_manager.show_driver_settings()
            except Exception as e:
                messagebox.showinfo("Ajustes avanzados", f"No disponible: {e}")

        def on_resolution_change(new_label: str):
            # (modo simple) un solo combo → aplica a foto y video
            state.video_resolution_label = new_label
            state.photo_resolution_label = new_label
            state.current_resolution_label = new_label  # compatibilidad
            state.cfg.set(video_resolution_label=new_label, photo_resolution_label=new_label)
            set_status(state)(f"Resolución preferida: {new_label}")

        cfg_holder["win"] = ConfigWindow(root, state, on_save_config, on_auto_wb, on_open_driver, on_resolution_change)

    wr, _btn_open_config = outlined_button(buttons_wrap, "Configuración", open_config)
    wr.grid(row=0, column=4, **gridpad)

    wr, _btn_open_folder = outlined_button(buttons_wrap, "Abrir carpeta", lambda: _abrir_carpeta(state))
    wr.grid(row=0, column=5, **gridpad)

    # Status box + Logo empresa a continuación
    status_box = tk.Frame(footer, bg="black", bd=0, highlightthickness=1, highlightbackground="#333")
    status_box.pack(side="left", padx=8, pady=8)

    state.lbl_status_transmision = tk.Label(status_box, text="Transmisión: DETENIDA", bg="black", fg="#a6ffa6", font=("Arial", 11, "bold"))
    state.lbl_status_transmision.pack(anchor="w", padx=10, pady=2)
    state.lbl_status_timelapse = tk.Label(status_box, text="Timelapse: DETENIDO", bg="black", fg="#a6ffa6", font=("Arial", 11, "bold"))
    state.lbl_status_timelapse.pack(anchor="w", padx=10, pady=2)
    state.lbl_status_maniobra = tk.Label(status_box, text="Maniobra: INACTIVA", bg="black", fg="#a6ffa6", font=("Arial", 11, "bold"))
    state.lbl_status_maniobra.pack(anchor="w", padx=10, pady=2)
    state.lbl_status_general = tk.Label(status_box, text="Listo", bg="black", fg="#e0e0e0", font=("Arial", 10))
    state.lbl_status_general.pack(anchor="w", padx=10, pady=4)

    company_logo = None
    try:
        if os.path.exists(COMPANY_LOGO_PATH):
            img = Image.open(COMPANY_LOGO_PATH).convert("RGBA")
            img = ImageOps.contain(img, (220, 80))
            company_logo = ImageTk.PhotoImage(img)
    except Exception as e:
        print(f"[FOOTER LOGO] Error: {e}")

    if company_logo:
        lbl_company = tk.Label(footer, image=company_logo, bg=BTN_COLOR)
        lbl_company.image = company_logo
        # pegado a la derecha del cuadro de estado (no al borde de la ventana)
        lbl_company.pack(side="left", padx=8, pady=8)

    # Inicialización de carpetas y estado inicial
    _ensure_initial_dirs(state)
    update_main_image(state)
    update_stream_ui(state); update_timelapse_ui(state); update_maniobra_ui(state)

    # Sincronización a Drive periódica
    _schedule_sync(state)

    # Cierre
    def on_close():
        state.cfg.set(
            stream_activo=state.streaming,
            timelapse_activo=state.timelapse_running,
            photo_resolution_label=state.photo_resolution_label,
            video_resolution_label=state.video_resolution_label,
            cam_index=state.cam_index
        )
        try:
            camera_manager.stop_stream(); camera_manager.shutdown()
        except Exception:
            pass
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_close)

    return state


# =========================
# Acciones de menú
# =========================
def _cambiar_directorio_fotos(state: AppState):
    nueva = fd.askdirectory(title="Selecciona la carpeta para guardar fotos")
    if not nueva: return
    if not has_write_access(nueva):
        messagebox.showerror("Permisos", "No hay permiso de escritura en la carpeta elegida."); return
    state.photo_dir = nueva; state.cfg.set(photo_dir=nueva)
    messagebox.showinfo("Ruta actualizada", f"Carpeta de fotos:\n{state.photo_dir}")
    update_main_image(state)


def _seleccionar_drive_manual(state: AppState):
    carpeta = fd.askdirectory(title="Selecciona la carpeta de Google Drive (KatcamAustralia/fotos)")
    if not carpeta: return
    if not has_write_access(carpeta):
        messagebox.showerror("Permisos", "No hay permiso de escritura en la carpeta seleccionada."); return
    state.drive_dir = carpeta; state.cfg.set(drive_dir=carpeta)
    messagebox.showinfo("Ruta actualizada", f"Carpeta de Google Drive:\n{state.drive_dir}")


def _abrir_carpeta(state: AppState):
    if not state.photo_dir:
        messagebox.showerror("Carpeta", "La carpeta de fotos no está configurada."); return
    path = os.path.realpath(state.photo_dir)
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            import subprocess; subprocess.Popen(["open", path])
        else:
            import subprocess; subprocess.Popen(["xdg-open", path])
    except Exception as e:
        messagebox.showerror("Carpeta", f"No se pudo abrir la carpeta:\n{e}")


# =========================
# UI/Estado
# =========================
def set_status(state: AppState):
    def _set(text):
        if state.lbl_status_general:
            state.lbl_status_general.config(text=text)
    return _set


def update_stream_ui(state: AppState):
    if state.streaming:
        if state.lbl_status_transmision:
            state.lbl_status_transmision.config(text="Transmisión: ACTIVA")
        if state.btn_switch_trans:
            state.btn_switch_trans.config(text="⏹ Live", bg="#FFFB92", fg="#000000")
    else:
        if state.lbl_status_transmision:
            state.lbl_status_transmision.config(text="Transmisión: DETENIDA")
        if state.btn_switch_trans:
            state.btn_switch_trans.config(text="▶ Live", bg=BTN_COLOR, fg=BTN_TEXT_COLOR)


def update_timelapse_ui(state: AppState):
    state.lbl_status_timelapse.config(text="Timelapse: ACTIVO" if state.timelapse_running else "Timelapse: DETENIDO")
    state.btn_switch_timelapse.config(
        text="⏹ Timelapse" if state.timelapse_running else "▶ Timelapse",
        bg="#FFFB92" if state.timelapse_running else BTN_COLOR,
        fg="#000000" if state.timelapse_running else BTN_TEXT_COLOR
    )


def update_maniobra_ui(state: AppState):
    state.lbl_status_maniobra.config(text="Short: ACTIVA" if state.maniobra_running else "Short: INACTIVA")
    state.btn_maniobra.config(
        text="⏹ Short" if state.maniobra_running else "▶ Short",
        bg="#FFFA78" if state.maniobra_running else BTN_COLOR,
        fg="#000000" if state.maniobra_running else BTN_TEXT_COLOR
    )


def _pause_stream_if_needed(state: AppState):
    """Pausa transmisión si está activa y marca que debe reanudarse
    luego de terminar la acción externa (foto manual, maniobra, etc.)."""
    if state.streaming:
        state.resume_stream_after_action = True
        try:
            camera_manager.stop_stream()
        except Exception:
            pass
        state.streaming = False
        update_stream_ui(state)


def _resume_stream_if_marked(state: AppState):
    """Reanuda transmisión solo si fue pausada por una acción."""
    if state.resume_stream_after_action:
        state.resume_stream_after_action = False
        stream_on(state)


# =========================
# Imagen principal
# =========================
def _get_last_photo(state: AppState):
    if not state.photo_dir or not os.path.exists(state.photo_dir): return None
    fotos = sorted([f for f in os.listdir(state.photo_dir) if f.lower().endswith((".jpg",".jpeg",".png"))])
    return os.path.join(state.photo_dir, fotos[-1]) if fotos else None


def update_main_image(state: AppState):
    if state.image_panel is None: return
    try:
        last_photo = _get_last_photo(state)
        if last_photo and os.path.exists(last_photo):
            img = Image.open(last_photo).convert("RGB")
        else:
            img = Image.new("RGB", (IMG_MIN_W, IMG_MIN_H), (64, 64, 64))
        state.image_panel.set_image(img)
    except Exception as e:
        set_status(state)(f"Error mostrando imagen: {e}")


# =========================
# Stream
# =========================
def stream_on(state: AppState):
    if state.streaming:
        return
    state.streaming = True

    # Usar resolución de VIDEO/stream
    label = state.video_resolution_label or state.current_resolution_label or DEFAULT_RES_LABEL
    wh = _find_res(label)
    try:
        if wh and hasattr(camera_manager, "set_resolution"):
            camera_manager.set_resolution(*wh)
    except Exception:
        pass

    camera_manager.start_stream()
    update_stream_ui(state)
    set_status(state)("Transmisión en directo")
    _tick_stream(state)


def stream_off(state: AppState):
    if not state.streaming:
        return
    state.streaming = False
    try:
        camera_manager.stop_stream()
    except Exception:
        pass
    update_stream_ui(state)
    set_status(state)("Transmisión detenida")
    update_main_image(state)


def _tick_stream(state: AppState):
    if not state.streaming: return
    try:
        frame_rgb = camera_manager.get_frame_rgb()
        if frame_rgb is not None and state.image_panel:
            img = Image.fromarray(frame_rgb); state.image_panel.set_image(img)
    except Exception:
        pass
    if state.streaming:
        state.root.after(40, lambda: _tick_stream(state))  # ~25fps


def toggle_transmision(state: AppState):
    # Transmisión puede convivir con timelapse (solo se pausa durante la foto).
    if state.maniobra_running:
        messagebox.showwarning("En ejecución",
                               "La maniobra está en ejecución.\nDetén la maniobra para realizar esta acción.")
        return
    if state.streaming:
        stream_off(state)
    else:
        stream_on(state)


# =========================
# Foto (manual)
# =========================
def take_and_update(state: AppState):
    # Si hay maniobra corriendo, bloquear
    if state.maniobra_running:
        messagebox.showwarning("En ejecución",
                               "La maniobra está en ejecución.\nDetén la maniobra para realizar esta acción.")
        return
    # Sacar foto está permitido durante timelapse.
    if state.is_capturing:
        set_status(state)("Ya hay una captura en curso..."); return

    # Si transmisión está activa, pausarla y marcar reanudación
    _pause_stream_if_needed(state)

    state.is_capturing = True
    set_status(state)("Preparando captura...")

    def _work():
        try:
            # Tamaño preferido: usa resolución de FOTO y si no hay, cae a la general
            label = state.photo_resolution_label or state.current_resolution_label or DEFAULT_RES_LABEL
            wh = _find_res(label)
            prefer = [wh] if wh else None

            take_photo(
                dest_folder=state.photo_dir,
                prefer_sizes=prefer,
                jpeg_quality=95,
                auto_resume_stream=False,
                block_until_done=True
            )
            msg = "Foto tomada."
        except Exception as e:
            msg = f"Error: {e}"
        finally:
            def _finish():
                set_status(state)(msg)
                update_main_image(state)
                state.is_capturing = False
                # Si pausamos transmisión para esta acción, reanudar
                _resume_stream_if_marked(state)
            state.root.after(0, _finish)

    threading.Thread(target=_work, daemon=True).start()


# =========================
# Timelapse
# =========================
def toggle_timelapse(state: AppState):
    if state.maniobra_running:
        messagebox.showwarning("En ejecución",
                               "La maniobra está en ejecución.\nDetén la maniobra para realizar esta acción.")
        return

    if not state.timelapse_running:
        # lee config (frecuencia en MINUTOS)
        freq_min = state.cfg.data.get("frecuencia_min", state.cfg.data.get("frecuencia", "10"))
        try:
            state.interval_ms = int(float(freq_min) * 60_000)
        except Exception:
            state.interval_ms = 10 * 60_000

        dias_cfg = state.cfg.data.get("dias", [True]*7)
        dias_lista = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
        state.days_selected = [d for d, ok in zip(dias_lista, dias_cfg) if ok]

        state.hour_start = state.cfg.data.get("hora_inicio", "08:00")
        state.hour_end   = state.cfg.data.get("hora_fin", "18:00")

        state.timelapse_running = True
        set_status(state)("Timelapse: activado. Esperando próxima foto...")
        update_timelapse_ui(state)
        _schedule_timelapse_tick(state)
    else:
        state.timelapse_running = False
        set_status(state)("Timelapse detenido.")
        update_timelapse_ui(state)


def _schedule_timelapse_tick(state: AppState):
    if not state.timelapse_running:
        return
    state.root.after(state.interval_ms, lambda: _timelapse_tick(state))


def _timelapse_tick(state: AppState):
    if not state.timelapse_running:
        return

    # Si justo hay una captura manual en curso, saltamos este tick
    if state.is_capturing:
        set_status(state)("Timelapse: captura manual en curso...")
        return _schedule_timelapse_tick(state)

    now = datetime.now()
    # filtro por día
    dias_en = {
        "monday":"lunes", "tuesday":"martes", "wednesday":"miércoles", "thursday":"jueves",
        "friday":"viernes", "saturday":"sábado", "sunday":"domingo"
    }
    dia_actual_es = dias_en.get(now.strftime("%A").lower(), "lunes")
    if state.days_selected and (dia_actual_es not in state.days_selected):
        set_status(state)("Timelapse: esperando día válido...")
        return _schedule_timelapse_tick(state)

    # filtro por hora
    if state.hour_start and state.hour_end:
        hhmm = now.strftime("%H:%M")
        if not (state.hour_start <= hhmm <= state.hour_end):
            set_status(state)("Timelapse: fuera de horario...")
            return _schedule_timelapse_tick(state)

    # --- Captura del timelapse ---
    # Si transmisión está activa, pausa SOLO durante la foto y reanuda al terminar
    paused_stream_here = False
    if state.streaming:
        paused_stream_here = True
        try:
            camera_manager.stop_stream()
        except Exception:
            pass
        state.streaming = False
        update_stream_ui(state)

    set_status(state)("Timelapse: capturando...")
    # Usar resolución de FOTO
    label = state.photo_resolution_label or state.current_resolution_label or DEFAULT_RES_LABEL
    wh = _find_res(label)
    prefer = [wh] if wh else None

    def _do_capture():
        try:
            take_photo(
                dest_folder=state.photo_dir,
                prefer_sizes=prefer,
                jpeg_quality=95,
                auto_resume_stream=False,
                block_until_done=True
            )
            msg = "Timelapse: foto tomada."
        except Exception as e:
            msg = f"Timelapse: error de captura: {e}"
        finally:
            def _finish():
                set_status(state)(msg)
                update_main_image(state)
                # Reanudar transmisión si la pausamos aquí
                if paused_stream_here:
                    stream_on(state)
                set_status(state)("Timelapse: esperando próxima captura...")
                _schedule_timelapse_tick(state)
            state.root.after(0, _finish)

    threading.Thread(target=_do_capture, daemon=True).start()


# =========================
# Maniobra
# =========================
def toggle_maniobra(state: AppState):
    if not state.maniobra_running:
        # Si timelapse está corriendo → pausar y recordar que hay que reanudarlo.
        if state.timelapse_running:
            state.timelapse_running = False
            update_timelapse_ui(state)
            state.timelapse_paused_by_maniobra = True
            set_status(state)("Timelapse pausado por maniobra.")

        # Pausar transmisión si está activa y marcar reanudar después
        _pause_stream_if_needed(state)

        try:
            duracion_min = float(state.cfg.data.get("maniobra_duracion", "10"))
            intervalo_s  = float(state.cfg.data.get("maniobra_intervalo", "1"))
        except Exception as e:
            set_status(state)(f"Error en maniobra: {e}")
            _resume_stream_if_marked(state)
            if state.timelapse_paused_by_maniobra:
                state.timelapse_paused_by_maniobra = False
                toggle_timelapse(state)
            return

        fin = datetime.now() + timedelta(seconds=duracion_min * 60)
        state.maniobra_running = True
        update_maniobra_ui(state)
        set_status(state)("Maniobra en curso...")

        def _tick():
            if datetime.now() >= fin or not state.maniobra_running:
                state.maniobra_running = False
                update_maniobra_ui(state)
                set_status(state)("Maniobra finalizada.")
                # Reanudar transmisión si la pausamos para esto
                _resume_stream_if_marked(state)
                # Reanudar timelapse si lo habíamos pausado por maniobra
                if state.timelapse_paused_by_maniobra:
                    state.timelapse_paused_by_maniobra = False
                    toggle_timelapse(state)
                return

            # Toma una foto (timelapse está pausado)
            threading.Thread(
                target=lambda: take_photo(state.photo_dir, block_until_done=True, auto_resume_stream=False),
                daemon=True
            ).start()
            update_main_image(state)
            state.root.after(int(intervalo_s * 1000), _tick)

        _tick()

    else:
        # Detener maniobra manualmente
        state.maniobra_running = False
        update_maniobra_ui(state)
        set_status(state)("Maniobra cancelada por el usuario.")
        _resume_stream_if_marked(state)
        if state.timelapse_paused_by_maniobra:
            state.timelapse_paused_by_maniobra = False
            toggle_timelapse(state)


# =========================
# Directorios iniciales
# =========================
def _ensure_initial_dirs(state: AppState):
    if not state.photo_dir or not os.path.exists(state.photo_dir) or not has_write_access(state.photo_dir):
        while True:
            ruta = fd.askdirectory(title="Selecciona la carpeta para guardar fotos (pendrive o local)")
            if ruta and has_write_access(ruta):
                state.photo_dir = ruta; state.cfg.set(photo_dir=ruta); break
            elif ruta:
                messagebox.showerror("Permisos", "No hay permiso de escritura en la carpeta elegida.")
            else:
                messagebox.showerror("Error", "Debes seleccionar una carpeta para continuar.")
    if not state.drive_dir or not os.path.exists(state.drive_dir) or not has_write_access(state.drive_dir):
        while True:
            ruta = fd.askdirectory(title="Selecciona la carpeta de Google Drive (KatcamAustralia/fotos)")
            if ruta and has_write_access(ruta):
                state.drive_dir = ruta; state.cfg.set(drive_dir=ruta); break
            elif ruta:
                messagebox.showerror("Permisos", "No hay permiso de escritura en la carpeta elegida.")
            else:
                messagebox.showerror("Error", "Debes seleccionar una carpeta para continuar.")


# =========================
# Sincronización a Drive
# =========================
def _sync_photos(state: AppState):
    try:
        if not (state.photo_dir and os.path.exists(state.photo_dir)):
            set_status(state)("Carpeta de fotos inválida."); return
        if not (state.drive_dir and os.path.exists(state.drive_dir)):
            set_status(state)("No se encontró Google Drive para sincronizar."); return

        fotos_src = sorted([f for f in os.listdir(state.photo_dir) if f.lower().endswith((".jpg",".jpeg",".png"))])
        fotos_dst = set(os.listdir(state.drive_dir))
        nuevas = [f for f in fotos_src if f not in fotos_dst]
        for f in nuevas:
            src = os.path.join(state.photo_dir, f); dst = os.path.join(state.drive_dir, f)
            try:
                import shutil; shutil.copy2(src, dst)
            except Exception:
                pass
        if nuevas:
            set_status(state)(f"Sincronizadas {len(nuevas)} fotos al Drive.")
    except Exception as e:
        set_status(state)(f"Sync error: {e}")


def _schedule_sync(state: AppState):
    _sync_photos(state)
    state.root.after(60_000, lambda: _schedule_sync(state))  # cada 60s

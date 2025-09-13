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

        # Alto del header responsivo (100–160 px según altura de pantalla)
        try:
            screen_h = parent.winfo_screenheight()
        except Exception:
            screen_h = 900
        self._target_h = max(100, min(160, int(screen_h * 0.16)))

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

        left_label = f"ID: {self._camera_name_getter()}"
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

    # Fullscreen / kiosk
    try:
        root.attributes('-fullscreen', True)
    except tk.TclError:
        try:
            root.state('zoomed')
        except Exception:
            pass

    state = AppState(root)

    # -------- Header --------
    def _get_name():
        return state.cfg.data.get("camera_id", "") or "Sin ID"

    header = HeaderBanner(root, camera_name_getter=_get_name)
    header.pack(fill="x", pady=0)
    header.update_idletasks()
    try:
        header.configure(height=header._target_h)
    except Exception:
        pass
    header.pack_propagate(False)

    # refrescar header cuando cambia la info
    def _on_info_updated(_evt=None):
        header._render()
        try:
            if hasattr(header, "_toolbar_win"):
                header._canvas.tag_raise(header._toolbar_win)
        except Exception:
            pass
    root.bind("<<INFO_UPDATED>>", _on_info_updated)

    # -------- Viewer (responsivo) --------
    viewer = tk.Frame(root, bg=BG_COLOR)
    viewer.pack(fill="both", expand=True, padx=10, pady=10)

    # Minimos responsivos: aseguran uso en 800x600 sin romper en pantallas grandes
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    min_w = max(320, int(sw * 0.25), IMG_MIN_W)  # al menos 320 o 25% del ancho o lo que diga settings
    min_h = max(220, int(sh * 0.25), IMG_MIN_H)  # al menos 220 o 25% del alto o lo que diga settings

    state.image_panel = ImagePanel(viewer, bg=BG_COLOR, min_size=(min_w, min_h))
    state.image_panel.pack(fill="both", expand=True)

    # ============================================================
    # Config modal (debe existir ANTES de construir el botón ⚙)
    # ============================================================
    cfg_holder = {"win": None}

    def open_config():
        if cfg_holder["win"] is not None and tk.Toplevel.winfo_exists(cfg_holder["win"].win):
            cfg_holder["win"].win.deiconify()
            cfg_holder["win"].win.lift()
            return

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
            state.video_resolution_label = new_label
            state.photo_resolution_label = new_label
            state.current_resolution_label = new_label
            state.cfg.set(video_resolution_label=new_label, photo_resolution_label=new_label)
            set_status(state)(f"Resolución preferida: {new_label}")

        def on_save_config():
            vals = cfg_holder["win"].read_all()
            # Acepta 9 valores (sin GPS). Si vienen 11, ignora los extra.
            if len(vals) == 9:
                (freq_min, dias, hstart, hend, maniobra_dur, maniobra_int,
                 photo_res_label, video_res_label, cam_index) = vals
            else:
                (freq_min, dias, hstart, hend, maniobra_dur, maniobra_int,
                 photo_res_label, video_res_label, cam_index, *_gps_ignored) = vals

            state.cfg.set(
                frecuencia_min=freq_min, dias=dias, hora_inicio=hstart, hora_fin=hend,
                maniobra_duracion=maniobra_dur, maniobra_intervalo=maniobra_int,
                photo_resolution_label=photo_res_label, video_resolution_label=video_res_label,
                cam_index=cam_index
            )

            state.photo_resolution_label = photo_res_label
            state.video_resolution_label = video_res_label

            if cam_index != state.cam_index:
                state.cam_index = cam_index
                try:
                    camera_manager.set_cam_index(state.cam_index)
                except Exception as e:
                    set_status(state)(f"No se pudo cambiar cámara: {e}")

            set_status(state)("Configuración guardada.")

        cfg_holder["win"] = ConfigWindow(
            root, state, on_save_config, on_auto_wb, on_open_driver, on_resolution_change
        )

    # Helper: abrir galería si existe, o carpeta como fallback
    def _open_gallery_or_folder():
        func = globals().get("open_gallery_window")
        if callable(func):
            try:
                func(state)
                return
            except Exception:
                pass
        _abrir_carpeta(state)

    # -------- Mini toolbar en el header: ☰  ⚙  📁 --------
    toolbar = tk.Frame(header, bg=BTN_COLOR)

    # ☰ Menú
    menu_btn = tk.Button(
        toolbar, text="☰",
        bg=BTN_COLOR, fg=BTN_TEXT_COLOR,
        bd=0, relief="flat", font=("Arial", 15, "bold"),
        padx=10, pady=4, cursor="hand2"
    )
    menu_btn.pack(side="left", padx=(0, 6))

    dd_menu = tk.Menu(
        menu_btn, tearoff=0,
        bg=BG_COLOR, fg=FG_COLOR,
        activebackground=BTN_COLOR, activeforeground=BTN_TEXT_COLOR
    )
    dd_menu.add_command(label="Cambiar carpeta de fotos…", command=lambda: _cambiar_directorio_fotos(state))
    dd_menu.add_command(label="Cambiar carpeta de Google Drive…", command=lambda: _seleccionar_drive_manual(state))
    dd_menu.add_separator()
    dd_menu.add_command(label="Inicio con Windows…", command=lambda: open_autostart_window(root, set_status(state)))
    dd_menu.add_separator()
    dd_menu.add_command(label="Info", command=lambda: open_info_window(root, state))

    def _show_menu(_evt=None):
        dd_menu.update_idletasks()
        x = menu_btn.winfo_rootx()
        y = menu_btn.winfo_rooty() + menu_btn.winfo_height()
        dd_menu.post(x, y)
    menu_btn.configure(command=_show_menu)

    # ⚙ Config
    gear_btn = tk.Button(
        toolbar, text="⚙",
        command=open_config,
        bg=BTN_COLOR, fg=BTN_TEXT_COLOR,
        bd=0, relief="flat", font=("Arial", 14, "bold"),
        padx=10, pady=4, cursor="hand2"
    )
    gear_btn.pack(side="left", padx=(0, 6))

    # 📁 Galería (o carpeta)
    folder_btn = tk.Button(
        toolbar, text="📁",
        command=_open_gallery_or_folder,
        bg=BTN_COLOR, fg=BTN_TEXT_COLOR,
        bd=0, relief="flat", font=("Arial", 14, "bold"),
        padx=10, pady=4, cursor="hand2"
    )
    folder_btn.pack(side="left")

    # Colocar la toolbar en el header (y asegurarla arriba)
    header._toolbar_win = header._canvas.create_window(10, 10, window=toolbar, anchor="nw")
    header._canvas.update_idletasks()
    header._canvas.tag_raise(header._toolbar_win)
    # Si el header se re-dibuja, vuelve a poner la toolbar arriba
    header.bind("<Configure>", lambda e: header._canvas.tag_raise(header._toolbar_win), add="+")

    # -------- Footer (centrado) --------
    footer = tk.Frame(root, bg=BTN_COLOR)
    footer.pack(side="bottom", fill="x", padx=0, pady=0)

    # Centrado con grid (no mezclar pack en este contenedor)
    footer.grid_columnconfigure(0, weight=1)   # spacer izq
    footer.grid_columnconfigure(1, weight=0)   # contenido
    footer.grid_columnconfigure(2, weight=1)   # spacer der

    # Contenedor centrado
    center = tk.Frame(footer, bg=BTN_COLOR)
    center.grid(row=0, column=1, pady=8)

    # --- Botonera (centrada) ---
    buttons_wrap = tk.Frame(center, bg=BTN_COLOR)   # hijo de center
    buttons_wrap.pack(side="left", padx=8)
    gridpad = dict(padx=6, pady=0)

    # Función para elegir el tamaño de ícono según la altura de la ventana
    def _icon_size():
        h = root.winfo_height()
        if h >= 900: return 60
        if h >= 700: return 48
        if h >= 600: return 40
        if h >= 500: return 30
        if h >= 400: return 24
        return 20

    def _get_icon(name):
        size = _icon_size()
        path = os.path.join("assets", f"{name}{size}px.png")
        try:
            img = Image.open(path).convert("RGBA")
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    live_icon = _get_icon("live")
    cam_icon = _get_icon("cam")

    wr, state.btn_switch_timelapse = outlined_button(buttons_wrap, "▶ Timelapse", lambda: toggle_timelapse(state))
    wr.grid(row=0, column=0, **gridpad)

    wr, state.btn_maniobra = outlined_button(buttons_wrap, "▶ Short TL", lambda: toggle_maniobra(state))
    wr.grid(row=0, column=1, **gridpad)

    # Botón Live solo icono, sin borde ni texto
    state.btn_switch_trans = tk.Button(
        buttons_wrap,
        command=lambda: toggle_transmision(state),
        image=live_icon if live_icon else None,
        bd=0, relief="flat", bg=BTN_COLOR, activebackground=BTN_COLOR,
        width=live_icon.width() if live_icon else 48,
        height=live_icon.height() if live_icon else 48,
        highlightthickness=0, cursor="hand2"
    )
    state.btn_switch_trans.image = live_icon
    state.btn_switch_trans.grid(row=0, column=2, **gridpad)

    # Botón Photo solo icono, sin borde ni texto
    _btn_take = tk.Button(
        buttons_wrap,
        command=lambda: take_and_update(state),
        image=cam_icon if cam_icon else None,
        bd=0, relief="flat", bg=BTN_COLOR, activebackground=BTN_COLOR,
        width=cam_icon.width() if cam_icon else 48,
        height=cam_icon.height() if cam_icon else 48,
        highlightthickness=0, cursor="hand2"
    )
    _btn_take.image = cam_icon
    _btn_take.grid(row=0, column=3, **gridpad)

    # --- Status + logo (centrados junto a la botonera) ---
    status_box = tk.Frame(center, bg="black", bd=0, highlightthickness=1, highlightbackground="#333")
    status_box.pack(side="left", padx=12)

    state.lbl_status_transmision = tk.Label(status_box, text="Live: STOPPED", bg="black", fg="#a6ffa6", font=("Arial", 11, "bold"))
    state.lbl_status_transmision.pack(anchor="w", padx=10, pady=2)
    state.lbl_status_timelapse = tk.Label(status_box, text="Timelapse: STOPPED", bg="black", fg="#a6ffa6", font=("Arial", 11, "bold"))
    state.lbl_status_timelapse.pack(anchor="w", padx=10, pady=2)
    state.lbl_status_maniobra = tk.Label(status_box, text="Short: INACTIVE", bg="black", fg="#a6ffa6", font=("Arial", 11, "bold"))
    state.lbl_status_maniobra.pack(anchor="w", padx=10, pady=2)
    state.lbl_status_general = tk.Label(status_box, text="Ready", bg="black", fg="#e0e0e0", font=("Arial", 10))
    state.lbl_status_general.pack(anchor="w", padx=10, pady=4)

    lbl_company = None
    company_logo_img = None

    def _logo_size():
        h = root.winfo_height()
        if h >= 900: return (260, 90)
        if h >= 700: return (220, 80)
        if h >= 600: return (180, 60)
        if h >= 500: return (140, 48)
        if h >= 400: return (100, 36)
        return (80, 28)

    def _update_company_logo():
        nonlocal lbl_company, company_logo_img
        if not os.path.exists(COMPANY_LOGO_PATH):
            if lbl_company:
                lbl_company.destroy()
                lbl_company = None
            return
        size = _logo_size()
        try:
            img = Image.open(COMPANY_LOGO_PATH).convert("RGBA")
            img = ImageOps.contain(img, size)
            company_logo_img = ImageTk.PhotoImage(img)
        except Exception as e:
            print(f"[FOOTER LOGO] Error: {e}")
            return
        if lbl_company is None:
            lbl_company = tk.Label(center, bg=BTN_COLOR)
            lbl_company.pack(side="left", padx=12)
        lbl_company.config(image=company_logo_img)
        lbl_company.image = company_logo_img

    _update_company_logo()

    # --- Layout responsivo del footer (apilar o en línea) ---
    def _layout_footer(_evt=None):
        w = root.winfo_width()

        # Limpiar empaques actuales dentro de 'center'
        try:
            buttons_wrap.pack_forget()
        except Exception:
            pass
        try:
            status_box.pack_forget()
        except Exception:
            pass
        try:
            if lbl_company is not None:
                lbl_company.pack_forget()
        except Exception:
            pass

        # Vista estrecha: apilar en vertical
        if w < 900:
            buttons_wrap.pack(side="top", pady=(0, 6))
            status_box.pack(side="top", pady=(0, 6))
            if lbl_company is not None:
                lbl_company.pack(side="top", pady=(0, 6))
        else:
            # Vista amplia: en línea (centrado porque 'center' está en la columna 1)
            buttons_wrap.pack(side="left", padx=8)
            status_box.pack(side="left", padx=12)
            if lbl_company is not None:
                lbl_company.pack(side="left", padx=12)
        _update_company_logo()

    # Aplicar ahora y en cada resize
   
    

    root.update_idletasks()
    _layout_footer()
        # Footer fijo y mínimos
    footer.update_idletasks()
    footer.configure(height=footer.winfo_reqheight())
    footer.pack_propagate(False)
    min_w = max(MIN_APP_W, header.winfo_reqwidth(), footer.winfo_reqwidth())
    min_h = max(MIN_APP_H, header.winfo_reqheight() + 120 + footer.winfo_reqheight())
    root.minsize(min_w, min_h)

    root.bind("<Configure>", _layout_footer)

    # --- Inicialización y cierre ---
    _ensure_initial_dirs(state)
    root.after(150, lambda: update_main_image(state))

    update_stream_ui(state); update_timelapse_ui(state); update_maniobra_ui(state)
    _schedule_sync(state)

    def on_close():
        state.cfg.set(
            stream_activo=state.streaming,
            timelapse_activo=state.timelapse_running,
            photo_resolution_label=state.photo_resolution_label,
            video_resolution_label=state.video_resolution_label,
            cam_index=state.cam_index
        )
        try:
            camera_manager.stop_stream()
            camera_manager.shutdown()
        except Exception:
            pass
        root.destroy()

    # Cierre solo con Shift+Q (bloquear cierre normal)
    root.protocol("WM_DELETE_WINDOW", lambda: None)
    root.bind_all('<Alt-F4>', lambda e: 'break')
    root.bind_all('<Shift-q>', lambda _e: on_close())
    root.bind_all('<Shift-Q>', lambda _e: on_close())

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
    if not state.photo_dir or not os.path.exists(state.photo_dir):
        return None
    fotos = [
        os.path.join(state.photo_dir, f)
        for f in os.listdir(state.photo_dir)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ]
    if not fotos:
        return None
    fotos.sort(key=lambda p: os.path.getmtime(p))
    return fotos[-1]



def update_main_image(state: AppState):
    if state.image_panel is None:
        return
    try:
        last_photo = _get_last_photo(state)
        if last_photo and os.path.exists(last_photo):
            img = Image.open(last_photo).convert("RGB")
        elif COMPANY_LOGO_PATH and os.path.exists(COMPANY_LOGO_PATH):
            # PNG con posible transparencia
            img = Image.open(COMPANY_LOGO_PATH).convert("RGBA")
        else:
            # Fallback final visible
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
def open_gallery_window(state: AppState):
    import queue, threading, calendar
    from datetime import datetime, date

    # Solo una galería a la vez
    if hasattr(state, "gallery_win") and state.gallery_win is not None:
        try:
            if tk.Toplevel.winfo_exists(state.gallery_win):
                state.gallery_win.deiconify()
                state.gallery_win.lift()
                return
        except Exception:
            state.gallery_win = None

    if not state.photo_dir or not os.path.isdir(state.photo_dir):
        messagebox.showerror("Carpeta", "La carpeta de fotos no está configurada o no existe.")
        return

    # ---------- Ventana sin contorno + al frente + centrada ----------
    win = tk.Toplevel(state.root)
    set_icon(win)
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    win.configure(bg=BG_COLOR)
    state.gallery_win = win

    W, H = 1000, 680
    try:
        sw, sh = state.root.winfo_screenwidth(), state.root.winfo_screenheight()
        x, y = (sw - W) // 2, (sh - H) // 2
    except Exception:
        x, y = 120, 80
    win.geometry(f"{W}x{H}+{x}+{y}")

    # ---------- Barra de título personalizada ----------
    titlebar = tk.Frame(win, bg=BTN_COLOR, height=36)
    titlebar.pack(fill="x")
    tk.Label(titlebar, text="Gallery", bg=BTN_COLOR, fg=BTN_TEXT_COLOR,
             font=("Arial", 12, "bold")).pack(side="left", padx=10)

    _drag = {"x": 0, "y": 0}
    def _start_drag(e): _drag.update(x=e.x, y=e.y)
    def _do_drag(e):
        try:
            win.geometry(f"+{win.winfo_x() + e.x - _drag['x']}+{win.winfo_y() + e.y - _drag['y']}")
        except Exception:
            pass
    titlebar.bind("<Button-1>", _start_drag)
    titlebar.bind("<B1-Motion>", _do_drag)

    # Cierre seguro
    def _close_now():
        stop_flag["stop"] = True
        try:
            t = worker.get("t")
            if t and t.is_alive():
                t.join(timeout=0.6)
        except Exception:
            pass
        _unbind_wheel()
        if win.winfo_exists():
            win.destroy()
        state.gallery_win = None

    tk.Button(titlebar, text="✕", command=_close_now,
              bg=BTN_COLOR, fg=BTN_TEXT_COLOR, bd=0,
              font=("Arial", 12, "bold"), padx=10, pady=2, cursor="hand2"
             ).pack(side="right", padx=6, pady=4)

    # ---------- Barra de info ----------
    bar = tk.Frame(win, bg=BG_COLOR); bar.pack(fill="x")
    tk.Label(bar, text=f"Folder: {state.photo_dir}", bg=BG_COLOR, fg=FG_COLOR
            ).pack(side="left", padx=10, pady=8)
    status_lbl = tk.Label(bar, text="", bg=BG_COLOR, fg=FG_COLOR)
    status_lbl.pack(side="left", padx=10, pady=8)

    # ---------- Filtros (fechas + cantidad) ----------
    ctrl = tk.Frame(win, bg=BG_COLOR); ctrl.pack(fill="x", pady=(0,4))

    # Helpers: datepicker minimalista
    def _set_entry_date(var: tk.StringVar, y: int, m: int, d: int):
        var.set(f"{y:04d}-{m:02d}-{d:02d}")

    def _open_datepicker(anchor_widget: tk.Widget, target_var: tk.StringVar):
        # pequeño calendario emergente
        cal = tk.Toplevel(win)
        cal.overrideredirect(True)
        cal.attributes("-topmost", True)
        cal.configure(bg=BG_COLOR)

        # posición junto al widget
        try:
            ax = anchor_widget.winfo_rootx()
            ay = anchor_widget.winfo_rooty() + anchor_widget.winfo_height() + 4
        except Exception:
            ax, ay = win.winfo_rootx()+80, win.winfo_rooty()+80
        cal.geometry(f"+{ax}+{ay}")

        now = datetime.now()
        state_cal = {"year": now.year, "month": now.month}

        header = tk.Frame(cal, bg=BTN_COLOR); header.pack(fill="x")
        lbl_title = tk.Label(header, text="", bg=BTN_COLOR, fg=BTN_TEXT_COLOR, font=("Arial", 10, "bold"))
        lbl_title.pack(side="top", pady=4)

        def _refresh_grid():
            for w in grid.winfo_children():
                w.destroy()
            y = state_cal["year"]; m = state_cal["month"]
            lbl_title.config(text=f"{calendar.month_name[m]} {y}")
            # nombres días
            row = 0
            for wd in ["Mo","Tu","We","Th","Fr","Sa","Su"]:
                tk.Label(grid, text=wd, bg=BG_COLOR, fg=FG_COLOR, width=3).grid(row=row, column=["Mo","Tu","We","Th","Fr","Sa","Su"].index(wd))
            row = 1
            for week in calendar.monthcalendar(y, m):
                col = 0
                for d in week:
                    if d == 0:
                        tk.Label(grid, text=" ", bg=BG_COLOR, fg=FG_COLOR, width=3).grid(row=row, column=col)
                    else:
                        def _mk_cmd(dd=d, yy=y, mm=m):
                            return lambda: (_set_entry_date(target_var, yy, mm, dd), cal.destroy())
                        tk.Button(grid, text=str(d), command=_mk_cmd(),
                                  bg=BTN_COLOR, fg=BTN_TEXT_COLOR, bd=0, width=3).grid(row=row, column=col, padx=1, pady=1)
                    col += 1
                row += 1

        def _prev_month():
            m = state_cal["month"] - 1
            y = state_cal["year"]
            if m < 1:
                m = 12; y -= 1
            state_cal.update(month=m, year=y); _refresh_grid()

        def _next_month():
            m = state_cal["month"] + 1
            y = state_cal["year"]
            if m > 12:
                m = 1; y += 1
            state_cal.update(month=m, year=y); _refresh_grid()

        tk.Button(header, text="◀", command=_prev_month, bg=BTN_COLOR, fg=BTN_TEXT_COLOR, bd=0, width=3
                 ).pack(side="left", padx=6)
        tk.Button(header, text="▶", command=_next_month, bg=BTN_COLOR, fg=BTN_TEXT_COLOR, bd=0, width=3
                 ).pack(side="right", padx=6)

        grid = tk.Frame(cal, bg=BG_COLOR); grid.pack(padx=6, pady=6)
        _refresh_grid()

        # cerrar si pierde foco
                # --- Cerrar el calendario si hace click fuera / ESC ---
        def _destroy_cal():
            try: win.unbind_all("<Button-1>")
            except Exception: pass
            try: cal.destroy()
            except Exception: pass

        # Cerrar si pierde foco (cuando aplica)
        cal.bind("<FocusOut>", lambda _e: _destroy_cal())

        # Cerrar con ESC
        cal.bind("<Escape>", lambda _e: _destroy_cal())

        # Cerrar al hacer click fuera del popup
        def _on_click_away(e):
            if not cal.winfo_exists():
                return
            # ¿Click fuera del rectángulo del calendario?
            cx, cy = cal.winfo_rootx(), cal.winfo_rooty()
            cw, ch = cal.winfo_width(), cal.winfo_height()
            if not (cx <= e.x_root <= cx + cw and cy <= e.y_root <= cy + ch):
                _destroy_cal()

        # Registramos el detector de click global mientras el popup está abierto
        win.bind_all("<Button-1>", _on_click_away, add="+")


    # Entradas de fecha
    tk.Label(ctrl, text="Desde:", bg=BG_COLOR, fg=FG_COLOR).pack(side="left", padx=(10,4))
    from_var = tk.StringVar()
    from_ent = tk.Entry(ctrl, textvariable=from_var, width=12); from_ent.pack(side="left")
    tk.Button(ctrl, text="📅", command=lambda: _open_datepicker(from_ent, from_var),
              bg=BTN_COLOR, fg=BTN_TEXT_COLOR, bd=0, padx=6).pack(side="left", padx=(2,10))

    tk.Label(ctrl, text="Hasta:", bg=BG_COLOR, fg=FG_COLOR).pack(side="left", padx=(4,4))
    to_var = tk.StringVar()
    to_ent = tk.Entry(ctrl, textvariable=to_var, width=12); to_ent.pack(side="left")
    tk.Button(ctrl, text="📅", command=lambda: _open_datepicker(to_ent, to_var),
              bg=BTN_COLOR, fg=BTN_TEXT_COLOR, bd=0, padx=6).pack(side="left", padx=(2,10))

    # Límite por defecto: 20
    tk.Label(ctrl, text="Últimas:", bg=BG_COLOR, fg=FG_COLOR).pack(side="left", padx=(4,4))
    limit_var = tk.StringVar(value="20")
    lim_opt = tk.OptionMenu(ctrl, limit_var, "20", "50", "100", "200")
    lim_opt.configure(bg=BTN_COLOR, fg=BTN_TEXT_COLOR, bd=0, highlightthickness=0, activebackground=BTN_COLOR)
    lim_opt.pack(side="left", padx=(0,8))

    def _ask_show_all():
        if messagebox.askyesno("Mostrar todas",
                               "Se mostrarán todas las imágenes.\nEsta acción puede tardar unos minutos.\n\n¿Continuar?"):
            _load_async(limit=None)

    tk.Button(ctrl, text="Mostrar todo", command=_ask_show_all,
              bg=BTN_COLOR, fg=BTN_TEXT_COLOR, bd=0,
              font=("Arial", 10, "bold"), padx=10, pady=4
             ).pack(side="right", padx=6)
    tk.Button(ctrl, text="Aplicar filtros",
              command=lambda: _load_async(limit=int(limit_var.get())),
              bg=BTN_COLOR, fg=BTN_TEXT_COLOR, bd=0,
              font=("Arial", 10, "bold"), padx=10, pady=4
             ).pack(side="right", padx=6)

    # ---------- Área scrollable ----------
    outer = tk.Frame(win, bg=BG_COLOR); outer.pack(fill="both", expand=True)
    canvas = tk.Canvas(outer, bg=BG_COLOR, highlightthickness=0, borderwidth=0)
    vbar = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vbar.set)
    vbar.pack(side="right", fill="y"); canvas.pack(side="left", fill="both", expand=True)
    inner = tk.Frame(canvas, bg=BG_COLOR)
    win_item = canvas.create_window((0, 0), window=inner, anchor="nw")
    # --- Scroll con rueda del mouse (Win/Mac/Linux) ---
    def _on_mousewheel(e):
        try:
            # Windows / macOS: e.delta = ±120 por “notch”
            if hasattr(e, "delta") and e.delta:
                steps = int(-e.delta / 120) or (-1 if e.delta > 0 else 1)
                canvas.yview_scroll(steps, "units")
            else:
                # Linux/X11: Button-4 (arriba), Button-5 (abajo)
                num = getattr(e, "num", None)
                if num == 4:
                    canvas.yview_scroll(-1, "units")
                elif num == 5:
                    canvas.yview_scroll(+1, "units")
        except Exception:
            pass
        return "break"

    def _bind_wheel():
        win.bind_all("<MouseWheel>", _on_mousewheel, add="+")
        win.bind_all("<Button-4>", _on_mousewheel, add="+")
        win.bind_all("<Button-5>", _on_mousewheel, add="+")
    def _unbind_wheel():
        try:
            win.unbind_all("<MouseWheel>")
            win.unbind_all("<Button-4>")
            win.unbind_all("<Button-5>")
        except Exception:
            pass

    _bind_wheel()


    # ---------- Grip de redimensionado ----------
    # --- Grip de redimensionado (esquina inferior derecha, funcional) ---
    grip = tk.Frame(win, bg=BTN_COLOR, width=26, height=26, cursor="bottom_right_corner")
    grip.place(relx=1.0, rely=1.0, x=0, y=0, anchor="se")   # pegado a la esquina
    grip.lift()  # asegúralo por encima del canvas

    # Decoración del grip (opcional)
    g_label = tk.Label(grip, text="◢", bg=BTN_COLOR, fg=BTN_TEXT_COLOR, font=("Arial", 11, "bold"))
    g_label.place(relx=0.5, rely=0.5, anchor="center")

    _resize = {"x":0,"y":0,"w":W,"h":H, "drag": False}

    def _start_resize(e):
        _resize.update(x=e.x_root, y=e.y_root, w=win.winfo_width(), h=win.winfo_height(), drag=True)
        # Mientras arrastro, escucho el movimiento globalmente
        win.bind_all("<Motion>", _do_resize, add="+")
        win.bind_all("<ButtonRelease-1>", _stop_resize, add="+")
        return "break"

    def _do_resize(e):
        if not _resize["drag"]:
            return
        dx = e.x_root - _resize["x"]; dy = e.y_root - _resize["y"]
        new_w = max(720, _resize["w"] + dx)
        new_h = max(480, _resize["h"] + dy)
        win.geometry(f"{int(new_w)}x{int(new_h)}+{win.winfo_x()}+{win.winfo_y()}")
        try:
            canvas.configure(scrollregion=canvas.bbox("all"))
        except Exception:
            pass

    def _stop_resize(e=None):
        _resize["drag"] = False
        try:
            win.unbind_all("<Motion>")
            win.unbind_all("<ButtonRelease-1>")
        except Exception:
            pass

    # Binds en el frame y también en su hijo (por si clickeas el icono)
    for w in (grip, g_label):
        w.bind("<Button-1>", _start_resize)


    # ---------- Loader asíncrono seguro ----------
    thumb_refs = []
    COLS = 4
    BATCH_UI = 16

    q = queue.Queue(maxsize=64)
    worker = {"t": None}
    stop_flag = {"stop": False}
    prog = {"done": 0, "total": 0}
    grid_state = {"count": 0}

    def _widget_exists(w):
        try:
            return bool(w.winfo_exists())
        except Exception:
            return False

    def _open_file(p: str):
        try:
            if sys.platform == "win32":
                os.startfile(p)
            elif sys.platform == "darwin":
                import subprocess; subprocess.Popen(["open", p])
            else:
                import subprocess; subprocess.Popen(["xdg-open", p])
        except Exception as e:
            messagebox.showerror("Abrir", f"No se pudo abrir la imagen:\n{e}")

    def _clear_grid():
        if not (_widget_exists(inner) and _widget_exists(canvas)):
            return
        for w in inner.winfo_children():
            try: w.destroy()
            except Exception: pass
        thumb_refs.clear()
        grid_state["count"] = 0
        try:
            canvas.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))
        except Exception:
            pass

    def _on_resize_content(_e=None):
        if not _widget_exists(canvas): return
        try:
            canvas.itemconfig(win_item, width=canvas.winfo_width())
            canvas.configure(scrollregion=canvas.bbox("all"))
        except Exception:
            pass

    inner.bind("<Configure>", _on_resize_content)
    win.bind("<Configure>", _on_resize_content)

    def _parse_date(s: str) -> date | None:
        s = (s or "").strip()
        if not s:
            return None
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except Exception:
            messagebox.showwarning("Fecha", f"Formato inválido: {s}\nUsa YYYY-MM-DD (ej. 2025-09-07).")
            return None

    def _producer(files: list[str]):
        from PIL import Image, ImageOps
        try:
            for p in files:
                if stop_flag["stop"]:
                    break
                try:
                    im = Image.open(p)
                    try: im = ImageOps.exif_transpose(im)
                    except Exception: pass
                    im.draft("RGB", (640, 480))
                    im = im.convert("RGB")
                    th = ImageOps.fit(im, (240, 180), Image.LANCZOS)
                    q.put((p, th), timeout=1)
                except Exception:
                    continue
        finally:
            try: q.put(None, timeout=1)
            except Exception: pass

    def _drain_queue(show_n: int, total_all: int, showing_all: bool):
        if stop_flag["stop"] or not (_widget_exists(win) and _widget_exists(inner) and _widget_exists(canvas)):
            return
        added = 0
        while added < BATCH_UI:
            try:
                item = q.get_nowait()
            except Exception:
                item = "empty"
            if item == "empty":
                break
            if item is None:
                msg = (f"Listo. Mostrando {total_all} imagen(es)." if showing_all
                       else f"Listo. Mostrando últimas {show_n} de {total_all}.")
                status_lbl.config(text=msg)
                return
            p, pil_thumb = item
            try:
                tkimg = ImageTk.PhotoImage(pil_thumb)
            except Exception:
                continue

            card = tk.Frame(inner, bg=BG_COLOR, bd=0, highlightthickness=1, highlightbackground="#333")
            lbl = tk.Label(card, image=tkimg, bg=BG_COLOR)
            lbl.image = tkimg
            thumb_refs.append(tkimg)
            lbl.pack()

            fname = os.path.basename(p)
            tk.Label(card, text=fname, bg=BG_COLOR, fg=FG_COLOR, wraplength=240
                     ).pack(fill="x", padx=6, pady=4)
            tk.Button(card, text="Open", command=lambda p=p: _open_file(p),
                      bg=BTN_COLOR, fg=BTN_TEXT_COLOR, bd=0,
                      font=("Arial", 10, "bold"), padx=8, pady=4
                     ).pack(pady=(0, 8))

            i = grid_state["count"]; r, c = divmod(i, COLS)
            card.grid(row=r, column=c, padx=8, pady=8, sticky="n")
            grid_state["count"] += 1
            added += 1
            prog["done"] += 1

        # continuar drenando sin bloquear
        if _widget_exists(win):
            try:
                status_lbl.config(text=f"Cargando miniaturas… {prog['done']}/{prog['total']}")
            except Exception:
                pass
            win.after(20, lambda: _drain_queue(show_n, total_all, showing_all))

    def _load_async(limit: int | None):
        # reinicio/limpieza
        stop_flag["stop"] = True
        t = worker.get("t")
        if t and t.is_alive():
            try: t.join(timeout=0.4)
            except Exception: pass
        stop_flag["stop"] = False
        while not q.empty():
            try: q.get_nowait()
            except Exception: break
        _clear_grid()

        # listar archivos
        exts = (".jpg", ".jpeg", ".png")
        try:
            files_all = [os.path.join(state.photo_dir, f)
                         for f in os.listdir(state.photo_dir)
                         if f.lower().endswith(exts)]
        except Exception as e:
            status_lbl.config(text=f"Error leyendo carpeta: {e}")
            return

        total_all = len(files_all)
        if total_all == 0:
            status_lbl.config(text="No hay imágenes en esta carpeta.")
            if _widget_exists(inner):
                tk.Label(inner, text="No hay imágenes en esta carpeta.", bg=BG_COLOR, fg=FG_COLOR,
                         font=("Arial", 12)).pack(pady=20)
                try:
                    canvas.configure(scrollregion=canvas.bbox("all"))
                except Exception:
                    pass
            return

        files_all.sort(key=lambda p: os.path.getmtime(p), reverse=True)

        # Filtro fechas
        df = _parse_date(from_var.get())
        dt = _parse_date(to_var.get())
        if df or dt:
            _filtered = []
            for p in files_all:
                try:
                    d = datetime.fromtimestamp(os.path.getmtime(p)).date()
                except Exception:
                    continue
                if df and d < df:   continue
                if dt and d > dt:   continue
                _filtered.append(p)
            files_all = _filtered
            total_all = len(files_all)

        if total_all == 0:
            status_lbl.config(text="Sin resultados para el filtro.")
            if _widget_exists(inner):
                tk.Label(inner, text="Sin resultados para el filtro.", bg=BG_COLOR, fg=FG_COLOR,
                         font=("Arial", 12)).pack(pady=20)
            return

        if limit is None:
            files = files_all
            showing_all = True
            show_n = len(files_all)
        else:
            files = files_all[:max(1, int(limit))]
            showing_all = False
            show_n = len(files)

        prog["done"] = 0
        prog["total"] = show_n
        status_lbl.config(text=f"Cargando miniaturas… 0/{prog['total']}")

        worker["t"] = threading.Thread(target=_producer, args=(files,), daemon=True)
        worker["t"].start()
        win.after(10, lambda: _drain_queue(show_n, total_all, showing_all))

    # Interceptar cierre del sistema de ventanas
    win.protocol("WM_DELETE_WINDOW", _close_now)

    # Carga por defecto: últimas 20
    _load_async(limit=20)

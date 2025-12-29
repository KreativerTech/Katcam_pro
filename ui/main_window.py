# -*- coding: utf-8 -*-
import os
import sys
import subprocess
import threading
import time
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import messagebox, filedialog as fd

from PIL import Image, ImageOps, ImageTk, ImageFilter
try:
    import tzlocal
except Exception:
    tzlocal = None

# Config y utilidades
from config.settings import (
    MIN_APP_W, MIN_APP_H, IMG_MIN_W, IMG_MIN_H,
    BG_COLOR, FG_COLOR, BTN_COLOR, BTN_TEXT_COLOR, BTN_BORDER_COLOR,
    DEFAULT_RES_LABEL, COMPANY_LOGO_PATH, HEADER_IMAGE_PATH, _asset,
    get_font, FONT_SMALL, FONT_NORMAL, FONT_MEDIUM, FONT_LARGE, SHADOW_COLOR, SHADOW_OFFSET_X, SHADOW_OFFSET_Y
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
        bd=0, relief="flat", font=get_font(FONT_NORMAL, "bold"), padx=6, pady=6
    )
    btn.pack()
    return wrapper, btn


def create_shadowed_text(canvas, x, y, text, fill=BTN_TEXT_COLOR, font=None, anchor="se"):
    """Crear texto simple sin sombra (funcionalidad removida)"""
    if font is None:
        font = get_font(FONT_LARGE, "bold")
    
    # Crear solo el texto principal (sin sombra)
    text_id = canvas.create_text(
        x, y, text=text, fill=fill, font=font, anchor=anchor
    )
    
    return text_id, None


def create_id_box(canvas, x, y, text, fill=BTN_TEXT_COLOR, font=None):
    """Crear recuadro con sombra sutil para el ID de cámara"""
    if font is None:
        font = get_font(FONT_LARGE, "bold")
    
    # Crear texto temporal para medir dimensiones
    temp_text = canvas.create_text(0, 0, text=text, fill=fill, font=font)
    bbox = canvas.bbox(temp_text)
    canvas.delete(temp_text)
    
    if bbox:
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # Dimensiones del recuadro con padding
        padding = 8
        box_width = text_width + (padding * 2)
        box_height = text_height + (padding * 2)
        
        # Coordenadas del recuadro (anclado en la esquina inferior izquierda)
        box_x1 = x - padding
        box_y1 = y - text_height - padding
        box_x2 = x + text_width + padding
        box_y2 = y + padding
        
        # Crear solo el recuadro principal - solo borde, sin fondo ni sombra
        box_id = canvas.create_rectangle(
            box_x1, box_y1, box_x2, box_y2,
            fill="", outline=BTN_COLOR, width=2
        )
        
        # Crear texto
        text_id = canvas.create_text(
            x + text_width//2, y - text_height//2,
            text=text, fill=fill, font=font, anchor="center"
        )
        
        return text_id, box_id, None
    
    return None, None, None


def add_shadow_to_icon(icon_image, shadow_offset=2):
    """Añadir sombra sutil a una imagen de icono"""
    if icon_image is None:
        return None
    
    try:
        # Convertir a RGBA si no lo es
        if icon_image.mode != 'RGBA':
            icon_image = icon_image.convert('RGBA')
        
        # Crear una imagen más grande para acomodar la sombra
        shadow_size = shadow_offset * 2
        new_width = icon_image.width + shadow_size
        new_height = icon_image.height + shadow_size
        
        # Crear imagen base transparente
        result = Image.new('RGBA', (new_width, new_height), (0, 0, 0, 0))
        
        # Crear sombra: versión negra y difuminada del icono
        shadow = Image.new('RGBA', icon_image.size, (0, 0, 0, 0))
        shadow.paste((0, 0, 0, 128), (0, 0), icon_image)  # Sombra semi-transparente
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=1))
        
        # Pegar la sombra con offset
        result.paste(shadow, (shadow_offset, shadow_offset), shadow)
        
        # Pegar el icono original encima
        result.paste(icon_image, (0, 0), icon_image)
        
        return result
    except Exception:
        # Si falla, devolver el icono original
        return icon_image


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


def _maybe_downgrade_resolution(state, requested_label: str):
    """
    Si el contador de mismatches para requested_label superó el umbral,
    degradar la resolución a la siguiente disponible más baja y persistirlo.
    """
    try:
        from config import settings as _cfg
        RES = getattr(_cfg, "RESOLUTIONS", [])
    except Exception:
        RES = []
    try:
        labels = [lbl for (lbl, w, h) in RES]
        if requested_label not in labels:
            return
        idx = labels.index(requested_label)
        # buscar siguiente más baja (índice incrementado). Si no hay, salir.
        if idx + 1 >= len(labels):
            return
        new_label = labels[idx + 1]
        old_label = requested_label
        # No forzamos el cambio en la configuración del usuario.
        # Solo reseteamos el contador y avisamos por telemetría/UI para que el usuario cambie manualmente si lo desea.
        # resetear contador
        try:
            state.res_mismatch_counters.pop(requested_label, None)
        except Exception:
            pass
        # telemetría y UI
        try:
            from infra.telemetry import log_event
            log_event("resolution_suggest_downgrade", from_label=old_label, suggested_label=new_label)
        except Exception:
            pass
        try:
            set_status(state)(f"Advertencia: {old_label} parece no ser soportada por la cámara. Se sugiere usar {new_label} desde Configuración.")
        except Exception:
            pass
    except Exception:
        pass


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
        self._id_box = None
        self._clock_text = None
        self._clock_shadow = None
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
            self._clock_text, _ = create_shadowed_text(
                self._canvas, w - self._right_pad, h - self._bottom_pad,
                clock_label, BTN_TEXT_COLOR, get_font(FONT_LARGE, "bold"), "se"
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
            self._id_text, self._id_box, _ = create_id_box(
                self._canvas, self._left_pad, h - self._bottom_pad,
                left_label, BTN_TEXT_COLOR, get_font(FONT_LARGE, "bold")
            )
        else:
            self._canvas.itemconfig(self._id_text, text=left_label)

        if self._clock_text is None:
            self._clock_text = self._canvas.create_text(
                w - self._right_pad, h - self._bottom_pad,
                text="--:--:--", fill=BTN_TEXT_COLOR, font=get_font(FONT_LARGE, "bold"), anchor="se"
            )

        self._position_text()

    def _position_text(self):
        w = max(1, self.winfo_width()); h = self._target_h
        if self._id_text is not None:
            # Recalcular posición del recuadro del ID
            self._canvas.delete(self._id_text)
            if self._id_box:
                self._canvas.delete(self._id_box)
            # No hay sombra que eliminar ahora
            
            left_label = f"ID: {self._camera_name_getter()}"
            self._id_text, self._id_box, _ = create_id_box(
                self._canvas, self._left_pad, h - self._bottom_pad,
                left_label, BTN_TEXT_COLOR, get_font(FONT_LARGE, "bold")
            )
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
        # Contadores para mismatches por etiqueta (para downgrade automático)
        self.res_mismatch_counters = {}

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
        # Control de timelapse / capturas
        self.last_timelapse_capture_ts = 0.0
        self.last_effective_resolution = None  # (w,h) de última captura
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
        # Telemetría / watchdog
        self.last_frame_ts = 0
        self.frame_counter = 0
        self.maniobra_capture_in_progress = False
        self.maniobra_cancelled_flag = False
        self.maniobra_was_streaming = False
        # Cola de capturas pendientes para evitar colapsos
        self.capture_queue = []  # elementos: dict(tipo="manual"|"timelapse"|"maniobra", params={})
        self.max_capture_queue = 3  # límite para no crecer indefinidamente
        # Acciones diferidas (stream_on / stream_off) mientras hay captura en curso
        self.deferred_actions = []  # lista de strings: 'stream_on' | 'stream_off'
        self.max_deferred_actions = 5
        # Resoluciones soportadas detectadas (labels). Se llena vía probe.
        self.supported_resolution_labels = []

    def coalesce_stream_action(self, action: str):
        """Mantiene solo la última intención de stream (on/off) si estamos capturando."""
        if action not in ("stream_on", "stream_off"):
            return
        # Filtra previas acciones de stream
        self.deferred_actions = [a for a in self.deferred_actions if a not in ("stream_on", "stream_off")]
        self.deferred_actions.append(action)



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
            # Aplicar inmediatamente si el stream está activo
            try:
                wh = _find_res(new_label)
                if wh and hasattr(camera_manager, "set_resolution"):
                    camera_manager.set_resolution(*wh)
            except Exception:
                pass
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

    # -------- Mini toolbar en el header: iconos menú / config / galería --------
    toolbar = tk.Frame(header, bg=BTN_COLOR)

    # Helper para iconos del header (tamaños 20–40 px según altura)
    def _toolbar_icon(name: str):
        def _strip_white_bg(img):
            try:
                img = img.convert("RGBA")
                datas = img.getdata()
                new_data = []
                for (r, g, b, a) in datas:
                    if a == 0:
                        new_data.append((r, g, b, a))
                    elif r >= 246 and g >= 246 and b >= 246:
                        # Hacer blanco/near-blanco transparente
                        new_data.append((255, 255, 255, 0))
                    else:
                        new_data.append((r, g, b, a))
                img.putdata(new_data)
            except Exception:
                pass
            return img
        # Elegir tamaño deseado según altura, luego buscar el más cercano disponible
        try:
            h = root.winfo_height()
        except Exception:
            h = 600
        if h >= 1000:
            desired = 60
        elif h >= 850:
            desired = 48
        elif h >= 700:
            desired = 40
        elif h >= 600:
            desired = 30
        elif h >= 500:
            desired = 24
        else:
            desired = 20

        available = [20, 24, 30, 40, 48, 60]
        # Ordenar por cercanía al deseado
        candidates = sorted(available, key=lambda s: (abs(s - desired), s))
        for sz in candidates:
            path = _asset(f"{name}{sz}.png")
            try:
                img = Image.open(path).convert("RGBA")
                # Si el PNG viene con fondo blanco, intentamos removerlo
                if name in ("menu", "conf", "gal"):
                    img = _strip_white_bg(img)
                
                # No aplicar sombra a iconos de toolbar
                return ImageTk.PhotoImage(img)
            except Exception:
                continue
        return None

    menu_icon = _toolbar_icon("menu")
    conf_icon = _toolbar_icon("conf")
    gal_icon  = _toolbar_icon("gal")

    # Menú (con icono; fallback a texto si falta)
    menu_btn = tk.Button(
        toolbar,
        image=menu_icon if menu_icon else None,
        text="☰" if not menu_icon else "",
        bg=BTN_COLOR, fg=BTN_TEXT_COLOR,
        bd=0, relief="flat",
        font=get_font(15, "bold") if not menu_icon else None,
        padx=10, pady=4, cursor="hand2",
        compound="center"
    )
    # Evitar GC del icono
    menu_btn.image = menu_icon
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
    dd_menu.add_separator()
    dd_menu.add_command(label="Apagar sistema", command=lambda: _apagar_sistema(state))
    dd_menu.add_command(label="Reiniciar sistema", command=lambda: _reiniciar_sistema(state))

    def _show_menu(_evt=None):
        dd_menu.update_idletasks()
        x = menu_btn.winfo_rootx()
        y = menu_btn.winfo_rooty() + menu_btn.winfo_height()
        dd_menu.post(x, y)
    menu_btn.configure(command=_show_menu)

    # Configuración
    gear_btn = tk.Button(
        toolbar,
        command=open_config,
        image=conf_icon if conf_icon else None,
        text="⚙" if not conf_icon else "",
        bg=BTN_COLOR, fg=BTN_TEXT_COLOR,
        bd=0, relief="flat",
        font=("Arial", 14, "bold") if not conf_icon else None,
        padx=10, pady=4, cursor="hand2",
        compound="center"
    )
    gear_btn.image = conf_icon
    gear_btn.pack(side="left", padx=(0, 6))

    # Galería (o carpeta)
    folder_btn = tk.Button(
        toolbar,
        command=_open_gallery_or_folder,
        image=gal_icon if gal_icon else None,
        text="📁" if not gal_icon else "",
        bg=BTN_COLOR, fg=BTN_TEXT_COLOR,
        bd=0, relief="flat",
        font=("Arial", 14, "bold") if not gal_icon else None,
        padx=10, pady=4, cursor="hand2",
        compound="center"
    )
    folder_btn.image = gal_icon
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
        path = _asset(f"{name}{size}px.png")
        try:
            img = Image.open(path).convert("RGBA")
            # No aplicar sombra a iconos de botones
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    live_icon = _get_icon("live")
    cam_icon = _get_icon("cam")
    tl_icon = _get_icon("tl")
    short_icon = _get_icon("s")

    # Botón Timelapse solo icono
    state.btn_switch_timelapse = tk.Button(
        buttons_wrap,
        command=lambda: toggle_timelapse(state),
        image=tl_icon if tl_icon else None,
        bd=0, relief="flat", bg=BTN_COLOR, activebackground=BTN_COLOR,
        width=tl_icon.width() if tl_icon else 48,
        height=tl_icon.height() if tl_icon else 48,
        highlightthickness=0, cursor="hand2"
    )
    state.btn_switch_timelapse.image = tl_icon
    state.btn_switch_timelapse.grid(row=0, column=0, **gridpad)

    # Botón Short TL solo icono
    state.btn_maniobra = tk.Button(
        buttons_wrap,
        command=lambda: toggle_maniobra(state),
        image=short_icon if short_icon else None,
        bd=0, relief="flat", bg=BTN_COLOR, activebackground=BTN_COLOR,
        width=short_icon.width() if short_icon else 48,
        height=short_icon.height() if short_icon else 48,
        highlightthickness=0, cursor="hand2"
    )
    state.btn_maniobra.image = short_icon
    state.btn_maniobra.grid(row=0, column=1, **gridpad)

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

    state.lbl_status_transmision = tk.Label(status_box, text="Live: STOPPED", bg="black", fg="#a6ffa6", font=get_font(FONT_NORMAL, "bold"))
    state.lbl_status_transmision.pack(anchor="w", padx=10, pady=2)
    state.lbl_status_timelapse = tk.Label(status_box, text="Timelapse: STOPPED", bg="black", fg="#a6ffa6", font=get_font(FONT_NORMAL, "bold"))
    state.lbl_status_timelapse.pack(anchor="w", padx=10, pady=2)
    state.lbl_status_maniobra = tk.Label(status_box, text="Short: INACTIVE", bg="black", fg="#a6ffa6", font=get_font(FONT_NORMAL, "bold"))
    state.lbl_status_maniobra.pack(anchor="w", padx=10, pady=2)
    state.lbl_status_general = tk.Label(status_box, text="Ready", bg="black", fg="#e0e0e0", font=get_font(FONT_SMALL))
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
            # Aplicar sombra solo al logo del footer
            img = add_shadow_to_icon(img)
            company_logo_img = ImageTk.PhotoImage(img)
        except Exception as e:
            print(f"[FOOTER LOGO] Error: {e}")
            return
        if lbl_company is None:
            lbl_company = tk.Label(center, bg=BTN_COLOR)
            lbl_company.pack(side="left", padx=12)
        lbl_company.config(image=company_logo_img)
        lbl_company.image = company_logo_img

        # Triple click en el logo de Kreativer -> solicitar cierre de la app
        try:
            lbl_company.bind(
                "<Triple-Button-1>",
                lambda _e: root.event_generate("<<KATCAM_CLOSE_REQUEST>>"),
                add="+",
            )
        except Exception:
            pass

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

        # Vista realmente estrecha: apilar en vertical solo si el ancho es menor a 600px
        if w < 600:
            buttons_wrap.pack(side="top", pady=(0, 6))
            status_box.pack(side="top", pady=(0, 6))
            if lbl_company is not None:
                lbl_company.pack(side="top", pady=(0, 6))
        else:
            # Vista en línea para 600px o más (incluye 800x600)
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

    # Solo actualizar el layout del footer si el tamaño de la ventana realmente cambió
    _last_size = [root.winfo_width(), root.winfo_height()]
    def _on_resize(evt=None):
        w, h = root.winfo_width(), root.winfo_height()
        if [w, h] != _last_size:
            _last_size[0], _last_size[1] = w, h
            _layout_footer()
    root.bind("<Configure>", _on_resize)

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

    # Permite disparar el cierre desde otros widgets (ej: triple click logo)
    try:
        root.bind("<<KATCAM_CLOSE_REQUEST>>", lambda _e: on_close(), add="+")
    except Exception:
        pass

    # Cierre solo con Shift+Q (bloquear cierre normal)
    root.protocol("WM_DELETE_WINDOW", lambda: None)
    root.bind_all('<Alt-F4>', lambda e: 'break')
    root.bind_all('<Shift-q>', lambda _e: on_close())
    root.bind_all('<Shift-Q>', lambda _e: on_close())

    # Reanudar estados previos (stream / timelapse)
    try:
        if state.cfg.data.get("stream_activo"):
            root.after(300, lambda: stream_on(state))
        if state.cfg.data.get("timelapse_activo"):
            root.after(800, lambda: toggle_timelapse(state) if not state.timelapse_running else None)
        try:
            from infra.telemetry import log_event
            log_event("resume_from_config", stream=state.cfg.data.get("stream_activo"),
                      timelapse=state.cfg.data.get("timelapse_activo"))
        except Exception:
            pass
    except Exception:
        pass

    # (watchdog principal redefinido más adelante con periodo de gracia)

    # Snapshot periódico del estado
    def _snapshot():
        try:
            from infra.telemetry import dump_state
            dump_state(state)
        except Exception:
            pass
        finally:
            root.after(60000, _snapshot)
    root.after(60000, _snapshot)

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


def _apagar_sistema(state: AppState):
    """Apaga el sistema completo (Windows/Linux/macOS) desde el menú."""
    try:
        state.cfg.set(
            stream_activo=state.streaming,
            timelapse_activo=state.timelapse_running,
            photo_resolution_label=state.photo_resolution_label,
            video_resolution_label=state.video_resolution_label,
            cam_index=state.cam_index
        )
    except Exception:
        pass

    try:
        camera_manager.stop_stream()
        camera_manager.shutdown()
    except Exception:
        pass

    try:
        if sys.platform == "win32":
            subprocess.Popen(["shutdown", "/s", "/t", "0"], shell=False)
        elif sys.platform == "darwin":
            subprocess.Popen(["osascript", "-e", 'tell app "System Events" to shut down'])
        else:
            subprocess.Popen(["shutdown", "-h", "now"], shell=False)
    except Exception as e:
        messagebox.showerror("Apagar sistema", f"No se pudo apagar el sistema:\n{e}")
        return

    try:
        state.root.destroy()
    except Exception:
        pass


def _reiniciar_sistema(state: AppState):
    """Reinicia el sistema completo (Windows/Linux/macOS) desde el menú."""
    try:
        state.cfg.set(
            stream_activo=state.streaming,
            timelapse_activo=state.timelapse_running,
            photo_resolution_label=state.photo_resolution_label,
            video_resolution_label=state.video_resolution_label,
            cam_index=state.cam_index
        )
    except Exception:
        pass

    try:
        camera_manager.stop_stream()
        camera_manager.shutdown()
    except Exception:
        pass

    try:
        if sys.platform == "win32":
            subprocess.Popen(["shutdown", "/r", "/t", "0"], shell=False)
        elif sys.platform == "darwin":
            subprocess.Popen(["osascript", "-e", 'tell app "System Events" to restart'])
        else:
            subprocess.Popen(["shutdown", "-r", "now"], shell=False)
    except Exception as e:
        messagebox.showerror("Reiniciar sistema", f"No se pudo reiniciar el sistema:\n{e}")
        return

    try:
        state.root.destroy()
    except Exception:
        pass


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


def _process_deferred_actions(state: AppState):
    if not state.deferred_actions:
        return
    # Tomar última intención de stream
    final_action = None
    for act in state.deferred_actions:
        if act in ("stream_on", "stream_off"):
            final_action = act
    state.deferred_actions.clear()
    if final_action == "stream_on" and not state.streaming:
        stream_on(state)
    elif final_action == "stream_off" and state.streaming:
        stream_off(state)


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
            # PNG con posible transparencia - aplicar sombra
            img = Image.open(COMPANY_LOGO_PATH).convert("RGBA")
            img = add_shadow_to_icon(img)
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
    # Si hay una captura en curso, diferir encendido (mantenemos cola de intención)
    if state.is_capturing or state.maniobra_capture_in_progress:
        state.coalesce_stream_action("stream_on")
        set_status(state)("Live se encenderá al terminar la captura...")
        return
    if state.streaming:
        return

    # Confirmar si hay procesos activos que vamos a detener
    conflicts = []
    if state.timelapse_running:
        conflicts.append("timelapse")
    if state.maniobra_running:
        conflicts.append("maniobra")
    if conflicts:
        try:
            resp = messagebox.askyesno(
                "Iniciar Live",
                "Para iniciar Live se detendrá: " + ", ".join(conflicts) + "\n¿Continuar?"
            )
        except Exception:
            resp = True
        if not resp:
            set_status(state)("Live cancelado por el usuario.")
            return
        # Detener lo que corresponda
        if state.timelapse_running:
            toggle_timelapse(state)
        if state.maniobra_running:
            toggle_maniobra(state)
    state.streaming = True
    try:
        state.cfg.set(stream_activo=True)
    except Exception:
        pass
    try:
        state.last_frame_ts = time.time()
        state.frame_counter = 0
    except Exception:
        pass

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
    try:
        from infra.telemetry import log_event
        log_event("stream_on", resolution=label)
    except Exception:
        pass
    _tick_stream(state)


def stream_off(state: AppState):
    if state.is_capturing:
        state.coalesce_stream_action("stream_off")
        set_status(state)("Acción 'detener live' diferida (captura en curso)...")
        return
    if not state.streaming:
        return
    state.streaming = False
    try:
        state.cfg.set(stream_activo=False)
    except Exception:
        pass
    try:
        camera_manager.stop_stream()
    except Exception:
        pass
    update_stream_ui(state)
    set_status(state)("Transmisión detenida")
    update_main_image(state)
    try:
        from infra.telemetry import log_event
        log_event("stream_off")
    except Exception:
        pass


def _tick_stream(state: AppState):
    if not state.streaming: return
    try:
        frame_rgb = camera_manager.get_frame_rgb()
        if frame_rgb is not None and state.image_panel:
            img = Image.fromarray(frame_rgb); state.image_panel.set_image(img)
            try:
                state.last_frame_ts = time.time()
                state.frame_counter += 1
                if state.frame_counter % 120 == 0:
                    try:
                        from infra.telemetry import log_event
                        log_event("stream_heartbeat", frames=state.frame_counter)
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception as e:
        try:
            from infra.telemetry import log_error
            log_error(e, {"phase": "stream_read"})
        except Exception:
            pass
    if state.streaming:
        state.root.after(40, lambda: _tick_stream(state))  # ~25fps


def toggle_transmision(state: AppState):
    # Live puede coexistir con timelapse/maniobra sólo si usuario lo confirma (se detienen primero).
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
        # Encolar si hay espacio
        if len(state.capture_queue) < state.max_capture_queue:
            state.capture_queue.append({"tipo": "manual"})
            set_status(state)(f"Captura en cola ({len(state.capture_queue)})...")
            try:
                from infra.telemetry import log_event
                log_event("capture_queued", kind="manual", queue_len=len(state.capture_queue))
            except Exception:
                pass
        else:
            set_status(state)("Cola de capturas llena, ignorada.")
        return

    state.is_capturing = True
    set_status(state)("Preparando captura...")

    def _work():
        try:
            try:
                from infra.telemetry import log_event
                log_event("manual_photo_start")
            except Exception:
                pass
            label = state.photo_resolution_label or state.current_resolution_label or DEFAULT_RES_LABEL
            wh = _find_res(label)
            prefer = [wh] if wh else None

            # Pasamos un result_holder para obtener resolución efectiva y estado
            result_holder = {}
            try:
                from infra.telemetry import log_event
                log_event("capture_requested", kind="manual", requested_label=label, prefer=prefer)
            except Exception:
                pass
            try:
                ok = take_photo(
                    dest_folder=state.photo_dir,
                    prefer_sizes=prefer,
                    jpeg_quality=95,
                    auto_resume_stream=True,
                    block_until_done=True,
                    result_holder=result_holder
                )
            except Exception as e:
                try:
                    from infra.telemetry import log_error
                    log_error(e, {"phase": "take_photo_call_manual"})
                except Exception:
                    pass
                ok = False
            # Si la llamada bloqueante devolvió True intentamos leer result_holder (si el manager lo rellenó)
            eff_label = None
            try:
                if ok and isinstance(result_holder, dict) and result_holder.get("eff_w"):
                    w = result_holder.get("eff_w")
                    h = result_holder.get("eff_h")
                    eff_label = f"{w}x{h}"
            except Exception:
                eff_label = None
            if ok and not result_holder.get("timeout") and not result_holder.get("cancelled"):
                msg = "Foto tomada."
                try:
                    from infra.telemetry import log_event
                    log_event("manual_photo_ok", resolution=eff_label or label)
                except Exception:
                    pass
            else:
                msg = "Foto cancelada/timeout/error."
            # Si hubo mismatch, considerar downgrade automático
            try:
                from config import settings as _cfg
                thresh = getattr(_cfg, "RES_MISMATCH_DOWNGRADE_THRESHOLD", 2)
            except Exception:
                thresh = 2
            try:
                if isinstance(result_holder, dict) and result_holder.get("mismatch"):
                    cnt = state.res_mismatch_counters.get(label, 0) + 1
                    state.res_mismatch_counters[label] = cnt
                    if cnt >= thresh:
                        _maybe_downgrade_resolution(state, label)
                else:
                    # éxito o no-mismatch -> reset counter
                    if label in state.res_mismatch_counters:
                        state.res_mismatch_counters.pop(label, None)
            except Exception:
                pass
        except Exception as e:
            msg = f"Error: {e}"
            try:
                from infra.telemetry import log_error
                log_error(e, {"phase": "manual_photo"})
            except Exception:
                pass
        finally:
            def _finish():
                set_status(state)(msg)
                update_main_image(state)
                state.is_capturing = False
                # Procesar siguiente en cola si existe
                if state.capture_queue:
                    nxt = state.capture_queue.pop(0)
                    try:
                        from infra.telemetry import log_event
                        log_event("capture_dequeued", kind=nxt.get("tipo"))
                    except Exception:
                        pass
                    # Por ahora sólo manual soportado
                    take_and_update(state)
                _process_deferred_actions(state)
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
            # frecuencia en minutos -> ms
            requested_ms = int(float(freq_min) * 60_000)
        except Exception:
            requested_ms = 10 * 60_000

        # Aplicar floor mínimo en segundos definido en settings
        try:
            from config.settings import TIME_LAPSE_MIN_INTERVAL_S
        except Exception:
            TIME_LAPSE_MIN_INTERVAL_S = 5
        min_ms = int(TIME_LAPSE_MIN_INTERVAL_S * 1000)
        applied_ms = requested_ms
        adjusted = False
        if requested_ms < min_ms:
            applied_ms = min_ms
            adjusted = True
        state.interval_ms = applied_ms

        dias_cfg = state.cfg.data.get("dias", [True]*7)
        dias_lista = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
        state.days_selected = [d for d, ok in zip(dias_lista, dias_cfg) if ok]

        state.hour_start = state.cfg.data.get("hora_inicio", "08:00")
        state.hour_end   = state.cfg.data.get("hora_fin", "18:00")

        state.timelapse_running = True
        set_status(state)("Timelapse: activado. Esperando próxima foto...")
        update_timelapse_ui(state)
        try:
            state.cfg.set(timelapse_activo=True)
            from infra.telemetry import log_event
            if adjusted:
                log_event("timelapse_on", interval_ms=state.interval_ms, requested_ms=requested_ms, adjusted=True)
            else:
                log_event("timelapse_on", interval_ms=state.interval_ms, requested_ms=requested_ms, adjusted=False)
        except Exception:
            pass
        _schedule_timelapse_tick(state)
    else:
        state.timelapse_running = False
        set_status(state)("Timelapse detenido.")
        update_timelapse_ui(state)
        try:
            state.cfg.set(timelapse_activo=False)
            from infra.telemetry import log_event
            log_event("timelapse_off")
        except Exception:
            pass


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

    # Throttle defensivo: si la última captura terminó hace muy poco, esperar.
    try:
        import time as _time
        last = getattr(state, "last_timelapse_capture_ts", 0.0) or 0.0
        since_last = _time.time() - last
        # mínimo entre 0.8s y la mitad del intervalo configurado
        min_gap = max(0.8, (state.interval_ms / 1000.0) * 0.5)
        if last > 0 and since_last < min_gap:
            try:
                from infra.telemetry import log_event
                log_event("timelapse_throttled", since_last_s=round(since_last, 3), min_gap_s=min_gap)
            except Exception:
                pass
            set_status(state)("Timelapse: esperando estabilizar antes de siguiente captura...")
            return _schedule_timelapse_tick(state)
    except Exception:
        pass

    # --- Captura del timelapse --- (no apagamos manualmente el stream: CameraManager se encarga)
    if state.is_capturing:
        # Cola timelapse si hay otra captura en progreso
        if len(state.capture_queue) < state.max_capture_queue:
            state.capture_queue.append({"tipo": "timelapse"})
            set_status(state)(f"Timelapse: captura en cola ({len(state.capture_queue)})...")
            try:
                from infra.telemetry import log_event
                log_event("capture_queued", kind="timelapse", queue_len=len(state.capture_queue))
            except Exception:
                pass
        else:
            set_status(state)("Timelapse: cola llena, tick ignorado.")
        return _schedule_timelapse_tick(state)

    set_status(state)("Timelapse: capturando...")
    # Usar resolución de FOTO
    label = state.photo_resolution_label or state.current_resolution_label or DEFAULT_RES_LABEL
    wh = _find_res(label)
    prefer = [wh] if wh else None

    def _do_capture():
        try:
            # Marcar que hay una captura en curso para evitar solapamientos con otros ticks
            state.is_capturing = True
            try:
                from infra.telemetry import log_event
                log_event("timelapse_capture_start")
            except Exception:
                pass
            # solicitar resultado efectivo
            result_holder = {}
            try:
                from infra.telemetry import log_event
                log_event("capture_requested", kind="timelapse", requested_label=label, prefer=prefer)
            except Exception:
                pass
            try:
                ok = take_photo(
                    dest_folder=state.photo_dir,
                    prefer_sizes=prefer,
                    jpeg_quality=95,
                    auto_resume_stream=True,
                    block_until_done=True,
                    result_holder=result_holder
                )
            except Exception as e:
                try:
                    from infra.telemetry import log_error
                    log_error(e, {"phase": "take_photo_call_timelapse"})
                except Exception:
                    pass
                ok = False
            eff_label = None
            try:
                if ok and isinstance(result_holder, dict) and result_holder.get("eff_w"):
                    w = result_holder.get("eff_w")
                    h = result_holder.get("eff_h")
                    eff_label = f"{w}x{h}"
            except Exception:
                eff_label = None
            if ok and not result_holder.get("timeout") and not result_holder.get("cancelled"):
                msg = "Timelapse: foto tomada."
                try:
                    from infra.telemetry import log_event
                    log_event("timelapse_capture_ok", resolution=eff_label or label)
                except Exception:
                    pass
                else:
                    msg = "Timelapse: foto cancelada/timeout/error."
                # mismatch handling for timelapse
                try:
                    from config import settings as _cfg
                    thresh = getattr(_cfg, "RES_MISMATCH_DOWNGRADE_THRESHOLD", 2)
                except Exception:
                    thresh = 2
                try:
                    if isinstance(result_holder, dict) and result_holder.get("mismatch"):
                        cnt = state.res_mismatch_counters.get(label, 0) + 1
                        state.res_mismatch_counters[label] = cnt
                        if cnt >= thresh:
                            _maybe_downgrade_resolution(state, label)
                    else:
                        if label in state.res_mismatch_counters:
                            state.res_mismatch_counters.pop(label, None)
                except Exception:
                    pass
        except Exception as e:
            msg = f"Timelapse: error de captura: {e}"
            try:
                from infra.telemetry import log_error
                log_error(e, {"phase": "timelapse_capture"})
            except Exception:
                pass
        finally:
            def _finish():
                set_status(state)(msg)
                update_main_image(state)
                set_status(state)("Timelapse: esperando próxima captura...")
                # limpiar flag de captura y registrar timestamp para throttling
                try:
                    state.is_capturing = False
                    state.last_timelapse_capture_ts = time.time()
                except Exception:
                    pass
                _schedule_timelapse_tick(state)
                # Procesar cola si quedó algo (timelapse encadena) pero no saturar UI
                if state.capture_queue and not state.is_capturing:
                    nxt = state.capture_queue.pop(0)
                    try:
                        from infra.telemetry import log_event
                        log_event("capture_dequeued", kind=nxt.get("tipo"))
                    except Exception:
                        pass
                    if nxt.get("tipo") == "timelapse" and state.timelapse_running:
                        # Disparar inmediatamente siguiente sin esperar intervalo adicional
                        _timelapse_tick(state)
                _process_deferred_actions(state)
            state.root.after(0, _finish)

    threading.Thread(target=_do_capture, daemon=True).start()


# =========================
# Maniobra
# =========================
def toggle_maniobra(state: AppState):
    if not state.maniobra_running:
        state.maniobra_cancelled_flag = False
        state.maniobra_was_streaming = state.streaming
        try:
            from infra.telemetry import log_event
            log_event("maniobra_start")
        except Exception:
            pass
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
                # Evitar doble evento si fue cancelada
                if not state.maniobra_cancelled_flag:
                    set_status(state)("Maniobra finalizada.")
                    # Reanudar transmisión si la pausamos y originalmente estaba activa
                    _resume_stream_if_marked(state)
                    if state.maniobra_was_streaming and (not state.streaming):
                        # Si originalmente estaba en ON pero no marcamos reanudación, encender
                        stream_on(state)
                    # Reanudar timelapse si lo habíamos pausado por maniobra.
                    # Evitamos llamar a toggle_timelapse() para no disparar
                    # comprobaciones/diálogos adicionales ni posibles ramas
                    # que bloqueen la reanudación. Restauramos el estado
                    # directamente y programamos el siguiente tick.
                    if state.timelapse_paused_by_maniobra:
                        state.timelapse_paused_by_maniobra = False
                        try:
                            state.timelapse_running = True
                            update_timelapse_ui(state)
                            # Persistir estado en configuración si es posible
                            try:
                                state.cfg.set(timelapse_activo=True)
                            except Exception:
                                pass
                            # Asegurar que el timelapse se programe de nuevo
                            _schedule_timelapse_tick(state)
                            # Emitir telemetría indicando reanudación por maniobra
                            try:
                                from infra.telemetry import log_event
                                log_event("timelapse_resumed_by_maniobra", cancelled=False, ts=time.time())
                            except Exception:
                                pass
                        except Exception:
                            # Si algo falla, al menos limpiar el flag
                            state.timelapse_paused_by_maniobra = False
                    try:
                        from infra.telemetry import log_event
                        state.last_timelapse_capture_ts = time.time()
                        log_event("maniobra_end")
                    except Exception:
                        pass
                return
            # Evitar solapamientos de capturas
            if state.maniobra_capture_in_progress:
                state.root.after(100, _tick)
                return
            state.maniobra_capture_in_progress = True

            def _cap():
                try:
                    from video_capture import camera_manager as _cm
                    # Usar la resolución seleccionada por el usuario para evitar mismatches altos
                    label_req = state.photo_resolution_label or state.current_resolution_label or DEFAULT_RES_LABEL
                    wh = _find_res(label_req)
                    prefer = [wh] if wh else None
                    result_holder = {}
                    try:
                        from infra.telemetry import log_event
                        log_event("capture_requested", kind="maniobra", requested_label=label_req, prefer=prefer)
                    except Exception:
                        pass
                    # Marcar captura en curso para coordinar con otros flujos
                    state.is_capturing = True
                    try:
                        ok = _cm.take_photo(state.photo_dir, prefer_sizes=prefer, block_until_done=True, auto_resume_stream=True, result_holder=result_holder)
                    except Exception as e:
                        try:
                            from infra.telemetry import log_error
                            log_error(e, {"phase": "take_photo_call_maniobra"})
                        except Exception:
                            pass
                        ok = False
                    try:
                        from infra.telemetry import log_event
                        if ok and not result_holder.get("timeout") and not result_holder.get("cancelled"):
                            log_event("maniobra_capture")
                        else:
                            log_event("maniobra_capture_failed", timeout=bool(result_holder.get("timeout")), cancelled=bool(result_holder.get("cancelled")))
                    except Exception:
                        pass
                except Exception as e:
                    try:
                        from infra.telemetry import log_error
                        log_error(e, {"phase": "maniobra_capture"})
                    except Exception:
                        pass
                finally:
                    state.maniobra_capture_in_progress = False
                    state.is_capturing = False
                    update_main_image(state)
                    # Procesar cola si hubiera pendiente manual (priorizar manual antes de siguiente tick)
                    if state.capture_queue and not state.is_capturing:
                        nxt = state.capture_queue.pop(0)
                        try:
                            from infra.telemetry import log_event
                            log_event("capture_dequeued", kind=nxt.get("tipo"))
                        except Exception:
                            pass
                        if nxt.get("tipo") == "manual":
                            take_and_update(state)
                    _process_deferred_actions(state)
                    state.root.after(int(intervalo_s * 1000), _tick)

            threading.Thread(target=_cap, daemon=True).start()

        _tick()

    else:
        # Detener maniobra manualmente
        state.maniobra_running = False
        state.maniobra_cancelled_flag = True
        update_maniobra_ui(state)
        set_status(state)("Maniobra cancelada por el usuario.")
        # Solicitar cancel cooperativo a la cámara para abortar cualquier captura en curso
        try:
            from video_capture import camera_manager as _cm
            _cm.cancel_capture()
        except Exception:
            pass
        _resume_stream_if_marked(state)
        # Restaurar timelapse pausado por maniobra sin llamar a toggle_timelapse
        if state.timelapse_paused_by_maniobra:
            state.timelapse_paused_by_maniobra = False
            try:
                state.timelapse_running = True
                update_timelapse_ui(state)
                try:
                    state.cfg.set(timelapse_activo=True)
                except Exception:
                    pass
                _schedule_timelapse_tick(state)
                # Telemetría indicando cancelación y reanudación
                try:
                    from infra.telemetry import log_event
                    log_event("timelapse_resumed_by_maniobra", cancelled=True, ts=time.time())
                except Exception:
                    pass
            except Exception:
                state.timelapse_paused_by_maniobra = False
        try:
            from infra.telemetry import log_event
            log_event("maniobra_cancelled")
        except Exception:
            pass


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
    # Watchdog con periodo de gracia (no dispara en primeros 5s tras encender stream)
        def _watchdog():
            try:
                if getattr(state, 'streaming', False):
                    now_ts = time.time()
                    # Gracia: si frame_counter < 30 (~<1.2s) o stream recién encendió hace <5s (approx)
                    if state.frame_counter < 30:
                        pass
                    else:
                        if getattr(state, 'last_frame_ts', 0) and (now_ts - state.last_frame_ts) > 3.0:
                            try:
                                from infra.telemetry import log_event
                                log_event("stream_watchdog_trigger")
                            except Exception:
                                pass
                            try:
                                camera_manager.stop_stream()
                            except Exception:
                                pass
                            try:
                                camera_manager.start_stream()
                            except Exception as e:
                                try:
                                    from infra.telemetry import log_error
                                    log_error(e, {"phase": "watchdog_restart"})
                                except Exception:
                                    pass
                            else:
                                state.last_frame_ts = time.time()
                                try:
                                    from infra.telemetry import log_event
                                    log_event("stream_watchdog_recover")
                                except Exception:
                                    pass
            finally:
                state.root.after(2000, _watchdog)
        state.root.after(2000, _watchdog)

    # Filtros de galería (from/to fechas) – asegurar variables definidas
    tk.Label(ctrl, text="Desde:", bg=BG_COLOR, fg=FG_COLOR).pack(side="left", padx=(4,4))
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

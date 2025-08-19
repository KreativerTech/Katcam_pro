import tkinter as tk
from tkinter import messagebox
from tkinter import filedialog as fd
from PIL import Image, ImageTk, ImageOps
import os
from datetime import datetime, timedelta
import json
import shutil
import subprocess
import sys
import cv2
from tkinter import ttk

import threading
import time
import tzlocal  # pip install tzlocal
from typing import Optional, Tuple

# --- Tamaño recomendado / mínimos ---
MIN_APP_W, MIN_APP_H = 1000, 700
IMG_MIN_W, IMG_MIN_H = 900, 600       # área de imagen "objetivo"
RESIZE_DEBOUNCE_MS = 120              # para suavizar el re-render en resize

# Si pones True, envuelve el layout en un contenedor con scroll (útil en pantallas pequeñas).
USE_SCROLL_CONTAINER = False

# info del sistema (opcionales; el código maneja su ausencia)
def _read_cpu_temp_c():
    try:
        import psutil
        temps = psutil.sensors_temperatures()
        if temps:
            for entries in temps.values():
                if entries:
                    cur = entries[0].current
                    if cur is not None:
                        return float(cur)
    except Exception:
        pass
    return None

def _read_cpu_percent():
    try:
        import psutil
        return psutil.cpu_percent(interval=None)
    except Exception:
        return None

def _read_mem_percent():
    try:
        import psutil
        return psutil.virtual_memory().percent
    except Exception:
        return None

def _read_free_space_bytes(path):
    try:
        usage = shutil.disk_usage(path)
        return usage.free
    except Exception:
        return None

from video_capture import camera_manager
from camera import take_photo

CONFIG_FILE = "katcam_config.json"
CAM_INDEX = 0

# Colores corporativos
BG_COLOR = "#181818"
FG_COLOR = "#FFFFFF"
BTN_COLOR = "#FFD600"
BTN_TEXT_COLOR = "#181818"
BTN_BORDER_COLOR = "#FFD600"

# Estados
is_capturing = False
maniobra_running = False
timelapse_running = False
streaming = False
_want_stream_on_start = False

# --- Lista de resoluciones ofrecidas (texto, w, h) ---
RESOLUTIONS = [
    ("3840 x 2160 (4K)", 3840, 2160),
    ("2560 x 1440 (QHD)", 2560, 1440),
    ("1920 x 1080 (FHD)", 1920, 1080),
    ("1600 x 1200 (UXGA)", 1600, 1200),
    ("1280 x 720 (HD)",   1280, 720),
    ("1024 x 768 (XGA)",  1024, 768),
    ("800 x 600 (SVGA)",   800, 600),
    ("640 x 480 (VGA)",    640, 480),
]
current_resolution_label = "1920 x 1080 (FHD)"  # default UI

# ---------- Panel de imagen sin “saltos” + reescalado suave ----------
class ImagePanel(tk.Frame):
    """Canvas que muestra una imagen redimensionada sin alterar el layout."""
    def __init__(self, parent, bg=BG_COLOR, min_size=(IMG_MIN_W, IMG_MIN_H)):
        super().__init__(parent, bg=bg)
        self.bg = bg
        self.min_w, self.min_h = min_size
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, borderwidth=0)
        self.canvas.pack(fill="both", expand=True)
        # Reserva tamaño mínimo inicial para evitar “saltos”
        self.update_idletasks()
        self.canvas.config(width=self.min_w, height=self.min_h)

        self._last_pil = None
        self._tk_img = None
        self._resize_job = None
        self.bind("<Configure>", self._on_resize)

    def set_image(self, pil_img: Image.Image):
        """Recibe PIL.Image (foto o frame) y la guarda como fuente de verdad."""
        self._last_pil = pil_img
        self._render()

    def _on_resize(self, _evt=None):
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(RESIZE_DEBOUNCE_MS, self._render)

    def _render(self):
        # placeholder estable si no hay imagen
        if self._last_pil is None:
            ph = Image.new("RGB", (self.min_w, self.min_h), (40, 40, 40))
            self._draw(ph)
            return

        # tamaño disponible del canvas, nunca por debajo del mínimo
        cw = max(self.canvas.winfo_width(), self.min_w)
        ch = max(self.canvas.winfo_height(), self.min_h)

        # Contener manteniendo aspecto
        shown = ImageOps.contain(self._last_pil, (cw, ch))
        self._draw(shown)

    def _draw(self, pil_img):
        self._tk_img = ImageTk.PhotoImage(pil_img)
        self.canvas.delete("all")
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        # centra siempre
        self.canvas.create_image(cw // 2, ch // 2, image=self._tk_img, anchor="center")


class ScrollableFrame(tk.Frame):
    """Contenedor con scroll vertical para pantallas pequeñas."""
    def __init__(self, parent, bg=BG_COLOR):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, borderwidth=0)
        self.vsb = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)

        self.inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")


# ---------- Utilidades ----------
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

def get_startup_dir():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs\Startup")

def startup_bat_path():
    sd = get_startup_dir()
    if not sd:
        return None
    return os.path.join(sd, "KatcamPro_start.bat")

def is_autostart_enabled():
    p = startup_bat_path()
    return bool(p and os.path.exists(p))

def enable_autostart():
    p = startup_bat_path()
    if not p:
        raise RuntimeError("No se pudo resolver la carpeta de inicio de Windows.")
    exe = sys.executable
    script = os.path.abspath(sys.argv[0])
    workdir = os.path.dirname(script)
    lines = [
        "@echo off",
        f'cd /d "{workdir}"',
        f'start "" /MIN "{exe}" "{script}"'
    ]
    with open(p, "w", encoding="utf-8") as f:
        f.write("\r\n".join(lines))

def disable_autostart():
    p = startup_bat_path()
    if p and os.path.exists(p):
        try:
            os.remove(p)
        except Exception:
            pass

# ---------- Config persistente ----------
def listar_camaras_disponibles(max_cams=8):
    disponibles = []
    for i in range(max_cams):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap is not None and cap.isOpened():
            disponibles.append(i)
        if cap is not None:
            cap.release()
    return disponibles

def seleccionar_camara():
    global CAM_INDEX
    cams = listar_camaras_disponibles()
    if not cams:
        messagebox.showerror("Cámaras", "No se detectaron cámaras conectadas.")
        return
    win = tk.Toplevel(root)
    win.title("Seleccionar cámara")
    win.configure(bg=BG_COLOR)
    tk.Label(win, text="Selecciona la cámara:", bg=BG_COLOR, fg=FG_COLOR, font=("Arial", 12, "bold")).pack(padx=20, pady=10)
    var = tk.IntVar(value=CAM_INDEX)
    for idx in cams:
        tk.Radiobutton(win, text=f"Cámara {idx}", variable=var, value=idx, bg=BG_COLOR, fg=FG_COLOR, selectcolor=BTN_COLOR).pack(anchor="w", padx=20)
    def set_cam():
        global CAM_INDEX
        CAM_INDEX = var.get()
        camera_manager.set_cam_index(CAM_INDEX)
        guardar_configuracion()
        win.destroy()
        messagebox.showinfo("Cámara", f"Cámara seleccionada: {CAM_INDEX}")
    tk.Button(win, text="Seleccionar", command=set_cam, bg=BTN_COLOR, fg=BTN_TEXT_COLOR, font=("Arial", 10, "bold")).pack(pady=10)

# Metadatos (cliente/proyecto/id/gps) en config
_meta_defaults = {
    "cliente": "",
    "proyecto": "",
    "camera_id": "",
    "gps_lat": "",
    "gps_lon": ""
}

def _meta_from_config(cfg):
    m = {}
    for k in _meta_defaults:
        m[k] = cfg.get(k, _meta_defaults[k])
    return m

def guardar_configuracion():
    try:
        prev = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                prev = json.load(f)
        # mantén metadatos existentes
        meta = _meta_from_config(prev)

        # Resolución elegida
        cfg_res = {"capture_resolution_label": current_resolution_label}

        config = {
            "frecuencia": entry_freq.get(),
            "dias": [var.get() for var in day_vars],
            "hora_inicio": entry_hour_start.get(),
            "hora_fin": entry_hour_end.get(),
            "timelapse_activo": timelapse_running,
            "photo_dir": PHOTO_DIR,
            "cam_index": CAM_INDEX,
            "drive_dir": prev.get("drive_dir"),
            "autostart_enabled": bool(is_autostart_enabled()),
            "stream_activo": bool(streaming),
            # metadatos:
            "cliente": meta.get("cliente", ""),
            "proyecto": meta.get("proyecto", ""),
            "camera_id": meta.get("camera_id", ""),
            "gps_lat": meta.get("gps_lat", ""),
            "gps_lon": meta.get("gps_lon", ""),
        }
        config.update(cfg_res)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        messagebox.showwarning("Config", f"No se pudo guardar configuración: {e}")

def _save_meta_to_config(new_meta: dict):
    try:
        cfg = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        cfg.update(new_meta)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        messagebox.showwarning("Config", f"No se pudo guardar metadatos: {e}")

def cargar_configuracion():
    global CAM_INDEX, PHOTO_DIR, DRIVE_DIR, _want_stream_on_start
    global current_resolution_label

    if not os.path.exists(CONFIG_FILE):
        return None

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        messagebox.showwarning("Config", f"No se pudo leer la configuración: {e}")
        return None

    CAM_INDEX = config.get("cam_index", 0)
    camera_manager.set_cam_index(CAM_INDEX)

    photo_dir_saved = config.get("photo_dir")
    if photo_dir_saved and os.path.exists(photo_dir_saved):
        PHOTO_DIR = photo_dir_saved
    drive_dir_saved = config.get("drive_dir")
    if drive_dir_saved and os.path.exists(drive_dir_saved):
        DRIVE_DIR = drive_dir_saved

    try:
        entry_freq.delete(0, "end")
        entry_freq.insert(0, config.get("frecuencia", "10"))
        dias_cfg = config.get("dias", [True] * 7)
        for i, valor in enumerate(dias_cfg):
            day_vars[i].set(valor)
        entry_hour_start.delete(0, "end")
        entry_hour_start.insert(0, config.get("hora_inicio", "08:00"))
        entry_hour_end.delete(0, "end")
        entry_hour_end.insert(0, config.get("hora_fin", "18:00"))
    except Exception:
        pass

    info_cliente.set(config.get("cliente", ""))
    info_proyecto.set(config.get("proyecto", ""))
    info_camera_id.set(config.get("camera_id", ""))
    info_gps_lat.set(config.get("gps_lat", ""))
    info_gps_lon.set(config.get("gps_lon", ""))

    # resolución elegida (para inicializar UI luego)
    current_resolution_label = config.get("capture_resolution_label", current_resolution_label)

    if config.get("timelapse_activo", False):
        root.after(500, start_timelapse)

    _want_stream_on_start = bool(config.get("stream_activo", False))
    return config

# ---------- Carpetas ----------
def seleccionar_directorio_manual(titulo):
    carpeta = fd.askdirectory(title=titulo)
    if carpeta:
        return carpeta
    return None

def inicializar_directorio_fotos():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            p = cfg.get("photo_dir")
            if p and os.path.exists(p) and has_write_access(p):
                return p
    except Exception:
        pass
    while True:
        ruta = seleccionar_directorio_manual("Selecciona la carpeta para guardar fotos (pendrive o local)")
        if ruta and has_write_access(ruta):
            return ruta
        elif ruta:
            messagebox.showerror("Permisos", "No hay permiso de escritura en la carpeta elegida.")
        else:
            messagebox.showerror("Error", "Debes seleccionar una carpeta para continuar.")

def inicializar_directorio_drive():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            d = cfg.get("drive_dir")
            if d and os.path.exists(d) and has_write_access(d):
                return d
    except Exception:
        pass
    while True:
        ruta = seleccionar_directorio_manual("Selecciona la carpeta de Google Drive (KatcamAustralia/fotos)")
        if ruta and has_write_access(ruta):
            return ruta
        elif ruta:
            messagebox.showerror("Permisos", "No hay permiso de escritura en la carpeta elegida.")
        else:
            messagebox.showerror("Error", "Debes seleccionar una carpeta para continuar.")

def cambiar_directorio_fotos():
    global PHOTO_DIR
    nueva = seleccionar_directorio_manual("Selecciona la carpeta para guardar fotos")
    if nueva and has_write_access(nueva):
        PHOTO_DIR = nueva
        guardar_configuracion()
        messagebox.showinfo("Ruta actualizada", f"Carpeta de fotos cambiada a:\n{PHOTO_DIR}")
        update_main_image()
        _refresh_info_tab()
    elif nueva:
        messagebox.showerror("Permisos", "No hay permiso de escritura en la carpeta seleccionada.")

def seleccionar_drive_manual():
    global DRIVE_DIR
    carpeta = seleccionar_directorio_manual("Selecciona la carpeta de Google Drive (KatcamAustralia/fotos)")
    if carpeta and has_write_access(carpeta):
        DRIVE_DIR = carpeta
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            else:
                cfg = {}
            cfg["drive_dir"] = carpeta
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showwarning("Config", f"No se pudo guardar la ruta de Drive: {e}")
        messagebox.showinfo("Ruta actualizada", f"Carpeta de Google Drive cambiada a:\n{DRIVE_DIR}")
    elif carpeta:
        messagebox.showerror("Permisos", "No hay permiso de escritura en la carpeta seleccionada.")

# ---------- Sincronización ----------
def sincronizar_fotos():
    try:
        if not os.path.exists(DRIVE_DIR):
            lbl_status_general.config(text="No se encontró Google Drive para sincronizar.")
            return
        if not os.path.exists(PHOTO_DIR):
            lbl_status_general.config(text="Carpeta de fotos inválida.")
            return

        fotos_pendrive = sorted([f for f in os.listdir(PHOTO_DIR) if f.lower().endswith((".jpg", ".jpeg", ".png"))])
        fotos_drive = set(os.listdir(DRIVE_DIR))
        nuevas = [f for f in fotos_pendrive if f not in fotos_drive]

        for f in nuevas:
            shutil.copy2(os.path.join(PHOTO_DIR, f), os.path.join(DRIVE_DIR, f))

        if nuevas:
            lbl_status_general.config(text=f"Sincronizadas {len(nuevas)} fotos al Drive.")
        else:
            lbl_status_general.config(text="No hay fotos nuevas para sincronizar.")
    except Exception as e:
        lbl_status_general.config(text=f"Error al sincronizar: {e}")

# ---------- Imagen (usando ImagePanel) ----------
image_panel = None  # se crea en el layout

def get_last_photo():
    if not os.path.exists(PHOTO_DIR):
        return None
    fotos = sorted([f for f in os.listdir(PHOTO_DIR) if f.lower().endswith((".jpg", ".jpeg", ".png"))])
    if fotos:
        return os.path.join(PHOTO_DIR, fotos[-1])
    return None

# Abrir carpeta de fotos
def abrir_carpeta_fotos():
    """Abre la carpeta actual de fotos en el explorador del sistema."""
    global PHOTO_DIR
    if not PHOTO_DIR:
        messagebox.showerror("Carpeta", "La carpeta de fotos no está configurada.")
        return
    path = os.path.realpath(PHOTO_DIR)
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        messagebox.showerror("Carpeta", f"No se pudo abrir la carpeta:\n{e}")

def update_main_image():
    if image_panel is None:
        return
    try:
        last_photo = get_last_photo()
        if last_photo and os.path.exists(last_photo):
            img = Image.open(last_photo).convert("RGB")
        else:
            try:
                img = Image.open("kreativerkatcam.jpg").convert("RGB")
            except Exception:
                img = Image.new("RGB", (IMG_MIN_W, IMG_MIN_H), (64, 64, 64))
        image_panel.set_image(img)
    except Exception as e:
        lbl_status_general.config(text=f"Error mostrando imagen: {e}")

# ---------- STREAM helpers ----------
ui_refresh_ms = 40  # ~25 fps

def _tick_stream():
    if not streaming:
        return
    frame_rgb = camera_manager.get_frame_rgb()
    if frame_rgb is not None:
        img = Image.fromarray(frame_rgb)
        image_panel.set_image(img)
    if streaming:
        root.after(ui_refresh_ms, _tick_stream)

def update_stream_ui():
    if streaming:
        lbl_status_transmision.config(text="Transmisión: ACTIVA")
        btn_switch_trans.config(text="Detener transmisión", bg="#FF5252", fg="#FFFFFF")
        toggle_transmision.on = True
    else:
        lbl_status_transmision.config(text="Transmisión: DETENIDA")
        btn_switch_trans.config(text="Iniciar transmisión", bg=BTN_COLOR, fg=BTN_TEXT_COLOR)
        toggle_transmision.on = False

def _find_res(label: str) -> Optional[Tuple[int, int]]:
    for t, w, h in RESOLUTIONS:
        if t == label:
            return (w, h)
    return None

def _apply_camera_resolution(w: int, h: int):
    # Intento principal: pedir al manager que cambie resolución
    try:
        if hasattr(camera_manager, "set_resolution"):
            camera_manager.set_resolution(w, h)
            return
    except Exception as e:
        print("camera_manager.set_resolution error:", e)
    # Alternativa: algunos managers aplican al iniciar el stream; aquí solo guardamos preferencia
    pass

def stream_on():
    global streaming
    if streaming:
        return
    streaming = True
    # Aplica resolución preferida al iniciar
    wh = _find_res(current_resolution_label)
    if wh:
        _apply_camera_resolution(*wh)
    camera_manager.start_stream()
    update_stream_ui()
    lbl_status_general.config(text="Transmisión en directo")
    _tick_stream()

def stream_off():
    global streaming
    if not streaming:
        return
    streaming = False
    camera_manager.stop_stream()
    update_stream_ui()
    lbl_status_general.config(text="Transmisión detenida")
    update_main_image()

def mostrar_transmision():
    if is_capturing:
        lbl_status_general.config(text="No se puede iniciar transmisión: capturando foto...")
        return
    if maniobra_running:
        lbl_status_general.config(text="No se puede iniciar transmisión: maniobra en curso.")
        return
    stream_on()

def detener_transmision():
    stream_off()

def toggle_transmision():
    if streaming:
        stream_off()
    else:
        mostrar_transmision()

# ---------- FOTO ----------
def take_and_update():
    global is_capturing
    if maniobra_running:
        lbl_status_general.config(text="No se puede sacar foto: maniobra en curso.")
        return
    if is_capturing:
        lbl_status_general.config(text="Ya hay una captura en curso...")
        return

    was_streaming = streaming
    is_capturing = True
    lbl_status_general.config(text="Preparando captura...")

    def _work():
        try:
            if was_streaming and not timelapse_running:
                root.after(0, stream_off)
                time.sleep(0.08)
            # pasa la resolución preferida al capturador, si tu módulo la usa
            wh = _find_res(current_resolution_label)
            prefer = [wh] if wh else None
            take_photo(
                dest_folder=PHOTO_DIR,
                prefer_sizes=prefer,
                jpeg_quality=95,
                auto_resume_stream=bool(was_streaming and timelapse_running),
                block_until_done=True
            )
            msg = "Foto tomada."
        except Exception as e:
            msg = f"Error: {e}"
        finally:
            def _finish():
                nonlocal was_streaming
                global is_capturing
                lbl_status_general.config(text=msg)
                update_main_image()
                _refresh_info_tab()
                if was_streaming:
                    if timelapse_running:
                        if not streaming:
                            stream_on()
                        else:
                            update_stream_ui()
                            _tick_stream()
                    else:
                        stream_on()
                is_capturing = False
            root.after(0, _finish)

    threading.Thread(target=_work, daemon=True).start()

# ---------- TIMELAPSE ----------
next_capture_time = None
interval_ms = 600000
days_selected = []
hour_start = "08:00"
hour_end = "18:00"

def start_timelapse():
    global timelapse_running, next_capture_time, interval_ms, days_selected, hour_start, hour_end
    guardar_configuracion()
    timelapse_running = True
    try:
        freq_str = entry_freq.get().strip()
        hour_start_str = entry_hour_start.get().strip()
        hour_end_str = entry_hour_end.get().strip()
        days_selected.clear()
        for i, var in enumerate(day_vars):
            if var.get():
                days_selected.append(dias_lista[i])
        hour_start = hour_start_str if hour_start_str else None
        hour_end = hour_end_str if hour_end_str else None
        next_capture_time = datetime.now()
        interval_ms = int(float(freq_str) * 1000 * 60) if freq_str else 600000
    except Exception as e:
        lbl_status_timelapse.config(text=f"Error en parámetros: {e}")
        return
    lbl_status_timelapse.config(text="Timelapse: ACTIVO")
    lbl_status_general.config(text="Esperando próxima foto...")
    schedule_next_capture()

def stop_timelapse():
    global timelapse_running
    timelapse_running = False
    guardar_configuracion()
    lbl_status_timelapse.config(text="Timelapse: DETENIDO")
    lbl_status_general.config(text="Timelapse detenido.")

def schedule_next_capture():
    global timelapse_running, next_capture_time, interval_ms, days_selected, hour_start, hour_end
    if not timelapse_running:
        lbl_status_timelapse.config(text="Timelapse: DETENIDO")
        lbl_status_general.config(text="Timelapse detenido.")
        return
    now = datetime.now()
    dia_actual = now.strftime("%A").lower()
    dias_es = {
        "monday": "lunes", "tuesday": "martes", "wednesday": "miércoles",
        "thursday": "jueves", "friday": "viernes", "saturday": "sábado", "sunday": "domingo"
    }
    dia_actual_es = dias_es.get(dia_actual, dia_actual)
    if days_selected and dia_actual_es not in days_selected:
        lbl_status_general.config(text="Esperando día válido para timelapse...")
        root.after(interval_ms, schedule_next_capture)
        return
    if hour_start and hour_end:
        hora_actual = now.strftime("%H:%M")
        if not (hour_start <= hora_actual <= hour_end):
            lbl_status_general.config(text="Fuera de horario. Esperando para timelapse...")
            root.after(interval_ms, schedule_next_capture)
            return
    if now >= next_capture_time:
        lbl_status_general.config(text="Capturando foto para timelapse...")
        take_and_update()
        next_capture_time = now + timedelta(milliseconds=interval_ms)
        lbl_status_general.config(text="Foto tomada. Esperando próxima captura...")
    else:
        lbl_status_general.config(text="Esperando próxima captura de timelapse...")
    root.after(interval_ms, schedule_next_capture)

# ---------- Autoajuste de cámara (un solo botón) ----------
def camera_autoadjust():
    """
    Botón único de autoajuste:
      - Activa modos automáticos de exposición y balance de blancos (si el driver lo soporta).
      - No apaga/enciende stream ni cambia resolución → evita saltos.
    """
    camera_manager.set_auto_modes(enable_exposure_auto=True, enable_wb_auto=True)
    lbl_status_general.config(text="Autoajuste aplicado (expo/WB automáticos).")

# ---------- UI ----------
root = tk.Tk()
root.title("Katcam Pro")
try:
    root.iconbitmap("katcam_multi.ico")
except Exception:
    pass
root.configure(bg=BG_COLOR)
root.minsize(MIN_APP_W, MIN_APP_H)

# posición/tamaño inicial centrado
screen_width = root.winfo_screenwidth()
screen_height = root.winfo_screenheight()
win_width = max(int(screen_width * 0.8), MIN_APP_W)
win_height = max(int(screen_height * 0.8), MIN_APP_H)
x = (screen_width - win_width) // 2
y = (screen_height - win_height) // 2
root.geometry(f"{win_width}x{win_height}+{x}+{y}")
root.resizable(True, True)

# contenedor raíz (con o sin scroll)
if USE_SCROLL_CONTAINER:
    container = ScrollableFrame(root, bg=BG_COLOR)
    container.pack(fill="both", expand=True)
    parent = container.inner
else:
    parent = tk.Frame(root, bg=BG_COLOR)
    parent.pack(fill="both", expand=True)

# Menú
menubar = tk.Menu(root, bg=BG_COLOR, fg=FG_COLOR)
root.config(menu=menubar)

carpeta_menu = tk.Menu(menubar, tearoff=0, bg=BG_COLOR, fg=FG_COLOR)
menubar.add_cascade(label="Opciones", menu=carpeta_menu)
carpeta_menu.add_command(label="Cambiar carpeta de fotos...", command=cambiar_directorio_fotos)
carpeta_menu.add_command(label="Cambiar carpeta de Google Drive...", command=seleccionar_drive_manual)
carpeta_menu.add_separator()
carpeta_menu.add_command(label="Seleccionar cámara...", command=seleccionar_camara)

def open_autostart_window():
    win = tk.Toplevel(root)
    win.title("Inicio con Windows")
    win.configure(bg=BG_COLOR)
    win.geometry("460x180")
    info = tk.Label(win, text="Configura si Katcam Pro se inicia automáticamente con Windows.",
                    bg=BG_COLOR, fg=FG_COLOR, font=("Arial", 11))
    info.pack(padx=12, pady=(12, 4))
    status_lbl = tk.Label(win, text="", bg=BG_COLOR, fg=BTN_COLOR, font=("Arial", 11, "bold"))
    status_lbl.pack(pady=(0, 8))
    autostart_var = tk.IntVar(value=1 if is_autostart_enabled() else 0)
    def on_toggle():
        try:
            if autostart_var.get():
                enable_autostart()
                status_lbl.config(text="Estado: ACTIVADO")
                lbl_status_general.config(text="Inicio automático habilitado.")
            else:
                disable_autostart()
                status_lbl.config(text="Estado: DESACTIVADO")
                lbl_status_general.config(text="Inicio automático deshabilitado.")
            guardar_configuracion()
        except Exception as e:
            lbl_status_general.config(text=f"Autostart error: {e}")
    chk = tk.Checkbutton(
        win, text="Iniciar Katcam Pro con Windows",
        variable=autostart_var, onvalue=1, offvalue=0, command=on_toggle,
        bg=BG_COLOR, fg=FG_COLOR, selectcolor="black",
        activebackground=BG_COLOR, activeforeground=FG_COLOR,
        font=("Arial", 12, "bold")
    )
    chk.pack(padx=12, pady=8)
    status_lbl.config(text="Estado: ACTIVADO" if autostart_var.get() else "Estado: DESACTIVADO")

ajustes_menu = tk.Menu(menubar, tearoff=0, bg=BG_COLOR, fg=FG_COLOR)
menubar.add_cascade(label="Ajustes", menu=ajustes_menu)
ajustes_menu.add_command(label="Inicio con Windows…", command=open_autostart_window)

# Header (logo izquierda, reloj derecha)
header_frame = tk.Frame(parent, bg=BG_COLOR)
header_frame.pack(fill="x", pady=(12, 6))
header_frame.grid_columnconfigure(0, weight=0)
header_frame.grid_columnconfigure(1, weight=1)
try:
    logo_img = Image.open("logo_katcam.png")
    logo_img = ImageOps.contain(logo_img, (350, 150))
    logo_photo = ImageTk.PhotoImage(logo_img)
    logo_label = tk.Label(header_frame, image=logo_photo, bg=BG_COLOR)
    logo_label.grid(row=0, column=0, sticky="w", padx=10)
except Exception:
    logo_label = tk.Label(header_frame, text="Katcam Pro", bg=BG_COLOR, fg=BTN_COLOR, font=("Arial", 20, "bold"))
    logo_label.grid(row=0, column=0, sticky="w", padx=10)

# Reloj arriba a la derecha
def update_clock():
    local_timezone = tzlocal.get_localzone()
    now = datetime.now(local_timezone)
    lbl_clock.config(text=now.strftime("%H:%M:%S") + f" ({local_timezone})")
    root.after(1000, update_clock)
lbl_clock = tk.Label(header_frame, text="", bg=BG_COLOR, fg=BTN_COLOR, font=("Arial", 14, "bold"))
lbl_clock.grid(row=0, column=1, sticky="e", padx=12)
update_clock()

main_frame = tk.Frame(parent, bg=BG_COLOR)
main_frame.pack(padx=10, pady=10, fill="both", expand=True)

# --- tres columnas responsivas (alineadas) ---
main_frame.grid_columnconfigure(0, weight=5, uniform="cols")  # imagen
main_frame.grid_columnconfigure(1, weight=2, uniform="cols")  # botones
main_frame.grid_columnconfigure(2, weight=3, uniform="cols")  # pestañas
main_frame.grid_rowconfigure(0, weight=1)

# Columna 1: Imagen (ImagePanel)
image_frame = tk.Frame(main_frame, bg=BG_COLOR)
image_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
tk.Label(image_frame, text="Última foto/Transmisión", font=("Arial", 16, "bold"),
         bg=BG_COLOR, fg=BTN_COLOR, anchor="w").pack(pady=5, anchor="w", fill="x")
image_panel = ImagePanel(image_frame, bg=BG_COLOR, min_size=(IMG_MIN_W, IMG_MIN_H))
image_panel.pack(fill="both", expand=True, pady=5)

# --- Bloque de estados debajo de la imagen, misma columna ---
status_frame = tk.Frame(image_frame, bg=BG_COLOR)
status_frame.pack(fill="x", pady=(8, 0))
lbl_status_transmision = tk.Label(status_frame, text="Transmisión: DETENIDA", bg=BG_COLOR, fg=FG_COLOR, font=("Arial", 11, "bold"))
lbl_status_transmision.grid(row=0, column=0, sticky="w", padx=2, pady=1)
lbl_status_timelapse = tk.Label(status_frame, text="Timelapse: DETENIDO", bg=BG_COLOR, fg=FG_COLOR, font=("Arial", 11, "bold"))
lbl_status_timelapse.grid(row=1, column=0, sticky="w", padx=2, pady=1)
lbl_status_maniobra = tk.Label(status_frame, text="Maniobra: INACTIVA", bg=BG_COLOR, fg=FG_COLOR, font=("Arial", 11, "bold"))
lbl_status_maniobra.grid(row=2, column=0, sticky="w", padx=2, pady=1)
lbl_status_general = tk.Label(status_frame, text="Listo", bg=BG_COLOR, fg=FG_COLOR, font=("Arial", 10))
lbl_status_general.grid(row=3, column=0, sticky="w", padx=2, pady=(4, 2))

# Columna 2: Botones (pegada arriba, tamaño estable)
button_frame = tk.Frame(main_frame, bg=BG_COLOR)
button_frame.grid(row=0, column=1, padx=10, pady=10, sticky="n")
button_frame.grid_propagate(False)
button_frame.update_idletasks()
# Forzamos a calcular dimensiones y establecemos tamaño mínimo de la ventana principal
root.update_idletasks()
root.minsize(800, 600)   # ajusta si quieres

tk.Label(button_frame, text="", bg=BG_COLOR).pack(pady=5)

btn_take = tk.Button(
    button_frame, text="Sacar Foto", command=take_and_update, width=25, height=2,
    bg=BTN_COLOR, fg=BTN_TEXT_COLOR, activebackground=BTN_COLOR, activeforeground=BTN_TEXT_COLOR,
    bd=0, font=("Arial", 12, "bold"), padx=10, pady=10
)
btn_take.pack(pady=8)

btn_switch_trans = tk.Button(
    button_frame, text="Iniciar transmisión", command=toggle_transmision, width=25, height=2,
    bg=BTN_COLOR, fg=BTN_TEXT_COLOR, activebackground=BTN_COLOR, activeforeground=BTN_TEXT_COLOR,
    bd=0, font=("Arial", 12, "bold"), padx=10, pady=10
)
btn_switch_trans.pack(pady=8)
toggle_transmision.on = False

def toggle_timelapse():
    if not getattr(toggle_timelapse, "on", False):
        start_timelapse()
        btn_switch_timelapse.config(text="Detener Timelapse", bg="#FF5252", fg="#FFFFFF")
        toggle_timelapse.on = True
    else:
        stop_timelapse()
        btn_switch_timelapse.config(text="Iniciar Timelapse", bg=BTN_COLOR, fg=BTN_TEXT_COLOR)
        toggle_timelapse.on = False

toggle_timelapse.on = False

btn_switch_timelapse = tk.Button(
    button_frame, text="Iniciar Timelapse", command=toggle_timelapse, width=25, height=2,
    bg=BTN_COLOR, fg=BTN_TEXT_COLOR, activebackground=BTN_COLOR, activeforeground=BTN_TEXT_COLOR,
    bd=0, font=("Arial", 12, "bold"), padx=10, pady=10
)
btn_switch_timelapse.pack(pady=8)

def toggle_maniobra():
    global maniobra_running
    if not getattr(toggle_maniobra, "on", False):
        try:
            duracion_min = float(entry_maniobra_duracion.get())
            intervalo = float(entry_maniobra_intervalo.get())
        except Exception as e:
            lbl_status_general.config(text=f"Error en maniobra: {e}")
            return
        fin = datetime.now() + timedelta(seconds=duracion_min * 60)
        maniobra_running = True
        try:
            lbl_status_maniobra.config(text="Maniobra: ACTIVA")
        except Exception:
            pass
        lbl_status_general.config(text="Maniobra en curso...")
        if streaming:
            stream_off()
        def _tick():
            global maniobra_running
            if datetime.now() >= fin or not maniobra_running:
                maniobra_running = False
                lbl_status_general.config(text="Maniobra finalizada.")
                btn_maniobra.config(text="Iniciar Maniobra", bg=BTN_COLOR, fg=BTN_TEXT_COLOR)
                toggle_maniobra.on = False
                try:
                    lbl_status_maniobra.config(text="Maniobra: INACTIVA")
                except Exception:
                    pass
                return
            threading.Thread(
                target=lambda: take_photo(PHOTO_DIR, block_until_done=True, auto_resume_stream=False),
                daemon=True
            ).start()
            update_main_image()
            _refresh_info_tab()
            root.after(int(float(intervalo) * 1000), _tick)
        _tick()
        btn_maniobra.config(text="Detener Maniobra", bg="#FF5252", fg="#FFFFFF")
        toggle_maniobra.on = True
    else:
        maniobra_running = False
        lbl_status_general.config(text="Maniobra cancelada por el usuario.")
        btn_maniobra.config(text="Iniciar Maniobra", bg=BTN_COLOR, fg=BTN_TEXT_COLOR)
        toggle_maniobra.on = False
        try:
            lbl_status_maniobra.config(text="Maniobra: INACTIVA")
        except Exception:
            pass

toggle_maniobra.on = False

btn_maniobra = tk.Button(
    button_frame, text="Iniciar Maniobra", command=toggle_maniobra, width=25, height=2,
    bg=BTN_COLOR, fg=BTN_TEXT_COLOR, activebackground=BTN_COLOR, activeforeground=BTN_TEXT_COLOR,
    bd=0, font=("Arial", 12, "bold"), padx=10, pady=10
)
btn_maniobra.pack(pady=8)

btn_open_folder = tk.Button(
    button_frame, text="Abrir carpeta de fotos", command=abrir_carpeta_fotos, width=25, height=2,
    bg=BG_COLOR, fg=BTN_COLOR, activebackground=BG_COLOR, activeforeground=BTN_COLOR,
    bd=2, highlightbackground=BTN_BORDER_COLOR, highlightcolor=BTN_BORDER_COLOR,
    font=("Arial", 12, "bold"), padx=10, pady=10
)
btn_open_folder.pack(pady=10, anchor="n")

# Columna 3: Configuración (pestañas) con grid para llenar espacio
config_frame = tk.Frame(main_frame, bg=BG_COLOR)
config_frame.grid(row=0, column=2, padx=10, pady=10, sticky="nsew")
config_frame.grid_rowconfigure(1, weight=1)

tk.Label(config_frame, text="Configuraciones", font=("Arial", 16, "bold"),
         bg=BG_COLOR, fg=BTN_COLOR).grid(row=0, column=0, sticky="w", pady=(0, 10))

notebook = ttk.Notebook(config_frame)
notebook.grid(row=1, column=0, sticky="nsew")

# 1) Timelapse
tab_timelapse = tk.Frame(notebook, bg=BG_COLOR)
notebook.add(tab_timelapse, text="Timelapse")

tk.Label(tab_timelapse, text="Configuración Timelapse", font=("Arial", 16, "bold"), bg=BG_COLOR, fg=FG_COLOR).grid(row=0, column=0, columnspan=2, pady=5)
tk.Label(tab_timelapse, text="Frecuencia (minutos):", bg=BG_COLOR, fg=FG_COLOR).grid(row=1, column=0, sticky="e")
entry_freq = tk.Entry(tab_timelapse)
entry_freq.grid(row=1, column=1)
entry_freq.insert(0, "10")

tk.Label(tab_timelapse, text="Días a funcionar:", bg=BG_COLOR, fg=FG_COLOR).grid(row=2, column=0, sticky="ne")
dias_lista = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
day_vars = [tk.BooleanVar(value=True) for _ in dias_lista]
days_frame = tk.Frame(tab_timelapse, bg=BG_COLOR)
days_frame.grid(row=2, column=1, sticky="w")
for i, dia in enumerate(dias_lista):
    tk.Checkbutton(
        days_frame, text=dia.capitalize(), variable=day_vars[i],
        bg=BG_COLOR, fg="white", selectcolor="black",
        activebackground=BG_COLOR, activeforeground="white",
        font=("Arial", 11, "bold"), padx=6, pady=2, borderwidth=0, highlightthickness=0
    ).pack(anchor="w", pady=1)

tk.Label(tab_timelapse, text="Hora inicio (HH:MM):", bg=BG_COLOR, fg=FG_COLOR).grid(row=3, column=0, sticky="e")
entry_hour_start = tk.Entry(tab_timelapse)
entry_hour_start.grid(row=3, column=1)
entry_hour_start.insert(0, "08:00")

tk.Label(tab_timelapse, text="Hora fin (HH:MM):", bg=BG_COLOR, fg=FG_COLOR).grid(row=4, column=0, sticky="e")
entry_hour_end = tk.Entry(tab_timelapse)
entry_hour_end.grid(row=4, column=1)
entry_hour_end.insert(0, "18:00")

# 2) Maniobra
tab_maniobra = tk.Frame(notebook, bg=BG_COLOR)
notebook.add(tab_maniobra, text="Maniobra")

tk.Label(tab_maniobra, text="Maniobra: Fotos continuas", font=("Arial", 16, "bold"), bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)
tk.Label(tab_maniobra, text="Duración (minutos):", bg=BG_COLOR, fg=FG_COLOR).pack(anchor="w", padx=10)
entry_maniobra_duracion = tk.Entry(tab_maniobra)
entry_maniobra_duracion.pack(anchor="w", padx=10, pady=5)
entry_maniobra_duracion.insert(0, "10")
tk.Label(tab_maniobra, text="Intervalo entre fotos (segundos):", bg=BG_COLOR, fg=FG_COLOR).pack(anchor="w", padx=10)
entry_maniobra_intervalo = tk.Entry(tab_maniobra)
entry_maniobra_intervalo.pack(anchor="w", padx=10, pady=5)
entry_maniobra_intervalo.insert(0, "1")

# 3) Cámara
tab_camara = tk.Frame(notebook, bg=BG_COLOR)
notebook.add(tab_camara, text="Cámara")

tk.Label(tab_camara, text="Ajustes de Cámara", font=("Arial", 16, "bold"), bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)
tk.Label(tab_camara, text="Usa Autoajuste para que el driver optimice exposición y balance de blancos.", bg=BG_COLOR, fg=FG_COLOR).pack(pady=(0,8))
btn_autoadj = tk.Button(
    tab_camara, text="Autoajuste (recomendado)", command=camera_autoadjust,
    bg=BTN_COLOR, fg=BTN_TEXT_COLOR, bd=0, font=("Arial", 12, "bold"), padx=12, pady=10
)
btn_autoadj.pack(padx=10, pady=10, anchor="center")

btn_ctrl_dialog = tk.Button(
    tab_camara, text="Ajustes avanzados del controlador…", command=camera_manager.show_driver_settings,
    bg="#FFB300", fg="#181818", bd=0, font=("Arial", 11, "bold"), padx=10, pady=8
)
btn_ctrl_dialog.pack(pady=6, padx=10, anchor="center")

# --- Selector de resolución ---
tk.Label(tab_camara, text="Resolución de captura/stream:", bg=BG_COLOR, fg=FG_COLOR).pack(pady=(14, 2))
resolution_var = tk.StringVar(value=current_resolution_label)
res_values = [t for (t, _, _) in RESOLUTIONS]
res_combo = ttk.Combobox(tab_camara, textvariable=resolution_var, values=res_values, state="readonly", width=28)
res_combo.pack(pady=(0, 8))

def _on_resolution_change(_evt=None):
    global current_resolution_label
    current_resolution_label = resolution_var.get()
    wh = _find_res(current_resolution_label)
    if wh:
        w, h = wh
        _apply_camera_resolution(w, h)
        lbl_status_general.config(text=f"Resolución preferida: {w}x{h}")
        guardar_configuracion()

res_combo.bind("<<ComboboxSelected>>", _on_resolution_change)

# 4) Info (Cliente/Proyecto/ID/GPS + conteo fotos + mapa futuro)
tab_info = tk.Frame(notebook, bg=BG_COLOR)
notebook.add(tab_info, text="Info")

info_cliente = tk.StringVar(value="")
info_proyecto = tk.StringVar(value="")
info_camera_id = tk.StringVar(value="")
info_gps_lat = tk.StringVar(value="")
info_gps_lon = tk.StringVar(value="")
info_fotos = tk.StringVar(value="0")
info_ultima = tk.StringVar(value="—")

def _count_photos_and_last():
    if not os.path.exists(PHOTO_DIR):
        return 0, "—"
    files = sorted([f for f in os.listdir(PHOTO_DIR) if f.lower().endswith((".jpg",".jpeg",".png"))])
    if not files:
        return 0, "—"
    last_path = os.path.join(PHOTO_DIR, files[-1])
    try:
        ts = datetime.fromtimestamp(os.path.getmtime(last_path)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        ts = "—"
    return len(files), ts

def _refresh_info_tab():
    total, last_ts = _count_photos_and_last()
    info_fotos.set(str(total))
    info_ultima.set(last_ts)

def _open_edit_meta():
    win = tk.Toplevel(root)
    win.title("Editar información")
    win.configure(bg=BG_COLOR)
    win.geometry("420x300")
    def row(lbl, var, r):
        tk.Label(win, text=lbl, bg=BG_COLOR, fg=FG_COLOR).grid(row=r, column=0, sticky="e", padx=8, pady=6)
        ent = tk.Entry(win, textvariable=var, width=28)
        ent.grid(row=r, column=1, sticky="w", padx=8, pady=6)
    row("Cliente:", info_cliente, 0)
    row("Proyecto:", info_proyecto, 1)
    row("ID Cámara:", info_camera_id, 2)
    row("GPS Lat:", info_gps_lat, 3)
    row("GPS Lon:", info_gps_lon, 4)

    def save_meta():
        meta = {
            "cliente": info_cliente.get(),
            "proyecto": info_proyecto.get(),
            "camera_id": info_camera_id.get(),
            "gps_lat": info_gps_lat.get(),
            "gps_lon": info_gps_lon.get(),
        }
        _save_meta_to_config(meta)
        lbl_status_general.config(text="Información guardada.")
        win.destroy()

    btn = tk.Button(win, text="Guardar", command=save_meta,
                    bg=BTN_COLOR, fg=BTN_TEXT_COLOR, bd=0, font=("Arial", 11, "bold"), padx=10, pady=8)
    btn.grid(row=5, column=0, columnspan=2, pady=12)

tk.Label(tab_info, text="Información de la instalación", font=("Arial", 16, "bold"), bg=BG_COLOR, fg=FG_COLOR).grid(row=0, column=0, columnspan=2, pady=(10, 6))

tk.Label(tab_info, text="Cliente:", bg=BG_COLOR, fg=FG_COLOR).grid(row=1, column=0, sticky="e", padx=8, pady=4)
tk.Label(tab_info, textvariable=info_cliente, bg=BG_COLOR, fg=BTN_COLOR, font=("Arial", 11, "bold")).grid(row=1, column=1, sticky="w", padx=8, pady=4)

tk.Label(tab_info, text="Proyecto:", bg=BG_COLOR, fg=FG_COLOR).grid(row=2, column=0, sticky="e", padx=8, pady=4)
tk.Label(tab_info, textvariable=info_proyecto, bg=BG_COLOR, fg=BTN_COLOR, font=("Arial", 11, "bold")).grid(row=2, column=1, sticky="w", padx=8, pady=4)

tk.Label(tab_info, text="ID Cámara:", bg=BG_COLOR, fg=FG_COLOR).grid(row=3, column=0, sticky="e", padx=8, pady=4)
tk.Label(tab_info, textvariable=info_camera_id, bg=BG_COLOR, fg=BTN_COLOR, font=("Arial", 11, "bold")).grid(row=3, column=1, sticky="w", padx=8, pady=4)

tk.Label(tab_info, text="GPS (lat, lon):", bg=BG_COLOR, fg=FG_COLOR).grid(row=4, column=0, sticky="e", padx=8, pady=4)
tk.Label(tab_info, textvariable=info_gps_lat, bg=BG_COLOR, fg=BTN_COLOR, font=("Arial", 11, "bold")).grid(row=4, column=1, sticky="w", padx=8, pady=4)
tk.Label(tab_info, textvariable=info_gps_lon, bg=BG_COLOR, fg=BTN_COLOR, font=("Arial", 11, "bold")).grid(row=5, column=1, sticky="w", padx=8, pady=0)

tk.Label(tab_info, text="Fotos totales:", bg=BG_COLOR, fg=FG_COLOR).grid(row=6, column=0, sticky="e", padx=8, pady=4)
tk.Label(tab_info, textvariable=info_fotos, bg=BG_COLOR, fg=BTN_COLOR, font=("Arial", 11, "bold")).grid(row=6, column=1, sticky="w", padx=8, pady=4)

tk.Label(tab_info, text="Última foto:", bg=BG_COLOR, fg=FG_COLOR).grid(row=7, column=0, sticky="e", padx=8, pady=4)
tk.Label(tab_info, textvariable=info_ultima, bg=BG_COLOR, fg=BTN_COLOR, font=("Arial", 11, "bold")).grid(row=7, column=1, sticky="w", padx=8, pady=4)

btn_edit_meta = tk.Button(tab_info, text="Editar…", command=_open_edit_meta,
                          bg=BTN_COLOR, fg=BTN_TEXT_COLOR, bd=0, font=("Arial", 11, "bold"), padx=10, pady=6)
btn_edit_meta.grid(row=8, column=0, columnspan=2, pady=(8, 12))

map_frame = tk.LabelFrame(tab_info, text="Mapa (futuro)", bg=BG_COLOR, fg=FG_COLOR, bd=2, labelanchor="n", font=("Arial", 11, "bold"))
map_frame.grid(row=9, column=0, columnspan=2, padx=8, pady=(4, 10), sticky="we")
tk.Label(map_frame, text="Aquí mostraremos un mapa cuando integremos GPS.", bg=BG_COLOR, fg=FG_COLOR).pack(padx=8, pady=8)

# 5) Sistema (nueva pestaña)
tab_sistema = tk.Frame(notebook, bg=BG_COLOR)
notebook.add(tab_sistema, text="Sistema")

lbl_temp = tk.Label(tab_sistema, text="Temp: —", bg=BG_COLOR, fg=FG_COLOR, font=("Arial", 11))
lbl_temp.pack(anchor="w", padx=12, pady=(10,4))
lbl_cpu = tk.Label(tab_sistema, text="CPU: —", bg=BG_COLOR, fg=FG_COLOR, font=("Arial", 11))
lbl_cpu.pack(anchor="w", padx=12, pady=4)
lbl_ram = tk.Label(tab_sistema, text="RAM: —", bg=BG_COLOR, fg=FG_COLOR, font=("Arial", 11))
lbl_ram.pack(anchor="w", padx=12, pady=4)
lbl_disk = tk.Label(tab_sistema, text="Libre en fotos: —", bg=BG_COLOR, fg=FG_COLOR, font=("Arial", 11))
lbl_disk.pack(anchor="w", padx=12, pady=4)
start_time = time.time()
lbl_uptime = tk.Label(tab_sistema, text="Uptime: 00:00:00", bg=BG_COLOR, fg=FG_COLOR, font=("Arial", 11))
lbl_uptime.pack(anchor="w", padx=12, pady=(4,10))

def _fmt_bytes(b):
    if b is None:
        return "—"
    for unit in ["B","KB","MB","GB","TB"]:
        if b < 1024:
            return f"{b:.0f} {unit}"
        b /= 1024
    return f"{b:.0f} PB"

def _fmt_pct(p):
    return "—" if p is None else f"{p:.0f}%"

def _fmt_temp(t):
    return "—" if t is None else f"{t:.1f}°C"

def update_system_info():
    try:
        t = _read_cpu_temp_c()
        cpu = _read_cpu_percent()
        ram = _read_mem_percent()
        free = _read_free_space_bytes(PHOTO_DIR)
        up = int(time.time() - start_time)
        h, rem = divmod(up, 3600)
        m, s = divmod(rem, 60)
        lbl_temp.config(text=f"Temp: {_fmt_temp(t)}")
        lbl_cpu.config(text=f"CPU: {_fmt_pct(cpu)}")
        lbl_ram.config(text=f"RAM: {_fmt_pct(ram)}")
        lbl_disk.config(text=f"Libre en fotos: {_fmt_bytes(free)}")
        lbl_uptime.config(text=f"Uptime: {h:02d}:{m:02d}:{s:02d}")
    except Exception:
        pass
    finally:
        root.after(2000, update_system_info)

update_system_info()

# ---------- Inicialización ----------
PHOTO_DIR = inicializar_directorio_fotos()
DRIVE_DIR = inicializar_directorio_drive()

update_stream_ui()
# Después de construir la UI por completo
def _after_ui_built():
    cfg = cargar_configuracion()
    # Sincroniza el combo con la config cargada
    try:
        resolution_var.set(current_resolution_label)
    except Exception:
        pass
    update_main_image()
    _refresh_info_tab()
    if _want_stream_on_start:
        # Aplica resolución preferida al arrancar stream
        wh = _find_res(current_resolution_label)
        if wh:
            _apply_camera_resolution(*wh)
        stream_on()
root.after(300, _after_ui_built)

def sync_auto():
    sincronizar_fotos()
    root.after(60000, sync_auto)

def on_close():
    guardar_configuracion()
    try:
        camera_manager.stop_stream()
        camera_manager.shutdown()
    except Exception:
        pass
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_close)

sync_auto()
root.mainloop()

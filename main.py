import tkinter as tk
from tkinter import messagebox
from tkinter import filedialog as fd
from PIL import Image, ImageTk, ImageOps, Image
import os
from datetime import datetime, timedelta
import json
import shutil
import subprocess
import sys
import cv2
from tkinter import ttk

import threading
import queue
import time
import tzlocal  # pip install tzlocal

from video_capture import camera_manager

CONFIG_FILE = "katcam_config.json"
CAM_INDEX = 0

# Colores corporativos
BG_COLOR = "#181818"
FG_COLOR = "#FFFFFF"
BTN_COLOR = "#FFD600"
BTN_TEXT_COLOR = "#181818"
BTN_BORDER_COLOR = "#FFD600"

# Estados de alto nivel
is_capturing = False
maniobra_running = False
timelapse_running = False
streaming = False                # estado global de transmisión
_want_stream_on_start = False    # reanudar transmisión si estaba activa al guardar

# -------------------- UTILIDADES --------------------

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

# -------------------- CONFIGURACIÓN PERSISTENTE --------------------

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

# ---- Persistencia de sliders (por cámara) ----
_cam_sliders = []  # (label, prop, minv, maxv, default, var, scale)

def _props_to_dict():
    d = {}
    for (_label, prop, _minv, _maxv, _default, var, _scale) in _cam_sliders:
        d[str(int(prop))] = float(var.get())
    return d

def _apply_saved_props(prop_map):
    changed = False
    for (_label, prop, _minv, _maxv, _default, var, _scale) in _cam_sliders:
        key = str(int(prop))
        if key in prop_map:
            val = prop_map[key]
            var.set(val)
            _ensure_prop_worker()
            try:
                _prop_queue.put_nowait((prop, val))
                changed = True
            except Exception:
                pass
    if changed:
        lbl_status_general.config(text="Parámetros de cámara restaurados del perfil.")

def guardar_configuracion():
    try:
        prev = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                prev = json.load(f)
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
            "cam_props": _props_to_dict(),
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        messagebox.showwarning("Config", f"No se pudo guardar configuración: {e}")

def cargar_configuracion():
    global CAM_INDEX, PHOTO_DIR, DRIVE_DIR, _want_stream_on_start

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

    # Restaurar sliders si están guardados (después de crear UI)
    saved_props = config.get("cam_props")
    if isinstance(saved_props, dict):
        root.after(600, lambda: _apply_saved_props(saved_props))

    if config.get("timelapse_activo", False):
        root.after(500, start_timelapse)

    _want_stream_on_start = bool(config.get("stream_activo", False))
    return config

# -------------------- SELECCIÓN DE CARPETAS --------------------

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

# -------------------- SINCRONIZACIÓN --------------------

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

# -------------------- IMAGEN --------------------

def get_last_photo():
    if not os.path.exists(PHOTO_DIR):
        return None
    fotos = sorted([f for f in os.listdir(PHOTO_DIR) if f.lower().endswith((".jpg", ".jpeg", ".png"))])
    if fotos:
        return os.path.join(PHOTO_DIR, fotos[-1])
    return None

def _placeholder_image(size=(600, 500)):
    img = Image.new("RGB", size, (64, 64, 64))
    return img

def update_main_image():
    try:
        last_photo = get_last_photo()
        if last_photo and os.path.exists(last_photo):
            img = Image.open(last_photo)
        else:
            try:
                img = Image.open("kreativerkatcam.jpg")
            except Exception:
                img = _placeholder_image()

        root.update_idletasks()
        win_width = root.winfo_width()
        win_height = root.winfo_height()
        img_width = int(win_width * 0.6)
        img_height = int(win_height * 0.6)
        img = ImageOps.contain(img, (img_width, img_height))
        photo = ImageTk.PhotoImage(img)
        lbl_main_image.config(image=photo)
        lbl_main_image.image = photo
    except Exception as e:
        lbl_status_general.config(text=f"Error mostrando imagen: {e}")

def update_stream_image(img):
    img = ImageOps.contain(img, (600, 500))
    photo = ImageTk.PhotoImage(img)
    lbl_main_image.config(image=photo)
    lbl_main_image.image = photo

def abrir_carpeta_fotos():
    path = os.path.realpath(PHOTO_DIR)
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])

# -------------------- STREAM: helpers y estado único --------------------

ui_refresh_ms = 40  # ~25 fps

def _tick_stream():
    if not streaming:
        return
    frame_rgb = camera_manager.get_frame_rgb()
    if frame_rgb is not None:
        img = Image.fromarray(frame_rgb)
        update_stream_image(img)
    if streaming:
        root.after(ui_refresh_ms, _tick_stream)

def update_stream_ui():
    """Refresca botón + label según el flag global `streaming`."""
    if streaming:
        lbl_status_transmision.config(text="Transmisión: ACTIVA")
        btn_switch_trans.config(text="Detener transmisión", bg="#FF5252", fg="#FFFFFF")
        toggle_transmision.on = True
    else:
        lbl_status_transmision.config(text="Transmisión: DETENIDA")
        btn_switch_trans.config(text="Iniciar transmisión", bg=BTN_COLOR, fg=BTN_TEXT_COLOR)
        toggle_transmision.on = False

def stream_on():
    """Enciende transmisión, sincroniza UI y arranca el loop de refresco."""
    global streaming
    if streaming:
        return
    streaming = True
    camera_manager.start_stream()
    update_stream_ui()
    lbl_status_general.config(text="Transmisión en directo")
    _tick_stream()

def stream_off():
    """Apaga transmisión, sincroniza UI y muestra la última foto."""
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

# -------------------- FOTO (coordina stream/timelapse) --------------------

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

            camera_manager.take_photo(
                dest_folder=PHOTO_DIR,
                prefer_sizes=None,
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

                if was_streaming:
                    if timelapse_running:
                        # Asegura que el loop/UI estén activos
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

# -------------------- TIMELAPSE --------------------

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

# -------------------- SLIDERS + Reset balanceado + Driver dialog --------------------

_prop_queue = queue.Queue()
_prop_worker_started = False

def _prop_worker():
    pending = {}
    last_apply = 0.0
    while True:
        try:
            pid, val = _prop_queue.get(timeout=0.1)
            pending[pid] = val
        except queue.Empty:
            pass
        now = time.time()
        if pending and (now - last_apply) >= 0.3:
            if not is_capturing and not maniobra_running:
                for pid, val in list(pending.items()):
                    camera_manager.set_property(pid, val)
                pending.clear()
                last_apply = now

def _ensure_prop_worker():
    global _prop_worker_started
    if not _prop_worker_started:
        t = threading.Thread(target=_prop_worker, daemon=True)
        t.start()
        _prop_worker_started = True

def on_slider_change(prop_id, var):
    _ensure_prop_worker()
    try:
        _prop_queue.put_nowait((prop_id, var.get()))
    except Exception:
        pass

def reset_camera_settings():
    # balanceado (medios) + auto expo/WB
    defaults = {
        cv2.CAP_PROP_BRIGHTNESS: 128,
        cv2.CAP_PROP_CONTRAST:   128,
        cv2.CAP_PROP_SATURATION: 128,
    }
    for (_label, prop, _minv, _maxv, _default, var, _scale) in _cam_sliders:
        if prop in defaults:
            var.set(defaults[prop])

    camera_manager.set_auto_modes(enable_exposure_auto=True, enable_wb_auto=True)

    _ensure_prop_worker()
    for pid, val in defaults.items():
        try:
            _prop_queue.put_nowait((pid, val))
        except Exception:
            pass

    lbl_status_general.config(text="Cámara balanceada (medios + auto expo/WB).")

def reset_driver_dialog():
    was_streaming = streaming
    if was_streaming:
        stream_off()
        root.update()
        time.sleep(0.05)
    camera_manager.show_driver_settings()
    if was_streaming:
        stream_on()
    lbl_status_general.config(text="Abierto diálogo del controlador; usa 'Default' y cierra.")

def set_camera_auto_modes():
    camera_manager.set_auto_modes(enable_exposure_auto=True, enable_wb_auto=True)
    lbl_status_general.config(text="Cámara en modos automáticos (expo/WB).")

# -------------------- UI --------------------

root = tk.Tk()
root.title("Katcam Pro")
try:
    root.iconbitmap("katcam_multi.ico")
except Exception:
    pass
root.configure(bg=BG_COLOR)
screen_width = root.winfo_screenwidth()
screen_height = root.winfo_screenheight()
win_width = int(screen_width * 0.8)
win_height = int(screen_height * 0.8)
x = (screen_width - win_width) // 2
y = (screen_height - win_height) // 2
root.geometry(f"{win_width}x{win_height}+{x}+{y}")
root.resizable(True, True)

# --- Menú superior ---
menubar = tk.Menu(root, bg=BG_COLOR, fg=FG_COLOR)
root.config(menu=menubar)

carpeta_menu = tk.Menu(menubar, tearoff=0, bg=BG_COLOR, fg=FG_COLOR)
menubar.add_cascade(label="Opciones", menu=carpeta_menu)
carpeta_menu.add_command(label="Cambiar carpeta de fotos...", command=cambiar_directorio_fotos)
carpeta_menu.add_command(label="Cambiar carpeta de Google Drive...", command=seleccionar_drive_manual)
carpeta_menu.add_separator()
carpeta_menu.add_command(label="Seleccionar cámara...", command=seleccionar_camara)

# Ventana de ajustes de inicio con Windows
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
        variable=autostart_var, onvalue=1, offvalue=0,
        command=on_toggle,
        bg=BG_COLOR, fg=FG_COLOR, selectcolor="black",
        activebackground=BG_COLOR, activeforeground=FG_COLOR,
        font=("Arial", 12, "bold")
    )
    chk.pack(padx=12, pady=8)

    # Estado inicial
    status_lbl.config(text="Estado: ACTIVADO" if autostart_var.get() else "Estado: DESACTIVADO")

ajustes_menu = tk.Menu(menubar, tearoff=0, bg=BG_COLOR, fg=FG_COLOR)
menubar.add_cascade(label="Ajustes", menu=ajustes_menu)
ajustes_menu.add_command(label="Inicio con Windows…", command=open_autostart_window)

# Logo
try:
    logo_img = Image.open("logo_katcam.png")
    logo_img = ImageOps.contain(logo_img, (350, 150))
    logo_photo = ImageTk.PhotoImage(logo_img)
    logo_label = tk.Label(root, image=logo_photo, bg=BG_COLOR)
    logo_label.pack(pady=(15, 10))
except Exception:
    pass

main_frame = tk.Frame(root, bg=BG_COLOR)
main_frame.pack(padx=10, pady=10)

# Columna 1: Imagen
image_frame = tk.Frame(main_frame, bg=BG_COLOR)
image_frame.grid(row=0, column=0, padx=10, pady=10, sticky="n")
tk.Label(image_frame, text="Última foto/Transmisión", font=("Arial", 16, "bold"), bg=BG_COLOR, fg=BTN_COLOR).pack(pady=5)
lbl_main_image = tk.Label(image_frame, bg="gray")
lbl_main_image.pack(pady=5)

# Columna 2: Botones
button_frame = tk.Frame(main_frame, bg=BG_COLOR)
button_frame.grid(row=0, column=1, padx=10, pady=10, sticky="n")
tk.Label(button_frame, text="", bg=BG_COLOR).pack(pady=5)

btn_take = tk.Button(
    button_frame, text="Sacar Foto", command=take_and_update, width=25, height=2,
    bg=BTN_COLOR, fg=BTN_TEXT_COLOR, activebackground=BTN_COLOR, activeforeground=BTN_TEXT_COLOR,
    bd=0, font=("Arial", 12, "bold"), padx=10, pady=10
)
btn_take.pack(pady=8)

def toggle_transmision():
    if streaming:
        stream_off()
    else:
        mostrar_transmision()

btn_switch_trans = tk.Button(
    button_frame, text="Iniciar transmisión", command=toggle_transmision, width=25, height=2,
    bg=BTN_COLOR, fg=BTN_TEXT_COLOR, activebackground=BTN_COLOR, activeforeground=BTN_TEXT_COLOR,
    bd=0, font=("Arial", 12, "bold"), padx=10, pady=10
)
btn_switch_trans.pack(pady=8)
toggle_transmision.on = False  # sólo informativo; lo mantiene update_stream_ui()

# Toggle timelapse
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

# Toggle maniobra
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
                return
            threading.Thread(
                target=lambda: camera_manager.take_photo(PHOTO_DIR, block_until_done=True, auto_resume_stream=False),
                daemon=True
            ).start()
            update_main_image()
            root.after(int(float(intervalo) * 1000), _tick)

        _tick()
        btn_maniobra.config(text="Detener Maniobra", bg="#FF5252", fg="#FFFFFF")
        toggle_maniobra.on = True

    else:
        maniobra_running = False
        lbl_status_general.config(text="Maniobra cancelada por el usuario.")
        btn_maniobra.config(text="Iniciar Maniobra", bg=BTN_COLOR, fg=BTN_TEXT_COLOR)
        toggle_maniobra.on = False

toggle_maniobra.on = False

btn_maniobra = tk.Button(
    button_frame, text="Iniciar Maniobra", command=toggle_maniobra, width=25, height=2,
    bg=BTN_COLOR, fg=BTN_TEXT_COLOR, activebackground=BTN_COLOR, activeforeground=BTN_TEXT_COLOR,
    bd=0, font=("Arial", 12, "bold"), padx=10, pady=10
)
btn_maniobra.pack(pady=8)

# Labels de estado
lbl_status_transmision = tk.Label(button_frame, text="Transmisión: DETENIDA", bg=BG_COLOR, fg=FG_COLOR, font=("Arial", 11, "bold"))
lbl_status_transmision.pack(pady=(5, 2))
lbl_status_timelapse = tk.Label(button_frame, text="Timelapse: DETENIDO", bg=BG_COLOR, fg=FG_COLOR, font=("Arial", 11, "bold"))
lbl_status_timelapse.pack(pady=(0, 2))
lbl_status_general = tk.Label(button_frame, text="Listo", bg=BG_COLOR, fg=FG_COLOR, font=("Arial", 10))
lbl_status_general.pack(pady=(0, 5))

# Reloj
def update_clock():
    local_timezone = tzlocal.get_localzone()
    now = datetime.now(local_timezone)
    lbl_clock.config(text=now.strftime("%H:%M:%S") + f" ({local_timezone})")
    root.after(1000, update_clock)

lbl_clock = tk.Label(button_frame, text="", bg=BG_COLOR, fg=BTN_COLOR, font=("Arial", 13, "bold"))
lbl_clock.pack(pady=(0, 10))
update_clock()

btn_open_folder = tk.Button(
    button_frame, text="Abrir carpeta de fotos", command=abrir_carpeta_fotos, width=25, height=2,
    bg=BG_COLOR, fg=BTN_COLOR, activebackground=BG_COLOR, activeforeground=BTN_COLOR,
    bd=2, highlightbackground=BTN_BORDER_COLOR, highlightcolor=BTN_BORDER_COLOR,
    font=("Arial", 12, "bold"), padx=10, pady=10
)
btn_open_folder.pack(pady=10)

# Columna 3: Configuración (pestañas)
config_frame = tk.Frame(main_frame, bg=BG_COLOR)
config_frame.grid(row=0, column=2, padx=10, pady=10, sticky="n")

tk.Label(config_frame, text="Configuraciones", font=("Arial", 16, "bold"), bg=BG_COLOR, fg=BTN_COLOR).pack(pady=(0, 10))
notebook = ttk.Notebook(config_frame)
notebook.pack(fill="both", expand=True)

# --- Pestaña Timelapse ---
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

# --- Pestaña Cámara ---
tab_camara = tk.Frame(notebook, bg=BG_COLOR)
notebook.add(tab_camara, text="Cámara")

tk.Label(tab_camara, text="Configuración de Cámara", font=("Arial", 16, "bold"), bg=BG_COLOR, fg=FG_COLOR).pack(pady=10)

cam_props = [
    ("Brillo", cv2.CAP_PROP_BRIGHTNESS, 0, 255, 128),
    ("Contraste", cv2.CAP_PROP_CONTRAST, 0, 255, 128),
    ("Saturación", cv2.CAP_PROP_SATURATION, 0, 255, 128),
    ("Exposición", cv2.CAP_PROP_EXPOSURE, -8, 0, -4),
    ("Balance Blancos", cv2.CAP_PROP_WHITE_BALANCE_BLUE_U, 2000, 6500, 4000),
]
for (label, prop, minv, maxv, default) in cam_props:
    tk.Label(tab_camara, text=label, bg=BG_COLOR, fg=FG_COLOR).pack(anchor="w", padx=10)
    var = tk.DoubleVar(value=default)
    scale = tk.Scale(
        tab_camara, from_=minv, to=maxv, orient="horizontal", variable=var,
        bg=BG_COLOR, fg=FG_COLOR, troughcolor=BTN_COLOR, highlightthickness=0,
        command=lambda v, p=prop, var=var: on_slider_change(p, var)
    )
    scale.pack(fill="x", padx=10, pady=2)
    _cam_sliders.append((label, prop, minv, maxv, default, var, scale))

btn_reset_cam = tk.Button(
    tab_camara, text="Reset cámara (balanceado)", command=reset_camera_settings,
    bg=BTN_COLOR, fg=BTN_TEXT_COLOR, bd=0, font=("Arial", 11, "bold"),
    padx=10, pady=8
)
btn_reset_cam.pack(pady=6, padx=10, anchor="e")

btn_auto_modes = tk.Button(
    tab_camara, text="Auto (expo/WB)", command=set_camera_auto_modes,
    bg="#9CCC65", fg="#181818", bd=0, font=("Arial", 11, "bold"), padx=10, pady=8
)
btn_auto_modes.pack(pady=6, padx=10, anchor="e")

btn_reset_driver = tk.Button(
    tab_camara, text="Reset (valores del controlador)", command=reset_driver_dialog,
    bg="#FFB300", fg="#181818", bd=0, font=("Arial", 11, "bold"), padx=10, pady=8
)
btn_reset_driver.pack(pady=6, padx=10, anchor="e")

# --- Pestaña Maniobra ---
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

# -------------------- INICIALIZACIÓN --------------------

# 1) Directorios
PHOTO_DIR = inicializar_directorio_fotos()
DRIVE_DIR = inicializar_directorio_drive()

# 2) Construimos UI y luego cargamos config (para poder aplicar sliders)
update_stream_ui()  # arranca consistente: "Iniciar transmisión" / "Detenida"
cargar_configuracion()
update_main_image()

# Si estaba activa la transmisión antes de salir, reanudar
def _resume_stream_if_needed():
    if _want_stream_on_start:
        stream_on()
root.after(800, _resume_stream_if_needed)

# 3) Sincronización automática
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

resize_job = None
def on_resize(event):
    global resize_job
    if resize_job is not None:
        root.after_cancel(resize_job)
    resize_job = root.after(300, update_main_image)

root.bind("<Configure>", on_resize)

sync_auto()
root.mainloop()
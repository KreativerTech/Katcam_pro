import tkinter as tk
from tkinter import messagebox
from tkinter import filedialog as fd
from camera import take_photo  # Debe aceptar la ruta destino: take_photo(PHOTO_DIR)
from PIL import Image, ImageTk, ImageOps
import os
from datetime import datetime, timedelta
import json
import shutil
import subprocess
import sys
import cv2

CONFIG_FILE = "katcam_config.json"
CAM_INDEX = 0

# Colores corporativos
BG_COLOR = "#181818"
FG_COLOR = "#FFFFFF"
BTN_COLOR = "#FFD600"
BTN_TEXT_COLOR = "#181818"
BTN_BORDER_COLOR = "#FFD600"

# -------------------- UTILIDADES --------------------

def has_write_access(path: str) -> bool:
    """
    Devuelve True si se puede escribir en 'path'. Intenta crear y borrar un archivo temporal.
    """
    try:
        os.makedirs(path, exist_ok=True)
        testfile = os.path.join(path, ".katcam_write_test")
        with open(testfile, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(testfile)
        return True
    except Exception:
        return False

# -------------------- CONFIGURACIÓN PERSISTENTE --------------------

def listar_camaras_disponibles(max_cams=5):
    disponibles = []
    for i in range(max_cams):
        cap = cv2.VideoCapture(i)
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
    # Ventana simple para elegir
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
        win.destroy()
        messagebox.showinfo("Cámara", f"Cámara seleccionada: {CAM_INDEX}")
    tk.Button(win, text="Seleccionar", command=set_cam, bg=BTN_COLOR, fg=BTN_TEXT_COLOR, font=("Arial", 10, "bold")).pack(pady=10)

def guardar_configuracion():
    try:
        config = {
            "frecuencia": entry_freq.get(),
            "dias": [var.get() for var in day_vars],
            "hora_inicio": entry_hour_start.get(),
            "hora_fin": entry_hour_end.get(),
            "timelapse_activo": timelapse_running,
            "photo_dir": PHOTO_DIR,
            "cam_index": CAM_INDEX
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        messagebox.showwarning("Config", f"No se pudo guardar configuración: {e}")

def cargar_configuracion():
    """
    CORREGIDO: ahora primero lee el archivo y recién después usa 'config'.
    Además actualiza PHOTO_DIR si corresponde y rellena la UI.
    """
    global CAM_INDEX, PHOTO_DIR

    if not os.path.exists(CONFIG_FILE):
        return None

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        messagebox.showwarning("Config", f"No se pudo leer la configuración: {e}")
        return None

    # Aplicar a variables globales
    CAM_INDEX = config.get("cam_index", 0)

    photo_dir_saved = config.get("photo_dir")
    if photo_dir_saved and os.path.exists(photo_dir_saved):
        PHOTO_DIR = photo_dir_saved

    # Rellenar UI (si los widgets existen)
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
        # Si todavía no existe la UI, ignoramos el rellenado
        pass

    if config.get("timelapse_activo", False):
        # Espera a que la UI esté lista
        root.after(500, start_timelapse)

    return config

# -------------------- SELECCIÓN DE CARPETA DE FOTOS --------------------

def seleccionar_directorio_manual():
    carpeta = fd.askdirectory(title="Selecciona la carpeta para guardar fotos")
    if carpeta:
        return carpeta
    return None

def inicializar_directorio_fotos():
    """
    Devuelve la carpeta donde guardar fotos. Intenta:
    1) Config previa válida
    2) Pendrive con carpeta 'FOTOS' con permiso de escritura
    3) Google Drive/KatcamAustralia/fotos con permiso de escritura
    4) Selección manual
    """
    # 1) Config previa
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            p = cfg.get("photo_dir")
            if p and os.path.exists(p) and has_write_access(p):
                return p
    except Exception:
        pass

    # 2) Pendrive
    pendrive = encontrar_pendrive()
    if pendrive:
        return pendrive

    # 3) Google Drive
    drive = encontrar_google_drive()
    if drive:
        return drive

    # 4) Manual
    respuesta = messagebox.askyesno(
        "Seleccionar carpeta",
        "No se encontró el pendrive 'FOTOS' ni la carpeta de Google Drive.\n¿Deseas seleccionar una carpeta manualmente?"
    )
    if respuesta:
        ruta = seleccionar_directorio_manual()
        if ruta and has_write_access(ruta):
            return ruta
        else:
            messagebox.showerror("Permisos", "No hay permiso de escritura en la carpeta elegida.")
            sys.exit(1)
    else:
        messagebox.showerror("Error", "No se puede continuar sin una carpeta para guardar fotos.")
        sys.exit(1)

def cambiar_directorio_fotos():
    global PHOTO_DIR
    nueva = seleccionar_directorio_manual()
    if nueva and has_write_access(nueva):
        PHOTO_DIR = nueva
        guardar_configuracion()
        messagebox.showinfo("Ruta actualizada", f"Carpeta de fotos cambiada a:\n{PHOTO_DIR}")
        update_main_image()
    elif nueva:
        messagebox.showerror("Permisos", "No hay permiso de escritura en la carpeta seleccionada.")

# -------------------- DETECCIÓN DE UNIDADES --------------------

def encontrar_pendrive():
    """
    Busca unidades D:..Z: y usa/crea 'FOTOS' si hay permiso de escritura.
    Evita reventar con 'Acceso denegado'.
    """
    for letra in "DEFGHIJKLMNOPQRSTUVWXYZ":
        unidad = f"{letra}:\\"
        if os.path.exists(unidad):
            fotos_path = os.path.join(unidad, "FOTOS")
            try:
                os.makedirs(fotos_path, exist_ok=True)
                if has_write_access(fotos_path):
                    return fotos_path
            except Exception:
                # Sin permisos en esa unidad, probamos la siguiente
                continue
    return None

def encontrar_google_drive():
    """
    Busca ubicaciones típicas de Google Drive y devuelve la carpeta
    '.../KatcamAustralia/fotos' si existe o si puede crearse con permisos.
    """
    posibles_nombres = ["Mi unidad", "Google Drive"]
    for letra in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        unidad = f"{letra}:\\"
        if not os.path.exists(unidad):
            continue
        for nombre in posibles_nombres:
            ruta_base = os.path.join(unidad, nombre)
            ruta = os.path.join(ruta_base, "KatcamAustralia", "fotos")
            try:
                os.makedirs(ruta, exist_ok=True)
                if has_write_access(ruta):
                    return ruta
            except Exception:
                continue
    return None

# -------------------- SINCRONIZACIÓN --------------------

def sincronizar_fotos():
    try:
        drive_dir = encontrar_google_drive()
        if not drive_dir:
            lbl_status.config(text="No se encontró Google Drive para sincronizar.")
            return
        if not os.path.exists(PHOTO_DIR):
            lbl_status.config(text="Carpeta de fotos inválida.")
            return

        fotos_pendrive = sorted([f for f in os.listdir(PHOTO_DIR) if f.lower().endswith((".jpg", ".jpeg", ".png"))])
        fotos_drive = set(os.listdir(drive_dir))
        nuevas = [f for f in fotos_pendrive if f not in fotos_drive]

        for f in nuevas:
            shutil.copy2(os.path.join(PHOTO_DIR, f), os.path.join(drive_dir, f))

        if nuevas:
            lbl_status.config(text=f"Sincronizadas {len(nuevas)} fotos al Drive.")
        else:
            lbl_status.config(text="No hay fotos nuevas para sincronizar.")
    except Exception as e:
        lbl_status.config(text=f"Error al sincronizar: {e}")

# -------------------- FUNCIONES DE IMAGEN --------------------

def get_last_photo():
    if not os.path.exists(PHOTO_DIR):
        return None
    fotos = sorted([f for f in os.listdir(PHOTO_DIR) if f.lower().endswith((".jpg", ".jpeg", ".png"))])
    if fotos:
        return os.path.join(PHOTO_DIR, fotos[-1])
    return None

def _placeholder_image(size=(600, 500)):
    # Imagen gris como placeholder si no hay archivo por defecto
    img = Image.new("RGB", size, (64, 64, 64))
    return img

def update_main_image():
    try:
        last_photo = get_last_photo()
        if last_photo and os.path.exists(last_photo):
            img = Image.open(last_photo)
        else:
            # Intenta cargar tu imagen por defecto, si falla usa placeholder
            try:
                img = Image.open("kreativerkatcam.jpg")
            except Exception:
                img = _placeholder_image()
        img = ImageOps.contain(img, (600, 500))
        photo = ImageTk.PhotoImage(img)
        lbl_main_image.config(image=photo)
        lbl_main_image.image = photo
    except Exception as e:
        lbl_status.config(text=f"Error mostrando imagen: {e}")

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

# -------------------- FUNCIONES DE CONTROL --------------------

streaming = False
cap_stream = None

def take_and_update():
    global streaming
    was_streaming = streaming
    if streaming:
        detener_transmision()
        root.update()
    take_photo(PHOTO_DIR)  # Pasa la ruta actual (asegúrate que camera.take_photo acepta la ruta)
    update_main_image()
    if was_streaming:
        mostrar_transmision()

def mostrar_transmision():
    global streaming, cap_stream
    if streaming:
        return
    streaming = True
    cap_stream = cv2.VideoCapture(CAM_INDEX)
    lbl_status.config(text="Transmisión en directo")
    actualizar_stream()

def actualizar_stream():
    global streaming, cap_stream
    if not streaming or cap_stream is None:
        return
    ret, frame = cap_stream.read()
    if ret:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame)
        update_stream_image(img)
    if streaming:
        root.after(30, actualizar_stream)

def detener_transmision():
    global streaming, cap_stream
    streaming = False
    if cap_stream is not None:
        cap_stream.release()
        cap_stream = None
    lbl_status.config(text="Transmisión detenida")
    update_main_image()

# -------------------- TIMELAPSE --------------------

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
        lbl_status.config(text=f"Error en parámetros: {e}")
        return
    lbl_status.config(text="Timelapse iniciado")
    schedule_next_capture()

def stop_timelapse():
    global timelapse_running
    timelapse_running = False
    guardar_configuracion()
    lbl_status.config(text="Timelapse detenido")

def schedule_next_capture():
    global timelapse_running, next_capture_time, interval_ms, days_selected, hour_start, hour_end
    if not timelapse_running:
        return
    now = datetime.now()
    dia_actual = now.strftime("%A").lower()
    dias_es = {
        "monday": "lunes", "tuesday": "martes", "wednesday": "miércoles",
        "thursday": "jueves", "friday": "viernes", "saturday": "sábado", "sunday": "domingo"
    }
    dia_actual_es = dias_es.get(dia_actual, dia_actual)
    if days_selected and dia_actual_es not in days_selected:
        root.after(interval_ms, schedule_next_capture)
        return
    if hour_start and hour_end:
        hora_actual = now.strftime("%H:%M")
        if not (hour_start <= hora_actual <= hour_end):
            root.after(interval_ms, schedule_next_capture)
            return
    if now >= next_capture_time:
        take_and_update()
        next_capture_time = now + timedelta(milliseconds=interval_ms)
    root.after(interval_ms, schedule_next_capture)

# -------------------- INICIALIZACIÓN DE INTERFAZ --------------------

root = tk.Tk()
root.title("Katcam Pro")
try:
    root.iconbitmap("katcam_multi.ico")
except Exception:
    pass
root.configure(bg=BG_COLOR)

# Menú para cambiar carpeta de fotos
menubar = tk.Menu(root, bg=BG_COLOR, fg=FG_COLOR)
root.config(menu=menubar)
carpeta_menu = tk.Menu(menubar, tearoff=0, bg=BG_COLOR, fg=FG_COLOR)
menubar.add_cascade(label="Opciones", menu=carpeta_menu)
carpeta_menu.add_command(label="Cambiar carpeta de fotos...", command=cambiar_directorio_fotos)
carpeta_menu.add_separator()
carpeta_menu.add_command(label="Seleccionar cámara...", command=seleccionar_camara)

# Logo
try:
    logo_img = Image.open("logo_katcam.png")
    logo_img = ImageOps.contain(logo_img, (350, 150))
    logo_photo = ImageTk.PhotoImage(logo_img)
    logo_label = tk.Label(root, image=logo_photo, bg=BG_COLOR)
    logo_label.pack(pady=(15, 10))
except Exception:
    # Si no hay logo, no se cae la app
    pass

main_frame = tk.Frame(root, bg=BG_COLOR)
main_frame.pack(padx=10, pady=10)

# Columna 1: Imagen
image_frame = tk.Frame(main_frame, bg=BG_COLOR)
image_frame.grid(row=0, column=0, padx=10, pady=10, sticky="n")
tk.Label(image_frame, text="Última foto/Transmisión", font=("Arial", 12, "bold"), bg=BG_COLOR, fg=FG_COLOR).pack(pady=5)
lbl_main_image = tk.Label(image_frame, bg="gray")
lbl_main_image.pack(pady=5)

# Columna 2: Botones
button_frame = tk.Frame(main_frame, bg=BG_COLOR)
button_frame.grid(row=0, column=1, padx=10, pady=10, sticky="n")
tk.Label(button_frame, text="", bg=BG_COLOR).pack(pady=5)  # Título vacío para alinear

btn_take = tk.Button(
    button_frame, text="Sacar Foto", command=take_and_update, width=25, height=2,
    bg=BTN_COLOR, fg=BTN_TEXT_COLOR, activebackground=BTN_COLOR, activeforeground=BTN_TEXT_COLOR,
    bd=0, font=("Arial", 12, "bold"), padx=10, pady=10
)
btn_take.pack(pady=8)

btn_stream = tk.Button(
    button_frame, text="Iniciar transmisión", command=mostrar_transmision, width=25, height=2,
    bg=BTN_COLOR, fg=BTN_TEXT_COLOR, activebackground=BTN_COLOR, activeforeground=BTN_TEXT_COLOR,
    bd=0, font=("Arial", 12, "bold"), padx=10, pady=10
)
btn_stream.pack(pady=8)

btn_stop_stream = tk.Button(
    button_frame, text="Detener transmisión", command=detener_transmision, width=25, height=2,
    bg=BTN_COLOR, fg=BTN_TEXT_COLOR, activebackground=BTN_COLOR, activeforeground=BTN_TEXT_COLOR,
    bd=0, font=("Arial", 12, "bold"), padx=10, pady=10
)
btn_stop_stream.pack(pady=8)

btn_open_folder = tk.Button(
    button_frame, text="Abrir carpeta de fotos", command=abrir_carpeta_fotos, width=25, height=2,
    bg=BG_COLOR, fg=BTN_COLOR, activebackground=BG_COLOR, activeforeground=BTN_COLOR,
    bd=2, highlightbackground=BTN_BORDER_COLOR, highlightcolor=BTN_BORDER_COLOR,
    font=("Arial", 12, "bold"), padx=10, pady=10
)
btn_open_folder.pack(pady=8)

lbl_status = tk.Label(button_frame, text="", bg=BG_COLOR, fg=FG_COLOR)
lbl_status.pack(pady=5)

# Columna 3: Configuración timelapse
config_frame = tk.Frame(main_frame, bg=BG_COLOR)
config_frame.grid(row=0, column=2, padx=10, pady=10, sticky="n")
tk.Label(config_frame, text="Configuración Timelapse", font=("Arial", 12, "bold"), bg=BG_COLOR, fg=FG_COLOR).grid(row=0, column=0, columnspan=2, pady=5)
tk.Label(config_frame, text="Frecuencia (minutos):", bg=BG_COLOR, fg=FG_COLOR).grid(row=1, column=0, sticky="e")
entry_freq = tk.Entry(config_frame)
entry_freq.grid(row=1, column=1)
entry_freq.insert(0, "10")

tk.Label(config_frame, text="Días a funcionar:", bg=BG_COLOR, fg=FG_COLOR).grid(row=2, column=0, sticky="ne")
dias_lista = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
day_vars = [tk.BooleanVar(value=True) for _ in dias_lista]
days_frame = tk.Frame(config_frame, bg=BG_COLOR)
days_frame.grid(row=2, column=1, sticky="w")
for i, dia in enumerate(dias_lista):
    tk.Checkbutton(
        days_frame, text=dia.capitalize(), variable=day_vars[i],
        bg=BG_COLOR, fg=FG_COLOR, selectcolor=BTN_COLOR,
        activebackground=BG_COLOR, activeforeground=BTN_COLOR
    ).pack(anchor="w")

tk.Label(config_frame, text="Hora inicio (HH:MM):", bg=BG_COLOR, fg=FG_COLOR).grid(row=3, column=0, sticky="e")
entry_hour_start = tk.Entry(config_frame)
entry_hour_start.grid(row=3, column=1)
entry_hour_start.insert(0, "08:00")

tk.Label(config_frame, text="Hora fin (HH:MM):", bg=BG_COLOR, fg=FG_COLOR).grid(row=4, column=0, sticky="e")
entry_hour_end = tk.Entry(config_frame)
entry_hour_end.grid(row=4, column=1)
entry_hour_end.insert(0, "18:00")

btn_start = tk.Button(
    config_frame, text="Iniciar Timelapse", command=start_timelapse, width=25, height=2,
    bg=BTN_COLOR, fg=BTN_TEXT_COLOR, activebackground=BTN_COLOR, activeforeground=BTN_TEXT_COLOR,
    bd=0, font=("Arial", 12, "bold"), padx=10, pady=10
)
btn_start.grid(row=5, column=0, columnspan=2, pady=5)

btn_stop = tk.Button(
    config_frame, text="Detener Timelapse", command=stop_timelapse, width=25, height=2,
    bg=BTN_COLOR, fg=BTN_TEXT_COLOR, activebackground=BTN_COLOR, activeforeground=BTN_TEXT_COLOR,
    bd=0, font=("Arial", 12, "bold"), padx=10, pady=10
)
btn_stop.grid(row=6, column=0, columnspan=2, pady=5)

# -------------------- INICIALIZACIÓN DE VARIABLES Y ARRANQUE --------------------

timelapse_running = False
next_capture_time = None
interval_ms = 600000
dias_lista = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
days_selected = dias_lista.copy()
hour_start = "08:00"
hour_end = "18:00"

# 1) Elegir carpeta de fotos con permisos
PHOTO_DIR = inicializar_directorio_fotos()

# 2) Cargar configuración (CORREGIDO)
cargar_configuracion()

# 3) Pintar imagen inicial
update_main_image()

# 4) Sincronización automática cada 60s
def sync_auto():
    sincronizar_fotos()
    root.after(60000, sync_auto)

def on_close():
    guardar_configuracion()
    root.destroy()
root.protocol("WM_DELETE_WINDOW", on_close)

sync_auto()
root.mainloop()

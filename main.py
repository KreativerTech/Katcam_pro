import tkinter as tk
from tkinter import messagebox
from tkinter import filedialog as fd
from camera import take_photo
from PIL import Image, ImageTk
import os
from datetime import datetime, timedelta
import json
import shutil
import subprocess
import sys

CONFIG_FILE = "katcam_config.json"

# Colores corporativos
BG_COLOR = "#181818"
FG_COLOR = "#FFFFFF"
BTN_COLOR = "#FFD600"
BTN_TEXT_COLOR = "#181818"
BTN_BORDER_COLOR = "#FFD600"

# -------------------- CONFIGURACIÓN PERSISTENTE --------------------

def guardar_configuracion():
    config = {
        "frecuencia": entry_freq.get(),
        "dias": [var.get() for var in day_vars],
        "hora_inicio": entry_hour_start.get(),
        "hora_fin": entry_hour_end.get(),
        "timelapse_activo": timelapse_running,
        "photo_dir": PHOTO_DIR
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)

def cargar_configuracion():
    if not os.path.exists(CONFIG_FILE):
        return None
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
    entry_freq.delete(0, "end")
    entry_freq.insert(0, config.get("frecuencia", "10"))
    for i, valor in enumerate(config.get("dias", [True]*7)):
        day_vars[i].set(valor)
    entry_hour_start.delete(0, "end")
    entry_hour_start.insert(0, config.get("hora_inicio", "08:00"))
    entry_hour_end.delete(0, "end")
    entry_hour_end.insert(0, config.get("hora_fin", "18:00"))
    if config.get("timelapse_activo", False):
        root.after(500, start_timelapse)
    return config

# -------------------- SELECCIÓN DE CARPETA DE FOTOS --------------------

def seleccionar_directorio_manual():
    carpeta = fd.askdirectory(title="Selecciona la carpeta para guardar fotos")
    if carpeta:
        return carpeta
    return None

def inicializar_directorio_fotos():
    config = None
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            try:
                config = json.load(f)
            except Exception:
                config = None
    if config and "photo_dir" in config and os.path.exists(config["photo_dir"]):
        return config["photo_dir"]

    pendrive = encontrar_pendrive()
    drive = encontrar_google_drive()
    ruta = None

    if pendrive:
        ruta = pendrive
    elif drive:
        ruta = drive
    else:
        respuesta = messagebox.askyesno(
            "Seleccionar carpeta",
            "No se encontró el pendrive 'FOTOS' ni la carpeta de Google Drive.\n¿Deseas seleccionar una carpeta manualmente?"
        )
        if respuesta:
            ruta = seleccionar_directorio_manual()
        else:
            messagebox.showerror("Error", "No se puede continuar sin una carpeta para guardar fotos.")
            sys.exit(1)
    return ruta

def cambiar_directorio_fotos():
    global PHOTO_DIR
    nueva = seleccionar_directorio_manual()
    if nueva:
        PHOTO_DIR = nueva
        guardar_configuracion()
        messagebox.showinfo("Ruta actualizada", f"Carpeta de fotos cambiada a:\n{PHOTO_DIR}")
        update_main_image()

# -------------------- DETECCIÓN DE UNIDADES --------------------

def encontrar_pendrive():
    for letra in "DEFGHIJKLMNOPQRSTUVWXYZ":
        unidad = f"{letra}:\\"
        if os.path.exists(unidad):
            fotos_path = os.path.join(unidad, "FOTOS")
            if not os.path.exists(fotos_path):
                try:
                    os.makedirs(fotos_path)
                    print(f"Carpeta FOTOS creada en {unidad}")
                except Exception as e:
                    print(f"No se pudo crear la carpeta FOTOS en {unidad}: {e}")
            if os.path.exists(fotos_path) and os.path.isdir(fotos_path):
                return fotos_path
    return None

def encontrar_google_drive():
    posibles_nombres = ["Mi unidad", "Google Drive"]
    for letra in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        unidad = f"{letra}:\\"
        if os.path.exists(unidad):
            for nombre in posibles_nombres:
                ruta = os.path.join(unidad, nombre, "KatcamAustralia", "fotos")
                if os.path.exists(ruta):
                    return ruta
    return None

# -------------------- SINCRONIZACIÓN --------------------

def sincronizar_fotos():
    drive_dir = encontrar_google_drive()
    if not drive_dir:
        lbl_status.config(text="No se encontró Google Drive para sincronizar.")
        return
    fotos_pendrive = sorted(os.listdir(PHOTO_DIR))
    fotos_drive = set(os.listdir(drive_dir))
    nuevas = [f for f in fotos_pendrive if f not in fotos_drive and f.lower().endswith(".jpg")]
    for f in nuevas:
        shutil.copy2(os.path.join(PHOTO_DIR, f), os.path.join(drive_dir, f))
    if nuevas:
        lbl_status.config(text=f"Sincronizadas {len(nuevas)} fotos al Drive.")
    else:
        lbl_status.config(text="No hay fotos nuevas para sincronizar.")

# -------------------- FUNCIONES DE IMAGEN --------------------

def get_last_photo():
    fotos = sorted(os.listdir(PHOTO_DIR))
    if fotos:
        return os.path.join(PHOTO_DIR, fotos[-1])
    return None

def update_main_image():
    last_photo = get_last_photo()
    if last_photo and os.path.exists(last_photo):
        img = Image.open(last_photo)
        img = img.resize((600, 500))
        photo = ImageTk.PhotoImage(img)
        lbl_main_image.config(image=photo)
        lbl_main_image.image = photo
    else:
        lbl_main_image.config(image="")

def update_stream_image(img):
    img = img.resize((600, 500))
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
    take_photo(PHOTO_DIR)  # Pasa la ruta actual
    update_main_image()
    if was_streaming:
        mostrar_transmision()

def mostrar_transmision():
    global streaming, cap_stream
    import cv2
    if streaming:
        return
    streaming = True
    cap_stream = cv2.VideoCapture(0)
    lbl_status.config(text="Transmisión en directo")
    actualizar_stream()

def actualizar_stream():
    global streaming, cap_stream
    import cv2
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
        freq_str = entry_freq.get()
        hour_start_str = entry_hour_start.get()
        hour_end_str = entry_hour_end.get()
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
root.iconbitmap("katcam_multi.ico")
root.configure(bg=BG_COLOR)

# Menú para cambiar carpeta de fotos
menubar = tk.Menu(root, bg=BG_COLOR, fg=FG_COLOR)
root.config(menu=menubar)
carpeta_menu = tk.Menu(menubar, tearoff=0, bg=BG_COLOR, fg=FG_COLOR)
menubar.add_cascade(label="Opciones", menu=carpeta_menu)
carpeta_menu.add_command(label="Cambiar carpeta de fotos...", command=cambiar_directorio_fotos)

# Logo
logo_img = Image.open("logo_katcam.png")
logo_img = logo_img.resize((350, 150))
logo_photo = ImageTk.PhotoImage(logo_img)
logo_label = tk.Label(root, image=logo_photo, bg=BG_COLOR)
logo_label.pack(pady=(15, 10))

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

PHOTO_DIR = inicializar_directorio_fotos()
cargar_configuracion()
update_main_image()

def sync_auto():
    sincronizar_fotos()
    root.after(60000, sync_auto)

sync_auto()
root.mainloop()

import tkinter as tk
from camera import take_photo
from PIL import Image, ImageTk
import os
from datetime import datetime, timedelta

PHOTO_DIR = "I:/Mi unidad/KatcamAustralia/fotos"  # Usa la misma ruta que en camera.py

def get_last_photo():
    fotos = sorted(os.listdir(PHOTO_DIR))
    if fotos:
        return os.path.join(PHOTO_DIR, fotos[-1])
    return None

def update_photo():
    last_photo = get_last_photo()
    if last_photo and os.path.exists(last_photo):
        img = Image.open(last_photo)
        img = img.resize((400, 300))  # Ajusta el tamaño según tu preferencia
        photo = ImageTk.PhotoImage(img)
        lbl_photo.config(image=photo)
        lbl_photo.image = photo  # Evita que la imagen se elimine por el recolector de basura

def take_and_update():
    take_photo()
    update_photo()

def start_timelapse():
    global timelapse_running, next_capture_time, end_time, interval_ms
    timelapse_running = True
    try:
        start_str = entry_start.get()
        end_str = entry_end.get()
        freq_str = entry_freq.get()
        # Fecha de inicio
        if start_str:
            next_capture_time = datetime.strptime(start_str, "%Y-%m-%d %H:%M")
        else:
            next_capture_time = datetime.now()
        # Fecha de término
        if end_str:
            end_time = datetime.strptime(end_str, "%Y-%m-%d %H:%M")
        else:
            end_time = None
        # Frecuencia en segundos
        interval_ms = int(float(freq_str) * 1000)
    except Exception as e:
        lbl_status.config(text=f"Error en parámetros: {e}")
        return
    lbl_status.config(text="Timelapse iniciado")
    schedule_next_capture()

def stop_timelapse():
    global timelapse_running
    timelapse_running = False
    lbl_status.config(text="Timelapse detenido")

def schedule_next_capture():
    global timelapse_running, next_capture_time, end_time, interval_ms
    if not timelapse_running:
        return
    now = datetime.now()
    if now >= next_capture_time:
        take_and_update()
        next_capture_time = now + timedelta(milliseconds=interval_ms)
    if end_time and now >= end_time:
        stop_timelapse()
    else:
        root.after(interval_ms, schedule_next_capture)

root = tk.Tk()
root.title("Katcam Pro")

lbl_photo = tk.Label(root)
lbl_photo.pack(pady=10)

btn_take = tk.Button(root, text="Sacar Foto", command=take_and_update, width=25, height=2)
btn_take.pack(pady=10)

# Parámetros de timelapse
frame_params = tk.Frame(root)
frame_params.pack(pady=10)

tk.Label(frame_params, text="Inicio (YYYY-MM-DD HH:MM):").grid(row=0, column=0)
entry_start = tk.Entry(frame_params)
entry_start.grid(row=0, column=1)

tk.Label(frame_params, text="Fin (YYYY-MM-DD HH:MM, vacío = indefinido):").grid(row=1, column=0)
entry_end = tk.Entry(frame_params)
entry_end.grid(row=1, column=1)

tk.Label(frame_params, text="Frecuencia (segundos):").grid(row=2, column=0)
entry_freq = tk.Entry(frame_params)
entry_freq.grid(row=2, column=1)
entry_freq.insert(0, "10")  # Valor por defecto

btn_start = tk.Button(root, text="Iniciar Timelapse", command=start_timelapse, width=25, height=2)
btn_start.pack(pady=5)

btn_stop = tk.Button(root, text="Detener Timelapse", command=stop_timelapse, width=25, height=2)
btn_stop.pack(pady=5)

lbl_status = tk.Label(root, text="")
lbl_status.pack(pady=5)

update_photo()  # Muestra la última foto al iniciar

# Variables globales para timelapse
timelapse_running = False
next_capture_time = None
end_time = None
interval_ms = 10000

root.mainloop()

import tkinter as tk
from camera import take_photo
from PIL import Image, ImageTk
import os
from datetime import datetime, timedelta

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

PHOTO_DIR = encontrar_google_drive()
if PHOTO_DIR is None:
    raise FileNotFoundError("No se encontró la carpeta de Google Drive 'KatcamAustralia/fotos' en ninguna unidad.")
os.makedirs(PHOTO_DIR, exist_ok=True)

streaming = False
cap_stream = None

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
    global streaming
    was_streaming = streaming
    if streaming:
        detener_transmision()
        root.update()
    take_photo()
    update_photo()
    if was_streaming:
        mostrar_transmision()

def start_timelapse():
    global timelapse_running, next_capture_time, end_time, interval_ms, days_selected, hour_start, hour_end
    timelapse_running = True
    try:
        start_str = entry_start.get()
        end_str = entry_end.get()
        freq_str = entry_freq.get()
        days_str = entry_days.get().lower()
        hour_start_str = entry_hour_start.get()
        hour_end_str = entry_hour_end.get()

        # Días seleccionados
        if days_str:
            days_selected = [d.strip() for d in days_str.split(",")]
        else:
            days_selected = []  # Todos los días

        # Horas seleccionadas
        hour_start = hour_start_str if hour_start_str else None
        hour_end = hour_end_str if hour_end_str else None

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
        # Frecuencia en minutos
        interval_ms = int(float(freq_str) * 1000 * 60) if freq_str else 600000  # 10 minutos por defecto
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
    global timelapse_running, next_capture_time, end_time, interval_ms, days_selected, hour_start, hour_end
    if not timelapse_running:
        return
    now = datetime.now()
    # Verifica rango de días
    dia_actual = now.strftime("%A").lower()
    # Traducción de días a español
    dias_es = {
        "monday": "lunes", "tuesday": "martes", "wednesday": "miércoles",
        "thursday": "jueves", "friday": "viernes", "saturday": "sábado", "sunday": "domingo"
    }
    dia_actual_es = dias_es.get(dia_actual, dia_actual)
    if days_selected and dia_actual_es not in days_selected:
        root.after(interval_ms, schedule_next_capture)
        return
    # Verifica rango de horas
    if hour_start and hour_end:
        hora_actual = now.strftime("%H:%M")
        if not (hour_start <= hora_actual <= hour_end):
            root.after(interval_ms, schedule_next_capture)
            return
    if now >= next_capture_time:
        take_and_update()
        next_capture_time = now + timedelta(milliseconds=interval_ms)
    if end_time and now >= end_time:
        stop_timelapse()
    else:
        root.after(interval_ms, schedule_next_capture)

def mostrar_transmision():
    global streaming, cap_stream
    import cv2
    if streaming:
        return  # Ya está transmitiendo
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
        # Convertir el frame de OpenCV (BGR) a PIL (RGB)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame)
        img = img.resize((400, 300))  # Ajusta el tamaño si lo deseas
        imgtk = ImageTk.PhotoImage(image=img)
        lbl_photo.imgtk = imgtk
        lbl_photo.config(image=imgtk)
    if streaming:
        root.after(30, actualizar_stream)  # Actualiza cada 30 ms

def detener_transmision():
    global streaming, cap_stream
    streaming = False
    if cap_stream is not None:
        cap_stream.release()
        cap_stream = None
    lbl_status.config(text="Transmisión detenida")
    update_photo()  # Vuelve a mostrar la última foto

root = tk.Tk()
root.title("Katcam Pro")

lbl_photo = tk.Label(root)
lbl_photo.pack(pady=10)

btn_take = tk.Button(root, text="Sacar Foto", command=take_and_update, width=25, height=2)
btn_take.pack(pady=10)

btn_stream = tk.Button(root, text="Transmisión en directo", command=mostrar_transmision, width=25, height=2)
btn_stream.pack(pady=5)

btn_stop_stream = tk.Button(root, text="Detener transmisión", command=detener_transmision, width=25, height=2)
btn_stop_stream.pack(pady=5)

# Parámetros de timelapse
frame_params = tk.Frame(root)
frame_params.pack(pady=10)

tk.Label(frame_params, text="Inicio (YYYY-MM-DD HH:MM):").grid(row=0, column=0)
entry_start = tk.Entry(frame_params)
entry_start.grid(row=0, column=1)

tk.Label(frame_params, text="Fin (YYYY-MM-DD HH:MM, vacío = indefinido):").grid(row=1, column=0)
entry_end = tk.Entry(frame_params)
entry_end.grid(row=1, column=1)

tk.Label(frame_params, text="Frecuencia (minutos):").grid(row=2, column=0)
entry_freq = tk.Entry(frame_params)
entry_freq.grid(row=2, column=1)
entry_freq.insert(0, "10")  # Valor por defecto

tk.Label(frame_params, text="Días (ej: lunes,martes,viernes):").grid(row=3, column=0)
entry_days = tk.Entry(frame_params)
entry_days.grid(row=3, column=1)

tk.Label(frame_params, text="Hora inicio (HH:MM, ej: 08:00):").grid(row=4, column=0)
entry_hour_start = tk.Entry(frame_params)
entry_hour_start.grid(row=4, column=1)

tk.Label(frame_params, text="Hora fin (HH:MM, ej: 18:00):").grid(row=5, column=0)
entry_hour_end = tk.Entry(frame_params)
entry_hour_end.grid(row=5, column=1)

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
interval_ms = 600000  # 10 minutos por defecto
days_selected = []
hour_start = None
hour_end = None

root.mainloop()

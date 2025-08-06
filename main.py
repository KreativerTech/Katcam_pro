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
        img = img.resize((400, 300))
        photo = ImageTk.PhotoImage(img)
        lbl_last_photo.config(image=photo, width=400, height=300)
        lbl_last_photo.image = photo

def update_stream_photo(img):
    img = img.resize((400, 300))
    photo = ImageTk.PhotoImage(img)
    lbl_stream_photo.config(image=photo, width=400, height=300)
    lbl_stream_photo.image = photo

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
        update_stream_photo(img)
    if streaming:
        root.after(30, actualizar_stream)

def detener_transmision():
    global streaming, cap_stream
    streaming = False
    if cap_stream is not None:
        cap_stream.release()
        cap_stream = None
    lbl_status.config(text="Transmisión detenida")
    lbl_stream_photo.config(image="")  # Limpia la imagen de transmisión

def start_timelapse():
    global timelapse_running, next_capture_time, interval_ms, days_selected, hour_start, hour_end
    timelapse_running = True
    try:
        freq_str = entry_freq.get()
        hour_start_str = entry_hour_start.get()
        hour_end_str = entry_hour_end.get()

        # Días seleccionados
        days_selected.clear()
        for i, var in enumerate(day_vars):
            if var.get():
                days_selected.append(dias_lista[i])

        # Horas seleccionadas
        hour_start = hour_start_str if hour_start_str else None
        hour_end = hour_end_str if hour_end_str else None

        next_capture_time = datetime.now()
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
    global timelapse_running, next_capture_time, interval_ms, days_selected, hour_start, hour_end
    if not timelapse_running:
        return
    now = datetime.now()
    # Verifica rango de días
    dia_actual = now.strftime("%A").lower()
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
    root.after(interval_ms, schedule_next_capture)

root = tk.Tk()
root.title("Katcam Pro")

main_frame = tk.Frame(root)
main_frame.pack(padx=10, pady=10)

# Scroll para columna izquierda (vertical y horizontal)
left_canvas = tk.Canvas(main_frame, width=420, height=650)
left_scrollbar = tk.Scrollbar(main_frame, orient="vertical", command=left_canvas.yview)
left_hscrollbar = tk.Scrollbar(main_frame, orient="horizontal", command=left_canvas.xview)
left_frame = tk.Frame(left_canvas)

left_frame.bind(
    "<Configure>",
    lambda e: left_canvas.configure(
        scrollregion=left_canvas.bbox("all")
    )
)
left_canvas.create_window((0, 0), window=left_frame, anchor="nw")
left_canvas.configure(yscrollcommand=left_scrollbar.set, xscrollcommand=left_hscrollbar.set)

left_canvas.grid(row=0, column=0, sticky="nsew")
left_scrollbar.grid(row=0, column=1, sticky="ns")
left_hscrollbar.grid(row=1, column=0, sticky="ew")

# Columna izquierda: transmisión y última foto
tk.Label(left_frame, text="Transmisión en directo", font=("Arial", 12, "bold")).pack(pady=5)
lbl_stream_photo = tk.Label(left_frame, width=400, height=300, bg="black")
lbl_stream_photo.pack(pady=5)

btn_stream = tk.Button(left_frame, text="Iniciar transmisión", command=mostrar_transmision, width=25, height=2)
btn_stream.pack(pady=2)

btn_stop_stream = tk.Button(left_frame, text="Detener transmisión", command=detener_transmision, width=25, height=2)
btn_stop_stream.pack(pady=2)

tk.Label(left_frame, text="Última foto tomada", font=("Arial", 12, "bold")).pack(pady=10)
lbl_last_photo = tk.Label(left_frame, width=400, height=300, bg="gray")
lbl_last_photo.pack(pady=5)

btn_take = tk.Button(left_frame, text="Sacar Foto", command=take_and_update, width=25, height=2)
btn_take.pack(pady=10)

# Columna derecha: configuración
right_frame = tk.Frame(main_frame)
right_frame.grid(row=0, column=2, padx=20, sticky="n")

tk.Label(right_frame, text="Configuración Timelapse", font=("Arial", 12, "bold")).grid(row=0, column=0, columnspan=2, pady=5)

tk.Label(right_frame, text="Frecuencia (minutos):").grid(row=1, column=0, sticky="e")
entry_freq = tk.Entry(right_frame)
entry_freq.grid(row=1, column=1)
entry_freq.insert(0, "10")

tk.Label(right_frame, text="Días a funcionar:").grid(row=2, column=0, sticky="ne")
dias_lista = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
day_vars = [tk.BooleanVar(value=True) for _ in dias_lista]
days_frame = tk.Frame(right_frame)
days_frame.grid(row=2, column=1, sticky="w")
for i, dia in enumerate(dias_lista):
    tk.Checkbutton(days_frame, text=dia.capitalize(), variable=day_vars[i]).pack(anchor="w")

tk.Label(right_frame, text="Hora inicio (HH:MM):").grid(row=3, column=0, sticky="e")
entry_hour_start = tk.Entry(right_frame)
entry_hour_start.grid(row=3, column=1)
entry_hour_start.insert(0, "08:00")

tk.Label(right_frame, text="Hora fin (HH:MM):").grid(row=4, column=0, sticky="e")
entry_hour_end = tk.Entry(right_frame)
entry_hour_end.grid(row=4, column=1)
entry_hour_end.insert(0, "18:00")

btn_start = tk.Button(right_frame, text="Iniciar Timelapse", command=start_timelapse, width=25, height=2)
btn_start.grid(row=5, column=0, columnspan=2, pady=5)

btn_stop = tk.Button(right_frame, text="Detener Timelapse", command=stop_timelapse, width=25, height=2)
btn_stop.grid(row=6, column=0, columnspan=2, pady=5)

lbl_status = tk.Label(right_frame, text="")
lbl_status.grid(row=7, column=0, columnspan=2, pady=5)

update_photo()

# Variables globales para timelapse
timelapse_running = False
next_capture_time = None
interval_ms = 600000  # 10 minutos por defecto
days_selected = dias_lista.copy()
hour_start = "08:00"
hour_end = "18:00"

root.mainloop()

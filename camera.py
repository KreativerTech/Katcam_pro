import cv2
import os
from datetime import datetime
import time
import shutil

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

PENDRIVE_DIR = encontrar_pendrive()
DRIVE_DIR = encontrar_google_drive()

if PENDRIVE_DIR:
    PHOTO_DIR = PENDRIVE_DIR
elif DRIVE_DIR:
    PHOTO_DIR = DRIVE_DIR
else:
    raise FileNotFoundError("No se encontró el pendrive 'FOTOS' ni la carpeta de Google Drive 'KatcamAustralia/fotos'.")
os.makedirs(PHOTO_DIR, exist_ok=True)

def take_photo(dest_folder, cam_index=0):
    cap = cv2.VideoCapture(cam_index)
    # Intenta máxima resolución soportada por la cámara
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 8000)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 6000)
    time.sleep(3)
    for _ in range(3):
        cap.read()
        time.sleep(0.3)
    ret, frame = cap.read()
    cap.release()

    if ret:
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        dest_path = os.path.join(dest_folder, filename)
        cv2.imwrite(dest_path, frame)
        print(f"Foto guardada en: {dest_path}")
        # Si tienes Google Drive y quieres copiar, puedes hacerlo aquí si lo deseas
        drive_dir = encontrar_google_drive()
        if drive_dir:
            try:
                drive_path = os.path.join(drive_dir, filename)
                shutil.copy2(dest_path, drive_path)
                print(f"Foto también copiada a Google Drive: {drive_path}")
            except Exception as e:
                print(f"No se pudo copiar al Drive: {e}")

        return dest_path
    else:
        print("Error al capturar imagen")
        return None


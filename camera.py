import cv2
import os
from datetime import datetime

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


def take_photo():
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 8000)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 6000)
    ret, frame = cap.read()
    cap.release()

    if ret:
        filename = f"{PHOTO_DIR}/{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        cv2.imwrite(filename, frame)
        print(f"Foto guardada: {filename}")
    else:
        print("Error al capturar imagen")

def show_last_photo():
    fotos = sorted(os.listdir(PHOTO_DIR))
    if fotos:
        img = cv2.imread(f"{PHOTO_DIR}/{fotos[-1]}")
        cv2.imshow("Última Foto", img)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    else:
        print("No hay fotos disponibles")

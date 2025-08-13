import cv2
import os
from datetime import datetime
import time

def take_photo(dest_folder, cam_index=0):
    cap = cv2.VideoCapture(cam_index)
    # Intenta máxima resolución soportada por la cámara
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 8000)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 6000)
    time.sleep(2)  # Espera 2 segundos para que la cámara ajuste
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
        return dest_path
    else:
        print("Error al capturar imagen")
        return None
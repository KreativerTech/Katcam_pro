import cv2
import os
from datetime import datetime
import time

# Caché de la cámara abierta para no reabrirla en cada foto
_camera_cache = None
_camera_index = None

# Resoluciones altas realistas para webcams/ELP; ajusta según tu modelo
_PREFERRED_SIZES = [
    (4056, 3040),   # ~12.3 MP (algunas ELP/IMX477)
    (3840, 2160),   # 4K UHD
    (3264, 2448),   # 8MP
    (2592, 1944),   # 5MP
    (1920, 1080),   # 1080p
    (1280, 720)     # 720p
]

def _try_set_resolution(cap, sizes):
    """Intenta setear la mejor resolución de la lista; retorna la efectiva."""
    for (w, h) in sizes:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        # lee lo que quedó realmente
        eff_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        eff_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if abs(eff_w - w) <= 16 and abs(eff_h - h) <= 16:
            return (eff_w, eff_h)
    # fallback: lo que sea que devolvió
    return (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))

def open_camera(cam_index=0, backend="dshow", force_mjpg=True, prefer_sizes=None):
    """Abre/recicla la cámara; negocia resolución alta; aplica MJPG para rapidez."""
    global _camera_cache, _camera_index
    if _camera_cache is None or _camera_index != cam_index:
        if _camera_cache is not None:
            _camera_cache.release()
        cap = cv2.VideoCapture(cam_index, cv2.CAP_DSHOW if backend == "dshow" else cv2.CAP_MSMF)
        if force_mjpg:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        sizes = prefer_sizes if prefer_sizes else _PREFERRED_SIZES
        eff = _try_set_resolution(cap, sizes)
        # warm-up corto (deja que enfoque/exponga)
        for _ in range(4):
            cap.read()
            time.sleep(0.05)
        _camera_cache = cap
        _camera_index = cam_index
    return _camera_cache

def close_camera():
    """Cierra la cámara si está abierta."""
    global _camera_cache
    if _camera_cache is not None:
        _camera_cache.release()
        _camera_cache = None

def take_photo(dest_folder, cam_index=0):
    """
    Captura una foto optimizada sin congelar la UI (se llama desde un hilo en main.py).
    - Reutiliza cámara abierta.
    - MJPG + resolución negociada para velocidad/estabilidad.
    """
    cap = open_camera(cam_index, backend="dshow", force_mjpg=True, prefer_sizes=_PREFERRED_SIZES)

    if not cap or not cap.isOpened():
        print("Error: No se pudo abrir la cámara.")
        return None

    # Un par de frames por si el driver tarda un poco en estabilizar
    for _ in range(2):
        cap.read()

    ret, frame = cap.read()
    if ret:
        os.makedirs(dest_folder, exist_ok=True)
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        dest_path = os.path.join(dest_folder, filename)
        # calidad JPG alta (95)
        cv2.imwrite(dest_path, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        print(f"Foto guardada en: {dest_path}")
        return dest_path
    else:
        print("Error al capturar imagen")
        return None

# camera.py
# Envoltorio fino para capturas usando el mismo CameraManager (evita conflictos).
from video_capture import camera_manager

def take_photo(dest_folder, prefer_sizes=None, jpeg_quality=95, auto_resume_stream=True, block_until_done=True):
    camera_manager.take_photo(
        dest_folder=dest_folder,
        prefer_sizes=prefer_sizes,
        jpeg_quality=jpeg_quality,
        auto_resume_stream=auto_resume_stream,
        block_until_done=block_until_done,
    )

def close_camera():
    # Compatibilidad con código previo; no hace falta aquí.
    pass

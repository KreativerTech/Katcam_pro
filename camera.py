# camera.py
# Envoltorio fino para capturas usando el mismo CameraManager (evita conflictos).
from video_capture import camera_manager

def take_photo(dest_folder, prefer_sizes=None, jpeg_quality=95, auto_resume_stream=True, block_until_done=True, result_holder=None):
    try:
        from infra.telemetry import log_event
        log_event("camera_wrapper_call", dest_folder=dest_folder, prefer_count=len(prefer_sizes) if prefer_sizes else 0, block_until_done=bool(block_until_done))
    except Exception:
        pass
    try:
        return camera_manager.take_photo(
            dest_folder=dest_folder,
            prefer_sizes=prefer_sizes,
            jpeg_quality=jpeg_quality,
            auto_resume_stream=auto_resume_stream,
            block_until_done=block_until_done,
            result_holder=result_holder,
        )
    except Exception as e:
        try:
            from infra.telemetry import log_error
            log_error(e, {"phase": "camera_wrapper"})
        except Exception:
            pass
        raise

def close_camera():
    # Compatibilidad con código previo; no hace falta aquí.
    pass

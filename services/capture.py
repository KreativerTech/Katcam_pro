
# -*- coding: utf-8 -*-
import time
from typing import Callable, Optional, Tuple, List
from services.stream import stop_stream, start_stream
from config.settings import DEFAULT_RES_LABEL
from PIL import Image

try:
    from camera import take_photo
except Exception:
    def take_photo(dest_folder, prefer_sizes=None, jpeg_quality=95, auto_resume_stream=False, block_until_done=True):
        raise RuntimeError("camera.take_photo no disponible")

def capture_once(dest_folder: str,
                 was_streaming: bool,
                 timelapse_running: bool,
                 current_resolution_label: str,
                 prefer_wh: Optional[Tuple[int,int]],
                 on_status: Callable[[str], None],
                 on_after: Callable[[], None],
                 stream_on_cb: Callable[[], None]):
    """
    Ejecuta una captura respetando el estado de stream y timelapse.
    """
    try:
        if was_streaming and not timelapse_running:
            stop_stream()
            time.sleep(0.08)
        prefer = [prefer_wh] if prefer_wh else None
        take_photo(
            dest_folder=dest_folder,
            prefer_sizes=prefer,
            jpeg_quality=95,
            auto_resume_stream=bool(was_streaming and timelapse_running),
            block_until_done=True
        )
        on_status("Foto tomada.")
    except Exception as e:
        on_status(f"Error: {e}")
    finally:
        if was_streaming:
            stream_on_cb()
        on_after()


# -*- coding: utf-8 -*-
from typing import Optional, Tuple, Callable
from config.settings import RESOLUTIONS
from PIL import Image

try:
    from video_capture import camera_manager
except Exception:
    camera_manager = None

def find_res(label: str) -> Optional[Tuple[int, int]]:
    for t, w, h in RESOLUTIONS:
        if t == label:
            return (w, h)
    return None

def apply_resolution(label: str):
    if camera_manager is None:
        return
    wh = find_res(label)
    if not wh:
        return
    try:
        if hasattr(camera_manager, "set_resolution"):
            camera_manager.set_resolution(*wh)
    except Exception as e:
        print("set_resolution error:", e)

def start_stream(on_frame: Callable[[Image.Image], None], current_resolution_label: str):
    apply_resolution(current_resolution_label)
    if camera_manager:
        camera_manager.start_stream()

def stop_stream():
    if camera_manager:
        camera_manager.stop_stream()

def get_frame_image():
    if not camera_manager:
        return None
    frame_rgb = camera_manager.get_frame_rgb()
    if frame_rgb is None:
        return None
    return Image.fromarray(frame_rgb)

def shutdown():
    if camera_manager:
        try:
            camera_manager.stop_stream()
            camera_manager.shutdown()
        except Exception:
            pass


# -*- coding: utf-8 -*-
import os, shutil, time
from typing import Callable

def sync_photos(photo_dir: str, drive_dir: str, on_status: Callable[[str], None]):
    if not drive_dir or not os.path.exists(drive_dir):
        on_status("No se encontró Google Drive para sincronizar.")
        return
    if not photo_dir or not os.path.exists(photo_dir):
        on_status("Carpeta de fotos inválida.")
        return
    fotos_pendrive = sorted([f for f in os.listdir(photo_dir) if f.lower().endswith((".jpg",".jpeg",".png"))])
    fotos_drive = set(os.listdir(drive_dir))
    nuevas = [f for f in fotos_pendrive if f not in fotos_drive]
    copied = 0
    now = time.time()
    for f in nuevas:
        src = os.path.join(photo_dir, f)
        try:
            # margen de 2s para evitar copiar en mitad de escritura
            if now - os.path.getmtime(src) < 2.0:
                continue
            shutil.copy2(src, os.path.join(drive_dir, f))
            copied += 1
        except Exception as e:
            on_status(f"Error copiando {f}: {e}")
    if copied:
        on_status(f"Sincronizadas {copied} fotos al Drive.")
    else:
        on_status("No hay fotos nuevas para sincronizar.")

def schedule_sync(root_after, photo_dir, drive_dir, on_status):
    def _tick():
        sync_photos(photo_dir, drive_dir, on_status)
        root_after(delay=60000, callback=_tick)
    _tick()

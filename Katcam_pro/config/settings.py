# -*- coding: utf-8 -*-
import os
import sys

# --- Paths base ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))   # /config
PROJECT_ROOT = os.path.dirname(BASE_DIR)                # raíz del proyecto

def _bundle_base() -> str:
    """
    Si está empaquetado con PyInstaller, sys._MEIPASS apunta a la carpeta temporal
    con los recursos. En dev, usamos la raíz del proyecto.
    """
    return getattr(sys, "_MEIPASS", PROJECT_ROOT)

ASSETS_DIR = os.path.join(_bundle_base(), "assets")

def _asset(path_relative: str) -> str:
    """Resuelve rutas relativas a assets/ de forma robusta (dev y exe)."""
    return os.path.join(ASSETS_DIR, path_relative)

# --- Apariencia / UI ---
BG_COLOR = "#181818"
FG_COLOR = "#FFFFFF"
BTN_COLOR = "#FFD600"       # header/footer amarillo
BTN_TEXT_COLOR = "#181818"
BTN_BORDER_COLOR = "#000000"

# Tamaños recomendados
MIN_APP_W, MIN_APP_H = 1000, 700
IMG_MIN_W, IMG_MIN_H = 900, 600
RESIZE_DEBOUNCE_MS = 120

# Resoluciones disponibles (etiqueta, w, h)
RESOLUTIONS = [
    ("3840 x 2160 (4K)", 3840, 2160),
    ("2560 x 1440 (QHD)", 2560, 1440),
    ("1920 x 1080 (FHD)", 1920, 1080),
    ("1600 x 1200 (UXGA)", 1600, 1200),
    ("1280 x 720 (HD)",   1280, 720),
    ("1024 x 768 (XGA)",  1024, 768),
    ("800 x 600 (SVGA)",   800, 600),
    ("640 x 480 (VGA)",    640, 480),
]
DEFAULT_RES_LABEL = "1920 x 1080 (FHD)"

# Días (para timelapse)
DIAS_LISTA = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]

# --- Rutas de imágenes / iconos ---
APP_LOGO_PATH      = _asset("logo_katcam.png")     # opcional
COMPANY_LOGO_PATH  = _asset("logo_kreativer.png")  # logo empresa (footer)
ICON_PATH          = _asset("katcam_multi.ico")    # icono ventanas
HEADER_IMAGE_PATH  = _asset("header-katcam.jpg")   # imagen de cabecera

# --- Config en AppData (siempre escribible) ---
APPDATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "KatcamPro")
# No crear carpeta acá (módulos import-time). La creamos justo al escribir/leer.
CONFIG_FILE = os.path.join(APPDATA_DIR, "katcam_config.json")

# --- Otros flags ---
USE_SCROLL_CONTAINER = False

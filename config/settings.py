# -*- coding: utf-8 -*-
import os
import sys



# --- Paths base ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))   # /config
PROJECT_ROOT = os.path.dirname(BASE_DIR)                # raíz del proyecto

from pathlib import Path  # añade este import arriba si no está

def _bundle_base() -> str:
    """
    Devuelve la base donde están los recursos:
    - PyInstaller onefile: usa _MEIPASS (si existe _internal/ lo prioriza)
    - PyInstaller onedir (v6+): usa <carpeta del exe>/_internal si existe
    - Dev: raíz del proyecto
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        base = Path(meipass)
        return str(base / "_internal") if (base / "_internal").exists() else str(base)

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        return str(exe_dir / "_internal") if (exe_dir / "_internal").exists() else str(exe_dir)

    return PROJECT_ROOT



ASSETS_DIR = os.path.join(_bundle_base(), "assets")

def _asset(path_relative: str) -> str:
    """Resuelve rutas relativas a assets/ de forma robusta (dev y exe)."""
    return os.path.join(ASSETS_DIR, path_relative)

def resource_path(rel_path: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))
    return os.path.join(base, rel_path)
# --- Apariencia / UI ---
BG_COLOR = "#181818"
FG_COLOR = "#FFFFFF"
BTN_COLOR = "#FFD600"       # header/footer amarillo
BTN_TEXT_COLOR = "#181818"
BTN_BORDER_COLOR = "#000000"

# --- Fuentes ---
# Fuente principal: Orbitron (futurista, ideal para apps técnicas)
# Fallback: Arial si Orbitron no está disponible
MAIN_FONT_FAMILY = "Orbitron"
FALLBACK_FONT_FAMILY = "Arial"

# Tamaños de fuente estandarizados
FONT_SMALL = 10
FONT_NORMAL = 11
FONT_MEDIUM = 12
FONT_LARGE = 14
FONT_XLARGE = 16

def get_font(size=FONT_NORMAL, weight="normal"):
    """Retorna tupla de fuente con fallback automático"""
    try:
        import tkinter.font as tkfont
        # Verificar si Orbitron está disponible
        available_families = tkfont.families()
        if MAIN_FONT_FAMILY in available_families:
            return (MAIN_FONT_FAMILY, size, weight)
    except:
        pass
    return (FALLBACK_FONT_FAMILY, size, weight)

# Efectos de sombra para texto
SHADOW_COLOR = "#000000"
SHADOW_OFFSET_X = 1
SHADOW_OFFSET_Y = 1

# Tamaños recomendados
MIN_APP_W, MIN_APP_H = 720, 520
IMG_MIN_W, IMG_MIN_H = 320, 180
RESIZE_DEBOUNCE_MS = 120

# Resoluciones disponibles (etiqueta, w, h)
RESOLUTIONS = [
    ("8000 x 6000 (48MP)", 8000, 6000),
    ("3840 x 2160 (4K)", 3840, 2160),
    ("3264 x 2448 (8MP)", 3264, 2448),
    ("2592 x 1944 (5MP)", 2592, 1944),
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

# --- Timelapse / Captura avanzada ---
# Intervalo mínimo duro (en segundos) para timelapse. El usuario indicó que nunca usa < 5s.
TIME_LAPSE_MIN_INTERVAL_S = 5
# Frames de warm-up para foto high-res antes de guardar (podrá usarse luego en lógica de cámara)
PHOTO_WARMUP_FRAMES = 4
# Timeout máximo para warm-up (ms)
PHOTO_WARMUP_TIMEOUT_MS = 800
# Cooldown mínimo entre reconfiguraciones high-res (s)
HIGHRES_RECONFIG_COOLDOWN_S = 2.0
# Estrategia cuando alguien solicitara (en el futuro) un intervalo menor al permitido: 'delay' | 'skip_highres' | 'use_live_frame'
FAST_INTERVAL_STRATEGY = "delay"
# Factor multiplicador para cálculo dinámico (no implementado aún) de intervalo mínimo adaptativo
DYNAMIC_MIN_FACTOR = 1.35

# --- Captura / Reanudación avanzada ---
CAPTURE_RES_TOLERANCE_PIX = 16   # tolerancia para considerar que la resolución efectiva coincide
CAPTURE_RES_MAX_RETRIES = 1      # número de reintentos si mismatch
POST_CAPTURE_RESUME_TIMEOUT_S = 1.2  # tiempo para esperar primer frame post-captura
POST_CAPTURE_REOPEN_WINDOW_S = 1.5   # ventana adicional tras reopen
CAPTURE_MAX_DURATION_S = 8.0         # timeout duro para una captura de foto
CAPTURE_CANCEL_POLL_MS = 50          # cadencia de chequeo de cancel cooperativo dentro del bucle de captura
# --- Downgrade automático tras mismatches ---
# Número de mismatches consecutivos necesarios para degradar a la siguiente resolución más baja
RES_MISMATCH_DOWNGRADE_THRESHOLD = 2

# --- Detección de foto negra (umbral de brillo medio 0-255) ---
# Si la media en escala de grises de la imagen cae por debajo de este
# valor se considerará una "foto negra" y se registrará en la carpeta de la
# foto (logs/YYYY-MM-DD.log) además de emitir telemetría.
CAPTURE_BLACK_MEAN_THRESHOLD = 10

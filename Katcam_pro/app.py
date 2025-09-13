# -*- coding: utf-8 -*-
import tkinter as tk
from infra.logging_setup import setup_logging
from ui.main_window import build_main_window

# --- Alta DPI (Windows) ---
try:
    import ctypes
    try:
        # Per-Monitor v2 (Windows 10+)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        # Fallback: system DPI aware
        ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

LOG_PATH = setup_logging(app_name="Katcam")

def main():
    root = tk.Tk()

    # --- Escalado de Tk según DPI real ---
    try:
        dpi = root.winfo_fpixels('1i')  # píxeles en 1 pulgada del monitor actual
        root.tk.call('tk', 'scaling', dpi / 72.0)
    except Exception:
        pass

    state = build_main_window(root)
    root.mainloop()

if __name__ == "__main__":
    main()

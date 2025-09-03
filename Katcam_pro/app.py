
# -*- coding: utf-8 -*-
import tkinter as tk
from infra.logging_setup import setup_logging
from ui.main_window import build_main_window

LOG_PATH = setup_logging(app_name="Katcam")

def main():
    root = tk.Tk()
    state = build_main_window(root)
    root.mainloop()

if __name__ == "__main__":
    main()

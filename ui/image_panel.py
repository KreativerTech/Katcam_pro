# -*- coding: utf-8 -*-
import tkinter as tk
from PIL import Image, ImageTk, ImageOps
from config.settings import BG_COLOR, IMG_MIN_W, IMG_MIN_H, RESIZE_DEBOUNCE_MS

class ImagePanel(tk.Frame):
    """Canvas que muestra una imagen redimensionada sin alterar el layout."""
    def __init__(self, parent, bg=BG_COLOR, min_size=(IMG_MIN_W, IMG_MIN_H)):
        super().__init__(parent, bg=bg)
        self.bg = bg
        self.min_w, self.min_h = min_size
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, borderwidth=0)
        self.canvas.pack(fill="both", expand=True)
        self.update_idletasks()
        self.canvas.config(width=self.min_w, height=self.min_h)

        self._last_pil = None
        self._tk_img = None
        self._resize_job = None
        self.bind("<Configure>", self._on_resize)

    def set_image(self, pil_img: Image.Image):
        self._last_pil = pil_img
        self._render()

    def _on_resize(self, _evt=None):
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(RESIZE_DEBOUNCE_MS, self._render)

    def _render(self):
        if self._last_pil is None:
            ph = Image.new("RGB", (self.min_w, self.min_h), (40, 40, 40))
            self._draw(ph); return

        cw = max(self.canvas.winfo_width(), self.min_w)
        ch = max(self.canvas.winfo_height(), self.min_h)
        shown = ImageOps.contain(self._last_pil, (cw, ch))
        self._draw(shown)

    def _draw(self, pil_img):
        self._tk_img = ImageTk.PhotoImage(pil_img)
        self.canvas.delete("all")
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        self.canvas.create_image(cw // 2, ch // 2, image=self._tk_img, anchor="center")

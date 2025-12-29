# ui/dialogs.py
# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext as st
from tkinter import messagebox
from config.settings import BG_COLOR, FG_COLOR, BTN_COLOR, BTN_TEXT_COLOR, ICON_PATH
import logging
try:
    from infra.telemetry import log_error as _tele_log_error
except Exception:
    _tele_log_error = None

# Si cambiaste de sitio estas utilidades, ajusta los imports:
from infra.paths import is_autostart_enabled, enable_autostart, disable_autostart


def set_icon(win: tk.Tk | tk.Toplevel):
    """Aplica el icono de la app a cualquier ventana Tk/Toplevel."""
    try:
        win.iconbitmap(ICON_PATH)
    except Exception:
        pass


def open_autostart_window(root, on_status):
    win = tk.Toplevel(root)
    set_icon(win)
    win.title("Inicio con Windows")
    win.configure(bg=BG_COLOR)
    win.geometry("460x180")
    # Mantener la ventana por encima al abrir y marcarla como transient respecto a la ventana padre
    try:
        win.transient(root)
        win.lift()
        win.attributes("-topmost", True)
        win.focus_force()
    except Exception:
        pass

    info = tk.Label(
        win,
        text="Configura si Katcam Pro se inicia automáticamente con Windows.",
        bg=BG_COLOR, fg=FG_COLOR, font=("Arial", 11),
    )
    info.pack(padx=12, pady=(12, 4))

    status_lbl = tk.Label(win, text="", bg=BG_COLOR, fg=BTN_COLOR, font=("Arial", 11, "bold"))
    status_lbl.pack(pady=(0, 8))

    autostart_var = tk.IntVar(value=1 if is_autostart_enabled() else 0)

    def on_toggle():
        try:
            if autostart_var.get():
                enable_autostart()
                status_lbl.config(text="Estado: ACTIVADO")
                on_status("Inicio automático habilitado.")
            else:
                disable_autostart()
                status_lbl.config(text="Estado: DESACTIVADO")
                on_status("Inicio automático deshabilitado.")
        except Exception as e:
            on_status(f"Autostart error: {e}")

    chk = tk.Checkbutton(
        win, text="Iniciar Katcam Pro con Windows",
        variable=autostart_var, onvalue=1, offvalue=0, command=on_toggle,
        bg=BG_COLOR, fg=FG_COLOR, selectcolor="black",
        activebackground=BG_COLOR, activeforeground=FG_COLOR,
        font=("Arial", 12, "bold"),
    )
    chk.pack(padx=12, pady=8)

    status_lbl.config(text="Estado: ACTIVADO" if autostart_var.get() else "Estado: DESACTIVADO")


# ============ INFO (ver y editar) ============
def open_info_window(root, state=None):
    win = tk.Toplevel(root)
    set_icon(win)
    win.title("Information")
    win.configure(bg=BG_COLOR)
    win.overrideredirect(True)
    win.resizable(True, True)
    win.lift()
    # Mantener la ventana Info por encima cuando se abre (topmost=True),
    # pero aún permitir moverla desde la barra de título.
    try:
        win.attributes("-topmost", True)
    except Exception:
        pass

    # Barra de título personalizada
    titlebar = tk.Frame(win, bg=BTN_COLOR, height=36)
    titlebar.pack(fill="x")
    tk.Label(titlebar, text="Information", bg=BTN_COLOR, fg=BTN_TEXT_COLOR,
             font=("Arial", 12, "bold")).pack(side="left", padx=10)

    # Permitir arrastrar la ventana desde la barra de título personalizada
    def _start_move(e):
        try:
            win._drag_offset = (e.x, e.y)
        except Exception:
            win._drag_offset = (0, 0)

    def _do_move(e):
        try:
            ox, oy = getattr(win, '_drag_offset', (0, 0))
            nx = win.winfo_x() + (e.x - ox)
            ny = win.winfo_y() + (e.y - oy)
            win.geometry(f"+{nx}+{ny}")
        except Exception:
            pass

    titlebar.bind("<Button-1>", _start_move)
    titlebar.bind("<B1-Motion>", _do_move)

    def _close_info():
        if win.winfo_exists():
            win.destroy()

    tk.Button(titlebar, text="✕", command=_close_info,
              bg=BTN_COLOR, fg=BTN_TEXT_COLOR, bd=0,
              font=("Arial", 12, "bold"), padx=10, pady=2, cursor="hand2"
             ).pack(side="right", padx=6, pady=4)

    # Permitir cerrar con Esc (después de definir _close_info)
    win.bind('<Escape>', lambda e: _close_info())

    # Grip para redimensionar (igual que gallery)
    grip = tk.Label(win, bg=BTN_COLOR, cursor="bottom_right_corner")
    def _place_grip():
        grip.place(relx=1.0, rely=1.0, anchor="se", width=18, height=18)
        grip.lift()
    def _resize_start(e):
        grip._drag = (e.x_root, e.y_root, win.winfo_width(), win.winfo_height())
    def _resize_drag(e):
        x0, y0, w0, h0 = grip._drag
        dx, dy = e.x_root - x0, e.y_root - y0
        win.geometry(f"{max(320, w0+dx)}x{max(240, h0+dy)}")
        _place_grip()
    grip.bind("<Button-1>", _resize_start)
    grip.bind("<B1-Motion>", _resize_drag)
    win.bind("<Configure>", lambda e: _place_grip())
    # Coloca el grip después de todo el layout
    win.after(10, _place_grip)

    nb = ttk.Notebook(win)
    nb.pack(fill="both", expand=True)

    # Ajustar tamaño mínimo y al contenido real
    win.update_idletasks()
    # Aumenta el tamaño mínimo y corrige área negra inicial
    min_w, min_h = 700, 480
    req_w = max(min_w, win.winfo_reqwidth())
    req_h = max(min_h, win.winfo_reqheight())
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    # Limita el tamaño máximo a 90% de la pantalla
    max_w, max_h = int(sw * 0.9), int(sh * 0.9)
    ww = min(req_w, max_w)
    wh = min(req_h, max_h)
    x, y = (sw - ww) // 2, (sh - wh) // 2
    win.geometry(f"{ww}x{wh}+{x}+{y}")

    # --- helpers ---
    def _make_scrollable_tab(title):
        tab = tk.Frame(nb, bg=BG_COLOR)
        nb.add(tab, text=title)

        outer = tk.Frame(tab, bg=BG_COLOR)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg=BG_COLOR, highlightthickness=0, borderwidth=0)
        vbar = tk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)
        vbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=BG_COLOR)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        # Exponer referencias para cálculos de tamaño externos
        inner._canvas_ref = canvas  # type: ignore[attr-defined]

        def _on_resize(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # fijar ancho del inner para evitar recortes
            try:
                canvas.itemconfig(1, width=canvas.winfo_width())
            except Exception:
                pass

        inner.bind("<Configure>", _on_resize)
        tab.bind("<Configure>", _on_resize)
        return inner

    def add_row(parent, r, label, value, bold=False):
        tk.Label(parent, text=label, bg=BG_COLOR, fg=FG_COLOR).grid(
            row=r, column=0, sticky="e", padx=10, pady=5
        )
        tk.Label(parent, text=value or "-", bg=BG_COLOR,
                 fg=BTN_COLOR, font=("Arial", 11, "bold") if bold else ("Arial", 11)).grid(
            row=r, column=1, sticky="w", padx=10, pady=5
        )

    # ===== Tab 1: Configuración =====
    cfg_tab = _make_scrollable_tab("Configuración")

    cfg = getattr(getattr(state, "cfg", None), "data", {}) if state else {}
    # valores de config / estado (sin GPS)
    camera_id = cfg.get("camera_id", "")
    cliente   = cfg.get("cliente", "")
    obra      = cfg.get("obra", "")
    ubicacion = cfg.get("ubicacion", "")
    contacto  = cfg.get("contacto", "")
    email     = cfg.get("email", "")
    telefono  = cfg.get("telefono", "")

    photo_dir = cfg.get("photo_dir", getattr(state, "photo_dir", ""))
    drive_dir = cfg.get("drive_dir", getattr(state, "drive_dir", ""))

    row = 0
    tk.Label(cfg_tab, text="Datos del proyecto", font=("Arial", 14, "bold"),
             bg=BG_COLOR, fg=FG_COLOR).grid(row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 6)); row += 1
    add_row(cfg_tab, row, "Nombre del equipo:", camera_id, bold=True); row += 1
    add_row(cfg_tab, row, "Cliente:", cliente); row += 1
    add_row(cfg_tab, row, "Obra:", obra); row += 1
    add_row(cfg_tab, row, "Ubicación:", ubicacion); row += 1
    add_row(cfg_tab, row, "Contacto:", contacto); row += 1
    add_row(cfg_tab, row, "Email:", email); row += 1
    add_row(cfg_tab, row, "Teléfono:", telefono); row += 1

    tk.Label(cfg_tab, text="Carpetas", font=("Arial", 14, "bold"),
             bg=BG_COLOR, fg=FG_COLOR).grid(row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(12, 6)); row += 1
    add_row(cfg_tab, row, "Fotos:", photo_dir); row += 1
    add_row(cfg_tab, row, "Google Drive:", drive_dir); row += 1

    # Botón editar
    def _refresh_and_header():
        # refrescar datos del tab y avisar a la main window
        for w in cfg_tab.grid_slaves():
            w.destroy()
        # reconstruir (reutilizamos la propia función para brevedad)
        nonlocal camera_id, cliente, obra, ubicacion, contacto, email, telefono, photo_dir, drive_dir
        cfg = state.cfg.data
        camera_id = cfg.get("camera_id", "")
        cliente   = cfg.get("cliente", "")
        obra      = cfg.get("obra", "")
        ubicacion = cfg.get("ubicacion", "")
        contacto  = cfg.get("contacto", "")
        email     = cfg.get("email", "")
        telefono  = cfg.get("telefono", "")
        photo_dir = cfg.get("photo_dir", getattr(state, "photo_dir", ""))
        drive_dir = cfg.get("drive_dir", getattr(state, "drive_dir", ""))

        r = 0
        tk.Label(cfg_tab, text="Datos del proyecto", font=("Arial", 14, "bold"),
                 bg=BG_COLOR, fg=FG_COLOR).grid(row=r, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 6)); r += 1
        add_row(cfg_tab, r, "Nombre del equipo:", camera_id, bold=True); r += 1
        add_row(cfg_tab, r, "Cliente:", cliente); r += 1
        add_row(cfg_tab, r, "Obra:", obra); r += 1
        add_row(cfg_tab, r, "Ubicación:", ubicacion); r += 1
        add_row(cfg_tab, r, "Contacto:", contacto); r += 1
        add_row(cfg_tab, r, "Email:", email); r += 1
        add_row(cfg_tab, r, "Teléfono:", telefono); r += 1
        tk.Label(cfg_tab, text="Carpetas", font=("Arial", 14, "bold"),
                 bg=BG_COLOR, fg=FG_COLOR).grid(row=r, column=0, columnspan=2, sticky="w", padx=10, pady=(12, 6)); r += 1
        add_row(cfg_tab, r, "Fotos:", photo_dir); r += 1
        add_row(cfg_tab, r, "Google Drive:", drive_dir); r += 1
        tk.Button(cfg_tab, text="Editar información…",
                  command=lambda: open_edit_client_info(root, state, on_saved=_refresh_and_header),
                  bg=BTN_COLOR, fg=BTN_TEXT_COLOR, bd=0,
                  font=("Arial", 12, "bold"), padx=12, pady=8
                 ).grid(row=r, column=0, columnspan=2, sticky="w", padx=10, pady=(12, 10))
        try:
            root.event_generate("<<INFO_UPDATED>>", when="tail")
        except Exception:
            pass

    tk.Button(cfg_tab, text="Editar información…",
              command=lambda: open_edit_client_info(root, state, on_saved=_refresh_and_header),
              bg=BTN_COLOR, fg=BTN_TEXT_COLOR, bd=0,
              font=("Arial", 12, "bold"), padx=12, pady=8
             ).grid(row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(12, 10))

    # ===== Tab 2: Acerca de =====
    about_tab = tk.Frame(nb, bg=BG_COLOR)
    nb.add(about_tab, text="Acerca de")

    data = getattr(getattr(state, "cfg", None), "data", {}) if state else {}
    version = data.get("version", "2.5.5")
    autor   = data.get("autor", "Kreativer")
    soporte = data.get("soporte", "kreativer.empresa@gmail.com")

    tk.Label(about_tab, text="Información general", font=("Arial", 14, "bold"),
             bg=BG_COLOR, fg=FG_COLOR).pack(anchor="w", padx=12, pady=(12, 6))
    tk.Label(about_tab, text=f"Versión: {version}", bg=BG_COLOR, fg=FG_COLOR).pack(anchor="w", padx=12, pady=3)
    tk.Label(about_tab, text=f"Autor: {autor}", bg=BG_COLOR, fg=FG_COLOR).pack(anchor="w", padx=12, pady=3)
    tk.Label(about_tab, text=f"Soporte: {soporte}", bg=BG_COLOR, fg=FG_COLOR).pack(anchor="w", padx=12, pady=3)

    # ===== Tab 3: Map (placeholder) =====
    map_tab = tk.Frame(nb, bg=BG_COLOR)
    nb.add(map_tab, text="Map")
    tk.Label(map_tab, text="Mapa (próximamente)",
             font=("Arial", 14, "bold"), bg=BG_COLOR, fg=FG_COLOR).pack(anchor="w", padx=12, pady=(12,6))
    tk.Label(map_tab,
             text="Este panel mostrará la ubicación estimada por telemetría.\n"
                  "Aún no hay fuente de telemetría configurada.",
             bg=BG_COLOR, fg=FG_COLOR, justify="left").pack(anchor="w", padx=12, pady=4)

    # Ajustar alto de la ventana al contenido de la pestaña Configuración
    def _adjust_height_to_cfg(_e=None):
        try:
            # cfg_tab es el contenedor interior (inner) del canvas scrollable
            inner = cfg_tab
            canvas = getattr(inner, "_canvas_ref", None)
            if canvas is None:
                return
            win.update_idletasks()
            # Overhead = altura de ventana actual - altura del canvas visible
            overhead = max(0, win.winfo_height() - canvas.winfo_height())
            content_h = inner.winfo_reqheight()
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            max_h = int(sh * 0.9)
            min_h = 280
            desired_h = min(max_h, max(min_h, content_h + overhead))
            # Mantener la posición actual (no recentrar). Ajustar para que
            # la ventana no salga de la pantalla si el nuevo alto la cortara.
            ww = max(600, win.winfo_width())
            nx = win.winfo_x()
            ny = win.winfo_y()
            # Clamp dentro de pantalla
            nx = max(0, min(nx, sw - ww))
            ny = max(0, min(ny, sh - desired_h))
            win.geometry(f"{ww}x{desired_h}+{nx}+{ny}")
        except Exception:
            pass

    # Llamar tras construir todo para que existan tamaños reales
    win.after(60, _adjust_height_to_cfg)

    # Reajustar cuando se vuelve a la pestaña Configuración
    def _on_tab_changed(_evt=None):
        try:
            if nb.index('current') == 0:  # índice 0 => Configuración
                _adjust_height_to_cfg()
        except Exception:
            pass
    nb.bind('<<NotebookTabChanged>>', _on_tab_changed)



def open_edit_client_info(root, state, on_saved=None):
    """Ventana para EDITAR info de cliente/obra/equipo (se guarda en ConfigStore)."""
    win = tk.Toplevel(root)
    set_icon(win)
    win.title("Editar Información")
    win.configure(bg=BG_COLOR)
    win.geometry("600x520")
    # Mostrar encima y recibir foco (transient respecto a la ventana padre)
    try:
        win.transient(root)
        win.lift()
        win.attributes("-topmost", True)
        win.focus_force()
    except Exception:
        pass

    frm = tk.Frame(win, bg=BG_COLOR)
    frm.pack(fill="both", expand=True, padx=16, pady=16)

    cfg = state.cfg.data

    def mk_row(r, label, key, width=40, initial=None):
        tk.Label(frm, text=label, bg=BG_COLOR, fg=FG_COLOR
                ).grid(row=r, column=0, sticky="e", padx=8, pady=6)
        val = cfg.get(key, "") if initial is None else initial
        var = tk.StringVar(value=str(val or ""))
        ent = tk.Entry(frm, textvariable=var, width=width)
        ent.grid(row=r, column=1, sticky="w", padx=6, pady=6)
        return var

    row = 0
    tk.Label(frm, text="Editar datos del proyecto", font=("Arial", 16, "bold"),
             bg=BG_COLOR, fg=FG_COLOR).grid(row=row, column=0, columnspan=2, sticky="w", pady=(0,10)); row+=1

    v_cliente   = mk_row(row, "Cliente:", "cliente"); row+=1
    v_obra      = mk_row(row, "Obra:", "obra"); row+=1
    v_ubicacion = mk_row(row, "Ubicación:", "ubicacion"); row+=1
    v_contacto  = mk_row(row, "Contacto:", "contacto"); row+=1
    v_email     = mk_row(row, "Email:", "email"); row+=1
    v_telefono  = mk_row(row, "Teléfono:", "telefono"); row+=1
    v_camid     = mk_row(row, "Nombre del equipo:", "camera_id"); row+=1

    def _save():
        try:
            state.cfg.set(
                cliente=v_cliente.get(),
                obra=v_obra.get(),
                ubicacion=v_ubicacion.get(),
                contacto=v_contacto.get(),
                email=v_email.get(),
                telefono=v_telefono.get(),
                camera_id=v_camid.get(),
            )
            # Mostrar confirmación en la barra de estado (arriba) para que sea visible
            try:
                if state is not None and getattr(state, 'lbl_status_general', None) is not None:
                    try:
                        state.lbl_status_general.config(text="Información actualizada.")
                    except Exception:
                        pass
            except Exception:
                pass
            # Además mostrar cuadro modal como antes (parentado a la ventana de edición)
            try:
                try:
                    win.lift()
                    win.attributes("-topmost", True)
                except Exception:
                    pass
                messagebox.showinfo("Guardado", "Información actualizada.", parent=win)
            except Exception:
                pass
            try:
                root.event_generate("<<INFO_UPDATED>>", when="tail")
            except Exception:
                pass
            if callable(on_saved):
                def _safe_on_saved():
                    try:
                        on_saved()
                    except Exception as _e:
                        try:
                            logging.getLogger().exception("on_saved callback failed")
                        except Exception:
                            pass
                        try:
                            if _tele_log_error:
                                _tele_log_error(_e, {"phase": "on_saved_callback"})
                        except Exception:
                            pass

                try:
                    # Ejecutar la callback de refresco de forma asíncrona en el loop
                    # de eventos para evitar reentradas que provocan errores de widget
                    root.after(0, _safe_on_saved)
                except Exception:
                    try:
                        _safe_on_saved()
                    except Exception:
                        pass
            win.destroy()
        except Exception as e:
            try:
                messagebox.showerror("Guardar", f"Error al guardar:\n{e}", parent=win)
            except Exception:
                try:
                    messagebox.showerror("Guardar", f"Error al guardar:\n{e}")
                except Exception:
                    pass

    btns = tk.Frame(win, bg=BG_COLOR)
    btns.pack(fill="x", padx=16, pady=8)
    tk.Button(btns, text="Guardar", command=_save,
              bg=BTN_COLOR, fg=BTN_TEXT_COLOR, bd=0,
              font=("Arial", 12, "bold"), padx=12, pady=8
             ).pack(side="right", padx=6)
    tk.Button(btns, text="Cancelar", command=win.destroy,
              bg=BG_COLOR, fg=FG_COLOR, bd=0,
              font=("Arial", 12), padx=12, pady=8
             ).pack(side="right", padx=6)


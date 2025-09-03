# ui/dialogs.py
# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import messagebox
from config.settings import BG_COLOR, FG_COLOR, BTN_COLOR, BTN_TEXT_COLOR, ICON_PATH

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
    """
    Muestra información de la app y (si hay `state`) datos guardados en la configuración.
    Incluye un botón para editar la información (requiere `state`).
    """
    win = tk.Toplevel(root)
    set_icon(win)
    win.title("Información")
    win.configure(bg=BG_COLOR)
    win.geometry("580x460")

    frm = tk.Frame(win, bg=BG_COLOR)
    frm.pack(fill="both", expand=True, padx=16, pady=16)

    tk.Label(frm, text="Katcam - Información", font=("Arial", 16, "bold"),
             bg=BG_COLOR, fg=FG_COLOR).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

    # Valores seguros por defecto si no hay state
    cfg = getattr(state, "cfg", None)
    data = getattr(cfg, "data", {}) if cfg else {}

    version      = data.get("version", "1.0.0")
    autor        = data.get("autor", "KreativerTech")
    soporte      = data.get("soporte", "support@kreativer.tech")

    camera_id    = data.get("camera_id", "")
    cliente      = data.get("cliente", "")
    obra         = data.get("obra", "")
    ubicacion    = data.get("ubicacion", "")
    contacto     = data.get("contacto", "")  # Mantengo tu clave actual
    email        = data.get("email", "")
    telefono     = data.get("telefono", "")
    gps_lat      = data.get("gps_lat", "")
    gps_lon      = data.get("gps_lon", "")
    photo_dir    = data.get("photo_dir", getattr(state, "photo_dir", ""))
    drive_dir    = data.get("drive_dir", getattr(state, "drive_dir", ""))

    row = 1
    def add_row(label, value):
        nonlocal row
        tk.Label(frm, text=label, bg=BG_COLOR, fg=FG_COLOR
                ).grid(row=row, column=0, sticky="e", padx=8, pady=4)
        tk.Label(frm, text=value or "-", bg=BG_COLOR, fg=BTN_COLOR,
                 font=("Arial", 11, "bold")).grid(row=row, column=1, sticky="w", padx=8, pady=4)
        row += 1

    add_row("Versión:", version)
    add_row("Autor:", autor)
    add_row("Soporte:", soporte)

    tk.Label(frm, text="Proyecto / Sitio", font=("Arial", 14, "bold"),
             bg=BG_COLOR, fg=FG_COLOR).grid(row=row, column=0, columnspan=2, sticky="w", pady=(12, 6)); row += 1
    add_row("Nombre del equipo:", camera_id)
    add_row("Cliente:", cliente)
    add_row("Obra:", obra)
    add_row("Ubicación:", ubicacion)
    add_row("Contacto:", contacto)
    if email or telefono:
        add_row("Email:", email)
        add_row("Teléfono:", telefono)
    if gps_lat or gps_lon:
        add_row("GPS (lat, lon):", f"{gps_lat} , {gps_lon}")

    tk.Label(frm, text="Carpetas", font=("Arial", 14, "bold"),
             bg=BG_COLOR, fg=FG_COLOR).grid(row=row, column=0, columnspan=2, sticky="w", pady=(12, 6)); row += 1
    add_row("Fotos:", photo_dir)
    add_row("Google Drive:", drive_dir)

    def _open_edit():
        if state is None:
            messagebox.showinfo("Editar", "Abre esta ventana desde la app principal con un estado válido.")
            return
        win.destroy()
        open_edit_client_info(root, state)

    tk.Button(frm, text="Editar información…", command=_open_edit,
              bg=BTN_COLOR, fg=BTN_TEXT_COLOR, bd=0,
              font=("Arial", 12, "bold"), padx=12, pady=8
             ).grid(row=row, column=0, columnspan=2, sticky="w", padx=8, pady=(12, 0))


def open_edit_client_info(root, state):
    """Ventana para EDITAR info de cliente/obra/equipo (se guarda en ConfigStore)."""
    win = tk.Toplevel(root)
    set_icon(win)
    win.title("Editar Información")
    win.configure(bg=BG_COLOR)
    win.geometry("600x540")

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

    tk.Label(frm, text="Coordenadas GPS (opcional)", font=("Arial", 12, "bold"),
             bg=BG_COLOR, fg=FG_COLOR).grid(row=row, column=0, columnspan=2, sticky="w", pady=(10,4)); row+=1
    v_lat       = mk_row(row, "Latitud:", "gps_lat", width=18); row+=1
    v_lon       = mk_row(row, "Longitud:", "gps_lon", width=18); row+=1

    def _save():
        # Guardar en config
        state.cfg.set(
            cliente=v_cliente.get(),
            obra=v_obra.get(),
            ubicacion=v_ubicacion.get(),
            contacto=v_contacto.get(),
            email=v_email.get(),
            telefono=v_telefono.get(),
            camera_id=v_camid.get(),
            gps_lat=v_lat.get(),
            gps_lon=v_lon.get()
        )
        messagebox.showinfo("Guardado", "Información actualizada.")
        try:
            # Notificar a la ventana principal por si quiere refrescar encabezado u otros
            root.event_generate("<<INFO_UPDATED>>", when="tail")
        except Exception:
            pass
        win.destroy()

    tk.Button(win, text="Guardar", command=_save,
              bg=BTN_COLOR, fg=BTN_TEXT_COLOR, bd=0,
              font=("Arial", 12, "bold"), padx=12, pady=8
             ).pack(pady=(12, 4))


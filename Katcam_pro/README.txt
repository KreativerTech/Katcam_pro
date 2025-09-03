
# Katcam Pro (refactor)

Esta es una reorganización modular del proyecto original, manteniendo el comportamiento:
- Transmisión / Foto / Timelapse / Maniobra / Sync
- Header y footer amarillos, botón con contorno, logo de empresa a la derecha
- Configuración en ventana con pestañas (lazy)

## Estructura

```
app.py
config/
  settings.py
  storage.py
services/
  stream.py
  capture.py
  timelapse.py
  maniobra.py
  sync.py
hardware/
  system_metrics.py
ui/
  main_window.py
  image_panel.py
  dialogs.py
  config_window.py
infra/
  logging_setup.py        # usa el que ya tienes en tu proyecto
assets/
```

> Reutiliza tus módulos `video_capture.camera_manager` y `camera.take_photo` existentes.

## Ejecutar
```
python app.py
```

Si necesitas arrancar con `main.py`, renombra `app.py` a `main.py`.

# Katcam Pro

Software de captura de fotos, transmisión en vivo y timelapse para proyectos de obra,
desarrollado por **KreativerTech**.

---

## 🚀 Instalación

1. Clona o descomprime el proyecto en tu PC con Windows.
2. Crea un entorno virtual:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate

# Instalador de Speech Studio

Plantilla de [xyz-installer](https://github.com/xyz-rainbow/xyz-installer) (Inno Setup 6). El asistente conserva las fotos y el estilo cyberpunk: cabecera `#0E1016`, marcos `#FF10F0`, pasos y barra `#39FF14`, `banner_side.bmp`, `banner_header.bmp`, `app_icon.ico`, `Final_Mockup.jpg` e `Icono_Original.jpg`.

La instalación por defecto es `C:\Program Files\Rainbow Technology\Speech Studio`. No usa `%LOCALAPPDATA%` para el programa. Hace falta administrador. El modo portable sigue disponible y no escribe la clave de desinstalación.

Los **datos de usuario** (ajustes, modelos, perfiles, salidas) viven en `%LOCALAPPDATA%\Speech Studio` en instalaciones normales, o en `{app}\data` en modo portable / legado. La desinstalación no borra esos datos.

## Runtime para el usuario final

El instalador **no** requiere Python, Node, Rust ni `uv` en el equipo de destino.

En tiempo de **compilación**, `installer/windows/build.ps1`:

1. Empaqueta CrispASR **CPU** desde `runtime/bin/cpu` (obligatorio).
2. Opcionalmente incluye CUDA si se pasa `-IncludeCuda` o el usuario marca la tarea CUDA en el asistente (descarga verificada en post-instalación).
3. Genera un intérprete autocontenido en `runtime/python` con `scripts/package_runtime.py` (python-build-standalone + dependencias core/STT CPU).

`installer/setup-env.ps1` es solo para desarrollo o reparación avanzada: crea `runtime/envs/*` con `uv` en la máquina de build. **No** forma parte del recorrido de usuario final.

## Compilar (Windows)

Hace falta el `speech-studio.exe` de `npx tauri build --no-bundle`, Inno Setup 6, `uv` en la máquina de build y CrispASR CPU:

```powershell
.\scripts\fetch-crispasr.ps1 -Variant cpu
npx tauri build --no-bundle
.\installer\windows\build.ps1
```

El resultado queda en `installer\Output\` como `SpeechStudio_<version>_Setup.exe`. Nunca entregues el `.exe` suelto de `target/release` como sustituto del Setup.

## Linux / macOS

Los workflows en `.github/workflows/build-installers.yml` generan `.deb` / `.dmg` con runtime unix (`scripts/fetch_unix_runtime.py`, `scripts/prepare_unix_payload.py`). Validar en equipo limpio antes de declarar soporte; una compilación CI no basta.

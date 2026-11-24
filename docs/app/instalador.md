# Instalador

## Ahora

`installer/windows/` es la plantilla de [xyz-installer](https://github.com/xyz-rainbow/xyz-installer): mismas fotos (`banner_side.bmp`, `banner_header.bmp`, `app_icon.ico`, `Final_Mockup.jpg`, `Icono_Original.jpg`) y el mismo estilo de cabecera, marcos y barra. `installer/windows/build.ps1` empaqueta el `.exe`, `backend/`, `scripts/notify.ps1` y `setup-env.ps1`, y compila `installer/Output/SpeechStudio_0.1.0_Setup.exe`.

La plantilla apunta a `{autopf}\XYZ-Productions\Speech Studio`. No usa `%LOCALAPPDATA%`. Hace falta administrador. `data\` se conserva al desinstalar. En la prueba silenciosa `/DIR` se ignoró y el programa quedó en `C:\Program Files (x86)\XYZ-Productions\Speech Studio`.

`installer/setup-env.ps1` crea con `uv` y Python 3.12 `runtime/envs/{core,qwen,stt,xtts}` a partir de `requirements-*.txt`. Para XTTS instala primero `torch`/`torchaudio`/`torchcodec` (`--torch-backend=auto`) y después `requirements-xtts.txt`. `build.ps1` copia `runtime/bin/cuda/` y `runtime/bin/cpu/` (tras `scripts/fetch-crispasr.ps1 -Variant both`). El selector GPU/CPU de la app elige la variante. Los pesos no van en el instalador.

Al publicar un tag `v*`, el workflow de release compila `speech-studio.exe` (`tauri build --no-bundle`), lanza `build.ps1` y adjunta `SpeechStudio_*_Setup.exe`. La app busca `backend/` y `runtime/envs/core` (con fallback legacy `.venvs/core`) subiendo desde su carpeta.

## Pendiente

- Hacer que el `/DIR` silencioso respete la carpeta pedida. La instalación de prueba cayó en `C:\Program Files (x86)\XYZ-Productions\Speech Studio`.
- Paquete de macOS y Linux. CI enlaza el shell de Linux (`cargo build` en Ubuntu 24.04, debug, sin empaquetar) y hace `cargo check` y clippy en macOS. No hay AppImage, `.deb` ni bundle de macOS: los sidecars de Python no van dentro. El icono de bandeja y los toasts están en el código. En Linux y macOS el clic primario abre el menú; en macOS el icono se marca como plantilla (`icon_as_template`). Los toasts salen como Speech Studio (`notify-send -a` en Linux y el proceso de la app en macOS). Esas sesiones de escritorio no se han probado. El instalador de Windows sigue siendo el único paquete. El MSI y el NSIS de `tauri build` no instalan Python.

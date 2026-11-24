# Instalador

## Ahora

`installer/windows/` es la plantilla de [xyz-installer](https://github.com/xyz-rainbow/xyz-installer): mismas fotos (`banner_side.bmp`, `banner_header.bmp`, `app_icon.ico`, `Final_Mockup.jpg`, `Icono_Original.jpg`) y el mismo estilo de cabecera, marcos y barra. `installer/windows/build.ps1` empaqueta el `.exe`, `backend/`, `scripts/notify.ps1` y `setup-env.ps1`, y compila `installer/Output/SpeechStudio_0.1.0_Setup.exe`.

La ruta por defecto es `C:\Program Files\XYZ-Productions\Speech Studio`. No usa `%LOCALAPPDATA%`. Hace falta administrador. `data\` se conserva al desinstalar.

`installer/setup-env.ps1` crea con `uv` y Python 3.12 `.venvs/core`, `.venvs/qwen` y `.venvs/stt` a partir de `requirements-*.txt`. Esos pines salen de los entornos ya creados a mano. `xtts` tiene un manifiesto vacío y no se instala.

`npx tauri build` sigue produciendo el `.exe` suelto y, de paso, MSI y NSIS. Esos bundles no son este instalador.

La app se desarrolla en `N:\`, que es un `subst` de `Z:\[🛠️] [Tools]\xyz-speech-studio`. El `.exe` busca `backend/` y `.venvs/core` subiendo desde su carpeta.

## Pendiente

- Ejecutar `SpeechStudio_0.1.0_Setup.exe` en una instalación limpia. El script está preparado; esa instalación no se ha lanzado.
- Entorno `xtts` cuando exista `xtts_worker.py`.
- README de arranque en la raíz del repo.
- Compilación de macOS y Linux. El icono de la bandeja y los toasts de esos sistemas están en el código para probarlos cuando exista esa compilación. En Linux y macOS el clic primario abre el menú; en macOS el icono se marca como plantilla (`icon_as_template`). Los toasts usan `notify-send` y `osascript`. Windows es el único objetivo compilado. No hay binario de Linux ni de macOS, y no se han probado.

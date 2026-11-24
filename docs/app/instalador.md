# Instalador

## Ahora

`installer/windows/` es la plantilla de [xyz-installer](https://github.com/xyz-rainbow/xyz-installer): mismas fotos (`banner_side.bmp`, `banner_header.bmp`, `app_icon.ico`, `Final_Mockup.jpg`, `Icono_Original.jpg`) y el mismo estilo de cabecera, marcos y barra. `installer/windows/build.ps1` empaqueta el `.exe`, `backend/`, `scripts/notify.ps1` y `setup-env.ps1`, y compila `installer/Output/SpeechStudio_0.1.0_Setup.exe`.

La ruta por defecto es `C:\Program Files\XYZ-Productions\Speech Studio`. No usa `%LOCALAPPDATA%`. Hace falta administrador. `data\` se conserva al desinstalar.

`installer/setup-env.ps1` crea con `uv` y Python 3.12 `.venvs/core`, `.venvs/qwen`, `.venvs/stt` y `.venvs/xtts`. Para XTTS instala primero `torch`, `torchaudio` y `torchcodec` con `--torch-backend=auto`, y después `requirements-xtts.txt` (`coqui-tts==0.28.0`). Ese paso no se ha ejecutado. Los pesos no van en el instalador.

Al publicar un tag `v*`, el workflow de release compila `speech-studio.exe` en Windows (`tauri build --no-bundle`), lanza `build.ps1` y adjunta `SpeechStudio_*_Setup.exe` a la release. `npx tauri build` en local sigue pudiendo emitir MSI y NSIS. Esos bundles no son este instalador y no se suben.

La app se desarrolla en `N:\`, que es un `subst` de `Z:\[🛠️] [Tools]\xyz-speech-studio`. El `.exe` busca `backend/` y `.venvs/core` subiendo desde su carpeta.

## Pendiente

- Ejecutar `SpeechStudio_0.1.0_Setup.exe` en una instalación limpia. El script está preparado; esa instalación no se ha lanzado.
- Ejecutar `setup-env.ps1` para crear `.venvs/xtts`. El script ya lo pide y no se ha lanzado.
- README de arranque en la raíz del repo.
- Paquete de macOS y Linux. CI enlaza el shell de Linux (`cargo build` en Ubuntu 24.04, debug, sin empaquetar) y hace `cargo check` y clippy en macOS. No hay AppImage, `.deb` ni bundle de macOS: los sidecars de Python no van dentro. El icono de bandeja y los toasts están en el código. En Linux y macOS el clic primario abre el menú; en macOS el icono se marca como plantilla (`icon_as_template`). Los toasts usan `notify-send` y `osascript`. Esas sesiones de escritorio no se han probado. El instalador de Windows sigue siendo el único paquete.

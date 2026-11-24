# Instalador

## Ahora

`installer/windows/` es la plantilla de [xyz-installer](https://github.com/xyz-rainbow/xyz-installer): mismas fotos (`banner_side.bmp`, `banner_header.bmp`, `app_icon.ico`, `Final_Mockup.jpg`, `Icono_Original.jpg`) y el mismo estilo de cabecera, marcos y barra. `installer/windows/build.ps1` empaqueta el `.exe`, `backend/`, `scripts/notify.ps1` y `setup-env.ps1`, y compila `installer/Output/SpeechStudio_0.1.0_Setup.exe`.

La plantilla apunta a `{autopf}\XYZ-Productions\Speech Studio`. No usa `%LOCALAPPDATA%`. Hace falta administrador. `data\` se conserva al desinstalar. En la prueba silenciosa `/DIR` se ignoró y el programa quedó en `C:\Program Files (x86)\XYZ-Productions\Speech Studio`.

`installer/setup-env.ps1` crea con `uv` y Python 3.12 `.venvs/core`, `.venvs/qwen`, `.venvs/stt` y `.venvs/xtts` a partir de `requirements-core.txt`, `requirements-qwen.txt`, `requirements-stt.txt` y `requirements-xtts.txt`. Para XTTS instala primero `torch`, `torchaudio` y `torchcodec` con `--torch-backend=auto`, y después `requirements-xtts.txt` (`coqui-tts==0.28.0` y `six==1.17.0`). El 24 de noviembre de 2026 una instalación silenciosa de `SpeechStudio_0.1.0_Setup.exe` quedó en `C:\Program Files (x86)\XYZ-Productions\Speech Studio`. `setup-env.ps1` salió con código 0 y creó los cuatro `.venvs`. `/DIR` en silencio ignoró la ruta pedida; la plantilla sigue en `{autopf}\XYZ-Productions\Speech Studio`. Los pesos no van en el instalador. Una carga de XTTS falló una vez porque faltaba `six`, hasta `pip install six`.

Al publicar un tag `v*`, el workflow de release compila `speech-studio.exe` en Windows (`tauri build --no-bundle`), lanza `build.ps1` y adjunta `SpeechStudio_*_Setup.exe` a la release. `npx tauri build` en local sigue pudiendo emitir MSI y NSIS. Esos bundles no son este instalador y no se suben.

La app consulta `releases/latest` de este repo (al abrir y cada 6 horas, más el botón Buscar actualizaciones). En Windows descarga ese `.exe` y lo ejecuta. Un `.dmg`/`.pkg` o un AppImage/`.deb`/`.rpm` en la misma release se usa en macOS y Linux. Hoy la release `v0.1.0` solo adjunta el setup de Windows.

La app se desarrolla en `N:\`, que es un `subst` de `Z:\[🛠️] [Tools]\xyz-speech-studio`. El `.exe` busca `backend/` y `.venvs/core` subiendo desde su carpeta.

## Pendiente

- Hacer que el `/DIR` silencioso respete la carpeta pedida. La instalación de prueba cayó en `C:\Program Files (x86)\XYZ-Productions\Speech Studio`.
- Paquete de macOS y Linux. CI enlaza el shell de Linux (`cargo build` en Ubuntu 24.04, debug, sin empaquetar) y hace `cargo check` y clippy en macOS. No hay AppImage, `.deb` ni bundle de macOS: los sidecars de Python no van dentro. El icono de bandeja y los toasts están en el código. En Linux y macOS el clic primario abre el menú; en macOS el icono se marca como plantilla (`icon_as_template`). Los toasts salen como Speech Studio (`notify-send -a` en Linux y el proceso de la app en macOS). Esas sesiones de escritorio no se han probado. El instalador de Windows sigue siendo el único paquete. El MSI y el NSIS de `tauri build` no instalan Python.

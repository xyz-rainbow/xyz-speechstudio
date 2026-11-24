# Instalador de Speech Studio

Plantilla de [xyz-installer](https://github.com/xyz-rainbow/xyz-installer) (Inno Setup 6). El asistente conserva las fotos y el estilo cyberpunk: cabecera `#0E1016`, marcos `#FF10F0`, pasos y barra `#39FF14`, `banner_side.bmp`, `banner_header.bmp`, `app_icon.ico`, `Final_Mockup.jpg` e `Icono_Original.jpg`.

La instalación por defecto es `C:\Program Files\XYZ-Productions\Speech Studio`. No usa `%LOCALAPPDATA%`. Hace falta administrador. El modo portable sigue disponible y no escribe la clave de desinstalación.

`data\` (modelos, perfiles y audios) se conserva al desinstalar. El acceso directo usa `speech-studio.ico`.

## Compilar

Hace falta el `speech-studio.exe` de `npx tauri build` e Inno Setup 6.

```powershell
.\installer\windows\build.ps1
```

El resultado queda en `installer\Output\SpeechStudio_0.1.0_Setup.exe`.

Al instalar, `setup-env.ps1` crea con `uv` y Python 3.12 los entornos `.venvs\core`, `.venvs\qwen`, `.venvs\stt` y `.venvs\xtts` desde `requirements-core.txt`, `requirements-qwen.txt`, `requirements-stt.txt` y `requirements-xtts.txt`. XTTS instala PyTorch con `--torch-backend=auto` y luego `coqui-tts==0.28.0` y `six==1.17.0`. Hace falta `uv` en el equipo de destino y WebView2.

El 24 de noviembre de 2026 se ejecutó una instalación silenciosa. El programa quedó en `C:\Program Files (x86)\XYZ-Productions\Speech Studio`, `setup-env.ps1` salió con código 0 y creó los `.venvs`. `/DIR` en silencio ignoró la ruta pedida. La plantilla sigue en `{autopf}\XYZ-Productions\Speech Studio`. El CI de Linux compila el shell y no hay AppImage ni `.deb`. macOS sigue sin paquete.

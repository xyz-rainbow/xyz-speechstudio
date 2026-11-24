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

Al instalar, `setup-env.ps1` crea con `uv` y Python 3.12 los entornos `.venvs\core`, `.venvs\qwen`, `.venvs\stt` y `.venvs\xtts`. XTTS instala PyTorch con `--torch-backend=auto` y luego `coqui-tts==0.28.0`. Ese script no se ha ejecutado. Hace falta `uv` en el equipo de destino y WebView2.

Ese setup todavía no se ha ejecutado en esta máquina. Linux y macOS siguen pendientes.

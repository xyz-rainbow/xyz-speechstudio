# Instalador de Speech Studio

Plantilla de [xyz-installer](https://github.com/xyz-rainbow/xyz-installer) (Inno Setup 6). El asistente conserva las fotos y el estilo cyberpunk: cabecera `#0E1016`, marcos `#FF10F0`, pasos y barra `#39FF14`, `banner_side.bmp`, `banner_header.bmp`, `app_icon.ico`, `Final_Mockup.jpg` e `Icono_Original.jpg`.

La instalación por defecto es `C:\Program Files\Rainbow Technology\Speech Studio`. No usa `%LOCALAPPDATA%`. Hace falta administrador. El modo portable sigue disponible y no escribe la clave de desinstalación.

`data\` (modelos, perfiles y audios) se conserva al desinstalar. El acceso directo usa `speech-studio.ico`.

## Compilar

Hace falta el `speech-studio.exe` de `npx tauri build` e Inno Setup 6.

```powershell
.\installer\windows\build.ps1
```

El resultado queda en `installer\Output\SpeechStudio_0.2.1_Setup.exe`.

Al instalar, `setup-env.ps1` crea con `uv` y Python 3.12 los entornos `runtime\envs\core` y el entorno unificado `runtime\envs\pytts` (PyTorch con `--torch-backend=auto`, `coqui-tts==0.28.0`, `f5-tts`, `fish-speech`, `onnxruntime` y `espeakng-loader`) desde `requirements-core.txt` y `requirements-pytts.txt`. Si `runtime\bin\cuda\` y `runtime\bin\cpu\` están en el payload (tras `scripts\fetch-crispasr.ps1`), Qwen3-TTS, Kokoro, Piper, Chatterbox, CosyVoice3, Parakeet y Whisper usan CrispASR siguiendo el selector GPU/CPU de la app. Hace falta `uv` en el equipo de destino y WebView2.

El 24 de noviembre de 2026 se ejecutó una instalación silenciosa de la `0.1.0` en `C:\Program Files (x86)\XYZ-Productions\Speech Studio`. El CI de Linux compila el shell; no hay AppImage/`.deb` ni bundle macOS.

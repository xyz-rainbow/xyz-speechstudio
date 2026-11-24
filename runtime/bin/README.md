# CrispASR binary (`runtime/bin`)

Speech Studio uses [CrispASR](https://github.com/CrispStrobe/CrispASR) as the preferred shared C++ runtime for Piper, F5-TTS GGUF, and (when GGUF voices are present) Kokoro.

The **TopBar GPU / CPU selector** (`tts_device`) picks which build to run:

| Selector | Path |
| --- | --- |
| GPU | `runtime/bin/cuda/crispasr.exe` |
| CPU | `runtime/bin/cpu/crispasr.exe` |

If only one variant is installed, the other selector falls back (CPU on a CUDA-only install adds `--no-gpu`).

## Install both variants

```powershell
.\scripts\fetch-crispasr.ps1
# or explicitly:
.\scripts\fetch-crispasr.ps1 -Variant both
```

Override with `CRISPASR_BIN` (full path). When the selector is CPU and `CRISPASR_BIN` points at a CUDA build, `--no-gpu` is still passed.

## Check

```text
runtime\bin\cuda\crispasr.exe --backend piper -m auto --tts "Hello GPU" --tts-output out-gpu.wav
runtime\bin\cpu\crispasr.exe  --backend piper -m auto --tts "Hello CPU" --tts-output out-cpu.wav
```

The Inno payload copies `cuda/` and `cpu/` when present (`installer/windows/build.ps1`).

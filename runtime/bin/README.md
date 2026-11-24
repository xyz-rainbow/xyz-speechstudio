# CrispASR binary (`runtime/bin`)

Speech Studio uses [CrispASR](https://github.com/CrispStrobe/CrispASR) as the preferred shared C++ runtime for Piper, F5-TTS GGUF, and (when GGUF voices are present) Kokoro.

## Install

1. Download a release asset for your OS from  
   https://github.com/CrispStrobe/CrispASR/releases/latest  
   (Windows: `crispasr-windows-x86_64-cuda.zip` or `…-cpu.zip`).
2. Extract so the executable is here:
   - Windows: `runtime/bin/crispasr.exe`
   - Linux/macOS: `runtime/bin/crispasr`
3. Or set `CRISPASR_BIN` to the full path of the binary.

Optional helper (Windows):

```powershell
.\scripts\fetch-crispasr.ps1
```

## Check

```text
runtime/bin/crispasr --backend piper -m auto --tts "Hello" --tts-output out.wav
```

When the binary is present, the catalog promotes Piper (and F5 GGUF) to `runtime_supported: true`.

# Investigación CrispASR — Migración Total, XTTS v2 / Fish Audio y Retirada de Workers Python

Fecha de investigación: **2026-11-26**  
Repositorio upstream analizado: [`CrispStrobe/CrispASR`](https://github.com/CrispStrobe/CrispASR) (HEAD `ad22a04`, 126 forks, 0 PRs abiertas al momento de consulta).

---

## 1. Capacidades actuales compiladas en `crispasr.exe`

Al consultar `runtime/bin/cpu/crispasr.exe --list-backends-json`, el binario incluido en Speech Studio compila **144 backends** en C++ (`ggml`):
- **71 backends TTS** (**36 con `voice-cloning` nativo** vía `--voice <ref.wav>` y `--ref-text "..."`, incluidos `qwen3-tts`, `f5-tts`, `chatterbox`, `cosyvoice3-tts`, `orpheus`, `indextts`, `bark`, `tada`, `pocket-tts`, `outetts`, `vibevoice-1.5b`, `dots-tts`, `kokoro`, `piper`, etc.).
- **64 backends STT**, incluidos `whisper`, `parakeet`, `moonshine`, `canary`, `sensevoice`, `granite`, `voxtral`, `cohere`, `qwen3`, `funasr`, `paraformer`, `wav2vec2`, `nemotron`, `gigaam`.
- **130+ scripts oficiales de conversión a GGUF** en `models/convert-*-to-gguf.py` dentro de `CrispStrobe/CrispASR` (incluidos `convert-qwen3-tts-to-gguf.py`, `convert-chatterbox-to-gguf.py`, `convert-cosyvoice3-to-gguf.py`, `convert-f5-tts-to-gguf.py`, `convert-orpheus-to-gguf.py`, `convert-indextts-to-gguf.py`, etc.).

---

## 2. Estado de XTTS v2 y Fish Audio en CrispASR (Upstream & Forks)

Se revisaron:
1. Los 144 backends registrados en `crispasr.exe --list-backends-json`.
2. Las issues históricas y recientes, commits recientes y la lista de `models/convert-*.py` en `CrispStrobe/CrispASR`.

**Conclusión:**
- **Ni XTTS v2 (`coqui-tts`) ni Fish Audio (`fish-speech` 1.5)** existen en `CrispStrobe/CrispASR` ni en los conversores oficiales `models/convert-*-to-gguf.py`.
- **Motivo técnico (viabilidad de portar a C++ / `ggml` para PR upstream):**
  1. **XTTS v2**: requiere portar e integrar **cuatro sub-redes heterogéneas** dentro de un mismo pipeline C++:
     - Encoder de DVAE / VQ-VAE discreto para tokens de audio,
     - Transformer GPT-2 autoregresivo condicionado por latentes de hablante (Perceiver Resampler),
     - Encoder de hablante ECAPA/H/ASP,
     - Decodificador HiFi-GAN condicionado con embedding de hablante + *conditioning latent*, además del normalizador/tokenizador multilingüe de Coqui (`vocab.json`).
     - Estimación para PR upstream: ~2.500–4.000 líneas de C++/ggml + script `convert-xtts-to-gguf.py` + batería de paridad numérica (`tools/`).
  2. **Fish Speech 1.5**: requiere portar el modelo Dual-AR (slow Llama + fast codebook head), el códec **Firefly-GAN VQ-FSQ** (8 codebooks a 21 Hz con convoluciones 1D traspuestas personalizadas y Snake/ConvNeXt) y el tokenizador `tiktoken` + semántica de tokens de control.
     - Estimación para PR upstream: ~2.000–3.500 líneas de C++/ggml + `convert-fish-speech-to-gguf.py`.
- **Por qué no conviene invertir ese esfuerzo frente a los nativos de CrispASR:**
  - CrispASR ya implementa **nativamente en C++ con GGUFs oficiales en `cstr/*-GGUF`** modelos de clonación superiores y activos:
    - **Qwen3-TTS 1.7B Base** (`cstr/qwen3-tts-1.7b-base-GGUF`)
    - **CosyVoice3 0.5B** (`cstr/cosyvoice3-0.5b-2512-GGUF`, con soporte *cross-lingual* `-tl` / `-sl`)
    - **Chatterbox Turbo** (`cstr/chatterbox-turbo-GGUF`)
    - **IndexTTS 1.5** (`cstr/indextts-1.5-GGUF`)
    - **F5-TTS GGUF F16** (`cstr/f5-tts-GGUF`)
    - **Orpheus 3B** (`cstr/orpheus-3b-base-GGUF`)

---

## 3. Hoja de ruta si en el futuro se quiere abrir PR en `CrispStrobe/CrispASR`

Si se decide implementar **XTTS v2** o **Fish Speech 1.5** como PR upstream en `CrispStrobe/CrispASR`:
1. Tomar como plantilla el backend `indextts` (`models/convert-indextts-to-gguf.py` + backend GPT+BigVGAN en `src/`), ya que su arquitectura (GPT-2 autoregresivo + vocoder neuronal) es la más parecida a XTTS v2.
2. Reutilizar las capas GPT-2 / Llama ya presentes en `ggml` dentro de CrispASR y añadir el bloque Perceiver + HiFiGAN/Firefly-GAN como tensores separados en un único archivo GGUF.
3. Añadir un harness de paridad en `tools/` comparando el primer frame mel/PCM contra PyTorch antes de abrir la PR en `CrispStrobe/CrispASR`.

---

## 4. Arquitectura Híbrida Actual: CrispASR Persistente + `.venvs/pytts` Unificado

Estado verificado tras las pruebas reales en RTX 2060 (6 GB VRAM):
- **CrispASR Persistente (`--server` + `POST /v1/audio/speech`)**:
  - `piper`, `kokoro`, `qwen3-tts` (incluida clonación), `chatterbox` (Multilingual + Turbo EN), `cosyvoice3-tts`, `orpheus` e `indextts` corren nativamente en `crispasr.exe --server --no-punctuation`.
  - Mantener el servidor HTTP persistente elimina la recarga del GGUF tras cada `Play` (bajando la síntesis caliente de Qwen3-TTS a **0.59–0.65 s** por frase) y permite liberar VRAM al instante desde `Eject` o al cambiar a un worker GPU en Python.
  - Se envía `spoken_disclaimer: false` + `marking_attestation` por petición para evitar el prefijo hablado en inglés manteniendo trazabilidad de operador.
  - **Kokoro 54 voces**: las voces faltantes de `onnx-community/Kokoro-82M-v1.0-ONNX` (incluidas `ef_dora`, `em_alex`, `em_santa`) se empaquetan automáticamente en GGUF v3 (`kokoro-voice-<id>.gguf`) al vuelo en `~/.cache/crispasr`.
- **eSpeak NG nativo CPU (`backend/orchestrator/espeak_engine.py`)**: usa `espeak-ng.dll` vía `ctypes` + datos copiados a ruta ASCII temporal (< 0.2 s CPU, 0 VRAM, sin depender de Piper ni prefijos).
- **Entorno Python Unificado (`.venvs/pytts`)** y selector por modelo (`CrispASR` / `Python`):
  - **Compatibilidad comprobada en 1 solo venv**: `coqui-tts==0.28.0` + `f5-tts==1.1.22` + `fish-speech @ v1.5.1` + `onnxruntime` + `espeakng-loader` coexisten en `.venvs/pytts` fijando `numpy>=1.26.4,<2` y `pyarrow<19` (evitando el choque `pyarrow>=20` con `numpy 1.26.4`), parcheando `torchaudio.load` con `soundfile` (evita fallo de `torchcodec` sin FFmpeg compartido en Windows) y adaptando `GPT2InferenceModel.forward` en XTTS v2 para aceptar tanto `tuple` (`transformers 4.46`) como `cache` (`transformers 5.x`).
  - Los modelos con ambos soportes (`Qwen3-TTS`, `F5-TTS`) exponen un selector compacto `CrispASR | Python` en `Models`; los que no tienen backend CrispASR (`XTTS v2`, `Fish Speech 1.5`, `KittenTTS 2 Mini`, `eSpeak NG`) no muestran la opción CrispASR.
- **STT:** `whisper`, `parakeet`, `moonshine`, `canary`, `sensevoice`, `granite`, `voxtral`, `cohere`, `qwen3-asr`, `funasr`, `paraformer`, `wav2vec2` corren en `crispasr.exe` (`faster-whisper` como alternativa Python).

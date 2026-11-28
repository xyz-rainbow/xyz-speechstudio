# GPT-SoVITS — Arquitectura y Diseño Propuesto (Pendiente)

> [!NOTE]
> **Estado actual:** Documento de diseño solamente. GPT-SoVITS **no** está instalado ni incluido en el catálogo activo (`BUILTIN_MODELS`) ni se presenta como motor operativo en esta versión.

---

## 1. Objetivo

Integrar **GPT-SoVITS** como motor aislado de clonación expresiva y *few-shot* multilingüe (ES/EN/JA/ZH/KO) sin contaminar el entorno core de Speech Studio ni duplicar pesos GGUF en el binario principal.

---

## 2. Arquitectura aislada (Python Worker / Sidecar)

Igual que `f5_worker.py`, `fish_worker.py` y `xtts_worker.py`, GPT-SoVITS exige dependencias PyTorch específicas (sovits v2/v3/v4, Hubert, CN-Hubert, BERT multilingüe). Por ello debe ejecutarse en un entorno virtual separado:

1. **Entorno aislado:** `runtime/envs/gpt_sovits/` (bajo `resolve_runtime_envs_root()`), gestionado bajo demanda.
2. **Worker HTTP local:** `backend/workers/gpt_sovits_worker.py` en `127.0.0.1:<puerto_efimero>` con endpoints:
   - `GET /health`
   - `POST /load` (`gpt_ckpt`, `sovits_pth`, `bert_dir`, `cnhubert_dir`)
   - `POST /synthesize` (`text`, `text_lang`, `ref_audio_path`, `prompt_text`, `prompt_lang`, `out_path`, `top_k`, `top_p`, `temperature`)
3. **Gestión VRAM:** Supervisado por `supervisor.ensure_vram_or_evict(...)` con estimación ~3.2–4.5 GB VRAM en GPU o ejecución CPU opcional.

---

## 3. Contrato de audio y perfiles

- **Audio de referencia:** 3–10 s (óptimo ~5–8 s), WAV mono PCM 16-bit a 32 kHz (o 24 kHz re-muestreado por el worker), limpio y sin música de fondo.
- **Transcripción obligatoria:** Requiere `ref_text` y `prompt_lang` precisos para alinear tokens semánticos AR/SoVITS.
- **Compatibilidad con Perfiles / Persona:**
  - `switch_profile_engine(pid, "gpt-sovits", preserve_original=True)` adaptará desde `ref_original_path` sin modificar la grabación original ni la transcripción original (`ref_original_text`).

---

## 4. Requisitos pendientes antes de activar en catálogo

- Definir descargas verificadas por archivo desde Hugging Face (`lj1995/GPT-SoVITS`) sin depender de scripts remotos no pinneados.
- Empaquetar y validar el instalador del entorno `gpt_sovits` en Windows y Linux.
- Añadir pruebas de carga/descarga en `supervisor`, liberación de VRAM y síntesis real antes de marcar `runtime_supported: True`.

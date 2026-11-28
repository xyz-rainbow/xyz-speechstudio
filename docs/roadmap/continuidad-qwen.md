# Continuidad de Speech Studio

Decisiones del 28 de noviembre de 2026. Este plan recoge trabajo pendiente. Para xyz-Ioquendo se eligió Qwen3-TTS 1.7B Base Q4_K_M. Álvaro en es-ES gustó tanto en Q4 como en Q8. En la RTX 2060, Q4 produjo 8,08 s en 2,48 s de síntesis y el pico total observado fue de 4568 MiB. La referencia válida fue el MP3 completo con su TXT. Conservar ambos como prueba de regresión. Chatterbox queda fuera del pack. GPT-SoVITS queda para una futura card en Featured, previa validación de idiomas, referencias de 3–10 s y runtime distribuible.

Los cambios descritos aquí están en un árbol compartido con trabajo paralelo y aún no representan una release validada. «Prueba dirigida» significa código y archivos simulados salvo que se indique una sesión real o un binario ejecutado.

| Área | Implementado en código | Verificación actual | Siguiente cierre |
| --- | --- | --- | --- |
| Variantes de modelos | Inventario por archivos, multi-variante + borrado seguro TTS, `Piper` unificado GGUF, `compute_type` Faster-Whisper, bloqueo honesto de runtimes no soportados | `test_model_hub_variants.py` (`12`), TypeScript, `--dry-run-resolve` CosyVoice3 | Alternar y borrar cuantizaciones descargadas desde UI con pesos reales en todas las familias |
| Reproducción TTS por tramos | Token de generación, control de avance, `ChunkedAudioPlayer` autoplay corregido, nombres WAV sanitizados y liberación de audio | `chunked_playback.test.mjs` (`8`), `test_chunked_tts_real.py` + eSpeak WAV real en install limpia `0.2.3` | Escucha interactiva prolongada en WebView2 |
| Persona | Sidebar ordenada, catálogo local operativo (`/api/persona/local-catalog` + audio) + remoto k3s, SHA-256, adaptación no destructiva y manifiestos k3s | Tests Python (`test_persona_e2e_integration`, `test_persona_install`, `test_persona_and_profiles`, `test_persona_k3s_service`), `test_persona_frontend.mjs` | Desplegar `services/persona/` en k3s y publicar audios con consentimiento |
| xyz-Ioquendo | Pack desacoplado de pesos Qwen, selector propio en Synthesize, filtro por locale y fallback en API local OpenAI | `test_voice_packs`, `test_xyz_ioquendo_e2e` (`6`), install/repair en Setup `0.2.3` y síntesis real Q8/CrispASR | Decisión legal antes de publicar las 453 voces; validar CTA Q4 con descarga completa |
| Instaladores y Update | Versión objetivo `0.2.3`; workflows multiplataforma, payload Python autónomo + CrispASR CPU + vertical slice `xyz-ioquendo` (corregido `build.ps1`), subprocesos ocultos en Windows | Build Windows `0.2.3` recompilado (`66890420…7a2a`, Setup `8e1ec34d…d0f7`), install portable + upgrades `0.2.1 -> 0.2.3` y `0.2.2 -> 0.2.3` verificados en build anterior `fa4e3482…9a88`, `test_updates.py` (`23`) | Revalidar smoke portable/UAC sobre `8e1ec34d…d0f7`, pruebas limpias `.deb`/`.dmg` y publicación coordinada `v0.2.3` |

## 1. Instalación y actualización

Estado actualizado (`0.2.3` en árbol de trabajo): la release publicada actual en GitHub sigue siendo `v0.2.2` (contiene `SpeechStudio_0.2.2_Setup.exe` anterior `24dbc9e8…`, `Speech.Studio.0.2.2_amd64.deb` `83e19341…` cuyo nombre difiere de `SpeechStudio_<VER>_amd64.deb` en `release.yml`, `SHA256SUMS.txt` y sin `.dmg`). Localmente se han recompilado para `0.2.3` (con soporte de los 79 idiomas de `xyz-Ioquendo` en UI y ocultación de consola en SAPI5/conversión GGUF) `speech-studio.exe` (`14.224.896` B, sha256 `66890420…7a2a`) y `SpeechStudio_0.2.3_Setup.exe` (`91.012.572` B, sha256 `8e1ec34d…d0f7`). En el build previo `0.2.3` (`fa4e3482…9a88`) se verificaron instalación portable limpia (sin Python/`uv`/Node en `PATH`, sin Vite), síntesis/guardado eSpeak, reinicio persistente, cero procesos huérfanos y actualizaciones reales `0.2.1 -> 0.2.3` y `0.2.2 -> 0.2.3` conservando `settings.json` y `profiles.json`. Faltan revalidar este último artefacto en modo portable/UAC en Windows, pruebas limpias Linux/macOS y credenciales Apple para firmar/notarizar `.dmg`.

Validar Update con dos versiones de prueba consecutivas. Comprobar detección por sistema y arquitectura, integridad del paquete, progreso, cancelación, fallo de red y reinicio con perfiles y ajustes conservados. Entregar el primer setup al superar instalación limpia y actualización. Publicar únicamente artefactos comprobados, con versión y hashes.

## 2. Variantes en todas las cards

El catálogo informa las cuantizaciones instaladas a partir de los archivos reales para los modelos con variantes declaradas. El resolver de Qwen respeta cualquier cuantización de su catálogo indicada en el ID activo y exige un par completo de talker y tokenizer. Featured permite descargar otra variante sin borrar la instalada, activar Qwen, Chatterbox, IndexTTS, CosyVoice3, Orpheus y Kokoro, y borrar una cuantización concreta. En CrispASR se pasa el fichero primario elegido y, cuando corresponde, el compañero de la misma variante. Al borrar una variante activa se selecciona otra instalada, si existe; el servidor CrispASR se expulsa antes de liberar sus ficheros. Las pruebas locales cubren Qwen Q4/Q8/BF16 simultáneos, IndexTTS Q4/Q8 con vocoder compartido y la selección LLM/Flow de CosyVoice3. `tsc --noEmit` y once pruebas dirigidas pasan. Falta la prueba desde la app con pesos reales.

CosyVoice3 pasa ahora explícitamente el LLM y el Flow de la variante elegida; CrispASR 0.8.55 confirmó mediante `--dry-run-resolve` la pareja Q4_K + Flow Q8_0 sin cargar pesos. Una prueba dirigida comprueba la pareja F16 en la ruta de síntesis. Falta sintetizar audio real con ambas variantes instaladas. Piper asocia calidad a voces concretas y necesita selección por voz, no una variante global; sus ficheros ONNX de catálogo tampoco corresponden a los GGUF que utiliza CrispASR. La card no debe prometer activación individual hasta corregir esa integración.
Para Faster-Whisper, INT8, INT8/FP16 y FP16 son modos de cómputo del mismo checkpoint descargado. Ahora se muestran como opciones instaladas de un único peso y el ID activo pasa el `compute_type` elegido al worker; no se ofrece borrado individual de esos modos. Falta verificar el cambio de cómputo en una sesión STT real. Los checkpoints ONNX de Parakeet y Moonshine continúan sin activación porque el runtime está marcado como no soportado.

El cierre requiere instalar Q4 y Q8 simultáneamente, alternar, reiniciar, comprobar los pesos usados y eliminar una variante sin romper la otra. Repetir en los motores con pares de archivos. Los modos de Faster-Whisper se validan con el mismo checkpoint. La compatibilidad de instalaciones previas sin metadatos debe probarse con copias de datos reales.

## 3. Pack xyz-Ioquendo

Módulo `voice_packs.py`, muestra vertical (`es-ES` Álvaro y `en-GB` Alfie) empaquetada y selector independiente `xyz-Ioquendo` en Synthesize respaldado por Qwen3-TTS Base Q4_K_M/Q8_0, además de su exposición en el catálogo local de Persona; el catálogo completo de 453 pares sigue fuera del instalador hasta revisión de licencia. Ver [estado del pack](../packs/xyz-ioquendo.md). Pendiente: decisión de redistribución antes de publicar el pack completo y validar la descarga completa Q4_K_M desde una instalación virgen.

## 4. Perfiles y diseño de voz

El backend conserva el audio y transcripción originales (`ref_original_path`, `ref_original_text`), adapta por motor y recorta a 12 s alineando texto; Qwen VoiceDesign (`Personalizada` / `Custom` en Perfiles y Synthesize) cuenta con endpoints propios, preview y guardado. Queda por validar interactivamente en una sesión con GPU la secuencia completa VoiceDesign -> Qwen Base Q4 en VRAM de 6 GB.

## 5. Subtítulos, atajo y audio continuo

La reproducción por tramos tiene token de generación, descarte de respuestas obsoletas, autoplay corregido en `ChunkedAudioPlayer`, nombres WAV sanitizados para Windows y liberación de audio; pasan 8 pruebas de lógica, pruebas reales de sesión multi-tramo eSpeak y guardado en instalación limpia `0.2.3`. Falta escucha interactiva prolongada en WebView2 y pruebas reales con voz/foco para Subtítulos y atajo por sistema operativo.

## 6. Persona

Persona ofrece catálogo local operativo (`/api/persona/local-catalog` y `/api/persona/local-audio/{slug}`) y origen remoto configurable k3s, con `POST /api/persona/install-remote`, `GET /api/persona/install-progress`, cambio de motor no destructivo y restauración original ya montados en `persona_routes.py` y verificados con pruebas Python y Node sobre servidor HTTP simulado. Falta desplegar `services/persona/` en k3s con audios consentidos para cerrar la descarga entre dos equipos reales.

## 7. Publicación y mantenimiento

Ejecutar las pruebas de instalación y del núcleo en los tres sistemas. Integrar los paquetes validados en el workflow de release. Documentar runtimes, workers, soporte por plataforma y recuperación de descargas. Revisar gitignore, pesos, cachés y artefactos generados antes del commit y release.


# Persona — Biblioteca de voces y adaptación por motor

## Ahora

Persona añade una sección en la barra lateral (`src/components/PersonaView.tsx`, `src/components/Sidebar.tsx`, `src/App.tsx`) para descubrir, inspeccionar y descargar perfiles de voz prefabricados o compartidos, así como preparar borradores locales de publicación sin subir archivos a servicios externos.

La vista funciona actualmente con una fuente de prueba local claramente identificada (`local_preview` en `src/services/personaClient.ts`) y permite configurar una URL base real (`remote_k3s`) para conectarse al servicio alojado en k3s/Rancher (`services/persona/`).

La descarga remota ya cuenta con módulo (`backend/orchestrator/persona_install.py`), rutas montadas en `backend/orchestrator/persona_routes.py` (`POST /api/persona/install-remote` y `GET /api/persona/install-progress`), cliente UI (`PersonaView.tsx`), cambio de motor y restauración del audio original desde Perfiles, con pruebas automatizadas sobre servidor HTTP simulado. Las fichas de demostración `local_preview` sin audio muestran claramente su estado de demo y no permiten una instalación ficticia. Falta únicamente desplegar el servicio `services/persona/` en el clúster k3s y publicar un catálogo real con consentimiento.

### Archivos implementados

- `src/types/persona.ts`: contratos TypeScript del catálogo (`PersonaRecord`, `PersonaAudioSpec`, `PersonaConsentRecord`), configuración de fuente (`PersonaConfig`), borradores de publicación (`PersonaPublishDraft`, `PersonaLocalDraft`) y evaluación de compatibilidad (`EngineCompatibilityEvaluation`).
- `src/services/personaClient.ts`: cliente HTTP configurable (`checkPersonaLibraryHealth`, `fetchPersonaCatalog`), validación de URL, filtros locales, fixtures `LOCAL_PREVIEW_PERSONAS`, validación de borradores (`validatePublishDraft`) y constructor de payload (`buildPublishApiPayload`).
- `src/utils/personaCompatibility.ts`: reglas explícitas por motor (`ENGINE_AUDIO_REQUIREMENTS`), evaluación de conversiones necesarias y detección honesta de motores sin clonación (`unsupported_no_cloning`).
- `src/components/PersonaView.tsx`: catálogo con búsqueda, filtro opcional por idioma, filtro de origen (`Todos` / `Prefabricados` / `Compartidos`), estados de carga/vacío/error, progreso en tiempo real, modal de detalle con matriz de compatibilidad y modal de preparación de publicación. Las fichas `local_preview` sin audio real se etiquetan como `Demo · sin audio` y nunca se marcan como instaladas.
- `backend/orchestrator/persona_install.py`: descarga verificada e instalación atómica de Personas remotas (`install_remote_persona`, `get_install_progress`) validando ID (`invalid_id`), mismo origen HTTP/HTTPS y redirecciones seguras (`disallowed_url`), límite de 50 MiB (`file_too_large`), cabecera mágica de formato (`wav`, `mp3`, `flac`, `ogg`, `m4a`), respuesta no truncada (`truncated_response`) y checksum SHA-256 (`sha256_mismatch`) antes de llamar a `profiles.create_profile` con desambiguación automática (`Nombre (Persona)`) para no sobrescribir perfiles personales y preservando intacto `ref_original_path`.
- `backend/orchestrator/persona_routes.py` montado en `backend/orchestrator/main.py`: expone `POST /api/persona/install-remote`, `GET /api/persona/install-progress`, `POST /api/profiles/{profile_id}/switch-engine` y `POST /api/profiles/{profile_id}/restore-original`.
- `backend/orchestrator/audio_adaptation.py`, `backend/orchestrator/profiles.py` y `src/components/ProfilesView.tsx`: cambio de motor no destructivo por card y editor conservando intacto `ref_original_path`, generación de copias adaptadas bajo `<profile_dir>/adapted/` y botón **Restaurar audio original**.
- `services/persona/` (`app.py`, `storage.py`, `Dockerfile`, `requirements.txt`, `k8s/*.yaml`): servicio HTTP `/v1` con SQLite WAL, almacenamiento atómico en PVC, validación obligatoria de consentimiento/formato/tamaño, autenticación Bearer para escritura y manifiestos Kustomize listos para k3s/Rancher (sin desplegar ni publicar audios).

---

## Contrato HTTP propuesto (`v1` en k3s / Rancher)

Base configurable desde UI (`PersonaConfig.library_url`, por ejemplo `https://persona.example.internal`):

| Método y ruta | Propósito | Respuesta / Campos clave |
| --- | --- | --- |
| `GET /v1/health` | Comprobar disponibilidad y versión | `{ "status": "ok", "api_version": "v1" }` |
| `GET /v1/personas?q=&language=&origin=&page=&page_size=` | Listar/buscar perfiles públicos | `{ "api_version": "v1", "items": [PersonaRecord], "total": number }` |
| `GET /v1/personas/{id}` | Metadatos completos de una Persona | `PersonaRecord` |
| `GET /v1/personas/{id}/audio` | Descargar audio de referencia (o redirect prefirmado) | Binario audio + cabecera/campo `sha256` verificable |
| `POST /v1/personas` | Publicar perfil compartido (autenticado) | Multipart (`metadata` JSON + `audio`) o JSON + presigned PUT; exige `consent.speaker_consent_confirmed = true` |
| `DELETE /v1/personas/{id}` | Retirada / moderación del propietario o admin | `{ "deleted": true, "id": "..." }` |

### Estructura mínima de `PersonaRecord`

```json
{
  "id": "uuid-o-slug-estable",
  "slug": "alvaro-castellano",
  "version": "1.0.0",
  "name": "Álvaro",
  "language": "Spanish",
  "locale": "es-ES",
  "origin": "prebuilt",
  "description": "Locución narrativa limpia.",
  "author": "Rainbow Voice Pack",
  "tags": ["narrador", "es-ES"],
  "ref_text": "Transcripción exacta del clip de referencia.",
  "audio": {
    "format": "wav",
    "sample_rate_hz": 24000,
    "channels": 1,
    "duration_s": 8.6,
    "sha256": "hex...",
    "size_bytes": 412844,
    "download_url": "https://persona.k3s.local/v1/personas/alvaro-castellano/audio"
  },
  "consent": {
    "speaker_consent_confirmed": true,
    "provenance_type": "pack_reference",
    "provenance_note": "Referencia verificada con licencia documentada.",
    "license": "proprietary-pack",
    "attribution": "Rainbow Technology"
  },
  "recommended_engines": ["qwen", "f5", "xtts"],
  "created_at": "2026-11-28T00:00:00Z",
  "updated_at": "2026-11-28T00:00:00Z"
}
```

---

## Conversiones de audio requeridas por motor TTS

El sistema nunca modifica el archivo original del usuario (`ref_original_path`). Al cambiar de motor o usar un perfil, se generan copias derivadas (`ref_24k.wav`, `ref_trim_24k.wav`, `adapted/adapted_<engine>.wav`):

| Motor | ¿Clona voz? | Formato / Frecuencia objetivo | Canales | Duración | Texto de referencia (`ref_text`) |
| --- | --- | --- | --- | --- | --- |
| **Qwen3-TTS** (`qwen`) | Sí | PCM16 WAV @ `24000 Hz` | Mono (`1`) | Recomendado `6–15 s` | Recomendado |
| **Chatterbox / Turbo** | Sí | PCM16 WAV @ `24000 Hz` | Mono (`1`) | Recomendado `5–15 s` | Opcional |
| **CosyVoice3** | Sí | PCM16 WAV @ `24000 Hz` | Mono (`1`) | Recomendado `5–15 s` | Recomendado |
| **IndexTTS 1.5** | Sí | PCM16 WAV @ `24000 Hz` | Mono (`1`) | Recomendado `5–15 s` | Opcional |
| **F5-TTS** (`f5` / `f5-tts`) | Sí | PCM16 WAV @ `24000 Hz` | Mono (`1`) | Máx. `12 s` (auto-recorte no destructivo a `11 s`) | **Obligatorio** para duración |
| **XTTS v2** (`xtts`) | Sí | PCM16 WAV @ `22050 Hz` (`24 kHz` soportado) | Mono (`1`) | Recomendado `6–12 s` | Opcional |
| **Fish Speech 1.5** (`fish`) | Sí | PCM16 WAV @ `44100 Hz` (VQGAN) | Mono (`1`) | Recomendado `5–15 s` | Recomendado |
| **Kokoro 82M** | **No** | Voces integradas (`voices_*.bin`) | — | — | No aplica |
| **Piper** | **No** | Voces ONNX/GGUF integradas | — | — | No aplica |
| **Orpheus 3B** | **No** | Voces predefinidas en catálogo | — | — | No aplica |
| **KittenTTS 2 Mini** | **No** | Packs `voices_<lang>.npz` | — | — | No aplica |
| **eSpeak NG / Windows SAPI 5** | **No** | Voces del motor / sistema Windows | — | — | No aplica |

---

## Acordado

- No prometer compatibilidad universal: tanto las tarjetas como el modal de detalle marcan explícitamente `No voice cloning / Sin clonación` cuando el modelo activo o catalogado usa `builtin_voices`.
- Mantener la publicación real deshabilitada hacia servicios externos hasta que exista el backend propio en k3s; mientras tanto, el flujo guarda borradores validados en local y genera el JSON exacto del contrato `POST /v1/personas`.
- Conservar siempre `ref_original_path` intacto en `profiles.py` al cambiar de motor o recortar a `<=12s`.

---

## Pendiente

### Despliegue operativo del servicio Persona en k3s / Rancher

Los manifiestos y el código del servicio ya están en `services/persona/`, pero **no se han desplegado en el clúster ni se han publicado audios reales**. Para ponerlo en marcha:

1. Construir y subir la imagen Docker de `services/persona/Dockerfile` a tu registro privado.
2. Ajustar `image:` en `services/persona/k8s/deployment.yaml` y el dominio TLS en `services/persona/k8s/ingress.yaml`.
3. Crear el `Secret` `persona-secrets` con un `PERSONA_WRITE_TOKEN` aleatorio real (sin usar `secret.example.yaml` literal).
4. Aplicar con `kubectl apply -k services/persona/k8s` (o desde Rancher) y configurar esa URL HTTPS en **Persona → Fuente** dentro de Speech Studio.

### Mejoras opcionales futuras

- Persistir `persona_library_url` dentro de `AppSettings` (`backend/orchestrator/config.py`, `src/types/index.ts`, `src/services/api.ts`) además de `localStorage`.
- Enlazar `POST /v1/personas` desde el modal de borrador local de `PersonaView.tsx` cuando el usuario tenga un `PERSONA_WRITE_TOKEN` configurado y decida publicar desde la app.

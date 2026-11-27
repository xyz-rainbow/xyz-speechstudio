# Endpoints

## Ahora

Las rutas internas `/api/*`, incluidos los WebSockets, requieren una conexión desde loopback. Si el cliente envía `Origin`, debe corresponder a Tauri o al desarrollo local. El acceso desde LAN usa las rutas públicas `/v1/*` con el token configurado. Los controles de ajustes, modelos, perfiles y actualizaciones responden 403 desde LAN.

Hay dos usos distintos.

### API local de Speech Studio

Apagada por defecto (`api_endpoint_enabled: false`). Con ella encendida, el orquestador acepta:

- `POST /v1/audio/speech` sintetiza con el perfil y el modelo local activos.
- `POST /v1/audio/transcriptions` transcribe un archivo con faster-whisper.

El bind es `127.0.0.1` salvo que se ponga `0.0.0.0`. El puerto 0 deja que el sidecar elija uno libre. Si hay `api_bearer_token`, la petición tiene que traerlo. Sin el interruptor, estas rutas responden 403. Si `api_bind_host` es `0.0.0.0`, `api_bearer_token` tiene que ser no vacío: no se guarda esa combinación y el orquestador no llega a escuchar en todas las interfaces sin token.

### Proveedores externos

Ajustes guarda endpoints TTS y STT con protocolo `openai`, `elevenlabs` o `deepgram`. Cada tarjeta se puede probar. Si `tts_source` o `stt_source` es `endpoint`, Synthesize y Transcriber usan ese proveedor en lugar del worker local.

La clave se queda en `data/settings.json`, que está fuera de git.

Si `stt_source` es `endpoint`, Live Captions manda las ventanas de voz a ese mismo proveedor (OpenAI-compatible o Deepgram). El PCM entra por `/api/captions/stream`. Ver [live-captions.md](live-captions.md).

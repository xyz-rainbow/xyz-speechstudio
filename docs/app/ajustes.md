# Ajustes

## Ahora

`data/settings.json` no se sube a git. Lo lee el orquestador y, para el hotkey, también Rust al arrancar.

| Campo | Qué hace hoy |
| --- | --- |
| `language` | `en` o `es` |
| `theme`, `accent` | Dark/Light y el color de acento |
| `ascii_fx_enabled`, `ascii_fx_opacity` | Fondo ASCII. Opacidad entre 0.04 y 0.25 |
| `sidebar_collapsed` | Sidebar plegada |
| `models_dir`, `outputs_dir` | Vacío significa `data/models` y `data/outputs` |
| `tts_device`, `stt_device` | `gpu` o `cpu` al arrancar el worker |
| `tts_source`, `stt_source` | `local` o `endpoint` |
| `active_tts_model`, `active_stt_model` | Id del catálogo |
| `active_tts_endpoint_id`, `active_stt_endpoint_id` | Endpoint externo elegido |
| `external_endpoints` | Lista de proveedores. Ver [endpoints.md](endpoints.md) |
| `captions_max_history` | 5–200. La pestaña Subtitles corta el historial de la sesión |
| `notifications_enabled` | Toasts. El texto sigue `language` (`en` o `es`). En Windows los entrega BurntToast. Linux (`notify-send`) y macOS (`osascript`) están escritos y pendientes de compilación, igual que el icono de bandeja de esos sistemas |
| `api_endpoint_enabled` | API OpenAI-compatible. Por defecto apagada |
| `api_bind_host`, `api_fixed_port` | `127.0.0.1` y puerto dinámico si el puerto es 0 |
| `api_bearer_token` | Vacío hasta que se active la API |
| `read_hotkey` | Acelerador físico, o vacío |

La pantalla de Ajustes deja cambiar idioma, tema, ASCII, carpetas, historial de subtítulos, toasts, el hotkey y la API local.

## Pendiente

La aplicación elegida para la captura es estado de la sesión, no un ajuste permanente. El STT sale de `stt_source`, `active_stt_model` y `active_stt_endpoint_id`.

# Speech Studio — estado de la app

Estos archivos describen lo que el código hace hoy y lo que todavía está diseñado. Se actualizan cuando esa parte cambia. El mapa de fases está en [../ROADMAP.md](../ROADMAP.md). El índice de la pull request [#1](https://github.com/xyz-rainbow/xyz-speechstudio/pull/1) (changelog, spec, issues conocidos y bitácora) está en [../README.md](../README.md).

Fecha de este corte: 24 de noviembre de 2026. Ruta de trabajo: `N:\` (`Z:\[🛠️] [Tools]\xyz-speech-studio`).

| Documento | Qué cubre | Estado |
| --- | --- | --- |
| [arquitectura.md](arquitectura.md) | Procesos, entornos y quién habla con quién | Hecho. La captura en vivo no se ha oído |
| [tts.md](tts.md) | Synthesize, perfiles, Qwen, historial | Hecho para Qwen. XTTS reservado |
| [stt.md](stt.md) | Transcribir un archivo | Hecho con faster-whisper |
| [live-captions.md](live-captions.md) | Cómo viaja el audio capturado hasta el texto | Escrito. Sin sesión de audio real |
| [modelos.md](modelos.md) | Catálogo, descarga y qué se puede cargar | Descarga hecha. Carga parcial |
| [interfaz.md](interfaz.md) | Pestañas, temas, overlay | Shell hecho. Subtítulos a la espera de una captura |
| [hotkey.md](hotkey.md) | Leer el texto seleccionado | Hecho en el `.exe`. Sin commit |
| [ajustes.md](ajustes.md) | `data/settings.json` | Hecho |
| [endpoints.md](endpoints.md) | API local y proveedores externos | Hecho |
| [instalador.md](instalador.md) | Empaquetado y entornos `uv` | Sin empezar |

Cada documento tiene tres bloques: **Ahora**, **Acordado** y **Pendiente**. Si un bloque no aplica, se omite.

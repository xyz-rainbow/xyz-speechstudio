# Speech Studio — estado de la app

Estos archivos describen lo que el código hace hoy y lo que todavía está diseñado. Se actualizan cuando esa parte cambia. El mapa de fases está en [../ROADMAP.md](../ROADMAP.md). El índice de la pull request [#1](https://github.com/xyz-rainbow/xyz-speechstudio/pull/1) (changelog, spec, issues conocidos y bitácora) está en [../README.md](../README.md).

Fecha de este corte: 28 de noviembre de 2026. Los cambios de esta sesión siguen en el árbol de trabajo compartido; las pruebas de código no equivalen a una instalación limpia. El estado por fases está en [continuidad-qwen.md](../roadmap/continuidad-qwen.md).

| Documento | Qué cubre | Estado |
| --- | --- | --- |
| [arquitectura.md](arquitectura.md) | Procesos, entornos y comunicación | Revisar frente al runtime empaquetado actual |
| [tts.md](tts.md) | Síntesis, voces, VoiceDesign y audio por tramos | Código, VoiceDesign `--instruct` y pruebas reales locales con CrispASR/eSpeak |
| [persona.md](persona.md) | Biblioteca, adaptación y publicación | UI, descarga verificada e integración local montada; servicio k3s listo sin desplegar |
| [stt.md](stt.md) | Transcripción de archivos y cancelación | Faster-Whisper (`compute_type`), CrispASR Whisper real y `/api/stt/cancel` |
| [live-captions.md](live-captions.md) | Captura hasta overlay | Código en revisión; audio real pendiente por sistema |
| [modelos.md](modelos.md) | Descarga, selección, GGUF unificado y borrado | Pruebas multi-variante, Piper/Kokoro GGUF y bloqueo honesto de runtimes |
| [gpt-sovits.md](gpt-sovits.md) | Arquitectura propuesta GPT-SoVITS | Solo diseño (no instalado ni listado en catálogo activo) |
| [interfaz.md](interfaz.md) | Pestañas, temas y overlay | Revisar junto con Persona y variantes nuevas |
| [hotkey.md](hotkey.md) | Lectura del texto seleccionado | Prueba interactiva en frío pendiente |
| [ajustes.md](ajustes.md) | Persistencia de ajustes | Verificar migración entre paquetes |
| [endpoints.md](endpoints.md) | API local y proveedores externos | Actualizar tras integrar Persona remota |
| [instalador.md](instalador.md) | Empaquetado y entornos | Instalación limpia y Update entre versiones pendientes |

Cada documento tiene tres bloques: **Ahora**, **Acordado** y **Pendiente**. Si un bloque no aplica, se omite.

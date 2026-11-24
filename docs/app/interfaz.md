# Interfaz

## Ahora

Una ventana principal, 880×580, con sidebar de iconos que se pliega. El estado del pliegue se guarda en Ajustes.

Pestañas: Synthesize, Profiles, Transcriber, Subtitles, Models, Settings.

Apariencia:

- Dark por defecto (`#050508`) y Light.
- Acentos Cyber, Emerald, Amber y Rose.
- Fondo ASCII a 30 FPS, con pausa si la ventana no se ve. El interruptor y la opacidad están en Ajustes, no en la barra superior.
- Tarjetas `GlassCard` y botones `BorderBeamButton`.
- Tipografía Inter y JetBrains Mono.

Idiomas de la interfaz: inglés (por defecto) y español. Los archivos son `src/i18n/locales/en.json` y `es.json`.

La barra superior enseña la VRAM en vivo y el toggle GPU/CPU de TTS y de STT. El puerto del orquestador se ve en Ajustes. Además, toda la app se puede inspeccionar y controlar desde terminal con el comando global `speechstudio` (`--status`, `--models`, `--profiles`, `--config`, `play`, `transcribe`, `endpoints`).

Cerrar la ventana la esconde. Salir de verdad está en la bandeja. En Windows el clic izquierdo muestra la ventana. En Linux y macOS ese clic abre el menú y, en macOS, el icono se trata como plantilla. Esas dos compilaciones siguen pendientes.

## Pendiente

Diez idiomas del plan original: italiano, francés, alemán, ruso, chino simplificado, portugués, japonés, coreano, árabe con `dir="rtl"` e hindi.

La pestaña Subtitles elige la app que suena y muestra el STT activo. El overlay pinta la frase del evento `caption`. Falta oír una captura real. Ver [live-captions.md](live-captions.md).

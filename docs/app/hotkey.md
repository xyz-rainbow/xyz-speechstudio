# Hotkey y bandeja

## Ahora

El hotkey lee el texto seleccionado en otra aplicación y lo manda a Synthesize como un Play. El atajo se registra al arrancar desde `settings.json` (`read_hotkey`) en **Windows, Linux y macOS**.

| SO | Lectura de selección | Portapapeles | Si falla |
| --- | --- | --- | --- |
| **Windows** | UI Automation (`selection/windows.rs`), con hook de foco para no perder la selección tras Alt | No se usa | Toast `hotkey.noSelection` |
| **Linux** | Solo selección primaria: `wl-paste --primary` → fallback `xclip -selection primary` | No se usa | Sin tools → `unavailable` + toast de instalar tools; vacío → `noSelection` |
| **macOS** | Aún sin Accessibility reader | — | Código `unsupported` + toast `settings.hotkeyUnsupported` |

### Comportamiento UI (2026-11-28)

- Primer intento y siguientes: mismo handler; Windows reintenta UI Automation 3× (~40 ms) tras el focus hook.
- `empty` / sin texto: toast, **no** cambia a Synthesize.
- `unavailable` (Linux sin tools): toast de herramientas.
- `unsupported` (macOS): toast de no disponible.
- Texto OK: pestaña Synthesize + evento de habla; mismo texto pausa/reanuda; texto nuevo corta y empieza.

Al grabarlo en Ajustes se guarda la tecla física (`KeyboardEvent.code` + modificadores), p. ej. `Ctrl+Alt+KeyM`, `Alt+Shift+Digit7`. Hace falta al menos un modificador. Si el SO rechaza la combinación, el error aparece bajo el campo y no se escribe en settings.

## Bandeja

Abrir, mostrar/ocultar, subtítulos y salir. Cerrar la ventana oculta; salir para el backend. Segunda instancia trae la ventana al frente.

## Comprobado en código

- Registro de atajo al arrancar también en macOS (antes solo Win/Linux).
- Toasts diferenciados empty / unavailable / unsupported.
- Lectura real de selección en apps de terceros: **no** ejecutada en este agente (hace falta escritorio con foco).

## Pendiente

- Probar selección primaria Wayland/X11 y bandeja GNOME/KDE.
- Implementar lectura macOS vía Accessibility API.
- Probar primer atajo justo tras arranque en Windows con texto en Notepad/Edge.

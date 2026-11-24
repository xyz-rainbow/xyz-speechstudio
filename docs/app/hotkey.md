# Hotkey y bandeja

## Ahora

El hotkey lee el texto seleccionado en otra aplicación y lo manda a Synthesize como un Play. La lectura la hace UI Automation en `src-tauri/src/selection.rs`. El portapapeles no se toca.

Al grabarlo en Ajustes se guarda la tecla física, `KeyboardEvent.code`, más los modificadores. Ejemplos: `Ctrl+Alt+KeyM`, `Alt+Shift+Digit7`, `Super+Slash`. No se traduce al carácter que pinta el teclado. En un teclado español, `/` es Shift+7, así que el atajo queda `Alt+Shift+Digit7` si se pulsó esa tecla.

Hace falta al menos un modificador. Escape a solas cancela la grabación. Escape con un modificador sí se puede guardar. Si Windows rechaza la combinación, el error aparece bajo el campo y no se escribe en `settings.json`.

`global-hotkey` registra esa cadena. Los nombres de `code` (`KeyM`, `Digit7`, `Slash`, `NumpadDivide`) coinciden con los que el parser ya acepta.

Pulsar el atajo otra vez con el mismo texto pausa o sigue. Con otro texto, corta y empieza. Si no hay selección, un toast lo dice.

La bandeja tiene mostrar/ocultar, subtítulos y salir. Las etiquetas cambian con el idioma. Una segunda instancia solo trae la ventana al frente.

Este comportamiento está en el `.exe` compilado el 24 de noviembre de 2026.

## Pendiente

Nada de producto.

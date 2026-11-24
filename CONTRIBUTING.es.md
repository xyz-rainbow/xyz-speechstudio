[English](CONTRIBUTING.md) | **Español**

# Contribuir a Speech Studio

Gracias por tomarte el tiempo de contribuir. Lee también el [Código de conducta](CODE_OF_CONDUCT.es.md).

## Cómo ayudar

- Abre un informe de error o una solicitud de función con las plantillas (inglés o español).
- Usa [Discussions](https://github.com/xyz-rainbow/xyz-speechstudio/discussions) para preguntas e ideas.
- Envía una pull request contra la rama por defecto, `main`.

No abras un issue público para una vulnerabilidad. Sigue [SECURITY.md](SECURITY.md).

## Entorno de desarrollo

Hoy la app es solo para Windows. Sigue las secciones **Requisitos**, **Instalación** y **Desarrollo** de [README.es.md](README.es.md) para clonar el repo, crear los tres entornos `.venvs\` y ejecutar `npm run tauri dev`.

Comprobaciones útiles antes de subir cambios:

```powershell
npm run build
python -m compileall backend
pytest -q
```

El CI ejecuta el build del frontend, la compilación de Python + pytest, y `cargo check` de `src-tauri` en Windows.

## Pull requests

1. Crea una rama de trabajo desde `main` (por ejemplo `fix/transcriber-copy` o `docs/api-examples`).
2. Mantén el cambio acotado. No mezcles refactors con correcciones salvo que no se puedan separar.
3. Actualiza [CHANGELOG.md](CHANGELOG.md) y añade una línea en `docs/logs/YYYY-MM.md` en el mismo commit cuando el cambio sea visible o toque el proceso o la documentación.
4. Mantén alineados [README.md](README.md) y [README.es.md](README.es.md) (y las dos guías de contribución) si cambias uno de ellos.
5. No subas secretos, claves de API, perfiles de voz, pesos de modelos ni archivos de `data/`.
6. Espera a que el CI esté en verde. Los responsables fusionan con squash en `main`.

Usa la plantilla de pull request. Explica qué has cambiado, por qué y cómo lo has probado.

## Notas de código

- Frontend: React 19 + TypeScript + Vite + Tailwind en `src/`. `npm run build` debe pasar (`tsc --noEmit` y Vite).
- Escritorio: Rust / Tauri 2 en `src-tauri/`. Este crate usa APIs de Windows y no compila en Linux ni en macOS.
- Backend: orquestador Python en `backend/orchestrator/` y workers en `backend/workers/`. Aún no hay `requirements.txt`; documenta las dependencias nuevas en las tablas del README.
- Los textos de la app están en `src/i18n/locales/en.json` y `es.json`. Mantén el mismo árbol de claves en los dos.
- `spikes/` es histórico; no lo uses como punto de entrada soportado.

## Licencia

El repositorio todavía no incluye un archivo de licencia. Al contribuir aceptas que tu trabajo pueda distribuirse con el proyecto bajo la licencia que publiquen después los responsables.

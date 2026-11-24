[English](CONTRIBUTING.md) | **Español**

# Contribuir a xyz-speechstudio

Gracias por tomarte el tiempo de contribuir. Windows desktop app (Tauri 2 + React/TypeScript + Python FastAPI workers) for local TTS and transcription.

## Licencia y contribuciones

Al abrir un issue o enviar una pull request aceptas la cláusula de contribución de [LICENSE](LICENSE): cedes a Rainbow Technology todos los derechos sobre lo que aportas o, si esa cesión no fuera eficaz, le concedes una licencia perpetua, irrevocable y exclusiva, y garantizas que tienes derecho a aportarlo.

No abras un issue público para una vulnerabilidad; usa el formulario de avisos de seguridad del repositorio si está disponible.

## Entorno de desarrollo

Hoy la app es solo para Windows. Sigue las secciones **Requisitos**, **Instalación** y **Desarrollo** de [README.es.md](README.es.md) para clonar el repo, crear los tres entornos `.venvs\\` y ejecutar `npm run tauri dev`.

Comprobaciones útiles antes de subir cambios:

```powershell
npm run build
python -m compileall backend
pytest -q
```

El CI ejecuta el build del frontend, la compilación de Python + pytest, y `cargo check` de `src-tauri` en Windows.

## Pull requests

1. Crea una rama de trabajo desde la rama por defecto (`main`).
2. Mantén el cambio acotado.
3. Actualiza [CHANGELOG.md](CHANGELOG.md) y añade una línea en `docs/logs/YYYY-MM.md` cuando el cambio sea visible o toque el proceso o la documentación.
4. No subas secretos, claves de API ni datos privados.
5. Espera a que el CI esté en verde si el repositorio tiene workflows. Los responsables fusionan con squash en la rama por defecto.

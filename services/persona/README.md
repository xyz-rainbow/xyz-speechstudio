# Speech Studio — Persona Library Service (k3s / Rancher)

Servicio HTTP `/v1` independiente preparado para alojar la biblioteca de perfiles de voz compartidos en k3s/Rancher.
Este paquete está listo para construir y desplegar, pero **no incluye audios prepublicados ni ha sido desplegado**.

## Endpoints

- `GET /v1/health`
- `GET /v1/personas?q=&language=&origin=&page=&page_size=`
- `GET /v1/personas/{persona_id}`
- `GET /v1/personas/{persona_id}/audio` (incluye cabecera `X-Persona-SHA256`)
- `POST /v1/personas` (multipart `metadata` + `audio`, requiere Bearer token en `PERSONA_WRITE_TOKEN` y `consent.speaker_consent_confirmed = true`)
- `DELETE /v1/personas/{persona_id}` (requiere Bearer token)

## Ejecución local de prueba

```powershell
$env:PERSONA_DATA_DIR = "$env:TEMP\persona-svc-data"
$env:PERSONA_WRITE_TOKEN = "dev-token-local"
$env:PERSONA_AUTOSTART_APP = "1"
uvicorn app:app --host 127.0.0.1 --port 8080
```

## Despliegue en k3s / Rancher (cuando decidas desplegarlo)

1. Construir y subir la imagen desde `services/persona/`:
   ```bash
   docker build -t registry.example.internal/speech-studio/persona:v1 .
   docker push registry.example.internal/speech-studio/persona:v1
   ```
2. Ajustar la imagen en `k8s/deployment.yaml` y el hostname TLS en `k8s/ingress.yaml`.
3. Crear el Secret real (sin usar `secret.example.yaml` literal):
   ```bash
   kubectl create namespace speech-studio-persona --dry-run=client -o yaml | kubectl apply -f -
   kubectl -n speech-studio-persona create secret generic persona-secrets \
     --from-literal=PERSONA_WRITE_TOKEN="<token-aleatorio-fuerte>"
   ```
4. Aplicar con Kustomize o desde Rancher:
   ```bash
   kubectl apply -k services/persona/k8s
   ```

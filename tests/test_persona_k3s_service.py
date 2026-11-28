from __future__ import annotations

import hashlib
import io
import json
import math
import struct
import sys
import wave
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.persona.app import create_app


def _wav_bytes(seconds: float = 1.0, sr: int = 24000) -> bytes:
    buf = io.BytesIO()
    frames = int(sr * seconds)
    pcm = bytearray()
    for i in range(frames):
        pcm.extend(struct.pack("<h", int(7000 * math.sin(2.0 * math.pi * 220.0 * i / sr))))
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(bytes(pcm))
    return buf.getvalue()


def _meta(consent: bool = True, *, pid: str = "demo-clara", lang: str = "Spanish") -> str:
    return json.dumps(
        {
            "id": pid,
            "name": "Clara K3s Test",
            "language": lang,
            "locale": "es-ES" if lang == "Spanish" else "en-US",
            "origin": "shared",
            "description": "Synthesized test payload validating k3s upload & download contract.",
            "ref_text": "Hola, comprobando el servicio Persona en k3s.",
            "tags": ["test", "k3s"],
            "consent": {
                "speaker_consent_confirmed": consent,
                "provenance_type": "self_recorded",
                "provenance_note": "Unit test fixture",
                "license": "cc-by-4.0",
                "attribution": "Test Contributor",
            },
        }
    )


def test_k3s_service_publish_query_download_and_delete(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path / "svc", write_token="secret-k3s-token")
    client = TestClient(app)

    # Starts empty with no bundled audio
    health = client.get("/v1/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "api_version": "v1", "personas_count": 0}

    wav = _wav_bytes()
    wav_sha = hashlib.sha256(wav).hexdigest()

    # Auth enforcement
    no_auth = client.post(
        "/v1/personas",
        data={"metadata": _meta(True)},
        files={"audio": ("clara.wav", wav, "audio/wav")},
    )
    assert no_auth.status_code == 401

    bad_auth = client.post(
        "/v1/personas",
        headers={"Authorization": "Bearer wrong-token"},
        data={"metadata": _meta(True)},
        files={"audio": ("clara.wav", wav, "audio/wav")},
    )
    assert bad_auth.status_code == 403

    # Consent enforcement
    no_consent = client.post(
        "/v1/personas",
        headers={"Authorization": "Bearer secret-k3s-token"},
        data={"metadata": _meta(False)},
        files={"audio": ("clara.wav", wav, "audio/wav")},
    )
    assert no_consent.status_code == 422

    # Invalid file signature rejected
    bad_magic = client.post(
        "/v1/personas",
        headers={"Authorization": "Bearer secret-k3s-token"},
        data={"metadata": _meta(True)},
        files={"audio": ("fake.wav", b"not-a-wav-file", "audio/wav")},
    )
    assert bad_magic.status_code == 422

    # Valid upload
    created = client.post(
        "/v1/personas",
        headers={"Authorization": "Bearer secret-k3s-token"},
        data={"metadata": _meta(True)},
        files={"audio": ("clara.wav", wav, "audio/wav")},
    )
    assert created.status_code == 201, created.text
    rec = created.json()
    assert rec["id"] == "demo-clara"
    assert rec["audio"]["sha256"] == wav_sha
    assert rec["audio"]["download_url"] == "/v1/personas/demo-clara/audio"

    # Catalog & filtering
    listed = client.get("/v1/personas", params={"language": "Spanish", "q": "clara"})
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert client.get("/v1/personas", params={"language": "Japanese"}).json()["total"] == 0

    # Audio stream + hash header
    audio_resp = client.get("/v1/personas/demo-clara/audio")
    assert audio_resp.status_code == 200
    assert audio_resp.headers["x-persona-sha256"] == wav_sha
    assert audio_resp.content == wav

    # Delete
    deleted = client.delete(
        "/v1/personas/demo-clara",
        headers={"Authorization": "Bearer secret-k3s-token"},
    )
    assert deleted.status_code == 200
    assert client.get("/v1/personas/demo-clara/audio").status_code == 404


def test_k3s_service_fails_closed_without_token_and_enforces_size_limit(tmp_path: Path) -> None:
    app_no_token = create_app(data_dir=tmp_path / "no-token", write_token="")
    c1 = TestClient(app_no_token)
    wav = _wav_bytes()
    res = c1.post(
        "/v1/personas",
        headers={"Authorization": "Bearer anything"},
        data={"metadata": _meta(True)},
        files={"audio": ("clara.wav", wav, "audio/wav")},
    )
    assert res.status_code == 503

    app_small = create_app(
        data_dir=tmp_path / "small",
        write_token="tok",
        max_upload_bytes=512,
    )
    c2 = TestClient(app_small)
    too_big = c2.post(
        "/v1/personas",
        headers={"Authorization": "Bearer tok"},
        data={"metadata": _meta(True)},
        files={"audio": ("clara.wav", wav, "audio/wav")},
    )
    assert too_big.status_code == 413


def test_k3s_manifests_present_and_hardened() -> None:
    k8s_dir = ROOT / "services" / "persona" / "k8s"
    expected = {
        "namespace.yaml",
        "pvc.yaml",
        "deployment.yaml",
        "service.yaml",
        "ingress.yaml",
        "kustomization.yaml",
        "secret.example.yaml",
    }
    assert expected.issubset({p.name for p in k8s_dir.iterdir()})

    dep = (k8s_dir / "deployment.yaml").read_text(encoding="utf-8")
    assert "runAsNonRoot: true" in dep
    assert "readOnlyRootFilesystem: true" in dep
    assert "/v1/health" in dep
    assert "persona-data-pvc" in dep

    kust = (k8s_dir / "kustomization.yaml").read_text(encoding="utf-8")
    assert "secret.example.yaml" not in kust

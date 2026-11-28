from __future__ import annotations

import hashlib
import io
import json
import math
import struct
import sys
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.orchestrator import main, persona_install, profiles


def _make_wav_bytes(*, sr: int = 48000, channels: int = 2, seconds: float = 14.0, freq: float = 240.0) -> bytes:
    buf = io.BytesIO()
    frames = int(sr * seconds)
    pcm = bytearray()
    for i in range(frames):
        val = int(9000 * math.sin(2.0 * math.pi * freq * i / sr))
        for _ in range(channels):
            pcm.extend(struct.pack("<h", val))
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(bytes(pcm))
    return buf.getvalue()


@pytest.fixture
def isolated_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    prof_dir = tmp_path / "profiles"
    tmp_dir = tmp_path / "tmp"
    monkeypatch.setattr(profiles, "DEFAULT_PROFILES_DIR", prof_dir)
    monkeypatch.setattr(profiles, "PROFILES_JSON", prof_dir / "profiles.json")
    monkeypatch.setattr(profiles, "ensure_data_dirs", lambda: prof_dir.mkdir(parents=True, exist_ok=True))
    monkeypatch.setattr(persona_install, "DEFAULT_TMP_DIR", tmp_dir)

    with TestClient(main.app, client=("127.0.0.1", 50000)) as client:
        yield client, prof_dir


@pytest.fixture
def sim_persona_server():
    good_wav = _make_wav_bytes(sr=48000, channels=2, seconds=14.0, freq=260.0)
    good_sha = hashlib.sha256(good_wav).hexdigest()
    tampered_wav = _make_wav_bytes(sr=24000, channels=1, seconds=2.0, freq=520.0)

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            return

        def do_GET(self) -> None:
            if self.path == "/v1/health":
                payload = json.dumps({"status": "ok", "api_version": "v1", "personas_count": 1}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return

            if self.path == "/v1/personas":
                payload = json.dumps(
                    {
                        "api_version": "v1",
                        "total": 1,
                        "items": [
                            {
                                "id": "remote-es-alvaro",
                                "slug": "remote-es-alvaro",
                                "version": "1.0.0",
                                "name": "Álvaro",
                                "language": "Spanish",
                                "locale": "es-ES",
                                "origin": "shared",
                                "description": "Remote simulated studio clip.",
                                "author": "Sim Server",
                                "tags": ["sim", "es-ES"],
                                "ref_text": "Hola desde el servidor HTTP simulado.",
                                "audio": {
                                    "format": "wav",
                                    "sample_rate_hz": 48000,
                                    "channels": 2,
                                    "duration_s": 14.0,
                                    "sha256": good_sha,
                                    "size_bytes": len(good_wav),
                                    "download_url": "/v1/personas/remote-es-alvaro/audio",
                                },
                                "consent": {
                                    "speaker_consent_confirmed": True,
                                    "provenance_type": "authorized_actor",
                                    "provenance_note": "Test fixture",
                                    "license": "cc-by-4.0",
                                    "attribution": "Sim Server",
                                },
                                "recommended_engines": ["qwen", "f5", "xtts"],
                                "created_at": "2026-11-28T00:00:00Z",
                                "updated_at": "2026-11-28T00:00:00Z",
                            }
                        ],
                    }
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return

            if self.path == "/v1/personas/remote-es-alvaro/audio":
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(good_wav)))
                self.send_header("X-Persona-SHA256", good_sha)
                self.end_headers()
                self.wfile.write(good_wav)
                return

            if self.path == "/v1/personas/tampered/audio":
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(tampered_wav)))
                self.end_headers()
                self.wfile.write(tampered_wav)
                return

            self.send_response(404)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        yield base_url, good_wav, good_sha
    finally:
        server.shutdown()
        server.server_close()


def test_e2e_remote_install_progress_collision_switch_and_restore(
    isolated_app,
    sim_persona_server,
    tmp_path: Path,
) -> None:
    client, prof_dir = isolated_app
    base_url, good_wav, good_sha = sim_persona_server

    # Pre-seed personal profile with same name "Álvaro" and its own distinct audio
    personal_wav = _make_wav_bytes(sr=24000, channels=1, seconds=1.5, freq=410.0)
    personal_sha = hashlib.sha256(personal_wav).hexdigest()
    personal_src = tmp_path / "personal.wav"
    personal_src.write_bytes(personal_wav)
    personal = profiles.create_profile(
        name="Álvaro",
        language="Spanish",
        engine="qwen",
        ref_audio_path=str(personal_src),
        ref_text="Mi audio personal intacto.",
    )

    # 1. Install remote Persona over real HTTP via mounted /api/persona/install-remote
    resp = client.post(
        "/api/persona/install-remote",
        json={
            "persona_id": "remote-es-alvaro",
            "name": "Álvaro",
            "language": "Spanish",
            "engine": "qwen",
            "ref_text": "Hola desde el servidor HTTP simulado.",
            "library_url": base_url,
            "download_url": "/v1/personas/remote-es-alvaro/audio",
            "sha256": good_sha,
            "audio_format": "wav",
            "expected_size_bytes": len(good_wav),
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sha256"] == good_sha
    assert body["name_disambiguated"] is True
    assert body["profile"]["name"] == "Álvaro (Persona)"
    remote_pid = body["profile"]["id"]

    # 2. Verify /api/persona/install-progress reflects final verified state
    prog_resp = client.get("/api/persona/install-progress")
    assert prog_resp.status_code == 200
    prog = prog_resp.json()
    assert prog["phase"] == "done"
    assert prog["persona_id"] == "remote-es-alvaro"
    assert prog["downloaded"] == len(good_wav)
    assert prog["total"] == len(good_wav)

    # 3. Verify persistence & untouched personal profile via GET /api/profiles
    listed = client.get("/api/profiles")
    assert listed.status_code == 200
    profs = listed.json()["profiles"]
    assert len(profs) == 2
    kept_personal = next(p for p in profs if p["id"] == personal.id)
    assert kept_personal["ref_text"] == "Mi audio personal intacto."
    assert hashlib.sha256(Path(kept_personal["ref_original_path"]).read_bytes()).hexdigest() == personal_sha

    installed_remote = next(p for p in profs if p["id"] == remote_pid)
    assert hashlib.sha256(Path(installed_remote["ref_original_path"]).read_bytes()).hexdigest() == good_sha

    # 4. Trim -> switch-engine -> restore-original over HTTP routes
    trim_resp = client.post(f"/api/profiles/{remote_pid}/trim", json={"max_seconds": 12.0})
    assert trim_resp.status_code == 200
    assert trim_resp.json()["profile"]["ref_trimmed"] is True

    sw_f5 = client.post(
        f"/api/profiles/{remote_pid}/switch-engine",
        json={"engine": "f5", "preserve_original": True},
    )
    assert sw_f5.status_code == 200
    assert sw_f5.json()["profile"]["engine"] == "f5"
    assert (prof_dir / remote_pid / "adapted" / "adapted_f5.wav").is_file()

    sw_xtts = client.post(
        f"/api/profiles/{remote_pid}/switch-engine",
        json={"engine": "xtts", "preserve_original": True},
    )
    assert sw_xtts.status_code == 200
    assert sw_xtts.json()["profile"]["engine"] == "xtts"
    assert (prof_dir / remote_pid / "adapted" / "adapted_xtts.wav").is_file()
    assert hashlib.sha256(Path(sw_xtts.json()["profile"]["ref_original_path"]).read_bytes()).hexdigest() == good_sha

    restore_resp = client.post(f"/api/profiles/{remote_pid}/restore-original")
    assert restore_resp.status_code == 200
    restored = restore_resp.json()["profile"]
    assert restored["ref_trimmed"] is False
    assert restored["ref_duration_s"] == pytest.approx(14.0, abs=0.1)
    assert hashlib.sha256(Path(restored["ref_original_path"]).read_bytes()).hexdigest() == good_sha

    # 5. Non-cloning engine switch rejected with 400
    bad_sw = client.post(
        f"/api/profiles/{remote_pid}/switch-engine",
        json={"engine": "piper", "preserve_original": True},
    )
    assert bad_sw.status_code == 400

    # 6. Tampered HTTP response returns 422 sha256_mismatch and leaves profiles unchanged
    tampered_resp = client.post(
        "/api/persona/install-remote",
        json={
            "persona_id": "tampered",
            "name": "Tampered Voice",
            "language": "Spanish",
            "engine": "qwen",
            "ref_text": "No debe instalarse.",
            "library_url": base_url,
            "download_url": "/v1/personas/tampered/audio",
            "sha256": good_sha,
            "audio_format": "wav",
        },
    )
    assert tampered_resp.status_code == 422
    assert tampered_resp.json()["code"] == "sha256_mismatch"
    assert len(client.get("/api/profiles").json()["profiles"]) == 2


def test_local_persona_catalog_audio_and_install(isolated_app, monkeypatch: pytest.MonkeyPatch) -> None:
    client, prof_dir = isolated_app
    from backend.orchestrator import persona_routes

    monkeypatch.setattr(persona_routes, "resolved_models_dir", lambda _s: prof_dir.parent / "models")
    cat = client.get("/api/persona/local-catalog")
    assert cat.status_code == 200
    items = cat.json()["items"]
    assert len(items) >= 2
    first = items[0]
    assert first["audio"]["local_path"]
    assert first["audio"]["preview_url"] == f"/api/persona/local-audio/{first['slug']}"

    aud = client.get(first["audio"]["preview_url"])
    assert aud.status_code == 200 and len(aud.content) > 100

    bad_aud = client.get("/api/persona/local-audio/nonexistent-slug")
    assert bad_aud.status_code == 404

    created = client.post(
        "/api/profiles",
        json={
            "name": first["name"],
            "language": first["language"],
            "engine": "qwen",
            "ref_audio_path": first["audio"]["local_path"],
            "ref_text": first["ref_text"],
            "build_voice": False,
        },
    )
    assert created.status_code == 200
    assert created.json()["profile"]["name"] == first["name"]


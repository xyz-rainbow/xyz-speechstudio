from __future__ import annotations

import hashlib
import io
import math
import struct
import sys
import wave
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.orchestrator import persona_install, profiles


def _make_wav_bytes(*, sr: int = 48000, channels: int = 2, seconds: float = 1.5, freq: float = 220.0) -> bytes:
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
def isolated_profiles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    prof_dir = tmp_path / "profiles"
    stage_dir = tmp_path / "staging"
    monkeypatch.setattr(profiles, "DEFAULT_PROFILES_DIR", prof_dir)
    monkeypatch.setattr(profiles, "PROFILES_JSON", prof_dir / "profiles.json")
    monkeypatch.setattr(profiles, "ensure_data_dirs", lambda: prof_dir.mkdir(parents=True, exist_ok=True))
    return {"profiles": prof_dir, "staging": stage_dir}


def test_install_remote_persona_success_and_preserves_original(isolated_profiles: dict[str, Path]) -> None:
    wav_bytes = _make_wav_bytes(sr=48000, channels=2, seconds=2.0)
    digest = hashlib.sha256(wav_bytes).hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://persona.k3s.local/v1/personas/es-alvaro/audio"
        return httpx.Response(
            200,
            headers={"Content-Length": str(len(wav_bytes)), "Content-Type": "audio/wav"},
            content=wav_bytes,
        )

    phases: list[str] = []
    req = persona_install.RemotePersonaInstallRequest(
        persona_id="es-alvaro",
        name="Álvaro Remoto",
        language="Spanish",
        engine="qwen",
        ref_text="Hola desde la biblioteca compartida.",
        library_url="https://persona.k3s.local/",
        download_url="/v1/personas/es-alvaro/audio",
        sha256=digest,
        audio_format="wav",
        expected_size_bytes=len(wav_bytes),
    )

    res = persona_install.install_remote_persona(
        req,
        staging_root=isolated_profiles["staging"],
        transport=httpx.MockTransport(handler),
        progress_cb=lambda snap: phases.append(str(snap["phase"])),
    )

    assert res.persona_id == "es-alvaro"
    assert res.sha256 == digest
    assert res.size_bytes == len(wav_bytes)
    assert res.name_disambiguated is False
    assert res.profile.name == "Álvaro Remoto"
    assert Path(res.profile.ref_original_path).is_file()
    assert hashlib.sha256(Path(res.profile.ref_original_path).read_bytes()).hexdigest() == digest
    assert Path(res.profile.ref_24k_path).is_file()
    assert phases[0] == "validating"
    assert "downloading" in phases
    assert "verifying" in phases
    assert "creating_profile" in phases
    assert phases[-1] == "done"
    assert list(isolated_profiles["staging"].iterdir()) == []


def test_install_remote_persona_sha256_mismatch(isolated_profiles: dict[str, Path]) -> None:
    wav_bytes = _make_wav_bytes()
    wrong_hash = "0" * 64

    transport = httpx.MockTransport(
        lambda _req: httpx.Response(
            200,
            headers={"Content-Length": str(len(wav_bytes))},
            content=wav_bytes,
        )
    )
    req = persona_install.RemotePersonaInstallRequest(
        persona_id="bad-hash",
        name="Bad Hash",
        library_url="https://persona.k3s.local",
        download_url="https://persona.k3s.local/v1/personas/bad-hash/audio",
        sha256=wrong_hash,
        audio_format="wav",
    )

    with pytest.raises(persona_install.PersonaInstallError) as exc_info:
        persona_install.install_remote_persona(
            req,
            staging_root=isolated_profiles["staging"],
            transport=transport,
        )

    assert exc_info.value.code == "sha256_mismatch"
    assert profiles.list_profiles() == []
    assert list(isolated_profiles["staging"].iterdir()) == []


def test_install_remote_persona_truncated_response(isolated_profiles: dict[str, Path]) -> None:
    wav_bytes = _make_wav_bytes()
    partial = wav_bytes[: len(wav_bytes) // 2]
    digest = hashlib.sha256(wav_bytes).hexdigest()

    # Case A: server declares full Content-Length but sends truncated body
    transport_short_body = httpx.MockTransport(
        lambda _req: httpx.Response(
            200,
            headers={"Content-Length": str(len(wav_bytes))},
            content=partial,
        )
    )
    req = persona_install.RemotePersonaInstallRequest(
        persona_id="trunc-1",
        name="Truncated",
        library_url="https://persona.k3s.local",
        download_url="/v1/personas/trunc-1/audio",
        sha256=digest,
        audio_format="wav",
    )

    with pytest.raises(persona_install.PersonaInstallError) as exc_a:
        persona_install.install_remote_persona(
            req,
            staging_root=isolated_profiles["staging"],
            transport=transport_short_body,
        )
    assert exc_a.value.code == "truncated_response"

    # Case B: stream raises ReadError mid-transfer
    class _BrokenStream(httpx.SyncByteStream):
        def __init__(self, first_chunk: bytes) -> None:
            self._first = first_chunk

        def __iter__(self):
            yield self._first
            raise httpx.ReadError("connection reset by peer")

    transport_stream_drop = httpx.MockTransport(
        lambda req_in: httpx.Response(
            200,
            headers={"Content-Length": str(len(wav_bytes))},
            stream=_BrokenStream(partial),
            request=req_in,
        )
    )
    with pytest.raises(persona_install.PersonaInstallError) as exc_b:
        persona_install.install_remote_persona(
            req,
            staging_root=isolated_profiles["staging"],
            transport=transport_stream_drop,
        )
    assert exc_b.value.code == "truncated_response"
    assert profiles.list_profiles() == []
    assert list(isolated_profiles["staging"].iterdir()) == []


def test_install_remote_persona_disallowed_url_and_foreign_redirect(
    isolated_profiles: dict[str, Path],
) -> None:
    wav_bytes = _make_wav_bytes()
    digest = hashlib.sha256(wav_bytes).hexdigest()

    foreign_req = persona_install.RemotePersonaInstallRequest(
        persona_id="evil-host",
        name="Evil",
        library_url="https://persona.k3s.local",
        download_url="https://evil.example.com/payload.wav",
        sha256=digest,
        audio_format="wav",
    )
    with pytest.raises(persona_install.PersonaInstallError) as exc_foreign:
        persona_install.install_remote_persona(
            foreign_req,
            staging_root=isolated_profiles["staging"],
            transport=httpx.MockTransport(lambda _r: httpx.Response(200, content=wav_bytes)),
        )
    assert exc_foreign.value.code == "disallowed_url"

    file_req = foreign_req.model_copy(update={"download_url": "file:///C:/Windows/win.ini"})
    with pytest.raises(persona_install.PersonaInstallError) as exc_scheme:
        persona_install.install_remote_persona(
            file_req,
            staging_root=isolated_profiles["staging"],
            transport=httpx.MockTransport(lambda _r: httpx.Response(200, content=wav_bytes)),
        )
    assert exc_scheme.value.code == "disallowed_url"

    redirect_req = foreign_req.model_copy(update={"download_url": "/v1/personas/evil-host/audio"})
    redirect_transport = httpx.MockTransport(
        lambda _r: httpx.Response(302, headers={"Location": "https://other-host.example/steal.wav"})
    )
    with pytest.raises(persona_install.PersonaInstallError) as exc_redirect:
        persona_install.install_remote_persona(
            redirect_req,
            staging_root=isolated_profiles["staging"],
            transport=redirect_transport,
        )
    assert exc_redirect.value.code == "disallowed_url"


def test_install_remote_persona_file_too_large(isolated_profiles: dict[str, Path]) -> None:
    wav_bytes = _make_wav_bytes(seconds=1.0)
    digest = hashlib.sha256(wav_bytes).hexdigest()

    # Case A: Content-Length exceeds limit immediately
    req = persona_install.RemotePersonaInstallRequest(
        persona_id="huge-1",
        name="Too Big",
        library_url="https://persona.k3s.local",
        download_url="/v1/personas/huge-1/audio",
        sha256=digest,
        audio_format="wav",
    )
    transport_cl = httpx.MockTransport(
        lambda _r: httpx.Response(
            200,
            headers={"Content-Length": "999999999"},
            content=wav_bytes,
        )
    )
    with pytest.raises(persona_install.PersonaInstallError) as exc_cl:
        persona_install.install_remote_persona(
            req,
            max_bytes=1024,
            staging_root=isolated_profiles["staging"],
            transport=transport_cl,
        )
    assert exc_cl.value.code == "file_too_large"

    # Case B: Chunked transfer without Content-Length exceeds max_bytes during streaming
    class _LargeStream(httpx.SyncByteStream):
        def __iter__(self):
            yield wav_bytes[:1024]
            yield wav_bytes[1024:]

    transport_chunked = httpx.MockTransport(
        lambda r: httpx.Response(200, stream=_LargeStream(), request=r)
    )
    with pytest.raises(persona_install.PersonaInstallError) as exc_stream:
        persona_install.install_remote_persona(
            req,
            max_bytes=1024,
            staging_root=isolated_profiles["staging"],
            transport=transport_chunked,
        )
    assert exc_stream.value.code == "file_too_large"
    assert profiles.list_profiles() == []


def test_install_remote_persona_name_collision_preserves_personal_profile(
    tmp_path: Path, isolated_profiles: dict[str, Path]
) -> None:
    personal_wav_bytes = _make_wav_bytes(sr=24000, channels=1, seconds=1.2, freq=330.0)
    personal_src = tmp_path / "personal_alvaro.wav"
    personal_src.write_bytes(personal_wav_bytes)
    personal_digest = hashlib.sha256(personal_wav_bytes).hexdigest()

    personal = profiles.create_profile(
        name="Álvaro",
        language="Spanish",
        engine="qwen",
        ref_audio_path=str(personal_src),
        ref_text="Mi voz personal original.",
    )

    remote_wav_bytes = _make_wav_bytes(sr=48000, channels=2, seconds=1.5, freq=520.0)
    remote_digest = hashlib.sha256(remote_wav_bytes).hexdigest()

    req = persona_install.RemotePersonaInstallRequest(
        persona_id="alvaro-shared",
        name="Álvaro",
        language="Spanish",
        engine="qwen",
        ref_text="Voz compartida desde biblioteca remota.",
        library_url="https://persona.k3s.local",
        download_url="/v1/personas/alvaro-shared/audio",
        sha256=remote_digest,
        audio_format="wav",
        expected_size_bytes=len(remote_wav_bytes),
    )

    res = persona_install.install_remote_persona(
        req,
        staging_root=isolated_profiles["staging"],
        transport=httpx.MockTransport(
            lambda _r: httpx.Response(
                200,
                headers={"Content-Length": str(len(remote_wav_bytes))},
                content=remote_wav_bytes,
            )
        ),
    )

    assert res.name_disambiguated is True
    assert res.original_name == "Álvaro"
    assert res.profile.name == "Álvaro (Persona)"
    assert res.profile.id != personal.id

    all_profiles = profiles.list_profiles()
    assert len(all_profiles) == 2

    kept_personal = profiles.get_profile(personal.id)
    assert kept_personal is not None
    assert kept_personal.name == "Álvaro"
    assert kept_personal.ref_text == "Mi voz personal original."
    assert hashlib.sha256(Path(kept_personal.ref_original_path).read_bytes()).hexdigest() == personal_digest

    installed_remote = profiles.get_profile(res.profile.id)
    assert installed_remote is not None
    assert hashlib.sha256(Path(installed_remote.ref_original_path).read_bytes()).hexdigest() == remote_digest


def test_install_remote_persona_rejects_bad_id_magic_and_non_cloning_engine(
    isolated_profiles: dict[str, Path],
) -> None:
    html_payload = b"<html><body>404 not audio</body></html>"
    html_digest = hashlib.sha256(html_payload).hexdigest()

    bad_id = persona_install.RemotePersonaInstallRequest(
        persona_id="../escape",
        name="Bad ID",
        library_url="https://persona.k3s.local",
        download_url="/v1/personas/x/audio",
        sha256=html_digest,
        audio_format="wav",
    )
    with pytest.raises(persona_install.PersonaInstallError) as exc_id:
        persona_install.install_remote_persona(bad_id, staging_root=isolated_profiles["staging"])
    assert exc_id.value.code == "invalid_id"

    bad_engine = bad_id.model_copy(update={"persona_id": "ok-id", "engine": "piper"})
    with pytest.raises(persona_install.PersonaInstallError) as exc_eng:
        persona_install.install_remote_persona(bad_engine, staging_root=isolated_profiles["staging"])
    assert exc_eng.value.code == "invalid_engine"

    bad_magic = bad_id.model_copy(update={"persona_id": "fake-wav", "engine": "qwen"})
    with pytest.raises(persona_install.PersonaInstallError) as exc_magic:
        persona_install.install_remote_persona(
            bad_magic,
            staging_root=isolated_profiles["staging"],
            transport=httpx.MockTransport(
                lambda _r: httpx.Response(
                    200,
                    headers={"Content-Length": str(len(html_payload))},
                    content=html_payload,
                )
            ),
        )
    assert exc_magic.value.code == "unsupported_audio_format"

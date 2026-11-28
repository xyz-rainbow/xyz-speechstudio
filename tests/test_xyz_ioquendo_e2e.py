"""End-to-end vertical slice for xyz-Ioquendo without publishing the full pack."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.orchestrator import voice_packs as vp
from backend.orchestrator.config import AppSettings
from backend.orchestrator.downloader import build_catalog, remove_installed_model

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "packs" / "xyz-ioquendo"


@pytest.fixture()
def models_dir(tmp_path: Path) -> Path:
    return tmp_path / "models"


def test_catalog_entry_and_pack_lifecycle(models_dir: Path):
    settings = AppSettings(models_dir=str(models_dir))
    before = next(e for e in build_catalog(settings) if e.id == "xyz-ioquendo")
    assert before.installed is False
    assert before.capabilities.install_mode == "voices_pack"

    installed = vp.install_from_bundle(models_dir, bundle_dir=BUNDLE)
    assert len(installed["voices"]) == 2

    after = next(e for e in build_catalog(settings) if e.id == "xyz-ioquendo")
    assert after.installed is True
    assert after.installed_quant == "references"
    assert "es" in after.capabilities.languages
    assert "en" in after.capabilities.languages

    # Uninstall via catalog remove must not require Qwen weights present.
    result = remove_installed_model(settings, "xyz-ioquendo")
    assert result["removed"] is True
    assert vp.is_pack_installed(models_dir) is False


def test_api_install_list_resolve_and_restart(models_dir: Path, monkeypatch: pytest.MonkeyPatch):
    settings = AppSettings(models_dir=str(models_dir), active_tts_model="qwen3-1.7b-base-Q8_0")
    monkeypatch.setattr("backend.orchestrator.voice_pack_routes.load_settings", lambda: settings)
    monkeypatch.setattr(
        "backend.orchestrator.voice_pack_routes.resolved_models_dir",
        lambda _s: models_dir,
    )
    monkeypatch.setattr("backend.orchestrator.main.load_settings", lambda: settings)
    monkeypatch.setattr("backend.orchestrator.main.resolved_models_dir", lambda _s: models_dir)

    from backend.orchestrator import voice_pack_routes as routes
    from backend.orchestrator.main import _resolve_profile

    status = routes.voice_pack_status("xyz-ioquendo")
    assert status["installed"] is False

    installed = routes.voice_pack_install("xyz-ioquendo")
    assert installed["pack_id"] == "xyz-ioquendo"

    es_list = routes.voice_pack_voices("xyz-ioquendo", locale="es-ES")["voices"]
    assert len(es_list) == 1
    assert es_list[0]["name"] == "Álvaro"
    alvaro_id = es_list[0]["id"]

    en_list = routes.voice_pack_voices("xyz-ioquendo", locale="en-GB")["voices"]
    assert len(en_list) == 1
    assert en_list[0]["name"] == "Alfie"

    # Simulate app restart: re-list from disk, same ids, no profiles.json row.
    again = routes.voice_pack_voices("xyz-ioquendo", locale="es")["voices"]
    assert again[0]["id"] == alvaro_id

    prof = _resolve_profile(alvaro_id, settings)
    assert prof is not None
    assert Path(prof.ref_audio_path).is_file()
    assert "Hola" in prof.ref_text or "hola" in prof.ref_text.lower()
    assert prof.ready is True

    from backend.orchestrator import profiles

    assert profiles.get_profile(alvaro_id) is None

    prof2 = _resolve_profile(alvaro_id, settings)
    assert prof2 is not None
    assert prof2.ref_audio_path == prof.ref_audio_path

    repaired = routes.voice_pack_repair("xyz-ioquendo")
    assert repaired["pack_id"] == "xyz-ioquendo"

    deleted = routes.voice_pack_uninstall("xyz-ioquendo")
    assert deleted["removed"] is True


def test_synth_context_accepts_pack_voice_without_profile(models_dir: Path, monkeypatch: pytest.MonkeyPatch):
    settings = AppSettings(models_dir=str(models_dir), active_tts_model="qwen3-1.7b-base-Q8_0")
    vp.install_from_bundle(models_dir, bundle_dir=BUNDLE)
    monkeypatch.setattr("backend.orchestrator.main.load_settings", lambda: settings)
    monkeypatch.setattr("backend.orchestrator.main.resolved_models_dir", lambda _s: models_dir)
    monkeypatch.setattr(
        "backend.orchestrator.main._active_tts_catalog_entry",
        lambda _s: type("E", (), {"engine": "qwen", "id": "qwen3-1.7b-base", "capabilities": None})(),
    )
    monkeypatch.setattr("backend.orchestrator.main._supports_profileless_tts", lambda *_a, **_k: False)

    from backend.orchestrator.main import SynthesizeRequest, _resolve_tts_context

    voice_id = "pack:xyz-ioquendo/es-ES/alvaro"
    text, _settings, prof, lang = _resolve_tts_context(
        SynthesizeRequest(text="Frase nueva de prueba con Álvaro.", profile_id=voice_id, language="Spanish")
    )
    assert "Frase nueva" in text
    assert prof is not None
    assert prof.id == voice_id
    assert lang

    alfie = "pack:xyz-ioquendo/en-GB/alfie"
    _t, _s, prof_en, _lang = _resolve_tts_context(
        SynthesizeRequest(text="A brand new sentence with Alfie.", profile_id=alfie, language="English")
    )
    assert prof_en is not None
    assert prof_en.name == "Alfie"


def test_pack_weights_isolation_and_internal_ref_non_editable(models_dir: Path, monkeypatch: pytest.MonkeyPatch):
    from fastapi.testclient import TestClient
    from backend.orchestrator import downloader, main, profiles

    prof_dir = models_dir.parent / "profiles"
    monkeypatch.setattr(profiles, "DEFAULT_PROFILES_DIR", prof_dir)
    monkeypatch.setattr(profiles, "PROFILES_JSON", prof_dir / "profiles.json")
    monkeypatch.setattr(main, "load_settings", lambda: AppSettings(models_dir=str(models_dir), active_tts_model="qwen3-1.7b-base-Q4_K_M"))
    monkeypatch.setattr(main, "resolved_models_dir", lambda _s: models_dir)

    # Seed Qwen Q4 weights independently of xyz-ioquendo pack
    qdir = models_dir / "tts" / "qwen3-1.7b"
    qdir.mkdir(parents=True)
    for fn in ("qwen-talker-1.7b-base-Q4_K_M.gguf", "qwen-tokenizer-12hz-Q4_K_M.gguf"):
        (qdir / fn).write_bytes(b"GGUF")

    vp.install_from_bundle(models_dir, bundle_dir=BUNDLE)
    # Removing xyz-ioquendo pack keeps Qwen Q4 weights intact
    downloader.remove_installed_model(AppSettings(models_dir=str(models_dir)), "xyz-ioquendo")
    assert (qdir / "qwen-talker-1.7b-base-Q4_K_M.gguf").is_file()
    assert vp.is_pack_installed(models_dir) is False

    # Reinstall pack, remove Qwen weights -> pack stays installed
    vp.install_from_bundle(models_dir, bundle_dir=BUNDLE)
    downloader.remove_installed_model(AppSettings(models_dir=str(models_dir)), "qwen3-1.7b-base")
    assert vp.is_pack_installed(models_dir) is True

    # Internal pack reference is not in profiles.json and cannot be edited or deleted via /api/profiles
    client = TestClient(main.app, client=("127.0.0.1", 50000))
    voice_id = "pack:xyz-ioquendo/es-ES/alvaro"
    r_put = client.put(f"/api/profiles/{voice_id}", json={"name": "Hacked"})
    assert r_put.status_code == 404
    r_del = client.delete(f"/api/profiles/{voice_id}")
    assert r_del.status_code == 404


def test_openai_speech_resolves_pack_voice_and_payload_stages_vertical_slice(
    models_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from fastapi.testclient import TestClient
    from backend.orchestrator import main

    vp.install_from_bundle(models_dir, bundle_dir=BUNDLE)
    settings = AppSettings(
        models_dir=str(models_dir),
        active_tts_model="qwen3-1.7b-base-Q4_K_M",
        api_endpoint_enabled=True,
    )
    monkeypatch.setattr(main, "load_settings", lambda: settings)
    monkeypatch.setattr(main, "resolved_models_dir", lambda _s: models_dir)
    monkeypatch.setattr(main, "DEFAULT_TMP_DIR", tmp_path)

    captured: dict = {}

    def fake_run_tts(**kwargs):
        captured.update(kwargs)
        kwargs["out_path"].write_bytes(b"RIFF_PACK")
        return {"duration_s": 1.0, "sr": 24000, "elapsed_s": 0.1, "rtf": 0.1}, "Álvaro"

    monkeypatch.setattr(main, "_run_tts", fake_run_tts)
    client = TestClient(main.app, client=("127.0.0.1", 50000))
    resp = client.post(
        "/v1/audio/speech",
        json={"input": "Hola desde la API local.", "voice": "pack:xyz-ioquendo/es-ES/alvaro", "language": "Spanish"},
    )
    assert resp.status_code == 200
    assert resp.content == b"RIFF_PACK"
    assert captured["prof"] is not None
    assert captured["prof"].id == "pack:xyz-ioquendo/es-ES/alvaro"

    win_code = "\n".join(
        line for line in (ROOT / "installer" / "windows" / "build.ps1").read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )
    unix_code = "\n".join(
        line for line in (ROOT / "scripts" / "prepare_unix_payload.py").read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "manifest.vertical.v1.json" in win_code
    assert "manifest.full.v1.json" not in win_code
    assert "manifest.vertical.v1.json" in unix_code
    assert "manifest.full.v1.json" not in unix_code


def test_locale_label_filtering_and_xyz_ioquendo_active_model_execution(
    models_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from fastapi import HTTPException
    from fastapi.testclient import TestClient
    from backend.orchestrator import crispasr, main

    vp.install_from_bundle(models_dir, bundle_dir=BUNDLE)

    for q in ("Spanish", "Spanish (Spain)", "es-ES"):
        voices = vp.list_installed_voices(models_dir, locale=q)
        assert [v["name"] for v in voices] == ["Álvaro"]
    for q in ("English", "English (UK)", "en-GB"):
        voices = vp.list_installed_voices(models_dir, locale=q)
        assert [v["name"] for v in voices] == ["Alfie"]
    for q in ("All Languages", "All", ""):
        voices = vp.list_installed_voices(models_dir, locale=q)
        assert len(voices) == 2

    settings = AppSettings(models_dir=str(models_dir), active_tts_model="xyz-ioquendo", tts_device="cpu")
    monkeypatch.setattr(main, "load_settings", lambda: settings)
    monkeypatch.setattr(main, "resolved_models_dir", lambda _s: models_dir)
    prof = main._resolve_profile("pack:xyz-ioquendo/es-ES/alvaro", settings)
    assert prof is not None

    out_wav = tmp_path / "out.wav"
    with pytest.raises(HTTPException) as exc:
        main._run_tts(prof=prof, text="Hola", lang="Spanish", out_path=out_wav, seed=42, force_stop_captions=False)
    assert exc.value.status_code == 400
    assert "Qwen3-TTS 1.7B Base" in exc.value.detail

    qdir = models_dir / "tts" / "qwen3-1.7b"
    qdir.mkdir(parents=True)
    for fn in (
        "qwen-talker-1.7b-base-Q4_K_M.gguf",
        "qwen-tokenizer-12hz-Q4_K_M.gguf",
        "qwen-talker-1.7b-base-Q8_0.gguf",
        "qwen-tokenizer-12hz-Q8_0.gguf",
    ):
        (qdir / fn).write_bytes(b"GGUF")

    monkeypatch.setattr(crispasr, "supports_engine", lambda *a, **k: True)
    seen: dict = {}

    def fake_run_crispasr_tts(**kwargs):
        import wave

        seen.update(kwargs)
        kwargs["out_path"].parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(kwargs["out_path"]), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(b"\x00\x00" * 2400)
        return {"duration_s": 1.0, "sr": 24000, "elapsed_s": 0.1, "rtf": 0.1}, kwargs["speaker_name"]

    monkeypatch.setattr(main, "_run_crispasr_tts", fake_run_crispasr_tts)
    res, speaker = main._run_tts(
        prof=prof,
        text="Hola mundo",
        lang="Spanish",
        out_path=out_wav,
        seed=42,
        force_stop_captions=False,
    )
    assert res["sr"] == 24000
    assert speaker == "Álvaro"
    assert seen["entry"].id == "qwen3-1.7b-base"
    assert seen["preferred_quant"] == "Q4_K_M"

    out_dir = tmp_path / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(main, "resolved_outputs_dir", lambda _s: out_dir)
    monkeypatch.setattr(main, "fire_toast", lambda *_a, **_k: None)
    monkeypatch.setattr(main, "PLAY_SESSION_DIR", tmp_path / "play_session")
    client = TestClient(main.app, client=("127.0.0.1", 50000))
    resp_save = client.post(
        "/api/tts/synthesize",
        json={
            "text": "Guardando audio de pack sin error de ruta.",
            "profile_id": "pack:xyz-ioquendo/es-ES/alvaro",
            "language": "Spanish",
            "mode": "wav",
        },
    )
    assert resp_save.status_code == 200
    saved_name = Path(resp_save.json()["record"]["saved_path"]).name
    assert ":" not in saved_name and "/" not in saved_name and "\\" not in saved_name
    assert (out_dir / saved_name).is_file()

    sess = client.post(
        "/api/tts/session/start",
        json={
            "text": "Guardando sesión por tramos con pack.",
            "profile_id": "pack:xyz-ioquendo/es-ES/alvaro",
            "language": "Spanish",
            "mode": "play",
        },
    )
    assert sess.status_code == 200
    sid = sess.json()["session_id"]
    sess_save = client.post(f"/api/tts/session/{sid}/save")
    assert sess_save.status_code == 200
    sess_name = Path(sess_save.json()["saved_path"]).name
    assert ":" not in sess_name and "/" not in sess_name and "\\" not in sess_name
    assert (out_dir / sess_name).is_file()


def test_install_from_source_multilocale_and_repair(
    models_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from fastapi.testclient import TestClient
    from backend.orchestrator import main, voice_pack_routes

    src_root = tmp_path / "external_source"
    pairs = [
        ("es-ES", "Alvaro_Hombre_Neuronal", "Hola desde España."),
        ("es-MX", "Dalia_Mujer_Neuronal", "Hola desde México."),
        ("bg-BG", "Borislav_Hombre_Neuronal", "Здравейте."),
        ("cmn-CN", "Xiaoxiao_Mujer_Neuronal", "你好世界。"),
    ]
    for loc, stem, txt in pairs:
        ldir = src_root / loc
        ldir.mkdir(parents=True)
        (ldir / f"{stem}.mp3").write_bytes(b"ID3" + b"\x00" * 2048)
        (ldir / f"{stem}.txt").write_text(txt, encoding="utf-8")

    # Benchmark folder must be skipped without touching originals.
    bdir = src_root / "benchmark"
    bdir.mkdir(parents=True)
    (bdir / "skip_Man.mp3").write_bytes(b"ID3" + b"\x00" * 2048)
    (bdir / "skip_Man.txt").write_text("No debe entrar.", encoding="utf-8")

    settings = AppSettings(models_dir=str(models_dir))
    monkeypatch.setattr(voice_pack_routes, "load_settings", lambda: settings)
    monkeypatch.setattr(voice_pack_routes, "resolved_models_dir", lambda _s: models_dir)

    client = TestClient(main.app, client=("127.0.0.1", 50000))
    resp = client.post(
        "/api/voice-packs/xyz-ioquendo/install",
        json={"source_dir": str(src_root)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == "1.0.0-local"
    assert len(body["voices"]) == 4

    codes = vp.installed_locale_codes(models_dir)
    assert codes == ["bg", "cmn", "es"]
    assert vp._language_label("bg-BG") == "Bulgarian"
    assert vp._language_label("cmn-CN") == "Chinese (Mandarin)"

    es_voices = client.get("/api/voice-packs/xyz-ioquendo/voices", params={"locale": "es"}).json()["voices"]
    assert len(es_voices) == 2

    # Delete one installed audio copy and verify repair restores from source_root cleanly.
    alvaro_audio = models_dir / "voice-packs" / "xyz-ioquendo" / "voices" / "es-ES" / "alvaro" / "audio.mp3"
    alvaro_audio.unlink()
    rep = client.post("/api/voice-packs/xyz-ioquendo/repair")
    assert rep.status_code == 200
    assert alvaro_audio.is_file()
    assert (src_root / "benchmark" / "skip_Man.mp3").is_file()




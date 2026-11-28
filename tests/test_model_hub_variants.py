"""Phase 1 tests: simultaneous multi-variant installs, safe deletes, Piper GGUF, STT compute_type, and honest runtime gates."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.orchestrator import crispasr, downloader, main  # noqa: E402
from backend.orchestrator.config import AppSettings  # noqa: E402


def _seed_variant_files(models_dir: Path, entry_id: str, quant_ids: list[str]) -> tuple[downloader.CatalogModelEntry, Path]:
    entry = next(e for e in downloader.build_catalog(AppSettings(models_dir=str(models_dir))) if e.id == entry_id)
    spec = downloader.BUILTIN_BY_ID[entry_id]
    rel_dir = (spec.get("dir_names") or [entry_id])[0]
    model_dir = models_dir / "tts" / rel_dir
    model_dir.mkdir(parents=True, exist_ok=True)
    for q in entry.quants:
        if q.id in quant_ids:
            for rel_file in q.files:
                fp = model_dir / rel_file
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_bytes(b"GGUF\x03\x00\x00\x00" + q.id.encode("utf-8"))
    refreshed = next(e for e in downloader.build_catalog(AppSettings(models_dir=str(models_dir))) if e.id == entry_id)
    return refreshed, model_dir


@pytest.mark.parametrize(
    ("model_id", "q_a", "q_b"),
    [
        ("qwen3-1.7b-base", "Q4_K_M", "Q8_0"),
        ("chatterbox-multilingual-gguf", "q4_k", "q8_0"),
        ("chatterbox-turbo-gguf", "q4_k", "f16"),
        ("indextts-1.5-gguf", "q8_0", "q4_k"),
        ("cosyvoice3-0.5b-gguf", "q4_k", "f16"),
        ("orpheus-3b-gguf", "q4_k", "q8_0"),
        ("kokoro-82m", "f16", "q8_0"),
    ],
)
def test_multi_variant_install_switch_restart_synth_and_safe_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    model_id: str,
    q_a: str,
    q_b: str,
) -> None:
    models_dir = tmp_path / "models"
    entry, model_dir = _seed_variant_files(models_dir, model_id, [q_a, q_b])
    assert entry.installed is True
    assert set(entry.installed_quants) == {q_a, q_b}

    # Simulated restart: fresh AppSettings read picks up both variants cleanly
    for qid in (q_a, q_b):
        restarted_settings = AppSettings(
            models_dir=str(models_dir),
            active_tts_model=f"{model_id}-{qid}",
        )
        reloaded = next(e for e in downloader.build_catalog(restarted_settings) if e.id == model_id)
        q_spec = next(q for q in reloaded.quants if q.id == qid)
        if reloaded.engine != "qwen":
            captured: dict = {}
            monkeypatch.setattr(main, "load_settings", lambda s=restarted_settings: s)
            monkeypatch.setattr(
                crispasr,
                "synthesize_tts",
                lambda **kw: captured.update(kw) or {"duration_s": 0.5},
            )
            main._run_crispasr_tts(
                entry=reloaded,
                engine=reloaded.engine,
                speaker_name="test",
                text="Hola mundo",
                lang="es",
                out_path=tmp_path / f"{model_id}_{qid}.wav",
                device="cpu",
            )
            assert captured["model_path"] == model_dir / q_spec.files[0]
            if len(q_spec.files) > 1 and reloaded.engine in ("chatterbox", "chatterbox-turbo", "indextts", "cosyvoice3-tts"):
                assert captured["codec_path"] == model_dir / q_spec.files[1]
        else:
            talker, codec, resolved_id = downloader.resolve_qwen_paths(restarted_settings)
            assert resolved_id == f"{model_id}-{qid}"
            assert talker == model_dir / q_spec.files[0]
            assert codec == model_dir / q_spec.files[1]

    # Delete first variant and verify second variant (plus shared companion files) keeps working
    res = downloader.remove_installed_model(AppSettings(models_dir=str(models_dir)), model_id, quant_id=q_a)
    assert res["removed"] is True
    assert q_b in res["remaining"]

    after_del_settings = AppSettings(
        models_dir=str(models_dir),
        active_tts_model=f"{model_id}-{q_b}",
    )
    after_entry = next(e for e in downloader.build_catalog(after_del_settings) if e.id == model_id)
    assert after_entry.installed is True
    assert after_entry.installed_quants == [q_b]
    b_spec = next(q for q in after_entry.quants if q.id == q_b)
    for rel_file in b_spec.files:
        assert (model_dir / rel_file).is_file()


def test_piper_unified_gguf_ignores_stale_onnx_and_prefers_local_dir(tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    piper_dir = models_dir / "tts" / "piper" / "en" / "en_US" / "lessac" / "high"
    piper_dir.mkdir(parents=True)
    (piper_dir / "en_US-lessac-high.onnx").write_bytes(b"ONNX")
    (piper_dir / "en_US-lessac-high.onnx.json").write_text("{}", encoding="utf-8")

    settings = AppSettings(models_dir=str(models_dir))
    cat = downloader.build_catalog(settings)
    piper_entry = next(e for e in cat if e.id == "piper-voices")
    assert piper_entry.installed is False
    assert piper_entry.installed_quants == []
    assert piper_entry.capabilities.quant_policy == "gguf"

    # Install GGUF medium + low
    entry, model_dir = _seed_variant_files(models_dir, "piper-voices", ["medium", "low"])
    assert set(entry.installed_quants) == {"medium", "low"}
    arg_es = crispasr._resolve_piper_model_arg("es_ES-davefx-medium-f16", "Spanish", model_dir)
    assert arg_es == model_dir / "piper-es_ES-davefx-medium-f16.gguf"
    arg_low = crispasr._resolve_piper_model_arg("es_ES-mls_10246-low-f16", "Spanish", model_dir)
    assert arg_low == model_dir / "piper-es_ES-mls_10246-low-f16.gguf"

    # Removing low keeps medium intact
    res = downloader.remove_installed_model(settings, "piper-voices", quant_id="low")
    assert res["remaining"] == ["medium"]
    assert (model_dir / "piper-es_ES-davefx-medium-f16.gguf").is_file()


def test_kokoro_stale_onnx_ignored_when_gguf_required(tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    onnx_dir = models_dir / "tts" / "kokoro-82m" / "onnx"
    onnx_dir.mkdir(parents=True)
    (onnx_dir / "model_fp16.onnx").write_bytes(b"ONNX")

    entry = next(e for e in downloader.build_catalog(AppSettings(models_dir=str(models_dir))) if e.id == "kokoro-82m")
    assert entry.installed is False
    assert entry.capabilities.quant_policy == "gguf"


def test_post_quantize_and_unsupported_runtimes_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(crispasr, "is_available", lambda *a, **kw: True)
    settings = AppSettings(models_dir=str(tmp_path / "models"))
    cat = {e.id: e for e in downloader.build_catalog(settings)}

    # Parakeet/Moonshine ONNX and non-GGUF F5 variants must NOT be falsely promoted
    assert cat["parakeet-tdt-0.6b-v3"].runtime_supported is False
    assert cat["moonshine-base"].runtime_supported is False
    assert cat["f5-tts-v1-base"].runtime_supported is False
    assert cat["f5-tts-french"].runtime_supported is False
    assert cat["f5-tts-spanish"].runtime_supported is True
    assert cat["f5-tts-gguf-f16"].runtime_supported is True

    mgr = downloader.DownloadManager()
    with pytest.raises(ValueError, match="Post-quantize"):
        mgr.start_catalog_download(settings, "fish-speech-1.5", quant_id="int8")
    with pytest.raises(ValueError, match="Post-quantize"):
        mgr.start_catalog_download(settings, "fish-speech-1.5", quant_id="int4")
    with pytest.raises(ValueError, match="compatible local runtime"):
        mgr.start_catalog_download(settings, "parakeet-tdt-0.6b-v3", quant_id="int8")

    # _run_stt must refuse unsupported onnx-asr entries with 501 rather than misrouting
    wav = tmp_path / "sample.wav"
    wav.write_bytes(b"RIFF")
    monkeypatch.setattr(main, "load_settings", lambda: settings.model_copy(update={"active_stt_model": "parakeet-tdt-0.6b-v3"}))
    with pytest.raises(HTTPException) as exc:
        main._run_stt(wav, language="en")
    assert exc.value.status_code == 501


def test_stt_compute_type_resolves_through_run_stt_and_worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    models_dir = tmp_path / "models"
    fw_dir = models_dir / "stt" / "faster-whisper-base"
    fw_dir.mkdir(parents=True)
    (fw_dir / "model.bin").write_bytes(b"ct2")
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"RIFF")

    for ctype in ("int8", "int8_float16", "float16"):
        settings = AppSettings(
            models_dir=str(models_dir),
            active_stt_model=f"faster-whisper-base-{ctype}",
            stt_device="cpu",
        )
        path, resolved_ct, _ = downloader.resolve_stt_load_target(settings, settings.active_stt_model)
        assert Path(path) == fw_dir
        assert resolved_ct == ctype

        monkeypatch.setattr(main, "load_settings", lambda s=settings: s)
        seen_loads: list[str] = []

        class FakeHandle:
            port = 1
            model_id = settings.active_stt_model

        class FakeResp:
            status_code = 200
            text = "{}"

            @staticmethod
            def json():
                return {"text": f"ok-{ctype}", "language": "es", "segments": []}

        class FakeClient:
            def __init__(self, **_kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            @staticmethod
            def post(_url, json=None):
                return FakeResp()

        monkeypatch.setattr(main, "ensure_stt_loaded", lambda model_id=None: seen_loads.append(model_id or "") or FakeHandle())
        monkeypatch.setattr(main.httpx, "Client", FakeClient)

        res = main._run_stt(wav, language="Spanish", model_id=f"faster-whisper-base-{ctype}")
        assert res["text"] == f"ok-{ctype}"
        assert seen_loads == [f"faster-whisper-base-{ctype}"]


def test_kitten_int8_vs_int4_selection_passed_to_worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    models_dir = tmp_path / "models"
    kdir = models_dir / "tts" / "kitten-tts-2-mini"
    kdir.mkdir(parents=True)
    (kdir / "kitten_tts_2_mini.onnx").write_bytes(b"ONNX8")
    (kdir / "kitten_tts_2_mini_int4.onnx").write_bytes(b"ONNX4")

    settings = AppSettings(models_dir=str(models_dir), active_tts_model="kitten-tts-2-mini-int4", tts_device="cpu")
    monkeypatch.setattr(main, "load_settings", lambda: settings)
    monkeypatch.setattr(main.supervisor, "active_workers", {})

    captured: dict = {}

    class FakeHandle:
        port = 50505
        process = type("P", (), {"poll": staticmethod(lambda: None)})()
        device = "cpu"
        model_id = "kitten-tts-2-mini-int4"

    class FakeResp:
        status_code = 200
        text = "{}"

    class FakeClient:
        def __init__(self, **_kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        @staticmethod
        def post(_url, json=None):
            captured["load_json"] = json
            return FakeResp()

    monkeypatch.setattr(main.supervisor, "spawn_worker", lambda **_kw: FakeHandle())
    monkeypatch.setattr(main.httpx, "Client", FakeClient)

    handle = main.ensure_kitten_loaded(model_id="kitten-tts-2-mini-int4")
    assert handle.model_id == "kitten-tts-2-mini-int4"
    assert Path(captured["load_json"]["model_dir"]) == kdir
    assert captured["load_json"]["model_file"] == "kitten_tts_2_mini_int4.onnx"

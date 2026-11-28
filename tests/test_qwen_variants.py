from backend.orchestrator.config import AppSettings
from backend.orchestrator.downloader import build_catalog, remove_installed_model, resolve_qwen_paths, resolve_stt_load_target


def test_qwen_selects_complete_requested_pair_with_both_quants_installed(tmp_path):
    model = tmp_path / "tts" / "qwen3-1.7b"
    model.mkdir(parents=True)
    for quant in ("Q4_K_M", "Q8_0", "BF16"):
        (model / f"qwen-talker-1.7b-base-{quant}.gguf").touch()
        (model / f"qwen-tokenizer-12hz-{quant}.gguf").touch()
    (model / ".speech_studio_model.json").write_text('{"quant":"Q8_0"}', encoding="utf-8")

    for quant in ("Q4_K_M", "Q8_0", "BF16"):
        selected = f"qwen3-1.7b-base-{quant}"
        settings = AppSettings(models_dir=str(tmp_path), active_tts_model=selected)
        talker, codec, resolved = resolve_qwen_paths(settings)
        assert resolved == selected
        assert talker.name == f"qwen-talker-1.7b-base-{quant}.gguf"
        assert codec.name == f"qwen-tokenizer-12hz-{quant}.gguf"

    remove_installed_model(settings, "qwen3-1.7b-base", quant_id="Q4_K_M")
    assert not (model / "qwen-talker-1.7b-base-Q4_K_M.gguf").exists()
    assert not (model / "qwen-tokenizer-12hz-Q4_K_M.gguf").exists()
    assert (model / "qwen-talker-1.7b-base-Q8_0.gguf").exists()
    assert (model / "qwen-tokenizer-12hz-Q8_0.gguf").exists()


def test_removing_one_indextts_quant_keeps_shared_vocoder(tmp_path):
    model = tmp_path / "tts" / "indextts-1.5-gguf"
    model.mkdir(parents=True)
    for filename in (
        "indextts-gpt-q8_0.gguf",
        "indextts-gpt-q4_k.gguf",
        "indextts-bigvgan.gguf",
    ):
        (model / filename).touch()

    settings = AppSettings(models_dir=str(tmp_path))
    result = remove_installed_model(settings, "indextts-1.5-gguf", quant_id="q4_k")
    assert result["remaining"] == ["q8_0"]
    assert not (model / "indextts-gpt-q4_k.gguf").exists()
    assert (model / "indextts-gpt-q8_0.gguf").exists()
    assert (model / "indextts-bigvgan.gguf").exists()

    remove_installed_model(settings, "indextts-1.5-gguf", quant_id="q8_0")
    assert not (model / "indextts-bigvgan.gguf").exists()
    entry = next(e for e in build_catalog(settings) if e.id == "indextts-1.5-gguf")
    assert not entry.installed
    assert entry.installed_quants == []


def test_crispasr_uses_active_indextts_quant_and_shared_codec(tmp_path, monkeypatch):
    from backend.orchestrator import main, crispasr

    model = tmp_path / "tts" / "indextts-1.5-gguf"
    model.mkdir(parents=True)
    for filename in ("indextts-gpt-q8_0.gguf", "indextts-gpt-q4_k.gguf", "indextts-bigvgan.gguf"):
        (model / filename).touch()
    settings = AppSettings(models_dir=str(tmp_path), active_tts_model="indextts-1.5-gguf-q4_k")
    entry = next(e for e in build_catalog(settings) if e.id == "indextts-1.5-gguf")
    captured = {}

    monkeypatch.setattr(main, "load_settings", lambda: settings)
    monkeypatch.setattr(crispasr, "synthesize_tts", lambda **kwargs: captured.update(kwargs) or {"duration_s": 1})
    main._run_crispasr_tts(
        entry=entry,
        engine="indextts",
        speaker_name="test",
        text="Hola",
        lang="es",
        out_path=tmp_path / "out.wav",
        device="cpu",
    )
    assert captured["model_path"] == model / "indextts-gpt-q4_k.gguf"
    assert captured["codec_path"] == model / "indextts-bigvgan.gguf"


def test_whisper_compute_options_share_one_checkpoint(tmp_path):
    model = tmp_path / "stt" / "faster-whisper-base"
    model.mkdir(parents=True)
    (model / "model.bin").touch()
    settings = AppSettings(models_dir=str(tmp_path))
    entry = next(e for e in build_catalog(settings) if e.id == "faster-whisper-base")
    assert set(entry.installed_quants) == {"int8", "int8_float16", "float16"}
    path, compute_type, _ = resolve_stt_load_target(settings, "faster-whisper-base-float16")
    assert path == str(model)
    assert compute_type == "float16"


def test_cosyvoice_uses_matching_llm_and_flow_quant(tmp_path, monkeypatch):
    from backend.orchestrator import main, crispasr

    model = tmp_path / "tts" / "cosyvoice3-0.5b-gguf"
    model.mkdir(parents=True)
    settings = AppSettings(models_dir=str(tmp_path), active_tts_model="cosyvoice3-0.5b-gguf-f16")
    spec = next(e for e in build_catalog(settings) if e.id == "cosyvoice3-0.5b-gguf")
    for quant in spec.quants:
        for filename in quant.files:
            (model / filename).touch()
    entry = next(e for e in build_catalog(settings) if e.id == spec.id)
    captured = {}
    monkeypatch.setattr(main, "load_settings", lambda: settings)
    monkeypatch.setattr(crispasr, "synthesize_tts", lambda **kwargs: captured.update(kwargs) or {"duration_s": 1})
    main._run_crispasr_tts(
        entry=entry,
        engine="cosyvoice3-tts",
        speaker_name="test",
        text="Hola",
        lang="es",
        out_path=tmp_path / "out.wav",
        device="cpu",
    )
    assert captured["model_path"] == model / "cosyvoice3-llm-f16.gguf"
    assert captured["codec_path"] == model / "cosyvoice3-flow-f16.gguf"

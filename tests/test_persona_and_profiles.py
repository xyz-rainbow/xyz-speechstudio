from __future__ import annotations

import hashlib
import math
import struct
import sys
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.orchestrator import audio_adaptation, profiles


def _write_stereo_wav(path: Path, *, sr: int = 48000, seconds: float = 15.0) -> bytes:
    frames = int(sr * seconds)
    buf = bytearray()
    for i in range(frames):
        s_l = int(8000 * math.sin(2.0 * math.pi * 220.0 * i / sr))
        s_r = int(4000 * math.sin(2.0 * math.pi * 440.0 * i / sr))
        buf.extend(struct.pack("<hh", s_l, s_r))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(bytes(buf))
    return hashlib.sha256(path.read_bytes()).digest()


def test_engine_adaptation_rules_reject_non_cloning_engines() -> None:
    qwen = audio_adaptation.describe_engine_adaptation(
        "qwen",
        {"format": "mp3", "sample_rate": 44100, "channels": 2, "duration_s": 14.0},
    )
    assert qwen["supports_cloning"] is True
    assert qwen["status"] == "needs_conversion"
    assert any("MP3" in c for c in qwen["conversions_needed"])
    assert any("Downmix 2ch" in c for c in qwen["conversions_needed"])
    assert any("Resample 44100 Hz -> 24000 Hz" in c for c in qwen["conversions_needed"])

    f5 = audio_adaptation.describe_engine_adaptation(
        "f5-tts",
        {"format": "wav", "sample_rate": 24000, "channels": 1, "duration_s": 15.0},
        has_ref_text=False,
    )
    assert f5["supports_cloning"] is True
    assert f5["status"] == "needs_conversion"
    assert any("Trim 15.0s -> <= 12s" in c for c in f5["conversions_needed"])
    assert f5["warnings"]

    for non_clone in ("piper", "kokoro", "orpheus", "kitten", "espeak", "sapi5"):
        res = audio_adaptation.describe_engine_adaptation(
            non_clone,
            {"format": "wav", "sample_rate": 24000, "channels": 1, "duration_s": 8.0},
        )
        assert res["supports_cloning"] is False
        assert res["status"] == "unsupported_no_cloning"
        assert res["conversions_needed"] == []


def test_adapt_audio_for_multiple_engines_preserves_original(tmp_path: Path) -> None:
    src = tmp_path / "source_stereo_48k.wav"
    orig_hash = _write_stereo_wav(src, sr=48000, seconds=14.0)
    out_dir = tmp_path / "adapted"

    qwen_wav, qwen_info = audio_adaptation.adapt_audio_for_engine(src, "qwen", out_dir)
    assert qwen_wav.is_file()
    assert qwen_info["sample_rate"] == 24000
    assert qwen_info["channels"] == 1
    assert qwen_info["duration_s"] == pytest.approx(14.0, abs=0.1)

    f5_wav, f5_info = audio_adaptation.adapt_audio_for_engine(src, "f5-tts", out_dir)
    assert f5_wav.is_file()
    assert f5_info["sample_rate"] == 24000
    assert f5_info["duration_s"] <= 11.05

    xtts_wav, xtts_info = audio_adaptation.adapt_audio_for_engine(src, "xtts", out_dir)
    assert xtts_wav.is_file()
    assert xtts_info["sample_rate"] == 22050

    fish_wav, fish_info = audio_adaptation.adapt_audio_for_engine(src, "fish-audio", out_dir)
    assert fish_wav.is_file()
    assert fish_info["sample_rate"] == 44100

    with pytest.raises(ValueError, match="does not support voice cloning"):
        audio_adaptation.adapt_audio_for_engine(src, "piper", out_dir)

    assert hashlib.sha256(src.read_bytes()).digest() == orig_hash


def test_switching_profile_engine_and_restoring_keeps_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prof_dir = tmp_path / "profiles"
    monkeypatch.setattr(profiles, "DEFAULT_PROFILES_DIR", prof_dir)
    monkeypatch.setattr(profiles, "PROFILES_JSON", prof_dir / "profiles.json")
    monkeypatch.setattr(profiles, "ensure_data_dirs", lambda: prof_dir.mkdir(parents=True, exist_ok=True))

    src = tmp_path / "user_clip.wav"
    _write_stereo_wav(src, sr=48000, seconds=14.0)

    created = profiles.create_profile(
        name="Persona Test",
        language="Spanish",
        engine="qwen",
        ref_audio_path=str(src),
        ref_text="Texto de prueba completo.",
    )
    orig_path = Path(created.ref_original_path)
    assert orig_path.is_file()
    orig_hash = hashlib.sha256(orig_path.read_bytes()).digest()

    trimmed = profiles.trim_profile_audio(created.id, max_seconds=12.0)
    assert trimmed is not None
    assert trimmed.ref_trimmed is True
    assert trimmed.ref_duration_s <= 12.05
    assert Path(trimmed.ref_original_path) == orig_path

    # Switching engine via switch_profile_engine must preserve original audio untouched
    switched = profiles.switch_profile_engine(created.id, "f5")
    assert switched is not None
    assert switched.engine == "f5"
    assert Path(switched.ref_original_path) == orig_path
    assert (prof_dir / created.id / "adapted" / "adapted_f5.wav").is_file()
    assert hashlib.sha256(orig_path.read_bytes()).digest() == orig_hash

    # Switching to XTTS prepares 22.05 kHz copy without touching ref_original_path
    switched_xtts = profiles.update_profile(created.id, engine="xtts")
    assert switched_xtts is not None
    assert switched_xtts.engine == "xtts"
    assert Path(switched_xtts.ref_original_path) == orig_path
    assert (prof_dir / created.id / "adapted" / "adapted_xtts.wav").is_file()

    # Passing derived path to update_profile must never overwrite ref_original_path
    derived_pass = profiles.update_profile(created.id, ref_audio_path=switched_xtts.ref_audio_path)
    assert derived_pass is not None
    assert Path(derived_pass.ref_original_path) == orig_path

    # Restoring original brings back full 14s duration and clears ref_trimmed
    restored = profiles.restore_original_audio(created.id)
    assert restored is not None
    assert restored.ref_trimmed is False
    assert Path(restored.ref_audio_path) == orig_path
    assert restored.ref_duration_s == pytest.approx(14.0, abs=0.1)


def test_trim_aligns_transcript_on_word_boundaries_and_restores_original_text(tmp_path: Path, monkeypatch) -> None:
    prof_dir = tmp_path / "profiles"
    src_wav = tmp_path / "long_24s.wav"
    _write_stereo_wav(src_wav, sr=44100, seconds=24.0)

    monkeypatch.setattr(profiles, "DEFAULT_PROFILES_DIR", prof_dir)
    monkeypatch.setattr(profiles, "PROFILES_JSON", prof_dir / "profiles.json")
    monkeypatch.setattr(profiles, "ensure_data_dirs", lambda: prof_dir.mkdir(parents=True, exist_ok=True))

    original_text = "Uno dos tres cuatro cinco seis siete ocho nueve diez once doce"
    created = profiles.create_profile(
        name="Trim Alignment Test",
        language="Spanish",
        engine="qwen",
        ref_audio_path=str(src_wav),
        ref_text=original_text,
    )
    assert created.ref_original_text == original_text

    trimmed = profiles.trim_profile_audio(created.id, max_seconds=12.0)
    assert trimmed is not None
    assert trimmed.ref_trimmed is True
    assert trimmed.ref_duration_s == pytest.approx(12.0, abs=0.1)
    # 12s of 24s = 50% of words -> "Uno dos tres cuatro cinco seis"
    assert trimmed.ref_text == "Uno dos tres cuatro cinco seis"
    assert trimmed.ref_original_text == original_text
    assert Path(trimmed.ref_original_path).is_file()

    restored = profiles.restore_original_audio(created.id)
    assert restored is not None
    assert restored.ref_trimmed is False
    assert restored.ref_text == original_text
    assert restored.ref_original_text == original_text


def test_persona_documentation_exists_and_covers_k3s_contract() -> None:
    doc = (ROOT / "docs" / "app" / "persona.md").read_text(encoding="utf-8")
    assert "/v1/personas" in doc
    assert "k3s" in doc.lower()
    assert "ref_original_path" in doc

"""Pure helpers for live-captions endpoint windowing (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.orchestrator.captions import (  # noqa: E402
    MIN_SPEECH_SECONDS,
    PARTIAL_SECONDS,
    PAUSE_SECONDS,
    SAMPLE_RATE,
    _language,
    _rms,
    _wav_bytes,
)


def test_language_auto_is_none():
    assert _language("auto") is None
    assert _language("") is None
    assert _language("es") == "es"


def test_rms_silence_near_zero():
    silence = b"\x00\x00" * 800
    assert _rms(silence) < 0.001


def test_rms_loud_pcm_above_voice_threshold():
    # ~0.5 amplitude 16-bit mono
    sample = int(0.5 * 32767).to_bytes(2, "little", signed=True)
    pcm = sample * 400
    assert _rms(pcm) >= 0.015


def test_wav_header_and_duration():
    frames = SAMPLE_RATE  # 1 second
    pcm = b"\x00\x00" * frames
    wav = _wav_bytes(pcm)
    assert wav[:4] == b"RIFF"
    assert wav[8:12] == b"WAVE"
    assert len(wav) > 44
    # PCM payload size
    assert len(wav) - 44 == frames * 2


def test_timing_constants_sane_for_ui():
    assert PARTIAL_SECONDS >= 0.5
    assert PAUSE_SECONDS < PARTIAL_SECONDS
    assert MIN_SPEECH_SECONDS > 0
    assert SAMPLE_RATE == 16000

"""Reference audio inspection, 24 kHz mono normalization, and non-destructive trimming."""

from __future__ import annotations

import array
import math
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Optional


def _read_pcm_wave(path: Path) -> tuple[array.array, int, int]:
    """Read PCM audio from WAV (or transcode via ffmpeg to temp WAV if needed)."""
    try:
        with wave.open(str(path), "rb") as wf:
            ch = wf.getnchannels()
            sw = wf.getsampwidth()
            sr = wf.getframerate()
            raw = wf.readframes(wf.getnframes())
    except wave.Error:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError(f"Unsupported non-WAV audio format without ffmpeg: {path.name}")
        tmp_wav = path.with_name(f".{path.stem}_conv.wav")
        subprocess.run(
            [ffmpeg, "-y", "-i", str(path), "-ac", "1", "-ar", "24000", "-sample_fmt", "s16", str(tmp_wav)],
            check=True,
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            with wave.open(str(tmp_wav), "rb") as wf:
                ch = wf.getnchannels()
                sw = wf.getsampwidth()
                sr = wf.getframerate()
                raw = wf.readframes(wf.getnframes())
        finally:
            tmp_wav.unlink(missing_ok=True)

    if sw == 2:
        samples = array.array("h")
        samples.frombytes(raw)
    elif sw == 1:
        samples = array.array("h", ((b - 128) * 256 for b in raw))
    elif sw == 4:
        ints = array.array("i")
        ints.frombytes(raw)
        samples = array.array("h", (v >> 16 for v in ints))
    else:
        raise RuntimeError(f"Unsupported WAV sample width: {sw * 8}-bit")

    if ch > 1:
        mono = array.array("h")
        for i in range(0, len(samples), ch):
            total = 0
            for c in range(ch):
                total += samples[i + c]
            mono.append(int(total / ch))
        samples = mono

    return samples, sr, 1


def _resample_linear(samples: array.array, src_sr: int, dst_sr: int = 24000) -> array.array:
    if src_sr == dst_sr or len(samples) == 0:
        return samples
    # Exact integer decimation (e.g., 48000 -> 24000) avoids interpolation blur.
    if src_sr > dst_sr and src_sr % dst_sr == 0:
        step = src_sr // dst_sr
        return array.array("h", samples[::step])
    n_out = max(1, int(round(len(samples) * dst_sr / float(src_sr))))
    out = array.array("h", [0]) * n_out
    ratio = (len(samples) - 1) / float(max(1, n_out - 1))
    for i in range(n_out):
        pos = i * ratio
        idx = int(pos)
        frac = pos - idx
        s0 = samples[idx]
        s1 = samples[idx + 1] if idx + 1 < len(samples) else s0
        val = int(round(s0 + (s1 - s0) * frac))
        out[i] = max(-32768, min(32767, val))
    return out


def _write_pcm16_mono(path: Path, samples: array.array, sr: int = 24000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(samples.tobytes())


def probe_audio_info(path: Path) -> dict:
    if not path.is_file():
        return {"duration_s": 0.0, "sample_rate": 0, "channels": 0}
    try:
        with wave.open(str(path), "rb") as wf:
            sr = wf.getframerate()
            frames = wf.getnframes()
            dur = round(frames / float(sr), 2) if sr > 0 else 0.0
            return {"duration_s": dur, "sample_rate": sr, "channels": wf.getnchannels()}
    except Exception:
        samples, sr, ch = _read_pcm_wave(path)
        dur = round(len(samples) / float(sr), 2) if sr > 0 else 0.0
        return {"duration_s": dur, "sample_rate": sr, "channels": ch}


def ensure_ref_24k(src: Path, dst: Optional[Path] = None, max_seconds: Optional[float] = None) -> tuple[Path, dict]:
    """Ensure a 24 kHz mono 16-bit WAV copy exists at dst without mutating src."""
    src = Path(src)
    if dst is None:
        dst = src.with_name(f"{src.stem}_24k.wav")
    if dst.is_file() and dst.stat().st_mtime >= src.stat().st_mtime:
        info = probe_audio_info(dst)
        if info["sample_rate"] == 24000 and info["channels"] == 1:
            if max_seconds is None or info["duration_s"] <= max_seconds + 0.05:
                return dst, info

    samples, sr, _ = _read_pcm_wave(src)
    samples_24k = _resample_linear(samples, sr, 24000)
    if max_seconds is not None and max_seconds > 0:
        cap = int(math.floor(max_seconds * 24000))
        if len(samples_24k) > cap:
            samples_24k = samples_24k[:cap]
    _write_pcm16_mono(dst, samples_24k, 24000)
    return dst, {
        "duration_s": round(len(samples_24k) / 24000.0, 2),
        "sample_rate": 24000,
        "channels": 1,
    }


def trim_ref_audio(src: Path, dst: Path, max_seconds: float = 12.0) -> tuple[Path, dict]:
    """Write a trimmed 24 kHz mono copy at dst, leaving src untouched."""
    samples, sr, _ = _read_pcm_wave(Path(src))
    samples_24k = _resample_linear(samples, sr, 24000)
    cap = max(24000, int(math.floor(max_seconds * 24000)))
    trimmed = samples_24k[:cap]
    _write_pcm16_mono(Path(dst), trimmed, 24000)
    return Path(dst), {
        "duration_s": round(len(trimmed) / 24000.0, 2),
        "sample_rate": 24000,
        "channels": 1,
    }

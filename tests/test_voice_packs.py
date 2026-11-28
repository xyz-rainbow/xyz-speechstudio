"""xyz-Ioquendo / voice pack unit tests (no network, no shared-file edits)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.orchestrator import voice_packs as vp

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "packs" / "xyz-ioquendo"
SOURCE = Path(r"Z:\[🤖] [Models]\tts\qwen3-1.7b\xyz-Ioquendo")


@pytest.fixture()
def vertical_manifest(tmp_path: Path) -> dict:
    data = vp.build_vertical_manifest_from_bundle(BUNDLE)
    out = tmp_path / "manifest.vertical.v1.json"
    vp.write_manifest(out, data)
    return data


def test_vertical_manifest_has_alvaro_and_alfie(vertical_manifest):
    ids = {v["id"] for v in vertical_manifest["voices"]}
    assert "xyz-ioquendo/es-ES/alvaro" in ids
    assert "xyz-ioquendo/en-GB/alfie" in ids
    assert vertical_manifest["required_model_id"] == "qwen3-1.7b-base"
    assert vertical_manifest["required_quant_id"] == "Q4_K_M"
    assert vertical_manifest["license"]["redistribution"] == "blocked_until_review"
    assert "Loquendo" in vertical_manifest["license"]["disclaimer"]


def test_stable_ids_and_slugify():
    assert vp.slugify_voice_name("Álvaro") == "alvaro"
    assert vp.stable_voice_id("xyz-ioquendo", "es-ES", "Álvaro") == "xyz-ioquendo/es-ES/alvaro"
    arabic_a = vp.slugify_voice_name("فاطمة")
    arabic_b = vp.slugify_voice_name("حمدان")
    assert arabic_a.startswith("v-")
    assert arabic_b.startswith("v-")
    assert arabic_a != arabic_b


def test_install_repair_uninstall_leaves_qwen_and_profiles(tmp_path: Path, vertical_manifest):
    models = tmp_path / "models"
    profiles = tmp_path / "profiles"
    profiles.mkdir(parents=True)
    (profiles / "user-mario.json").write_text("{}", encoding="utf-8")
    qwen = models / "tts" / "qwen3-1.7b"
    qwen.mkdir(parents=True)
    weight = qwen / "qwen-talker-1.7b-base-Q4_K_M.gguf"
    weight.write_bytes(b"fake-weight")

    # Ensure vertical manifest exists in bundle for install_from_bundle.
    vp.write_manifest(BUNDLE / "manifest.vertical.v1.json", vertical_manifest)

    installed = vp.install_from_bundle(models, bundle_dir=BUNDLE)
    assert installed["pack_id"] == "xyz-ioquendo"
    assert len(installed["voices"]) == 2
    assert vp.is_pack_installed(models)

    voices_es = vp.list_installed_voices(models, locale="es-ES")
    assert len(voices_es) == 1
    assert voices_es[0]["name"] == "Álvaro"
    assert voices_es[0]["id"].startswith("pack:")

    resolved = vp.resolve_pack_voice(models, voices_es[0]["id"])
    assert resolved is not None
    assert resolved["editable"] is False
    assert Path(resolved["ref_audio_path"]).is_file()
    assert "Hola" in resolved["ref_text"] or "hola" in resolved["ref_text"].lower()

    # Corrupt a file then repair.
    audio = Path(installed["voices"][0]["audio_path"])
    audio.write_bytes(b"broken")
    repaired = vp.repair_pack(models, bundle_dir=BUNDLE)
    assert Path(repaired["voices"][0]["audio_path"]).stat().st_size > 1000

    personas = vp.to_persona_records(repaired)
    assert personas[0]["id"].startswith("xyz-ioquendo/")
    assert personas[0]["consent"]["license"] == "proprietary-pack"

    result = vp.uninstall_pack(models)
    assert result["removed"] is True
    assert not vp.is_pack_installed(models)
    assert weight.exists(), "Qwen weights must survive pack uninstall"
    assert (profiles / "user-mario.json").exists(), "User profiles must survive pack uninstall"


def test_scan_source_excludes_benchmark_and_reports_pairs():
    if not SOURCE.is_dir():
        pytest.skip("Authoring xyz-Ioquendo tree not mounted")
    voices, excluded, warnings = vp.scan_source_tree(SOURCE)
    assert len(voices) >= 2
    assert any(v["id"] == "xyz-ioquendo/es-ES/alvaro" for v in voices)
    assert all(e.get("reason") != "incomplete_pair" or True for e in excluded)
    # Benchmark dir must not contribute voices.
    assert all("/benchmark/" not in v["audio_relpath"].replace("\\", "/") for v in voices)
    assert any(e.get("reason") == "benchmark_or_skip_dir" for e in excluded)
    # Authoring tree has 453 mp3+txt pairs; all should map to unique stable ids.
    assert len(voices) == 453
    incomplete = [e for e in excluded if e.get("reason") == "incomplete_pair"]
    assert incomplete == []
    dupes = [e for e in excluded if e.get("reason") == "duplicate_id"]
    assert dupes == []


def test_dependency_status_detects_q4():
    class Entry:
        def __init__(self, id, installed, installed_quants):
            self.id = id
            self.installed = installed
            self.installed_quants = installed_quants

    status = vp.dependency_status(
        [Entry("qwen3-1.7b-base", True, ["Q8_0"]), Entry("xyz-ioquendo", False, [])]
    )
    assert status["qwen_base_installed"] is True
    assert status["qwen_q4_installed"] is False
    assert status["ready"] is False

    status_q4 = vp.dependency_status([Entry("qwen3-1.7b-base", True, ["Q4_K_M", "Q8_0"])])
    assert status_q4["ready"] is True


def test_manifest_json_roundtrip(vertical_manifest, tmp_path: Path):
    path = tmp_path / "m.json"
    vp.write_manifest(path, vertical_manifest)
    loaded = vp.load_manifest(path)
    assert loaded.pack_id == "xyz-ioquendo"
    assert loaded.voice_by_id("xyz-ioquendo/es-ES/alvaro").name == "Álvaro"
    assert len(loaded.voices_for_locale("es")) == 1
    assert len(loaded.voices_for_locale("en-GB")) == 1

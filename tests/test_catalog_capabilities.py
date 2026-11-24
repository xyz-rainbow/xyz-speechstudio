"""Pure helpers for TTS catalog capabilities (Fase 1)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.orchestrator.catalog_capabilities import (  # noqa: E402
    capabilities_from_spec,
    is_language_ready,
    resolve_install_target,
    resolve_quant,
    resolve_runtime_envs_root,
    uninstall_language_pack,
)
from backend.orchestrator.downloader import BUILTIN_MODELS, QuantOption, build_catalog  # noqa: E402
from backend.orchestrator.config import AppSettings  # noqa: E402


def test_f5_spanish_is_per_language_es():
    caps = capabilities_from_spec(next(m for m in BUILTIN_MODELS if m["id"] == "f5-tts-spanish"))
    assert caps.install_mode == "per_language_checkpoint"
    assert caps.voice_mode == "clone_profile"
    assert caps.languages == ["es"]


def test_xtts_shared_weights_clone():
    caps = capabilities_from_spec(next(m for m in BUILTIN_MODELS if m["id"] == "xtts-v2"))
    assert caps.install_mode == "shared_weights"
    assert caps.voice_mode == "clone_profile"
    assert "es" in caps.languages


def test_resolve_install_target_requires_language_for_checkpoint():
    target = resolve_install_target(
        install_mode="per_language_checkpoint",
        family_id="f5-tts",
        model_id="f5-tts-spanish",
        language="es",
    )
    assert target["unit"] == "language_checkpoint"
    try:
        resolve_install_target(
            install_mode="per_language_checkpoint",
            family_id="f5-tts",
            model_id="f5-tts-spanish",
            language=None,
        )
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_resolve_quant_prefers_recommended():
    quants = [
        QuantOption(id="a", label="A", disk_mb=1, vram_mib=1, recommended=False),
        QuantOption(id="b", label="B", disk_mb=1, vram_mib=1, recommended=True),
    ]
    assert resolve_quant(quants).id == "b"
    assert resolve_quant(quants, "a").id == "a"


def test_is_language_ready():
    assert is_language_ready("f5-tts", "es", {"f5-tts": ["es", "en"]})
    assert not is_language_ready("f5-tts", "fr", {"f5-tts": ["es"]})


def test_build_catalog_includes_capabilities():
    entries = build_catalog(AppSettings())
    f5 = next(e for e in entries if e.id == "f5-tts-spanish")
    assert f5.capabilities.install_mode == "per_language_checkpoint"
    assert f5.capabilities.languages == ["es"]
    xtts = next(e for e in entries if e.id == "xtts-v2")
    assert xtts.capabilities.install_mode == "shared_weights"


def test_uninstall_language_pack_removes_f5_dir(tmp_path: Path):
    models = tmp_path / "models"
    target = models / "tts" / "f5-tts-spanish"
    target.mkdir(parents=True)
    (target / "vocab.txt").write_text("x", encoding="utf-8")
    deleted = uninstall_language_pack(
        models_root=models,
        install_mode="per_language_checkpoint",
        family_id="f5-tts",
        language="es",
        catalog_specs=BUILTIN_MODELS,
    )
    assert str(target) in deleted
    assert not target.exists()


def test_runtime_envs_prefers_canonical(tmp_path: Path):
    (tmp_path / "runtime" / "envs").mkdir(parents=True)
    (tmp_path / ".venvs").mkdir()
    assert resolve_runtime_envs_root(tmp_path) == tmp_path / "runtime" / "envs"


def test_runtime_envs_falls_back_to_legacy(tmp_path: Path):
    (tmp_path / ".venvs").mkdir()
    assert resolve_runtime_envs_root(tmp_path) == tmp_path / ".venvs"

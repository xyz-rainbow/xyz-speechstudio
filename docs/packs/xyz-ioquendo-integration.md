# xyz-Ioquendo — exact shared-file integration (do not apply blindly while files are locked)

Ready-made modules already land outside the locked set:

- `backend/orchestrator/voice_packs.py`
- `packs/xyz-ioquendo/**` (vertical slice + schema)
- `scripts/build_xyz_ioquendo_manifest.py`
- `src/lib/xyzIoquendo.ts`
- `tests/test_voice_packs.py`
- `docs/packs/xyz-ioquendo.md`

Below are **exact change intents** for the files you asked to coordinate before editing.

---

## 1. `backend/orchestrator/downloader.py`

Add a Featured catalog entry (near other TTS builtins; can replace or sit beside `loquendo-tts7`):

```python
{
    "id": "xyz-ioquendo",
    "name": "xyz-Ioquendo",
    "kind": "tts",
    "engine": "qwen",
    "family_id": "xyz-ioquendo",
    "family_name": "xyz-Ioquendo",
    "variant_label": "Qwen3 reference pack",
    "repo_id": "local/xyz-ioquendo",
    "dir_names": ["voice-packs/xyz-ioquendo"],
    "description": (
        "Reference voice pack for Qwen3-TTS 1.7B Base Q4_K_M cloning. "
        "Independent of Qwen weights. Not an official Loquendo product; "
        "redistribution pending license review."
    ),
    "runtime_supported": True,
    "install_mode": "voices_pack",
    "voice_mode": "clone_profile",
    "quant_policy": "binary",
    "languages": [],  # filled from installed pack locales at catalog build time
    "quants": [
        {
            "id": "references",
            "label": "Reference pack (vertical)",
            "disk_mb": 1,
            "vram_mib": 0,
            "files": [],
            "recommended": True,
        }
    ],
    "depends_on_model_id": "qwen3-1.7b-base",
    "depends_on_quant_id": "Q4_K_M",
    "pack_kind": "reference_pack",
},
```

In `build_catalog` / installed detection for `xyz-ioquendo`:

```python
if m["id"] == "xyz-ioquendo":
    from . import voice_packs
    installed = voice_packs.is_pack_installed(resolved_models_dir(settings))
    # set entry.installed, languages from installed marker locales
```

Do **not** treat pack uninstall as Qwen weight removal.

Optional: stop advertising `loquendo-tts7` as Featured once this card ships (roadmap §3).

---

## 2. `backend/orchestrator/main.py`

Minimal wire-up (routes already live in `voice_pack_routes.py`):

```python
from .voice_pack_routes import router as voice_pack_router
app.include_router(voice_pack_router)
```

Keep Loquendo SAPI routes until you retire `loquendo-tts7`.

In `_resolve_tts_context` / profile lookup, before 404:

```python
if req.profile_id.startswith("pack:"):
    from . import voice_packs
    pack_prof = voice_packs.resolve_pack_voice(Path(resolved_models_dir(settings)), req.profile_id)
    if pack_prof is None:
        raise HTTPException(404, detail=f"Pack voice not found: {req.profile_id}")
    # Use a lightweight namespace/SimpleNamespace or adapt synthesize path to accept
    # ref_audio_path + ref_text + name + language without profiles.get_profile.
```

Session start should store `speaker_label` from pack voice name.

---

## 3. `src/services/api.ts`

```ts
export async function fetchVoicePackStatus(baseUrl: string, packId: string) { ... }
export async function fetchVoicePackVoices(baseUrl: string, packId: string, locale?: string) { ... }
export async function installVoicePack(baseUrl: string, packId: string) { ... }
export async function repairVoicePack(baseUrl: string, packId: string) { ... }
export async function uninstallVoicePack(baseUrl: string, packId: string) { ... }
```

(Wrappers can delegate to `src/lib/xyzIoquendo.ts` for the xyz pack.)

---

## 4. `src/types/index.ts`

```ts
// CatalogModelEntry extras (optional fields)
depends_on_model_id?: string;
depends_on_quant_id?: string;
pack_kind?: "reference_pack";
```

If `InstallMode` is extended in `catalog_capabilities.py` with `reference_pack`, mirror it here.

---

## 5. `src/components/ModelHubModal.tsx`

On the Featured card for `variant.id === "xyz-ioquendo"`:

- Show dependency banner when `dependency.qwen_q4_installed === false` with CTA to install `qwen3-1.7b-base` / `Q4_K_M`.
- Install / Repair / Uninstall pack actions (call voice-pack APIs).
- Copy: not Loquendo official; references for Qwen cloning.
- Mirror other Featured card chrome (GlassCard, quant row can show “Reference pack”).

---

## 6. `src/components/ModelsView.tsx`

Same dependency + pack actions if the Models grid renders `xyz-ioquendo`; ensure uninstall calls pack uninstall, not `remove_installed_model` for Qwen dirs.

---

## Frontend already prepared

- `src/lib/xyzIoquendo.ts` — IDs, locale filter, fetch helpers pointing at the routes above.
- Wire `TtsStudioView` after routes exist: when active engine is Qwen + pack installed, merge `fetchXyzIoquendoVoices` into the voice selector (read-only; `profile_id = pack:…`).

## Persona

`voice_packs.to_persona_records()` emits stable Persona-compatible dicts. Later Persona cards download by the same `id` (`xyz-ioquendo/es-ES/alvaro`).

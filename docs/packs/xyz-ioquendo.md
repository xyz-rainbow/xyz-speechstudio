# xyz-Ioquendo reference pack

Internal Speech Studio pack of **audio + transcript** pairs for **Qwen3-TTS 1.7B Base** cloning. It is **not** a new TTS worker and **not** an official Loquendo product. The pack name does **not** grant rights over third-party samples or trademarks.

## Status (vertical E2E)

| Piece | State |
| --- | --- |
| Manifest + vertical slice (Álvaro `es-ES`, Alfie `en-GB`) | Shipped under `packs/xyz-ioquendo/` |
| Install / repair / uninstall API | `/api/voice-packs/xyz-ioquendo` |
| Featured + Models card | `XyzIoquendoInstallControl` (dependency CTA for Q4) |
| Synthesize voice selector | Pack voices as `pack:…` (not editable profiles) |
| Full 453-voice publish | **Blocked** until license review — do not upload |
| Declared quant dependency | `qwen3-1.7b-base` / `Q4_K_M` |

## Engine dependency

| Field | Value |
| --- | --- |
| Engine | `qwen` (existing CrispASR / Qwen path) |
| Model | `qwen3-1.7b-base` |
| Quant (card CTA) | `Q4_K_M` |
| Pack id | `xyz-ioquendo` |

Installing or uninstalling this pack must **never** delete Qwen weights or user profiles under `profiles/`.

The Featured card explains the Q4 dependency and can start that download. Cloning still works against any installed Base quant for local smoke tests; the product CTA remains Q4_K_M.

## Provenance

Reference clips under the authoring tree `…/tts/qwen3-1.7b/xyz-Ioquendo/<locale>/` were prepared as **synthetic references generated with Qwen3-TTS** for cloning demos (full MP3 + matching TXT). Benchmark outputs under `benchmark/` are **excluded** from the pack manifest.

Speech Studio ships a **vertical slice** only (`Álvaro` / `es-ES`, `Alfie` / `en-GB`) under `packs/xyz-ioquendo/voices/` for local verification. The full catalog (~453 pairs, ~100.5 MB of MP3) remains outside the published installer until license review completes.

## License / redistribution

**Status: blocked until review.** Do not publish, upload, or redistribute the pack archive yet.

- Do **not** claim affiliation with Loquendo, Nuance, or Vocalizer.
- Do **not** present these clips as licensed Loquendo TTS 7 voices.
- Treat redistribution as **proprietary-pack** / pending counsel review.
- Persona cards may reuse the same stable voice IDs later; consent metadata marks `provenance_type: pack_reference` and `license: proprietary-pack`.

## Manifest

Schema: `speechstudio.voice_pack.v1`

Stable voice id: `xyz-ioquendo/<locale>/<slug>`  
API / UI profile-style id: `pack:xyz-ioquendo/<locale>/<slug>`

Fields per voice: `id`, `name`, `locale` (e.g. `es-ES`), `audio_relpath`, `text_relpath`, `duration_s`, `format`, `audio_sha256`, `text_sha256`, provenance.

Build:

```bash
python scripts/build_xyz_ioquendo_manifest.py --vertical
python scripts/build_xyz_ioquendo_manifest.py --full --source "PATH/to/xyz-Ioquendo"
```

## Install layout

```
<models_dir>/voice-packs/xyz-ioquendo/
  installed.json
  manifest.json
  voices/<locale>/<slug>/audio.mp3
  voices/<locale>/<slug>/transcript.txt
```

Operations: install (from local bundle), repair (re-hash + re-copy), update (version bump), uninstall (delete pack dir only).

## UX

1. Featured card **xyz-Ioquendo** with Install / Repair / Uninstall.
2. If Q4 is missing, the card shows the dependency and offers **Install Qwen Q4**.
3. Keep **Qwen3-TTS 1.7B Base** as the active model in Synthesize (the pack is not a loadable engine).
4. After install, voices appear in the clone selector filtered by locale (e.g. Álvaro for Spanish / `es-ES`).
5. References are **not** written to `profiles.json` and are not editable Persona/profile cards until a future Persona download flow reuses the same IDs.

## Verification

```bash
python -m pytest tests/test_voice_packs.py tests/test_xyz_ioquendo_e2e.py -q
npx tsc --noEmit -p tsconfig.json
```

Manual audio (requires CrispASR + Qwen Base loaded):

1. Install the vertical pack from Featured.
2. Activate `qwen3-1.7b-base` (Q4 preferred; Q8 acceptable for smoke).
3. Synthesize a **new** Spanish sentence with Álvaro, then an English sentence with Alfie.
4. Restart the app, select the same voices again, synthesize once more.
5. Uninstall the pack and confirm Qwen weights + user profiles remain.

### Local smoke (2026-11-28)

On this workstation only **Q8_0** Base weights were installed (`N:\data\models\tts\qwen3-1.7b`). Vertical pack install + resolve + three CrispASR generations succeeded:

| Voice | New text | Duration |
| --- | --- | --- |
| Álvaro | Spanish smoke sentence | ~3.9 s |
| Alfie | English smoke sentence | ~5.9 s |
| Álvaro (2nd pass) | Second generation after re-resolve | ~3.6 s |

Outputs: `data/tmp/xyz_ioquendo_alvaro_e2e.wav`, `data/tmp/xyz_ioquendo_alfie_e2e.wav`. Q4 CTA remains correct for the Featured card; download Q4 when validating the declared dependency path.

## Integration notes

See [xyz-ioquendo-integration.md](./xyz-ioquendo-integration.md) for the shared-file checklist. Routes live in `voice_pack_routes.py` and are included from `main.py`.

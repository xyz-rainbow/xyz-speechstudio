# xyz-Ioquendo (vertical slice)

Local reference pack for Speech Studio. Engine: existing **Qwen3-TTS 1.7B Base Q4_K_M**. Not a new worker. Not Loquendo official.

## Vertical voices

| ID | Name | Locale |
| --- | --- | --- |
| `xyz-ioquendo/es-ES/alvaro` | Álvaro | es-ES |
| `xyz-ioquendo/en-GB/alfie` | Alfie | en-GB |

Originals on the authoring disk are left untouched. This folder holds copies for install/repair tests only.

## Commands

```bash
python scripts/build_xyz_ioquendo_manifest.py --vertical
python -m pytest tests/test_voice_packs.py -q
```

Do **not** publish this pack until license review completes. See [docs/packs/xyz-ioquendo.md](../../docs/packs/xyz-ioquendo.md).

import type { CatalogModelEntry, ModelCapabilities } from "../types/index.ts";
import type {
  EngineAudioRequirement,
  EngineCompatibilityEvaluation,
  PersonaAudioSpec,
  PersonaRecord,
} from "../types/persona.ts";

export const ENGINE_AUDIO_REQUIREMENTS: Record<string, EngineAudioRequirement> = {
  qwen: {
    engine: "qwen",
    label: "Qwen3-TTS",
    supports_cloning: true,
    target_sample_rate_hz: 24000,
    target_channels: 1,
    max_duration_s: null,
    recommended_duration_s: [6, 15],
    ref_text_requirement: "recommended",
    notes: "CrispASR reads 24 kHz mono 16-bit PCM WAV; Python worker also extracts .spk/.rvq embeddings.",
  },
  chatterbox: {
    engine: "chatterbox",
    label: "Chatterbox",
    supports_cloning: true,
    target_sample_rate_hz: 24000,
    target_channels: 1,
    max_duration_s: null,
    recommended_duration_s: [5, 15],
    ref_text_requirement: "optional",
    notes: "Normalized to 24 kHz mono PCM16 WAV before CrispASR synthesis.",
  },
  "chatterbox-turbo": {
    engine: "chatterbox-turbo",
    label: "Chatterbox Turbo",
    supports_cloning: true,
    target_sample_rate_hz: 24000,
    target_channels: 1,
    max_duration_s: null,
    recommended_duration_s: [5, 15],
    ref_text_requirement: "optional",
    notes: "Normalized to 24 kHz mono PCM16 WAV before CrispASR synthesis.",
  },
  "cosyvoice3-tts": {
    engine: "cosyvoice3-tts",
    label: "CosyVoice3",
    supports_cloning: true,
    target_sample_rate_hz: 24000,
    target_channels: 1,
    max_duration_s: null,
    recommended_duration_s: [5, 15],
    ref_text_requirement: "recommended",
    notes: "Normalized to 24 kHz mono PCM16 WAV; reference transcript improves alignment.",
  },
  indextts: {
    engine: "indextts",
    label: "IndexTTS 1.5",
    supports_cloning: true,
    target_sample_rate_hz: 24000,
    target_channels: 1,
    max_duration_s: null,
    recommended_duration_s: [5, 15],
    ref_text_requirement: "optional",
    notes: "Normalized to 24 kHz mono PCM16 WAV before CrispASR synthesis.",
  },
  f5: {
    engine: "f5",
    label: "F5-TTS",
    supports_cloning: true,
    target_sample_rate_hz: 24000,
    target_channels: 1,
    max_duration_s: 12,
    recommended_duration_s: [6, 11],
    ref_text_requirement: "required",
    notes: "Requires matching transcript; clips over 12s are non-destructively trimmed to <=11s.",
  },
  xtts: {
    engine: "xtts",
    label: "XTTS v2",
    supports_cloning: true,
    target_sample_rate_hz: 22050,
    target_channels: 1,
    max_duration_s: null,
    recommended_duration_s: [6, 12],
    ref_text_requirement: "optional",
    notes: "XTTS worker loads WAV/FLAC/OGG and resamples mono conditioning audio to 22.05 kHz (24 kHz fallback supported).",
  },
  fish: {
    engine: "fish",
    label: "Fish Speech 1.5",
    supports_cloning: true,
    target_sample_rate_hz: 44100,
    target_channels: 1,
    max_duration_s: null,
    recommended_duration_s: [5, 15],
    ref_text_requirement: "recommended",
    notes: "Firefly VQGAN encodes mono reference audio at 44.1 kHz with paired transcript.",
  },
  kokoro: {
    engine: "kokoro",
    label: "Kokoro 82M",
    supports_cloning: false,
    target_sample_rate_hz: null,
    target_channels: null,
    max_duration_s: null,
    recommended_duration_s: null,
    ref_text_requirement: "none",
    notes: "Uses built-in voices only; zero-shot voice cloning is not supported.",
  },
  piper: {
    engine: "piper",
    label: "Piper",
    supports_cloning: false,
    target_sample_rate_hz: null,
    target_channels: null,
    max_duration_s: null,
    recommended_duration_s: null,
    ref_text_requirement: "none",
    notes: "Single-speaker ONNX/GGUF built-in voices only; voice cloning is not supported.",
  },
  orpheus: {
    engine: "orpheus",
    label: "Orpheus 3B",
    supports_cloning: false,
    target_sample_rate_hz: null,
    target_channels: null,
    max_duration_s: null,
    recommended_duration_s: null,
    ref_text_requirement: "none",
    notes: "Cataloged with built-in voice presets only; custom cloning is not supported.",
  },
  kitten: {
    engine: "kitten",
    label: "KittenTTS 2 Mini",
    supports_cloning: false,
    target_sample_rate_hz: null,
    target_channels: null,
    max_duration_s: null,
    recommended_duration_s: null,
    ref_text_requirement: "none",
    notes: "Uses packaged voices_<lang>.npz presets only; custom cloning is not supported.",
  },
  espeak: {
    engine: "espeak",
    label: "eSpeak NG",
    supports_cloning: false,
    target_sample_rate_hz: null,
    target_channels: null,
    max_duration_s: null,
    recommended_duration_s: null,
    ref_text_requirement: "none",
    notes: "Formant synthesizer with built-in voices only; voice cloning is not supported.",
  },
  sapi5: {
    engine: "sapi5",
    label: "Windows SAPI 5",
    supports_cloning: false,
    target_sample_rate_hz: null,
    target_channels: null,
    max_duration_s: null,
    recommended_duration_s: null,
    ref_text_requirement: "none",
    notes: "System SAPI 5 / Loquendo voices only; custom audio cloning is not supported.",
  },
};

export function normalizeEngineKey(engine: string): string {
  const low = (engine || "").trim().toLowerCase();
  if (low === "f5-tts") return "f5";
  if (low === "fish-audio") return "fish";
  if (low === "qwen3-tts") return "qwen";
  if (low === "cosyvoice3") return "cosyvoice3-tts";
  return low;
}

export function getEngineAudioRequirement(
  engine: string,
  capabilities?: ModelCapabilities
): EngineAudioRequirement {
  const key = normalizeEngineKey(engine);
  const known = ENGINE_AUDIO_REQUIREMENTS[key];
  if (known) {
    if (capabilities?.voice_mode === "builtin_voices" && known.supports_cloning) {
      return {
        ...known,
        supports_cloning: false,
        ref_text_requirement: "none",
        notes: "Active model capability reports built-in voices only; cloning disabled.",
      };
    }
    return known;
  }

  if (capabilities?.voice_mode === "clone_profile") {
    return {
      engine: key || engine,
      label: engine,
      supports_cloning: true,
      target_sample_rate_hz: 24000,
      target_channels: 1,
      max_duration_s: null,
      recommended_duration_s: [6, 12],
      ref_text_requirement: "recommended",
      notes: "Declared clone_profile capability; standard 24 kHz mono PCM WAV conversion assumed.",
    };
  }

  return {
    engine: key || engine,
    label: engine || "Unknown",
    supports_cloning: false,
    target_sample_rate_hz: null,
    target_channels: null,
    max_duration_s: null,
    recommended_duration_s: null,
    ref_text_requirement: "none",
    notes: "Cloning support could not be verified for this engine.",
  };
}

export function evaluateAudioForEngine(
  engine: string,
  audio: PersonaAudioSpec,
  refText: string,
  options?: {
    modelId?: string;
    label?: string;
    installed?: boolean;
    capabilities?: ModelCapabilities;
  }
): EngineCompatibilityEvaluation {
  const key = normalizeEngineKey(engine);
  const known = Boolean(ENGINE_AUDIO_REQUIREMENTS[key] || options?.capabilities);
  const req = getEngineAudioRequirement(engine, options?.capabilities);
  const label = options?.label || req.label;
  const installed = options?.installed ?? false;

  if (!known) {
    return {
      engine: req.engine,
      model_id: options?.modelId,
      label,
      installed,
      supports_cloning: false,
      status: "unknown",
      requirement: req,
      conversions_needed: [],
      warnings: [req.notes],
    };
  }

  if (!req.supports_cloning) {
    return {
      engine: req.engine,
      model_id: options?.modelId,
      label,
      installed,
      supports_cloning: false,
      status: "unsupported_no_cloning",
      requirement: req,
      conversions_needed: [],
      warnings: [req.notes],
    };
  }

  const conversions_needed: string[] = [];
  const warnings: string[] = [];

  if (audio.format !== "wav") {
    conversions_needed.push(`Transcode ${audio.format.toUpperCase()} -> 16-bit PCM WAV`);
  }
  if (audio.channels > 1) {
    conversions_needed.push(`Downmix ${audio.channels}ch -> mono (1ch)`);
  }
  if (
    req.target_sample_rate_hz !== null &&
    audio.sample_rate_hz > 0 &&
    audio.sample_rate_hz !== req.target_sample_rate_hz
  ) {
    const srcKhz = (audio.sample_rate_hz / 1000).toFixed(1).replace(/\.0$/, "");
    const dstKhz = (req.target_sample_rate_hz / 1000).toFixed(1).replace(/\.0$/, "");
    conversions_needed.push(`Resample ${srcKhz} kHz -> ${dstKhz} kHz`);
  }
  if (req.max_duration_s !== null && audio.duration_s > req.max_duration_s) {
    conversions_needed.push(
      `Trim ${audio.duration_s.toFixed(1)}s -> <=${req.max_duration_s}s (keeps original)`
    );
  }

  if (!refText.trim()) {
    if (req.ref_text_requirement === "required") {
      warnings.push("Reference transcript is required for accurate timing.");
    } else if (req.ref_text_requirement === "recommended") {
      warnings.push("Reference transcript recommended for cleaner cloning.");
    }
  }

  if (req.recommended_duration_s) {
    const [minRec, maxRec] = req.recommended_duration_s;
    if (audio.duration_s > 0 && audio.duration_s < minRec) {
      warnings.push(`Clip is short (${audio.duration_s.toFixed(1)}s < ${minRec}s recommended).`);
    } else if (req.max_duration_s === null && audio.duration_s > maxRec) {
      warnings.push(
        `Clip exceeds ideal window (${audio.duration_s.toFixed(1)}s > ${maxRec}s recommended).`
      );
    }
  }

  return {
    engine: req.engine,
    model_id: options?.modelId,
    label,
    installed,
    supports_cloning: true,
    status: conversions_needed.length > 0 ? "needs_conversion" : "compatible",
    requirement: req,
    conversions_needed,
    warnings,
  };
}

export function evaluatePersonaAgainstCatalog(
  persona: PersonaRecord,
  catalog: CatalogModelEntry[],
  activeTtsModelId?: string
): {
  active: EngineCompatibilityEvaluation | null;
  compatible: EngineCompatibilityEvaluation[];
  unsupported: EngineCompatibilityEvaluation[];
  preferredCloneEngine: string | null;
} {
  const ttsEntries = catalog.filter((m) => m.kind === "tts");
  const activeEntry = activeTtsModelId
    ? ttsEntries.find(
        (m) =>
          m.id === activeTtsModelId ||
          activeTtsModelId.startsWith(`${m.id}-`) ||
          m.id.startsWith(activeTtsModelId)
      ) || null
    : null;

  const active = activeEntry
    ? evaluateAudioForEngine(activeEntry.engine, persona.audio, persona.ref_text, {
        modelId: activeEntry.id,
        label: activeEntry.family_name || activeEntry.name,
        installed: activeEntry.installed,
        capabilities: activeEntry.capabilities,
      })
    : null;

  // Deduplicate by normalized engine key, keeping installed entry first if present.
  const byEngine = new Map<string, CatalogModelEntry>();
  for (const entry of ttsEntries) {
    const key = normalizeEngineKey(entry.engine);
    const prev = byEngine.get(key);
    if (!prev || (!prev.installed && entry.installed)) {
      byEngine.set(key, entry);
    }
  }

  const evaluations: EngineCompatibilityEvaluation[] = [];
  if (byEngine.size > 0) {
    for (const entry of byEngine.values()) {
      evaluations.push(
        evaluateAudioForEngine(entry.engine, persona.audio, persona.ref_text, {
          modelId: entry.id,
          label: entry.family_name || entry.name,
          installed: entry.installed && entry.runtime_supported,
          capabilities: entry.capabilities,
        })
      );
    }
  } else {
    for (const req of Object.values(ENGINE_AUDIO_REQUIREMENTS)) {
      evaluations.push(
        evaluateAudioForEngine(req.engine, persona.audio, persona.ref_text, {
          label: req.label,
          installed: false,
        })
      );
    }
  }

  const compatible = evaluations
    .filter((ev) => ev.supports_cloning)
    .sort((a, b) => Number(b.installed) - Number(a.installed));
  const unsupported = evaluations.filter((ev) => !ev.supports_cloning);

  let preferredCloneEngine: string | null = null;
  if (active && active.supports_cloning && active.installed) {
    preferredCloneEngine = active.engine;
  } else {
    const firstInstalled = compatible.find((ev) => ev.installed);
    preferredCloneEngine =
      firstInstalled?.engine ||
      (persona.recommended_engines[0] ? normalizeEngineKey(persona.recommended_engines[0]) : "qwen");
  }

  return {
    active,
    compatible,
    unsupported,
    preferredCloneEngine,
  };
}

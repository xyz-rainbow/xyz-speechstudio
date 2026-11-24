import type { EndpointProtocol, ExternalEndpointConfig } from "../types";

export interface EndpointPresetTemplate {
  key: string;
  label: string;
  name: string;
  protocol: EndpointProtocol;
  base_url: string;
  model: string;
  voice: string;
}

export const ENDPOINT_PRESETS: Record<"tts" | "stt", EndpointPresetTemplate[]> = {
  stt: [
    {
      key: "groq",
      label: "Groq Whisper",
      name: "Groq Whisper Turbo",
      protocol: "openai",
      base_url: "https://api.groq.com/openai/v1",
      model: "whisper-large-v3-turbo",
      voice: "",
    },
    {
      key: "openai",
      label: "OpenAI Whisper",
      name: "OpenAI Whisper",
      protocol: "openai",
      base_url: "https://api.openai.com/v1",
      model: "whisper-1",
      voice: "",
    },
    {
      key: "deepgram",
      label: "Deepgram Nova-3",
      name: "Deepgram Nova-3",
      protocol: "deepgram",
      base_url: "https://api.deepgram.com/v1",
      model: "nova-3",
      voice: "",
    },
    {
      key: "custom",
      label: "Custom STT",
      name: "Custom STT API",
      protocol: "openai",
      base_url: "http://127.0.0.1:8000/v1",
      model: "whisper-1",
      voice: "",
    },
  ],
  tts: [
    {
      key: "openai",
      label: "OpenAI TTS",
      name: "OpenAI TTS",
      protocol: "openai",
      base_url: "https://api.openai.com/v1",
      model: "gpt-4o-mini-tts",
      voice: "alloy",
    },
    {
      key: "elevenlabs",
      label: "ElevenLabs",
      name: "ElevenLabs",
      protocol: "elevenlabs",
      base_url: "https://api.elevenlabs.io/v1",
      model: "eleven_multilingual_v2",
      voice: "21m00Tcm4TlvDq8ikWAM",
    },
    {
      key: "custom",
      label: "Custom TTS",
      name: "Custom TTS API",
      protocol: "openai",
      base_url: "http://127.0.0.1:8000/v1",
      model: "tts-1",
      voice: "default",
    },
  ],
};

export function createEndpointFromPreset(
  kind: "tts" | "stt",
  preset?: EndpointPresetTemplate
): ExternalEndpointConfig {
  const shortId =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID().slice(0, 8)
      : Math.random().toString(36).slice(2, 10);

  if (preset) {
    return {
      id: `ep-${kind}-${shortId}`,
      name: preset.name,
      kind,
      protocol: preset.protocol,
      base_url: preset.base_url,
      api_key: "",
      model: preset.model,
      voice: kind === "tts" ? preset.voice : "",
    };
  }

  return {
    id: `ep-${kind}-${shortId}`,
    name: kind === "tts" ? "New TTS Endpoint" : "New STT Endpoint",
    kind,
    protocol: "openai",
    base_url: "",
    api_key: "",
    model: "",
    voice: "",
  };
}

export function reconcileActiveEndpointId(
  endpoints: ExternalEndpointConfig[],
  kind: "tts" | "stt",
  currentActiveId: string
): string {
  const matching = endpoints.filter((e) => e.kind === kind);
  if (matching.some((e) => e.id === currentActiveId)) {
    return currentActiveId;
  }
  return matching[0]?.id || "";
}

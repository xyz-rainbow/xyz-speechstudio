import type { EngineKind, VoiceProfile } from "../types";

export interface VoiceDesignStatus {
  installed: boolean;
  crispasr_available: boolean;
  ready: boolean;
  model_id: string;
  quant_id: string | null;
  model_path: string | null;
  model_dir: string | null;
}

export interface VoiceDesignPreviewResponse {
  preview_id: string;
  audio_url: string;
  duration_s: number;
  sr: number;
  elapsed_s: number;
}

async function handleJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      if (data?.detail) {
        msg = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      }
    } catch {
      const txt = await res.text().catch(() => "");
      if (txt) msg = txt;
    }
    throw new Error(msg);
  }
  return (await res.json()) as T;
}

export async function fetchVoiceDesignStatus(baseUrl: string): Promise<VoiceDesignStatus> {
  const res = await fetch(`${baseUrl}/api/tts/voice-design/status`);
  return handleJson<VoiceDesignStatus>(res);
}

export async function generateVoiceDesignPreview(
  baseUrl: string,
  payload: {
    instructions: string;
    language: string;
    sample_text: string;
    device?: "gpu" | "cpu";
  }
): Promise<VoiceDesignPreviewResponse> {
  const res = await fetch(`${baseUrl}/api/tts/voice-design/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleJson<VoiceDesignPreviewResponse>(res);
}

export async function saveVoiceDesignProfile(
  baseUrl: string,
  payload: {
    preview_id: string;
    name: string;
    language: string;
    sample_text: string;
    engine?: EngineKind;
  }
): Promise<VoiceProfile> {
  const res = await fetch(`${baseUrl}/api/tts/voice-design/save`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await handleJson<{ profile: VoiceProfile }>(res);
  return data.profile;
}

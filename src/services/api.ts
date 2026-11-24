import { invoke } from "@tauri-apps/api/core";
import type {
  AppSettings,
  BackendInfo,
  DeviceMode,
  DownloadJob,
  EndpointTestResponse,
  EngineKind,
  GenerationRecord,
  HfInspectResponse,
  ModelsCatalogResponse,
  SettingsResponse,
  SynthesizeResponse,
  TranscribeResponse,
  VoiceProfile,
  VramStatus,
  WorkersSnapshot,
} from "../types";

export const isTauri = () =>
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

export class LiveCaptionsConflictError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "LiveCaptionsConflictError";
  }
}

async function parseErrorOrJson<T>(res: Response): Promise<T> {
  if (res.status === 409) {
    const body = await res.json().catch(() => ({}));
    if (body?.requires_confirmation) {
      throw new LiveCaptionsConflictError(body.detail || "Live Captions is active.");
    }
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function getVramStatus(): Promise<VramStatus> {
  if (!isTauri()) {
    return {
      available: true,
      gpu: "NVIDIA GeForce RTX 2060 (Preview)",
      total_mib: 6144,
      used_mib: 1200,
      free_mib: 4944,
    };
  }
  return invoke<VramStatus>("get_vram_status");
}

export async function getBackendInfo(): Promise<BackendInfo> {
  if (!isTauri()) {
    return {
      running: true,
      port: 8765,
      pid: 0,
      base_url: "http://127.0.0.1:8765",
    };
  }
  return invoke<BackendInfo>("get_backend_info");
}

export async function toggleOverlayWindow(): Promise<boolean> {
  if (!isTauri()) return false;
  return invoke<boolean>("toggle_overlay");
}

export async function setOverlayPinned(pinned: boolean): Promise<void> {
  if (!isTauri()) return;
  await invoke("set_overlay_pinned", { pinned });
}

export async function sendWindowsToast(
  title: string,
  message: string,
  progress?: number
): Promise<void> {
  if (!isTauri()) return;
  await invoke("send_toast", { title, message, progress: progress ?? null });
}

export async function revealInExplorer(path: string): Promise<void> {
  if (!isTauri()) return;
  await invoke("reveal_in_explorer", { path });
}

export interface TrayLabelsPayload {
  open: string;
  show_hide: string;
  subtitles: string;
  stop_subtitles: string;
  eject: string;
  exit: string;
  subtitles_active: boolean;
}

export async function updateTrayMenu(labels: TrayLabelsPayload): Promise<void> {
  if (!isTauri()) return;
  await invoke("update_tray", { labels });
}

export async function setReadHotkey(accelerator: string): Promise<void> {
  if (!isTauri()) return;
  await invoke("set_read_hotkey", { accelerator });
}

export async function fetchSettings(baseUrl: string): Promise<SettingsResponse> {
  const res = await fetch(`${baseUrl}/api/settings`);
  return parseErrorOrJson<SettingsResponse>(res);
}

export async function saveSettings(
  baseUrl: string,
  settings: AppSettings
): Promise<SettingsResponse> {
  const res = await fetch(`${baseUrl}/api/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
  return parseErrorOrJson<SettingsResponse>(res);
}

export async function fetchWorkers(baseUrl: string): Promise<WorkersSnapshot> {
  const res = await fetch(`${baseUrl}/api/workers`);
  return parseErrorOrJson<WorkersSnapshot>(res);
}

export async function loadQwenWorker(
  baseUrl: string,
  device?: DeviceMode,
  forceStopCaptions = false,
  modelId?: string
): Promise<WorkersSnapshot> {
  const res = await fetch(`${baseUrl}/api/workers/qwen/load`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model_id: modelId ?? null,
      device: device ?? null,
      force_stop_captions: forceStopCaptions,
    }),
  });
  return parseErrorOrJson<WorkersSnapshot>(res);
}

export async function loadSttWorker(
  baseUrl: string,
  modelId?: string,
  device?: DeviceMode,
  forceStopCaptions = false
): Promise<WorkersSnapshot> {
  const res = await fetch(`${baseUrl}/api/workers/stt/load`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model_id: modelId ?? null,
      device: device ?? null,
      force_stop_captions: forceStopCaptions,
    }),
  });
  return parseErrorOrJson<WorkersSnapshot>(res);
}

export async function ejectWorker(
  baseUrl: string,
  family: string
): Promise<WorkersSnapshot> {
  const res = await fetch(`${baseUrl}/api/workers/${family}/eject`, {
    method: "POST",
  });
  return parseErrorOrJson<WorkersSnapshot>(res);
}

export async function ejectWorkerGroup(
  baseUrl: string,
  group: "tts" | "stt"
): Promise<WorkersSnapshot> {
  const res = await fetch(`${baseUrl}/api/workers/eject_group/${group}`, {
    method: "POST",
  });
  return parseErrorOrJson<WorkersSnapshot>(res);
}

export async function testExternalEndpoint(
  baseUrl: string,
  endpointId: string
): Promise<EndpointTestResponse> {
  const res = await fetch(`${baseUrl}/api/endpoints/${endpointId}/test`, {
    method: "POST",
  });
  return parseErrorOrJson<EndpointTestResponse>(res);
}

export async function fetchProfiles(baseUrl: string): Promise<VoiceProfile[]> {
  const res = await fetch(`${baseUrl}/api/profiles`);
  const data = await parseErrorOrJson<{ profiles: VoiceProfile[] }>(res);
  return data.profiles;
}

export async function createProfile(
  baseUrl: string,
  payload: {
    name: string;
    language: string;
    engine: EngineKind;
    ref_audio_path: string;
    ref_text: string;
    build_voice?: boolean;
  }
): Promise<VoiceProfile> {
  const res = await fetch(`${baseUrl}/api/profiles`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...payload, build_voice: payload.build_voice ?? true }),
  });
  const data = await parseErrorOrJson<{ profile: VoiceProfile }>(res);
  return data.profile;
}

export async function updateProfile(
  baseUrl: string,
  profileId: string,
  payload: {
    name?: string;
    language?: string;
    engine?: EngineKind;
    ref_audio_path?: string;
    ref_text?: string;
    rebuild_voice?: boolean;
  }
): Promise<VoiceProfile> {
  const res = await fetch(`${baseUrl}/api/profiles/${profileId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await parseErrorOrJson<{ profile: VoiceProfile }>(res);
  return data.profile;
}

export async function buildProfileVoice(
  baseUrl: string,
  profileId: string
): Promise<VoiceProfile> {
  const res = await fetch(`${baseUrl}/api/profiles/${profileId}/build`, {
    method: "POST",
  });
  const data = await parseErrorOrJson<{ profile: VoiceProfile }>(res);
  return data.profile;
}

export async function deleteProfile(baseUrl: string, profileId: string): Promise<void> {
  const res = await fetch(`${baseUrl}/api/profiles/${profileId}`, {
    method: "DELETE",
  });
  await parseErrorOrJson(res);
}

export async function synthesizeTts(
  baseUrl: string,
  payload: {
    profile_id: string;
    text: string;
    language?: string;
    mode: "play" | "wav";
    seed?: number;
    force_stop_captions?: boolean;
  }
): Promise<SynthesizeResponse> {
  const res = await fetch(`${baseUrl}/api/tts/synthesize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseErrorOrJson<SynthesizeResponse>(res);
}

export async function transcribeAudioFile(
  baseUrl: string,
  payload: {
    audio_path: string;
    language?: string;
    model_id?: string;
  }
): Promise<TranscribeResponse> {
  const res = await fetch(`${baseUrl}/api/stt/transcribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseErrorOrJson<TranscribeResponse>(res);
}

export async function fetchHistory(baseUrl: string): Promise<GenerationRecord[]> {
  const res = await fetch(`${baseUrl}/api/tts/history`);
  const data = await parseErrorOrJson<{ history: GenerationRecord[] }>(res);
  return data.history;
}

export async function saveHistoryAs(
  baseUrl: string,
  recId: string,
  destPath: string
): Promise<GenerationRecord> {
  const res = await fetch(`${baseUrl}/api/tts/history/${recId}/save_as`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dest_path: destPath }),
  });
  const data = await parseErrorOrJson<{ record: GenerationRecord }>(res);
  return data.record;
}

export async function deleteHistoryRecord(baseUrl: string, recId: string): Promise<void> {
  const res = await fetch(`${baseUrl}/api/tts/history/${recId}`, {
    method: "DELETE",
  });
  await parseErrorOrJson(res);
}

export async function fetchModelsCatalog(baseUrl: string): Promise<ModelsCatalogResponse> {
  const res = await fetch(`${baseUrl}/api/models/catalog`);
  return parseErrorOrJson<ModelsCatalogResponse>(res);
}

export async function startModelDownload(
  baseUrl: string,
  modelId: string,
  quantId?: string
): Promise<DownloadJob> {
  const res = await fetch(`${baseUrl}/api/models/download`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model_id: modelId, quant_id: quantId ?? null }),
  });
  const data = await parseErrorOrJson<{ job: DownloadJob }>(res);
  return data.job;
}

export async function cancelModelDownload(baseUrl: string, jobId: string): Promise<void> {
  const res = await fetch(`${baseUrl}/api/models/downloads/${jobId}/cancel`, {
    method: "POST",
  });
  await parseErrorOrJson(res);
}

export async function removeInstalledModel(baseUrl: string, modelId: string): Promise<void> {
  const res = await fetch(`${baseUrl}/api/models/${encodeURIComponent(modelId)}`, {
    method: "DELETE",
  });
  await parseErrorOrJson(res);
}

export async function inspectHfRepo(baseUrl: string, url: string): Promise<HfInspectResponse> {
  const res = await fetch(`${baseUrl}/api/models/hf/inspect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  return parseErrorOrJson<HfInspectResponse>(res);
}

export async function installHfModel(
  baseUrl: string,
  payload: {
    repo_id: string;
    name: string;
    kind: "tts" | "stt";
    files: string[];
  }
): Promise<DownloadJob> {
  const res = await fetch(`${baseUrl}/api/models/hf/install`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await parseErrorOrJson<{ job: DownloadJob }>(res);
  return data.job;
}

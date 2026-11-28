export type TabId =
  | "synthesize"
  | "profiles"
  | "transcriber"
  | "subtitles"
  | "models"
  | "settings"
  | "updates";

export type DeviceMode = "gpu" | "cpu";
export type SourceMode = "local" | "endpoint";
export type ThemeMode = "dark" | "light";
export type AccentPreset = "cyber" | "emerald" | "amber" | "rose";
export type EngineKind = "qwen" | "xtts" | "f5" | "fish" | "chatterbox" | "chatterbox-turbo" | "cosyvoice3-tts" | "orpheus" | "indextts";
export type EndpointProtocol = "openai" | "elevenlabs" | "deepgram";
export type CloseBehavior = "ask" | "minimize" | "quit";

export interface ExternalEndpointConfig {
  id: string;
  name: string;
  kind: "tts" | "stt";
  protocol: EndpointProtocol;
  base_url: string;
  api_key: string;
  model: string;
  voice: string;
}

export interface AppSettings {
  language: "en" | "es";
  theme: ThemeMode;
  accent: AccentPreset;
  ascii_fx_enabled: boolean;
  ascii_fx_opacity: number;
  sidebar_collapsed: boolean;
  models_dir: string;
  outputs_dir: string;
  tts_device: DeviceMode;
  stt_device: DeviceMode;
  tts_source: SourceMode;
  stt_source: SourceMode;
  active_tts_model: string;
  active_stt_model: string;
  active_tts_endpoint_id: string;
  active_stt_endpoint_id: string;
  captions_max_history: number;
  notifications_enabled: boolean;
  api_endpoint_enabled: boolean;
  api_fixed_port: number;
  api_bind_host: "127.0.0.1" | "0.0.0.0";
  api_bearer_token: string;
  read_hotkey: string;
  close_behavior: CloseBehavior;
  tts_chunk_enabled: boolean;
  tts_chunk_max_chars: number;
  model_runtimes?: Record<string, "crispasr" | "python">;
  external_endpoints: ExternalEndpointConfig[];
  capabilities_v1: boolean;
  /** family_id → language codes ready on disk */
  installed_languages: Record<string, string[]>;
}

export interface SettingsResponse {
  settings: AppSettings;
  resolved_models_dir: string;
  resolved_outputs_dir: string;
  api_base_url: string;
}

export interface VramStatus {
  available: boolean;
  gpu: string;
  total_mib: number;
  used_mib: number;
  free_mib: number;
}

export interface BackendInfo {
  running: boolean;
  port: number;
  pid: number;
  base_url: string;
  live_captions_supported: boolean;
  read_selection_supported: boolean;
}

export interface WorkerInfo {
  family: "qwen" | "stt" | "xtts" | "f5" | "fish" | "kitten" | "crispasr" | string;
  venv_ready: boolean;
  script_ready: boolean;
  running: boolean;
  pid: number | null;
  port: number | null;
  model_id: string | null;
  device: DeviceMode | null;
  vram_est_mib: number;
  started_at: number | null;
}

export interface WorkersSnapshot {
  workers: Record<string, WorkerInfo>;
  live_captions_active: boolean;
}

export interface VoiceProfile {
  id: string;
  name: string;
  language: string;
  engine: EngineKind;
  ref_audio_path: string;
  ref_24k_path?: string;
  ref_original_path?: string;
  ref_duration_s?: number;
  ref_trimmed?: boolean;
  ref_text: string;
  ref_original_text?: string;
  spk_path: string;
  rvq_path: string;
  ready: boolean;
  created_at: number;
  updated_at: number;
}

export interface GenerationRecord {
  id: string;
  profile_id: string;
  profile_name: string;
  text: string;
  language: string;
  file_path: string;
  saved_path: string;
  duration_s: number;
  sr: number;
  elapsed_s: number;
  rtf: number;
  created_at: number;
}

export interface SynthesizeResponse {
  mode: "play" | "wav";
  audio_url: string;
  record?: GenerationRecord;
  duration_s?: number;
  sr?: number;
  elapsed_s?: number;
  rtf?: number;
}

export interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
}

export interface TranscribeResponse {
  text: string;
  language: string;
  duration_s: number;
  elapsed_s: number;
  segments: TranscriptSegment[];
  source: SourceMode;
  model: string;
}

export interface EndpointTestResponse {
  ok: boolean;
  status_code: number;
  latency_ms: number;
  detail: string;
}

export interface QuantOption {
  id: string;
  label: string;
  disk_mb: number;
  vram_mib: number;
  files: string[];
  compute_type?: string | null;
  recommended: boolean;
}

export type InstallMode = "shared_weights" | "per_language_checkpoint" | "voices_pack";
export type VoiceMode = "clone_profile" | "builtin_voices";
export type QuantPolicy = "gguf" | "checkpoint" | "onnx" | "binary" | "post_quantize";

export interface ModelCapabilities {
  install_mode: InstallMode;
  voice_mode: VoiceMode;
  quant_policy: QuantPolicy;
  languages: string[];
}

export interface CatalogModelEntry {
  id: string;
  name: string;
  kind: "tts" | "stt";
  engine: string;
  family_id: string;
  family_name: string;
  variant_label: string;
  repo_id: string;
  description: string;
  runtime_supported: boolean;
  available_runtimes?: string[];
  active_runtime?: string;
  capabilities: ModelCapabilities;
  quants: QuantOption[];
  installed: boolean;
  installed_quant: string | null;
  installed_quants: string[];
  install_dir: string | null;
  external: boolean;
  removable: boolean;
  custom: boolean;
  disk_mb: number;
  vram_mib: number;
}

export interface DownloadJob {
  job_id: string;
  model_id: string;
  name: string;
  kind: "tts" | "stt";
  quant: string;
  status: "queued" | "downloading" | "completed" | "failed" | "cancelled";
  progress: number;
  downloaded_bytes: number;
  total_bytes: number;
  current_file: string;
  error: string;
  started_at: number;
}

export interface ModelsCatalogResponse {
  models: CatalogModelEntry[];
  downloads: DownloadJob[];
  models_dir: string;
}

export interface HfInspectFile {
  filename: string;
  size_bytes: number;
  size_mb: number;
  recommended: boolean;
  download_url?: string | null;
}

export interface HfInspectResponse {
  source: "huggingface" | "modelscope" | "direct";
  repo_id: string;
  suggested_name: string;
  suggested_kind: "tts" | "stt";
  files: HfInspectFile[];
  crispasr_ready?: boolean;
  crispasr_backend?: string | null;
  crispasr_reason?: string;
  can_convert_gguf?: boolean;
  convert_script?: string | null;
}

export interface HubModelSummary {
  repo_id: string;
  name: string;
  author: string;
  downloads: number;
  likes: number;
  tags: string[];
  pipeline_tag: string;
  crispasr_ready?: boolean;
  crispasr_backend?: string | null;
  crispasr_reason?: string;
}

export interface HubSearchResponse {
  kind: "tts" | "stt";
  query: string;
  page: number;
  page_size: number;
  has_more: boolean;
  items: HubModelSummary[];
}

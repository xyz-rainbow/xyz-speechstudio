import type { TabId, VoiceProfile } from "./index.ts";

export type AppTabId = TabId | "persona";

export type PersonaOrigin = "prebuilt" | "shared";
export type PersonaSourceMode = "local_preview" | "remote_k3s";
export type PersonaLicenseKind =
  | "cc0"
  | "cc-by-4.0"
  | "personal-non-commercial"
  | "proprietary-pack"
  | "custom";
export type PersonaProvenanceType =
  | "self_recorded"
  | "authorized_actor"
  | "synthetic_reference"
  | "pack_reference";

export interface PersonaConsentRecord {
  speaker_consent_confirmed: boolean;
  provenance_type: PersonaProvenanceType;
  provenance_note: string;
  license: PersonaLicenseKind;
  attribution: string;
}

export interface PersonaAudioSpec {
  format: "wav" | "mp3" | "flac" | "ogg" | "m4a";
  sample_rate_hz: number;
  channels: number;
  duration_s: number;
  sha256?: string;
  size_bytes?: number;
  preview_url?: string;
  download_url?: string;
  local_path?: string;
}

export interface PersonaRecord {
  id: string;
  slug: string;
  version: string;
  name: string;
  language: string;
  locale: string;
  origin: PersonaOrigin;
  description: string;
  author: string;
  tags: string[];
  ref_text: string;
  audio: PersonaAudioSpec;
  consent: PersonaConsentRecord;
  recommended_engines: string[];
  created_at: string;
  updated_at: string;
}

export interface PersonaConfig {
  source_mode: PersonaSourceMode;
  library_url: string;
  auth_token_header?: string;
}

export interface PersonaQuery {
  search?: string;
  language?: string;
  origin?: PersonaOrigin | "all";
}

export interface PersonaCatalogResponse {
  source_mode: PersonaSourceMode;
  server_url: string | null;
  api_version: string;
  items: PersonaRecord[];
  total: number;
  warning?: string;
}

export interface PersonaHealthResult {
  ok: boolean;
  status: number | null;
  api_version?: string;
  detail: string;
  checked_url: string;
}

export interface PersonaPublishDraft {
  name: string;
  language: string;
  locale: string;
  description: string;
  ref_audio_path: string;
  ref_text: string;
  tags: string[];
  provenance_type: PersonaProvenanceType;
  provenance_note: string;
  license: PersonaLicenseKind;
  attribution: string;
  speaker_consent_confirmed: boolean;
  source_profile_id?: string;
}

export interface PersonaLocalDraft extends PersonaPublishDraft {
  draft_id: string;
  status: "local_draft_only";
  created_at: string;
  api_payload_preview: Record<string, unknown>;
}

export interface PersonaPublishValidation {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

export interface PersonaInstallRecord {
  persona_id: string;
  version: string;
  mode: "profile" | "preview_cache";
  profile_id?: string;
  installed_at: string;
}

export type EngineCloningStatus =
  | "compatible"
  | "needs_conversion"
  | "unsupported_no_cloning"
  | "unknown";

export interface EngineAudioRequirement {
  engine: string;
  label: string;
  supports_cloning: boolean;
  target_sample_rate_hz: number | null;
  target_channels: number | null;
  max_duration_s: number | null;
  recommended_duration_s: [number, number] | null;
  ref_text_requirement: "required" | "recommended" | "optional" | "none";
  notes: string;
}

export interface EngineCompatibilityEvaluation {
  engine: string;
  model_id?: string;
  label: string;
  installed: boolean;
  supports_cloning: boolean;
  status: EngineCloningStatus;
  requirement: EngineAudioRequirement;
  conversions_needed: string[];
  warnings: string[];
}

export interface PersonaRemoteInstallRequest {
  persona_id: string;
  name: string;
  language: string;
  engine: string;
  ref_text: string;
  library_url: string;
  download_url: string;
  sha256: string;
  audio_format: PersonaAudioSpec["format"];
  expected_size_bytes?: number;
  auth_header?: string;
}

export interface PersonaRemoteInstallResponse {
  profile: VoiceProfile;
  persona_id: string;
  sha256: string;
  size_bytes: number;
  audio_format: string;
  name_disambiguated: boolean;
  original_name: string;
}

export interface PersonaInstallProgress {
  phase:
    | "idle"
    | "validating"
    | "downloading"
    | "verifying"
    | "creating_profile"
    | "done"
    | "failed";
  persona_id: string;
  downloaded: number;
  total: number;
  error_code?: string | null;
}

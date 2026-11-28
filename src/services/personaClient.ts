import type { VoiceProfile } from "../types/index.ts";
import type {
  PersonaCatalogResponse,
  PersonaConfig,
  PersonaHealthResult,
  PersonaInstallProgress,
  PersonaLocalDraft,
  PersonaPublishDraft,
  PersonaPublishValidation,
  PersonaQuery,
  PersonaRecord,
  PersonaRemoteInstallRequest,
  PersonaRemoteInstallResponse,
  PersonaSourceMode,
} from "../types/persona.ts";

export const PERSONA_API_VERSION = "v1";
export const PERSONA_CONFIG_STORAGE_KEY = "speechstudio.persona.config.v1";
export const PERSONA_DRAFTS_STORAGE_KEY = "speechstudio.persona.drafts.v1";

export const DEFAULT_PERSONA_CONFIG: PersonaConfig = {
  source_mode: "local_preview",
  library_url: "",
};

export type PersonaClientErrorCode =
  | "UNCONFIGURED_URL"
  | "INVALID_URL"
  | "UNREACHABLE_SERVER"
  | "HTTP_ERROR"
  | "INVALID_RESPONSE"
  | "AUTH_REQUIRED"
  | "BACKEND_REQUIRED";

export class PersonaClientError extends Error {
  code: PersonaClientErrorCode;
  status?: number;
  backendCode?: string;

  constructor(
    code: PersonaClientErrorCode,
    message: string,
    status?: number,
    backendCode?: string
  ) {
    super(message);
    this.name = "PersonaClientError";
    this.code = code;
    this.status = status;
    this.backendCode = backendCode;
  }
}

/**
 * Local preview fixtures used while no k3s/Rancher Persona service is deployed.
 * Audio paths are explicitly synthetic/unset so the UI never fakes a download or live upload.
 */
export const LOCAL_PREVIEW_PERSONAS: PersonaRecord[] = [
  {
    id: "preview-es-narrator-01",
    slug: "alvaro-castellano-preview",
    version: "1.0.0",
    name: "Álvaro (Preview)",
    language: "Spanish",
    locale: "es-ES",
    origin: "prebuilt",
    description:
      "Clear Iberian Spanish narrative reference formatted at 24 kHz mono WAV for zero-shot Qwen3-TTS and F5 cloning.",
    author: "Rainbow Voice Pack (Preview)",
    tags: ["narrative", "clear", "es-ES", "preview"],
    ref_text:
      "Hola, hoy vamos a comprobar que la configuración de audio y perfiles funciona correctamente antes de exportar el resultado.",
    audio: {
      format: "wav",
      sample_rate_hz: 24000,
      channels: 1,
      duration_s: 8.6,
      size_bytes: 412844,
    },
    consent: {
      speaker_consent_confirmed: true,
      provenance_type: "synthetic_reference",
      provenance_note: "Local preview metadata fixture representing a verified prebuilt pack entry.",
      license: "proprietary-pack",
      attribution: "Speech Studio Preview Fixture",
    },
    recommended_engines: ["qwen", "f5", "chatterbox", "xtts"],
    created_at: "2026-11-28T00:00:00Z",
    updated_at: "2026-11-28T00:00:00Z",
  },
  {
    id: "preview-en-studio-01",
    slug: "claire-studio-en-preview",
    version: "1.0.0",
    name: "Claire Studio (Preview)",
    language: "English",
    locale: "en-US",
    origin: "prebuilt",
    description:
      "Neutral North American presenter tone suited for tutorials, documentation voiceovers, and crisp short-form synthesis.",
    author: "Rainbow Voice Pack (Preview)",
    tags: ["presenter", "clean", "en-US", "preview"],
    ref_text:
      "Welcome back to the workspace. Next we will verify model selection, sample timing, and local output export.",
    audio: {
      format: "wav",
      sample_rate_hz: 24000,
      channels: 1,
      duration_s: 7.4,
      size_bytes: 355244,
    },
    consent: {
      speaker_consent_confirmed: true,
      provenance_type: "authorized_actor",
      provenance_note: "Local preview metadata fixture (no external media bundled in installer).",
      license: "cc-by-4.0",
      attribution: "Speech Studio Preview Fixture",
    },
    recommended_engines: ["qwen", "chatterbox-turbo", "cosyvoice3-tts", "xtts"],
    created_at: "2026-11-28T00:00:00Z",
    updated_at: "2026-11-28T00:00:00Z",
  },
  {
    id: "preview-es-podcast-shared",
    slug: "mateo-podcast-stereo-mp3",
    version: "0.9.0",
    name: "Mateo Podcast (Preview)",
    language: "Spanish",
    locale: "es-419",
    origin: "shared",
    description:
      "Warm conversational LatAm reference supplied as stereo 44.1 kHz MP3 (16.4s) — demonstrates automatic transcoding, mono downmix, resampling, and <=12s trim for F5.",
    author: "Community Sample (Preview)",
    tags: ["conversational", "podcast", "mp3", "needs-adaptation"],
    ref_text:
      "Qué tal a todos, bienvenidos a una nueva sesión de pruebas. Hoy revisamos micrófonos, ganancia de entrada y exportación en calidad de estudio.",
    audio: {
      format: "mp3",
      sample_rate_hz: 44100,
      channels: 2,
      duration_s: 16.4,
      size_bytes: 263400,
    },
    consent: {
      speaker_consent_confirmed: true,
      provenance_type: "self_recorded",
      provenance_note: "Simulated community upload demonstrating pre-flight audio conversion notices.",
      license: "cc0",
      attribution: "Community Contributor",
    },
    recommended_engines: ["fish", "qwen", "chatterbox"],
    created_at: "2026-11-28T00:00:00Z",
    updated_at: "2026-11-28T00:00:00Z",
  },
  {
    id: "preview-ja-doc-01",
    slug: "ren-doc-ja-preview",
    version: "1.0.0",
    name: "Ren Documentary (Preview)",
    language: "Japanese",
    locale: "ja-JP",
    origin: "prebuilt",
    description:
      "Measured Japanese documentary timbre balanced for Qwen3-TTS and CosyVoice3 multilingual synthesis.",
    author: "Rainbow Voice Pack (Preview)",
    tags: ["documentary", "calm", "ja-JP"],
    ref_text: "こんにちは。これから音声合成の設定と参照クリップの品質を確認します。",
    audio: {
      format: "wav",
      sample_rate_hz: 24000,
      channels: 1,
      duration_s: 6.8,
      size_bytes: 326444,
    },
    consent: {
      speaker_consent_confirmed: true,
      provenance_type: "synthetic_reference",
      provenance_note: "Local preview metadata fixture.",
      license: "personal-non-commercial",
      attribution: "Speech Studio Preview Fixture",
    },
    recommended_engines: ["qwen", "cosyvoice3-tts", "fish"],
    created_at: "2026-11-28T00:00:00Z",
    updated_at: "2026-11-28T00:00:00Z",
  },
  {
    id: "preview-fr-guide-shared",
    slug: "camille-tech-fr-preview",
    version: "1.1.0",
    name: "Camille Guide (Preview)",
    language: "French",
    locale: "fr-FR",
    origin: "shared",
    description:
      "Crisp French explainer voice packaged as 48 kHz mono FLAC — auto-resampled to target engine rate on use.",
    author: "Community Sample (Preview)",
    tags: ["explainer", "tech", "fr-FR", "flac"],
    ref_text:
      "Bonjour et bienvenue dans ce guide rapide pour vérifier le clonage vocal et la préparation audio.",
    audio: {
      format: "flac",
      sample_rate_hz: 48000,
      channels: 1,
      duration_s: 9.2,
      size_bytes: 298110,
    },
    consent: {
      speaker_consent_confirmed: true,
      provenance_type: "self_recorded",
      provenance_note: "Simulated community voice entry with explicit CC-BY attribution.",
      license: "cc-by-4.0",
      attribution: "Camille (Preview)",
    },
    recommended_engines: ["qwen", "xtts", "f5"],
    created_at: "2026-11-28T00:00:00Z",
    updated_at: "2026-11-28T00:00:00Z",
  },
  {
    id: "preview-de-reader-shared",
    slug: "lukas-audiobook-de-preview",
    version: "1.0.0",
    name: "Lukas Reader (Preview)",
    language: "German",
    locale: "de-DE",
    origin: "shared",
    description:
      "Deep German long-form reader clip stored at 22.05 kHz mono WAV — ready for XTTS v2 or resampled cleanly to 24 kHz.",
    author: "Community Sample (Preview)",
    tags: ["audiobook", "deep", "de-DE"],
    ref_text:
      "Guten Tag. Heute testen wir die automatische Anpassung der Abtastrate zwischen verschiedenen Sprachmodellen.",
    audio: {
      format: "wav",
      sample_rate_hz: 22050,
      channels: 1,
      duration_s: 10.1,
      size_bytes: 445454,
    },
    consent: {
      speaker_consent_confirmed: true,
      provenance_type: "authorized_actor",
      provenance_note: "Simulated shared sample illustrating 22.05 kHz -> 24 kHz adaptation.",
      license: "cc-by-4.0",
      attribution: "Lukas (Preview)",
    },
    recommended_engines: ["xtts", "qwen", "f5"],
    created_at: "2026-11-28T00:00:00Z",
    updated_at: "2026-11-28T00:00:00Z",
  },
];

function hasLocalStorage(): boolean {
  try {
    return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
  } catch {
    return false;
  }
}

export function validatePersonaLibraryUrl(raw: string): {
  valid: boolean;
  normalized: string;
  error?: string;
} {
  const trimmed = (raw || "").trim();
  if (!trimmed) {
    return {
      valid: false,
      normalized: "",
      error: "Library URL is empty.",
    };
  }
  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return {
        valid: false,
        normalized: "",
        error: "Library URL must start with http:// or https://.",
      };
    }
    const cleanPath = parsed.pathname.replace(/\/+$/, "");
    const normalized = `${parsed.origin}${cleanPath}`;
    return { valid: true, normalized };
  } catch {
    return {
      valid: false,
      normalized: "",
      error: "Invalid Library URL format.",
    };
  }
}

export function loadPersonaConfig(): PersonaConfig {
  if (!hasLocalStorage()) return { ...DEFAULT_PERSONA_CONFIG };
  try {
    const raw = window.localStorage.getItem(PERSONA_CONFIG_STORAGE_KEY);
    if (!raw) return { ...DEFAULT_PERSONA_CONFIG };
    const parsed = JSON.parse(raw) as Partial<PersonaConfig>;
    return {
      source_mode: parsed.source_mode === "remote_k3s" ? "remote_k3s" : "local_preview",
      library_url: typeof parsed.library_url === "string" ? parsed.library_url : "",
      auth_token_header:
        typeof parsed.auth_token_header === "string" ? parsed.auth_token_header : undefined,
    };
  } catch {
    return { ...DEFAULT_PERSONA_CONFIG };
  }
}

export function savePersonaConfig(config: PersonaConfig): PersonaConfig {
  const normalized: PersonaConfig = {
    source_mode: config.source_mode === "remote_k3s" ? "remote_k3s" : "local_preview",
    library_url: config.library_url.trim().replace(/\/+$/, ""),
    auth_token_header: config.auth_token_header?.trim() || undefined,
  };
  if (hasLocalStorage()) {
    window.localStorage.setItem(PERSONA_CONFIG_STORAGE_KEY, JSON.stringify(normalized));
  }
  return normalized;
}

export function isPersonaDemoOnly(
  persona: PersonaRecord,
  sourceMode?: PersonaSourceMode
): boolean {
  if (persona.audio.local_path && persona.audio.local_path.trim()) {
    return false;
  }
  if (sourceMode !== "local_preview" && persona.audio.download_url && persona.audio.download_url.trim()) {
    return false;
  }
  return true;
}

export function loadLocalDrafts(): PersonaLocalDraft[] {
  if (!hasLocalStorage()) return [];
  try {
    const raw = window.localStorage.getItem(PERSONA_DRAFTS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as PersonaLocalDraft[]) : [];
  } catch {
    return [];
  }
}

export function saveLocalDrafts(drafts: PersonaLocalDraft[]): PersonaLocalDraft[] {
  if (hasLocalStorage()) {
    window.localStorage.setItem(PERSONA_DRAFTS_STORAGE_KEY, JSON.stringify(drafts));
  }
  return drafts;
}

export function filterPersonas(items: PersonaRecord[], query: PersonaQuery = {}): PersonaRecord[] {
  const q = (query.search || "").trim().toLowerCase();
  const lang = (query.language || "").trim().toLowerCase();
  const origin = query.origin && query.origin !== "all" ? query.origin : null;

  return items.filter((item) => {
    if (origin && item.origin !== origin) {
      return false;
    }
    if (lang && lang !== "all") {
      const langMatch =
        item.language.toLowerCase() === lang ||
        item.locale.toLowerCase() === lang ||
        item.locale.toLowerCase().startsWith(`${lang}-`);
      if (!langMatch) return false;
    }
    if (!q) return true;
    const haystack = [
      item.name,
      item.description,
      item.author,
      item.language,
      item.locale,
      item.ref_text,
      ...item.tags,
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(q);
  });
}

function authHeaders(config: PersonaConfig): Record<string, string> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (config.auth_token_header && config.auth_token_header.trim()) {
    headers.Authorization = config.auth_token_header.trim();
  }
  return headers;
}

export async function checkPersonaLibraryHealth(
  config: PersonaConfig,
  fetchImpl: typeof fetch = fetch
): Promise<PersonaHealthResult> {
  if (config.source_mode === "local_preview") {
    return {
      ok: true,
      status: null,
      api_version: PERSONA_API_VERSION,
      detail: "Using local preview fixtures (no remote k3s/Rancher server configured).",
      checked_url: "local://preview",
    };
  }

  const check = validatePersonaLibraryUrl(config.library_url);
  if (!check.valid) {
    throw new PersonaClientError(
      config.library_url.trim() ? "INVALID_URL" : "UNCONFIGURED_URL",
      check.error || "Configure a valid k3s/Rancher Persona Library URL first."
    );
  }

  const checkedUrl = `${check.normalized}/v1/health`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const res = await fetchImpl(checkedUrl, {
      method: "GET",
      headers: authHeaders(config),
      signal: controller.signal,
    });
    const body = await res.json().catch(() => null);
    if (!res.ok) {
      return {
        ok: false,
        status: res.status,
        detail:
          (body && typeof body.detail === "string" && body.detail) ||
          `HTTP ${res.status} from Persona server`,
        checked_url: checkedUrl,
      };
    }
    return {
      ok: true,
      status: res.status,
      api_version:
        body && typeof body.api_version === "string" ? body.api_version : PERSONA_API_VERSION,
      detail:
        (body && typeof body.status === "string" && `Server responded: ${body.status}`) ||
        "Persona library server reachable.",
      checked_url: checkedUrl,
    };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new PersonaClientError(
      "UNREACHABLE_SERVER",
      `Could not reach k3s Persona service at ${checkedUrl}: ${msg}`
    );
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchPersonaCatalog(
  config: PersonaConfig,
  query: PersonaQuery = {},
  fetchImpl: typeof fetch = fetch
): Promise<PersonaCatalogResponse> {
  if (config.source_mode === "local_preview") {
    const items = filterPersonas(LOCAL_PREVIEW_PERSONAS, query);
    return {
      source_mode: "local_preview",
      server_url: null,
      api_version: PERSONA_API_VERSION,
      items,
      total: items.length,
      warning: "preview_mode",
    };
  }

  const check = validatePersonaLibraryUrl(config.library_url);
  if (!check.valid) {
    throw new PersonaClientError(
      config.library_url.trim() ? "INVALID_URL" : "UNCONFIGURED_URL",
      check.error || "Configure a valid k3s/Rancher Persona Library URL first."
    );
  }

  const params = new URLSearchParams();
  if (query.search && query.search.trim()) params.set("q", query.search.trim());
  if (query.language && query.language !== "all") params.set("language", query.language);
  if (query.origin && query.origin !== "all") params.set("origin", query.origin);
  const qs = params.toString();
  const endpoint = `${check.normalized}/v1/personas${qs ? `?${qs}` : ""}`;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  let res: Response;
  try {
    res = await fetchImpl(endpoint, {
      method: "GET",
      headers: authHeaders(config),
      signal: controller.signal,
    });
  } catch (err) {
    clearTimeout(timer);
    const msg = err instanceof Error ? err.message : String(err);
    throw new PersonaClientError(
      "UNREACHABLE_SERVER",
      `Could not reach k3s Persona server (${endpoint}): ${msg}`
    );
  }
  clearTimeout(timer);

  if (res.status === 401 || res.status === 403) {
    throw new PersonaClientError(
      "AUTH_REQUIRED",
      `Authentication required by Persona library (${res.status}).`,
      res.status
    );
  }

  const rawBody = await res.json().catch(() => null);
  if (!res.ok) {
    const detail =
      (rawBody && typeof rawBody.detail === "string" && rawBody.detail) ||
      `HTTP ${res.status} loading Persona catalog`;
    throw new PersonaClientError("HTTP_ERROR", detail, res.status);
  }

  if (!rawBody || !Array.isArray(rawBody.items)) {
    throw new PersonaClientError(
      "INVALID_RESPONSE",
      "Persona server response did not match the v1 catalog contract ({ items: PersonaRecord[] })."
    );
  }

  return {
    source_mode: "remote_k3s",
    server_url: check.normalized,
    api_version:
      typeof rawBody.api_version === "string" ? rawBody.api_version : PERSONA_API_VERSION,
    items: filterPersonas(rawBody.items as PersonaRecord[], query),
    total: typeof rawBody.total === "number" ? rawBody.total : rawBody.items.length,
  };
}

export function validatePublishDraft(draft: PersonaPublishDraft): PersonaPublishValidation {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!draft.name.trim()) {
    errors.push("missing_name");
  }
  if (!draft.language.trim()) {
    errors.push("missing_language");
  }
  if (!draft.description.trim()) {
    errors.push("missing_description");
  } else if (draft.description.trim().length < 12) {
    warnings.push("short_description");
  }
  if (!draft.ref_audio_path.trim()) {
    errors.push("missing_audio");
  }
  if (!draft.ref_text.trim()) {
    errors.push("missing_ref_text");
  }
  if (!draft.speaker_consent_confirmed) {
    errors.push("missing_consent");
  }
  if (!draft.provenance_note.trim()) {
    warnings.push("missing_provenance_note");
  }
  if (!draft.attribution.trim()) {
    warnings.push("missing_attribution");
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
  };
}

export function buildPublishApiPayload(draft: PersonaPublishDraft): Record<string, unknown> {
  const ext = draft.ref_audio_path.trim().split(".").pop()?.toLowerCase() || "wav";
  const format = ["wav", "mp3", "flac", "ogg", "m4a"].includes(ext) ? ext : "wav";
  return {
    api_version: PERSONA_API_VERSION,
    name: draft.name.trim(),
    language: draft.language.trim(),
    locale: draft.locale.trim() || draft.language.trim(),
    description: draft.description.trim(),
    tags: draft.tags.map((tag) => tag.trim()).filter(Boolean),
    ref_text: draft.ref_text.trim(),
    audio: {
      filename: draft.ref_audio_path.split(/[\\/]/).pop() || `reference.${format}`,
      format,
      upload_pending_backend: true,
    },
    consent: {
      speaker_consent_confirmed: draft.speaker_consent_confirmed,
      provenance_type: draft.provenance_type,
      provenance_note: draft.provenance_note.trim(),
      license: draft.license,
      attribution: draft.attribution.trim(),
    },
  };
}

export function createLocalPublishDraft(draft: PersonaPublishDraft): PersonaLocalDraft {
  return {
    ...draft,
    draft_id: `draft-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    status: "local_draft_only",
    created_at: new Date().toISOString(),
    api_payload_preview: buildPublishApiPayload(draft),
  };
}

export function resolvePersonaInstallStatus(
  persona: PersonaRecord,
  localProfiles: VoiceProfile[]
): { installed: boolean; mode: "profile" | null; profileId?: string } {
  const idLower = persona.id.toLowerCase();
  const slugLower = persona.slug.toLowerCase();
  const nameLower = persona.name.toLowerCase();
  const direct = localProfiles.find(
    (p) =>
      p.id.toLowerCase() === idLower ||
      p.id.toLowerCase() === slugLower ||
      p.name.toLowerCase() === nameLower ||
      p.name.toLowerCase().startsWith(`${nameLower} (persona`)
  );
  if (direct) {
    return { installed: true, mode: "profile", profileId: direct.id };
  }
  return { installed: false, mode: null };
}

export async function installRemotePersona(
  baseUrl: string,
  payload: PersonaRemoteInstallRequest,
  fetchImpl: typeof fetch = fetch
): Promise<PersonaRemoteInstallResponse> {
  const cleanBase = baseUrl.trim().replace(/\/+$/, "");
  if (!cleanBase) {
    throw new PersonaClientError(
      "BACKEND_REQUIRED",
      "Local backend orchestrator URL is missing."
    );
  }

  let res: Response;
  try {
    res = await fetchImpl(`${cleanBase}/api/persona/install-remote`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(payload),
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new PersonaClientError(
      "UNREACHABLE_SERVER",
      `Could not reach local Speech Studio orchestrator: ${msg}`
    );
  }

  const body = await res.json().catch(() => null);
  if (res.status === 404 || res.status === 501) {
    const detail =
      (body && typeof body.detail === "string" && body.detail) ||
      "Local backend route /api/persona/install-remote is not wired yet.";
    throw new PersonaClientError("BACKEND_REQUIRED", detail, res.status, "backend_required");
  }

  if (!res.ok) {
    const backendCode =
      body && typeof body.code === "string" ? body.code : undefined;
    const detail =
      (body && typeof body.detail === "string" && body.detail) ||
      `HTTP ${res.status} installing remote Persona`;
    const mappedCode: PersonaClientError["code"] =
      res.status === 401 || res.status === 403 || backendCode === "auth_required"
        ? "AUTH_REQUIRED"
        : backendCode === "disallowed_url" || backendCode === "invalid_library_url"
        ? "INVALID_URL"
        : "HTTP_ERROR";
    throw new PersonaClientError(mappedCode, detail, res.status, backendCode);
  }

  if (!body || typeof body !== "object" || !body.profile) {
    throw new PersonaClientError(
      "INVALID_RESPONSE",
      "Invalid response from /api/persona/install-remote (missing profile)."
    );
  }
  return body as PersonaRemoteInstallResponse;
}

export async function fetchPersonaInstallProgress(
  baseUrl: string,
  fetchImpl: typeof fetch = fetch
): Promise<PersonaInstallProgress | null> {
  const cleanBase = baseUrl.trim().replace(/\/+$/, "");
  if (!cleanBase) return null;
  try {
    const res = await fetchImpl(`${cleanBase}/api/persona/install-progress`, {
      method: "GET",
      headers: { Accept: "application/json" },
    });
    if (!res.ok) return null;
    const data = await res.json().catch(() => null);
    if (!data || typeof data.phase !== "string") return null;
    return data as PersonaInstallProgress;
  } catch {
    return null;
  }
}

export async function switchProfileEngine(
  baseUrl: string,
  profileId: string,
  engine: string,
  preserveOriginal = true,
  fetchImpl: typeof fetch = fetch
): Promise<VoiceProfile> {
  const cleanBase = baseUrl.trim().replace(/\/+$/, "");
  if (!cleanBase) {
    throw new PersonaClientError(
      "BACKEND_REQUIRED",
      "Local backend orchestrator URL is missing."
    );
  }
  const res = await fetchImpl(
    `${cleanBase}/api/profiles/${encodeURIComponent(profileId)}/switch-engine`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ engine, preserve_original: preserveOriginal }),
    }
  );
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const detail =
      (body && typeof body.detail === "string" && body.detail) ||
      `HTTP ${res.status} switching profile engine`;
    throw new PersonaClientError("HTTP_ERROR", detail, res.status);
  }
  if (!body || !body.profile) {
    throw new PersonaClientError(
      "INVALID_RESPONSE",
      "Invalid response switching profile engine."
    );
  }
  return body.profile as VoiceProfile;
}

export async function fetchLocalBackendPersonas(
  baseUrl: string,
  fetchImpl: typeof fetch = fetch
): Promise<PersonaRecord[]> {
  const cleanBase = baseUrl.trim().replace(/\/+$/, "");
  if (!cleanBase) return [];
  const res = await fetchImpl(`${cleanBase}/api/persona/local-catalog`, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) return [];
  const body = (await res.json().catch(() => null)) as { items?: unknown } | null;
  if (!body || !Array.isArray(body.items)) return [];
  return body.items.filter(
    (x): x is PersonaRecord =>
      Boolean(x && typeof x === "object" && typeof (x as PersonaRecord).id === "string" && (x as PersonaRecord).audio)
  );
}


export async function restoreProfileOriginalAudio(
  baseUrl: string,
  profileId: string,
  fetchImpl: typeof fetch = fetch
): Promise<VoiceProfile> {
  const cleanBase = baseUrl.trim().replace(/\/+$/, "");
  if (!cleanBase) {
    throw new PersonaClientError(
      "BACKEND_REQUIRED",
      "Local backend orchestrator URL is missing."
    );
  }
  const res = await fetchImpl(
    `${cleanBase}/api/profiles/${encodeURIComponent(profileId)}/restore-original`,
    {
      method: "POST",
      headers: { Accept: "application/json" },
    }
  );
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const detail =
      (body && typeof body.detail === "string" && body.detail) ||
      `HTTP ${res.status} restoring original profile audio`;
    throw new PersonaClientError("HTTP_ERROR", detail, res.status);
  }
  if (!body || !body.profile) {
    throw new PersonaClientError(
      "INVALID_RESPONSE",
      "Invalid response restoring original profile audio."
    );
  }
  return body.profile as VoiceProfile;
}

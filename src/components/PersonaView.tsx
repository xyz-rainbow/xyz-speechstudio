import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Compass,
  Copy,
  Download,
  FileAudio,
  Globe,
  Info,
  Loader2,
  Pause,
  Play,
  RefreshCw,
  Search,
  Server,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
  UploadCloud,
  X,
  XCircle,
} from "lucide-react";
import { clsx } from "clsx";
import { useI18n } from "../i18n";
import { createProfile, getPreviewAudioUrl, notify } from "../services/api";
import { pickFile } from "../services/fileDialog";
import {
  buildPublishApiPayload,
  checkPersonaLibraryHealth,
  createLocalPublishDraft,
  DEFAULT_PERSONA_CONFIG,
  fetchLocalBackendPersonas,
  fetchPersonaCatalog,
  fetchPersonaInstallProgress,
  installRemotePersona,
  isPersonaDemoOnly,
  loadLocalDrafts,
  loadPersonaConfig,
  PersonaClientError,
  resolvePersonaInstallStatus,
  saveLocalDrafts,
  savePersonaConfig,
  validatePersonaLibraryUrl,
  validatePublishDraft,
} from "../services/personaClient";
import type { AppSettings, CatalogModelEntry, EngineKind, VoiceProfile } from "../types";
import type {
  EngineCompatibilityEvaluation,
  PersonaConfig,
  PersonaHealthResult,
  PersonaInstallProgress,
  PersonaLicenseKind,
  PersonaLocalDraft,
  PersonaOrigin,
  PersonaProvenanceType,
  PersonaPublishDraft,
  PersonaRecord,
} from "../types/persona";
import { evaluatePersonaAgainstCatalog } from "../utils/personaCompatibility";
import { BorderBeamButton } from "./BorderBeamButton";
import { GlassCard } from "./GlassCard";

interface PersonaViewProps {
  baseUrl: string;
  catalog: CatalogModelEntry[];
  settings: AppSettings;
  profiles: VoiceProfile[];
  onProfilesChange: (next: VoiceProfile[]) => void;
  onUseProfile: (id: string) => void;
  initialPublishProfile?: VoiceProfile | null;
  onConsumeInitialPublishProfile?: () => void;
  notificationsEnabled: boolean;
}

const EMPTY_PUBLISH_DRAFT: PersonaPublishDraft = {
  name: "",
  language: "Spanish",
  locale: "es-ES",
  description: "",
  ref_audio_path: "",
  ref_text: "",
  tags: [],
  provenance_type: "self_recorded",
  provenance_note: "",
  license: "cc-by-4.0",
  attribution: "",
  speaker_consent_confirmed: false,
};

function toEngineKind(engine: string): EngineKind {
  const valid: EngineKind[] = [
    "qwen",
    "xtts",
    "f5",
    "fish",
    "chatterbox",
    "chatterbox-turbo",
    "cosyvoice3-tts",
    "orpheus",
    "indextts",
  ];
  return (valid.includes(engine as EngineKind) ? engine : "qwen") as EngineKind;
}

function statusPillColors(ev: EngineCompatibilityEvaluation | null) {
  if (!ev) {
    return {
      borderColor: "var(--border-glass)",
      color: "var(--text-secondary)",
      bg: "rgba(148, 163, 184, 0.08)",
    };
  }
  if (ev.status === "compatible") {
    return {
      borderColor: "rgba(16, 185, 129, 0.45)",
      color: "#34d399",
      bg: "rgba(16, 185, 129, 0.12)",
    };
  }
  if (ev.status === "needs_conversion") {
    return {
      borderColor: "rgba(245, 158, 11, 0.45)",
      color: "#fbbf24",
      bg: "rgba(245, 158, 11, 0.12)",
    };
  }
  return {
    borderColor: "rgba(244, 63, 94, 0.45)",
    color: "#fda4af",
    bg: "rgba(244, 63, 94, 0.12)",
  };
}

export const PersonaView: React.FC<PersonaViewProps> = ({
  baseUrl,
  catalog,
  settings,
  profiles,
  onProfilesChange,
  onUseProfile,
  initialPublishProfile,
  onConsumeInitialPublishProfile,
  notificationsEnabled,
}) => {
  const { t } = useI18n();

  const [config, setConfig] = useState<PersonaConfig>(() => loadPersonaConfig());
  const [urlDraft, setUrlDraft] = useState(config.library_url);
  const [modeDraft, setModeDraft] = useState(config.source_mode);
  const [authDraft, setAuthDraft] = useState(config.auth_token_header || "");
  const [configOpen, setConfigOpen] = useState(false);
  const [healthResult, setHealthResult] = useState<PersonaHealthResult | null>(null);
  const [testingHealth, setTestingHealth] = useState(false);

  const [search, setSearch] = useState("");
  const [languageFilter, setLanguageFilter] = useState("all");
  const [originFilter, setOriginFilter] = useState<PersonaOrigin | "all">("all");

  const [items, setItems] = useState<PersonaRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sourceWarning, setSourceWarning] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [installingId, setInstallingId] = useState<string | null>(null);
  const [installProgress, setInstallProgress] = useState<PersonaInstallProgress | null>(null);
  const [detailPersona, setDetailPersona] = useState<PersonaRecord | null>(null);

  const [publishOpen, setPublishOpen] = useState(false);
  const [publishDraft, setPublishDraft] = useState<PersonaPublishDraft>(EMPTY_PUBLISH_DRAFT);
  const [tagsInput, setTagsInput] = useState("");
  const [localDrafts, setLocalDrafts] = useState<PersonaLocalDraft[]>(() => loadLocalDrafts());
  const [publishFeedback, setPublishFeedback] = useState<string | null>(null);
  const [copiedPayload, setCopiedPayload] = useState(false);

  const [previewPlaying, setPreviewPlaying] = useState(false);
  const previewAudioRef = useRef<HTMLAudioElement | null>(null);
  const [playingCardId, setPlayingCardId] = useState<string | null>(null);
  const cardAudioRef = useRef<HTMLAudioElement | null>(null);

  const loadCatalog = useCallback(async (activeConfig: PersonaConfig) => {
    setLoading(true);
    setError(null);
    try {
      if (activeConfig.source_mode === "local_preview" && baseUrl) {
        const localItems = await fetchLocalBackendPersonas(baseUrl).catch(() => []);
        if (localItems.length > 0) {
          setItems(localItems);
          setSourceWarning("local_pack");
          return;
        }
      }
      const res = await fetchPersonaCatalog(activeConfig);
      setItems(res.items);
      setSourceWarning(res.warning || null);
    } catch (err) {
      if (err instanceof PersonaClientError) {
        setError(err.message);
      } else {
        setError(err instanceof Error ? err.message : String(err));
      }
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [baseUrl]);

  useEffect(() => {
    void loadCatalog(config);
  }, [config, loadCatalog]);

  useEffect(() => {
    return () => {
      previewAudioRef.current?.pause();
      cardAudioRef.current?.pause();
    };
  }, []);

  const toggleCardPreview = (persona: PersonaRecord) => {
    if (playingCardId === persona.id && cardAudioRef.current) {
      cardAudioRef.current.pause();
      cardAudioRef.current = null;
      setPlayingCardId(null);
      return;
    }
    cardAudioRef.current?.pause();
    if (!baseUrl) return;
    const url = persona.audio.preview_url
      ? `${baseUrl.replace(/\/$/, "")}${persona.audio.preview_url}`
      : persona.audio.local_path
        ? getPreviewAudioUrl(baseUrl, persona.audio.local_path)
        : "";
    if (!url) return;
    const audio = new Audio(url);
    cardAudioRef.current = audio;
    setPlayingCardId(persona.id);
    audio.onended = () => setPlayingCardId(null);
    audio.onerror = () => setPlayingCardId(null);
    audio.play().catch(() => setPlayingCardId(null));
  };

  const prefillFromVoiceProfile = useCallback((profile: VoiceProfile) => {
    setPublishDraft({
      name: profile.name,
      language: profile.language || "Spanish",
      locale: profile.language?.toLowerCase().startsWith("en") ? "en-US" : "es-ES",
      description: "",
      ref_audio_path: profile.ref_original_path || profile.ref_audio_path || "",
      ref_text: profile.ref_text || "",
      tags: [profile.engine, profile.language.toLowerCase()],
      provenance_type: "self_recorded",
      provenance_note: "",
      license: "personal-non-commercial",
      attribution: profile.name,
      speaker_consent_confirmed: false,
      source_profile_id: profile.id,
    });
    setTagsInput([profile.engine, profile.language].filter(Boolean).join(", "));
    setPublishFeedback(null);
  }, []);

  useEffect(() => {
    if (!initialPublishProfile) return;
    prefillFromVoiceProfile(initialPublishProfile);
    setPublishOpen(true);
    onConsumeInitialPublishProfile?.();
  }, [initialPublishProfile, onConsumeInitialPublishProfile, prefillFromVoiceProfile]);

  const availableLanguages = useMemo(() => {
    const langs = new Set<string>();
    for (const item of items) {
      if (item.language) langs.add(item.language);
    }
    return Array.from(langs).sort((a, b) => a.localeCompare(b));
  }, [items]);

  const filteredItems = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((item) => {
      if (originFilter !== "all" && item.origin !== originFilter) return false;
      if (languageFilter !== "all" && item.language.toLowerCase() !== languageFilter.toLowerCase()) {
        return false;
      }
      if (!q) return true;
      const hay = [
        item.name,
        item.description,
        item.author,
        item.language,
        item.locale,
        ...item.tags,
      ]
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [items, search, languageFilter, originFilter]);

  const mapInstallError = useCallback(
    (err: unknown): string => {
      if (err instanceof PersonaClientError) {
        if (err.code === "BACKEND_REQUIRED" || err.backendCode === "backend_required") {
          return t("persona.errRouteNotWired");
        }
        switch (err.backendCode) {
          case "sha256_mismatch":
          case "invalid_sha256":
            return t("persona.errSha256Mismatch");
          case "truncated_response":
            return t("persona.errTruncated");
          case "disallowed_url":
          case "invalid_library_url":
            return t("persona.errDisallowedUrl");
          case "file_too_large":
            return t("persona.errFileTooLarge");
          case "unsupported_audio_format":
            return t("persona.errUnsupportedAudio");
          case "busy":
            return t("persona.errBusy");
          case "auth_required":
            return t("persona.errAuthRequired");
          default:
            return err.message;
        }
      }
      return err instanceof Error ? err.message : String(err);
    },
    [t]
  );

  const handleSaveSourceConfig = () => {
    if (modeDraft === "remote_k3s") {
      const check = validatePersonaLibraryUrl(urlDraft);
      if (!check.valid) {
        setError(check.error || t("persona.invalidUrl"));
        return;
      }
      const saved = savePersonaConfig({
        source_mode: "remote_k3s",
        library_url: check.normalized,
        auth_token_header: authDraft.trim() || undefined,
      });
      setConfig(saved);
      setUrlDraft(saved.library_url);
      setHealthResult(null);
      setNotice(null);
      return;
    }
    const saved = savePersonaConfig({
      source_mode: "local_preview",
      library_url: urlDraft.trim(),
      auth_token_header: authDraft.trim() || undefined,
    });
    setConfig(saved);
    setHealthResult(null);
    setNotice(null);
  };

  const handleResetToPreview = () => {
    const saved = savePersonaConfig({
      ...DEFAULT_PERSONA_CONFIG,
      library_url: urlDraft.trim(),
    });
    setModeDraft("local_preview");
    setConfig(saved);
    setError(null);
    setHealthResult(null);
  };

  const handleTestHealth = async () => {
    setTestingHealth(true);
    setHealthResult(null);
    try {
      const candidate: PersonaConfig = {
        source_mode: modeDraft,
        library_url: urlDraft.trim(),
        auth_token_header: authDraft.trim() || undefined,
      };
      const res = await checkPersonaLibraryHealth(candidate);
      setHealthResult(res);
    } catch (err) {
      setHealthResult({
        ok: false,
        status: null,
        detail: err instanceof Error ? err.message : String(err),
        checked_url: urlDraft.trim() || "local://preview",
      });
    } finally {
      setTestingHealth(false);
    }
  };

  const handleInstallPersona = async (
    persona: PersonaRecord,
    attachLocalAudio = false
  ) => {
    setInstallingId(persona.id);
    setError(null);
    setNotice(null);

    const evalSummary = evaluatePersonaAgainstCatalog(
      persona,
      catalog,
      settings.active_tts_model
    );
    const installedClone = evalSummary.compatible.find((ev) => ev.installed);

    if (!baseUrl) {
      setError(t("persona.backendUnavailable"));
      setInstallingId(null);
      return;
    }

    if (!installedClone) {
      setNotice(t("persona.noInstalledCloneEngine"));
      setInstallingId(null);
      return;
    }

    try {
      if (attachLocalAudio || persona.audio.local_path) {
        let chosenPath = persona.audio.local_path || "";
        if (attachLocalAudio) {
          const picked = await pickFile({
            title: t("persona.pickReferenceAudio"),
            filters: [{ name: "Audio", extensions: ["wav", "mp3", "m4a", "flac", "ogg"] }],
          });
          if (!picked) return;
          chosenPath = picked;
        }
        const created = await createProfile(baseUrl, {
          name: persona.name,
          language: persona.language || "Spanish",
          engine: toEngineKind(installedClone.engine),
          ref_audio_path: chosenPath,
          ref_text: persona.ref_text,
          build_voice: installedClone.engine === "qwen",
        });
        onProfilesChange([...profiles, created]);
        setNotice(
          t("persona.installedAsProfile")
            .replace("{{name}}", persona.name)
            .replace("{{engine}}", installedClone.engine)
        );
        void notify(notificationsEnabled, t("toast.title"), t("toast.profileSaved"));
        return;
      }

      if (isPersonaDemoOnly(persona, config.source_mode) || !persona.audio.download_url) {
        setNotice(t("persona.demoDetailNotice"));
        return;
      }

      if (!persona.audio.sha256 || !persona.audio.sha256.trim()) {
        setError(t("persona.errMissingSha256"));
        return;
      }

      setInstallProgress({
        phase: "validating",
        persona_id: persona.id,
        downloaded: 0,
        total: persona.audio.size_bytes || 0,
      });

      const pollTimer = window.setInterval(() => {
        void fetchPersonaInstallProgress(baseUrl).then((prog) => {
          if (prog && prog.persona_id === persona.id) {
            setInstallProgress(prog);
          }
        });
      }, 350);

      try {
        const result = await installRemotePersona(baseUrl, {
          persona_id: persona.id,
          name: persona.name,
          language: persona.language || "Spanish",
          engine: installedClone.engine,
          ref_text: persona.ref_text,
          library_url: config.library_url,
          download_url: persona.audio.download_url,
          sha256: persona.audio.sha256,
          audio_format: persona.audio.format,
          expected_size_bytes: persona.audio.size_bytes,
          auth_header: config.auth_token_header,
        });
        onProfilesChange([...profiles, result.profile]);
        setNotice(
          result.name_disambiguated
            ? t("persona.installedDisambiguated")
                .replace("{{name}}", persona.name)
                .replace("{{savedName}}", result.profile.name)
                .replace("{{engine}}", result.profile.engine)
            : t("persona.installedAsProfile")
                .replace("{{name}}", persona.name)
                .replace("{{engine}}", result.profile.engine)
        );
        void notify(notificationsEnabled, t("toast.title"), t("toast.profileSaved"));
      } finally {
        window.clearInterval(pollTimer);
        setInstallProgress(null);
      }
    } catch (err) {
      setError(mapInstallError(err));
      void notify(notificationsEnabled, t("toast.title"), t("toast.failed"));
    } finally {
      setInstallingId(null);
    }
  };

  const publishValidation = useMemo(
    () =>
      validatePublishDraft({
        ...publishDraft,
        tags: tagsInput
          .split(",")
          .map((x) => x.trim())
          .filter(Boolean),
      }),
    [publishDraft, tagsInput]
  );

  const toggleDraftAudioPreview = () => {
    if (previewPlaying && previewAudioRef.current) {
      previewAudioRef.current.pause();
      previewAudioRef.current = null;
      setPreviewPlaying(false);
      return;
    }
    if (!baseUrl || !publishDraft.ref_audio_path.trim()) return;
    const audio = new Audio(getPreviewAudioUrl(baseUrl, publishDraft.ref_audio_path.trim()));
    previewAudioRef.current = audio;
    setPreviewPlaying(true);
    audio.onended = () => setPreviewPlaying(false);
    audio.onerror = () => setPreviewPlaying(false);
    audio.play().catch(() => setPreviewPlaying(false));
  };

  const handleSavePublishDraft = () => {
    const draftWithTags: PersonaPublishDraft = {
      ...publishDraft,
      tags: tagsInput
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean),
    };
    const check = validatePublishDraft(draftWithTags);
    if (!check.valid) {
      setPublishFeedback(
        `${t("persona.publishValidationFailed")}: ${check.errors.join(", ")}`
      );
      return;
    }
    const created = createLocalPublishDraft(draftWithTags);
    const next = [created, ...localDrafts];
    setLocalDrafts(saveLocalDrafts(next));
    setPublishFeedback(t("persona.draftSavedLocally"));
  };

  const handleCopyPayload = async () => {
    const payload = buildPublishApiPayload({
      ...publishDraft,
      tags: tagsInput
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean),
    });
    await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
    setCopiedPayload(true);
    setTimeout(() => setCopiedPayload(false), 1500);
  };

  const handleDeleteLocalDraft = (draftId: string) => {
    const next = localDrafts.filter((d) => d.draft_id !== draftId);
    setLocalDrafts(saveLocalDrafts(next));
  };

  const detailCompat = useMemo(() => {
    if (!detailPersona) return null;
    return evaluatePersonaAgainstCatalog(detailPersona, catalog, settings.active_tts_model);
  }, [detailPersona, catalog, settings.active_tts_model]);

  const renderProgressText = (prog: PersonaInstallProgress) => {
    const pct =
      prog.total > 0 ? ` ${Math.min(100, Math.round((prog.downloaded / prog.total) * 100))}%` : "";
    switch (prog.phase) {
      case "validating":
        return t("persona.phase_validating");
      case "downloading":
        return `${t("persona.phase_downloading")}${pct}`;
      case "verifying":
        return t("persona.phase_verifying");
      case "creating_profile":
        return t("persona.phase_creating_profile");
      default:
        return t("persona.phase_downloading");
    }
  };

  return (
    <div className="flex flex-col gap-2.5 pb-4">
      <GlassCard className="p-3 flex flex-col gap-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <Compass className="w-4 h-4 text-purple-400 shrink-0" />
            <h1 className="text-sm font-semibold">{t("persona.title")}</h1>
            <button
              type="button"
              onClick={() => setConfigOpen((v) => !v)}
              title={t("persona.subtitle")}
              className="rounded-full px-2 py-0.5 text-[10px] font-mono border truncate max-w-[200px] transition-colors hover:brightness-110"
              style={{
                borderColor:
                  config.source_mode === "remote_k3s"
                    ? "rgba(6, 182, 212, 0.45)"
                    : sourceWarning === "local_pack"
                      ? "rgba(16, 185, 129, 0.45)"
                      : "rgba(245, 158, 11, 0.45)",
                color:
                  config.source_mode === "remote_k3s"
                    ? "#67e8f9"
                    : sourceWarning === "local_pack"
                      ? "#6ee7b7"
                      : "#fcd34d",
                backgroundColor:
                  config.source_mode === "remote_k3s"
                    ? "rgba(6, 182, 212, 0.1)"
                    : sourceWarning === "local_pack"
                      ? "rgba(16, 185, 129, 0.1)"
                      : "rgba(245, 158, 11, 0.1)",
              }}
            >
              {config.source_mode === "remote_k3s"
                ? `${t("persona.sourceK3sBadge")}: ${config.library_url || "—"}`
                : sourceWarning === "local_pack"
                  ? t("models.local")
                  : t("persona.sourcePreviewBadge")}
            </button>
          </div>

          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => setConfigOpen((v) => !v)}
              className={clsx(
                "inline-flex items-center gap-1.5 rounded-xl border px-2.5 py-1.5 text-xs font-medium hover:border-cyan-400/50",
                configOpen && "border-cyan-400/50 text-cyan-200"
              )}
              style={{
                borderColor: configOpen ? undefined : "var(--border-glass)",
                backgroundColor: "var(--bg-elevated)",
              }}
            >
              <SlidersHorizontal className="w-3.5 h-3.5" />
              {t("persona.configureSource")}
            </button>
            <button
              type="button"
              disabled={loading}
              title={t("persona.refresh")}
              aria-label={t("persona.refresh")}
              onClick={() => void loadCatalog(config)}
              className="inline-flex items-center justify-center rounded-xl border p-1.5 text-xs hover:border-cyan-400/50 disabled:opacity-50"
              style={{
                borderColor: "var(--border-glass)",
                backgroundColor: "var(--bg-elevated)",
              }}
            >
              <RefreshCw className={clsx("w-3.5 h-3.5", loading && "animate-spin")} />
            </button>
            <button
              type="button"
              onClick={() => setPublishOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-xl border border-purple-400/50 bg-purple-500/15 px-3 py-1.5 text-xs font-medium text-purple-200 hover:bg-purple-500/25"
            >
              <UploadCloud className="w-3.5 h-3.5" />
              {t("persona.shareProfileBtn")}
            </button>
          </div>
        </div>

        {sourceWarning === "preview_mode" && configOpen && (
          <div className="rounded-xl border border-amber-400/30 bg-amber-500/10 px-3 py-1.5 text-[11px] text-amber-200 flex items-center gap-2">
            <Info className="w-3.5 h-3.5 shrink-0 text-amber-300" />
            <span>{t("persona.previewNotice")}</span>
          </div>
        )}

        {configOpen && (
          <div
            className="rounded-2xl border p-3 flex flex-col gap-2.5"
            style={{
              borderColor: "var(--border-glass)",
              backgroundColor: "var(--bg-elevated)",
            }}
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs font-semibold flex items-center gap-1.5">
                <Server className="w-3.5 h-3.5 text-cyan-400" />
                {t("persona.sourceConfigTitle")}
              </span>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => setModeDraft("local_preview")}
                  className={clsx(
                    "rounded-lg border px-2.5 py-1 text-[11px] font-medium",
                    modeDraft === "local_preview"
                      ? "border-amber-400/60 text-amber-200 bg-amber-500/15"
                      : "border-white/10"
                  )}
                >
                  {t("persona.modeLocalPreview")}
                </button>
                <button
                  type="button"
                  onClick={() => setModeDraft("remote_k3s")}
                  className={clsx(
                    "rounded-lg border px-2.5 py-1 text-[11px] font-medium",
                    modeDraft === "remote_k3s"
                      ? "border-cyan-400/60 text-cyan-200 bg-cyan-500/15"
                      : "border-white/10"
                  )}
                >
                  {t("persona.modeRemoteK3s")}
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <div className="flex flex-col gap-1">
                <label className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
                  {t("persona.libraryUrlLabel")}
                </label>
                <input
                  value={urlDraft}
                  onChange={(e) => setUrlDraft(e.target.value)}
                  placeholder="https://persona.k3s.local"
                  className="rounded-xl border px-3 py-1.5 text-xs font-mono outline-none"
                  style={{
                    backgroundColor: "var(--bg-input)",
                    borderColor: "var(--border-glass)",
                  }}
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
                  {t("persona.authHeaderLabel")}
                </label>
                <input
                  value={authDraft}
                  onChange={(e) => setAuthDraft(e.target.value)}
                  placeholder="Bearer ... (optional)"
                  className="rounded-xl border px-3 py-1.5 text-xs font-mono outline-none"
                  style={{
                    backgroundColor: "var(--bg-input)",
                    borderColor: "var(--border-glass)",
                  }}
                />
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={handleSaveSourceConfig}
                className="rounded-xl border border-cyan-400/50 bg-cyan-500/15 px-3 py-1.5 text-xs font-medium text-cyan-200 hover:bg-cyan-500/25"
              >
                {t("persona.saveAndLoad")}
              </button>
              <button
                type="button"
                disabled={testingHealth}
                onClick={() => void handleTestHealth()}
                className="inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium disabled:opacity-50"
                style={{
                  borderColor: "var(--border-glass)",
                  backgroundColor: "var(--bg-input)",
                }}
              >
                {testingHealth && <Loader2 className="w-3 h-3 animate-spin" />}
                {t("persona.testConnection")}
              </button>
              <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                {t("persona.k3sNotDeployedHint")}
              </span>
            </div>

            {healthResult && (
              <div
                className={clsx(
                  "rounded-xl border px-3 py-2 text-[11px]",
                  healthResult.ok
                    ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-200"
                    : "border-rose-400/40 bg-rose-500/10 text-rose-200"
                )}
              >
                {healthResult.detail} ({healthResult.checked_url})
              </div>
            )}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative flex-1 min-w-[200px]">
            <Search
              className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2"
              style={{ color: "var(--text-muted)" }}
            />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("persona.searchPlaceholder")}
              className="w-full rounded-xl border pl-8 pr-8 py-1.5 text-xs outline-none"
              style={{
                backgroundColor: "var(--bg-input)",
                borderColor: "var(--border-glass)",
              }}
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch("")}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 opacity-70 hover:opacity-100"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          <div className="flex items-center gap-1.5">
            <Globe className="w-3.5 h-3.5" style={{ color: "var(--text-secondary)" }} />
            <select
              value={languageFilter}
              onChange={(e) => setLanguageFilter(e.target.value)}
              className="rounded-xl border px-2.5 py-1.5 text-xs outline-none"
              style={{
                backgroundColor: "var(--bg-input)",
                borderColor: "var(--border-glass)",
                color: "var(--text-primary)",
              }}
            >
              <option value="all">{t("persona.allLanguages")}</option>
              {availableLanguages.map((lang) => (
                <option key={lang} value={lang}>
                  {lang}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-1">
            {(["all", "prebuilt", "shared"] as const).map((originOpt) => (
              <button
                key={originOpt}
                type="button"
                onClick={() => setOriginFilter(originOpt)}
                className={clsx(
                  "rounded-xl border px-2.5 py-1.5 text-[11px] font-medium transition-colors",
                  originFilter === originOpt ? "border-purple-400/60" : "border-white/10"
                )}
                style={{
                  backgroundColor:
                    originFilter === originOpt ? "var(--bg-elevated)" : "transparent",
                  color:
                    originFilter === originOpt ? "var(--text-primary)" : "var(--text-secondary)",
                }}
              >
                {t(`persona.origin_${originOpt}`)}
              </button>
            ))}
          </div>
        </div>
      </GlassCard>

      {notice && (
        <div className="rounded-xl border border-cyan-400/40 bg-cyan-500/10 px-3 py-2 text-xs text-cyan-200 flex items-center justify-between gap-2">
          <span>{notice}</span>
          <button type="button" onClick={() => setNotice(null)}>
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {error && (
        <GlassCard className="p-4 border-rose-500/40 bg-rose-500/10 flex flex-col gap-2">
          <div className="flex items-center gap-2 text-xs font-semibold text-rose-300">
            <XCircle className="w-4 h-4 shrink-0" />
            <span>{t("persona.errorTitle")}</span>
          </div>
          <p className="text-xs text-rose-200/90 break-words">{error}</p>
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <button
              type="button"
              onClick={() => void loadCatalog(config)}
              className="rounded-xl border border-rose-400/40 px-3 py-1 text-xs font-medium text-rose-200 hover:bg-rose-500/20"
            >
              {t("persona.retry")}
            </button>
            {config.source_mode === "remote_k3s" && (
              <button
                type="button"
                onClick={handleResetToPreview}
                className="rounded-xl border border-amber-400/40 px-3 py-1 text-xs font-medium text-amber-200 hover:bg-amber-500/20"
              >
                {t("persona.switchToPreview")}
              </button>
            )}
          </div>
        </GlassCard>
      )}

      {loading && (
        <GlassCard className="p-8 flex flex-col items-center justify-center gap-2 text-xs">
          <Loader2 className="w-5 h-5 animate-spin text-cyan-400" />
          <span style={{ color: "var(--text-secondary)" }}>{t("persona.loading")}</span>
        </GlassCard>
      )}

      {!loading && !error && filteredItems.length === 0 && (
        <GlassCard className="p-6 flex flex-col items-center justify-center gap-2 text-center">
          <span className="text-xs font-medium">{t("persona.emptyTitle")}</span>
          <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
            {t("persona.emptyHint")}
          </span>
          {(search || languageFilter !== "all" || originFilter !== "all") && (
            <button
              type="button"
              onClick={() => {
                setSearch("");
                setLanguageFilter("all");
                setOriginFilter("all");
              }}
              className="mt-1 rounded-xl border px-3 py-1 text-xs font-medium"
              style={{
                borderColor: "var(--border-glass)",
                backgroundColor: "var(--bg-elevated)",
              }}
            >
              {t("persona.clearFilters")}
            </button>
          )}
        </GlassCard>
      )}

      {!loading && !error && filteredItems.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {filteredItems.map((persona) => {
            const installStatus = resolvePersonaInstallStatus(persona, profiles);
            const demoOnly = isPersonaDemoOnly(persona, config.source_mode);
            const isInstallingThis = installingId === persona.id;
            const prog =
              isInstallingThis && installProgress?.persona_id === persona.id
                ? installProgress
                : null;
            const compat = evaluatePersonaAgainstCatalog(
              persona,
              catalog,
              settings.active_tts_model
            );
            const activePill = statusPillColors(compat.active);
            const activeStatusText = !compat.active
              ? t("persona.compatCheckDetails")
              : compat.active.status === "compatible"
              ? `${compat.active.label}: ${t("persona.statusCompatible")}`
              : compat.active.status === "needs_conversion"
              ? `${compat.active.label}: ${t("persona.statusNeedsConversion")}`
              : `${compat.active.label}: ${t("persona.statusUnsupported")}`;

            return (
              <GlassCard key={persona.id} className="p-4 flex flex-col gap-2.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-semibold text-sm">{persona.name}</span>
                      <span className="rounded-full px-2 py-0.5 text-[10px] font-mono border border-white/10">
                        {persona.language} · {persona.locale}
                      </span>
                      <span
                        className="rounded-full px-2 py-0.5 text-[10px] font-mono border"
                        style={{
                          borderColor:
                            persona.origin === "prebuilt"
                              ? "rgba(168, 85, 247, 0.45)"
                              : "rgba(6, 182, 212, 0.45)",
                          color: persona.origin === "prebuilt" ? "#d8b4fe" : "#67e8f9",
                        }}
                      >
                        {persona.origin === "prebuilt"
                          ? t("persona.origin_prebuilt")
                          : t("persona.origin_shared")}
                      </span>
                    </div>
                    <div className="text-[11px] mt-0.5" style={{ color: "var(--text-muted)" }}>
                      {persona.author} · v{persona.version} · {persona.audio.format.toUpperCase()}{" "}
                      {(persona.audio.sample_rate_hz / 1000).toFixed(1).replace(/\.0$/, "")} kHz ·{" "}
                      {persona.audio.channels === 1 ? "mono" : `${persona.audio.channels}ch`} ·{" "}
                      {persona.audio.duration_s.toFixed(1)}s
                    </div>
                  </div>

                  {installStatus.installed && installStatus.profileId ? (
                    <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-mono border border-emerald-400/45 text-emerald-300 bg-emerald-500/10 shrink-0">
                      <CheckCircle2 className="w-3 h-3" />
                      {t("persona.installedBadge")}
                    </span>
                  ) : demoOnly ? (
                    <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-mono border border-amber-400/45 text-amber-300 bg-amber-500/10 shrink-0">
                      {t("persona.demoOnlyBadge")}
                    </span>
                  ) : null}
                </div>

                <p className="text-xs line-clamp-2" style={{ color: "var(--text-secondary)" }}>
                  {persona.description}
                </p>

                <div className="flex flex-wrap items-center gap-1.5">
                  <span
                    className="rounded-lg border px-2 py-0.5 text-[10px] font-medium"
                    style={{
                      borderColor: activePill.borderColor,
                      color: activePill.color,
                      backgroundColor: activePill.bg,
                    }}
                  >
                    {activeStatusText}
                  </span>
                  {persona.tags.slice(0, 3).map((tag) => (
                    <span
                      key={tag}
                      className="rounded-lg border border-white/10 px-1.5 py-0.5 text-[10px] font-mono opacity-75"
                    >
                      #{tag}
                    </span>
                  ))}
                </div>

                {prog && (
                  <div className="flex flex-col gap-1">
                    <div className="flex items-center justify-between text-[10px] text-cyan-200 font-mono">
                      <span>{renderProgressText(prog)}</span>
                      {prog.total > 0 && (
                        <span>
                          {(prog.downloaded / 1024).toFixed(0)} / {(prog.total / 1024).toFixed(0)}{" "}
                          KiB
                        </span>
                      )}
                    </div>
                    <div className="h-1.5 w-full rounded-full bg-white/10 overflow-hidden">
                      <div
                        className="h-full bg-cyan-400 transition-all duration-200"
                        style={{
                          width:
                            prog.total > 0
                              ? `${Math.min(100, Math.round((prog.downloaded / prog.total) * 100))}%`
                              : "45%",
                        }}
                      />
                    </div>
                  </div>
                )}

                <div className="flex flex-wrap items-center gap-1.5 mt-auto pt-1">
                  {(persona.audio.preview_url || persona.audio.local_path) && baseUrl && (
                    <button
                      type="button"
                      onClick={() => toggleCardPreview(persona)}
                      title={playingCardId === persona.id ? t("synthesize.stop") : t("synthesize.play")}
                      className="inline-flex items-center gap-1 rounded-xl border px-2 py-1 text-xs font-medium hover:border-purple-400/50"
                      style={{
                        borderColor: playingCardId === persona.id ? "rgba(168, 85, 247, 0.55)" : "var(--border-glass)",
                        backgroundColor: "var(--bg-elevated)",
                      }}
                    >
                      {playingCardId === persona.id ? (
                        <Pause className="w-3 h-3 text-purple-300" />
                      ) : (
                        <Play className="w-3 h-3 text-purple-300" />
                      )}
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => setDetailPersona(persona)}
                    className="rounded-xl border px-2.5 py-1 text-xs font-medium hover:border-cyan-400/50"
                    style={{
                      borderColor: "var(--border-glass)",
                      backgroundColor: "var(--bg-elevated)",
                    }}
                  >
                    {t("persona.detailsBtn")}
                  </button>

                  {installStatus.installed && installStatus.profileId ? (
                    <button
                      type="button"
                      onClick={() => onUseProfile(installStatus.profileId!)}
                      className="rounded-xl border border-emerald-400/45 bg-emerald-500/15 px-2.5 py-1 text-xs font-medium text-emerald-200 hover:bg-emerald-500/25"
                    >
                      {t("profiles.useInStudio")}
                    </button>
                  ) : demoOnly ? (
                    <button
                      type="button"
                      disabled
                      title={t("persona.demoDetailNotice")}
                      className="inline-flex items-center gap-1 rounded-xl border border-amber-400/35 bg-amber-500/10 px-2.5 py-1 text-xs font-medium text-amber-200/80 opacity-75 cursor-not-allowed"
                    >
                      {t("persona.demoNoAudioBtn")}
                    </button>
                  ) : (
                    <button
                      type="button"
                      disabled={isInstallingThis || !baseUrl}
                      onClick={() => void handleInstallPersona(persona, false)}
                      className="inline-flex items-center gap-1 rounded-xl border border-cyan-400/45 bg-cyan-500/15 px-2.5 py-1 text-xs font-medium text-cyan-200 hover:bg-cyan-500/25 disabled:opacity-50"
                    >
                      {isInstallingThis ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <Download className="w-3 h-3" />
                      )}
                      {t("persona.downloadBtn")}
                    </button>
                  )}
                </div>
              </GlassCard>
            );
          })}
        </div>
      )}

      {localDrafts.length > 0 && (
        <GlassCard className="p-4 flex flex-col gap-2">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-xs font-semibold">{t("persona.localDraftsTitle")}</h2>
            <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
              {t("persona.localDraftsHint")}
            </span>
          </div>
          <div className="flex flex-col gap-2">
            {localDrafts.map((d) => (
              <div
                key={d.draft_id}
                className="rounded-xl border px-3 py-2 flex flex-wrap items-center justify-between gap-2 text-xs"
                style={{
                  borderColor: "var(--border-glass)",
                  backgroundColor: "var(--bg-elevated)",
                }}
              >
                <div className="min-w-0">
                  <span className="font-medium">{d.name}</span>{" "}
                  <span className="text-[11px] font-mono" style={{ color: "var(--text-secondary)" }}>
                    ({d.language} · {d.license} · {d.provenance_type})
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="rounded-full border border-amber-400/40 bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-200">
                    {t("persona.draftPendingServer")}
                  </span>
                  <button
                    type="button"
                    onClick={() => handleDeleteLocalDraft(d.draft_id)}
                    className="p-1 rounded-lg border border-white/10 text-rose-300 hover:border-rose-400/50"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </GlassCard>
      )}

      {/* Detail modal */}
      {detailPersona && detailCompat && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <GlassCard className="w-full max-w-2xl max-h-[88vh] overflow-y-auto p-5 flex flex-col gap-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-base font-semibold">{detailPersona.name}</h2>
                  <span className="rounded-full px-2 py-0.5 text-[10px] font-mono border border-white/15">
                    {detailPersona.language} · {detailPersona.locale}
                  </span>
                  <span className="rounded-full px-2 py-0.5 text-[10px] font-mono border border-purple-400/40 text-purple-200">
                    v{detailPersona.version}
                  </span>
                  {isPersonaDemoOnly(detailPersona, config.source_mode) && (
                    <span className="rounded-full px-2 py-0.5 text-[10px] font-mono border border-amber-400/45 text-amber-300 bg-amber-500/10">
                      {t("persona.demoOnlyBadge")}
                    </span>
                  )}
                </div>
                <p className="text-xs mt-1" style={{ color: "var(--text-secondary)" }}>
                  {detailPersona.description}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setDetailPersona(null)}
                className="p-1.5 rounded-xl border border-white/10 hover:border-white/30"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {isPersonaDemoOnly(detailPersona, config.source_mode) && (
              <div className="rounded-xl border border-amber-400/35 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-200">
                {t("persona.demoDetailNotice")}
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-xs">
              <div
                className="rounded-xl border p-3 flex flex-col gap-1"
                style={{
                  borderColor: "var(--border-glass)",
                  backgroundColor: "var(--bg-elevated)",
                }}
              >
                <span className="font-semibold">{t("persona.audioSpecTitle")}</span>
                <span className="font-mono text-[11px]" style={{ color: "var(--text-secondary)" }}>
                  {detailPersona.audio.format.toUpperCase()} · {detailPersona.audio.sample_rate_hz} Hz ·{" "}
                  {detailPersona.audio.channels === 1 ? "mono" : `${detailPersona.audio.channels} ch`} ·{" "}
                  {detailPersona.audio.duration_s.toFixed(1)}s
                </span>
                {detailPersona.audio.sha256 && (
                  <span className="font-mono text-[10px] break-all" style={{ color: "var(--text-muted)" }}>
                    SHA-256: {detailPersona.audio.sha256}
                  </span>
                )}
              </div>

              <div
                className="rounded-xl border p-3 flex flex-col gap-1"
                style={{
                  borderColor: "var(--border-glass)",
                  backgroundColor: "var(--bg-elevated)",
                }}
              >
                <span className="font-semibold flex items-center gap-1.5">
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                  {t("persona.consentTitle")}
                </span>
                <span className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
                  {detailPersona.consent.provenance_type} · {detailPersona.consent.license}
                </span>
                <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                  {detailPersona.consent.provenance_note}
                </span>
              </div>
            </div>

            <div
              className="rounded-xl border p-3 flex flex-col gap-1 text-xs"
              style={{
                borderColor: "var(--border-glass)",
                backgroundColor: "var(--bg-elevated)",
              }}
            >
              <span className="font-semibold">{t("profiles.refText")}</span>
              <p style={{ color: "var(--text-secondary)" }}>{detailPersona.ref_text}</p>
            </div>

            <div
              className="rounded-xl border p-3 flex flex-col gap-2 text-xs"
              style={{
                borderColor: "var(--border-glass)",
                backgroundColor: "var(--bg-elevated)",
              }}
            >
              <span className="font-semibold">{t("persona.compatibilityMatrixTitle")}</span>
              <p className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
                {t("persona.compatibilityHonestNote")}
              </p>

              <div className="flex flex-col gap-1.5">
                {detailCompat.compatible.map((ev) => (
                  <div
                    key={ev.engine}
                    className="rounded-lg border px-2.5 py-2 flex flex-col gap-1"
                    style={{
                      borderColor:
                        ev.status === "compatible"
                          ? "rgba(16,185,129,0.35)"
                          : "rgba(245,158,11,0.35)",
                      backgroundColor: "var(--bg-input)",
                    }}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-medium">
                        {ev.label}{" "}
                        <span className="font-mono text-[10px] opacity-70">
                          ({ev.installed ? t("persona.engineInstalled") : t("persona.engineNotInstalled")})
                        </span>
                      </span>
                      <span
                        className={clsx(
                          "text-[10px] font-mono",
                          ev.status === "compatible" ? "text-emerald-300" : "text-amber-300"
                        )}
                      >
                        {ev.status === "compatible"
                          ? t("persona.statusCompatible")
                          : t("persona.statusNeedsConversion")}
                      </span>
                    </div>
                    {ev.conversions_needed.length > 0 && (
                      <div className="text-[11px] text-amber-200/90">
                        {t("persona.conversionsLabel")}: {ev.conversions_needed.join(" · ")}
                      </div>
                    )}
                    {ev.warnings.length > 0 && (
                      <div className="text-[10px]" style={{ color: "var(--text-muted)" }}>
                        {ev.warnings.join(" ")}
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {detailCompat.unsupported.length > 0 && (
                <div className="mt-1 flex flex-col gap-1">
                  <span className="text-[11px] font-medium text-rose-300">
                    {t("persona.unsupportedEnginesTitle")}
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {detailCompat.unsupported.map((ev) => (
                      <span
                        key={ev.engine}
                        title={ev.requirement.notes}
                        className="rounded-lg border border-rose-500/35 bg-rose-500/10 px-2 py-0.5 text-[10px] text-rose-200"
                      >
                        {ev.label}: {t("persona.statusUnsupported")}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {installingId === detailPersona.id &&
              installProgress?.persona_id === detailPersona.id && (
                <div className="rounded-xl border border-cyan-400/35 bg-cyan-500/10 px-3 py-2 text-xs text-cyan-200 font-mono">
                  {renderProgressText(installProgress)}
                </div>
              )}

            <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
              <button
                type="button"
                disabled={!baseUrl || installingId === detailPersona.id}
                onClick={() => void handleInstallPersona(detailPersona, true)}
                className="inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium hover:border-cyan-400/50 disabled:opacity-45"
                style={{
                  borderColor: "var(--border-glass)",
                  backgroundColor: "var(--bg-elevated)",
                }}
              >
                <FileAudio className="w-3.5 h-3.5" />
                {t("persona.attachAudioCreateProfile")}
              </button>
              {!isPersonaDemoOnly(detailPersona, config.source_mode) && (
                <BorderBeamButton
                  disabled={installingId === detailPersona.id || !baseUrl}
                  onClick={() => void handleInstallPersona(detailPersona, false)}
                >
                  {installingId === detailPersona.id ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Download className="w-3.5 h-3.5" />
                  )}
                  {t("persona.downloadBtn")}
                </BorderBeamButton>
              )}
            </div>
          </GlassCard>
        </div>
      )}

      {/* Share / Publish Own Profile modal */}
      {publishOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <GlassCard className="w-full max-w-2xl max-h-[90vh] overflow-y-auto p-5 flex flex-col gap-3">
            <div className="flex items-start justify-between gap-2">
              <div>
                <h2 className="text-base font-semibold">{t("persona.publishTitle")}</h2>
                <p className="text-xs mt-0.5" style={{ color: "var(--text-secondary)" }}>
                  {t("persona.publishSubtitle")}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setPublishOpen(false)}
                className="p-1.5 rounded-xl border border-white/10 hover:border-white/30"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="rounded-xl border border-amber-400/35 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-200 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0 text-amber-300 mt-0.5" />
              <span>{t("persona.publishBackendBoundaryNotice")}</span>
            </div>

            {profiles.length > 0 && (
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span style={{ color: "var(--text-secondary)" }}>
                  {t("persona.prefillFromProfile")}:
                </span>
                <select
                  value={publishDraft.source_profile_id || ""}
                  onChange={(e) => {
                    const prof = profiles.find((p) => p.id === e.target.value);
                    if (prof) prefillFromVoiceProfile(prof);
                  }}
                  className="rounded-xl border px-2.5 py-1.5 text-xs outline-none"
                  style={{
                    backgroundColor: "var(--bg-input)",
                    borderColor: "var(--border-glass)",
                    color: "var(--text-primary)",
                  }}
                >
                  <option value="">{t("persona.chooseLocalProfile")}</option>
                  {profiles.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({p.engine} · {p.language})
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <input
                value={publishDraft.name}
                onChange={(e) => setPublishDraft({ ...publishDraft, name: e.target.value })}
                placeholder={t("persona.publishNamePlaceholder")}
                className="rounded-xl border px-3 py-2 text-xs outline-none"
                style={{ backgroundColor: "var(--bg-input)", borderColor: "var(--border-glass)" }}
              />
              <input
                value={publishDraft.language}
                onChange={(e) => setPublishDraft({ ...publishDraft, language: e.target.value })}
                placeholder={t("persona.publishLanguagePlaceholder")}
                className="rounded-xl border px-3 py-2 text-xs outline-none"
                style={{ backgroundColor: "var(--bg-input)", borderColor: "var(--border-glass)" }}
              />
              <input
                value={publishDraft.locale}
                onChange={(e) => setPublishDraft({ ...publishDraft, locale: e.target.value })}
                placeholder="es-ES / en-US"
                className="rounded-xl border px-3 py-2 text-xs font-mono outline-none"
                style={{ backgroundColor: "var(--bg-input)", borderColor: "var(--border-glass)" }}
              />
            </div>

            <textarea
              rows={2}
              value={publishDraft.description}
              onChange={(e) =>
                setPublishDraft({ ...publishDraft, description: e.target.value })
              }
              placeholder={t("persona.publishDescriptionPlaceholder")}
              className="w-full rounded-xl border p-2.5 text-xs outline-none"
              style={{ backgroundColor: "var(--bg-input)", borderColor: "var(--border-glass)" }}
            />

            <div className="flex items-center gap-2">
              <input
                value={publishDraft.ref_audio_path}
                onChange={(e) =>
                  setPublishDraft({ ...publishDraft, ref_audio_path: e.target.value })
                }
                placeholder={t("profiles.refAudio")}
                className="flex-1 rounded-xl border px-3 py-2 text-xs font-mono outline-none"
                style={{ backgroundColor: "var(--bg-input)", borderColor: "var(--border-glass)" }}
              />
              {publishDraft.ref_audio_path && baseUrl && (
                <button
                  type="button"
                  onClick={toggleDraftAudioPreview}
                  className="p-2 rounded-xl border text-cyan-300"
                  style={{
                    borderColor: "var(--border-glass)",
                    backgroundColor: "var(--bg-elevated)",
                  }}
                >
                  {previewPlaying ? (
                    <Pause className="w-3.5 h-3.5" />
                  ) : (
                    <Play className="w-3.5 h-3.5" />
                  )}
                </button>
              )}
              <button
                type="button"
                onClick={async () => {
                  const picked = await pickFile({
                    filters: [{ name: "Audio", extensions: ["wav", "mp3", "m4a", "flac", "ogg"] }],
                  });
                  if (picked) {
                    setPublishDraft({ ...publishDraft, ref_audio_path: picked });
                  }
                }}
                className="inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-medium"
                style={{
                  borderColor: "var(--border-glass)",
                  backgroundColor: "var(--bg-elevated)",
                }}
              >
                <FileAudio className="w-3.5 h-3.5" />
                {t("profiles.selectAudio")}
              </button>
            </div>

            <textarea
              rows={2}
              value={publishDraft.ref_text}
              onChange={(e) => setPublishDraft({ ...publishDraft, ref_text: e.target.value })}
              placeholder={t("profiles.refTextPlaceholder")}
              className="w-full rounded-xl border p-2.5 text-xs outline-none"
              style={{ backgroundColor: "var(--bg-input)", borderColor: "var(--border-glass)" }}
            />

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <select
                value={publishDraft.provenance_type}
                onChange={(e) =>
                  setPublishDraft({
                    ...publishDraft,
                    provenance_type: e.target.value as PersonaProvenanceType,
                  })
                }
                className="rounded-xl border px-2.5 py-2 text-xs outline-none"
                style={{
                  backgroundColor: "var(--bg-input)",
                  borderColor: "var(--border-glass)",
                  color: "var(--text-primary)",
                }}
              >
                <option value="self_recorded">{t("persona.prov_self_recorded")}</option>
                <option value="authorized_actor">{t("persona.prov_authorized_actor")}</option>
                <option value="synthetic_reference">{t("persona.prov_synthetic_reference")}</option>
                <option value="pack_reference">{t("persona.prov_pack_reference")}</option>
              </select>

              <select
                value={publishDraft.license}
                onChange={(e) =>
                  setPublishDraft({
                    ...publishDraft,
                    license: e.target.value as PersonaLicenseKind,
                  })
                }
                className="rounded-xl border px-2.5 py-2 text-xs outline-none"
                style={{
                  backgroundColor: "var(--bg-input)",
                  borderColor: "var(--border-glass)",
                  color: "var(--text-primary)",
                }}
              >
                <option value="cc-by-4.0">CC-BY 4.0</option>
                <option value="cc0">CC0 (Public Domain)</option>
                <option value="personal-non-commercial">Personal / Non-Commercial</option>
                <option value="proprietary-pack">Proprietary Pack</option>
                <option value="custom">Custom License</option>
              </select>

              <input
                value={tagsInput}
                onChange={(e) => setTagsInput(e.target.value)}
                placeholder={t("persona.tagsPlaceholder")}
                className="rounded-xl border px-3 py-2 text-xs outline-none"
                style={{ backgroundColor: "var(--bg-input)", borderColor: "var(--border-glass)" }}
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <input
                value={publishDraft.attribution}
                onChange={(e) =>
                  setPublishDraft({ ...publishDraft, attribution: e.target.value })
                }
                placeholder={t("persona.attributionPlaceholder")}
                className="rounded-xl border px-3 py-2 text-xs outline-none"
                style={{ backgroundColor: "var(--bg-input)", borderColor: "var(--border-glass)" }}
              />
              <input
                value={publishDraft.provenance_note}
                onChange={(e) =>
                  setPublishDraft({ ...publishDraft, provenance_note: e.target.value })
                }
                placeholder={t("persona.provenanceNotePlaceholder")}
                className="rounded-xl border px-3 py-2 text-xs outline-none"
                style={{ backgroundColor: "var(--bg-input)", borderColor: "var(--border-glass)" }}
              />
            </div>

            <label className="flex items-start gap-2 text-xs cursor-pointer">
              <input
                type="checkbox"
                checked={publishDraft.speaker_consent_confirmed}
                onChange={(e) =>
                  setPublishDraft({
                    ...publishDraft,
                    speaker_consent_confirmed: e.target.checked,
                  })
                }
                className="mt-0.5"
              />
              <span style={{ color: "var(--text-secondary)" }}>{t("persona.consentCheckbox")}</span>
            </label>

            {publishFeedback && (
              <div className="rounded-xl border border-cyan-400/35 bg-cyan-500/10 px-3 py-2 text-xs text-cyan-200">
                {publishFeedback}
              </div>
            )}

            <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
              <button
                type="button"
                onClick={() => void handleCopyPayload()}
                className="inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium"
                style={{
                  borderColor: "var(--border-glass)",
                  backgroundColor: "var(--bg-elevated)",
                }}
              >
                <Copy className="w-3.5 h-3.5" />
                {copiedPayload ? t("transcriber.copied") : t("persona.copyPayloadBtn")}
              </button>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setPublishOpen(false)}
                  className="rounded-full border px-4 py-1.5 text-xs font-medium"
                  style={{
                    borderColor: "var(--border-glass)",
                    backgroundColor: "var(--bg-elevated)",
                  }}
                >
                  {t("profiles.cancel")}
                </button>
                <BorderBeamButton
                  disabled={!publishValidation.valid}
                  onClick={handleSavePublishDraft}
                >
                  {t("persona.saveDraftBtn")}
                </BorderBeamButton>
              </div>
            </div>
          </GlassCard>
        </div>
      )}
    </div>
  );
};

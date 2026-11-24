import React, { useEffect, useState } from "react";
import { CheckCircle2, Edit3, FileAudio, Loader2, Plus, Sparkles, Trash2 } from "lucide-react";
import { useI18n } from "../i18n";
import {
  buildProfileVoice,
  createProfile,
  deleteProfile,
  notify,
  transcribeAudioFile,
  updateProfile,
} from "../services/api";
import { pickFile } from "../services/fileDialog";
import type { AppSettings, CatalogModelEntry, EngineKind, VoiceProfile } from "../types";
import { BorderBeamButton } from "./BorderBeamButton";
import { GlassCard } from "./GlassCard";

const PROFILE_LANGUAGES = [
  "Auto",
  "Spanish",
  "English",
  "French",
  "German",
  "Italian",
  "Portuguese",
  "Japanese",
  "Korean",
  "Chinese",
  "Russian",
];

const STT_CODE_TO_LABEL: Record<string, string> = {
  es: "Spanish",
  en: "English",
  fr: "French",
  de: "German",
  it: "Italian",
  pt: "Portuguese",
  ja: "Japanese",
  ko: "Korean",
  zh: "Chinese",
  ru: "Russian",
};

interface ProfilesViewProps {
  baseUrl: string;
  catalog: CatalogModelEntry[];
  settings: AppSettings;
  profiles: VoiceProfile[];
  selectedProfileId: string;
  onProfilesChange: (next: VoiceProfile[]) => void;
  onUseProfile: (id: string) => void;
  onAfterGpuAction: () => void;
  notificationsEnabled: boolean;
}

export const ProfilesView: React.FC<ProfilesViewProps> = ({
  baseUrl,
  catalog,
  settings,
  profiles,
  selectedProfileId,
  onProfilesChange,
  onUseProfile,
  onAfterGpuAction,
  notificationsEnabled,
}) => {
  const { t } = useI18n();
  const [editingId, setEditingId] = useState<string | "new" | null>(null);
  const [name, setName] = useState("");
  const [language, setLanguage] = useState("Spanish");
  const [engine, setEngine] = useState<EngineKind>("qwen");
  const [refAudioPath, setRefAudioPath] = useState("");
  const [refText, setRefText] = useState("");
  const [busy, setBusy] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sttOptions = React.useMemo(
    () => catalog.filter((m) => m.kind === "stt" && m.installed && m.runtime_supported),
    [catalog]
  );
  const isSttEndpoint =
    settings.stt_source === "endpoint" && Boolean(settings.active_stt_endpoint_id);
  const [selectedSttId, setSelectedSttId] = useState<string>(settings.active_stt_model || "");

  useEffect(() => {
    if (sttOptions.some((m) => m.id === selectedSttId)) return;
    const preferred =
      sttOptions.find((m) => m.id === settings.active_stt_model)?.id || sttOptions[0]?.id || "";
    setSelectedSttId(preferred);
  }, [sttOptions, selectedSttId, settings.active_stt_model]);

  const hasSttReady = isSttEndpoint || sttOptions.length > 0;

  const availableEngines = React.useMemo(() => {
    const list: { value: EngineKind; label: string }[] = [];
    if (catalog.some((m) => m.kind === "tts" && m.engine === "qwen" && m.installed && m.runtime_supported)) {
      list.push({ value: "qwen", label: "Qwen3-TTS" });
    }
    if (catalog.some((m) => m.kind === "tts" && m.engine === "xtts" && m.installed && m.runtime_supported)) {
      list.push({ value: "xtts", label: "XTTS v2" });
    }
    if (catalog.some((m) => m.kind === "tts" && (m.engine === "f5-tts" || m.engine === "f5") && m.installed && m.runtime_supported)) {
      list.push({ value: "f5", label: "F5-TTS" });
    }
    if (catalog.some((m) => m.kind === "tts" && (m.engine === "fish-audio" || m.engine === "fish") && m.installed && m.runtime_supported)) {
      list.push({ value: "fish", label: "Fish Speech 1.5" });
    }
    return list;
  }, [catalog]);

  useEffect(() => {
    if (editingId === "new" && availableEngines.length > 0 && !availableEngines.some((e) => e.value === engine)) {
      setEngine(availableEngines[0].value);
    }
  }, [editingId, availableEngines, engine]);

  const openNew = () => {
    setEditingId("new");
    setName("");
    setLanguage("Spanish");
    setEngine(availableEngines[0]?.value || "qwen");
    setRefAudioPath("");
    setRefText("");
    setError(null);
  };

  const openEdit = (p: VoiceProfile) => {
    setEditingId(p.id);
    setName(p.name);
    setLanguage(p.language);
    setEngine(p.engine);
    setRefAudioPath(p.ref_audio_path);
    setRefText(p.ref_text);
    setError(null);
  };

  const pickAudio = async () => {
    setError(null);
    try {
      const selected = await pickFile({
        filters: [{ name: "Audio", extensions: ["wav", "mp3", "m4a", "flac", "ogg"] }],
      });
      if (selected) {
        setRefAudioPath(selected);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleSave = async () => {
    if (!baseUrl || !name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      if (editingId === "new") {
        const created = await createProfile(baseUrl, {
          name,
          language,
          engine,
          ref_audio_path: refAudioPath,
          ref_text: refText,
          build_voice: engine === "qwen" && !!refAudioPath,
        });
        onProfilesChange([...profiles, created]);
      } else if (editingId) {
        const updated = await updateProfile(baseUrl, editingId, {
          name,
          language,
          engine,
          ref_audio_path: refAudioPath,
          ref_text: refText,
          rebuild_voice: false,
        });
        onProfilesChange(profiles.map((p) => (p.id === updated.id ? updated : p)));
      }
      setEditingId(null);
      onAfterGpuAction();
      void notify(notificationsEnabled, t("toast.title"), t("toast.profileSaved"));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      void notify(notificationsEnabled, t("toast.title"), t("toast.failed"));
    } finally {
      setBusy(false);
    }
  };

  const handleBuild = async (p: VoiceProfile) => {
    if (!baseUrl) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await buildProfileVoice(baseUrl, p.id);
      onProfilesChange(profiles.map((item) => (item.id === updated.id ? updated : item)));
      onAfterGpuAction();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      void notify(notificationsEnabled, t("toast.title"), t("toast.failed"));
    } finally {
      setBusy(false);
    }
  };

  const handleAutoTranscribe = async () => {
    if (!baseUrl || !refAudioPath.trim()) return;
    if (!hasSttReady) {
      setError(t("profiles.noSttHint"));
      return;
    }
    setTranscribing(true);
    setError(null);
    try {
      const res = await transcribeAudioFile(baseUrl, {
        audio_path: refAudioPath.trim(),
        language: language === "Auto" ? undefined : language,
        model_id: isSttEndpoint ? undefined : selectedSttId || undefined,
      });
      setRefText(res.text);
      if (language === "Auto" && res.language && res.language.toLowerCase() !== "auto") {
        const mapped = STT_CODE_TO_LABEL[res.language.toLowerCase()] || res.language;
        if (PROFILE_LANGUAGES.includes(mapped)) {
          setLanguage(mapped);
        }
      }
      onAfterGpuAction();
      void notify(notificationsEnabled, t("toast.title"), t("toast.transcribed"));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      void notify(notificationsEnabled, t("toast.title"), t("toast.failed"));
    } finally {
      setTranscribing(false);
    }
  };

  const handleDelete = async (p: VoiceProfile) => {
    if (!baseUrl) return;
    setError(null);
    try {
      await deleteProfile(baseUrl, p.id);
      onProfilesChange(profiles.filter((item) => item.id !== p.id));
      void notify(notificationsEnabled, t("toast.title"), t("toast.profileDeleted"));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      void notify(notificationsEnabled, t("toast.title"), t("toast.failed"));
    }
  };

  return (
    <div className="flex flex-col gap-3 pb-4">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold leading-tight">{t("profiles.title")}</h1>
          <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
            {t("profiles.subtitle")}
          </p>
        </div>
        <BorderBeamButton onClick={openNew}>
          <Plus className="w-4 h-4" />
          {t("profiles.newProfile")}
        </BorderBeamButton>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
          {error}
        </div>
      )}

      {editingId && (
        <GlassCard className="p-4 flex flex-col gap-3">
          <h2 className="text-sm font-semibold">
            {editingId === "new" ? t("profiles.newProfile") : t("profiles.editProfile")}
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("profiles.name")}
              className="rounded-xl border px-3 py-2 text-xs outline-none"
              style={{ backgroundColor: "var(--bg-input)", borderColor: "var(--border-glass)" }}
            />
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="rounded-xl border px-3 py-2 text-xs outline-none"
              style={{
                backgroundColor: "var(--bg-input)",
                borderColor: "var(--border-glass)",
                color: "var(--text-primary)",
              }}
            >
              {(PROFILE_LANGUAGES.includes(language)
                ? PROFILE_LANGUAGES
                : [language, ...PROFILE_LANGUAGES]
              ).map((langOpt) => (
                <option key={langOpt} value={langOpt}>
                  {langOpt}
                </option>
              ))}
            </select>
            <select
              value={availableEngines.length > 0 ? engine : ""}
              onChange={(e) => setEngine(e.target.value as EngineKind)}
              disabled={availableEngines.length === 0}
              title={availableEngines.length === 0 ? t("profiles.noCloneTtsHint") : undefined}
              className="rounded-xl border px-3 py-2 text-xs outline-none disabled:opacity-50"
              style={{
                backgroundColor: "var(--bg-input)",
                borderColor: "var(--border-glass)",
                color: "var(--text-primary)",
              }}
            >
              {availableEngines.length === 0 ? (
                <option value="">{t("profiles.noCloneTtsInstalled")}</option>
              ) : (
                availableEngines.map((eng) => (
                  <option key={eng.value} value={eng.value}>
                    {eng.label}
                  </option>
                ))
              )}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <input
              value={refAudioPath}
              onChange={(e) => setRefAudioPath(e.target.value)}
              placeholder={t("profiles.refAudio")}
              className="flex-1 rounded-xl border px-3 py-2 text-xs font-mono outline-none"
              style={{ backgroundColor: "var(--bg-input)", borderColor: "var(--border-glass)" }}
            />
            <button
              type="button"
              onClick={pickAudio}
              className="inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-medium hover:border-cyan-400/50"
              style={{ borderColor: "var(--border-glass)", backgroundColor: "var(--bg-elevated)" }}
            >
              <FileAudio className="w-3.5 h-3.5" />
              {t("profiles.selectAudio")}
            </button>
          </div>

          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
              {t("profiles.refText")}
            </span>
            <textarea
              rows={3}
              value={refText}
              onChange={(e) => setRefText(e.target.value)}
              placeholder={t("profiles.refTextPlaceholder")}
              className="w-full rounded-2xl border p-2.5 text-xs outline-none"
              style={{ backgroundColor: "var(--bg-input)", borderColor: "var(--border-glass)" }}
            />
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <BorderBeamButton
                disabled={busy || !name.trim() || (editingId === "new" && availableEngines.length === 0)}
                onClick={handleSave}
              >
                {busy && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                {busy ? t("profiles.building") : t("profiles.save")}
              </BorderBeamButton>
              <button
                type="button"
                disabled={busy}
                onClick={() => setEditingId(null)}
                className="rounded-full border px-4 py-2 text-xs font-medium"
                style={{ borderColor: "var(--border-glass)", backgroundColor: "var(--bg-elevated)" }}
              >
                {t("profiles.cancel")}
              </button>
            </div>

            <div className="flex items-center gap-2">
              <select
                value={isSttEndpoint ? "__endpoint__" : selectedSttId}
                onChange={(e) => setSelectedSttId(e.target.value)}
                disabled={isSttEndpoint || sttOptions.length === 0 || transcribing || busy}
                title={hasSttReady ? undefined : t("profiles.noSttHint")}
                className="rounded-xl border px-2.5 py-1.5 text-xs outline-none disabled:opacity-50"
                style={{
                  backgroundColor: "var(--bg-input)",
                  borderColor: "var(--border-glass)",
                  color: "var(--text-primary)",
                }}
              >
                {isSttEndpoint ? (
                  <option value="__endpoint__">{t("models.endpoint")}</option>
                ) : sttOptions.length === 0 ? (
                  <option value="">{t("profiles.noSttInstalled")}</option>
                ) : (
                  sttOptions.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name}
                    </option>
                  ))
                )}
              </select>
              <button
                type="button"
                disabled={!hasSttReady || transcribing || busy || !refAudioPath.trim()}
                title={!hasSttReady ? t("profiles.noSttHint") : undefined}
                onClick={handleAutoTranscribe}
                className="inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs hover:border-cyan-400/50 disabled:opacity-45"
                style={{ borderColor: "var(--border-glass)", backgroundColor: "var(--bg-elevated)" }}
              >
                {transcribing ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Sparkles className="w-3.5 h-3.5" />
                )}
                {transcribing ? t("profiles.transcribing") : t("profiles.transcribe")}
              </button>
            </div>
          </div>
        </GlassCard>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {profiles.map((p) => {
          const active = p.id === selectedProfileId;
          return (
            <GlassCard key={p.id} className="p-4 flex flex-col gap-2.5">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="font-semibold text-sm truncate">{p.name}</span>
                  <span className="rounded-full px-2 py-0.5 text-[10px] font-mono border border-white/10">
                    {p.engine} · {p.language}
                  </span>
                </div>
                <span
                  className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-mono border shrink-0"
                  style={{
                    borderColor: p.ready ? "rgba(16,185,129,0.4)" : "rgba(245,158,11,0.4)",
                    color: p.ready ? "#34d399" : "#fbbf24",
                  }}
                >
                  <CheckCircle2 className="w-3 h-3" />
                  {p.ready ? t("profiles.ready") : t("profiles.notBuilt")}
                </span>
              </div>

              <p className="text-xs line-clamp-2" style={{ color: "var(--text-secondary)" }}>
                {p.ref_text || "—"}
              </p>

              <div className="flex flex-wrap items-center gap-1.5 mt-auto pt-1">
                <button
                  type="button"
                  onClick={() => onUseProfile(p.id)}
                  className="rounded-xl border px-2.5 py-1 text-xs font-medium transition-colors"
                  style={{
                    borderColor: active ? "var(--accent-secondary)" : "var(--border-glass)",
                    backgroundColor: "var(--bg-elevated)",
                  }}
                >
                  {t("profiles.useInStudio")}
                </button>
                {!p.ready && p.engine === "qwen" && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => handleBuild(p)}
                    className="rounded-xl border px-2.5 py-1 text-xs font-medium border-cyan-400/40 text-cyan-300"
                  >
                    {t("profiles.buildNow")}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => openEdit(p)}
                  className="inline-flex items-center gap-1 rounded-xl border px-2.5 py-1 text-xs"
                  style={{ borderColor: "var(--border-glass)", backgroundColor: "var(--bg-elevated)" }}
                >
                  <Edit3 className="w-3 h-3" />
                  {t("profiles.edit")}
                </button>
                <button
                  type="button"
                  onClick={() => handleDelete(p)}
                  className="inline-flex items-center gap-1 rounded-xl border px-2 py-1 text-xs text-rose-300 hover:border-rose-500/50 ml-auto"
                  style={{ borderColor: "var(--border-glass)", backgroundColor: "var(--bg-elevated)" }}
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            </GlassCard>
          );
        })}
      </div>
    </div>
  );
};

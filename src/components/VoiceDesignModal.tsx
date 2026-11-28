import React, { useEffect, useState } from "react";
import { Loader2, Sparkles, Volume2, X } from "lucide-react";
import { useI18n } from "../i18n";
import {
  fetchVoiceDesignStatus,
  generateVoiceDesignPreview,
  saveVoiceDesignProfile,
  type VoiceDesignStatus,
} from "../services/voiceDesignApi";
import type { VoiceProfile } from "../types";
import { BorderBeamButton } from "./BorderBeamButton";
import { GlassCard } from "./GlassCard";

const VD_LANGUAGES = [
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

interface VoiceDesignModalProps {
  open: boolean;
  baseUrl: string;
  defaultLanguage?: string;
  onClose: () => void;
  onSaved: (profile: VoiceProfile) => void;
  onOpenModels?: () => void;
}

export const VoiceDesignModal: React.FC<VoiceDesignModalProps> = ({
  open,
  baseUrl,
  defaultLanguage = "Spanish",
  onClose,
  onSaved,
  onOpenModels,
}) => {
  const { t } = useI18n();
  const [status, setStatus] = useState<VoiceDesignStatus | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(false);
  const [instructions, setInstructions] = useState(
    "Calm, warm Spanish narrator, clear articulation, mid-low register."
  );
  const [language, setLanguage] = useState(
    VD_LANGUAGES.includes(defaultLanguage) ? defaultLanguage : "Spanish"
  );
  const [sampleText, setSampleText] = useState(
    "Hola, esta es una muestra diseñada para clonar esta voz con claridad."
  );
  const [voiceName, setVoiceName] = useState("");
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewDuration, setPreviewDuration] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !baseUrl) return;
    setError(null);
    setLoadingStatus(true);
    void fetchVoiceDesignStatus(baseUrl)
      .then(setStatus)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoadingStatus(false));

    const onKeyDown = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, baseUrl, onClose]);

  if (!open) return null;

  const handleGenerate = async () => {
    if (!baseUrl || !instructions.trim() || !sampleText.trim()) return;
    setGenerating(true);
    setError(null);
    try {
      const res = await generateVoiceDesignPreview(baseUrl, {
        instructions: instructions.trim(),
        language,
        sample_text: sampleText.trim(),
      });
      setPreviewId(res.preview_id);
      setPreviewUrl(`${baseUrl}${res.audio_url}?t=${Date.now()}`);
      setPreviewDuration(res.duration_s);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setGenerating(false);
    }
  };

  const handleSave = async () => {
    if (!baseUrl || !previewId || !voiceName.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const prof = await saveVoiceDesignProfile(baseUrl, {
        preview_id: previewId,
        name: voiceName.trim(),
        language,
        sample_text: sampleText.trim(),
        engine: "qwen",
      });
      onSaved(prof);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
      aria-label={t("voiceDesign.title")}
    >
      <GlassCard className="w-full max-w-xl p-5 flex flex-col gap-3.5 max-h-[90vh] overflow-y-auto">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-purple-400" />
            <div>
              <h3 className="text-sm font-semibold">{t("voiceDesign.title")}</h3>
              <p className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
                {t("voiceDesign.subtitle")}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("profiles.cancel")}
            className="p-1 rounded-lg opacity-70 hover:opacity-100"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {loadingStatus ? (
          <div className="flex items-center gap-2 text-xs py-2" style={{ color: "var(--text-secondary)" }}>
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            <span>{t("voiceDesign.checkingModel")}</span>
          </div>
        ) : status && !status.ready ? (
          <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-3 flex flex-wrap items-center justify-between gap-2 text-xs text-amber-200">
            <span>{t("voiceDesign.notInstalledHint")}</span>
            {onOpenModels && (
              <button
                type="button"
                onClick={() => {
                  onClose();
                  onOpenModels();
                }}
                className="rounded-xl border border-amber-400/50 bg-amber-500/20 px-3 py-1 text-xs font-medium hover:bg-amber-500/30"
              >
                {t("synthesize.installInModels")}
              </button>
            )}
          </div>
        ) : null}

        {error && (
          <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
            {error}
          </div>
        )}

        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
            {t("voiceDesign.instructionsLabel")}
          </label>
          <textarea
            rows={2}
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            placeholder={t("voiceDesign.instructionsPlaceholder")}
            className="w-full rounded-xl border px-3 py-2 text-xs outline-none"
            style={{ backgroundColor: "var(--bg-input)", borderColor: "var(--border-glass)" }}
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
              {t("voiceDesign.languageLabel")}
            </label>
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
              {VD_LANGUAGES.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
              {t("voiceDesign.nameLabel")}
            </label>
            <input
              value={voiceName}
              onChange={(e) => setVoiceName(e.target.value)}
              placeholder={t("voiceDesign.namePlaceholder")}
              className="rounded-xl border px-3 py-2 text-xs outline-none"
              style={{ backgroundColor: "var(--bg-input)", borderColor: "var(--border-glass)" }}
            />
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
            {t("voiceDesign.sampleTextLabel")}
          </label>
          <textarea
            rows={2}
            value={sampleText}
            onChange={(e) => setSampleText(e.target.value)}
            placeholder={t("voiceDesign.sampleTextPlaceholder")}
            className="w-full rounded-xl border px-3 py-2 text-xs outline-none"
            style={{ backgroundColor: "var(--bg-input)", borderColor: "var(--border-glass)" }}
          />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
          <BorderBeamButton
            disabled={generating || !instructions.trim() || !sampleText.trim()}
            onClick={handleGenerate}
          >
            {generating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Volume2 className="w-3.5 h-3.5" />}
            {generating ? t("voiceDesign.generating") : t("voiceDesign.previewBtn")}
          </BorderBeamButton>

          <button
            type="button"
            disabled={saving || !previewId || !voiceName.trim()}
            onClick={handleSave}
            className="rounded-full border border-emerald-400/50 bg-emerald-500/20 px-4 py-2 text-xs font-semibold text-emerald-200 hover:bg-emerald-500/30 disabled:opacity-45"
          >
            {saving ? t("profiles.building") : t("voiceDesign.saveBtn")}
          </button>
        </div>

        {previewUrl && (
          <div
            className="rounded-xl border p-2.5 flex flex-col gap-1.5"
            style={{ borderColor: "var(--border-glass)", backgroundColor: "var(--bg-elevated)" }}
          >
            <div className="flex items-center justify-between text-[11px] font-mono" style={{ color: "var(--text-secondary)" }}>
              <span>{t("voiceDesign.previewReady")}</span>
              <span>{previewDuration.toFixed(1)}s</span>
            </div>
            <audio controls src={previewUrl} className="w-full h-8" />
          </div>
        )}
      </GlassCard>
    </div>
  );
};

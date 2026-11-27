import React, { useState } from "react";
import {
  Check,
  Copy,
  Eraser,
  FileAudio,
  Loader2,
  Sparkles,
  X,
} from "lucide-react";
import { useI18n } from "../i18n";
import { notify, transcribeAudioFile } from "../services/api";
import { pickFile } from "../services/fileDialog";
import type { AppSettings, CatalogModelEntry, TranscriptSegment } from "../types";
import { BorderBeamButton } from "./BorderBeamButton";
import { GlassCard } from "./GlassCard";
import { SttModelSelector } from "./SttModelSelector";

interface TranscriberViewProps {
  baseUrl: string;
  catalog: CatalogModelEntry[];
  settings: AppSettings;
  onSaveSettings: (next: AppSettings) => Promise<void>;
  onAfterGpuAction: () => void;
}

const STT_LANGS = [
  { code: "auto", label: "Auto" },
  { code: "es", label: "Spanish (es)" },
  { code: "en", label: "English (en)" },
  { code: "fr", label: "French (fr)" },
  { code: "de", label: "German (de)" },
  { code: "it", label: "Italian (it)" },
  { code: "pt", label: "Portuguese (pt)" },
  { code: "ja", label: "Japanese (ja)" },
  { code: "ko", label: "Korean (ko)" },
  { code: "zh", label: "Chinese (zh)" },
  { code: "ru", label: "Russian (ru)" },
];

export const TranscriberView: React.FC<TranscriberViewProps> = ({
  baseUrl,
  catalog,
  settings,
  onSaveSettings,
  onAfterGpuAction,
}) => {
  const { t } = useI18n();
  const [audioPath, setAudioPath] = useState("");
  const [language, setLanguage] = useState("auto");
  const [outputText, setOutputText] = useState("");
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [stats, setStats] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pickAudio = async () => {
    setError(null);
    try {
      const selected = await pickFile({
        title: t("transcriber.selectAudio"),
        filters: [{ name: "Audio", extensions: ["wav", "mp3", "m4a", "flac", "opus", "ogg"] }],
      });
      if (selected) {
        setAudioPath(selected);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleTranscribe = async () => {
    if (!baseUrl || !audioPath.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await transcribeAudioFile(baseUrl, {
        audio_path: audioPath.trim(),
        language: language === "auto" ? undefined : language,
      });
      setOutputText(res.text);
      setSegments(res.segments || []);
      setStats(`${res.language} · ${res.duration_s.toFixed(1)}s in ${res.elapsed_s.toFixed(2)}s`);
      onAfterGpuAction();
      void notify(settings.notifications_enabled, t("toast.title"), t("toast.transcribed"));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      void notify(settings.notifications_enabled, t("toast.title"), t("toast.failed"));
    } finally {
      setBusy(false);
    }
  };

  const handleCopy = async () => {
    if (!outputText) return;
    await navigator.clipboard.writeText(outputText);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <GlassCard className="flex-1 min-h-0 p-4 flex flex-col gap-2.5 overflow-hidden">
        <div className="flex flex-wrap items-center justify-end gap-2 shrink-0">
          <SttModelSelector
            catalog={catalog}
            settings={settings}
            onSaveSettings={onSaveSettings}
            disabled={busy}
          />
        </div>

        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <input
            value={audioPath}
            onChange={(e) => setAudioPath(e.target.value)}
            placeholder={t("transcriber.audioPlaceholder")}
            className="flex-1 min-w-[200px] rounded-xl border px-3 py-1.5 text-xs font-mono outline-none"
            style={{ backgroundColor: "var(--bg-input)", borderColor: "var(--border-glass)" }}
          />
          {audioPath && (
            <button
              type="button"
              disabled={busy}
              onClick={() => setAudioPath("")}
              title={t("transcriber.clearAudio")}
              className="p-1.5 rounded-xl border hover:border-rose-400/50 text-rose-300 disabled:opacity-40"
              style={{ borderColor: "var(--border-glass)", backgroundColor: "var(--bg-elevated)" }}
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
          <button
            type="button"
            onClick={pickAudio}
            className="inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium hover:border-cyan-400/50"
            style={{ borderColor: "var(--border-glass)", backgroundColor: "var(--bg-elevated)" }}
          >
            <FileAudio className="w-3.5 h-3.5" />
            {t("transcriber.selectAudio")}
          </button>
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="rounded-xl border px-2.5 py-1.5 text-xs outline-none"
            style={{
              backgroundColor: "var(--bg-input)",
              borderColor: "var(--border-glass)",
              color: "var(--text-primary)",
            }}
          >
            {STT_LANGS.map((l) => (
              <option key={l.code} value={l.code}>
                {l.code === "auto" ? t("transcriber.autoLang") : l.label}
              </option>
            ))}
          </select>
        </div>

        {error && (
          <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-300 shrink-0">
            {error}
          </div>
        )}

        <textarea
          value={outputText}
          onChange={(e) => setOutputText(e.target.value)}
          placeholder={t("transcriber.outputPlaceholder")}
          className="flex-1 min-h-[110px] w-full rounded-2xl border p-3 text-sm outline-none resize-none"
          style={{
            backgroundColor: "var(--bg-input)",
            borderColor: "var(--border-glass)",
            color: "var(--text-primary)",
          }}
        />

        {segments.length > 0 && (
          <div
            className="max-h-[110px] overflow-y-auto rounded-xl border p-2.5 flex flex-col gap-1 text-xs shrink-0"
            style={{ backgroundColor: "var(--bg-input)", borderColor: "var(--border-glass)" }}
          >
            <span className="text-[10px] font-mono uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>
              {t("transcriber.segments")}
            </span>
            {segments.map((s, i) => (
              <div key={i} className="flex gap-2">
                <span className="font-mono text-[11px] text-cyan-400 shrink-0">
                  [{s.start.toFixed(1)}s–{s.end.toFixed(1)}s]
                </span>
                <span style={{ color: "var(--text-secondary)" }}>{s.text}</span>
              </div>
            ))}
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-2 shrink-0">
          <div className="flex items-center gap-2">
            <BorderBeamButton disabled={busy || !audioPath.trim()} onClick={handleTranscribe}>
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              {busy ? t("transcriber.transcribing") : t("transcriber.transcribe")}
            </BorderBeamButton>

            <button
              type="button"
              disabled={!outputText}
              onClick={handleCopy}
              className="inline-flex items-center gap-1.5 rounded-full border px-3.5 py-2 text-xs font-medium disabled:opacity-40 hover:border-cyan-400/50"
              style={{ backgroundColor: "var(--bg-surface-strong)", borderColor: "var(--border-glass)" }}
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              {copied ? t("transcriber.copied") : t("transcriber.copy")}
            </button>

            <button
              type="button"
              disabled={!outputText && segments.length === 0}
              onClick={() => {
                setOutputText("");
                setSegments([]);
                setStats(null);
              }}
              className="inline-flex items-center gap-1.5 rounded-full border px-3.5 py-2 text-xs font-medium disabled:opacity-40 hover:border-rose-400/50"
              style={{
                backgroundColor: "var(--bg-surface-strong)",
                borderColor: "var(--border-glass)",
                color: "var(--text-secondary)",
              }}
            >
              <Eraser className="w-3.5 h-3.5" />
              {t("transcriber.erase")}
            </button>
          </div>

          {stats && (
            <span className="text-[11px] font-mono" style={{ color: "var(--text-secondary)" }}>
              {stats}
            </span>
          )}
        </div>
      </GlassCard>
    </div>
  );
};

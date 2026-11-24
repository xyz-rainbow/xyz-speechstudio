import React, { useEffect, useRef, useState } from "react";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import {
  Check,
  ChevronDown,
  Copy,
  Eraser,
  FileAudio,
  Loader2,
  Sparkles,
} from "lucide-react";
import { clsx } from "clsx";
import { useI18n } from "../i18n";
import { fetchModelsCatalog, isTauri, transcribeAudioFile } from "../services/api";
import type { AppSettings, CatalogModelEntry, TranscriptSegment } from "../types";
import { BorderBeamButton } from "./BorderBeamButton";
import { GlassCard } from "./GlassCard";

interface TranscriberViewProps {
  baseUrl: string;
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

  const [menuOpen, setMenuOpen] = useState(false);
  const [localModels, setLocalModels] = useState<CatalogModelEntry[]>([]);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!baseUrl) return;
    let alive = true;
    fetchModelsCatalog(baseUrl)
      .then((res) => {
        if (!alive) return;
        setLocalModels(
          res.models.filter((m) => m.kind === "stt" && m.installed && m.runtime_supported)
        );
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [baseUrl]);

  useEffect(() => {
    if (!menuOpen) return;
    const onPointerDown = (ev: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(ev.target as Node)) {
        setMenuOpen(false);
      }
    };
    window.addEventListener("mousedown", onPointerDown);
    return () => window.removeEventListener("mousedown", onPointerDown);
  }, [menuOpen]);

  const sttEndpoints = settings.external_endpoints.filter((e) => e.kind === "stt");
  const activeEp = sttEndpoints.find((e) => e.id === settings.active_stt_endpoint_id);
  const isEndpointMode = settings.stt_source === "endpoint";

  const sourceLabel = isEndpointMode
    ? `Endpoint · ${activeEp ? activeEp.name : t("transcriber.unconfigured")}`
    : `Local · ${settings.active_stt_model} (${settings.stt_device.toUpperCase()})`;

  const localOptions: { id: string; name: string }[] = React.useMemo(() => {
    const items = localModels.map((m) => ({ id: m.id, name: m.name }));
    if (
      settings.active_stt_model &&
      !items.some((i) => i.id === settings.active_stt_model)
    ) {
      items.unshift({ id: settings.active_stt_model, name: settings.active_stt_model });
    }
    return items;
  }, [localModels, settings.active_stt_model]);

  const selectLocalModel = async (id: string) => {
    setMenuOpen(false);
    if (id === settings.active_stt_model) return;
    await onSaveSettings({ ...settings, active_stt_model: id });
  };

  const selectEndpoint = async (id: string) => {
    setMenuOpen(false);
    if (id === settings.active_stt_endpoint_id) return;
    await onSaveSettings({ ...settings, active_stt_endpoint_id: id });
  };

  const pickAudio = async () => {
    if (!isTauri()) return;
    const selected = await openDialog({
      multiple: false,
      filters: [{ name: "Audio", extensions: ["wav", "mp3", "m4a", "flac", "opus", "ogg"] }],
    });
    if (typeof selected === "string" && selected.length > 0) {
      setAudioPath(selected);
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
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
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
        <div className="flex flex-wrap items-center justify-between gap-2 shrink-0">
          <div>
            <h1 className="text-lg font-semibold leading-tight">{t("transcriber.title")}</h1>
            <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
              {t("transcriber.subtitle")}
            </p>
          </div>

          <div className="relative" ref={menuRef}>
            <button
              type="button"
              onClick={() => setMenuOpen((v) => !v)}
              title={t("transcriber.selectModelHint")}
              className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-mono border transition-colors hover:brightness-110"
              style={{
                backgroundColor: "var(--bg-input)",
                borderColor: isEndpointMode
                  ? "rgba(16,185,129,0.45)"
                  : "rgba(6,182,212,0.45)",
                color: isEndpointMode ? "#34d399" : "#67e8f9",
              }}
            >
              <span>{sourceLabel}</span>
              <ChevronDown
                className={clsx("w-3.5 h-3.5 transition-transform", menuOpen && "rotate-180")}
              />
            </button>

            {menuOpen && (
              <div
                className="absolute right-0 mt-1.5 z-40 min-w-[230px] max-w-[290px] rounded-2xl border p-1.5 shadow-2xl backdrop-blur-xl flex flex-col gap-0.5"
                style={{
                  backgroundColor: "var(--bg-elevated)",
                  borderColor: "var(--border-glass)",
                }}
              >
                <span
                  className="px-2.5 py-1 text-[10px] font-mono uppercase tracking-wider"
                  style={{ color: "var(--text-muted)" }}
                >
                  {isEndpointMode ? t("transcriber.endpointModels") : t("transcriber.localModels")}
                </span>

                {isEndpointMode ? (
                  sttEndpoints.length > 0 ? (
                    sttEndpoints.map((ep) => {
                      const active = ep.id === settings.active_stt_endpoint_id;
                      return (
                        <button
                          key={ep.id}
                          type="button"
                          onClick={() => selectEndpoint(ep.id)}
                          className={clsx(
                            "w-full text-left rounded-xl px-2.5 py-1.5 text-xs flex items-center justify-between gap-2 hover:bg-white/10",
                            active && "bg-emerald-500/15 text-emerald-300"
                          )}
                        >
                          <div className="min-w-0">
                            <div className="font-medium truncate">{ep.name}</div>
                            <div className="text-[10px] font-mono opacity-70 truncate">
                              {ep.protocol} · {ep.model || "—"}
                            </div>
                          </div>
                          {active && <Check className="w-3.5 h-3.5 shrink-0 text-emerald-400" />}
                        </button>
                      );
                    })
                  ) : (
                    <div
                      className="px-2.5 py-2 text-[11px]"
                      style={{ color: "var(--text-secondary)" }}
                    >
                      {t("transcriber.noEndpoints")}
                    </div>
                  )
                ) : (
                  localOptions.map((m) => {
                    const active = m.id === settings.active_stt_model;
                    return (
                      <button
                        key={m.id}
                        type="button"
                        onClick={() => selectLocalModel(m.id)}
                        className={clsx(
                          "w-full text-left rounded-xl px-2.5 py-1.5 text-xs flex items-center justify-between gap-2 hover:bg-white/10",
                          active && "bg-cyan-500/15 text-cyan-200"
                        )}
                      >
                        <div className="min-w-0">
                          <div className="font-medium truncate">{m.name}</div>
                          <div className="text-[10px] font-mono opacity-65 truncate">{m.id}</div>
                        </div>
                        {active && <Check className="w-3.5 h-3.5 shrink-0 text-cyan-400" />}
                      </button>
                    );
                  })
                )}
              </div>
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <input
            value={audioPath}
            onChange={(e) => setAudioPath(e.target.value)}
            placeholder={t("transcriber.audioPlaceholder")}
            className="flex-1 min-w-[200px] rounded-xl border px-3 py-1.5 text-xs font-mono outline-none"
            style={{ backgroundColor: "var(--bg-input)", borderColor: "var(--border-glass)" }}
          />
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

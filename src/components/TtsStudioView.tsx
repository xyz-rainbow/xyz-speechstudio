import React, { useEffect, useRef, useState } from "react";
import { save as saveDialog } from "@tauri-apps/plugin-dialog";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  ChevronDown,
  ChevronRight,
  Eraser,
  FolderArchive,
  FolderOpen,
  Loader2,
  Play,
  Save,
  Trash2,
  Volume2,
} from "lucide-react";
import { clsx } from "clsx";
import { useI18n } from "../i18n";
import {
  deleteHistoryRecord,
  isTauri,
  LiveCaptionsConflictError,
  notify,
  revealInExplorer,
  saveHistoryAs,
  synthesizeTts,
} from "../services/api";
import type {
  AppSettings,
  CatalogModelEntry,
  GenerationRecord,
  VoiceProfile,
} from "../types";
import { endpointProviderSubtitle } from "../utils/endpointPresets";
import { BorderBeamButton } from "./BorderBeamButton";
import { GlassCard } from "./GlassCard";

interface TtsStudioViewProps {
  baseUrl: string;
  catalog: CatalogModelEntry[];
  settings: AppSettings;
  onSaveSettings: (next: AppSettings) => Promise<void>;
  profiles: VoiceProfile[];
  selectedProfileId: string;
  onSelectProfileId: (id: string) => void;
  history: GenerationRecord[];
  onHistoryChange: (next: GenerationRecord[]) => void;
  onAfterGpuAction: () => void;
  incomingSpeak?: { text: string; nonce: number } | null;
  notificationsEnabled: boolean;
}

const LANGUAGES = [
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

function normalizeTtsModelId(id: string): string {
  if (id.startsWith("qwen3-1.7b-base")) return "qwen3-1.7b-base";
  if (id.startsWith("qwen3-1.7b-customvoice")) return "qwen3-1.7b-customvoice";
  if (id.startsWith("qwen3-0.6b-base")) return "qwen3-0.6b-base";
  if (id.startsWith("xtts")) return "xtts-v2";
  return id;
}

export const TtsStudioView: React.FC<TtsStudioViewProps> = ({
  baseUrl,
  catalog,
  settings,
  onSaveSettings,
  profiles,
  selectedProfileId,
  onSelectProfileId,
  history,
  onHistoryChange,
  onAfterGpuAction,
  incomingSpeak,
  notificationsEnabled,
}) => {
  const { t } = useI18n();
  const [subView, setSubView] = useState<"editor" | "exported">("editor");
  const [text, setText] = useState("");
  const [language, setLanguage] = useState("Spanish");
  const [busyMode, setBusyMode] = useState<"play" | "wav" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingForceMode, setPendingForceMode] = useState<"play" | "wav" | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [lastStats, setLastStats] = useState<{ dur: number; elapsed: number; rtf: number } | null>(
    null
  );
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const catalogTts = React.useMemo(
    () => catalog.filter((m) => m.kind === "tts" && m.runtime_supported && m.installed),
    [catalog]
  );

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

  const activeModelId = normalizeTtsModelId(settings.active_tts_model || "qwen3-1.7b-base");
  const isEndpointMode = settings.tts_source === "endpoint";
  const ttsEndpoints = settings.external_endpoints.filter((e) => e.kind === "tts");
  const activeEp = ttsEndpoints.find((e) => e.id === settings.active_tts_endpoint_id);

  const localOptions: { id: string; name: string; subtitle: string; engine: "qwen" | "xtts" }[] =
    React.useMemo(
      () =>
        catalogTts.map((m) => ({
          id: m.id,
          name: m.name,
          subtitle: `${m.installed_quant || m.quants[0]?.id || m.engine} · ~${(
            m.vram_mib / 1024
          ).toFixed(1)} GB`,
          engine: (m.engine === "xtts" ? "xtts" : "qwen") as "qwen" | "xtts",
        })),
      [catalogTts]
    );

  const activeLocal = localOptions.find((m) => m.id === activeModelId) || localOptions[0];
  const modelFamily = (activeLocal?.id || activeModelId).startsWith("xtts") ? "xtts" : "qwen";
  const visibleProfiles = profiles.filter((p) => p.engine === modelFamily);
  const selectedProfile =
    visibleProfiles.find((p) => p.id === selectedProfileId) || visibleProfiles[0];

  const selectorLabel = isEndpointMode
    ? `${t("models.externalGroup")} · ${activeEp ? activeEp.name : t("transcriber.unconfigured")}`
    : activeLocal
      ? `${t("models.local")} · ${activeLocal.name}`
      : `${t("models.local")} · ${t("models.noLocalInstalled")}`;

  const selectLocalModel = async (id: string) => {
    setMenuOpen(false);
    if (settings.tts_source === "local" && normalizeTtsModelId(settings.active_tts_model) === id) {
      return;
    }
    await onSaveSettings({
      ...settings,
      tts_source: "local",
      active_tts_model: id,
    });
  };

  const selectEndpoint = async (id: string) => {
    setMenuOpen(false);
    if (settings.tts_source === "endpoint" && settings.active_tts_endpoint_id === id) {
      return;
    }
    await onSaveSettings({
      ...settings,
      tts_source: "endpoint",
      active_tts_endpoint_id: id,
    });
  };

  useEffect(() => {
    if (visibleProfiles.some((p) => p.id === selectedProfileId)) return;
    if (visibleProfiles[0]) onSelectProfileId(visibleProfiles[0].id);
  }, [activeModelId, profiles, selectedProfileId, onSelectProfileId, visibleProfiles]);

  useEffect(() => {
    if (selectedProfile) {
      setLanguage(selectedProfile.language || "Spanish");
    }
  }, [selectedProfile?.id]);

  const synthTokenRef = useRef(0);
  const lastSpokenRef = useRef("");

  const canSynthesize =
    !busyMode &&
    !!text.trim() &&
    (isEndpointMode ? !!activeEp : !!activeLocal && !!selectedProfile);

  const runSynth = async (
    mode: "play" | "wav",
    forceStopCaptions = false,
    textOverride?: string
  ) => {
    if (!baseUrl) return;
    if (!isEndpointMode && !selectedProfile) return;
    if (isEndpointMode && !activeEp) return;
    const myToken = ++synthTokenRef.current;
    if (mode === "play") lastSpokenRef.current = (textOverride ?? text).trim();
    setBusyMode(mode);
    setError(null);
    setPendingForceMode(null);
    try {
      const res = await synthesizeTts(baseUrl, {
        profile_id: selectedProfile?.id || "mario",
        text: textOverride ?? text,
        language,
        mode,
        force_stop_captions: forceStopCaptions,
      });
      if (myToken !== synthTokenRef.current) return;
      const fullAudioUrl = `${baseUrl}${res.audio_url}`;
      setPreviewUrl(fullAudioUrl);

      if (mode === "wav" && res.record) {
        onHistoryChange([res.record, ...history]);
        setLastStats({
          dur: res.record.duration_s,
          elapsed: res.record.elapsed_s,
          rtf: res.record.rtf,
        });
      } else {
        void notify(notificationsEnabled, t("toast.title"), t("toast.playing"));
        setLastStats({
          dur: res.duration_s ?? 0,
          elapsed: res.elapsed_s ?? 0,
          rtf: res.rtf ?? 0,
        });
        setTimeout(() => {
          audioRef.current?.play().catch(() => {});
        }, 60);
      }
      onAfterGpuAction();
    } catch (err) {
      if (err instanceof LiveCaptionsConflictError) {
        setPendingForceMode(mode);
      } else {
        const message = err instanceof Error ? err.message : String(err);
        setError(message);
        void notify(notificationsEnabled, t("toast.title"), t("toast.failed"));
      }
    } finally {
      setBusyMode(null);
    }
  };

  // Global hotkey "read selection": toggle pause/resume on same text, otherwise stop and play the new text.
  useEffect(() => {
    if (!incomingSpeak) return;
    const incoming = incomingSpeak.text.trim();
    const audio = audioRef.current;
    const isPlaying = !!audio && !audio.paused && !audio.ended;
    const isPaused =
      !!audio && audio.paused && !audio.ended && audio.currentTime > 0 && !!previewUrl;
    const sameText = incoming === "" || incoming === lastSpokenRef.current;

    if (sameText && isPlaying) {
      audio!.pause();
      return;
    }
    if (sameText && isPaused) {
      audio!.play().catch(() => {});
      void notify(notificationsEnabled, t("toast.title"), t("toast.playing"));
      return;
    }
    if (incoming === "") {
      if (!isPlaying && !isPaused) {
        void notify(notificationsEnabled, t("toast.title"), t("hotkey.noSelection"));
      }
      return;
    }

    audio?.pause();
    void notify(notificationsEnabled, t("toast.title"), t("hotkey.processing"));
    setSubView("editor");
    setText(incoming);
    lastSpokenRef.current = incoming;
    void runSynth("play", false, incoming);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incomingSpeak?.nonce]);

  const handleSaveAs = async (rec: GenerationRecord) => {
    if (!baseUrl || !isTauri()) return;
    const dest = await saveDialog({
      defaultPath: `${rec.profile_name.toLowerCase()}-${rec.id}.wav`,
      filters: [{ name: "WAV Audio", extensions: ["wav"] }],
    });
    if (!dest) return;
    const updated = await saveHistoryAs(baseUrl, rec.id, dest);
    onHistoryChange(history.map((h) => (h.id === rec.id ? updated : h)));
    void notify(notificationsEnabled, t("toast.title"), t("toast.saved"));
  };

  const handleReveal = async (rec: GenerationRecord) => {
    await revealInExplorer(rec.saved_path || rec.file_path);
  };

  const handleDelete = async (rec: GenerationRecord) => {
    if (!baseUrl) return;
    await deleteHistoryRecord(baseUrl, rec.id);
    onHistoryChange(history.filter((h) => h.id !== rec.id));
    void notify(notificationsEnabled, t("toast.title"), t("toast.deletedAudio"));
  };

  if (subView === "exported") {
    return (
      <div className="flex-1 min-h-0 flex flex-col">
        <GlassCard className="flex-1 min-h-0 p-4 flex flex-col gap-3 overflow-hidden">
          <div className="flex items-center justify-between gap-2 shrink-0">
            <div className="flex items-center gap-2.5">
              <button
                type="button"
                onClick={() => setSubView("editor")}
                className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium hover:border-purple-400/50 transition-colors"
                style={{
                  backgroundColor: "var(--bg-elevated)",
                  borderColor: "var(--border-glass)",
                }}
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                {t("synthesize.back")}
              </button>
              <h1 className="text-base font-semibold">
                {t("synthesize.historyTitle")} ({history.length})
              </h1>
            </div>
          </div>

          {previewUrl && (
            <div
              className="flex items-center gap-2 rounded-xl border px-3 py-1.5 shrink-0"
              style={{ backgroundColor: "var(--bg-input)", borderColor: "var(--border-glass)" }}
            >
              <Volume2 className="w-4 h-4 text-cyan-400 shrink-0" />
              <audio ref={audioRef} controls src={previewUrl} className="w-full h-8" />
            </div>
          )}

          <div className="flex-1 min-h-0 overflow-y-auto pr-1 flex flex-col gap-2">
            {history.length === 0 ? (
              <div
                className="flex-1 flex items-center justify-center text-xs rounded-2xl border p-6"
                style={{
                  borderColor: "var(--border-glass)",
                  backgroundColor: "var(--bg-input)",
                  color: "var(--text-muted)",
                }}
              >
                {t("synthesize.emptyHistory")}
              </div>
            ) : (
              history.map((rec) => {
                const url = `${baseUrl}/api/tts/history/${rec.id}/audio`;
                return (
                  <div
                    key={rec.id}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border px-3 py-2"
                    style={{
                      backgroundColor: "var(--bg-input)",
                      borderColor: "var(--border-glass)",
                    }}
                  >
                    <div className="flex-1 min-w-[180px]">
                      <div className="flex items-center gap-2 text-xs">
                        <span className="font-semibold text-purple-300">{rec.profile_name}</span>
                        <span className="font-mono text-[10px]" style={{ color: "var(--text-muted)" }}>
                          {rec.duration_s.toFixed(2)}s · RTF {rec.rtf.toFixed(2)}
                        </span>
                        {rec.saved_path && (
                          <span className="rounded-full px-2 py-0.5 text-[10px] bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                            {t("synthesize.savedAt")}
                          </span>
                        )}
                      </div>
                      <p className="text-xs truncate mt-0.5" style={{ color: "var(--text-secondary)" }}>
                        {rec.text}
                      </p>
                    </div>

                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => {
                          setPreviewUrl(url);
                          setTimeout(() => audioRef.current?.play().catch(() => {}), 50);
                          void notify(notificationsEnabled, t("toast.title"), t("toast.playing"));
                        }}
                        className="inline-flex items-center gap-1 rounded-xl border px-2.5 py-1 text-xs hover:border-cyan-400/50"
                        style={{ borderColor: "var(--border-glass)", backgroundColor: "var(--bg-elevated)" }}
                      >
                        <Play className="w-3 h-3" />
                        {t("synthesize.play")}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleSaveAs(rec)}
                        className="inline-flex items-center gap-1 rounded-xl border px-2.5 py-1 text-xs hover:border-emerald-400/50"
                        style={{ borderColor: "var(--border-glass)", backgroundColor: "var(--bg-elevated)" }}
                      >
                        <Save className="w-3 h-3" />
                        {t("synthesize.saveAs")}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleReveal(rec)}
                        className="inline-flex items-center gap-1 rounded-xl border px-2.5 py-1 text-xs hover:border-purple-400/50"
                        style={{ borderColor: "var(--border-glass)", backgroundColor: "var(--bg-elevated)" }}
                      >
                        <FolderOpen className="w-3 h-3" />
                        {t("synthesize.reveal")}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDelete(rec)}
                        title={t("synthesize.delete")}
                        className="p-1.5 rounded-xl border hover:border-rose-500/50 text-rose-300"
                        style={{ borderColor: "var(--border-glass)", backgroundColor: "var(--bg-elevated)" }}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </GlassCard>
      </div>
    );
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col gap-2.5">
      <GlassCard className="flex-1 min-h-0 p-4 flex flex-col gap-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2 shrink-0">
          <div>
            <h1 className="text-lg font-semibold leading-tight">{t("synthesize.title")}</h1>
            <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
              {t("synthesize.subtitle")}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {/* Unified Glass Dropdown: Local + Externo */}
            <div className="relative" ref={menuRef}>
              <button
                type="button"
                onClick={() => setMenuOpen((v) => !v)}
                title={t("synthesize.model")}
                className="inline-flex items-center gap-1.5 rounded-xl px-2.5 py-1.5 text-xs font-mono border transition-colors hover:brightness-110"
                style={{
                  backgroundColor: "var(--bg-input)",
                  borderColor: isEndpointMode
                    ? "rgba(16,185,129,0.45)"
                    : "var(--border-glass)",
                  color: isEndpointMode ? "#34d399" : "var(--text-primary)",
                }}
              >
                <span>{selectorLabel}</span>
                <ChevronDown
                  className={clsx("w-3.5 h-3.5 transition-transform", menuOpen && "rotate-180")}
                />
              </button>

              {menuOpen && (
                <div
                  className="absolute right-0 mt-1.5 z-40 min-w-[255px] max-w-[310px] max-h-[320px] overflow-y-auto rounded-2xl border p-1.5 shadow-2xl backdrop-blur-xl flex flex-col gap-0.5"
                  style={{
                    backgroundColor: "var(--bg-elevated)",
                    borderColor: "var(--border-glass)",
                  }}
                >
                  <span
                    className="px-2.5 pt-1 pb-0.5 text-[10px] font-mono uppercase tracking-wider"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {t("models.local")}
                  </span>

                  {localOptions.length > 0 ? (
                    localOptions.map((m) => {
                      const active = !isEndpointMode && m.id === activeLocal?.id;
                      return (
                        <button
                          key={m.id}
                          type="button"
                          onClick={() => selectLocalModel(m.id)}
                          className={clsx(
                            "w-full text-left rounded-xl px-2.5 py-1.5 text-xs flex items-center justify-between gap-2 hover:bg-white/10",
                            active && "bg-purple-500/15 text-purple-200"
                          )}
                        >
                          <div className="min-w-0">
                            <div className="font-medium truncate">{m.name}</div>
                            <div className="text-[10px] font-mono opacity-65 truncate">
                              {m.subtitle}
                            </div>
                          </div>
                          {active && <Check className="w-3.5 h-3.5 shrink-0 text-purple-400" />}
                        </button>
                      );
                    })
                  ) : (
                    <div
                      className="px-2.5 py-1.5 text-[11px]"
                      style={{ color: "var(--text-secondary)" }}
                    >
                      {t("models.noLocalInstalled")}
                    </div>
                  )}

                  <div className="my-1 h-px bg-white/10" />

                  <span
                    className="px-2.5 pt-0.5 pb-0.5 text-[10px] font-mono uppercase tracking-wider"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {t("models.externalGroup")}
                  </span>

                  {ttsEndpoints.length > 0 ? (
                    ttsEndpoints.map((ep) => {
                      const active = isEndpointMode && ep.id === settings.active_tts_endpoint_id;
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
                              {endpointProviderSubtitle(ep)}
                            </div>
                          </div>
                          {active && <Check className="w-3.5 h-3.5 shrink-0 text-emerald-400" />}
                        </button>
                      );
                    })
                  ) : (
                    <div
                      className="px-2.5 py-1.5 text-[11px]"
                      style={{ color: "var(--text-secondary)" }}
                    >
                      {t("models.noExternalConfigured")}
                    </div>
                  )}
                </div>
              )}
            </div>

            {!isEndpointMode ? (
              <select
                value={selectedProfile?.id || ""}
                onChange={(e) => onSelectProfileId(e.target.value)}
                className="rounded-xl border px-2.5 py-1.5 text-xs font-medium outline-none"
                style={{
                  backgroundColor: "var(--bg-input)",
                  borderColor: "var(--border-glass)",
                  color: "var(--text-primary)",
                }}
              >
                {visibleProfiles.length === 0 ? (
                  <option value="">{t("synthesize.noProfiles")}</option>
                ) : (
                  visibleProfiles.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({p.engine})
                    </option>
                  ))
                )}
              </select>
            ) : (
              activeEp && (
                <span
                  className="rounded-xl border px-2.5 py-1.5 text-xs font-mono"
                  style={{
                    backgroundColor: "var(--bg-input)",
                    borderColor: "var(--border-glass)",
                    color: "var(--text-secondary)",
                  }}
                >
                  {activeEp.voice || activeEp.model || t("synthesize.endpointActive")}
                </span>
              )
            )}

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
              {LANGUAGES.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
          </div>
        </div>

        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t("synthesize.inputPlaceholder")}
          className="flex-1 min-h-[120px] w-full rounded-2xl border p-3.5 text-sm outline-none resize-none"
          style={{
            backgroundColor: "var(--bg-input)",
            borderColor: "var(--border-glass)",
            color: "var(--text-primary)",
          }}
        />

        {pendingForceMode && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-amber-400/40 bg-amber-500/10 px-3 py-2 text-xs shrink-0">
            <div className="flex items-center gap-2 text-amber-200">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{t("synthesize.confirmCaptions")}</span>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => runSynth(pendingForceMode, true)}
                className="rounded-lg px-2.5 py-1 bg-amber-500/25 border border-amber-400/50 font-medium"
              >
                {t("synthesize.stopCaptionsAndRun")}
              </button>
              <button
                type="button"
                onClick={() => setPendingForceMode(null)}
                className="rounded-lg px-2.5 py-1 border border-white/15"
              >
                {t("synthesize.cancel")}
              </button>
            </div>
          </div>
        )}

        {error && (
          <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-300 shrink-0">
            {error}
          </div>
        )}

        {busyMode && (
          <div className="flex flex-col gap-1 shrink-0">
            <div className="h-1.5 w-full rounded-full overflow-hidden bg-white/10">
              <div className="h-full w-2/3 rounded-full bg-gradient-to-r from-purple-500 via-cyan-400 to-purple-500 animate-pulse" />
            </div>
            <span className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
              {t("synthesize.generating")}
            </span>
          </div>
        )}

        {previewUrl && (
          <div
            className="flex items-center gap-2 rounded-xl border px-3 py-1 shrink-0"
            style={{ backgroundColor: "var(--bg-input)", borderColor: "var(--border-glass)" }}
          >
            <Volume2 className="w-4 h-4 text-cyan-400 shrink-0" />
            <audio ref={audioRef} controls src={previewUrl} className="w-full h-8" />
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 shrink-0 pt-0.5">
          <div className="flex items-center gap-2">
            <BorderBeamButton
              disabled={!canSynthesize}
              onClick={() => runSynth("play")}
            >
              {busyMode === "play" ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Play className="w-4 h-4" />
              )}
              {t("synthesize.play")}
            </BorderBeamButton>

            <BorderBeamButton
              variant="emerald"
              disabled={!canSynthesize}
              onClick={() => runSynth("wav")}
            >
              {busyMode === "wav" ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Save className="w-4 h-4" />
              )}
              {t("synthesize.save")}
            </BorderBeamButton>
          </div>

          <button
            type="button"
            disabled={!text.length || !!busyMode}
            onClick={() => setText("")}
            className="ml-auto mr-2 inline-flex items-center gap-1.5 rounded-full border px-3.5 py-2 text-sm font-medium transition-colors disabled:opacity-40 hover:border-rose-400/50"
            style={{
              backgroundColor: "var(--bg-surface-strong)",
              borderColor: "var(--border-glass)",
              color: "var(--text-secondary)",
            }}
          >
            <Eraser className="w-4 h-4" />
            {t("synthesize.erase")}
          </button>

          {lastStats && (
            <div className="text-[11px] font-mono" style={{ color: "var(--text-secondary)" }}>
              {lastStats.dur.toFixed(2)}s · {lastStats.elapsed.toFixed(2)}s · RTF {lastStats.rtf.toFixed(3)}
            </div>
          )}
        </div>
      </GlassCard>

      <button
        type="button"
        onClick={() => setSubView("exported")}
        className="w-full text-left group shrink-0"
      >
        <GlassCard className="px-4 py-2.5 flex items-center justify-between gap-3 group-hover:border-cyan-400/50">
          <div className="flex items-center gap-2.5">
            <FolderArchive className="w-4 h-4 text-cyan-400 shrink-0" />
            <span className="text-sm font-medium">{t("synthesize.openExported")}</span>
            <span
              className="rounded-full px-2 py-0.5 text-[11px] font-mono border"
              style={{
                borderColor: "var(--border-glass)",
                backgroundColor: "var(--bg-elevated)",
                color: "var(--text-secondary)",
              }}
            >
              {history.length}
            </span>
          </div>
          <ChevronRight
            className="w-4 h-4 transition-transform group-hover:translate-x-0.5"
            style={{ color: "var(--text-secondary)" }}
          />
        </GlassCard>
      </button>
    </div>
  );
};

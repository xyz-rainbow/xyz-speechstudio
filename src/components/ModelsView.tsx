import React, { useCallback, useEffect, useState } from "react";
import {
  Check,
  Cpu,
  Download,
  Eye,
  EyeOff,
  Globe,
  HardDrive,
  Loader2,
  Play,
  Plus,
  Power,
  Search,
  Settings as SettingsIcon,
  Trash2,
  X,
  Zap,
} from "lucide-react";
import { clsx } from "clsx";
import { useI18n } from "../i18n";
import {
  cancelModelDownload,
  ejectWorker,
  ejectWorkerGroup,
  fetchModelsCatalog,
  inspectHfRepo,
  installHfModel,
  loadQwenWorker,
  loadSttWorker,
  notify,
  removeInstalledModel,
  startModelDownload,
  testExternalEndpoint,
} from "../services/api";
import type {
  AppSettings,
  CatalogModelEntry,
  DownloadJob,
  EndpointProtocol,
  EndpointTestResponse,
  ExternalEndpointConfig,
  HfInspectResponse,
  SourceMode,
  VramStatus,
  WorkersSnapshot,
} from "../types";
import {
  createEndpointFromPreset,
  ENDPOINT_PRESETS,
  reconcileActiveEndpointId,
} from "../utils/endpointPresets";
import { GlassCard } from "./GlassCard";

interface ModelsViewProps {
  baseUrl: string;
  settings: AppSettings;
  workers: WorkersSnapshot | null;
  vram: VramStatus | null;
  onSaveSettings: (next: AppSettings) => Promise<void>;
  onWorkersChange: (next: WorkersSnapshot) => void;
  onAfterGpuAction: () => void;
}

function formatDiskSize(mb: number): string {
  if (!mb || mb <= 0) return "—";
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb} MB`;
}

function formatVramSize(mib: number): string {
  if (!mib || mib <= 0) return "—";
  return mib >= 1024 ? `~${(mib / 1024).toFixed(1)} GB` : `~${mib} MB`;
}

function SourceSlideToggle({
  value,
  localLabel,
  endpointLabel,
  onChange,
}: {
  value: SourceMode;
  localLabel: string;
  endpointLabel: string;
  onChange: (next: SourceMode) => void;
}) {
  const isLocal = value === "local";
  return (
    <button
      type="button"
      onClick={() => onChange(isLocal ? "endpoint" : "local")}
      className="relative flex items-center w-[138px] h-7 rounded-full p-0.5 border transition-colors"
      style={{
        backgroundColor: "var(--bg-input)",
        borderColor: isLocal ? "rgba(6, 182, 212, 0.45)" : "rgba(16, 185, 129, 0.45)",
      }}
    >
      <span
        className={clsx(
          "absolute top-0.5 bottom-0.5 w-[66px] rounded-full transition-transform duration-200",
          isLocal
            ? "translate-x-0 bg-cyan-500/25 border border-cyan-400/55"
            : "translate-x-[66px] bg-emerald-500/25 border border-emerald-400/55"
        )}
      />
      <span
        className={clsx(
          "relative z-10 w-1/2 text-center text-[11px] font-medium",
          isLocal ? "text-cyan-300" : "opacity-60"
        )}
      >
        {localLabel}
      </span>
      <span
        className={clsx(
          "relative z-10 w-1/2 text-center text-[11px] font-medium",
          !isLocal ? "text-emerald-300" : "opacity-60"
        )}
      >
        {endpointLabel}
      </span>
    </button>
  );
}

export const ModelsView: React.FC<ModelsViewProps> = ({
  baseUrl,
  settings,
  workers,
  vram,
  onSaveSettings,
  onWorkersChange,
  onAfterGpuAction,
}) => {
  const { t } = useI18n();
  const [catalog, setCatalog] = useState<CatalogModelEntry[]>([]);
  const [downloads, setDownloads] = useState<DownloadJob[]>([]);
  const [modelsDir, setModelsDir] = useState<string>("");
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, EndpointTestResponse>>({});

  // Download quantization modal
  const [downloadTarget, setDownloadTarget] = useState<CatalogModelEntry | null>(null);
  const [selectedQuantId, setSelectedQuantId] = useState<string>("");

  // Remove model confirmation modal
  const [removeTarget, setRemoveTarget] = useState<CatalogModelEntry | null>(null);

  // Hugging Face custom modal
  const [hfOpen, setHfOpen] = useState(false);
  const [hfUrl, setHfUrl] = useState("");
  const [hfInspecting, setHfInspecting] = useState(false);
  const [hfPreview, setHfPreview] = useState<HfInspectResponse | null>(null);
  const [hfName, setHfName] = useState("");
  const [hfKind, setHfKind] = useState<"tts" | "stt">("stt");
  const [hfFiles, setHfFiles] = useState<string[]>([]);

  // Endpoint create / edit modal
  const [epModalMode, setEpModalMode] = useState<"create" | "edit">("create");
  const [epDraft, setEpDraft] = useState<ExternalEndpointConfig | null>(null);
  const [epShowKey, setEpShowKey] = useState(false);
  const [epTesting, setEpTesting] = useState(false);
  const [epModalTest, setEpModalTest] = useState<EndpointTestResponse | null>(null);

  const refreshCatalog = useCallback(async () => {
    if (!baseUrl) return;
    try {
      const res = await fetchModelsCatalog(baseUrl);
      setCatalog(res.models);
      setDownloads(res.downloads);
      setModelsDir(res.models_dir);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [baseUrl]);

  useEffect(() => {
    refreshCatalog();
  }, [refreshCatalog]);

  const hasActiveDownloads = downloads.some(
    (d) => d.status === "queued" || d.status === "downloading"
  );

  useEffect(() => {
    if (!hasActiveDownloads) return;
    const timer = window.setInterval(refreshCatalog, 1000);
    return () => window.clearInterval(timer);
  }, [hasActiveDownloads, refreshCatalog]);

  const qwenWorker = workers?.workers?.qwen;
  const sttWorker = workers?.workers?.stt;
  const xttsWorker = workers?.workers?.xtts;
  const ttsRunning = !!(qwenWorker?.running || xttsWorker?.running);
  const sttRunning = !!sttWorker?.running;

  const activeJobFor = (modelId: string): DownloadJob | undefined =>
    downloads.find(
      (d) => d.model_id === modelId && (d.status === "queued" || d.status === "downloading")
    );

  const openHfModalForKind = (kind: "tts" | "stt") => {
    setHfKind(kind);
    setHfUrl("");
    setHfPreview(null);
    setHfName("");
    setHfFiles([]);
    setHfOpen(true);
  };

  const openCreateEndpointModal = (kind: "tts" | "stt") => {
    const fresh = createEndpointFromPreset(kind);
    fresh.name = "";
    setEpModalMode("create");
    setEpDraft(fresh);
    setEpShowKey(false);
    setEpModalTest(null);
  };

  const openEditEndpointModal = (ep: ExternalEndpointConfig) => {
    setEpModalMode("edit");
    setEpDraft({ ...ep });
    setEpShowKey(false);
    setEpModalTest(testResults[ep.id] || null);
  };

  const persistEndpointDraft = async (ep: ExternalEndpointConfig): Promise<AppSettings> => {
    const normalized: ExternalEndpointConfig = {
      ...ep,
      name: ep.name.trim() || (ep.kind === "tts" ? "Custom TTS" : "Custom STT"),
      base_url: ep.base_url.trim(),
      model: ep.model.trim(),
      voice: ep.kind === "tts" ? ep.voice.trim() : "",
    };
    const exists = settings.external_endpoints.some((e) => e.id === normalized.id);
    const nextList = exists
      ? settings.external_endpoints.map((e) => (e.id === normalized.id ? normalized : e))
      : [...settings.external_endpoints, normalized];

    const nextSettings: AppSettings = {
      ...settings,
      external_endpoints: nextList,
      active_tts_endpoint_id:
        normalized.kind === "tts" && !settings.active_tts_endpoint_id
          ? normalized.id
          : reconcileActiveEndpointId(nextList, "tts", settings.active_tts_endpoint_id),
      active_stt_endpoint_id:
        normalized.kind === "stt" && !settings.active_stt_endpoint_id
          ? normalized.id
          : reconcileActiveEndpointId(nextList, "stt", settings.active_stt_endpoint_id),
    };
    await onSaveSettings(nextSettings);
    return nextSettings;
  };

  const handleSaveEndpointModal = async () => {
    if (!epDraft) return;
    setError(null);
    try {
      await persistEndpointDraft(epDraft);
      setEpDraft(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleTestEndpointModal = async () => {
    if (!baseUrl || !epDraft) return;
    setEpTesting(true);
    setEpModalTest(null);
    try {
      await persistEndpointDraft(epDraft);
      const res = await testExternalEndpoint(baseUrl, epDraft.id);
      setEpModalTest(res);
      setTestResults((prev) => ({ ...prev, [epDraft.id]: res }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setEpTesting(false);
    }
  };

  const handleDeleteEndpointModal = async () => {
    if (!epDraft) return;
    setError(null);
    const nextList = settings.external_endpoints.filter((e) => e.id !== epDraft.id);
    const nextSettings: AppSettings = {
      ...settings,
      external_endpoints: nextList,
      active_tts_endpoint_id: reconcileActiveEndpointId(
        nextList,
        "tts",
        settings.active_tts_endpoint_id
      ),
      active_stt_endpoint_id: reconcileActiveEndpointId(
        nextList,
        "stt",
        settings.active_stt_endpoint_id
      ),
    };
    try {
      await onSaveSettings(nextSettings);
      setEpDraft(null);
      void notify(settings.notifications_enabled, t("toast.title"), t("toast.endpointDeleted"));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      void notify(settings.notifications_enabled, t("toast.title"), t("toast.failed"));
    }
  };

  const handleGroupEject = async (group: "tts" | "stt") => {
    if (!baseUrl) return;
    setBusyKey(`eject-${group}`);
    setError(null);
    try {
      const snap = await ejectWorkerGroup(baseUrl, group);
      onWorkersChange(snap);
      onAfterGpuAction();
      void notify(settings.notifications_enabled, t("toast.title"), t("toast.ejected"));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      void notify(settings.notifications_enabled, t("toast.title"), t("toast.failed"));
    } finally {
      setBusyKey(null);
    }
  };

  const handleLoadModel = async (card: CatalogModelEntry) => {
    if (!baseUrl) return;
    setBusyKey(card.id);
    setError(null);
    try {
      if (card.kind === "tts") {
        await onSaveSettings({ ...settings, active_tts_model: card.id });
        const snap = await loadQwenWorker(baseUrl, settings.tts_device, false, card.id);
        onWorkersChange(snap);
      } else {
        await onSaveSettings({ ...settings, active_stt_model: card.id });
        const snap = await loadSttWorker(baseUrl, card.id, settings.stt_device);
        onWorkersChange(snap);
      }
      onAfterGpuAction();
      void notify(settings.notifications_enabled, t("toast.title"), t("toast.modelLoaded"));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      void notify(settings.notifications_enabled, t("toast.title"), t("toast.failed"));
    } finally {
      setBusyKey(null);
    }
  };

  const handleEjectSingle = async (family: string) => {
    if (!baseUrl) return;
    setBusyKey(`eject-${family}`);
    setError(null);
    try {
      const snap = await ejectWorker(baseUrl, family);
      onWorkersChange(snap);
      onAfterGpuAction();
      void notify(settings.notifications_enabled, t("toast.title"), t("toast.ejected"));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      void notify(settings.notifications_enabled, t("toast.title"), t("toast.failed"));
    } finally {
      setBusyKey(null);
    }
  };

  const handleTestEndpoint = async (epId: string) => {
    if (!baseUrl) return;
    setBusyKey(`test-${epId}`);
    try {
      const res = await testExternalEndpoint(baseUrl, epId);
      setTestResults((prev) => ({ ...prev, [epId]: res }));
    } finally {
      setBusyKey(null);
    }
  };

  const openDownloadModal = (card: CatalogModelEntry) => {
    const rec = card.quants.find((q) => q.recommended) || card.quants[0];
    setSelectedQuantId(rec?.id || "");
    setDownloadTarget(card);
  };

  const confirmDownload = async () => {
    if (!baseUrl || !downloadTarget) return;
    setError(null);
    try {
      await startModelDownload(baseUrl, downloadTarget.id, selectedQuantId || undefined);
      setDownloadTarget(null);
      await refreshCatalog();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      void notify(settings.notifications_enabled, t("toast.title"), t("toast.failed"));
    }
  };

  const handleCancelDownload = async (jobId: string) => {
    if (!baseUrl) return;
    try {
      await cancelModelDownload(baseUrl, jobId);
      await refreshCatalog();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      void notify(settings.notifications_enabled, t("toast.title"), t("toast.failed"));
    }
  };

  const confirmRemove = async () => {
    if (!baseUrl || !removeTarget) return;
    setBusyKey(`rm-${removeTarget.id}`);
    setError(null);
    try {
      await removeInstalledModel(baseUrl, removeTarget.id);
      setRemoveTarget(null);
      await refreshCatalog();
      onAfterGpuAction();
      void notify(settings.notifications_enabled, t("toast.title"), t("toast.modelRemoved"));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      void notify(settings.notifications_enabled, t("toast.title"), t("toast.failed"));
    } finally {
      setBusyKey(null);
    }
  };

  const handleInspectHf = async () => {
    if (!baseUrl || !hfUrl.trim()) return;
    setHfInspecting(true);
    setError(null);
    try {
      const info = await inspectHfRepo(baseUrl, hfUrl.trim());
      setHfPreview(info);
      setHfName(info.suggested_name);
      const defaults = info.files
        .filter((f) => f.recommended || f.filename.endsWith(".json") || f.filename.endsWith(".txt"))
        .map((f) => f.filename);
      setHfFiles(defaults.length ? defaults : info.files.slice(0, 4).map((f) => f.filename));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setHfPreview(null);
    } finally {
      setHfInspecting(false);
    }
  };

  const handleInstallHf = async () => {
    if (!baseUrl || !hfPreview || hfFiles.length === 0) return;
    setBusyKey("hf-install");
    setError(null);
    try {
      await installHfModel(baseUrl, {
        repo_id: hfPreview.repo_id,
        name: hfName.trim() || hfPreview.suggested_name,
        kind: hfKind,
        files: hfFiles,
      });
      setHfOpen(false);
      setHfUrl("");
      setHfPreview(null);
      await refreshCatalog();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyKey(null);
    }
  };

  const ttsModels = catalog.filter((m) => m.kind === "tts");
  const sttModels = catalog.filter((m) => m.kind === "stt");
  const ttsEndpoints = settings.external_endpoints.filter((e) => e.kind === "tts");
  const sttEndpoints = settings.external_endpoints.filter((e) => e.kind === "stt");

  const renderSection = (opts: {
    kind: "tts" | "stt";
    title: string;
    accentClass: string;
    source: SourceMode;
    running: boolean;
    badgeText: string | null;
    ejectLabel: string;
    onSourceChange: (next: SourceMode) => void;
    localCards: CatalogModelEntry[];
    endpoints: ExternalEndpointConfig[];
    activeEndpointId: string;
    onSelectEndpoint: (id: string) => void;
  }) => {
    const isEndpoint = opts.source === "endpoint";
    const triggerAdd = () =>
      isEndpoint ? openCreateEndpointModal(opts.kind) : openHfModalForKind(opts.kind);

    return (
      <GlassCard className="p-4 flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Cpu className={clsx("w-4 h-4", opts.accentClass)} />
            <h2 className="text-sm font-semibold">{opts.title}</h2>
            {opts.badgeText && (
              <span className="rounded-full px-2 py-0.5 text-[10px] font-mono bg-emerald-500/15 text-emerald-300 border border-emerald-500/35">
                {opts.badgeText}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={triggerAdd}
              title={isEndpoint ? t("models.addEndpoint") : t("models.addHfModel")}
              className="inline-flex items-center justify-center w-7 h-7 rounded-full border hover:border-cyan-400/60 text-cyan-300 transition-colors"
              style={{ borderColor: "var(--border-glass)", backgroundColor: "var(--bg-elevated)" }}
            >
              <Plus className="w-3.5 h-3.5" />
            </button>
            <SourceSlideToggle
              value={opts.source}
              localLabel={t("models.local")}
              endpointLabel={t("models.endpoint")}
              onChange={opts.onSourceChange}
            />
            <button
              type="button"
              disabled={!opts.running || busyKey === `eject-${opts.kind}`}
              onClick={() => handleGroupEject(opts.kind)}
              className="inline-flex items-center gap-1 rounded-full border px-3 py-1.5 text-xs font-medium disabled:opacity-40 hover:border-rose-400/60 text-rose-300"
              style={{ borderColor: "var(--border-glass)", backgroundColor: "var(--bg-elevated)" }}
            >
              <Power className="w-3.5 h-3.5" />
              {opts.ejectLabel}
            </button>
          </div>
        </div>

        <div className="flex gap-3 overflow-x-auto pb-2">
          {!isEndpoint
            ? opts.localCards.map((card) => {
                const isLoaded =
                  card.kind === "tts"
                    ? card.engine === "qwen" &&
                      !!qwenWorker?.running &&
                      (qwenWorker.model_id === card.id ||
                        !!qwenWorker.model_id?.startsWith(`${card.id}-`))
                    : !!sttWorker?.running && sttWorker.model_id === card.id;
                const isSelected =
                  card.kind === "tts"
                    ? settings.active_tts_model === card.id
                    : settings.active_stt_model === card.id;
                const activeJob = activeJobFor(card.id);
                const singleFamily = card.kind === "tts" ? card.engine : "stt";

                return (
                  <div
                    key={card.id}
                    className={clsx(
                      "min-w-[225px] max-w-[225px] shrink-0 rounded-2xl border p-3 flex flex-col gap-2 transition-colors",
                      isLoaded
                        ? "border-cyan-400/55"
                        : isSelected
                          ? "border-purple-400/45"
                          : card.installed
                            ? "border-white/15"
                            : "border-white/10 opacity-90"
                    )}
                    style={{ backgroundColor: "var(--bg-input)" }}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-xs font-semibold leading-snug">{card.name}</span>
                      <span className="rounded-full px-1.5 py-0.5 text-[10px] font-mono border border-white/10 shrink-0">
                        {formatVramSize(card.vram_mib)}
                      </span>
                    </div>

                    <div
                      className="flex flex-wrap items-center gap-1.5 text-[10px] font-mono"
                      style={{ color: "var(--text-muted)" }}
                    >
                      <span>{card.installed_quant || card.quants[0]?.id || "GGUF"}</span>
                      <span>·</span>
                      <span>{formatDiskSize(card.disk_mb)}</span>
                      {card.external && (
                        <span className="rounded-full px-1.5 py-0.5 bg-amber-500/15 text-amber-300 border border-amber-500/30">
                          {t("models.externalBadge")}
                        </span>
                      )}
                    </div>

                    {activeJob ? (
                      <div className="mt-auto flex flex-col gap-1.5 pt-1">
                        <div className="flex items-center justify-between text-[10px] font-mono">
                          <span className="text-cyan-300 truncate">{t("models.downloading")}</span>
                          <span>{activeJob.progress}%</span>
                        </div>
                        <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
                          <div
                            className="h-full bg-gradient-to-r from-cyan-400 to-purple-500 transition-all"
                            style={{ width: `${activeJob.progress}%` }}
                          />
                        </div>
                        <button
                          type="button"
                          onClick={() => handleCancelDownload(activeJob.job_id)}
                          className="inline-flex items-center justify-center gap-1 rounded-xl border px-2 py-1 text-xs hover:border-rose-400/50 text-rose-300"
                          style={{
                            borderColor: "var(--border-glass)",
                            backgroundColor: "var(--bg-elevated)",
                          }}
                        >
                          <X className="w-3 h-3" />
                          {t("models.cancel")}
                        </button>
                      </div>
                    ) : card.installed ? (
                      <div className="flex flex-col gap-1.5 mt-auto pt-1">
                        {!card.runtime_supported && (
                          <span className="text-[10px] font-mono text-amber-300/80">
                            {t("models.runtimeLater")}
                          </span>
                        )}
                        <div className="flex items-center gap-1.5">
                          {card.runtime_supported && (
                            <>
                              <button
                                type="button"
                                disabled={!!busyKey || isLoaded}
                                onClick={() => handleLoadModel(card)}
                                className="flex-1 inline-flex items-center justify-center gap-1 rounded-xl border px-2 py-1 text-xs font-medium disabled:opacity-40 hover:border-cyan-400/50"
                                style={{
                                  borderColor: "var(--border-glass)",
                                  backgroundColor: "var(--bg-elevated)",
                                }}
                              >
                                {busyKey === card.id ? (
                                  <Loader2 className="w-3 h-3 animate-spin" />
                                ) : (
                                  <Play className="w-3 h-3" />
                                )}
                                {t("models.load")}
                              </button>
                              <button
                                type="button"
                                disabled={!isLoaded || !!busyKey}
                                onClick={() => handleEjectSingle(singleFamily)}
                                className="inline-flex items-center justify-center rounded-xl border px-2 py-1 text-xs disabled:opacity-40 hover:border-rose-400/50 text-rose-300"
                                style={{
                                  borderColor: "var(--border-glass)",
                                  backgroundColor: "var(--bg-elevated)",
                                }}
                                title={t("models.eject")}
                              >
                                <Power className="w-3 h-3" />
                              </button>
                            </>
                          )}
                          {card.removable && (
                            <button
                              type="button"
                              disabled={!!busyKey}
                              onClick={() => setRemoveTarget(card)}
                              className={clsx(
                                "inline-flex items-center justify-center gap-1 rounded-xl border px-2 py-1 text-xs disabled:opacity-40 hover:border-rose-400/60 text-rose-300",
                                !card.runtime_supported && "flex-1"
                              )}
                              style={{
                                borderColor: "var(--border-glass)",
                                backgroundColor: "var(--bg-elevated)",
                              }}
                              title={t("models.remove")}
                            >
                              <Trash2 className="w-3 h-3" />
                              {!card.runtime_supported && t("models.remove")}
                            </button>
                          )}
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1.5 mt-auto pt-1">
                        <button
                          type="button"
                          onClick={() => openDownloadModal(card)}
                          className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-xl border px-2.5 py-1.5 text-xs font-medium hover:border-cyan-400/60 text-cyan-300"
                          style={{
                            borderColor: "var(--border-glass)",
                            backgroundColor: "var(--bg-elevated)",
                          }}
                        >
                          <Download className="w-3.5 h-3.5" />
                          {t("models.download")}
                        </button>
                      </div>
                    )}
                  </div>
                );
              })
            : opts.endpoints.map((ep) => {
                const active = opts.activeEndpointId === ep.id;
                const tr = testResults[ep.id];
                return (
                  <div
                    key={ep.id}
                    className={clsx(
                      "min-w-[235px] max-w-[235px] shrink-0 rounded-2xl border p-3 flex flex-col gap-2",
                      active ? "border-emerald-400/60" : "border-white/10"
                    )}
                    style={{ backgroundColor: "var(--bg-input)" }}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-semibold truncate">{ep.name}</span>
                      <Globe className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                    </div>
                    <span
                      className="text-[11px] font-mono truncate"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {ep.protocol} · {ep.model || "—"}
                    </span>
                    {tr && (
                      <span
                        className={clsx(
                          "text-[10px] font-mono",
                          tr.ok ? "text-emerald-300" : "text-rose-300"
                        )}
                      >
                        {tr.ok ? `OK (${tr.latency_ms}ms)` : `ERR ${tr.status_code || ""}`}
                      </span>
                    )}
                    <div className="flex items-center gap-1.5 mt-auto pt-1">
                      <button
                        type="button"
                        onClick={() => opts.onSelectEndpoint(ep.id)}
                        className="flex-1 inline-flex items-center justify-center gap-1 rounded-xl border px-2 py-1 text-xs font-medium"
                        style={{
                          borderColor: active ? "rgba(16,185,129,0.5)" : "var(--border-glass)",
                          backgroundColor: "var(--bg-elevated)",
                        }}
                      >
                        {active && <Check className="w-3 h-3 text-emerald-400" />}
                        {active ? t("models.active") : t("models.select")}
                      </button>
                      <button
                        type="button"
                        onClick={() => openEditEndpointModal(ep)}
                        title={t("models.configureEndpoint")}
                        className="inline-flex items-center justify-center rounded-xl border p-1.5 text-xs hover:border-purple-400/60"
                        style={{
                          borderColor: "var(--border-glass)",
                          backgroundColor: "var(--bg-elevated)",
                        }}
                      >
                        <SettingsIcon className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button"
                        disabled={busyKey === `test-${ep.id}`}
                        onClick={() => handleTestEndpoint(ep.id)}
                        title={t("models.test")}
                        className="inline-flex items-center justify-center rounded-xl border p-1.5 text-xs hover:border-cyan-400/50"
                        style={{
                          borderColor: "var(--border-glass)",
                          backgroundColor: "var(--bg-elevated)",
                        }}
                      >
                        <Zap className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                );
              })}

          {/* Trailing (+) Add Card */}
          <button
            type="button"
            onClick={triggerAdd}
            className="min-w-[165px] max-w-[165px] shrink-0 rounded-2xl border border-dashed p-3 flex flex-col items-center justify-center gap-2 transition-colors hover:border-cyan-400/60 text-cyan-300/85 hover:text-cyan-200"
            style={{
              borderColor: "var(--border-glass)",
              backgroundColor: "var(--bg-input)",
            }}
          >
            <div className="w-8 h-8 rounded-full border border-cyan-400/40 bg-cyan-500/10 flex items-center justify-center">
              <Plus className="w-4 h-4" />
            </div>
            <span className="text-xs font-medium text-center leading-tight">
              {isEndpoint ? t("models.addEndpoint") : t("models.addHfModel")}
            </span>
          </button>
        </div>
      </GlassCard>
    );
  };

  const selectedQuant =
    downloadTarget?.quants.find((q) => q.id === selectedQuantId) || downloadTarget?.quants[0];

  return (
    <div className="flex flex-col gap-3 pb-4">
      <div className="flex items-center gap-2 px-1 text-[11px] font-mono truncate" style={{ color: "var(--text-muted)" }}>
        <HardDrive className="w-3.5 h-3.5 shrink-0" />
        <span className="truncate">{modelsDir || "..."}</span>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
          {error}
        </div>
      )}

      {renderSection({
        kind: "tts",
        title: t("models.ttsSection"),
        accentClass: "text-purple-400",
        source: settings.tts_source,
        running: ttsRunning,
        badgeText: qwenWorker?.running
          ? `${qwenWorker.model_id || t("models.running")} · ${qwenWorker.device?.toUpperCase()}`
          : null,
        ejectLabel: t("models.ejectTts"),
        onSourceChange: (next) => onSaveSettings({ ...settings, tts_source: next }),
        localCards: ttsModels,
        endpoints: ttsEndpoints,
        activeEndpointId: settings.active_tts_endpoint_id,
        onSelectEndpoint: (id) => onSaveSettings({ ...settings, active_tts_endpoint_id: id }),
      })}

      {renderSection({
        kind: "stt",
        title: t("models.sttSection"),
        accentClass: "text-cyan-400",
        source: settings.stt_source,
        running: sttRunning,
        badgeText: sttWorker?.running
          ? `${sttWorker.model_id} · ${sttWorker.device?.toUpperCase()}`
          : null,
        ejectLabel: t("models.ejectStt"),
        onSourceChange: (next) => onSaveSettings({ ...settings, stt_source: next }),
        localCards: sttModels,
        endpoints: sttEndpoints,
        activeEndpointId: settings.active_stt_endpoint_id,
        onSelectEndpoint: (id) => onSaveSettings({ ...settings, active_stt_endpoint_id: id }),
      })}

      {/* Endpoint Create / Edit Modal */}
      {epDraft && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 backdrop-blur-sm p-4">
          <GlassCard className="w-full max-w-lg p-4 flex flex-col gap-3">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-sm font-semibold">
                {epModalMode === "create"
                  ? `${t("models.epModalCreate")} (${epDraft.kind.toUpperCase()})`
                  : `${t("models.epModalEdit")} (${epDraft.kind.toUpperCase()})`}
              </h3>
              <button
                type="button"
                onClick={() => setEpDraft(null)}
                className="opacity-70 hover:opacity-100"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {epModalMode === "create" && (
              <div className="flex flex-col gap-1">
                <span className="text-[10px] font-mono" style={{ color: "var(--text-muted)" }}>
                  {t("models.quickPresets")}
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {ENDPOINT_PRESETS[epDraft.kind].map((preset) => (
                    <button
                      key={preset.key}
                      type="button"
                      onClick={() =>
                        setEpDraft({
                          ...epDraft,
                          name: preset.name,
                          protocol: preset.protocol,
                          base_url: preset.base_url,
                          model: preset.model,
                          voice: epDraft.kind === "tts" ? preset.voice : "",
                        })
                      }
                      className="rounded-full border px-2.5 py-0.5 text-[11px] hover:border-cyan-400/60"
                      style={{
                        borderColor: "var(--border-glass)",
                        backgroundColor: "var(--bg-input)",
                      }}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              <div className="flex flex-col gap-1">
                <span className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
                  {t("models.epName")}
                </span>
                <input
                  value={epDraft.name}
                  onChange={(e) => setEpDraft({ ...epDraft, name: e.target.value })}
                  className="rounded-xl border px-3 py-1.5 text-xs outline-none"
                  style={{
                    backgroundColor: "var(--bg-input)",
                    borderColor: "var(--border-glass)",
                  }}
                />
              </div>

              <div className="flex flex-col gap-1">
                <span className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
                  {t("models.epProtocol")}
                </span>
                <select
                  value={epDraft.protocol}
                  onChange={(e) =>
                    setEpDraft({ ...epDraft, protocol: e.target.value as EndpointProtocol })
                  }
                  className="rounded-xl border px-2.5 py-1.5 text-xs outline-none"
                  style={{
                    backgroundColor: "var(--bg-input)",
                    borderColor: "var(--border-glass)",
                    color: "var(--text-primary)",
                  }}
                >
                  <option value="openai">OpenAI Compatible</option>
                  {epDraft.kind === "tts" && <option value="elevenlabs">ElevenLabs</option>}
                  {epDraft.kind === "stt" && <option value="deepgram">Deepgram</option>}
                </select>
              </div>

              <div className="sm:col-span-2 flex flex-col gap-1">
                <span className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
                  {t("settings.endpointBaseUrl")}
                </span>
                <input
                  value={epDraft.base_url}
                  onChange={(e) => setEpDraft({ ...epDraft, base_url: e.target.value })}
                  className="rounded-xl border px-3 py-1.5 text-xs font-mono outline-none"
                  style={{
                    backgroundColor: "var(--bg-input)",
                    borderColor: "var(--border-glass)",
                  }}
                />
              </div>

              <div className="sm:col-span-2 flex flex-col gap-1">
                <span className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
                  {t("settings.endpointApiKey")}
                </span>
                <div className="flex items-center gap-1.5">
                  <input
                    type={epShowKey ? "text" : "password"}
                    value={epDraft.api_key}
                    onChange={(e) => setEpDraft({ ...epDraft, api_key: e.target.value })}
                    className="flex-1 rounded-xl border px-3 py-1.5 text-xs font-mono outline-none"
                    style={{
                      backgroundColor: "var(--bg-input)",
                      borderColor: "var(--border-glass)",
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => setEpShowKey((v) => !v)}
                    className="p-1.5 rounded-xl border hover:border-purple-400/50"
                    style={{
                      borderColor: "var(--border-glass)",
                      backgroundColor: "var(--bg-elevated)",
                    }}
                  >
                    {epShowKey ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                  </button>
                </div>
              </div>

              <div className={clsx("flex flex-col gap-1", epDraft.kind === "stt" && "sm:col-span-2")}>
                <span className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
                  {t("settings.endpointModel")}
                </span>
                <input
                  value={epDraft.model}
                  onChange={(e) => setEpDraft({ ...epDraft, model: e.target.value })}
                  className="rounded-xl border px-3 py-1.5 text-xs font-mono outline-none"
                  style={{
                    backgroundColor: "var(--bg-input)",
                    borderColor: "var(--border-glass)",
                  }}
                />
              </div>

              {epDraft.kind === "tts" && (
                <div className="flex flex-col gap-1">
                  <span className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
                    {t("settings.endpointVoice")}
                  </span>
                  <input
                    value={epDraft.voice}
                    onChange={(e) => setEpDraft({ ...epDraft, voice: e.target.value })}
                    className="rounded-xl border px-3 py-1.5 text-xs font-mono outline-none"
                    style={{
                      backgroundColor: "var(--bg-input)",
                      borderColor: "var(--border-glass)",
                    }}
                  />
                </div>
              )}
            </div>

            {epModalTest && (
              <div
                className={clsx(
                  "rounded-xl border px-3 py-1.5 text-xs font-mono",
                  epModalTest.ok
                    ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                    : "border-rose-500/40 bg-rose-500/10 text-rose-300"
                )}
              >
                {epModalTest.ok
                  ? `HTTP ${epModalTest.status_code} · ${epModalTest.latency_ms}ms`
                  : `ERR ${epModalTest.status_code || ""}: ${epModalTest.detail}`}
              </div>
            )}

            <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
              <div className="flex items-center gap-2">
                {epModalMode === "edit" && (
                  <button
                    type="button"
                    onClick={handleDeleteEndpointModal}
                    className="inline-flex items-center gap-1 rounded-xl border border-rose-500/50 bg-rose-500/15 px-3 py-1.5 text-xs font-medium text-rose-200 hover:bg-rose-500/25"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    {t("profiles.delete")}
                  </button>
                )}
                <button
                  type="button"
                  disabled={epTesting || !epDraft.base_url.trim()}
                  onClick={handleTestEndpointModal}
                  className="inline-flex items-center gap-1 rounded-xl border px-3 py-1.5 text-xs font-medium hover:border-cyan-400/50 disabled:opacity-40"
                  style={{
                    borderColor: "var(--border-glass)",
                    backgroundColor: "var(--bg-elevated)",
                  }}
                >
                  {epTesting ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Zap className="w-3.5 h-3.5" />
                  )}
                  {t("models.test")}
                </button>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setEpDraft(null)}
                  className="rounded-xl border px-3 py-1.5 text-xs"
                  style={{ borderColor: "var(--border-glass)" }}
                >
                  {t("models.cancel")}
                </button>
                <button
                  type="button"
                  disabled={!epDraft.base_url.trim()}
                  onClick={handleSaveEndpointModal}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-cyan-400/60 bg-cyan-500/20 px-3.5 py-1.5 text-xs font-semibold text-cyan-200 disabled:opacity-40"
                >
                  <Check className="w-3.5 h-3.5" />
                  {t("settings.save")}
                </button>
              </div>
            </div>
          </GlassCard>
        </div>
      )}

      {/* Quantization Download Modal */}
      {downloadTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 backdrop-blur-sm p-4">
          <GlassCard className="w-full max-w-md p-4 flex flex-col gap-3">
            <div className="flex items-start justify-between gap-2">
              <div>
                <h3 className="text-sm font-semibold">{t("models.quantTitle")}</h3>
                <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
                  {downloadTarget.name} · {downloadTarget.repo_id}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setDownloadTarget(null)}
                className="opacity-70 hover:opacity-100"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {vram?.available && (
              <div
                className="rounded-xl border px-3 py-1.5 text-[11px] font-mono flex items-center justify-between"
                style={{
                  borderColor: "var(--border-glass)",
                  backgroundColor: "var(--bg-input)",
                }}
              >
                <span>
                  {t("models.vramBudget")}: {vram.gpu}
                </span>
                <span>
                  {vram.free_mib} / {vram.total_mib} MiB free
                </span>
              </div>
            )}

            <div className="flex flex-col gap-2 max-h-56 overflow-y-auto">
              {downloadTarget.quants.map((q) => {
                const selected = (selectedQuant?.id || "") === q.id;
                const fits = !vram?.available || q.vram_mib <= vram.total_mib - 400;
                return (
                  <button
                    key={q.id}
                    type="button"
                    onClick={() => setSelectedQuantId(q.id)}
                    className={clsx(
                      "rounded-xl border p-2.5 text-left flex items-center justify-between gap-2 transition-colors",
                      selected ? "border-cyan-400/70" : "border-white/10"
                    )}
                    style={{ backgroundColor: "var(--bg-input)" }}
                  >
                    <div className="flex flex-col">
                      <span className="text-xs font-semibold">{q.label}</span>
                      <span
                        className={clsx(
                          "text-[10px] font-mono",
                          fits ? "text-emerald-300" : "text-amber-300"
                        )}
                      >
                        {fits ? t("models.fitsVram") : t("models.tightVram")}
                      </span>
                    </div>
                    <div className="text-right text-[11px] font-mono">
                      <div>{formatDiskSize(q.disk_mb)}</div>
                      <div style={{ color: "var(--text-muted)" }}>
                        {formatVramSize(q.vram_mib)} VRAM
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>

            <div className="flex justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={() => setDownloadTarget(null)}
                className="rounded-xl border px-3 py-1.5 text-xs"
                style={{ borderColor: "var(--border-glass)" }}
              >
                {t("models.cancel")}
              </button>
              <button
                type="button"
                onClick={confirmDownload}
                className="inline-flex items-center gap-1.5 rounded-xl border border-cyan-400/60 bg-cyan-500/20 px-3.5 py-1.5 text-xs font-semibold text-cyan-200"
              >
                <Download className="w-3.5 h-3.5" />
                {t("models.startDownload")}
              </button>
            </div>
          </GlassCard>
        </div>
      )}

      {/* Custom Hugging Face URL Modal */}
      {hfOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 backdrop-blur-sm p-4">
          <GlassCard className="w-full max-w-lg p-4 flex flex-col gap-3">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-sm font-semibold">{t("models.hfTitle")}</h3>
              <button
                type="button"
                onClick={() => setHfOpen(false)}
                className="opacity-70 hover:opacity-100"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex gap-2">
              <input
                type="text"
                value={hfUrl}
                onChange={(e) => setHfUrl(e.target.value)}
                placeholder={t("models.hfUrlPlaceholder")}
                className="flex-1 rounded-xl border px-3 py-1.5 text-xs font-mono outline-none"
                style={{
                  borderColor: "var(--border-glass)",
                  backgroundColor: "var(--bg-input)",
                }}
              />
              <button
                type="button"
                disabled={hfInspecting || !hfUrl.trim()}
                onClick={handleInspectHf}
                className="inline-flex items-center gap-1 rounded-xl border px-3 py-1.5 text-xs font-medium hover:border-cyan-400/60 disabled:opacity-40"
                style={{
                  borderColor: "var(--border-glass)",
                  backgroundColor: "var(--bg-elevated)",
                }}
              >
                {hfInspecting ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Search className="w-3.5 h-3.5" />
                )}
                {t("models.inspect")}
              </button>
            </div>

            {hfPreview && (
              <>
                <div className="grid grid-cols-3 gap-2">
                  <div className="col-span-2 flex flex-col gap-1">
                    <span className="text-[10px] font-mono" style={{ color: "var(--text-muted)" }}>
                      {t("models.modelName")}
                    </span>
                    <input
                      type="text"
                      value={hfName}
                      onChange={(e) => setHfName(e.target.value)}
                      className="rounded-xl border px-2.5 py-1 text-xs outline-none"
                      style={{
                        borderColor: "var(--border-glass)",
                        backgroundColor: "var(--bg-input)",
                      }}
                    />
                  </div>
                  <div className="flex flex-col gap-1">
                    <span className="text-[10px] font-mono" style={{ color: "var(--text-muted)" }}>
                      {t("models.modelType")}
                    </span>
                    <select
                      value={hfKind}
                      onChange={(e) => setHfKind(e.target.value as "tts" | "stt")}
                      className="rounded-xl border px-2.5 py-1 text-xs outline-none"
                      style={{
                        borderColor: "var(--border-glass)",
                        backgroundColor: "var(--bg-input)",
                      }}
                    >
                      <option value="tts">TTS</option>
                      <option value="stt">STT</option>
                    </select>
                  </div>
                </div>

                <div className="flex flex-col gap-1">
                  <span className="text-[10px] font-mono" style={{ color: "var(--text-muted)" }}>
                    {t("models.selectFiles")}
                  </span>
                  <div
                    className="max-h-44 overflow-y-auto rounded-xl border p-2 flex flex-col gap-1"
                    style={{
                      borderColor: "var(--border-glass)",
                      backgroundColor: "var(--bg-input)",
                    }}
                  >
                    {hfPreview.files.map((f) => {
                      const checked = hfFiles.includes(f.filename);
                      return (
                        <label
                          key={f.filename}
                          className="flex items-center justify-between gap-2 text-xs font-mono cursor-pointer py-0.5"
                        >
                          <span className="flex items-center gap-2 truncate">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() =>
                                setHfFiles((prev) =>
                                  checked
                                    ? prev.filter((x) => x !== f.filename)
                                    : [...prev, f.filename]
                                )
                              }
                            />
                            <span className="truncate">{f.filename}</span>
                          </span>
                          <span className="shrink-0 opacity-70">{f.size_mb} MB</span>
                        </label>
                      );
                    })}
                  </div>
                </div>

                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setHfOpen(false)}
                    className="rounded-xl border px-3 py-1.5 text-xs"
                    style={{ borderColor: "var(--border-glass)" }}
                  >
                    {t("models.cancel")}
                  </button>
                  <button
                    type="button"
                    disabled={hfFiles.length === 0 || busyKey === "hf-install"}
                    onClick={handleInstallHf}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-cyan-400/60 bg-cyan-500/20 px-3.5 py-1.5 text-xs font-semibold text-cyan-200 disabled:opacity-40"
                  >
                    <Download className="w-3.5 h-3.5" />
                    {t("models.installSelected")}
                  </button>
                </div>
              </>
            )}
          </GlassCard>
        </div>
      )}

      {/* Remove Model Confirmation Modal */}
      {removeTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 backdrop-blur-sm p-4">
          <GlassCard className="w-full max-w-sm p-4 flex flex-col gap-3">
            <h3 className="text-sm font-semibold">{t("models.removeConfirmTitle")}</h3>
            <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
              {t("models.removeConfirmBody")} ({removeTarget.name})
            </p>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setRemoveTarget(null)}
                className="rounded-xl border px-3 py-1.5 text-xs"
                style={{ borderColor: "var(--border-glass)" }}
              >
                {t("models.cancel")}
              </button>
              <button
                type="button"
                disabled={busyKey === `rm-${removeTarget.id}`}
                onClick={confirmRemove}
                className="inline-flex items-center gap-1.5 rounded-xl border border-rose-500/60 bg-rose-500/20 px-3.5 py-1.5 text-xs font-semibold text-rose-200"
              >
                <Trash2 className="w-3.5 h-3.5" />
                {t("models.confirmRemove")}
              </button>
            </div>
          </GlassCard>
        </div>
      )}
    </div>
  );
};

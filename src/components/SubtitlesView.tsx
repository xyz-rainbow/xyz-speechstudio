import { useEffect, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import { AppWindow, Captions, ChevronDown, Monitor, RefreshCw, X } from "lucide-react";
import { clsx } from "clsx";
import { BorderBeamButton } from "./BorderBeamButton";
import { GlassCard } from "./GlassCard";
import { SttModelSelector } from "./SttModelSelector";
import { WindowPickerModal } from "./WindowPickerModal";
import { useI18n } from "../i18n";
import {
  fetchModelsCatalog,
  listAudioApps,
  loadSttWorker,
  notify,
  setCaptionsLock,
  showOverlayWindow,
  startLiveCaptions,
  stopLiveCaptions,
  toggleOverlayWindow,
  type AudioAppRow,
} from "../services/api";
import type { AppSettings, CatalogModelEntry } from "../types";

interface CaptionEvent {
  type: "partial" | "final" | "error" | "status";
  text: string;
}

function rowKey(row: AudioAppRow): string {
  if (!row.pid) return "";
  return row.stream_index == null ? String(row.pid) : `${row.pid}:${row.stream_index}`;
}

interface SubtitlesViewProps {
  baseUrl: string;
  catalog: CatalogModelEntry[];
  settings: AppSettings;
  onSaveSettings: (next: AppSettings) => Promise<void>;
  onAfterGpuAction: () => void;
  liveCaptionsSupported: boolean;
}

export const SubtitlesView: React.FC<SubtitlesViewProps> = ({
  baseUrl,
  catalog,
  settings,
  onSaveSettings,
  onAfterGpuAction,
  liveCaptionsSupported,
}) => {
  const { t } = useI18n();
  const [apps, setApps] = useState<AudioAppRow[]>([]);
  const [selected, setSelected] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [loadingApps, setLoadingApps] = useState(false);
  const [running, setRunning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState("");
  const [history, setHistory] = useState<string[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let unlisten: (() => void) | undefined;
    let disposed = false;
    listen<string>("caption", (ev) => {
      let body: CaptionEvent;
      try {
        body = JSON.parse(ev.payload) as CaptionEvent;
      } catch {
        return;
      }
      if (body.type === "error") {
        setError(body.text);
        setRunning(false);
        if (baseUrl) {
          void setCaptionsLock(baseUrl, false).catch(() => {});
        }
        return;
      }
      if (body.type === "partial") {
        setLive(body.text);
        setError("");
        return;
      }
      if (body.type === "final" && body.text.trim()) {
        setLive("");
        setHistory((prev) => {
          const next = [...prev, body.text.trim()];
          const cap = settings.captions_max_history || 20;
          return next.slice(-cap);
        });
      }
    }).then((fn) => {
      if (disposed) fn();
      else unlisten = fn;
    });
    return () => {
      disposed = true;
      unlisten?.();
    };
  }, [baseUrl, settings.captions_max_history]);

  const refreshApps = async () => {
    setError("");
    setLoadingApps(true);
    try {
      const rows = await listAudioApps();
      setApps(rows);
      setSelected((current) => {
        if (current && rows.some((row) => rowKey(row) === current)) return current;
        return rows[0] ? rowKey(rows[0]) : "";
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoadingApps(false);
    }
  };

  useEffect(() => {
    if (liveCaptionsSupported) {
      void refreshApps();
    }
  }, [liveCaptionsSupported]);

  const selectedRow = apps.find((item) => rowKey(item) === selected) || null;

  const start = async () => {
    if (!baseUrl || !selectedRow) return;
    setBusy(true);
    setError("");
    try {
      let chosenModelId = settings.active_stt_model;
      if (settings.stt_source === "local") {
        const cat = await fetchModelsCatalog(baseUrl);
        const runnable = cat.models.filter(
          (m) => m.kind === "stt" && m.installed && m.runtime_supported
        );
        if (runnable.length === 0) {
          throw new Error(t("subtitles.noSttInstalled"));
        }
        chosenModelId =
          runnable.find((m) => m.id === settings.active_stt_model)?.id || runnable[0].id;
        await loadSttWorker(baseUrl, chosenModelId, settings.stt_device);
        onAfterGpuAction();
      }
      const query =
        settings.stt_source === "local" && chosenModelId
          ? `?model_id=${encodeURIComponent(chosenModelId)}`
          : "";
      const wsUrl = baseUrl.replace(/^http/i, "ws") + `/api/captions/stream${query}`;
      await showOverlayWindow();
      await setCaptionsLock(baseUrl, true);
      setRunning(true);
      await startLiveCaptions(selectedRow.pid, wsUrl, "auto", selectedRow.stream_index);
      void notify(settings.notifications_enabled, t("toast.title"), t("toast.captionsOn"));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setRunning(false);
      await setCaptionsLock(baseUrl, false).catch(() => {});
      void notify(settings.notifications_enabled, t("toast.title"), t("toast.failed"));
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    setBusy(true);
    try {
      await stopLiveCaptions();
      if (baseUrl) await setCaptionsLock(baseUrl, false);
      onAfterGpuAction();
      void notify(settings.notifications_enabled, t("toast.title"), t("toast.captionsOff"));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      void notify(settings.notifications_enabled, t("toast.title"), t("toast.failed"));
    } finally {
      setRunning(false);
      setBusy(false);
    }
  };

  return (
    <>
      <GlassCard className="p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
            {t("subtitles.activeStt")}
          </span>
          <SttModelSelector
            catalog={catalog}
            settings={settings}
            onSaveSettings={onSaveSettings}
            disabled={running || busy}
          />
        </div>
        <BorderBeamButton onClick={() => toggleOverlayWindow()}>
          <Captions className="w-4 h-4" />
          {t("subtitles.overlay")}
        </BorderBeamButton>
      </div>

      {!liveCaptionsSupported && (
        <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
          {t("subtitles.unsupportedPlatform")}
        </p>
      )}

      {/* Discord-style Selected Source Trigger + Preview Strip */}
      <div className="flex flex-wrap items-center gap-2.5">
        <button
          type="button"
          onClick={() => {
            void refreshApps();
            setPickerOpen(true);
          }}
          disabled={!liveCaptionsSupported}
          className="flex-1 min-w-[240px] flex items-center gap-2.5 rounded-2xl border px-3 py-2 text-left hover:border-cyan-400/60 transition-colors disabled:opacity-50"
          style={{
            backgroundColor: "var(--bg-input)",
            borderColor: "var(--border-glass)",
            color: "var(--text-primary)",
          }}
        >
          <div className="w-12 h-7 rounded-lg bg-black/80 border border-white/10 overflow-hidden flex items-center justify-center shrink-0">
            {selectedRow?.thumbnail ? (
              <img
                src={selectedRow.thumbnail}
                alt=""
                className="w-full h-full object-cover"
              />
            ) : selectedRow?.icon ? (
              <img src={selectedRow.icon} alt="" className="w-4 h-4" />
            ) : (
              <Monitor className="w-3.5 h-3.5 opacity-60" />
            )}
          </div>

          <div className="min-w-0 flex-1 flex items-center gap-2">
            {selectedRow?.icon && (
              <img src={selectedRow.icon} alt="" className="w-4 h-4 rounded-sm shrink-0" />
            )}
            {!selectedRow?.icon && selectedRow && (
              <AppWindow className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
            )}
            <span className="text-xs font-medium truncate">
              {selectedRow ? selectedRow.name : t("subtitles.chooseWindow")}
            </span>
          </div>

          <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-mono border border-cyan-400/35 text-cyan-300 shrink-0">
            {t("subtitles.chooseWindow")}
            <ChevronDown className="w-3 h-3" />
          </span>
        </button>

        <button
          type="button"
          onClick={() => void refreshApps()}
          disabled={!liveCaptionsSupported || loadingApps}
          className="p-2.5 rounded-xl border disabled:opacity-50 hover:border-cyan-400/50"
          style={{ borderColor: "var(--border-glass)", color: "var(--text-secondary)" }}
          title={t("subtitles.refreshApps")}
        >
          <RefreshCw className={clsx("w-3.5 h-3.5", loadingApps && "animate-spin")} />
        </button>

        {selected && !running && (
          <button
            type="button"
            onClick={() => setSelected("")}
            disabled={!liveCaptionsSupported}
            className="p-2.5 rounded-xl border hover:border-rose-400/50 text-rose-300"
            style={{ borderColor: "var(--border-glass)" }}
            title={t("subtitles.clearWindow")}
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}

        {running ? (
          <BorderBeamButton onClick={() => void stop()} disabled={busy || !liveCaptionsSupported}>
            {t("subtitles.stop")}
          </BorderBeamButton>
        ) : (
          <BorderBeamButton
            onClick={() => void start()}
            disabled={busy || !selectedRow || !liveCaptionsSupported}
          >
            {busy ? t("subtitles.working") : t("subtitles.start")}
          </BorderBeamButton>
        )}

        <button
          type="button"
          onClick={() => {
            setHistory([]);
            setLive("");
          }}
          className="text-xs px-2"
          style={{ color: "var(--text-secondary)" }}
        >
          {t("subtitles.clear")}
        </button>
      </div>

      <div
        className="rounded-2xl border p-3.5 text-sm min-h-[48px]"
        style={{
          borderColor: "var(--border-glass)",
          backgroundColor: "var(--bg-input)",
          color: "var(--text-primary)",
        }}
      >
        {live || t("subtitles.waiting")}
      </div>

      {history.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
            {t("subtitles.history")}
          </span>
          {history.map((line, index) => (
            <p key={`${index}-${line.slice(0, 12)}`} className="text-xs leading-snug">
              {line}
            </p>
          ))}
        </div>
      )}

      {error && <p className="text-xs text-rose-300">{error}</p>}
      </GlassCard>

      <WindowPickerModal
        open={pickerOpen}
        apps={apps}
        selectedKey={selected}
        loading={loadingApps}
        rowKeyFn={rowKey}
        onRefresh={() => void refreshApps()}
        onSelect={setSelected}
        onClose={() => setPickerOpen(false)}
      />
    </>
  );
};

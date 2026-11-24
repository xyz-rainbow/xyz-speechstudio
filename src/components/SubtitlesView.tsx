import { useEffect, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import { Captions, RefreshCw } from "lucide-react";
import { BorderBeamButton } from "./BorderBeamButton";
import { GlassCard } from "./GlassCard";
import { useI18n } from "../i18n";
import {
  listAudioApps,
  loadSttWorker,
  notify,
  setCaptionsLock,
  showOverlayWindow,
  startLiveCaptions,
  stopLiveCaptions,
  toggleOverlayWindow,
} from "../services/api";
import type { AppSettings } from "../types";

interface CaptionEvent {
  type: "partial" | "final" | "error" | "status";
  text: string;
}

interface SubtitlesViewProps {
  baseUrl: string;
  settings: AppSettings;
  onAfterGpuAction: () => void;
  liveCaptionsSupported: boolean;
}

export const SubtitlesView: React.FC<SubtitlesViewProps> = ({
  baseUrl,
  settings,
  onAfterGpuAction,
  liveCaptionsSupported,
}) => {
  const { t } = useI18n();
  const [apps, setApps] = useState<{ pid: number; name: string }[]>([]);
  const [pid, setPid] = useState<number>(0);
  const [running, setRunning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState("");
  const [history, setHistory] = useState<string[]>([]);
  const [error, setError] = useState("");

  const activeLabel =
    settings.stt_source === "endpoint"
      ? settings.external_endpoints.find((ep) => ep.id === settings.active_stt_endpoint_id)?.name ||
        t("subtitles.noEndpoint")
      : settings.active_stt_model;

  useEffect(() => {
    let unlisten: (() => void) | undefined;
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
      unlisten = fn;
    });
    return () => unlisten?.();
  }, [settings.captions_max_history]);

  const refreshApps = async () => {
    setError("");
    try {
      const rows = await listAudioApps();
      setApps(rows);
      setPid((current) => (rows.some((row) => row.pid === current) ? current : rows[0]?.pid ?? 0));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  useEffect(() => {
    if (liveCaptionsSupported) {
      void refreshApps();
    }
  }, [liveCaptionsSupported]);

  const start = async () => {
    if (!baseUrl || !pid) return;
    setBusy(true);
    setError("");
    try {
      if (settings.stt_source === "local") {
        await loadSttWorker(baseUrl, settings.active_stt_model, settings.stt_device);
        onAfterGpuAction();
      }
      const wsUrl = baseUrl.replace(/^http/i, "ws") + "/api/captions/stream";
      await showOverlayWindow();
      await startLiveCaptions(pid, wsUrl, "auto");
      await setCaptionsLock(baseUrl, true);
      setRunning(true);
      void notify(settings.notifications_enabled, t("toast.title"), t("toast.captionsOn"));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setRunning(false);
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
    <GlassCard className="p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-lg font-semibold">{t("subtitles.title")}</h1>
          <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
            {t("subtitles.subtitle")}
          </p>
        </div>
        <BorderBeamButton onClick={() => toggleOverlayWindow()}>
          <Captions className="w-4 h-4" />
          {t("subtitles.overlay")}
        </BorderBeamButton>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
          {t("subtitles.activeStt")}
        </span>
        <span className="text-xs font-mono">{activeLabel}</span>
      </div>

      {!liveCaptionsSupported && (
        <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
          {t("subtitles.unsupportedPlatform")}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <select
          value={pid || ""}
          onChange={(e) => setPid(Number(e.target.value))}
          disabled={!liveCaptionsSupported}
          className="rounded-xl border px-2.5 py-1.5 text-xs outline-none min-w-[220px] disabled:opacity-50"
          style={{
            backgroundColor: "var(--bg-input)",
            borderColor: "var(--border-glass)",
            color: "var(--text-primary)",
          }}
        >
          {apps.length === 0 && <option value="">{t("subtitles.noApps")}</option>}
          {apps.map((app) => (
            <option key={app.pid} value={app.pid}>
              {app.name} · {app.pid}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => void refreshApps()}
          disabled={!liveCaptionsSupported}
          className="p-2 rounded-xl border disabled:opacity-50"
          style={{ borderColor: "var(--border-glass)", color: "var(--text-secondary)" }}
          title={t("subtitles.refreshApps")}
        >
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
        {running ? (
          <BorderBeamButton onClick={() => void stop()} disabled={busy || !liveCaptionsSupported}>
            {t("subtitles.stop")}
          </BorderBeamButton>
        ) : (
          <BorderBeamButton
            onClick={() => void start()}
            disabled={busy || !pid || !liveCaptionsSupported}
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
  );
};

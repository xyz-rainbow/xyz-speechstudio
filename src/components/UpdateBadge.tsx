import React, { useCallback, useEffect, useState } from "react";
import { getVersion } from "@tauri-apps/api/app";
import { ExternalLink, RefreshCw } from "lucide-react";
import { clsx } from "clsx";
import { useI18n } from "../i18n";
import { GlassCard } from "./GlassCard";
import {
  checkForUpdate,
  fetchUpdateProgress,
  cancelUpdate,
  installUpdate,
  isTauri,
  openUpdateRelease,
  quitApp,
  type UpdateCheck,
  type UpdateProgress,
} from "../services/api";

const SIX_HOURS_MS = 6 * 60 * 60 * 1000;

interface UpdateBadgeProps {
  baseUrl: string;
  collapsed: boolean;
  active?: boolean;
  onOpen: () => void;
}

export const UpdateBadge: React.FC<UpdateBadgeProps> = ({
  baseUrl,
  collapsed,
  active = false,
  onOpen,
}) => {
  const { t } = useI18n();
  const [version, setVersion] = useState(t("app.phaseBadge").replace(/^v/i, ""));
  const [info, setInfo] = useState<UpdateCheck | null>(null);

  useEffect(() => {
    if (!isTauri()) return;
    getVersion()
      .then((value) => setVersion(value))
      .catch(() => {});
  }, []);

  const refresh = useCallback(async () => {
    if (!baseUrl) return;
    try {
      const next = await checkForUpdate(baseUrl, version, false);
      setInfo(next);
    } catch {
      // Background check is silent on the sidebar badge.
    }
  }, [baseUrl, version]);

  useEffect(() => {
    if (!baseUrl) return;
    void refresh();
    const soon = window.setTimeout(() => void refresh(), 4000);
    const timer = window.setInterval(() => void refresh(), SIX_HOURS_MS);
    return () => {
      window.clearTimeout(soon);
      window.clearInterval(timer);
    };
  }, [baseUrl, refresh]);

  const available = Boolean(info?.update_available);
  if (collapsed && !available) return null;

  const label = available ? t("update.badge") : `v${version}`;

  return (
    <button
      type="button"
      onClick={onOpen}
      title={available ? t("update.available") : label}
      className={clsx(
        "ss-update-badge text-center",
        collapsed ? "mx-auto w-10" : "w-full",
        available && "is-available",
        active && "ring-1 ring-purple-400/60",
      )}
    >
      {available && <span className="ss-update-spin" aria-hidden />}
      <span
        className={clsx(
          "ss-update-face block truncate px-2 py-2 text-[11px] font-mono",
          available && "font-sans font-bold text-white",
        )}
      >
        {label}
      </span>
    </button>
  );
};

interface UpdatesViewProps {
  baseUrl: string;
}

export const UpdatesView: React.FC<UpdatesViewProps> = ({ baseUrl }) => {
  const { t, lang } = useI18n();
  const [version, setVersion] = useState(t("app.phaseBadge").replace(/^v/i, ""));
  const [info, setInfo] = useState<UpdateCheck | null>(null);
  const [checking, setChecking] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [progress, setProgress] = useState<UpdateProgress | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!installing) return;
    let disposed = false;
    const poll = async () => {
      try {
        const next = await fetchUpdateProgress(baseUrl);
        if (!disposed) setProgress(next);
      } catch { /* The install request reports terminal errors. */ }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 500);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [installing, baseUrl]);

  useEffect(() => {
    if (!isTauri()) return;
    getVersion()
      .then((value) => setVersion(value))
      .catch(() => {});
  }, []);

  const refresh = useCallback(
    async (force: boolean) => {
      if (!baseUrl) return;
      setChecking(true);
      setError("");
      try {
        const next = await checkForUpdate(baseUrl, version, force);
        setInfo(next);
      } catch {
        setError(t("update.error"));
      } finally {
        setChecking(false);
      }
    },
    [baseUrl, t, version],
  );

  useEffect(() => {
    if (!baseUrl) return;
    void refresh(false);
  }, [baseUrl, refresh]);

  const available = Boolean(info?.update_available);
  const dateLabel = formatReleaseDate(info?.published_at, lang);
  const canInstall = available && Boolean(info?.asset) && !installing;

  const onInstall = async () => {
    if (!canInstall) return;
    setInstalling(true);
    setProgress(null);
    setError("");
    try {
      const result = await installUpdate(baseUrl, version);
      if (result.quits_app) {
        await quitApp();
        return;
      }
      setInstalling(false);
    } catch (err) {
      const code = err instanceof Error ? err.message : "";
      setError(code === "no-asset" ? t("update.noAsset") : code === "cancelled" ? t("update.cancelled") : t("update.installError"));
      setInstalling(false);
    }
  };

  return (
    <GlassCard className="flex-1 min-h-0 p-5 flex flex-col gap-4 overflow-y-auto">
      <div className="flex flex-col gap-1">
        <p className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
          {available ? t("update.available") : info ? t("update.upToDate") : t("update.checking")}
        </p>
      </div>

      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-xs max-w-md">
        <dt style={{ color: "var(--text-muted)" }}>{t("update.installed")}</dt>
        <dd className="font-mono">v{version}</dd>
        <dt style={{ color: "var(--text-muted)" }}>{t("update.latest")}</dt>
        <dd className="font-mono">{info?.latest ? `v${info.latest}` : "—"}</dd>
        <dt style={{ color: "var(--text-muted)" }}>{t("update.released")}</dt>
        <dd>{dateLabel}</dd>
      </dl>

      <div className="flex flex-col gap-1.5 flex-1 min-h-0">
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
          {t("update.notes")}
        </span>
        <div
          className="flex-1 min-h-[120px] max-h-72 overflow-auto rounded-xl border px-3.5 py-2.5 text-xs whitespace-pre-wrap"
          style={{
            borderColor: "var(--border-glass)",
            backgroundColor: "var(--bg-input)",
            color: "var(--text-secondary)",
          }}
        >
          {info?.notes || t("update.noNotes")}
        </div>
      </div>

      {available && info?.platform === "win32" && info.asset && (
        <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
          {t("update.willQuit")}
        </p>
      )}
      {available && !info?.asset && (
        <p className="text-xs text-amber-300">{t("update.noAsset")}</p>
      )}
      {error && <p className="text-xs text-rose-300">{error}</p>}

      {installing && (
        <div className="flex items-center gap-3 text-xs">
          <progress className="flex-1" aria-label={t("update.installing")}
            value={progress?.total ? progress.downloaded : undefined}
            max={progress?.total || 1} />
          {progress && progress.total > 0 && <span>{Math.min(100, Math.round(progress.downloaded / progress.total * 100))}%</span>}
          <button type="button" onClick={() => void cancelUpdate(baseUrl).catch(() => setError(t("update.installError")))}>
            {t("update.cancel")}
          </button>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 pt-1">
        <button
          type="button"
          disabled={!canInstall}
          onClick={() => void onInstall()}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-lime-400 bg-lime-500/15 hover:bg-lime-500/25 disabled:opacity-40 px-4 py-2 text-xs font-semibold text-white transition-colors"
        >
          {installing ? t("update.installing") : t("update.install")}
        </button>
        <button
          type="button"
          disabled={checking || !baseUrl}
          onClick={() => void refresh(true)}
          className="inline-flex items-center justify-center gap-2 rounded-xl border px-4 py-2 text-xs font-medium transition-colors disabled:opacity-40"
          style={{ borderColor: "var(--border-glass)", color: "var(--text-primary)" }}
        >
          <RefreshCw className={clsx("w-3.5 h-3.5", checking && "animate-spin")} />
          {checking ? t("update.checking") : t("update.check")}
        </button>
        <button
          type="button"
          disabled={!baseUrl}
          onClick={() => void openUpdateRelease(baseUrl, version).catch(() => setError(t("update.error")))}
          className="inline-flex items-center justify-center gap-2 rounded-xl border px-4 py-2 text-xs font-medium transition-colors disabled:opacity-40"
          style={{ borderColor: "var(--border-glass)", color: "var(--text-secondary)" }}
        >
          <ExternalLink className="w-3.5 h-3.5" />
          {t("update.github")}
        </button>
      </div>
    </GlassCard>
  );
};

function formatReleaseDate(value: string | null | undefined, lang: string): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(lang === "es" ? "es-ES" : "en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

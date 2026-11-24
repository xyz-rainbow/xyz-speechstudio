import React, { useCallback, useEffect, useState } from "react";
import { getVersion } from "@tauri-apps/api/app";
import { ExternalLink, RefreshCw, X } from "lucide-react";
import { clsx } from "clsx";
import { useI18n } from "../i18n";
import { GlassCard } from "./GlassCard";
import {
  checkForUpdate,
  installUpdate,
  isTauri,
  openUpdateRelease,
  quitApp,
  type UpdateCheck,
} from "../services/api";

const SIX_HOURS_MS = 6 * 60 * 60 * 1000;

interface UpdateBadgeProps {
  baseUrl: string;
  collapsed: boolean;
}

export const UpdateBadge: React.FC<UpdateBadgeProps> = ({ baseUrl, collapsed }) => {
  const { t, lang } = useI18n();
  const [version, setVersion] = useState(t("app.phaseBadge").replace(/^v/i, ""));
  const [info, setInfo] = useState<UpdateCheck | null>(null);
  const [open, setOpen] = useState(false);
  const [checking, setChecking] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [error, setError] = useState("");

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
    const soon = window.setTimeout(() => void refresh(false), 4000);
    const timer = window.setInterval(() => void refresh(false), SIX_HOURS_MS);
    return () => {
      window.clearTimeout(soon);
      window.clearInterval(timer);
    };
  }, [baseUrl, refresh]);

  const available = Boolean(info?.update_available);
  if (collapsed && !available) return null;

  const label = available ? t("update.badge") : `v${version}`;
  const dateLabel = formatReleaseDate(info?.published_at, lang);
  const canInstall = available && Boolean(info?.asset) && !installing;

  const onInstall = async () => {
    if (!canInstall) return;
    setInstalling(true);
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
      setError(code === "no-asset" ? t("update.noAsset") : t("update.error"));
      setInstalling(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        title={available ? t("update.available") : label}
        className={clsx(
          "ss-update-badge text-center",
          collapsed ? "mx-auto w-10" : "w-full",
          available && "is-available",
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

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4"
          onClick={() => setOpen(false)}
        >
          <div className="w-full max-w-md" onClick={(event) => event.stopPropagation()}>
          <GlassCard className="p-5 flex flex-col gap-3">
            <div className="flex items-start justify-between gap-2">
              <h3 className="text-sm font-semibold">{t("update.title")}</h3>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="p-1 rounded-lg opacity-70 hover:opacity-100"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
              {available ? t("update.available") : info ? t("update.upToDate") : t("update.checking")}
            </p>

            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
              <dt style={{ color: "var(--text-muted)" }}>{t("update.installed")}</dt>
              <dd className="font-mono">v{version}</dd>
              <dt style={{ color: "var(--text-muted)" }}>{t("update.latest")}</dt>
              <dd className="font-mono">{info?.latest ? `v${info.latest}` : "—"}</dd>
              <dt style={{ color: "var(--text-muted)" }}>{t("update.released")}</dt>
              <dd>{dateLabel}</dd>
            </dl>

            <div className="flex flex-col gap-1">
              <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>
                {t("update.notes")}
              </span>
              <div
                className="max-h-32 overflow-auto rounded-xl border px-3 py-2 text-xs whitespace-pre-wrap"
                style={{ borderColor: "var(--border-glass)", color: "var(--text-secondary)" }}
              >
                {info?.notes || t("update.noNotes")}
              </div>
            </div>

            {available && info?.platform === "win32" && info.asset && (
              <p className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
                {t("update.willQuit")}
              </p>
            )}
            {available && !info?.asset && (
              <p className="text-[11px] text-amber-300">{t("update.noAsset")}</p>
            )}
            {error && <p className="text-[11px] text-rose-300">{error}</p>}

            <div className="flex flex-col gap-2">
              <button
                type="button"
                disabled={!canInstall}
                onClick={() => void onInstall()}
                className="w-full inline-flex items-center justify-center gap-2 rounded-xl border border-lime-400 bg-lime-500/15 hover:bg-lime-500/25 disabled:opacity-40 px-4 py-2.5 text-sm font-semibold text-white transition-colors"
              >
                {installing ? t("update.installing") : t("update.install")}
              </button>
              <button
                type="button"
                disabled={checking || !baseUrl}
                onClick={() => void refresh(true)}
                className="w-full inline-flex items-center justify-center gap-2 rounded-xl border px-4 py-2 text-sm font-medium transition-colors disabled:opacity-40"
                style={{ borderColor: "var(--border-glass)", color: "var(--text-primary)" }}
              >
                <RefreshCw className={clsx("w-4 h-4", checking && "animate-spin")} />
                {checking ? t("update.checking") : t("update.check")}
              </button>
              <button
                type="button"
                disabled={!baseUrl}
                onClick={() => void openUpdateRelease(baseUrl, version).catch(() => setError(t("update.error")))}
                className="w-full inline-flex items-center justify-center gap-2 rounded-xl border px-4 py-2 text-sm font-medium transition-colors disabled:opacity-40"
                style={{ borderColor: "var(--border-glass)", color: "var(--text-secondary)" }}
              >
                <ExternalLink className="w-4 h-4" />
                {t("update.github")}
              </button>
            </div>
          </GlassCard>
          </div>
        </div>
      )}
    </>
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

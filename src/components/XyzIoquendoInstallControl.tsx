import { useCallback, useEffect, useState } from "react";
import { Download, Loader2, RefreshCw, Trash2, Wrench } from "lucide-react";
import { useI18n } from "../i18n";
import { startModelDownload } from "../services/api";
import {
  XYZ_IOQUENDO_PACK_ID,
  XYZ_IOQUENDO_REQUIRED_MODEL_ID,
  XYZ_IOQUENDO_REQUIRED_QUANT_ID,
  fetchXyzIoquendoStatus,
  installXyzIoquendoFromLocalBundle,
  type PackInstallStatus,
} from "../lib/xyzIoquendo";

interface Props {
  baseUrl: string;
  onRefresh: () => Promise<void>;
}

async function repairPack(baseUrl: string): Promise<void> {
  const res = await fetch(
    `${baseUrl.replace(/\/$/, "")}/api/voice-packs/${XYZ_IOQUENDO_PACK_ID}/repair`,
    { method: "POST" },
  );
  if (!res.ok) throw new Error((await res.text()) || `Repair failed: HTTP ${res.status}`);
}

async function uninstallPack(baseUrl: string): Promise<void> {
  const res = await fetch(
    `${baseUrl.replace(/\/$/, "")}/api/voice-packs/${XYZ_IOQUENDO_PACK_ID}`,
    { method: "DELETE" },
  );
  if (!res.ok) throw new Error((await res.text()) || `Uninstall failed: HTTP ${res.status}`);
}

export function XyzIoquendoInstallControl({ baseUrl, onRefresh }: Props) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState<PackInstallStatus | null>(null);

  const refreshStatus = useCallback(async () => {
    if (!baseUrl) return;
    try {
      const next = await fetchXyzIoquendoStatus(baseUrl);
      setStatus(next);
      setError("");
    } catch (failure) {
      setStatus(null);
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }, [baseUrl]);

  useEffect(() => {
    void refreshStatus();
  }, [refreshStatus]);

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await action();
      await onRefresh();
      await refreshStatus();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  };

  const q4Ready = Boolean(status?.dependency?.qwen_q4_installed);
  const installed = Boolean(status?.installed);

  return (
    <div className="mt-auto flex flex-col gap-1.5 pt-0.5">
      <p
        className="text-[10px] leading-snug line-clamp-2"
        style={{ color: "var(--text-secondary)" }}
        title={t("xyzIoquendo.blurb")}
      >
        {t("xyzIoquendo.blurb")}
      </p>
      {!q4Ready && (
        <p
          className="text-[10px] leading-snug line-clamp-2 text-amber-300/90"
          title={t("xyzIoquendo.needsQwenQ4")}
        >
          {t("xyzIoquendo.needsQwenQ4")}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-1">
        {!q4Ready && (
          <button
            type="button"
            disabled={!baseUrl || busy}
            onClick={() =>
              void run(async () => {
                await startModelDownload(
                  baseUrl,
                  XYZ_IOQUENDO_REQUIRED_MODEL_ID,
                  XYZ_IOQUENDO_REQUIRED_QUANT_ID,
                );
              })
            }
            className="inline-flex items-center gap-1 rounded-xl border px-2 py-1 text-[11px] text-cyan-300 disabled:opacity-40"
            style={{ borderColor: "var(--border-glass)" }}
          >
            {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Download className="h-3 w-3" />}
            {t("xyzIoquendo.installQwenQ4")}
          </button>
        )}
        {!installed ? (
          <button
            type="button"
            disabled={!baseUrl || busy}
            onClick={() => void run(() => installXyzIoquendoFromLocalBundle(baseUrl))}
            className="inline-flex items-center gap-1 rounded-xl border px-2 py-1 text-[11px] text-cyan-300 disabled:opacity-40"
            style={{ borderColor: "var(--border-glass)" }}
          >
            {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Download className="h-3 w-3" />}
            {t("xyzIoquendo.installPack")}
          </button>
        ) : (
          <>
            <span className="rounded-full px-2 py-0.5 text-[10px] font-mono bg-emerald-500/15 text-emerald-300 border border-emerald-500/35">
              {t("xyzIoquendo.installed")} · {status?.voice_count ?? 0}
            </span>
            <button
              type="button"
              disabled={!baseUrl || busy}
              onClick={() => void run(() => repairPack(baseUrl))}
              className="inline-flex items-center gap-1 rounded-xl border px-2 py-1 text-[11px] disabled:opacity-40"
              style={{ borderColor: "var(--border-glass)", color: "var(--text-primary)" }}
            >
              <Wrench className="h-3 w-3" />
              {t("xyzIoquendo.repair")}
            </button>
            <button
              type="button"
              disabled={!baseUrl || busy}
              onClick={() => void run(() => uninstallPack(baseUrl))}
              className="inline-flex items-center justify-center rounded-xl border p-1 text-rose-300 disabled:opacity-40 hover:border-rose-400/60"
              style={{ borderColor: "var(--border-glass)" }}
              title={t("xyzIoquendo.uninstall")}
              aria-label={t("xyzIoquendo.uninstall")}
            >
              <Trash2 className="h-3 w-3" />
            </button>
          </>
        )}
        <button
          type="button"
          disabled={!baseUrl || busy}
          onClick={() => void refreshStatus()}
          className="inline-flex items-center justify-center rounded-xl border p-1 disabled:opacity-40 hover:border-cyan-400/50"
          style={{ borderColor: "var(--border-glass)", color: "var(--text-primary)" }}
          title={t("xyzIoquendo.refresh")}
          aria-label={t("xyzIoquendo.refresh")}
        >
          <RefreshCw className="h-3 w-3" />
        </button>
      </div>
      {error && (
        <p className="text-xs text-rose-300" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

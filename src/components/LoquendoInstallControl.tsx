import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { FolderOpen, Loader2, RefreshCw } from "lucide-react";
import { useI18n } from "../i18n";
import { installLoquendo, refreshLoquendo } from "../services/api";
import { pickFile } from "../services/fileDialog";

interface Props {
  baseUrl: string;
  supported: boolean;
  onRefresh: () => Promise<void>;
}

export function LoquendoInstallControl({ baseUrl, supported, onRefresh }: Props) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [launched, setLaunched] = useState(false);
  const [error, setError] = useState("");
  const [pendingSource, setPendingSource] = useState<string | null>(null);
  const [licenseConfirmed, setLicenseConfirmed] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);
  const busyRef = useRef(busy);
  busyRef.current = busy;
  const dialogTitleId = useId();

  useEffect(() => {
    if (!pendingSource) return;
    const previousFocus = document.activeElement;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busyRef.current) setPendingSource(null);
      if (event.key !== "Tab") return;
      const elements = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled)") ?? []);
      if (elements.length === 0) {
        event.preventDefault();
        return;
      }
      const first = elements[0];
      const last = elements[elements.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      if (previousFocus instanceof HTMLElement) previousFocus.focus();
    };
  }, [pendingSource]);

  const install = async () => {
    setBusy(true);
    setError("");
    try {
      const source = await pickFile({
        title: t("loquendo.selectInstaller"),
        filters: [{ name: t("loquendo.installerFilter"), extensions: ["exe", "msi"] }],
      });
      if (source) {
        setPendingSource(source);
        setLicenseConfirmed(false);
      }
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  };

  const confirmInstall = async () => {
    if (!pendingSource || !licenseConfirmed) return;
    setBusy(true);
    setError("");
    try {
      await installLoquendo(baseUrl, pendingSource);
      setPendingSource(null);
      setLaunched(true);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
      setPendingSource(null);
    } finally {
      setBusy(false);
    }
  };

  const rescan = async () => {
    setBusy(true);
    setError("");
    try {
      await refreshLoquendo(baseUrl);
      await onRefresh();
      setLaunched(false);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-auto flex flex-col gap-1.5 pt-0.5">
      <p
        className="text-[10px] leading-snug line-clamp-2"
        style={{ color: "var(--text-secondary)" }}
        title={supported ? t(launched ? "loquendo.finishInstaller" : "loquendo.installerRequired") : t("loquendo.windowsOnly")}
      >
        {supported ? t(launched ? "loquendo.finishInstaller" : "loquendo.installerRequired") : t("loquendo.windowsOnly")}
      </p>
      <div className="flex flex-wrap gap-1">
        <button
          type="button"
          disabled={!supported || !baseUrl || busy}
          onClick={() => void install()}
          className="inline-flex items-center gap-1 rounded-xl border px-2 py-1 text-[11px] text-cyan-300 disabled:opacity-40"
          style={{ borderColor: "var(--border-glass)" }}
        >
          {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <FolderOpen className="h-3 w-3" />}
          {t("loquendo.installLocal")}
        </button>
        <button
          type="button"
          disabled={!supported || !baseUrl || busy}
          onClick={() => void rescan()}
          className="inline-flex items-center gap-1 rounded-xl border px-2 py-1 text-[11px] disabled:opacity-40"
          style={{ borderColor: "var(--border-glass)", color: "var(--text-primary)" }}
        >
          <RefreshCw className="h-3 w-3" />
          {t("loquendo.rescan")}
        </button>
      </div>
      {error && <p className="text-xs text-rose-300" role="alert">{error}</p>}
      {pendingSource && createPortal(
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-5">
          <div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby={dialogTitleId}
            className="w-full max-w-md rounded-2xl border p-5 shadow-2xl flex flex-col gap-4"
            style={{ borderColor: "var(--border-glass)", background: "var(--bg-elevated)", color: "var(--text-primary)" }}
          >
            <h2 id={dialogTitleId} className="font-semibold">{t("loquendo.confirmTitle")}</h2>
            <p className="text-sm leading-relaxed">{t("loquendo.licenseNotice")}</p>
            <p className="text-xs break-all font-mono">{pendingSource.split(/[\\/]/).pop()}</p>
            <label className="flex items-start gap-2 text-xs leading-relaxed">
              <input autoFocus type="checkbox" disabled={busy} checked={licenseConfirmed} onChange={(event) => setLicenseConfirmed(event.target.checked)} className="mt-0.5" />
              {t("loquendo.licenseConfirm")}
            </label>
            <div className="flex justify-end gap-2">
              <button type="button" disabled={busy} onClick={() => setPendingSource(null)} className="rounded-xl border px-3 py-2 text-xs" style={{ borderColor: "var(--border-glass)" }}>{t("loquendo.cancel")}</button>
              <button type="button" disabled={!licenseConfirmed || busy} onClick={() => void confirmInstall()} className="rounded-xl border border-cyan-400/50 px-3 py-2 text-xs text-cyan-300 disabled:opacity-40">{t("loquendo.openInstaller")}</button>
            </div>
          </div>
        </div>, document.body,
      )}
    </div>
  );
}

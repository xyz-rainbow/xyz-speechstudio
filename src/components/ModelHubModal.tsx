import React, { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Download,
  File as FileIcon,
  FolderOpen,
  Loader2,
  Search,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { clsx } from "clsx";
import { useI18n } from "../i18n";
import {
  cancelModelDownload,
  importLocalModel,
  inspectModelUrl,
  installModelFromUrl,
  searchModelHub,
  startModelDownload,
  uninstallLanguagePack,
} from "../services/api";
import { pickFile, pickFolder } from "../services/fileDialog";
import type {
  CatalogModelEntry,
  DownloadJob,
  HfInspectResponse,
  HubModelSummary,
  InstallMode,
  VramStatus,
} from "../types";
import { GlassCard } from "./GlassCard";
import { LoquendoInstallControl } from "./LoquendoInstallControl";

interface ModelHubModalProps {
  open: boolean;
  kind: "tts" | "stt";
  baseUrl: string;
  catalog: CatalogModelEntry[];
  downloads: DownloadJob[];
  vram: VramStatus | null;
  installedLanguages?: Record<string, string[]>;
  onClose: () => void;
  onRefreshCatalog: () => Promise<void>;
  onRequestRemove: (entry: CatalogModelEntry) => void;
  onInstalledLanguagesChange?: (next: Record<string, string[]>) => void;
}

interface FamilyGroup {
  familyId: string;
  familyName: string;
  variants: CatalogModelEntry[];
}

function formatDiskSize(mb: number): string {
  if (!mb || mb <= 0) return "—";
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb} MB`;
}

function formatVramSize(mib: number): string {
  if (!mib || mib <= 0) return "—";
  return mib >= 1024 ? `~${(mib / 1024).toFixed(1)} GB` : `~${mib} MB`;
}

function installModeHintKey(mode: InstallMode): string {
  if (mode === "per_language_checkpoint") return "models.installModePerLanguage";
  if (mode === "voices_pack") return "models.installModeVoices";
  return "models.installModeShared";
}

function familyLanguages(variants: CatalogModelEntry[]): string[] {
  const set = new Set<string>();
  for (const v of variants) {
    for (const lang of v.capabilities?.languages ?? []) set.add(lang);
  }
  return Array.from(set);
}

function variantForLanguage(
  variants: CatalogModelEntry[],
  language: string | undefined,
): CatalogModelEntry {
  if (language) {
    const match = variants.find((v) => (v.capabilities?.languages ?? []).includes(language));
    if (match) return match;
  }
  return variants[0];
}

export const ModelHubModal: React.FC<ModelHubModalProps> = ({
  open,
  kind,
  baseUrl,
  catalog,
  downloads,
  vram,
  installedLanguages = {},
  onClose,
  onRefreshCatalog,
  onRequestRemove,
  onInstalledLanguagesChange,
}) => {
  const { t } = useI18n();
  const [tab, setTab] = useState<"featured" | "hub" | "import">("featured");
  const [error, setError] = useState<string | null>(null);
  const [langChoice, setLangChoice] = useState<Record<string, string>>({});
  const [pendingLangRemove, setPendingLangRemove] = useState<{
    familyId: string;
    language: string;
    mode: InstallMode;
  } | null>(null);

  // Featured state
  const [featuredPage, setFeaturedPage] = useState(1);
  const [variantChoice, setVariantChoice] = useState<Record<string, string>>({});
  const [quantChoice, setQuantChoice] = useState<Record<string, string>>({});
  const [installingId, setInstallingId] = useState<string | null>(null);

  // Hub Search state
  const [hubQuery, setHubQuery] = useState("");
  const [hubSubmittedQuery, setHubSubmittedQuery] = useState("");
  const [hubReadyOnly, setHubReadyOnly] = useState(true);
  const [hubPage, setHubPage] = useState(1);
  const [hubLoading, setHubLoading] = useState(false);
  const [hubItems, setHubItems] = useState<HubModelSummary[]>([]);
  const [hubHasMore, setHubHasMore] = useState(false);
  const [hubInspecting, setHubInspecting] = useState(false);

  // Shared URL inspect preview (used by both Hub click and Import URL)
  const [inspectPreview, setInspectPreview] = useState<HfInspectResponse | null>(null);
  const [inspectName, setInspectName] = useState("");
  const [inspectFiles, setInspectFiles] = useState<string[]>([]);
  const [convertToGguf, setConvertToGguf] = useState(false);
  const [installingUrl, setInstallingUrl] = useState(false);

  // Import tab state
  const [importUrl, setImportUrl] = useState("");
  const [urlInspecting, setUrlInspecting] = useState(false);
  const [localPath, setLocalPath] = useState("");
  const [localName, setLocalName] = useState("");
  const [importingLocal, setImportingLocal] = useState(false);

  useEffect(() => {
    if (!open) return;
    setTab("featured");
    setFeaturedPage(1);
    setHubPage(1);
    setInspectPreview(null);
    setConvertToGguf(false);
    setError(null);
  }, [open, kind]);

  const loadHub = async (query: string, page: number, readyOnly: boolean) => {
    if (!baseUrl) return;
    setHubLoading(true);
    setError(null);
    try {
      const res = await searchModelHub(baseUrl, kind, query, page, 6, readyOnly);
      setHubItems(res.items);
      setHubHasMore(res.has_more);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setHubLoading(false);
    }
  };

  useEffect(() => {
    if (!open || tab !== "hub") return;
    void loadHub(hubSubmittedQuery, hubPage, hubReadyOnly);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, tab, kind, hubPage, hubSubmittedQuery, hubReadyOnly]);

  const families: FamilyGroup[] = useMemo(() => {
    const map = new Map<string, FamilyGroup>();
    for (const m of catalog) {
      if (m.kind !== kind || m.custom) continue;
      const fid = m.family_id || m.id;
      const existing = map.get(fid);
      if (existing) {
        existing.variants.push(m);
      } else {
        map.set(fid, {
          familyId: fid,
          familyName: m.family_name || m.name,
          variants: [m],
        });
      }
    }
    return Array.from(map.values());
  }, [catalog, kind]);

  const PAGE_SIZE = 4;
  const totalFeaturedPages = Math.max(1, Math.ceil(families.length / PAGE_SIZE));
  const safeFeaturedPage = Math.min(featuredPage, totalFeaturedPages);
  const pagedFamilies = families.slice(
    (safeFeaturedPage - 1) * PAGE_SIZE,
    safeFeaturedPage * PAGE_SIZE
  );

  if (!open) return null;

  const activeJobFor = (modelId: string) =>
    downloads.find(
      (d) => d.model_id === modelId && (d.status === "queued" || d.status === "downloading")
    );

  const runInspectUrl = async (target: string) => {
    if (!baseUrl || !target.trim()) return;
    setError(null);
    setConvertToGguf(false);
    const res = await inspectModelUrl(baseUrl, target.trim());
    setInspectPreview(res);
    setInspectName(res.suggested_name);
    const defaults = res.files
      .filter(
        (f) => f.recommended || f.filename.endsWith(".json") || f.filename.endsWith(".txt")
      )
      .map((f) => f.filename);
    setInspectFiles(defaults.length ? defaults : res.files.slice(0, 4).map((f) => f.filename));
  };

  const handleInstallInspected = async () => {
    if (!baseUrl || !inspectPreview || inspectFiles.length === 0) return;
    const hasSelectedGguf = inspectFiles.some((f) => f.toLowerCase().endsWith(".gguf"));
    const readyNow = Boolean(inspectPreview.crispasr_ready) || hasSelectedGguf;
    if (!readyNow && !(convertToGguf && inspectPreview.can_convert_gguf)) {
      setError(inspectPreview.crispasr_reason || t("models.notReadyReason"));
      return;
    }
    setInstallingUrl(true);
    setError(null);
    try {
      const directUrls: Record<string, string> = {};
      for (const f of inspectPreview.files) {
        if (f.download_url && inspectFiles.includes(f.filename)) {
          directUrls[f.filename] = f.download_url;
        }
      }
      await installModelFromUrl(baseUrl, {
        source: inspectPreview.source,
        repo_id: inspectPreview.repo_id,
        name: inspectName.trim() || inspectPreview.suggested_name,
        kind,
        files: inspectFiles,
        direct_urls: directUrls,
        crispasr_ready: readyNow,
        crispasr_backend: inspectPreview.crispasr_backend ?? null,
        convert_to_gguf: !readyNow && convertToGguf,
        convert_script: inspectPreview.convert_script ?? null,
      });
      await onRefreshCatalog();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setInstallingUrl(false);
    }
  };

  const pickLocal = async (directory: boolean) => {
    setError(null);
    try {
      const selected = directory ? await pickFolder() : await pickFile();
      if (selected) {
        setLocalPath(selected);
        if (!localName.trim()) {
          const base = selected.split(/[\\/]/).filter(Boolean).pop() || "";
          setLocalName(base.replace(/\.[^.]+$/, ""));
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleImportLocal = async () => {
    if (!baseUrl || !localPath.trim()) return;
    setImportingLocal(true);
    setError(null);
    try {
      const fallbackName =
        localPath.trim().split(/[\\/]/).filter(Boolean).pop()?.replace(/\.[^.]+$/, "") ||
        "local-model";
      await importLocalModel(baseUrl, {
        source_path: localPath.trim(),
        name: localName.trim() || fallbackName,
        kind,
      });
      await onRefreshCatalog();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setImportingLocal(false);
    }
  };

  const renderInspectPanel = (onBack?: () => void) => {
    if (!inspectPreview) return null;
    const hasSelectedGguf = inspectFiles.some((f) => f.toLowerCase().endsWith(".gguf"));
    const readyNow = Boolean(inspectPreview.crispasr_ready) || hasSelectedGguf;
    const canInstallNow =
      inspectFiles.length > 0 &&
      !installingUrl &&
      (readyNow || (convertToGguf && Boolean(inspectPreview.can_convert_gguf)));

    return (
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          {onBack && (
            <button
              type="button"
              onClick={onBack}
              className="inline-flex items-center gap-1 rounded-xl border px-2.5 py-1 text-xs hover:border-cyan-400/50"
              style={{ borderColor: "var(--border-glass)", backgroundColor: "var(--bg-elevated)" }}
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              {t("models.backToResults")}
            </button>
          )}
          <div className="flex items-center gap-2 ml-auto min-w-0">
            <span className="text-[11px] font-mono truncate" style={{ color: "var(--text-muted)" }}>
              {inspectPreview.source.toUpperCase()} · {inspectPreview.repo_id}
            </span>
            <span
              className={clsx(
                "rounded-full px-2 py-0.5 text-[10px] font-mono font-semibold border shrink-0",
                readyNow
                  ? "bg-emerald-500/20 text-emerald-300 border-emerald-400/50"
                  : "bg-rose-500/20 text-rose-300 border-rose-400/50"
              )}
            >
              {readyNow ? t("models.crispReady") : t("models.crispNotReady")}
            </span>
          </div>
        </div>

        {!readyNow && (
          <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-200 flex flex-col gap-2">
            <span>{inspectPreview.crispasr_reason || t("models.notReadyReason")}</span>
            {inspectPreview.can_convert_gguf && inspectPreview.convert_script && (
              <label className="inline-flex items-center gap-2 text-[11px] font-mono text-amber-200 cursor-pointer">
                <input
                  type="checkbox"
                  checked={convertToGguf}
                  onChange={(e) => setConvertToGguf(e.target.checked)}
                />
                <span>
                  {t("models.convertGgufOption")} ({inspectPreview.convert_script})
                </span>
              </label>
            )}
          </div>
        )}

        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-mono" style={{ color: "var(--text-muted)" }}>
            {t("models.modelName")}
          </span>
          <input
            value={inspectName}
            onChange={(e) => setInspectName(e.target.value)}
            className="rounded-xl border px-2.5 py-1.5 text-xs outline-none"
            style={{ borderColor: "var(--border-glass)", backgroundColor: "var(--bg-input)" }}
          />
        </div>

        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-mono" style={{ color: "var(--text-muted)" }}>
            {t("models.selectFiles")}
          </span>
          <div
            className="max-h-48 overflow-y-auto rounded-xl border p-2 flex flex-col gap-1"
            style={{ borderColor: "var(--border-glass)", backgroundColor: "var(--bg-input)" }}
          >
            {inspectPreview.files.map((f) => {
              const checked = inspectFiles.includes(f.filename);
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
                        setInspectFiles((prev) =>
                          checked ? prev.filter((x) => x !== f.filename) : [...prev, f.filename]
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
            disabled={!canInstallNow}
            onClick={handleInstallInspected}
            className="inline-flex items-center gap-1.5 rounded-xl border border-cyan-400/60 bg-cyan-500/20 px-3.5 py-1.5 text-xs font-semibold text-cyan-200 disabled:opacity-40"
          >
            {installingUrl ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Download className="w-3.5 h-3.5" />
            )}
            {t("models.installSelected")}
          </button>
        </div>
      </div>
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <GlassCard className="w-full max-w-3xl max-h-[88vh] p-4 flex flex-col gap-3 overflow-hidden">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-2 shrink-0">
          <div className="flex items-center gap-2.5">
            <Sparkles className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-semibold">
              {kind === "tts" ? t("models.ttsSection") : t("models.sttSection")}
            </h3>
            {vram?.available && (
              <span
                className="rounded-full px-2.5 py-0.5 text-[10px] font-mono border"
                style={{
                  borderColor: "var(--border-glass)",
                  backgroundColor: "var(--bg-input)",
                  color: "var(--text-secondary)",
                }}
              >
                {vram.free_mib} / {vram.total_mib} MiB {t("topbar.free")}
              </span>
            )}
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg opacity-70 hover:opacity-100"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* 3 Tabs */}
        <div className="flex items-center gap-1.5 border-b border-white/10 pb-2 shrink-0">
          {(
            [
              { id: "featured", label: t("models.tabFeatured") },
              { id: "hub", label: t("models.tabHub") },
              { id: "import", label: t("models.tabImport") },
            ] as const
          ).map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => {
                setTab(item.id);
                setInspectPreview(null);
                setError(null);
              }}
              className={clsx(
                "rounded-full px-3.5 py-1 text-xs font-medium border transition-colors",
                tab === item.id
                  ? "border-cyan-400/60 bg-cyan-500/20 text-cyan-200"
                  : "border-transparent opacity-70 hover:opacity-100"
              )}
            >
              {item.label}
            </button>
          ))}
        </div>

        {error && (
          <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 px-3 py-1.5 text-xs text-rose-300 shrink-0">
            {error}
          </div>
        )}

        {/* Body */}
        <div className="flex-1 min-h-0 overflow-y-auto pr-1 flex flex-col gap-3">
          {tab === "featured" && (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {pagedFamilies.map((fam) => {
                  const installMode =
                    fam.variants[0]?.capabilities?.install_mode ?? "shared_weights";
                  const langs = familyLanguages(fam.variants);
                  const selectedLang =
                    langChoice[fam.familyId] ||
                    langs.find((l) =>
                      fam.variants.some(
                        (v) =>
                          (v.capabilities?.languages ?? []).includes(l) && v.installed,
                      ),
                    ) ||
                    langs[0];
                  const chosenVarId = variantChoice[fam.familyId];
                  const variant = chosenVarId
                    ? fam.variants.find((v) => v.id === chosenVarId) ||
                      variantForLanguage(fam.variants, selectedLang)
                    : variantForLanguage(fam.variants, selectedLang);
                  const recQuant =
                    variant.quants.find((q) => q.recommended) || variant.quants[0];
                  const chosenQId = quantChoice[variant.id] || recQuant?.id || "";
                  const quant =
                    variant.quants.find((q) => q.id === chosenQId) || recQuant;
                  const activeJob = activeJobFor(variant.id);
                  const fitsVram =
                    !vram?.available || !quant || quant.vram_mib <= vram.total_mib - 400;
                  const readyLangs = new Set<string>([
                    ...(installedLanguages[fam.familyId] ?? []),
                    ...fam.variants
                      .filter((v) => v.installed)
                      .flatMap((v) => v.capabilities?.languages ?? []),
                  ]);
                  const showLangTrash =
                    installMode === "per_language_checkpoint" ||
                    installMode === "voices_pack";

                  return (
                    <div
                      key={fam.familyId}
                      className="rounded-2xl border p-3.5 flex flex-col gap-2.5"
                      style={{
                        borderColor: variant.installed
                          ? "rgba(16,185,129,0.45)"
                          : "var(--border-glass)",
                        backgroundColor: "var(--bg-input)",
                      }}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="text-sm font-semibold">{fam.familyName}</div>
                          <p
                            className="text-[11px] leading-snug mt-0.5"
                            style={{ color: "var(--text-secondary)" }}
                          >
                            {variant.description}
                          </p>
                          <p
                            className="text-[10px] mt-1"
                            style={{ color: "var(--text-muted)" }}
                          >
                            {t(installModeHintKey(installMode))}
                          </p>
                        </div>
                        {!variant.runtime_supported && (
                          <span className="rounded-full px-2 py-0.5 text-[10px] font-mono bg-amber-500/15 text-amber-300 border border-amber-500/35 shrink-0">
                            {t("models.phase4")}
                          </span>
                        )}
                      </div>

                      {langs.length > 0 && (
                        <div className="flex flex-col gap-1.5">
                          <span
                            className="text-[10px] font-mono"
                            style={{ color: "var(--text-muted)" }}
                          >
                            {t("models.languages")}
                          </span>
                          <div className="flex flex-wrap gap-1.5">
                            {langs.map((lang) => {
                              const active = selectedLang === lang;
                              const ready = readyLangs.has(lang);
                              return (
                                <div key={lang} className="inline-flex items-center gap-0.5">
                                  <button
                                    type="button"
                                    onClick={() => {
                                      setLangChoice((prev) => ({
                                        ...prev,
                                        [fam.familyId]: lang,
                                      }));
                                      if (installMode === "per_language_checkpoint") {
                                        const next = variantForLanguage(fam.variants, lang);
                                        setVariantChoice((prev) => ({
                                          ...prev,
                                          [fam.familyId]: next.id,
                                        }));
                                      }
                                    }}
                                    className={clsx(
                                      "rounded-lg border px-2 py-0.5 text-[10px] font-mono uppercase",
                                      active && "border-cyan-400/60 text-cyan-200",
                                      ready && !active && "border-emerald-500/40 text-emerald-300",
                                    )}
                                    style={{
                                      borderColor: active
                                        ? undefined
                                        : "var(--border-glass)",
                                      backgroundColor: "var(--bg-elevated)",
                                      color: active ? undefined : "var(--text-secondary)",
                                    }}
                                  >
                                    {lang}
                                  </button>
                                  {showLangTrash && ready && (
                                    <button
                                      type="button"
                                      title={t("models.removeLanguage")}
                                      aria-label={t("models.removeLanguage")}
                                      onClick={() =>
                                        setPendingLangRemove({
                                          familyId: fam.familyId,
                                          language: lang,
                                          mode: installMode,
                                        })
                                      }
                                      className="rounded-md p-0.5 text-rose-400/70 hover:text-rose-300 hover:bg-rose-500/10"
                                    >
                                      <Trash2 className="w-3 h-3" />
                                    </button>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        {fam.variants.length > 1 &&
                          installMode !== "per_language_checkpoint" && (
                          <div className="flex flex-col gap-1">
                            <span
                              className="text-[10px] font-mono"
                              style={{ color: "var(--text-muted)" }}
                            >
                              {t("models.variant")}
                            </span>
                            <select
                              value={variant.id}
                              onChange={(e) =>
                                setVariantChoice((prev) => ({
                                  ...prev,
                                  [fam.familyId]: e.target.value,
                                }))
                              }
                              className="rounded-xl border px-2 py-1 text-xs outline-none"
                              style={{
                                borderColor: "var(--border-glass)",
                                backgroundColor: "var(--bg-elevated)",
                                color: "var(--text-primary)",
                              }}
                            >
                              {fam.variants.map((v) => (
                                <option key={v.id} value={v.id}>
                                  {v.variant_label || v.name}
                                </option>
                              ))}
                            </select>
                          </div>
                        )}

                        <div
                          className={clsx(
                            "flex flex-col gap-1",
                            (fam.variants.length <= 1 ||
                              installMode === "per_language_checkpoint") &&
                              "sm:col-span-2"
                          )}
                        >
                          <span
                            className="text-[10px] font-mono"
                            style={{ color: "var(--text-muted)" }}
                          >
                            {t("models.quantization")}
                          </span>
                          <select
                            value={chosenQId}
                            onChange={(e) =>
                              setQuantChoice((prev) => ({
                                ...prev,
                                [variant.id]: e.target.value,
                              }))
                            }
                            className="rounded-xl border px-2 py-1 text-xs font-mono outline-none"
                            style={{
                              borderColor: "var(--border-glass)",
                              backgroundColor: "var(--bg-elevated)",
                              color: "var(--text-primary)",
                            }}
                          >
                            {variant.quants.map((q) => (
                              <option key={q.id} value={q.id}>
                                {q.label} · {formatDiskSize(q.disk_mb)} ·{" "}
                                {formatVramSize(q.vram_mib)} VRAM
                              </option>
                            ))}
                          </select>
                          {quant &&
                            quant.files.length === 0 &&
                            variant.capabilities?.quant_policy !== "binary" &&
                            variant.quants.some((q) => q.files.length > 0) && (
                            <span className="text-[10px] text-amber-300/90">
                              {t("models.postQuantHint")}
                            </span>
                          )}
                        </div>
                      </div>

                      {quant && (
                        <div className="flex items-center justify-between text-[10px] font-mono">
                          <span className={fitsVram ? "text-emerald-300" : "text-amber-300"}>
                            {fitsVram ? t("models.fitsVram") : t("models.tightVram")}
                          </span>
                          <span style={{ color: "var(--text-muted)" }}>
                            {formatDiskSize(quant.disk_mb)} · {formatVramSize(quant.vram_mib)} VRAM
                          </span>
                        </div>
                      )}

                      {variant.id === "loquendo-tts7" ? (
                        <LoquendoInstallControl baseUrl={baseUrl} supported={variant.runtime_supported} onRefresh={onRefreshCatalog} />
                      ) : activeJob ? (
                        <div className="mt-auto flex flex-col gap-1.5 pt-1">
                          <div className="flex items-center justify-between text-[10px] font-mono">
                            <span className="text-cyan-300">{t("models.downloading")}</span>
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
                            onClick={async () => {
                              await cancelModelDownload(baseUrl, activeJob.job_id);
                              await onRefreshCatalog();
                            }}
                            className="inline-flex items-center justify-center gap-1 rounded-xl border px-2 py-1 text-xs text-rose-300"
                            style={{
                              borderColor: "var(--border-glass)",
                              backgroundColor: "var(--bg-elevated)",
                            }}
                          >
                            <X className="w-3 h-3" />
                            {t("models.cancel")}
                          </button>
                        </div>
                      ) : variant.installed ? (
                        <div className="mt-auto flex items-center justify-between gap-2 pt-1">
                          <span className="rounded-full px-2.5 py-0.5 text-[10px] font-mono bg-emerald-500/15 text-emerald-300 border border-emerald-500/35">
                            {t("models.installedBadge")} · {variant.installed_quant}
                          </span>
                          {variant.removable && (
                            <button
                              type="button"
                              onClick={() => onRequestRemove(variant)}
                              className="inline-flex items-center gap-1 rounded-xl border px-2.5 py-1 text-xs text-rose-300 hover:border-rose-400/60"
                              style={{
                                borderColor: "var(--border-glass)",
                                backgroundColor: "var(--bg-elevated)",
                              }}
                            >
                              <Trash2 className="w-3 h-3" />
                              {t("models.remove")}
                            </button>
                          )}
                        </div>
                      ) : (
                        <button
                          type="button"
                          disabled={installingId === variant.id}
                          onClick={async () => {
                            setError(null);
                            setInstallingId(variant.id);
                            try {
                              await startModelDownload(baseUrl, variant.id, chosenQId);
                              await onRefreshCatalog();
                            } catch (err) {
                              setError(err instanceof Error ? err.message : String(err));
                            } finally {
                              setInstallingId((cur) => (cur === variant.id ? null : cur));
                            }
                          }}
                          className="mt-auto inline-flex items-center justify-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium hover:border-cyan-400/60 text-cyan-200 disabled:opacity-50"
                          style={{
                            borderColor: "var(--border-glass)",
                            backgroundColor: "var(--bg-elevated)",
                          }}
                        >
                          <Download className="w-3.5 h-3.5" />
                          {t("models.install")}
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>

              {totalFeaturedPages > 1 && (
                <div className="flex items-center justify-center gap-2 pt-1">
                  <button
                    type="button"
                    disabled={featuredPage <= 1}
                    onClick={() => setFeaturedPage((p) => Math.max(1, p - 1))}
                    className="inline-flex items-center gap-1 rounded-xl border px-2.5 py-1 text-xs disabled:opacity-40"
                    style={{
                      borderColor: "var(--border-glass)",
                      backgroundColor: "var(--bg-elevated)",
                    }}
                  >
                    <ChevronLeft className="w-3.5 h-3.5" />
                    {t("models.prevPage")}
                  </button>
                  <span className="text-xs font-mono" style={{ color: "var(--text-secondary)" }}>
                    {t("models.pageLabel")} {featuredPage} / {totalFeaturedPages}
                  </span>
                  <button
                    type="button"
                    disabled={featuredPage >= totalFeaturedPages}
                    onClick={() => setFeaturedPage((p) => Math.min(totalFeaturedPages, p + 1))}
                    className="inline-flex items-center gap-1 rounded-xl border px-2.5 py-1 text-xs disabled:opacity-40"
                    style={{
                      borderColor: "var(--border-glass)",
                      backgroundColor: "var(--bg-elevated)",
                    }}
                  >
                    {t("models.nextPage")}
                    <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}
            </>
          )}

          {tab === "hub" &&
            (inspectPreview ? (
              renderInspectPanel(() => setInspectPreview(null))
            ) : (
              <div className="flex flex-col gap-3">
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    setHubPage(1);
                    setHubSubmittedQuery(hubQuery.trim());
                  }}
                  className="flex gap-2"
                >
                  <input
                    value={hubQuery}
                    onChange={(e) => setHubQuery(e.target.value)}
                    placeholder={t("models.searchPlaceholder")}
                    className="flex-1 rounded-xl border px-3 py-1.5 text-xs outline-none"
                    style={{
                      borderColor: "var(--border-glass)",
                      backgroundColor: "var(--bg-input)",
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => {
                      setHubPage(1);
                      setHubReadyOnly((v) => !v);
                    }}
                    className={clsx(
                      "inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-mono font-semibold transition-colors shrink-0",
                      hubReadyOnly
                        ? "border-emerald-400/60 bg-emerald-500/20 text-emerald-300"
                        : "border-white/15 opacity-70 hover:opacity-100"
                    )}
                    title={t("models.readyFilterHint")}
                  >
                    <span
                      className={clsx(
                        "w-2 h-2 rounded-full",
                        hubReadyOnly ? "bg-emerald-400" : "bg-zinc-400"
                      )}
                    />
                    {t("models.crispReady")}
                  </button>
                  <button
                    type="submit"
                    disabled={hubLoading}
                    className="inline-flex items-center gap-1 rounded-xl border px-3 py-1.5 text-xs font-medium hover:border-cyan-400/60"
                    style={{
                      borderColor: "var(--border-glass)",
                      backgroundColor: "var(--bg-elevated)",
                    }}
                  >
                    {hubLoading ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Search className="w-3.5 h-3.5" />
                    )}
                    {t("models.search")}
                  </button>
                </form>

                {hubLoading || hubInspecting ? (
                  <div className="py-10 flex items-center justify-center gap-2 text-xs opacity-75">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Loading...</span>
                  </div>
                ) : hubItems.length === 0 ? (
                  <div
                    className="py-8 text-center text-xs rounded-2xl border border-dashed"
                    style={{ borderColor: "var(--border-glass)", color: "var(--text-muted)" }}
                  >
                    {t("models.hubEmpty")}
                  </div>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                    {hubItems.map((item) => (
                      <button
                        key={item.repo_id}
                        type="button"
                        onClick={async () => {
                          setHubInspecting(true);
                          try {
                            await runInspectUrl(item.repo_id);
                          } catch (err) {
                            setError(err instanceof Error ? err.message : String(err));
                          } finally {
                            setHubInspecting(false);
                          }
                        }}
                        className="rounded-2xl border p-3 text-left flex flex-col gap-1.5 hover:border-cyan-400/60 transition-colors"
                        style={{
                          borderColor: "var(--border-glass)",
                          backgroundColor: "var(--bg-input)",
                        }}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <span className="text-xs font-semibold truncate">{item.repo_id}</span>
                          <span
                            title={item.crispasr_reason || undefined}
                            className={clsx(
                              "rounded-full px-2 py-0.5 text-[10px] font-mono font-semibold border shrink-0",
                              item.crispasr_ready
                                ? "bg-emerald-500/20 text-emerald-300 border-emerald-400/50"
                                : "bg-rose-500/20 text-rose-300 border-rose-400/50"
                            )}
                          >
                            {item.crispasr_ready ? t("models.crispReady") : t("models.crispNotReady")}
                          </span>
                        </div>
                        <div
                          className="text-[10px] font-mono flex items-center gap-2"
                          style={{ color: "var(--text-muted)" }}
                        >
                          <span>
                            {item.downloads.toLocaleString()} {t("models.downloadsCount")}
                          </span>
                          <span>·</span>
                          <span>★ {item.likes}</span>
                          {item.crispasr_backend && (
                            <>
                              <span>·</span>
                              <span className="text-cyan-300">{item.crispasr_backend}</span>
                            </>
                          )}
                        </div>
                      </button>
                    ))}
                  </div>
                )}

                <div className="flex items-center justify-center gap-2 pt-1">
                  <button
                    type="button"
                    disabled={hubPage <= 1 || hubLoading}
                    onClick={() => setHubPage((p) => Math.max(1, p - 1))}
                    className="inline-flex items-center gap-1 rounded-xl border px-2.5 py-1 text-xs disabled:opacity-40"
                    style={{
                      borderColor: "var(--border-glass)",
                      backgroundColor: "var(--bg-elevated)",
                    }}
                  >
                    <ChevronLeft className="w-3.5 h-3.5" />
                    {t("models.prevPage")}
                  </button>
                  <span className="text-xs font-mono" style={{ color: "var(--text-secondary)" }}>
                    {t("models.pageLabel")} {hubPage}
                  </span>
                  <button
                    type="button"
                    disabled={!hubHasMore || hubLoading}
                    onClick={() => setHubPage((p) => p + 1)}
                    className="inline-flex items-center gap-1 rounded-xl border px-2.5 py-1 text-xs disabled:opacity-40"
                    style={{
                      borderColor: "var(--border-glass)",
                      backgroundColor: "var(--bg-elevated)",
                    }}
                  >
                    {t("models.nextPage")}
                    <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ))}

          {tab === "import" && (
            <div className="flex flex-col gap-3">
              {/* Block 1: URL (Hugging Face / ModelScope / Direct) */}
              <div
                className="rounded-2xl border p-3.5 flex flex-col gap-2.5"
                style={{
                  borderColor: "var(--border-glass)",
                  backgroundColor: "var(--bg-input)",
                }}
              >
                <span className="text-xs font-semibold">{t("models.importUrlTitle")}</span>
                <div className="flex gap-2">
                  <input
                    value={importUrl}
                    onChange={(e) => setImportUrl(e.target.value)}
                    placeholder={t("models.importUrlPlaceholder")}
                    className="flex-1 rounded-xl border px-3 py-1.5 text-xs font-mono outline-none"
                    style={{
                      borderColor: "var(--border-glass)",
                      backgroundColor: "var(--bg-elevated)",
                    }}
                  />
                  <button
                    type="button"
                    disabled={urlInspecting || !importUrl.trim()}
                    onClick={async () => {
                      setUrlInspecting(true);
                      try {
                        await runInspectUrl(importUrl);
                      } catch (err) {
                        setError(err instanceof Error ? err.message : String(err));
                      } finally {
                        setUrlInspecting(false);
                      }
                    }}
                    className="inline-flex items-center gap-1 rounded-xl border px-3 py-1.5 text-xs font-medium hover:border-cyan-400/60 disabled:opacity-40"
                    style={{
                      borderColor: "var(--border-glass)",
                      backgroundColor: "var(--bg-elevated)",
                    }}
                  >
                    {urlInspecting ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Search className="w-3.5 h-3.5" />
                    )}
                    {t("models.inspect")}
                  </button>
                </div>

                {inspectPreview && renderInspectPanel(() => setInspectPreview(null))}
              </div>

              {/* Block 2: Local Folder / File */}
              <div
                className="rounded-2xl border p-3.5 flex flex-col gap-2.5"
                style={{
                  borderColor: "var(--border-glass)",
                  backgroundColor: "var(--bg-input)",
                }}
              >
                <span className="text-xs font-semibold">{t("models.importLocalTitle")}</span>
                <div className="flex flex-wrap gap-2">
                  <input
                    value={localPath}
                    onChange={(e) => setLocalPath(e.target.value)}
                    placeholder={t("models.localPathPlaceholder")}
                    className="flex-1 min-w-[200px] rounded-xl border px-3 py-1.5 text-xs font-mono outline-none"
                    style={{
                      borderColor: "var(--border-glass)",
                      backgroundColor: "var(--bg-elevated)",
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => pickLocal(true)}
                    className="inline-flex items-center gap-1 rounded-xl border px-2.5 py-1.5 text-xs hover:border-cyan-400/50"
                    style={{
                      borderColor: "var(--border-glass)",
                      backgroundColor: "var(--bg-elevated)",
                    }}
                  >
                    <FolderOpen className="w-3.5 h-3.5" />
                    {t("models.pickFolder")}
                  </button>
                  <button
                    type="button"
                    onClick={() => pickLocal(false)}
                    className="inline-flex items-center gap-1 rounded-xl border px-2.5 py-1.5 text-xs hover:border-cyan-400/50"
                    style={{
                      borderColor: "var(--border-glass)",
                      backgroundColor: "var(--bg-elevated)",
                    }}
                  >
                    <FileIcon className="w-3.5 h-3.5" />
                    {t("models.pickFile")}
                  </button>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-2">
                  <input
                    value={localName}
                    onChange={(e) => setLocalName(e.target.value)}
                    placeholder={t("models.modelName")}
                    className="flex-1 min-w-[180px] rounded-xl border px-3 py-1.5 text-xs outline-none"
                    style={{
                      borderColor: "var(--border-glass)",
                      backgroundColor: "var(--bg-elevated)",
                    }}
                  />
                  <button
                    type="button"
                    disabled={!localPath.trim() || importingLocal}
                    onClick={handleImportLocal}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-emerald-400/60 bg-emerald-500/20 px-3.5 py-1.5 text-xs font-semibold text-emerald-200 disabled:opacity-40"
                  >
                    {importingLocal ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Download className="w-3.5 h-3.5" />
                    )}
                    {t("models.importNow")}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </GlassCard>

      {pendingLangRemove && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/65 backdrop-blur-sm p-4">
          <GlassCard className="w-full max-w-sm p-4 flex flex-col gap-3">
            <h3 className="text-sm font-semibold">{t("models.removeLanguage")}</h3>
            <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
              {t("models.removeLanguageConfirm")} ({pendingLangRemove.language})
            </p>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setPendingLangRemove(null)}
                className="rounded-xl border px-3 py-1.5 text-xs"
                style={{ borderColor: "var(--border-glass)" }}
              >
                {t("models.cancel")}
              </button>
              <button
                type="button"
                onClick={async () => {
                  if (
                    pendingLangRemove.mode !== "per_language_checkpoint" &&
                    pendingLangRemove.mode !== "voices_pack"
                  ) {
                    setPendingLangRemove(null);
                    return;
                  }
                  try {
                    const res = await uninstallLanguagePack(
                      baseUrl,
                      pendingLangRemove.familyId,
                      pendingLangRemove.language,
                      pendingLangRemove.mode,
                    );
                    onInstalledLanguagesChange?.(res.installed_languages);
                    await onRefreshCatalog();
                  } catch (err) {
                    setError(err instanceof Error ? err.message : String(err));
                  } finally {
                    setPendingLangRemove(null);
                  }
                }}
                className="rounded-xl border border-rose-400/50 bg-rose-500/20 px-3 py-1.5 text-xs text-rose-200"
              >
                {t("models.confirmRemoveLanguage")}
              </button>
            </div>
          </GlassCard>
        </div>
      )}
    </div>
  );
};

import React, { useEffect, useMemo, useState } from "react";
import {
  AppWindow,
  ChevronLeft,
  ChevronRight,
  Monitor,
  RefreshCw,
  Search,
  Volume2,
  X,
} from "lucide-react";
import { clsx } from "clsx";
import { useI18n } from "../i18n";
import type { AudioAppRow } from "../services/api";
import { GlassCard } from "./GlassCard";

interface WindowPickerModalProps {
  open: boolean;
  apps: AudioAppRow[];
  selectedKey: string;
  loading: boolean;
  rowKeyFn: (row: AudioAppRow) => string;
  onRefresh: () => void;
  onSelect: (key: string) => void;
  onClose: () => void;
}

const PAGE_SIZE = 4;

export const WindowPickerModal: React.FC<WindowPickerModalProps> = ({
  open,
  apps,
  selectedKey,
  loading,
  rowKeyFn,
  onRefresh,
  onSelect,
  onClose,
}) => {
  const { t } = useI18n();
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    if (!open) return;
    setPage(1);
    setQuery("");
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return apps;
    return apps.filter(
      (a) =>
        a.name.toLowerCase().includes(q) ||
        (a.app_name || "").toLowerCase().includes(q) ||
        String(a.pid).includes(q)
    );
  }, [apps, query]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageItems = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <GlassCard className="w-full max-w-3xl p-4 flex flex-col gap-3">
        {/* Header */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Monitor className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-semibold">{t("subtitles.pickerTitle")}</h3>
            <span className="text-[11px] font-mono" style={{ color: "var(--text-muted)" }}>
              ({filtered.length})
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg opacity-70 hover:opacity-100"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Search + Refresh */}
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search
              className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2"
              style={{ color: "var(--text-muted)" }}
            />
            <input
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(1);
              }}
              placeholder={t("subtitles.searchWindows")}
              className="w-full rounded-xl border pl-8 pr-3 py-1.5 text-xs outline-none"
              style={{
                backgroundColor: "var(--bg-input)",
                borderColor: "var(--border-glass)",
                color: "var(--text-primary)",
              }}
            />
          </div>
          <button
            type="button"
            onClick={onRefresh}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium hover:border-cyan-400/50 disabled:opacity-50"
            style={{
              backgroundColor: "var(--bg-elevated)",
              borderColor: "var(--border-glass)",
            }}
          >
            <RefreshCw className={clsx("w-3.5 h-3.5", loading && "animate-spin")} />
            {t("subtitles.refreshApps")}
          </button>
        </div>

        {/* 2x2 Paginated Preview Grid with Side Navigation Arrows */}
        <div className="relative">
          {safePage > 1 && (
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              aria-label={t("models.prevPage")}
              className="absolute -left-2 top-1/2 -translate-y-1/2 z-20 w-8 h-8 rounded-full border bg-black/80 text-white hover:border-cyan-400 flex items-center justify-center shadow-lg transition-colors"
              style={{ borderColor: "var(--border-glass)" }}
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
          )}

          {safePage < totalPages && (
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              aria-label={t("models.nextPage")}
              className="absolute -right-2 top-1/2 -translate-y-1/2 z-20 w-8 h-8 rounded-full border bg-black/80 text-white hover:border-cyan-400 flex items-center justify-center shadow-lg transition-colors"
              style={{ borderColor: "var(--border-glass)" }}
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          )}

          {pageItems.length === 0 ? (
            <div
              className="rounded-2xl border border-dashed py-14 text-center text-xs"
              style={{
                borderColor: "var(--border-glass)",
                backgroundColor: "var(--bg-input)",
                color: "var(--text-muted)",
              }}
            >
              {t("subtitles.noApps")}
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 px-4">
              {pageItems.map((app) => {
                const key = rowKeyFn(app);
                const isSelected = key === selectedKey;
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => {
                      onSelect(key);
                      onClose();
                    }}
                    className={clsx(
                      "group rounded-2xl border overflow-hidden text-left flex flex-col transition-all hover:border-cyan-400/70",
                      isSelected
                        ? "border-cyan-400 ring-1 ring-cyan-400/50"
                        : "border-white/10"
                    )}
                    style={{ backgroundColor: "var(--bg-input)" }}
                  >
                    <div className="relative aspect-video w-full bg-black/90 flex items-center justify-center overflow-hidden">
                      {app.thumbnail ? (
                        <img
                          src={app.thumbnail}
                          alt={app.name}
                          className="w-full h-full object-contain group-hover:scale-[1.02] transition-transform"
                        />
                      ) : (
                        <div className="flex flex-col items-center justify-center gap-1.5 px-4 text-center">
                          {app.has_audio ? (
                            <Volume2 className="w-7 h-7 text-emerald-400/80" />
                          ) : (
                            <Monitor className="w-7 h-7 opacity-45" />
                          )}
                          <span
                            className="text-[11px] font-mono truncate max-w-[200px]"
                            style={{ color: "var(--text-muted)" }}
                          >
                            {app.app_name || t("subtitles.noPreview")}
                          </span>
                        </div>
                      )}

                      {app.has_audio && (
                        <span className="absolute top-2 right-2 inline-flex items-center gap-1 rounded-full bg-black/75 border border-emerald-400/40 px-2 py-0.5 text-[10px] font-mono text-emerald-300">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                          Audio
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-2 px-3 py-2 border-t border-white/10">
                      {app.icon ? (
                        <img src={app.icon} alt="" className="w-4 h-4 rounded-sm shrink-0" />
                      ) : (
                        <AppWindow className="w-4 h-4 shrink-0 text-cyan-400/80" />
                      )}
                      <span className="text-xs font-medium truncate flex-1">{app.name}</span>
                      <span className="text-[10px] font-mono opacity-50 shrink-0">
                        {app.pid}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Bottom Centered Pagination Dots */}
        <div className="flex items-center justify-center gap-3 pt-1">
          {totalPages > 1 && (
            <div className="flex items-center gap-1.5">
              {Array.from({ length: totalPages }, (_, idx) => idx + 1).map((n) => (
                <button
                  key={n}
                  type="button"
                  onClick={() => setPage(n)}
                  aria-label={`${t("models.pageLabel")} ${n}`}
                  className={clsx(
                    "h-2 rounded-full transition-all",
                    n === safePage ? "w-5 bg-cyan-400" : "w-2 bg-white/25 hover:bg-white/45"
                  )}
                />
              ))}
            </div>
          )}
          <span className="text-[11px] font-mono" style={{ color: "var(--text-muted)" }}>
            {t("models.pageLabel")} {safePage} / {totalPages}
          </span>
        </div>
      </GlassCard>
    </div>
  );
};

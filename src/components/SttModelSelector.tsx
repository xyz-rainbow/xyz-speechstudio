import React, { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown } from "lucide-react";
import { clsx } from "clsx";
import { useI18n } from "../i18n";
import type { AppSettings, CatalogModelEntry } from "../types";
import { endpointProviderSubtitle } from "../utils/endpointPresets";

interface SttModelSelectorProps {
  catalog: CatalogModelEntry[];
  settings: AppSettings;
  onSaveSettings: (next: AppSettings) => Promise<void>;
  disabled?: boolean;
}

export const SttModelSelector: React.FC<SttModelSelectorProps> = ({
  catalog,
  settings,
  onSaveSettings,
  disabled = false,
}) => {
  const { t } = useI18n();
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuPos, setMenuPos] = useState<{ top: number; left: number; width: number } | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const dropdownRef = useRef<HTMLDivElement | null>(null);

  const localModels = useMemo(
    () => catalog.filter((m) => m.kind === "stt" && m.installed && m.runtime_supported),
    [catalog]
  );

  useEffect(() => {
    if (disabled && menuOpen) {
      setMenuOpen(false);
    }
  }, [disabled, menuOpen]);

  useEffect(() => {
    if (!menuOpen) return;
    const onPointerDown = (ev: MouseEvent) => {
      const target = ev.target as Node;
      if (
        menuRef.current &&
        !menuRef.current.contains(target) &&
        !dropdownRef.current?.contains(target)
      ) {
        setMenuOpen(false);
      }
    };
    const onKeyDown = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") setMenuOpen(false);
    };
    window.addEventListener("mousedown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("mousedown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [menuOpen]);

  useEffect(() => {
    if (!menuOpen) {
      setMenuPos(null);
      return;
    }
    const updatePos = () => {
      const el = menuRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const width = 280;
      const rawLeft = rect.left + rect.width / 2 - width / 2;
      const left = Math.max(12, Math.min(window.innerWidth - width - 12, rawLeft));
      setMenuPos({ top: rect.bottom + 6, left, width });
    };
    updatePos();
    window.addEventListener("resize", updatePos);
    return () => window.removeEventListener("resize", updatePos);
  }, [menuOpen]);

  const sttEndpoints = settings.external_endpoints.filter((e) => e.kind === "stt");
  const activeEp = sttEndpoints.find((e) => e.id === settings.active_stt_endpoint_id);
  const isEndpointMode = settings.stt_source === "endpoint";

  const localOptions = useMemo(
    () =>
      localModels.flatMap((m) => {
        const computeQuants = m.quants.filter((q) => Boolean(q.compute_type));
        if (computeQuants.length > 1) {
          return computeQuants.map((q) => ({
            id: `${m.id}-${q.id}`,
            baseId: m.id,
            name: `${m.name} · ${q.id}`,
            subtitle: `${q.label} · ~${q.vram_mib} MB`,
          }));
        }
        const quantBadge = m.installed_quant || m.quants[0]?.id || m.engine;
        return [
          {
            id: m.id,
            baseId: m.id,
            name: m.installed_quant ? `${m.name} · ${m.installed_quant}` : m.name,
            subtitle: `${quantBadge} · ~${m.vram_mib} MB`,
          },
        ];
      }),
    [localModels]
  );

  const activeLocal =
    localOptions.find((m) => m.id === settings.active_stt_model) ||
    localOptions.find(
      (m) =>
        m.baseId === settings.active_stt_model &&
        m.id.endsWith("-int8_float16")
    ) ||
    localOptions.find((m) => m.baseId === settings.active_stt_model) ||
    localOptions[0];
  const sourceLabel = isEndpointMode
    ? `${t("models.externalGroup")} · ${activeEp ? activeEp.name : t("transcriber.unconfigured")}`
    : activeLocal
      ? `${t("models.local")} · ${activeLocal.name} (${settings.stt_device.toUpperCase()})`
      : `${t("models.local")} · ${t("models.noLocalInstalled")}`;

  const selectLocalModel = async (id: string) => {
    setMenuOpen(false);
    if (settings.stt_source === "local" && id === settings.active_stt_model) return;
    await onSaveSettings({
      ...settings,
      stt_source: "local",
      active_stt_model: id,
    });
  };

  const selectEndpoint = async (id: string) => {
    setMenuOpen(false);
    if (settings.stt_source === "endpoint" && id === settings.active_stt_endpoint_id) return;
    await onSaveSettings({
      ...settings,
      stt_source: "endpoint",
      active_stt_endpoint_id: id,
    });
  };

  return (
    <div className="relative" ref={menuRef}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setMenuOpen((v) => !v)}
        title={sourceLabel}
        className="w-[225px] inline-flex items-center justify-between gap-1.5 rounded-full px-3 py-1 text-[11px] font-mono border transition-colors hover:brightness-110 disabled:opacity-50"
        style={{
          backgroundColor: "var(--bg-input)",
          borderColor: isEndpointMode
            ? "rgba(16,185,129,0.45)"
            : "rgba(6,182,212,0.45)",
          color: isEndpointMode ? "#34d399" : "#67e8f9",
        }}
      >
        <span className="truncate">{sourceLabel}</span>
        <ChevronDown
          className={clsx("w-3.5 h-3.5 shrink-0 transition-transform", menuOpen && "rotate-180")}
        />
      </button>

      {menuOpen &&
        menuPos &&
        createPortal(
          <div
            ref={dropdownRef}
            className="fixed z-[9999] max-h-[320px] overflow-y-auto rounded-2xl border p-1.5 shadow-2xl backdrop-blur-xl flex flex-col gap-0.5"
            style={{
              top: menuPos.top,
              left: menuPos.left,
              width: menuPos.width,
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
                    onClick={() => void selectLocalModel(m.id)}
                    className={clsx(
                      "w-full text-left rounded-xl px-2.5 py-1.5 text-xs flex items-center justify-between gap-2 hover:bg-white/10",
                      active && "bg-cyan-500/15 text-cyan-200"
                    )}
                  >
                    <div className="min-w-0">
                      <div className="font-medium truncate">{m.name}</div>
                      <div className="text-[10px] font-mono opacity-65 truncate">
                        {m.subtitle}
                      </div>
                    </div>
                    {active && <Check className="w-3.5 h-3.5 shrink-0 text-cyan-400" />}
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

            {sttEndpoints.length > 0 ? (
              sttEndpoints.map((ep) => {
                const active = isEndpointMode && ep.id === settings.active_stt_endpoint_id;
                return (
                  <button
                    key={ep.id}
                    type="button"
                    onClick={() => void selectEndpoint(ep.id)}
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
          </div>,
          document.body
        )}
    </div>
  );
};

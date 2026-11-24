import React from "react";
import { Cpu, Moon, Sun } from "lucide-react";
import { clsx } from "clsx";
import { useI18n } from "../i18n";
import type { DeviceMode, SourceMode, ThemeMode, VramStatus } from "../types";

interface TopBarProps {
  vram: VramStatus;
  ttsDevice: DeviceMode;
  sttDevice: DeviceMode;
  ttsSource: SourceMode;
  sttSource: SourceMode;
  theme: ThemeMode;
  onChangeTtsDevice: (d: DeviceMode) => void;
  onChangeSttDevice: (d: DeviceMode) => void;
  onToggleTheme: () => void;
}

function DeviceSlideToggle({
  label,
  value,
  source,
  onChange,
}: {
  label: string;
  value: DeviceMode;
  source: SourceMode;
  onChange: (d: DeviceMode) => void;
}) {
  const isGpu = value === "gpu";
  const isApi = source === "endpoint";
  return (
    <div
      className="flex items-center gap-1.5 rounded-full border px-2 py-1 text-xs"
      style={{
        backgroundColor: "var(--bg-surface-strong)",
        borderColor: "var(--border-glass)",
      }}
    >
      <span className="font-mono font-semibold text-[10px]" style={{ color: "var(--text-secondary)" }}>
        {label}
      </span>
      {isApi ? (
        <span className="px-2 py-0.5 rounded-full font-mono text-[10px] font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-400/40">
          API
        </span>
      ) : (
        <button
          type="button"
          onClick={() => onChange(isGpu ? "cpu" : "gpu")}
          className="relative flex items-center w-[68px] h-5 rounded-full p-0.5 transition-colors border"
          style={{
            backgroundColor: "var(--bg-input)",
            borderColor: isGpu ? "rgba(6, 182, 212, 0.45)" : "rgba(168, 85, 247, 0.45)",
          }}
        >
          <span
            className={clsx(
              "absolute top-0.5 bottom-0.5 w-[31px] rounded-full transition-transform duration-200",
              isGpu
                ? "translate-x-0 bg-cyan-500/30 border border-cyan-400/60"
                : "translate-x-[32px] bg-purple-500/30 border border-purple-400/60"
            )}
          />
          <span className={clsx("relative z-10 w-1/2 text-center font-mono text-[10px] font-semibold", isGpu ? "text-cyan-300" : "opacity-55")}>
            GPU
          </span>
          <span className={clsx("relative z-10 w-1/2 text-center font-mono text-[10px] font-semibold", !isGpu ? "text-purple-300" : "opacity-55")}>
            CPU
          </span>
        </button>
      )}
    </div>
  );
}

export const TopBar: React.FC<TopBarProps> = ({
  vram,
  ttsDevice,
  sttDevice,
  ttsSource,
  sttSource,
  theme,
  onChangeTtsDevice,
  onChangeSttDevice,
  onToggleTheme,
}) => {
  const { t } = useI18n();
  const pct = vram.total_mib > 0 ? Math.min(100, Math.round((vram.used_mib / vram.total_mib) * 100)) : 0;
  const barColor =
    pct >= 88 ? "bg-rose-500" : pct >= 70 ? "bg-amber-400" : "bg-gradient-to-r from-purple-500 to-cyan-400";

  return (
    <header
      className="relative z-10 flex flex-wrap items-center justify-between gap-2 rounded-[20px] border backdrop-blur-xl px-3.5 py-2"
      style={{
        backgroundColor: "var(--bg-surface)",
        borderColor: "var(--border-neon)",
        boxShadow: "var(--glow-card)",
      }}
    >
      <div className="flex items-center gap-2.5 min-w-[200px] flex-1">
        <Cpu className="w-4 h-4 text-cyan-400 shrink-0" />
        <div className="flex flex-col gap-1 min-w-[160px] max-w-[280px] flex-1">
          <div className="flex items-center justify-between gap-2 text-[11px]">
            <span className="font-medium truncate">
              {vram.available ? vram.gpu : t("topbar.noGpu")}
            </span>
            {vram.available && (
              <span className="font-mono text-[10px] shrink-0" style={{ color: "var(--text-secondary)" }}>
                {vram.used_mib}/{vram.total_mib} MiB
              </span>
            )}
          </div>
          <div className="h-1.5 w-full rounded-full overflow-hidden bg-white/10">
            <div className={clsx("h-full rounded-full transition-all duration-500", barColor)} style={{ width: `${pct}%` }} />
          </div>
        </div>
      </div>

      <div className="flex items-center gap-1.5 shrink-0">
        <DeviceSlideToggle label={t("topbar.ttsLabel")} value={ttsDevice} source={ttsSource} onChange={onChangeTtsDevice} />
        <DeviceSlideToggle label={t("topbar.sttLabel")} value={sttDevice} source={sttSource} onChange={onChangeSttDevice} />

        <button
          type="button"
          onClick={onToggleTheme}
          className="inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-all"
          style={{
            backgroundColor: "var(--bg-surface-strong)",
            borderColor: "var(--border-glass)",
          }}
          title={t("topbar.mode")}
        >
          {theme === "dark" ? <Moon className="w-3.5 h-3.5 text-purple-400" /> : <Sun className="w-3.5 h-3.5 text-amber-500" />}
          <span className="hidden sm:inline">{t("topbar.mode")}</span>
        </button>
      </div>
    </header>
  );
};

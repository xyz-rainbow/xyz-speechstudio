import React from "react";
import {
  AudioLines,
  Captions,
  Compass,
  Cpu,
  FileAudio,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  Users,
} from "lucide-react";
import { clsx } from "clsx";
import { useI18n } from "../i18n";
import type { AppTabId } from "../types/persona";
import { UpdateBadge } from "./UpdateBadge";

interface SidebarProps {
  activeTab: AppTabId;
  collapsed: boolean;
  baseUrl: string;
  onSelectTab: (tab: AppTabId) => void;
  onToggleCollapse: () => void;
}

const NAV_ITEMS: { id: AppTabId; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: "synthesize", icon: AudioLines },
  { id: "profiles", icon: Users },
  { id: "persona", icon: Compass },
  { id: "transcriber", icon: FileAudio },
  { id: "subtitles", icon: Captions },
  { id: "models", icon: Cpu },
  { id: "settings", icon: Settings },
];

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  collapsed,
  baseUrl,
  onSelectTab,
  onToggleCollapse,
}) => {
  const { t } = useI18n();

  return (
    <aside
      className={clsx(
        "relative z-10 flex flex-col justify-between rounded-[20px] border backdrop-blur-xl transition-all duration-300 p-2",
        collapsed ? "w-[68px]" : "w-[154px]"
      )}
      style={{
        backgroundColor: "var(--bg-surface)",
        borderColor: "var(--border-neon)",
        boxShadow: "var(--glow-card)",
      }}
    >
      <div className="flex flex-col gap-1.5">
        <div
          className={clsx(
            "flex items-center px-1.5 py-2 mb-1.5",
            collapsed ? "justify-center" : "justify-between"
          )}
        >
          {!collapsed && (
            <div className="flex items-center gap-1.5 min-w-0">
              <span
                className="h-2.5 w-2.5 rounded-full shrink-0"
                style={{
                  background: "linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))",
                  boxShadow: "0 0 12px var(--accent-primary)",
                }}
              />
              <span className="font-semibold text-[13px] tracking-tight truncate">
                {t("app.name")}
              </span>
            </div>
          )}
          <button
            type="button"
            onClick={onToggleCollapse}
            title={collapsed ? t("nav.expand") : t("nav.collapse")}
            className="p-1.5 rounded-xl border border-transparent hover:border-purple-500/30 transition-colors"
            style={{ color: "var(--text-secondary)" }}
          >
            {collapsed ? (
              <PanelLeftOpen className="w-4 h-4" />
            ) : (
              <PanelLeftClose className="w-4 h-4" />
            )}
          </button>
        </div>

        <nav className="flex flex-col gap-1">
          {NAV_ITEMS.map(({ id, icon: Icon }) => {
            const active = activeTab === id;
            const label = t(`nav.${id}`);
            return (
              <button
                key={id}
                type="button"
                title={collapsed ? label : undefined}
                onClick={() => onSelectTab(id)}
                className={clsx(
                  "group flex items-center gap-2 rounded-xl px-2.5 py-2 text-[13px] font-medium transition-all duration-200 border",
                  collapsed && "justify-center px-0",
                  active
                    ? "border-purple-500/40"
                    : "border-transparent hover:border-white/10"
                )}
                style={{
                  backgroundColor: active ? "var(--bg-elevated)" : "transparent",
                  color: active ? "var(--text-primary)" : "var(--text-secondary)",
                  boxShadow: active ? "0 0 18px rgba(168, 85, 247, 0.16)" : undefined,
                }}
              >
                <Icon
                  className={clsx(
                    "w-4 h-4 shrink-0 transition-colors",
                    active && "text-purple-400"
                  )}
                />
                {!collapsed && <span className="truncate">{label}</span>}
              </button>
            );
          })}
        </nav>
      </div>

      <UpdateBadge
        baseUrl={baseUrl}
        collapsed={collapsed}
        active={activeTab === "updates"}
        onOpen={() => onSelectTab("updates")}
      />
    </aside>
  );
};

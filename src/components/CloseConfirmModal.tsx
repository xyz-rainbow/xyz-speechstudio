import React, { useState } from "react";
import { Minimize2, Power, X } from "lucide-react";
import { useI18n } from "../i18n";
import { GlassCard } from "./GlassCard";

interface CloseConfirmModalProps {
  open: boolean;
  onMinimize: (remember: boolean) => void;
  onQuit: (remember: boolean) => void;
  onCancel: () => void;
}

export const CloseConfirmModal: React.FC<CloseConfirmModalProps> = ({
  open,
  onMinimize,
  onQuit,
  onCancel,
}) => {
  const { t } = useI18n();
  const [remember, setRemember] = useState(false);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <GlassCard className="w-full max-w-md p-5 flex flex-col gap-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex flex-col gap-1">
            <h3 className="text-sm font-semibold">{t("closeModal.title")}</h3>
            <p className="text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
              {t("closeModal.body")}
            </p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="p-1 rounded-lg opacity-70 hover:opacity-100"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex flex-col gap-2.5">
          <button
            type="button"
            onClick={() => onMinimize(remember)}
            className="w-full inline-flex items-center justify-center gap-2 rounded-xl border border-lime-400 bg-lime-500/15 hover:bg-lime-500/25 px-4 py-2.5 text-sm font-semibold text-lime-300 transition-colors"
          >
            <Minimize2 className="w-4 h-4" />
            {t("closeModal.minimizeBtn")}
          </button>

          <button
            type="button"
            onClick={() => onQuit(remember)}
            className="w-full inline-flex items-center justify-center gap-2 rounded-xl border border-red-500 bg-red-500/15 hover:bg-red-500/25 px-4 py-2.5 text-sm font-semibold text-red-400 transition-colors"
          >
            <Power className="w-4 h-4" />
            {t("closeModal.quitBtn")}
          </button>
        </div>

        <label
          className="flex items-center gap-2 text-xs cursor-pointer select-none"
          style={{ color: "var(--text-secondary)" }}
        >
          <input
            type="checkbox"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
            className="w-3.5 h-3.5 accent-cyan-400"
          />
          <span>{t("closeModal.remember")}</span>
        </label>
      </GlassCard>
    </div>
  );
};

import React from "react";
import { clsx } from "clsx";

interface GlassCardProps {
  children: React.ReactNode;
  className?: string;
  alertRipple?: boolean;
}

export const GlassCard: React.FC<GlassCardProps> = ({
  children,
  className = "",
  alertRipple = false,
}) => {
  return (
    <div
      className={clsx(
        "relative rounded-[20px] backdrop-blur-xl transition-all duration-300 border",
        alertRipple && "ring-2 ring-rose-500/60 animate-pulse",
        className
      )}
      style={{
        backgroundColor: "var(--bg-surface)",
        borderColor: alertRipple ? "rgba(244, 63, 94, 0.55)" : "var(--border-neon)",
        boxShadow: "var(--glow-card)",
      }}
    >
      {children}
    </div>
  );
};

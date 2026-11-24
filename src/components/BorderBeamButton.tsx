import React from "react";
import { clsx } from "clsx";

interface BorderBeamButtonProps {
  children: React.ReactNode;
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
  disabled?: boolean;
  variant?: "primary" | "emerald" | "rose";
  activeBeam?: boolean;
  className?: string;
  title?: string;
  type?: "button" | "submit";
}

const GRADIENTS = {
  primary: "from-purple-500 via-cyan-400 to-purple-500",
  emerald: "from-emerald-400 via-cyan-400 to-emerald-400",
  rose: "from-rose-500 via-amber-400 to-rose-500",
};

export const BorderBeamButton: React.FC<BorderBeamButtonProps> = ({
  children,
  onClick,
  disabled = false,
  variant = "primary",
  activeBeam = true,
  className = "",
  title,
  type = "button",
}) => {
  return (
    <button
      type={type}
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={clsx(
        "group relative inline-flex items-center justify-center rounded-full p-[1.5px] transition-transform duration-200 active:scale-[0.98] disabled:opacity-45 disabled:pointer-events-none",
        className
      )}
      style={{ boxShadow: "var(--glow-strong)" }}
    >
      <span
        className={clsx(
          "absolute inset-0 rounded-full bg-gradient-to-r opacity-75 blur-[1px] transition-opacity duration-300",
          GRADIENTS[variant],
          activeBeam ? "opacity-90" : "opacity-40 group-hover:opacity-95"
        )}
      />
      <span
        className="relative flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium tracking-tight"
        style={{
          backgroundColor: "var(--bg-surface-strong)",
          color: "var(--text-primary)",
        }}
      >
        {children}
      </span>
    </button>
  );
};

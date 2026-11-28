import React, { useEffect, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { Eye, Pin, PinOff, Type, X } from "lucide-react";
import { clsx } from "clsx";
import { isTauri, setOverlayPinned } from "../services/api";

export const CaptionOverlay: React.FC = () => {
  const [pinned, setPinned] = useState(true);
  const [opacity, setOpacity] = useState(0.84);
  const [fontSize, setFontSize] = useState(16);
  const [line, setLine] = useState("");
  const [kind, setKind] = useState<"idle" | "partial" | "final" | "error">("idle");

  useEffect(() => {
    let unlisten: (() => void) | undefined;
    let disposed = false;
    listen<string>("caption", (ev) => {
      try {
        const body = JSON.parse(ev.payload) as { type?: string; text?: string };
        if (body.type === "partial") {
          setKind("partial");
          setLine(body.text || "");
          return;
        }
        if (body.type === "final") {
          const text = (body.text || "").trim();
          if (!text) return;
          setKind("final");
          setLine(text);
          return;
        }
        if (body.type === "error") {
          setKind("error");
          setLine(body.text || "");
        }
        // status events are for session lifecycle in SubtitlesView, not overlay text
      } catch {
        /* ignore malformed events */
      }
    }).then((fn) => {
      if (disposed) fn();
      else unlisten = fn;
    });
    return () => {
      disposed = true;
      unlisten?.();
    };
  }, []);

  useEffect(() => {
    document.body.classList.remove("app-main");
    document.body.classList.add("app-overlay");
  }, []);

  const togglePin = async () => {
    const next = !pinned;
    setPinned(next);
    await setOverlayPinned(next);
  };

  const cycleOpacity = () => {
    setOpacity((prev) => (prev > 0.85 ? 0.62 : prev > 0.68 ? 0.92 : 0.80));
  };

  const cycleFont = () => {
    setFontSize((prev) => (prev >= 20 ? 14 : prev + 2));
  };

  const hideWindow = async () => {
    if (isTauri()) {
      await getCurrentWindow().hide();
    }
  };

  return (
    <div className="w-screen h-screen p-2 flex items-center justify-center bg-transparent">
      <div
        data-tauri-drag-region
        className="group relative w-full h-full rounded-[20px] border backdrop-blur-xl px-5 py-3.5 flex items-center cursor-move transition-all"
        style={{
          backgroundColor: `rgba(8, 9, 15, ${opacity})`,
          borderColor: "rgba(168, 85, 247, 0.40)",
          boxShadow: "0 12px 36px rgba(0, 0, 0, 0.45), 0 0 24px rgba(6, 182, 212, 0.16)",
        }}
      >
        <p
          data-tauri-drag-region
          className={clsx(
            "w-full text-center font-medium leading-snug line-clamp-3 pointer-events-none",
            kind === "error" && "text-rose-300",
            kind === "partial" && "text-slate-300/90 italic",
            (kind === "final" || kind === "idle") && "text-slate-100",
          )}
          style={{ fontSize: `${fontSize}px` }}
        >
          {line || "—"}
        </p>

        <div className="absolute top-2 right-2.5 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-200 rounded-full px-1.5 py-1 bg-black/55 border border-white/10">
          <button
            type="button"
            onClick={togglePin}
            title="Pin on top"
            className={clsx("p-1 rounded-full hover:bg-white/10", pinned ? "text-cyan-400" : "text-slate-400")}
          >
            {pinned ? <Pin className="w-3.5 h-3.5" /> : <PinOff className="w-3.5 h-3.5" />}
          </button>
          <button
            type="button"
            onClick={cycleOpacity}
            title="Opacity"
            className="p-1 rounded-full hover:bg-white/10 text-slate-300"
          >
            <Eye className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={cycleFont}
            title="Font Size"
            className="p-1 rounded-full hover:bg-white/10 text-slate-300"
          >
            <Type className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={hideWindow}
            title="Close"
            className="p-1 rounded-full hover:bg-rose-500/30 text-rose-300"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
};

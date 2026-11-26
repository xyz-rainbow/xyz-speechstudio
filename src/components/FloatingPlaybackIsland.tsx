import React from "react";
import { Pause, Play } from "lucide-react";
import type { PlaybackIslandState } from "./ChunkedAudioPlayer";

interface FloatingPlaybackIslandProps {
  visible: boolean;
  state: PlaybackIslandState;
  onTogglePlay: () => void;
  onOpenSynthesize: () => void;
}

export const FloatingPlaybackIsland: React.FC<FloatingPlaybackIslandProps> = ({
  visible,
  state,
  onTogglePlay,
  onOpenSynthesize,
}) => {
  if (!visible || !state.active) return null;

  return (
    <div className="fixed top-2.5 left-1/2 -translate-x-1/2 z-50">
      <div className="ss-audio-island flex items-center gap-2 px-2.5 py-1 text-[11px] font-mono text-white shadow-lg">
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onTogglePlay();
          }}
          className="w-5 h-5 rounded-full flex items-center justify-center bg-[#39ff14]/20 border border-[#39ff14]/65 text-[#39ff14] hover:bg-[#39ff14]/30 transition-colors"
          title={state.isPlaying ? "Pause" : "Play"}
        >
          {state.isPlaying ? (
            <Pause className="w-2.5 h-2.5" />
          ) : (
            <Play className="w-2.5 h-2.5 ml-0.5" />
          )}
        </button>

        <button
          type="button"
          onClick={onOpenSynthesize}
          className="flex items-center gap-2 hover:opacity-95 transition-opacity"
        >
          <span className="flex items-end gap-[2px] h-3" aria-hidden>
            <span
              className={`ss-eq-bar ${state.isPlaying ? "" : "paused"}`}
              style={{ animationDelay: "0ms" }}
            />
            <span
              className={`ss-eq-bar ${state.isPlaying ? "" : "paused"}`}
              style={{ animationDelay: "180ms" }}
            />
            <span
              className={`ss-eq-bar ${state.isPlaying ? "" : "paused"}`}
              style={{ animationDelay: "340ms" }}
            />
          </span>
          <div className="w-16 h-1.5 rounded-full bg-white/15 overflow-hidden">
            <div
              className="h-full rounded-full bg-[#39ff14] transition-[width] duration-150"
              style={{ width: `${state.progressPct}%` }}
            />
          </div>
          <span className="text-[11px] font-semibold text-white whitespace-nowrap">
            {state.timeLabel}
          </span>
          {state.chunkLabel && (
            <span className="text-[10px] text-[#39ff14]">{state.chunkLabel}</span>
          )}
        </button>
      </div>
    </div>
  );
};

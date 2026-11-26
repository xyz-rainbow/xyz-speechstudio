import React, { useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { Pause, Play, Volume2, VolumeX } from "lucide-react";

export interface AudioChunkItem {
  index: number;
  text: string;
  audioUrl?: string;
  durationS?: number;
}

export interface PlaybackIslandState {
  active: boolean;
  isPlaying: boolean;
  isGenerating: boolean;
  progressPct: number;
  timeLabel: string;
  chunkLabel: string;
}

export interface ChunkedAudioPlayerHandle {
  togglePlay: () => void;
  pause: () => void;
  playFromStart: () => void;
  isPlaying: () => boolean;
  isPausedMidway: () => boolean;
}

interface ChunkedAudioPlayerProps {
  chunks: AudioChunkItem[];
  singleUrl?: string | null;
  isGenerating?: boolean;
  autoPlayNonce?: number;
  onPlaybackChange?: (state: PlaybackIslandState) => void;
  onEndedAll?: () => void;
}

const SPEED_STEPS = [1, 1.25, 1.5, 2, 3, 0.75] as const;

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const whole = Math.floor(seconds);
  const mins = Math.floor(whole / 60);
  const secs = whole % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

export const ChunkedAudioPlayer = React.forwardRef<
  ChunkedAudioPlayerHandle,
  ChunkedAudioPlayerProps
>(({ chunks, singleUrl, isGenerating = false, autoPlayNonce = 0, onPlaybackChange, onEndedAll }, ref) => {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const trackRef = useRef<HTMLDivElement | null>(null);

  const items: AudioChunkItem[] = useMemo(() => {
    if (singleUrl) {
      return [{ index: 0, text: "", audioUrl: singleUrl }];
    }
    return chunks;
  }, [chunks, singleUrl]);

  const [currentIndex, setCurrentIndex] = useState(0);
  const [chunkLocalTime, setChunkLocalTime] = useState(0);
  const [singleDuration, setSingleDuration] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [waitingNext, setWaitingNext] = useState(false);
  const [volume, setVolume] = useState(1);
  const [muted, setMuted] = useState(false);
  const [speedIdx, setSpeedIdx] = useState(0);
  const wantPlayRef = useRef(false);

  const speed = SPEED_STEPS[speedIdx];

  const { chunkStarts, readyDuration, totalEstimated, readyCount } = useMemo(() => {
    const starts: number[] = [];
    let acc = 0;
    let readyAcc = 0;
    let ready = 0;
    for (let i = 0; i < items.length; i++) {
      starts.push(acc);
      const item = items[i];
      const dur = singleUrl
        ? singleDuration
        : item.durationS && item.durationS > 0
          ? item.durationS
          : Math.max(1.2, item.text.length / 15);
      acc += dur;
      if (item.audioUrl) {
        ready++;
        readyAcc = acc;
      }
    }
    return {
      chunkStarts: starts,
      readyDuration: readyAcc,
      totalEstimated: Math.max(acc, 0.1),
      readyCount: ready,
    };
  }, [items, singleUrl, singleDuration]);

  const activeItem = items[currentIndex];
  const activeUrl = activeItem?.audioUrl || "";
  const globalTime = (chunkStarts[currentIndex] || 0) + chunkLocalTime;
  const allReady = items.length > 0 && readyCount === items.length;
  const progressPct = Math.min(100, Math.max(0, (globalTime / totalEstimated) * 100));
  const bufferPct = Math.min(100, Math.max(0, (readyDuration / totalEstimated) * 100));

  const timeLabel = `${formatTime(globalTime)} / ${allReady ? "" : "~"}${formatTime(totalEstimated)}`;
  const chunkLabel =
    items.length > 1 && !allReady ? `${readyCount}/${items.length}` : "";

  // Reset to chunk 0 when a brand-new playback session starts.
  useEffect(() => {
    if (!autoPlayNonce) return;
    setCurrentIndex(0);
    setChunkLocalTime(0);
    setWaitingNext(false);
    wantPlayRef.current = true;
  }, [autoPlayNonce]);

  // Reset if singleUrl changes.
  useEffect(() => {
    if (!singleUrl) return;
    setCurrentIndex(0);
    setChunkLocalTime(0);
    setSingleDuration(0);
  }, [singleUrl]);

  // Sync audio element attributes and auto-play when current chunk becomes ready.
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.volume = muted ? 0 : volume;
    audio.playbackRate = speed;
  }, [volume, muted, speed, activeUrl]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (!activeUrl) {
      if (wantPlayRef.current) setWaitingNext(true);
      return;
    }
    setWaitingNext(false);
    if (wantPlayRef.current && audio.paused) {
      audio.playbackRate = speed;
      audio.play().catch(() => {});
    }
  }, [activeUrl, speed]);

  // Report status upward for the floating island.
  useEffect(() => {
    onPlaybackChange?.({
      active: items.length > 0 && readyCount > 0,
      isPlaying: isPlaying || waitingNext,
      isGenerating,
      progressPct,
      timeLabel,
      chunkLabel,
    });
  }, [items.length, readyCount, isPlaying, waitingNext, isGenerating, progressPct, timeLabel, chunkLabel, onPlaybackChange]);

  const togglePlay = useCallback(() => {
    const audio = audioRef.current;
    if (!audio || items.length === 0) return;
    if (isPlaying || waitingNext) {
      wantPlayRef.current = false;
      setWaitingNext(false);
      audio.pause();
      setIsPlaying(false);
      return;
    }
    // If at end of last chunk, restart from chunk 0.
    const lastReady = items.length - 1;
    if (
      currentIndex === lastReady &&
      audio.ended
    ) {
      setCurrentIndex(0);
      setChunkLocalTime(0);
      wantPlayRef.current = true;
      setTimeout(() => {
        if (audioRef.current) {
          audioRef.current.currentTime = 0;
          audioRef.current.play().catch(() => {});
        }
      }, 20);
      return;
    }
    wantPlayRef.current = true;
    if (activeUrl) {
      audio.playbackRate = speed;
      audio.play().catch(() => {});
    } else {
      setWaitingNext(true);
    }
  }, [items.length, isPlaying, waitingNext, currentIndex, activeUrl, speed]);

  useImperativeHandle(
    ref,
    () => ({
      togglePlay,
      pause: () => {
        wantPlayRef.current = false;
        setWaitingNext(false);
        audioRef.current?.pause();
      },
      playFromStart: () => {
        setCurrentIndex(0);
        setChunkLocalTime(0);
        wantPlayRef.current = true;
        setTimeout(() => {
          if (audioRef.current && items[0]?.audioUrl) {
            audioRef.current.currentTime = 0;
            audioRef.current.playbackRate = speed;
            audioRef.current.play().catch(() => {});
          }
        }, 20);
      },
      isPlaying: () => isPlaying || waitingNext,
      isPausedMidway: () => {
        const a = audioRef.current;
        return !!a && a.paused && !a.ended && (globalTime > 0 || currentIndex > 0);
      },
    }),
    [togglePlay, items, speed, isPlaying, waitingNext, globalTime, currentIndex]
  );

  const handleTrackSeek = (e: React.MouseEvent<HTMLDivElement>) => {
    const el = trackRef.current;
    if (!el || items.length === 0 || readyDuration <= 0) return;
    const rect = el.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    const targetSec = Math.min(ratio * totalEstimated, Math.max(0, readyDuration - 0.05));

    let targetIdx = 0;
    for (let i = 0; i < items.length; i++) {
      if (!items[i].audioUrl) break;
      if ((chunkStarts[i] || 0) <= targetSec) {
        targetIdx = i;
      }
    }
    const localOffset = Math.max(0, targetSec - (chunkStarts[targetIdx] || 0));
    if (targetIdx !== currentIndex) {
      setCurrentIndex(targetIdx);
      setChunkLocalTime(localOffset);
      setTimeout(() => {
        if (audioRef.current) {
          audioRef.current.currentTime = localOffset;
          if (wantPlayRef.current) audioRef.current.play().catch(() => {});
        }
      }, 30);
    } else if (audioRef.current) {
      audioRef.current.currentTime = localOffset;
      setChunkLocalTime(localOffset);
    }
  };

  const handleEnded = () => {
    if (currentIndex + 1 < items.length) {
      const nextIdx = currentIndex + 1;
      setCurrentIndex(nextIdx);
      setChunkLocalTime(0);
      if (items[nextIdx]?.audioUrl) {
        wantPlayRef.current = true;
      } else {
        setWaitingNext(true);
      }
    } else {
      wantPlayRef.current = false;
      setIsPlaying(false);
      setWaitingNext(false);
      onEndedAll?.();
    }
  };

  if (items.length === 0) return null;

  return (
    <div
      className="flex items-center gap-2.5 rounded-xl border px-3 py-1.5 shrink-0 select-none"
      style={{ backgroundColor: "var(--bg-input)", borderColor: "var(--border-glass)" }}
    >
      <audio
        ref={audioRef}
        src={activeUrl || undefined}
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
        onTimeUpdate={(e) => setChunkLocalTime(e.currentTarget.currentTime)}
        onLoadedMetadata={(e) => {
          e.currentTarget.playbackRate = speed;
          if (singleUrl) setSingleDuration(e.currentTarget.duration || 0);
        }}
        onEnded={handleEnded}
      />

      <button
        type="button"
        onClick={togglePlay}
        disabled={!items[0]?.audioUrl && !activeUrl}
        className="w-7 h-7 rounded-full flex items-center justify-center border border-purple-400/50 bg-purple-500/20 hover:bg-purple-500/35 text-white shrink-0 transition-colors disabled:opacity-40"
      >
        {isPlaying || waitingNext ? (
          <Pause className="w-3.5 h-3.5" />
        ) : (
          <Play className="w-3.5 h-3.5 ml-0.5" />
        )}
      </button>

      <div className="flex-1 min-w-0 flex flex-col gap-1">
        <div
          ref={trackRef}
          onClick={handleTrackSeek}
          className="relative h-2 w-full rounded-full bg-white/10 cursor-pointer overflow-hidden group"
        >
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-cyan-400/25 transition-all duration-200"
            style={{ width: `${bufferPct}%` }}
          />
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-purple-500 to-cyan-400 transition-[width] duration-75"
            style={{ width: `${progressPct}%` }}
          />
        </div>
      </div>

      <span className="text-[11px] font-mono shrink-0" style={{ color: "var(--text-secondary)" }}>
        {timeLabel}
      </span>

      {chunkLabel && (
        <span className="rounded-full px-1.5 py-0.5 text-[10px] font-mono bg-cyan-500/15 text-cyan-300 border border-cyan-500/35 shrink-0">
          {chunkLabel}
        </span>
      )}

      <div className="flex items-center gap-1 shrink-0">
        <button
          type="button"
          onClick={() => setMuted((m) => !m)}
          className="p-1 rounded-lg hover:bg-white/10 text-cyan-300 transition-colors"
          title={muted ? "Unmute" : "Mute"}
        >
          {muted || volume === 0 ? (
            <VolumeX className="w-3.5 h-3.5 text-rose-300" />
          ) : (
            <Volume2 className="w-3.5 h-3.5" />
          )}
        </button>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={muted ? 0 : volume}
          onChange={(e) => {
            const v = parseFloat(e.target.value);
            setVolume(v);
            if (v > 0 && muted) setMuted(false);
          }}
          className="w-12 h-1 accent-cyan-400 cursor-pointer"
        />
      </div>

      <button
        type="button"
        onClick={() => setSpeedIdx((i) => (i + 1) % SPEED_STEPS.length)}
        className="rounded-lg border px-1.5 py-0.5 text-[11px] font-mono hover:border-purple-400/60 transition-colors shrink-0 min-w-[38px] text-center"
        style={{
          borderColor: "var(--border-glass)",
          backgroundColor: "var(--bg-elevated)",
          color: speed !== 1 ? "#c084fc" : "var(--text-primary)",
        }}
        title="Playback speed"
      >
        {speed}x
      </button>
    </div>
  );
});

ChunkedAudioPlayer.displayName = "ChunkedAudioPlayer";

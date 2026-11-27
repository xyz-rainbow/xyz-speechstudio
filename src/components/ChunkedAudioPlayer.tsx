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

function knownDuration(node: HTMLAudioElement, item?: AudioChunkItem): number {
  const media =
    Number.isFinite(node.duration) && node.duration > 0 && node.duration < 1e6
      ? node.duration
      : 0;
  const reported = item?.durationS && item.durationS > 0 ? item.durationS : 0;
  return media || reported;
}

export const ChunkedAudioPlayer = React.forwardRef<
  ChunkedAudioPlayerHandle,
  ChunkedAudioPlayerProps
>(({ chunks, singleUrl, isGenerating = false, autoPlayNonce = 0, onPlaybackChange, onEndedAll }, ref) => {
  const aRef = useRef<HTMLAudioElement | null>(null);
  const bRef = useRef<HTMLAudioElement | null>(null);
  const trackRef = useRef<HTMLDivElement | null>(null);
  const itemsRef = useRef<AudioChunkItem[]>([]);
  const indexRef = useRef(0);
  const slotRef = useRef<0 | 1>(0);
  const wantPlayRef = useRef(false);
  const advancingRef = useRef(false);
  const pendingOffsetRef = useRef(0);

  const items: AudioChunkItem[] = useMemo(() => {
    if (singleUrl) {
      return [{ index: 0, text: "", audioUrl: singleUrl }];
    }
    return chunks;
  }, [chunks, singleUrl]);
  itemsRef.current = items;

  const [currentIndex, setCurrentIndex] = useState(0);
  const [slot, setSlot] = useState<0 | 1>(0);
  const [chunkLocalTime, setChunkLocalTime] = useState(0);
  const [singleDuration, setSingleDuration] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [waitingNext, setWaitingNext] = useState(false);
  const [volume, setVolume] = useState(1);
  const [muted, setMuted] = useState(false);
  const [speedIdx, setSpeedIdx] = useState(0);

  const speed = SPEED_STEPS[speedIdx];
  indexRef.current = currentIndex;
  slotRef.current = slot;

  const nodeFor = (which: 0 | 1) => (which === 0 ? aRef.current : bRef.current);

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

  const applyGain = useCallback(
    (node: HTMLAudioElement | null) => {
      if (!node) return;
      node.volume = muted ? 0 : volume;
      node.playbackRate = speed;
    },
    [muted, volume, speed]
  );

  const assignSrc = (node: HTMLAudioElement, url: string) => {
    if ((node.getAttribute("data-src") || "") === url) return false;
    node.setAttribute("data-src", url);
    if (url) {
      node.preload = "auto";
      node.src = url;
    } else {
      node.removeAttribute("src");
      node.load();
    }
    return true;
  };

  const startNode = (node: HTMLAudioElement, offset: number, fromStart: boolean) => {
    applyGain(node);
    const run = () => {
      try {
        if (offset > 0.01) {
          const limit = Number.isFinite(node.duration) ? Math.max(0, node.duration - 0.05) : offset;
          node.currentTime = Math.min(offset, limit);
        } else if (fromStart && node.currentTime > 0.05) {
          node.currentTime = 0;
        }
      } catch {
        // Not seekable until the new buffer is ready.
      }
      node.play().catch(() => {});
    };
    if (node.readyState >= 2) run();
    else node.addEventListener("canplay", run, { once: true });
  };

  const advanceFrom = useCallback(
    (fromIndex: number) => {
      if (advancingRef.current) return;
      if (fromIndex !== indexRef.current) return;
      const list = itemsRef.current;
      const nextIdx = fromIndex + 1;
      if (nextIdx >= list.length) {
        wantPlayRef.current = false;
        setIsPlaying(false);
        setWaitingNext(false);
        onEndedAll?.();
        return;
      }
      advancingRef.current = true;
      pendingOffsetRef.current = 0;
      setChunkLocalTime(0);
      if (!list[nextIdx]?.audioUrl) {
        setCurrentIndex(nextIdx);
        if (wantPlayRef.current) setWaitingNext(true);
        advancingRef.current = false;
        return;
      }
      setSlot((current) => {
        const nextSlot: 0 | 1 = current === 0 ? 1 : 0;
        slotRef.current = nextSlot;
        return nextSlot;
      });
      setCurrentIndex(nextIdx);
    },
    [onEndedAll]
  );

  useEffect(() => {
    if (!autoPlayNonce) return;
    setCurrentIndex(0);
    setSlot(0);
    slotRef.current = 0;
    setChunkLocalTime(0);
    setWaitingNext(false);
    pendingOffsetRef.current = 0;
    advancingRef.current = false;
    wantPlayRef.current = true;
    for (const node of [aRef.current, bRef.current]) {
      if (!node) continue;
      node.pause();
      node.removeAttribute("data-src");
      node.removeAttribute("src");
    }
  }, [autoPlayNonce]);

  useEffect(() => {
    if (!singleUrl) return;
    setCurrentIndex(0);
    setChunkLocalTime(0);
    setSingleDuration(0);
  }, [singleUrl]);

  // Active element plays the current chunk. The other element preloads the next one
  // so the handoff does not wait for a fresh decode (~200 ms).
  useEffect(() => {
    const active = nodeFor(slot);
    const idle = nodeFor(slot === 0 ? 1 : 0);
    const current = items[currentIndex];
    const next = items[currentIndex + 1];
    if (idle) {
      assignSrc(idle, next?.audioUrl || "");
      applyGain(idle);
    }
    if (!active) return;
    if (!current?.audioUrl) {
      if (wantPlayRef.current) setWaitingNext(true);
      advancingRef.current = false;
      return;
    }
    setWaitingNext(false);
    const switched = assignSrc(active, current.audioUrl);
    applyGain(active);
    if (wantPlayRef.current && active.paused) {
      const dur = knownDuration(active, current);
      const atEnd = !switched && dur > 0.2 && active.currentTime >= dur - 0.08;
      if (atEnd) {
        advanceFrom(currentIndex);
      } else if (switched) {
        const offset = pendingOffsetRef.current;
        pendingOffsetRef.current = 0;
        startNode(active, offset, offset < 0.01);
      } else {
        active.play().catch(() => {});
      }
    }
    advancingRef.current = false;
  }, [slot, currentIndex, items, applyGain, advanceFrom]);

  useEffect(() => {
    let lastTime = -1;
    let lastMove = performance.now();
    const id = window.setInterval(() => {
      if (!wantPlayRef.current) return;
      const node = nodeFor(slotRef.current);
      if (!node) return;
      const idx = indexRef.current;
      const item = itemsRef.current[idx];
      if (!item?.audioUrl) return;
      const dur = knownDuration(node, item);
      const now = performance.now();
      if (Math.abs(node.currentTime - lastTime) > 0.02) {
        lastTime = node.currentTime;
        lastMove = now;
      }
      const frozenMs = now - lastMove;
      const nextExists = idx + 1 < itemsRef.current.length;
      const atEnd = dur > 0.2 && (node.ended || node.currentTime >= dur - 0.03);
      // Kokoro WAVs can stall on the last frame without firing `ended`.
      const stalledAtEnd =
        nextExists &&
        node.currentTime > 0.4 &&
        frozenMs > 350 &&
        ((dur > 0 && node.currentTime >= dur - 0.45) ||
          (dur === 0 && !node.paused && node.readyState >= 2));
      if (atEnd || stalledAtEnd) {
        advanceFrom(idx);
        return;
      }
      if (node.paused && node.readyState >= 2 && !node.ended && node.currentTime < Math.max(0, dur - 0.08)) {
        node.play().catch(() => {});
      }
    }, 40);
    return () => window.clearInterval(id);
  }, [advanceFrom, slot]);

  useEffect(() => {
    onPlaybackChange?.({
      active: items.length > 0 && readyCount > 0,
      isPlaying: isPlaying || waitingNext,
      isGenerating,
      progressPct,
      timeLabel,
      chunkLabel,
    });
  }, [
    items.length,
    readyCount,
    isPlaying,
    waitingNext,
    isGenerating,
    progressPct,
    timeLabel,
    chunkLabel,
    onPlaybackChange,
  ]);

  const togglePlay = useCallback(() => {
    const audio = nodeFor(slotRef.current);
    if (!audio || items.length === 0) return;
    if (isPlaying || waitingNext) {
      wantPlayRef.current = false;
      setWaitingNext(false);
      aRef.current?.pause();
      bRef.current?.pause();
      setIsPlaying(false);
      return;
    }
    const atEnd =
      currentIndex >= items.length - 1 &&
      (audio.ended || audio.currentTime >= knownDuration(audio, items[currentIndex]) - 0.05);
    if (atEnd && items[currentIndex]?.audioUrl) {
      pendingOffsetRef.current = 0;
      setCurrentIndex(0);
      setSlot(0);
      slotRef.current = 0;
      setChunkLocalTime(0);
      wantPlayRef.current = true;
      return;
    }
    wantPlayRef.current = true;
    if (activeUrl) {
      startNode(audio, audio.currentTime, false);
    } else {
      setWaitingNext(true);
    }
  }, [items, isPlaying, waitingNext, currentIndex, activeUrl, applyGain]);

  useImperativeHandle(
    ref,
    () => ({
      togglePlay,
      pause: () => {
        wantPlayRef.current = false;
        setWaitingNext(false);
        aRef.current?.pause();
        bRef.current?.pause();
      },
      playFromStart: () => {
        pendingOffsetRef.current = 0;
        setCurrentIndex(0);
        setSlot(0);
        slotRef.current = 0;
        setChunkLocalTime(0);
        wantPlayRef.current = true;
      },
      isPlaying: () => isPlaying || waitingNext,
      isPausedMidway: () => {
        const a = nodeFor(slotRef.current);
        return !!a && a.paused && !a.ended && (globalTime > 0 || currentIndex > 0);
      },
    }),
    [togglePlay, isPlaying, waitingNext, globalTime, currentIndex]
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
      if ((chunkStarts[i] || 0) <= targetSec) targetIdx = i;
    }
    const localOffset = Math.max(0, targetSec - (chunkStarts[targetIdx] || 0));
    const targetUrl = items[targetIdx]?.audioUrl || "";
    const idleSlot: 0 | 1 = slotRef.current === 0 ? 1 : 0;
    const idle = nodeFor(idleSlot);
    pendingOffsetRef.current = localOffset;
    wantPlayRef.current = true;
    if (targetIdx !== currentIndex) {
      if (idle && targetUrl && (idle.getAttribute("data-src") || "") === targetUrl) {
        slotRef.current = idleSlot;
        setSlot(idleSlot);
      }
      setCurrentIndex(targetIdx);
      setChunkLocalTime(localOffset);
    } else {
      const active = nodeFor(slotRef.current);
      if (active) {
        try {
          active.currentTime = localOffset;
        } catch {
          // Seek lands in startNode once the buffer is ready.
        }
        setChunkLocalTime(localOffset);
        if (active.paused) startNode(active, localOffset, false);
      }
    }
  };

  const handleTimeUpdate = (which: 0 | 1) => (e: React.SyntheticEvent<HTMLAudioElement>) => {
    if (slotRef.current !== which) return;
    const node = e.currentTarget;
    setChunkLocalTime(node.currentTime);
    const dur = knownDuration(node, itemsRef.current[indexRef.current]);
    if (wantPlayRef.current && dur > 0.2 && node.currentTime >= dur - 0.03) {
      advanceFrom(indexRef.current);
    }
  };

  const handleEnded = (which: 0 | 1) => () => {
    if (slotRef.current !== which) return;
    if (singleUrl) setIsPlaying(false);
    advanceFrom(indexRef.current);
  };

  const handlePlay = (which: 0 | 1) => () => {
    if (slotRef.current !== which) return;
    setIsPlaying(true);
    const other = nodeFor(which === 0 ? 1 : 0);
    if (other && !other.paused && (other.getAttribute("data-src") || "") !== activeUrl) {
      other.pause();
    }
  };

  const handlePause = (which: 0 | 1) => () => {
    if (slotRef.current !== which || wantPlayRef.current) return;
    setIsPlaying(false);
  };

  if (items.length === 0) return null;

  return (
    <div
      className="flex items-center gap-2.5 rounded-xl border px-3 py-1.5 shrink-0 select-none"
      style={{ backgroundColor: "var(--bg-input)", borderColor: "var(--border-glass)" }}
    >
      <audio
        ref={aRef}
        preload="auto"
        onPlay={handlePlay(0)}
        onPause={handlePause(0)}
        onTimeUpdate={handleTimeUpdate(0)}
        onEnded={handleEnded(0)}
        onLoadedMetadata={(e) => {
          e.currentTarget.playbackRate = speed;
          if (singleUrl && slotRef.current === 0) setSingleDuration(e.currentTarget.duration || 0);
        }}
      />
      <audio
        ref={bRef}
        preload="auto"
        onPlay={handlePlay(1)}
        onPause={handlePause(1)}
        onTimeUpdate={handleTimeUpdate(1)}
        onEnded={handleEnded(1)}
        onLoadedMetadata={(e) => {
          e.currentTarget.playbackRate = speed;
        }}
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

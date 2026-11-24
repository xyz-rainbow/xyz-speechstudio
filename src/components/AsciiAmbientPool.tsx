import React, { useEffect, useRef } from "react";
import type { AccentPreset, ThemeMode } from "../types";

export interface AsciiAmbientPoolProps {
  enabled?: boolean;
  opacity?: number;
  theme?: ThemeMode;
  accent?: AccentPreset;
  characterSet?: string;
}

const DEFAULT_CHARS = " ·+~*^°x01Δλ§:";
const TARGET_FRAME_MS = 1000 / 30;
const MOUSE_RADIUS_SQ = 220 * 220;

const PALETTE: Record<AccentPreset, [[number, number, number], [number, number, number]]> = {
  cyber: [[168, 85, 247], [6, 182, 212]],
  emerald: [[16, 185, 129], [6, 182, 212]],
  amber: [[245, 158, 11], [251, 113, 133]],
  rose: [[244, 63, 94], [168, 85, 247]],
};

export const AsciiAmbientPool: React.FC<AsciiAmbientPoolProps> = ({
  enabled = true,
  opacity = 0.13,
  theme = "dark",
  accent = "cyber",
  characterSet = DEFAULT_CHARS,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const mouseRef = useRef({ x: -9999, y: -9999, active: false });

  useEffect(() => {
    if (!enabled) return;

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let rafId = 0;
    let width = 0;
    let height = 0;
    let time = 0;
    let lastDraw = 0;
    let paused = document.visibilityState === "hidden";

    const charSize = 14;
    const chars = characterSet.split("");
    const [c1, c2] = PALETTE[accent] ?? PALETTE.cyber;
    const lightMul = theme === "light" ? 0.72 : 1.0;

    const buckets = 16;
    const colorTable: string[] = new Array(buckets);
    for (let i = 0; i < buckets; i++) {
      const t = i / (buckets - 1);
      const r = Math.round(c1[0] * t + c2[0] * (1 - t));
      const g = Math.round(c1[1] * t + c2[1] * (1 - t));
      const b = Math.round(c1[2] * t + c2[2] * (1 - t));
      colorTable[i] = `rgb(${r},${g},${b})`;
    }

    const resize = () => {
      width = window.innerWidth;
      height = window.innerHeight;
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.font = `${charSize}px "JetBrains Mono", monospace`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
    };

    resize();
    window.addEventListener("resize", resize);

    const onMove = (e: MouseEvent) => {
      mouseRef.current.x = e.clientX;
      mouseRef.current.y = e.clientY;
      mouseRef.current.active = true;
    };
    const onLeave = () => {
      mouseRef.current.active = false;
    };
    const onVis = () => {
      paused = document.visibilityState === "hidden";
    };

    window.addEventListener("mousemove", onMove, { passive: true });
    document.addEventListener("mouseleave", onLeave);
    document.addEventListener("visibilitychange", onVis);

    const render = (now: number) => {
      rafId = requestAnimationFrame(render);
      if (paused || (lastDraw !== 0 && now - lastDraw < TARGET_FRAME_MS)) return;
      lastDraw = now;
      time += 0.032;

      ctx.clearRect(0, 0, width, height);
      const cols = Math.floor(width / charSize);
      const rows = Math.floor(height / charSize);
      const mouse = mouseRef.current;

      for (let r = 0; r < rows; r += 2) {
        const y = r * charSize + charSize * 0.5;
        for (let c = 0; c < cols; c += 2) {
          const x = c * charSize + charSize * 0.5;
          let mouseInfluence = 0;
          if (mouse.active) {
            const dx = mouse.x - x;
            const dy = mouse.y - y;
            const distSq = dx * dx + dy * dy;
            if (distSq < MOUSE_RADIUS_SQ) {
              mouseInfluence = 1 - Math.sqrt(distSq) / 220;
            }
          }

          const wave =
            Math.sin(c * 0.08 + time) * 0.5 +
            Math.cos(r * 0.08 - time * 0.8) * 0.5 +
            mouseInfluence * 1.4;

          const idx = Math.min(
            chars.length - 1,
            Math.max(0, Math.floor(((wave + 1) * 0.5) * chars.length))
          );
          const ch = chars[idx];
          if (ch && ch !== " ") {
            const ratio = (Math.sin(time + c * 0.05) + 1) * 0.5;
            const bucket = Math.min(buckets - 1, Math.floor(ratio * buckets));
            ctx.globalAlpha = Math.min(0.62, (opacity * 1.65 + mouseInfluence * 0.32) * lightMul);
            ctx.fillStyle = colorTable[bucket];
            ctx.fillText(ch, x, y);
          }
        }
      }
      ctx.globalAlpha = 1;
    };

    rafId = requestAnimationFrame(render);
    return () => {
      cancelAnimationFrame(rafId);
      window.removeEventListener("resize", resize);
      window.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseleave", onLeave);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [enabled, opacity, theme, accent, characterSet]);

  if (!enabled) return null;

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 pointer-events-none z-0 w-screen h-screen"
    />
  );
};

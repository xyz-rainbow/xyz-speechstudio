/**
 * Pure helpers for chunked TTS playback — generation tokens discard stale updates.
 */

export interface ChunkState {
  index: number;
  text: string;
  audioUrl?: string;
  durationS?: number;
}

export interface ChunkPatch {
  audioUrl: string;
  durationS: number;
}

/** True when an advance request still matches the live playhead. */
export function canAdvanceFrom(
  fromIndex: number,
  currentIndex: number,
  advancing: boolean,
): boolean {
  if (advancing) return false;
  return fromIndex === currentIndex;
}

/** Next index after finishing `fromIndex`, or null when the playlist is done. */
export function nextChunkIndex(fromIndex: number, length: number): number | null {
  if (length <= 0) return null;
  const next = fromIndex + 1;
  return next < length ? next : null;
}

/**
 * Apply a synthesized chunk only if it belongs to the active generation
 * and does not clobber a different index / newer URL.
 */
export function applyChunkResult(
  chunks: ChunkState[],
  index: number,
  patch: ChunkPatch,
  generation: number,
  expectedGeneration: number,
): ChunkState[] {
  if (generation !== expectedGeneration) return chunks;
  if (index < 0 || index >= chunks.length) return chunks;
  return chunks.map((item) =>
    item.index === index
      ? { ...item, audioUrl: patch.audioUrl, durationS: patch.durationS }
      : item,
  );
}

/** Reject out-of-order or duplicate ready indices for a session. */
export function assertChunkSequence(chunks: ChunkState[]): {
  ok: boolean;
  reason?: string;
} {
  if (chunks.length === 0) return { ok: true };
  for (let i = 0; i < chunks.length; i++) {
    if (chunks[i].index !== i) {
      return { ok: false, reason: `index gap at ${i}: got ${chunks[i].index}` };
    }
  }
  let sawHole = false;
  for (const item of chunks) {
    if (item.audioUrl) {
      if (sawHole) return { ok: false, reason: "ready chunk after hole" };
    } else {
      sawHole = true;
    }
  }
  return { ok: true };
}

/** Contiguous ready prefix length (playback can only seek within this). */
export function readyPrefixLength(chunks: ChunkState[]): number {
  let n = 0;
  for (const item of chunks) {
    if (!item.audioUrl) break;
    n += 1;
  }
  return n;
}

export function shouldDiscardSynth(
  token: number,
  currentToken: number,
  aborted: boolean,
): boolean {
  return aborted || token !== currentToken;
}

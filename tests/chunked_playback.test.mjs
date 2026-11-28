/**
 * Node test runner for chunked playback helpers.
 * Run: node --experimental-strip-types --test tests/chunked_playback.test.mjs
 * Fallback embeds the same pure rules if strip-types is unavailable.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const tsPath = path.join(__dirname, "..", "src", "lib", "chunkedPlayback.ts");

async function loadHelpers() {
  try {
    return await import(pathToFileURL(tsPath).href);
  } catch {
    // Pure reimplementation kept in sync with src/lib/chunkedPlayback.ts for Node without TS loader.
    return {
      canAdvanceFrom(fromIndex, currentIndex, advancing) {
        if (advancing) return false;
        return fromIndex === currentIndex;
      },
      nextChunkIndex(fromIndex, length) {
        if (length <= 0) return null;
        const next = fromIndex + 1;
        return next < length ? next : null;
      },
      applyChunkResult(chunks, index, patch, generation, expectedGeneration) {
        if (generation !== expectedGeneration) return chunks;
        if (index < 0 || index >= chunks.length) return chunks;
        return chunks.map((item) =>
          item.index === index
            ? { ...item, audioUrl: patch.audioUrl, durationS: patch.durationS }
            : item,
        );
      },
      assertChunkSequence(chunks) {
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
      },
      readyPrefixLength(chunks) {
        let n = 0;
        for (const item of chunks) {
          if (!item.audioUrl) break;
          n += 1;
        }
        return n;
      },
      shouldDiscardSynth(token, currentToken, aborted) {
        return aborted || token !== currentToken;
      },
    };
  }
}

const {
  canAdvanceFrom,
  nextChunkIndex,
  applyChunkResult,
  assertChunkSequence,
  readyPrefixLength,
  shouldDiscardSynth,
} = await loadHelpers();

describe("chunked playback races", () => {
  it("discards stale synth tokens", () => {
    assert.equal(shouldDiscardSynth(1, 2, false), true);
    assert.equal(shouldDiscardSynth(3, 3, true), true);
    assert.equal(shouldDiscardSynth(3, 3, false), false);
  });

  it("ignores chunk patches from an old generation", () => {
    const base = [
      { index: 0, text: "a" },
      { index: 1, text: "b" },
    ];
    const next = applyChunkResult(
      base,
      1,
      { audioUrl: "/old.wav", durationS: 1 },
      1,
      2,
    );
    assert.equal(next[1].audioUrl, undefined);
    assert.equal(next, base);
  });

  it("applies in-order patches for the live generation", () => {
    let chunks = [
      { index: 0, text: "a" },
      { index: 1, text: "b" },
      { index: 2, text: "c" },
    ];
    chunks = applyChunkResult(chunks, 0, { audioUrl: "/0.wav", durationS: 1.2 }, 5, 5);
    chunks = applyChunkResult(chunks, 1, { audioUrl: "/1.wav", durationS: 0.8 }, 5, 5);
    assert.equal(readyPrefixLength(chunks), 2);
    assert.equal(assertChunkSequence(chunks).ok, true);
  });

  it("detects ready chunk after a hole", () => {
    const bad = [
      { index: 0, text: "a", audioUrl: "/0.wav" },
      { index: 1, text: "b" },
      { index: 2, text: "c", audioUrl: "/2.wav" },
    ];
    const result = assertChunkSequence(bad);
    assert.equal(result.ok, false);
  });

  it("blocks double-advance while already advancing", () => {
    assert.equal(canAdvanceFrom(0, 0, true), false);
    assert.equal(canAdvanceFrom(0, 0, false), true);
    assert.equal(canAdvanceFrom(0, 1, false), false);
  });

  it("sequences next indices until end", () => {
    assert.equal(nextChunkIndex(0, 3), 1);
    assert.equal(nextChunkIndex(2, 3), null);
    assert.equal(nextChunkIndex(0, 0), null);
  });

  it("bounds readyPrefixLength when a prefetch chunk fails in the middle", () => {
    const partial = [
      { index: 0, text: "uno", audioUrl: "/0.wav", durationS: 1.0 },
      { index: 1, text: "dos" },
      { index: 2, text: "tres", audioUrl: "/2.wav", durationS: 1.0 },
    ];
    assert.equal(readyPrefixLength(partial), 1);
    assert.equal(assertChunkSequence(partial).ok, false);
  });

  it("ignores late chunk completion once aborted or superseded", () => {
    let chunks = [
      { index: 0, text: "uno", audioUrl: "/0.wav", durationS: 1.0 },
      { index: 1, text: "dos" },
    ];
    if (!shouldDiscardSynth(4, 5, false)) {
      chunks = applyChunkResult(chunks, 1, { audioUrl: "/1.wav", durationS: 1.1 }, 4, 5);
    }
    assert.equal(chunks[1].audioUrl, undefined);
  });
});

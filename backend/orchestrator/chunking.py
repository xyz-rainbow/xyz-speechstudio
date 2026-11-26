"""Sentence- and word-aware text chunking for low-latency progressive TTS playback."""

from __future__ import annotations

import re

_SENTENCE_END = re.compile(r'[.!?…]+(?:["\')\]»]+)?(?=\s|$)')
_CLAUSE_END = re.compile(r'[,;:—–](?=\s)')
_WHITESPACE = re.compile(r'\s+')


def _clean_paragraph(paragraph: str) -> str:
    return _WHITESPACE.sub(" ", paragraph).strip()


def _pick_split_index(segment: str, max_chars: int) -> int:
    if len(segment) <= max_chars:
        return len(segment)

    min_len = max(40, int(max_chars * 0.55))
    max_len = min(len(segment), int(max_chars * 1.15))

    # 1. Prefer a sentence terminator within [0.55 * max_chars, 1.15 * max_chars].
    best_sentence: int | None = None
    best_dist = 10**9
    for match in _SENTENCE_END.finditer(segment, 0, max_len):
        end_pos = match.end()
        if end_pos < min_len:
            continue
        dist = abs(max_chars - end_pos)
        if dist < best_dist or (dist == best_dist and end_pos <= max_chars):
            best_dist = dist
            best_sentence = end_pos
    if best_sentence is not None:
        return best_sentence

    # 2. If sentence terminator is too far (beyond 1.15x), fall back to clause punctuation <= max_chars.
    best_clause: int | None = None
    for match in _CLAUSE_END.finditer(segment, 0, max_chars):
        if match.end() >= min_len:
            best_clause = match.end()
    if best_clause is not None:
        return best_clause

    # 3. Cut at the last whitespace <= max_chars (never inside a word).
    space_idx = segment.rfind(" ", 0, max_chars + 1)
    if space_idx > 0:
        return space_idx

    # 4. Single long token exceeding max_chars: advance to next whitespace.
    next_space = segment.find(" ", max_chars)
    return next_space if next_space != -1 else len(segment)


def split_text_into_chunks(text: str, max_chars: int = 300) -> list[str]:
    """Split text into chunks without cutting words.

    Respects sentence endings (., !, ?) when they land reasonably near ``max_chars``
    (between 55% and 115% of ``max_chars``). If a sentence runs well past that window,
    falls back to clause punctuation or whitespace so playback starts promptly.
    """
    raw = (text or "").strip()
    if not raw:
        return []

    limit = max(80, int(max_chars))
    paragraphs = [_clean_paragraph(p) for p in re.split(r"\r?\n\s*\r?\n+", raw)]
    paragraphs = [p for p in paragraphs if p]

    chunks: list[str] = []
    for para in paragraphs:
        rest = para
        while rest:
            if len(rest) <= limit:
                chunks.append(rest)
                break
            idx = _pick_split_index(rest, limit)
            head = rest[:idx].strip()
            tail = rest[idx:].strip()
            if head:
                chunks.append(head)
            rest = tail
    return chunks

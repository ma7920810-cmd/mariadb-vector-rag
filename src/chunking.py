"""Reproducible chunking for Wikipedia articles.

Two strategies:

* ``chunk_text`` - the original fixed word window (kept for compatibility).
* ``chunk_sections`` - used by the ingestion pipeline. Chunks never cross a
  section boundary, are cut at sentence boundaries, overlap by whole sentences
  and stay below the embedding model's input limit. Each chunk records its
  section heading and an ``embed_text`` that prefixes "Title — Section:" so the
  vector knows what the passage is about even when the passage itself only
  says "it" or "this method".
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from src.config import CHUNK_OVERLAP, CHUNK_WORDS, MIN_CHUNK_WORDS

# Bump when chunking behaviour changes so existing articles are re-chunked.
CHUNKER_VERSION = "sections-v1"

# Candidate sentence boundary: terminal punctuation, optional closing quote or
# bracket, whitespace, then something that looks like a sentence start.
_BOUNDARY = re.compile(r"(?<=[.!?])([\"')\]]?)\s+(?=[\"'(\[]?[A-Z0-9])")
# Tokens after which a period does not end the sentence.
_ABBREVIATIONS = {"e.g.", "i.e.", "etc.", "vs.", "cf.", "al.", "no.", "fig.",
                  "mr.", "mrs.", "dr.", "prof.", "st.", "approx.", "ca.", "c.",
                  "vol.", "pp.", "p.", "eq.", "ed.", "jr.", "sr.", "inc.", "ltd."}


def clean_text(text):
    text = re.sub(r"\[[0-9]+\]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def chunk_text(text, size=CHUNK_WORDS, overlap=CHUNK_OVERLAP):
    """Fixed-size word windows (original strategy, kept for compatibility)."""
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("Require size > overlap >= 0.")
    words = clean_text(text).split()
    chunks = []
    step = size - overlap
    for start in range(0, len(words), step):
        piece = words[start:start + size]
        if not piece:
            break
        if len(piece) >= 30:
            chunks.append(" ".join(piece))
        if start + size >= len(words):
            break
    return chunks


@dataclass
class Chunk:
    text: str
    section: str
    embed_text: str
    word_count: int
    content_hash: str


def normalized_hash(text: str) -> str:
    """Hash that ignores case, whitespace and punctuation differences."""
    norm = re.sub(r"[^\w]+", " ", text.lower()).strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _is_abbreviation(token: str) -> bool:
    token = token.lstrip("\"'([")
    return (token.lower() in _ABBREVIATIONS
            or re.fullmatch(r"[A-Z]\.", token) is not None          # initials: "J."
            or re.fullmatch(r"(?:[A-Za-z]\.){2,}", token) is not None)  # "U.S."


def _split_paragraph(paragraph: str) -> list[str]:
    sentences, start = [], 0
    for match in _BOUNDARY.finditer(paragraph):
        before = paragraph[start:match.start()].rsplit(None, 1)
        if before and _is_abbreviation(before[-1]):
            continue
        sentences.append(paragraph[start:match.end(1)].strip())
        start = match.end()
    sentences.append(paragraph[start:].strip())
    return [s for s in sentences if s]


def split_sentences(text: str) -> list[str]:
    """Split text into sentences, treating blank lines as paragraph breaks."""
    sentences = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = clean_text(paragraph)
        if paragraph:
            sentences += _split_paragraph(paragraph)
    return sentences


def _split_long(sentence: str, max_words: int) -> list[str]:
    words = sentence.split()
    return [" ".join(words[i:i + max_words]) for i in range(0, len(words), max_words)]


def _pack(sentences: list[str], max_words: int, overlap_words: int) -> list[str]:
    units = []
    for sentence in sentences:
        units += _split_long(sentence, max_words) if len(sentence.split()) > max_words else [sentence]

    chunks, current, count = [], [], 0
    for unit in units:
        n = len(unit.split())
        if current and count + n > max_words:
            chunks.append(" ".join(current))
            # Carry trailing whole sentences forward as overlap.
            carry, carried = [], 0
            for prev in reversed(current):
                m = len(prev.split())
                if carried + m > overlap_words:
                    break
                carry.insert(0, prev)
                carried += m
            if carried + n > max_words:
                carry, carried = [], 0
            current, count = carry, carried
        current.append(unit)
        count += n
    if current:
        tail = " ".join(current)
        # Drop a final window that is entirely overlap with the previous chunk.
        if not chunks or not chunks[-1].endswith(tail):
            chunks.append(tail)
    return chunks


def chunk_sections(sections, title: str, max_words: int = CHUNK_WORDS,
                   overlap_words: int = CHUNK_OVERLAP,
                   min_words: int = MIN_CHUNK_WORDS) -> list[Chunk]:
    """Chunk an article given as ``[(heading, text), ...]`` or Section objects.

    * Short sections are merged into the following section of the same
      top-level heading so they are not lost or embedded as fragments.
    * Exact/near-exact duplicate chunks within the article are removed.
    """
    if max_words <= 0 or overlap_words < 0 or overlap_words >= max_words:
        raise ValueError("Require max_words > overlap_words >= 0.")

    items = [(s.heading, s.text) if hasattr(s, "heading") else (s[0], s[1])
             for s in sections]

    # Merge sections too small to stand alone into their neighbour.
    merged: list[list] = []
    pending = None  # (heading, text) of a short section waiting to be merged
    for heading, text in items:
        if pending:
            same_parent = pending[0].split(" > ")[0] == heading.split(" > ")[0]
            if same_parent:
                heading, text = pending[0], pending[1] + "\n\n" + text
            else:
                merged.append(list(pending))
            pending = None
        if len(text.split()) < min_words:
            pending = (heading, text)
        else:
            merged.append([heading, text])
    if pending:
        if merged and len(merged[-1][1].split()) + len(pending[1].split()) <= max_words * 1.25:
            merged[-1][1] += "\n\n" + pending[1]
        else:
            merged.append(list(pending))

    chunks, seen = [], set()
    for heading, text in merged:
        for piece in _pack(split_sentences(text), max_words, overlap_words):
            words = len(piece.split())
            if words < min_words:
                continue
            digest = normalized_hash(piece)
            if digest in seen:
                continue
            seen.add(digest)
            context = title if heading in ("", "Introduction") else f"{title} — {heading}"
            chunks.append(Chunk(piece, heading, f"{context}: {piece}", words, digest))
    return chunks

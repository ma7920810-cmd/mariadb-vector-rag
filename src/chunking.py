"""Simple reproducible word-window chunking."""
import re
from src.config import CHUNK_WORDS, CHUNK_OVERLAP


def clean_text(text):
    text = re.sub(r"\[[0-9]+\]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def chunk_text(text, size=CHUNK_WORDS, overlap=CHUNK_OVERLAP):
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

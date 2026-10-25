"""Sentence-transformer embeddings used for both documents and queries."""
from functools import lru_cache
from sentence_transformers import SentenceTransformer
from src.config import EMBEDDING_MODEL


@lru_cache(maxsize=1)
def model():
    return SentenceTransformer(EMBEDDING_MODEL)


def embed_texts(texts):
    """Return normalized embeddings; all-MiniLM-L6-v2 produces 384 dimensions."""
    return model().encode(
        texts, normalize_embeddings=True, convert_to_numpy=True,
        show_progress_bar=len(texts) > 8
    )


def embed_query(text):
    return embed_texts([text])[0]

"""Shared embedding model — BGE-M3 via sentence-transformers.

Cached singleton: first call loads the model (~30s after disk cache);
subsequent calls reuse. Pre-load at app startup (main.py lifespan) so
the first query isn't slow.
"""

from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer


MODEL_NAME = "BAAI/bge-m3"


@lru_cache(maxsize=1)
def get_embedder() -> SentenceTransformer:
    """Load and cache the embedding model. Thread-safe via lru_cache lock."""
    return SentenceTransformer(MODEL_NAME)


def embed_query(query: str) -> np.ndarray:
    """Embed a single query. Returns 1024-dim normalized vector."""
    model = get_embedder()
    return model.encode(query, normalize_embeddings=True)
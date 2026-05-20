"""Cross-encoder reranker — BGE Reranker v2-m3.

Precision stage of 2-stage retrieval:
- stage 1 (embedder): fast cosine similarity over independent embeddings.
- stage 2 (this): cross-encoder attends to (query,document) jointly

Cross-encoders score relevance more accurately than dot-product on
separate embeddings because they see both texts together with full
token-level attention. Cost: slower(~50ms per pair vs ~1ms cosine).
"""

from functools import lru_cache

from sentence_transformers import CrossEncoder

MODEL_NAME = "BAAI/bge-reranker-v2-m3"

@lru_cache(maxsize=1)
def get_reranker() -> CrossEncoder:
    """Load and cache the reranker model. First call download ~2GB."""
    return CrossEncoder(MODEL_NAME)

def rerank(query:str, documents: list[dict]) -> list[tuple[dict, float]]:
    """Score and sort document by cross-encoder relevance to query.
    
    Args:
        query: Natural language query.
        document: List of document dicts(each must have 'body' key).
    
    Returns:
        List of (documents, rerank_score) tuples sorted by score descending.
        Scores are unbounded floats (typically -10 to + 10); higher = more relevant.
        Different scale from cosine similarity — do not mix.
    """
    if not documents:
        return []

    model = get_reranker()
    pairs = [(query, doc["body"]) for doc in documents]
    scores = model.predict(pairs)

    scored = list(zip(documents, [float(s) for s in scores]))
    scored.sort(key=lambda x:x[1], reverse=True)
    return scored



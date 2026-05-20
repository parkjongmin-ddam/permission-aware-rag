"""Types for permission-aware retrieval."""

from dataclasses import dataclass

from permission_aware_rag.permission.types import PolicyDecision


@dataclass(frozen=True)
class ScoredDocument:
    """A document returned from vector search with similarity and decision.
    
    `similarity` = cosine similarity from embedding (always present, 0-1).
    `rerank_score` = cross-enconder relevance score (None if rerank disabled).
    
    When both are present, rerank_score is the better relevance signal but
    has a different scale; do not arithmetic-mix the two.
    """

    id: str
    title: str
    body: str
    sub_type: str
    similarity: float
    decision: PolicyDecision
    rerank_score: float | None = None


@dataclass(frozen=True)
class RetrievalResult:
    """Result of a permission-aware retrieval."""

    allowed: list[ScoredDocument]
    denied: list[ScoredDocument]
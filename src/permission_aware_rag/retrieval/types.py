"""Types for permission-aware retrieval."""

from dataclasses import dataclass

from permission_aware_rag.permission.types import PolicyDecision


@dataclass(frozen=True)
class ScoredDocument:
    """A document returned from vector search with similarity and decision."""

    id: str
    title: str
    body: str
    sub_type: str
    similarity: float
    decision: PolicyDecision


@dataclass(frozen=True)
class RetrievalResult:
    """Result of a permission-aware retrieval.

    `allowed` is what the caller can see.
    `denied` is what was filtered out (for audit logging).
    """

    allowed: list[ScoredDocument]
    denied: list[ScoredDocument]
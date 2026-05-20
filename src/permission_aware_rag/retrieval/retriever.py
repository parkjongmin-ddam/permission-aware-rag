"""Permission-aware document retrieval with optional cross-encoder reranking.

Two-stage retrieval:
1. Embedding stage: pgvector HNSW top top_k * oversample_factor candidates
2. (Optional) Rerank stage: BGE Reranker v2-m3 keeps top rerank_keep
3. Permission stage: can_read() filters all reranked candidates

Returns ALL permission-allowed and permission-denied documents — does not
truncate to top_k here. The caller (API layer) is responsible for any
presentation-time slicing. This separation ensures audit logs capture
the full set of permission decisions, not just what was displayed.

Toggleable via use_reranker. Both signals are preserved on ScoredDocument
for downstream A/B comparison and observability.
"""

from permission_aware_rag.auth.dependencies import Principal
from permission_aware_rag.db.session import get_connection
from permission_aware_rag.permission.policy import can_read
from permission_aware_rag.retrieval.embedder import embed_query
from permission_aware_rag.retrieval.reranker import rerank as cross_encoder_rerank
from permission_aware_rag.retrieval.types import RetrievalResult, ScoredDocument


SEARCH_SQL = """
SELECT
    id, title, body, category, sub_type, sensitivity, language,
    subject, project_id, project_members, parties, case_id,
    stakeholders, severity, executive_briefed, disclosure_level, tags,
    expected_readers,
    1 - (embedding <=> %(q)s) AS similarity
FROM documents
ORDER BY embedding <=> %(q)s
LIMIT %(limit)s
"""


async def retrieve(
    principal: Principal,
    query: str,
    top_k: int = 5,
    oversample_factor: int = 10,
    use_reranker: bool = True,
    rerank_keep: int = 15,
) -> RetrievalResult:
    """Retrieve documents for `query`, filtered by `principal`'s permissions.

    Args:
        principal: Authenticated caller.
        query: Natural language query.
        top_k: Used only to compute the embedding-stage oversample size.
            The returned `allowed` list is NOT truncated; the caller
            handles display-time slicing.
        oversample_factor: Embedding stage fetches top_k * this many candidates.
        use_reranker: If True, cross-encoder reranks before permission filter.
        rerank_keep: After reranking, keep this many before permission filter.

    Returns:
        RetrievalResult with all allowed (audit-accurate) and denied docs.
    """
    query_emb = embed_query(query)
    fetch_limit = top_k * oversample_factor

    async with get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(SEARCH_SQL, {"q": query_emb, "limit": fetch_limit})
            rows = await cur.fetchall()
            columns = [desc[0] for desc in cur.description]

    # Build (doc, similarity, rerank_score) tuples
    triples: list[tuple[dict, float, float | None]] = []
    for row in rows:
        doc = dict(zip(columns, row))
        similarity = float(doc.pop("similarity"))
        triples.append((doc, similarity, None))

    # Optional rerank stage
    if use_reranker and triples:
        docs_only = [t[0] for t in triples]
        sim_lookup = {t[0]["id"]: t[1] for t in triples}
        reranked = cross_encoder_rerank(query, docs_only)[:rerank_keep]
        triples = [
            (doc, sim_lookup[doc["id"]], rerank_score)
            for doc, rerank_score in reranked
        ]

    # Permission filter — record ALL decisions, no truncation
    allowed: list[ScoredDocument] = []
    denied: list[ScoredDocument] = []
    for doc, similarity, rerank_score in triples:
        decision = can_read(principal, doc)
        scored = ScoredDocument(
            id=doc["id"],
            title=doc["title"],
            body=doc["body"],
            sub_type=doc["sub_type"],
            similarity=similarity,
            decision=decision,
            rerank_score=rerank_score,
        )
        if decision.is_allowed:
            allowed.append(scored)
        else:
            denied.append(scored)

    return RetrievalResult(allowed=allowed, denied=denied)
"""Permission-aware document retrieval.

Post-filter pattern:
1. Vector search retrieves top_k * oversample_factor candidates from pgvector
2. Each candidate is evaluated by can_read(principal, doc)
3. Allowed up to top_k returned; denied recorded for audit

Trade-off: post-filter is simple but can return fewer than top_k if many
candidates are denied. Pre-filter (encoding policy as SQL WHERE) is faster
at scale but much more complex. For this demo, post-filter is sufficient
and pedagogically clearer.
"""

from permission_aware_rag.auth.dependencies import Principal
from permission_aware_rag.db.session import get_connection
from permission_aware_rag.permission.policy import can_read
from permission_aware_rag.retrieval.embedder import embed_query
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
    oversample_factor: int = 5,
) -> RetrievalResult:
    """Retrieve documents matching `query`, filtered by `principal`'s permissions.

    Args:
        principal: Authenticated caller (from JWT).
        query: Natural language query.
        top_k: How many allowed documents to return.
        oversample_factor: How much to oversample so post-filter can still
            return top_k after denials. Total retrieved = top_k * oversample.

    Returns:
        RetrievalResult with `allowed` (visible to caller) and `denied`
        (filtered out — recorded for audit).
    """
    query_emb = embed_query(query)
    fetch_limit = top_k * oversample_factor

    async with get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(SEARCH_SQL, {"q": query_emb, "limit": fetch_limit})
            rows = await cur.fetchall()
            columns = [desc[0] for desc in cur.description]

    allowed: list[ScoredDocument] = []
    denied: list[ScoredDocument] = []

    for row in rows:
        doc = dict(zip(columns, row))
        similarity = float(doc.pop("similarity"))
        decision = can_read(principal, doc)

        scored = ScoredDocument(
            id=doc["id"],
            title=doc["title"],
            body=doc["body"],
            sub_type=doc["sub_type"],
            similarity=similarity,
            decision=decision,
        )

        if decision.is_allowed:
            allowed.append(scored)
        else:
            denied.append(scored)

    return RetrievalResult(allowed=allowed[:top_k], denied=denied)
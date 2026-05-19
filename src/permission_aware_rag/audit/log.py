"""Audit log writer for permission-aware RAG queries.

Every query — including unauthorized attempts and partial denials — is
recorded for compliance, security investigation, and access pattern analysis.
"""

from permission_aware_rag.db.session import get_connection


INSERT_AUDIT_SQL = """
INSERT INTO audit_log (
    user_id, user_role, query,
    retrieved_doc_ids, granted_doc_ids, denied_doc_ids,
    audit_engagement_id
) VALUES (
    %(user_id)s, %(user_role)s, %(query)s,
    %(retrieved)s, %(granted)s, %(denied)s,
    %(engagement)s
)
"""


async def write_audit_log(
    user_id: str,
    user_role: str,
    query: str,
    retrieved_doc_ids: list[str],
    granted_doc_ids: list[str],
    denied_doc_ids: list[str],
    audit_engagement_id: str | None = None,
) -> None:
    """Record a query and its permission outcome to audit_log table."""
    async with get_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                INSERT_AUDIT_SQL,
                {
                    "user_id": user_id,
                    "user_role": user_role,
                    "query": query,
                    "retrieved": retrieved_doc_ids,
                    "granted": granted_doc_ids,
                    "denied": denied_doc_ids,
                    "engagement": audit_engagement_id,
                },
            )
            await conn.commit()
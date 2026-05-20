"""Permission-aware /query endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from permission_aware_rag.audit.log import write_audit_log
from permission_aware_rag.auth.dependencies import Principal, get_current_principal
from permission_aware_rag.retrieval.retriever import retrieve


router = APIRouter(prefix="/query", tags=["query"])


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5


class DocumentResult(BaseModel):
    id: str
    title: str
    body: str
    sub_type: str
    similarity: float
    rerank_score: float | None = None


class QueryResponse(BaseModel):
    query: str
    results: list[DocumentResult]
    total_retrieved: int
    total_allowed: int
    total_denied: int
    total_displayed: int


@router.post("", response_model=QueryResponse)
async def query_documents(
    request: QueryRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> QueryResponse:
    """Retrieve documents matching the query, filtered by principal's permissions.

    Every query is recorded to audit_log regardless of outcome.
    Counts reflect the full set of permission decisions, not just displayed docs.
    """
    result = await retrieve(principal, request.query, top_k=request.top_k)

    # Audit log captures ALL permission decisions, regardless of display
    await write_audit_log(
        user_id=principal.user_id,
        user_role=principal.role,
        query=request.query,
        retrieved_doc_ids=[d.id for d in result.allowed + result.denied],
        granted_doc_ids=[d.id for d in result.allowed],
        denied_doc_ids=[d.id for d in result.denied],
        audit_engagement_id=principal.audit_engagement_id,
    )

    # Display-time truncation — separate from permission evaluation
    displayed = result.allowed[:request.top_k]

    return QueryResponse(
        query=request.query,
        results=[
            DocumentResult(
                id=d.id,
                title=d.title,
                body=d.body,
                sub_type=d.sub_type,
                similarity=d.similarity,
                rerank_score=d.rerank_score,
            )
            for d in displayed
        ],
        total_retrieved=len(result.allowed) + len(result.denied),
        total_allowed=len(result.allowed),
        total_denied=len(result.denied),
        total_displayed=len(displayed),
    )
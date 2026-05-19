"""Permission-aware query endpoint.

Wires together: JWT auth → permission-aware retrieval → audit logging.
This is the public API entry point for end users.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from permission_aware_rag.audit.log import write_audit_log
from permission_aware_rag.auth.dependencies import Principal, get_current_principal
from permission_aware_rag.retrieval.retriever import retrieve

router = APIRouter(prefix="/query", tags=["query"])


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


class DocumentResult(BaseModel):
    id: str
    title: str
    body: str
    sub_type: str
    similarity: float


class QueryResponse(BaseModel):
    query: str
    results: list[DocumentResult]
    total_retrieved: int
    total_allowed: int
    total_denied: int


@router.post("", response_model=QueryResponse)
async def query_documents(
    request: QueryRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> QueryResponse:
    """Retrieve documents matching the query, filtered by principal's permissions.

    Every query is recorded to audit_log regardless of outcome.
    """
    result = await retrieve(principal, request.query, top_k=request.top_k)

    await write_audit_log(
        user_id=principal.user_id,
        user_role=principal.role,
        query=request.query,
        retrieved_doc_ids=[d.id for d in result.allowed + result.denied],
        granted_doc_ids=[d.id for d in result.allowed],
        denied_doc_ids=[d.id for d in result.denied],
        audit_engagement_id=principal.audit_engagement_id,
    )

    return QueryResponse(
        query=request.query,
        results=[
            DocumentResult(
                id=d.id,
                title=d.title,
                body=d.body,
                sub_type=d.sub_type,
                similarity=d.similarity,
            )
            for d in result.allowed
        ],
        total_retrieved=len(result.allowed) + len(result.denied),
        total_allowed=len(result.allowed),
        total_denied=len(result.denied),
    )
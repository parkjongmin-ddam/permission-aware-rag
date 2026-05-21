"""Permission-aware /answer endpoint.

Same retrieval + permission pipeline as /query, plus an LLM generation step:

    retrieve -> rerank -> can_read() filter -> ALLOWED docs only -> LLM

The language model only ever sees documents the principal may read.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from permission_aware_rag.audit.log import write_audit_log
from permission_aware_rag.auth.dependencies import Principal, get_current_principal
from permission_aware_rag.generation.answerer import generate_answer
from permission_aware_rag.retrieval.retriever import retrieve


router = APIRouter(prefix="/answer", tags=["answer"])


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    top_k: int = 5
    use_reranker: bool = True


class CitedDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    sub_type: str


class AnswerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    answer: str
    refused: bool
    cited_documents: list[CitedDocument]
    context_doc_ids: list[str]
    total_allowed: int
    total_denied: int


@router.post("", response_model=AnswerResponse)
async def answer_question(
    request: AnswerRequest,
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> AnswerResponse:
    """Answer grounded only in documents the principal may read."""
    result = await retrieve(
        principal,
        request.query,
        top_k=request.top_k,
        use_reranker=request.use_reranker,
    )

    await write_audit_log(
        user_id=principal.user_id,
        user_role=principal.role,
        query=request.query,
        retrieved_doc_ids=[d.id for d in result.allowed + result.denied],
        granted_doc_ids=[d.id for d in result.allowed],
        denied_doc_ids=[d.id for d in result.denied],
        audit_engagement_id=principal.audit_engagement_id,
    )

    context_docs = result.allowed[: request.top_k]
    answer = await generate_answer(request.query, context_docs)

    by_id = {d.id: d for d in context_docs}
    cited = [
        CitedDocument(id=d.id, title=d.title, sub_type=d.sub_type)
        for doc_id in answer.cited_doc_ids
        if (d := by_id.get(doc_id)) is not None
    ]

    return AnswerResponse(
        query=request.query,
        answer=answer.text,
        refused=answer.refused,
        cited_documents=cited,
        context_doc_ids=answer.context_doc_ids,
        total_allowed=len(result.allowed),
        total_denied=len(result.denied),
    )

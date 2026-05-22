"""LLM answer generation over permission-filtered documents.

The generation half of the RAG pipeline. It only ever sees documents that have
already passed can_read():

    retrieve() -> can_read() filter -> allowed docs -> generate_answer()

so a document the principal may not read can never enter the LLM context.
"""

from dataclasses import dataclass

from langchain_anthropic import ChatAnthropic

from permission_aware_rag.config import settings
from permission_aware_rag.retrieval.types import ScoredDocument


_MAX_CONTEXT_DOCS = 8
_MAX_BODY_CHARS = 2000

_SYSTEM_PROMPT = """You are a careful enterprise document assistant.

Rules you must follow:
1. Answer ONLY using the provided documents. Do not use outside knowledge.
2. If the documents do not contain enough information to answer, say so plainly.
   Do not guess or fabricate.
3. Cite the document id (e.g. [DOC-012]) inline after each claim it supports.
4. Be concise and factual. Match the language of the user's question.

You will receive a set of documents the user is authorized to read, followed by
their question. Documents outside the user's permission have already been removed
before they reach you - never speculate about documents you cannot see."""


@dataclass(frozen=True)
class Answer:
    text: str
    cited_doc_ids: list[str]
    context_doc_ids: list[str]
    refused: bool


def _build_context(docs: list[ScoredDocument]) -> str:
    blocks: list[str] = []
    for d in docs[:_MAX_CONTEXT_DOCS]:
        body = d.body[:_MAX_BODY_CHARS]
        if len(d.body) > _MAX_BODY_CHARS:
            body += " ...(truncated)"
        blocks.append(f"[{d.id}] {d.title}\n{body}")
    return "\n\n---\n\n".join(blocks)


def _extract_cited_ids(text: str, candidate_ids: list[str]) -> list[str]:
    return [doc_id for doc_id in candidate_ids if f"[{doc_id}]" in text]


async def generate_answer(query: str, allowed_docs: list[ScoredDocument]) -> Answer:
    """Generate an answer grounded ONLY in allowed_docs (already permission-filtered)."""
    context_ids = [d.id for d in allowed_docs[:_MAX_CONTEXT_DOCS]]

    if not allowed_docs:
        return Answer(
            text=(
                "I can't answer this from the documents you have access to. "
                "No readable documents matched your query."
            ),
            cited_doc_ids=[],
            context_doc_ids=[],
            refused=True,
        )

    context = _build_context(allowed_docs)
    user_message = (
        f"Documents you are authorized to read:\n\n{context}\n\n"
        f"---\n\nQuestion: {query}"
    )

    # --- LLM backend (single swap point) ---
    # Cloud demo uses the Claude API (claude-sonnet-4-6).
    #
    # DESIGN INTENT - air-gapped / API-restricted deployment:
    # This project primarily targets enterprise environments where outbound LLM
    # API calls or data exfiltration are controlled (network isolation, DLP,
    # API-key governance). This is the ONE place that changes for such a
    # deployment: replace ChatAnthropic with an on-prem backend - e.g. Ollama
    # serving a local model (Qwen2.5 / Llama 3.1) via langchain-ollama's
    # ChatOllama. Everything else (retrieval, the 6-rule permission filter,
    # citation extraction) is unchanged.
    #
    # Why this matters: the permission filter runs BEFORE this call, so no
    # document outside the principal's permission ever reaches ANY LLM - cloud
    # or local. The permission boundary doubles as a data-egress control point.
    llm = ChatAnthropic(
        model=settings.answer_model,
        api_key=settings.anthropic_api_key,
        max_tokens=settings.answer_max_tokens,
        temperature=0,
    )
    response = await llm.ainvoke(
        [
            ("system", _SYSTEM_PROMPT),
            ("human", user_message),
        ]
    )

    text = response.content if isinstance(response.content, str) else str(response.content)
    cited = _extract_cited_ids(text, context_ids)

    return Answer(
        text=text,
        cited_doc_ids=cited,
        context_doc_ids=context_ids,
        refused=False,
    )
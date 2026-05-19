"""Ingest documents.yaml into pgvector with BGE-M3 embeddings.

Usage:
    uv run python scripts/ingest.py

First run downloads BGE-M3 (~2GB) from HuggingFace, cached locally.
Subsequent runs use cache and skip the download.
"""

import asyncio
from pathlib import Path

import psycopg
import yaml
from pgvector.psycopg import register_vector_async
from sentence_transformers import SentenceTransformer

from permission_aware_rag.config import settings


EMBEDDING_MODEL = "BAAI/bge-m3"
DOCUMENTS_FILE = Path(__file__).parent.parent / "data" / "documents.yaml"


INSERT_SQL = """
INSERT INTO documents (
    id, title, category, sub_type, sensitivity, language,
    body, embedding,
    subject, project_id, project_members, parties,
    case_id, stakeholders, severity, executive_briefed,
    disclosure_level, tags, expected_readers
) VALUES (
    %(id)s, %(title)s, %(category)s, %(sub_type)s,
    %(sensitivity)s, %(language)s, %(body)s, %(embedding)s,
    %(subject)s, %(project_id)s, %(project_members)s, %(parties)s,
    %(case_id)s, %(stakeholders)s, %(severity)s, %(executive_briefed)s,
    %(disclosure_level)s, %(tags)s, %(expected_readers)s
)
ON CONFLICT (id) DO UPDATE SET
    title             = EXCLUDED.title,
    category          = EXCLUDED.category,
    sub_type          = EXCLUDED.sub_type,
    sensitivity       = EXCLUDED.sensitivity,
    language          = EXCLUDED.language,
    body              = EXCLUDED.body,
    embedding         = EXCLUDED.embedding,
    subject           = EXCLUDED.subject,
    project_id        = EXCLUDED.project_id,
    project_members   = EXCLUDED.project_members,
    parties           = EXCLUDED.parties,
    case_id           = EXCLUDED.case_id,
    stakeholders      = EXCLUDED.stakeholders,
    severity          = EXCLUDED.severity,
    executive_briefed = EXCLUDED.executive_briefed,
    disclosure_level  = EXCLUDED.disclosure_level,
    tags              = EXCLUDED.tags,
    expected_readers  = EXCLUDED.expected_readers,
    updated_at        = now()
"""


def load_embedder() -> SentenceTransformer:
    """Load BGE-M3. First call downloads ~2GB from HuggingFace."""
    print(f"Loading embedding model: {EMBEDDING_MODEL}")
    print("(First run downloads ~2GB; cached locally for next time.)")
    model = SentenceTransformer(EMBEDDING_MODEL)
    print(f"  Model loaded. Dimension: {model.get_embedding_dimension()}")
    return model


def load_documents() -> list[dict]:
    """Load documents.yaml and return the document list."""
    print(f"\nLoading documents from: {DOCUMENTS_FILE}")
    with open(DOCUMENTS_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    documents = data["documents"]
    print(f"  Loaded {len(documents)} documents")
    return documents


def generate_embeddings(model: SentenceTransformer, documents: list[dict]):
    """Generate normalized dense embeddings for document bodies."""
    print("\nGenerating embeddings...")
    texts = [doc["body"] for doc in documents]
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=True,
        batch_size=8,
    )
    print(f"  Generated {len(embeddings)} embeddings, shape={embeddings.shape}")
    return embeddings


async def insert_documents(documents, embeddings) -> tuple[int, int, int]:
    """Insert documents with embeddings into pgvector (upsert on conflict)."""
    print("\nConnecting to database...")
    async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
        await register_vector_async(conn)
        print("  Connected and pgvector type registered")

        inserted = 0
        failed = 0
        async with conn.cursor() as cur:
            for doc, embedding in zip(documents, embeddings):
                try:
                    await cur.execute(
                        INSERT_SQL,
                        {
                            "id": doc["id"],
                            "title": doc["title"],
                            "category": doc["category"],
                            "sub_type": doc["sub_type"],
                            "sensitivity": doc["sensitivity"],
                            "language": doc["language"],
                            "body": doc["body"],
                            "embedding": embedding,
                            "subject": doc.get("subject"),
                            "project_id": doc.get("project_id"),
                            "project_members": doc.get("project_members"),
                            "parties": doc.get("parties"),
                            "case_id": doc.get("case_id"),
                            "stakeholders": doc.get("stakeholders"),
                            "severity": doc.get("severity"),
                            "executive_briefed": doc.get("executive_briefed"),
                            "disclosure_level": doc.get("disclosure_level"),
                            "tags": doc.get("tags"),
                            "expected_readers": doc["expected_readers"],
                        },
                    )
                    inserted += 1
                except Exception as exc:
                    print(f"  Failed to insert {doc['id']}: {type(exc).__name__}: {exc}")
                    failed += 1
            await conn.commit()

        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM documents")
            row = await cur.fetchone()
            total = row[0] if row else 0

    return inserted, failed, total


async def verify_search(model: SentenceTransformer) -> None:
    """Run a sample similarity search to verify the pipeline."""
    print("\n--- Verification: similarity search ---")
    queries = [
        "휴가 정책이 어떻게 되나요?",
        "프로덕션 장애 대응 절차",
        "보안 사고 보고서",
    ]

    async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
        await register_vector_async(conn)
        for query in queries:
            print(f"\nQuery: {query}")
            query_emb = model.encode(query, normalize_embeddings=True)
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT id, title, sub_type,
                           1 - (embedding <=> %(q)s) AS similarity
                    FROM documents
                    ORDER BY embedding <=> %(q)s
                    LIMIT 3
                    """,
                    {"q": query_emb},
                )
                rows = await cur.fetchall()
            for row in rows:
                doc_id, title, sub_type, sim = row
                print(f"  {doc_id} [{sub_type}] sim={sim:.3f} — {title}")


async def main() -> None:
    print("=" * 70)
    print("BWCorp Permission-aware RAG: Document Ingestion")
    print("=" * 70)

    model = load_embedder()
    documents = load_documents()
    embeddings = generate_embeddings(model, documents)
    inserted, failed, total = await insert_documents(documents, embeddings)

    print(f"\nResults:")
    print(f"  Inserted/updated: {inserted}")
    print(f"  Failed:           {failed}")
    print(f"  Total in DB:      {total}")

    if total > 0:
        await verify_search(model)

    print("\n" + "=" * 70)
    print("Ingestion complete!")
    print("=" * 70)


if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
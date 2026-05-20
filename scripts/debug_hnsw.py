"""Diagnose why retrieve() sees fewer candidates than fetch_limit.

Hypothesis: pgvector HNSW with default ef_search returns fewer rows than
LIMIT when the dataset is small and the query is specific.
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import psycopg
from pgvector.psycopg import register_vector_async

from permission_aware_rag.config import settings
from permission_aware_rag.retrieval.embedder import embed_query


async def main():
    print("Loading embedder...")
    query_emb = embed_query("휴가 정책이 어떻게 되나요?")

    async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
        await register_vector_async(conn)

        # Total docs
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM documents")
            total = (await cur.fetchone())[0]
        print(f"\nTotal documents in DB: {total}\n")

        # Show current ef_search
        async with conn.cursor() as cur:
            await cur.execute("SHOW hnsw.ef_search")
            ef = (await cur.fetchone())[0]
        print(f"Current hnsw.ef_search = {ef}\n")

        # Try various LIMITs with default ef_search
        print("Default ef_search behavior:")
        for limit in [5, 10, 13, 15, 20, 30, 45, 50, 100]:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT COUNT(*) FROM (SELECT id FROM documents "
                    "ORDER BY embedding <=> %(q)s LIMIT %(l)s) sub",
                    {"q": query_emb, "l": limit},
                )
                count = (await cur.fetchone())[0]
            mark = " ← MATCH OUR 13!" if count == 13 else ""
            print(f"  LIMIT {limit:4d} → returned {count:4d}{mark}")

        # Bump ef_search and retry
        print("\nWith ef_search = 100:")
        for limit in [13, 15, 30, 45, 50, 100]:
            async with conn.cursor() as cur:
                await cur.execute("SET LOCAL hnsw.ef_search = 100")
                await cur.execute(
                    "SELECT COUNT(*) FROM (SELECT id FROM documents "
                    "ORDER BY embedding <=> %(q)s LIMIT %(l)s) sub",
                    {"q": query_emb, "l": limit},
                )
                count = (await cur.fetchone())[0]
            print(f"  LIMIT {limit:4d} → returned {count:4d}")

        # Sequential scan baseline (no index)
        print("\nSequential scan (bypass index):")
        async with conn.cursor() as cur:
            await cur.execute("SET LOCAL enable_indexscan = off")
            await cur.execute("SET LOCAL enable_bitmapscan = off")
            await cur.execute(
                "SELECT COUNT(*) FROM (SELECT id FROM documents "
                "ORDER BY embedding <=> %(q)s LIMIT 30) sub",
                {"q": query_emb},
            )
            count = (await cur.fetchone())[0]
        print(f"  LIMIT 30 → returned {count:4d}  (without HNSW index)")


if __name__ == "__main__":
    asyncio.run(main())
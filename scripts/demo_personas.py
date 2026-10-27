"""3-persona (or all-persona) permission demo without the HTTP server.

Calls the same retrieve() used by /query, so counts match the API. Runs on a
SelectorEventLoop because psycopg async does not support Windows'
ProactorEventLoop (which uvicorn uses by default on Windows).

Usage:
    uv run python scripts/demo_personas.py
    uv run python scripts/demo_personas.py "ExternalCo dispute litigation"
"""

import asyncio
import sys

from permission_aware_rag.auth.dependencies import Principal
from permission_aware_rag.auth.personas import PERSONAS
from permission_aware_rag.db.session import close_pool, init_pool
from permission_aware_rag.retrieval.retriever import retrieve

QUERY = sys.argv[1] if len(sys.argv) > 1 else "ExternalCo dispute litigation"
TOP_K = 5


async def main() -> None:
    await init_pool()
    try:
        print(f"query: {QUERY!r}  top_k={TOP_K}\n")
        for uid, p in PERSONAS.items():
            principal = Principal(
                user_id=p["user_id"],
                role=p["role"],
                dept=p.get("dept"),
                audit_engagement_id=p.get("audit_engagement_id"),
            )
            r = await retrieve(principal, QUERY, top_k=TOP_K)
            shown = [d.id for d in r.allowed[:TOP_K]]
            has44 = "O" if "DOC-044" in shown else "X"
            print(f"{uid:15s} | allowed {len(r.allowed):2d} / denied {len(r.denied):2d}"
                  f" | DOC-044: {has44} | docs: [{', '.join(shown)}]")
            print(f"{'':15s}   allowed_all: {[d.id for d in r.allowed]}")
            print(f"{'':15s}   denied_all : "
                  f"{[(d.id, d.decision.rule_name) for d in r.denied]}")
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)

"""Manual smoke test for permission-aware retrieval (Stage 4.3).

Run: uv run python scripts/test_retrieval.py
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from permission_aware_rag.auth.dependencies import Principal
from permission_aware_rag.db.session import close_pool, init_pool
from permission_aware_rag.retrieval.retriever import retrieve


def print_result(label, result):
    print(f"\n=== {label} ===")
    print(f"Allowed: {len(result.allowed)}, Denied: {len(result.denied)}")
    for d in result.allowed:
        print(f"  ALLOW [{d.sub_type}] sim={d.similarity:.3f} {d.id} — {d.title}")
    for d in result.denied[:3]:
        print(f"  DENY  [{d.sub_type}] sim={d.similarity:.3f} {d.id} — {d.decision.reason}")


async def main():
    await init_pool()

    # Test 1: Employee searches HR
    emp = Principal(user_id="user_emp_001", role="employee", dept="engineering")
    result = await retrieve(emp, "휴가 정책", top_k=3)
    print_result("Employee query: 휴가 정책", result)

    # Test 2: Contractor searches projects
    ext = Principal(user_id="user_ext_001", role="contractor", dept=None)
    result = await retrieve(ext, "project architecture", top_k=3)
    print_result("Contractor query: project architecture", result)

    # Test 3: Auditor sees almost everything
    aud = Principal(
        user_id="user_aud_001",
        role="auditor",
        dept="external",
        audit_engagement_id="AUDIT-2026-SOC2-001",
    )
    result = await retrieve(aud, "재무 보고서", top_k=3)
    print_result("Auditor query: 재무 보고서", result)

    await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
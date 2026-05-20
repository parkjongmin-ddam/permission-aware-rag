"""A/B comparison: cross-encoder rerank ON vs OFF.

Issues two queries for each test case — one with use_reranker=False,
one with use_reranker=True — and shows the top-K side by side.
Demonstrates where rerank changes the ordering of cosine-similarity
results.
"""

import httpx


BASE = "http://127.0.0.1:8000"
TOP_K = 3


def login(user_id: str) -> str:
    r = httpx.post(f"{BASE}/auth/mock-login", json={"user_id": user_id})
    r.raise_for_status()
    return r.json()["access_token"]


def query(token: str, q: str, use_reranker: bool) -> dict:
    r = httpx.post(
        f"{BASE}/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": q, "top_k": TOP_K, "use_reranker": use_reranker},
        timeout=120.0,
    )
    r.raise_for_status()
    return r.json()


def format_doc(d: dict, idx: int, show_rerank: bool) -> list[str]:
    """Build 3 lines representing one document in the comparison column."""
    sim = d["similarity"]
    rerank = d.get("rerank_score")

    rank_id = f"#{idx + 1} {d['id']} [{d['sub_type']}]"
    if show_rerank and rerank is not None:
        score = f"   sim={sim:.3f}  rerank={rerank:+.3f}"
    else:
        score = f"   sim={sim:.3f}"
    title = f"   {d['title'][:38]}"

    return [rank_id, score, title]


def compare(query_text: str, user_id: str) -> None:
    token = login(user_id)
    without = query(token, query_text, use_reranker=False)
    with_rr = query(token, query_text, use_reranker=True)

    header = "=" * 96
    print(f"\n{header}")
    print(f"Query: {query_text}")
    print(f"User:  {user_id}")
    print(header)
    print(f"  {'EMBEDDING ONLY':^44} | {'EMBEDDING + RERANK':^44}")
    print(f"  {'-' * 44}-+-{'-' * 44}")

    diffs = 0
    for i in range(TOP_K):
        left = without["results"][i] if i < len(without["results"]) else None
        right = with_rr["results"][i] if i < len(with_rr["results"]) else None

        if left and right and left["id"] != right["id"]:
            diffs += 1
            marker = "  ▶"
        else:
            marker = "   "

        left_lines = format_doc(left, i, show_rerank=False) if left else ["", "", ""]
        right_lines = format_doc(right, i, show_rerank=True) if right else ["", "", ""]

        for j, (ll, rl) in enumerate(zip(left_lines, right_lines)):
            prefix = marker if j == 0 else "   "
            print(f"  {ll:<42}{prefix} | {rl:<44}")
        print(f"  {'-' * 44}-+-{'-' * 44}")

    print(f"\n  Ranking changed: {diffs}/{TOP_K} positions")
    print(
        f"  Total allowed (audit-accurate): "
        f"w/o={without['total_allowed']},  w/={with_rr['total_allowed']}"
    )
    print(
        f"  Total retrieved (after rerank stage): "
        f"w/o={without['total_retrieved']},  w/={with_rr['total_retrieved']}"
    )


def main():
    print("\n" + "M3.2: A/B Comparison — Cross-encoder Rerank vs Cosine-only".center(96))

    # Diverse personas + categories + languages
    cases = [
        ("휴가 정책이 어떻게 되나요?", "user_emp_001"),
        ("project deliverables and architecture", "user_ext_001"),
        ("expense and finance report", "user_aud_001"),
        ("프로덕션 장애 대응 절차", "user_emp_001"),
        ("security incident database breach", "user_sec_001"),
    ]

    for q, uid in cases:
        compare(q, uid)


if __name__ == "__main__":
    main()
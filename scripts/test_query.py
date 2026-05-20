"""HTTP smoke test for /query endpoint with rerank visibility."""

import httpx


BASE = "http://127.0.0.1:8000"


def main():
    r = httpx.post(f"{BASE}/auth/mock-login", json={"user_id": "user_emp_001"})
    r.raise_for_status()
    token = r.json()["access_token"]

    r = httpx.post(
        f"{BASE}/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "휴가 정책이 어떻게 되나요?", "top_k": 3},
        timeout=60.0,
    )
    r.raise_for_status()
    data = r.json()

    print(f"Query: {data['query']}")
    print(f"Retrieved: {data['total_retrieved']}, Allowed: {data['total_allowed']}, Denied: {data['total_denied']}\n")
    for doc in data["results"]:
        sim = doc["similarity"]
        rerank = doc.get("rerank_score")
        rerank_str = f"rerank={rerank:+.3f}" if rerank is not None else "rerank=n/a"
        print(f"  [{doc['sub_type']}] sim={sim:.3f} {rerank_str} {doc['id']} — {doc['title']}")


if __name__ == "__main__":
    main()
"""HTTP smoke test for /query endpoint with Korean support."""

import httpx


BASE = "http://127.0.0.1:8000"


def main():
    # Login
    r = httpx.post(f"{BASE}/auth/mock-login", json={"user_id": "user_emp_001"})
    r.raise_for_status()
    token = r.json()["access_token"]

    # Query (Korean)
    r = httpx.post(
        f"{BASE}/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "휴가 정책이 어떻게 되나요?", "top_k": 3},
    )
    r.raise_for_status()
    data = r.json()

    print(f"Query: {data['query']}")
    print(f"Retrieved: {data['total_retrieved']}, Allowed: {data['total_allowed']}, Denied: {data['total_denied']}\n")
    for doc in data["results"]:
        print(f"  [{doc['sub_type']}] sim={doc['similarity']:.3f} {doc['id']} — {doc['title']}")


if __name__ == "__main__":
    main()
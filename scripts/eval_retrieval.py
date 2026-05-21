"""RAGAS-style evaluation: precision@K and recall@K with vs without reranker.

Ground truth is computed by calling the actual can_read() policy — the same
function the production retriever uses. This avoids the heuristic-mismatch
problem of using documents.yaml's expected_readers field as proxy (which
misses rbac_default and other rule-based grants).
"""

import sys
from pathlib import Path

import httpx
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from permission_aware_rag.auth.dependencies import Principal
from permission_aware_rag.auth.personas import PERSONAS
from permission_aware_rag.permission.policy import can_read


BASE = "http://127.0.0.1:8000"


def load_dataset() -> tuple[list[dict], dict]:
    with open(PROJECT_ROOT / "eval" / "dataset.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["test_cases"], data.get("config", {"top_k": 5})


def load_documents() -> dict[str, dict]:
    """Returns {doc_id: full_doc_dict} from documents.yaml."""
    with open(PROJECT_ROOT / "data" / "documents.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {d["id"]: d for d in data["documents"]}


def get_principal(user_id: str) -> Principal:
    """Construct Principal from the PERSONAS registry.

    PERSONAS has fewer fields than Principal (audit_engagement_id is only
    on auditors; raw_claims isn't stored at all). Fill missing ones with
    None / empty dict.
    """
    p = PERSONAS[user_id]
    return Principal(
        user_id=p["user_id"],
        role=p["role"],
        dept=p.get("dept"),
        audit_engagement_id=p.get("audit_engagement_id"),
        raw_claims=p.get("raw_claims", {}),
    )


def compute_truth(
    persona_id: str,
    relevant_doc_ids: list[str],
    docs_by_id: dict[str, dict],
) -> set[str]:
    """Truth = relevant docs that the actual policy allows for this persona."""
    principal = get_principal(persona_id)
    truth = set()
    for doc_id in relevant_doc_ids:
        doc = docs_by_id.get(doc_id)
        if doc and can_read(principal, doc).is_allowed:
            truth.add(doc_id)
    return truth


def login(user_id: str) -> str:
    r = httpx.post(
        f"{BASE}/auth/mock-login",
        json={"user_id": user_id},
        timeout=30.0,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def query(token: str, q: str, use_reranker: bool, top_k: int) -> list[str]:
    r = httpx.post(
        f"{BASE}/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": q, "top_k": top_k, "use_reranker": use_reranker},
        timeout=120.0,
    )
    r.raise_for_status()
    return [d["id"] for d in r.json()["results"]]


def precision(retrieved: list[str], truth: set[str]) -> float:
    if not retrieved:
        return 0.0
    return len(set(retrieved) & truth) / len(retrieved)


def recall(retrieved: list[str], truth: set[str]) -> float:
    if not truth:
        return float("nan")  # undefined — skip in aggregation
    return len(set(retrieved) & truth) / len(truth)


def main():
    cases, config = load_dataset()
    docs_by_id = load_documents()
    top_k = config["top_k"]

    print(f"\n{'=' * 96}")
    print(f"  M3.3: RAGAS-style Retrieval Evaluation — top_k={top_k}")
    print(f"  Cases: {len(cases)}, Personas tested: "
          f"{sum(len(c['personas']) for c in cases)}")
    print(f"  Ground truth: actual can_read() policy")
    print(f"{'=' * 96}\n")

    rows = []

    for case in cases:
        for persona in case["personas"]:
            truth = compute_truth(persona, case["relevant_docs"], docs_by_id)

            token = login(persona)
            retrieved_off = query(token, case["query"], False, top_k)
            retrieved_on = query(token, case["query"], True, top_k)

            p_off, r_off = precision(retrieved_off, truth), recall(retrieved_off, truth)
            p_on, r_on = precision(retrieved_on, truth), recall(retrieved_on, truth)

            rows.append({
                "case_id": case["id"], "persona": persona,
                "truth": truth,
                "p_off": p_off, "r_off": r_off,
                "p_on": p_on, "r_on": r_on,
            })

            print(f"[{case['id']}] {case['query'][:50]:50s} × {persona}")
            truth_str = ", ".join(sorted(truth)) if truth else "(empty — persona has no relevant access)"
            print(f"   Truth ({len(truth)}): {truth_str}")
            print(f"   W/o rerank: {retrieved_off}")
            if truth:
                print(f"               P={p_off:.2f} R={r_off:.2f}")
            else:
                print(f"               (no truth — case skipped in aggregate)")
            print(f"   W/  rerank: {retrieved_on}")
            if truth:
                print(f"               P={p_on:.2f} R={r_on:.2f}")
            else:
                print(f"               (no truth — case skipped in aggregate)")
            print()

    eligible = [r for r in rows if r["truth"]]
    n = len(eligible)

    if n == 0:
        print("No eligible cases. Check dataset labels vs personas.")
        return

    avg = {
        "p_off": sum(r["p_off"] for r in eligible) / n,
        "r_off": sum(r["r_off"] for r in eligible) / n,
        "p_on": sum(r["p_on"] for r in eligible) / n,
        "r_on": sum(r["r_on"] for r in eligible) / n,
    }

    print("=" * 96)
    print(f"  AGGREGATE — {n} eligible cases (truth non-empty)")
    print("=" * 96)
    print(f"\n  {'metric':<14} {'w/o rerank':<13} {'w/ rerank':<13} {'delta':<10}")
    print(f"  {'-' * 14} {'-' * 13} {'-' * 13} {'-' * 10}")
    print(f"  {f'precision@{top_k}':<14} "
          f"{avg['p_off']:<13.3f} {avg['p_on']:<13.3f} "
          f"{avg['p_on'] - avg['p_off']:+.3f}")
    print(f"  {f'recall@{top_k}':<14} "
          f"{avg['r_off']:<13.3f} {avg['r_on']:<13.3f} "
          f"{avg['r_on'] - avg['r_off']:+.3f}")

    def f1(p, r):
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    f1_off, f1_on = f1(avg["p_off"], avg["r_off"]), f1(avg["p_on"], avg["r_on"])
    print(f"  {'F1':<14} {f1_off:<13.3f} {f1_on:<13.3f} {f1_on - f1_off:+.3f}")
    print()


if __name__ == "__main__":
    main()
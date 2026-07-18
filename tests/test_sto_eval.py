"""Guards the STO eval cases in eval/dataset.yaml.

Verifies each TC-STO case's ground truth (computed by the real can_read policy,
exactly as scripts/eval_retrieval.py does) exhibits the intended permission gradient —
without needing the live retrieval stack.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from permission_aware_rag.auth.dependencies import Principal
from permission_aware_rag.permission.policy import can_read

_ROOT = Path(__file__).resolve().parents[1]


def _docs() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for name in ("documents.yaml", "sto_chapter.yaml"):
        p = _ROOT / "data" / name
        if p.exists():
            for d in yaml.safe_load(p.read_text(encoding="utf-8"))["documents"]:
                out[d["id"]] = d
    return out


def _sto_cases() -> dict[str, dict]:
    ds = yaml.safe_load((_ROOT / "eval" / "dataset.yaml").read_text(encoding="utf-8"))
    return {c["id"]: c for c in ds["test_cases"] if c["id"].startswith("TC-STO")}


def _truth(role_user: str, relevant: list[str], docs: dict[str, dict]) -> set[str]:
    principal = Principal(user_id=role_user, role=role_user, dept=None)
    return {i for i in relevant
            if (d := docs.get(i)) and can_read(principal, d).is_allowed}


DOCS = _docs()
CASES = _sto_cases()


def test_sto_cases_present() -> None:
    assert set(CASES) == {"TC-STO-01", "TC-STO-02", "TC-STO-03"}


def test_public_sto_case_readable_by_all_listed_personas() -> None:
    # TC-STO-01 / TC-STO-03 reference public STO docs → every RBAC role sees all.
    for cid in ("TC-STO-01", "TC-STO-03"):
        rel = CASES[cid]["relevant_docs"]
        for role in ("employee", "team_lead", "contractor"):
            assert _truth(role, rel, DOCS) == set(rel), f"{cid}/{role}"


def test_internal_sto_case_is_permission_differentiated() -> None:
    # TC-STO-02 references internal STO docs → the whole point: gated.
    rel = CASES["TC-STO-02"]["relevant_docs"]
    assert _truth("employee", rel, DOCS) == set()      # denied
    assert _truth("contractor", rel, DOCS) == set()    # denied
    assert _truth("team_lead", rel, DOCS) == set(rel)  # allowed
    assert _truth("executive", rel, DOCS) == set(rel)  # allowed


def test_relevant_docs_exist_in_corpus() -> None:
    for cid, case in CASES.items():
        for doc_id in case["relevant_docs"]:
            assert doc_id in DOCS, f"{cid} references missing {doc_id}"

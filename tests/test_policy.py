"""Permission engine regression tests on the main corpus (data/documents.yaml).

No DB or embeddings needed: these exercise can_read() directly.

Two layers:
1. Targeted cases for the sub-type refinements (data-spec 4.3).
2. A corpus sweep: for every refined sub-type, no persona may be granted a
   document that its expected_readers label does not list. This is checked
   against the labels in documents.yaml, not against can_read() itself, so a
   policy over-grant is caught instead of being treated as ground truth.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from permission_aware_rag.auth.dependencies import Principal
from permission_aware_rag.auth.personas import PERSONAS
from permission_aware_rag.permission.policy import can_read
from permission_aware_rag.permission.rules import SUBTYPE_READERS

_DOCS_PATH = Path(__file__).resolve().parents[1] / "data" / "documents.yaml"
DOCS = {d["id"]: d for d in yaml.safe_load(_DOCS_PATH.read_text(encoding="utf-8"))["documents"]}


def _principal(user_id: str) -> Principal:
    p = PERSONAS[user_id]
    return Principal(
        user_id=p["user_id"],
        role=p["role"],
        dept=p.get("dept"),
        audit_engagement_id=p.get("audit_engagement_id"),
    )


def _allowed(user_id: str, doc_id: str) -> bool:
    return can_read(_principal(user_id), DOCS[doc_id]).is_allowed


# ─── 1. Targeted cases ───────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("user_id", "doc_id", "expected"),
    [
        # hr.personnel: subject + hr_specialist only
        ("user_emp_001", "DOC-006", True),    # own record
        ("user_hrs_001", "DOC-006", True),
        ("user_exec_001", "DOC-006", False),
        ("user_sec_001", "DOC-006", False),
        ("user_tl_001", "DOC-006", False),    # someone else's record
        # finance.expense: subject only (+ auditor via audit_rule)
        ("user_emp_001", "DOC-030", True),
        ("user_aud_001", "DOC-030", True),
        ("user_exec_001", "DOC-030", False),
        ("user_hrs_001", "DOC-030", False),
        ("user_sec_001", "DOC-030", False),
        # hr.compensation
        ("user_exec_001", "DOC-004", True),
        ("user_hrs_001", "DOC-004", True),
        ("user_sec_001", "DOC-004", False),
        ("user_tl_001", "DOC-004", False),
        # hr.recruitment
        ("user_tl_001", "DOC-008", True),
        ("user_sec_001", "DOC-008", False),
        # security.threat_intel / compliance
        ("user_sec_001", "DOC-014", True),
        ("user_exec_001", "DOC-014", False),
        ("user_hrs_001", "DOC-014", False),
        ("user_hrs_001", "DOC-015", False),
        # finance.statement / budget
        ("user_exec_001", "DOC-028", True),
        ("user_hrs_001", "DOC-028", False),
        ("user_sec_001", "DOC-026", False),
    ],
)
def test_subtype_refinements(user_id: str, doc_id: str, expected: bool) -> None:
    assert _allowed(user_id, doc_id) is expected


def test_unlisted_role_gets_explicit_deny_reason() -> None:
    decision = can_read(_principal("user_sec_001"), DOCS["DOC-004"])
    assert not decision.is_allowed
    assert decision.rule_name == "subtype_restriction"


def test_privileged_litigation_memo_still_blocked_for_auditor() -> None:
    # DOC-044 is the demo's key document; the refinement must not change it.
    assert not _allowed("user_aud_001", "DOC-044")
    assert not _allowed("user_emp_001", "DOC-044")


# ─── 2. Corpus sweep: no over-grant on refined sub-types ─────────────────────

def _over_grants() -> list[tuple[str, str, str]]:
    found = []
    for doc in DOCS.values():
        if doc["sub_type"] not in SUBTYPE_READERS:
            continue
        readers = set(doc.get("expected_readers") or [])
        for user_id, persona in PERSONAS.items():
            # Auditor access is governed by audit_rule (evaluated first, by
            # design) and is checked separately in the targeted cases.
            if persona["role"] == "auditor":
                continue
            if not _allowed(user_id, doc["id"]):
                continue
            if persona["role"] not in readers and user_id not in readers:
                found.append((user_id, doc["id"], doc["sub_type"]))
    return found


def test_no_over_grant_on_refined_subtypes() -> None:
    assert _over_grants() == []

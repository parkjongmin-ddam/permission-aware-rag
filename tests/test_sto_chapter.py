"""STO chapter integration tests.

Verifies the STO legal chapter (adapted from sto-rag) is served correctly by THIS
project's real 6-rule permission engine — no DB or embeddings needed, the integration
point is the permission decision.

Mapping: STO view-tiers → sensitivity (general/legal → public, engineer → internal),
so public STO reference is readable by all roles while internal STO engineering
commentary is gated to team_lead and above.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from permission_aware_rag.auth.dependencies import Principal
from permission_aware_rag.permission.policy import can_read

_STO = Path(__file__).resolve().parents[1] / "data" / "sto_chapter.yaml"

if not _STO.exists():
    pytest.skip("STO chapter not generated (run scripts/adapt_sto_chapter.py)",
                allow_module_level=True)

_DOCS = yaml.safe_load(_STO.read_text(encoding="utf-8"))["documents"]
_PUBLIC = next(d for d in _DOCS if d["sensitivity"] == "public")
_INTERNAL = next(d for d in _DOCS if d["sensitivity"] == "internal")


def _p(role: str) -> Principal:
    return Principal(user_id=f"u_{role}", role=role, dept=None)


def test_chapter_shape() -> None:
    assert len(_DOCS) == 96
    sens = {d["sensitivity"] for d in _DOCS}
    assert sens == {"public", "internal"}
    for d in _DOCS:  # conform to the ingest-required schema
        for f in ("id", "title", "category", "sub_type", "sensitivity",
                  "language", "body", "expected_readers"):
            assert d.get(f), f"{d.get('id')} missing {f}"
        assert d["category"] == "legal"
        assert d["sub_type"] in {"legal.regulatory", "legal.opinion"}


def test_public_sto_readable_by_all_rbac_roles() -> None:
    for role in ("employee", "team_lead", "executive", "security_officer",
                 "hr_specialist", "contractor"):
        assert can_read(_p(role), _PUBLIC).is_allowed, f"{role} denied public STO"


def test_internal_sto_gated_to_team_lead_and_above() -> None:
    # Denied to the {public}-only roles
    for role in ("employee", "contractor"):
        assert not can_read(_p(role), _INTERNAL).is_allowed, \
            f"{role} should NOT read internal STO"
    # Allowed to roles whose default includes 'internal'
    for role in ("team_lead", "executive", "security_officer", "hr_specialist"):
        assert can_read(_p(role), _INTERNAL).is_allowed, \
            f"{role} should read internal STO"


def test_sto_decision_flows_through_sensitivity_rule() -> None:
    # legal.regulatory/opinion abstain in parties_rule → sensitivity_rule decides.
    d = can_read(_p("employee"), _PUBLIC)
    assert d.rule_name == "sensitivity"

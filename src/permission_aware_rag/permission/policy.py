"""Permission policy orchestrator.

Evaluates rules in priority order, returning the first decision. If no rule
fires, defaults to deny (closed-world assumption).
"""

from typing import Callable, Optional

from permission_aware_rag.auth.dependencies import Principal
from permission_aware_rag.permission.rules import (
    audit_rule,
    incident_rule,
    parties_rule,
    project_rule,
    rbac_default,
    self_access_rule,
)
from permission_aware_rag.permission.types import PolicyDecision

# Type alias: a rule takes (principal, document) and returns a decision
# or None if the rule does not apply to this document.
Rule = Callable[[Principal, dict], Optional[PolicyDecision]]


# Rule registry — evaluated in order. Earlier rules take precedence.
# Order matters: audit_rule first (auditor override), conditional rules in
# the middle (self/project/parties/incident), rbac_default last as catch-all.
RULES: list[Rule] = [
    audit_rule,             # 4.2.4 - highest priority: auditor with engagement_id
    self_access_rule,       # 4.2.2 - self-grant for hr.personnel / finance.expense
    project_rule,           # 4.2.2 - tech.project strict ABAC (no role override)
    parties_rule,           # 4.2.3 - legal.* case parties
    incident_rule,          # 4.2.3 - security.incident ReBAC + role gates
    rbac_default,           # 4.2.4 - lowest priority: role-based catch-all
]


def can_read(principal: Principal, document: dict) -> PolicyDecision:
    """Evaluate whether `principal` can read `document`.

    Walks the rule registry in order. The first rule to return a non-None
    decision wins. If no rule fires, returns a default deny.

    Args:
        principal: Authenticated caller's identity (from JWT).
        document: Document dict from pgvector — must contain at minimum
            'id', 'category', 'sub_type'. Conditional fields (subject,
            project_members, parties, stakeholders, etc.) are checked
            per-rule when present.

    Returns:
        PolicyDecision with explicit allow/deny effect, the name of the
        rule that fired, and a human-readable reason.
    """
    for rule in RULES:
        decision = rule(principal, document)
        if decision is not None:
            return decision

    # No rule fired — closed-world default deny.
    return PolicyDecision.deny(
        rule_name="default",
        reason=(
            f"no rule matched for role={principal.role}, "
            f"sub_type={document.get('sub_type')}"
        ),
    )
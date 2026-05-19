"""Permission policy orchestrator.

Evaluates rules in priority order, returning the first decision. If no rule
fires, defaults to deny (closed-world assumption).
"""

from typing import Callable, Optional

from permission_aware_rag.auth.dependencies import Principal
from permission_aware_rag.permission.rules import (
    incident_rule,
    parties_rule,
    project_rule,
    self_access_rule,
)
from permission_aware_rag.permission.types import PolicyDecision

# Type alias: a rule takes (principal, document) and returns a decision
# or None if the rule does not apply to this document.
Rule = Callable[[Principal, dict], Optional[PolicyDecision]]


# Rule registry — evaluated in order. Earlier rules take precedence.
RULES: list[Rule] = [
    # audit_rule will be inserted here in Stage 4.2.4 (highest priority —
    # auditor with engagement_id can override most denials).
    self_access_rule,       # 4.2.2 - hr.personnel, finance.expense self-grant
    project_rule,           # 4.2.2 - tech.project ABAC (strict)
    parties_rule,           # 4.2.3 - legal.* case parties
    incident_rule,          # 4.2.3 - security.incident ReBAC + role gates
    # rbac_default will be appended here in 4.2.4 (lowest priority — role
    # determines default category access for everything else).
]


def can_read(principal: Principal, document: dict) -> PolicyDecision:
    """Evaluate whether `principal` can read `document`.

    Walks the rule registry in order. The first rule to return a non-None
    decision wins. If no rule fires, returns a default deny.
    """
    for rule in RULES:
        decision = rule(principal, document)
        if decision is not None:
            return decision

    return PolicyDecision.deny(
        rule_name="default",
        reason=(
            f"no rule matched for role={principal.role}, "
            f"sub_type={document.get('sub_type')}"
        ),
    )
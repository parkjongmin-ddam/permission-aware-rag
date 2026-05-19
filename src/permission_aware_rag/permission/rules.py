"""Permission rules for the permission-aware RAG system.

Each rule is a pure function: (Principal, document_dict) -> Optional[PolicyDecision].

Convention:
- Return None when the rule does NOT apply to this document (let other
  rules decide). This is the "abstain" outcome.
- Return PolicyDecision.allow(...) for an explicit grant.
- Return PolicyDecision.deny(...) for an explicit block. Use sparingly —
  only when the rule's domain demands strict closure (project secrets,
  NDAs, security incidents).

Rule ordering is defined in policy.RULES, not here.
"""

from typing import Optional

from permission_aware_rag.auth.dependencies import Principal
from permission_aware_rag.permission.types import PolicyDecision


# ─────────────────────────────────────────────────────────────────────────────
# Stage 4.2.2 — Self-access + Project ABAC
# ─────────────────────────────────────────────────────────────────────────────

SELF_ACCESS_SUBTYPES: frozenset[str] = frozenset({"hr.personnel", "finance.expense"})


def self_access_rule(
    principal: Principal, document: dict
) -> Optional[PolicyDecision]:
    """Grant access when the principal is the subject of a personal document.

    Applies only to hr.personnel and finance.expense. Returns:
    - ALLOW if document.subject == principal.user_id (the document is about you)
    - None otherwise — let downstream rules decide (e.g., hr_specialist via RBAC)

    Note: we never DENY here. Non-subjects might still have legitimate access
    through their role (hr_specialist, executive). That decision belongs to
    the RBAC default rule.
    """
    if document.get("sub_type") not in SELF_ACCESS_SUBTYPES:
        return None

    subject = document.get("subject")
    if subject is None:
        # Defensive: missing subject metadata. Don't grant, but don't block
        # either — let other rules try, then default-deny if nothing fires.
        return None

    if subject == principal.user_id:
        return PolicyDecision.allow(
            rule_name="self_access",
            reason=(
                f"user is the subject of "
                f"{document.get('sub_type')} document {document.get('id')}"
            ),
        )

    # Subject mismatch — fall through (RBAC may still grant)
    return None


def project_rule(
    principal: Principal, document: dict
) -> Optional[PolicyDecision]:
    """Project membership ABAC for tech.project documents.

    Strict closure: only listed project_members can access. Even executives
    are denied if not on the project — this is intentional. Tech project
    confidentiality outranks role privilege.
    """
    if document.get("sub_type") != "tech.project":
        return None

    members = document.get("project_members") or []
    doc_id = document.get("id")
    project_id = document.get("project_id")

    if principal.user_id in members:
        return PolicyDecision.allow(
            rule_name="project_member",
            reason=f"user is a member of {project_id}",
        )

    return PolicyDecision.deny(
        rule_name="project_member",
        reason=(
            f"user not in project_members of {project_id} "
            f"(document {doc_id})"
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Stage 4.2.3 — Legal parties + Security incident ReBAC
# ─────────────────────────────────────────────────────────────────────────────

LEGAL_SUBTYPES: frozenset[str] = frozenset({"legal.contract", "legal.litigation"})


def parties_rule(
    principal: Principal, document: dict
) -> Optional[PolicyDecision]:
    """Grant case parties access to legal documents.

    - legal.contract: parties-only. Non-parties get explicit DENY (NDA closure).
    - legal.litigation: parties get ALLOW. Non-parties fall through to RBAC
      where disclosure_level + role decides further access.
    """
    sub_type = document.get("sub_type")
    if sub_type not in LEGAL_SUBTYPES:
        return None

    parties = document.get("parties") or []
    case_id = document.get("case_id")
    doc_id = document.get("id")

    if principal.user_id in parties:
        disclosure = document.get("disclosure_level", "internal")
        return PolicyDecision.allow(
            rule_name="legal_parties",
            reason=(
                f"user is party in {case_id} "
                f"(sub_type={sub_type}, disclosure={disclosure})"
            ),
        )

    # User is not a party
    if sub_type == "legal.contract":
        # Contracts are closed to non-parties
        return PolicyDecision.deny(
            rule_name="legal_parties",
            reason=f"user not in parties of contract {case_id} (document {doc_id})",
        )

    # legal.litigation: fall through — RBAC may grant access based on
    # disclosure_level (e.g., security_officer for 'restricted', etc.)
    return None


def incident_rule(
    principal: Principal, document: dict
) -> Optional[PolicyDecision]:
    """ReBAC + role-based access to security incidents.

    Multiple paths to ALLOW within this rule:
    1. Direct stakeholder (named in stakeholders array)
    2. security_officer role (institutional incident response visibility)
    3. Executive who has been briefed (executive_briefed == True)
    4. Critical-severity incident + executive role (mandatory escalation)

    Any other access is explicitly DENIED — security incidents are too
    sensitive to fall through to generic RBAC.
    """
    if document.get("sub_type") != "security.incident":
        return None

    stakeholders = document.get("stakeholders") or []
    severity = document.get("severity")
    executive_briefed = bool(document.get("executive_briefed", False))
    doc_id = document.get("id")

    # Path 1: Direct stakeholder (ReBAC)
    if principal.user_id in stakeholders:
        return PolicyDecision.allow(
            rule_name="incident",
            reason=f"user is named stakeholder in {doc_id}",
        )

    # Path 2: Security officer — broad institutional visibility
    if principal.role == "security_officer":
        return PolicyDecision.allow(
            rule_name="incident",
            reason=f"security_officer role grants visibility on {doc_id}",
        )

    # Path 3: Executive explicitly briefed on this incident
    if principal.role == "executive" and executive_briefed:
        return PolicyDecision.allow(
            rule_name="incident",
            reason=f"executive briefed on {doc_id}",
        )

    # Path 4: Critical incidents auto-escalate to executives
    if principal.role == "executive" and severity == "Critical":
        return PolicyDecision.allow(
            rule_name="incident",
            reason=f"executive auto-access on Critical incident {doc_id}",
        )

    # No path matched — explicit deny (incidents are closed by default)
    return PolicyDecision.deny(
        rule_name="incident",
        reason=(
            f"user has no relationship to incident {doc_id} "
            f"(role={principal.role}, severity={severity})"
        ),
    )
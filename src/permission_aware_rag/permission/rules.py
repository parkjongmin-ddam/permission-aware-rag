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


# ─────────────────────────────────────────────────────────────────────────────
# Stage 4.2.4 — Auditor special access + RBAC default matrix
# ─────────────────────────────────────────────────────────────────────────────


def audit_rule(
    principal: Principal, document: dict
) -> Optional[PolicyDecision]:
    """Auditor with active engagement gets read access to most documents.

    Exclusions (privacy/privilege boundaries even auditors cannot cross):
    - hr.personnel: personal HR records remain subject-only (privacy)
    - legal.litigation with disclosure_level='privileged': attorney-client
      privilege not waived by audit engagement.

    Auditors WITHOUT an engagement_id get no special access (fall through).
    """
    if principal.role != "auditor":
        return None

    if principal.audit_engagement_id is None:
        # Auditor not currently engaged — no special privilege
        return None

    sub_type = document.get("sub_type")

    # Exclusion 1: Personal HR records
    if sub_type == "hr.personnel":
        return None  # let self_access (which already ran) handle, or fall to default deny

    # Exclusion 2: Privileged litigation
    if sub_type == "legal.litigation":
        if document.get("disclosure_level") == "privileged":
            return PolicyDecision.deny(
                rule_name="audit",
                reason=(
                    f"auditor cannot access privileged litigation "
                    f"{document.get('case_id')} (attorney-client privilege)"
                ),
            )

    # Default: auditor gets oversight read access
    return PolicyDecision.allow(
        rule_name="audit",
        reason=(
            f"auditor with engagement {principal.audit_engagement_id} "
            f"(oversight read on {sub_type})"
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Stage 4.2.4 — RBAC default matrix
#
# M4.0 migration in progress (see docs/schema-drift-migration-plan.md):
# - LEGACY_ROLE_DEFAULTS: sub_type-keyed matrix used by rbac_default.
#   Will be deleted in Step 5 when the switch is flipped.
# - ROLE_DEFAULTS: new sensitivity-keyed matrix used by sensitivity_rule.
#   Currently dormant — sensitivity_rule is defined but NOT wired into
#   policy.RULES yet.
#
# During Steps 1-4 the system behaves identically to pre-migration:
# rbac_default reads from LEGACY_ROLE_DEFAULTS, sensitivity_rule is unused.
# ─────────────────────────────────────────────────────────────────────────────


# LEGACY (sub_type-keyed) — used by rbac_default until Step 5.
#
# Background: designed with sensitivity-based sub_type vocabulary
# (.handbook, .public, .documentation, .internal, ...) intended to describe
# document exposure levels. The data layer was later instantiated with
# topic-based sub_type vocabulary (.policy, .recruitment, .architecture, ...)
# describing document content. As a result, several entries below reference
# sub_types that don't exist in data, and several real data sub_types have
# no role assignment. M3.3 eval surfaced this drift quantitatively.
LEGACY_ROLE_DEFAULTS: dict[str, frozenset[str]] = {
    "employee": frozenset({
        "hr.policy", "hr.handbook",
        "tech.runbook", "tech.documentation",
        "marketing.public",
        "legal.public",
    }),
    "team_lead": frozenset({
        # employee defaults + team lead additions
        "hr.policy", "hr.handbook",
        "tech.runbook", "tech.documentation",
        "marketing.public", "marketing.internal",
        "legal.public",
        "finance.budget",  # budget visibility for planning
    }),
    "executive": frozenset({
        # broad strategic access
        "hr.policy", "hr.handbook",
        "tech.runbook", "tech.documentation",
        "marketing.public", "marketing.internal", "marketing.campaign",
        "legal.public", "legal.contract", "legal.opinion",
        "finance.budget", "finance.statement", "finance.forecast",
    }),
    "security_officer": frozenset({
        # security incidents handled by incident_rule
        "hr.policy",
        "tech.runbook", "tech.documentation",
        "legal.public", "legal.contract",
        "marketing.public",
        "security.policy", "security.audit", "security.training",
    }),
    "hr_specialist": frozenset({
        "hr.policy", "hr.handbook", "hr.personnel", "hr.training",
        "marketing.public",
        "legal.public", "legal.contract",  # employment contracts
    }),
    "contractor": frozenset({
        # Project access handled by project_rule
        "marketing.public",
    }),
    "auditor": frozenset(),  # auditor uses audit_rule exclusively
}


# NEW (sensitivity-keyed) — activated in Step 5 via sensitivity_rule.
# Each role declares the maximum sensitivity it can read by default;
# more specialized access still flows through upstream ABAC rules.
ROLE_DEFAULTS: dict[str, frozenset[str]] = {
    "employee":         frozenset({"public"}),
    "team_lead":        frozenset({"public", "internal"}),
    "executive":        frozenset({"public", "internal", "restricted"}),
    "security_officer": frozenset({"public", "internal", "restricted"}),
    "hr_specialist":    frozenset({"public", "internal", "restricted"}),
    "contractor":       frozenset({"public"}),
    "auditor":          frozenset(),  # audit_rule exclusively
}


def rbac_default(
    principal: Principal, document: dict
) -> Optional[PolicyDecision]:
    """Role-based catch-all access for unmatched documents.

    Last rule in the pipeline. If a role has the document's sub_type listed
    in LEGACY_ROLE_DEFAULTS, allow. Otherwise, fall through (which means
    default deny in the orchestrator).

    M4.0 migration note: reads from LEGACY_ROLE_DEFAULTS, not ROLE_DEFAULTS.
    Will be replaced by sensitivity_rule in Step 5.
    """
    sub_type = document.get("sub_type")
    allowed = LEGACY_ROLE_DEFAULTS.get(principal.role, frozenset())

    if sub_type in allowed:
        return PolicyDecision.allow(
            rule_name="rbac_default",
            reason=f"role {principal.role} has default access to {sub_type}",
        )

    return None


def sensitivity_rule(
    principal: Principal, document: dict
) -> Optional[PolicyDecision]:
    """Role-based access by document sensitivity level.

    Replaces the legacy sub_type-keyed LEGACY_ROLE_DEFAULTS matrix in Step 5.
    Each role declares the maximum sensitivity it can read by default; more
    specialized access still flows through upstream ABAC rules.

    Status: dormant until permission/policy.py:RULES is updated in Step 5.
    """
    sensitivity = document.get("sensitivity")
    if sensitivity is None:
        return None  # documents without sensitivity → no default access

    allowed = ROLE_DEFAULTS.get(principal.role, frozenset())
    if sensitivity in allowed:
        return PolicyDecision.allow(
            rule_name="sensitivity",
            reason=(
                f"role {principal.role} reads {sensitivity} documents "
                f"(sub_type={document.get('sub_type')})"
            ),
        )
    return None
"""Predefined personas for mock login.

Each persona represents a distinct role + department + access context,
used to demostrate permission-aware retrieval. In production these
would come from an IdP(ADFS, Okta, Cognito).
"""

from typing import TypedDict

class Persona(TypedDict, total=False):
    user_id: str
    role: str
    dept: str | None
    audit_engagement_id: str | None

PERSONAS: dict[str, Persona] = {
    "user_emp_001": {
        "user_id": "user_emp_001",
        "role": "employee",
        "dept": "engineering",
    },
    "user_emp_002": {
        "user_id": "user_emp_002",
        "role": "employee",
        "dept": "marketing",
    },
    "user_emp_003": {
        "user_id": "user_emp_003",
        "role": "employee",
        "dept": "engineering",
    },
    "user_tl_001": {
        "user_id": "user_tl_001",
        "role": "team_lead",
        "dept": "engineering",
    },
    "user_exec_001": {
        "user_id": "user_exec_001",
        "role": "executive",
        "dept": "executive",
    },
    "user_sec_001": {
        "user_id": "user_sec_001",
        "role": "security_officer",
        "dept": "security",
    },
    "user_ext_001": {
        "user_id": "user_ext_001",
        "role": "contractor",
        "dept": None,
    },
    "user_aud_001": {
        "user_id": "user_aud_001",
        "role": "auditor",
        "dept": "external",
        "audit_engagement_id": "AUDIT-2026-SOC2-001",
    },
    "user_hrs_001": {
        "user_id": "user_hrs_001",
        "role": "hr_specialist",
        "dept": "hr",
    },
}
"""JWT issuance and validation utilities.

In production, JWT signing keys would come from a secure KMS (AWS KMS,
HashiCorp Vault). For this portfolio demo, we use a static secret loaded
from environment via Settings.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from permission_aware_rag.config import settings


def encode_token(
    user_id: str,
    role: str,
    dept: str | None = None,
    expires_in: timedelta | None = None,
    **extra_claims: Any,
) -> str:
    """Issue a signed JWT for a user.

    Args:
        user_id: Stable user identifier (e.g., "user_emp_001"). Becomes 'sub' claim.
        role: One of {employee, team_lead, executive, security_officer,
                      contractor, auditor, hr_specialist}.
        dept: Department code; None for cross-org roles like auditor.
        expires_in: Token validity. Defaults to settings.jwt_expire_minutes.
        **extra_claims: Additional claims (e.g., audit_engagement_id for auditors).
    """
    if expires_in is None:                                          # ← 4칸 들여쓰기
        expires_in = timedelta(minutes=settings.jwt_expire_minutes) # ← 8칸

    now = datetime.now(timezone.utc)                                # ← 4칸
    payload: dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": now + expires_in,
    }
    if dept is not None:                                            # ← is not None
        payload["dept"] = dept
    payload.update(extra_claims)

    return jwt.encode(                                              # ← 4칸
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> dict[str, Any]:                     # ← decode (오타 수정)
    """Validate signature/expiry and return decoded claims.

    Raises jwt.ExpiredSignatureError if expired.                    # ← Raises (3인칭)
    Raises jwt.InvalidTokenError for any other validation failure.
    """
    return jwt.decode(                                              # ← 4칸 들여쓰기
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
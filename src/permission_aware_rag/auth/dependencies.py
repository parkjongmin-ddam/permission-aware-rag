"""FastAPI dependencies for authentication."""

from dataclasses import dataclass, field
from typing import Annotated, Any

import jwt
from fastapi import Header, HTTPException, status

from permission_aware_rag.auth.jwt_utils import decode_token

@dataclass(frozen=True)
class Principal:
    """The authenticated caller's identity and permission context.

    Built from a decoded JWT. Immutable (frozen=True) to prevent accidental
    mutation during permission filtering downstream.
    """

    user_id: str                                              # ← 4칸
    role: str                                                 # ← 4칸
    dept: str | None = None                                   # ← 4칸
    audit_engagement_id: str | None = None                    # ← 4칸
    raw_claims: dict[str, Any] = field(default_factory=dict)  # ← 4칸


def get_current_principal(
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    """..."""
    if authorization is None:
        raise HTTPException(...)
    
    scheme, _, token = authorization.partition(" ")           # ← " " 한 칸
    if scheme.lower() != "bearer" or not token:               # ← 따옴표 위치
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must be 'Bearer <token>'",
        )
    
    try:
        claims = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(...)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",                   # ← f-string 한 줄
        )

    return Principal(
        user_id=claims["sub"],
        role=claims["role"],
        dept=claims.get("dept"),
        audit_engagement_id=claims.get("audit_engagement_id"),
        raw_claims=claims,
    )
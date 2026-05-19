"""Mock authentication endpoint for permission-aware RAG demo.

In production, replace with real OIDC/SAML flow (ADFS, Okta, Cognito). For
demo purposes, we issue JWTs for predefined personas without password
verification — this is acceptable for a portfolio demonstration but must
never be used in a real system.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from permission_aware_rag.auth.jwt_utils import encode_token
from permission_aware_rag.auth.personas import PERSONAS

router = APIRouter(prefix="/auth", tags=["auth"])


class MockLoginRequest(BaseModel):
    user_id: str


class MockLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    persona: dict


@router.get("/personas")
async def list_personas() -> dict:
    """List available persona user_ids and their attributes."""
    return {"personas": PERSONAS}


@router.post("/mock-login", response_model=MockLoginResponse)
async def mock_login(request: MockLoginRequest) -> MockLoginResponse:
    """Issue a JWT for a predefined persona. NOT for production use."""
    persona = PERSONAS.get(request.user_id)
    if persona is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Unknown user_id: {request.user_id}. "
                f"Valid personas: {list(PERSONAS.keys())}"
            ),
        )

    extra_claims = {
        k: v
        for k, v in persona.items()
        if k not in {"user_id", "role", "dept"} and v is not None
    }
    token = encode_token(
        user_id=persona["user_id"],
        role=persona["role"],
        dept=persona.get("dept"),
        **extra_claims,
    )
    return MockLoginResponse(access_token=token, persona=dict(persona))
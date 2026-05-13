"""FastAPI application entry points."""

from fastapi import FastAPI

from permission_aware_rag.api.routes import health
from permission_aware_rag.config import settings

app = FastAPI(
    title="Permission-aware-RAG",
    description=(
        "A LangGraup-based RAG system with multi-dimensional permission filtering"
        "(RBAC + ReBAC + ABAC)"        
    ),
    version="0.1.0"
)

#Routers
app.include_router(health.router)

@app.get("/")
async def root() -> dict[str,str]:
    """Root endpoint - basic service identification."""
    return {
        "service": "permission-aware-rag",
        "version": "0.1.0",
        "environment": settings.environment,
    }
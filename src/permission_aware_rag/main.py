"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from permission_aware_rag.api.routes import auth, health, query   # ← auth 추가
from permission_aware_rag.config import settings
from permission_aware_rag.db.session import close_pool, init_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle — DB pool + embedder preload."""
    await init_pool()
    # Preload embedder so first /query isn't slow (loading takes ~10-30s)
    from permission_aware_rag.retrieval.embedder import get_embedder
    from permission_aware_rag.retrieval.reranker import get_reranker
    get_embedder()
    get_reranker()
    yield
    await close_pool()


app = FastAPI(
    title="Permission-aware RAG",
    description=(
        "A LangGraph-based RAG system with multi-dimensional permission filtering "
        "(RBAC + ReBAC + ABAC)."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# Routers
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(query.router)


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint — basic service identification."""
    return {
        "service": "permission-aware-rag",
        "version": "0.1.0",
        "environment": settings.environment,
    }
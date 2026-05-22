"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from permission_aware_rag.api.routes import answer, auth, health, query
from permission_aware_rag.config import settings
from permission_aware_rag.db.session import close_pool, init_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - DB pool + embedder preload."""
    await init_pool()
    from permission_aware_rag.retrieval.embedder import get_embedder
    from permission_aware_rag.retrieval.reranker import get_reranker

    get_embedder()
    get_reranker()
    yield
    await close_pool()


app = FastAPI(
    title="Permission-aware RAG",
    description=(
        "A permission-aware RAG system with multi-dimensional access control "
        "(RBAC + ReBAC + ABAC). Permission filtering sits between retrieval and generation."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow the static demo UI (demo/chat.html) to call the API from a
# browser. In development we allow any origin for convenience (local file://
# or a local static server). In other environments, origins are restricted to
# an explicit allow-list from settings (cors_allow_origins), so a deployed API
# only accepts the demo origins you opt in to — consistent with the
# API-restricted posture of the rest of the project.
_is_dev = settings.environment.lower() in {"development", "dev", "local", "test"}
if _is_dev:
    _allow_origins = ["*"]
else:
    _allow_origins = settings.cors_allow_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(query.router)
app.include_router(answer.router)


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint - basic service identification."""
    return {
        "service": "permission-aware-rag",
        "version": "0.1.0",
        "environment": settings.environment,
    }
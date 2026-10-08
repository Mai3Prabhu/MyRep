from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.routes.profiles import router as profiles_router
from app.api.routes.documents import profile_documents_router, documents_router
from app.api.routes.public import router as public_router
from app.api.routes.voice import router as voice_router
from app.db.database import engine, Base
from app.db.migrations import ensure_document_status_columns, ensure_profile_visibility_column

# Import all models so SQLAlchemy registers them with Base before create_all runs.
import app.db.models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan: run startup tasks before accepting requests.

    MySQL: create all tables if they don't exist yet, then run lightweight
           column migrations for existing installations.
    Qdrant: ensure the `myrep_knowledge` collection exists.
            If QDRANT_URL is not configured, the Qdrant step is silently
            skipped so the server can still start for development/testing.
    """
    # MySQL table creation (will be replaced by Alembic migrations later).
    Base.metadata.create_all(bind=engine)

    # Layer 2.9: add indexing status columns to existing documents tables.
    # On fresh installs, create_all already includes these columns — the
    # migration is a no-op. On existing installs it adds the missing columns.
    ensure_document_status_columns(engine)

    # Layer 4: add is_public column to existing profiles tables.
    ensure_profile_visibility_column(engine)

    # Qdrant collection initialization (Layer 2.5).
    # Import here to avoid circular imports and to allow running tests
    # without a live Qdrant instance.
    from app.services import qdrant_service
    qdrant_service.ensure_collection()

    yield
    # Nothing to clean up on shutdown in this layer.


app = FastAPI(
    title="MyRep API",
    description=(
        "Layers 1–8 — Professional Profile Backend with Grounded RAG, "
        "Public Recruiter View, LangGraph orchestration, controlled contact, "
        "Sarvam voice, conversation-aware retrieval, and evaluation/observability"
    ),
    version="0.14.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profiles_router, prefix="/api/v1")
app.include_router(profile_documents_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(public_router, prefix="/api/v1")
app.include_router(voice_router, prefix="/api/v1")


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    """Simple liveness check — confirms the server is running."""
    return {"status": "ok"}

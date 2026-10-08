from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import settings


# The engine is the low-level connection to PostgreSQL.
# pool_pre_ping=True makes SQLAlchemy test the connection before use,
# which handles dropped connections gracefully.
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

# SessionLocal is a factory that produces individual database sessions.
# autocommit=False means we control when to commit transactions.
# autoflush=False prevents SQLAlchemy from flushing changes before every query.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """
    All SQLAlchemy ORM models will inherit from this Base class.
    It gives SQLAlchemy the metadata it needs to create/manage tables.
    """
    pass


def get_db():
    """
    FastAPI dependency that provides a database session per request.
    The session is always closed when the request finishes, even if an error occurs.

    Usage in a route:
        def my_route(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
